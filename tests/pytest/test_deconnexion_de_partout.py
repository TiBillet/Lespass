"""
Tests de la déconnexion de partout.
/ Tests of the "log out everywhere" feature.

LOCALISATION : tests/pytest/test_deconnexion_de_partout.py
Code testé :
- AuthBillet/models.py : TibilletUser.jeton_de_session,
  TibilletUser._get_session_auth_hash, TibilletUser.deconnecter_de_partout ;
- BaseBillet/views.py : deconnexion (POST /deconnexion/ sur le lieu) ;
- Administration/admin/site.py : StaffAdminSite.logout (POST /admin/logout/).

COMMENT ÇA MARCHE :
Django garde dans chaque session une empreinte calculée depuis le compte. À chaque
requête, il la compare à l'empreinte du compte. Si elles diffèrent, la session est
vidée : la personne est anonyme. Changer `jeton_de_session` change l'empreinte du
compte, donc ferme toutes ses sessions (tous les lieux et le guichet).
/ Each session stores a hash computed from the account. Changing
`jeton_de_session` changes that hash, so every session of the account dies.

QUI VISE QUOI :
- le lieu : client de test avec HTTP_HOST="lespass.tibillet.localhost" ;
- le guichet : client de test avec HTTP_HOST="tibillet.localhost" (tenant public).
La table des sessions est unique (django.contrib.sessions est en SHARED_APPS).

COMMENT ON SAIT QU'UN CLIENT EST CONNECTÉ :
- sur le lieu : `GET /connexion/?next=/page/` renvoie vers `/page/` si la personne
  est connectée, vers le guichet sinon ;
- sur le guichet : `GET /sso/?lieu=...&state=...` renvoie vers le lieu avec un
  ticket (302) si la personne est connectée, affiche le formulaire (200) sinon.
/ Venue: /connexion/ redirects to next if logged in. Desk: /sso/ redirects (302)
if logged in, shows the form (200) otherwise.

PIÈGES (tests/PIEGES.md) :
- Comptes créés dans `tenant_context`, pas `schema_context` (FakeTenant).
- `django_db` : tout est annulé en fin de test (comptes, sessions). Ne jamais
  utiliser le compte admin partagé de la base de dev : le déconnecter de partout
  fermerait aussi les sessions des autres tests et du navigateur du mainteneur.
/ tenant_context; django_db rollback; never the shared dev admin account.
"""

from uuid import uuid4

import pytest
from django.contrib.auth.base_user import AbstractBaseUser
from django.test import Client as ClientDeTest
from django.test import override_settings
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser

pytestmark = pytest.mark.django_db

DOMAINE_DU_LIEU = "lespass.tibillet.localhost"
DOMAINE_DU_GUICHET = "tibillet.localhost"

PAGE_DE_RETOUR = "/page-de-retour-du-test/"


# --- Petites fonctions / Helpers ---


def creer_un_compte(tenant, administrateur_du_lieu=False):
    """
    Crée un compte humain activé, dans le contexte du lieu.
    / Creates an active human account, in the venue context.
    """
    email = f"deconnexion-{uuid4().hex[:8]}@test.local"
    with tenant_context(tenant):
        compte = TibilletUser.objects.create(
            email=email,
            username=email,
            espece=TibilletUser.TYPE_HUM,
            is_active=True,
            email_valid=True,
            is_staff=administrateur_du_lieu,
        )
        compte.client_achat.add(tenant)
        if administrateur_du_lieu:
            compte.client_admin.add(tenant)
    return compte


def client_connecte(domaine, compte):
    """Client de test connecté au compte, sur ce domaine. / Logged-in test client."""
    client = ClientDeTest(HTTP_HOST=domaine)
    client.force_login(compte)
    return client


def est_connecte_sur_le_lieu(client_du_lieu):
    """
    True si la requête suivante du client se fait en personne connectée.
    `/connexion/` renvoie vers `next` seulement pour une personne connectée.
    / True if the client's next request is authenticated.
    """
    reponse = client_du_lieu.get("/connexion/", {"next": PAGE_DE_RETOUR})
    assert reponse.status_code == 302
    return reponse.url == PAGE_DE_RETOUR


def est_connecte_sur_le_guichet(client_du_guichet):
    """
    True si le guichet donne tout de suite un ticket (personne connectée).
    / True if the desk hands out a ticket at once (logged in).
    """
    reponse = client_du_guichet.get(
        "/sso/", {"lieu": DOMAINE_DU_LIEU, "state": "state-du-test"}
    )
    if reponse.status_code == 302:
        return True
    assert reponse.status_code == 200
    return False


# =============================================================================
# L'empreinte de session / The session hash
# =============================================================================


def test_un_compte_au_jeton_vide_garde_l_empreinte_de_django():
    """
    Jeton vide → même empreinte que Django : le déploiement ne déconnecte personne.
    Vrai aussi pour l'empreinte de secours (SECRET_KEY_FALLBACKS).
    / Empty token → Django's own hash, also for the fallback secrets.
    """
    compte = TibilletUser(email="empreinte@test.local", password="mot-de-passe-haché")

    assert compte.jeton_de_session == ""
    assert compte.get_session_auth_hash() == AbstractBaseUser._get_session_auth_hash(
        compte
    )
    with override_settings(SECRET_KEY_FALLBACKS=["ancienne-cle-secrete-du-test"]):
        empreintes_de_secours = list(compte.get_session_auth_fallback_hash())
    assert empreintes_de_secours == [
        AbstractBaseUser._get_session_auth_hash(
            compte, secret="ancienne-cle-secrete-du-test"
        )
    ]


def test_deconnecter_de_partout_change_l_empreinte_et_l_enregistre(tenant):
    """
    `deconnecter_de_partout()` pose un nouveau jeton, l'enregistre en base, et
    l'empreinte du compte change. Deux appels donnent deux empreintes différentes.
    / A new token is saved; the hash changes, and changes again on a second call.
    """
    compte = creer_un_compte(tenant)
    empreinte_avant = compte.get_session_auth_hash()

    compte.deconnecter_de_partout()
    empreinte_apres_le_premier_appel = compte.get_session_auth_hash()
    compte.refresh_from_db()

    assert len(compte.jeton_de_session) == 64
    assert compte.get_session_auth_hash() == empreinte_apres_le_premier_appel
    assert empreinte_apres_le_premier_appel != empreinte_avant

    compte.deconnecter_de_partout()
    assert compte.get_session_auth_hash() != empreinte_apres_le_premier_appel


# =============================================================================
# Les déconnexions / Logging out
# =============================================================================


def test_deconnexion_sur_le_lieu_ferme_les_autres_sessions_et_le_guichet(tenant):
    """
    Trois sessions du même compte : deux navigateurs sur le lieu, un sur le
    guichet. `/deconnexion/` sur le premier → les deux autres sont anonymes à leur
    requête suivante.
    / Three sessions of one account; /deconnexion/ on one closes the two others.
    """
    compte = creer_un_compte(tenant)
    premier_navigateur = client_connecte(DOMAINE_DU_LIEU, compte)
    second_navigateur = client_connecte(DOMAINE_DU_LIEU, compte)
    navigateur_du_guichet = client_connecte(DOMAINE_DU_GUICHET, compte)
    assert est_connecte_sur_le_lieu(second_navigateur)
    assert est_connecte_sur_le_guichet(navigateur_du_guichet)

    reponse = premier_navigateur.post("/deconnexion/")

    assert reponse.status_code == 302
    assert not est_connecte_sur_le_lieu(premier_navigateur)
    assert not est_connecte_sur_le_lieu(second_navigateur)
    assert not est_connecte_sur_le_guichet(navigateur_du_guichet)


def test_une_nouvelle_connexion_apres_la_deconnexion_reste_connectee(tenant):
    """
    Après la déconnexion de partout, une nouvelle connexion prend la nouvelle
    empreinte : elle reste connectée.
    / A login after "log out everywhere" stays logged in.
    """
    compte = creer_un_compte(tenant)
    premier_navigateur = client_connecte(DOMAINE_DU_LIEU, compte)
    premier_navigateur.post("/deconnexion/")
    compte.refresh_from_db()

    nouveau_navigateur = client_connecte(DOMAINE_DU_LIEU, compte)

    assert est_connecte_sur_le_lieu(nouveau_navigateur)


def test_deconnexion_de_l_admin_ferme_les_autres_sessions(tenant):
    """
    Le bouton « Se déconnecter » de l'admin (POST /admin/logout/) ferme aussi
    toutes les sessions du compte.
    / The admin logout button closes every session of the account too.
    """
    administrateur = creer_un_compte(tenant, administrateur_du_lieu=True)
    navigateur_de_l_admin = client_connecte(DOMAINE_DU_LIEU, administrateur)
    autre_navigateur = client_connecte(DOMAINE_DU_LIEU, administrateur)
    navigateur_du_guichet = client_connecte(DOMAINE_DU_GUICHET, administrateur)
    assert est_connecte_sur_le_lieu(autre_navigateur)

    reponse = navigateur_de_l_admin.post("/admin/logout/")

    assert reponse.status_code == 200
    assert not est_connecte_sur_le_lieu(navigateur_de_l_admin)
    assert not est_connecte_sur_le_lieu(autre_navigateur)
    assert not est_connecte_sur_le_guichet(navigateur_du_guichet)


# =============================================================================
# Une page d'un autre site ne peut pas déconnecter / A third-party page cannot log out
# =============================================================================


@pytest.mark.parametrize("adresse_de_deconnexion", ["/deconnexion/", "/logout/"])
def test_un_get_sur_la_deconnexion_ne_deconnecte_personne(tenant, adresse_de_deconnexion):
    """
    Un GET (une image `<img src=".../deconnexion/">` sur un autre site) reçoit
    une 405. Les sessions du compte restent ouvertes, sur le lieu et le guichet.
    / A GET gets a 405; every session stays open.
    """
    compte = creer_un_compte(tenant)
    navigateur = client_connecte(DOMAINE_DU_LIEU, compte)
    navigateur_du_guichet = client_connecte(DOMAINE_DU_GUICHET, compte)

    reponse = navigateur.get(adresse_de_deconnexion)

    assert reponse.status_code == 405
    assert est_connecte_sur_le_lieu(navigateur)
    assert est_connecte_sur_le_guichet(navigateur_du_guichet)


def test_un_post_sans_jeton_csrf_ne_deconnecte_personne(tenant):
    """
    Un formulaire posté depuis un autre site n'a pas le jeton CSRF : 403, et
    la session reste ouverte.
    / A cross-site form has no CSRF token: 403, the session stays open.
    """
    compte = creer_un_compte(tenant)
    navigateur_qui_verifie_le_csrf = ClientDeTest(
        HTTP_HOST=DOMAINE_DU_LIEU, enforce_csrf_checks=True
    )
    navigateur_qui_verifie_le_csrf.force_login(compte)

    reponse = navigateur_qui_verifie_le_csrf.post("/deconnexion/")

    assert reponse.status_code == 403
    assert est_connecte_sur_le_lieu(navigateur_qui_verifie_le_csrf)


def test_un_get_sur_la_deconnexion_de_l_admin_ne_deconnecte_personne(tenant):
    """
    Django 4.2 accepte encore le GET sur /admin/logout/. StaffAdminSite.logout
    le refuse : 405, et les sessions restent ouvertes.
    / Django 4.2 still accepts GET on /admin/logout/; ours refuses it with a 405.
    """
    administrateur = creer_un_compte(tenant, administrateur_du_lieu=True)
    navigateur_de_l_admin = client_connecte(DOMAINE_DU_LIEU, administrateur)
    navigateur_du_guichet = client_connecte(DOMAINE_DU_GUICHET, administrateur)

    reponse = navigateur_de_l_admin.get("/admin/logout/")

    assert reponse.status_code == 405
    assert est_connecte_sur_le_lieu(navigateur_de_l_admin)
    assert est_connecte_sur_le_guichet(navigateur_du_guichet)
