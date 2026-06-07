"""
Tests du formulaire event unifié (CHANTIER-03 / EVENT_WIZARD).
/ Tests for the unified event wizard.

LOCALISATION : tests/pytest/test_event_wizard_unifie.py
Réutilise la base de dev (schema lespass) comme test_event_wizard_public.
"""

import io
import uuid as uuidlib

import pytest

from Customers.models import Client


@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de base de test).
    # / Reuse dev DB (no test DB creation).
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()


def _vraie_image_jpeg():
    """Petite vraie image JPEG (PIL) pour que StdImageField génère ses variations."""
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), (0, 100, 200)).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.mark.django_db
def test_attacher_image_brouillon_migre_vers_images_et_nettoie_le_temp():
    """
    Fix bug #1 : l'image temp du brouillon doit être MIGRÉE vers images/ (et plus
    rester dans event_wizard_drafts/), puis le temp supprimé.
    """
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    from django_tenants.utils import tenant_context
    from BaseBillet.views import _attacher_image_brouillon
    from BaseBillet.models import Event

    lespass = Client.objects.get(schema_name="lespass")
    with tenant_context(lespass):
        chemin_temp = f"event_wizard_drafts/test/{uuidlib.uuid4().hex}.jpg"
        default_storage.save(chemin_temp, ContentFile(_vraie_image_jpeg()))
        assert default_storage.exists(chemin_temp)

        # Event transient (on ne sauve pas en DB : on teste juste l'attachement image).
        # / Transient Event (no DB save: we only test the image attachment).
        event = Event(name="Test image wizard")
        _attacher_image_brouillon(event, {"image": chemin_temp})

        # L'image pointe vers images/ (vrai fichier), pas vers le dossier temp.
        # / Image points to images/ (real file), not the temp draft folder.
        assert event.img.name.startswith("images/"), event.img.name
        assert default_storage.exists(event.img.name)
        # Le fichier temporaire a été supprimé.
        # / The temp file was deleted.
        assert not default_storage.exists(chemin_temp)

        # Cleanup du fichier créé par le test.
        default_storage.delete(event.img.name)


@pytest.mark.django_db
def test_attacher_image_brouillon_sans_image_ne_fait_rien():
    """Brouillon sans image -> event.img reste vide, pas d'erreur."""
    from django_tenants.utils import tenant_context
    from BaseBillet.views import _attacher_image_brouillon
    from BaseBillet.models import Event

    lespass = Client.objects.get(schema_name="lespass")
    with tenant_context(lespass):
        event = Event(name="Sans image")
        _attacher_image_brouillon(event, {})  # pas de cle "image"
        assert not event.img


def _draft_minimal(nom, tags=""):
    from django.utils import timezone
    return {
        "name": nom,
        "datetime": (timezone.now() + timezone.timedelta(days=10)).isoformat(),
        "long_description": "",
        "tags": tags,
        "jauge_max": None,
    }


@pytest.mark.django_db
def test_creer_event_staff_cree_event_publie():
    """est_staff=True -> event publie (is_proposal=False)."""
    from django.contrib.auth.models import AnonymousUser
    from django_tenants.utils import tenant_context
    from BaseBillet.views import _creer_event_depuis_brouillon
    from BaseBillet.models import Event, PostalAddress

    lespass = Client.objects.get(schema_name="lespass")
    with tenant_context(lespass):
        pa = PostalAddress.objects.first()
        event = _creer_event_depuis_brouillon(
            _draft_minimal("Staff publie test"), pa, AnonymousUser(), est_staff=True)
        try:
            assert event.published is True
            assert event.is_proposal is False
        finally:
            Event.objects.filter(pk=event.pk).delete()


@pytest.mark.django_db
def test_creer_event_public_est_proposition_avec_tag_auto():
    """est_staff=False -> proposition (is_proposal=True) + tag_auto_proposition applique."""
    from django.contrib.auth.models import AnonymousUser
    from django_tenants.utils import tenant_context
    from BaseBillet.views import _creer_event_depuis_brouillon
    from BaseBillet.models import Event, PostalAddress, Tag, FederationConfiguration

    lespass = Client.objects.get(schema_name="lespass")
    with tenant_context(lespass):
        pa = PostalAddress.objects.first()
        tag_auto, _created = Tag.objects.get_or_create(name="Propose-auto-test")
        federation_config = FederationConfiguration.get_solo()
        ancien_tag_id = federation_config.tag_auto_proposition_id
        federation_config.tag_auto_proposition = tag_auto
        federation_config.save()
        try:
            event = _creer_event_depuis_brouillon(
                _draft_minimal("Public proposition test"), pa, AnonymousUser(), est_staff=False)
            assert event.published is False
            assert event.is_proposal is True
            assert tag_auto in event.tag.all()
            Event.objects.filter(pk=event.pk).delete()
        finally:
            federation_config.tag_auto_proposition_id = ancien_tag_id
            federation_config.save()


@pytest.mark.django_db
def test_proposition_non_staff_applique_la_jauge():
    """
    Jauge pour tous : un proposeur non-staff qui renseigne une jauge la voit
    appliquee (jauge_max + show_gauge=True + produit FREERES), tout en restant
    une proposition moderee. Sans jauge -> defaut intact, pas de billetterie.
    / Gauge for everyone: a non-staff proposer's gauge is applied (jauge_max +
    show_gauge + FREERES product) while staying a moderated proposal.
    """
    from django.contrib.auth.models import AnonymousUser
    from django_tenants.utils import tenant_context
    from BaseBillet.views import _creer_event_depuis_brouillon
    from BaseBillet.models import Event, PostalAddress, Product

    lespass = Client.objects.get(schema_name="lespass")
    with tenant_context(lespass):
        pa = PostalAddress.objects.first()
        free_res = Product.objects.filter(
            categorie_article=Product.FREERES, publish=True, archive=False).first()

        # Avec jauge -> appliquee + billetterie de reservation gratuite.
        # / With a gauge -> applied + free-reservation product.
        draft = _draft_minimal("Non-staff jauge test")
        draft["jauge_max"] = 30
        event = _creer_event_depuis_brouillon(draft, pa, AnonymousUser(), est_staff=False)
        try:
            assert event.jauge_max == 30
            assert event.show_gauge is True
            assert event.is_proposal is True  # reste une proposition moderee
            if free_res:
                assert free_res in event.products.all()
        finally:
            Event.objects.filter(pk=event.pk).delete()

        # Sans jauge -> defaut du modele intact, aucune billetterie greffee.
        # / No gauge -> model default untouched, no product attached.
        event2 = _creer_event_depuis_brouillon(
            _draft_minimal("Non-staff sans jauge test"), pa, AnonymousUser(), est_staff=False)
        try:
            assert event2.show_gauge is False
            assert event2.products.count() == 0
        finally:
            Event.objects.filter(pk=event2.pk).delete()


@pytest.mark.django_db
def test_tags_public_uniquement_existants_pas_de_creation():
    """Public : un tag inexistant n'est PAS cree ; un tag existant est applique."""
    from django.contrib.auth.models import AnonymousUser
    from django_tenants.utils import tenant_context
    from BaseBillet.views import _creer_event_depuis_brouillon
    from BaseBillet.models import Event, PostalAddress, Tag

    lespass = Client.objects.get(schema_name="lespass")
    with tenant_context(lespass):
        pa = PostalAddress.objects.first()
        tag_existant, _created = Tag.objects.get_or_create(name="TagExistantTest")
        nom_inexistant = "TagInexistantZZZ999"
        Tag.objects.filter(name=nom_inexistant).delete()
        nb_tags_avant = Tag.objects.count()

        event = _creer_event_depuis_brouillon(
            _draft_minimal("Public tags test", tags=f"TagExistantTest, {nom_inexistant}"),
            pa, AnonymousUser(), est_staff=False)
        try:
            # Le tag inexistant n'a pas ete cree (anti-spam public).
            assert Tag.objects.count() == nb_tags_avant
            assert not Tag.objects.filter(name=nom_inexistant).exists()
            # Le tag existant est applique.
            assert tag_existant in event.tag.all()
        finally:
            Event.objects.filter(pk=event.pk).delete()


@pytest.mark.django_db
def test_garde_acces_anonyme_selon_config():
    """Anonyme + module ON : refuse si anonyme OFF (redirect login), autorise si anonyme ON."""
    from django.test.client import Client as DjangoClient
    from django.urls import reverse
    from django_tenants.utils import tenant_context
    from BaseBillet.models import FederationConfiguration

    lespass = Client.objects.get(schema_name="lespass")
    domain = lespass.domains.first()
    http = DjangoClient(HTTP_HOST=domain.domain)  # client anonyme

    with tenant_context(lespass):
        federation_config = FederationConfiguration.get_solo()
        module_avant = federation_config.module_agenda_participatif
        anonyme_avant = federation_config.proposition_anonyme_autorisee
        federation_config.module_agenda_participatif = True
        federation_config.proposition_anonyme_autorisee = False
        federation_config.save()
        try:
            # Anonyme non autorise -> redirige vers la connexion.
            resp = http.get(reverse("event-wizard-place"))
            assert resp.status_code == 302

            # Anonyme autorise -> acces OK (200).
            federation_config.proposition_anonyme_autorisee = True
            federation_config.save()
            resp2 = http.get(reverse("event-wizard-place"))
            assert resp2.status_code == 200
        finally:
            federation_config.module_agenda_participatif = module_avant
            federation_config.proposition_anonyme_autorisee = anonyme_avant
            federation_config.save()


@pytest.mark.django_db
def test_proposition_anonyme_cree_user_non_valide_et_le_lie():
    """
    Lot B : un proposeur anonyme -> get_or_create_user(email, send_mail=False)
    cree un compte NON valide (email_valid=False, inactif), SANS OTP, et l'event
    est lie a ce compte (created_by) en restant une proposition moderee.
    / Anonymous proposer -> account created but not validated, no OTP, event
    linked via created_by and kept as a moderated proposal.
    """
    from django_tenants.utils import tenant_context
    from BaseBillet.views import _creer_event_depuis_brouillon
    from BaseBillet.models import Event, PostalAddress
    from AuthBillet.utils import get_or_create_user

    lespass = Client.objects.get(schema_name="lespass")
    email = f"anon-wizard-{uuidlib.uuid4().hex[:8]}@example.org"
    with tenant_context(lespass):
        pa = PostalAddress.objects.first()
        user = get_or_create_user(email, send_mail=False)
        try:
            # Compte cree mais NON valide : la personne validera plus tard.
            # / Account created but NOT validated: the person will validate later.
            assert user is not None
            assert user.email_valid is False
            assert user.is_active is False

            event = _creer_event_depuis_brouillon(
                _draft_minimal("Anon proposition test"), pa, user, est_staff=False)
            # L'event est lie au compte et reste une proposition moderee.
            # / Event linked to the account and kept as a moderated proposal.
            assert event.created_by == user
            assert event.is_proposal is True
            assert event.published is False
        finally:
            Event.objects.filter(created_by=user).delete()
            user.delete()


@pytest.mark.django_db
def test_wizard_map_get_sans_prefill_se_rend_sans_erreur():
    """
    Regression : GET /event/wizard/map/ pour un nouveau lieu saisi A LA MAIN
    (nom en session, AUCUNE fiche Tiers-Lieux choisie) doit renvoyer 200.

    Avant le fix, `_form_carte.html` levait `VariableDoesNotExist` : `prefill`
    etait un dict vide et `valeur|default:prefill.latitude` ne tolere pas une
    cle absente quand elle est resolue comme ARGUMENT de filtre. La vue garantit
    desormais toutes les cles du prefill (vides -> le widget bascule sur Nominatim).
    / Regression: GET map for a hand-typed new place must return 200 (no TL prefill
    in session). The view now guarantees all prefill keys.
    """
    from django.test.client import Client as DjangoClient
    from django.urls import reverse
    from django_tenants.utils import tenant_context
    from BaseBillet.models import FederationConfiguration

    lespass = Client.objects.get(schema_name="lespass")
    domain = lespass.domains.first()
    http = DjangoClient(HTTP_HOST=domain.domain)  # client anonyme

    with tenant_context(lespass):
        federation_config = FederationConfiguration.get_solo()
        module_avant = federation_config.module_agenda_participatif
        anonyme_avant = federation_config.proposition_anonyme_autorisee
        federation_config.module_agenda_participatif = True
        federation_config.proposition_anonyme_autorisee = True
        federation_config.save()
    try:
        # Nouveau lieu saisi a la main : nom en session, pas de prefill Tiers-Lieux.
        # / Hand-typed new place: name in session, no TL prefill.
        session = http.session
        session["event_wizard_new_address_name"] = "Lieu Sans Prefill Test"
        session.pop("event_wizard_tierslieux_prefill", None)
        session.pop("event_wizard_tierslieux_adresse_recherche", None)
        session.save()

        resp = http.get(reverse("event-wizard-map"))
        assert resp.status_code == 200, (
            "GET map sans prefill doit se rendre (regression VariableDoesNotExist)."
        )
    finally:
        with tenant_context(lespass):
            federation_config.module_agenda_participatif = module_avant
            federation_config.proposition_anonyme_autorisee = anonyme_avant
            federation_config.save()


@pytest.mark.django_db
def test_wizard_place_email_obligatoire_pour_anonyme():
    """
    Lot B : a l'etape 1 du wizard, un visiteur anonyme DOIT fournir un email.
    Sans email -> 422 ; avec email -> 302 + email garde en session.
    / Step 1: an anonymous visitor MUST provide an email. Without -> 422;
    with -> 302 and the email is kept in session.
    """
    from django.test.client import Client as DjangoClient
    from django.urls import reverse
    from django_tenants.utils import tenant_context
    from BaseBillet.models import FederationConfiguration, PostalAddress

    lespass = Client.objects.get(schema_name="lespass")
    domain = lespass.domains.first()
    http = DjangoClient(HTTP_HOST=domain.domain)  # client anonyme

    with tenant_context(lespass):
        federation_config = FederationConfiguration.get_solo()
        module_avant = federation_config.module_agenda_participatif
        anonyme_avant = federation_config.proposition_anonyme_autorisee
        federation_config.module_agenda_participatif = True
        federation_config.proposition_anonyme_autorisee = True
        federation_config.save()
        pa = PostalAddress.objects.first()

    try:
        # Sans email -> erreur de validation (422).
        resp = http.post(reverse("event-wizard-place"), {
            "_form_mode": "existing", "postal_address": str(pa.pk),
        })
        assert resp.status_code == 422

        # Avec email -> on passe (302) et l'email est garde en session.
        email = f"anon-place-{uuidlib.uuid4().hex[:8]}@example.org"
        resp2 = http.post(reverse("event-wizard-place"), {
            "_form_mode": "existing", "postal_address": str(pa.pk),
            "email_proposeur": email,
        })
        assert resp2.status_code == 302
        assert http.session.get("event_wizard_email_proposeur") == email
    finally:
        with tenant_context(lespass):
            federation_config.module_agenda_participatif = module_avant
            federation_config.proposition_anonyme_autorisee = anonyme_avant
            federation_config.save()
