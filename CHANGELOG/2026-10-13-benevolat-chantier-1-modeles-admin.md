# Bénévolat, chantier 1 : modèles et admin du planning des bénévoles / Volunteering, step 1: volunteer planning models and admin

**Date :** 2026-10-13
**Migration :** Oui — `booking/0002_benevolat.py` (TENANT_APPS : passe sur chaque lieu)

## Resume / Summary
**Quoi / What :** quatre modèles dans l'app `booking` : `TacheBenevole` (le catalogue des tâches du lieu), `PlanningBenevole` (un tableau de besoins, avec ses adhésions requises et son calendrier de fermetures), `BesoinBenevole` (une tâche, un jour, une plage facultative, un nombre souhaité) et `InscriptionBenevole` (une personne sur un besoin). Leur admin Unfold, rangé dans le menu « Réservation de ressources ».
/ Four models in `booking` (task catalogue, planning, need, sign-up) and their Unfold admin.

**Pourquoi / Why :** premier chantier de la spec `TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md` (§4, §5.6). La page publique, l'inscription et l'API viennent aux chantiers suivants.
/ First step of the volunteering spec; public page, sign-up and API come next.

Points notables :
- clé primaire `uuid` sur les quatre modèles (D25) : identifiant de l'API v2 et du futur lien de désistement signé ;
- `nombre_souhaite` est un objectif, pas un plafond ; méthodes `debut()`, `fin()` (fin le lendemain si `heure_fin <= heure_debut`), `est_passe()`, `places_couvertes()`, `places_libres()`, `nombre_de_renforts()` ;
- `PlanningBenevole.date_est_fermee()` et `libelle_de_fermeture()` lisent les `ClosedPeriod` du calendrier choisi ;
- les slugs `besoin` et `desistement` sont refusés (segments des futures routes) ;
- un besoin saisi un jour fermé est enregistré, la colonne « Fermeture » de la ligne le signale ;
- l'admin des inscriptions n'a pas de formulaire d'ajout (liste de tous les comptes de l'instance, et `admin.E039` en autocomplétion) : lecture, recherche par prénom, nom, email, suppression.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/models.py` | Les quatre modèles et leurs méthodes |
| `booking/migrations/0002_benevolat.py` | Nouvelle migration |
| `Administration/admin/benevolat.py` | Nouveau : `TacheBenevoleAdmin`, `PlanningBenevoleAdmin` (+ `BesoinBenevoleInline`), `InscriptionBenevoleAdmin` |
| `Administration/admin_tenant.py` | Import à effet de bord du nouveau module (`# noqa: F401`) |
| `Administration/admin/dashboard.py` | Trois entrées de menu dans `module_booking`, leurs textes d'aide et leurs verbes |
| `booking/tests/test_benevolat_models.py` | 14 tests (contraintes, dates, compteurs, fermetures, admin), vérifiés par mutation |
| `TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md` | Relecture Fable du 2026-10-13 intégrée (D25 à D27) |

i18n : nouvelles chaînes traduisibles (msgid en français), workflow i18n à lancer par le mainteneur.

---

## Comment tester (a la main) / Manual test

### Test 1 — créer un planning
1. Se connecter avec `admin@admin.com`, module « Réservation de ressources » actif.
2. Menu → « Tâches bénévoles » → ajouter « Tenir le bar ».
3. Menu → « Plannings bénévoles » → ajouter « Bar associatif : octobre » ; l'adresse se remplit seule.
4. Ajouter deux besoins : un jour 18:00–21:00, nombre 2 ; un autre jour sans heure.
5. Attendu : enregistrement OK, colonne « Inscrit·es » à `0/2`.

### Test 2 — jour fermé
1. Choisir un calendrier qui a une fermeture, ajouter un besoin ce jour-là.
2. Attendu : le besoin est enregistré, sa ligne affiche « Fermé : <libellé> ».

### Test 3 — garde-fous
1. Remplir seulement l'heure de début → message « Remplissez les deux heures, ou aucune ».
2. Mettre l'adresse `desistement` → refusée.
3. « Inscriptions bénévoles » : pas de bouton « Ajouter ».

### Verifs automatiques
- `docker exec lespass_django poetry run pytest /DjangoFiles/booking/tests/test_benevolat_models.py -q`
