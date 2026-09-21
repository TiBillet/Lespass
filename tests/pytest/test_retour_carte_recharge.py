"""
tests/pytest/test_retour_carte_recharge.py
Popup « check carte » : la zone « Recharger » et ses etapes.
/ Card check popup: the "Top up" zone and its steps.

LOCALISATION : tests/pytest/test_retour_carte_recharge.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
1. retour_carte() propose les produits de recharge du LIEU, depuis n'importe
   quel point de vente (uuid_pv envoye par hx_check_card.html) — meme un PV
   qui ne contient aucun produit de recharge, comme le Bar. Rien sans PV.
2. recharge_carte() renvoie la zone a chaque etape : QUOI, COMBIEN,
   MONTANT LIBRE (valide ou non), CONFIRMER.
3. Les champs de l'etape CONFIRMER, postes tels quels vers les vues
   existantes, creditent bien la carte :
   - recharge payante (RE) → payer() en especes ;
   - recharge offerte (RC) → identifier_client().

/ 1. retour_carte() offers the current POS top-ups. 2. recharge_carte()
renders each step. 3. The confirm step fields, posted to the existing views,
really credit the card.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_retour_carte_recharge.py -v
"""

import uuid as uuid_module

import pytest
from django.db.models import Q
from django.test import Client as ClientHttpDjango
from django_tenants.utils import schema_context, tenant_context

from AuthBillet.models import TibilletUser, Wallet
from BaseBillet.models import LigneArticle, Product
from Customers.models import Client
from QrcodeCashless.models import CarteCashless, Detail
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import WalletService

# Prefixe pour reconnaitre les donnees de ce fichier (base de dev, sans rollback)
# / Prefix to recognise this file's data (dev DB, no rollback)
PREFIXE = "[rc_test]"
TAG_CAISSIER = "RCT00001"
TAG_CLIENT = "RCT00002"

URL_RETOUR_CARTE = "/laboutik/paiement/retour_carte/"
URL_RECHARGE_CARTE = "/laboutik/paiement/recharge_carte/"
URL_PAYER = "/laboutik/paiement/payer/"
URL_IDENTIFIER_CLIENT = "/laboutik/paiement/identifier_client/"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tenant_lespass():
    return Client.objects.get(schema_name="lespass")


@pytest.fixture(scope="module")
def produits_de_recharge(tenant_lespass):
    """
    Deux monnaies du lieu : locale (TLF) et cadeau (TNF).
    Le signal post_save de Asset (fedow_core/signals.py) cree pour chacune un
    Product de recharge avec les tarifs 1, 5, 10 et Libre.
    / Two venue currencies. The Asset post_save signal creates a top-up
    Product for each, with prices 1, 5, 10 and Free.
    """
    with tenant_context(tenant_lespass):
        wallet_du_lieu, _created = Wallet.objects.get_or_create(name=f"{PREFIXE} Lieu")
        asset_local, _created = Asset.objects.get_or_create(
            name=f"{PREFIXE} Locale",
            category=Asset.TLF,
            defaults={
                "currency_code": "EUR",
                "wallet_origin": wallet_du_lieu,
                "tenant_origin": tenant_lespass,
            },
        )
        asset_cadeau, _created = Asset.objects.get_or_create(
            name=f"{PREFIXE} Cadeau",
            category=Asset.TNF,
            defaults={
                "currency_code": "EUR",
                "wallet_origin": wallet_du_lieu,
                "tenant_origin": tenant_lespass,
            },
        )
        # Reactive les monnaies archivees par le run precedent (voir fin de fixture).
        # Le signal propage l'archivage de l'Asset vers son Product de recharge.
        # / Re-enable the currencies archived by the previous run (see fixture end).
        for asset_de_test in (asset_local, asset_cadeau):
            if asset_de_test.archive or not asset_de_test.active:
                asset_de_test.archive = False
                asset_de_test.active = True
                asset_de_test.save()
        produit_local = Product.objects.get(asset=asset_local)
        produit_cadeau = Product.objects.get(asset=asset_cadeau)
        Product.objects.filter(pk__in=[produit_local.pk, produit_cadeau.pk]).update(
            archive=False, publish=True
        )
        yield {
            "asset_local": asset_local,
            "asset_cadeau": asset_cadeau,
            "produit_local": produit_local,
            "produit_cadeau": produit_cadeau,
        }

        # Le signal a rattache ces produits a TOUS les PV CASHLESS de la base de dev.
        # On les retire partout, sinon ils s'affichent dans la vraie caisse.
        # / The signal attached these products to EVERY cashless POS of the dev DB.
        # Remove them everywhere, otherwise they show up in the real POS.
        from laboutik.models import PointDeVente

        for produit_de_test in (produit_local, produit_cadeau):
            for pv in PointDeVente.objects.filter(products=produit_de_test):
                pv.products.remove(produit_de_test)

        # La recharge est proposee depuis TOUS les PV : une monnaie de test active
        # apparaitrait dans la vraie caisse. On l'archive en partant.
        # / Top-ups are offered from EVERY POS: an active test currency would show
        # up in the real POS. Archive it on the way out.
        # active=False aussi : d'autres tests prennent « le premier asset TLF actif »
        # (ex : test_pos_views_data) et tomberaient sur cette monnaie archivee.
        # / active=False too: other tests pick "the first active TLF asset".
        for asset_de_test in (asset_local, asset_cadeau):
            asset_de_test.archive = True
            asset_de_test.active = False
            asset_de_test.save()


@pytest.fixture
def carte_caissier(tenant_lespass):
    """Carte primaire du caissier. / Cashier's primary card."""
    with schema_context("lespass"):
        detail, _created = Detail.objects.get_or_create(
            base_url=f"{PREFIXE}_DETAIL",
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        carte, _created = CarteCashless.objects.get_or_create(
            tag_id=TAG_CAISSIER,
            defaults={
                "number": TAG_CAISSIER,
                "uuid": uuid_module.uuid4(),
                "detail": detail,
            },
        )
        yield carte


@pytest.fixture
def point_de_vente(carte_caissier, produits_de_recharge):
    """
    Un point de vente comme le Bar : il accepte les especes mais ne contient
    AUCUN produit de recharge. La recharge doit quand meme etre proposee et
    acceptee (regle : recharge depuis tous les PV). La carte du caissier y a acces.
    / A POS like the Bar: accepts cash but holds NO top-up product. Top-ups
    must still be offered and accepted (rule: top-up from every POS).
    """
    from laboutik.models import CartePrimaire, PointDeVente

    with schema_context("lespass"):
        pv, _created = PointDeVente.objects.get_or_create(
            name=f"{PREFIXE} PV",
            defaults={"comportement": "V", "hidden": False},
        )
        pv.accepte_especes = True
        pv.save()
        pv.products.remove(produits_de_recharge["produit_local"])
        pv.products.remove(produits_de_recharge["produit_cadeau"])
        carte_primaire, _created = CartePrimaire.objects.get_or_create(
            carte=carte_caissier,
            defaults={"edit_mode": False},
        )
        carte_primaire.points_de_vente.add(pv)
        yield pv


@pytest.fixture
def carte_client(tenant_lespass):
    """Carte anonyme du client, wallet vide. / Anonymous client card, empty wallet."""
    with schema_context("lespass"):
        detail, _created = Detail.objects.get_or_create(
            base_url=f"{PREFIXE}_DETAIL",
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        wallet_client = Wallet.objects.create(name=f"{PREFIXE} Wallet client")
        CarteCashless.objects.filter(tag_id=TAG_CLIENT).delete()
        carte = CarteCashless.objects.create(
            tag_id=TAG_CLIENT,
            number=TAG_CLIENT,
            uuid=uuid_module.uuid4(),
            detail=detail,
            wallet_ephemere=wallet_client,
        )
        yield carte
        # Nettoyage dans l'ordre des FK / Cleanup in FK order
        # La recharge cree une Transaction dont le wallet est le destinataire (FK PROTECT)
        # / The top-up creates a Transaction whose receiver is the wallet (PROTECT FK)
        LigneArticle.objects.filter(carte=carte).delete()
        Transaction.objects.filter(
            Q(card=carte) | Q(receiver=wallet_client) | Q(sender=wallet_client)
        ).delete()
        Token.objects.filter(wallet=wallet_client).delete()
        carte.delete()
        wallet_client.delete()


def _client_connecte_admin(tenant_lespass):
    """
    Client HTTP connecte en admin du tenant (meme pattern que test_pos_vider_carte).
    / HTTP client logged in as tenant admin (same pattern as test_pos_vider_carte).
    """
    client_http = ClientHttpDjango(HTTP_HOST="lespass.tibillet.localhost")
    email = "rc_test-admin@tibillet.localhost"
    utilisateur, _created = TibilletUser.objects.get_or_create(
        email=email,
        defaults={
            "username": email,
            "espece": TibilletUser.TYPE_HUM,
            "is_staff": True,
            "is_active": True,
        },
    )
    utilisateur.client_admin.add(tenant_lespass)
    if not utilisateur.is_active or utilisateur.espece != TibilletUser.TYPE_HUM:
        utilisateur.is_active = True
        utilisateur.espece = TibilletUser.TYPE_HUM
        utilisateur.save(update_fields=["is_active", "espece"])
    client_http.force_login(utilisateur)
    return client_http


def _tarif(produit, montant_en_euros=None, libre=False):
    """Retrouve un tarif du produit de recharge. / Finds a top-up price."""
    with schema_context("lespass"):
        if libre:
            return produit.prices.get(free_price=True)
        return produit.prices.get(prix=montant_en_euros, free_price=False)


def _champs_du_formulaire_de_recharge(contenu_html):
    """
    Lit les champs caches de #card-recharge-form dans le HTML rendu.
    C'est exactement ce que htmx enverra (hx-include).
    / Reads #card-recharge-form hidden fields: exactly what htmx will send.
    """
    import re

    debut = contenu_html.index('id="card-recharge-form"')
    fin = contenu_html.index("</form>", debut)
    bloc_du_formulaire = contenu_html[debut:fin]
    champs = {}
    for nom, valeur in re.findall(
        r'name="([^"]+)" value="([^"]*)"', bloc_du_formulaire
    ):
        champs[nom] = valeur
    return champs


# ---------------------------------------------------------------------------
# 1. retour_carte : la zone « Recharger » suit le point de vente
# ---------------------------------------------------------------------------


def test_retour_carte_avec_point_de_vente_affiche_les_tuiles_de_recharge(
    tenant_lespass, point_de_vente, carte_client, produits_de_recharge
):
    client_http = _client_connecte_admin(tenant_lespass)
    reponse = client_http.post(
        URL_RETOUR_CARTE,
        {"tag_id": carte_client.tag_id, "uuid_pv": str(point_de_vente.uuid)},
    )
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    # Le PV ne contient aucun produit de recharge : les tuiles s'affichent quand meme
    # / The POS holds no top-up product: tiles are shown anyway
    with schema_context("lespass"):
        assert not point_de_vente.products.filter(
            methode_caisse__in=["RE", "RC", "TM"]
        ).exists()
    assert 'data-testid="recharge-produit-1"' in contenu
    assert produits_de_recharge["asset_local"].name in contenu
    assert produits_de_recharge["asset_cadeau"].name in contenu
    # La reference de la carte vient du tag, plus de valeur en dur
    # / Card reference comes from the tag, no more hard-coded value
    assert "·· 0002" in contenu


def test_retour_carte_sans_point_de_vente_ne_propose_pas_de_recharge(
    tenant_lespass, carte_client
):
    client_http = _client_connecte_admin(tenant_lespass)
    reponse = client_http.post(URL_RETOUR_CARTE, {"tag_id": carte_client.tag_id})
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert 'data-testid="retour-carte-anonyme"' in contenu
    assert 'data-testid="recharge-produit-1"' not in contenu


def test_retour_carte_inconnue_propose_de_scanner_une_autre_carte(tenant_lespass):
    client_http = _client_connecte_admin(tenant_lespass)
    reponse = client_http.post(URL_RETOUR_CARTE, {"tag_id": "RCTXXXXX"})
    contenu = reponse.content.decode()

    assert 'data-testid="retour-carte-erreur"' in contenu
    assert 'data-testid="retour-carte-btn-rescanner"' in contenu
    assert 'data-testid="retour-carte-recharge"' not in contenu


# ---------------------------------------------------------------------------
# 2. recharge_carte : les etapes
# ---------------------------------------------------------------------------


def test_recharge_etape_combien_affiche_les_tarifs_du_produit(
    tenant_lespass, point_de_vente, carte_client, produits_de_recharge
):
    client_http = _client_connecte_admin(tenant_lespass)
    reponse = client_http.get(
        URL_RECHARGE_CARTE,
        {
            "tag_id": carte_client.tag_id,
            "uuid_pv": str(point_de_vente.uuid),
            "produit": str(produits_de_recharge["produit_local"].uuid),
        },
    )
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert 'aria-pressed="true"' in contenu
    assert 'data-testid="recharge-montant-libre"' in contenu
    assert 'data-testid="recharge-confirmation"' not in contenu


def test_recharge_tarif_fixe_affiche_la_confirmation_et_les_especes(
    tenant_lespass, point_de_vente, carte_client, produits_de_recharge
):
    produit_local = produits_de_recharge["produit_local"]
    tarif_5_euros = _tarif(produit_local, montant_en_euros=5)
    client_http = _client_connecte_admin(tenant_lespass)
    reponse = client_http.get(
        URL_RECHARGE_CARTE,
        {
            "tag_id": carte_client.tag_id,
            "uuid_pv": str(point_de_vente.uuid),
            "produit": str(produit_local.uuid),
            "prix": str(tarif_5_euros.uuid),
        },
    )
    contenu = reponse.content.decode()

    assert 'data-testid="recharge-confirmation"' in contenu
    assert 'data-testid="recharge-btn-especes"' in contenu
    champs = _champs_du_formulaire_de_recharge(contenu)
    assert champs[f"repid-{produit_local.uuid}--{tarif_5_euros.uuid}"] == "1"
    assert champs["total"] == "500"
    assert not any(nom.startswith("custom-") for nom in champs)


def test_recharge_montant_libre_invalide_affiche_une_erreur(
    tenant_lespass, point_de_vente, carte_client, produits_de_recharge
):
    produit_local = produits_de_recharge["produit_local"]
    tarif_libre = _tarif(produit_local, libre=True)
    client_http = _client_connecte_admin(tenant_lespass)
    reponse = client_http.get(
        URL_RECHARGE_CARTE,
        {
            "tag_id": carte_client.tag_id,
            "uuid_pv": str(point_de_vente.uuid),
            "produit": str(produit_local.uuid),
            "prix": str(tarif_libre.uuid),
            "montant": "douze",
        },
    )
    contenu = reponse.content.decode()

    assert 'data-testid="recharge-input-montant"' in contenu
    assert 'role="alert"' in contenu
    assert 'data-testid="recharge-confirmation"' not in contenu


def test_recharge_montant_libre_avec_virgule_donne_des_centimes(
    tenant_lespass, point_de_vente, carte_client, produits_de_recharge
):
    produit_local = produits_de_recharge["produit_local"]
    tarif_libre = _tarif(produit_local, libre=True)
    client_http = _client_connecte_admin(tenant_lespass)
    reponse = client_http.get(
        URL_RECHARGE_CARTE,
        {
            "tag_id": carte_client.tag_id,
            "uuid_pv": str(point_de_vente.uuid),
            "produit": str(produit_local.uuid),
            "prix": str(tarif_libre.uuid),
            "montant": "12,50",
        },
    )
    contenu = reponse.content.decode()

    champs = _champs_du_formulaire_de_recharge(contenu)
    assert champs[f"custom-{produit_local.uuid}--{tarif_libre.uuid}"] == "1250"
    assert champs["total"] == "1250"


# ---------------------------------------------------------------------------
# 3. Parcours complets : les champs de confirmation creditent la carte
# ---------------------------------------------------------------------------


def test_recharge_payee_en_especes_credite_la_carte(
    tenant_lespass, point_de_vente, carte_caissier, carte_client, produits_de_recharge
):
    produit_local = produits_de_recharge["produit_local"]
    tarif_5_euros = _tarif(produit_local, montant_en_euros=5)
    client_http = _client_connecte_admin(tenant_lespass)

    # Etape CONFIRMER : on recupere les champs que htmx enverra
    # / CONFIRM step: get the fields htmx will send
    reponse_confirmation = client_http.get(
        URL_RECHARGE_CARTE,
        {
            "tag_id": carte_client.tag_id,
            "uuid_pv": str(point_de_vente.uuid),
            "produit": str(produit_local.uuid),
            "prix": str(tarif_5_euros.uuid),
        },
    )
    champs = _champs_du_formulaire_de_recharge(reponse_confirmation.content.decode())

    # Clic sur la tuile ESPÈCE : hx-vals + hx-include (tag_id_cm de #addition-form)
    # / Tap on the CASH tile: hx-vals + hx-include
    champs["moyen_paiement"] = "espece"
    champs["tag_id_cm"] = carte_caissier.tag_id
    reponse_paiement = client_http.post(URL_PAYER, champs)

    assert reponse_paiement.status_code == 200
    assert 'data-testid="paiement-succes"' in reponse_paiement.content.decode()
    with schema_context("lespass"):
        solde_local = WalletService.obtenir_solde(
            carte_client.wallet_ephemere, produits_de_recharge["asset_local"]
        )
    assert solde_local == 500


def test_recharge_offerte_credite_la_carte_sans_paiement(
    tenant_lespass, point_de_vente, carte_caissier, carte_client, produits_de_recharge
):
    produit_cadeau = produits_de_recharge["produit_cadeau"]
    tarif_10 = _tarif(produit_cadeau, montant_en_euros=10)
    client_http = _client_connecte_admin(tenant_lespass)

    reponse_confirmation = client_http.get(
        URL_RECHARGE_CARTE,
        {
            "tag_id": carte_client.tag_id,
            "uuid_pv": str(point_de_vente.uuid),
            "produit": str(produit_cadeau.uuid),
            "prix": str(tarif_10.uuid),
        },
    )
    contenu_confirmation = reponse_confirmation.content.decode()
    assert 'data-testid="recharge-btn-offrir"' in contenu_confirmation
    # Une recharge offerte ne propose pas de moyen de paiement
    # / A free top-up offers no payment method
    assert 'data-testid="recharge-btn-especes"' not in contenu_confirmation

    champs = _champs_du_formulaire_de_recharge(contenu_confirmation)
    champs["tag_id_cm"] = carte_caissier.tag_id
    reponse_offrir = client_http.post(URL_IDENTIFIER_CLIENT, champs)

    assert reponse_offrir.status_code == 200
    assert 'data-testid="paiement-succes"' in reponse_offrir.content.decode()
    with schema_context("lespass"):
        solde_cadeau = WalletService.obtenir_solde(
            carte_client.wallet_ephemere, produits_de_recharge["asset_cadeau"]
        )
    assert solde_cadeau == 1000
