"""
Tests C2 — répartition du débit legacy sur les articles, distinction fine des moyens.
/ C2 tests — legacy debit distribution over articles, fine-grained payment method split.

LOCALISATION : tests/pytest/test_c2_legacy_repartition.py

CE QUI EST TESTÉ / WHAT IS TESTED :
Quand on paie au POS avec une carte du réseau, le débit legacy (côté Fedow) peut puiser dans
PLUSIEURS assets : des TLF fédérés (monnaies locales d'autres lieux → `LOCAL_EURO`, gérées par les
LIEUX) et du FED (monnaie fédérée → `STRIPE_FED`, gérée par la COOPÉRATIVE). Le helper
`_repartir_legacy_sur_articles` répartit ces transactions sur les articles non couverts par les
locaux, en gardant chaque moyen de paiement DISTINCT — pour que la compta attribue chaque euro au
bon responsable.

Helper PUR (pas de DB, pas de réseau) → tests rapides sans fixtures.
/ PURE helper (no DB, no network) → fast tests without fixtures.
"""

from laboutik.views import _repartir_legacy_sur_articles, _decouper_lignes_complement
from BaseBillet.models import PaymentMethod

UUID_TLF = "11111111-1111-1111-1111-111111111111"  # un TLF fédéré (monnaie locale d'un autre lieu)
UUID_FED = (
    "22222222-2222-2222-2222-222222222222"  # le FED (monnaie fédérée de la coopérative)
)


def test_repartition_distingue_finement_tlf_et_fed():
    """Un panier couvert par 4 € de TLF fédéré + 1 € de FED : chaque part garde son moyen.
    / A cart covered by €4 federated TLF + €1 FED: each part keeps its own payment method.
    """
    article_un = {"name": "Article 1"}
    article_deux = {"name": "Article 2"}
    # 2 articles non couverts par les locaux : 3,00 € et 2,00 €.
    # / 2 articles not covered by locals: €3.00 and €2.00.
    lignes_complement = [
        (article_un, None, 300, None),
        (article_deux, None, 200, None),
    ]
    # Fedow a débité 4,00 € de TLF fédéré puis 1,00 € de FED (total 5,00 € = le complément).
    # / Fedow debited €4.00 federated TLF then €1.00 FED (total €5.00 = the complement).
    transactions_legacy = [
        (UUID_TLF, 400, PaymentMethod.LOCAL_EURO),
        (UUID_FED, 100, PaymentMethod.STRIPE_FED),
    ]

    lignes = _repartir_legacy_sur_articles(lignes_complement, transactions_legacy)

    # Article 1 (3 €) entièrement en TLF ; article 2 (2 €) en 1 € TLF + 1 € FED.
    # / Article 1 (€3) fully TLF; article 2 (€2) as €1 TLF + €1 FED.
    assert lignes == [
        (article_un, UUID_TLF, 300, PaymentMethod.LOCAL_EURO),
        (article_deux, UUID_TLF, 100, PaymentMethod.LOCAL_EURO),
        (article_deux, UUID_FED, 100, PaymentMethod.STRIPE_FED),
    ]
    # Invariant : tout le complément est couvert, ni plus ni moins.
    # / Invariant: the whole complement is covered, no more no less.
    assert sum(montant for _a, _u, montant, _pm in lignes) == 500


def test_repartition_tout_fed_un_seul_article():
    """Cas simple : un article entièrement couvert par du FED → une seule ligne STRIPE_FED.
    / Simple case: one article fully covered by FED → a single STRIPE_FED line.
    """
    article = {"name": "Biere"}
    lignes_complement = [(article, None, 500, None)]
    transactions_legacy = [(UUID_FED, 500, PaymentMethod.STRIPE_FED)]

    lignes = _repartir_legacy_sur_articles(lignes_complement, transactions_legacy)

    assert lignes == [(article, UUID_FED, 500, PaymentMethod.STRIPE_FED)]


def test_repartition_une_transaction_couvre_plusieurs_articles():
    """Une seule transaction FED couvre 3 articles : 3 lignes, toutes STRIPE_FED, même asset.
    / A single FED transaction covers 3 articles: 3 lines, all STRIPE_FED, same asset.
    """
    a1, a2, a3 = {"name": "A1"}, {"name": "A2"}, {"name": "A3"}
    lignes_complement = [
        (a1, None, 100, None),
        (a2, None, 250, None),
        (a3, None, 150, None),
    ]
    transactions_legacy = [(UUID_FED, 500, PaymentMethod.STRIPE_FED)]

    lignes = _repartir_legacy_sur_articles(lignes_complement, transactions_legacy)

    assert lignes == [
        (a1, UUID_FED, 100, PaymentMethod.STRIPE_FED),
        (a2, UUID_FED, 250, PaymentMethod.STRIPE_FED),
        (a3, UUID_FED, 150, PaymentMethod.STRIPE_FED),
    ]
    assert sum(montant for _a, _u, montant, _pm in lignes) == 500


def test_decouper_complement_fed_partiel():
    """FED partiel : le FED couvre 2 € sur un reste de 5 € (articles 3 € + 2 €).
    Le 1er article est coupé (2 € FED + 1 € complément), le 2e reste entier en complément.
    / Partial FED: covers €2 of a €5 remainder; article 1 is split, article 2 stays in complement.
    """
    a1, a2 = {"name": "A1"}, {"name": "A2"}
    lignes_complement = [(a1, None, 300, None), (a2, None, 200, None)]

    couvertes, reste = _decouper_lignes_complement(lignes_complement, 200)

    assert couvertes == [(a1, None, 200, None)]
    assert reste == [(a1, None, 100, None), (a2, None, 200, None)]
    # Le découpage conserve les montants : couvert (FED) + reste (espèces/CB) = total initial.
    # / The split preserves amounts: FED-covered + complement = original total.
    assert sum(m for _a, _u, m, _p in couvertes) == 200
    assert sum(m for _a, _u, m, _p in reste) == 300
