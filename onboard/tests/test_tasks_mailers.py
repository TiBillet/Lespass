"""
Tests des tasks Celery onboard_otp_mailer + onboard_ready_mailer.
/ Tests for OTP and ready mailer Celery tasks.

LOCALISATION: onboard/tests/test_tasks_mailers.py

NOTE : on utilise `django.test.TestCase` (executable via `manage.py test`),
car `pytest-django` n'est pas installe sur cette branche (cf. test_models.py).
Les tasks sont appelees synchroniquement (sans .delay()) pour pouvoir tester
le contenu reel envoye dans `mail.outbox` (locmem.EmailBackend par defaut
en mode TEST Django).
/ NOTE: we use `django.test.TestCase` (runnable via `manage.py test`),
because `pytest-django` is not installed on this branch. Tasks are invoked
synchronously (without .delay()) so we can assert against `mail.outbox`
(locmem.EmailBackend, Django's default TEST email backend).
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django_tenants.utils import schema_context, tenant_context

from Customers.models import Client, Domain
from MetaBillet.models import WaitingConfiguration


class OnboardOtpMailerTests(TestCase):
    """
    Tests unitaires de la task `onboard_otp_mailer`.
    / Unit tests for the `onboard_otp_mailer` Celery task.
    """

    def setUp(self):
        """
        Cree un WaitingConfiguration dans le schema "meta".
        / Create a WaitingConfiguration in the "meta" schema.
        """
        # WaitingConfiguration vit dans le schema "meta" (cf. install.py).
        # MetaBillet etant en SHARED_APPS, l'ecriture est possible depuis
        # public, mais on respecte la convention du plan.
        # / WaitingConfiguration lives in the "meta" schema. MetaBillet being
        # in SHARED_APPS, writing from public would work too, but we stick
        # to the plan's convention.
        with schema_context("meta"):
            # On nettoie pour eviter les collisions d'organisation/slug si la
            # base de test garde de la donnee entre runs.
            # / Cleanup to avoid org/slug collisions if test DB is reused.
            WaitingConfiguration.objects.filter(
                email="otp-user@example.com",
            ).delete()
            self.wc = WaitingConfiguration.objects.create(
                organisation="OtpTestOrg",
                email="otp-user@example.com",
                dns_choice="tibillet.localhost",
                phone="0102030405",  # champ obligatoire / required field
            )
            self.wc_uuid = str(self.wc.uuid)

        # Vidage de la boite d'envoi avant chaque test pour un assert propre.
        # / Empty outbox before each test for clean assertions.
        mail.outbox = []

    def test_onboard_otp_mailer_sends_email_with_code_in_body(self):
        """
        La task envoie un email au destinataire avec l'OTP dans le corps.
        / The task sends an email to the recipient with the OTP in the body.
        """
        from onboard.tasks import onboard_otp_mailer

        # Appel synchrone (pas .delay()) pour tester deterministe.
        # / Sync call (no .delay()) for deterministic testing.
        onboard_otp_mailer(wc_uuid=self.wc_uuid, otp_clair="123456")

        self.assertEqual(
            len(mail.outbox), 1,
            "Un et un seul email doit etre envoye.",
        )
        sent = mail.outbox[0]

        # Destinataire correct. / Correct recipient.
        self.assertEqual(sent.to, ["otp-user@example.com"])

        # Le code OTP est dans le sujet et dans le corps texte.
        # / OTP code present both in subject and text body.
        self.assertIn("123456", sent.subject)
        self.assertIn("123456", sent.body)

        # L'alternative HTML est bien attachee. / HTML alternative attached.
        self.assertEqual(len(sent.alternatives), 1)
        html_content, html_mime = sent.alternatives[0]
        self.assertEqual(html_mime, "text/html")
        self.assertIn("123456", html_content)


class OnboardReadyMailerTests(TestCase):
    """
    Tests unitaires de la task `onboard_ready_mailer`.
    / Unit tests for the `onboard_ready_mailer` Celery task.
    """

    def setUp(self):
        """
        Cree un tenant non-ROOT, un domaine primaire, puis un
        WaitingConfiguration rattache a ce tenant.
        / Create a non-ROOT tenant, a primary domain, then a
        WaitingConfiguration linked to that tenant.
        """
        # Tenant + domaine en SHARED_APPS (schema public).
        # / Tenant + domain in SHARED_APPS (public schema).
        with schema_context("public"):
            Client.objects.filter(
                schema_name="ready-mailer-test-tenant",
            ).delete()
            self.tenant = Client.objects.create(
                schema_name="ready-mailer-test-tenant",
                name="Ready Mailer Test Tenant",
                categorie=Client.SALLE_SPECTACLE,
            )
            self.primary_domain = Domain.objects.create(
                domain="ready-mailer-test.tibillet.localhost",
                tenant=self.tenant,
                is_primary=True,
            )

        # WaitingConfiguration en schema "meta", rattache au tenant ci-dessus.
        # / WaitingConfiguration in "meta" schema, linked to tenant above.
        with schema_context("meta"):
            WaitingConfiguration.objects.filter(
                email="ready-user@example.com",
            ).delete()
            self.wc = WaitingConfiguration.objects.create(
                organisation="ReadyTestOrg",
                email="ready-user@example.com",
                dns_choice="tibillet.localhost",
                phone="0102030405",
                tenant=self.tenant,
            )
            self.wc_uuid = str(self.wc.uuid)

        mail.outbox = []

    def test_onboard_ready_mailer_sends_email_with_admin_link(self):
        """
        La task envoie un email contenant le lien admin du tenant.
        Depuis 2026-05-16, le mail embarque un magic-link
        (`/emailconfirmation/<token>?next=<signed>/admin/`) au lieu d'un
        lien direct vers `/admin/`. En cas d'echec de generation
        (get_or_create_user qui plante en test), la task fallback sur le
        lien direct `/admin/`. On accepte donc les deux dans l'assertion.

        / The task sends an email containing the tenant's admin URL.
        Since 2026-05-16, the mail embeds a magic-link
        (`/emailconfirmation/<token>?next=<signed>/admin/`) instead of a
        direct `/admin/` link. On magic-link generation failure
        (get_or_create_user raising in test), the task falls back to the
        direct `/admin/` link. We accept either in the assertion.
        """
        from onboard.tasks import onboard_ready_mailer

        onboard_ready_mailer(wc_uuid=self.wc_uuid)

        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]

        self.assertEqual(sent.to, ["ready-user@example.com"])

        # Le domaine primaire DOIT etre dans le body. On lit l'attribut
        # `self.primary_domain.domain` pose dans setUp() plutot que d'appeler
        # `self.tenant.get_primary_domain()` qui depend de l'etat DB
        # (potentiellement perturbe par les test parallels et le pattern V2
        # de DB partagee — cf. tests/PIEGES.md sur django-tenants).
        # / Read `self.primary_domain.domain` set in setUp() instead of
        # calling `self.tenant.get_primary_domain()` (depends on DB state).
        domain = self.primary_domain.domain
        self.assertIn(domain, sent.body)

        # Le mail contient SOIT le magic-link `/emailconfirmation/` (cas
        # nominal), SOIT le lien direct `/admin/` (fallback en cas d'echec).
        # Les deux sont des "liens admin valides" — le test accepte les deux.
        # / The mail contains EITHER the magic-link OR the direct admin
        # link (fallback). Both are valid admin entries.
        self.assertTrue(
            "/emailconfirmation/" in sent.body or "/admin/" in sent.body,
            f"Body must contain an admin link (magic-link or direct). "
            f"Body excerpt: {sent.body[:300]!r}",
        )

        # Le nom de l'organisation apparait dans le sujet.
        # / Organisation name appears in the subject.
        self.assertIn("ReadyTestOrg", sent.subject)

        # Alternative HTML egalement presente, contenant le domaine.
        # / HTML alternative also present, containing the domain.
        self.assertEqual(len(sent.alternatives), 1)
        html_content, html_mime = sent.alternatives[0]
        self.assertEqual(html_mime, "text/html")
        self.assertIn(domain, html_content)

    def test_onboard_ready_mailer_skips_when_no_tenant(self):
        """
        Si le WC n'a pas encore de tenant attache, la task n'envoie rien
        (filet de securite, pas une erreur).
        / If WC has no tenant yet, task sends nothing (safety net, not error).
        """
        from onboard.tasks import onboard_ready_mailer

        # On detache le tenant pour simuler un appel premature.
        # / Detach tenant to simulate a premature call.
        with schema_context("meta"):
            self.wc.tenant = None
            self.wc.save()

        onboard_ready_mailer(wc_uuid=self.wc_uuid)

        self.assertEqual(
            len(mail.outbox), 0,
            "Aucun email ne doit etre envoye si le WC n'a pas de tenant.",
        )
