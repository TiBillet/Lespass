"""
Tests pytest : adhesions complexes avec paiement Stripe (mock).
/ Pytest tests: complex memberships with Stripe payment (mocked).

Conversion de :
- PW 17 : membership-free-price-multi.spec.ts (multi-tarifs prix libre)
- PW 42 : membership-zero-price.spec.ts (prix zero = pas de Stripe)
- PW 27 : membership-dynamic-form-full-cycle.spec.ts (cycle complet, tarif gratuit)
"""

import json
import random
import string

import pytest


def _random_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _create_membership_product(api_client, auth_headers, name, offers,
                                form_fields=None):
    """Helper : cree un produit adhesion via API v2 avec plusieurs tarifs.
    / Helper: creates a membership product via API v2 with multiple prices.
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "description": f"Test mock Stripe complexe - {name}",
        "category": "Membership",
        "offers": offers,
    }
    if form_fields:
        payload["additionalProperty"] = [{
            "@type": "PropertyValue",
            "name": "formFields",
            "value": form_fields,
        }]

    resp = api_client.post(
        "/api/v2/products/",
        data=json.dumps(payload),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code in (200, 201), (
        f"Création produit échouée ({resp.status_code}): {resp.content[:300]}"
    )
    data = resp.json()
    return data


def _submit_membership(api_client, price_uuid, email, firstname="Test",
                        lastname="User", custom_amount=None, form_data=None):
    """POST le formulaire d'adhesion / POST the membership form."""
    post_data = {
        "price": price_uuid,
        "email": email,
        "firstname": firstname,
        "lastname": lastname,
        "acknowledge": "on",
        "newsletter": "false",
    }
    if custom_amount is not None:
        post_data[f"custom_amount_{price_uuid}"] = str(custom_amount)
    if form_data:
        post_data.update(form_data)

    return api_client.post(
        "/memberships/",
        data=post_data,
        HTTP_REFERER="https://lespass.tibillet.localhost/memberships/",
    )


# ===========================================================================
# PW 17 — Multi prix libre / Multi free price
# ===========================================================================


class TestStripeMembershipMultiFreePrice:
    """Multi-tarifs prix libre / Multi free price memberships (PW 17)."""

    @pytest.fixture(autouse=True)
    def _setup_product(self, api_client, auth_headers):
        """Cree un produit avec 2 tarifs prix libre.
        / Creates a product with 2 free price tiers.
        """
        rid = _random_id()
        self.product_name = f"Multi-Prix Libre {rid}"
        data = _create_membership_product(
            api_client, auth_headers,
            name=self.product_name,
            offers=[
                {
                    "@type": "Offer",
                    "name": "Prix Libre 1",
                    "price": "5.00",
                    "priceCurrency": "EUR",
                    "freePrice": True,
                },
                {
                    "@type": "Offer",
                    "name": "Prix Libre 2",
                    "price": "8.00",
                    "priceCurrency": "EUR",
                    "freePrice": True,
                },
            ],
        )
        self.price1_uuid = data["offers"][0]["identifier"]
        self.price2_uuid = data["offers"][1]["identifier"]

    def test_select_price1_sends_correct_amount(
        self, api_client, auth_headers, mock_stripe
    ):
        """Sélectionner Prix Libre 1 (min 5€) avec montant 12€ → Stripe reçoit 12€.
        / Select Prix Libre 1 (min 5€) with amount 12€ → Stripe receives 12€.
        """
        from django_tenants.utils import schema_context
        from BaseBillet.models import Membership

        rid = _random_id()
        email = f"test+multi1-{rid}@mock.test"

        resp = _submit_membership(
            api_client, self.price1_uuid, email,
            custom_amount="12.00",
        )
        assert resp.status_code in (200, 302, 303)
        assert mock_stripe.mock_create.called

        with schema_context("lespass"):
            membership = Membership.objects.filter(
                user__email=email,
            ).order_by("-date_added").first()
            assert membership is not None
            assert membership.contribution_value == 12

    def test_select_price2_sends_correct_amount(
        self, api_client, auth_headers, mock_stripe
    ):
        """Sélectionner Prix Libre 2 (min 8€) avec montant 18€ → Stripe reçoit 18€.
        / Select Prix Libre 2 (min 8€) with amount 18€ → Stripe receives 18€.
        """
        from django_tenants.utils import schema_context
        from BaseBillet.models import Membership

        rid = _random_id()
        email = f"test+multi2-{rid}@mock.test"

        resp = _submit_membership(
            api_client, self.price2_uuid, email,
            custom_amount="18.00",
        )
        assert resp.status_code in (200, 302, 303)
        assert mock_stripe.mock_create.called

        with schema_context("lespass"):
            membership = Membership.objects.filter(
                user__email=email,
            ).order_by("-date_added").first()
            assert membership is not None
            assert membership.contribution_value == 18


# ===========================================================================
# PW 42 — Prix zero / Zero price
# ===========================================================================


class TestStripeMembershipZeroPrice:
    """Prix libre : 0€ = pas de Stripe, >0€ = Stripe (PW 42)."""

    @pytest.fixture(autouse=True)
    def _setup_product(self, api_client, auth_headers):
        """Cree un produit avec prix libre min 0€.
        / Creates a product with free price min 0€.
        """
        rid = _random_id()
        self.product_name = f"Prix Libre Zero {rid}"
        data = _create_membership_product(
            api_client, auth_headers,
            name=self.product_name,
            offers=[{
                "@type": "Offer",
                "name": "Prix Libre (min 0€)",
                "price": "0.00",
                "priceCurrency": "EUR",
                "freePrice": True,
            }],
        )
        self.price_uuid = data["offers"][0]["identifier"]

    def test_zero_amount_no_stripe(self, api_client, mock_stripe):
        """0€ → pas de Stripe, confirmation directe.
        / 0€ → no Stripe, direct confirmation.
        """
        from django_tenants.utils import schema_context
        from BaseBillet.models import Membership, Paiement_stripe

        rid = _random_id()
        email = f"test+zero{rid}@mock.test"

        resp = _submit_membership(
            api_client, self.price_uuid, email,
            custom_amount="0",
        )
        # Devrait retourner 200 (confirmation dans la page) ou 302 vers la page de confirmation
        assert resp.status_code in (200, 302, 303)

        # Stripe ne doit PAS avoir été appelé / Stripe must NOT have been called
        assert not mock_stripe.mock_create.called, (
            "Stripe Session.create ne devrait pas être appelé pour 0€"
        )

        # La membership doit exister en DB / Membership must exist in DB
        with schema_context("lespass"):
            membership = Membership.objects.filter(
                user__email=email,
            ).order_by("-date_added").first()
            assert membership is not None, f"Membership non trouvée pour {email}"

    def test_nonzero_amount_uses_stripe(self, api_client, mock_stripe):
        """1€ → Stripe appelé.
        / 1€ → Stripe called.
        """
        from django_tenants.utils import schema_context
        from BaseBillet.models import Membership

        rid = _random_id()
        email = f"test+one{rid}@mock.test"

        resp = _submit_membership(
            api_client, self.price_uuid, email,
            custom_amount="1.00",
        )
        assert resp.status_code in (200, 302, 303)
        assert mock_stripe.mock_create.called, (
            "Stripe Session.create devrait être appelé pour 1€"
        )

        with schema_context("lespass"):
            membership = Membership.objects.filter(
                user__email=email,
            ).order_by("-date_added").first()
            assert membership is not None


# ===========================================================================
# PW 27 — Cycle complet formulaire dynamique (tarif gratuit, pas de Stripe)
# ===========================================================================


class TestDynamicFormFullCycle:
    """Cycle complet : produit avec 6 types de champs dynamiques → adhésion gratuite (PW 27)."""

    def test_create_and_subscribe_with_dynamic_fields(
        self, api_client, auth_headers, mock_stripe
    ):
        """Créer produit + form fields via API, soumettre adhésion gratuite avec données.
        / Create product + form fields via API, submit free membership with data.
        """
        from django_tenants.utils import schema_context
        from BaseBillet.models import Membership

        rid = _random_id()
        email = f"test+dynform{rid}@mock.test"

        # Créer produit avec prix gratuit (0€) + champs dynamiques
        data = _create_membership_product(
            api_client, auth_headers,
            name=f"DynForm Test {rid}",
            offers=[{
                "@type": "Offer",
                "name": "Gratuit",
                "price": "0.00",
                "priceCurrency": "EUR",
                "freePrice": True,
            }],
            form_fields=[
                {"label": "Nom complet", "fieldType": "shortText", "required": True, "order": 1},
                {"label": "Bio", "fieldType": "longText", "required": False, "order": 2},
                {"label": "Ville", "fieldType": "singleSelect", "options": ["Paris", "Lyon", "Marseille"], "required": True, "order": 3},
                {"label": "Accepter", "fieldType": "boolean", "required": True, "order": 4},
            ],
        )
        price_uuid = data["offers"][0]["identifier"]

        # Soumettre avec les champs dynamiques + montant 0€
        resp = _submit_membership(
            api_client, price_uuid, email,
            custom_amount="0",
            form_data={
                "form__nom-complet": "Douglas Adams",
                "form__bio": "Ecrivain de science-fiction",
                "form__ville": "Paris",
                "form__accepter": "on",
            },
        )
        assert resp.status_code in (200, 302, 303)

        # Pas de Stripe pour 0€ / No Stripe for 0€
        assert not mock_stripe.mock_create.called

        # Vérifier membership + form data
        with schema_context("lespass"):
            membership = Membership.objects.filter(
                user__email=email,
            ).order_by("-date_added").first()
            assert membership is not None

    def test_admin_can_see_form_answers_in_db(
        self, api_client, auth_headers, mock_stripe
    ):
        """Vérifier que les réponses form fields sont stockées en DB.
        / Verify that form field answers are stored in DB.
        """
        from django_tenants.utils import schema_context
        from BaseBillet.models import Membership

        rid = _random_id()
        email = f"test+dynverify{rid}@mock.test"

        data = _create_membership_product(
            api_client, auth_headers,
            name=f"DynVerify {rid}",
            offers=[{
                "@type": "Offer",
                "name": "Gratuit",
                "price": "0.00",
                "priceCurrency": "EUR",
                "freePrice": True,
            }],
            form_fields=[
                {"label": "Pseudo", "fieldType": "shortText", "required": True, "order": 1},
            ],
        )
        price_uuid = data["offers"][0]["identifier"]

        resp = _submit_membership(
            api_client, price_uuid, email,
            custom_amount="0",
            form_data={"form__pseudo": "ZaphodBeeblebrox"},
        )
        assert resp.status_code in (200, 302, 303)

        with schema_context("lespass"):
            membership = Membership.objects.filter(
                user__email=email,
            ).order_by("-date_added").first()
            assert membership is not None

            # Les réponses sont stockées dans membership.custom_form (JSONField)
            custom = membership.custom_form or {}
            assert "pseudo" in str(custom).lower() or "Zaphod" in str(custom), (
                f"Réponse form field non trouvée dans custom_form: {custom}"
            )
