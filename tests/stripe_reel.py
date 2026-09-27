"""
Stripe RÉEL en mode test : outils partagés par les tests pytest et E2E.
/ REAL Stripe in test mode: tools shared by pytest and E2E tests.

LOCALISATION : tests/stripe_reel.py

Ce module donne des outils pour parler au VRAI Stripe, en mode test :
   - `preparer_stripe_mode_test()` pose la clé racine et REFUSE toute clé qui n'est pas
     une clé de test. Elle renvoie le compte Stripe Connect du lieu courant.
   - `payer_avec_la_carte_de_test()` fait un vrai paiement, côté serveur, sans navigateur.
   - `montants_rembourses_chez_stripe()` lit les vrais remboursements d'un paiement.
/ Tools to talk to the REAL Stripe in test mode (live keys are refused).

Les tests qui s'en servent (marqueur `stripe_reel`) tournent à chaque `make test` :
aucun n'est ignoré. Si Stripe n'est pas joignable, ou si la clé n'est pas une clé de
test, ils ÉCHOUENT.
/ Tests using them (`stripe_reel` marker) run on every `make test`: none is skipped.

Utilisé par / Used by :
- tests/pytest/test_stripe_reel_remboursement.py ;
- tests/e2e/test_renouvellement_adhesion_recurrente.py (dans le code passé à django_shell).

Les fonctions Stripe s'appellent dans le contexte du lieu (tenant_context) : elles lisent
sa Configuration.
/ Stripe functions are called inside the place's context (tenant_context).
"""

import stripe

# Moyen de paiement de test fourni par Stripe : une carte Visa qui accepte tout paiement.
# / Test payment method provided by Stripe: a Visa card that accepts any payment.
CARTE_DE_TEST_VISA = "pm_card_visa"

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
