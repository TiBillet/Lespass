# Observatoire : mesurer l'usage, pas seulement l'argent / Observatory: measure usage, not only money

**Date :** 2026-11-13
**Migration :** Non
**Spec :** `TECH_DOC/SESSIONS/OBSERVATOIRE/CHANTIER-04-usages-hors-argent.md`

## Resume / Summary

**Quoi / What :** l'observatoire classe les lieux par la **régularité** de leur usage
(mois d'usage sur 12), et plus par leur chiffre d'affaires. Un mois d'usage = au moins
1 événement publié, 10 billets (gratuits compris), 200 € de CA, 5 adhésions, 200 € de
recharges, 20 paiements cashless ou 1 location. La « nature » devient des **usages**
(agenda, billetterie gratuite, billetterie payante, adhésions, caisse, location, réseau :
un lieu peut en avoir plusieurs) et un **rythme** lu sur le volume d'activité
(saisonnier, ponctuel, temps forts, régulier). La catégorie déclarée et « bidouillage »
disparaissent. Les paiements cashless de Fedow legacy (carte NFC et QR code) sont
rattachés à chaque lieu.
/ Venues are classified by regularity (months of use), not revenue. Nature becomes uses
(several per venue) and a rhythm read on activity volume. Legacy Fedow cashless sales are
attributed per venue.

**Pourquoi / Why :** en prod, 7 lieux sur 524 étaient « actifs ». Sur une copie de la prod,
55 % des billets sont gratuits et ne passent pas par une vente, et 38 lieux encaissent par
QR code dans Fedow legacy : ils étaient invisibles. Avec la nouvelle règle, environ 56
lieux sont actifs.
/ Only 7 of 524 venues were "active": free tickets and legacy cashless were invisible.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/observatoire.py` | Nouveaux compteurs : `billets_gratuits`, `billets_payants` (table des billets, mois de l'événement), `adhesions` (lignes de vente d'adhésion), `locations`, `transactions_cashless`, `portemonnaies_actifs` (V2 + Fedow legacy). Retirés : `inscriptions`, `cartes_actives`, `connexions_admin`. Événements : publiés, sans sous-événements. Un seul appel Fedow, avant la boucle. Ligne d'un lieu : catégorie retirée, `federe` ajouté |
| `seo/static/seo/observatoire.js` | Activité par mois d'usage (`actifMois`), usages multiples, rythme sur le volume, tendance (CA, ou mois d'usage sans CA avant). Matrice taille × rythme, filtres par usage et par rythme, colonne « Usages ». Clé du navigateur en `v4` |
| `seo/templates/seo/observatoire.html` | Filtres et choix (usage, rythme), bandeau Fedow legacy |
| `seo/views_observatoire.py` | Libellés et méthodes de calcul (bulles « ? ») |
| `tests/pytest/test_observatoire.py`, `tests/e2e/test_admin_observatoire.py` | 32 + 4 tests |
| `../Fedow` (autre dépôt) | `/statistiques_reseau/` rend aussi `ventes_par_lieu` (SAL + QRS par Place et par mois, 25 mois). Nouvelle clé de cache |

### Migration
- **Migration necessaire / Migration required :** Non

### Deploiement / Deployment
1. **Fedow d'abord** : pull, puis relancer gunicorn. Sans lui, les ventes legacy valent 0
   (le reste est calculé, la page le dit).
2. **Lespass** : pull, `collectstatic`, relancer gunicorn, daphne et celery.
3. **Tout de suite** : `manage.py refresh_observatoire`. Entre le déploiement et ce calcul,
   le cache garde l'ancien format, que la nouvelle page ne sait pas lire.
4. Le mainteneur lance `makemessages` / `compilemessages` (nouveaux textes).

## Tester / Test
- `docker exec lespass_django poetry run pytest tests/pytest/test_observatoire.py -q`
- `make e2e ARGS="tests/e2e/test_admin_observatoire.py"`
- Fedow : `poetry run python manage.py test fedow_core.tests.test_statistiques_reseau`
- À la main : `/admin/observatoire/` en superadmin. Un lieu qui n'a que des billets
  gratuits sur 3 mois apparaît « actif », avec l'usage « billetterie gratuite ».
