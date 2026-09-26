# Écran de tireuse sans contact / Contactless tap screen

**Date :** 2026-09-26
**Migration :** Non / No (`makemigrations --check` : « No changes detected »)

## Résumé / Summary

**Quoi / What :** les écrans kiosk de `controlvanne` adoptent la maquette
`TEMP-tibillet-tireuse-main/tireuses-non-tactile/`.
- `kiosk_detail.html` (écran du Pi sur une tireuse) : 3 étapes de la maquette
  (veille, service, bilan) et 2 étapes ajoutées (refus, maintenance).
- `kiosk_list.html` (toutes les tireuses) : grille de vignettes dans la même charte.
- Plus de Bootstrap sur ces 2 pages. Polices auto-hébergées (Luciole, Unbounded,
  Sonder Sans), pas de Google Fonts : le Pi peut être hors ligne.
- Le prénom du titulaire de la carte s'affiche (« Bonjour Camille »,
  « Merci Camille ! »). Carte anonyme : « Bonjour », « Merci ! ».
- Admin des fûts : section « Écran de la tireuse », avec des libellés clairs
  et un nouveau champ « Caractéristiques » (les tags).

/ The controlvanne kiosk screens adopt the contactless mockup: 5 stages on the
detail page, a thumbnail grid on the list page, no Bootstrap, self-hosted fonts,
customer first name shown, clearer keg admin with tags as chips.

**Pourquoi / Why :** nouvelle maquette de l'écran de tireuse, non tactile.

## Choix d'implémentation / Implementation notes

- **Surtout HTML + CSS.** `ecran_tireuse.js` pose `data-etat` sur la racine de
  la tireuse, écrit les `[data-champ]` et 2 variables CSS
  (`--remplissage-verre`, `--niveau-fut`). C'est `tireuse.css` qui montre la
  bonne étape et allume le mode d'emploi.
- **Une étape = un fichier** (`partial/etapes/*.html`). Toutes sont rendues
  une fois ; pas de rechargement HTMX. Le flux vient du WebSocket (écran non
  tactile, un message toutes les ~0,5 s pendant le tirage, transition CSS du verre).
- **État « tirage »** : il est déclenché par `volume_ml > 0`, pas par
  `vanne_ouverte`. `authorize()` envoie déjà `vanne_ouverte=true` au badge.
- **Données bière sans migration** : titre = `name`, pastilles = `tag`
  (ordre alphabétique, la 1re en couleur), description = `long_description`
  (HTML nettoyé par `sanitize_textfields`), étiquette = `img`,
  brasserie = `short_description`.
- **Libellés admin posés par le formulaire** (`FutProductForm.__init__`), pas par
  `verbose_name` : cela évite une migration `AlterField` sur chaque tenant.
  `("BaseBillet", "FutProduct", "tag")` est ajouté à `TOLERES` dans
  `tests/pytest/test_admin_verbose_name.py`.
- **Sonder Sans n'a aucune lettre accentuée** : les titres sont en majuscules.
  La lettre de secours (Unbounded) reste ainsi une capitale.
- Le panneau du simulateur (DEMO) garde tous ses ids `simu-*` : `simu_pi.js`
  n'est pas modifié.
- **Bilan et snapshot** : au `pour_end`, le serveur pousse d'abord un snapshot
  de la tireuse (signal `post_save` du réservoir, `present=false`), puis le
  message `session_done`. Le bilan s'affiche donc dès qu'un `session_done` arrive
  avec du volume, sans regarder le message précédent. L'écran passe en veille
  pendant quelques millisecondes entre les deux.
- **Écran refus sans minuteur** : il reste affiché tant que la carte est posée.
  Le Pi envoie `card_removed` au retrait même sans session
  (`Pi/controllers/tibeer_controller.py`, `_handle_card_removal`) ; le serveur
  pousse alors `present=false`, ce qui ramène en veille.
- **Sessions orphelines fermées et facturées au badge suivant** : une session
  restait ouverte si `card_removed` n'arrivait jamais (Pi redémarré, coupure
  réseau, page du simulateur rechargée). Le kiosk s'ouvrait alors sur l'écran
  de service, et le volume versé n'était jamais facturé. Désormais,
  `authorize()` appelle `_cloturer_sessions_orphelines` avant tout : les sessions
  encore ouvertes sur la tireuse sont fermées et facturées au dernier volume
  connu (`dernier_volume_ml`). La fermeture et la facturation sont dans une
  fonction partagée avec `event()` (`_cloturer_session_et_facturer`), avec le même
  verrou anti-double facturation.
- **Fûts toujours vendus au volume** : `FutProductAdmin.save_related` force
  `poids_mesure=True` (et `contenance=None`) sur tous les tarifs du fût, y compris
  les anciens. Le formulaire des tarifs n'affiche plus la case ni la contenance,
  et le prix s'appelle « Prix au litre ».
- **Admin `ConfigurationTireuse`** : il passe sur `SingletonModelAdmin`, comme
  `ConfigurationAdmin`. La page liste redirigeait en 302, et la barre d'onglets
  du module ne la trouvait pas (`test_admin_configuration_onglets.py`).

### Fichiers / Files
| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/templates/controlvanne/kiosk_detail.html` | Réécrit sur `base_tireuse.html`, simulateur restylé |
| `controlvanne/templates/controlvanne/kiosk_list.html` | Grille de vignettes |
| `controlvanne/templates/controlvanne/base_tireuse.html` | Nouveau — base sans Bootstrap |
| `controlvanne/templates/controlvanne/partial/tireuse_ecran.html` | Nouveau — conteneur des étapes |
| `controlvanne/templates/controlvanne/partial/etapes/*.html` | Nouveau — veille, service, fin, refus, maintenance |
| `controlvanne/templates/controlvanne/partial/tireuse_vignette.html` | Nouveau — vignette de la liste |
| `controlvanne/templates/controlvanne/partial/biere_pastilles.html` | Nouveau — pastilles (tags) |
| `controlvanne/templates/controlvanne/partial/tireuse_pied.html` | Nouveau — mention légale + signature |
| `controlvanne/static/controlvanne/css/tireuse.css` | Nouveau — adapté de la maquette |
| `controlvanne/static/controlvanne/js/ecran_tireuse.js` | Nouveau — remplace `panel_kiosk.js` |
| `controlvanne/static/controlvanne/fonts/` | Nouveau — Luciole, Unbounded (+ OFL), Sonder Sans |
| `controlvanne/models.py` | Property `TireuseBec.prix_verre_25cl` |
| `controlvanne/viewsets.py` | `prenom` dans `_construire_payload_session`, `select_related` |
| `controlvanne/ws_payloads.py` | Champ `prenom` |
| `controlvanne/viewsets.py` (bis) | `_cloturer_session_et_facturer` (extrait de `event()`), `_cloturer_sessions_orphelines` appelée dans `authorize()` |
| `tests/pytest/test_controlvanne_billing.py` | `test_08` : session orpheline fermée et facturée au badge suivant |
| `Administration/admin/products.py` | Fûts : section « Écran de la tireuse », libellés, tags, tarifs toujours au volume |
| `tests/pytest/test_admin_verbose_name.py` | `FutProduct.tag` dans `TOLERES` |
| `controlvanne/admin.py` | `ConfigurationTireuseAdmin` sur `SingletonModelAdmin` (plus de 302). Liste des tireuses : bouton « Voir le kiosk », Pi appairé en coche/croix, colonne prix au litre retirée |

### Supprimé / Removed
- `controlvanne/static/controlvanne/js/panel_kiosk.js` et
  `controlvanne/templates/controlvanne/partial/kiosk_card.html` (remplacés).
- Le bandeau WebSocket de `base.html` (seul `panel_kiosk.js` le pilotait).
- `base.html` + Bootstrap restent : la page de calibration les utilise.
- `controlvanne/README.md` et les commentaires de `consumers.py` pointent vers
  `ecran_tireuse.js`.

## À tester / To test

### Test 1 : écran d'une tireuse (mode DEMO, 1280×800)
1. Admin → Fûts → un fût : remplir Brasserie, Description, Caractéristiques
   (ex. « Blanche », « 4,4° », « IBU 25 »), Étiquette. Enregistrer.
2. Ouvrir `/controlvanne/kiosk/<uuid>/` → veille : titre, pastilles, description,
   prix « x,xx € / 25 cl (soit y €/L) », étiquette, brasserie.
3. Simulateur « Carte client 1 » → service : « Bonjour <prénom> », solde,
   « soit N verres », étapes 1-2 allumées.
4. Slider de débit → tirage : étape 3 allumée, le verre monte, le solde baisse.
5. « Retirer la carte » → bilan « Merci <prénom> ! », puis veille après 6 s.
6. « Carte inconnue » → « Carte refusée » + message. L'écran reste affiché
   tant que la carte est posée, puis « Retirer la carte » → veille.
7. Carte anonyme : « Bonjour » et « Merci ! », sans espace en trop.

### Test 1 bis : tarifs d'un fût
1. Admin → Fûts → un fût : le tarif n'a plus de case « vente au poids/volume »,
   le prix s'appelle « Prix au litre ».
2. Enregistrer → en base, tous les tarifs du fût ont `poids_mesure=True`.

### Test 1 ter : liste des tireuses dans l'admin
1. Admin → Tireuses : pas de colonne prix au litre.
2. Colonne « Raspberry Pi appairé » : coche verte ou croix rouge.
3. Bouton « Voir le kiosk » → ouvre `/controlvanne/kiosk/<uuid>/` dans un nouvel onglet.

### Test 1 quater : session orpheline
1. Simulateur : badger une carte, verser ~20 cl, puis **recharger la page**
   sans retirer la carte → le kiosk rouvre sur l'écran de service.
2. Badger à nouveau → dans les logs : « Session orpheline fermée au badge
   suivant … facture=oui ». Le solde affiché tient compte du volume facturé.

### Test 2 : maintenance
1. Désactiver la tireuse dans l'admin, puis recharger la page → écran maintenance.
2. Badger une carte maintenance → « Volume rincé » s'affiche pendant le rinçage.

### Test 3 : liste
1. Ouvrir `/controlvanne/kiosk/` → une vignette par tireuse active.
2. Badger sur la page détail dans un autre onglet → la pastille d'état de la
   vignette change (« Carte posée », « Service en cours »…).
3. Tireuse à réservoir limité → barre de niveau du fût.

### Test 4 : reconnexion
Couper daphne → le bandeau jaune apparaît. Relancer → il disparaît.

### Commandes
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_*.py tests/pytest/test_admin_verbose_name.py -q
docker exec lespass_django poetry run python manage.py makemigrations --check --dry-run
```

### Limites connues / Known limits
- Si la page se recharge en pleine session, le prénom n'est pas dans le payload
  initial du consumer : on voit « Bonjour » jusqu'à la fin de la session.
- Les tags sont partagés avec les événements : l'autocomplete propose tous les tags.
- Nouveaux textes en `{% translate %}` : les fichiers `.po` ne sont pas mis à jour.
