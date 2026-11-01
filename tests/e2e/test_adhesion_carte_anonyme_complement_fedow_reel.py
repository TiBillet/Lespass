"""
Une adhésion payée par une carte anonyme avec un complément, contre le VRAI Fedow.
/ A membership paid by an anonymous card with a complement, against the REAL Fedow.

LOCALISATION : tests/e2e/test_adhesion_carte_anonyme_complement_fedow_reel.py

LE PARCOURS, ÉCRAN PAR ÉCRAN
Le caissier met une adhésion à 5,00 € au panier, scanne une carte anonyme qui porte
1,00 € de monnaie locale, saisit l'e-mail, le prénom et le nom, choisit le cashless,
puis règle les 4,00 € restants. Le champ e-mail doit survivre jusqu'au complément : seul
le vrai navigateur le prouve (#addition-form, htmx).
/ Real screens: the typed email must survive up to the complement. Only a browser
proves it.

LES CINQ CAS
1. Reste en espèces.
2. Reste sur une 2ᵉ carte anonyme, qui ne doit pas être rattachée.
3. Reste en CB.
4. Adhésion à prix libre à 20,00 €, reste en espèces.
5. Adhésion à prix libre à 20,00 €, reste sur une 2ᵉ carte.

Après chaque vente, on relit la base ET l'ancien Fedow : l'adhésion existe, avec le
montant, le prénom et le nom, et la carte 1 n'y est plus éphémère. Rien n'est annulé : une
carte et une adhérente neuves par test.
/ After each sale, database AND old Fedow are read back. New card and member per test.

LANCEMENT
    make e2e ARGS="tests/e2e/test_adhesion_carte_anonyme_complement_fedow_reel.py -v -s"
"""

import uuid as uuid_module

import pytest
from playwright.sync_api import expect

from tests.e2e.test_carte_liee_par_qrcode_fed_en_caisse import (
    TAG_DE_LA_CARTE_PRIMAIRE,
    _creer_une_carte_neuve_chez_l_ancien_fedow_seulement,
    _lire_json_marque,
    _scanner_la_carte,
    ancien_fedow_joignable,  # noqa: F401
)
from tests.e2e.test_parcours_fedow_reel import carte_primaire_declaree_a_l_ancien_fedow  # noqa: F401

pytestmark = [
    pytest.mark.caisse,
    pytest.mark.monnaie,
    pytest.mark.adhesion,
    pytest.mark.usefixtures(
        "carte_primaire_declaree_a_l_ancien_fedow", "ancien_fedow_joignable"
    ),
]

NOM_DU_COMPTOIR = "E2E Comptoir adhesion complement"
NOM_DE_L_ADHESION = "E2E Adhesion complement"
NOM_DE_L_ADHESION_A_PRIX_LIBRE = "E2E Adhesion complement prix libre"
PRIX_DE_L_ADHESION_CENTIMES = 500


@pytest.fixture
def comptoir_de_l_adhesion(django_shell, ensure_pos_data):
    """
    Un point de vente propre à ce fichier, une adhésion annuelle à 5,00 € et une adhésion
    à prix libre, à 5,00 € minimum.
    / A POS reserved to this file, a 5.00 € yearly membership and a free-price one.
    """
    prix_en_euros = f"{PRIX_DE_L_ADHESION_CENTIMES / 100:.2f}"
    sortie = django_shell(
        "import json, sys\n"
        "from decimal import Decimal\n"
        "from BaseBillet.models import Price, Product\n"
        "from laboutik.models import CartePrimaire, PointDeVente\n"
        "sys.path.insert(0, '/DjangoFiles/tests/pytest')\n"
        "from fabriques_vente import donner_un_compte_au_produit\n"
        "pv, _cree = PointDeVente.objects.get_or_create(\n"
        f"    name='{NOM_DU_COMPTOIR}',\n"
        "    defaults={'comportement': PointDeVente.DIRECT, 'service_direct': True,\n"
        "              'accepte_especes': True, 'accepte_carte_bancaire': True})\n"
        "article, _cree = Product.objects.get_or_create(\n"
        f"    name='{NOM_DE_L_ADHESION}',\n"
        "    defaults={'categorie_article': Product.ADHESION})\n"
        "donner_un_compte_au_produit(article)\n"
        "tarif, _cree = Price.objects.get_or_create(\n"
        "    product=article, name='Annuelle',\n"
        f"    defaults={{'prix': Decimal('{prix_en_euros}'), 'publish': True,\n"
        "               'subscription_type': Price.YEAR})\n"
        "article_libre, _cree = Product.objects.get_or_create(\n"
        f"    name='{NOM_DE_L_ADHESION_A_PRIX_LIBRE}',\n"
        "    defaults={'categorie_article': Product.ADHESION})\n"
        "donner_un_compte_au_produit(article_libre)\n"
        "tarif_libre, _cree = Price.objects.get_or_create(\n"
        "    product=article_libre, name='Annuelle libre',\n"
        f"    defaults={{'prix': Decimal('{prix_en_euros}'), 'publish': True,\n"
        "               'free_price': True, 'subscription_type': Price.YEAR})\n"
        "pv.products.add(article, article_libre)\n"
        f"primaire = CartePrimaire.objects.get(carte__tag_id='{TAG_DE_LA_CARTE_PRIMAIRE}')\n"
        "primaire.points_de_vente.add(pv)\n"
        "print('COMPTOIR_JSON=' + json.dumps({\n"
        "    'article_uuid': str(article.uuid),\n"
        "    'tarif_uuid': str(tarif.uuid),\n"
        "    'article_libre_uuid': str(article_libre.uuid),\n"
        "    'tarif_libre_uuid': str(tarif_libre.uuid),\n"
        "}))"
    )
    return _lire_json_marque(sortie, "COMPTOIR_JSON=")


def _fabriquer_une_carte_anonyme(django_shell, local_centimes):
    """
    Une carte anonyme, connue du vrai Fedow, avec de la monnaie locale sur son portefeuille
    éphémère. La monnaie locale est celle que lit la cascade de la caisse.
    / An anonymous card known to the real Fedow, with local currency on its wallet.

    :return: str, le tag de la carte
    """
    carte = _creer_une_carte_neuve_chez_l_ancien_fedow_seulement(django_shell)
    sortie = django_shell(
        "import json\n"
        "from django.db import connection, transaction\n"
        "from fedow_core.models import Asset\n"
        "from fedow_core.services import AssetService, WalletService\n"
        "from laboutik.views import _obtenir_ou_creer_wallet, trouver_ou_rapatrier_la_carte\n"
        f"carte = trouver_ou_rapatrier_la_carte('{carte['tag']}')\n"
        "portefeuille = _obtenir_ou_creer_wallet(carte)\n"
        "asset = AssetService.obtenir_assets_accessibles(connection.tenant)"
        ".filter(category=Asset.TLF).first()\n"
        "with transaction.atomic():\n"
        f"    WalletService.crediter(portefeuille, asset, {local_centimes})\n"
        "print('CREDIT_JSON=' + json.dumps({\n"
        "    'titulaire': str(carte.user),\n"
        "    'solde': WalletService.obtenir_solde(wallet=portefeuille, asset=asset),\n"
        "}))"
    )
    credit = _lire_json_marque(sortie, "CREDIT_JSON=")
    assert credit == {"titulaire": "None", "solde": local_centimes}, credit
    return carte["tag"]


def _mettre_l_adhesion_au_panier(page, comptoir):
    """
    Le caissier touche la tuile de l'adhésion à 5,00 €.
    / The cashier taps the 5.00 € membership tile.
    """
    tuile = page.locator(f'[data-testid="article-{comptoir["article_uuid"]}"]')
    expect(tuile).to_be_visible()
    tuile.click()


def _mettre_l_adhesion_a_vingt_euros_au_panier(page, comptoir):
    """
    Le caissier touche la tuile de l'adhésion à prix libre, tape 20 sur le pavé et ajoute.
    / The cashier taps the free-price tile, types 20 on the keypad and adds it.
    """
    tarif_uuid = comptoir["tarif_libre_uuid"]
    tuile = page.locator(f'[data-testid="article-{comptoir["article_libre_uuid"]}"]')
    expect(tuile).to_be_visible()
    tuile.click()

    page.locator(f'[data-testid="tarif-libre-ouvrir-{tarif_uuid}"]').click()
    pave = page.locator(f"#tarif-libre-{tarif_uuid}")
    pave.locator('.numpad-touch[data-key="2"]').click()
    pave.locator('.numpad-touch[data-key="0"]').click()
    page.locator(f'[data-testid="tarif-free-validate-{tarif_uuid}"]').click()


def _vendre_l_adhesion_a_la_carte_anonyme(
    page, pos_page, comptoir, tag_de_la_carte, email, reste_attendu="4,00", prix_libre=False
):
    """
    Le caissier met l'adhésion au panier, scanne la carte anonyme, saisit l'identité du
    client et choisit le cashless. La caisse annonce le complément.
    / The cashier adds the membership, scans the card, types the identity, picks cashless.
    """
    pos_page(page, NOM_DU_COMPTOIR)
    if prix_libre:
        _mettre_l_adhesion_a_vingt_euros_au_panier(page, comptoir)
    else:
        _mettre_l_adhesion_au_panier(page, comptoir)

    bouton_valider = page.locator('[data-testid="addition-valider"]')
    expect(bouton_valider).to_be_enabled()
    bouton_valider.click()

    page.locator('[data-testid="client-choose-nfc"]').click()
    _scanner_la_carte(page, tag_de_la_carte)

    formulaire = page.locator('[data-testid="client-form"]')
    expect(formulaire).to_be_visible(timeout=20_000)
    page.locator('[data-testid="client-input-email"]').fill(email)
    page.locator('[data-testid="client-input-prenom"]').fill("Ada")
    page.locator('[data-testid="client-input-nom"]').fill("Lovelace")
    page.locator('[data-testid="client-btn-valider"]').click()

    expect(page.locator('[data-testid="client-recapitulatif"]')).to_be_visible(
        timeout=20_000
    )
    page.locator('[data-testid="paiement-btn-cashless"]').click()

    ecran_du_complement = page.locator('[data-testid="complement-paiement"]')
    expect(ecran_du_complement).to_be_visible(timeout=20_000)
    expect(
        page.locator('[data-testid="complement-reste-a-payer"]')
    ).to_contain_text(reste_attendu)


def _etat_apres_la_vente(django_shell, email, tarif_uuid, tag_de_la_carte):
    """
    Relit l'adhésion, la vente et la carte en base, et la fiche de la carte sur le VRAI
    Fedow.
    / Reads back the membership, sale and card, and the card's record on the REAL Fedow.
    """
    sortie = django_shell(
        "import json\n"
        "from AuthBillet.models import TibilletUser\n"
        "from BaseBillet.models import LigneArticle, Membership\n"
        "from BaseBillet.models_vente import Vente\n"
        "from QrcodeCashless.models import CarteCashless\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        f"adhesion = Membership.objects.filter(user=user, price__uuid='{tarif_uuid}').first()\n"
        "ligne = LigneArticle.objects.filter(membership=adhesion).first() if adhesion else None\n"
        "vente = ligne.vente if ligne else None\n"
        "reglements = []\n"
        "if vente:\n"
        "    for reglement in vente.reglements.all():\n"
        "        reglements.append([reglement.moyen, reglement.montant])\n"
        f"carte = CarteCashless.objects.get(tag_id='{tag_de_la_carte}')\n"
        f"fiche = FedowAPI().NFCcard.qr_retrieve(str(carte.uuid))\n"
        "print('ETAT_JSON=' + json.dumps({\n"
        "    'adhesion': adhesion is not None,\n"
        "    'contribution': str(adhesion.contribution_value) if adhesion else None,\n"
        "    'adhesion_vendue_en_caisse': adhesion.status == Membership.LABOUTIK,\n"
        "    'adhesion_a_une_echeance': adhesion.deadline is not None,\n"
        "    'prenom': adhesion.first_name if adhesion else None,\n"
        "    'nom': adhesion.last_name if adhesion else None,\n"
        "    'ligne': ligne is not None,\n"
        "    'client_de_la_vente': str(ligne.vente.client) if ligne else None,\n"
        "    'vente_reglee': vente.statut == Vente.Statut.REGLEE,\n"
        "    'vente_numerotee': vente.numero is not None,\n"
        "    'carte_de_la_vente': vente.carte.tag_id if vente.carte else None,\n"
        "    'total_ttc': vente.total_ttc,\n"
        "    'reglements': sorted(reglements),\n"
        f"    'tag_de_la_carte': '{tag_de_la_carte}',\n"
        "    'titulaire_local': str(carte.user),\n"
        "    'ephemere_chez_fedow': bool(fiche.get('is_wallet_ephemere')),\n"
        "    'email': user.email,\n"
        "}))"
    )
    return _lire_json_marque(sortie, "ETAT_JSON=")


def _verifier_l_adhesion(etat, reglements_attendus, contribution_attendue="5.00"):
    """
    L'adhésion existe, vendue en caisse, avec une échéance, le montant, le prénom et le
    nom, sur la ligne de vente. La vente est réglée et numérotée, avec sa carte, son total
    et ses règlements. La carte est à l'adhérente, ici et sur le vrai Fedow.
    / The till membership has its deadline, amount and names. The sale is settled and
    numbered, with its card, total and payments. The card is the member's, on both sides.

    :param reglements_attendus: liste triée de paires [moyen, montant en centimes]
    """
    assert etat["adhesion"] is True, etat
    assert etat["adhesion_vendue_en_caisse"] is True, etat
    assert etat["adhesion_a_une_echeance"] is True, etat
    assert etat["contribution"] == contribution_attendue, etat
    assert etat["vente_reglee"] is True, etat
    assert etat["vente_numerotee"] is True, etat
    assert etat["carte_de_la_vente"] == etat["tag_de_la_carte"], etat
    assert etat["reglements"] == reglements_attendus, etat
    total_des_reglements = 0
    for _moyen, montant in reglements_attendus:
        total_des_reglements += montant
    assert etat["total_ttc"] == total_des_reglements, etat
    assert etat["prenom"] == "Ada", etat
    assert etat["nom"] == "Lovelace", etat
    assert etat["ligne"] is True, etat
    assert etat["client_de_la_vente"] == etat["email"], etat
    assert etat["titulaire_local"] == etat["email"], etat
    assert etat["ephemere_chez_fedow"] is False, etat


def test_carte_anonyme_adhesion_avec_le_reste_en_especes(
    page, pos_page, django_shell, comptoir_de_l_adhesion
):
    """
    1,00 € sur la carte, 4,00 € en espèces : l'adhésion est enregistrée et la carte
    rattachée, ici et chez Fedow.
    / 1.00 € on the card, 4.00 € in cash: membership recorded, card attached.
    """
    tag = _fabriquer_une_carte_anonyme(django_shell, 100)
    email = f"e2e-complement-{uuid_module.uuid4().hex[:8]}@tibillet.test"

    _vendre_l_adhesion_a_la_carte_anonyme(
        page, pos_page, comptoir_de_l_adhesion, tag, email
    )
    page.locator('[data-testid="btn-complement-especes"]').click()
    page.locator('[data-testid="paiement-btn-valider"]').click()

    expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=20_000)
    _verifier_l_adhesion(
        _etat_apres_la_vente(
            django_shell, email, comptoir_de_l_adhesion["tarif_uuid"], tag
        ),
        [["CA", 400], ["LE", 100]],
    )


def test_carte_anonyme_adhesion_avec_le_reste_sur_une_deuxieme_carte(
    page, pos_page, django_shell, comptoir_de_l_adhesion
):
    """
    1,00 € sur la carte 1, 4,00 € sur une 2ᵉ carte anonyme : l'adhésion est enregistrée,
    la carte 1 est rattachée, la carte 2 reste anonyme.
    / 1.00 € on card 1, 4.00 € on an anonymous card 2: card 1 attached, card 2 not.
    """
    tag_carte_1 = _fabriquer_une_carte_anonyme(django_shell, 100)
    tag_carte_2 = _fabriquer_une_carte_anonyme(django_shell, 1000)
    email = f"e2e-complement-{uuid_module.uuid4().hex[:8]}@tibillet.test"

    _vendre_l_adhesion_a_la_carte_anonyme(
        page, pos_page, comptoir_de_l_adhesion, tag_carte_1, email
    )
    page.locator('[data-testid="btn-complement-2eme-carte"]').click()
    _scanner_la_carte(page, tag_carte_2)

    expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=20_000)
    _verifier_l_adhesion(
        _etat_apres_la_vente(
            django_shell, email, comptoir_de_l_adhesion["tarif_uuid"], tag_carte_1
        ),
        [["LE", 100], ["LE", 400]],
    )
    titulaire_de_la_carte_2 = _lire_json_marque(
        django_shell(
            "import json\n"
            "from QrcodeCashless.models import CarteCashless\n"
            f"carte = CarteCashless.objects.get(tag_id='{tag_carte_2}')\n"
            "print('CARTE2_JSON=' + json.dumps({'user': str(carte.user)}))"
        ),
        "CARTE2_JSON=",
    )
    assert titulaire_de_la_carte_2 == {"user": "None"}


def test_carte_anonyme_adhesion_avec_le_reste_en_cb(
    page, pos_page, django_shell, comptoir_de_l_adhesion
):
    """
    1,00 € sur la carte, 4,00 € en CB : l'adhésion est enregistrée et la carte rattachée.
    / 1.00 € on the card, 4.00 € by bank card: membership recorded, card attached.
    """
    tag = _fabriquer_une_carte_anonyme(django_shell, 100)
    email = f"e2e-complement-{uuid_module.uuid4().hex[:8]}@tibillet.test"

    _vendre_l_adhesion_a_la_carte_anonyme(
        page, pos_page, comptoir_de_l_adhesion, tag, email
    )
    page.locator('[data-testid="btn-complement-cb"]').click()
    page.locator('[data-testid="paiement-btn-valider"]').click()

    expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=20_000)
    _verifier_l_adhesion(
        _etat_apres_la_vente(
            django_shell, email, comptoir_de_l_adhesion["tarif_uuid"], tag
        ),
        [["CC", 400], ["LE", 100]],
    )


def test_carte_anonyme_adhesion_a_prix_libre_avec_le_reste_en_especes(
    page, pos_page, django_shell, comptoir_de_l_adhesion
):
    """
    Adhésion à 20,00 € au pavé, 1,00 € sur la carte, 19,00 € en espèces : l'adhésion garde
    20,00 €.
    / 20.00 € typed on the keypad, 1.00 € on the card, 19.00 € in cash: membership at 20.00 €.
    """
    tag = _fabriquer_une_carte_anonyme(django_shell, 100)
    email = f"e2e-complement-{uuid_module.uuid4().hex[:8]}@tibillet.test"

    _vendre_l_adhesion_a_la_carte_anonyme(
        page,
        pos_page,
        comptoir_de_l_adhesion,
        tag,
        email,
        reste_attendu="19,00",
        prix_libre=True,
    )
    page.locator('[data-testid="btn-complement-especes"]').click()
    page.locator('[data-testid="paiement-btn-valider"]').click()

    expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=20_000)
    _verifier_l_adhesion(
        _etat_apres_la_vente(
            django_shell, email, comptoir_de_l_adhesion["tarif_libre_uuid"], tag
        ),
        [["CA", 1900], ["LE", 100]],
        contribution_attendue="20.00",
    )


def test_carte_anonyme_adhesion_a_prix_libre_avec_le_reste_sur_une_deuxieme_carte(
    page, pos_page, django_shell, comptoir_de_l_adhesion
):
    """
    Adhésion à 20,00 € au pavé, 1,00 € sur la carte 1, 19,00 € sur une 2ᵉ carte : l'adhésion
    garde 20,00 €.
    / 20.00 € typed on the keypad, paid by two cards: membership at 20.00 €.
    """
    tag_carte_1 = _fabriquer_une_carte_anonyme(django_shell, 100)
    tag_carte_2 = _fabriquer_une_carte_anonyme(django_shell, 2000)
    email = f"e2e-complement-{uuid_module.uuid4().hex[:8]}@tibillet.test"

    _vendre_l_adhesion_a_la_carte_anonyme(
        page,
        pos_page,
        comptoir_de_l_adhesion,
        tag_carte_1,
        email,
        reste_attendu="19,00",
        prix_libre=True,
    )
    page.locator('[data-testid="btn-complement-2eme-carte"]').click()
    _scanner_la_carte(page, tag_carte_2)

    expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=20_000)
    _verifier_l_adhesion(
        _etat_apres_la_vente(
            django_shell, email, comptoir_de_l_adhesion["tarif_libre_uuid"], tag_carte_1
        ),
        [["LE", 100], ["LE", 1900]],
        contribution_attendue="20.00",
    )
