"""
Tests pytest : adhesions avec paiement Stripe (mock).
/ Pytest tests: memberships with Stripe payment (mocked).

Conversion de :
- PW 11 : anonymous-membership.spec.ts
- PW 12 : anonymous-membership-dynamic-form.spec.ts
- PW 13 : ssa-membership-tokens.spec.ts
- PW 14+43 : membership-manual-validation + stripe-payment
- PW 15 : membership-free-price.spec.ts

Stripe est mocke cote serveur : pas d'aller-retour reseau.
/ Stripe is mocked server-side: no network round-trip.
"""

import json
import random
import re
import string

import pytest


def _random_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _create_membership_product(api_client, auth_headers, name, price_name,
                                price_amount="10.00", free_price=False,
                                form_fields=None, manual_validation=False,
                                subscription_type=None):
    """Helper : cree un produit adhesion via API v2.
    / Helper: creates a membership product via API v2.

    Retourne (product_data, price_uuid).
    """
    offers = [{
        "@type": "Offer",
        "name": price_name,
        "price": price_amount,
        "priceCurrency": "EUR",
    }]
    if free_price:
        offers[0]["freePrice"] = True
    if manual_validation:
        offers[0]["additionalProperty"] = [{
            "@type": "PropertyValue",
            "name": "manualValidation",
            "value": True,
        }]
    if subscription_type:
        offers[0].setdefault("additionalProperty", []).append({
            "@type": "PropertyValue",
            "name": "subscriptionType",
            "value": subscription_type,
        })

    payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "description": f"Test mock Stripe - {name}",
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
    assert resp.status_code in (200, 201), f"Création produit échouée ({resp.status_code}): {resp.content[:300]}"
    data = resp.json()
    price_uuid = data["offers"][0]["identifier"]
    return data, price_uuid


def _submit_membership_form(api_client, price_uuid, email, firstname="Test",
                             lastname="User", custom_amount=None,
                             form_fields_data=None):
    """Helper : POST le formulaire d'adhesion comme le ferait le navigateur.
    / Helper: POST the membership form as the browser would.
    """
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
    if form_fields_data:
        post_data.update(form_fields_data)

    resp = api_client.post(
        "/memberships/",
        data=post_data,
        HTTP_REFERER="https://lespass.tibillet.localhost/memberships/",
    )
    return resp


def _simulate_stripe_return(paiement_stripe_db):
    """Simule le retour Stripe en appelant update_checkout_status() avec le mock.
    Le mock stripe.checkout.Session.retrieve retourne payment_status="paid".
    / Simulates Stripe return by calling update_checkout_status() with mock.
    """
    paiement_stripe_db.update_checkout_status()
    paiement_stripe_db.refresh_from_db()
    return paiement_stripe_db


class TestStripeMembershipSimple:
    """Adhesions simples avec mock Stripe / Simple memberships with mocked Stripe."""

    def test_anonymous_membership_paid(
        self, api_client, auth_headers, mock_stripe
    ):
        """PW 11 : adhesion anonyme payante → Stripe → Membership creee.
        / PW 11: anonymous paid membership → Stripe → Membership created.
        """
        from django_tenants.utils import schema_context
        from BaseBillet.models import Membership, Paiement_stripe

        rid = _random_id()
        email = f"test+adh{rid}@mock.test"

        # 1. Créer le produit via API
        _, price_uuid = _create_membership_product(
            api_client, auth_headers,
            name=f"Adhesion Mock {rid}",
            price_name="Annuelle",
            price_amount="20.00",
        )

        # 2. Soumettre le formulaire
        resp = _submit_membership_form(api_client, price_uuid, email)
        # Le formulaire redirige vers Stripe (302) ou renvoie une page avec redirect JS
        assert resp.status_code in (200, 302, 303), (
            f"POST /memberships/ inattendu ({resp.status_code}): {resp.content[:300]}"
        )

        # 3. Vérifier que Session.create a été appelé
        assert mock_stripe.mock_create.called, "stripe.checkout.Session.create() non appelé"

        # 4. Vérifier le Paiement_stripe créé en DB
        with schema_context("lespass"):
            paiement = Paiement_stripe.objects.filter(
                checkout_session_id_stripe="cs_test_mock_session",
            ).order_by("-datetime").first()
            assert paiement is not None, "Paiement_stripe non trouvé en DB"
            assert paiement.status == Paiement_stripe.PENDING

            # 5. Simuler le retour Stripe (mock retrieve retourne paid)
            _simulate_stripe_return(paiement)
            assert paiement.status == Paiement_stripe.PAID

            # 6. Vérifier la Membership
            membership = Membership.objects.filter(
                user__email=email,
            ).order_by("-date_added").first()
            assert membership is not None, f"Membership non trouvée pour {email}"

    def test_anonymous_membership_dynamic_form(
        self, api_client, auth_headers, mock_stripe
    ):
        """PW 12 : adhesion avec champs dynamiques (boolean + multiSelect).
        / PW 12: membership with dynamic form fields (boolean + multiSelect).
        """
        from django_tenants.utils import schema_context
        from BaseBillet.models import Membership, Paiement_stripe

        rid = _random_id()
        email = f"test+adhform{rid}@mock.test"

        # 1. Créer le produit avec form_fields
        _, price_uuid = _create_membership_product(
            api_client, auth_headers,
            name=f"Adhesion Form Mock {rid}",
            price_name="Plein tarif",
            price_amount="15.00",
            form_fields=[
                {"label": "Chantiers", "fieldType": "boolean", "required": True, "order": 1},
                {"label": "Interets", "fieldType": "multiSelect", "options": ["Art", "Sport"], "required": True, "order": 2},
            ],
        )

        # 2. Soumettre avec les champs dynamiques
        resp = _submit_membership_form(
            api_client, price_uuid, email,
            form_fields_data={
                "form__chantiers": "on",
                "form__interets": "Art",
            },
        )
        assert resp.status_code in (200, 302, 303)
        assert mock_stripe.mock_create.called

        # 3. Simuler retour Stripe + vérifier
        with schema_context("lespass"):
            paiement = Paiement_stripe.objects.filter(
                checkout_session_id_stripe="cs_test_mock_session",
            ).order_by("-datetime").first()
            assert paiement is not None
            _simulate_stripe_return(paiement)

            membership = Membership.objects.filter(
                user__email=email,
            ).order_by("-date_added").first()
            assert membership is not None

    def test_membership_free_price(
        self, api_client, auth_headers, mock_stripe
    ):
        """PW 15 : adhesion prix libre → montant custom → Stripe.
        / PW 15: free price membership → custom amount → Stripe.
        """
        from django_tenants.utils import schema_context
        from BaseBillet.models import Membership, Paiement_stripe

        rid = _random_id()
        email = f"test+free{rid}@mock.test"

        # 1. Créer produit prix libre (min 5€)
        _, price_uuid = _create_membership_product(
            api_client, auth_headers,
            name=f"Adhesion Prix Libre {rid}",
            price_name="Prix Libre",
            price_amount="5.00",
            free_price=True,
        )

        # 2. Soumettre avec montant custom 15€
        resp = _submit_membership_form(
            api_client, price_uuid, email,
            custom_amount="15.00",
        )
        assert resp.status_code in (200, 302, 303)
        assert mock_stripe.mock_create.called

        # 3. Simuler retour + vérifier contribution_value
        with schema_context("lespass"):
            paiement = Paiement_stripe.objects.filter(
                checkout_session_id_stripe="cs_test_mock_session",
            ).order_by("-datetime").first()
            assert paiement is not None
            _simulate_stripe_return(paiement)

            membership = Membership.objects.filter(
                user__email=email,
            ).order_by("-date_added").first()
            assert membership is not None
            # Le montant custom doit être 15.00
            assert membership.contribution_value == 15

    def test_membership_manual_validation_stripe(
        self, api_client, auth_headers, admin_client, mock_stripe, tenant
    ):
        """PW 14+43 : validation manuelle → lien paiement → Stripe.
        / PW 14+43: manual validation → payment link → Stripe.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Membership, Paiement_stripe

        rid = _random_id()
        email = f"test+manual{rid}@mock.test"

        # 1. Créer produit avec validation manuelle
        _, price_uuid = _create_membership_product(
            api_client, auth_headers,
            name=f"Adhesion Manuelle {rid}",
            price_name=f"Annuel {rid}",
            price_amount="20.00",
            manual_validation=True,
            subscription_type="Y",
        )

        # 2. Créer l'adhésion en ADMIN_WAITING via API
        payload = {
            "@context": "https://schema.org",
            "@type": "ProgramMembership",
            "member": {
                "@type": "Person",
                "email": email,
                "givenName": "Manual",
                "familyName": "Test",
            },
            "membershipPlan": {
                "@type": "Offer",
                "identifier": price_uuid,
            },
            "additionalProperty": [{
                "@type": "PropertyValue",
                "name": "paymentMode",
                "value": "FREE",
            }, {
                "@type": "PropertyValue",
                "name": "status",
                "value": "AW",
            }],
        }
        resp = api_client.post(
            "/api/v2/memberships/",
            data=json.dumps(payload),
            content_type="application/json",
            **auth_headers,
        )
        assert resp.status_code in (200, 201), (
            f"Création membership échouée ({resp.status_code}): {resp.content[:300]}"
        )

        # 3. Valider en admin (admin_accept) — tenant_context pour eviter FakeTenant
        with tenant_context(tenant):
            membership = Membership.objects.filter(
                user__email=email,
            ).order_by("-date_added").first()
            assert membership is not None
            assert membership.status == "AW"

            # Simuler l'admin_accept
            membership.status = "AV"
            membership.save()

            # 4. Appeler directement get_checkout_stripe() qui cree LigneArticle + Paiement_stripe
            # tenant_context requis car get_checkout_stripe accede a connection.tenant.uuid
            from BaseBillet.validators import MembershipValidator
            checkout_url = MembershipValidator.get_checkout_stripe(membership)
            assert checkout_url is not None, "get_checkout_stripe a retourné None"
            assert mock_stripe.mock_create.called

            # 5. Simuler retour Stripe
            paiement = Paiement_stripe.objects.filter(
                checkout_session_id_stripe="cs_test_mock_session",
            ).order_by("-datetime").first()
            assert paiement is not None
            _simulate_stripe_return(paiement)

    def test_ssa_membership_tokens(
        self, api_client, auth_headers, mock_stripe
    ):
        """PW 13 : adhesion SSA → Stripe → tokens Fedow credites.
        / PW 13: SSA membership → Stripe → Fedow tokens credited.

        Note : ce test verifie que le flow de paiement fonctionne.
        La verification des tokens Fedow depend de la config SSA en base dev.
        Si le produit SSA n'existe pas, le test est skip.
        """
        from django_tenants.utils import schema_context
        from BaseBillet.models import Product, Membership, Paiement_stripe

        with schema_context("lespass"):
            # Chercher un produit SSA existant en base dev
            ssa_product = Product.objects.filter(
                categorie_article=Product.ADHESION,
                name__icontains="sécurité sociale alimentaire",
            ).first()

        if not ssa_product:
            pytest.skip("Produit SSA introuvable en base dev")

        rid = _random_id()
        email = f"test+ssa{rid}@mock.test"

        with schema_context("lespass"):
            # Trouver un prix publié pour ce produit
            price = ssa_product.prices.filter(publish=True).first()
            if not price:
                pytest.skip("Aucun prix publié pour le produit SSA")

            price_uuid = str(price.uuid)

        # Soumettre le formulaire SSA
        post_data = {
            "price": price_uuid,
            "email": email,
            "firstname": "SSA",
            "lastname": "TestMock",
            "acknowledge": "on",
            "newsletter": "false",
        }
        # Si prix libre, ajouter un montant
        with schema_context("lespass"):
            if price.free_price:
                post_data[f"custom_amount_{price_uuid}"] = "10"
            # Remplir les champs dynamiques obligatoires
            for field in ssa_product.form_fields.filter(required=True):
                post_data[f"form__{field.name}"] = "TestSSA"

        resp = api_client.post("/memberships/", data=post_data)
        assert resp.status_code in (200, 302, 303)

        # Simuler retour Stripe
        with schema_context("lespass"):
            paiement = Paiement_stripe.objects.filter(
                checkout_session_id_stripe="cs_test_mock_session",
            ).order_by("-datetime").first()
            if paiement:
                _simulate_stripe_return(paiement)

            membership = Membership.objects.filter(
                user__email=email,
            ).order_by("-date_added").first()
            assert membership is not None, f"Membership SSA non trouvée pour {email}"
