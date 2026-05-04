# Session 33 — Visualisation historique transactions V2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher les `fedow_core.Transaction` d'un user (plus les tx des wallets éphémères fusionnés dans `user.wallet`) sur `/my_account/balance/` → section historique, en remplacement de l'appel `FedowAPI.paginated_list_by_wallet_signature` pour le verdict `"v2"` uniquement.

**Architecture:** Dispatch inline dans `MyAccount.transactions_table` selon `peut_recharger_v2(user)`. Verdict `"v2"` → méthode privée `_transactions_table_v2` qui reconstitue `wallets_historiques_pks` via les `Transaction(action=FUSION, receiver=user.wallet)`, puis fait une query ORM optimisée filtrée par `Q(sender__in) | Q(receiver__in)` avec exclusion des actions techniques (`FIRST`, `CREATION`, `BANK_TRANSFER`). Pagination Django 40/page + HTMX swap sur `#transactionHistory`. Les autres verdicts tombent sur le code V1 actuel inchangé.

**Tech Stack:** Django 4.2 ViewSet (DRF), django-tenants (SHARED_APPS pour `fedow_core`), HTMX, template `reunion/partials/...`, pytest DB-only avec fixtures `bootstrap_fed_asset`, `django.core.paginator.Paginator`, Django cache framework (réutilisation de `_get_tenant_info_cached` Session 32).

**Spec source:** `TECH DOC/Laboutik sessions/Session 33 - Visualisation historique transactions V2/SPEC_VISU_HISTORIQUE_V2.md`

**Règle projet critique :** *Ne JAMAIS exécuter d'opérations git (no `commit`, `push`, `add`, `checkout --`, `stash`, `reset`, `restore --`, `clean -f`).* Les étapes "Commit" du plan sont **des suggestions de messages au mainteneur**. C'est le mainteneur qui commit.

---

## File Structure

### Fichiers créés

| Fichier | Rôle |
|---|---|
| `BaseBillet/templates/reunion/partials/account/transaction_history_v2.html` | Partial V2 : tableau 4 colonnes + empty state + pagination HTMX |
| `tests/pytest/test_transactions_table_v2.py` | 8 tests pytest DB-only |
| `A TESTER et DOCUMENTER/visu-historique-transactions-v2.md` | Guide mainteneur |

### Fichiers modifiés

| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` | Dispatch V2 dans `MyAccount.transactions_table` + nouvelle méthode `_transactions_table_v2` + 2 helpers module-level (`_enrichir_transaction_v2`, `_structure_pour_transaction`) |
| `CHANGELOG.md` | Entrée bilingue FR/EN en tête |
| `locale/fr/LC_MESSAGES/django.po` + `locale/en/LC_MESSAGES/django.po` | 7 nouvelles strings i18n |

### Fichiers intacts (vérifier non touchés)

- `BaseBillet/templates/reunion/partials/account/transaction_history.html` (V1)
- `fedow_core/services.py` (aucune nouvelle méthode — query directe `Transaction.objects`)
- Tests Sessions 31 et 32 (non-régression)

---

## Task 1 : Dispatch V2 squelette + template minimal + test dispatch

**Objectif :** Poser la structure du dispatch sans logique métier. Test vert = la branche `"v2"` appelle le nouveau partial.

**Files:**
- Modify: `BaseBillet/views.py` (dispatch + skeleton `_transactions_table_v2`)
- Create: `BaseBillet/templates/reunion/partials/account/transaction_history_v2.html`
- Create: `tests/pytest/test_transactions_table_v2.py`

- [ ] **Step 1.1: Créer le fichier de tests avec 1 test**

Créer `tests/pytest/test_transactions_table_v2.py` :

```python
"""
Tests de la vue MyAccount.transactions_table pour la branche V2 (fedow_core local).
Tests for MyAccount.transactions_table — V2 branch (local fedow_core).

LOCALISATION : tests/pytest/test_transactions_table_v2.py

Couvre :
- Dispatch V2 vs V1
- Wallet absent
- Tri chronologique desc
- Exclusion actions techniques
- Reconstitution wallets historiques via FUSION
- Signe entrant/sortant
- Pagination 40/page

/ Covers V2 dispatch, empty wallet, desc sort, technical exclusion, historical
wallets via FUSION, signs, pagination.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py -v --api-key dummy
"""

import sys
import uuid

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import RequestFactory
from django_tenants.utils import tenant_context
from django.utils import timezone

from Customers.models import Client
from AuthBillet.models import Wallet, TibilletUser
from BaseBillet.models import Configuration
from fedow_core.models import Asset, Transaction
from BaseBillet.views import MyAccount


TEST_PREFIX = "[test_transactions_table_v2]"


@pytest.fixture(scope="module")
def tenant_federation_fed():
    """Bootstrape federation_fed (idempotent). / Bootstrap federation_fed."""
    call_command("bootstrap_fed_asset")
    return Client.objects.get(schema_name="federation_fed")


@pytest.fixture(scope="module")
def tenant_lespass():
    """Tenant principal du projet (schema 'lespass'). / Main project tenant."""
    return Client.objects.get(schema_name="lespass")


@pytest.fixture
def user_v2(tenant_federation_fed):
    """
    User avec wallet origine=federation_fed (cas V2 nominal).
    / User with wallet origin=federation_fed (V2 nominal case).
    """
    email = f"{TEST_PREFIX} v2 {uuid.uuid4()}@test.local"
    user = TibilletUser.objects.create(email=email, username=email)
    user.wallet = Wallet.objects.create(
        origin=tenant_federation_fed,
        name=f"Wallet {email}",
    )
    user.save(update_fields=["wallet"])
    return user


@pytest.fixture
def config_v2(tenant_lespass):
    """
    Met lespass en mode V2 (module_monnaie_locale=True, server_cashless=None),
    et restaure en fin de test.
    / Sets lespass to V2 mode, restores at teardown.
    """
    with tenant_context(tenant_lespass):
        config = Configuration.get_solo()
        module_initial = config.module_monnaie_locale
        server_initial = config.server_cashless
        config.module_monnaie_locale = True
        config.server_cashless = None
        config.save(update_fields=["module_monnaie_locale", "server_cashless"])
    yield tenant_lespass
    with tenant_context(tenant_lespass):
        config = Configuration.get_solo()
        config.module_monnaie_locale = module_initial
        config.server_cashless = server_initial
        config.save(update_fields=["module_monnaie_locale", "server_cashless"])


def test_transactions_table_v2_dispatch_branche_v2(config_v2, user_v2):
    """
    Verdict peut_recharger_v2 == 'v2' -> le template transaction_history_v2.html
    est rendu.
    / V2 verdict -> transaction_history_v2.html template is rendered.
    """
    with tenant_context(config_v2):
        request = RequestFactory().get("/my_account/transactions_table/")
        request.user = user_v2
        response = MyAccount().transactions_table(request)
        assert response.status_code == 200
        html = response.content.decode()
        # Marker V2 present dans le HTML.
        # / V2 marker present in HTML.
        assert 'data-testid="tx-v2-container"' in html or 'data-testid="tx-v2-empty"' in html
```

- [ ] **Step 1.2: Lancer le test (doit échouer)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py::test_transactions_table_v2_dispatch_branche_v2 -v --api-key dummy
```

Expected : **FAIL** (TemplateDoesNotExist `transaction_history_v2.html` ou assertion sur `data-testid` absent).

- [ ] **Step 1.3: Créer le template minimal**

Créer `BaseBillet/templates/reunion/partials/account/transaction_history_v2.html` :

```html
{% load i18n %}
{# Partial V2 minimal — sera enrichi aux tasks suivantes. #}
{# V2 partial minimal — will be enriched in later tasks. #}
<section id="transactionHistory" aria-live="polite" data-testid="tx-v2-container">
  <h2 class="pt-3">{% translate "Transaction history" %}</h2>
  <div class="text-center py-4 opacity-75" data-testid="tx-v2-empty">
    <p class="mb-0">{% translate "No transaction yet." %}</p>
  </div>
</section>
```

- [ ] **Step 1.4: Ajouter le dispatch V2 + méthode squelette dans views.py**

Dans `BaseBillet/views.py`, localiser la méthode `transactions_table` (autour de la ligne 1260). La remplacer par :

```python
    @action(detail=False, methods=['GET'])
    def transactions_table(self, request):
        """
        Historique des transactions du user connecte.
        / User transaction history.

        LOCALISATION : BaseBillet/views.py

        Dispatch V1/V2 selon peut_recharger_v2(user) :
        - Verdict "v2" -> lecture locale fedow_core.Transaction (Session 33)
        - Autres verdicts -> flow V1 FedowAPI (inchange)
        / V1/V2 dispatch based on peut_recharger_v2(user).
        """
        user = request.user
        verdict_ok, verdict = peut_recharger_v2(user)

        # --- Branche V2 : lecture locale fedow_core ---
        # / V2 branch: local fedow_core read
        if verdict == "v2":
            return self._transactions_table_v2(request)

        # --- Autres verdicts : code V1 existant inchange ---
        # / Other verdicts: existing V1 code unchanged
        config = Configuration.get_solo()
        fedowAPI = FedowAPI()
        # On utilise ici .data plutot que validated_data pour executer les to_representation (celui du WalletSerializer)
        # et les serializer.methodtruc
        paginated_list_by_wallet_signature = fedowAPI.transaction.paginated_list_by_wallet_signature(
            request.user).validated_data

        transactions = paginated_list_by_wallet_signature.get('results')
        next_url = paginated_list_by_wallet_signature.get('next')
        previous_url = paginated_list_by_wallet_signature.get('previous')

        context = {
            'actions_choices': TransactionSimpleValidator.TYPE_ACTION,
            'config': config,
            'transactions': transactions,
            'next_url': next_url,
            'previous_url': previous_url,
        }
        return render(request, "reunion/partials/account/transaction_history.html", context=context)

    def _transactions_table_v2(self, request):
        """
        Branche V2 de transactions_table : squelette.
        / V2 branch: skeleton.

        LOCALISATION : BaseBillet/views.py

        Enrichi aux tasks 2-6 du plan (wallets historiques, query, pagination,
        enrichissement, exclusion actions techniques).
        """
        config = Configuration.get_solo()
        return render(
            request,
            "reunion/partials/account/transaction_history_v2.html",
            {
                "config": config,
                "transactions": [],
                "paginator_page": None,
                "aucune_transaction": True,
            },
        )
```

- [ ] **Step 1.5: Lancer le test (doit passer)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py::test_transactions_table_v2_dispatch_branche_v2 -v --api-key dummy
```

Expected : **PASS**.

- [ ] **Step 1.6: Non-régression Sessions 31-32**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_refill_service.py tests/pytest/test_tokens_table_v2.py -v --api-key dummy
```

Expected : tous les tests Session 31 + 32 PASS (~12 tests).

- [ ] **Step 1.7: Suggérer commit au mainteneur**

Message proposé :
```
feat(Session33): task 1 — dispatch V2 squelette + template minimal

- BaseBillet/views.py: dispatch "v2" dans MyAccount.transactions_table,
  methode _transactions_table_v2 squelette
- Template transaction_history_v2.html minimal (section + empty state)
- Test dispatch branche V2 dans tests/pytest/test_transactions_table_v2.py

Refs: Session 33 - Visualisation historique transactions V2
```

---

## Task 2 : Helper `_structure_pour_transaction` (mapping des labels)

**Objectif :** Module-level helper qui retourne le libellé "Structure" selon l'action (REFILL→"TiBillet", FUSION→`Carte #{number}`, autres→nom collectif via cache).

**Files:**
- Modify: `BaseBillet/views.py` (ajouter helper après `_lieux_utilisables_pour_asset`)
- Modify: `tests/pytest/test_transactions_table_v2.py` (ajouter 3 tests)

- [ ] **Step 2.1: Écrire les 3 tests structure**

Ajouter à `tests/pytest/test_transactions_table_v2.py` :

```python
from fedow_core.models import Asset, Transaction
from BaseBillet.views import _structure_pour_transaction
from QrcodeCashless.models import CarteCashless


@pytest.fixture
def asset_fed_instance(tenant_federation_fed):
    """L'unique Asset FED du systeme. / Unique FED Asset."""
    return Asset.objects.get(category=Asset.FED)


def test_structure_pour_transaction_refill_retourne_tibillet(
    asset_fed_instance, user_v2, tenant_federation_fed
):
    """
    REFILL -> structure = "TiBillet" (nom propre, convention mainteneur).
    / REFILL -> structure = "TiBillet" (brand name, maintainer convention).
    """
    tx = Transaction.objects.create(
        sender=asset_fed_instance.wallet_origin,
        receiver=user_v2.wallet,
        asset=asset_fed_instance,
        amount=2000,
        action=Transaction.REFILL,
        tenant=tenant_federation_fed,
        datetime=timezone.now(),
    )
    # user.wallet est le receiver -> receiver_est_historique=True
    # / user.wallet is receiver -> receiver_est_historique=True
    structure = _structure_pour_transaction(tx, receiver_est_historique=True)
    assert structure == "TiBillet"


def test_structure_pour_transaction_fusion_retourne_carte_number(
    asset_fed_instance, user_v2, tenant_federation_fed
):
    """
    FUSION avec card -> structure = "Carte #{card.number}".
    / FUSION with card -> structure = "Carte #{card.number}".
    """
    # Creer une carte avec un number imprime de 8 chars.
    # / Create a card with 8-char printed number.
    wallet_ephemere = Wallet.objects.create(
        origin=tenant_federation_fed,
        name=f"Wallet ephemere {uuid.uuid4()}",
    )
    carte = CarteCashless.objects.create(
        tag_id=uuid.uuid4().hex[:8].upper(),
        number="ABCD1234",
        wallet_ephemere=wallet_ephemere,
    )
    tx = Transaction.objects.create(
        sender=wallet_ephemere,
        receiver=user_v2.wallet,
        asset=asset_fed_instance,
        amount=1500,
        action=Transaction.FUSION,
        tenant=tenant_federation_fed,
        datetime=timezone.now(),
        card=carte,
    )
    structure = _structure_pour_transaction(tx, receiver_est_historique=True)
    assert structure == "Carte #ABCD1234"


def test_structure_pour_transaction_sale_retourne_organisation_collectif(
    asset_fed_instance, user_v2, tenant_lespass, tenant_federation_fed
):
    """
    SALE -> structure = nom du collectif receiver (via cache tenant_info_v2).
    / SALE -> structure = receiver collective name (via cache).
    """
    # Wallet du lieu lespass (receveur de la vente).
    # / Lespass venue wallet (sale receiver).
    wallet_lieu_lespass = Wallet.objects.create(
        origin=tenant_lespass,
        name=f"Wallet lieu lespass {uuid.uuid4()}",
    )
    tx = Transaction.objects.create(
        sender=user_v2.wallet,
        receiver=wallet_lieu_lespass,
        asset=asset_fed_instance,
        amount=500,
        action=Transaction.SALE,
        tenant=tenant_lespass,
        datetime=timezone.now(),
    )
    # Cold cache pour propre reconstitution.
    # / Cold cache for clean reconstruction.
    cache.delete("tenant_info_v2")

    # user est sender -> receiver_est_historique=False
    # / user is sender -> receiver_est_historique=False
    structure = _structure_pour_transaction(tx, receiver_est_historique=False)
    # Le nom de l'organisation lespass (depuis Configuration).
    # / Lespass Configuration organisation name.
    with tenant_context(tenant_lespass):
        config_lespass = Configuration.get_solo()
        nom_attendu = config_lespass.organisation
    assert structure == nom_attendu
```

- [ ] **Step 2.2: Lancer les tests (doivent échouer)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py::test_structure_pour_transaction_refill_retourne_tibillet tests/pytest/test_transactions_table_v2.py::test_structure_pour_transaction_fusion_retourne_carte_number tests/pytest/test_transactions_table_v2.py::test_structure_pour_transaction_sale_retourne_organisation_collectif -v --api-key dummy
```

Expected : **FAIL** (`ImportError: cannot import name '_structure_pour_transaction'`).

- [ ] **Step 2.3: Implémenter le helper `_structure_pour_transaction`**

Dans `BaseBillet/views.py`, **juste après** le helper `_lieux_utilisables_pour_asset` (créé en Session 32, autour de la ligne 817), ajouter :

```python
def _structure_pour_transaction(tx, receiver_est_historique):
    """
    Retourne le libelle de la colonne "Structure" selon l'action de tx.
    / Returns the "Structure" column label based on tx action.

    LOCALISATION : BaseBillet/views.py (helper module-level)

    Utilise _get_tenant_info_cached (Session 32) pour resoudre le nom d'un
    collectif a partir de son Client.pk (cache global 3600s).

    Cas particuliers :
    - REFILL : "TiBillet" (convention : monnaie federee unique)
    - FUSION : "Carte #{card.number}" (ou "-" si card None, anormal)
    - Autres : nom du collectif "autre partie" selon le sens du flux

    :param tx: fedow_core.Transaction
    :param receiver_est_historique: bool (True si receiver ∈ wallets historiques)
    :return: str label pour la colonne Structure
    """
    # REFILL : pot central FED, label conventionnel "TiBillet".
    # / REFILL: central FED pot, conventional label "TiBillet".
    if tx.action == Transaction.REFILL:
        return "TiBillet"

    # FUSION : rattachement carte anonyme vers compte user.
    # Le number imprime (8 chars) identifie la carte pour l'user.
    # / FUSION: anonymous card -> user account attachment.
    # The printed number (8 chars) identifies the card to the user.
    if tx.action == Transaction.FUSION:
        if tx.card is None:
            logger.warning(
                f"Transaction FUSION #{tx.id} sans card : affichage fallback"
            )
            return "—"
        return f"Carte #{tx.card.number}"

    # Autres actions : afficher le nom du collectif "autre partie" selon
    # le sens du flux par rapport au wallet user.
    # Si user recoit (receiver_est_historique=True) -> contrepartie = sender
    # Sinon -> contrepartie = receiver
    # / Other actions: show the "other party" collective name.
    # If user receives, counterpart is sender. Else, it's receiver.
    if receiver_est_historique:
        tenant_contrepartie = getattr(tx.sender, "origin", None)
    else:
        tenant_contrepartie = (
            getattr(tx.receiver, "origin", None) if tx.receiver else None
        )

    if tenant_contrepartie is None:
        return "—"

    info = _get_tenant_info_cached(tenant_contrepartie.pk)
    if info is None:
        return "—"

    return info.get("organisation") or "—"
```

- [ ] **Step 2.4: Lancer les tests (doivent passer)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py -v --api-key dummy
```

Expected : **4 tests PASS** (1 task 1 + 3 task 2).

- [ ] **Step 2.5: Suggérer commit au mainteneur**

Message proposé :
```
feat(Session33): task 2 — helper _structure_pour_transaction

Mapping Structure selon l'action :
- REFILL -> "TiBillet" (nom propre)
- FUSION -> "Carte #{card.number}" (number imprime 8 chars)
- SALE/REFUND/etc -> nom du collectif contrepartie (via cache V2)

Refs: Session 33 - Visualisation historique transactions V2
```

---

## Task 3 : Helper `_enrichir_transaction_v2` + test signe entrant/sortant

**Objectif :** Module-level helper qui transforme une `Transaction` en dict explicite pour le template.

**Files:**
- Modify: `BaseBillet/views.py` (ajouter helper après `_structure_pour_transaction`)
- Modify: `tests/pytest/test_transactions_table_v2.py` (ajouter 1 test)

- [ ] **Step 3.1: Écrire le test signe entrant/sortant**

Ajouter à `tests/pytest/test_transactions_table_v2.py` :

```python
from BaseBillet.views import _enrichir_transaction_v2


def test_enrichir_transaction_v2_signe_entrant_sortant(
    asset_fed_instance, user_v2, tenant_lespass, tenant_federation_fed
):
    """
    SALE (sender=user.wallet) -> dict a signe='-'.
    REFILL (receiver=user.wallet) -> dict a signe='+'.
    / SALE sender=user -> signe='-'. REFILL receiver=user -> signe='+'.
    """
    wallet_lieu = Wallet.objects.create(
        origin=tenant_lespass,
        name=f"Wallet lieu {uuid.uuid4()}",
    )

    # SALE : user paye (sortant).
    # / SALE: user pays (outgoing).
    tx_sale = Transaction.objects.create(
        sender=user_v2.wallet,
        receiver=wallet_lieu,
        asset=asset_fed_instance,
        amount=350,
        action=Transaction.SALE,
        tenant=tenant_lespass,
        datetime=timezone.now(),
    )
    # REFILL : user recoit (entrant).
    # / REFILL: user receives (incoming).
    tx_refill = Transaction.objects.create(
        sender=asset_fed_instance.wallet_origin,
        receiver=user_v2.wallet,
        asset=asset_fed_instance,
        amount=2000,
        action=Transaction.REFILL,
        tenant=tenant_federation_fed,
        datetime=timezone.now(),
    )

    wallets_historiques_pks = {user_v2.wallet.pk}

    item_sale = _enrichir_transaction_v2(tx_sale, user_v2.wallet, wallets_historiques_pks)
    item_refill = _enrichir_transaction_v2(tx_refill, user_v2.wallet, wallets_historiques_pks)

    assert item_sale["signe"] == "-"
    assert item_sale["amount_euros"] == 3.5
    assert item_sale["action"] == Transaction.SALE

    assert item_refill["signe"] == "+"
    assert item_refill["amount_euros"] == 20.0
    assert item_refill["asset_name_affichage"] == "TiBillets"
    assert item_refill["structure"] == "TiBillet"
```

- [ ] **Step 3.2: Lancer le test (doit échouer)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py::test_enrichir_transaction_v2_signe_entrant_sortant -v --api-key dummy
```

Expected : **FAIL** (`ImportError: cannot import name '_enrichir_transaction_v2'`).

- [ ] **Step 3.3: Implémenter le helper `_enrichir_transaction_v2`**

Dans `BaseBillet/views.py`, **juste après** `_structure_pour_transaction`, ajouter :

```python
def _enrichir_transaction_v2(tx, wallet_user, wallets_historiques_pks):
    """
    Transforme une fedow_core.Transaction en dict explicite pour le template.
    / Turns a fedow_core.Transaction into an explicit dict for the template.

    LOCALISATION : BaseBillet/views.py (helper module-level)

    Calcule :
    - signe : "+" si receiver ∈ wallets_historiques, "-" sinon
    - amount_euros : amount / 100 (centimes -> euros)
    - asset_name_affichage : "TiBillets" pour FED, sinon asset.name
    - action_display : tx.get_action_display() (label traduit)
    - structure : via _structure_pour_transaction (cf. helper)

    :param tx: fedow_core.Transaction
    :param wallet_user: AuthBillet.Wallet (user.wallet, conserve pour compat future)
    :param wallets_historiques_pks: set[UUID] (user.wallet.pk + ephemeres fusionnes)
    :return: dict explicite consomme par transaction_history_v2.html
    """
    # Signe : + si user recoit, - si user envoie.
    # / Sign: + if user receives, - if user sends.
    receiver_est_historique = (
        tx.receiver_id is not None
        and tx.receiver_id in wallets_historiques_pks
    )
    signe = "+" if receiver_est_historique else "-"

    # Label asset : "TiBillets" pour FED (nom propre), sinon nom de l'asset.
    # / Asset label: "TiBillets" for FED, else asset name.
    if tx.asset.category == Asset.FED:
        asset_name_affichage = "TiBillets"
    else:
        asset_name_affichage = tx.asset.name

    # Libelle Structure via le helper dedie.
    # / Structure label via dedicated helper.
    structure = _structure_pour_transaction(tx, receiver_est_historique)

    return {
        "uuid": str(tx.uuid),
        "datetime": tx.datetime,
        "action": tx.action,
        "action_display": tx.get_action_display(),
        "amount_euros": tx.amount / 100,
        "amount_brut": tx.amount,
        "signe": signe,
        "asset_name_affichage": asset_name_affichage,
        "structure": structure,
    }
```

- [ ] **Step 3.4: Lancer tous les tests du fichier**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py -v --api-key dummy
```

Expected : **5 tests PASS**.

- [ ] **Step 3.5: Suggérer commit au mainteneur**

```
feat(Session33): task 3 — helper _enrichir_transaction_v2

Transforme une Transaction en dict explicite pour le template :
signe (+/-), amount_euros, asset_name_affichage ("TiBillets" pour FED),
action_display, structure. Zero mutation ORM.

Refs: Session 33 - Visualisation historique transactions V2
```

---

## Task 4 : Reconstitution wallets historiques + test FUSION

**Objectif :** Dans `_tokens_table_v2`, ajouter la reconstitution `wallets_historiques_pks` via les FUSIONs + test que les tx du wallet éphémère apparaissent.

**Files:**
- Modify: `BaseBillet/views.py` (enrichir `_transactions_table_v2`)
- Modify: `tests/pytest/test_transactions_table_v2.py` (ajouter 1 test)

- [ ] **Step 4.1: Écrire le test reconstitution wallets historiques**

Ajouter à `tests/pytest/test_transactions_table_v2.py` :

```python
def test_reconstitution_wallets_historiques_via_fusion(
    asset_fed_instance, config_v2, user_v2, tenant_lespass, tenant_federation_fed
):
    """
    Un wallet ephemere + une FUSION(receiver=user.wallet) + une SALE sur
    le wallet ephemere -> la SALE apparait dans l'historique du user.
    / ephemeral wallet + FUSION + SALE on ephemeral -> SALE appears in
    user history.
    """
    # 1. Creer un wallet ephemere (ex-carte anonyme).
    # / 1. Create ephemeral wallet (ex-anonymous card).
    wallet_ephemere = Wallet.objects.create(
        origin=tenant_federation_fed,
        name=f"Wallet ephemere {uuid.uuid4()}",
    )

    # 2. Creer une SALE AVANT identification (sender=wallet_ephemere).
    # / 2. Create a SALE BEFORE identification.
    wallet_lieu = Wallet.objects.create(
        origin=tenant_lespass,
        name=f"Wallet lieu {uuid.uuid4()}",
    )
    tx_sale = Transaction.objects.create(
        sender=wallet_ephemere,
        receiver=wallet_lieu,
        asset=asset_fed_instance,
        amount=500,
        action=Transaction.SALE,
        tenant=tenant_lespass,
        datetime=timezone.now(),
    )

    # 3. Creer la FUSION(sender=wallet_ephemere, receiver=user.wallet).
    # / 3. Create FUSION.
    tx_fusion = Transaction.objects.create(
        sender=wallet_ephemere,
        receiver=user_v2.wallet,
        asset=asset_fed_instance,
        amount=1500,
        action=Transaction.FUSION,
        tenant=tenant_federation_fed,
        datetime=timezone.now(),
    )

    # 4. Appeler la vue V2.
    # / 4. Call V2 view.
    with tenant_context(config_v2):
        request = RequestFactory().get("/my_account/transactions_table/")
        request.user = user_v2
        response = MyAccount().transactions_table(request)
        assert response.status_code == 200

        # Recuperer la liste de transactions depuis le context rendu.
        # / Get transactions from rendered context.
        transactions = response.context_data.get("transactions") if hasattr(response, "context_data") else None
        # Fallback : parser le HTML pour chercher la presence du marker "Vente".
        # / Fallback: parse HTML to find "Vente" marker.
        html = response.content.decode()
        # Les 2 tx (SALE + FUSION) doivent etre presentes.
        # / Both transactions (SALE + FUSION) must be present.
        assert str(tx_sale.uuid) in html or tx_sale.get_action_display() in html
        assert str(tx_fusion.uuid) in html or tx_fusion.get_action_display() in html
```

- [ ] **Step 4.2: Lancer le test (doit échouer)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py::test_reconstitution_wallets_historiques_via_fusion -v --api-key dummy
```

Expected : **FAIL** (le squelette de `_transactions_table_v2` retourne `aucune_transaction=True`, le HTML ne contient pas les tx).

- [ ] **Step 4.3: Remplacer la méthode `_transactions_table_v2` avec la logique complète**

Dans `BaseBillet/views.py`, remplacer **entièrement** le corps de `_transactions_table_v2` par :

```python
    def _transactions_table_v2(self, request):
        """
        Branche V2 de transactions_table : lit fedow_core.Transaction en base
        locale et reconstitue l'historique des wallets ephemeres fusionnes
        dans user.wallet.
        / V2 branch: reads fedow_core.Transaction from local DB and
        reconstitutes history of ephemeral wallets merged into user.wallet.

        LOCALISATION : BaseBillet/views.py

        Pagination Django 40/page. HTMX swap sur #transactionHistory.
        """
        from django.core.paginator import Paginator

        user = request.user
        config = Configuration.get_solo()

        # Garde : wallet absent -> aucune transaction.
        # / Guard: no wallet -> no transaction.
        if user.wallet is None:
            return render(
                request,
                "reunion/partials/account/transaction_history_v2.html",
                {
                    "config": config,
                    "transactions": [],
                    "paginator_page": None,
                    "aucune_transaction": True,
                },
            )

        # 1. Reconstituer les wallets historiques (user.wallet + ephemeres fusionnes).
        # / 1. Reconstitute historical wallets.
        wallets_historiques_pks = {user.wallet.pk}
        fusions_passees = Transaction.objects.filter(
            action=Transaction.FUSION,
            receiver=user.wallet,
        ).values_list('sender_id', flat=True)
        wallets_historiques_pks.update(fusions_passees)

        # 2. Query : tx touchant ces wallets + exclude actions techniques.
        # / 2. Query: tx touching these wallets + exclude technical actions.
        actions_techniques_a_cacher = [
            Transaction.FIRST,
            Transaction.CREATION,
            Transaction.BANK_TRANSFER,
        ]
        tx_queryset = (
            Transaction.objects
            .filter(
                Q(sender_id__in=wallets_historiques_pks)
                | Q(receiver_id__in=wallets_historiques_pks)
            )
            .exclude(action__in=actions_techniques_a_cacher)
            .select_related(
                'asset',
                'sender__origin',
                'receiver__origin',
                'card',
            )
            .order_by('-datetime')
        )

        # 3. Pagination 40/page.
        # / 3. Paginate 40/page.
        paginator = Paginator(tx_queryset, 40)
        numero_page = request.GET.get('page', 1)
        page = paginator.get_page(numero_page)

        # 4. Enrichir chaque transaction pour le template.
        # / 4. Enrich each transaction for template.
        transactions_enrichies = [
            _enrichir_transaction_v2(tx, user.wallet, wallets_historiques_pks)
            for tx in page.object_list
        ]

        return render(
            request,
            "reunion/partials/account/transaction_history_v2.html",
            {
                "config": config,
                "transactions": transactions_enrichies,
                "paginator_page": page,
                "aucune_transaction": len(transactions_enrichies) == 0,
            },
        )
```

- [ ] **Step 4.4: Lancer le test (doit passer)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py::test_reconstitution_wallets_historiques_via_fusion -v --api-key dummy
```

Expected : **PASS** — le HTML contient l'UUID ou le label Action des 2 tx (SALE + FUSION).

Note : le template ne rend pas encore les lignes de transactions (task 5 ajoute la table complète). L'assertion `tx.uuid in html or tx.get_action_display() in html` est volontairement laxe pour valider uniquement que la vue a bien construit la liste.

- [ ] **Step 4.5: Lancer tous les tests du fichier**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py -v --api-key dummy
```

Expected : **6 tests PASS**. Note : le test `test_reconstitution_wallets_historiques_via_fusion` peut faiblir si l'assertion se base uniquement sur `tx.uuid in html` — la task 5 ajoute le rendu visuel.

- [ ] **Step 4.6: Suggérer commit au mainteneur**

```
feat(Session33): task 4 — reconstitution wallets historiques + query

_transactions_table_v2 reconstitue wallets_historiques_pks via les
FUSIONs(receiver=user.wallet), fait la query ORM optimisee
(select_related + prefetch implicite), exclut FIRST/CREATION/
BANK_TRANSFER, pagine 40/page et enrichit chaque Transaction via le
helper _enrichir_transaction_v2.

Refs: Session 33 - Visualisation historique transactions V2
```

---

## Task 5 : Template complet avec table 4 colonnes + pagination

**Objectif :** Rendu complet des 4 colonnes (Date | Action | Montant ±signé | Structure) + bouton pagination HTMX.

**Files:**
- Modify: `BaseBillet/templates/reunion/partials/account/transaction_history_v2.html` (remplacer squelette par rendu complet)

- [ ] **Step 5.1: Remplacer le template par la version complète**

Remplacer **entièrement** `BaseBillet/templates/reunion/partials/account/transaction_history_v2.html` par :

```html
{% load humanize i18n %}
{% comment %}
Partial V2 : historique des transactions d'un user sur /my_account/balance/.

LOCALISATION : BaseBillet/templates/reunion/partials/account/transaction_history_v2.html

Rendu par MyAccount._transactions_table_v2() uniquement pour les users V2
(verdict peut_recharger_v2 == "v2"). Les autres branches utilisent le
partial V1 transaction_history.html (inchange).

/ V2 partial for Transaction history. Rendered only for V2 users.
{% endcomment %}

<section id="transactionHistory" aria-live="polite" data-testid="tx-v2-container">
  <h2 class="pt-3">{% translate "Transaction history" %}</h2>

  {% if aucune_transaction %}
    <div class="text-center py-4 opacity-75" data-testid="tx-v2-empty">
      <i class="bi bi-clock-history fs-1 d-block mb-2" aria-hidden="true"></i>
      <p class="mb-0">{% translate "No transaction yet." %}</p>
    </div>
  {% else %}
    <div class="table-responsive">
      <table class="table" data-testid="tx-v2-table">
        <thead>
          <tr>
            <th>{% translate "Date" %}</th>
            <th>{% translate "Action" %}</th>
            <th class="text-end">{% translate "Amount" %}</th>
            <th>{% translate "Structure" %}</th>
          </tr>
        </thead>
        <tbody>
          {% for item in transactions %}
            <tr data-testid="tx-v2-row" data-tx-action="{{ item.action }}">
              <td>
                <span>{{ item.datetime|naturaltime }}</span>
                <br>
                <small class="opacity-75">{{ item.datetime|date:"d/m/Y H:i" }}</small>
              </td>
              <td>{{ item.action_display }}</td>
              <td class="text-end">
                {# Couleur + signe pour direction immediate : vert entrant, rouge sortant. #}
                {# / Color + sign for immediate direction: green incoming, red outgoing. #}
                <span class="{% if item.signe == '+' %}text-success{% else %}text-danger{% endif %}">
                  <strong>{{ item.signe }}{{ item.amount_euros|floatformat:2 }}</strong>
                  <span class="ms-1">{{ item.asset_name_affichage }}</span>
                </span>
              </td>
              <td>{{ item.structure }}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    {% if paginator_page.has_other_pages %}
      <nav aria-label="{% translate 'Pagination historique transactions' %}" class="d-flex justify-content-center gap-2">
        {% if paginator_page.has_previous %}
          <a class="btn btn-sm btn-outline-primary"
             href="?page={{ paginator_page.previous_page_number }}"
             hx-get="/my_account/transactions_table/?page={{ paginator_page.previous_page_number }}"
             hx-target="#transactionHistory"
             hx-swap="outerHTML"
             hx-indicator="#tibillet-spinner"
             data-testid="tx-v2-page-prev">
            <i class="bi bi-chevron-left" aria-hidden="true"></i>
            {% translate "Previous" %}
          </a>
        {% endif %}
        <span class="btn btn-sm btn-light disabled">
          {% blocktranslate with current=paginator_page.number total=paginator_page.paginator.num_pages %}
            Page {{ current }} / {{ total }}
          {% endblocktranslate %}
        </span>
        {% if paginator_page.has_next %}
          <a class="btn btn-sm btn-outline-primary"
             href="?page={{ paginator_page.next_page_number }}"
             hx-get="/my_account/transactions_table/?page={{ paginator_page.next_page_number }}"
             hx-target="#transactionHistory"
             hx-swap="outerHTML"
             hx-indicator="#tibillet-spinner"
             data-testid="tx-v2-page-next">
            {% translate "Next" %}
            <i class="bi bi-chevron-right" aria-hidden="true"></i>
          </a>
        {% endif %}
      </nav>
    {% endif %}
  {% endif %}
</section>
```

- [ ] **Step 5.2: Lancer tous les tests du fichier**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py -v --api-key dummy
```

Expected : **6 tests PASS** (inchangé niveau count, mais le HTML contient maintenant les vraies lignes).

- [ ] **Step 5.3: Suggérer commit au mainteneur**

```
feat(Session33): task 5 — template V2 complet 4 colonnes + pagination HTMX

Rendu complet : Date (naturaltime + date brute) | Action | Montant
±signe (vert entrant / rouge sortant) + asset | Structure. Pagination
HTMX avec swap outerHTML sur #transactionHistory. Fallback href
pour no-JS.

Refs: Session 33 - Visualisation historique transactions V2
```

---

## Task 6 : Tests exclusion actions techniques + tri desc + pagination + wallet absent

**Objectif :** Consolider la couverture avec 4 tests supplémentaires.

**Files:**
- Modify: `tests/pytest/test_transactions_table_v2.py` (ajouter 4 tests)

- [ ] **Step 6.1: Écrire les 4 tests**

Ajouter à la fin de `tests/pytest/test_transactions_table_v2.py` :

```python
@pytest.fixture
def user_v2_sans_wallet():
    """
    User sans wallet (user neuf qui n'a jamais ete credite).
    / User without wallet (new user never credited).
    """
    email = f"{TEST_PREFIX} no_wallet {uuid.uuid4()}@test.local"
    user = TibilletUser.objects.create(email=email, username=email)
    return user


def test_transactions_table_v2_wallet_absent(config_v2, user_v2_sans_wallet):
    """
    User sans wallet -> aucune_transaction=True, message "empty" visible.
    / User without wallet -> empty state visible.
    """
    with tenant_context(config_v2):
        request = RequestFactory().get("/my_account/transactions_table/")
        request.user = user_v2_sans_wallet
        response = MyAccount().transactions_table(request)
        assert response.status_code == 200
        html = response.content.decode()
        assert 'data-testid="tx-v2-empty"' in html


def test_transactions_table_v2_tri_chronologique_desc(
    asset_fed_instance, config_v2, user_v2, tenant_federation_fed
):
    """
    3 Transactions crees a des datetimes differents -> ordre desc dans le rendu.
    / 3 tx created at different datetimes -> desc order in output.
    """
    from datetime import timedelta
    base = timezone.now()

    for i, minutes in enumerate([0, 10, 20]):
        Transaction.objects.create(
            sender=asset_fed_instance.wallet_origin,
            receiver=user_v2.wallet,
            asset=asset_fed_instance,
            amount=1000 + i,  # amounts distincts pour reperer l'ordre
            action=Transaction.REFILL,
            tenant=tenant_federation_fed,
            datetime=base - timedelta(minutes=minutes),
        )

    with tenant_context(config_v2):
        request = RequestFactory().get("/my_account/transactions_table/")
        request.user = user_v2
        response = MyAccount().transactions_table(request)
        html = response.content.decode()
        # Le montant le plus recent (1000) doit apparaitre AVANT 1001 et 1002
        # dans le HTML (tri desc).
        # / Most recent amount (1000) must appear BEFORE 1001 and 1002 (desc).
        pos_10_00 = html.find("10,00")
        pos_10_01 = html.find("10,01")
        pos_10_02 = html.find("10,02")
        assert pos_10_00 != -1 and pos_10_01 != -1 and pos_10_02 != -1
        assert pos_10_00 < pos_10_01 < pos_10_02


def test_transactions_table_v2_exclusion_actions_techniques(
    asset_fed_instance, config_v2, user_v2, tenant_federation_fed
):
    """
    FIRST, CREATION, BANK_TRANSFER crees sur le wallet user -> ABSENTS du HTML.
    SALE/REFILL present -> DANS le HTML.
    / Technical actions excluded from rendering, non-technical included.
    """
    actions_masquees = [
        Transaction.FIRST,
        Transaction.CREATION,
        Transaction.BANK_TRANSFER,
    ]
    for act in actions_masquees:
        Transaction.objects.create(
            sender=asset_fed_instance.wallet_origin,
            receiver=user_v2.wallet,
            asset=asset_fed_instance,
            amount=1111,  # marker unique
            action=act,
            tenant=tenant_federation_fed,
            datetime=timezone.now(),
        )
    # Une action visible pour controle positif.
    # / One visible action for positive control.
    Transaction.objects.create(
        sender=asset_fed_instance.wallet_origin,
        receiver=user_v2.wallet,
        asset=asset_fed_instance,
        amount=2222,  # marker unique
        action=Transaction.REFILL,
        tenant=tenant_federation_fed,
        datetime=timezone.now(),
    )

    with tenant_context(config_v2):
        request = RequestFactory().get("/my_account/transactions_table/")
        request.user = user_v2
        response = MyAccount().transactions_table(request)
        html = response.content.decode()
        # Action visible (REFILL 22,22) presente.
        # / Visible action present.
        assert "22,22" in html
        # Actions techniques (11,11) ABSENTES — aucune des 3 ne doit s'afficher.
        # / Technical actions (11,11) absent.
        assert "11,11" not in html


def test_transactions_table_v2_pagination_40_par_page(
    asset_fed_instance, config_v2, user_v2, tenant_federation_fed
):
    """
    45 Transactions crees -> page 1 = 40 lignes, has_other_pages=True.
    / 45 tx -> page 1 = 40 rows, has_other_pages=True.
    """
    from datetime import timedelta
    base = timezone.now()
    for i in range(45):
        Transaction.objects.create(
            sender=asset_fed_instance.wallet_origin,
            receiver=user_v2.wallet,
            asset=asset_fed_instance,
            amount=100 + i,
            action=Transaction.REFILL,
            tenant=tenant_federation_fed,
            datetime=base - timedelta(seconds=i),
        )

    with tenant_context(config_v2):
        # Page 1 : 40 lignes + bouton "Next".
        # / Page 1: 40 rows + "Next" button.
        request_p1 = RequestFactory().get("/my_account/transactions_table/")
        request_p1.user = user_v2
        response_p1 = MyAccount().transactions_table(request_p1)
        html_p1 = response_p1.content.decode()
        assert html_p1.count('data-testid="tx-v2-row"') == 40
        assert 'data-testid="tx-v2-page-next"' in html_p1

        # Page 2 : 5 lignes + bouton "Previous".
        # / Page 2: 5 rows + "Previous" button.
        request_p2 = RequestFactory().get("/my_account/transactions_table/?page=2")
        request_p2.user = user_v2
        response_p2 = MyAccount().transactions_table(request_p2)
        html_p2 = response_p2.content.decode()
        assert html_p2.count('data-testid="tx-v2-row"') == 5
        assert 'data-testid="tx-v2-page-prev"' in html_p2
```

- [ ] **Step 6.2: Lancer tous les tests du fichier**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py -v --api-key dummy
```

Expected : **10 tests PASS** (6 précédents + 4 nouveaux).

- [ ] **Step 6.3: Non-régression Sessions 31 + 32**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_refill_service.py tests/pytest/test_tokens_table_v2.py tests/pytest/test_peut_recharger_v2.py tests/pytest/test_traiter_paiement_cashless_refill.py -v --api-key dummy
```

Expected : tous les tests Sessions 31-32 passent (~31+ tests).

- [ ] **Step 6.4: Suggérer commit au mainteneur**

```
test(Session33): task 6 — 4 tests supplementaires (wallet absent, tri,
exclusion techniques, pagination)

Consolide la couverture : 10 tests pytest au total. Valide que
FIRST/CREATION/BANK_TRANSFER sont bien masques, tri desc strict,
pagination 40/page avec Previous/Next.

Refs: Session 33 - Visualisation historique transactions V2
```

---

## Task 7 : Test non-régression V1 legacy

**Objectif :** Vérifier que le verdict `"v1_legacy"` (tenant avec `server_cashless`) n'appelle PAS la branche V2.

**Files:**
- Modify: `tests/pytest/test_transactions_table_v2.py` (ajouter 1 test)

- [ ] **Step 7.1: Écrire le test non-régression V1**

Ajouter à `tests/pytest/test_transactions_table_v2.py` :

```python
def test_transactions_table_v2_non_regression_branche_v1_legacy(
    tenant_lespass, tenant_federation_fed, user_v2
):
    """
    Verdict "v1_legacy" (tenant avec server_cashless) -> code V1 appele,
    template V1 rendu. Le conteneur V2 n'est PAS dans le HTML.
    / V1 legacy verdict -> V1 code called. V2 container NOT in HTML.
    """
    with tenant_context(tenant_lespass):
        config = Configuration.get_solo()
        module_initial = config.module_monnaie_locale
        server_initial = config.server_cashless
        config.module_monnaie_locale = True
        config.server_cashless = "https://laboutik.example.com"
        config.save(update_fields=["module_monnaie_locale", "server_cashless"])

    try:
        with tenant_context(tenant_lespass):
            request = RequestFactory().get("/my_account/transactions_table/")
            request.user = user_v2
            # 2 outcomes acceptables :
            # 1. Exception reseau (FedowAPI distant non joignable)
            # 2. Response 200 mais sans le conteneur V2
            # / 2 acceptable outcomes: network error OR 200 without V2 marker.
            try:
                response = MyAccount().transactions_table(request)
                html = response.content.decode()
                assert 'data-testid="tx-v2-container"' not in html
            except Exception as erreur_fedow_api:
                message = str(erreur_fedow_api).lower()
                indices_reseau = (
                    "connection", "resolve", "timeout", "http",
                    "fedow", "url", "name or service", "max retries",
                )
                assert any(i in message for i in indices_reseau), (
                    f"Exception inattendue : {erreur_fedow_api!r}"
                )
    finally:
        with tenant_context(tenant_lespass):
            config = Configuration.get_solo()
            config.module_monnaie_locale = module_initial
            config.server_cashless = server_initial
            config.save(update_fields=["module_monnaie_locale", "server_cashless"])
```

- [ ] **Step 7.2: Lancer tous les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py -v --api-key dummy
```

Expected : **11 tests PASS**.

- [ ] **Step 7.3: Suggérer commit au mainteneur**

```
test(Session33): task 7 — non-regression V1 legacy

Verdict "v1_legacy" ne passe PAS par _transactions_table_v2. Accepte
2 chemins : exception reseau (Fedow distant injoignable en test) OU
response 200 sans le marker V2.

Refs: Session 33 - Visualisation historique transactions V2
```

---

## Task 8 : i18n — extraction et traduction des 7 nouvelles strings

**Objectif :** Traductions FR/EN des strings ajoutées dans le template V2.

**Files:**
- Modify: `locale/fr/LC_MESSAGES/django.po`
- Modify: `locale/en/LC_MESSAGES/django.po`
- Recompile: `django.mo` fr + en

- [ ] **Step 8.1: Lancer makemessages**

```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
```

Expected : `processing locale fr/en`, aucune erreur.

- [ ] **Step 8.2: Éditer `locale/fr/LC_MESSAGES/django.po`**

Localiser les 7 nouvelles entrées (normalement fuzzy) ou absentes. Renseigner :

| msgid | msgstr FR |
|---|---|
| `No transaction yet.` | `Aucune transaction pour l'instant.` |
| `Amount` | `Montant` |
| `Structure` | `Structure` |
| `Pagination historique transactions` | `Pagination historique transactions` |
| `Previous` | `Précédent` |
| `Next` | `Suivant` |
| `Page {{ current }} / {{ total }}` | `Page {{ current }} / {{ total }}` |

**Supprimer** les marqueurs `#, fuzzy` s'ils apparaissent au-dessus de ces msgid.

- [ ] **Step 8.3: Éditer `locale/en/LC_MESSAGES/django.po`**

Renseigner les msgstr identiques à msgid (source déjà en anglais) :

| msgid | msgstr EN |
|---|---|
| `No transaction yet.` | `No transaction yet.` |
| `Amount` | `Amount` |
| `Structure` | `Structure` |
| `Pagination historique transactions` | `Transaction history pagination` |
| `Previous` | `Previous` |
| `Next` | `Next` |
| `Page {{ current }} / {{ total }}` | `Page {{ current }} / {{ total }}` |

- [ ] **Step 8.4: Compiler**

```bash
docker exec lespass_django poetry run django-admin compilemessages
```

Expected : aucune erreur.

- [ ] **Step 8.5: Re-lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py -v --api-key dummy
```

Expected : **11 tests PASS**.

- [ ] **Step 8.6: Suggérer commit au mainteneur**

```
i18n(Session33): task 8 — 7 nouvelles strings FR/EN

makemessages + traductions FR + compilemessages. Strings ajoutees :
- No transaction yet.
- Amount
- Structure
- Pagination historique transactions
- Previous
- Next
- Page X / Y

Refs: Session 33 - Visualisation historique transactions V2
```

---

## Task 9 : CHANGELOG + A TESTER + validation finale

**Objectif :** Documentation finale + tests complets de non-régression.

**Files:**
- Modify: `CHANGELOG.md`
- Create: `A TESTER et DOCUMENTER/visu-historique-transactions-v2.md`

- [ ] **Step 9.1: Ajouter entrée CHANGELOG**

Ouvrir `CHANGELOG.md` (racine) et ajouter AU TOP (après le titre principal ou au-dessus de Session 32) :

```markdown
## Session 33 — Visualisation historique transactions V2 / Tx history display V2 (2026-04-20)

**Quoi / What:** La page `/my_account/balance/` affiche desormais les `fedow_core.Transaction` locales pour les users V2 (historique complet incluant les transactions des wallets ephemeres fusionnes dans `user.wallet`), au lieu d'appeler `FedowAPI` distant. Dispatch symetrique Sessions 31-32 via `peut_recharger_v2(user)`.
/ The balance page now displays local `fedow_core.Transaction` for V2 users (full history including ephemeral wallets merged into `user.wallet`), instead of calling the remote `FedowAPI`.

**Pourquoi / Why:** Apres Sessions 31 (recharge FED V2) et 32 (affichage tokens V2), l'historique transactions restait lu sur Fedow distant. Un user qui rechargeait en V2 voyait son solde mis a jour mais pas la transaction dans son historique. Cette session complete la coherence read-side.
/ After Sessions 31 (refill) and 32 (tokens display), transaction history was still read from remote Fedow. This session completes read-side consistency.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | Dispatch V2 + methode `_transactions_table_v2` + 2 helpers module-level (`_enrichir_transaction_v2`, `_structure_pour_transaction`) |
| `BaseBillet/templates/reunion/partials/account/transaction_history_v2.html` | Nouveau partial : table 4 colonnes (Date \| Action \| Montant ±signe \| Structure) + pagination HTMX |
| `tests/pytest/test_transactions_table_v2.py` | Nouveau, 11 tests pytest DB-only |
| `A TESTER et DOCUMENTER/visu-historique-transactions-v2.md` | Guide mainteneur |
| `locale/{fr,en}/LC_MESSAGES/django.po` + `.mo` | 7 nouvelles strings |

### Migration
- **Migration necessaire / Migration required:** Non / No
- **Non-regression :** Sessions 31 + 32 inchangees. V1 `transaction_history.html` inchange.

### Tests
- 11 tests pytest DB-only
- Sessions 31 + 32 non-regressees
```

- [ ] **Step 9.2: Créer `A TESTER et DOCUMENTER/visu-historique-transactions-v2.md`**

```markdown
# Visualisation historique transactions V2 (Session 33)

## Ce qui a ete fait

La vue `MyAccount.transactions_table` (`BaseBillet/views.py`) dispatch sur `peut_recharger_v2(user)` :

- Verdict `"v2"` -> nouvelle methode `_transactions_table_v2` qui lit `fedow_core.Transaction` local + reconstitue les wallets ephemeres via les FUSIONs(receiver=user.wallet)
- Autres verdicts -> code V1 actuel inchange (appel `FedowAPI`)

Nouveau partial `reunion/partials/account/transaction_history_v2.html` : table 4 colonnes (Date \| Action \| Montant ±signe coloré \| Structure) + pagination HTMX 40/page.

### Modifications
| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` | Dispatch + methode + 2 helpers module-level |
| `BaseBillet/templates/reunion/partials/account/transaction_history_v2.html` | Nouveau partial |
| `tests/pytest/test_transactions_table_v2.py` | 11 tests pytest |
| `locale/*/LC_MESSAGES/django.po` | 7 strings i18n |
| `CHANGELOG.md` | Entree bilingue |

## Tests a realiser

### Test 1 : Scenario nominal (user V2 avec recharge)
1. Se connecter `admin@admin.com` sur `https://lespass.tibillet.localhost/`
2. Aller sur `/my_account/balance/`
3. Recharger 20€ via le bouton "Recharger TiBillets" → carte test `4242 4242 4242 4242`
4. Cliquer sur "Historique des transactions"
5. Verifier :
   - Section "Transaction history" avec 1 ligne "Recharge +20,00 TiBillets / TiBillet"
   - Date en naturaltime ("Il y a quelques secondes") + date brute (JJ/MM/AAAA HH:MM)
   - Montant en vert (+20,00)
   - Colonne Structure = "TiBillet"

### Test 2 : User avec carte fusionnee (historique complet)
1. Depuis la caisse POS V2 d'un lieu test : ajouter manuellement un wallet_ephemere lie a une carte test + creer une transaction SALE/REFILL sur ce wallet
2. Identifier l'user sur cette carte (flow `fusionner_wallet_ephemere`)
3. Se connecter avec ce user sur `/my_account/balance/`
4. Verifier dans l'historique :
   - Les tx d'avant identification (SALE sur le lieu)
   - La ligne FUSION "Rattachement carte → compte" avec "Carte #{number}" dans Structure
   - Les tx d'apres identification

### Test 3 : User sans wallet (empty state)
1. Creer un compte neuf, ne pas recharger
2. Aller sur `/my_account/balance/` → cliquer "Historique des transactions"
3. Verifier :
   - Icone horloge + message "Aucune transaction pour l'instant."

### Test 4 : Pagination
1. Avoir >40 transactions sur un compte user V2 (seed manuel)
2. Aller sur `/my_account/balance/` → historique
3. Verifier :
   - 40 lignes affichees
   - Nav en bas : "Previous disabled | Page 1/N | Next"
   - Clic Next → page 2 (HTMX swap, pas de full reload)

### Test 5 : Non-regression V1 legacy
1. Tenant avec `Configuration.server_cashless` renseigne (ex: connecté à LaBoutik externe)
2. Aller sur `/my_account/balance/` → historique
3. Verifier l'ancien tableau V1 (colonnes Value \| Action \| Date \| Path) s'affiche
4. Inspecter HTML : **pas** de `data-testid="tx-v2-container"`

### Commandes DB utiles

```python
# docker exec lespass_django poetry run python /DjangoFiles/manage.py shell_plus

from AuthBillet.models import TibilletUser
from fedow_core.models import Transaction
from django.db.models import Q

user = TibilletUser.objects.get(email="admin@admin.com")
# Transactions ou user.wallet est sender ou receiver.
tx = Transaction.objects.filter(
    Q(sender=user.wallet) | Q(receiver=user.wallet)
).select_related('asset', 'sender__origin', 'receiver__origin', 'card').order_by('-datetime')
for t in tx[:10]:
    print(f"{t.datetime} | {t.get_action_display()} | {t.amount} | {t.asset.name}")

# Reconstitue wallets historiques via FUSION.
from fedow_core.models import Transaction
fusions = Transaction.objects.filter(action=Transaction.FUSION, receiver=user.wallet)
wallets_historiques = {user.wallet.pk} | {f.sender_id for f in fusions}
print(f"Wallets historiques : {wallets_historiques}")
```

### Commande pytest rapide

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py -v --api-key dummy
```

## Compatibilite

- V1 legacy inchange (template `transaction_history.html`, flow `FedowAPI`)
- `FedowAPI` toujours appele pour `v1_legacy`, `wallet_legacy`, `feature_desactivee`
- Aucune migration DB
- Pas d'impact sur le POS V2 ni la billetterie

## Hors scope (sessions futures)

- Migration wallet_legacy -> fedow_core local (avec import des tx historiques)
- Suppression de `FedowAPI`
- Filtres avancés (par asset, par action, par date)
- Export CSV/PDF de l'historique
- Regroupement par date ("Aujourd'hui", "Hier"...)
```

- [ ] **Step 9.3: Ruff check sur nouveaux fichiers**

```bash
docker exec lespass_django poetry run ruff check tests/pytest/test_transactions_table_v2.py
```

Attendu : erreurs E402 sur les imports après `django.setup()` — pattern projet identique à tous les tests Session 31-32, non bloquant.

- [ ] **Step 9.4: Django check + suite complète pytest**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected : `System check identified no issues (0 silenced).`

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_transactions_table_v2.py tests/pytest/test_tokens_table_v2.py tests/pytest/test_refill_service.py tests/pytest/test_peut_recharger_v2.py tests/pytest/test_traiter_paiement_cashless_refill.py -v --api-key dummy
```

Expected : tous les tests Sessions 31+32+33 PASS (~40+ tests).

- [ ] **Step 9.5: Vérification visuelle manuelle**

1. Serveur dev up : `docker exec lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002` (ou `rsp`)
2. Ouvrir `https://lespass.tibillet.localhost/my_account/balance/`
3. Se connecter `admin@admin.com`
4. Recharger 20€ (carte test `4242 4242 4242 4242`)
5. Cliquer "Historique des transactions"
6. Vérifier les 4 colonnes + couleur verte sur le +20,00

- [ ] **Step 9.6: Suggérer commit final au mainteneur**

```
docs(Session33): task 9 — CHANGELOG + A TESTER + validation finale

- CHANGELOG.md : entree bilingue Session 33
- A TESTER et DOCUMENTER/visu-historique-transactions-v2.md : guide
  mainteneur avec 5 scenarios de test + commandes DB shell
- Ruff check + Django check + suite complete tests Sessions 31+32+33

Session 33 terminee et prete pour merge V2.

Refs: Session 33 - Visualisation historique transactions V2
```

---

## Synthèse du plan

| # | Task | Fichiers touchés | Tests cumulés |
|---|------|------------------|---------------|
| 1 | Dispatch V2 squelette + template minimal | views.py + new template + new test file | 1 |
| 2 | Helper `_structure_pour_transaction` | views.py + test file | +3 → 4 |
| 3 | Helper `_enrichir_transaction_v2` | views.py + test file | +1 → 5 |
| 4 | Reconstitution wallets historiques + query | views.py + test file | +1 → 6 |
| 5 | Template complet 4 colonnes + pagination | template | 6 (HTML enrichi) |
| 6 | Tests consolidation (wallet absent, tri, exclusion, pagination) | test file | +4 → 10 |
| 7 | Test non-régression V1 legacy | test file | +1 → 11 |
| 8 | i18n makemessages + traductions + compile | locale po/mo | 11 |
| 9 | CHANGELOG + A TESTER + validation finale | CHANGELOG + new doc | full suite |

**Total tests ajoutés :** 11 tests pytest dans `test_transactions_table_v2.py`.
**Total fichiers créés :** 3 (partial template, test file, doc mainteneur).
**Total fichiers modifiés :** 3 (views.py, CHANGELOG, 2 locale files).
**Pas de migration DB.**
