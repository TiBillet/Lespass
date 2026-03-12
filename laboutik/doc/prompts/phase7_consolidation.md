# Phase 7 — Consolidation et nettoyage

## Prompt

```
On travaille sur la Phase 7 du plan laboutik/doc/PLAN_INTEGRATION.md
(section 15 + section 17.7).

⚠️ CETTE PHASE NE DEMARRE QUE QUAND :
- Tous les anciens tenants sont migres (Phase 6 terminee pour chaque tenant)
- Plus aucun tenant n'a server_cashless renseigne
- Le mainteneur a valide la checklist section 17.7

Verification prerequis (faire AVANT de coder) :
docker exec lespass_django poetry run python manage.py shell -c "
from BaseBillet.models import Configuration
from Customers.models import Client
from django_tenants.utils import tenant_context
for client in Client.objects.exclude(schema_name='public'):
    with tenant_context(client):
        config = Configuration.get_solo()
        if config.server_cashless:
            print(f'BLOQUANT: {client.name} encore sur V1')
print('Check termine')
"

Si un tenant est encore sur V1 → STOP. Phase 7 impossible.

Tache :

PARTIE A — Recalcul des hash (fedow_core/management/commands/recalculate_hashes.py)

1. Parcourir toutes les Transaction par id croissant (BigAutoField)
2. Pour chaque transaction, calculer le hash SHA256 individuel :
   hash_data = json.dumps({
     "id": tx.id,
     "uuid": str(tx.uuid),
     "sender": str(tx.sender.uuid) if tx.sender else None,
     "receiver": str(tx.receiver.uuid) if tx.receiver else None,
     "asset": str(tx.asset.uuid),
     "amount": tx.amount,
     "datetime": tx.datetime.isoformat(),
     "action": tx.action,
     "card": str(tx.card.tag_id) if tx.card else None,
     "primary_card": str(tx.primary_card.tag_id) if tx.primary_card else None,
     "metadata": tx.metadata,
     "comment": tx.comment,
   }, sort_keys=True)
   hash = hashlib.sha256(hash_data.encode()).hexdigest()
3. Mettre a jour tx.hash (bulk_update par batch de 1000)
4. Afficher la progression (X / total, % complete)
5. Options :
   - --dry-run : calculer sans ecrire (afficher les 5 premiers hash)
   - --batch-size=1000 : taille des batch de bulk_update
   - --verify : recalculer et comparer avec le hash stocke (apres la migration NOT NULL)

PARTIE B — Migration Django : hash NOT NULL

6. Creer une migration Django :
   - AlterField : hash CharField(max_length=64, null=False, unique=True)
   ⚠️ A lancer APRES recalculate_hashes (sinon echec garanti — hash encore null)
   ⚠️ Verifier d'abord : Transaction.objects.filter(hash__isnull=True).count() == 0

PARTIE C — Nettoyage des mocks

7. AVANT de supprimer, auditer les imports :
   docker exec lespass_django poetry run python -c "
   import ast, sys
   for f in ['laboutik/views.py', 'laboutik/urls.py']:
       with open(f'/DjangoFiles/{f}') as fh:
           content = fh.read()
       for module in ['mockData', 'dbJson', 'mockDb', 'method']:
           if module in content:
               print(f'ATTENTION: {f} reference encore {module}')
   print('Audit termine')
   "

8. Si l'audit est clean, supprimer :
   - laboutik/utils/mockData.py
   - laboutik/utils/dbJson.py
   - laboutik/utils/mockDb.json
   - laboutik/utils/method.py
   - Les imports de ces fichiers restants (devrait etre deja fait)
   ⚠️ Lancer manage.py check APRES chaque suppression (pas tout d'un coup)

PARTIE D — Nettoyage fedow_connect

9. Auditer les references AVANT suppression :
   - Chercher tous les imports de fedow_connect dans le projet
   - Lister les fichiers qui importent fedow_connect.models (Asset, FedowConfig)
   - Lister les fichiers qui importent fedow_connect.fedow_api

10. Supprimer progressivement (1 fichier a la fois, manage.py check entre chaque) :
    - fedow_connect/fedow_api.py (700 lignes HTTP → remplace par fedow_core/services.py)
    - fedow_connect.Asset (miroir cache) + migration
    - fedow_connect.FedowConfig (config connexion distante) + migration

11. Adapter :
    - fedow_public/views.py → utiliser fedow_core.Asset au lieu de fedow_connect.Asset
    - Garder fedow_connect/validators.py si reutilises (chercher les imports)
    - Garder fedow_connect/utils.py (Fernet encryption) si reutilise (chercher les imports)

PARTIE E — Nettoyage fedow_public

12. Supprimer :
    - fedow_public.AssetFedowPublic → remplace par fedow_core.Asset + migration
    - Adapter fedow_public/views.py pour utiliser fedow_core.Asset

PARTIE F — Tests finaux

13. manage.py check
14. manage.py makemigrations --check --dry-run (pas de migration manquante)
15. verify_transactions sur chaque tenant
16. Lancer tous les tests pytest existants
17. Lancer les tests Playwright (au moins les critiques : 29, 31, 32, 33, 34, 35)

⚠️ Chaque suppression = manage.py check AVANT de supprimer le fichier suivant.
⚠️ NE PAS supprimer fedow_connect entierement (garder validators/utils si utilises).
⚠️ Cette phase est methodique et repetitive. Pas besoin de se presser.
```

## Tests

### pytest

```python
# Pas de nouveau fichier de test, mais verifier que TOUT passe :
# docker exec lespass_django poetry run pytest tests/pytest/ -v
#
# Tests specifiques a ajouter dans test_fedow_core.py :
# 1. test_recalculate_hashes — toutes les transactions ont un hash non null
# 2. test_hash_unique — pas de doublons
# 3. test_hash_deterministe — recalculer 2 fois donne le meme hash
#
# Tests de regression apres nettoyage :
# 4. test_import_fedow_core_apres_nettoyage — "from fedow_core.models import Asset" OK
# 5. test_import_fedow_connect_supprime — "from fedow_connect.models import Asset" → ImportError
```

### Playwright

```
Lancer les tests critiques un par un :
yarn playwright test --project=chromium --headed --workers=1 tests/29-admin-proxy-products.spec.ts
yarn playwright test --project=chromium --headed --workers=1 tests/31-admin-asset-federation.spec.ts
yarn playwright test --project=chromium --headed --workers=1 tests/32-laboutik-caisse-db.spec.ts
yarn playwright test --project=chromium --headed --workers=1 tests/33-laboutik-paiement-nfc.spec.ts
yarn playwright test --project=chromium --headed --workers=1 tests/34-laboutik-commandes.spec.ts
yarn playwright test --project=chromium --headed --workers=1 tests/35-laboutik-cloture.spec.ts
```

### Verification manuelle

- recalculate_hashes termine sans erreur
- Migration hash NOT NULL appliquee
- Transaction.objects.filter(hash__isnull=True).count() == 0
- Tous les mocks supprimes, aucun import casse
- fedow_connect nettoye (seuls validators/utils restent si utilises)
- manage.py check passe
- verify_transactions passe pour tous les tenants

## Checklist fin d'etape

- [ ] recalculate_hashes OK (dry-run puis reel)
- [ ] Migration hash NOT NULL appliquee
- [ ] Mocks supprimes (4 fichiers)
- [ ] fedow_connect.fedow_api.py supprime
- [ ] fedow_connect.Asset et FedowConfig supprimes + migrations
- [ ] fedow_public.AssetFedowPublic supprime + migration
- [ ] `manage.py check` passe
- [ ] `manage.py makemigrations --check --dry-run` → pas de migration manquante
- [ ] Tous les pytest verts
- [ ] Tous les Playwright critiques verts
- [ ] verify_transactions OK sur tous les tenants
- [ ] Mettre a jour CHANGELOG.md
- [ ] Creer `A TESTER et DOCUMENTER/phase7-consolidation.md`

## Modele recommande

Sonnet — nettoyage methodique, pattern repetitif
