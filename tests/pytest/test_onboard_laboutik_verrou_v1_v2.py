"""
tests/pytest/test_onboard_laboutik_verrou_v1_v2.py — Une caisse V1 ne s'appaire pas sur un lieu V2.
tests/pytest/test_onboard_laboutik_verrou_v1_v2.py — A V1 POS cannot pair with a V2 venue.

POURQUOI / WHY :
Un lieu ne peut pas heberger a la fois la caisse LaBoutik V2 (integree a Lespass, monnaie
dans `fedow_core` local) et une caisse LaBoutik V1 (conteneur separe, monnaie dans le Fedow
distant). Les deux tiennent la monnaie dans un moteur different et rien ne reconcilie les
deux soldes.
/ A venue cannot host both the V2 cash register (money in the local fedow_core) and a V1 POS
(money in the remote Fedow). Nothing reconciles the two balances.

DEUX VERROUS, DANS CET ORDRE (ApiBillet/views.py, `Onboard_laboutik`) :
1. Le verrou de moteur : un lieu sur le moteur V2 (`Client.moteur_monnaie == "v2"`) n'a
   jamais de caisse V1 → 409, `code = "lieu_en_moteur_v2"` (spec 15, decision I1 ; teste
   aussi dans test_verrou_moteur_legacy.py, test 23).
2. Le verrou des modules : un lieu legacy dont un module V2 est reste allume en base
   (caisse, kiosk, monnaie locale) → 409, `code = "modules_v2_actifs"`.
/ Two locks, in this order: the engine lock (v2 venue), then the module lock (legacy venue
with a V2 flag still on).

Le verrou des modules regarde TROIS modules, pas seulement `module_caisse` : le handshake
V1 pose une cle RSA cashless sur la place Fedow, ce qui retire a Lespass le droit d'appeler
Fedow avec sa seule cle de place. Le kiosk et la monnaie locale tombent alors en 403 tout
autant que la caisse.
/ The V1 handshake sets a cashless RSA key on the Fedow place, revoking Lespass' key-only
access: kiosk and local currency break as much as the register. Hence THREE modules checked.

Les verrous sont **inconditionnels** : contrairement au garde « deja appaire » plus bas dans
la vue, ils ne sont PAS desarmes en DEBUG. C'est en developpement qu'on monte le banc V1/V2,
donc c'est la qu'ils doivent proteger.
/ The locks are unconditional, NOT disabled in DEBUG: the V1/V2 bench lives in development.

SIMULATIONS
- Lieu dedie `test_verrou_moteur_legacy` (`FastTenantTestCase`, schema clone, partage
  avec test_verrou_moteur_legacy.py). Jamais `lespass` ni un lieu de demo.
- Le moteur du lieu est pose par `update()` dans la transaction du test (annulee a la fin).
  Le middleware relit le `Client` a chaque requete : il voit la valeur posee.
- La `Configuration` est un objet EN MEMOIRE rendu par `get_solo()` patche ; `save()` est
  patche aussi. Rien n'est ecrit dans la base ni dans memcached (tests/PIEGES.md 13.5).
/ Dedicated test venue; engine set by update(); in-memory Configuration; nothing written.

Lancement / Run:
    make test ARGS="tests/pytest/test_onboard_laboutik_verrou_v1_v2.py"
"""

from unittest.mock import patch

from django.test import override_settings
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from AuthBillet.models import TibilletUser
from BaseBillet.models import Configuration
from Customers.models import Client

# Charge utile minimale. Les verrous agissent AVANT toute lecture de ces champs : ils n'ont
# pas besoin d'etre valides, seulement presents. L'email ne correspond a aucun admin du lieu.
# / Minimal payload. The locks fire BEFORE these fields are read.
CHARGE_UTILE = {
    "server_cashless": "https://laboutik.test.localhost",
    "key_cashless": "peu-importe",
    "pum_pem_cashless": "peu-importe",
    "email": "personne@test.loc",
}

# Les trois modules V2 que le verrou des modules regarde.
# / The three V2 modules the module lock checks.
MODULES_V2_DU_VERROU = ["module_caisse", "module_kiosk", "module_monnaie_locale"]


class TestOnboardLaboutikVerrouV1V2(FastTenantTestCase):
    """
    Les deux verrous de l'appairage LaBoutik V1, dans le lieu dedie.
    / The two LaBoutik V1 pairing locks, in the dedicated venue.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_verrou_moteur_legacy"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-verrou-moteur-legacy.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test verrou moteur legacy"

    def setUp(self):
        # Le lieu dedie est legacy pour tous les tests de ce fichier : seul un lieu legacy
        # atteint le verrou des modules. / The venue is legacy: only then the module lock.
        Client.objects.filter(pk=self.tenant.pk).update(
            moteur_monnaie=Client.MOTEUR_LEGACY
        )
        Configuration.clear_cache()

    def tearDown(self):
        Configuration.clear_cache()

    def configuration_en_memoire(self, modules_allumes):
        """
        Une `Configuration` en memoire, jamais enregistree : les trois modules V2 eteints
        sauf ceux de la liste, aucune caisse V1 deja branchee.
        / An in-memory Configuration: the three V2 modules off except the listed ones.
        """
        configuration = Configuration(
            pk=Configuration.singleton_instance_id,
            organisation="Test verrou moteur legacy",
            slug="test-verrou-moteur-legacy",
            server_cashless=None,
            key_cashless=None,
        )
        for nom_du_module in MODULES_V2_DU_VERROU:
            setattr(configuration, nom_du_module, nom_du_module in modules_allumes)
        return configuration

    def poster_onboard(self, configuration):
        """
        Poste un onboard LaBoutik sur le lieu dedie, par sa route HTTP.
        `get_solo()` rend la configuration en memoire ; `save()` est un faux.
        / Posts a LaBoutik onboard to the dedicated venue, through its HTTP route.
        """
        navigateur = TenantClient(self.tenant)
        with patch.object(Configuration, "get_solo", return_value=configuration):
            with patch.object(Configuration, "save", autospec=True):
                return navigateur.post("/api/onboard_laboutik/", CHARGE_UTILE)

    def test_onboard_refuse_si_un_module_v2_est_actif(self):
        """Lieu legacy : chacun des trois modules V2, actif seul, suffit a refuser.
        / Legacy venue: each of the three V2 modules, active on its own, refuses pairing."""
        for module_actif in MODULES_V2_DU_VERROU:
            reponse = self.poster_onboard(self.configuration_en_memoire([module_actif]))

            assert reponse.status_code == 409, (
                f"Avec {module_actif} actif, l'appairage V1 doit etre refuse en 409 "
                f"(recu : {reponse.status_code})."
            )
            corps = reponse.json()
            assert corps["code"] == "modules_v2_actifs", module_actif
            # La reponse nomme le module fautif : sans ca, le message cote LaBoutik n'est
            # pas actionnable. / The response names the offending module.
            assert module_actif in corps["modules"], module_actif

    def test_onboard_nomme_tous_les_modules_fautifs(self):
        """Lieu legacy : les trois modules actifs sont tous listes, pas seulement le premier.
        / Legacy venue: all three active modules are listed, not just the first one."""
        corps = self.poster_onboard(
            self.configuration_en_memoire(MODULES_V2_DU_VERROU)
        ).json()

        assert set(corps["modules"]) == set(MODULES_V2_DU_VERROU)

    def test_onboard_passe_le_verrou_si_aucun_module_v2(self):
        """Lieu legacy, modules eteints : les verrous laissent passer, la vue poursuit.
        / Legacy venue, modules off: the locks let the request through.

        On n'exerce pas le handshake complet (il faudrait Fedow, un admin de tenant et des
        cles RSA valides). La preuve du franchissement : la vue va CHERCHER l'admin du lieu
        correspondant a l'email envoye, et notre charge utile en porte un qui n'existe pas.
        L'exception `TibilletUser.DoesNotExist` prouve donc que les verrous ont laisse
        passer.
        / Proof of passage: the view looks up the venue admin matching the posted email,
        which our payload deliberately gets wrong.

        Si un jour la vue gere proprement un email d'admin inconnu (au lieu de laisser
        remonter l'exception en 500), ce test devra viser la nouvelle reponse. Ce sera un
        signal d'amelioration, pas une regression.
        / If the view ever handles an unknown admin email properly, retarget this assertion.
        """
        with self.assertRaises(TibilletUser.DoesNotExist):
            self.poster_onboard(self.configuration_en_memoire([]))

    def test_le_verrou_reste_actif_en_debug(self):
        """Le verrou des modules ne se desarme PAS en DEBUG, contrairement au garde « deja
        appaire ». / The module lock is NOT disabled in DEBUG.

        C'est la propriete qui compte : le banc V1/V2 se monte en developpement. Un verrou
        desarme en DEBUG ne protegerait jamais la seule situation ou on en a besoin.
        / That is the property that matters: the V1/V2 bench is built in development.
        """
        with override_settings(DEBUG=True):
            reponse = self.poster_onboard(
                self.configuration_en_memoire(["module_caisse", "module_monnaie_locale"])
            )

        assert reponse.status_code == 409
        assert reponse.json()["code"] == "modules_v2_actifs"

    def test_lieu_v2_refuse_avant_le_verrou_des_modules(self):
        """Lieu v2 avec des modules V2 allumes : c'est le verrou de moteur qui refuse, en
        premier (`lieu_en_moteur_v2`), en DEBUG aussi.
        / v2 venue with V2 modules on: the engine lock refuses first, in DEBUG too."""
        Client.objects.filter(pk=self.tenant.pk).update(moteur_monnaie=Client.MOTEUR_V2)

        with override_settings(DEBUG=True):
            reponse = self.poster_onboard(
                self.configuration_en_memoire(MODULES_V2_DU_VERROU)
            )

        assert reponse.status_code == 409
        assert reponse.json()["code"] == "lieu_en_moteur_v2"
