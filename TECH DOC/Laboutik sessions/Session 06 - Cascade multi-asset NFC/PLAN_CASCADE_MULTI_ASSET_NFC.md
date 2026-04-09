# Cascade multi-asset NFC — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre le débit NFC cascade multi-asset (TNF→TLF→FED), le débit direct non-fiduciaire (TIM/FID), et le paiement complémentaire (espèces/CB/2ème carte).

**Architecture:** Tout dans `_payer_par_nfc()` (approche FALC). Nouvelle fonction `_creer_lignes_articles_cascade()` pour créer N LigneArticle par article avec qty partielle et amount entier. Nouveau template HTMX `hx_complement_paiement.html` + action `payer_complementaire()`.

**Tech Stack:** Django, HTMX, fedow_core (WalletService, TransactionService, Asset), Unfold admin, Playwright (E2E).

**Spec:** `TECH DOC/Laboutik sessions/Session 06 - Cascade multi-asset NFC/DESIGN_CASCADE_MULTI_ASSET_NFC.md`

**Conventions:** Suivre le skill `/djc` (FALC, ViewSet, DRF Serializers, HTMX, i18n, a11y, data-testid). Lire `tests/TESTS_README.md` pour les pièges.

---

## Structure des fichiers

| Fichier | Action | Responsabilité |
|---------|--------|---------------|
| `BaseBillet/models.py` | Modifier | `Price.non_fiduciaire` + `clean()` |
| `BaseBillet/migrations/0215_price_non_fiduciaire.py` | Créer | Migration |
| `laboutik/views.py` | Modifier | `_payer_par_nfc()` refonte, `_creer_lignes_articles_cascade()`, constantes cascade, `payer_complementaire()` |
| `laboutik/templates/laboutik/partial/hx_complement_paiement.html` | Créer | Écran complémentaire |
| `laboutik/templates/laboutik/partial/hx_return_payment_success.html` | Modifier | Affichage multi-soldes |
| `laboutik/templates/laboutik/partial/hx_lire_nfc_complement.html` | Créer | Scan 2ème carte NFC |
| `laboutik/reports.py` | Modifier | `cashless_detail` enrichi (déjà presque OK) |
| `laboutik/printing/formatters.py` | Modifier | Ticket vente avec détail par asset |
| `Administration/admin/products.py` | Modifier | `POSPriceInline` : `non_fiduciaire` + conditional `asset` |
| `laboutik/management/commands/create_test_pos_data.py` | Modifier | Fixtures : FED, FID, articles TIM/FID, wallets garnis |
| `tests/pytest/test_cascade_nfc.py` | Créer | 68 tests pytest |
| `tests/e2e/test_cascade_nfc.py` | Créer | 8 tests E2E |
| `tests/e2e/test_admin_price_non_fiduciaire.py` | Créer | 6 tests admin |

---

## Task 1 : Price.non_fiduciaire — modèle + migration + validation

**Files:**
- Modify: `BaseBillet/models.py` (classe Price, ~ligne 1805)
- Create: `BaseBillet/migrations/0215_price_non_fiduciaire.py`
- Test: `tests/pytest/test_cascade_nfc.py`

### Étapes

- [ ] **Step 1 : Écrire les tests de validation Price**

```python
# tests/pytest/test_cascade_nfc.py
"""
Tests de la cascade multi-asset NFC.
/ Tests for multi-asset NFC cascade.

LOCALISATION : tests/pytest/test_cascade_nfc.py
"""
import uuid as uuid_module
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django_tenants.utils import tenant_context


# === Section N : Price.non_fiduciaire validation ===


@pytest.mark.django_db
def test_65_non_fiduciaire_true_sans_asset_leve_validation_error(tenant):
    """
    non_fiduciaire=True sans asset → ValidationError.
    / non_fiduciaire=True without asset → ValidationError.
    """
    from BaseBillet.models import Price, Product

    with tenant_context(tenant):
        produit = Product.objects.filter(methode_caisse=Product.VENTE).first()
        prix = Price(
            product=produit,
            name="Test sans asset",
            prix=Decimal("1.00"),
            non_fiduciaire=True,
            asset=None,
        )
        with pytest.raises(ValidationError) as exc_info:
            prix.clean()
        assert "asset" in str(exc_info.value)


@pytest.mark.django_db
def test_66_non_fiduciaire_true_avec_asset_fiduciaire_leve_validation_error(tenant):
    """
    non_fiduciaire=True avec asset TLF → ValidationError.
    Les fiduciaires (TLF/TNF/FED) passent par la cascade, pas par le débit direct.
    / non_fiduciaire=True with TLF asset → ValidationError.
    """
    from BaseBillet.models import Price, Product
    from fedow_core.models import Asset

    with tenant_context(tenant):
        produit = Product.objects.filter(methode_caisse=Product.VENTE).first()
        asset_tlf = Asset.objects.filter(
            tenant_origin=tenant, category=Asset.TLF, active=True
        ).first()
        if not asset_tlf:
            pytest.skip("Pas d'asset TLF en base")

        prix = Price(
            product=produit,
            name="Test TLF interdit",
            prix=Decimal("1.00"),
            non_fiduciaire=True,
            asset=asset_tlf,
        )
        with pytest.raises(ValidationError) as exc_info:
            prix.clean()
        assert "fiduciaire" in str(exc_info.value).lower() or "fiduciary" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_67_non_fiduciaire_true_avec_asset_tim_ok(tenant):
    """
    non_fiduciaire=True avec asset TIM → OK.
    / non_fiduciaire=True with TIM asset → OK.
    """
    from BaseBillet.models import Price, Product
    from fedow_core.models import Asset

    with tenant_context(tenant):
        produit = Product.objects.filter(methode_caisse=Product.VENTE).first()
        asset_tim = Asset.objects.filter(
            tenant_origin=tenant, category=Asset.TIM, active=True
        ).first()
        if not asset_tim:
            pytest.skip("Pas d'asset TIM en base")

        prix = Price(
            product=produit,
            name="Test TIM ok",
            prix=Decimal("1.00"),
            non_fiduciaire=True,
            asset=asset_tim,
        )
        # Ne doit PAS lever d'exception
        # / Must NOT raise an exception
        prix.clean()


@pytest.mark.django_db
def test_68_non_fiduciaire_false_avec_asset_tim_ignore(tenant):
    """
    non_fiduciaire=False avec asset=TIM → pas d'erreur, asset ignoré.
    / non_fiduciaire=False with asset=TIM → no error, asset ignored.
    """
    from BaseBillet.models import Price, Product
    from fedow_core.models import Asset

    with tenant_context(tenant):
        produit = Product.objects.filter(methode_caisse=Product.VENTE).first()
        asset_tim = Asset.objects.filter(
            tenant_origin=tenant, category=Asset.TIM, active=True
        ).first()
        if not asset_tim:
            pytest.skip("Pas d'asset TIM en base")

        prix = Price(
            product=produit,
            name="Test ignore",
            prix=Decimal("1.00"),
            non_fiduciaire=False,
            asset=asset_tim,
        )
        # Ne doit PAS lever d'exception
        prix.clean()
```

- [ ] **Step 2 : Lancer les tests, vérifier qu'ils échouent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_cascade_nfc.py::test_65_non_fiduciaire_true_sans_asset_leve_validation_error tests/pytest/test_cascade_nfc.py::test_66_non_fiduciaire_true_avec_asset_fiduciaire_leve_validation_error tests/pytest/test_cascade_nfc.py::test_67_non_fiduciaire_true_avec_asset_tim_ok tests/pytest/test_cascade_nfc.py::test_68_non_fiduciaire_false_avec_asset_tim_ignore -v
```

Attendu : FAIL (champ `non_fiduciaire` n'existe pas)

- [ ] **Step 3 : Ajouter le champ et le clean() sur Price**

Dans `BaseBillet/models.py`, après le champ `asset` (ligne ~1822) :

```python
    # Tarif en monnaie non-fiduciaire (temps, fidélité, crypto, etc.)
    # Si True, le champ `asset` ci-dessus DOIT être renseigné
    # et doit pointer vers un asset non-fiduciaire (TIM, FID).
    # Si False (défaut), le prix est en euros et `asset` est ignoré.
    # / Non-fiduciary price (time, loyalty, crypto, etc.)
    # If True, the `asset` field above MUST be set
    # and must point to a non-fiduciary asset (TIM, FID).
    # If False (default), price is in euros and `asset` is ignored.
    non_fiduciaire = models.BooleanField(
        default=False,
        verbose_name=_("Non-fiduciary price"),
        help_text=_(
            "If checked, the price is in tokens (time, loyalty, etc.) "
            "instead of euros. You must select the asset below."
        ),
    )
```

Ajouter la méthode `clean()` sur Price (après `__str__`) :

```python
    def clean(self):
        """
        Validation du tarif non-fiduciaire.
        / Non-fiduciary price validation.

        Règles :
        - non_fiduciaire=True et asset=None → erreur
        - non_fiduciaire=True et asset fiduciaire (TLF/TNF/FED) → erreur
        - non_fiduciaire=False → asset ignoré, pas d'erreur
        """
        super().clean()

        if not self.non_fiduciaire:
            # Prix en euros — asset ignoré, rien à valider
            # / Euro price — asset ignored, nothing to validate
            return

        # non_fiduciaire=True : asset obligatoire
        # / non_fiduciaire=True: asset required
        if self.asset is None:
            raise ValidationError({
                "asset": _("An asset is required for non-fiduciary prices."),
            })

        # L'asset ne doit PAS être fiduciaire (TLF/TNF/FED passent par la cascade)
        # / Asset must NOT be fiduciary (TLF/TNF/FED go through the cascade)
        from fedow_core.models import Asset as FedowAsset
        categories_fiduciaires = (FedowAsset.TLF, FedowAsset.TNF, FedowAsset.FED)
        if self.asset.category in categories_fiduciaires:
            raise ValidationError({
                "asset": _(
                    "Fiduciary assets (local, gift, federated) use the automatic cascade. "
                    "Select a non-fiduciary asset (time, loyalty)."
                ),
            })
```

- [ ] **Step 4 : Créer la migration**

```bash
docker exec lespass_django poetry run python manage.py makemigrations BaseBillet --name price_non_fiduciaire
```

- [ ] **Step 5 : Appliquer la migration**

```bash
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
```

- [ ] **Step 6 : Lancer les tests, vérifier qu'ils passent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_cascade_nfc.py -k "test_65 or test_66 or test_67 or test_68" -v
```

Attendu : 4 PASS

- [ ] **Step 7 : Lancer la suite complète pour vérifier zéro régression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q --tb=short
```

---

## Task 2 : Enrichir les fixtures de test

**Files:**
- Modify: `laboutik/management/commands/create_test_pos_data.py`
- Test: vérification manuelle via `manage.py create_test_pos_data`

Les fixtures actuelles créent 3 Assets (TLF, TNF, TIM) mais pas FED ni FID. Pas de produit avec `non_fiduciaire=True`. Pas de wallet client garni en TNF/FED.

### Étapes

- [ ] **Step 1 : Ajouter FED et FID dans les assets créés**

Dans `create_test_pos_data.py`, enrichir la liste des assets (après la boucle existante ~ligne 151) :

```python
    # Ajouter FED (fédéré) et FID (fidélité) pour les tests cascade
    # / Add FED (federated) and FID (loyalty) for cascade tests
    for asset_def in [
        {
            "name": "Fédéré TiBillet",
            "category": FedowAsset.FED,
            "currency_code": "EUR",
        },
        {
            "name": "Points fidélité",
            "category": FedowAsset.FID,
            "currency_code": "PTS",
        },
    ]:
        asset_existant = FedowAsset.objects.filter(
            tenant_origin=tenant_client,
            category=asset_def["category"],
            active=True,
        ).first()
        if asset_existant is None:
            AssetService.creer_asset(
                tenant=tenant_client,
                name=asset_def["name"],
                category=asset_def["category"],
                currency_code=asset_def["currency_code"],
                wallet_origin=wallet_du_lieu,
            )
```

- [ ] **Step 2 : Ajouter un produit avec tarif non-fiduciaire TIM**

```python
    # Produit avec tarif en TIM (temps / bénévolat)
    # / Product with TIM price (time / volunteer)
    asset_tim = FedowAsset.objects.filter(
        tenant_origin=tenant_client, category=FedowAsset.TIM, active=True
    ).first()

    produit_machine_3d, _created = Product.objects.get_or_create(
        name="Machine 3D",
        defaults={
            "categorie_article": Product.NONE,
            "methode_caisse": Product.VENTE,
            "poid_liste": 50,
        },
    )
    if _created and asset_tim:
        Price.objects.create(
            product=produit_machine_3d,
            name="1 heure",
            prix=Decimal("1.00"),
            non_fiduciaire=True,
            asset=asset_tim,
            publish=True,
        )
        self.stdout.write(f"  Produit 'Machine 3D' créé avec tarif 1 TIM")

    # Produit avec DOUBLE tarif : EUR + TIM (bière bénévole)
    # / Product with DUAL pricing: EUR + TIM (volunteer beer)
    produit_biere = Product.objects.filter(name="Biere").first()
    if produit_biere and asset_tim:
        tarif_tim_existant = Price.objects.filter(
            product=produit_biere, non_fiduciaire=True, asset=asset_tim
        ).exists()
        if not tarif_tim_existant:
            Price.objects.create(
                product=produit_biere,
                name="Bénévole",
                prix=Decimal("1.00"),
                non_fiduciaire=True,
                asset=asset_tim,
                publish=True,
            )
            self.stdout.write(f"  Tarif 'Bénévole 1 TIM' ajouté à Biere")
```

- [ ] **Step 3 : Ajouter un produit avec tarif FID (fidélité)**

```python
    # Produit vendable uniquement en fidélité
    # / Product sold only with loyalty points
    asset_fid = FedowAsset.objects.filter(
        tenant_origin=tenant_client, category=FedowAsset.FID, active=True
    ).first()

    produit_pins, _created = Product.objects.get_or_create(
        name="Pin's TiBillet",
        defaults={
            "categorie_article": Product.NONE,
            "methode_caisse": Product.VENTE,
            "poid_liste": 51,
        },
    )
    if _created and asset_fid:
        Price.objects.create(
            product=produit_pins,
            name="300 points",
            prix=Decimal("300.00"),
            non_fiduciaire=True,
            asset=asset_fid,
            publish=True,
        )
        self.stdout.write(f"  Produit 'Pin's TiBillet' créé avec tarif 300 FID")
```

- [ ] **Step 4 : Garnir le wallet de la carte NFC de test avec TNF et FED**

```python
    # Garnir le wallet de la carte test avec des tokens multi-asset
    # / Top up the test card's wallet with multi-asset tokens
    from fedow_core.services import WalletService
    from django.db import transaction as db_transaction

    carte_test = CarteCashless.objects.filter(tag_id="AAAAAAAA").first()
    if carte_test:
        wallet_test = None
        if carte_test.user and carte_test.user.wallet:
            wallet_test = carte_test.user.wallet
        elif carte_test.wallet_ephemere:
            wallet_test = carte_test.wallet_ephemere

        if wallet_test:
            # TNF : 5€ cadeau
            asset_tnf = FedowAsset.objects.filter(
                tenant_origin=tenant_client, category=FedowAsset.TNF, active=True
            ).first()
            if asset_tnf:
                solde_tnf = WalletService.obtenir_solde(wallet_test, asset_tnf)
                if solde_tnf < 500:
                    with db_transaction.atomic():
                        WalletService.crediter(wallet_test, asset_tnf, 500 - solde_tnf)
                    self.stdout.write(f"  Wallet test crédité +{(500 - solde_tnf)/100:.2f}€ TNF")

            # FED : 3€ fédéré
            asset_fed = FedowAsset.objects.filter(
                tenant_origin=tenant_client, category=FedowAsset.FED, active=True
            ).first()
            if asset_fed:
                solde_fed = WalletService.obtenir_solde(wallet_test, asset_fed)
                if solde_fed < 300:
                    with db_transaction.atomic():
                        WalletService.crediter(wallet_test, asset_fed, 300 - solde_fed)
                    self.stdout.write(f"  Wallet test crédité +{(300 - solde_fed)/100:.2f}€ FED")

            # TIM : 5 unités temps
            if asset_tim:
                solde_tim = WalletService.obtenir_solde(wallet_test, asset_tim)
                if solde_tim < 500:
                    with db_transaction.atomic():
                        WalletService.crediter(wallet_test, asset_tim, 500 - solde_tim)
                    self.stdout.write(f"  Wallet test crédité +{(500 - solde_tim)/100} TIM")

            # FID : 1000 points
            if asset_fid:
                solde_fid = WalletService.obtenir_solde(wallet_test, asset_fid)
                if solde_fid < 100000:
                    with db_transaction.atomic():
                        WalletService.crediter(wallet_test, asset_fid, 100000 - solde_fid)
                    self.stdout.write(f"  Wallet test crédité +{(100000 - solde_fid)/100} FID")
```

- [ ] **Step 5 : Attacher les nouveaux produits au PV "Mix"**

```python
    # Attacher Machine 3D et Pin's au PV "Mix" pour les tests
    # / Attach Machine 3D and Pin's to "Mix" POS for tests
    pv_mix = PointDeVente.objects.filter(name__icontains="Mix").first()
    if pv_mix:
        if produit_machine_3d:
            pv_mix.products.add(produit_machine_3d)
        if produit_pins:
            pv_mix.products.add(produit_pins)
```

- [ ] **Step 6 : Lancer la commande et vérifier**

```bash
docker exec lespass_django poetry run python manage.py tenant_command create_test_pos_data --schema=lespass
```

- [ ] **Step 7 : Vérifier zéro régression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q --tb=short
```

---

## Task 3 : Admin POSPriceInline — non_fiduciaire + conditional asset

**Files:**
- Modify: `Administration/admin/products.py` (POSPriceInline, ~ligne 520)
- Test: `tests/e2e/test_admin_price_non_fiduciaire.py`

### Étapes

- [ ] **Step 1 : Ajouter non_fiduciaire et asset dans POSPriceInline**

Dans `Administration/admin/products.py`, modifier `POSPriceInline` :

```python
class POSPriceInline(BasePriceInline):
    """Inline tarifs pour les produits de caisse (POS).
    Ajoute contenance, poids_mesure, et non_fiduciaire (tarif en tokens).
    / POS product price inline.
    Adds contenance, weight/measure, and non-fiduciary (token pricing)."""

    fields = (
        "name", "prix", "poids_mesure", "contenance",
        "non_fiduciaire", "asset",
        ("publish", "order"),
    )

    # Champs conditionnels :
    # - contenance caché si poids_mesure coché
    # - asset caché si non_fiduciaire décoché
    # / Conditional fields:
    # - contenance hidden if poids_mesure checked
    # - asset hidden if non_fiduciaire unchecked
    inline_conditional_fields = {
        "contenance": "poids_mesure == false",
        "asset": "non_fiduciaire == true",
    }

    class Media:
        js = ("admin/js/inline_conditional_fields.js",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Filtre les assets dans le dropdown : uniquement TIM et FID du tenant.
        Les fiduciaires (TLF/TNF/FED) passent par la cascade, pas ici.
        / Filter assets in dropdown: only TIM and FID for this tenant.
        Fiduciary assets (TLF/TNF/FED) use the cascade, not direct pricing.
        """
        if db_field.name == "asset":
            from fedow_core.models import Asset as FedowAsset
            from django.db import connection
            categories_non_fiduciaires = (FedowAsset.TIM, FedowAsset.FID)
            kwargs["queryset"] = FedowAsset.objects.filter(
                tenant_origin=connection.tenant,
                category__in=categories_non_fiduciaires,
                active=True,
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
```

- [ ] **Step 2 : Lancer manage.py check**

```bash
docker exec lespass_django poetry run python manage.py check
```

Attendu : 0 issue

- [ ] **Step 3 : Écrire les tests E2E admin**

```python
# tests/e2e/test_admin_price_non_fiduciaire.py
"""
Tests E2E admin : champ non_fiduciaire sur POSPriceInline.
/ E2E tests for non_fiduciaire field on POSPriceInline.

LOCALISATION : tests/e2e/test_admin_price_non_fiduciaire.py
"""
import pytest


@pytest.mark.e2e
def test_80_checkbox_non_fiduciaire_affiche_asset(
    page, login_as_admin, django_shell, ensure_pos_data
):
    """
    Cocher non_fiduciaire → le champ asset apparaît.
    Décocher → le champ asset disparaît.
    / Check non_fiduciaire → asset field appears.
    Uncheck → asset field disappears.
    """
    login_as_admin(page)

    # Trouver un POSProduct
    # / Find a POSProduct
    uuid_produit = django_shell(
        "from BaseBillet.models import Product; "
        "p = Product.objects.filter(methode_caisse='VT').first(); "
        "print(p.uuid)"
    )
    page.goto(f"/admin/BaseBillet/posproduct/{uuid_produit}/change/")
    page.wait_for_load_state("networkidle")

    # Le champ asset doit être caché par défaut (non_fiduciaire=False)
    # / Asset field must be hidden by default
    premier_inline = page.locator(".inline-related").first
    champ_asset = premier_inline.locator("[class*='asset']")
    assert not champ_asset.is_visible()

    # Cocher non_fiduciaire
    # / Check non_fiduciaire
    checkbox = premier_inline.locator("input[name$='-non_fiduciaire']")
    checkbox.check()

    # Le champ asset doit être visible
    # / Asset field must be visible
    champ_asset.wait_for(state="visible", timeout=2000)
    assert champ_asset.is_visible()

    # Décocher → asset caché à nouveau
    # / Uncheck → asset hidden again
    checkbox.uncheck()
    assert not champ_asset.is_visible()


@pytest.mark.e2e
def test_81_asset_filtre_tim_fid_uniquement(
    page, login_as_admin, django_shell, ensure_pos_data
):
    """
    Le dropdown asset ne contient que TIM et FID, pas TLF/TNF/FED.
    / Asset dropdown contains only TIM and FID, not TLF/TNF/FED.
    """
    login_as_admin(page)

    uuid_produit = django_shell(
        "from BaseBillet.models import Product; "
        "p = Product.objects.filter(methode_caisse='VT').first(); "
        "print(p.uuid)"
    )
    page.goto(f"/admin/BaseBillet/posproduct/{uuid_produit}/change/")
    page.wait_for_load_state("networkidle")

    # Cocher non_fiduciaire pour voir le dropdown asset
    premier_inline = page.locator(".inline-related").first
    checkbox = premier_inline.locator("input[name$='-non_fiduciaire']")
    checkbox.check()

    # Lire les options du select asset
    # / Read asset select options
    select_asset = premier_inline.locator("select[name$='-asset']")
    options = select_asset.locator("option").all_text_contents()

    # Doit contenir TIM (Temps) et FID (Points fidélité)
    # Ne doit PAS contenir TLF, TNF, FED
    # / Must contain TIM and FID. Must NOT contain TLF, TNF, FED.
    options_texte = " ".join(options).lower()
    assert "temps" in options_texte or "time" in options_texte or "tim" in options_texte
    assert "fidel" in options_texte or "fid" in options_texte or "points" in options_texte
    assert "monnaie locale" not in options_texte
    assert "cadeau" not in options_texte
```

- [ ] **Step 4 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/e2e/test_admin_price_non_fiduciaire.py -v -s
```

---

## Task 4 : Constantes cascade + mapping asset→PaymentMethod

**Files:**
- Modify: `laboutik/views.py` (~ligne 3093, zone des constantes)

### Étapes

- [ ] **Step 1 : Ajouter les constantes de cascade**

Après `MAPPING_CODES_PAIEMENT` (~ligne 3099) dans `laboutik/views.py` :

```python
# Ordre de priorité pour la cascade de débit NFC fiduciaire.
# Cadeau d'abord (offert au lieu), puis local (déjà encaissé à la recharge),
# puis fédéré (frais Stripe pour le lieu).
# Ordre fixe, pas configurable par tenant (décision brainstorming 2026-04-08).
# / Priority order for NFC fiduciary debit cascade.
# Gift first (free to venue), then local (already cashed at top-up),
# then federated (Stripe fees for venue).
# Fixed order, not configurable per tenant (brainstorming decision 2026-04-08).
ORDRE_CASCADE_FIDUCIAIRE = [Asset.TNF, Asset.TLF, Asset.FED]

# Mapping catégorie d'Asset → PaymentMethod pour les LigneArticle.
# Permet aux rapports de distinguer les paiements cadeau (LG) des paiements
# monnaie locale (LE) dans le Ticket X et la clôture.
# / Asset category → PaymentMethod mapping for LigneArticle.
# Lets reports distinguish gift payments (LG) from local currency (LE)
# in Ticket X and closing reports.
MAPPING_ASSET_CATEGORY_PAYMENT_METHOD = {
    Asset.TNF: PaymentMethod.LOCAL_GIFT,    # LG — cadeau
    Asset.TLF: PaymentMethod.LOCAL_EURO,    # LE — monnaie locale
    Asset.FED: PaymentMethod.LOCAL_EURO,    # LE — fédéré (assimilé local en comptabilité)
    Asset.TIM: PaymentMethod.LOCAL_EURO,    # LE — temps (traité comme cashless)
    Asset.FID: PaymentMethod.LOCAL_EURO,    # LE — fidélité (traité comme cashless)
}

# Constante Decimal pour arrondir les qty partielles à 6 décimales.
# / Decimal constant for rounding partial qty to 6 decimal places.
SIX_DECIMALES = Decimal("0.000001")
```

- [ ] **Step 2 : Ajouter l'import Asset en haut du fichier si manquant**

Vérifier que `from fedow_core.models import Asset` est importé dans `laboutik/views.py`. Si absent :

```python
from fedow_core.models import Asset
```

- [ ] **Step 3 : Vérifier que ça compile**

```bash
docker exec lespass_django poetry run python -c "from laboutik.views import ORDRE_CASCADE_FIDUCIAIRE; print(ORDRE_CASCADE_FIDUCIAIRE)"
```

---

## Task 5 : `_creer_lignes_articles_cascade()` — nouvelle fonction

**Files:**
- Modify: `laboutik/views.py` (après `_creer_lignes_articles`, ~ligne 3605)
- Test: `tests/pytest/test_cascade_nfc.py`

C'est la fonction qui crée N LigneArticle par article avec qty partielle, amount entier en centimes, stock décrémenté 1 seule fois, et HMAC chaîné.

### Étapes

- [ ] **Step 1 : Écrire les tests de qty partielle et amounts**

```python
# Dans tests/pytest/test_cascade_nfc.py

# === Section B : qty partielle et amounts ===


@pytest.mark.django_db
def test_09_split_2_assets_somme_qty_exacte(tenant):
    """
    Split sur 2 assets : la somme des qty partielles == qty_totale exactement.
    / Split on 2 assets: sum of partial qty == total qty exactly.
    """
    from laboutik.views import _calculer_qty_partielles

    lignes = [
        {"amount_centimes": 100},  # 1€ sur TNF
        {"amount_centimes": 300},  # 3€ sur TLF
    ]
    prix_unitaire_centimes = 400  # Article à 4€
    qty_totale = Decimal("1")

    resultats = _calculer_qty_partielles(lignes, prix_unitaire_centimes, qty_totale)

    somme_qty = sum(r["qty"] for r in resultats)
    assert somme_qty == Decimal("1.000000")
    assert resultats[0]["qty"] == Decimal("0.250000")
    assert resultats[1]["qty"] == Decimal("0.750000")


@pytest.mark.django_db
def test_10_split_3_assets_derniere_prend_reste(tenant):
    """
    Split sur 3 assets : pas de .333333 infini. Dernière ligne = reste.
    / Split on 3 assets: no infinite .333333. Last line = remainder.
    """
    from laboutik.views import _calculer_qty_partielles

    lignes = [
        {"amount_centimes": 100},  # 1€
        {"amount_centimes": 100},  # 1€
        {"amount_centimes": 100},  # 1€
    ]
    prix_unitaire_centimes = 300  # Article à 3€
    qty_totale = Decimal("1")

    resultats = _calculer_qty_partielles(lignes, prix_unitaire_centimes, qty_totale)

    somme_qty = sum(r["qty"] for r in resultats)
    assert somme_qty == Decimal("1.000000")
    # Les 2 premières : 0.333333 (arrondi 6 déc)
    assert resultats[0]["qty"] == Decimal("0.333333")
    assert resultats[1]["qty"] == Decimal("0.333333")
    # La dernière prend le reste : 1 - 0.333333 - 0.333333 = 0.333334
    assert resultats[2]["qty"] == Decimal("0.333334")


@pytest.mark.django_db
def test_11_qty_superieure_a_1(tenant):
    """
    qty=3 (3 bières) splitté sur 2 assets.
    / qty=3 (3 beers) split on 2 assets.
    """
    from laboutik.views import _calculer_qty_partielles

    lignes = [
        {"amount_centimes": 400},   # 4€ sur TNF
        {"amount_centimes": 800},   # 8€ sur TLF
    ]
    prix_unitaire_centimes = 400   # Bière à 4€/unité, qty=3, total=12€
    qty_totale = Decimal("3")

    resultats = _calculer_qty_partielles(lignes, prix_unitaire_centimes, qty_totale)

    somme_qty = sum(r["qty"] for r in resultats)
    assert somme_qty == Decimal("3.000000")
    somme_amount = sum(l["amount_centimes"] for l in lignes)
    assert somme_amount == 1200  # 12€ en centimes
```

- [ ] **Step 2 : Implémenter `_calculer_qty_partielles()`**

Fonction utilitaire pure (pas d'accès DB) pour le calcul des qty :

```python
def _calculer_qty_partielles(lignes_avec_amounts, prix_unitaire_centimes, qty_totale):
    """
    Calcule les qty partielles pour N lignes d'un même article splitté.
    / Computes partial qty for N lines of the same split article.

    LOCALISATION : laboutik/views.py

    Chaque ligne a un amount_centimes (entier). La qty est proportionnelle.
    La dernière ligne prend le reste pour que la somme soit exacte.
    / Each line has an amount_centimes (integer). Qty is proportional.
    Last line takes the remainder so the sum is exact.

    :param lignes_avec_amounts: list de dicts avec clé "amount_centimes"
    :param prix_unitaire_centimes: int (prix unitaire en centimes)
    :param qty_totale: Decimal (quantité totale de l'article)
    :return: list de dicts enrichis avec clé "qty"
    """
    nombre_de_lignes = len(lignes_avec_amounts)

    # Cas trivial : 1 seule ligne = qty complète
    # / Trivial case: 1 line = full qty
    if nombre_de_lignes == 1:
        lignes_avec_amounts[0]["qty"] = qty_totale
        return lignes_avec_amounts

    # Cas général : N lignes, calcul proportionnel
    # / General case: N lines, proportional calculation
    somme_qty_precedentes = Decimal("0")

    for i, ligne in enumerate(lignes_avec_amounts):
        est_derniere_ligne = (i == nombre_de_lignes - 1)

        if est_derniere_ligne:
            # Dernière ligne : prend le reste exact
            # / Last line: takes the exact remainder
            ligne["qty"] = qty_totale - somme_qty_precedentes
        else:
            # Lignes intermédiaires : proportionnel, arrondi 6 décimales
            # / Intermediate lines: proportional, rounded to 6 decimal places
            qty_proportionnelle = (
                qty_totale
                * Decimal(ligne["amount_centimes"])
                / Decimal(prix_unitaire_centimes)
            ).quantize(SIX_DECIMALES)
            ligne["qty"] = qty_proportionnelle
            somme_qty_precedentes += qty_proportionnelle

    return lignes_avec_amounts
```

- [ ] **Step 3 : Vérifier les tests qty passent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_cascade_nfc.py -k "test_09 or test_10 or test_11" -v
```

- [ ] **Step 4 : Implémenter `_creer_lignes_articles_cascade()`**

Fonction complète qui crée les LigneArticle avec qty partielle, stock, HMAC :

```python
def _creer_lignes_articles_cascade(
    lignes_pre_calculees,
    carte=None,
    carte_complement=None,
    wallet=None,
    uuid_transaction=None,
    point_de_vente=None,
):
    """
    Crée N LigneArticle par article à partir des lignes pré-calculées par la cascade.
    / Creates N LigneArticle per article from cascade pre-calculated lines.

    LOCALISATION : laboutik/views.py

    Différences avec _creer_lignes_articles() (paiement simple) :
    - Chaque article peut générer N lignes (1 par asset débité + 1 complémentaire)
    - qty est partielle (somme = qty totale de l'article)
    - amount est le montant débité sur cet asset (entier, centimes)
    - Stock décrémenté 1 SEULE FOIS par article (pas par ligne partielle)
    - HMAC chaîné sur toutes les lignes créées
    / Differences with _creer_lignes_articles() (simple payment):
    - Each article can generate N lines (1 per debited asset + 1 complementary)
    - qty is partial (sum = total article qty)
    - amount is the amount debited on this asset (integer, cents)
    - Stock decremented ONCE per article (not per partial line)
    - HMAC chained on all created lines

    :param lignes_pre_calculees: list de tuples (article_dict, asset_or_none, amount_centimes, payment_method_code)
        - article_dict : dict de _extraire_articles_du_panier (product, price, quantite, prix_centimes, etc.)
        - asset_or_none : Asset fedow_core ou None (complémentaire espèces/CB)
        - amount_centimes : int (montant débité sur cet asset)
        - payment_method_code : str (PaymentMethod value : LE, LG, CA, CC...)
    :param carte: CarteCashless (1ère carte NFC, ou None)
    :param carte_complement: CarteCashless (2ème carte NFC, ou None)
    :param wallet: Wallet du client (1ère carte)
    :param uuid_transaction: UUID unique de ce paiement
    :param point_de_vente: PointDeVente d'origine
    :return: list de LigneArticle créées
    """
    # Mode école (LNE exigence 5)
    # / Training mode (LNE req. 5)
    laboutik_config = LaboutikConfiguration.get_solo()
    if laboutik_config.mode_ecole:
        sale_origin = SaleOrigin.LABOUTIK_TEST
    else:
        sale_origin = SaleOrigin.LABOUTIK

    lignes_creees = []
    produits_stock_mis_a_jour = []

    # Regrouper les lignes par article pour :
    # 1. Calculer les qty partielles (par article)
    # 2. Décrémer le stock 1 seule fois (par article)
    # / Group lines by article to:
    # 1. Calculate partial qty (per article)
    # 2. Decrement stock once (per article)
    from collections import OrderedDict
    lignes_par_article = OrderedDict()

    for article_dict, asset_ou_none, amount_centimes, payment_method_code in lignes_pre_calculees:
        # Clé unique par article dans le panier
        # / Unique key per article in cart
        cle_article = id(article_dict)

        if cle_article not in lignes_par_article:
            lignes_par_article[cle_article] = {
                "article": article_dict,
                "lignes": [],
            }
        lignes_par_article[cle_article]["lignes"].append({
            "asset": asset_ou_none,
            "amount_centimes": amount_centimes,
            "payment_method": payment_method_code,
        })

    for cle_article, groupe in lignes_par_article.items():
        article = groupe["article"]
        lignes_du_groupe = groupe["lignes"]

        produit = article["product"]
        prix_obj = article["price"]
        qty_totale = article["quantite"]
        prix_centimes = article["prix_centimes"]
        weight_amount = article.get("weight_amount")

        # Calculer les qty partielles
        # / Calculate partial qty
        _calculer_qty_partielles(lignes_du_groupe, prix_centimes, qty_totale)

        # ProductSold + PriceSold (1 seul par article, comme avant)
        # / ProductSold + PriceSold (1 per article, as before)
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

        # Créer les LigneArticle (1 par asset débité)
        # / Create LigneArticle (1 per debited asset)
        for ligne_info in lignes_du_groupe:
            asset_obj = ligne_info["asset"]
            asset_uuid = asset_obj.uuid if asset_obj else None

            # Déterminer la carte associée à cette ligne
            # Les lignes complémentaires (asset=None, espèces/CB) n'ont pas de carte
            # / Determine the card for this line
            # Complementary lines (asset=None, cash/CC) have no card
            carte_pour_ligne = None
            if asset_obj is not None:
                carte_pour_ligne = carte  # par défaut carte 1
                # TODO: si 2ème carte, déterminer laquelle

            ligne = LigneArticle.objects.create(
                pricesold=price_sold,
                qty=ligne_info["qty"],
                amount=ligne_info["amount_centimes"],
                sale_origin=sale_origin,
                payment_method=ligne_info["payment_method"],
                status=LigneArticle.VALID,
                uuid_transaction=uuid_transaction,
                point_de_vente=point_de_vente,
                asset=asset_uuid,
                carte=carte_pour_ligne,
                wallet=wallet,
                weight_quantity=weight_amount,
            )
            lignes_creees.append(ligne)

        # Stock : décrémenter 1 SEULE fois par article (qty totale)
        # / Stock: decrement ONCE per article (total qty)
        try:
            stock_du_produit = produit.stock_inventaire
            from inventaire.services import StockService

            if weight_amount:
                StockService.decrementer_pour_vente(
                    stock=stock_du_produit,
                    contenance=weight_amount,
                    qty=1,
                    ligne_article=lignes_creees[-1],  # dernière ligne de cet article
                )
            else:
                StockService.decrementer_pour_vente(
                    stock=stock_du_produit,
                    contenance=prix_obj.contenance,
                    qty=qty_totale,
                    ligne_article=lignes_creees[-1],
                )

            stock_du_produit.refresh_from_db()
            produits_stock_mis_a_jour.append({
                "product_uuid": str(produit.uuid),
                "quantite": stock_du_produit.quantite,
                "unite": stock_du_produit.unite,
                "en_alerte": stock_du_produit.est_en_alerte(),
                "en_rupture": stock_du_produit.est_en_rupture(),
                "bloquant": (
                    stock_du_produit.est_en_rupture()
                    and not stock_du_produit.autoriser_vente_hors_stock
                ),
                "quantite_lisible": _formater_stock_lisible(
                    stock_du_produit.quantite, stock_du_produit.unite
                ),
            })
        except Exception:
            pass

    # Chainage HMAC (conformité LNE exigence 8)
    # / HMAC chaining (LNE compliance req. 8)
    cle_hmac = laboutik_config.get_or_create_hmac_key()
    sale_origin_pour_chaine = SaleOrigin.LABOUTIK
    if lignes_creees:
        sale_origin_pour_chaine = lignes_creees[0].sale_origin

    previous_hmac_value = obtenir_previous_hmac(sale_origin=sale_origin_pour_chaine)

    for ligne_a_chainer in lignes_creees:
        ligne_a_chainer.total_ht = calculer_total_ht(
            ligne_a_chainer.amount, ligne_a_chainer.vat
        )
        ligne_a_chainer.previous_hmac = previous_hmac_value
        ligne_a_chainer.hmac_hash = calculer_hmac(
            ligne_a_chainer, cle_hmac, previous_hmac_value
        )
        ligne_a_chainer.save(update_fields=["total_ht", "hmac_hash", "previous_hmac"])
        previous_hmac_value = ligne_a_chainer.hmac_hash

    # Broadcast WebSocket stock
    # / WebSocket stock broadcast
    if produits_stock_mis_a_jour:
        from django.db import transaction
        from wsocket.broadcast import broadcast_stock_update

        donnees_par_produit = {}
        for donnee in produits_stock_mis_a_jour:
            donnees_par_produit[donnee["product_uuid"]] = donnee
        donnees_a_broadcaster = list(donnees_par_produit.values())

        transaction.on_commit(
            lambda: broadcast_stock_update(donnees_a_broadcaster, str(point_de_vente.uuid))
        )

    return lignes_creees
```

- [ ] **Step 5 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_cascade_nfc.py -v --tb=short
```

---

## Task 6 : Refonte `_payer_par_nfc()` — cascade complète

**Files:**
- Modify: `laboutik/views.py` (~ligne 4793, méthode `_payer_par_nfc`)
- Test: `tests/pytest/test_cascade_nfc.py` (sections A, C, D, G, H, I, J, K, O)

C'est la tâche principale. La méthode `_payer_par_nfc()` est réécrite pour supporter :
1. Classification fiduciaire / non-fiduciaire / recharges
2. Vérification soldes non-fiduciaires (tout ou rien)
3. Cascade TNF→TLF→FED article par article
4. Détection complémentaire
5. Bloc atomic avec ordre : crédits RC/TM → débits non-fidu → débits cascade → lignes

### Étapes

- [ ] **Step 1 : Écrire les tests de cascade de base (section A)**

Les tests #1 à #8 de la spec. Utiliser le pattern existant des tests POS : `schema_context('lespass')` + `APIClient` + fixture `auth_headers`.

Chaque test :
1. Crée/ajuste les soldes wallet
2. POST vers `payer()` avec `moyen_paiement=nfc` et `tag_id=...`
3. Vérifie les LigneArticle créées (count, amount, asset, qty, payment_method)

Voir la matrice de tests section 11 de la spec pour les 68 cas pytest.

**Exemple test #2 (TNF + TLF partiel) :**

```python
@pytest.mark.django_db
def test_02_cascade_tnf_plus_tlf(tenant, api_client, auth_headers):
    """
    TNF insuffisant pour tout → split TNF + TLF.
    2 LigneArticle, sum(amount) = total, sum(qty) = 1.
    / TNF insufficient for all → split TNF + TLF.
    """
    from django_tenants.utils import tenant_context
    from django.db import transaction as db_transaction
    from fedow_core.models import Asset
    from fedow_core.services import WalletService
    from BaseBillet.models import LigneArticle
    from QrcodeCashless.models import CarteCashless

    with tenant_context(tenant):
        # Setup : carte avec 100 centimes TNF + 500 centimes TLF
        # / Setup: card with 100 cents TNF + 500 cents TLF
        carte = CarteCashless.objects.filter(tag_id="AAAAAAAA").first()
        assert carte is not None, "Carte test AAAAAAAA introuvable"

        wallet = carte.user.wallet if carte.user else carte.wallet_ephemere
        assert wallet is not None

        asset_tnf = Asset.objects.filter(
            tenant_origin=tenant, category=Asset.TNF, active=True
        ).first()
        asset_tlf = Asset.objects.filter(
            tenant_origin=tenant, category=Asset.TLF, active=True
        ).first()
        assert asset_tnf and asset_tlf

        # Ajuster les soldes : TNF=100, TLF=500
        # / Adjust balances: TNF=100, TLF=500
        with db_transaction.atomic():
            token_tnf, _ = Token.objects.get_or_create(
                wallet=wallet, asset=asset_tnf, defaults={"value": 0}
            )
            Token.objects.filter(pk=token_tnf.pk).update(value=100)
            token_tlf, _ = Token.objects.get_or_create(
                wallet=wallet, asset=asset_tlf, defaults={"value": 0}
            )
            Token.objects.filter(pk=token_tlf.pk).update(value=500)

        # Trouver un article VT à 4€ (400 centimes)
        # / Find a VT article at 4€
        from BaseBillet.models import Product, Price
        from laboutik.models import PointDeVente
        produit_biere = Product.objects.filter(name="Biere").first()
        prix_biere = Price.objects.filter(product=produit_biere, non_fiduciaire=False).first()
        pv = PointDeVente.objects.filter(hidden=False).first()

        uuid_tx = uuid_module.uuid4()

        # POST paiement NFC
        response = api_client.post(
            "/laboutik/paiement/payer/",
            data={
                f"repid-{produit_biere.uuid}--{prix_biere.uuid}": "1",
                "moyen_paiement": "nfc",
                "tag_id": "AAAAAAAA",
                "uuid_pv": str(pv.uuid),
            },
            **auth_headers,
        )
        assert response.status_code == 200

        # Vérifier : 2 LigneArticle
        # / Verify: 2 LigneArticle
        lignes = LigneArticle.objects.filter(
            pricesold__price=prix_biere,
            carte=carte,
        ).order_by("-datetime")[:2]

        assert len(lignes) == 2

        amounts = sorted([l.amount for l in lignes])
        assert amounts == [100, 300]  # 1€ TNF + 3€ TLF

        qtys = [l.qty for l in lignes]
        somme_qty = sum(qtys)
        assert somme_qty == Decimal("1.000000")

        # Vérifier les assets
        assets_debites = set(l.asset for l in lignes)
        assert asset_tnf.uuid in assets_debites
        assert asset_tlf.uuid in assets_debites
```

- [ ] **Step 2 : Réécrire `_payer_par_nfc()` — Phase 1 à 4 (classification + cascade)**

Remplacer le corps de `_payer_par_nfc()` par l'algorithme de la spec section 3.2. Conserver les gardes existantes (recharges payantes bloquées, carte inconnue, wallet).

Le code est trop long pour le plan (300+ lignes). Suivre fidèlement le pseudo-code de la spec :
- Phase 1 : `soldes_cascade = OrderedDict()` avec ORDRE_CASCADE_FIDUCIAIRE
- Phase 2 : classifier articles (fiduciaire / non-fiduciaire / recharge / adhésion)
- Phase 3 : vérifier soldes non-fiduciaires → rejet total si insuffisant
- Phase 4 : boucle cascade article par article

- [ ] **Step 3 : Réécrire `_payer_par_nfc()` — Phase 5-6 (complémentaire ou atomic)**

- Phase 5 : calculer `total_complementaire`
- Phase 6 : si complémentaire > 0 → render `hx_complement_paiement.html` (Task 7)
- Sinon : bloc atomic complet (Phase 7 de la spec section 6)

- [ ] **Step 4 : Réécrire le bloc atomic**

Ordre dans l'atomic (spec section 6) :
1. Crédits RC/TM (avant débits)
2. Débits non-fiduciaires → `TransactionService.creer_vente()`
3. Débits fiduciaires cascade → `TransactionService.creer_vente()` par asset
4. Appel `_creer_lignes_articles_cascade()` pour toutes les lignes
5. Adhésions + billetterie (code existant adapté)

- [ ] **Step 5 : Adapter l'écran de succès**

Le contexte de succès doit inclure les soldes de tous les assets débités :

```python
# Lire les soldes de tous les assets débités (après les débits)
# / Read all debited asset balances (after debits)
soldes_apres_paiement = []
for asset_debite in assets_debites_dans_cascade:
    solde_restant = WalletService.obtenir_solde(wallet_client, asset_debite)
    soldes_apres_paiement.append({
        "name": asset_debite.name,
        "solde_euros": solde_restant / 100,
    })
```

- [ ] **Step 6 : Lancer les tests de cascade**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_cascade_nfc.py -k "cascade" -v --tb=short
```

- [ ] **Step 7 : Lancer la suite complète**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q --tb=short
```

---

## Task 7 : Paiement complémentaire — template + action

**Files:**
- Create: `laboutik/templates/laboutik/partial/hx_complement_paiement.html`
- Create: `laboutik/templates/laboutik/partial/hx_lire_nfc_complement.html`
- Modify: `laboutik/views.py` (nouvelle action `payer_complementaire` sur PaiementViewSet)
- Modify: `laboutik/templates/laboutik/partial/hx_return_payment_success.html`
- Test: `tests/pytest/test_cascade_nfc.py` (sections E, F)

### Étapes

- [ ] **Step 1 : Créer le template `hx_complement_paiement.html`**

```html
<!--
ECRAN COMPLEMENT DE PAIEMENT
/ Complementary payment screen

LOCALISATION : laboutik/templates/laboutik/partial/hx_complement_paiement.html

Affiché quand la cascade NFC ne couvre pas le total.
L'opérateur choisit comment payer le reste : espèces, CB, ou 2ème carte NFC.

FLUX :
1. _payer_par_nfc() calcule cascade → insuffisant
2. Render ce template avec total_nfc et reste
3. Clic espèces/CB → hx-post payer-complementaire (moyen=espece/carte_bancaire)
4. Clic autre carte → hx-get lire_nfc_complement (scan 2ème carte)
-->
<div id="complement-paiement"
     data-testid="complement-paiement"
     aria-live="polite">

    <div class="text-center mb-4">
        <h3>{% translate "Complément de paiement" %}</h3>

        <p class="fs-5">
            {% translate "Carte" %} : <strong>{{ tag_id_carte1 }}</strong>
        </p>

        {% if detail_cascade %}
        <div class="mb-3">
            {% for detail in detail_cascade %}
            <span class="badge bg-secondary me-1">
                {{ detail.name }} : {{ detail.montant_euros }}€
            </span>
            {% endfor %}
        </div>
        {% endif %}

        <p class="fs-4">
            {% translate "Total panier" %} : <strong>{{ total_panier_euros }}€</strong>
        </p>
        <p class="fs-3 text-warning">
            {% translate "Reste à payer" %} : <strong>{{ reste_euros }}€</strong>
        </p>
    </div>

    <!-- Hidden fields pour propager les données cascade -->
    <input type="hidden" name="tag_id_carte1" value="{{ tag_id_carte1 }}" form="addition-form">
    <input type="hidden" name="cascade_carte1" value="{{ cascade_carte1_json }}" form="addition-form">
    <input type="hidden" name="total_nfc_carte1" value="{{ total_nfc_carte1 }}" form="addition-form">

    <div class="d-flex justify-content-center gap-3">
        {% if accepte_especes %}
        <button type="button"
                class="btn btn-success btn-lg"
                data-testid="complement-btn-especes"
                hx-post="{% url 'laboutik-paiement-payer-complementaire' %}"
                hx-vals='{"moyen_complement": "espece"}'
                hx-include="#addition-form"
                hx-target="body"
                hx-swap="innerHTML"
                hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
            <i class="bi bi-cash" aria-hidden="true"></i>
            {% translate "Espèces" %}
        </button>
        {% endif %}

        {% if accepte_carte_bancaire %}
        <button type="button"
                class="btn btn-primary btn-lg"
                data-testid="complement-btn-cb"
                hx-post="{% url 'laboutik-paiement-payer-complementaire' %}"
                hx-vals='{"moyen_complement": "carte_bancaire"}'
                hx-include="#addition-form"
                hx-target="body"
                hx-swap="innerHTML"
                hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
            <i class="bi bi-credit-card" aria-hidden="true"></i>
            {% translate "Carte bancaire" %}
        </button>
        {% endif %}

        {% if autoriser_2eme_carte %}
        <button type="button"
                class="btn btn-warning btn-lg"
                data-testid="complement-btn-nfc"
                hx-get="{% url 'laboutik-paiement-lire-nfc-complement' %}"
                hx-target="#complement-paiement"
                hx-swap="outerHTML">
            <i class="bi bi-nfc" aria-hidden="true"></i>
            {% translate "Autre carte" %}
        </button>
        {% endif %}
    </div>
</div>
```

- [ ] **Step 2 : Créer le template `hx_lire_nfc_complement.html`**

Template de scan NFC pour la 2ème carte, similaire à `hx_lire_nfc_client.html` mais POST vers `payer_complementaire` avec `moyen_complement=nfc`.

- [ ] **Step 3 : Implémenter l'action `payer_complementaire()`**

```python
@action(detail=False, methods=["POST"], url_path="payer-complementaire")
def payer_complementaire(self, request):
    """
    POST /laboutik/paiement/payer-complementaire/
    Finalise un paiement NFC avec complément (espèces, CB, ou 2ème carte).
    / Finalizes an NFC payment with complement (cash, CC, or 2nd card).

    LOCALISATION : laboutik/views.py

    FLUX :
    1. Relire les données cascade carte1 depuis le POST
    2. Relire les articles du panier depuis les repid-*
    3. Re-calculer la cascade (protection race condition)
    4. Si moyen_complement = espece/carte_bancaire :
       → bloc atomic (débits NFC cascade + lignes complémentaires)
    5. Si moyen_complement = nfc (2ème carte) :
       → cascade sur carte2 pour le reste
       → si encore insuffisant → re-render complément (sans bouton "Autre carte")
       → si OK → bloc atomic (débits carte1 + carte2)
    6. Même uuid_transaction pour toutes les lignes
    """
    # ... implémentation complète ...
```

- [ ] **Step 4 : Adapter `hx_return_payment_success.html` pour multi-soldes**

Ajouter une section conditionnelle qui affiche les soldes par asset :

```html
{% if soldes_apres_paiement %}
<div class="mt-3" data-testid="soldes-multi-asset">
    {% for solde in soldes_apres_paiement %}
    <span class="badge bg-secondary me-1">
        {{ solde.name }} : {{ solde.solde_euros }}€
    </span>
    {% endfor %}
</div>
{% endif %}
```

- [ ] **Step 5 : Écrire les tests complémentaire (section E)**

Tests #26 à #33 de la spec.

- [ ] **Step 6 : Écrire les tests 2ème carte (section F)**

Tests #34 à #39 de la spec. Attention : piège #36 (même carte), #38 (wallet_ephemere).

- [ ] **Step 7 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_cascade_nfc.py -k "complement" -v --tb=short
```

---

## Task 8 : Rapports + impression — enrichissement cashless_detail

**Files:**
- Modify: `laboutik/reports.py` (~ligne 76, `calculer_totaux_par_moyen`)
- Modify: `laboutik/printing/formatters.py` (~ligne 25, `formatter_ticket_vente`)
- Test: `tests/pytest/test_cascade_nfc.py` (sections L, M)

### Étapes

- [ ] **Step 1 : Vérifier que `calculer_totaux_par_moyen()` gère déjà le multi-asset**

D'après l'exploration, cette méthode regroupe déjà par `asset` UUID et construit `cashless_detail` avec nom/code/montant. Si la cascade crée des LigneArticle avec des `asset` UUID différents (TNF, TLF, FED), les rapports devraient déjà fonctionner.

→ Écrire le test #59 pour vérifier :

```python
@pytest.mark.django_db
def test_59_cashless_detail_par_asset(tenant):
    """
    Après un paiement cascade TNF+TLF, cashless_detail contient 2 entrées.
    / After a TNF+TLF cascade payment, cashless_detail has 2 entries.
    """
    # Créer 2 LigneArticle avec des assets différents
    # Appeler calculer_totaux_par_moyen()
    # Vérifier cashless_detail a 2 entrées avec les bons noms et montants
```

- [ ] **Step 2 : Enrichir `formatter_ticket_vente()` avec le détail par asset**

Ajouter une section dans le dict de retour pour le détail cascade :

```python
# Détail cascade NFC (si paiement multi-asset)
# / NFC cascade detail (if multi-asset payment)
detail_cascade = []
if uuid_transaction:
    lignes_cascade_du_paiement = LigneArticle.objects.filter(
        uuid_transaction=uuid_transaction,
        asset__isnull=False,
    ).values("asset").annotate(total=Sum("amount"))

    from fedow_core.models import Asset as FedowAsset
    for ligne in lignes_cascade_du_paiement:
        asset_obj = FedowAsset.objects.filter(uuid=ligne["asset"]).first()
        if asset_obj:
            detail_cascade.append({
                "name": asset_obj.name,
                "total": ligne["total"],
            })

# Dans le return :
"cascade_detail": detail_cascade,
```

- [ ] **Step 3 : Adapter `escpos_builder.py` pour imprimer le détail cascade**

Si `cascade_detail` est non-vide, ajouter une section "Détail NFC" sur le ticket.

- [ ] **Step 4 : Lancer les tests rapports**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_cascade_nfc.py -k "cashless_detail or ticket_cascade" -v
```

---

## Task 9 : Tests E2E Playwright

**Files:**
- Create: `tests/e2e/test_cascade_nfc.py`

### Étapes

- [ ] **Step 1 : Écrire les 8 tests E2E (section P de la spec)**

Tests #75 à #82. Utiliser les fixtures `pos_page`, `django_shell`, `ensure_pos_data`.

Pattern clé pour les tests NFC E2E :
1. `pos_page(page, "Mix")` pour ouvrir le PV Mix
2. Cliquer sur un article (ex: `page.locator('[data-name="Biere"]').click()`)
3. Cliquer VALIDER → identification NFC
4. Simuler scan NFC : `page.locator('#nfc-input').fill("AAAAAAAA")` + submit
5. Vérifier l'écran de succès ou l'écran complémentaire
6. Vérifier en DB via `django_shell`

- [ ] **Step 2 : Lancer les tests E2E**

```bash
docker exec lespass_django poetry run pytest tests/e2e/test_cascade_nfc.py -v -s
```

- [ ] **Step 3 : Lancer la suite complète (pytest + E2E)**

```bash
docker exec lespass_django poetry run pytest tests/ -q --tb=short
```

---

## Task 10 : Vérification finale + i18n

**Files:**
- Divers fichiers .po

### Étapes

- [ ] **Step 1 : Lancer ruff sur les fichiers modifiés**

```bash
docker exec lespass_django poetry run ruff check --fix laboutik/views.py BaseBillet/models.py Administration/admin/products.py
docker exec lespass_django poetry run ruff format laboutik/views.py BaseBillet/models.py Administration/admin/products.py
```

- [ ] **Step 2 : Extraire et compiler les traductions**

```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
# Éditer les .po pour les nouvelles chaînes
docker exec lespass_django poetry run django-admin compilemessages
```

- [ ] **Step 3 : Suite complète pytest + E2E**

```bash
docker exec lespass_django poetry run pytest tests/ -q
```

Attendu : tous les tests passent, 0 régression.

- [ ] **Step 4 : Vérifier manage.py check**

```bash
docker exec lespass_django poetry run python manage.py check
```

Attendu : 0 issue.

---

## Récapitulatif des tâches

| Task | Fichiers | Tests | Risque |
|------|----------|-------|--------|
| 1. Price.non_fiduciaire | BaseBillet/models.py + migration | 4 pytest | Faible |
| 2. Fixtures enrichies | create_test_pos_data.py | Vérification manuelle | Faible |
| 3. Admin POSPriceInline | admin/products.py | 2 E2E | Faible |
| 4. _calculer_qty_partielles + _creer_lignes_articles_cascade | laboutik/views.py | 3+ pytest | Moyen |
| 5. _payer_par_nfc() refonte | laboutik/views.py | 40+ pytest | **Élevé** |
| 6. Paiement complémentaire | views.py + templates | 14 pytest | **Élevé** |
| 7. Rapports + impression | reports.py + formatters.py | 6 pytest | Faible |
| 8. Tests E2E | test_cascade_nfc.py | 8 E2E | Moyen |
| 9. Vérification finale | i18n, ruff, check | Suite complète | Faible |

**Checkpoint sécurité obligatoire** après Task 5 : vérifier l'isolation cross-tenant et l'atomicité des transactions.
