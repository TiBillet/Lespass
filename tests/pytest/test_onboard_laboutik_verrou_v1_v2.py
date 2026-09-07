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

S'ajoute un effet de bord cote Fedow : le handshake V1 pose une cle RSA cashless sur la place,
ce qui retire a Lespass le droit d'appeler Fedow avec sa seule cle de place. Le kiosk et la
monnaie locale tombent alors en 403 tout autant que la caisse — d'ou les TROIS modules
verifies, et pas seulement `module_caisse`.
/ The V1 handshake sets a cashless RSA key on the Fedow place, revoking Lespass' key-only
access: kiosk and local currency break as much as the register. Hence THREE modules checked.

Le verrou est **inconditionnel** : contrairement au garde « deja appaire » juste en dessous
dans la vue, il n'est PAS desarme en DEBUG. C'est en developpement qu'on monte le banc V1/V2,
donc c'est la qu'il doit proteger.
/ The lock is unconditional, NOT disabled in DEBUG: the V1/V2 bench lives in development.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_onboard_laboutik_verrou_v1_v2.py -q
"""

import pytest
from django_tenants.utils import tenant_context

from Customers.models import Client


pytestmark = pytest.mark.django_db

# Charge utile minimale. Le verrou agit AVANT toute lecture de ces champs : ils n'ont pas
# besoin d'etre valides, seulement presents.
# / Minimal payload. The lock fires BEFORE these fields are read.
CHARGE_UTILE = {
    "server_cashless": "https://laboutik.test.localhost",
    "key_cashless": "peu-importe",
    "pum_pem_cashless": "peu-importe",
    "email": "personne@test.loc",
}


def _poster_onboard(schema):
    """Poste un onboard LaBoutik sur le tenant donne, via son domaine.
    / Posts a LaBoutik onboard to the given tenant, through its domain."""
    from django.test import Client as DjangoClient

    navigateur = DjangoClient(HTTP_HOST=f"{schema}.tibillet.localhost")
    return navigateur.post("/api/onboard_laboutik/", CHARGE_UTILE)


@pytest.fixture
def modules_v2_du_tenant():
    """Pose l'etat des trois modules V2 sur un tenant, et le restaure apres le test.
    / Sets the three V2 modules on a tenant, restores them afterwards.

    La base de dev est partagee et `Configuration` est un singleton par schema : sans
    restauration, un test laisserait le lieu dans un etat qui fausserait les suivants.
    / The dev database is shared and Configuration is a per-schema singleton: without
    restoring, a test would leave the venue in a state that misleads the next ones.
    """
    etats_a_restaurer = []

    def poser(schema, caisse, kiosk, monnaie):
        from BaseBillet.models import Configuration

        tenant = Client.objects.get(schema_name=schema)
        with tenant_context(tenant):
            config = Configuration.get_solo()
            etats_a_restaurer.append(
                (schema, config.module_caisse, config.module_kiosk, config.module_monnaie_locale)
            )
            config.module_caisse = caisse
            config.module_kiosk = kiosk
            config.module_monnaie_locale = monnaie
            config.save()

    yield poser

    from BaseBillet.models import Configuration

    for schema, caisse, kiosk, monnaie in reversed(etats_a_restaurer):
        with tenant_context(Client.objects.get(schema_name=schema)):
            config = Configuration.get_solo()
            config.module_caisse = caisse
            config.module_kiosk = kiosk
            config.module_monnaie_locale = monnaie
            config.save()


@pytest.mark.parametrize(
    "module_actif",
    ["module_caisse", "module_kiosk", "module_monnaie_locale"],
)
def test_onboard_refuse_si_un_module_v2_est_actif(modules_v2_du_tenant, module_actif):
    """Chacun des trois modules V2, actif seul, suffit a refuser l'appairage.
    / Each of the three V2 modules, active on its own, is enough to refuse pairing."""
    modules_v2_du_tenant(
        "lespass",
        caisse=(module_actif == "module_caisse"),
        kiosk=(module_actif == "module_kiosk"),
        monnaie=(module_actif == "module_monnaie_locale"),
    )

    reponse = _poster_onboard("lespass")

    assert reponse.status_code == 409, (
        f"Avec {module_actif} actif, l'appairage V1 doit etre refuse en 409 "
        f"(recu : {reponse.status_code})."
    )
    corps = reponse.json()
    assert corps["code"] == "modules_v2_actifs"
    # La reponse nomme le module fautif : sans ca, le message cote LaBoutik n'est pas
    # actionnable. / The response names the offending module, else the LaBoutik-side
    # message is not actionable.
    assert module_actif in corps["modules"]


def test_onboard_nomme_tous_les_modules_fautifs(modules_v2_du_tenant):
    """Les trois modules actifs sont tous listes, pas seulement le premier rencontre.
    / All three active modules are listed, not just the first one found."""
    modules_v2_du_tenant("lespass", caisse=True, kiosk=True, monnaie=True)

    corps = _poster_onboard("lespass").json()

    assert set(corps["modules"]) == {"module_caisse", "module_kiosk", "module_monnaie_locale"}


def test_onboard_passe_le_verrou_si_aucun_module_v2(modules_v2_du_tenant):
    """Modules eteints : le verrou laisse passer, la vue poursuit son travail.
    / Modules off: the lock lets the request through and the view carries on.

    On n'exerce pas le handshake complet (il faudrait Fedow, un admin de tenant et des cles
    RSA valides). La preuve du franchissement est ailleurs : la vue va CHERCHER l'admin du
    tenant correspondant a l'email envoye, et notre charge utile en porte un qui n'existe
    pas. L'exception `TibilletUser.DoesNotExist` prouve donc que le verrou a laisse passer
    et que la vue a poursuivi son travail.
    / Proof of passage: the view looks up the tenant admin matching the posted email, which
    our payload deliberately gets wrong. TibilletUser.DoesNotExist proves the lock let it by.

    Si un jour la vue gere proprement un email d'admin inconnu (au lieu de laisser remonter
    l'exception en 500), ce test devra viser la nouvelle reponse. Ce sera un signal
    d'amelioration, pas une regression.
    / If the view ever handles an unknown admin email properly, retarget this assertion.
    """
    from AuthBillet.models import TibilletUser

    modules_v2_du_tenant("lespass", caisse=False, kiosk=False, monnaie=False)

    with pytest.raises(TibilletUser.DoesNotExist):
        _poster_onboard("lespass")


def test_le_verrou_reste_actif_en_debug(modules_v2_du_tenant, settings):
    """Le verrou ne se desarme PAS en DEBUG, contrairement au garde « deja appaire ».
    / The lock is NOT disabled in DEBUG, unlike the "already paired" guard.

    C'est la propriete qui compte : le banc V1/V2 se monte en developpement. Un verrou
    desarme en DEBUG ne protegerait jamais la seule situation ou on en a besoin.
    / That is the property that matters: the V1/V2 bench is built in development.
    """
    settings.DEBUG = True
    modules_v2_du_tenant("lespass", caisse=True, kiosk=False, monnaie=True)

    reponse = _poster_onboard("lespass")

    assert reponse.status_code == 409
    assert reponse.json()["code"] == "modules_v2_actifs"
