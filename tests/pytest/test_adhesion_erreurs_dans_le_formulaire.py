"""
Formulaire d'adhésion : les erreurs s'affichent DANS le formulaire.
/ Membership form: errors are shown INSIDE the form.

LOCALISATION : tests/pytest/test_adhesion_erreurs_dans_le_formulaire.py

Code testé : BaseBillet/views.py, MembershipMVT.create() — refus = partiel d'erreurs
+ HX-Retarget vers #adhesion-erreurs, sans HX-Redirect (sinon la page se recharge et la
personne perd sa saisie).

Les assertions lisent les éléments stables (zone ciblée, nombre d'erreurs), pas la
formulation des messages : elle change avec la langue et les traductions.
Chaque test est marqué `django_db` : transaction annulée à la fin.
"""
import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import client_connecte, creer_adhesion, identifiant_unique

pytestmark = pytest.mark.django_db

EN_TETE_HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


def envoyer_le_formulaire(tarif, **champs):
    donnees_du_formulaire = {
        "price": str(tarif.uuid),
        "email": f"adhesion-{identifiant_unique()}@example.org",
        "firstname": "Ada",
        "lastname": "Lovelace",
        "acknowledge": "on",
    }
    donnees_du_formulaire.update(champs)
    return client_connecte().post("/memberships/", donnees_du_formulaire, **EN_TETE_HTMX)


def test_un_refus_s_affiche_dans_le_formulaire_sans_recharger_la_page(tenant):
    from BaseBillet.models import Membership

    with tenant_context(tenant):
        adhesion = creer_adhesion(prix="10.00", prix_libre=True)

        # Prix libre à 5 € pour un minimum de 10 € : refusé.
        # / Free price of 5 € for a 10 € minimum: refused.
        reponse = envoyer_le_formulaire(
            adhesion.tarif, **{f"custom_amount_{adhesion.tarif.uuid}": "5"},
        )

        # Seule la zone d'erreurs du formulaire est remplacée : pas de rechargement.
        # / Only the form's error zone is replaced: no reload.
        assert reponse.status_code == 200
        assert reponse["HX-Retarget"] == "#adhesion-erreurs"
        assert reponse["HX-Reswap"] == "innerHTML"
        assert "HX-Redirect" not in reponse
        assert 'data-testid="booking-server-errors-list"' in reponse.content.decode()

        assert not Membership.objects.filter(price=adhesion.tarif).exists()


def test_plusieurs_erreurs_s_affichent_en_liste_pas_en_liste_python(tenant):
    with tenant_context(tenant):
        adhesion = creer_adhesion()

        reponse = envoyer_le_formulaire(adhesion.tarif, firstname="", lastname="")

        contenu = reponse.content.decode()
        assert reponse["HX-Retarget"] == "#adhesion-erreurs"
        # Une puce par erreur, jamais la liste Python brute « ['…'] ».
        # / One bullet per error, never the raw Python list.
        assert contenu.count("<li>") == 2
        assert "['" not in contenu
