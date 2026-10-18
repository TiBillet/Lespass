"""
Tests de « Inscrire quelqu'un à sa place » : l'équipe du lieu inscrit une autre personne.
/ Tests of "Sign someone up": the venue team signs another person up.

LOCALISATION : tests/pytest/test_benevolat_equipe.py

Code testé / Tested code : booking/views_benevolat.py (inscrire_une_personne,
chercher_une_personne, InscriptionParLEquipeSerializer), booking/benevolat.py (lien admin)
Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§5.10, D23, D27)

« Personne d'un autre lieu » : un compte qui n'a pas `lespass` dans client_achat. C'est
exactement ce que filtre HumanUser.objects (comptes humains rattachés AU LIEU).
/ "Someone from another venue": an account without `lespass` in client_achat.

Chaque test est marqué `django_db` : transaction annulée à la fin.
Lancer / Run : make test ARGS="tests/pytest/test_benevolat_equipe.py"
"""

import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context

from fabriques_panier import creer_adhesion, creer_utilisateur, identifiant_unique, taches_celery_enregistrees

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les tâches activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5)."""
    from django.utils import translation

    yield
    translation.deactivate()


def navigateur(utilisateur=None):
    client = Client(HTTP_HOST="lespass.tibillet.localhost", HTTP_ACCEPT_LANGUAGE="fr")
    if utilisateur is not None:
        client.force_login(utilisateur)
    return client


def personne_du_lieu(tenant, prenom="Camille", nom="Martin"):
    """Un compte rattaché au lieu (client_achat) : HumanUser.objects le voit."""
    personne = creer_utilisateur(prenom=prenom, nom=nom)
    personne.client_achat.add(tenant)
    return personne


@pytest.fixture
def lieu(tenant):
    """Un planning publié avec un besoin dans 5 jours, un·e admin du lieu, Celery intercepté."""
    from BaseBillet.models import Configuration
    from booking.models import BesoinBenevole, PlanningBenevole, TacheBenevole

    with tenant_context(tenant):
        with taches_celery_enregistrees():
            identifiant = identifiant_unique()
            fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
            aujourd_hui = timezone.now().astimezone(fuseau_du_lieu).date()
            planning = PlanningBenevole.objects.create(
                name=f"TEST_benevolat planning {identifiant}", slug=f"test-benevolat-{identifiant}", published=True,
            )
            tache = TacheBenevole.objects.create(name=f"TEST_benevolat bar {identifiant}")
            besoin = BesoinBenevole.objects.create(
                planning=planning, tache=tache, date=aujourd_hui + datetime.timedelta(days=5),
                heure_debut=datetime.time(18), heure_fin=datetime.time(21), nombre_souhaite=2,
            )
            admin_du_lieu = creer_utilisateur(prenom="Alex", nom="Admin")
            admin_du_lieu.client_admin.add(tenant)
            yield SimpleNamespace(
                tenant=tenant, planning=planning, besoin=besoin, admin=admin_du_lieu, aujourd_hui=aujourd_hui,
            )


def adresse_inscrire_une_personne(besoin):
    return f"/booking/benevolat/besoin/{besoin.pk}/inscrire-une-personne/"


def adresse_chercher(besoin, texte):
    return f"/booking/benevolat/besoin/{besoin.pk}/chercher-une-personne/?q={texte}"


# ---------------------------------------------------------------------------
# Droits / Rights
# ---------------------------------------------------------------------------

def test_anonyme_et_non_admin_recoivent_403_sur_les_trois_vues(lieu):
    from booking.models import InscriptionBenevole

    camille = personne_du_lieu(lieu.tenant)
    for client in [navigateur(), navigateur(creer_utilisateur())]:
        assert client.get(adresse_inscrire_une_personne(lieu.besoin)).status_code == 403
        assert client.post(adresse_inscrire_une_personne(lieu.besoin), {"user": str(camille.pk)}).status_code == 403
        assert client.get(adresse_chercher(lieu.besoin, "Cam")).status_code == 403
    assert not InscriptionBenevole.objects.filter(besoin=lieu.besoin).exists()


def test_seul_l_admin_voit_le_lien_inscrire_quelqu_un(lieu):
    lien = f'data-testid="benevolat-inscrire-quelquun-{lieu.besoin.pk}"'
    adresse = f"/booking/benevolat/{lieu.planning.slug}/"

    assert lien in navigateur(lieu.admin).get(adresse).content.decode()
    assert lien not in navigateur(creer_utilisateur()).get(adresse).content.decode()
    assert lien not in navigateur().get(adresse).content.decode()


def test_le_get_ouvre_la_fenetre(lieu):
    reponse = navigateur(lieu.admin).get(adresse_inscrire_une_personne(lieu.besoin))

    assert reponse.status_code == 200
    assert reponse["HX-Retarget"] == "#benevolat-modale-contenu"
    assert "ouvrirModaleBenevolat" in reponse["HX-Trigger-After-Settle"]
    assert 'data-testid="benevolat-recherche-personne"' in reponse.content.decode()


# ---------------------------------------------------------------------------
# Recherche / Search
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texte", ["Zéphy", "Lacroix", "zephyrine.lacroix"])
def test_recherche_par_prenom_nom_ou_email(lieu, texte):
    zephyrine = personne_du_lieu(lieu.tenant, prenom="Zéphyrine", nom="Lacroix")
    zephyrine.email = f"zephyrine.lacroix.{identifiant_unique()}@mock.test"
    zephyrine.save(update_fields=["email"])

    html = navigateur(lieu.admin).get(adresse_chercher(lieu.besoin, texte)).content.decode()

    assert f'data-testid="benevolat-resultat-personne-{zephyrine.pk}"' in html


def test_moins_de_2_lettres_aucun_resultat(lieu):
    personne_du_lieu(lieu.tenant, prenom="Zo")

    html = navigateur(lieu.admin).get(adresse_chercher(lieu.besoin, "Z")).content.decode()

    assert "Tape au moins 2 lettres" in html
    assert "benevolat-resultat-personne-" not in html


def test_un_compte_d_un_autre_lieu_ne_sort_jamais_meme_par_email_exact(lieu):
    d_ailleurs = creer_utilisateur(prenom="Ailleurs", nom="Autrelieu")

    for texte in ["Ailleurs", "Autrelieu", d_ailleurs.email]:
        html = navigateur(lieu.admin).get(adresse_chercher(lieu.besoin, texte)).content.decode()
        assert str(d_ailleurs.pk) not in html, texte


def test_une_personne_deja_inscrite_n_a_pas_de_bouton(lieu):
    from booking.models import InscriptionBenevole

    camille = personne_du_lieu(lieu.tenant, prenom="Quentinette")
    InscriptionBenevole.objects.create(besoin=lieu.besoin, user=camille)

    html = navigateur(lieu.admin).get(adresse_chercher(lieu.besoin, "Quentinette")).content.decode()

    assert "déjà inscrite" in html
    assert f'data-testid="benevolat-inscrire-personne-{camille.pk}"' not in html


# ---------------------------------------------------------------------------
# Inscrire une personne trouvée / Sign up a found person
# ---------------------------------------------------------------------------

def test_inscrire_une_personne_trouvee(lieu, django_capture_on_commit_callbacks):
    """inscrit_par = l'admin ; mail « L'équipe t'a inscrit·e » ; zone rendue, fenêtre fermée."""
    from booking.models import InscriptionBenevole

    camille = personne_du_lieu(lieu.tenant)
    with patch("booking.views_benevolat.envoyer_confirmation_benevole") as tache_de_confirmation:
        with django_capture_on_commit_callbacks(execute=True):
            reponse = navigateur(lieu.admin).post(adresse_inscrire_une_personne(lieu.besoin), {"user": str(camille.pk)})

    assert reponse.status_code == 200
    assert "fermerModaleBenevolat" in reponse["HX-Trigger-After-Settle"]
    assert "Camille Martin" in reponse["HX-Trigger"]
    inscription = InscriptionBenevole.objects.get(besoin=lieu.besoin, user=camille)
    assert inscription.inscrit_par == lieu.admin
    tache_de_confirmation.delay.assert_called_once_with(str(inscription.pk), par_l_equipe=True)


def test_reinscrire_la_meme_personne_ne_cree_rien_et_n_envoie_rien(lieu, django_capture_on_commit_callbacks):
    from booking.models import InscriptionBenevole

    camille = personne_du_lieu(lieu.tenant)
    InscriptionBenevole.objects.create(besoin=lieu.besoin, user=camille)

    with patch("booking.views_benevolat.envoyer_confirmation_benevole") as tache_de_confirmation:
        with django_capture_on_commit_callbacks(execute=True):
            reponse = navigateur(lieu.admin).post(adresse_inscrire_une_personne(lieu.besoin), {"user": str(camille.pk)})

    assert reponse.status_code == 200
    assert InscriptionBenevole.objects.filter(besoin=lieu.besoin, user=camille).count() == 1
    tache_de_confirmation.delay.assert_not_called()


def test_un_pk_force_vers_un_compte_d_un_autre_lieu_est_refuse(lieu):
    from booking.models import InscriptionBenevole

    d_ailleurs = creer_utilisateur()

    reponse = navigateur(lieu.admin).post(adresse_inscrire_une_personne(lieu.besoin), {"user": str(d_ailleurs.pk)})

    assert reponse.status_code == 422
    assert not InscriptionBenevole.objects.filter(besoin=lieu.besoin).exists()


def test_un_planning_reserve_aux_adherents_accepte_quand_meme(lieu):
    """L'équipe décide qui elle inscrit : pas de contrôle d'adhésion."""
    from booking.models import InscriptionBenevole

    lieu.planning.adhesions_requises.add(creer_adhesion().produit)
    camille = personne_du_lieu(lieu.tenant)

    reponse = navigateur(lieu.admin).post(adresse_inscrire_une_personne(lieu.besoin), {"user": str(camille.pk)})

    assert reponse.status_code == 200
    assert InscriptionBenevole.objects.filter(besoin=lieu.besoin, user=camille).exists()


def test_un_besoin_passe_est_refuse(lieu):
    from booking.models import BesoinBenevole, InscriptionBenevole

    besoin_passe = BesoinBenevole.objects.create(
        planning=lieu.planning, tache=lieu.besoin.tache, date=lieu.aujourd_hui - datetime.timedelta(days=2),
    )
    camille = personne_du_lieu(lieu.tenant)

    reponse = navigateur(lieu.admin).post(adresse_inscrire_une_personne(besoin_passe), {"user": str(camille.pk)})

    assert reponse.status_code == 422
    assert not InscriptionBenevole.objects.filter(besoin=besoin_passe).exists()


# ---------------------------------------------------------------------------
# Personne nouvelle / New person
# ---------------------------------------------------------------------------

def test_email_inconnu_cree_le_compte_rattache_au_lieu_sans_mail_de_connexion(lieu):
    from AuthBillet.models import TibilletUser
    from booking.models import InscriptionBenevole

    email = f"nouvelle.{identifiant_unique()}@mock.test"
    with patch("AuthBillet.utils.sender_mail_connect") as mail_de_connexion:
        reponse = navigateur(lieu.admin).post(
            adresse_inscrire_une_personne(lieu.besoin), {"email": email, "prenom": "Nina", "nom": "Simone"},
        )

    assert reponse.status_code == 200
    nouvelle = TibilletUser.objects.get(email=email)
    assert (nouvelle.first_name, nouvelle.last_name) == ("Nina", "Simone")
    assert lieu.tenant in nouvelle.client_achat.all()
    assert InscriptionBenevole.objects.filter(besoin=lieu.besoin, user=nouvelle).exists()
    mail_de_connexion.assert_not_called()


def test_email_connu_ne_reecrit_pas_le_nom_existant(lieu):
    from booking.models import InscriptionBenevole

    camille = personne_du_lieu(lieu.tenant, prenom="Camille", nom="Martin")

    reponse = navigateur(lieu.admin).post(
        adresse_inscrire_une_personne(lieu.besoin), {"email": camille.email, "prenom": "Autre", "nom": "Autre"},
    )

    assert reponse.status_code == 200
    camille.refresh_from_db()
    assert (camille.first_name, camille.last_name) == ("Camille", "Martin")
    assert InscriptionBenevole.objects.filter(besoin=lieu.besoin, user=camille).exists()


@pytest.mark.parametrize("donnees", [
    {"email": "", "prenom": "Nina", "nom": "Simone"},
    {"email": "nina@mock.test", "prenom": "", "nom": "Simone"},
    {"email": "nina@mock.test", "prenom": "Nina", "nom": " "},
    {"email": "pas-un-email", "prenom": "Nina", "nom": "Simone"},
    {"email": "nina@mock.test", "prenom": "Nina\nX", "nom": "Simone"},
])
def test_creation_incomplete_refusee_dans_la_fenetre(lieu, donnees):
    from booking.models import InscriptionBenevole

    reponse = navigateur(lieu.admin).post(adresse_inscrire_une_personne(lieu.besoin), donnees)

    assert reponse.status_code == 422
    assert reponse["HX-Retarget"] == "#benevolat-modale-contenu"
    assert not InscriptionBenevole.objects.filter(besoin=lieu.besoin).exists()


def test_email_marque_en_erreur_rend_422(lieu):
    from booking.models import InscriptionBenevole

    en_erreur = personne_du_lieu(lieu.tenant)
    en_erreur.email_error = True
    en_erreur.save(update_fields=["email_error"])

    reponse = navigateur(lieu.admin).post(
        adresse_inscrire_une_personne(lieu.besoin), {"email": en_erreur.email, "prenom": "A", "nom": "B"},
    )

    assert reponse.status_code == 422
    assert "Cet email ne fonctionne pas" in reponse.content.decode()
    assert not InscriptionBenevole.objects.filter(besoin=lieu.besoin).exists()


def test_le_mail_de_l_equipe_dit_l_equipe_t_a_inscrit_et_porte_le_lien(lieu):
    from django.template.loader import render_to_string

    html = render_to_string("booking/benevolat/emails/confirmation.html", {
        "title": "T", "organisation": "Lespass", "image_url_place": "", "besoin": lieu.besoin, "plage": "18h–21h",
        "par_l_equipe": True, "url_du_planning": "https://x/", "url_de_mes_creneaux": "https://x/m/",
        "url_de_desistement": "https://x/booking/benevolat/desistement/JETON/",
    })

    assert "Lespass t'a inscrit·e" in html
    assert "/booking/benevolat/desistement/JETON/" in html


# ---------------------------------------------------------------------------
# Relecture du 2026-10-16 / 2026-10-16 review
# ---------------------------------------------------------------------------

def test_un_superuser_a_les_droits_de_l_equipe(lieu):
    """Même règle que l'admin du projet (TenantAdminPermissionWithRequest)."""
    from booking.models import InscriptionBenevole

    superuser = creer_utilisateur()
    superuser.is_superuser = True
    superuser.save(update_fields=["is_superuser"])
    camille = personne_du_lieu(lieu.tenant)

    html = navigateur(superuser).get(f"/booking/benevolat/{lieu.planning.slug}/").content.decode()
    reponse = navigateur(superuser).post(adresse_inscrire_une_personne(lieu.besoin), {"user": str(camille.pk)})

    assert f'data-testid="benevolat-inscrire-quelquun-{lieu.besoin.pk}"' in html
    assert reponse.status_code == 200
    assert InscriptionBenevole.objects.filter(besoin=lieu.besoin, user=camille).exists()


def test_un_admin_inactif_n_a_pas_les_droits(lieu):
    lieu.admin.is_active = False
    lieu.admin.save(update_fields=["is_active"])

    assert navigateur(lieu.admin).get(adresse_chercher(lieu.besoin, "Cam")).status_code == 403


def test_un_email_en_erreur_ne_rattache_pas_le_compte_au_lieu(lieu):
    """get_or_create_user rattache avant de tester email_error : le rattachement est annulé."""
    d_ailleurs = creer_utilisateur()
    d_ailleurs.email_error = True
    d_ailleurs.save(update_fields=["email_error"])

    reponse = navigateur(lieu.admin).post(
        adresse_inscrire_une_personne(lieu.besoin), {"email": d_ailleurs.email, "prenom": "A", "nom": "B"},
    )

    assert reponse.status_code == 422
    assert lieu.tenant not in d_ailleurs.client_achat.all()


def test_le_toast_porte_l_email_et_le_bouton_demande_confirmation(lieu):
    camille = personne_du_lieu(lieu.tenant, prenom="Quentina")

    html = navigateur(lieu.admin).get(adresse_chercher(lieu.besoin, "Quentina")).content.decode()
    reponse = navigateur(lieu.admin).post(adresse_inscrire_une_personne(lieu.besoin), {"user": str(camille.pk)})

    assert "hx-confirm=" in html and camille.email in html
    assert camille.email in reponse["HX-Trigger"]
