"""
tests/pytest/test_carte_cashless_admin.py — Admin CarteCashless (bug bouton # + isolation).
tests/pytest/test_carte_cashless_admin.py — CarteCashless admin (dead-button fix + isolation).

POURQUOI / WHY :
Le bouton « Cartes NFC » du dashboard (Administration/admin/dashboard.py) pointe vers
`staff_admin:QrcodeCashless_cartecashless_changelist`. Tant qu'aucun ModelAdmin n'est
enregistre pour CarteCashless, ce reverse echoue (NoReverseMatch) et `_safe_rev` renvoie
« # » → bouton mort. CarteCashless est en SHARED_APPS (cross-tenant) : l'admin DOIT filtrer
par tenant (via detail.origine), comme fedow_core.

/ The dashboard "NFC cards" button reverses an admin changelist that doesn't exist until a
ModelAdmin is registered; `_safe_rev` then returns "#" (dead button). CarteCashless is in
SHARED_APPS, so the admin MUST filter by tenant (via detail.origine), like fedow_core.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_carte_cashless_admin.py -q
"""

import uuid as uuid_module

import pytest
from django.test import RequestFactory
from django.urls import NoReverseMatch, reverse
from django_tenants.utils import tenant_context

from Customers.models import Client
from QrcodeCashless.models import CarteCashless, Detail


pytestmark = pytest.mark.django_db


def _tag():
    """tag_id de carte de test : 8 caracteres max (piege 9.31).
    / Test card tag_id: 8 chars max."""
    return f"CA{uuid_module.uuid4().hex[:6].upper()}"  # "CA" + 6 = 8


@pytest.fixture
def carte_du_tenant_a():
    """Cree une CarteCashless rattachee a lespass (detail.origine=lespass), nettoyee apres.
    / Creates a CarteCashless tied to lespass (detail.origine=lespass), cleaned up after.

    DB dev partagee, pas de rollback : nettoyage manuel en teardown.
    / Shared dev DB, no rollback: manual teardown cleanup.
    """
    tenant_a = Client.objects.get(schema_name="lespass")
    tag = _tag()
    # Detail stable reutilise entre les runs (slug fixe) : on ne le supprime PAS
    # (Detail.img est un StdImageField delete_orphans=True qui plante a la suppression
    # quand l'image est vide). Pollution nulle : un seul Detail partage.
    # / Stable Detail reused across runs (fixed slug): we don't delete it (StdImageField
    # delete_orphans crashes on empty image). No accumulation: a single shared Detail.
    detail, _ = Detail.objects.get_or_create(
        slug="test-carte-cashless-admin",
        defaults={
            "base_url": "test-carte-admin.localhost",
            "generation": 1,
            "origine": tenant_a,
        },
    )
    carte = CarteCashless.objects.create(
        tag_id=tag,
        uuid=uuid_module.uuid4(),
        number=tag,
        detail=detail,
    )
    yield {"tenant_a": tenant_a, "carte": carte, "detail": detail}
    # Suppression DANS le tenant_context : CarteCashless (SHARED) a une FK inverse
    # depuis BaseBillet.LigneArticle (TENANT) ; le cascade-collect du delete exige
    # que la table tenant existe (sinon UndefinedTable hors schema).
    # / Delete INSIDE the tenant_context: CarteCashless (SHARED) is referenced by
    # BaseBillet.LigneArticle (TENANT); the delete's cascade-collect needs the tenant table.
    with tenant_context(tenant_a):
        carte.delete()


def test_reverse_changelist_carte_cashless_existe():
    """Le lien du dashboard doit resoudre (sinon `_safe_rev` renvoie « # » = bouton mort).
    / The dashboard link must resolve (otherwise `_safe_rev` returns "#" = dead button)."""
    try:
        url = reverse("staff_admin:QrcodeCashless_cartecashless_changelist")
    except NoReverseMatch:
        pytest.fail(
            "staff_admin:QrcodeCashless_cartecashless_changelist introuvable — "
            "aucun ModelAdmin enregistre pour CarteCashless → bouton dashboard mort (#)."
        )
    assert url.endswith("/")


def test_changelist_carte_cashless_se_rend(admin_client, carte_du_tenant_a):
    """La page changelist se rend (HTTP 200) : le bouton dashboard mene a une page valide.
    / The changelist renders (HTTP 200): the dashboard button leads to a working page."""
    url = reverse("staff_admin:QrcodeCashless_cartecashless_changelist")
    response = admin_client.get(url)
    assert response.status_code == 200


def test_admin_carte_cashless_isole_par_tenant(carte_du_tenant_a):
    """SHARED_APPS : l'admin ne montre QUE les cartes du tenant courant (via detail.origine).
    / SHARED_APPS: the admin shows ONLY the current tenant's cards (via detail.origine)."""
    from Administration.admin_tenant import staff_admin_site

    carte = carte_du_tenant_a["carte"]
    admin_instance = staff_admin_site._registry[CarteCashless]
    request = RequestFactory().get("/admin/")

    tenant_b = Client.objects.exclude(schema_name__in=["lespass", "public"]).first()
    assert tenant_b is not None, "Un 2e tenant est requis pour tester l'isolation."

    # Le tenant proprietaire (lespass) voit sa carte.
    # / The owner tenant (lespass) sees its card.
    with tenant_context(carte_du_tenant_a["tenant_a"]):
        ids_visibles_a = set(
            admin_instance.get_queryset(request).values_list("pk", flat=True)
        )
    assert carte.pk in ids_visibles_a

    # Un autre tenant NE voit PAS cette carte.
    # / Another tenant does NOT see this card.
    with tenant_context(tenant_b):
        ids_visibles_b = set(
            admin_instance.get_queryset(request).values_list("pk", flat=True)
        )
    assert carte.pk not in ids_visibles_b


def test_generation_par_defaut_rattachee_au_lieu_courant():
    """Le filet auto renvoie une generation (Detail) rattachee au lieu courant,
    et reste idempotent (aucun MultipleObjectsReturned au 2e appel).
    / The auto net returns a generation tied to the current venue, idempotently."""
    from QrcodeCashless.admin import _obtenir_la_generation_par_defaut_du_lieu

    tenant_a = Client.objects.get(schema_name="lespass")

    with tenant_context(tenant_a):
        detail = _obtenir_la_generation_par_defaut_du_lieu()
        assert detail.origine_id == tenant_a.pk

        # Deuxieme appel : ne plante pas, renvoie une generation du meme lieu.
        # / Second call: does not raise, returns a generation of the same venue.
        detail_bis = _obtenir_la_generation_par_defaut_du_lieu()
        assert detail_bis.origine_id == tenant_a.pk


def test_carte_sans_generation_choisie_reste_visible():
    """Coeur du fix : une carte rattachee a la generation par defaut (cas ou le
    gestionnaire n'en a pas choisi) APPARAIT dans la liste admin du lieu.
    / Core fix: a card attached to the default generation shows in the venue's list.

    Mutation : si le filet ne rattachait PAS de Detail (detail=None), le filtre
    detail.origine de get_queryset exclurait la carte et l'assert echouerait.
    / Mutation: without the Detail (detail=None), get_queryset's detail.origine
    filter would exclude the card and the assert would fail.
    """
    from QrcodeCashless.admin import (
        _obtenir_la_generation_par_defaut_du_lieu,
        staff_admin_site,
    )

    tenant_a = Client.objects.get(schema_name="lespass")
    admin_instance = staff_admin_site._registry[CarteCashless]
    request = RequestFactory().get("/admin/")
    tag = _tag()

    with tenant_context(tenant_a):
        detail = _obtenir_la_generation_par_defaut_du_lieu()
        carte = CarteCashless.objects.create(
            tag_id=tag,
            uuid=uuid_module.uuid4(),
            number=tag,
            detail=detail,
        )
        try:
            ids_visibles = set(
                admin_instance.get_queryset(request).values_list("pk", flat=True)
            )
            assert carte.pk in ids_visibles
        finally:
            # On supprime la carte (le Detail est reutilise entre les runs, on ne
            # le touche pas : StdImageField delete_orphans plante sur image vide).
            # / Delete the card; keep the Detail (delete_orphans crashes on empty img).
            carte.delete()


def test_form_ajout_preselectionne_la_generation_la_plus_haute():
    """Le formulaire d'ajout pre-remplit `detail` avec la generation la plus haute
    du lieu. Instancier le form ne plante jamais (guard si aucune generation).
    / The add form pre-fills `detail` with the venue's highest generation; building
    the form never crashes (guarded when there is no generation)."""
    from QrcodeCashless.admin import CarteCashlessAddForm

    tenant_a = Client.objects.get(schema_name="lespass")

    with tenant_context(tenant_a):
        # On garantit deux generations stables (slugs fixes, reutilises entre runs) :
        # la plus haute (99) doit etre celle qui est pre-selectionnee.
        # / Ensure two stable generations (fixed slugs): the highest (99) must win.
        Detail.objects.get_or_create(
            slug="test-carte-admin-gen-basse",
            defaults={"base_url": "t1.localhost", "generation": 1, "origine": tenant_a},
        )
        generation_la_plus_haute, _ = Detail.objects.get_or_create(
            slug="test-carte-admin-gen-haute",
            defaults={"base_url": "t2.localhost", "generation": 99, "origine": tenant_a},
        )

        formulaire = CarteCashlessAddForm()
        assert formulaire.fields["detail"].initial == generation_la_plus_haute
