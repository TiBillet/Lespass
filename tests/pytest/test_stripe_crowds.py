"""
Tests pytest : contributions crowds avec paiement Stripe (mock).
/ Pytest tests: crowds contributions with Stripe payment (mocked).

Conversion de PW 44 : crowds-contribution-stripe.spec.ts
"""

import json
import random
import string

import pytest


def _random_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


class TestCrowdsContributionStripe:
    """Contributions crowds avec Stripe / Crowds contributions with Stripe (PW 44)."""

    def test_anonymous_contribution_blocked(self, api_client):
        """Un utilisateur anonyme ne peut pas contribuer (pas authentifié).
        / An anonymous user cannot contribute (not authenticated).
        """
        from django_tenants.utils import schema_context
        from crowds.models import Initiative

        with schema_context("lespass"):
            initiative = Initiative.objects.first()

        if not initiative:
            pytest.skip("Aucune initiative crowds en base dev")

        # POST en anonyme (pas de login)
        resp = api_client.post(
            f"/crowd/{initiative.pk}/contribute/",
            data=json.dumps({
                "amount": 1500,
                "contributor_name": "Anonyme",
                "description": "Test anonyme",
            }),
            content_type="application/json",
        )
        # La vue retourne 401 pour un utilisateur non authentifié
        # ou un HTML sans création de contribution
        # Vérifier qu'aucune contribution n'a été créée
        with schema_context("lespass"):
            from crowds.models import Contribution
            contrib = Contribution.objects.filter(
                contributor_name="Anonyme",
                description="Test anonyme",
            ).first()
            assert contrib is None, "Une contribution a été créée pour un anonyme — bug"

    def test_direct_debit_creates_stripe_session(
        self, api_client, admin_user, admin_client, mock_stripe
    ):
        """Contribution avec direct_debit=True → Stripe Session créée.
        / Contribution with direct_debit=True → Stripe Session created.
        """
        from django_tenants.utils import schema_context
        from crowds.models import Initiative, Contribution
        from BaseBillet.models import LigneArticle

        with schema_context("lespass"):
            initiative = Initiative.objects.first()

        if not initiative:
            pytest.skip("Aucune initiative crowds en base dev")

        # Activer direct_debit sur l'initiative
        with schema_context("lespass"):
            initiative.direct_debit = True
            initiative.save(update_fields=["direct_debit"])

        rid = _random_id()
        contributor_name = f"Contrib Stripe {rid}"

        # POST en tant qu'admin authentifié
        resp = admin_client.post(
            f"/crowd/{initiative.pk}/contribute/",
            data=json.dumps({
                "amount": 1500,
                "contributor_name": contributor_name,
                "description": f"Test contribution Stripe {rid}",
            }),
            content_type="application/json",
        )
        # La vue retourne du JSON avec stripe_url quand direct_debit=True
        assert resp.status_code == 200, (
            f"POST contribute inattendu ({resp.status_code}): {resp.content[:300]}"
        )

        # Vérifier que Stripe a été appelé
        assert mock_stripe.mock_create.called, (
            "stripe.checkout.Session.create devrait être appelé pour direct_debit"
        )

        # Vérifier la Contribution en DB
        with schema_context("lespass"):
            contrib = Contribution.objects.filter(
                contributor_name=contributor_name,
            ).first()
            assert contrib is not None, f"Contribution non trouvée: {contributor_name}"
            assert contrib.amount == 1500

            # Vérifier la LigneArticle créée
            ligne = LigneArticle.objects.filter(
                amount=1500,
                sale_origin="LP",
            ).order_by("-datetime").first()
            assert ligne is not None, "LigneArticle non trouvée pour la contribution"

            # Remettre direct_debit à False / Reset direct_debit
            initiative.direct_debit = False
            initiative.save(update_fields=["direct_debit"])
