"""
Tests de la formule d'argent d'un article vendu : `calculer_montants_article`.
/ Tests of the money formula of a sold item: `calculer_montants_article`.

LOCALISATION : tests/pytest/test_montants_article.py

À QUOI SERVENT CES TESTS
`calculer_montants_article` est la SEULE formule d'argent du projet. Elle reçoit un prix
unitaire en centimes, une quantité et un taux de TVA. Elle rend des centimes ENTIERS,
écrits une fois au moment de la vente, puis seulement additionnés.
/ `calculer_montants_article` is the ONLY money formula of the project. It returns whole
cents, written once at sale time, then only summed.

LA FORMULE (tronc du chantier 05, §2)
    total_catalogue = arrondi_demi_haut(prix_unitaire × quantité)
    net_vendu       = total_catalogue − part_offerte
    total_ht        = arrondi_demi_haut(net_vendu × 100 / (100 + taux_tva))
    total_tva       = net_vendu − total_ht
    cout_achat      = arrondi_demi_haut(quantité_réelle × prix_achat)   (vide si prix_achat = 0)
« Arrondi demi-haut » : 0,5 va vers le haut (451,5 → 452 ; 92,5 → 93). Jamais l'arrondi
au pair de `round()`, jamais la troncature de `int()`.
/ Half-up rounding: 0.5 goes up. Never round() (half-even), never int() (truncation).

Chaque test compare des ENTIERS EXACTS : pas de « à un centime près ».
/ Every test compares EXACT integers.

LES TYPES REFUSÉS
Les centimes reçus (prix unitaire, part offerte, prix d'achat, total imposé) sont des
`int`, et rien d'autre : ni `Decimal`, ni `float`, ni `bool`. La quantité, la quantité
pour le coût et le taux de TVA sont des `Decimal` ou des `int`, jamais des `float` :
`Decimal(0.35)` vaut 0,34999…, et 1290 × 0,35 donnerait 451 au lieu de 452, en silence.
/ Cents are int only. Quantities and VAT rate are Decimal or int, never float.

Ces tests n'utilisent pas la base de données : la formule est un calcul pur.
/ These tests do not use the database: the formula is a pure computation.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-A-vente-reglement.md (§3, §7)
et CHANTIER-05-montants-entiers.md (§2).

CODE TESTÉ / CODE UNDER TEST
- BaseBillet/services_vente.py — calculer_montants_article()

Lancer / Run : make test ARGS="tests/pytest/test_montants_article.py"
"""

from decimal import Decimal

import pytest

from BaseBillet.services_vente import calculer_montants_article

# Les taux de TVA utilisés dans ces tests, en pour cent.
# / VAT rates used in these tests, in percent.
TVA_NORMALE_20_POURCENT = Decimal("20")
TVA_ALIMENTAIRE_5_5_POURCENT = Decimal("5.5")
TVA_ZERO = Decimal("0")


def test_trois_jus_a_350_font_1050_ht_875_tva_175():
    """
    Trois jus à 3,50 € (TVA 20 %) : 10,50 € au catalogue, rien d'offert, 10,50 € vendus,
    dont 8,75 € hors taxes et 1,75 € de TVA. Aucun prix d'achat : pas de coût.
    Chaque montant rendu est un `int`, jamais un `Decimal` ni un `float`.
    / Three juices at 3.50 €: 1050 / 875 / 175 cents, no purchase cost. Every amount is an int.
    """
    montants = calculer_montants_article(
        prix_unitaire=350,
        quantite=Decimal("3"),
        taux_tva=TVA_NORMALE_20_POURCENT,
    )

    assert montants == {
        "total_catalogue": 1050,
        "part_offerte": 0,
        "total_ttc": 1050,
        "total_ht": 875,
        "total_tva": 175,
        "cout_achat": None,
    }

    # Un Decimal(1050) serait égal à 1050 dans la comparaison ci-dessus : on vérifie le
    # type à part. Les champs de la base sont des entiers.
    # / Decimal(1050) == 1050 is true: the type is checked separately.
    noms_des_montants_en_centimes = [
        "total_catalogue",
        "part_offerte",
        "total_ttc",
        "total_ht",
        "total_tva",
    ]
    for nom_du_montant in noms_des_montants_en_centimes:
        assert type(montants[nom_du_montant]) is int, nom_du_montant


def test_fromage_0_350_kg_a_1290_arrondi_demi_haut():
    """
    350 g de fromage à 12,90 € le kilo (TVA 5,5 %) : 1290 × 0,350 = 451,5 centimes.
    L'arrondi demi-haut donne 452. La troncature donnerait 451.
    HT : 452 × 100 / 105,5 = 428,4… → 428. TVA : 452 − 428 = 24.
    / 350 g of cheese at 12.90 €/kg: 451.5 cents, rounded half-up to 452.
    """
    montants = calculer_montants_article(
        prix_unitaire=1290,
        quantite=Decimal("0.350"),
        taux_tva=TVA_ALIMENTAIRE_5_5_POURCENT,
    )

    assert montants == {
        "total_catalogue": 452,
        "part_offerte": 0,
        "total_ttc": 452,
        "total_ht": 428,
        "total_tva": 24,
        "cout_achat": None,
    }


def test_part_offerte_300_sur_500_net_200_tva_sur_200():
    """
    Un article à 5,00 € dont le gérant offre 3,00 € : le net vendu vaut 2,00 €.
    La TVA se calcule sur le net vendu (200), pas sur le prix catalogue (500).
    HT : 200 × 100 / 120 = 166,7 → 167. TVA : 200 − 167 = 33.
    / A 5.00 € item with 3.00 € offered: net 200, VAT computed on the net.
    """
    montants = calculer_montants_article(
        prix_unitaire=500,
        quantite=Decimal("1"),
        taux_tva=TVA_NORMALE_20_POURCENT,
        part_offerte=300,
    )

    assert montants == {
        "total_catalogue": 500,
        "part_offerte": 300,
        "total_ttc": 200,
        "total_ht": 167,
        "total_tva": 33,
        "cout_achat": None,
    }


def test_avoir_moins_deux_biere_a_500():
    """
    Un avoir sur deux bières à 5,00 € (TVA 20 %) : quantité −2, prix unitaire positif.
    Tous les montants sont négatifs : −1000, dont −833 HT et −167 de TVA.
    / A credit note on two beers: quantity −2, positive unit price, negative amounts.
    """
    montants = calculer_montants_article(
        prix_unitaire=500,
        quantite=Decimal("-2"),
        taux_tva=TVA_NORMALE_20_POURCENT,
    )

    assert montants == {
        "total_catalogue": -1000,
        "part_offerte": 0,
        "total_ttc": -1000,
        "total_ht": -833,
        "total_tva": -167,
        "cout_achat": None,
    }


def test_taux_zero_ht_egal_net():
    """
    Une recharge cashless de 25,00 € (TVA 0 %) : le hors taxes vaut le net vendu, la TVA 0.
    / A 25.00 € cashless top-up at 0 % VAT: excl. tax equals net, VAT is 0.
    """
    montants = calculer_montants_article(
        prix_unitaire=2500,
        quantite=Decimal("1"),
        taux_tva=TVA_ZERO,
    )

    assert montants == {
        "total_catalogue": 2500,
        "part_offerte": 0,
        "total_ttc": 2500,
        "total_ht": 2500,
        "total_tva": 0,
        "cout_achat": None,
    }


def test_net_105_a_20_pourcent_ht_88_tva_17():
    """
    Net vendu 1,05 € à 20 % : HT = 105 × 100 / 120 = 87,5 → 88 ; TVA = 105 − 88 = 17.
    La TVA est la DIFFÉRENCE net − HT. Calculée à part (105 × 20 / 120 = 17,5 → 18),
    elle donnerait HT + TVA = 106, un centime inventé.
    / VAT is net − HT. Computed on its own it would be 18, and HT + VAT = 106.
    """
    montants = calculer_montants_article(
        prix_unitaire=105,
        quantite=Decimal("1"),
        taux_tva=TVA_NORMALE_20_POURCENT,
    )

    assert montants == {
        "total_catalogue": 105,
        "part_offerte": 0,
        "total_ttc": 105,
        "total_ht": 88,
        "total_tva": 17,
        "cout_achat": None,
    }


def test_net_111_a_20_pourcent_ht_93():
    """
    Net vendu 1,11 € à 20 % : HT = 111 × 100 / 120 = 92,5 → 93 (arrondi demi-haut).
    L'arrondi au pair donnerait 92. TVA = 111 − 93 = 18.
    / HT 92.5 rounds half-up to 93 (half-even would give 92).
    """
    montants = calculer_montants_article(
        prix_unitaire=111,
        quantite=Decimal("1"),
        taux_tva=TVA_NORMALE_20_POURCENT,
    )

    assert montants == {
        "total_catalogue": 111,
        "part_offerte": 0,
        "total_ttc": 111,
        "total_ht": 93,
        "total_tva": 18,
        "cout_achat": None,
    }


def test_cout_achat_fige_et_vide_si_prix_inconnu():
    """
    Le coût d'achat est figé en centimes au moment de la vente : trois jus achetés 1,20 €
    pièce coûtent 360. Un prix d'achat à 0 veut dire « inconnu » : le coût reste vide
    (`None`), il ne vaut pas 0.
    / Purchase cost is frozen: 3 × 120 = 360. A purchase price of 0 means unknown: None.
    """
    montants_avec_prix_d_achat_connu = calculer_montants_article(
        prix_unitaire=350,
        quantite=Decimal("3"),
        taux_tva=TVA_NORMALE_20_POURCENT,
        prix_achat=120,
    )
    assert montants_avec_prix_d_achat_connu["cout_achat"] == 360

    montants_avec_prix_d_achat_inconnu = calculer_montants_article(
        prix_unitaire=350,
        quantite=Decimal("3"),
        taux_tva=TVA_NORMALE_20_POURCENT,
        prix_achat=0,
    )
    assert montants_avec_prix_d_achat_inconnu["cout_achat"] is None


def test_total_catalogue_impose_est_repris_tel_quel():
    """
    Pendant la transition, un article payé avec deux moyens est coupé en « parts ». Chaque
    part porte l'argent réellement débité : le producteur l'impose, la formule le reprend
    tel quel au lieu de refaire prix × quantité.
    / During the transition, a split item's part carries the money really debited: the
    formula takes the imposed total as is.

    Premier cas : la part payée en monnaie locale d'un article à 10,50 € (tronc §5) :
    350 × 1,428571 → 500 imposés ; HT 417, TVA 83.
    Second cas : un article à 10,00 € payé en trois parts 334 + 333 + 333. La part de 334
    a la quantité 0,333333 : le calcul donnerait 333. Le 334 rendu prouve que le montant
    imposé est repris tel quel. HT : 334 × 100 / 120 = 278,3 → 278 ; TVA 56.
    / Case 1 from the spec. Case 2: computing would give 333; 334 proves the imposed total
    is kept.
    """
    montants_de_la_part_en_monnaie_locale = calculer_montants_article(
        prix_unitaire=350,
        quantite=Decimal("1.428571"),
        taux_tva=TVA_NORMALE_20_POURCENT,
        total_catalogue_impose=500,
    )
    assert montants_de_la_part_en_monnaie_locale == {
        "total_catalogue": 500,
        "part_offerte": 0,
        "total_ttc": 500,
        "total_ht": 417,
        "total_tva": 83,
        "cout_achat": None,
    }

    montants_de_la_premiere_part_sur_trois = calculer_montants_article(
        prix_unitaire=1000,
        quantite=Decimal("0.333333"),
        taux_tva=TVA_NORMALE_20_POURCENT,
        total_catalogue_impose=334,
    )
    assert montants_de_la_premiere_part_sur_trois == {
        "total_catalogue": 334,
        "part_offerte": 0,
        "total_ttc": 334,
        "total_ht": 278,
        "total_tva": 56,
        "cout_achat": None,
    }


def test_part_offerte_superieure_au_total_refusee():
    """
    On ne peut pas offrir 6,00 € sur un article à 5,00 € : la formule refuse, avec une
    `ValueError`, au lieu de rendre un net vendu négatif.
    / Offering 600 on a 500 item is refused with a ValueError.
    """
    with pytest.raises(ValueError):
        calculer_montants_article(
            prix_unitaire=500,
            quantite=Decimal("1"),
            taux_tva=TVA_NORMALE_20_POURCENT,
            part_offerte=600,
        )


def test_cout_achat_sur_la_quantite_reelle():
    """
    Vente au poids pendant la transition : la ligne a `quantite = 1` et un prix de 4,52 €
    (350 g de fromage). Le prix d'achat est au kilo (8,00 €) : le coût se calcule sur la
    quantité réellement servie, 0,350 kg, passée à part. 800 × 0,350 = 280.
    Calculé sur `quantite` (1), il vaudrait 800.
    / Weight sale with qty = 1: the cost uses the real quantity served (0.350 kg) → 280.
    """
    montants = calculer_montants_article(
        prix_unitaire=452,
        quantite=Decimal("1"),
        taux_tva=TVA_ALIMENTAIRE_5_5_POURCENT,
        prix_achat=800,
        quantite_pour_cout=Decimal("0.350"),
    )

    assert montants["cout_achat"] == 280


def test_montants_rendus_entiers_avec_part_offerte_et_cout():
    """
    Un article à 5,00 € dont 3,00 € sont offerts, acheté 1,20 € : TOUS les montants
    rendus sont des `int`, y compris la part offerte et le coût d'achat.
    / With an offered part and a purchase cost, every returned amount is an int.
    """
    montants = calculer_montants_article(
        prix_unitaire=500,
        quantite=Decimal("1"),
        taux_tva=TVA_NORMALE_20_POURCENT,
        part_offerte=300,
        prix_achat=120,
    )

    # Un Decimal(300) serait égal à 300 : on vérifie le type de chaque montant.
    # / Decimal(300) == 300 is true: the type of each amount is checked.
    for nom_du_montant, montant in montants.items():
        assert type(montant) is int, f"{nom_du_montant} : {montant!r}"


def test_quantite_en_float_refusee():
    """
    350 g de fromage à 12,90 € le kilo, avec la quantité en `float` (0.35) :
    `Decimal(0.35)` vaut 0,34999…, et 1290 × 0,34999… = 451,49… donnerait 451 au lieu
    de 452. La formule refuse un `float` (ValueError), avec un message qui demande un
    `Decimal`.
    / A float quantity (0.35 is really 0.34999…) would give 451 instead of 452: refused.
    """
    with pytest.raises(ValueError, match="Decimal"):
        calculer_montants_article(
            prix_unitaire=1290,
            quantite=0.35,
            taux_tva=TVA_ALIMENTAIRE_5_5_POURCENT,
        )


def test_quantite_pour_cout_en_float_refusee():
    """
    La quantité réellement servie, pour le coût d'achat, suit la même règle que la
    quantité : un `float` est refusé (ValueError), avec un message qui demande un
    `Decimal`. Il est refusé TOUJOURS, même sans prix d'achat, quand la valeur ne sert
    pas au calcul : une seule règle.
    / The quantity used for the cost follows the same rule: a float is always refused,
    even without a purchase price.
    """
    with pytest.raises(ValueError, match="Decimal"):
        calculer_montants_article(
            prix_unitaire=452,
            quantite=Decimal("1"),
            taux_tva=TVA_ALIMENTAIRE_5_5_POURCENT,
            prix_achat=800,
            quantite_pour_cout=0.35,
        )

    with pytest.raises(ValueError, match="Decimal"):
        calculer_montants_article(
            prix_unitaire=452,
            quantite=Decimal("1"),
            taux_tva=TVA_ALIMENTAIRE_5_5_POURCENT,
            prix_achat=0,
            quantite_pour_cout=0.35,
        )


def test_taux_tva_en_float_refuse():
    """
    Un taux de TVA en `float` (5.5) est refusé (ValueError), avec un message qui demande
    un `Decimal` : `Decimal(5.5)` tombe juste, mais d'autres taux ne tombent pas juste
    en binaire, et la formule ne fait pas le tri.
    / A float VAT rate is refused, with a message asking for a Decimal.
    """
    with pytest.raises(ValueError, match="Decimal"):
        calculer_montants_article(
            prix_unitaire=1290,
            quantite=Decimal("0.350"),
            taux_tva=5.5,
        )


def test_quantite_et_taux_en_int_acceptes():
    """
    Un `int` est exact : la quantité et le taux de TVA peuvent être des `int`. Trois jus
    à 3,50 € (TVA 20) donnent les mêmes montants qu'avec des `Decimal`.
    / An int is exact: int quantity and VAT rate are accepted, same amounts as Decimal.
    """
    montants = calculer_montants_article(
        prix_unitaire=350,
        quantite=3,
        taux_tva=20,
    )

    assert montants == {
        "total_catalogue": 1050,
        "part_offerte": 0,
        "total_ttc": 1050,
        "total_ht": 875,
        "total_tva": 175,
        "cout_achat": None,
    }


def test_centimes_non_entiers_refuses():
    """
    Le prix unitaire, la part offerte et le prix d'achat sont des centimes ENTIERS
    (`int`). Un `Decimal`, un `float` ou un `bool` est refusé (ValueError), avant tout
    calcul : un tel montant serait arrondi en silence.
    Chaque cas est joué, puis le test liste ceux qui n'ont pas été refusés.
    / Unit price, offered part and purchase price must be int: Decimal, float and bool
    are refused. Every case is played, then the test lists those not refused.
    """
    # Un article à 3,50 € (TVA 20 %), sans offert ni prix d'achat : on remplace un
    # montant à la fois par une valeur qui n'est pas un `int`.
    # / A 3.50 € item: one amount at a time is replaced by a value that is not an int.
    arguments_valides = {
        "prix_unitaire": 350,
        "quantite": Decimal("1"),
        "taux_tva": TVA_NORMALE_20_POURCENT,
        "part_offerte": 0,
        "prix_achat": 0,
    }
    cas_a_verifier = [
        ("prix_unitaire", Decimal("350.5")),
        ("prix_unitaire", 350.0),
        ("prix_unitaire", True),
        ("part_offerte", Decimal("100.5")),
        ("part_offerte", 100.0),
        ("part_offerte", True),
        ("prix_achat", Decimal("120.5")),
        ("prix_achat", 120.0),
        ("prix_achat", True),
    ]

    cas_non_refuses = []
    for nom_de_l_argument, valeur_non_entiere in cas_a_verifier:
        arguments_du_cas = dict(arguments_valides)
        arguments_du_cas[nom_de_l_argument] = valeur_non_entiere
        try:
            calculer_montants_article(**arguments_du_cas)
        except ValueError:
            continue
        cas_non_refuses.append(f"{nom_de_l_argument}={valeur_non_entiere!r}")

    assert cas_non_refuses == [], f"Centimes non entiers acceptés : {cas_non_refuses}"
