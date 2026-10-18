# Bénévolat, chantier 7 : une semaine à la fois / Volunteering, step 7: one week at a time

**Date :** 2026-10-17
**Migration :** Non

## Resume / Summary
**Quoi / What :** la page publique d'un planning (`/booking/benevolat/<slug>/`) montre une semaine (lundi → dimanche), avec « ← Semaine précédente » / « Semaine suivante → » et le titre « 20 – 26 octobre ». L'adresse porte `?semaine=AAAA-MM-JJ` (n'importe quel jour, ramené à son lundi). Sans paramètre, avec une valeur illisible ou une semaine passée : la semaine du prochain besoin. Les liens marchent sans JS (`href`) et rechargent la zone seule en htmx (`hx-get` + `hx-push-url`). Après « Je viens », « Me retirer » ou « Inscrire quelqu'un », la zone montre la semaine du besoin touché. Le compteur de l'en-tête reste celui du planning entier.
/ The public planning page shows one week, with previous/next links (plain href + htmx zone reload with pushed URL). After an action, the zone shows the need's week. The header counter still covers the whole planning.

**Pourquoi / Why :** chantier 7 de `TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md` (§11.1, D28) : un planning hebdomadaire sans fin (chantier 8) rendrait une page de plusieurs mois.

Points notables :
- le fuseau du lieu est lu une seule fois par page et passé à `debut()`, `fin()`, `est_passe()`, `limite_pour_se_retirer_sans_prevenir()` (nouveau paramètre facultatif `fuseau_du_lieu`) : le nombre de requêtes et de lectures de la Configuration ne dépend plus du nombre de besoins ;
- la vue `retrieve` rend la zone seule quand l'en-tête `HX-Target` vaut `benevolat-planning`, la page entière sinon (retour arrière compris) ;
- les jours de la vue mobile passent de `h2` à `h3` : le titre de la semaine est le `h2`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/models.py` | `fuseau_du_lieu` facultatif sur `debut`, `fin`, `est_passe`, `limite_pour_se_retirer_sans_prevenir` |
| `booking/benevolat.py` | `lundi_de_la_semaine`, `lire_la_semaine_demandee`, `choisir_la_semaine`, `titre_de_la_semaine` ; `construire_le_planning(…, semaine)` découpe la semaine ; fuseau lu une fois |
| `booking/views_benevolat.py` | `retrieve` lit `?semaine=` et rend la zone seule pour htmx ; `_reponse_zone` reçoit la semaine du besoin |
| `booking/templates/booking/benevolat/partials/zone.html` | Navigation par semaine, message « Aucun besoin cette semaine. » |
| `booking/templates/booking/benevolat/partials/jours_mobile.html`, `planning.html` | Jours en `h3` ; défilement de la grille remis au début après un lien de semaine |
| `booking/static/booking/css/benevolat.css` | Styles `.bv-semaines` (desktop : trois colonnes ; mobile : titre puis deux boutons) |
| `tests/pytest/test_benevolat_semaines.py` | Nouveau : 23 tests |
| `tests/e2e/test_benevolat_flow.py` | « Semaine suivante » sans rechargement, puis retour arrière |

Nouvelles chaînes à traduire (msgid FR) : « Changer de semaine », « Semaine précédente », « Semaine suivante », « Aucun besoin cette semaine. ».

---

## Comment tester (a la main) / Manual test

### Test 1 — navigation
1. Créer un planning publié avec des besoins sur trois semaines (admin, ou « Répéter des besoins »).
2. Ouvrir `/booking/benevolat/<slug>/` : la semaine du premier besoin s'affiche, sans « Semaine précédente » si c'est la semaine en cours.
3. Cliquer « Semaine suivante » : la zone change sans recharger, l'adresse porte `?semaine=`.
4. Retour arrière du navigateur : la première semaine revient.
5. Sur la dernière semaine, « Semaine suivante » a disparu.

### Test 2 — adresse
- `?semaine=` un dimanche → sa semaine (lundi → dimanche).
- `?semaine=abc` ou une date passée → la semaine par défaut.

### Test 3 — après une action
1. Connecté·e, aller sur la 3ᵉ semaine, cliquer « Je viens » : la zone reste sur cette semaine.
2. Le compteur de l'en-tête compte toujours tous les besoins à venir.

### Test 4 — mobile (375 px)
- Le titre de la semaine est sur sa ligne, les deux boutons dessous, sans débordement.

### Verifs automatiques
- `docker exec -w /DjangoFiles lespass_django poetry run pytest tests/pytest/test_benevolat_semaines.py -q`
- `make e2e benevolat`
