# SPEC — Recharge FED V2 (fedow_core, sans Fedow distant)

**Date :** 2026-04-19
**Statut :** Design validé après brainstorm du 2026-04-19, prêt pour writing-plans
**Scope :** Recharge utilisateur de la monnaie fédérée FED depuis Lespass (interface web).
Remplace le passage par le serveur Fedow legacy **pour les nouveaux tenants V2 uniquement**.
Les tenants legacy (avec LaBoutik externe connecté) continuent d'utiliser le flow V1 inchangé.

---

## 1. Contexte et problème

### Situation actuelle (legacy)

La recharge FED passe par **3 acteurs** avec HTTP + signature RSA inter-service :

1. Lespass (UI, `BaseBillet/views.py:1071`)
2. Fedow serveur distant (crée la session Stripe, reçoit le webhook, gère les tokens)
3. Stripe (paiement bancaire)

Points de friction :

- Dépendance critique au serveur Fedow distant.
- Race condition webhook POST vs GET return (gérée par polling 10s côté Fedow).
- Double signature (RSA inter-service + Django Signer sur metadata Stripe).
- `Paiement_stripe` côté Lespass n'enregistre rien pour les recharges FED (webhook rejette en HTTP 205).
- Hash chain Fedow avec typo historique (`checkoupt_stripe`).

### Décision stratégique

Le plan de fusion mono-repo (cf. `PLAN_LABOUTIK.md`) remplace Fedow distant par l'app `fedow_core` en SHARED_APPS. La recharge FED est **le cas d'usage n°1** à réécrire en accès DB direct.

**Coexistence V1/V2 (stricte, par tenant) :**

| Situation | Flow |
|---|---|
| `module_monnaie_locale=False` | Pas de feature, bouton refill invisible |
| `module_monnaie_locale=True AND server_cashless IS NULL` | **V2** (cette spec) |
| `server_cashless IS NOT NULL` (LaBoutik externe connecté) | **V1** inchangé (FedowAPI distant) |

Règle cohérente avec le POS V2 (cf. PLAN_LABOUTIK.md:158-165). Un tenant avec LaBoutik externe doit rester sur V1 pour que les tokens du POS et les tokens de recharge soient dans la même base.

### Audit Fedow legacy

L'audit de suppression complète de `FedowAPI` a identifié **36 usages non gardés** répartis sur 13 fichiers (wallet, transactions POS, webhooks Stripe, admin, validators). Rendre Fedow distant optionnel = **chantier 5-7 jours (Phase E)**, hors scope Session 31.

→ **`install.py` reste inchangé**. Fedow distant reste obligatoire au démarrage pour les features non migrées (adhésions, rewards, etc.). Seul l'ajout : hook `call_command('bootstrap_fed_asset')` dans `install.py`.

---

## 2. Décisions architecturales validées

| Décision | Valeur | Raison |
|---|---|---|
| **Moteur cible** | `fedow_core` (SHARED_APPS) | Pas de HTTP, pas de RSA, accès DB direct |
| **Séparation moyen/résultat** | `Paiement_stripe` (moyen) ≠ `Transaction(action=REFILL)` (résultat) | Changement de PSP sans toucher à la logique wallet |
| **Classe de création Stripe** | `CreationPaiementStripeFederation` dans `PaiementStripe/refill_federation.py` | Séparée de `CreationPaiementStripe` existante : pas de Stripe Connect, compte central, logique minimale |
| **Contrat multi-PSP** | Documenté dans `fedow_core/PSP_INTERFACE.md` | Pas d'ABC (YAGNI). Contrat implicite dans signature `RefillService.process_cashless_refill()` |
| **Tenant de stockage** | Tenant dédié `federation_fed` (catégorie `Client.FED = 'E'`) | Isolation comptable propre, pas de pollution des rapports lieux |
| **Bootstrap** | Management command `bootstrap_fed_asset` + hook dans `install.py` + ajout dans `create_test_pos_data` | Idempotent, explicite, FALC |
| **Produit métier** | `Product(categorie_article=RECHARGE_CASHLESS_FED)` | Cohérent avec catalogue, réutilise `Price.asset` |
| **Saisie montant** | Côté TiBillet (pas `custom_unit_amount` Stripe) | Portabilité multi-PSP |
| **Min/max** | Hardcodés **100 centimes (1€)** et **50000 centimes (500€)** dans `RefillAmountSerializer` | Simple, YAGNI. Déplaçable sur Asset plus tard si besoin |
| **Price Stripe** | Créé à la volée via `get_or_create_price_sold(custom_amount=...)` | Pattern existant (`ApiBillet/serializers.py`). `Asset.FED.id_price_stripe` reste null |
| **SEPA** | Interdit (`accept_sepa=False`) | UX recharge immédiate, SEPA = 2-5 jours |
| **Wallet sender REFILL** | `Asset.FED.wallet_origin` (pot central) | Pas de singleton `primary_wallet` séparé |
| **Unicité Asset FED** | Convention (pas de contrainte DB) + admin en lecture seule pour category=FED | 1 seul asset FED global, créé par bootstrap uniquement |
| **Unicité Product recharge FED** | Convention + admin interdit de créer un Product sur l'asset FED | Création réservée au bootstrap |
| **Idempotence webhook + retour user** | Fonction commune `traiter_paiement_cashless_refill()` + `select_for_update` sur `Paiement_stripe` + re-check status après lock | Permet au user qui revient vite de déclencher le traitement si le webhook est en retard. Concurrency-safe via row lock, pas de flag applicatif |
| **Stripe API call position** | Hors de `transaction.atomic()` (le verrou ne retient jamais pendant l'appel réseau) | Protège le pool DB des latences réseau (1-3s Stripe) |
| **Hash chain** | **Non reprise** (décision globale fedow_core) | Hash individuel par transaction, pas de chaîne |
| **Affichage wallet user** | Deux sections côte à côte (legacy + V2) si présence | Cohabitation assumée tant que Fedow legacy existe |
| **Block user legacy** | Si `user.wallet.origin` pointe vers un tenant V1 → refus avec message "migration en cours" | Évite doubles tokens incohérents |
| **Détection legacy** | Dans `tenant_context(user.wallet.origin)` → lire `Configuration.get_solo().server_cashless` | Déterministe, zéro HTTP |
| **Workflow djc obligatoire** | CHANGELOG.md + `makemessages`/`compilemessages` + fichier `A TESTER et DOCUMENTER/recharge-fed-v2.md` | Conformité stack djc (cf. skill) |
| **Visibilité Transaction REFILL** | `Transaction.tenant = federation_fed` — **pas** dans le tenant du lieu où l'user a cliqué | Isolation comptable stricte. Stats conversion par lieu reportées à une feature future (YAGNI) |

---

## 3. Architecture cible (4 couches)

```
┌──────────────────────────────────────────────────────────────┐
│  COUCHE 1 — INTENTION métier (catalogue)                     │
│  Product(categorie_article=RECHARGE_CASHLESS_FED)            │
│  Price(asset=FED)                                            │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  COUCHE 2 — GATEWAY PSP (remplaçable)                        │
│  CreationPaiementStripeFederation (Stripe, compte central)   │
│  → demain : CreationPaiementPayplugFederation, etc.          │
│  Contrat commun : fedow_core/PSP_INTERFACE.md                │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  COUCHE 3 — MOYEN de paiement (persistance)                  │
│  Paiement_stripe(source=CASHLESS_REFILL)                     │
│  LigneArticle(payment_method=STRIPE_FED, amount=...)         │
│  Stocké dans le schema federation_fed                        │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  COUCHE 4 — RÉSULTAT wallet (moteur fedow_core)              │
│  RefillService.process_cashless_refill()                     │
│  Transaction(action=REFILL, asset=FED, amount=...)           │
│  Token.value += amount (select_for_update)                   │
└──────────────────────────────────────────────────────────────┘
```

### Point d'entrée unique pour créer la Transaction REFILL

Tout futur PSP appelle **la même fonction** :

```python
# fedow_core/services.py
class RefillService:
    @staticmethod
    def process_cashless_refill(
        paiement_uuid,   # UUID générique, pas un modèle Django
        user,            # TibilletUser
        amount_cents,    # int centimes
        tenant,          # Client (federation_fed)
        ip,              # str
    ) -> Transaction:
        """
        Idempotent. Crée une Transaction(action=REFILL) et crédite le
        Token du user. Appelable depuis n'importe quel webhook PSP.
        Contrat : fedow_core/PSP_INTERFACE.md
        """
```

### Pas de Stripe Connect

`CreationPaiementStripeFederation` n'injecte **pas** `stripe_account` dans `stripe.checkout.Session.create()`. L'argent arrive sur le compte Stripe **root** (`RootConfiguration.get_stripe_api()`), pas sur le compte connecté du lieu. Cohérent avec la nature fédérée de FED : une seule trésorerie partagée.

---

## 4. Flow utilisateur complet (V2)

### Étape 1 — Clic sur "Recharger"

**Vue :** `MyAccount.refill_wallet()` (`BaseBillet/views.py:1071`)

Trois gardes avant d'afficher le formulaire :

```python
def peut_recharger_v2(user):
    """
    Retourne (True, "v2") si l'user peut recharger en V2.
    Sinon (False, <raison>) avec une des raisons :
    - "feature_desactivee" : module_monnaie_locale=False
    - "v1_legacy" : tenant courant a server_cashless (LaBoutik externe)
    - "wallet_legacy" : wallet de l'user origine d'un tenant V1

    Le tenant courant est lu depuis connection.tenant (via Configuration.get_solo()).
    """
    # Garde 1 : le tenant courant est en mode V2
    config = Configuration.get_solo()
    if not config.module_monnaie_locale:
        return False, "feature_desactivee"   # pas de bouton refill

    if config.server_cashless is not None:
        return False, "v1_legacy"             # flow V1 inchangé

    # Garde 2 : le wallet de l'user n'est pas lié à un tenant V1
    if user.wallet and user.wallet.origin:
        with tenant_context(user.wallet.origin):
            config_origin = Configuration.get_solo()
            if config_origin.server_cashless is not None:
                return False, "wallet_legacy"  # message "migration en cours"

    return True, "v2"
```

**Comportement selon le verdict :**

| Verdict | Action |
|---|---|
| `"feature_desactivee"` | Bouton refill invisible (géré côté template par `{% if config.module_monnaie_locale %}`) |
| `"v1_legacy"` | Flow V1 inchangé (appel `FedowAPI()`) |
| `"wallet_legacy"` | Message FALC : *"Votre wallet est en cours de migration. Merci de patienter, désolés pour la gêne occasionnée."* |
| `"v2"` | Formulaire HTMX avec champ montant |

### Étape 2 — Saisie du montant

**Convention de conversion euros ↔ centimes :**

- **Template** : l'user saisit un nombre en euros (ex : `10,50`) dans un champ `amount_euros` (type decimal)
- **Vue** : la vue reçoit `amount_euros` en POST, convertit en `amount_cents = int(Decimal(amount_euros_str.replace(',', '.')) * 100)`
- **Serializer** : valide `amount_cents` (int) contre les bornes
- **`get_or_create_price_sold`** : attend `custom_amount` en **Decimal euros** → reconvertir `Decimal(amount_cents) / 100` avant appel

Règle simple : `amount_cents` (int centimes) est la source de vérité partout, sauf pour `PriceSold.prix` qui est stocké en `Decimal` euros (existant, pas touché).

```python
# PaiementStripe/serializers.py
class RefillAmountSerializer(serializers.Serializer):
    """
    Valide un montant de recharge FED saisi en centimes.
    La conversion euros → centimes est faite par la vue avant d'appeler ce serializer.
    """
    MIN_CENTS = 100    # 1,00 EUR
    MAX_CENTS = 50000  # 500,00 EUR

    amount_cents = serializers.IntegerField(
        min_value=MIN_CENTS,
        max_value=MAX_CENTS,
        error_messages={
            'min_value': _('Montant minimum : 1,00 €'),
            'max_value': _('Montant maximum : 500,00 €'),
        },
    )
```

### Étape 3 — Création du paiement

**Préambule 1 : capturer le domain du tenant courant AVANT toute bascule.**
Le return URL Stripe doit pointer vers le domaine du lieu où l'user a cliqué, pas vers `federation_fed` (qui n'a pas de Domain). Une fois qu'on entre dans `tenant_context(federation_fed)`, `connection.tenant` change — donc on capture avant :

```python
# Dans MyAccount.refill_wallet() — AVANT toute bascule
tenant_courant_domain = connection.tenant.get_primary_domain().domain
absolute_domain = f'https://{tenant_courant_domain}/my_account/'

tenant_federation = Client.objects.get(schema_name='federation_fed')
```

**Préambule 2 : création du wallet si absent.**
Si `user.wallet is None`, on crée le wallet avant l'entrée dans Stripe (la metadata a besoin de `wallet.uuid`). `Wallet` et `TibilletUser` sont en SHARED_APPS — **pas besoin** de `tenant_context(federation_fed)` pour cette création. Seul le champ `origin` doit pointer vers `federation_fed` pour la cohérence V2 :

```python
if user.wallet is None:
    user.wallet = Wallet.objects.create(
        origin=tenant_federation,
        name=f"Wallet {user.email}",
    )
    user.save(update_fields=['wallet'])
```

**Bascule dans `federation_fed`** pour créer les objets TENANT_APPS (`Product`, `Price`, `PriceSold`, `LigneArticle`, `Paiement_stripe`) :

```python
with tenant_context(tenant_federation):
    # 1. Asset FED (SHARED_APPS, accessible partout — on est dans le bon
    #    context pour les accès TENANT_APPS qui suivent)
    asset_fed = Asset.objects.get(category=Asset.FED)

    # 2. Product/Price de recharge (créés au bootstrap, vivent dans federation_fed)
    product_refill = Product.objects.get(categorie_article=Product.RECHARGE_CASHLESS_FED)
    price_refill = product_refill.prices.first()

    # 3. PriceSold — conversion centimes → Decimal euros pour custom_amount
    #    car get_or_create_price_sold() stocke PriceSold.prix en Decimal euros
    from decimal import Decimal
    custom_amount_euros = Decimal(amount_cents) / Decimal(100)
    pricesold = get_or_create_price_sold(price_refill, custom_amount=custom_amount_euros)

    # 4. LigneArticle — amount en centimes (convention existante)
    ligne = LigneArticle.objects.create(
        pricesold=pricesold,
        amount=amount_cents,
        qty=1,
        payment_method=PaymentMethod.STRIPE_FED,
    )

    # 5. Création paiement via gateway — la classe crée le Paiement_stripe en interne
    paiement_creator = CreationPaiementStripeFederation(
        user=user,
        liste_ligne_article=[ligne],
        wallet_receiver=user.wallet,
        asset_fed=asset_fed,
        tenant_federation=tenant_federation,
        absolute_domain=absolute_domain,   # capturé AVANT la bascule
        success_url='return_refill_wallet/',
    )
    return HttpResponseClientRedirect(paiement_creator.checkout_session.url)
```

**Responsabilité de `CreationPaiementStripeFederation` :**

1. Crée le `Paiement_stripe(source=CASHLESS_REFILL, user=user)` en base
2. Lie la `LigneArticle` au `Paiement_stripe`
3. Construit le `metadata` Stripe et la `success_url`
4. Appelle `stripe.checkout.Session.create(**data)` **sans `stripe_account`** (compte central)
5. **Interdit SEPA** : `payment_method_types=['card']` uniquement
6. Persiste `checkout_session_id_stripe` + `checkout_session_url` sur le `Paiement_stripe`

**Metadata Stripe injectée par la gateway :**

```python
metadata = {
    'tenant': f'{tenant_federation.uuid}',
    'paiement_stripe_uuid': f'{paiement.uuid}',  # créé par la gateway
    'refill_type': 'FED',
    'wallet_receiver_uuid': f'{user.wallet.uuid}',
    'asset_uuid': f'{asset_fed.uuid}',
}
```

Pas de Django `Signer` : la sécurité est assurée par la signature Stripe du webhook (`stripe.Webhook.construct_event`) et la relecture de `Paiement_stripe.uuid` côté serveur.

### Étape 4 — Paiement sur Stripe

Flux Stripe Checkout standard, **CB uniquement** (SEPA interdit).

**Return URL** : le user revient sur le domaine du tenant où il a cliqué (celui sur lequel il navigue actuellement, pas `federation_fed` qui n'a pas de domain) :
```
https://{tenant_courant.domain}/my_account/{paiement.uuid}/return_refill_wallet/
```

La vue `return_refill_wallet` tourne alors dans le tenant courant, puis bascule dans `federation_fed` via `tenant_context` pour lire le `Paiement_stripe`.

### Étape 5 — Webhook Stripe

**`ApiBillet/views.py:1042`** — modification. Le dispatch FED V2 est placé **AVANT** le check legacy `if "return_refill_wallet" in success_url` (qui retournait HTTP 205 pour rejeter les webhooks Fedow distant). Ce check legacy reste en place (tenants V1) mais ne matchera jamais les paiements V2 (car la success_url V2 pointe vers le tenant courant, pas vers un endpoint Fedow).

```python
if payload.get('type') in ("checkout.session.completed",):
    metadata = payload["data"]["object"]["metadata"]

    # === DISPATCH V2 (NOUVEAU, avant tout le reste) ===
    # Si la metadata contient refill_type=FED, c'est une recharge V2
    if metadata.get('refill_type') == 'FED':
        return _process_stripe_webhook_cashless_refill(payload, request)

    # === LEGACY (inchangé) ===
    # Rejet des webhooks destinés à Fedow distant
    if "return_refill_wallet" in payload["data"]["object"]["success_url"]:
        return Response(f"Ce checkout est pour fedow.", status=status.HTTP_205_RESET_CONTENT)

    # ... suite existante pour les autres sources (BILLETTERIE, CROWDS, INVOICE)
```

**Fonction `_process_stripe_webhook_cashless_refill()`** (extraite pour lisibilité) :

```python
def _process_stripe_webhook_cashless_refill(payload, request):
    """
    Traite un webhook Stripe de recharge FED V2.
    Crée la Transaction REFILL via RefillService (idempotent).
    """
    metadata = payload["data"]["object"]["metadata"]
    tenant_uuid = metadata.get('tenant')
    paiement_uuid = metadata.get('paiement_stripe_uuid')

    tenant = Client.objects.get(uuid=tenant_uuid)
    with tenant_context(tenant):
        paiement = Paiement_stripe.objects.get(uuid=paiement_uuid)
        if paiement.source != Paiement_stripe.CASHLESS_REFILL:
            return Response("Not a cashless refill", status=400)

        # Anti-tampering : comparer montant Stripe (int centimes) et paiement.total()
        # paiement.total() retourne un Decimal (dround), on convertit en int centimes
        stripe_amount_cents = payload["data"]["object"]["amount_total"]  # int
        paiement_amount_cents = int(paiement.total() * 100)
        if stripe_amount_cents != paiement_amount_cents:
            logger.error(
                f"Tampering détecté : Stripe {stripe_amount_cents} != "
                f"paiement {paiement_amount_cents}"
            )
            return Response("Amount mismatch", status=400)

        RefillService.process_cashless_refill(
            paiement_uuid=paiement.uuid,
            user=paiement.user,
            amount_cents=paiement_amount_cents,
            tenant=tenant,
            ip=get_request_ip(request),
        )
        paiement.status = Paiement_stripe.PAID
        paiement.save(update_fields=['status'])
        return Response("OK", status=200)
```

**Note bug `paiement.total()`** : la méthode existante retourne `dround(total)` (Decimal). Pour comparer avec `amount_total` Stripe (int centimes), on convertit via `int(paiement.total() * 100)`. Alternative propre : ajouter une méthode `paiement.total_cents() -> int` sur le modèle — envisageable en refactoring mais pas bloquant pour cette spec.

### Étape 6 — Création de la Transaction

**`RefillService.process_cashless_refill()`** dans `fedow_core/services.py` :

```python
@staticmethod
def process_cashless_refill(paiement_uuid, user, amount_cents, tenant, ip):
    """
    Crée une Transaction(action=REFILL) idempotente.
    Contrat PSP-agnostique : voir PSP_INTERFACE.md

    Normalement, user.wallet existe déjà (créé par MyAccount.refill_wallet
    avant l'entrée dans Stripe — car la metadata a besoin de wallet.uuid).
    La création du wallet ici est un fallback défensif pour les scénarios
    où le webhook arrive alors que le wallet aurait été supprimé entre-temps.
    """
    asset_fed = Asset.objects.get(category=Asset.FED)  # unique global

    # Idempotence : si déjà créée, retourner l'existante
    with transaction.atomic():
        tx_existante = Transaction.objects.filter(
            checkout_stripe=paiement_uuid,
            action=Transaction.REFILL,
        ).first()
        if tx_existante:
            return tx_existante

        # Fallback défensif : créer le wallet si absent (normalement déjà fait en amont)
        if user.wallet is None:
            user.wallet = Wallet.objects.create(
                origin=tenant,  # federation_fed
                name=f"Wallet {user.email}",
            )
            user.save(update_fields=['wallet'])

        # Création Transaction + crédit Token atomique
        # Note : TransactionService.creer_recharge() fait son propre atomic() imbriqué,
        # géré par Django via savepoint — pas de problème.
        return TransactionService.creer_recharge(
            sender_wallet=asset_fed.wallet_origin,
            receiver_wallet=user.wallet,
            asset=asset_fed,
            montant_en_centimes=amount_cents,
            tenant=tenant,
            ip=ip,
            checkout_stripe_uuid=paiement_uuid,
            comment="Recharge FED via Stripe",
        )
```

**Responsabilité de création du wallet :** le flow nominal crée le wallet à l'Étape 3 (`MyAccount.refill_wallet`) **avant** le passage chez Stripe, car la metadata nécessite `wallet.uuid`. La création dans `RefillService` (Étape 6) est un filet de sécurité pour un edge case improbable (wallet supprimé pendant le paiement Stripe).

### Étape 7 — Retour utilisateur

**URL partagée V1/V2** : la même URL `/my_account/<uuid>/return_refill_wallet/` gère les deux flows. Le dispatch se fait sur `peut_recharger_v2()` au début de la vue :

- **V1** (`server_cashless IS NOT NULL`) : le `<uuid>` est le `CheckoutStripe.uuid` Fedow distant → flow legacy inchangé (`FedowAPI.retrieve_from_refill_checkout`)
- **V2** (tenant V2) : le `<uuid>` est le `Paiement_stripe.uuid` → lecture locale

```python
@action(detail=True, methods=['GET'])
def return_refill_wallet(self, request, pk=None):
    user = request.user
    verdict_ok, verdict = peut_recharger_v2(user)

    # Legacy V1 : le pk est un CheckoutStripe UUID (Fedow distant)
    if verdict == "v1_legacy":
        return self._return_refill_wallet_legacy(request, pk)

    # V2 : le pk est un Paiement_stripe UUID (schema federation_fed)
    tenant_federation = Client.objects.get(schema_name='federation_fed')
    with tenant_context(tenant_federation):
        try:
            paiement = Paiement_stripe.objects.get(uuid=pk, user=user)
        except Paiement_stripe.DoesNotExist:
            messages.error(request, _("Paiement introuvable"))
            return redirect('/my_account/')

        if paiement.status == Paiement_stripe.PAID:
            messages.success(request, _("Wallet rechargé avec succès"))
        else:
            messages.info(request, _("Paiement en cours de traitement"))
    return redirect('/my_account/')
```

Plus de polling serveur : si le webhook n'est pas encore arrivé, le user voit "en cours de traitement" et rafraîchit sa page.

---

## 5. Modèle de données

### Nouveaux éléments

| Élément | Fichier | Changement |
|---|---|---|
| `Client.FED = 'E'` | `Customers/models.py` | +1 valeur dans `CATEGORIE_CHOICES` — verbose "Federation currency" |
| `Paiement_stripe.SOURCE_CHOICES` | `BaseBillet/models.py:3589` | +`CASHLESS_REFILL = "R"` |
| `Product.categorie_article` | `BaseBillet/models.py:1186` | Décommenter ou ajouter `RECHARGE_CASHLESS_FED` |
| `RefillAmountSerializer` | `PaiementStripe/serializers.py` (nouveau fichier) | Validation montant (1€ min / 500€ max) |
| `CreationPaiementStripeFederation` | `PaiementStripe/refill_federation.py` (nouveau fichier) | Gateway Stripe dédié recharges (compte central, pas de Connect, pas de SEPA) |
| `RefillService` | `fedow_core/services.py` (nouvelle classe) | Logique idempotente de recharge |
| `PSP_INTERFACE.md` | `fedow_core/PSP_INTERFACE.md` (nouveau fichier) | Contrat documenté pour futurs PSP |
| Management command | `fedow_core/management/commands/bootstrap_fed_asset.py` | Crée tenant `federation_fed` + root_wallet + Asset FED + Product de recharge |

### Éléments existants réutilisés

| Élément | Fichier | Rôle |
|---|---|---|
| `Asset.FED` | `fedow_core/models.py:67` | Catégorie déjà prévue |
| `Asset.wallet_origin` | `fedow_core/models.py:134` | Devient le "pot central" pour REFILL |
| `Transaction.REFILL` | `fedow_core/models.py:362` | Action déjà prévue |
| `Transaction.checkout_stripe` | `fedow_core/models.py:594` | UUIDField cross-schema (reste nommé ainsi, docstring PSP-agnostic) |
| `TransactionService.creer_recharge()` | `fedow_core/services.py:867` | Wrapper déjà prêt |
| `WalletService.crediter()` | `fedow_core/services.py:246` | `select_for_update` OK |
| `get_or_create_price_sold(custom_amount=)` | `ApiBillet/serializers.py` | Réutilisé pour montant libre |
| `stripe.Webhook.construct_event` | `ApiBillet/views.py` | Sécurité webhook déjà en place |

### Bootstrap (management command)

Pseudo-code de `bootstrap_fed_asset` :


```python
def handle(self, *args, **options):
    # 1. Tenant federation_fed (schema PostgreSQL dédié, auto-créé)
    tenant, created = Client.objects.get_or_create(
        schema_name='federation_fed',
        defaults={
            'name': 'Fédération FED',
            'categorie': Client.FED,
            'on_trial': False,
        },
    )
    # Pas de Domain : pas d'accès HTTP direct à ce tenant

    # 2. Migrer les TENANT_APPS dans ce schéma.
    # auto_create_schema=True crée le schéma PostgreSQL, mais NE lance PAS
    # les migrations. On le fait manuellement (idempotent, skip si déjà migré).
    if created:
        call_command('migrate_schemas', schema_name='federation_fed', interactive=False)

    with tenant_context(tenant):
        # 3. Root wallet (pot central)
        root_wallet, _ = Wallet.objects.get_or_create(
            name='Pot central TiBillet FED',
            origin=tenant,
        )

        # 4. Asset FED unique
        asset_fed, _ = Asset.objects.get_or_create(
            category=Asset.FED,
            defaults={
                'name': 'Euro fédéré TiBillet',
                'currency_code': 'EUR',
                'wallet_origin': root_wallet,
                'tenant_origin': tenant,
            },
        )

        # 5. Product de recharge FED (TENANT_APPS, dans federation_fed)
        product, _ = Product.objects.get_or_create(
            categorie_article=Product.RECHARGE_CASHLESS_FED,
            defaults={
                'name': 'Recharge monnaie fédérée',
                'asset': asset_fed,
            },
        )

        # 6. Price par défaut (prix=0, custom_amount écrase à chaque achat)
        Price.objects.get_or_create(
            product=product,
            defaults={
                'name': 'Montant libre',
                'prix': 0,
                'asset': asset_fed,
            },
        )
```

Branché dans `Administration/management/commands/install.py` après `tenant_meta` (ligne 134), avant `tenant_first_sub`.

### Admin — verrouillage Asset FED

Pour garantir qu'il n'y ait **jamais** deux Assets FED ni un Product de recharge créé manuellement, on impose via l'admin Unfold :

1. **`Asset` de catégorie FED en lecture seule** dans `fedow_core/admin.py` :
   - Override `has_change_permission(request, obj=None)` retourne False si `obj.category == Asset.FED`
   - Override `has_delete_permission(request, obj=None)` retourne False idem
   - Override `has_add_permission(request)` : autorisé mais `get_form()` exclut la catégorie FED du dropdown
2. **Impossible de créer un `Product` sur l'asset FED** dans `Administration/admin_tenant.py` :
   - Le `ProductForm.asset.queryset` exclut `Asset.objects.filter(category=Asset.FED)`
   - Résultat : un admin ne verra jamais l'asset FED dans le dropdown au moment de créer/éditer un Product

Avec ces deux verrous, le seul chemin de création reste le bootstrap.

---

## 6. Phases d'implémentation

### Phase A — Modèle + service (1 session)

1. **Migration `Customers`** : ajouter `Client.FED = 'E'` aux choix
2. **Migration `BaseBillet`** : ajouter `Paiement_stripe.CASHLESS_REFILL` + `Product.RECHARGE_CASHLESS_FED`
3. **Management command `bootstrap_fed_asset`** idempotente (incl. `migrate_schemas` sur federation_fed si créé)
4. **Hook dans `install.py`** : `call_command('bootstrap_fed_asset')`
5. **Ajout dans `create_test_pos_data`** pour fixtures démo (idempotent, appelle la command)
6. **`RefillAmountSerializer`** dans `PaiementStripe/serializers.py`
7. **`RefillService.process_cashless_refill()`** dans `fedow_core/services.py`
8. **`fedow_core/PSP_INTERFACE.md`** documentation contrat

**Checkpoint :** tests unitaires `RefillService` (idempotence, crédit correct, wallet créé si absent).

### Phase B — Gateway Stripe + Webhook + Verrous admin (1 session)

9. **`CreationPaiementStripeFederation`** dans `PaiementStripe/refill_federation.py` (classe courte, ~80 lignes, sans Connect, sans SEPA)
10. **Modification `ApiBillet/views.py:1042`** : dispatch `refill_type == 'FED'` avant le block existant
11. **Fonction `_process_stripe_webhook_cashless_refill()`** dans `ApiBillet/views.py` (à côté de la vue appelante), contient anti-tampering + appel `RefillService`
12. **Anti-tampering** : vérification `stripe_amount_cents == int(paiement.total() * 100)`
13. **Idempotence** : 2 webhooks consécutifs → 1 seule Transaction
14. **Verrous admin** :
   - `fedow_core/admin.py` : Asset FED lecture seule (change/delete permissions + add exclut FED du form)
   - `Administration/admin_tenant.py` : `ProductForm.asset.queryset.exclude(category=FED)`

**Checkpoint sécurité obligatoire :** zone sensible, zéro régression sur les autres sources (QRCODE, BILLETTERIE, CROWDS, INVOICE).

### Phase C — Vues utilisateur (1 session)

15. **Réécriture `MyAccount.refill_wallet()`** avec `peut_recharger_v2()` + 4 branches (désactivé / V1 / wallet legacy / V2)
16. **Simplification `MyAccount.return_refill_wallet()`** (lecture locale, plus de polling HTTP)
17. **Template `my_account_refill_form.html`** : formulaire HTMX avec saisie montant + validation client
18. **Template `my_account_wallet.html`** : deux sections côte à côte (legacy + V2) avec noms humains
19. **Messages i18n** (`_()` + `{% translate %}` partout, FR/EN)
20. **Accessibilité** : `aria-hidden` sur icônes décoratives, `aria-live="polite"` sur la zone du message "migration en cours", `visually-hidden` pour les alternatives textuelles
21. **`data-testid` sur les éléments interactifs** (convention `refill-<element>-<context>`) :
    - `refill-btn-open-form` (bouton qui ouvre le formulaire)
    - `refill-input-amount` (champ euros)
    - `refill-btn-submit` (soumission)
    - `refill-message-migration` (bloc wallet_legacy)
    - `refill-balance-v2` (section solde V2)
    - `refill-balance-legacy` (section solde Fedow distant)
22. **Pattern HTMX 422 pour erreurs formulaire** : configurer `htmx:beforeOnLoad` pour accepter le swap sur 422 (cf. skill djc) — si `RefillAmountSerializer.is_valid()` False, renvoyer le partial avec erreurs en 422

**Workflow final Phase C :**
- `docker exec lespass_django poetry run django-admin makemessages -l fr -l en`
- Remplir les `msgstr` manquants, vérifier les fuzzy
- `docker exec lespass_django poetry run django-admin compilemessages`
- Entrée dans `CHANGELOG.md` (bloc bilingue FR/EN : Quoi, Pourquoi, Fichiers modifiés, Migration requise=Oui pour Phase A)
- Fichier dans `A TESTER et DOCUMENTER/recharge-fed-v2.md` (checklist mainteneur : tests manuels nominaux + edge cases + commandes DB de vérification)

### Phase D — Tests critiques (1 session)

Priorité sécurité : on teste d'abord ce qui protège le code prod contre les bugs ou les attaques. Les tests "nice-to-have" (validation serializer, messages UI) sont reportés dans une **Phase D-polish** optionnelle.

**Tests critiques inclus (9 pytest + 2 E2E) :**

18. **`tests/pytest/test_cashless_refill.py`** — 9 tests critiques :
    - Nominal : user → checkout → webhook mocké → Transaction REFILL + Token crédité
    - Idempotence : 2 webhooks consécutifs → 1 Transaction (protection anti-retry Stripe)
    - Anti-tampering : `stripe_amount != paiement.total() * 100` → webhook 400
    - `peut_recharger_v2` module_off → `"feature_desactivee"`
    - `peut_recharger_v2` tenant_v1 → `"v1_legacy"`
    - `peut_recharger_v2` wallet_legacy → `"wallet_legacy"`
    - `peut_recharger_v2` OK → `"v2"`
    - Gateway `CreationPaiementStripeFederation` n'injecte pas `stripe_account`
    - Gateway `CreationPaiementStripeFederation` rejette SEPA (`payment_method_types=['card']` uniquement)
19. **`tests/e2e/test_cashless_refill_flow.py`** — 2 tests E2E critiques :
    - Flow V2 complet : login → refill → montant → Stripe 4242 → retour → solde à jour
    - Non-régression V1 : tenant legacy `server_cashless NOT NULL` → flow V1 intact

### Phase D-polish — Tests nice-to-have (optionnelle, ~0.5 session)

À programmer quand Phase D est en prod et stable. Pas bloquante pour le release.

20. Tests pytest secondaires :
    - Asset FED absent → erreur claire
    - Cross-tenant : user du tenant A recharge depuis tenant B → OK
    - Wallet créé automatiquement si absent (fallback défensif)
    - `RefillAmountSerializer` bornes (99 → reject, 50001 → reject, 100/50000 OK)
21. Tests E2E secondaires :
    - Message "migration en cours" affiché pour user avec wallet_legacy
    - Bouton refill invisible quand `module_monnaie_locale=False`

### Phase E — Nettoyage (optionnel, plus tard, NON couvert par Session 31)

- Suppression `WalletFedow.*_refill_checkout` du legacy
- Audit suppression Fedow distant complet (chantier 5-7j séparé)

---

## 7. Cohabitation V1/V2 — cas concrets

### Cas 1 — Tenant en mode V2 pour la recharge (nouveau déploiement typique)

`module_monnaie_locale=True`, `server_cashless=NULL`.

**Clarification importante** : le tenant peut être en V2 **pour la recharge FED** sans que le système global soit "V2 pur". Fedow distant continue de tourner au démarrage (`install.py` l'exige) pour les features non encore migrées (adhésions, rewards). Ce n'est que **la recharge FED** qui utilise le flow V2 en local.

- User tout neuf → wallet créé dans `federation_fed`, tokens V2 uniquement
- Affichage wallet : uniquement section V2 (aucun token Fedow legacy côté user)
- Recharge V2 → OK

### Cas 2 — Tenant V1 pur (legacy, LaBoutik externe)

`server_cashless IS NOT NULL`.

- User → wallet géré par Fedow distant via `FedowAPI`
- Affichage wallet : uniquement section legacy (pas de section V2 si aucun token V2)
- Recharge → flow V1 inchangé

### Cas 3 — Tenant V2 avec user arrivé depuis un tenant V1 (edge case)

User a fait ses premiers pas dans un tenant V1 (son `wallet.origin` pointe là). Il navigue sur un tenant V2 et regarde son compte.

- `peut_recharger_v2()` retourne `"wallet_legacy"` (garde 2)
- **Pas de bouton "Recharger"** : le template `my_account_wallet.html` affiche à la place un **bloc inline** (pas modal, pas tooltip) avec le message FALC. Le message doit être internationalisé (`{% translate %}` ou `_()`) et la zone doit porter `aria-live="polite"` + `data-testid="refill-message-migration"` :

  ```django
  {% if verdict == "wallet_legacy" %}
    <div class="alert alert-info" role="status" aria-live="polite"
         data-testid="refill-message-migration">
      <i class="bi bi-info-circle" aria-hidden="true"></i>
      {% translate "Votre wallet est en cours de migration. Merci de patienter, désolés pour la gêne occasionnée." %}
    </div>
  {% endif %}
  ```

- Le bloc est placé dans la zone où s'afficherait le bouton, avec un style informatif (fond clair, icône info, pas d'alerte anxiogène)
- Bouton réactivé automatiquement quand la migration globale Fedow V1→V2 sera faite (Phase 6-7 plan global)

### Cas 4 — User multi-lieux (deux soldes parallèles)

Très rare. User avec wallet origin dans tenant V1 mais qui a aussi reçu des tokens V2 (via fusion de carte ou autre). Le template affiche **les deux sections** :

- Section "Monnaie fédérée (système historique)" → solde legacy
- Section "Monnaie fédérée (V2)" → solde `fedow_core.Token`

À documenter en interne : cas marginal, sera résolu par la migration Phase 6-7.

---

## 8. Points d'attention et pièges

### Sécurité

1. **Pas de RSA inter-service** : signature Django Signer inutile. Sécurité du webhook = `stripe.Webhook.construct_event` déjà en place.
2. **Idempotence** : check dans `transaction.atomic()`, pas hors atomic.
3. **Anti-tampering** : vérifier `stripe.amount_total == int(paiement.total() * 100)` au webhook avant de créditer. Attention : `paiement.total()` retourne un `Decimal` (via `dround()`), il faut convertir en `int` centimes.
4. **Tenant context** : le webhook tourne initialement sur schema `public`. Toujours `with tenant_context(tenant):` avant de toucher `Paiement_stripe` (TENANT_APPS).
5. **`connection.tenant` dans le webhook** : ne pas se fier à `connection.tenant` dans `ApiBillet/views.py:1042`, toujours passer par le `tenant_uuid` du metadata Stripe.

### Multi-tenancy

6. **Asset FED en SHARED_APPS** : accessible depuis tous les tenants. La Transaction est stockée avec `tenant=federation_fed`.
7. **Wallet user** : `AuthBillet.Wallet` en SHARED_APPS. Un user = un seul wallet, UUID partagé V1/V2.
8. **`Paiement_stripe` en TENANT_APPS** : stocké dans `federation_fed` (pas dans le tenant du lieu où l'user a cliqué).

### Bootstrap

9. **`bootstrap_fed_asset` lancée une fois** avant le premier refill V2. Hook auto dans `install.py`. Fixtures de tests la relancent (idempotent).
10. **Tenant `federation_fed` sans Domain** : il n'est pas accessible via HTTP. Seulement via `tenant_context()`.

### UX

11. **Webhook avant return** : possible → user voit "Succès" direct.
12. **Webhook après return** : possible → user voit "En cours de traitement", rafraîchit, voit le solde à jour.
13. **Webhook jamais reçu** : scénario extrême (Stripe down). Hors scope Session 31 — à traiter en Phase D-polish ou plus tard via un job Celery de reconciliation périodique.

### Cohabitation V1/V2

14. **Ne pas remplir `FedowTransaction`** en V2. M2M `Paiement_stripe.fedow_transactions` reste vide pour CASHLESS_REFILL. Tout l'audit V2 est dans `fedow_core.Transaction`.
15. **Ne pas reproduire la hash chain** legacy. Hash individuel uniquement (Phase 3 plan global).
16. **`Configuration.primary_wallet`** : n'existe pas et ne doit pas être ajouté. Utiliser `Asset.FED.wallet_origin`.
17. **Détection wallet legacy via `wallet.origin`** : robuste car `fedow_connect/fedow_api.py:583` met toujours `origin=connection.tenant` à la création.

---

## 9. Tests

### Fixtures nécessaires

- `asset_fed_bootstrap` (session-scoped) : appelle `bootstrap_fed_asset` si absent
- `tenant_federation_fed` : récupère le tenant après bootstrap
- `user_avec_wallet_v2` : user + wallet(origin=tenant_v2)
- `user_avec_wallet_legacy` : user + wallet(origin=tenant_avec_server_cashless)
- `mock_stripe_checkout` : fixture existante

### Scénarios pytest DB-only

**Phase D — 9 critiques (inclus dans la release) :**

| # | Test | Attendu |
|---|---|---|
| 1 | `test_refill_service_nominal` | Transaction créée, Token crédité de `amount_cents` |
| 2 | `test_refill_service_idempotent` | 2 appels consécutifs → 1 seule Transaction |
| 3 | `test_webhook_idempotent_on_stripe_retry` | Même event Stripe 2 fois → 1 Transaction |
| 4 | `test_webhook_anti_tampering` | `stripe_amount_cents != int(paiement.total() * 100)` → webhook 400 |
| 5 | `test_peut_recharger_v2_module_off` | `module_monnaie_locale=False` → `"feature_desactivee"` |
| 6 | `test_peut_recharger_v2_tenant_v1` | `server_cashless NOT NULL` → `"v1_legacy"` |
| 7 | `test_peut_recharger_v2_wallet_legacy` | `wallet.origin` pointe vers tenant V1 → `"wallet_legacy"` |
| 8 | `test_peut_recharger_v2_ok` | Tenant V2 + wallet V2 → `"v2"` |
| 9 | `test_creation_paiement_stripe_federation_no_connect_no_sepa` | Pas de `stripe_account`, `payment_method_types=['card']` |

**Phase D-polish — 5 nice-to-have (après prod stable) :**

| # | Test | Attendu |
|---|---|---|
| 10 | `test_refill_service_no_asset_fed` | `Asset.DoesNotExist` avec message clair |
| 11 | `test_refill_service_creates_wallet_if_missing` | User sans wallet → wallet créé auto (fallback défensif) |
| 12 | `test_refill_serializer_min_max` | 99 centimes → reject, 50001 → reject, 100/50000 OK |
| 13 | `test_webhook_dispatch_cashless_refill` | Webhook `refill_type=FED` → RefillService appelé (intégration) |
| 14 | `test_refill_cross_tenant` | User du tenant A recharge depuis tenant B → OK (FED partagé) |

### Scénarios E2E Playwright

**Phase D — 2 critiques (inclus dans la release) :**

| # | Test | Attendu |
|---|---|---|
| 1 | `test_cashless_refill_flow_v2` | Login → refill → montant → Stripe 4242 → retour → solde à jour |
| 2 | `test_cashless_refill_legacy_tenant` | Tenant avec `server_cashless` → flow V1 intact |

**Phase D-polish — 2 nice-to-have :**

| # | Test | Attendu |
|---|---|---|
| 3 | `test_cashless_refill_wallet_legacy_message` | User avec wallet origin V1 → voit `data-testid="refill-message-migration"` |
| 4 | `test_cashless_refill_module_disabled` | `module_monnaie_locale=False` → bouton refill invisible |

---

## 10. Glossaire

| Terme | Définition |
|---|---|
| **FED** | Fiduciaire Fédérée. Monnaie euro partagée entre tous les tenants TiBillet. Un seul `Asset` de cette catégorie dans tout le système |
| **Pot central** | Wallet qui "émet" les tokens FED. Sender des REFILL sans débit. C'est `Asset.FED.wallet_origin` |
| **Tenant `federation_fed`** | Tenant dédié (catégorie `Client.FED`) qui porte le pot central, le `Product` de recharge, les `Paiement_stripe`. Pas de Domain HTTP |
| **Recharge cashless** | Ajout de tokens sur le wallet d'un utilisateur contre un paiement bancaire |
| **REFILL** | Action `Transaction.REFILL = 'RFL'`. Crédite le receiver, ne débite pas le sender (création monétaire) |
| **Wallet legacy** | Wallet dont `origin` pointe vers un tenant avec `Configuration.server_cashless IS NOT NULL`. Ses tokens sont sur Fedow distant, pas accessibles à V2 |
| **Gateway PSP** | Classe de création de paiement (Stripe, Payplug...). Appelle `RefillService` après validation du paiement |
| **V1** | Code qui passe par le serveur Fedow distant via HTTP+RSA. Conservé tant que des tenants legacy existent |
| **V2** | Code qui passe par `fedow_core` en accès DB direct. Pour les tenants modernes |
| **Idempotence** | Propriété d'une opération qui peut être rejouée sans effet de bord. Ici, un webhook Stripe rejoué ne double pas les tokens |

---

## 11. Références

### Code legacy (pour référence, à ne pas modifier)
- `OLD_REPO/Fedow/fedow_core/views.py:685` — endpoint legacy `get_federated_token_refill_checkout`
- `OLD_REPO/Fedow/fedow_core/views.py:1160` — validation legacy `validate_stripe_checkout_and_make_transaction`
- `fedow_connect/fedow_api.py:598` — client HTTP vers Fedow distant
- `fedow_connect/fedow_api.py:571` — `get_or_create_wallet` (détermine `wallet.origin`)

### Code V2 réutilisé
- `fedow_core/services.py:867` — `TransactionService.creer_recharge()` (wrapper prêt)
- `fedow_core/models.py:362` — `Transaction.REFILL` action
- `fedow_core/models.py:594` — `Transaction.checkout_stripe` UUIDField
- `PaiementStripe/views.py:32` — `CreationPaiementStripe` (modèle dont s'inspirer pour `CreationPaiementStripeFederation`)
- `ApiBillet/serializers.py` — `get_or_create_price_sold(custom_amount=...)`

### Points d'entrée à modifier
- `BaseBillet/views.py:1071` — `MyAccount.refill_wallet()` (bascule V1/V2)
- `BaseBillet/views.py:1087` — `MyAccount.return_refill_wallet()` (simplification)
- `ApiBillet/views.py:1042` — webhook Stripe (dispatch CASHLESS_REFILL)
- `Administration/management/commands/install.py:134` — hook `bootstrap_fed_asset`

### Contexte projet
- `TECH DOC/Laboutik sessions/PLAN_LABOUTIK.md` — plan global de fusion mono-repo
- `TECH DOC/Laboutik sessions/PLAN_LABOUTIK.md:146-167` — règle de coexistence V1/V2
- `MEMORY.md` — décisions projet (Asset FED unique, centimes, hash individuel)
