# Ce qui reste après le restylage de l'admin

**Relevé du 2026-09-09**, issu de trois relectures indépendantes des 9 commits
du restylage (78 fichiers, 9840 insertions).

Chaque point a été **mesuré**, pas supposé. Ce qui a été corrigé est dans
`CHANGELOG/2026-09-09-correctifs-apres-relecture.md`. Ce qui suit ne l'est pas.

**Ordre de priorité proposé :** 1 (SEPA) → 2 (contrastes) → 4 (500 Fedow) →
3 (`search_help_text`) → 5 (traductions) → 6 (finitions). Le point 7 n'est pas
un chantier mais un **contrôle à faire avant le prochain déploiement**.

---

## 1. SEPA — corrigé en partie, risque résiduel

### Ce qui a été fait

Un `super().save()` a été inséré **avant** le `raise` dans
`Configuration.save()` (`BaseBillet/models.py`). Bon correctif : il supprime le
mal principal — la perte de tout le formulaire — et le message dit désormais la
vérité. Vérifié : **aucun risque de récursion**, `super().save()` part sur
`SingletonModel.save()` de django-solo, pas sur `Configuration.save()`.

**Bénéfice collatéral :** `Administration/admin_tenant.py:590` (la bascule des
modules du tableau de bord) appelle aussi `configuration.save()`. Avant, si SEPA
était mal configuré, **activer un module ne faisait rien du tout**. C'est réparé.

### Le risque résiduel

`check_stripe_sepa_capability()` fait `except Exception: return False` : **une
panne Stripe ou un timeout est indiscernable d'un « SEPA désactivé »**.

| | Stripe injoignable, SEPA légitimement actif |
|---|---|
| avant | rien n'est écrit, SEPA reste actif en base |
| après | **SEPA est désactivé en base**, silencieusement |

Le risque n'est pas plus grave — il a **changé de nature** : d'une perte visible
et immédiate à une désactivation invisible et durable. Il se déclenche depuis des
chemins sans rapport avec le paiement : la bascule d'un module,
`ApiBillet/views.py:1102`, les commandes de gestion.

**Correctif, trois lignes :** faire renvoyer trois états à
`check_stripe_sepa_capability` — actif / inactif / **injoignable** — et ne
désactiver que sur un « inactif » explicite ; sur « injoignable », laisser le
flag et se contenter du log.

### Ce qui reste au-delà

La validation vit toujours dans `save()` et non dans un formulaire. Le point
d'accroche est prévu et commenté depuis longtemps — `admin_tenant.py:413` :

```python
# form = ConfigurationAdminForm
```

Un `clean_stripe_accept_sepa()` dans ce formulaire ferait réafficher la page avec
l'erreur **sur le champ concerné**, en conservant les saisies. À décider alors :
garder le `raise` du modèle (il protège les écritures hors admin — API, Celery)
mais supprimer le `try/except` de `save_model` qui l'avale.

**Contrainte de test :** `check_stripe_sepa_capability` **doit être mocké**,
sinon le test appelle Stripe pour de vrai — déjà la cause de deux échecs
récurrents de la suite.

---

## 2. Contrastes en mode sombre — trois substitutions à moitié faites

C'est la même famille d'erreur que celles corrigées : **une substitution
partielle est pire que pas de substitution**. À traiter en **un seul lot**,
fonds et textes ensemble.

### 2a. Une variable CSS sur une page qui ne charge pas la feuille

`Administration/templates/admin/cloture/rapport_temps_reel.html:177`

Ce gabarit est une **page autonome** (`<!DOCTYPE html>`, rendue par
`laboutik/views.py:3251`), sans `{% extends %}`. Elle ne charge jamais
`tibillet-admin.css`, seul endroit où `--tb-texte-doux` est défini. La `var()`
ne résout pas → la couleur retombe sur l'héritage (`body { color: #333 }`).

**Observable :** sur `/laboutik/caisse/rapport-temps-reel/`, les lignes de
sous-détail cashless deviennent **mi-grises mi-noires**.

La substitution est **isolée** : le même fichier garde `#333`, `#666`, `#ddd`,
`#f0f0f0` dans son `<style>`. Une occurrence sur sept a été touchée — celle qui
ne pouvait pas marcher.

**Correctif :** revenir à `#666` ici, **ou** définir les jetons dans le `<style>`
de la page et finir les six autres. Pas d'entre-deux.

### 2b. Texte thémé sur fond codé en dur

`Administration/templates/admin/cloture/rapport_before.html:15,19,23,27` — le
fond est resté `#f8f9fa`, le texte est passé à un jeton qui **s'inverse** en mode
sombre.

| | contraste |
|---|---|
| avant (`#666` sur `#f8f9fa`) | 5,45:1 |
| après, clair | 6,16:1 ✅ |
| après, **sombre** | **2,74:1** ❌ |

**Observable :** fiche de clôture en mode sombre — le bandeau reste blanc et les
lignes « Niveau », « Responsable », « Point de vente », « Période » virent au
gris pâle sur blanc. Sous le seuil AA, et même sous 3:1. **Régression nette.**

### 2c. Lignes « Total » invisibles en mode sombre

`rapport_before.html:117, 175, 240, 275, 311, 419` — `background: #e8f5e9` sans
`color`, non substitué. Texte clair hérité sur fond vert pâle : **contraste
1,03:1**.

Préexistant, mais **la bordure de ces mêmes cellules a été thémée** : on voit
désormais une grille vide. Et `#555` est oublié ligne 139 (2,38:1 en sombre).

### Le test à étendre

`tests/pytest/test_admin_couleurs_gabarits.py` ne vérifie que l'absence des
quatre codes ciblés : **il donne un feu vert sur un écran illisible**. Il doit
refuser un texte thémé posé sur un fond codé en dur.

---

## 3. `search_help_text` — un chemin de crash et des libellés dégradés

`Administration/admin/base.py`. Aucune exception sur les 55 admins réels, et
aucun 500 sur 100 URL balayées. Mais le fuzzing révèle :

| entrée | résultat |
|---|---|
| `12345` (entier) | **`AttributeError`** ligne 69 — le garde `(chemin or "")` ne couvre que `None`/`""` |
| `"___"` | `" "` — un espace, *truthy* → « Rechercher :   » |
| `"name__icontains"` | `"icontains"` — Django **accepte** les lookups explicites ; le code suppose que tout segment non final est une relation |

Et des libellés faussés, visibles sur 55 changelists :

- **contexte de relation perdu** : `point_de_vente__name` → « nom » — nom de quoi ?
- **mélange FR/EN** là où le `verbose_name` source est anglais : « adresse
  e-mail, **order date** » ;
- **acronymes cassés** par le `.lower()` (l. 157) : « uuid », « siren », « ip ».

Déduplication et plafonnement sont, eux, **corrects** (vérifié).

---

## 4. Un 500 préexistant sur `/admin/fedow_public/assetfedowpublic/`

`AttributeError: 'NoneType' object has no attribute 'email'`.

`AssetAdmin.get_queryset()` (`Administration/admin_tenant.py:4264`) fait un
**appel réseau à Fedow** à chaque chargement de la changelist, avant même de
construire le queryset. Découvert par le balayage étendu des pages d'onglets ;
`tests/pytest/test_admin_configuration_onglets.py` le signale par un `warning`.

Un appel réseau synchrone dans un `get_queryset` est fragile par construction :
la page devient indisponible dès que Fedow l'est.

---

## 5. Traductions — 31 `msgid` sans version anglaise

**⚠️ RÈGLE DU PROJET : ne JAMAIS lancer `makemessages` automatiquement.** Les
catalogues sont du ressort exclusif du mainteneur.

L'ajout des `verbose_name` français a **remplacé** les libellés anglais que
Django fabriquait automatiquement. Avant, `last_response` s'affichait
« Last response » en anglais — c'était **correct**. Ce ne l'est plus : l'admin
anglais affiche du français sur ces 31 entrées.

Rappel du piège `tests/PIEGES.md` 11.11 : après `makemessages`, **retirer les
`#, fuzzy` sur les entrées ajoutées**, sans quoi Django ignore silencieusement la
traduction. Mesuré à l'époque : les markers passeraient de **4 à 230**, et le
diff ferait **18 310 lignes** — il ramasse un arriéré antérieur à ce lot.

À noter aussi : `locale/*/LC_MESSAGES/django.mo` datent du **3 septembre** alors
que les `.po` datent du **9**. Même les traductions déjà écrites ne sont pas
compilées.

### La liste

| `msgid` | Champs concernés |
|---|---|
| `Action` | BaseBillet.webhook.active |
| `Adresse e-mail` | AuthBillet.tibilletuser.email, BaseBillet.configuration.email, MetaBillet.waitingconfiguration.email |
| `Adresse e-mail confirmée` | AuthBillet.tibilletuser.email_valid, MetaBillet.waitingconfiguration.email_confirmed |
| `Adresse postale` | BaseBillet.configuration.postal_address, BaseBillet.event.postal_address |
| `Appairée` | BaseBillet.scanapp.claimed |
| `Archivée` | BaseBillet.scanapp.archive |
| `Clé` | BaseBillet.externalapikey.key |
| `Code devise` | BaseBillet.configuration.currency_code, fedow_public.assetfedowpublic.currency_code |
| `Créée le` | onboard.onboardinvitation.created_at |
| `Dernier journal` | BaseBillet.brevoconfig.last_log |
| `Dernier journal Ghost` | BaseBillet.ghostconfig.ghost_last_log |
| `Dernière modification` | BaseBillet.externalapikey.created |
| `Dernière réponse` | BaseBillet.webhook.last_response |
| `Description` | crowds.crowdconfig.description |
| `Génération` | QrcodeCashless.detail.generation |
| `Identifiant NFC` | QrcodeCashless.cartecashless.tag_id |
| `Identifiant d'environnement` | BaseBillet.formbricksforms.environmentId |
| `Instance créée` | MetaBillet.waitingconfiguration.created |
| `LaBoutik souhaité` | MetaBillet.waitingconfiguration.laboutik_wanted |
| `Langue` | BaseBillet.configuration.language |
| `Nom de l'application` | BaseBillet.scanapp.name |
| `Nom de la clé` | BaseBillet.externalapikey.name |
| `Nom du lieu` | Customers.client.name |
| `Numéro` | QrcodeCashless.cartecashless.number |
| `Numéro de carte` | BaseBillet.membership.card_number |
| `Paiement souhaité` | MetaBillet.waitingconfiguration.payment_wanted |
| `Personne qui réserve` | BaseBillet.reservation.user_commande |
| `Portefeuille d'origine` | fedow_public.assetfedowpublic.wallet_origin |
| `Site web` | BaseBillet.configuration.site_web, MetaBillet.waitingconfiguration.site_web |
| `URL de destination` | BaseBillet.webhook.url |
| `Utilisateur·ice` | BaseBillet.externalapikey.user, BaseBillet.paiement_stripe.user, QrcodeCashless.cartecashless.user |

---

## 6. Finitions

- **`Reservation.datetime`** est en `auto_now=True` mais libellé « Date et
  heure ». Vague plutôt que mensonger — le renommer en « Dernière
  modification » serait exact, mais c'est une décision produit sur une colonne
  vue par les utilisateurs.
- **`export_csv_comptable_detail_form.html`** est un gabarit **mort** (aucune
  référence ; le formulaire réel est construit en HTML inline dans
  `Administration/admin/laboutik.py:1440`). Il a pourtant reçu une substitution
  de couleur. Son lien « Annuler » pointe vers `../voir-rapport/`, route qui
  n'existe plus → 404. À supprimer, comme `cloture_detail.html` l'a été.
- **`rapport_before.html:148`** : `{% translate "Poids/Vol" %}` est un `msgid`
  **français** au milieu d'une ligne d'en-têtes anglais.
- **Carte de module comptée active mais cachée.** Sur un tenant en LaBoutik
  **V1**, le compteur du domaine compte la caisse comme active
  (`dashboard.py:2255`) mais sa carte n'a pas de `lien_du_module`, donc porte
  `tb-carte-off` et est masquée par le repli. Le compteur dit `3/5` et on ne voit
  que 2 cartes.
- **`Page.enfants_pour_section`** est une `property`, pas une `cached_property` :
  chaque accès reconstruit un queryset.
- **Le CHANGELOG du 2026-09-09** annonce 24 gabarits touchés par la passe
  couleurs ; il y en a **4** (185 substitutions). Le volume est juste, le
  périmètre annoncé ne l'est pas.
- **Trou de couverture assumé :** aucun test ne voit le comportement d'Alpine
  dans le navigateur. C'est par là qu'est passée la régression du repli du rail.
  Seul un test E2E le fermerait.

---

## 7. Avant le prochain déploiement — contrôle obligatoire

`BaseBillet/migrations/0228_alter_scanapp_name.py` (commit `7fbe2a3f`) pose
`unique=True` sur `ScanApp.name` **sans dédoublonnage**. SQL réel confirmé :

```sql
ALTER TABLE "BaseBillet_scanapp" ADD CONSTRAINT ... UNIQUE ("name");
```

**Un seul tenant avec deux scan apps homonymes fait échouer `migrate_schemas`
en cours de route** : les tenants déjà traités sont migrés, les suivants non, et
le code applicatif est déjà déployé partout. Or c'est exactement le symptôme de
l'issue #454 que le commit prétend corriger.

Base de dev : 43 tenants, **0 `ScanApp`** partout — aucun risque local. Le risque
est **entièrement reporté sur la production**.

```sql
-- à exécuter schéma par schéma AVANT de déployer
SELECT name, count(*) FROM "BaseBillet_scanapp" GROUP BY name HAVING count(*) > 1;
```

> **Piège de méthode à retenir :** `sqlmigrate` lancé depuis le schéma `public`
> renvoie `-- (no-op)` **trompeur** pour une app tenant — le routeur saute les
> opérations au lieu de les évaluer. Il faut
> `tenant_command sqlmigrate --schema=<tenant>`. C'est ce faux négatif qui
> masquait cet `ALTER TABLE`.

Effet de bord : `archive=True` ne libère pas le nom. Archiver « Entrée » puis en
recréer une du même nom devient impossible. Une
`UniqueConstraint(fields=['name'], condition=Q(archive=False))` serait plus juste.
