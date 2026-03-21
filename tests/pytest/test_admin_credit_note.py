"""
tests/pytest/test_admin_credit_note.py — Test emission d'avoir (credit note) via admin.
tests/pytest/test_admin_credit_note.py — Test credit note issuance via admin.

Verifie que l'action emettre_avoir cree une LigneArticle CREDIT_NOTE,
et qu'un 2e appel est bloque.

Converti depuis : tests/playwright/tests/admin/32-admin-credit-note.spec.ts
Converted from: tests/playwright/tests/admin/32-admin-credit-note.spec.ts

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_admin_credit_note.py -v
"""

import os
import sys

sys.path.insert(0, '/DjangoFiles')


import django

django.setup()

import pytest

from django_tenants.utils import schema_context

from BaseBillet.models import LigneArticle


TENANT_SCHEMA = 'lespass'


class TestAdminCreditNote:
    """Test de l'action emettre_avoir sur LigneArticle.
    / Test of the emettre_avoir action on LigneArticle."""

    def test_credit_note_create_and_duplicate_blocked(self, admin_client):
        """Emettre un avoir → credit note creee. 2e appel → bloque.
        / Issue a credit note → credit note created. 2nd call → blocked."""

        with schema_context(TENANT_SCHEMA):
            # 1. Trouver une LigneArticle VALID sans avoir existant
            # / Find a VALID LigneArticle without existing credit note
            ligne = (
                LigneArticle.objects
                .filter(status=LigneArticle.VALID)
                .exclude(credit_notes__isnull=False)
                .select_related('pricesold', 'pricesold__productsold')
                .first()
            )
            if not ligne:
                pytest.skip("Aucune LigneArticle VALID sans avoir en base — skip")

            pk = str(ligne.pk)

            # 2. Emettre l'avoir via l'URL admin
            # / Issue credit note via admin URL
            resp = admin_client.get(
                f'/admin/BaseBillet/lignearticle/{pk}/emettre_avoir/',
                follow=True,
            )
            assert resp.status_code == 200

            # 3. Verifier qu'un avoir a ete cree en base
            # / Verify a credit note was created in DB
            avoir = LigneArticle.objects.filter(
                credit_note_for=ligne,
                status=LigneArticle.CREDIT_NOTE,
            ).first()
            assert avoir is not None, "L'avoir doit exister en base"
            assert avoir.qty < 0, "La quantite de l'avoir doit etre negative"

            # 4. 2e appel → message d'erreur "already exists"
            # / 2nd call → "already exists" error message
            resp2 = admin_client.get(
                f'/admin/BaseBillet/lignearticle/{pk}/emettre_avoir/',
                follow=True,
            )
            assert resp2.status_code == 200
            html = resp2.content.decode()
            assert 'already exists' in html or 'existe' in html.lower(), (
                "Le 2e appel doit afficher un message d'erreur 'already exists'"
            )
