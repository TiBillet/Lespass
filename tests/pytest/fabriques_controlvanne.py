"""
Fabriques pour les tests des tireuses connectées (controlvanne).
/ Factories for the connected tap tests (controlvanne).

LOCALISATION : tests/pytest/fabriques_controlvanne.py

Ce module n'est pas un fichier de tests (pas de préfixe test_) : pytest ne le collecte pas.
Les fichiers de tests l'importent : `from fabriques_controlvanne import ...`.
/ Not a test file (no test_ prefix): pytest does not collect it. Test files import it.

Depuis le point 1.4 de l'audit (CHANGELOG/a traiter/controlvanne-audit-securite-facturation.md),
une clé API de tireuse DOIT appartenir au terminal (Raspberry Pi) de la tireuse visée :
- une clé sans compte est refusée (403) ;
- une clé d'un autre terminal est refusée (403).
Les tests ne peuvent donc plus partager une clé « nue » entre plusieurs tireuses.
/ Since audit point 1.4, a tap API key MUST belong to the target tap's terminal.
"""

import uuid
from unittest import mock

import pytest
from django.utils.text import slugify
from django_tenants.utils import tenant_context


def cle_api_de_la_tireuse(tenant, tireuse):
    """
    Appaire le terminal de la tireuse comme le fait discovery, et renvoie sa clé API.
    / Pairs the tap's terminal like discovery does, and returns its API key.

    Même chose que discovery/views.py (_remplir_le_terminal) :
    1. un compte TermUser (rôle tireuse) est posé sur le terminal de la tireuse ;
    2. une TireuseAPIKey est créée pour ce compte.

    Le compte est réutilisé d'un lancement à l'autre (email tiré du nom de la
    tireuse) : la base de dev n'est pas remise à zéro entre deux runs.
    Une nouvelle clé remplace l'ancienne à chaque appel : on ne peut pas relire
    une clé existante (seul son hash est stocké).
    / The account is reused across runs; a new key replaces the old one on each call.

    tenant_context et pas schema_context : TermUser.save() lit connection.tenant.
    / tenant_context, not schema_context: TermUser.save() reads connection.tenant.

    :param tenant: Client — le lieu de la tireuse
    :param tireuse: TireuseBec — la tireuse (son Terminal est créé par le signal post_save)
    :return: str — la clé API à mettre dans « Authorization: Api-Key <clé> »
    """
    with tenant_context(tenant):
        from AuthBillet.models import TermUser, TibilletUser
        from controlvanne.models import TireuseAPIKey, TireuseBec
        from laboutik.models import Terminal

        tireuse_a_jour = TireuseBec.objects.select_related("terminal").get(
            pk=tireuse.pk
        )
        terminal_de_la_tireuse = tireuse_a_jour.terminal

        email_du_compte = f"test-{slugify(tireuse_a_jour.nom_tireuse)}@terminals.test"
        compte_du_terminal = TermUser.objects.filter(email=email_du_compte).first()
        if compte_du_terminal is None:
            compte_du_terminal = TermUser.objects.create(
                email=email_du_compte,
                username=email_du_compte,
                first_name=tireuse_a_jour.nom_tireuse,
                terminal_role=TibilletUser.ROLE_TIREUSE,
                accept_newsletter=False,
            )

        # Un terminal d'un run précédent peut encore porter ce compte (OneToOne)
        # / A terminal from a previous run may still hold this account (OneToOne)
        Terminal.objects.filter(term_user=compte_du_terminal).exclude(
            pk=terminal_de_la_tireuse.pk
        ).update(term_user=None)
        terminal_de_la_tireuse.term_user = compte_du_terminal
        terminal_de_la_tireuse.save(update_fields=["term_user"])

        TireuseAPIKey.objects.filter(user=compte_du_terminal).delete()
        _cle_en_base, cle_api = TireuseAPIKey.objects.create_key(
            name=f"test-{slugify(tireuse_a_jour.nom_tireuse)}",
            user=compte_du_terminal,
        )
        return cle_api


def donner_une_carte_primaire_au_lieu(lieu):
    """
    Le lieu a au moins une carte primaire : créée si le schéma n'en a aucune (annulée
    avec la transaction du test). Sans elle, la tireuse refuse de servir : c'est la
    carte primaire qui signe ses débits sur l'ancien Fedow (controlvanne/billing.py).
    / The venue has at least one primary card; without one, the tap refuses to pour.

    :param lieu: Client (tenant)
    """
    from laboutik.models import CartePrimaire
    from QrcodeCashless.models import CarteCashless

    with tenant_context(lieu):
        if CartePrimaire.objects.exists():
            return
        tag_de_la_carte_primaire = uuid.uuid4().hex[:8].upper()
        carte_du_responsable = CarteCashless.objects.create(
            tag_id=tag_de_la_carte_primaire,
            number=tag_de_la_carte_primaire,
            uuid=uuid.uuid4(),
        )
        CartePrimaire.objects.create(carte=carte_du_responsable)


@pytest.fixture
def carte_primaire_du_lieu_confirmee_par_l_ancien_fedow(tenant, db):
    """
    Le lieu a une carte primaire, et l'ancien Fedow la confirme
    (`_verifier_carte_primaire_aupres_de_l_ancien_fedow` simulée) : la tireuse peut
    servir et débiter le FED. À importer dans un fichier de tests, puis à activer par
    `pytestmark = pytest.mark.usefixtures(...)` ou en argument.
    / The venue has a primary card, confirmed by the old Fedow.
    """
    donner_une_carte_primaire_au_lieu(tenant)
    with mock.patch(
        "laboutik.views._verifier_carte_primaire_aupres_de_l_ancien_fedow",
        return_value=None,
    ):
        yield
