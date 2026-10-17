# Bénévolat, chantier 8 : semaine type et page « Besoins » / Volunteering, step 8: template week and "Needs" page

**Date :** 2026-10-17
**Migration :** Oui — `booking/0004_semaine_type.py` (`docker exec lespass_django poetry run python manage.py migrate_schemas`). Plannings existants : ponctuels, aucune migration de données.

## Resume / Summary
**Quoi / What :** un planning est « Ponctuel » (comme avant) ou « Chaque semaine ». En mode hebdomadaire, une **semaine type** (lignes « jour + tâche + heures + nombre », dans la fiche du planning) crée les besoins réels de `date_de_debut` à `date_de_fin` (vide = sans fin), `horizon_en_semaines` à l'avance (1 à 26). La création a lieu à l'enregistrement de la fiche et chaque nuit (Celery, 3 h UTC, tous les lieux). Modifier la semaine type ne touche que les besoins futurs **sans inscrit** qui suivent leur ligne ; l'admin affiche « N besoins créés, M mis à jour, P supprimés. K besoins avec des inscrits n'ont pas été modifiés : voir la page Besoins. ». Nouvelle page d'admin **« Besoins »** (tous les plannings, « À venir » par défaut, filtres planning / tâche / avec-sans inscrit·es, navigation par date). Index `(planning, date)` sur les besoins.
/ A planning is one-off or weekly. A weekly planning's template week creates real needs over a rolling horizon, on save and every night. Editing it only touches future needs without sign-ups. New admin "Needs" page, upcoming by default. Index on (planning, date).

**Pourquoi / Why :** chantier 8 de `TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md` (§11.2 à §11.4, D29 à D34) : un bar ouvert deux soirs par semaine toute l'année ne doit pas être ressaisi chaque mois.

Points notables :
- `besoins_crees_jusqu_au` ne recule jamais : un besoin supprimé à la main n'est jamais recréé ;
- un verrou (`select_for_update` sur le planning) empêche l'enregistrement de la fiche et la tâche de nuit de créer deux fois les mêmes besoins ;
- un besoin modifié un par un (page « Besoins », inline, API `PATCH`) qui ne correspond plus à sa ligne en est **détaché** (`BesoinBenevole.save`) : c'est une exception manuelle, que la ligne n'écrase jamais. Un `POST /api/v2/volunteer-needs/` crée un besoin manuel ;
- la fiche montre **soit** la semaine type (hebdomadaire), **soit** les besoins à venir (ponctuel), selon le type enregistré ; « Répéter des besoins » est masqué et refusé (403) pour un planning hebdomadaire (D34) ;
- la carte du bloc d'accueil dit « chaque semaine » pour un planning hebdomadaire ;
- premier jour avancé : les jours ajoutés (jusqu'à l'ancien premier jour) sont créés ; premier jour reculé ou dernier jour avancé : les besoins futurs sans inscrit sortis de la période sont supprimés.

Relecture Fable (2026-10-17) appliquée : création des jours quand le premier jour est avancé (bug), requêtes de l'inline de la semaine type, focus sur le titre de la semaine après un changement de semaine (chantier 7), `logger.exception` dans les boucles par lieu (rappel et semaine type), trois tests en plus.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/models.py`, `booking/migrations/0004_semaine_type.py` | `PlanningBenevole` : `type_de_planning`, `date_de_debut`, `date_de_fin`, `horizon_en_semaines`, `besoins_crees_jusqu_au`, `clean()` ; nouveau `LigneDeSemaineType` ; `BesoinBenevole.ligne_de_semaine_type`, index, détachement dans `save()` ; `verifier_les_heures` partagée |
| `booking/benevolat.py` | `besoins_de_la_semaine_type` (calcul pur), `aujourd_hui_au_lieu`, `creer_des_besoins_pour_ces_lignes`, `creer_les_besoins_de_la_semaine_type`, `appliquer_la_semaine_type_modifiee` ; `chaque_semaine` dans les cartes |
| `booking/tasks.py`, `TiBillet/celery.py` | Tâche de nuit `creer_les_besoins_des_semaines_types` (3 h UTC) |
| `Administration/admin/benevolat.py` | Inline de la semaine type, inlines selon le type, `save_related` (D30), champs conditionnels, « Répéter » bloqué, `BesoinBenevoleAdmin` et ses filtres |
| `Administration/admin/dashboard.py` | Entrée « Besoins bénévoles » dans le menu du module |
| `booking/templates/booking/benevolat/partials/cartes_accueil.html` | « chaque semaine » |
| `booking/tests/test_benevolat_semaine_type.py` | Nouveau : 36 tests |
| `tests/pytest/test_benevolat_api.py`, `tests/pytest/test_benevolat_module.py` | Besoin manuel par l'API ; quatre pages dans le menu |

Nouvelles chaînes à traduire (msgid FR) : types de planning, jours de la semaine, libellés et aides des nouveaux champs, filtres « Quand / À venir / Passés / Tous », « Inscrit·es / Avec inscrit·es / Sans inscrit·e », message de la semaine type, « Voir tous les besoins de ce planning », « Besoins bénévoles », « chaque semaine ».

**Après déploiement :** redémarrer Celery (`supervisorctl restart … celery`) pour charger la nouvelle tâche de nuit.

---

## Comment tester (a la main) / Manual test

### Test 1 — créer un planning hebdomadaire
1. Admin → Bénévolat → Plannings bénévoles → Ajouter. Type « Chaque semaine », premier jour = aujourd'hui, 4 semaines. Enregistrer.
2. La fiche montre maintenant « Semaine type » (plus les besoins). Ajouter : vendredi, bar, 18:00–00:00, 2 ; samedi, accueil, heures vides, 1. Enregistrer.
3. Message « N besoins créés… ». « Voir tous les besoins de ce planning » → la page « Besoins » liste les vendredis et samedis des 4 semaines.
4. La page publique montre une semaine à la fois ; la carte du bloc d'accueil dit « chaque semaine ».

### Test 2 — modifier la semaine type
1. S'inscrire (site public) sur le prochain vendredi.
2. Admin : passer la ligne du vendredi à 3 personnes. Enregistrer.
3. Message : « 0 besoins créés, X mis à jour, 0 supprimés. 1 besoins avec des inscrits n'ont pas été modifiés : voir la page Besoins. »
4. Le vendredi avec inscrit garde 2 ; les autres passent à 3.
5. Changer le jour de la ligne (vendredi → jeudi) : les vendredis sans inscrit disparaissent, les jeudis apparaissent.
6. Supprimer la ligne : ses besoins sans inscrit disparaissent ; celui avec inscrit reste.

### Test 3 — exception manuelle
1. Page « Besoins » : ouvrir un samedi, passer à 4 personnes, enregistrer.
2. Fiche du planning : passer la ligne du samedi à 2. Le samedi modifié garde 4.

### Test 4 — « Répéter » et page « Besoins »
- Sur un planning hebdomadaire, le bouton « Répéter des besoins » n'apparaît pas ; `/admin/booking/planningbenevole/<uuid>/repeter/` rend 403.
- Page « Besoins » : « À venir » par défaut ; filtres « Passés », « Tous », planning, tâche, avec / sans inscrit·es.

### Test 5 — tâche de nuit
```bash
docker exec -w /DjangoFiles lespass_django poetry run python manage.py shell -c "from booking.tasks import creer_les_besoins_des_semaines_types; creer_les_besoins_des_semaines_types()"
```
Relancer ne crée rien de plus.

### Verifs automatiques
- `docker exec -w /DjangoFiles lespass_django poetry run pytest booking/tests/test_benevolat_semaine_type.py -q`
- `docker exec -w /DjangoFiles lespass_django poetry run pytest tests/pytest/test_benevolat_*.py booking/tests -q`
