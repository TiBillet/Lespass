"""
Tests du champ « Type de caisse » dans l'admin des points de vente.
/ Tests of the "POS type" field in the point of sale admin.

LOCALISATION : tests/pytest/test_admin_point_de_vente_type.py

Le champ est une liste de boutons radio. Chaque choix porte sa description.
Seuls Direct, Cashless et Billetterie sont proposes.
/ The field is a radio list. Each choice carries its description.
Only Direct, Cashless and Ticketing are offered.

Aucun test n'ecrit en base : les points de vente « existants » sont des
instances non enregistrees, marquees comme deja en base.
/ No test writes to the DB: "existing" POS are unsaved instances flagged as saved.
"""

from django.urls import reverse
from django_tenants.utils import tenant_context

from Administration.admin.laboutik import PointDeVenteForm
from laboutik.models import PointDeVente


def _valeurs_des_choix_du_type(formulaire):
    """Les valeurs proposees par le champ « Type de caisse ».
    / Values offered by the "POS type" field."""
    valeurs = []
    for valeur, _libelle in formulaire.fields["comportement"].choices:
        valeurs.append(valeur)
    return valeurs


def _point_de_vente_deja_en_base(comportement):
    """Un point de vente qui se presente comme deja enregistre, sans toucher la base.
    / A POS that looks already saved, without touching the DB."""
    point_de_vente = PointDeVente(name="PV de test du type", comportement=comportement)
    point_de_vente._state.adding = False
    return point_de_vente


def test_creation_propose_seulement_direct_cashless_billetterie(tenant):
    """A la creation, ni Adhesions, ni Avance, ni Tireuse ne sont proposes.
    / On creation, neither Memberships, Advanced nor Tap are offered."""
    with tenant_context(tenant):
        formulaire = PointDeVenteForm()

        valeurs_proposees = _valeurs_des_choix_du_type(formulaire)

    assert valeurs_proposees == [
        PointDeVente.DIRECT,
        PointDeVente.CASHLESS,
        PointDeVente.BILLETTERIE,
    ]


def test_point_de_vente_existant_garde_son_type_non_propose(tenant):
    """Un PV deja en « Adhesions » garde ce choix : l'enregistrer ne change pas son type.
    / A POS already in "Memberships" keeps it: saving does not change its type."""
    with tenant_context(tenant):
        point_de_vente_adhesion = _point_de_vente_deja_en_base(PointDeVente.ADHESION)
        formulaire = PointDeVenteForm(instance=point_de_vente_adhesion)

        valeurs_proposees = _valeurs_des_choix_du_type(formulaire)

    assert PointDeVente.ADHESION in valeurs_proposees
    assert PointDeVente.AVANCE not in valeurs_proposees
    assert PointDeVente.TIREUSE not in valeurs_proposees


def test_chaque_choix_affiche_sa_description_reliee_au_bouton(tenant):
    """La description est sous le choix, et reliee au bouton par aria-describedby.
    / The description sits under the choice, linked to the radio by aria-describedby."""
    with tenant_context(tenant):
        formulaire = PointDeVenteForm()
        html_du_champ = str(formulaire["comportement"])

    assert 'type="radio"' in html_du_champ
    assert 'aria-describedby="id_comportement_1-description"' in html_du_champ
    assert 'id="id_comportement_1-description"' in html_du_champ
    assert "la caisse demande la carte du client avant le paiement" in html_du_champ


def test_page_d_ajout_affiche_les_boutons_radio(admin_client, tenant):
    """La page d'ajout de l'admin s'affiche avec les trois boutons radio.
    / The admin add page renders with the three radio buttons."""
    with tenant_context(tenant):
        adresse_de_la_page_d_ajout = reverse("staff_admin:laboutik_pointdevente_add")

    reponse = admin_client.get(adresse_de_la_page_d_ajout)

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert 'data-testid="radio-choix-D"' in contenu
    assert 'data-testid="radio-choix-C"' in contenu
    assert 'data-testid="radio-choix-T"' in contenu
    assert 'data-testid="radio-choix-I"' not in contenu
