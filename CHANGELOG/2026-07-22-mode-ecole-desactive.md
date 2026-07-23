# Archivage fiscal LNE repare, mode ecole desactive / LNE archive fixed, training mode disabled

**Date :** 2026-07-22
**Migration :** Oui — `laboutik/migrations/0002_alter_laboutikconfiguration_mode_ecole.py`
(`AlterField` sur un `help_text`, **no-op cote SQL**, verifie par `sqlmigrate`)

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```

## Resume / Summary

**Quoi / What :** L'archivage fiscal LNE ne pouvait plus s'executer. Il est repare. Le mode
ecole, qui en etait la cause, est desactive proprement en attendant un chantier de remise en
conformite.
/ The LNE fiscal archive could no longer run. It is fixed. Training mode, which caused it,
is cleanly disabled pending compliance work.

**Pourquoi / Why :** Trois endroits du code referencaient `SaleOrigin.LABOUTIK_TEST`, une
valeur **absente de l'enumeration**. Verifie en execution reelle :

```
>>> generer_fichiers_archive(schema='lespass')
AttributeError: LABOUTIK_TEST
```

Consequences : l'archivage fiscal etait mort pour tout le monde — `laboutik/views.py`, et les
commandes `archiver_donnees`, `verifier_archive`, `acces_fiscal` — et activer le mode ecole
faisait planter **tout encaissement** au point de vente. Aucun test ne couvrait ce chemin.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/archivage.py` | Filtre sur `SaleOrigin.LABOUTIK` seul. **Debloque l'archivage fiscal** |
| `laboutik/views.py` (deux fonctions de creation de lignes) | Branche `if mode_ecole` retiree : toute vente est une vente reelle |
| `laboutik/models.py` | `mode_ecole` : `help_text` marque « DESACTIVE », commentaire expliquant pourquoi |
| `Administration/admin/laboutik.py` | `mode_ecole` retire du fieldset : plus activable depuis l'admin |
| `tests/pytest/test_archivage_fiscal_lne.py` | **Nouveau** — 4 tests, dont deux garde-fous contre les valeurs fantomes |

Le champ `mode_ecole` **reste en base**, a `False`. Le bandeau POS
(`laboutik/templates/cotton/header.html`) et la mention « SIMULATION » du ticket
(`laboutik/printing/formatters.py`) le lisent toujours : ils sont inertes tant qu'il vaut
`False`, et les laisser en place evite de les reecrire quand le chantier reprendra.

Verifie avant la desactivation : **aucune ligne ni aucun ticket ne porte l'origine `LT`** en
base (scan de tous les tenants). La desactivation ne rend donc aucune donnee orpheline.

## Pourquoi desactiver plutot que reparer

L'audit du prototype (`../old-v2-proto`, ou le mecanisme est complet en 11 pieces) montre que
la simple restauration de la constante manquante serait un **piege** :

`comptabilite/services.py:59` et `:168` construisent la cloture comptable en ligne avec
`.exclude(sale_origin=SaleOrigin.LABOUTIK)`. Cette app n'existe pas dans le prototype. Des
que l'origine de test existerait, les ventes de formation **entreraient dans la cloture
comptable** — l'inverse exact de l'exigence LNE. On echangerait un plantage bruyant et
immediatement visible contre une faussete comptable silencieuse, sur un logiciel de caisse
sous norme fiscale.

Par ailleurs, le prototype lui-meme etait incomplet : les billets de billetterie POS
restaient marques en vente reelle, cinq formatters de ticket sur six ne portaient pas la
mention « SIMULATION », les listes de ventes du POS filtraient l'origine en dur (l'operateur
ne revoyait pas ses propres ventes de formation), et rien ne journalisait le basculement de
mode. Remettre la constante ne produirait donc pas un mode ecole conforme, seulement un mode
ecole qui ne plante pas.

/ Restoring the missing constant would be a trap: the online accounting closure excludes
LABOUTIK only, so training sales would enter it — the exact opposite of the requirement. And
the prototype's mechanism was itself incomplete.

## Chantier a ouvrir / Follow-up work

Remise en conformite du mode ecole (LNE exigence 5), estimee a 1,5–3 jours. Les pieces, par
ordre de dependance :

1. `LABOUTIK_TEST = "LT"` dans `SaleOrigin` (le code `LT` est libre sur ce champ) + migration
   `AlterField` sur `lignearticle.sale_origin` et `ticket.sale_origin`
2. **`comptabilite/services.py:59` et `:168`** — exclure aussi l'origine de test (le piege
   ci-dessus ; inedit, absent du prototype)
3. Documenter l'exclusion dans `ORIGINES_ENCAISSEES_PAR_LE_LIEU` (`laboutik/reports.py`)
4. Rapatrier et adapter `tests/pytest/test_mode_ecole.py` depuis le prototype
5. Marquer les billets de billetterie POS (`laboutik/views.py`, `Ticket.objects.create`)
6. Mention « SIMULATION » sur les cinq autres formatters de ticket
7. Rendre les ventes de formation visibles dans les listes du POS (sept filtres en dur)
8. Traiter `TIREUSE`, `QRCODE_MA` et `NFC_MA` en mode ecole — sinon une biere tiree ou un
   paiement QR pendant une formation entre dans le chiffre d'affaires reel
9. Journaliser le basculement de mode (qui, quand) — attendu par un auditeur
10. Tests E2E : bandeau visible, mention sur le ticket

Note : la spec `TECH_DOC/SESSIONS/LABOUTIK/DONE/Session 02 .../15_mode_ecole_exports_admin.md`
est classee **DONE** et cochee dans l'INDEX alors qu'elle ne l'est pas.

---

## Comment tester (a la main) / Manual test

### Test 1 — l'archivage fiscal fonctionne

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
with tenant_context(Client.objects.get(schema_name='lespass')):
    from laboutik.archivage import generer_fichiers_archive
    print(list(generer_fichiers_archive(schema='lespass').keys()))"
```

Doit lister les cinq CSV. Avant le correctif : `AttributeError: LABOUTIK_TEST`.

### Test 2 — la commande d'archivage aboutit

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py archiver_donnees --help
```

### Test 3 — le mode ecole n'est plus proposé

Aller sur `/admin/laboutik/laboutikconfiguration/`, section « Interface caisse ». La case
« Training mode » ne doit plus apparaitre. Une vente au point de vente doit fonctionner
normalement.

### Tests automatiques

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_archivage_fiscal_lne.py -v
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/ -q
```

Etat au moment de l'ecriture : **1015 tests verts en 2 min 41**, aucun echec.
