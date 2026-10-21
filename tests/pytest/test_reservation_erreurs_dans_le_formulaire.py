"""
Réservation d'un événement : les erreurs s'affichent DANS le formulaire.
/ Event booking: errors are shown INSIDE the form.

LOCALISATION : tests/pytest/test_reservation_erreurs_dans_le_formulaire.py

Code testé :
- BaseBillet/views.py : EventMVT.reservation() — refus = partiel d'erreurs + HX-Retarget
  vers #reservation-erreurs, sans HX-Redirect (sinon la page se recharge et la personne
  perd sa saisie).
- BaseBillet/validators.py : ReservationValidator — messages précis (nom du tarif,
  limite, quantités).

Les assertions lisent les éléments stables des messages (nom du tarif, chiffres), pas
leur formulation : elle change avec la langue et les traductions.
Chaque test est marqué `django_db` : transaction annulée à la fin.
"""
import re

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import (
    client_connecte,
    creer_evenement_avec_tarif,
    creer_utilisateur,
)

pytestmark = pytest.mark.django_db

EN_TETE_HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


def texte_des_erreurs(reponse):
    """
    Le texte seul des erreurs, sans les balises : un chiffre cherché dans le HTML
    brut serait trouvé dans les classes CSS (« mb-3 »).
    / Error text only, tags stripped: digits would match CSS classes otherwise.
    """
    return re.sub(r"<[^>]+>", " ", reponse.content.decode())


def envoyer_le_formulaire(client, acheteur, evenement, quantites_par_tarif):
    donnees_du_formulaire = {"event": str(evenement.uuid), "email": acheteur.email}
    for tarif, quantite in quantites_par_tarif.items():
        donnees_du_formulaire[str(tarif.uuid)] = str(quantite)
    return client.post(
        f"/event/{evenement.slug}/reservation/", donnees_du_formulaire, **EN_TETE_HTMX,
    )


def test_un_refus_s_affiche_dans_le_formulaire_sans_recharger_la_page(tenant):
    from BaseBillet.models import Reservation

    with tenant_context(tenant):
        acheteur = creer_utilisateur()
        billetterie = creer_evenement_avec_tarif(max_par_personne_evenement=2)

        reponse = envoyer_le_formulaire(
            client_connecte(acheteur), acheteur, billetterie.evenement, {billetterie.tarif: 3},
        )

        # Seule la zone d'erreurs du formulaire est remplacée : pas de rechargement.
        # / Only the form's error zone is replaced: no reload.
        assert reponse.status_code == 200
        assert reponse["HX-Retarget"] == "#reservation-erreurs"
        assert reponse["HX-Reswap"] == "innerHTML"
        assert "HX-Redirect" not in reponse

        assert 'data-testid="booking-server-errors-list"' in reponse.content.decode()
        # Limite 2, demandés 3, déjà réservés 0 : les trois chiffres sont dans le texte.
        # / Limit 2, requested 3, already booked 0.
        chiffres_du_message = re.findall(r"\d+", texte_des_erreurs(reponse))
        assert chiffres_du_message == ["2", "3", "0"]

        assert not Reservation.objects.filter(event=billetterie.evenement).exists()


def test_le_message_de_limite_par_tarif_nomme_le_tarif_et_les_quantites(tenant):
    from BaseBillet.models import Price

    with tenant_context(tenant):
        acheteur = creer_utilisateur()
        billetterie = creer_evenement_avec_tarif(max_par_personne_tarif=1)
        # update() et pas save() : aucun signal (Stripe, Fedow) hors simulation.
        # / update(), not save(): no signal (Stripe, Fedow) outside the mocks.
        Price.objects.filter(pk=billetterie.tarif.pk).update(name="Tarif solidaire TEST")

        reponse = envoyer_le_formulaire(
            client_connecte(acheteur), acheteur, billetterie.evenement, {billetterie.tarif: 4},
        )

        texte = texte_des_erreurs(reponse)
        assert reponse["HX-Retarget"] == "#reservation-erreurs"
        assert "Tarif solidaire TEST" in texte
        # Limite 1, demandés 4, déjà réservés 0. / Limit 1, requested 4, already 0.
        assert re.findall(r"\d+", texte) == ["1", "4", "0"]


def test_le_message_d_adhesion_requise_nomme_le_tarif_et_l_adhesion(tenant):
    from BaseBillet.models import Price, Product
    from fabriques_panier import creer_adhesion

    with tenant_context(tenant):
        acheteur = creer_utilisateur()
        billetterie = creer_evenement_avec_tarif()
        adhesion = creer_adhesion()
        # update() et pas save() : aucun signal (Stripe, Fedow) hors simulation.
        # / update(), not save(): no signal (Stripe, Fedow) outside the mocks.
        Product.objects.filter(pk=adhesion.produit.pk).update(name="Adhésion TEST asso")
        Price.objects.filter(pk=billetterie.tarif.pk).update(name="Tarif adhérent TEST")
        billetterie.tarif.adhesions_obligatoires.add(adhesion.produit)

        reponse = envoyer_le_formulaire(
            client_connecte(acheteur), acheteur, billetterie.evenement, {billetterie.tarif: 1},
        )

        contenu = reponse.content.decode()
        assert reponse["HX-Retarget"] == "#reservation-erreurs"
        assert "Tarif adhérent TEST" in contenu
        assert "Adhésion TEST asso" in contenu
