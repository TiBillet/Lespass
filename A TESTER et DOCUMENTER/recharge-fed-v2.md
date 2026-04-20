# Recharge FED V2 — Guide de test mainteneur

Session 31 du plan de fusion mono-repo. Phases A, B, C terminées.
Spec complète : `TECH DOC/Laboutik sessions/Session 31 - Recharge FED V2/SPEC_RECHARGE_FED_V2.md`.

## Ce qui a été fait

### Phase A — Modèle + service
- Nouvelle catégorie `Client.FED = 'E'`
- Nouveau `Product.categorie_article=RECHARGE_CASHLESS_FED` ("E")
- Nouveau `Paiement_stripe.source=CASHLESS_REFILL` ("R")
- Management command `bootstrap_fed_asset` idempotente (crée tenant `federation_fed` + root wallet + Asset FED + Product/Price de recharge)
- Serializer `RefillAmountSerializer` (1 € min / 500 € max, centimes int)
- Service `RefillService.process_cashless_refill()` (idempotent, crée Transaction REFILL + crédite Token)
- Documentation contrat multi-PSP : `fedow_core/PSP_INTERFACE.md`

### Phase B — Gateway Stripe + webhook + verrous admin
- `CreationPaiementStripeFederation` (compte central, CB uniquement, pas SEPA)
- Handler webhook `_process_stripe_webhook_cashless_refill` avec anti-tampering + idempotence
- Dispatch dans `Webhook_stripe.post` avant le legacy : `if metadata.refill_type == 'FED'`
- Verrous admin : Asset FED lecture seule, Product de recharge non créable via admin

### Phase C — Vues utilisateur + templates HTMX
- Helper `peut_recharger_v2(user)` avec 4 verdicts
- `MyAccount.refill_wallet()` réécrite (dispatch 4 branches)
- Nouvelle action `MyAccount.refill_wallet_submit()` (POST, formulaire V2)
- `MyAccount.return_refill_wallet()` dispatch V1/V2
- Templates : `refill_form_v2.html` + `refill_migration_inline.html`

### Phase C+ — Pattern "webhook + retour user" (convergence)
- Fonction commune `ApiBillet.views.traiter_paiement_cashless_refill()` appelée depuis :
  - Le webhook Stripe (`Webhook_stripe.post` → `_process_stripe_webhook_cashless_refill`)
  - La vue de retour user (`MyAccount.return_refill_wallet`)
- Idempotente via `select_for_update` + re-check status après lock
- Appel Stripe `checkout.Session.retrieve()` HORS atomic (latence réseau n'immobilise pas le pool DB)
- Exception custom `CashlessRefillTamperingError` pour signaler un anti-tampering
- 6 tests pytest dédiés : `tests/pytest/test_traiter_paiement_cashless_refill.py`

## Avant de tester

### 1. Appliquer les migrations

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```

### 2. Bootstrap de l'infrastructure V2

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py bootstrap_fed_asset
```

Attendu (premier run) :
```
Tenant federation_fed cree (schema PostgreSQL auto-genere).
Migration des TENANT_APPS dans federation_fed...
Migrations appliquees.
Root wallet cree : <uuid>
Asset FED cree : <uuid>
Product de recharge FED cree : <uuid>
Price de recharge FED cree : <uuid>

Bootstrap FED V2 termine.
```

Attendu (runs suivants, idempotent) :
```
Tenant federation_fed deja present, reutilise.

Bootstrap FED V2 termine.
```

## Tests à réaliser

### Test 1 — Configuration du tenant "lespass" en mode V2

Vérifier que le tenant `lespass` est bien en mode V2 pour la recharge :

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import Configuration

tenant = Client.objects.get(schema_name='lespass')
with tenant_context(tenant):
    config = Configuration.get_solo()
    print(f'module_monnaie_locale : {config.module_monnaie_locale}')
    print(f'server_cashless : {config.server_cashless}')
"
```

Attendu : `module_monnaie_locale: True` et `server_cashless: None` (ou vide).

Si besoin : aller dans l'admin Unfold → Configuration → activer `module_monnaie_locale` et vider `server_cashless`.

### Test 2 — Flow V2 complet (test manuel navigateur)

**Carte Stripe test : `4242 4242 4242 4242`, nom `Douglas Adams`, date `12/42`, code `424`**

1. Lancer le serveur ASGI : `docker exec lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002` (ou via Traefik avec alias `rsp`)
2. Ouvrir `https://lespass.tibillet.localhost/my_account/`
3. Login avec `admin@admin.com`
4. Cliquer sur "Wallet" (ou le tab wallet)
5. Cliquer "Refill my wallet"

   **Attendu :** le formulaire V2 s'affiche (`data-testid="refill-form-container"`) avec :
   - Titre "Recharger ma tirelire fédérée"
   - Champ montant en euros (step=0.01, min=1, max=500)
   - Bouton "Payer par carte bancaire"
   - Bouton "Annuler"

6. Saisir `15.00` et cliquer "Payer"

   **Attendu :** redirection vers `https://checkout.stripe.com/...`

7. Saisir la carte test 4242, date 12/42, code 424

   **Attendu :** Stripe valide, redirect vers `https://lespass.tibillet.localhost/my_account/<paiement_uuid>/return_refill_wallet/`
   puis redirect final `/my_account/` avec message "Wallet rechargé avec succès" (ou "Payment in progress. Please refresh in a moment." si le webhook est lent)

8. Rafraîchir la page si besoin, vérifier le solde dans "Wallet"

### Test 3 — Idempotence webhook (shell)

Rejouer manuellement le webhook Stripe via shell :

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
import uuid
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import Paiement_stripe
from fedow_core.models import Transaction
from fedow_core.services import RefillService

tenant = Client.objects.get(schema_name='federation_fed')
with tenant_context(tenant):
    paiement = Paiement_stripe.objects.filter(source=Paiement_stripe.CASHLESS_REFILL, status=Paiement_stripe.PAID).last()
    if paiement is None:
        print('Aucun paiement CASHLESS_REFILL trouve. Lance le flow V2 d\\'abord.')
    else:
        # Appeler RefillService 2 fois avec le meme paiement_uuid
        tx1 = RefillService.process_cashless_refill(
            paiement_uuid=paiement.uuid,
            user=paiement.user,
            amount_cents=int(paiement.total() * 100),
            tenant=tenant,
        )
        tx2 = RefillService.process_cashless_refill(
            paiement_uuid=paiement.uuid,
            user=paiement.user,
            amount_cents=int(paiement.total() * 100),
            tenant=tenant,
        )
        print(f'Meme Transaction : {tx1.pk == tx2.pk}')
        count = Transaction.objects.filter(
            checkout_stripe=paiement.uuid, action=Transaction.REFILL
        ).count()
        print(f'Nombre de Transaction REFILL pour ce paiement : {count}')
"
```

Attendu :
```
Meme Transaction : True
Nombre de Transaction REFILL pour ce paiement : 1
```

### Test 4 — Vérification en base

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from fedow_core.models import Transaction, Token, Asset

asset_fed = Asset.objects.get(category=Asset.FED)
print(f'Asset FED : {asset_fed.name} ({asset_fed.uuid})')

# Dernieres Transactions REFILL
# / Latest REFILL Transactions
transactions_refill = Transaction.objects.filter(
    action=Transaction.REFILL, asset=asset_fed
).order_by('-datetime')[:5]

for tx in transactions_refill:
    print(f'  #{tx.id} | {tx.amount} cents | receiver={tx.receiver.name} | paiement={tx.checkout_stripe}')

# Soldes FED non nuls
# / Non-zero FED balances
tokens_fed = Token.objects.filter(asset=asset_fed, value__gt=0)
print(f'\\n{tokens_fed.count()} wallet(s) avec solde FED > 0')
"
```

### Test 5 — Verrou admin Asset FED

1. Ouvrir l'admin Unfold en tant que superuser
2. Aller dans "Assets" (sidebar Fedow)

   **Attendu :** l'Asset FED n'est **pas** visible (il appartient à `tenant_origin=federation_fed`, invisible depuis les autres tenants).

3. Essayer de créer un Asset

   **Attendu :** le dropdown de catégorie propose TLF, TNF, TIM, FID — **pas FED** (exclu via `get_form` ligne 277 de `fedow_core/admin.py`).

### Test 6 — Bouton refill invisible si module désactivé

1. Dans l'admin → Configuration du tenant → désactiver `module_monnaie_locale`
2. Aller sur `/my_account/wallet/`

   **Attendu :** le bouton "Refill my wallet" est toujours présent (template non conditionné) — **limitation connue, à faire en Phase D-polish**.

3. Cliquer sur le bouton

   **Attendu :** message d'erreur "Not available. Contact an admin." et redirect `/my_account/`.

## Scénarios Playwright (à écrire en Phase D-polish)

À écrire dans `tests/e2e/test_cashless_refill_flow.py` :

1. `test_cashless_refill_flow_v2` : login → refill → montant 15€ → Stripe 4242 → return → solde à jour
2. `test_cashless_refill_legacy_tenant` : tenant avec `server_cashless` set → flow V1 intact
3. `test_cashless_refill_wallet_legacy_message` : user avec wallet origin V1 → voit `data-testid="refill-message-migration"`
4. `test_cashless_refill_module_disabled` : `module_monnaie_locale=False` → message d'erreur

## Commits à faire (côté mainteneur)

Suggestion : un commit par phase (A, B, C) pour la traçabilité, ou un seul commit global "Session 31 Phase A+B+C".

Messages suggérés dans les fichiers :
- `TECH DOC/Laboutik sessions/Session 31 - Recharge FED V2/PLAN_PHASE_A.md`
- `TECH DOC/Laboutik sessions/Session 31 - Recharge FED V2/PLAN_PHASE_B.md`

## Workflow i18n (obligatoire djc)

Nouveaux strings traduits ajoutés dans :
- `PaiementStripe/serializers.py` (error_messages)
- `fedow_core/admin.py` (help texts)
- `BaseBillet/views.py` (messages.add_message)
- Templates `refill_form_v2.html` + `refill_migration_inline.html`

Exécuter :

```bash
docker exec lespass_django poetry run django-admin makemessages -l fr -l en
# Editer locale/fr/LC_MESSAGES/django.po et locale/en/LC_MESSAGES/django.po :
#   - Remplir les msgstr manquants
#   - Verifier les flags #, fuzzy
docker exec lespass_django poetry run django-admin compilemessages
```

## Compatibilité

- **Zéro rupture** : aucun code existant ne référence les nouveaux éléments
- **Tenants V1 (legacy)** : flow inchangé (FedowAPI distant)
- **Tenants V2** : nouveau flow local
- **Fedow distant** : reste obligatoire au démarrage (`install.py` inchangé) pour les features non migrées (adhésions, rewards, etc.)
- **Tests existants** : 36 tests (17 fedow_core + 19 Stripe) intacts, 0 régression

## Prochaine session proposée

**Session 31 Phase D-polish** :
- Tests E2E Playwright (4 scénarios)
- Condition template `my_account_wallet.html` : masquer bouton si `module_monnaie_locale=False`
- Affichage double section wallet (legacy + V2) si les deux soldes coexistent
- Tests pytest nice-to-have (5 restants)
