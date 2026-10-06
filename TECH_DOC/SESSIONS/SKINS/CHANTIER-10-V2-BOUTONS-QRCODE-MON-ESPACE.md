# CHANTIER 10 — Skin V2 : remettre les boutons de paiement QR code dans « Mon espace »

**Date :** 2026-10-06
**Statut :** spec à valider — rien n'est codé.
**Skin concerné :** V2 (DA v1). Le skin classic n'est touché que par les défauts D1, D2 et D4,
qui vivent dans des gabarits partagés.

---

## 0. À lire en premier : les défauts corrigés au passage

Ces défauts ont été trouvés en creusant. Aucun n'est la cause de la régression, mais ils sont
sur le même chemin de code et se corrigent dans le même chantier. Le mainteneur a donné son
accord pour les corriger, à condition qu'ils soient annoncés **avant** le code.

### D1 — `tirelire_section.html` a perdu son enveloppe

**Fichier :** `BaseBillet/templates/htmx/views/my_account/tirelire_section.html`

Le commit `71fe1225` (2026-06-15, « Update tirelire_section.html with changes from
Lespass/main ») a supprimé :

- l'ouverture `<section class="card mb-3 pt-3" id="tirelire-section">`,
- le titre « My balance » et son paragraphe d'introduction,
- le `hx-target="#tirelire-section"` du bouton de recharge,
- le `data-testid="refill-btn-open"` et les `aria-hidden="true"` sur les icônes.

Il a laissé un `</section>` **orphelin** en fin de fichier (ligne 142). Le navigateur le
tolère, mais le HTML est invalide.

Conséquences :
- La route `MyAccount.tirelire_section` (`BaseBillet/views.py:1251`) n'a plus aucun appelant.
  Elle servait à un bouton « Annuler » d'un formulaire de recharge qui n'existe plus :
  `refill_wallet` renvoie aujourd'hui un `HttpResponseClientRedirect` vers Stripe, sans formulaire.
- Les commentaires de `pages/classic/vues/compte/balance.html` (l. 26-31), de
  `pages/V2/vues/compte/balance.html` (l. 13-14 et 42-45) et la docstring de la route parlent
  d'un `#tirelire-section` qui n'existe plus.

**Correction :**
1. Supprimer le `</section>` orphelin.
2. Supprimer la route morte `MyAccount.tirelire_section`. Aucun test ne l'appelle (vérifié par
   `rg tirelire_section tests/`).
3. Réécrire les commentaires des deux `balance.html` au présent, sans `#tirelire-section`.
4. Remettre `aria-hidden="true"` sur les icônes `bi-*` du partiel.

On ne restaure **pas** le titre « My balance » ni l'enveloppe `<section>` : le skin classic
s'affiche ainsi depuis juin et personne ne l'a signalé. Restaurer changerait l'écran de
classic, hors périmètre.

### D2 — Le scanner a une branche morte et un repli qui répond 405

**Fichier :** `BaseBillet/templates/fonctionnel/qrcode_scan_pay/scanner.html` (partagé par
tous les skins)

- La branche `{% if qrcode_processed %}` (l. 10-28) n'est jamais affichée : aucune vue ne
  pose `qrcode_processed` dans le contexte (vérifié par `rg qrcode_processed`).
- Quand le contenu scanné **n'est pas une URL** (`new URL()` lève une exception), le JS
  soumet le formulaire `#form-qrcode-scan` en `hx-post` vers `qrcodescanpay-get-scanner`.
  Cette action n'accepte que `GET` → **405**. htmx (1.9.12) ne swappe pas une réponse 4xx ;
  les deux shells ne forcent le swap que des 404 et 500 (`pages/V2/shell.html:200-207`,
  `classic/shell.html:194-201`), pas du 405. L'utilisateur voit « Automatically submitting
  QR code... » puis plus rien.

**Correction :**
1. Supprimer la branche `qrcode_processed`, le formulaire `#form-qrcode-scan` et le
   `{% if not qrcode_processed %}` autour du script.
2. Quand le contenu scanné n'est pas une URL : afficher dans `#scan-result-container` un
   message lisible (« Ce QR code n'est pas un QR code de paiement TiBillet. ») et laisser
   l'utilisateur relancer la caméra avec le bouton « Start Camera » déjà présent.
3. Les deux autres cas ne changent pas : même domaine → redirection directe ; autre domaine
   → `/login/<b64>/redirect_session_to_another_tenant/`. Cette dernière vue vérifie que le
   domaine appartient à un lieu TiBillet (`Domain.objects.filter(domain=host)`) : pas de
   redirection ouverte.

### D3 — Le bouton d'encaissement ne suit pas la même règle que la permission

- **Affichage** (gabarits actuels) : `profile.admin_this_tenant or profile.can_initiate_payment`.
- **Permission** des routes (`CanInitiatePaymentPermissionWithRequest`,
  `ApiBillet/permissions.py:117`) : compte **actif**, **humain**, et
  (`is_superuser` **ou** admin du lieu **ou** droit `initiate_payment` sur le lieu).

Écart concret : un superuser qui n'est pas dans `client_admin` du lieu peut encaisser, mais
ne voit pas le bouton. (Un compte désactivé ne pose pas de problème en pratique : sa session
n'est plus authentifiée, il n'atteint pas `/my_account/`.)

**Correction :** la vue calcule **un seul booléen** avec la fonction de la permission, et
les gabarits le lisent :

```python
# Le bouton d'encaissement suit EXACTEMENT la regle de la permission des routes.
# Si on recalcule la regle dans le gabarit, les deux finissent par diverger.
# / The collect button follows EXACTLY the route permission rule.
from ApiBillet.permissions import CanInitiatePaymentPermissionWithRequest
template_context['peut_initier_un_paiement'] = CanInitiatePaymentPermissionWithRequest(request)
```

Ce booléen est posé dans `MyAccount.list` (index V2) **et** dans `MyAccount.balance`
(balance classic, qui garde son bandeau).

### D4 — Le bouton gris « email non validé » recharge la page

Sur main comme ici, la variante « Please valid your email to scan a payment QR Code » est un
`<a href="">`. Un clic recharge la page, sans rien expliquer.

**Correction :** garder **le même aspect gris et le même libellé**, mais en élément non
cliquable : `<button type="button" class="… " disabled>`. Le lien « renvoyer l'email
d'activation » existe déjà en tête de page (`account_base.html`), on n'en ajoute pas.
S'applique au nouveau bouton V2 **et** au partiel partagé (classic).

---

## 1. Le problème

Le commit `eb519112` (2026-09-12) a retiré le raccourci « My wallet » de la liste « Mon compte »
de `pages/templates/pages/V2/vues/compte/index.html`. La page `/my_account/balance/` reste
atteignable par le lien « Historique », mais **seulement si une carte est liée** (`{% if card %}`).

Or deux fonctions n'existent **que** sur cette page :

| Fonction | Pour qui | Route |
|---|---|---|
| Initier un paiement (QR code, lien de paiement, carte NFC) | admins et caissier·es du lieu | `qrcodescanpay-get-generator` |
| Scanner un QR code de paiement | tout compte à l'email validé | `qrcodescanpay-get-scanner` |

Sans carte liée, ces deux fonctions sont **inaccessibles**. Avec une carte, il faut deviner
qu'elles se cachent derrière « Historique ».

Les tests n'ont rien vu : ils appellent les routes en direct (`page.request.post(...)`),
jamais par un clic, et aucun ne vérifie la présence des boutons.

Les pages de paiement elles-mêmes (`fonctionnel/qrcode_scan_pay/*.html`) sont **identiques à
main**, à part leurs chemins statiques. Ce chantier ne touche que les points d'entrée.

## 2. Ce que les utilisateurs connaissent (main, skin `reunion`)

Sur main, les deux boutons sont dans `reunion/views/account/balance.html`, atteinte par la
tuile « My wallet » de l'index :

- **Initier un paiement** : bandeau `alert alert-info` pleine largeur (fond bleu clair),
  texte « Vous pouvez initier un paiement pour le compte de votre collectif : {organisation} »,
  à droite un bouton `btn btn-warning square-btn` **jaune** avec l'icône `bi-qr-code`.
- **Scanner** : bouton `btn btn-primary square-btn` **bleu** avec l'icône `bi-qr-code-scan`,
  libellé « Scan a payment QR Code ».

Le chantier garde : la forme (bandeau + bouton ; bouton avec icône), les couleurs (bleu et
jaune), les icônes et les libellés. Il change : l'emplacement.

## 3. Décisions du mainteneur (2026-10-06)

1. « Initier un paiement » va dans le module **« Mes responsabilités »**, **en premier**,
   **pleine largeur**, en bleu et jaune.
2. « Scanner un QR code de paiement » va **sous le bloc « Ma carte »**, reconnaissable à son
   ancien dessin et à sa couleur.
3. Le bleu est le **bleu « lien » de V2** (`--color-link` = `--loseyan-text` = `#3578a3`),
   pas le bleu Bootstrap `#0d6efd`.
4. Les boutons **sont retirés** de `/my_account/balance/` en V2 (pas de doublon).
5. Les défauts D1 à D4 sont corrigés dans ce chantier.

## 4. Pièges de V2 à connaître avant d'écrire le CSS

- **`.btn-primary` n'est pas bleu en V2.** `V2.css` le repeint en encre avec un liseré
  letchi (l. 1072-1079, et ses `--bs-btn-*` l. 1158). Il ne faut donc **pas** l'utiliser
  pour le bouton bleu.
- **`.btn` est redessiné par V2** (`V2.css:1038`) : pilule, `inline-flex`,
  `white-space: nowrap`. Un long libellé (« Please valid your email to scan a payment QR
  Code ») déborderait sur mobile. Les nouvelles classes doivent autoriser le retour à la ligne.
- **`alert-info` et `btn-warning` gardent leurs couleurs Bootstrap** en V2 (le pont de
  `V2.css` ne remappe que `--bs-primary`). On ne s'en sert pas pour autant : on prend les
  tokens V2, pour rester dans la DA.
- **Tokens V2 utilisés** (`V2.css` l. 80-95) :
  - bleu : `--color-link` (`#3578a3`) pour le texte et les fonds sous texte blanc
    (≈ 4,8:1 avec le blanc) ; `--loseyan` (`#4296cc`) seulement en fond clair ou liseré ;
  - jaune : `--zanana` (`#e9b322`), **fond uniquement**, toujours sous texte encre
    (`--color-text`).
- Le skin V2 n'a pas de thème sombre : une seule palette à vérifier.

## 5. Ce qui change

### 5.1 « Initier un paiement » — en tête de « Mes responsabilités »

**Fichier :** `pages/templates/pages/V2/vues/compte/index.html`

- Le module s'affiche si `tenants_admin` **ou** `peut_initier_un_paiement`. Une caissière
  qui n'administre aucun lieu doit voir le module, sinon elle perd le bouton.
- Le compteur `· N` du titre ne s'affiche que si `tenants_admin` (il compte les lieux
  administrés, pas le bouton).
- Le bandeau est le **premier enfant** de `.module__body`, **avant** `.module__content` et
  sa grille `.grid--3` : il prend toute la largeur.
- `.module__content` et sa boucle `{% for tenant in tenants_admin %}` passent sous
  `{% if tenants_admin %}`. Sinon une caissière sans lieu administré verrait une grille vide
  sous le bandeau.
- Contenu, repris de main :

```html
{% if peut_initier_un_paiement %}
    <div class="compte__encaisser" data-testid="compte-initier-paiement">
        <p class="compte__encaisser-texte">
            {% blocktrans with organisation=config.organisation %}Vous pouvez initier un paiement pour le compte de votre collectif : {{ organisation }}{% endblocktrans %}
        </p>
        <a href="{% url 'qrcodescanpay-get-generator' %}" class="btn compte__encaisser-bouton">
            <i class="bi bi-qr-code" aria-hidden="true"></i>
            {% translate "Initiate a payment" %}
        </a>
    </div>
{% endif %}
```

- `peut_initier_un_paiement` porte sur le **lieu courant** uniquement. `tenants_admin`
  liste aussi d'autres lieux : il ne sert **pas** à décider de ce bouton.

### 5.2 « Scanner un QR code de paiement » — sous « Ma carte »

**Fichier :** `pages/templates/pages/V2/vues/compte/index.html`

- Dans le `.me-block` « Ma carte », **après** le `{% if card %}…{% else %}…{% endif %}` :
  le bouton s'affiche **avec ou sans carte liée**. Payer par QR code débite la tirelire
  (Fedow), pas la carte.
- « Email validé » = `user.email_valid`, comme le partiel et la vue `get_scanner`. Pas
  `user.email_valid and user.is_active` (condition du lien « J'ai perdu ma carte »).
- Email validé :

```html
<a href="{% url 'qrcodescanpay-get-scanner' %}" class="btn compte__scanner"
   data-testid="compte-scanner-qrcode">
    <i class="bi bi-qr-code-scan" aria-hidden="true"></i>
    {% translate "Scan a payment QR Code" %}
</a>
```

- Email non validé (D4) : même place, gris, non cliquable, libellé de main :

```html
<button type="button" class="btn btn--secondary compte__scanner" disabled
        data-testid="compte-scanner-qrcode-email-non-valide">
    <i class="bi bi-qr-code-scan" aria-hidden="true"></i>
    {% translate "Please valid your email to scan a payment QR Code" %}
</button>
```

### 5.3 CSS

**Fichier :** `pages/static/V2/css/V2.css`, à côté des règles `.compte__*` existantes
(l. 2341-2358).

| Classe | Rôle | Couleurs |
|---|---|---|
| `.compte__encaisser` | bandeau pleine largeur, texte à gauche et bouton à droite ; empilés sur mobile | fond `--loseyan` éclairci (≈ 12 % dans `--color-surface`), liseré gauche `--color-link`, texte `--color-text` |
| `.compte__encaisser-bouton` | bouton jaune | fond `--zanana`, texte `--color-text`, survol un peu assombri |
| `.compte__scanner` | bouton bleu, pleine largeur du bloc sur mobile | fond `--color-link`, texte `--color-text-inverse` |

Règles communes : `white-space: normal` (cf. piège §4), focus clavier visible
(`outline: 2px solid var(--color-link)`, comme `.btn-outline-primary` l. 1094), cible tactile
≥ 44 px. La variante `disabled` de `.compte__scanner` reprend le gris de `.btn--secondary`.

On n'utilise **pas** `square-btn` : il donne un bouton carré sur mobile, dessiné pour la
rangée de quatre boutons de l'ancienne page. Ici chaque bouton est seul sur sa ligne.

### 5.4 Retrait des boutons de `/my_account/balance/` en V2

**Fichier :** `pages/templates/pages/V2/vues/compte/balance.html`

- Supprimer le bloc `callout` « Initiate a payment » et son commentaire (l. 29-40).
- Le bouton « Scan a payment QR Code » vit dans le **partiel partagé**
  `tirelire_section.html`, que classic affiche toujours. On l'y masque **pour V2 seulement** :

```django
{# V2 affiche le scanner sous « Ma carte » (index) : pas de doublon ici. #}
{% include "htmx/views/my_account/tirelire_section.html" with masquer_le_bouton_scanner=True %}
```

  et dans le partiel : `{% if not masquer_le_bouton_scanner %} … {% endif %}` autour des deux
  variantes du bouton scanner (email validé / non validé).
- Le skin **classic ne change pas** : sa tuile « My wallet » et ses boutons restent.
  `pages/classic/vues/compte/balance.html` lit seulement `peut_initier_un_paiement` (D3) au
  lieu de la double condition.

### 5.5 Vue

**Fichier :** `BaseBillet/views.py`

- `MyAccount.list` et `MyAccount.balance` : poser `peut_initier_un_paiement` (D3).
- Supprimer `MyAccount.tirelire_section` (D1).
- Mettre à jour la docstring du gabarit V2 index : le contexte gagne
  `peut_initier_un_paiement`.

## 6. Traductions

On réutilise les msgid existants : « Initiate a payment », « Scan a payment QR Code »,
« Please valid your email to scan a payment QR Code », « Vous pouvez initier un paiement pour
le compte de votre collectif : %(organisation)s ».

**Nouvelle chaîne (D2) :** « Ce QR code n'est pas un QR code de paiement TiBillet. »
→ le signaler au mainteneur en fin de chantier (workflow i18n à lancer, jamais par l'agent).

## 7. Tests

Lire `tests/PIEGES.md` avant d'écrire. Chaque test doit être vu **échouer** sur une mutation
volontaire avant d'être livré.

### 7.1 pytest — rendu de l'index V2

Nouveau fichier `tests/pytest/test_mon_espace_v2_boutons_qrcode.py`.

Mise en place :

- **Skin** : `mock.patch("BaseBillet.views.get_skin_courant", return_value="V2")`
  (`"reunion"` pour le test « balance classic »). **Ne jamais écrire
  `ConfigurationSite.skin` en base** : `get_solo()` passe par le cache memcached partagé
  avec le serveur de dev et survit au rollback (`tests/PIEGES.md` 9.86). Le patch marche
  parce que `pages.services.gabarit_skin` importe `get_skin_courant` localement à chaque
  appel. Même pattern que `test_pages_admin_apercu.py`.
- **Fedow** : `mock.patch("BaseBillet.views.FedowAPI")`, comme
  `test_balance_soldes_et_recharge.py`. **Pas** `fedow_connect.fedow_api.FedowAPI` :
  `MyAccount` utilise le nom importé en tête de `BaseBillet/views.py` (l. 84), et ce patch-là
  ne le toucherait pas. (L'import local ne concerne que `QrCodeScanPay`.)
- **Carte** : `NFCcard.retrieve_card_by_signature.return_value` vaut **`[]`** pour « sans
  carte » (un `MagicMock` nu est vrai et indexable : le test rendrait la branche « avec
  carte »), et `[{"number_printed": "TEST0001"}]` pour « avec carte ».
- **Soldes** : `wallet.cached_retrieve_by_signature.return_value.validated_data =
  {"tokens": []}`.
- `get_context` → `MeSerializer` ne fait que des requêtes en base : pas d'autre mock.

| Test | Attendu |
|---|---|
| admin du lieu | `compte-initier-paiement` présent, lien vers `/qrcodescanpay/get_generator/` |
| droit `initiate_payment` seul, admin d'aucun lieu | module `module-responsabilites` **et** bouton présents |
| simple adhérent | ni module, ni bouton |
| admin d'un **autre** lieu seulement | module présent (son lieu), bouton **absent** |
| superuser absent de `client_admin` du lieu | bouton présent (D3) |
| email validé, **sans carte** | `compte-scanner-qrcode` présent, lien vers `/qrcodescanpay/get_scanner/` |
| email validé, avec carte | `compte-scanner-qrcode` présent |
| email non validé | `compte-scanner-qrcode-email-non-valide` présent et `disabled`, pas de lien |
| page balance V2 | aucun des deux boutons |
| page balance classic | les deux boutons toujours là (non-régression) |

### 7.2 pytest — défauts

- D1 : la route `/my_account/tirelire_section/` répond 404 ; le partiel ne contient plus de
  `</section>` sans ouverture.
- D2 : le gabarit du scanner ne contient plus `form-qrcode-scan` ni `qrcode_processed`.

### 7.3 E2E — greffe sur le parcours réel « adhésion qui recharge, puis dépense »

Pas de nouveau test contre Fedow : on **greffe** les clics sur
`tests/e2e/test_adhesion_recompense_puis_qrcode.py`, qui fait déjà le parcours complet
contre le **vrai Fedow** (adhérent neuf à l'email validé + portefeuille, cotisation en
espèces, versement de la récompense, dépense par QR code, comptabilité).

Aujourd'hui, son étape 4 (« L'adhérent dépense sa monnaie par QR code ») passe par des appels
directs : `POST generate_qrcode`, requête en base sur « la dernière demande en attente »,
`POST valid_payment`. On la remplace par le parcours dans le navigateur, avec **deux
contextes** (`browser.new_context()`, comme `test_reservation_limits.py`) : l'encaisseur et
l'adhérent, comme deux téléphones.

| Qui | Action | Vérification |
|---|---|---|
| encaisseur (`login_as_admin`) | `/my_account/` → clic `compte-initier-paiement` | arrivée sur le générateur (`#amount` visible) |
| encaisseur | saisit le montant dans `#amount`, garde `EURO`, clique « Initier un paiement » | le QR code et `#copy-pay-link-btn` sont affichés |
| encaisseur | lit `data-link` de `#copy-pay-link-btn` | c'est le lien de paiement ; il contient l'uuid hex de la demande |
| adhérent (`login_as`) | `/my_account/` → clic `compte-scanner-qrcode` | arrivée sur le scanner (`#start-button` visible) |
| adhérent | ouvre le lien de paiement (remplace la caméra : c'est l'URL du QR code) | écran de validation, montant demandé affiché |
| adhérent | clic « Confirm Payment » | écran « Payment Confirmed » |
| encaisseur | clic « Paiement en attente. Vérifier maintenant » (`#check-payment-button`) | « Paiement validé » |

Les étapes suivantes du test (débit exact sur Fedow, vente validée, comptabilité) ne
changent pas. L'uuid de la demande vient désormais du lien affiché, et non plus de « la
dernière ligne en attente en base » : une demande créée par un test voisin ne peut plus être
prise à la place.

Pourquoi une greffe plutôt qu'un nouveau test :
- le parcours des boutons est couvert de bout en bout avec le vrai Fedow, y compris le lien de
  paiement et le bouton « Vérifier » du générateur, qui n'avaient aucun test ;
- pas de deuxième émission de monnaie locale par lancement (chaque run de ce fichier émet
  déjà 100 MonaLocalim, sans rollback possible).

**Skin :** le tenant `lespass` est en V2 en dev (vérifié le 2026-10-06). Le test lit le skin
au départ (`django_shell`) et **échoue** avec une consigne claire s'il ne vaut pas `V2`
(« lancer `manage.py charger_site_lespass` »). Jamais de `pytest.skip`, et jamais d'écriture
du skin par le test : `ConfigurationSite.get_solo()` est en cache partagé avec le serveur.

**Captures visuelles :** petit fichier séparé `tests/e2e/test_mon_espace_v2_boutons_qrcode.py`,
sans Fedow : l'admin sur `/my_account/` à 375 px et à 1280 px — bandeau pleine largeur,
libellés sans débordement, les deux boutons visibles.

### 7.4 Suite

Lancer les tests du domaine (`test_qrcodescanpay_*`, `test_balance_soldes_et_recharge.py`,
`test_membership_gabarits_attributs.py`) puis la suite complète, via le skill `tibillet-test`.

## 8. Fichiers touchés

| Fichier | Changement |
|---|---|
| `pages/templates/pages/V2/vues/compte/index.html` | bandeau d'encaissement (5.1), bouton scanner (5.2) |
| `pages/templates/pages/V2/vues/compte/balance.html` | retrait des deux boutons, commentaires (5.4, D1) |
| `pages/templates/pages/classic/vues/compte/balance.html` | condition `peut_initier_un_paiement`, commentaires (D1, D3) |
| `BaseBillet/templates/htmx/views/my_account/tirelire_section.html` | `</section>` orphelin, `aria-hidden`, `masquer_le_bouton_scanner`, bouton gris non cliquable (D1, D4, 5.4) |
| `BaseBillet/templates/fonctionnel/qrcode_scan_pay/scanner.html` | branche morte et repli 405 (D2) |
| `BaseBillet/views.py` | `peut_initier_un_paiement`, suppression de `tirelire_section` (D1, D3) |
| `pages/static/V2/css/V2.css` | `.compte__encaisser*`, `.compte__scanner` (5.3) |
| `tests/pytest/test_mon_espace_v2_boutons_qrcode.py` | nouveau (7.1, 7.2) |
| `tests/e2e/test_adhesion_recompense_puis_qrcode.py` | étape 4 refaite par des clics, deux contextes (7.3) |
| `tests/e2e/test_mon_espace_v2_boutons_qrcode.py` | nouveau, captures 375 / 1280 px sans Fedow (7.3) |
| `CHANGELOG/2026-10-06-mon-espace-v2-boutons-qrcode.md` | nouveau |

**Migration :** non.

## 9. Hors périmètre

- Les pages de paiement elles-mêmes (générateur, scanner, validation) : identiques à main,
  on n'y touche pas, sauf D2.
- Le dessin de ces pages en V2 (elles héritent de `fonctionnel/account_base.html`, en
  Bootstrap, où `btn-primary` est encre).
- Le titre « My balance » perdu en juin dans classic (cf. D1).
- La tuile « Ma carte Pass » retirée du même menu par le commit `eb519112`.
