# Observatoire des instances / Instance observatory

**Date :** 2026-11-12
**Migration :** Oui — `seo/migrations/0007_alter_seocache_cache_type.py` (ajout d'un choix,
aucun SQL : `sqlmigrate seo 0007` affiche `(no-op)`). Commande :
`docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --shared`

## Resume / Summary

**Quoi / What :** une page de l'admin, réservée au superadmin (menu « Root Configuration »
→ « Observatoire des instances »), qui montre l'activité de chaque lieu du réseau mois par
mois sur 24 mois et classe les lieux (très actif, actif, peu utilisé, bidouillage, sommeil ;
festival, lieu, mixte…). Le calcul tourne chaque nuit (Celery beat, 2 h 30) ou par
`manage.py refresh_observatoire`, jamais depuis la page. L'argent vient des clôtures
comptables (mensuelles, puis journalières du mois en cours).
/ A superadmin-only admin page showing each venue's monthly activity over 24 months and
classifying venues. Computed nightly or by `manage.py`, never from the page. Money comes
from the accounting closures.

**Pourquoi / Why :** savoir quels lieux utilisent vraiment TiBillet, sans charger le
serveur ni recalculer le chiffre d'affaires à côté des tickets Z.
/ Know which venues really use TiBillet, without server load nor a second revenue rule.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/observatoire.py` | Nouveau : le calcul (4 requêtes sur le public et 1 appel Fedow, puis 8 par lieu) |
| `seo/management/commands/refresh_observatoire.py` | Nouveau : la commande ; n'écrit rien si aucun lieu n'a été lu |
| `seo/views_observatoire.py` | Nouveau : la page, GET seul, 403 si pas superadmin, textes traduits |
| `seo/templates/seo/observatoire.html` | Nouveau : le gabarit (cadre Unfold) |
| `seo/static/seo/observatoire.js`, `observatoire.css` | Nouveaux : classement et graphiques (repris du prototype, réécrits) |
| `seo/models.py`, `seo/migrations/0007_*` | Choix `OBSERVATOIRE` de `SEOCache` |
| `Administration/admin/site.py` | Route `/admin/observatoire/` |
| `Administration/admin/dashboard.py` | Entrée du menu « Root Configuration » |
| `TiBillet/celery.py` | Beat `cron_refresh_observatoire` à 2 h 30 |
| `flush.sh` | `refresh_observatoire` après les données de démo : la page est remplie dès la fin du flush |
| `tests/pytest/test_observatoire.py`, `tests/e2e/test_admin_observatoire.py` | 22 + 2 tests |
| `TECH_DOC/SESSIONS/OBSERVATOIRE/` | Nouveau hub (spec, chantier 02 à faire plus tard) |
| `../Fedow` (autre dépôt) | Route `GET /statistiques_reseau/` (clé root, lecture seule, cache 1 h) : recharges par asset et cartes. **À déployer** pour que le bloc réseau affiche recharges et cartes |

---

## Comment tester (a la main) / Manual test

### Test 1 — scénario nominal
1. `docker exec lespass_django poetry run python /DjangoFiles/manage.py refresh_observatoire`
   → une ligne par lieu sur stderr, puis « Observatoire enregistré : N lieux ».
2. Se connecter en superadmin sur `https://lespass.tibillet.localhost/admin/`.
3. Menu « Root Configuration » → « Observatoire des instances ».
4. Vérifier : la date du calcul, le bilan (lieux lus), les tuiles, la matrice, le graphique,
   la liste. En dev, les chiffres sont faibles (le seed de démo n'a pas encore de vraies
   ventes sur 24 mois : voir `COMPTABILITE/CHANTIER-07-seed-ventes-reelles.md`).
5. Ouvrir « Régler les seuils de classement », changer un seuil : la page se reclasse
   sans se recharger.

### Test 1 bis — le réseau depuis le début
1. En haut de la page : lieux, utilisateurs, transactions (recharges), billets, cartes,
   heures de bénévolat, chacun avec « ≈ ».
2. Tant que la route Fedow n'est pas déployée, « Transactions » et « Cartes » affichent
   « Fedow legacy n'a pas répondu ». Après déploiement : relancer `refresh_observatoire`.

### Test 2 — droits
1. Se connecter avec un admin du lieu qui n'est PAS superadmin : le menu n'a pas l'entrée,
   et `/admin/observatoire/` répond 403.
2. Non connecté : `/admin/observatoire/` renvoie vers l'accueil.

### Test 3 — cache vide
1. `docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "from seo.models import SEOCache; SEOCache.objects.filter(cache_type='observatoire').delete()"`
2. Ouvrir la page : message « Aucun calcul pour l'instant ». Aucun calcul n'est lancé.
3. Relancer `refresh_observatoire` pour retrouver les chiffres.

### Vérifs DB / Playwright
- `docker exec lespass_django bash -c "ulimit -v 8000000; timeout 600 poetry run pytest tests/pytest/test_observatoire.py -q"`
- `make e2e ARGS="tests/e2e/test_admin_observatoire.py"`
- En production, avant d'activer le beat : lancer une fois la commande à la main et lire la
  durée par lieu.
- **Ordre de déploiement :** Fedow d'abord (route `statistiques_reseau`), puis Lespass. Sinon
  chaque nuit journalise une erreur « Fedow legacy n'a pas répondu ».
