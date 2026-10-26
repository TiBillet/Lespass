"""
Tests de la désactivation du suivi de stock (Stock.actif).
/ Tests for deactivating stock tracking (Stock.actif).

LOCALISATION : tests/pytest/test_stock_desactivation.py

Spec : TECH_DOC/SESSIONS/INVENTAIRE/SPEC.md (chantier 01).

Règle testée : un stock non suivi (actif=False) se comporte comme un produit
sans stock pour le décompte (pas de mouvement, pas de blocage, pas de badge),
mais garde son unité (ventes au poids ou au volume) et son journal.
/ An untracked stock behaves like no stock for counting, but keeps its unit.

Marque django_db : chaque test tourne dans une transaction annulée à la fin.
Produits, stocks, ventes et mouvements créés disparaissent sans nettoyage.
/ django_db mark: each test runs in a rolled-back transaction.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_stock_desactivation.py -v
"""

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db

PREFIXE_NOM_PRODUIT = "TEST stock desactivation"


# ─────────────────────────────────────────────────────────────────────
# Fabriques / Factories
# ─────────────────────────────────────────────────────────────────────


def _produit_avec_stock(
    quantite=10,
    unite="UN",
    actif=True,
    autoriser_vente_hors_stock=True,
    seuil_alerte=None,
    poids_mesure=False,
):
    """
    Crée un produit de caisse, son tarif et son stock.
    À appeler dans un tenant_context.
    / Creates a POS product, its price and its stock (inside a tenant_context).

    :return: (produit, tarif, stock)
    """
    from BaseBillet.models import Price, Product
    from inventaire.models import Stock

    produit = Product.objects.create(
        name=f"{PREFIXE_NOM_PRODUIT} {uuid.uuid4().hex[:8]}",
        methode_caisse=Product.VENTE,
        publish=True,
    )
    tarif = Price.objects.create(
        product=produit,
        name=f"{produit.name} tarif",
        prix=Decimal("12.00") if poids_mesure else Decimal("3.00"),
        poids_mesure=poids_mesure,
        publish=True,
    )
    stock = Stock.objects.create(
        product=produit,
        quantite=quantite,
        unite=unite,
        seuil_alerte=seuil_alerte,
        autoriser_vente_hors_stock=autoriser_vente_hors_stock,
        actif=actif,
    )
    return produit, tarif, stock


def _point_de_vente_avec(produit):
    """Point de vente minimal qui propose le produit. / Minimal POS with the product."""
    from laboutik.models import PointDeVente

    point_de_vente = PointDeVente.objects.create(
        name=f"{PREFIXE_NOM_PRODUIT} PV {uuid.uuid4().hex[:6]}",
        comportement=PointDeVente.DIRECT,
    )
    point_de_vente.products.add(produit)
    return point_de_vente


def _nombre_de_mouvements(stock):
    from inventaire.models import MouvementStock

    return MouvementStock.objects.filter(stock=stock).count()


# ─────────────────────────────────────────────────────────────────────
# Fonction commune / Shared helper
# ─────────────────────────────────────────────────────────────────────


def test_stock_suivi_du_produit_ou_none_ignore_un_stock_non_suivi(tenant):
    """Stock actif → renvoyé ; stock non suivi → None.
    / Active stock → returned; untracked stock → None."""
    with tenant_context(tenant):
        from inventaire.models import stock_suivi_du_produit_ou_none

        produit_suivi, _tarif, stock_suivi = _produit_avec_stock(actif=True)
        produit_non_suivi, _tarif, _stock = _produit_avec_stock(actif=False)

        assert stock_suivi_du_produit_ou_none(produit_suivi) == stock_suivi
        assert stock_suivi_du_produit_ou_none(produit_non_suivi) is None


# ─────────────────────────────────────────────────────────────────────
# Service / Service
# ─────────────────────────────────────────────────────────────────────


def test_desactiver_suivi_garde_la_quantite_et_ne_cree_aucun_mouvement(tenant):
    """Désactiver : actif=False, quantité figée, aucun mouvement (D4).
    / Deactivate: actif=False, quantity frozen, no movement."""
    with tenant_context(tenant):
        from inventaire.services import StockService

        _produit, _tarif, stock = _produit_avec_stock(quantite=17)

        StockService.desactiver_suivi(stock)

        stock.refresh_from_db()
        assert stock.actif is False
        assert stock.quantite == 17
        assert _nombre_de_mouvements(stock) == 0


def test_reprendre_suivi_repart_de_la_quantite_comptee_avec_un_ajustement(
    tenant, admin_user
):
    """Reprendre : actif=True, quantité = quantité comptée, un mouvement AJ
    « Reprise du suivi » (D5).
    / Resume: actif=True, counted quantity, one AJ movement."""
    with tenant_context(tenant):
        from inventaire.models import MouvementStock, TypeMouvement
        from inventaire.services import StockService

        _produit, _tarif, stock = _produit_avec_stock(quantite=40, actif=False)

        StockService.reprendre_suivi(stock, quantite_comptee=12, utilisateur=admin_user)

        stock.refresh_from_db()
        assert stock.actif is True
        assert stock.quantite == 12
        mouvement = MouvementStock.objects.get(stock=stock)
        assert mouvement.type_mouvement == TypeMouvement.AJ
        assert mouvement.motif == "Reprise du suivi"
        assert mouvement.quantite_avant == 40
        assert mouvement.quantite == -28


# ─────────────────────────────────────────────────────────────────────
# Panneau d'opérations de l'admin / Admin operations panel
# ─────────────────────────────────────────────────────────────────────


def test_bouton_desactiver_du_panneau_passe_le_stock_en_non_suivi(tenant, admin_client):
    """POST du bouton « Désactiver le suivi » → stock non suivi, panneau en
    état « non suivi » avec le formulaire de reprise.
    / Deactivate button → untracked stock, panel shows the resume form."""
    with tenant_context(tenant):
        _produit, _tarif, stock = _produit_avec_stock(quantite=5)

    reponse = admin_client.post(f"/admin/inventaire/stock/{stock.pk}/desactiver-suivi/")

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert 'data-testid="stock-suivi-desactive"' in contenu
    assert 'data-testid="stock-btn-reprendre-suivi"' in contenu
    assert 'data-testid="btn-reception"' not in contenu
    with tenant_context(tenant):
        stock.refresh_from_db()
        assert stock.actif is False


def test_reprise_sans_quantite_comptee_est_refusee(tenant, admin_client):
    """Reprendre le suivi sans quantité → erreur, stock toujours non suivi (D5).
    / Resume without quantity → error, stock still untracked."""
    with tenant_context(tenant):
        _produit, _tarif, stock = _produit_avec_stock(quantite=5, actif=False)

    reponse = admin_client.post(
        f"/admin/inventaire/stock/{stock.pk}/reprendre-suivi/",
        data={"quantite_comptee": ""},
    )

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert 'data-testid="stock-action-error"' in contenu
    assert "Indiquez la quantité comptée" in contenu
    with tenant_context(tenant):
        stock.refresh_from_db()
        assert stock.actif is False
        assert _nombre_de_mouvements(stock) == 0


def test_reprise_avec_quantite_comptee_remet_le_panneau_d_operations(
    tenant, admin_client
):
    """Reprendre avec 12 → stock suivi à 12, le panneau montre les opérations.
    / Resume with 12 → tracked at 12, panel shows the operations."""
    with tenant_context(tenant):
        _produit, _tarif, stock = _produit_avec_stock(quantite=5, actif=False)

    reponse = admin_client.post(
        f"/admin/inventaire/stock/{stock.pk}/reprendre-suivi/",
        data={"quantite_comptee": "12"},
    )

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert 'data-testid="btn-reception"' in contenu
    assert 'data-testid="stock-btn-desactiver-suivi"' in contenu
    with tenant_context(tenant):
        stock.refresh_from_db()
        assert stock.actif is True
        assert stock.quantite == 12


def test_operation_manuelle_refusee_sur_un_stock_non_suivi(tenant, admin_client):
    """Une réception sur un stock non suivi est refusée, sans mouvement (D7).
    / A reception on an untracked stock is refused, no movement."""
    with tenant_context(tenant):
        _produit, _tarif, stock = _produit_avec_stock(quantite=5, actif=False)

    reponse = admin_client.post(
        f"/admin/inventaire/stock/{stock.pk}/action/",
        data={"type_mouvement": "RE", "quantite": "10", "motif": ""},
    )

    assert reponse.status_code == 200
    assert "Le suivi de stock est désactivé" in reponse.content.decode()
    with tenant_context(tenant):
        stock.refresh_from_db()
        assert stock.quantite == 5
        assert _nombre_de_mouvements(stock) == 0


def test_fiche_produit_d_un_stock_non_suivi_affiche_le_formulaire_de_reprise(
    tenant, admin_client
):
    """La section Stock d'un produit au stock non suivi montre le formulaire
    « Suivre le stock — quantité comptée », pas les opérations.
    / The product page shows the resume form for an untracked stock."""
    with tenant_context(tenant):
        produit, _tarif, _stock = _produit_avec_stock(quantite=5, actif=False)

    reponse = admin_client.get(f"/admin/BaseBillet/posproduct/{produit.pk}/change/")

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert 'data-testid="stock-form-reprendre-suivi"' in contenu
    assert 'data-testid="btn-reception"' not in contenu


# ─────────────────────────────────────────────────────────────────────
# Caisse / POS
# ─────────────────────────────────────────────────────────────────────


def test_vente_d_un_produit_au_stock_non_suivi_ne_decompte_rien(tenant):
    """Vente en caisse : aucun mouvement, quantité inchangée (D3).
    / POS sale: no movement, quantity unchanged."""
    with tenant_context(tenant):
        from django.db import transaction

        from laboutik.views import _creer_lignes_articles

        produit, tarif, stock = _produit_avec_stock(quantite=3, actif=False)
        articles_panier = [
            {"product": produit, "price": tarif, "quantite": 2, "prix_centimes": 600}
        ]

        with transaction.atomic():
            lignes, produits_stock_negatif = _creer_lignes_articles(
                articles_panier,
                "espece",
                point_de_vente=_point_de_vente_avec(produit),
            )

        assert len(lignes) == 1
        assert produits_stock_negatif == []
        stock.refresh_from_db()
        assert stock.quantite == 3
        assert _nombre_de_mouvements(stock) == 0


def test_stock_non_suivi_ne_bloque_pas_la_vente(tenant):
    """Rupture + vente hors stock interdite, mais stock non suivi : pas de blocage.
    / Out of stock + forbidden, but untracked: not blocked."""
    with tenant_context(tenant):
        from laboutik.views import _valider_stock_panier

        produit, tarif, _stock = _produit_avec_stock(
            quantite=0, actif=False, autoriser_vente_hors_stock=False
        )
        articles_panier = [
            {"product": produit, "price": tarif, "quantite": 1, "prix_centimes": 300}
        ]

        assert _valider_stock_panier(articles_panier) == []


def test_tuile_d_un_stock_non_suivi_n_a_pas_de_donnees_de_stock(tenant):
    """La tuile d'un stock non suivi : stock_quantite=None (pas de badge, pas de garde).
    / The tile of an untracked stock has stock_quantite=None."""
    with tenant_context(tenant):
        from laboutik.views import _construire_donnees_articles

        produit, _tarif, _stock = _produit_avec_stock(quantite=0, actif=False)

        articles = _construire_donnees_articles(_point_de_vente_avec(produit))
        article = next(a for a in articles if a["name"] == produit.name)

        assert article["stock_quantite"] is None
        assert "stock_bloquant" not in article


def test_tarif_au_poids_d_un_stock_non_suivi_garde_son_unite_sans_garde(tenant):
    """Tarif au volume, stock non suivi en CL : l'unité de saisie reste « cl »,
    mais le pavé n'a ni stock disponible ni blocage (D2).
    / Volume price, untracked CL stock: unit kept, no guard."""
    with tenant_context(tenant):
        from laboutik.views import _construire_donnees_articles

        produit, _tarif, _stock = _produit_avec_stock(
            quantite=0,
            unite="CL",
            actif=False,
            autoriser_vente_hors_stock=False,
            poids_mesure=True,
        )

        articles = _construire_donnees_articles(_point_de_vente_avec(produit))
        article = next(a for a in articles if a["name"] == produit.name)
        tarif_au_volume = next(t for t in article["tarifs"] if t.get("poids_mesure"))

        assert tarif_au_volume["unite_saisie_label"] == "cl"
        assert tarif_au_volume["prix_reference_label"] == "/L"
        assert tarif_au_volume["stock_disponible"] is None
        assert tarif_au_volume["autoriser_hors_stock"] is True


def test_diviseur_au_volume_lu_sur_un_stock_non_suivi(tenant):
    """Le prix au volume d'un stock non suivi en CL se divise par 100 (litre),
    pas par 1000 (kilo) : l'unité du stock reste lue (D2).
    / The volume price divisor still reads the untracked stock's unit."""
    with tenant_context(tenant):
        from laboutik.views import _diviseur_de_la_quantite_saisie

        produit, _tarif, _stock = _produit_avec_stock(unite="CL", actif=False)

        assert _diviseur_de_la_quantite_saisie(produit) == Decimal(100)


def test_panel_caisse_refuse_les_operations_sur_un_stock_non_suivi(tenant):
    """Le panel d'appui long refuse une opération et la bascule « vente hors
    stock » sur un stock non suivi (404), sans rien modifier (D7).
    / The long-press panel refuses operations on an untracked stock (404)."""
    from django.http import Http404
    from django.test import RequestFactory

    with tenant_context(tenant):
        from laboutik.views import ArticlePanelViewSet

        produit, _tarif, stock = _produit_avec_stock(quantite=5, actif=False)
        requete = RequestFactory().post("/", data={"quantite": "3", "motif": ""})
        requete.user = SimpleNamespace(is_authenticated=False)
        vue_du_panel = ArticlePanelViewSet()

        with pytest.raises(Http404):
            vue_du_panel.stock_action(requete, produit.uuid, "reception")
        with pytest.raises(Http404):
            vue_du_panel.toggle_bloquant(requete, produit.uuid)

        stock.refresh_from_db()
        assert stock.quantite == 5
        assert stock.autoriser_vente_hors_stock is True
        assert _nombre_de_mouvements(stock) == 0


# ─────────────────────────────────────────────────────────────────────
# Badge WebSocket / WebSocket badge
# ─────────────────────────────────────────────────────────────────────


def test_badge_websocket_d_un_stock_non_suivi_est_vide(tenant):
    """Le badge envoyé par WebSocket pour un stock non suivi n'a ni pastille
    ni data-* : la tuile se comporte comme sans stock (D9).
    / The WebSocket badge of an untracked stock has no badge and no data-*."""
    with tenant_context(tenant):
        from django.template.loader import render_to_string

        from wsocket.broadcast import donnees_badge_stock

        _produit, _tarif, stock = _produit_avec_stock(
            quantite=0, actif=False, autoriser_vente_hors_stock=False
        )
        donnees = donnees_badge_stock(stock)
        html = render_to_string(
            "laboutik/partial/hx_stock_badge.html", {"produits_stock": [donnees]}
        )

        assert donnees["suivi"] is False
        assert f'id="stock-badge-{stock.product_id}"' in html
        assert "data-stock-quantite" not in html
        assert "data-stock-bloquant" not in html
        assert "Épuisé" not in html


# ─────────────────────────────────────────────────────────────────────
# Liste des produits / Product list
# ─────────────────────────────────────────────────────────────────────


def test_filtre_etat_du_stock_range_un_stock_non_suivi_dans_non_suivi(tenant):
    """Un stock non suivi à 0 sort dans « Non suivi », pas dans « Épuisé ».
    / An untracked stock at 0 shows under "Non suivi", not "Épuisé"."""
    with tenant_context(tenant):
        from Administration.admin.stock_fiche_produit import EtatStockFilter
        from BaseBillet.models import Product

        produit, _tarif, _stock = _produit_avec_stock(quantite=0, actif=False)
        tous_les_produits = Product.objects.filter(pk=produit.pk)

        def produits_du_filtre(valeur):
            # Django 4.2 : la valeur du paramètre est une chaîne
            # / Django 4.2: the parameter value is a string
            filtre = EtatStockFilter(None, {"etat_stock": valeur}, Product, None)
            assert filtre.value() == valeur
            return list(filtre.queryset(None, tous_les_produits))

        assert produits_du_filtre("non_suivi") == [produit]
        assert produits_du_filtre("rupture") == []
        assert produits_du_filtre("ok") == []


def test_badge_de_la_liste_d_un_stock_non_suivi_dit_non_suivi(tenant):
    """La colonne Stock de la liste affiche « Non suivi » avec le lien vers la
    section Stock (c'est là qu'on reprend le suivi).
    / The list column shows "Non suivi" with the link to the Stock section."""
    with tenant_context(tenant):
        from Administration.admin.stock_fiche_produit import (
            display_stock_produit_caisse,
        )

        produit, _tarif, _stock = _produit_avec_stock(quantite=0, actif=False)
        html = str(display_stock_produit_caisse(produit))

        assert "Non suivi" in html
        assert "Épuisé" not in html
        assert "#section-stock" in html


# ─────────────────────────────────────────────────────────────────────
# D10 — stock créé automatiquement pour un fût / auto-created keg stock
# ─────────────────────────────────────────────────────────────────────


def test_stock_cree_automatiquement_pour_un_fut_n_est_pas_suivi(tenant):
    """Fût enregistré sans « Suivre le stock » : save_related crée un stock en CL,
    NON suivi (D10). L'unité sert aux ventes en litres, sans décompte.
    / Keg saved without "Track stock": the auto-created CL stock is untracked."""
    from django.test import RequestFactory

    with tenant_context(tenant):
        from Administration.admin.site import staff_admin_site
        from BaseBillet.models import FutProduct, Price, Product
        from inventaire.models import Stock

        fut = Product.objects.create(
            name=f"{PREFIXE_NOM_PRODUIT} fut {uuid.uuid4().hex[:6]}",
            categorie_article=Product.FUT,
            publish=True,
        )
        Price.objects.create(product=fut, name="Pinte", prix=Decimal("5.00"))

        admin_des_futs = staff_admin_site._registry[FutProduct]
        formulaire_fictif = SimpleNamespace(instance=fut, save_m2m=lambda: None)
        with mock.patch("Administration.admin.products.messages"):
            admin_des_futs.save_related(
                RequestFactory().post("/"), formulaire_fictif, [], False
            )

        stock = Stock.objects.get(product=fut)
        assert stock.unite == "CL"
        assert stock.actif is False


# ─────────────────────────────────────────────────────────────────────
# Tireuse : changement de fût / Tap: keg swap
# ─────────────────────────────────────────────────────────────────────


def test_changer_de_fut_vers_un_stock_non_suivi_remet_le_reservoir_a_zero(tenant):
    """Le nouveau fût a un stock de 3000 cl, mais non suivi : la tireuse le traite
    comme un fût sans stock, le réservoir repart à 0 (D8).
    Un stock suivi aurait donné 30 000 ml.
    / New keg with an untracked 3000 cl stock: reservoir resets to 0."""
    with tenant_context(tenant):
        from BaseBillet.models import Product
        from controlvanne.models import TireuseBec
        from inventaire.models import Stock

        nom_de_la_tireuse = f"{PREFIXE_NOM_PRODUIT} tireuse {uuid.uuid4().hex[:6]}"
        premier_fut = Product.objects.create(
            name=f"{PREFIXE_NOM_PRODUIT} fut A", categorie_article=Product.FUT
        )
        fut_au_stock_non_suivi = Product.objects.create(
            name=f"{PREFIXE_NOM_PRODUIT} fut B", categorie_article=Product.FUT
        )
        Stock.objects.create(
            product=fut_au_stock_non_suivi, quantite=3000, unite="CL", actif=False
        )
        tireuse = TireuseBec.objects.create(
            nom_tireuse=nom_de_la_tireuse,
            enabled=True,
            fut_actif=premier_fut,
            reservoir_illimite=False,
            reservoir_ml=Decimal("150.00"),
        )

        tireuse.fut_actif = fut_au_stock_non_suivi
        tireuse.save()
        tireuse.refresh_from_db()

        assert tireuse.reservoir_ml == Decimal("0.00")
