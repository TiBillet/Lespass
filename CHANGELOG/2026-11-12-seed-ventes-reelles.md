# Seed de démo : des ventes réelles, comme en production / Demo seed: real sales, as in production

**Date :** 2026-11-12
**Migration :** Non

## Resume / Summary

**Quoi / What :** le seed des ventes de `demo_data_v2` écrit maintenant ses ventes par le
vrai moteur de vente (`BaseBillet/services_vente.py` : `Vente`, articles, `Reglement`,
encaissement chaîné, avoirs). Il couvre les 24 mois complets avant le mois en cours, avec
le même programme chaque mois (billets, adhésions, caisse du Bar, recharges `R`, `E` et
de caisse, gratuits, offert, jetons cadeau, deux avoirs) : 30 ventes et 1 000,00 € de
chiffre d'affaires par mois. Il crée ensuite les clôtures J, H, M et A des périodes
finies, jour après jour, comme la tâche horaire. Relancer ne double rien ;
`--reset-sales` efface toutes les ventes et clôtures du lieu, sous garde-fou `DEBUG` +
`TEST`, après un passage à blanc.
/ The demo sales seed now writes its sales through the real sales engine, over the 24
full months before the current one (30 sales, 1,000.00 € revenue a month), then creates
the J, H, M, A closures day by day. Re-running doubles nothing; `--reset-sales` wipes the
venue's sales and closures, guarded by DEBUG + TEST, after a dry run.

**Pourquoi / Why :** l'ancien seed créait les articles sans vente : rapports, clôtures,
FEC et API comptable ne les voyaient pas (37 articles sur 48 sans vente sur `lespass`).
Le dev doit ressembler à la production après la reprise des ventes.
/ The old seed wrote items without a sale, invisible to reports, closures and exports.
Dev must look like production after the sales takeover.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/management/commands/_demo_data_v2_ventes.py` | Réécrit : historique par le moteur (`seed_ventes_demo`), clôtures jour après jour (`seed_clotures_demo`), reset sous garde-fou (`reinitialiser_les_ventes_du_lieu`), garde des ventes d'hier fondée sur hier 0 h |
| `Administration/management/commands/_demo_data_v2_recap.py` | Garde : bloque si une J finit après hier 0 h (plus « le lieu a une J ») |
| `Administration/management/commands/demo_data_v2.py` | Une seule étape des ventes, après le seed de la caisse : historique, hier, récap, clôtures, bilan |
| `tests/pytest/test_demo_data_ventes.py` | Réécrit : schéma dédié, 8 tests (vente de chaque article, M à 1 000 €, ordre et chaîne, export des J, cas couverts, idempotence, reset) |
| `tests/pytest/test_demo_ventes_de_la_veille.py` | + 1 test : les ventes d'hier après un historique |
| `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-07-seed-ventes-reelles.md` | Nouvelle spec |
| `TECH_DOC/SESSIONS/COMPTABILITE/INDEX.md` | Ligne du chantier 07 |

---

## Comment tester (a la main) / Manual test

### Test 1 — refaire les ventes de `lespass`
1. `docker exec lespass_django poetry run python /DjangoFiles/manage.py demo_data_v2 --sales-only --reset-sales`
2. La sortie affiche le passage à blanc, puis le reset réel, puis
   « Historique : 720 ventes, 744 articles, 24 mois (1000.00 EUR de CA par mois) », les
   ventes d'hier et du récap, et « Clotures creees : {'J': 49, 'H': 48, 'M': 24, 'A': 2} »
   (environ une minute).
3. Le bilan dit « 0 article(s) [DEMO] sans vente » et les trois dernières M à 1 000,00 €.

### Test 2 — relancer ne double rien
1. `docker exec lespass_django poetry run python /DjangoFiles/manage.py demo_data_v2 --sales-only`
2. Attendu : « Historique : le lieu a deja des ventes ou des clotures, rien d'ajoute »,
   les ventes d'hier sautées, « Clotures creees : {'J': 0, 'H': 0, 'M': 0, 'A': 0} ».

### Test 3 — dans l'admin
1. `https://lespass.tibillet.localhost/admin/comptabilite/cloturecaisse/` : une M par mois
   sur 24 mois, chacune à 1 000,00 €, 30 ventes ; les A 2024 (2 000 €) et 2025
   (12 000 €).
2. Ouvrir la J d'une soirée concert (du 6 à 4 h au 7 à 4 h) : 670,00 €, journaux ADMIN,
   BAR, CASHLESS, WEB ; FEC téléchargeable. Celle d'une journée atelier (le 20) : 330,00 €,
   journaux ADMIN et WEB.
3. Menu des ventes : les ventes sont numérotées dans l'ordre de leurs heures ; la fiche
   d'un avoir montre sa vente liée.

### Verifs DB
```python
# docker exec -i lespass_django poetry run python /DjangoFiles/manage.py shell
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import LigneArticle
from comptabilite.models import ClotureCaisse
from laboutik.integrity import verifier_chaine_ventes
from laboutik.models import LaboutikConfiguration
with tenant_context(Client.objects.get(schema_name="lespass")):
    print(LigneArticle.objects.filter(vente__isnull=True, pricesold__productsold__product__name__startswith="[DEMO] ").count())  # 0
    print(ClotureCaisse.objects.filter(niveau="M").exclude(total_general=100000).count())  # 0
    print(len(verifier_chaine_ventes(LaboutikConfiguration.get_solo().get_or_create_hmac_key())))  # 0
```

### Hors périmètre
Les 13 lignes de démo de `laboutik/management/commands/create_test_pos_data.py` restent
sans vente (fichier utilisé par beaucoup de tests, à traiter à part).
