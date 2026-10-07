"""
tests/pytest/test_noms_de_routes_admin_uniques.py
Chaque nom de route du site d'admin `staff_admin` designe UNE seule page.
/ Every route name of the `staff_admin` admin site points to ONE page only.

LOCALISATION : tests/pytest/test_noms_de_routes_admin_uniques.py

POURQUOI / WHY
---------------
`{% url 'staff_admin:<nom>' %}` et `reverse()` ne previennent pas quand deux routes
portent le meme nom : ils renvoient l'une des deux, en silence. Un gabarit poste alors vers
la page d'un autre admin. Cas reel : le bouton « ACCEPTER » des invitations d'assets legacy
(`fedow_public`) postait vers l'acceptation des assets `fedow_core`, qui refuse un lieu
legacy : un lieu du reseau CLAF ne pouvait plus accepter une federation.
/ Duplicate route names make `{% url %}` / `reverse()` silently pick one of them.

EXCEPTION ADMISE / ALLOWED EXCEPTION
-------------------------------------
django-solo (`SingletonModelAdmin`) declare deux fois `<app>_<modele>_change` et
`<app>_<modele>_history` DANS LE MEME admin : la page unique du singleton, puis les routes
standard. C'est voulu (la premiere gagne, et c'est la bonne). Le test refuse seulement un
nom porte par deux admins DIFFERENTS.
/ django-solo repeats `_change` / `_history` inside one admin, by design: only a name
shared by two DIFFERENT admins fails.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_noms_de_routes_admin_uniques.py -q
"""

import re
import uuid
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.urls import URLPattern, URLResolver


def _admins_par_nom_de_route(motifs_d_url, prefixe_de_l_admin, admins_par_nom):
    """
    Parcourt les routes du site d'admin et note, pour chaque nom, les admins qui le portent.
    Un admin est identifie par son prefixe d'URL (`fedow_core/asset/`).
    / Walks the admin site routes and records, per name, the admins (URL prefix) using it.
    """
    for motif in motifs_d_url:
        if isinstance(motif, URLResolver):
            _admins_par_nom_de_route(
                motif.url_patterns,
                prefixe_de_l_admin + str(motif.pattern),
                admins_par_nom,
            )
        elif isinstance(motif, URLPattern) and motif.name:
            if motif.name not in admins_par_nom:
                admins_par_nom[motif.name] = set()
            admins_par_nom[motif.name].add(prefixe_de_l_admin)


def test_aucun_nom_de_route_n_est_partage_par_deux_admins():
    """
    Aucun nom de route de `staff_admin` n'est porte par deux admins differents.
    / No `staff_admin` route name is shared by two different admins.
    """
    # L'import enregistre les ModelAdmin sur le site (decorateurs @admin.register).
    # / The import registers the ModelAdmins on the site.
    import Administration.admin_tenant  # noqa: F401
    from Administration.admin.site import staff_admin_site

    admins_par_nom = {}
    _admins_par_nom_de_route(staff_admin_site.get_urls(), "", admins_par_nom)

    noms_partages = {}
    for nom_de_route, prefixes_des_admins in admins_par_nom.items():
        if len(prefixes_des_admins) > 1:
            noms_partages[nom_de_route] = sorted(prefixes_des_admins)

    assert noms_partages == {}, (
        "Noms de route d'admin portes par plusieurs admins : "
        f"{noms_partages}. `{{% url %}}` et `reverse()` n'en renvoient qu'un, en silence. "
        "Donner a chaque route un nom propre (le `name=` de son `get_urls()`)."
    )


def _action_du_formulaire(html_du_panneau):
    """
    L'adresse `action` du premier formulaire du panneau.
    / The `action` URL of the panel's first form.
    """
    trouve = re.search(r'<form[^>]*action="([^"]+)"', html_du_panneau)
    assert trouve, f"Aucun formulaire dans le panneau :\n{html_du_panneau[:2000]}"
    return trouve.group(1)


def test_le_panneau_legacy_poste_vers_l_acceptation_legacy():
    """
    Le bouton « ACCEPTER » des invitations d'assets legacy poste vers la route de
    `fedow_public` (`AssetAdmin.accept_invitation`, Administration/admin_tenant.py).
    / The legacy invitations panel posts to the `fedow_public` accept route.
    """
    uuid_de_l_asset = uuid.uuid4()
    asset_invitant = SimpleNamespace(
        pk=uuid_de_l_asset,
        name="Monnaie de test",
        origin=SimpleNamespace(name="Lespass"),
    )
    html_du_panneau = render_to_string(
        "admin/asset/asset_list_before.html",
        {"asset_invitations": [asset_invitant]},
    )
    assert _action_du_formulaire(html_du_panneau) == (
        f"/admin/fedow_public/assetfedowpublic/accept_invitation/{uuid_de_l_asset}/"
    )


def test_le_panneau_v2_poste_vers_l_acceptation_fedow_core():
    """
    Le bouton « Accepter le partage » des invitations d'assets `fedow_core` poste vers la
    route de `fedow_core` (`AssetAdmin.accept_asset_invitation`, fedow_core/admin.py).
    / The fedow_core invitations panel posts to the fedow_core accept route.
    """
    uuid_de_l_asset = uuid.uuid4()
    asset_invitant = SimpleNamespace(
        pk=uuid_de_l_asset,
        name="Monnaie de test",
        currency_code="EUR",
        tenant_origin=SimpleNamespace(name="Lespass"),
        get_category_display=lambda: "Token local fiduciaire",
    )
    html_du_panneau = render_to_string(
        "admin/asset/asset_changelist_invitations.html",
        {"invitations_asset_en_attente": [asset_invitant]},
    )
    assert _action_du_formulaire(html_du_panneau) == (
        f"/admin/fedow_core/asset/accept_asset_invitation/{uuid_de_l_asset}/"
    )
