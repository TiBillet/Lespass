"""
Tests du modele OnboardInvitation.
/ Tests for OnboardInvitation model.

LOCALISATION: onboard/tests/test_models.py

NOTE : le plan initial prevoyait pytest + pytest-django + une FK federation
vers `fedow_core.Federation`. Sur la branche `main-wizard` :
  - `pytest-django` n'est pas installe (la suite pytest existante fait des
    tests d'integration HTTP via `requests`, pas du Django ORM).
  - L'app `fedow_core` n'existe pas encore (mono-repo V2 pas merge sur cette
    branche). Le champ `federation` du modele est commente avec un TODO.
On utilise donc `django.test.TestCase` (executable via `manage.py test`)
et on cree tenant + user dans setUp().
/ NOTE: the original plan used pytest + pytest-django + a federation FK to
`fedow_core.Federation`. On the `main-wizard` branch, neither is available,
so we use `django.test.TestCase` and create tenant + user in setUp().
The two tests below keep the same semantics as the plan : auto-generated
unique code + `is_valid()` honors `used_at` and `expires_at`.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django_tenants.utils import schema_context, tenant_context

from Customers.models import Client, Domain


class OnboardInvitationModelTests(TestCase):
    """
    Tests unitaires du modele OnboardInvitation.
    / Unit tests for the OnboardInvitation model.
    """

    def setUp(self):
        """
        Cree un tenant non-ROOT + un utilisateur pour les FK.
        / Create a non-ROOT tenant + a user for the FKs.
        """
        # Travail dans le schema public car OnboardInvitation est en SHARED_APPS.
        # / Work in the public schema since OnboardInvitation is in SHARED_APPS.
        with schema_context('public'):
            Client.objects.filter(schema_name='onboard-test-tenant').delete()
            self.tenant = Client.objects.create(
                schema_name='onboard-test-tenant',
                name='Onboard Test Tenant',
                categorie=Client.SALLE_SPECTACLE,
            )
            Domain.objects.create(
                domain='onboard-test.tibillet.localhost',
                tenant=self.tenant,
                is_primary=True,
            )

            UserModel = get_user_model()
            with tenant_context(self.tenant):
                self.user = UserModel.objects.create(
                    email='onboard-inviter@example.com',
                    username='onboard-inviter@example.com',
                    email_valid=True,
                )

    def test_invitation_code_unique_and_auto_generated(self):
        """
        Une invitation cree un code unique automatiquement si pas fourni.
        / An invitation gets a unique auto-generated code.
        """
        from onboard.models import OnboardInvitation

        inv = OnboardInvitation.objects.create(
            invited_by_user=self.user,
            invited_by_tenant=self.tenant,
        )

        # Le code est genere automatiquement, non vide, suffisamment long.
        # / Code auto-generated, non-empty, long enough.
        self.assertTrue(inv.code, "Le code d'invitation doit etre non vide.")
        self.assertGreaterEqual(len(inv.code), 8)
        # L'expiration par defaut est ~30 jours dans le futur.
        # / Default expiry is ~30 days in the future.
        self.assertGreater(
            inv.expires_at,
            timezone.now() + timedelta(days=29),
        )
        # used_at non renseigne a la creation.
        # / used_at is None on creation.
        self.assertIsNone(inv.used_at)

    def test_invitation_is_valid_method(self):
        """
        Une invitation expiree ou deja utilisee est marquee invalide.
        / An expired or already used invitation is invalid.
        """
        from onboard.models import OnboardInvitation

        # 1) Invitation fraiche -> valide. / Fresh invitation -> valid.
        valide = OnboardInvitation.objects.create(
            invited_by_user=self.user,
            invited_by_tenant=self.tenant,
        )
        self.assertTrue(valide.is_valid())

        # 2) Marquee comme utilisee -> invalide. / Marked as used -> invalid.
        valide.used_at = timezone.now()
        valide.save()
        self.assertFalse(valide.is_valid())

        # 3) Date d'expiration dans le passe -> invalide.
        # / Expiry in the past -> invalid.
        perimee = OnboardInvitation.objects.create(
            invited_by_user=self.user,
            invited_by_tenant=self.tenant,
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(perimee.is_valid())
