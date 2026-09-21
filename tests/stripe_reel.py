"""
Stripe RÉEL en mode test : outils partagés par les tests pytest et E2E.
/ REAL Stripe in test mode: tools shared by pytest and E2E tests.

LOCALISATION : tests/stripe_reel.py

Ce module donne deux choses.
/ This module provides two things.

1. Des outils pour parler au VRAI Stripe, en mode test :
   - `preparer_stripe_mode_test()` pose la clé racine et REFUSE toute clé qui n'est pas
     une clé de test. Elle renvoie le compte Stripe Connect du lieu courant.
   - `payer_avec_la_carte_de_test()` fait un vrai paiement, côté serveur, sans navigateur.
   - `montants_rembourses_chez_stripe()` lit les vrais remboursements d'un paiement.
   / Tools to talk to the REAL Stripe in test mode (live keys are refused).

2. Le lancement « sur demande » des tests qui appellent le vrai Stripe :
   ils ne tournent qu'avec STRIPE_REEL=1 (make test-stripe, make e2e-stripe).
   Sans la variable, ils sont ignorés, et un encadré rouge les nomme en fin de run.
   / On-demand runs: real-Stripe tests only run with STRIPE_REEL=1. Otherwise they
   are skipped, and a red box names them at the end of the run.

Utilisé par / Used by :
- tests/pytest/conftest.py et tests/e2e/conftest.py (lancement sur demande) ;
- tests/pytest/test_stripe_reel_remboursement.py ;
- tests/e2e/test_renouvellement_adhesion_recurrente.py (dans le code passé à django_shell).

Les fonctions Stripe s'appellent dans le contexte du lieu (tenant_context) : elles lisent
sa Configuration.
/ Stripe functions are called inside the place's context (tenant_context).
"""

import os

import pytest
import stripe

# La variable qui demande les tests Stripe réel, pour les deux suites.
# / The variable that requests real-Stripe tests, for both suites.
VARIABLE_STRIPE_REEL = "STRIPE_REEL"

# Moyen de paiement de test fourni par Stripe : une carte Visa qui accepte tout paiement.
# / Test payment method provided by Stripe: a Visa card that accepts any payment.
CARTE_DE_TEST_VISA = "pm_card_visa"

# Tests ignorés faute de STRIPE_REEL=1, relus par le résumé de fin de run.
# / Tests skipped for lack of STRIPE_REEL=1, read back by the end-of-run summary.
_tests_stripe_reel_non_joues = []


# ---------------------------------------------------------------------------
# Parler au vrai Stripe / Talk to the real Stripe
# ---------------------------------------------------------------------------


def preparer_stripe_mode_test():
    """Pose la clé Stripe racine et renvoie le compte Connect du lieu courant.
    / Sets the root Stripe key and returns the current place's Connect account.

    Refuse toute clé qui n'est pas une clé de TEST : un test ne doit jamais toucher
    un vrai compte, ni de vrais clients.
    / Refuses any key that is not a TEST key: a test must never touch a real account.
    """
    from BaseBillet.models import Configuration
    from root_billet.models import RootConfiguration

    cle_racine = RootConfiguration.get_solo().get_stripe_api() or ""
    if not cle_racine.startswith("sk_test_"):
        raise RuntimeError(
            "La clé Stripe racine n'est pas une clé de TEST (sk_test_…). "
            "Refus : un test ne touche jamais un vrai compte Stripe."
        )
    stripe.api_key = cle_racine

    compte_connect = Configuration.get_solo().get_stripe_connect_account()
    if not compte_connect:
        raise RuntimeError(
            "Le lieu n'a pas de compte Stripe Connect : impossible de payer chez Stripe."
        )
    return compte_connect


def payer_avec_la_carte_de_test(montant_en_centimes, compte_connect, description):
    """Fait un VRAI paiement en mode test, sur le compte Connect du lieu.
    / Makes a REAL test-mode payment, on the place's Connect account.

    Le paiement est confirmé côté serveur avec la carte Visa de test : pas de navigateur,
    pas de session Checkout. L'argent (de test) est réellement encaissé chez Stripe.
    / Confirmed server-side with the test Visa card: no browser, no Checkout session.

    :return: le PaymentIntent Stripe, au statut « succeeded ».
    """
    paiement_intent = stripe.PaymentIntent.create(
        amount=montant_en_centimes,
        currency="eur",
        payment_method=CARTE_DE_TEST_VISA,
        payment_method_types=["card"],
        confirm=True,
        description=description,
        stripe_account=compte_connect,
    )
    if paiement_intent.status != "succeeded":
        raise RuntimeError(
            f"Le paiement de test n'a pas abouti chez Stripe (statut : {paiement_intent.status})."
        )
    return paiement_intent


def montants_rembourses_chez_stripe(payment_intent_id, compte_connect):
    """Montants (en centimes) des remboursements réussis d'un paiement, lus chez Stripe.
    / Amounts (in cents) of a payment's succeeded refunds, read at Stripe.

    Du plus ancien au plus récent. / Oldest first.
    """
    remboursements = stripe.Refund.list(
        payment_intent=payment_intent_id,
        limit=100,
        stripe_account=compte_connect,
    )

    # Stripe renvoie le plus récent en premier : on remet la liste dans l'ordre des remboursements.
    # / Stripe returns the most recent first: put the list back in refund order.
    montants = []
    for remboursement in reversed(remboursements.data):
        if remboursement.status == "succeeded":
            montants.append(remboursement.amount)
    return montants


def etat_du_paiement_chez_stripe(payment_intent_id, compte_connect):
    """Ce que Stripe sait d'un paiement : montant encaissé, montant remboursé, en totalité ou non.
    / What Stripe knows about a payment: captured amount, refunded amount, fully or not.

    On lit les charges (Charge.list), pas le PaymentIntent : la fixture mock_stripe remplace
    stripe.PaymentIntent.retrieve (tests/PIEGES.md, piège 12.18).
    / Reads the charges, not the PaymentIntent: mock_stripe replaces PaymentIntent.retrieve.

    :return: {"montant_encaisse": int, "montant_rembourse": int, "rembourse_en_totalite": bool}
             (montants en centimes / amounts in cents)
    """
    charges = stripe.Charge.list(
        payment_intent=payment_intent_id,
        stripe_account=compte_connect,
    )

    montant_encaisse = 0
    montant_rembourse = 0
    rembourse_en_totalite = True
    for charge in charges.data:
        if charge.status != "succeeded":
            continue
        montant_encaisse += charge.amount_captured
        montant_rembourse += charge.amount_refunded
        if not charge.refunded:
            rembourse_en_totalite = False

    return {
        "montant_encaisse": montant_encaisse,
        "montant_rembourse": montant_rembourse,
        "rembourse_en_totalite": rembourse_en_totalite,
    }


# ---------------------------------------------------------------------------
# Lancement sur demande / On-demand runs
# ---------------------------------------------------------------------------


def stripe_reel_est_demande():
    """Les tests Stripe réel sont-ils demandés (STRIPE_REEL=1) ?
    / Are real-Stripe tests requested (STRIPE_REEL=1)?

    La variable est posée par scripts/lancer_tests.sh (make test-stripe, make e2e-stripe).
    / The variable is set by scripts/lancer_tests.sh.
    """
    return os.environ.get(VARIABLE_STRIPE_REEL) == "1"


def ignorer_les_tests_stripe_reel_non_demandes(items, nom_du_marqueur):
    """Ignore les tests portant `nom_du_marqueur` quand STRIPE_REEL=1 n'est pas posé.
    / Skips tests carrying `nom_du_marqueur` when STRIPE_REEL=1 is not set.

    À appeler depuis `pytest_collection_modifyitems` d'un conftest.
    / To be called from a conftest's `pytest_collection_modifyitems`.
    """
    if stripe_reel_est_demande():
        return

    raison = pytest.mark.skip(
        reason=(
            f"Stripe réel non demandé ({VARIABLE_STRIPE_REEL}!=1) — "
            "lancer make test-stripe ou make e2e-stripe."
        ),
    )
    for item in items:
        if item.get_closest_marker(nom_du_marqueur):
            _tests_stripe_reel_non_joues.append(item.nodeid)
            item.add_marker(raison)


def afficher_les_tests_stripe_reel_non_joues(terminalreporter):
    """Encadré rouge en fin de run : les tests Stripe réel qui n'ont PAS tourné.
    / Red box at the end of the run: the real-Stripe tests that did NOT run.

    Sans lui, « 12 passed, 2 skipped » se lit comme un succès complet, alors qu'un parcours
    de paiement n'a pas été vérifié. La liste est vidée après affichage : si deux conftests
    appellent cette fonction dans le même run, l'encadré n'apparaît qu'une fois.
    / Without it, "12 passed, 2 skipped" reads as full success. The list is emptied after
    display, so the box appears once even if two conftests call this function.

    À appeler depuis `pytest_terminal_summary` d'un conftest.
    / To be called from a conftest's `pytest_terminal_summary`.
    """
    if not _tests_stripe_reel_non_joues:
        return

    terminalreporter.write_sep(
        "=", "PARCOURS DE PAIEMENT NON VÉRIFIÉS (Stripe réel)", red=True, bold=True
    )
    terminalreporter.write_line(
        f"{len(_tests_stripe_reel_non_joues)} test(s) IGNORÉS faute de {VARIABLE_STRIPE_REEL}=1 "
        "(make test-stripe / make e2e-stripe).",
        red=True,
        bold=True,
    )
    for identifiant in _tests_stripe_reel_non_joues:
        terminalreporter.write_line(f"  - {identifiant}", red=True)
    _tests_stripe_reel_non_joues.clear()
