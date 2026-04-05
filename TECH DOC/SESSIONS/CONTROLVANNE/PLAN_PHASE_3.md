# Phase 3 — Facturation fedow_core pour controlvanne

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Les tirages de bière sont facturés via le circuit existant laboutik/fedow_core : vérification du solde wallet à l'authorize, création de Transaction + LigneArticle + MouvementStock au pour_end. Les ventes tireuse apparaissent dans la clôture de caisse.

**Architecture:** On modifie `authorize` pour calculer `allowed_ml` depuis le solde wallet (WalletService) et `event(pour_end)` pour créer la facturation (TransactionService + LigneArticle + StockService). Un helper `controlvanne/billing.py` encapsule la logique de facturation spécifique à la tireuse, séparé du ViewSet pour lisibilité. Le circuit réutilise les mêmes services que le paiement NFC laboutik — même Transaction, même LigneArticle, même MouvementStock.

**Tech Stack:** Django 4.x, DRF, fedow_core (WalletService, TransactionService), BaseBillet (LigneArticle, ProductSold, PriceSold), inventaire (StockService, MouvementStock)

**Spec de référence :** `TECH DOC/SESSIONS/CONTROLVANNE/SPEC_CONTROLVANNE.md` section 2.13

**IMPORTANT :** Ne pas faire d'opérations git. Le mainteneur gère git.

---

## Vue d'ensemble des fichiers

| Fichier | Action | Rôle |
|---------|--------|------|
| `controlvanne/billing.py` | Créer | Helpers : `obtenir_contexte_cashless()`, `facturer_tirage()` |
| `controlvanne/viewsets.py` | Modifier | `authorize` : calcul allowed_ml depuis wallet. `event(pour_end)` : appel `facturer_tirage()` |
| `tests/pytest/test_controlvanne_billing.py` | Créer | Tests facturation : solde, transaction, LigneArticle, stock |

---

## Circuit de facturation — résumé

```
authorize:
  1. CarteCashless → wallet (via _obtenir_ou_creer_wallet pattern)
  2. Asset TLF du tenant → WalletService.obtenir_solde(wallet, asset)
  3. prix_litre = tireuse.prix_litre (Decimal, EUR)
  4. allowed_ml = (solde_centimes / (prix_litre * 100)) * 1000
  5. min(allowed_ml, reservoir_disponible)

pour_end:
  1. montant_centimes = int(round(volume_ml * prix_litre / 1000 * 100))
  2. TransactionService.creer_vente(wallet_client → wallet_lieu, montant)
  3. ProductSold + PriceSold + LigneArticle (payment_method=LOCAL_EURO)
  4. StockService.decrementer_pour_vente() si Stock existe
  5. Session → ligne_article FK
```

---

## Ordre des tâches

1. Helper `controlvanne/billing.py`
2. Refactorer `authorize` dans viewsets.py
3. Refactorer `event(pour_end)` dans viewsets.py
4. Tests pytest
5. Vérification finale

---

### Tâche 1 : Créer controlvanne/billing.py

**Fichiers :**
- Créer : `controlvanne/billing.py`

- [ ] **Step 1 : Créer le fichier billing.py**

```python
"""
Facturation des tirages de bière via fedow_core.
/ Billing for beer pours via fedow_core.

LOCALISATION : controlvanne/billing.py

Ce module encapsule la logique de facturation spécifique à la tireuse.
Le ViewSet appelle ces fonctions — séparation ViewSet / logique métier.
/ This module encapsulates tap-specific billing logic.
The ViewSet calls these functions — separation of ViewSet / business logic.

Dépendances :
- fedow_core.services : WalletService, TransactionService
- fedow_core.models : Asset, Token, Transaction
- BaseBillet.models : LigneArticle, ProductSold, PriceSold, PaymentMethod, SaleOrigin
- inventaire.services : StockService
- QrcodeCashless.models : CarteCashless
- AuthBillet.models : Wallet
"""

import logging
from decimal import Decimal

from django.db import connection, transaction

logger = logging.getLogger(__name__)


def obtenir_contexte_cashless(carte):
    """
    Résout le wallet et l'asset TLF pour un paiement cashless tireuse.
    / Resolves the wallet and TLF asset for a tap cashless payment.

    Même logique que _obtenir_ou_creer_wallet() dans laboutik/views.py
    mais retourne aussi l'asset TLF et le wallet du lieu.
    / Same logic as _obtenir_ou_creer_wallet() in laboutik/views.py
    but also returns the TLF asset and the venue wallet.

    :param carte: CarteCashless
    :return: dict avec wallet_client, asset_tlf, wallet_lieu. None si pas d'asset TLF.
    """
    from AuthBillet.models import Wallet
    from fedow_core.models import Asset

    # --- Résoudre le wallet du client ---
    # / Resolve client wallet
    # Priorité : user.wallet > wallet_ephemere > créer éphémère
    # / Priority: user.wallet > wallet_ephemere > create ephemeral
    wallet_client = None

    if carte.user and hasattr(carte.user, 'wallet') and carte.user.wallet:
        wallet_client = carte.user.wallet
    elif carte.wallet_ephemere:
        wallet_client = carte.wallet_ephemere
    else:
        # Créer un wallet éphémère pour cette carte anonyme
        # / Create an ephemeral wallet for this anonymous card
        wallet_client = Wallet.objects.create(
            origin=connection.tenant,
            name=f"Éphémère - {carte.tag_id}",
        )
        carte.wallet_ephemere = wallet_client
        carte.save(update_fields=["wallet_ephemere"])

    # --- Trouver l'asset TLF actif du tenant ---
    # / Find the active TLF asset for this tenant
    asset_tlf = Asset.objects.filter(
        tenant_origin=connection.tenant,
        category=Asset.TLF,
        active=True,
    ).first()

    if not asset_tlf:
        logger.warning(f"Pas d'asset TLF actif pour le tenant {connection.tenant.name}")
        return None

    wallet_lieu = asset_tlf.wallet_origin

    return {
        "wallet_client": wallet_client,
        "asset_tlf": asset_tlf,
        "wallet_lieu": wallet_lieu,
    }


def calculer_volume_autorise_ml(solde_centimes, prix_litre_decimal, reservoir_disponible_ml):
    """
    Calcule le volume maximum autorisé en ml depuis le solde wallet.
    / Computes the maximum allowed volume in ml from wallet balance.

    Formule : (solde_centimes / prix_centimes_par_litre) * 1000 ml
    / Formula: (balance_cents / price_cents_per_liter) * 1000 ml

    :param solde_centimes: int — solde du wallet en centimes
    :param prix_litre_decimal: Decimal — prix au litre en EUR (ex: Decimal("3.50"))
    :param reservoir_disponible_ml: float — volume restant dans la tireuse en ml
    :return: Decimal — volume autorisé en ml (arrondi à 2 décimales)
    """
    if prix_litre_decimal <= 0:
        return Decimal("0.00")

    # Prix au litre en centimes / Price per liter in cents
    prix_centimes_par_litre = int(round(prix_litre_decimal * 100))
    if prix_centimes_par_litre <= 0:
        return Decimal("0.00")

    # Volume max selon le solde / Max volume based on balance
    volume_max_solde_ml = Decimal(str(solde_centimes)) / Decimal(str(prix_centimes_par_litre)) * 1000

    # Limiter au réservoir disponible / Cap at available reservoir
    volume_max_ml = min(volume_max_solde_ml, Decimal(str(reservoir_disponible_ml)))

    return max(Decimal("0.00"), volume_max_ml.quantize(Decimal("0.01")))


def facturer_tirage(session, tireuse, carte, volume_ml, contexte_cashless, ip="0.0.0.0"):
    """
    Facture un tirage de bière : Transaction + LigneArticle + MouvementStock.
    / Bills a beer pour: Transaction + LigneArticle + MouvementStock.

    Appelé au pour_end quand le volume final est connu.
    / Called at pour_end when the final volume is known.

    :param session: RfidSession — la session de service
    :param tireuse: TireuseBec — la tireuse
    :param carte: CarteCashless — la carte NFC du client
    :param volume_ml: Decimal — volume servi en ml
    :param contexte_cashless: dict retourné par obtenir_contexte_cashless()
    :param ip: str — IP du Raspberry Pi
    :return: dict avec transaction, ligne_article, montant_centimes. None si volume=0.
    """
    from fedow_core.services import TransactionService
    from BaseBillet.models import (
        LigneArticle, ProductSold, PriceSold,
        PaymentMethod, SaleOrigin,
    )

    if volume_ml <= 0:
        return None

    prix_litre = tireuse.prix_litre  # Decimal, EUR
    if prix_litre <= 0:
        logger.warning(f"Tireuse {tireuse.nom_tireuse} : prix_litre=0, pas de facturation")
        return None

    # Calculer le montant en centimes / Calculate amount in cents
    # montant = volume_ml * prix_litre / 1000 * 100
    # Ex: 250ml * 3.50 EUR/L = 0.250L * 3.50 = 0.875 EUR = 88 centimes
    montant_eur = volume_ml * prix_litre / Decimal("1000")
    montant_centimes = int(round(montant_eur * 100))

    if montant_centimes <= 0:
        return None

    wallet_client = contexte_cashless["wallet_client"]
    wallet_lieu = contexte_cashless["wallet_lieu"]
    asset_tlf = contexte_cashless["asset_tlf"]
    tenant_courant = connection.tenant

    # --- Bloc atomique : transaction + LigneArticle + stock ---
    # / Atomic block: transaction + LigneArticle + stock
    with transaction.atomic():
        # 1. Créer la transaction fedow_core (débit client → crédit lieu)
        # / Create fedow_core transaction (debit client → credit venue)
        tx = TransactionService.creer_vente(
            sender_wallet=wallet_client,
            receiver_wallet=wallet_lieu,
            asset=asset_tlf,
            montant_en_centimes=montant_centimes,
            tenant=tenant_courant,
            card=carte,
            ip=ip,
            comment=f"Tirage {tireuse.nom_tireuse}: {float(volume_ml):.0f}ml",
        )

        # 2. Snapshots ProductSold / PriceSold
        # Le fut actif est un Product, le prix est un Price avec poids_mesure=True
        # / The active keg is a Product, the price is a Price with poids_mesure=True
        produit = tireuse.fut_actif
        prix_obj = produit.prices.filter(poids_mesure=True, archived=False).first()

        product_sold, _ = ProductSold.objects.get_or_create(
            product=produit,
            event=None,
            defaults={"categorie_article": produit.categorie_article},
        )

        price_sold, _ = PriceSold.objects.get_or_create(
            productsold=product_sold,
            price=prix_obj,
            defaults={"prix": prix_obj.prix},
        )

        # 3. Créer la LigneArticle / Create the LigneArticle
        # Volume en centilitres pour weight_quantity (unité stock = cl)
        # / Volume in centiliters for weight_quantity (stock unit = cl)
        volume_cl = int(round(float(volume_ml) / 10))

        import uuid as uuid_module
        uuid_transaction = uuid_module.uuid4()

        ligne = LigneArticle.objects.create(
            pricesold=price_sold,
            qty=1,
            amount=montant_centimes,
            sale_origin=SaleOrigin.LABOUTIK,
            payment_method=PaymentMethod.LOCAL_EURO,
            status=LigneArticle.VALID,
            asset=asset_tlf.uuid,
            carte=carte,
            wallet=wallet_client,
            point_de_vente=tireuse.point_de_vente,
            weight_quantity=volume_cl,
            uuid_transaction=uuid_transaction,
        )

        # 4. Lier la session à la ligne / Link session to line
        session.ligne_article = ligne
        session.save(update_fields=["ligne_article"])

        # 5. Décrémenter le stock inventaire si le produit en a un
        # / Decrement inventory stock if the product has one
        try:
            stock_du_produit = produit.stock_inventaire
            from inventaire.services import StockService
            StockService.decrementer_pour_vente(
                stock=stock_du_produit,
                contenance=volume_cl,
                qty=1,
                ligne_article=ligne,
            )
        except Exception:
            # Pas de stock géré — comportement normal
            # / No stock managed — normal behavior
            pass

    logger.info(
        f"Facturation: tireuse={tireuse.nom_tireuse} volume={float(volume_ml):.0f}ml "
        f"montant={montant_centimes}cts tx={tx.id} ligne={ligne.uuid}"
    )

    return {
        "transaction": tx,
        "ligne_article": ligne,
        "montant_centimes": montant_centimes,
    }
```

- [ ] **Step 2 : Vérifier l'import**

```bash
docker exec lespass_django poetry run python -c "from controlvanne.billing import obtenir_contexte_cashless, calculer_volume_autorise_ml, facturer_tirage; print('OK')"
```

---

### Tâche 2 : Refactorer authorize — calcul allowed_ml depuis wallet

**Fichiers :**
- Modifier : `controlvanne/viewsets.py` (méthode `authorize`, lignes ~100-177)

- [ ] **Step 1 : Modifier la méthode authorize**

Remplacer le bloc après le check maintenance (à partir de `# Créer la session RFID`) par une version qui vérifie le solde wallet :

Ancien code (lignes 146-177 environ) :
```python
        # Créer la session RFID / Create the RFID session
        session = RfidSession.objects.create(
            uid=uid,
            carte=carte,
            ...
            authorized=True,
            # Phase 3 : allowed_ml calculé depuis le solde wallet
            # / Phase 3: allowed_ml computed from wallet balance
            allowed_ml_session=tireuse.reservoir_ml if is_maintenance else Decimal("500.00"),
            volume_start_ml=Decimal("0.00"),
        )

        logger.info(...)

        return Response({
            "authorized": True,
            "session_id": session.pk,
            "is_maintenance": is_maintenance,
            "allowed_ml": float(session.allowed_ml_session),
            "liquid_label": tireuse.liquid_label,
            "message": "Maintenance mode" if is_maintenance else "OK",
        })
```

Nouveau code :
```python
        # --- Maintenance : pas de facturation ---
        # / Maintenance: no billing
        if is_maintenance:
            session = RfidSession.objects.create(
                uid=uid,
                carte=carte,
                tireuse_bec=tireuse,
                label_snapshot=str(carte),
                liquid_label_snapshot=tireuse.liquid_label,
                is_maintenance=True,
                carte_maintenance=carte_maintenance,
                produit_maintenance_snapshot=carte_maintenance.produit if carte_maintenance else "",
                authorized=True,
                allowed_ml_session=tireuse.reservoir_ml,
                volume_start_ml=Decimal("0.00"),
            )
            return Response({
                "authorized": True,
                "session_id": session.pk,
                "is_maintenance": True,
                "allowed_ml": float(session.allowed_ml_session),
                "liquid_label": tireuse.liquid_label,
                "message": "Maintenance mode",
            })

        # --- Service normal : vérifier le solde wallet ---
        # / Normal service: check wallet balance
        from controlvanne.billing import obtenir_contexte_cashless, calculer_volume_autorise_ml
        from fedow_core.services import WalletService

        contexte = obtenir_contexte_cashless(carte)
        if not contexte:
            return Response({
                "authorized": False,
                "message": "No cashless asset configured for this venue.",
            })

        solde_centimes = WalletService.obtenir_solde(
            contexte["wallet_client"], contexte["asset_tlf"]
        )

        prix_litre = tireuse.prix_litre
        if prix_litre <= 0:
            return Response({
                "authorized": False,
                "message": "No price configured for the active keg.",
            })

        # Réservoir disponible (avec ou sans réserve)
        # / Available reservoir (with or without reserve)
        reservoir_disponible = float(tireuse.reservoir_ml)
        if tireuse.appliquer_reserve:
            reservoir_disponible = max(0, reservoir_disponible - float(tireuse.seuil_mini_ml))

        allowed_ml = calculer_volume_autorise_ml(
            solde_centimes, prix_litre, reservoir_disponible
        )

        if allowed_ml <= 0:
            return Response({
                "authorized": False,
                "message": "Insufficient funds.",
                "solde_centimes": solde_centimes,
            })

        session = RfidSession.objects.create(
            uid=uid,
            carte=carte,
            tireuse_bec=tireuse,
            label_snapshot=str(carte),
            liquid_label_snapshot=tireuse.liquid_label,
            is_maintenance=False,
            authorized=True,
            allowed_ml_session=allowed_ml,
            volume_start_ml=Decimal("0.00"),
        )

        logger.info(
            f"Authorize: carte={uid} tireuse={tireuse.nom_tireuse} "
            f"solde={solde_centimes}cts allowed={float(allowed_ml):.0f}ml"
        )

        return Response({
            "authorized": True,
            "session_id": session.pk,
            "is_maintenance": False,
            "allowed_ml": float(allowed_ml),
            "liquid_label": tireuse.liquid_label,
            "solde_centimes": solde_centimes,
            "message": "OK",
        })
```

- [ ] **Step 2 : Vérifier la syntaxe**

```bash
docker exec lespass_django poetry run python -c "from controlvanne.viewsets import TireuseViewSet; print('OK')"
```

---

### Tâche 3 : Refactorer event(pour_end) — facturation

**Fichiers :**
- Modifier : `controlvanne/viewsets.py` (méthode `event`, bloc `pour_end`/`card_removed`)

- [ ] **Step 1 : Modifier le bloc pour_end/card_removed dans event()**

Remplacer le bloc `elif event_type in ("pour_end", "card_removed"):` par :

Ancien code :
```python
        elif event_type in ("pour_end", "card_removed"):
            session.close_with_volume(float(volume_ml))

            # Décrémenter le réservoir avec le volume final / Decrement reservoir with final volume
            if volume_ml > 0:
                tireuse.reservoir_ml = max(
                    Decimal("0"),
                    tireuse.reservoir_ml - Decimal(str(float(volume_ml))),
                )
                tireuse.save(update_fields=["reservoir_ml"])

            logger.info(
                f"Event {event_type}: carte={uid} tireuse={tireuse.nom_tireuse} "
                f"volume={volume_ml}ml session={session.pk}"
            )
```

Nouveau code :
```python
        elif event_type in ("pour_end", "card_removed"):
            session.close_with_volume(float(volume_ml))

            # Décrémenter le réservoir / Decrement reservoir
            if volume_ml > 0:
                tireuse.reservoir_ml = max(
                    Decimal("0"),
                    tireuse.reservoir_ml - Decimal(str(float(volume_ml))),
                )
                tireuse.save(update_fields=["reservoir_ml"])

            # --- Facturation (sauf maintenance) ---
            # / Billing (except maintenance)
            resultat_facturation = None
            if not session.is_maintenance and volume_ml > 0 and tireuse.fut_actif:
                from controlvanne.billing import obtenir_contexte_cashless, facturer_tirage
                from fedow_core.exceptions import SoldeInsuffisant

                contexte = obtenir_contexte_cashless(session.carte)
                if contexte:
                    try:
                        resultat_facturation = facturer_tirage(
                            session=session,
                            tireuse=tireuse,
                            carte=session.carte,
                            volume_ml=volume_ml,
                            contexte_cashless=contexte,
                            ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
                        )
                    except SoldeInsuffisant:
                        # Le solde a changé entre authorize et pour_end (race condition).
                        # La bière est déjà servie — on log l'erreur mais on ne bloque pas.
                        # / Balance changed between authorize and pour_end (race condition).
                        # Beer is already served — log the error but don't block.
                        logger.error(
                            f"SoldeInsuffisant au pour_end: carte={uid} "
                            f"tireuse={tireuse.nom_tireuse} volume={volume_ml}ml"
                        )

            logger.info(
                f"Event {event_type}: carte={uid} tireuse={tireuse.nom_tireuse} "
                f"volume={volume_ml}ml session={session.pk} "
                f"facture={'oui' if resultat_facturation else 'non'}"
            )
```

Aussi, ajouter `montant_centimes` dans la réponse du event. Modifier le return à la fin de event() :

Ancien code :
```python
        return Response({
            "status": "ok",
            "event_type": event_type,
            "session_id": session.pk,
            "volume_ml": float(volume_ml),
        })
```

Nouveau code :
```python
        response_data = {
            "status": "ok",
            "event_type": event_type,
            "session_id": session.pk,
            "volume_ml": float(volume_ml),
        }
        if resultat_facturation:
            response_data["montant_centimes"] = resultat_facturation["montant_centimes"]
            response_data["transaction_id"] = resultat_facturation["transaction"].id

        return Response(response_data)
```

**Attention :** la variable `resultat_facturation` est définie dans le bloc `pour_end` mais pas dans les autres blocs. Il faut initialiser `resultat_facturation = None` au début de la méthode `event()`, juste après la recherche de session (vers la ligne 222). Ajouter :

```python
        # Variable pour la facturation (uniquement remplie par pour_end)
        # / Variable for billing (only set by pour_end)
        resultat_facturation = None
```

- [ ] **Step 2 : Vérifier la syntaxe**

```bash
docker exec lespass_django poetry run python -c "from controlvanne.viewsets import TireuseViewSet; print('OK')"
```

---

### Tâche 4 : Tests pytest facturation

**Fichiers :**
- Créer : `tests/pytest/test_controlvanne_billing.py`

- [ ] **Step 1 : Créer le fichier de tests**

```python
"""
Tests de la facturation tireuse (controlvanne) — Phase 3.
/ Tests for tap billing (controlvanne) — Phase 3.

LOCALISATION : tests/pytest/test_controlvanne_billing.py

Couvre :
- obtenir_contexte_cashless : résolution wallet + asset TLF
- calculer_volume_autorise_ml : formule volume = f(solde, prix)
- authorize avec solde wallet réel
- event pour_end avec Transaction + LigneArticle créées
- Fonds insuffisants → refus

Prérequis :
- Un asset TLF actif doit exister sur le tenant lespass
- Un wallet avec du solde doit exister
"""

import pytest
import json
from decimal import Decimal

from django.test import Client as DjangoClient
from django_tenants.utils import schema_context


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def tireuse_api_key_billing(tenant):
    """TireuseAPIKey pour les tests billing.
    / TireuseAPIKey for billing tests."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseAPIKey
        _key_obj, key_string = TireuseAPIKey.objects.create_key(
            name="test-tireuse-billing"
        )
        yield key_string
        TireuseAPIKey.objects.filter(name="test-tireuse-billing").delete()


@pytest.fixture(scope="session")
def billing_headers(tireuse_api_key_billing):
    return {"HTTP_AUTHORIZATION": f"Api-Key {tireuse_api_key_billing}"}


@pytest.fixture(scope="session")
def billing_client():
    return DjangoClient(HTTP_HOST="lespass.tibillet.localhost")


@pytest.fixture(scope="session")
def asset_tlf(tenant):
    """Récupère ou crée un asset TLF actif pour le tenant lespass.
    / Gets or creates an active TLF asset for the lespass tenant."""
    with schema_context(tenant.schema_name):
        from fedow_core.models import Asset
        from AuthBillet.models import Wallet

        asset = Asset.objects.filter(
            tenant_origin=tenant,
            category=Asset.TLF,
            active=True,
        ).first()

        if not asset:
            # Créer wallet lieu + asset TLF / Create venue wallet + TLF asset
            wallet_lieu = Wallet.objects.create(
                origin=tenant,
                name="Wallet lieu test billing",
            )
            asset = Asset.objects.create(
                name="Monnaie locale test",
                category=Asset.TLF,
                currency_code="EUR",
                wallet_origin=wallet_lieu,
                tenant_origin=tenant,
                active=True,
            )

        yield asset


@pytest.fixture(scope="session")
def carte_avec_solde(tenant, asset_tlf):
    """CarteCashless avec un wallet crédité de 10 EUR (1000 centimes).
    / CarteCashless with a wallet credited with 10 EUR (1000 cents)."""
    with schema_context(tenant.schema_name):
        from QrcodeCashless.models import CarteCashless
        from AuthBillet.models import Wallet
        from fedow_core.models import Token

        # Créer carte / Create card
        import uuid
        carte = CarteCashless.objects.create(
            tag_id="TESTBL01",
            number="TESTBL01",
            uuid=uuid.uuid4(),
        )

        # Créer wallet éphémère / Create ephemeral wallet
        wallet = Wallet.objects.create(
            origin=tenant,
            name=f"Éphémère test billing - {carte.tag_id}",
        )
        carte.wallet_ephemere = wallet
        carte.save(update_fields=["wallet_ephemere"])

        # Créditer 1000 centimes (10 EUR) / Credit 1000 cents (10 EUR)
        Token.objects.create(
            wallet=wallet,
            asset=asset_tlf,
            value=1000,
        )

        yield carte

        # Nettoyage / Cleanup
        Token.objects.filter(wallet=wallet).delete()
        carte.delete()
        wallet.delete()


@pytest.fixture(scope="session")
def tireuse_billing(tenant):
    """TireuseBec avec un FutProduct qui a un prix au litre.
    / TireuseBec with a FutProduct that has a per-liter price."""
    with schema_context(tenant.schema_name):
        from controlvanne.models import TireuseBec, Debimetre
        from BaseBillet.models import Product, Price

        debimetre = Debimetre.objects.create(
            name="Test billing debimetre",
            flow_calibration_factor=6.5,
        )

        # Créer un FutProduct / Create a FutProduct
        fut = Product.objects.create(
            name="Test IPA Billing",
            categorie_article=Product.FUT,
            publish=True,
        )

        # Prix au litre : 5.00 EUR / Per-liter price: 5.00 EUR
        Price.objects.create(
            product=fut,
            name="Litre",
            prix=Decimal("5.00"),
            poids_mesure=True,
        )

        tireuse = TireuseBec.objects.create(
            nom_tireuse="Test Tap Billing",
            enabled=True,
            debimetre=debimetre,
            fut_actif=fut,
            reservoir_ml=Decimal("20000.00"),
            seuil_mini_ml=Decimal("500.00"),
            appliquer_reserve=True,
        )

        yield tireuse

        # Nettoyage / Cleanup
        tireuse.delete()
        Price.objects.filter(product=fut).delete()
        fut.delete()
        debimetre.delete()


# ──────────────────────────────────────────────────────────────────────
# Tests unitaires : billing.py
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCalculVolume:
    """Tests de calculer_volume_autorise_ml.
    / Tests for calculer_volume_autorise_ml."""

    def test_01_formule_basique(self):
        """1000 centimes (10 EUR) / 5 EUR/L = 2L = 2000 ml.
        / 1000 cents (10 EUR) / 5 EUR/L = 2L = 2000 ml."""
        from controlvanne.billing import calculer_volume_autorise_ml
        result = calculer_volume_autorise_ml(
            solde_centimes=1000,
            prix_litre_decimal=Decimal("5.00"),
            reservoir_disponible_ml=20000.0,
        )
        assert result == Decimal("2000.00")

    def test_02_limite_par_reservoir(self):
        """Solde permet 2000 ml mais réservoir = 500 ml → 500 ml.
        / Balance allows 2000 ml but reservoir = 500 ml → 500 ml."""
        from controlvanne.billing import calculer_volume_autorise_ml
        result = calculer_volume_autorise_ml(
            solde_centimes=1000,
            prix_litre_decimal=Decimal("5.00"),
            reservoir_disponible_ml=500.0,
        )
        assert result == Decimal("500.00")

    def test_03_solde_zero(self):
        """Solde 0 → 0 ml."""
        from controlvanne.billing import calculer_volume_autorise_ml
        result = calculer_volume_autorise_ml(
            solde_centimes=0,
            prix_litre_decimal=Decimal("5.00"),
            reservoir_disponible_ml=20000.0,
        )
        assert result == Decimal("0.00")

    def test_04_prix_zero(self):
        """Prix 0 → 0 ml (pas de division par zéro)."""
        from controlvanne.billing import calculer_volume_autorise_ml
        result = calculer_volume_autorise_ml(
            solde_centimes=1000,
            prix_litre_decimal=Decimal("0.00"),
            reservoir_disponible_ml=20000.0,
        )
        assert result == Decimal("0.00")


# ──────────────────────────────────────────────────────────────────────
# Tests d'intégration : authorize + event avec facturation
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestBillingIntegration:
    """Tests d'intégration authorize + pour_end avec facturation réelle.
    / Integration tests for authorize + pour_end with real billing."""

    def test_05_authorize_avec_solde(
        self, billing_client, billing_headers, tireuse_billing, carte_avec_solde, asset_tlf
    ):
        """Authorize retourne allowed_ml calculé depuis le solde wallet.
        / Authorize returns allowed_ml computed from wallet balance."""
        response = billing_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps({
                "tireuse_uuid": str(tireuse_billing.uuid),
                "uid": carte_avec_solde.tag_id,
            }),
            **billing_headers,
        )
        data = response.json()
        assert data["authorized"] is True
        # 1000 cts / 5 EUR/L = 2L = 2000 ml
        assert data["allowed_ml"] == 2000.0
        assert data["solde_centimes"] == 1000
        assert "session_id" in data

    def test_06_pour_end_cree_transaction(
        self, billing_client, billing_headers, tireuse_billing, carte_avec_solde, asset_tlf, tenant
    ):
        """Pour_end crée une Transaction + LigneArticle + débite le wallet.
        / Pour_end creates a Transaction + LigneArticle + debits the wallet."""
        # Authorize d'abord / Authorize first
        auth_resp = billing_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps({
                "tireuse_uuid": str(tireuse_billing.uuid),
                "uid": carte_avec_solde.tag_id,
            }),
            **billing_headers,
        )
        assert auth_resp.json()["authorized"] is True

        # Pour_end avec 500 ml / Pour_end with 500 ml
        response = billing_client.post(
            "/controlvanne/api/tireuse/event/",
            content_type="application/json",
            data=json.dumps({
                "tireuse_uuid": str(tireuse_billing.uuid),
                "uid": carte_avec_solde.tag_id,
                "event_type": "pour_end",
                "volume_ml": "500.00",
            }),
            **billing_headers,
        )
        data = response.json()
        assert data["status"] == "ok"
        # 500ml * 5 EUR/L = 0.5L * 5 = 2.50 EUR = 250 centimes
        assert data["montant_centimes"] == 250
        assert "transaction_id" in data

        # Vérifier que le wallet a été débité / Check wallet was debited
        with schema_context(tenant.schema_name):
            from fedow_core.services import WalletService
            nouveau_solde = WalletService.obtenir_solde(
                carte_avec_solde.wallet_ephemere, asset_tlf
            )
            # 1000 - 250 = 750 centimes
            assert nouveau_solde == 750

    def test_07_authorize_fonds_insuffisants(
        self, billing_client, billing_headers, tireuse_billing, tenant, asset_tlf
    ):
        """Carte avec solde 0 → authorized=False.
        / Card with balance 0 → authorized=False."""
        with schema_context(tenant.schema_name):
            from QrcodeCashless.models import CarteCashless
            from AuthBillet.models import Wallet
            from fedow_core.models import Token
            import uuid

            # Carte sans solde / Card with no balance
            carte_vide = CarteCashless.objects.create(
                tag_id="TESTBL02",
                number="TESTBL02",
                uuid=uuid.uuid4(),
            )
            wallet_vide = Wallet.objects.create(
                origin=tenant,
                name="Wallet vide billing",
            )
            carte_vide.wallet_ephemere = wallet_vide
            carte_vide.save(update_fields=["wallet_ephemere"])
            # Token avec solde 0 / Token with balance 0
            Token.objects.create(wallet=wallet_vide, asset=asset_tlf, value=0)

        response = billing_client.post(
            "/controlvanne/api/tireuse/authorize/",
            content_type="application/json",
            data=json.dumps({
                "tireuse_uuid": str(tireuse_billing.uuid),
                "uid": "TESTBL02",
            }),
            **billing_headers,
        )
        data = response.json()
        assert data["authorized"] is False
        assert "Insufficient" in data["message"]

        # Nettoyage / Cleanup
        with schema_context(tenant.schema_name):
            Token.objects.filter(wallet=wallet_vide).delete()
            carte_vide.delete()
            wallet_vide.delete()
```

- [ ] **Step 2 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_billing.py -v
```

---

### Tâche 5 : Vérification finale

- [ ] **Step 1 : System check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Step 2 : Tests controlvanne complets**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_api.py tests/pytest/test_controlvanne_billing.py -v
```

- [ ] **Step 3 : Non-régression complète**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

---

## Résumé des fichiers

| Fichier | Changement |
|---------|------------|
| `controlvanne/billing.py` | CRÉÉ — `obtenir_contexte_cashless()`, `calculer_volume_autorise_ml()`, `facturer_tirage()` |
| `controlvanne/viewsets.py` | MODIFIÉ — authorize calcule allowed_ml depuis wallet, event(pour_end) appelle facturer_tirage() |
| `tests/pytest/test_controlvanne_billing.py` | CRÉÉ — 7 tests (4 unitaires + 3 intégration) |

## Notes Phase 4

Points d'accroche pour les templates kiosk :
- La réponse `authorize` inclut maintenant `solde_centimes` et `allowed_ml` calculé → le kiosk peut afficher "Solde: X€, Max: Y cl"
- La réponse `event(pour_end)` inclut `montant_centimes` et `transaction_id` → le kiosk peut afficher "Facturé: X€"
