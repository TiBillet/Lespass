# controlvanne : corrections de l'audit (écran kiosk, calibration, i18n, a11y)

**Date :** 2026-09-26
**Migration :** Non / No (`makemigrations --check` : « No changes detected »)

## Résumé / Summary

**Quoi / What :** trois audits en lecture seule de `controlvanne/` ont été
faits : djc côté Python, djc côté templates/JS, hallmark sur l'interface. Ce
chantier corrige les lots 3 (écran kiosk) et 4 (calibration, i18n,
accessibilité). Les lots 1 (sécurité) et 2 (facturation) sont **en attente** :
voir `CHANGELOG/a traiter/controlvanne-audit-securite-facturation.md`.

/ Three read-only audits of `controlvanne/`. This change fixes lot 3 (kiosk
screen) and lot 4 (calibration, i18n, accessibility). Lots 1 (security) and 2
(billing) are on hold, documented in `CHANGELOG/a traiter/`.

**Pourquoi / Why :**
- Le texte blanc était illisible sur les accents clairs de la maquette (cyan
  2,4:1, ambre 1,7:1, corail 2,9:1), y compris la mention légale obligatoire.
- Les noms longs, les descriptions longues et les nombreux tags sortaient du
  cadre de 1280×800.
- La page de calibration n'était pas traduite, dépendait de l'horloge du PC et
  pouvait appliquer le facteur deux fois.

## Lot 3 — Écran kiosk

- **Couleur d'accent lisible, texte toujours blanc** (comme la maquette).
  - Pas de calcul côté serveur : le texte reste blanc. C'est la **palette
    proposée dans l'admin** qui garantit le contraste. Les 14 couleurs de
    `COULEURS_ACCENT` (`Administration/admin/products.py`) ont été calculées
    pour avoir au moins 4,5:1 avec le blanc (fond sous du texte, y compris la
    mention légale) et au moins 3:1 sur la carte sombre `#2a2d2f` (texte en
    couleur, en gros caractères).
  - Les trois couleurs de la maquette (cyan, ambre, corail) ont été retirées de
    la palette, car le blanc était illisible dessus.
  - Deux tests vérifient les deux seuils pour chaque couleur
    (`TestPaletteDesFuts`).
  - `kiosk_detail.html` pose `--tireuse-accent` depuis la couleur du fût, et
    chaque vignette de la liste porte la couleur de son fût.
  - **Limite :** sans couleur choisie (« Aucune »), l'écran garde le cyan de la
    maquette, où le blanc n'a que 2,4:1. Une couleur déjà enregistrée hors
    palette est gardée telle quelle.
- **Mention légale** : 18 px, en gras.
- **Débordements**
  - Titre réduit selon la longueur du nom (60 px au-delà de 12 caractères,
    44 px au-delà de 20).
  - Description limitée à 7 lignes. Titres et listes de l'éditeur ramenés à la
    taille du texte.
  - Pastilles qui passent à la ligne.
  - Sur l'écran de service : nom sur une ligne à 48 px, pastilles sur une
    rangée.
- **Hiérarchie pendant le tirage** : volume à 56 px, avec « / 50 cl ».
- **Refus** : liseré rouge de 10 px autour de la carte.
- **Bandeau « connexion perdue »** : 24 px, `role="alert"`. La page est
  atténuée pendant la coupure (CSS `:has()`, sans JS).
- **Sans fût** : écran « Aucun fût branché » au lieu de « LIQUIDE / Présentez
  votre carte ». Même chose dans la liste. Prix à 0 : « — » sur l'écran de
  service.
- **Liste en responsive** : titres en `clamp()`, `min-width: 0`, valeurs qui
  passent à la ligne, texte de 14 px au minimum. Pas de défilement horizontal
  à 375 px.
- **Animations** : le verre et la barre du fût bougent avec `transform`
  (`translateY` / `translateX`) au lieu de `height` / `width`.
- **Simulateur DEMO** : c'est un `<details>` replié en haut à droite. Il ne
  cache plus le pied de page, sans JS.
- **Jetons** : filets, voiles et tailles de texte remontés dans `:root`.
  Nouveau jeton `--ease-in-out`.
- **JS** :
  - suppression du code mort `kiosk_url` / `kiosk_reload` (jamais envoyés par
    le serveur) ;
  - `aria-live` retiré des zones mises à jour chaque seconde (bandeau
    Prix/Solde, volume, rinçage, vignettes sauf l'état) ;
  - le prix servi et le nombre de verres restent calculés en JS : cela relève
    du lot 2.
- **Prix** : partial commun `partial/biere_prix.html`, pour la veille et la
  liste.

### Rechargement du kiosk quand le fût change

- **Problème :** après un changement de fût dans l'admin, le kiosk restait sur
  l'ancien fût. La fiche de la bière (nom, description, étiquette, tags, prix,
  couleur) est rendue une seule fois par le serveur, et les messages
  WebSocket ne mettent à jour que l'état. Les commandes `kiosk_reload` du JS
  n'étaient jamais envoyées par le serveur.
- **Correctif** (`controlvanne/signals.py`) :
  - nouvelle fonction `demander_rechargement_des_kiosks(tireuse)`, qui envoie
    `{"kiosk_reload": true}` à la fin de la transaction (`on_commit`), sur le
    groupe de la tireuse et sur `rfid_state.all` ;
  - `tireusebec_post_save` l'appelle quand le fût branché change (repéré par
    `_old_fut_id` du `pre_save`), à la place du snapshot ;
  - nouveau signal `recharger_les_kiosks_du_fut`, branché sur `Product` et
    `FutProduct` (modèle proxy : l'admin envoie `sender=FutProduct`). Quand
    un fût est modifié (couleur, nom, description, tags, tarifs), les kiosks
    des tireuses qui le servent rechargent leur page. Les produits qui ne sont
    pas des fûts sont ignorés sans requête.
- `ecran_tireuse.js` recharge la page quand il reçoit `kiosk_reload`.
  `ws_payloads.py` documente le champ.
- La mise à jour du niveau du fût à chaque tirage envoie toujours un simple
  snapshot, sans rechargement (testé).

### Simulateur dans un template séparé

Le panneau `#simu-pi-panel` est déplacé dans
`partial/simulateur_pi.html` (inclus par `kiosk_detail.html` si `demo_tags`).

## Lot 4 — Calibration, i18n, a11y

- **Calibration** (`calibration_views.py`)
  - Validation par `VolumeReelSerializer` (DRF).
  - Toute saisie invalide renvoie un **422** avec la liste des erreurs, et rien
    n'est enregistré. Avant, les valeurs invalides étaient ignorées en silence.
  - Écritures dans `transaction.atomic()`.
  - « Nouvelle série » : le lien `?nouvelle_serie=1` redirige vers
    `?depuis=<heure du serveur>`. `Date.now()` est supprimé.
  - « Ignorer » un versement : une case à cocher gardée par `hx-preserve`,
    grisée en CSS et écartée par le serveur. `window.ignoredSessions` est
    supprimé.
  - `page.html` accepte les 422 avec `htmx:beforeSwap`. Le projet utilise
    htmx 2.0.7, où `htmx:beforeOnLoad` (cité par le skill djc) ne permet pas de
    forcer l'affichage.
  - Formulaire : `hx-disabled-elt` et `hx-sync`. Un double clic ne donne qu'une
    seule requête (vérifié dans Chromium).
- **Traductions**
  - Les 3 templates de calibration sont en `{% translate %}` /
    `{% blocktranslate %}`, avec le pluriel du nombre de versements.
  - Messages du kiosk dans `viewsets.py`, `consumers.py` et `signals.py`
    (refus, « Tirage en cours », « Fin de service », « En maintenance »…),
    ainsi que « Liquide » dans `models.py`. On utilise `gettext` et pas
    `gettext_lazy`, car ces messages partent en JSON sur le WebSocket.
  - Les réponses destinées au Pi restent en anglais : ce sont des messages
    machine.
  - `simu_pi.js` : les libellés viennent des attributs `data-libelle-*`
    traduits du panneau. Cela corrige aussi le badge « Closed » / « Fermée »
    incohérent, et la couleur du message passe par une classe CSS.
- **Accessibilité** : `aria-label` sur les champs de volume et les cases à
  cocher, emoji en `aria-hidden`, `role="alert"` sur les erreurs,
  `.table-responsive`, `<th scope>`, titre `h1`. Dans `base.html`, la règle
  `.card { color }` remplace les `style="color:#111"`.
- **Templates admin**
  - `tireusebec_before.html` : styles en ligne avec les variables Unfold (il
    utilisait des classes Bootstrap qu'Unfold n'embarque pas), `rel="noopener"`,
    `data-testid`.
  - `date_range_filter.html` : traductions, `<label for>`, contraste.
- **Petites corrections**
  - `RfidSession.__str__` quand la tireuse vaut `None`.
  - `TireuseBecAdmin.get_queryset` charge aussi `fut_actif`.
  - `RfidSessionAdmin` : une session facturée ne se supprime plus, ni une par
    une, ni en suppression groupée.
  - `billing.py` : `_created` au lieu de `_`.
  - `except: pass` remplacés par `logger.warning` (`models.py`, `signals.py`).
  - `FutProductForm.clean_couleur_fond_pos` : format `#rrggbb` obligatoire.
  - `data-testid` ajoutés, et en-têtes FALC sur `base.html`, la calibration et
    les templates admin.

## Fichiers / Files

| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/templates/controlvanne/partial/biere_prix.html` | Nouveau : ligne de prix commune |
| `controlvanne/static/controlvanne/css/tireuse.css` | Débordements, jetons, liste, simulateur, animations |
| `controlvanne/static/controlvanne/js/ecran_tireuse.js` | Code mort retiré |
| `controlvanne/static/controlvanne/js/simu_pi.js` | Libellés traduits (`data-libelle-*`), classe d'erreur |
| `controlvanne/templates/controlvanne/*.html`, `partial/**` | Accent, sans fût, prix, `<details>`, `aria-live`, `role="alert"` |
| `controlvanne/calibration_views.py` | Serializer, 422, `atomic`, nouvelle série côté serveur, cases « ignorer » |
| `controlvanne/templates/calibration/*.html`, `templates/base.html` | Traductions, HTMX, a11y, FALC |
| `controlvanne/templates/admin/**` | Styles Unfold, traductions, `label for` |
| `controlvanne/viewsets.py`, `consumers.py`, `signals.py`, `models.py` | `gettext` sur les messages du kiosk, logs, `__str__` |
| `controlvanne/admin.py` | Sessions facturées protégées, `select_related("fut_actif")` |
| `controlvanne/billing.py` | `_created` |
| `Administration/admin/products.py` | Palette `COULEURS_ACCENT` au contraste vérifié, validation hex de la couleur du fût |
| `Administration/templates/admin/product/widget_couleur_accent.html` | Une seule liste de couleurs, `data-testid` sur « Aucune » |
| `controlvanne/signals.py` | Rechargement des kiosks quand le fût change ou est modifié |
| `controlvanne/templates/controlvanne/partial/simulateur_pi.html` | Nouveau : panneau du simulateur (sorti de `kiosk_detail.html`) |
| `tests/pytest/test_controlvanne_ecran_calibration.py` | Nouveau : contraste de la palette, rendu du kiosk, calibration, couleur du fût |
| `CHANGELOG/a traiter/controlvanne-audit-securite-facturation.md` | Nouveau : lots 1 et 2 en attente |

**Non fait :** les nouvelles chaînes ne sont pas dans les `.po` (pas de
`makemessages`, règle du projet).

## À tester / To test

### Test 1 : couleur d'accent
1. Admin → Fûts : les pastilles proposent 14 couleurs (bleu, pétrole…
   indigo), sans cyan, ambre ni corail.
2. Choisir une couleur → `/controlvanne/kiosk/<uuid>/` : le fond et la case
   Solde prennent cette couleur, et le texte reste blanc et lisible.

### Test 2 : débordements
Nom de bière long (30 caractères ou plus), description de plus de 10
paragraphes, 6 tags. La veille reste dans le cadre, « Présentez votre carte »
reste visible, et l'écran de service affiche les 4 étapes et le verre.

### Test 3 : sans fût
Retirer le fût d'une tireuse → « Aucun fût branché » sur le kiosk et dans la
liste.

### Test 4 : calibration
1. Tireuse désactivée → page de calibration. Cliquer « Nouvelle série » :
   l'URL contient `?depuis=` à l'heure du serveur.
2. Carte maintenance : versements. Cliquer « Calculer » sans rien saisir →
   message d'erreur, la liste continue de se mettre à jour.
3. Cocher « Ignorer » sur un versement, saisir les autres, double-cliquer sur
   « Calculer » → une seule application, et le versement ignoré n'est pas
   compté.

### Test 4 bis : changement de fût
1. Ouvrir `/controlvanne/kiosk/<uuid>/` dans un onglet.
2. Admin → Tireuses : changer le fût de cette tireuse (fiche ou liste) →
   le kiosk se recharge tout seul et affiche le nouveau fût.
3. Admin → Fûts : changer la couleur ou la description du fût branché →
   le kiosk se recharge avec la nouvelle version.

### Test 5 : simulateur
Mode DEMO : le simulateur est replié en haut à droite. Une fois ouvert, les
libellés sont en français (« En attente », « Fermée ») et les erreurs
s'affichent en rouge.

### Commandes
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_*.py tests/pytest/test_admin_*.py -q
docker exec lespass_django poetry run python manage.py makemigrations --check --dry-run
```
