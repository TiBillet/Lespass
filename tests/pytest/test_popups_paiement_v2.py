"""
tests/pytest/test_popups_paiement_v2.py
Popups V2 : confirmation de paiement et fonds insuffisants.
/ V2 popups: payment confirmation and insufficient funds.

LOCALISATION : tests/pytest/test_popups_paiement_v2.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
1. confirmer() rend la popup V2 :
   - especes : pave numerique, champ #given-sum, « compte juste » par defaut ;
   - CB : pictogramme et consigne, pas de pave.
2. hx_funds_insufficient.html affiche le manque, la reference courte de la
   carte, les soldes en pastilles et les tuiles « Compléter avec ».
3. _soldes_locaux_pour_affichage() lit les soldes locaux d'un wallet
   (avant : le template attendait « wallets », jamais fourni → soldes vides).

Le JavaScript (calcul de la monnaie a rendre) n'est pas teste ici : pytest
n'execute pas de JS. Voir le scenario manuel dans le CHANGELOG.
/ JS (change computation) is not tested here: pytest runs no JS.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_popups_paiement_v2.py -v
"""

import pytest
from django.db import transaction as db_transaction
from django.template.loader import render_to_string
from django.test import Client as ClientHttpDjango
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser, Wallet
from Customers.models import Client
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import WalletService

PREFIXE = "[popup_v2_test]"
URL_CONFIRMER = "/laboutik/paiement/confirmer/"


@pytest.fixture(scope="module")
def tenant_lespass():
    return Client.objects.get(schema_name="lespass")


def _client_connecte_admin(tenant_lespass):
    """Client HTTP connecte en admin du tenant. / HTTP client logged in as tenant admin."""
    client_http = ClientHttpDjango(HTTP_HOST="lespass.tibillet.localhost")
    email = "popup_v2_test-admin@tibillet.localhost"
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


# ---------------------------------------------------------------------------
# 1. Confirmation de paiement
# ---------------------------------------------------------------------------


def test_confirmation_especes_affiche_le_pave_et_compte_juste(tenant_lespass):
    client_http = _client_connecte_admin(tenant_lespass)
    reponse = client_http.get(URL_CONFIRMER, {"method": "espece", "total": "12,5"})
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert 'data-testid="paiement-confirmation"' in contenu
    assert 'class="card-modal"' in contenu
    assert 'id="confirm-numpad"' in contenu
    assert 'data-cible="#confirm-especes"' in contenu
    assert 'id="given-sum"' in contenu
    assert 'data-testid="paiement-btn-valider"' in contenu
    assert "compte juste" in contenu or "exact" in contenu.lower()
    # Le total arrive avec une virgule et doit etre lu correctement
    # / The total arrives with a comma and must be parsed correctly
    assert "12,50" in contenu


def test_confirmation_cb_affiche_la_consigne_sans_pave(tenant_lespass):
    client_http = _client_connecte_admin(tenant_lespass)
    reponse = client_http.get(URL_CONFIRMER, {"method": "carte_bancaire", "total": "8"})
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert 'class="confirm-signal"' in contenu
    assert 'id="confirm-numpad"' not in contenu
    assert 'id="given-sum"' not in contenu
    assert 'data-testid="paiement-btn-valider"' in contenu


def test_confirmation_complement_soumet_le_formulaire_complement(tenant_lespass):
    """complement=1 : Valider soumet #complement-form (payer_complementaire),
    pas #addition-form vers payer.
    / complement=1: Validate submits #complement-form, not #addition-form to payer."""
    client_http = _client_connecte_admin(tenant_lespass)
    reponse = client_http.get(
        URL_CONFIRMER, {"method": "espece", "total": "9.00", "complement": "1"}
    )
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert 'id="confirm-numpad"' in contenu
    assert "htmx.trigger('#complement-form', 'submit')" in contenu
    assert "/laboutik/paiement/payer/" not in contenu
    assert "9,00" in contenu


def test_confirmation_sans_complement_soumet_vers_payer(tenant_lespass):
    """Sans complement=1 : comportement classique inchange.
    / Without complement=1: classic behaviour unchanged."""
    client_http = _client_connecte_admin(tenant_lespass)
    reponse = client_http.get(URL_CONFIRMER, {"method": "carte_bancaire", "total": "8"})
    contenu = reponse.content.decode()

    assert "/laboutik/paiement/payer/" in contenu
    assert "htmx.trigger('#complement-form', 'submit')" not in contenu


# ---------------------------------------------------------------------------
# 2. Fonds insuffisants
# ---------------------------------------------------------------------------


def test_fonds_insuffisants_affiche_manque_soldes_et_tuiles(tenant_lespass):
    contexte = {
        "currency_data": {"symbol": "€"},
        "payment": {"missing": 3.5},
        "card": {"name": "A49E8E2A"},
        "carte_ref": "8E2A",
        "soldes": [
            {
                "asset_name": "Monnaie locale",
                "asset_category": "TLF",
                "value_euros": 9.0,
            },
            {"asset_name": "Cadeau", "asset_category": "TNF", "value_euros": 2.0},
        ],
        "monnaie_name": "Monnaie locale",
        "payments_accepted": {"accepte_especes": True, "accepte_carte_bancaire": True},
        "uuid_transaction": "",
    }
    with tenant_context(tenant_lespass):
        contenu = render_to_string(
            "laboutik/partial/hx_funds_insufficient.html", contexte
        )

    assert 'data-testid="paiement-nfc-insuffisant"' in contenu
    assert "3,50" in contenu
    assert "·· 8E2A" in contenu
    # Le tag complet n'est plus affiche comme un nom / Full tag no longer shown as a name
    assert "A49E8E2A" not in contenu
    assert 'data-testid="paiement-insuffisant-solde-1"' in contenu
    assert "Monnaie locale" in contenu
    assert 'data-testid="paiement-insuffisant-btn-especes"' in contenu
    assert 'data-testid="paiement-insuffisant-btn-cb"' in contenu
    assert 'data-testid="paiement-insuffisant-btn-cashless"' in contenu


def test_fonds_insuffisants_sans_especes_ni_cb_propose_seulement_le_cashless(
    tenant_lespass,
):
    contexte = {
        "currency_data": {"symbol": "€"},
        "payment": {"missing": 1},
        "carte_ref": "8E2A",
        "soldes": [],
        "payments_accepted": {
            "accepte_especes": False,
            "accepte_carte_bancaire": False,
        },
        "uuid_transaction": "",
    }
    with tenant_context(tenant_lespass):
        contenu = render_to_string(
            "laboutik/partial/hx_funds_insufficient.html", contexte
        )

    assert 'data-testid="paiement-insuffisant-btn-especes"' not in contenu
    assert 'data-testid="paiement-insuffisant-btn-cb"' not in contenu
    assert 'data-testid="paiement-insuffisant-btn-cashless"' in contenu
    assert "card-pastilles" not in contenu


# ---------------------------------------------------------------------------
# 3. Helper des soldes
# ---------------------------------------------------------------------------


def test_soldes_locaux_pour_affichage_lit_les_tokens_du_wallet(tenant_lespass):
    from laboutik.views import _soldes_locaux_pour_affichage

    with tenant_context(tenant_lespass):
        wallet_du_lieu, _created = Wallet.objects.get_or_create(name=f"{PREFIXE} Lieu")
        asset_de_test, _created = Asset.objects.get_or_create(
            name=f"{PREFIXE} Locale",
            category=Asset.TLF,
            defaults={
                "currency_code": "EUR",
                "wallet_origin": wallet_du_lieu,
                "tenant_origin": tenant_lespass,
            },
        )
        # Le signal cree un produit de recharge : on archive tout de suite la
        # monnaie pour qu'elle n'apparaisse pas dans la vraie caisse.
        # / The signal creates a top-up product: archive the currency at once.
        asset_de_test.archive = True
        asset_de_test.active = False
        asset_de_test.save()
        from BaseBillet.models import Product
        from laboutik.models import PointDeVente

        for produit_de_test in Product.objects.filter(asset=asset_de_test):
            for pv in PointDeVente.objects.filter(products=produit_de_test):
                pv.products.remove(produit_de_test)

        wallet_client = Wallet.objects.create(name=f"{PREFIXE} Wallet client")
        with db_transaction.atomic():
            WalletService.crediter(
                wallet=wallet_client, asset=asset_de_test, montant_en_centimes=950
            )

        soldes = _soldes_locaux_pour_affichage(wallet_client)

        # Nettoyage / Cleanup
        Transaction.objects.filter(receiver=wallet_client).delete()
        Token.objects.filter(wallet=wallet_client).delete()
        wallet_client.delete()

    assert soldes == [
        {
            "asset_name": f"{PREFIXE} Locale",
            "asset_category": Asset.TLF,
            "value_euros": 9.5,
        }
    ]


# ---------------------------------------------------------------------------
# 4. Complement de paiement (design A · ticket de repartition)
# ---------------------------------------------------------------------------


def _contexte_complement(**changements):
    """
    Contexte d'exemple de _payer_par_nfc() : panier 15 €, carte ·· 4F2A a paye 6 €.
    / Example context from _payer_par_nfc(): 15 € cart, card paid 6 €.
    """
    contexte = {
        "action": "initUrlAddition();",
        "tag_id_carte1": "A49E4F2A",
        "detail_cascade": [
            {"name": "Monnaie locale", "montant_euros": "4.00"},
            {"name": "Réseau (FED)", "montant_euros": "2.00"},
        ],
        "cascade_carte1_json": '[["uuid-asset", 400]]',
        "total_nfc_carte1": 600,
        "total_nfc_carte1_euros": "6.00",
        "total_panier_euros": "15.00",
        "reste_euros": "9.00",
        "accepte_especes": True,
        "accepte_carte_bancaire": True,
        "autoriser_2eme_carte": True,
    }
    contexte.update(changements)
    return contexte


def _reste_lu_comme_dans_test_paiement_complementaire(contenu_html):
    """
    Meme regex que _extraire_reste() de test_paiement_complementaire.py :
    le reste doit y rester lisible.
    / Same regex as _extraire_reste(): the remaining amount must stay readable.
    """
    import re

    motif = re.compile(
        r"complement-reste-a-payer.*?<strong>\s*([0-9.,]+)\s*€", re.DOTALL
    )
    correspondance = motif.search(contenu_html)
    return correspondance.group(1).replace(",", ".") if correspondance else None


def test_complement_affiche_le_ticket_et_l_encart_reste(tenant_lespass):
    with tenant_context(tenant_lespass):
        contenu = render_to_string(
            "laboutik/partial/hx_complement_paiement.html", _contexte_complement()
        )

    assert 'data-testid="complement-paiement"' in contenu
    assert 'class="card-modal"' in contenu
    assert 'data-testid="complement-titre"' in contenu
    assert 'data-testid="complement-total-panier"' in contenu
    assert "15,00" in contenu
    assert "·· 4F2A" in contenu
    assert "6,00" in contenu
    assert 'data-testid="complement-detail-cascade"' in contenu
    assert 'class="card-encart-reste"' in contenu
    assert _reste_lu_comme_dans_test_paiement_complementaire(contenu) == "9.00"
    # Le formulaire cache propage toujours la cascade de la carte 1
    # / The hidden form still carries card 1's cascade
    assert 'data-testid="hidden-cascade-carte1"' in contenu
    assert 'id="complement-form"' in contenu


def test_complement_propose_les_trois_tuiles(tenant_lespass):
    with tenant_context(tenant_lespass):
        contenu = render_to_string(
            "laboutik/partial/hx_complement_paiement.html", _contexte_complement()
        )

    assert 'data-testid="btn-complement-especes"' in contenu
    assert 'data-testid="btn-complement-cb"' in contenu
    assert 'data-testid="btn-complement-2eme-carte"' in contenu
    # Les tuiles ne sont pas dans le formulaire (piege 58)
    # / Tiles are not inside the form (trap 58)
    debut_formulaire = contenu.index('id="complement-form"')
    fin_formulaire = contenu.index("</form>", debut_formulaire)
    assert "btn-complement" not in contenu[debut_formulaire:fin_formulaire]


def test_complement_tuiles_especes_et_cb_ouvrent_la_confirmation(tenant_lespass):
    """Les tuiles especes/CB ouvrent confirmer() dans #confirm (pave / rappel TPE)
    au lieu de soumettre directement le paiement.
    / Cash/card tiles open confirmer() instead of submitting the payment directly."""
    with tenant_context(tenant_lespass):
        contenu = render_to_string(
            "laboutik/partial/hx_complement_paiement.html", _contexte_complement()
        )

    assert "/laboutik/paiement/confirmer/?method=espece" in contenu
    assert "/laboutik/paiement/confirmer/?method=carte_bancaire" in contenu
    assert "total=9.00" in contenu
    assert "complement=1" in contenu
    # Plus de soumission directe au clic sur la tuile
    # / No more direct submit on tile click
    assert "onclick=\"askAdditionManageForm('updateInput','#addition-moyen-complement'" not in contenu


def test_complement_apres_deuxieme_carte_retire_la_tuile_carte(tenant_lespass):
    with tenant_context(tenant_lespass):
        contenu = render_to_string(
            "laboutik/partial/hx_complement_paiement.html",
            _contexte_complement(autoriser_2eme_carte=False, reste_euros="1.00"),
        )

    assert 'data-testid="btn-complement-2eme-carte"' not in contenu
    assert 'data-testid="btn-complement-especes"' in contenu
    assert _reste_lu_comme_dans_test_paiement_complementaire(contenu) == "1.00"


def test_complement_suit_les_moyens_du_point_de_vente(tenant_lespass):
    with tenant_context(tenant_lespass):
        contenu = render_to_string(
            "laboutik/partial/hx_complement_paiement.html",
            _contexte_complement(accepte_especes=False, accepte_carte_bancaire=False),
        )

    assert 'data-testid="btn-complement-especes"' not in contenu
    assert 'data-testid="btn-complement-cb"' not in contenu
    assert 'data-testid="btn-complement-2eme-carte"' in contenu


def test_attente_deuxieme_carte_utilise_la_popup_v2(tenant_lespass):
    with tenant_context(tenant_lespass):
        contenu = render_to_string(
            "laboutik/partial/hx_lire_nfc_complement.html",
            {
                "tag_id_carte1": "A49E4F2A",
                "cascade_carte1": "[]",
                "total_nfc_carte1": 600,
            },
        )

    assert 'data-testid="lire-nfc-complement"' in contenu
    assert 'class="card-modal"' in contenu
    assert 'data-testid="nfc-attente"' in contenu
