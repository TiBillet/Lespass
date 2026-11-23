"""
Fiche adhésion de l'admin : un enregistrement refusé réaffiche la fiche, sans planter.
/ Admin membership page: a rejected save shows the page again, without crashing.

LOCALISATION : tests/pytest/test_admin_adhesion_formulaire_invalide.py

Quand une saisie est fausse (par exemple une date de fin illisible), Django réaffiche la
fiche avec un message d'erreur. Il reconstruit alors le tableau « Ventes / Ligne
comptables » à partir des données envoyées par le navigateur. Chaque ligne doit donc être
retrouvée grâce à son identifiant caché `lignearticles-N-uuid`. Sans cet identifiant,
Django fabrique une ligne vide, sans quantité, et l'affichage de la quantité plante.

Le POST est construit UNIQUEMENT à partir du HTML de la fiche : c'est ce que fait le
navigateur. Ajouter l'uuid à la main ferait passer le test même quand la page ne l'écrit
pas.
/ The POST is built ONLY from the page's HTML, like a browser does. Adding the uuid by hand
would make the test pass even when the page does not write it.
"""

from html.parser import HTMLParser

import pytest
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db


class _LecteurDesChampsDuFormulaire(HTMLParser):
    """
    Relève les champs que le navigateur enverrait : les `<input>` (sauf boutons et
    fichiers) et les cases cochées.
    / Collects the fields a browser would send: inputs (except buttons and files) and
    checked boxes.
    """

    def __init__(self):
        super().__init__()
        self.donnees_envoyees = {}

    def handle_starttag(self, balise, attributs):
        if balise != "input":
            return
        attributs = dict(attributs)
        nom_du_champ = attributs.get("name")
        type_du_champ = attributs.get("type", "text")
        if not nom_du_champ:
            return
        if type_du_champ in ("submit", "button", "file"):
            return
        if type_du_champ in ("checkbox", "radio"):
            case_cochee = "checked" in attributs
            if case_cochee:
                self.donnees_envoyees[nom_du_champ] = attributs.get("value", "on")
            return
        self.donnees_envoyees[nom_du_champ] = attributs.get("value", "")


def test_fiche_adhesion_avec_ventes_reaffichee_apres_une_saisie_invalide(
    admin_client, tenant
):
    """
    Une date de fin illisible : la fiche revient en 200 avec le message d'erreur, et
    chaque ligne de vente garde son identifiant caché.
    / An unreadable end date: the page comes back as 200 with the error, and each sale
    line keeps its hidden id.
    """
    from BaseBillet.models import LigneArticle, Membership

    with tenant_context(tenant):
        identifiants_des_adhesions_avec_ventes = LigneArticle.objects.exclude(
            membership=None
        ).values_list("membership_id", flat=True)
        adhesion_avec_ventes = Membership.objects.filter(
            pk__in=identifiants_des_adhesions_avec_ventes
        ).first()

    # Le test a besoin d'une adhésion qui a au moins une vente : sans ligne, le tableau
    # est vide et le défaut ne peut pas se produire.
    # / The test needs a membership with at least one sale line.
    assert adhesion_avec_ventes is not None, (
        "Aucune adhésion avec une ligne de vente dans le tenant lespass."
    )

    adresse_de_la_fiche = (
        f"/admin/BaseBillet/membership/{adhesion_avec_ventes.pk}/change/"
    )
    reponse_affichage = admin_client.get(adresse_de_la_fiche)
    assert reponse_affichage.status_code == 200
    html_de_la_fiche = reponse_affichage.content.decode()

    # La page écrit l'identifiant caché de la première ligne de vente.
    # / The page writes the hidden id of the first sale line.
    assert 'name="lignearticles-0-uuid"' in html_de_la_fiche

    lecteur = _LecteurDesChampsDuFormulaire()
    lecteur.feed(html_de_la_fiche)
    donnees_envoyees = lecteur.donnees_envoyees
    donnees_envoyees["deadline_0"] = "pas-une-date"
    donnees_envoyees["deadline_1"] = "12:00"

    reponse_enregistrement = admin_client.post(adresse_de_la_fiche, donnees_envoyees)

    # 200 = la fiche est réaffichée avec l'erreur. Une redirection (302) voudrait dire
    # que la saisie invalide a été acceptée.
    # / 200 = the page is shown again with the error. A 302 would mean it was accepted.
    assert reponse_enregistrement.status_code == 200
    html_reaffiche = reponse_enregistrement.content.decode()
    assert 'name="lignearticles-0-uuid"' in html_reaffiche
