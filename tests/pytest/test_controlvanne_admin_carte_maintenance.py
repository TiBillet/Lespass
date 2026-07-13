"""
tests/pytest/test_controlvanne_admin_carte_maintenance.py — Admin CarteMaintenance.
tests/pytest/test_controlvanne_admin_carte_maintenance.py — CarteMaintenance admin.

POURQUOI / WHY (issue #446) :
Le formulaire d'ajout d'une carte de maintenance affichait un champ « Carte NFC »
en saisie brute (raw_id) : l'utilisateur devait taper le pk NUMERIQUE de la carte.
En regie, on tape naturellement le Tag ID lu sur la puce (« 611377E9 ») : rien
n'etait reconnu, et la loupe ouvrait le changelist des cartes en popup.
On attend une autocompletion, comme sur CartePrimaire (laboutik).

Second defaut, non signale dans l'issue mais plus grave : CarteCashless est en
SHARED_APPS (schema public, aucune isolation). Sans queryset filtre sur le lieu
courant, un pk force rattacherait la carte d'un AUTRE lieu.

/ WHY (issue #446): the maintenance card add form used a raw_id text input, so the
user had to type the card's NUMERIC pk. In the field, people type the NFC Tag ID.
Nothing matched. We expect autocompletion, like CartePrimaire (laboutik).
Second flaw: CarteCashless is in SHARED_APPS (public schema, no isolation). Without
a tenant-filtered queryset, a forged pk would attach another venue's card.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        tests/pytest/test_controlvanne_admin_carte_maintenance.py -q
"""

import uuid as uuid_module

import pytest
from django.contrib.admin.widgets import AutocompleteSelect, RelatedFieldWidgetWrapper
from django.test import RequestFactory
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from Customers.models import Client
from QrcodeCashless.models import CarteCashless, Detail
from controlvanne.models import CarteMaintenance


pytestmark = pytest.mark.django_db


def _tag():
    """tag_id de carte de test : 8 caracteres exactement.
    / Test card tag_id: exactly 8 chars."""
    return f"CM{uuid_module.uuid4().hex[:6].upper()}"  # "CM" + 6 = 8


def _carte_pour_le_lieu(tenant):
    """Cree une CarteCashless emise par ce lieu (via detail.origine).
    / Creates a CarteCashless issued by this venue (via detail.origine)."""
    # Le Detail porte un slug FIXE et n'est JAMAIS supprime : `Detail.img` est un
    # StdImageField(delete_orphans=True) qui plante a la suppression quand l'image est
    # vide. Le slug fixe fait qu'un seul Detail est partage entre tous les runs :
    # aucune accumulation en base malgre l'absence de teardown.
    # Detail.slug est limite a 50 caracteres : on tronque le nom du schema.
    # / The Detail has a FIXED slug and is NEVER deleted: Detail.img is a
    # StdImageField(delete_orphans=True) that crashes on delete when the image is empty.
    # The fixed slug means a single Detail is shared across runs: no accumulation.
    detail, _cree = Detail.objects.get_or_create(
        slug=f"test-cm-{tenant.schema_name[:20]}",
        defaults={
            "base_url": "test-carte-maintenance.localhost",
            "generation": 1,
            "origine": tenant,
        },
    )
    tag = _tag()
    return CarteCashless.objects.create(
        tag_id=tag,
        uuid=uuid_module.uuid4(),
        number=tag,
        detail=detail,
    )


@pytest.fixture
def deux_lieux_avec_chacun_une_carte():
    """Un lieu A (lespass) et un lieu B, chacun avec sa propre carte NFC.
    / Venue A (lespass) and venue B, each with its own NFC card.

    DB dev partagee, pas de rollback : nettoyage manuel en teardown.
    / Shared dev DB, no rollback: manual teardown cleanup.
    """
    lieu_a = Client.objects.get(schema_name="lespass")
    lieu_b = Client.objects.exclude(schema_name__in=["lespass", "public"]).first()
    assert lieu_b is not None, "Un 2e lieu est requis pour tester l'isolation."

    carte_du_lieu_a = _carte_pour_le_lieu(lieu_a)
    carte_du_lieu_b = _carte_pour_le_lieu(lieu_b)

    yield {
        "lieu_a": lieu_a,
        "lieu_b": lieu_b,
        "carte_du_lieu_a": carte_du_lieu_a,
        "carte_du_lieu_b": carte_du_lieu_b,
    }

    # Suppression DANS un tenant_context : CarteCashless (SHARED) est referencee
    # par des modeles TENANT ; le cascade-collect du delete exige que les tables
    # tenant existent. / Delete INSIDE a tenant_context: the delete's cascade-collect
    # needs the tenant tables to exist.
    with tenant_context(lieu_a):
        carte_du_lieu_a.delete()
        carte_du_lieu_b.delete()


def _champ_carte_du_formulaire_d_ajout(lieu):
    """Rend le formulaire d'ajout de CarteMaintenance et renvoie son champ « carte ».
    / Renders the CarteMaintenance add form and returns its "carte" field."""
    from Administration.admin_tenant import staff_admin_site

    admin_de_la_carte_maintenance = staff_admin_site._registry[CarteMaintenance]
    requete = RequestFactory().get("/admin/")

    # L'admin Unfold lit `request.user` : il faut un vrai utilisateur staff. On echoue
    # avec un message clair plutot que sur un AttributeError si la base n'en a aucun.
    # / Unfold reads request.user: fail loudly if the dev DB has no staff user.
    utilisateur_staff = TibilletUser.objects.filter(is_staff=True).first()
    assert utilisateur_staff is not None, (
        "Aucun utilisateur staff dans la base de dev : ce test en a besoin pour rendre "
        "le formulaire d'admin."
    )
    requete.user = utilisateur_staff

    with tenant_context(lieu):
        classe_de_formulaire = admin_de_la_carte_maintenance.get_form(requete)
        return classe_de_formulaire().fields["carte"]


def test_le_champ_carte_propose_une_autocompletion(deux_lieux_avec_chacun_une_carte):
    """Le champ « Carte NFC » doit etre une autocompletion, pas une saisie de pk.
    / The "NFC card" field must be an autocomplete, not a raw pk input.

    Avec raw_id_fields, le widget est un ForeignKeyRawIdWidget : il attend le pk
    numerique de la carte. Taper le Tag ID lu sur la puce ne donne rien (issue #446).
    """
    champ_carte = _champ_carte_du_formulaire_d_ajout(
        deux_lieux_avec_chacun_une_carte["lieu_a"]
    )

    # Django emballe le widget dans un RelatedFieldWidgetWrapper (boutons + / loupe).
    # Le vrai widget est dedans. / Django wraps the widget; the real one is inside.
    widget_reel = champ_carte.widget
    if isinstance(widget_reel, RelatedFieldWidgetWrapper):
        widget_reel = widget_reel.widget

    assert isinstance(widget_reel, AutocompleteSelect), (
        f"Le champ « carte » utilise {type(widget_reel).__name__} : l'utilisateur doit "
        f"taper le pk numerique de la carte. Attendu : une autocompletion sur le Tag ID "
        f"(autocomplete_fields, comme CartePrimaireAdmin)."
    )


def test_le_champ_carte_ne_montre_que_les_cartes_du_lieu_courant(
    deux_lieux_avec_chacun_une_carte,
):
    """CarteCashless est en SHARED_APPS : le champ DOIT filtrer sur le lieu courant.
    / CarteCashless is in SHARED_APPS: the field MUST filter on the current venue.

    Le queryset du champ est ce qui VALIDE la valeur postee. Sans filtre, un pk
    force pointant sur la carte d'un autre lieu serait accepte.
    """
    carte_du_lieu_a = deux_lieux_avec_chacun_une_carte["carte_du_lieu_a"]
    carte_du_lieu_b = deux_lieux_avec_chacun_une_carte["carte_du_lieu_b"]

    champ_carte = _champ_carte_du_formulaire_d_ajout(
        deux_lieux_avec_chacun_une_carte["lieu_a"]
    )
    pks_selectionnables = set(champ_carte.queryset.values_list("pk", flat=True))

    assert carte_du_lieu_a.pk in pks_selectionnables, (
        "Le lieu courant doit pouvoir choisir SES propres cartes."
    )
    assert carte_du_lieu_b.pk not in pks_selectionnables, (
        "Fuite cross-tenant : la carte d'un autre lieu est selectionnable comme "
        "carte de maintenance."
    )
