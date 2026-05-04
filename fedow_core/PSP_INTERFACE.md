# PSP Interface — Contrat de recharge FED

> Pour ajouter un nouveau PSP (Payplug, Lydia, Stripe alternatif…), respecter ce contrat.

## Responsabilités

### Ce que le PSP fait

1. **Création d'un checkout / intent de paiement** dans son propre module (`PaiementXxx/refill_federation.py`)
   - Créer le `Paiement_xxx` en base (dans le tenant `federation_fed`)
   - Injecter la metadata requise (voir section "Metadata attendue")
   - Configurer le return URL vers `/my_account/<paiement_uuid>/return_refill_wallet/`
   - **Pas de compte connecté** : la recharge FED utilise le compte central du PSP
   - **Pas de paiement différé** (SEPA, virement, etc.) : UX recharge immédiate seulement
2. **Gestion du webhook PSP** (dans `ApiBillet/views.py` ou un module dédié)
   - Valider la signature du webhook (sécurité PSP)
   - Extraire la metadata
   - Anti-tampering : vérifier que le montant PSP correspond au montant stocké en base
   - Appeler `RefillService.process_cashless_refill(...)` avec les bons arguments
   - Marquer le `Paiement_xxx.status = PAID`

### Ce que `RefillService` fait (fourni par `fedow_core`)

- Vérifier l'idempotence (pas de doublon si le webhook est rejoué)
- Créer `Transaction(action=REFILL, asset=FED, amount=amount_cents, ...)` dans `federation_fed`
- Créditer `Token(wallet=user.wallet, asset=FED).value` atomiquement
- Retourner la `Transaction` (nouvelle ou existante)

Le PSP n'a **jamais** à toucher directement aux `Token`, `Wallet`, ou `Transaction`. Tout passe par `RefillService`.

## Signature de `RefillService.process_cashless_refill`

```python
from fedow_core.services import RefillService
from fedow_core.models import Transaction

tx: Transaction = RefillService.process_cashless_refill(
    paiement_uuid=paiement.uuid,        # UUID — identifiant stable du paiement externe
    user=paiement.user,                 # TibilletUser — bénéficiaire du crédit
    amount_cents=int(...),              # int centimes — montant validé et sécurisé
    tenant=tenant_federation_fed,       # Client — doit être le tenant federation_fed
    ip=get_request_ip(request),         # str — IP de la requête pour audit
)
```

## Metadata attendue sur le paiement PSP

Pour que le webhook puisse retrouver le contexte, injecter au minimum :

| Clé | Valeur | Usage côté webhook |
|---|---|---|
| `tenant` | UUID du tenant `federation_fed` | Charger le bon schéma avant `Paiement_xxx.objects.get()` |
| `paiement_xxx_uuid` | UUID du paiement | Retrouver l'enregistrement local |
| `refill_type` | `'FED'` | Dispatch dans le webhook (filtre : c'est une recharge FED) |
| `wallet_receiver_uuid` | UUID du wallet user | Debug / audit |
| `asset_uuid` | UUID de l'asset FED | Debug / audit |

Chaque PSP adapte les noms si son système impose des contraintes (ex: Stripe accepte des clés libres, d'autres limitent à certains noms).

## Checklist d'implémentation d'un nouveau PSP

- [ ] Créer `Paiement<PSP>` en TENANT_APPS avec au minimum : `uuid`, `user`, `source` (avec valeur `CASHLESS_REFILL`), `status`, lien vers `LigneArticle`
- [ ] Créer `Paiement<PSP>/refill_federation.py` avec une classe `CreationPaiement<PSP>Federation`
- [ ] Ajouter une action dans le webhook `<PSP>` qui filtre `metadata.refill_type == 'FED'` et appelle `RefillService.process_cashless_refill`
- [ ] Tests pytest : nominal, idempotence, anti-tampering
- [ ] Pas de compte connecté, pas de paiement différé
- [ ] Respecter la structure `tenant_context(tenant_federation_fed)` pour toutes les opérations TENANT_APPS

## Référence

- Spec produit : `TECH DOC/Laboutik sessions/Session 31 - Recharge FED V2/SPEC_RECHARGE_FED_V2.md`
- Implémentation Stripe de référence (Phase B) : `PaiementStripe/refill_federation.py` + `ApiBillet/views.py:1042+`
