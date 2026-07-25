"""
Test unitaire — une seule adresse principale par lieu (PostalAddress.is_main).
/ Unit test — only one main address per venue (PostalAddress.is_main).

LOCALISATION : tests/pytest/test_postal_address_is_main.py

L'admin (PostalAddressAdmin.save_model) garantit qu'au plus UNE PostalAddress
porte is_main=True par tenant : cocher une adresse comme principale decoche
automatiquement les autres (la derniere cochee gagne).
/ The admin guarantees at most ONE PostalAddress has is_main=True per tenant:
ticking one as main unticks the others (last ticked wins).
"""

import pytest

from django_tenants.utils import tenant_context


class _FakeRequest:
    """Requete minimale : save_model ne lit rien dessus. / Minimal request."""
    pass


@pytest.mark.django_db
def test_cocher_une_adresse_principale_decoche_les_autres(tenant):
    """
    Deux adresses principales ne peuvent coexister : cocher la seconde decoche
    la premiere, il reste exactement une adresse principale.
    / Two main addresses cannot coexist: ticking the second unticks the first.
    """
    from BaseBillet.models import PostalAddress
    from Administration.admin_tenant import PostalAddressAdmin, staff_admin_site

    with tenant_context(tenant):
        # Nettoyage prealable au cas ou un run precedent aurait laisse des restes.
        # / Pre-clean in case a previous run left leftovers.
        PostalAddress.objects.filter(name__startswith="TEST is_main").delete()

        adresse_a = PostalAddress.objects.create(
            name="TEST is_main A", street_address="1 rue A",
            address_locality="Ville", is_main=True,
        )
        adresse_b = PostalAddress.objects.create(
            name="TEST is_main B", street_address="2 rue B",
            address_locality="Ville", is_main=False,
        )

        admin = PostalAddressAdmin(PostalAddress, staff_admin_site)

        # On coche B comme principale via le chemin reel de l'admin.
        # / Tick B as main through the real admin path.
        adresse_b.is_main = True
        admin.save_model(_FakeRequest(), adresse_b, form=None, change=True)

        adresse_a.refresh_from_db()
        adresse_b.refresh_from_db()

        try:
            # A a ete decochee, B est la seule principale.
            # / A got unticked, B is the only main one.
            assert adresse_a.is_main is False
            assert adresse_b.is_main is True
            assert PostalAddress.objects.filter(is_main=True).count() == 1
        finally:
            PostalAddress.objects.filter(name__startswith="TEST is_main").delete()


@pytest.mark.django_db
def test_enregistrer_sans_cocher_ne_touche_pas_les_autres(tenant):
    """
    Enregistrer une adresse NON principale ne doit PAS decocher l'adresse
    principale existante.
    / Saving a NON-main address must NOT untick the existing main address.
    """
    from BaseBillet.models import PostalAddress
    from Administration.admin_tenant import PostalAddressAdmin, staff_admin_site

    with tenant_context(tenant):
        PostalAddress.objects.filter(name__startswith="TEST is_main").delete()

        principale = PostalAddress.objects.create(
            name="TEST is_main principale", street_address="1",
            address_locality="Ville", is_main=True,
        )
        secondaire = PostalAddress.objects.create(
            name="TEST is_main secondaire", street_address="2",
            address_locality="Ville", is_main=False,
        )

        admin = PostalAddressAdmin(PostalAddress, staff_admin_site)
        admin.save_model(_FakeRequest(), secondaire, form=None, change=True)

        principale.refresh_from_db()

        try:
            # L'adresse principale reste principale.
            # / The main address stays main.
            assert principale.is_main is True
            assert PostalAddress.objects.filter(is_main=True).count() == 1
        finally:
            PostalAddress.objects.filter(name__startswith="TEST is_main").delete()
