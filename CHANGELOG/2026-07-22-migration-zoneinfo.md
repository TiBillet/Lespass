# Migration pytz → zoneinfo et correction du décalage horaire de la journée commerciale / Migration from pytz to zoneinfo and business-day time drift fix

**Date :** 2026-07-22
**Migration :** Oui — `BaseBillet/migrations/0225_fuseau_horaire_choix_zoneinfo.py`
(`AlterField` purement déclarative sur `Configuration.fuseau_horaire`, aucun SQL de données)

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```

## Resume / Summary

**Quoi / What :** tout le code manipulant le fuseau du lieu passe de `pytz` à `zoneinfo`
(bibliothèque standard). Au passage, la « journée commerciale » de 4 h à 4 h ne dérive plus
d'une heure les deux nuits de changement d'heure.
/ All venue-timezone code moves from `pytz` to the standard library `zoneinfo`. As a side
effect, the 4am-to-4am business day no longer drifts by an hour on the two DST nights.

**Pourquoi / Why :** deux raisons.

1. **Compatibilité Django 5.** En Django 4.2, `make_aware(dt, zone)` détecte pytz et appelle
   `zone.localize(dt)`. Django 5 supprime cette détection et fait un `replace(tzinfo=...)`
   direct : avec un objet pytz, on obtient l'offset **LMT** (temps solaire de Paris figé en
   1891, `+00:09`). Le code aurait cassé silencieusement à la montée de version.
   / Django 5 drops pytz detection in `make_aware`, yielding the LMT offset (`+00:09`).

2. **Un bug de bord déjà présent en production.** `borne_temps_4h()` calculait
   `localize(minuit) + timedelta(hours=4)`. `localize` fige l'offset de minuit, puis
   l'addition est absolue : les jours de bascule, la borne tombait à côté.
   / A live edge-case bug: freezing midnight's offset before adding 4 hours drifts the bound.

## Changement de comportement observable / Observable behaviour change

La journée commerciale sert au ticket Z automatique. En festival, l'activité se termine vers
4 h du matin : les ventes de fin de nuit doivent être rattachées à la journée écoulée.

| Nuit | Borne de début, avant | après |
|---|---|---|
| 29/03/2026 (entrée heure d'été) | **05:00** locales | 04:00 |
| 25/10/2026 (retour heure d'hiver) | **03:00** locales | 04:00 |
| tout autre jour | 04:00 | 04:00 (inchangé) |

Concrètement : deux fois par an, des ventes de fin de soirée pouvaient tomber dans le mauvais
rapport Z. Ce n'est plus le cas.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `get_tzinfo()` renvoie un `ZoneInfo` ; `TZ_CHOICES` construit depuis `sorted(zoneinfo.available_timezones())` ; `Event.save` utilise `get_tzinfo()` |
| `BaseBillet/migrations/0225_fuseau_horaire_choix_zoneinfo.py` | `AlterField` sur les `choices` (597 → 599 fuseaux), déclarative |
| `ApiBillet/views.py` | `borne_temps_4h()` : fuseau posé avant l'ajout des 4 h → **correction DST**. `is_dst=None` retiré (inatteignable : minuit et 23:59:59 ne sont jamais ambigus) |
| `Administration/admin_tenant.py` | filtre de dates : `.localize()` → `.replace(tzinfo=...)` |
| `Administration/importers/ticket_exporter.py` | `get_tzinfo()` au lieu de reconstruire le fuseau |
| `Administration/importers/lignearticle_exporter.py` | idem ; repli `pytz.UTC` → `datetime.timezone.utc` |
| `BaseBillet/validators.py` | `_get_tz()` délègue à `get_tzinfo()` ; `.localize()` → `.replace(tzinfo=...)` |
| `tests/pytest/test_borne_temps_journee_commerciale.py` | **nouveau** — 4 tests, rouges avant le correctif |
| `tests/pytest/test_exporters_fuseau_horaire.py` | **nouveau** — 6 tests sur les dates de l'export comptable |

`pytz` reste installé (dépendance de **flower**) mais n'est plus utilisé par le projet.

**Note pour le filtre admin :** sur une heure ambiguë saisie à la main (2 fois par an, entre
2 h et 3 h du matin), `ZoneInfo` retient la première occurrence là où pytz retenait l'heure
d'hiver. Écart d'une heure sur un filtre d'affichage, sans effet sur les données.

---

## Comment tester (a la main) / Manual test

### Test 1 — la journée commerciale aux deux bascules

Doit afficher `04:00` dans les deux cas :

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from unittest.mock import patch
import datetime as dt, zoneinfo
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import Configuration
from ApiBillet.views import borne_temps_4h
tenant = Client.objects.get(schema_name='lespass')
with tenant_context(tenant):
    tz = zoneinfo.ZoneInfo(Configuration.get_solo().fuseau_horaire)
for jour in [dt.date(2026, 3, 29), dt.date(2026, 10, 25), dt.date(2026, 7, 15)]:
    midi = dt.datetime.combine(jour, dt.time(12, 0)).replace(tzinfo=tz)
    with tenant_context(tenant), patch('ApiBillet.views.timezone.now', return_value=midi):
        debut, fin = borne_temps_4h()
    print(jour, '-> debut', debut.astimezone(tz).strftime('%H:%M'))
"
```

### Test 2 — l'export comptable date au jour local

1. Admin → Ventes → sélectionner une période contenant une vente passée **après minuit**
   heure du lieu
2. Exporter en CSV
3. Vérifier que la colonne `date` porte le jour **local** de la vente (une vente à 00 h 30 à
   Paris le 16 doit afficher le 16, alors qu'elle est stockée le 15 à 22 h 30 UTC)

### Test 3 — l'admin affiche toujours les fuseaux

1. Admin → Configuration → champ « Timezone »
2. La liste déroulante est triée alphabétiquement et contient `Europe/Paris` et
   `Indian/Reunion`
3. Enregistrer sans changer la valeur : aucune erreur

### Verifs automatiques / Automated checks

```bash
# Aucun pytz ne doit subsister dans le code (hors commentaires explicatifs)
rg -n "pytz" -t py -g '!.venv/*' -g '!*/migrations/*'

docker exec lespass_django poetry run pytest tests/pytest/test_borne_temps_journee_commerciale.py -v
docker exec lespass_django poetry run pytest tests/pytest/test_exporters_fuseau_horaire.py -v
docker exec lespass_django poetry run pytest tests/pytest/test_timezone_middleware.py -v
```
