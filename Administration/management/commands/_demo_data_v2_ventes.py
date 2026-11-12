"""
Helper du management command `demo_data_v2` : les ventes de démo du lieu `lespass`,
écrites par le VRAI moteur de vente, et leurs clôtures J, H, M, A.
/ Helper for `demo_data_v2`: the demo sales of the `lespass` venue, written by the REAL
sales engine, and their J, H, M, A closures.

LOCALISATION : Administration/management/commands/_demo_data_v2_ventes.py

TROIS ÉTAPES, appelées dans cet ordre par `demo_data_v2` (`_handle_seed_ventes`) :
1. `seed_ventes_demo` : l'historique, 24 mois complets avant le mois en cours. Chaque
   mois reçoit le même programme (deux journées, le 6 et le 20) : 30 ventes, dont
   2 avoirs, et 1 000,00 € de chiffre d'affaires. Voir `_ecrire_la_soiree_concert` et
   `_ecrire_la_journee_atelier`.
2. `seed_ventes_de_la_veille_par_le_moteur` (puis le récap, `_demo_data_v2_recap.py`) :
   quelques ventes d'hier. Elles sont écrites APRÈS l'historique : plus récentes, leurs
   numéros suivent.
3. `seed_clotures_demo` : les clôtures des périodes finies, jour après jour, comme la
   tâche horaire les aurait faites.
/ Three steps: the 24-month history, yesterday's sales, then the closures.

LE VRAI CHEMIN (BaseBillet/services_vente.py) :
`ouvrir_vente` → `ajouter_article` (montants par `calculer_montants_article`,
`hors_chiffre_affaires` figé depuis le produit) → `ajouter_reglement` →
`encaisser_vente(vente, datetime_encaissement=heure)`. Les avoirs passent par
`ecrire_la_vente_d_avoir_d_une_ligne` et `ecrire_la_vente_d_avoir_d_une_vente`.
/ The real path of the sales service, credit notes included.

L'ORDRE CHRONOLOGIQUE : une vente reçoit son numéro et son empreinte chaînée à
l'encaissement. Les ventes sont donc écrites dans l'ordre de leurs heures : sinon les
numéros ne suivraient plus les dates, et une J vérifierait une plage de numéros qui
déborde sur d'autres journées.
/ Sales are written in time order: numbers and chained fingerprints follow the dates.

AUCUN APPEL RÉSEAU : aucun `Paiement_stripe` (les avoirs Stripe sont « à rembourser à la
main », comme ceux de l'admin), aucun remboursement Stripe `REFUNDED`, aucune
transaction Fedow, avoirs d'origine ADMIN (rien n'est envoyé à l'ancien LaBoutik),
adhésions au statut ONCE (jamais ADMIN : un signal écrirait une vente de plus).
/ No network call: no Stripe payment, no Stripe refund, no Fedow transaction.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-07-seed-ventes-reelles.md
Tests : tests/pytest/test_demo_data_ventes.py, tests/pytest/test_demo_ventes_de_la_veille.py
"""
import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Min
from django.utils import timezone

logger = logging.getLogger(__name__)


# Préfixe des produits et événements créés par la démo : le reset les retrouve par lui.
# / Prefix of the demo products and events: the reset finds them by it.
DEMO_PRODUCT_PREFIX = "[DEMO] "

# L'historique couvre les 24 mois complets avant le mois en cours.
# / The history covers the 24 full months before the current month.
NOMBRE_DE_MOIS_DE_VENTES_PAR_DEFAUT = 24

# Le chiffre d'affaires de chaque mois du programme, en centimes (voir la spec §3).
# / The revenue of each month of the programme, in cents.
CHIFFRE_D_AFFAIRES_D_UN_MOIS_EN_CENTIMES = 100000

# Les deux journées de ventes de chaque mois. Des jours qui existent dans tous les mois.
# / The two sales days of each month. Days that exist in every month.
JOUR_DE_LA_SOIREE_CONCERT = 6
JOUR_DE_LA_JOURNEE_ATELIER = 20

# Les personnes de démo dont le reset efface les objets (adhésions, réservations,
# réservations de ressources, inscriptions bénévoles) : celle de ce module et les
# quatre du récap (`_demo_data_v2_recap.py`, `recap-<prénom>@example.com`).
# / Demo people whose objects the reset deletes.
EMAIL_DU_CLIENT_DE_DEMO = "demo-ventes@example.com"
PREFIXE_DES_EMAILS_DU_RECAP = "recap-"
DOMAINE_DES_EMAILS_DE_DEMO = "@example.com"


# ============================================================================
# Les objets de la démo : produits, tarifs, client, événements.
# / Demo objects: products, prices, customer, events.
# ============================================================================


def _produit_demo(name, categorie_article, taux_de_tva):
    """
    Crée (ou récupère) un produit de démo, marqué par DEMO_PRODUCT_PREFIX, avec sa TVA.
    La TVA est celle du PRODUIT (`Product.tva`) : c'est elle que lit le moteur
    (`taux_de_tva_du_produit`, laboutik/plan_comptable.py), jamais celle du lieu.
    / Get/create a demo product with its own VAT (read by the engine).
    """
    from BaseBillet.models import Product, Tva

    tva_du_produit, _tva_creee = Tva.objects.get_or_create(tva_rate=taux_de_tva)
    nom = f"{DEMO_PRODUCT_PREFIX}{name}"
    produit, _produit_cree = Product.objects.get_or_create(
        name=nom,
        defaults={
            "categorie_article": categorie_article,
            "tva": tva_du_produit,
            "publish": False,  # invisible pour le public / hidden from the public
        },
    )
    produit_a_corriger = (
        produit.categorie_article != categorie_article
        or produit.tva_id != tva_du_produit.pk
    )
    if produit_a_corriger:
        produit.categorie_article = categorie_article
        produit.tva = tva_du_produit
        produit.save(update_fields=["categorie_article", "tva"])
    return produit


def _prix_demo(produit, name, prix_ttc):
    """
    Crée (ou récupère) le tarif d'un produit de démo, au prix donné (Decimal, euros).
    / Get/create a demo product's price.
    """
    from BaseBillet.models import Price

    tarif, _tarif_cree = Price.objects.get_or_create(
        product=produit,
        name=name,
        defaults={"prix": prix_ttc},
    )
    if tarif.prix != prix_ttc:
        tarif.prix = prix_ttc
        tarif.save(update_fields=["prix"])
    return tarif


def _user_demo():
    """
    Crée (ou récupère) le client de démo `demo-ventes@example.com`.
    / Get/create the demo customer.
    """
    from AuthBillet.models import TibilletUser

    user, _user_cree = TibilletUser.objects.get_or_create(
        email=EMAIL_DU_CLIENT_DE_DEMO,
        defaults={
            "username": "demo-ventes",
            "is_active": True,
            "first_name": "Demo",
            "last_name": "Ventes",
        },
    )
    return user


def _event_demo(name, datetime_event):
    """
    Crée (ou récupère) un événement de démo, marqué par DEMO_PRODUCT_PREFIX.
    / Get/create a demo Event, marked by DEMO_PRODUCT_PREFIX.
    """
    from BaseBillet.models import Event

    nom = f"{DEMO_PRODUCT_PREFIX}{name}"
    event, _event_cree = Event.objects.get_or_create(
        name=nom,
        defaults={
            "datetime": datetime_event,
            "published": False,  # invisible des users finaux / hidden from end users
        },
    )
    return event


def _reservation_demo(user, event, status="V"):
    """
    Crée une Reservation directement en status final (V=VALID par défaut), avec
    mail_send=True pour éviter tout envoi.
    / Create a Reservation directly in final status, mail_send=True.
    """
    from BaseBillet.models import Reservation

    return Reservation.objects.create(
        user_commande=user,
        event=event,
        status=status,
        mail_send=True,  # bloque l'envoi de mail si un signal le déclenche
    )


def _membership_demo(user, price, payment_method):
    """
    Crée une Membership au statut ONCE (payée en ligne), valable un an à partir de
    « maintenant » (l'heure de la vente quand l'appelant a remplacé `timezone.now`).
    Jamais le statut ADMIN : un signal écrirait une LigneArticle de plus (et appellerait
    Stripe par get_or_create_price_sold).
    / Create a Membership in ONCE status, valid one year. Never ADMIN (a signal would
    write one more line).
    """
    from BaseBillet.models import Membership

    return Membership.objects.create(
        user=user,
        price=price,
        contribution_value=price.prix,
        payment_method=payment_method,
        status=Membership.ONCE,
        deadline=timezone.now() + timedelta(days=365),
    )


def _tarif_vendu_par_le_moteur(produit, tarif, evenement=None):
    """
    Le tarif vendu (ProductSold + PriceSold) d'un produit, comme la caisse le crée,
    sans appel Stripe (`id_price_stripe` reste vide).
    / The sold price of a product, as the POS creates it, without any Stripe call.
    """
    from BaseBillet.models import ProductSold, PriceSold

    produit_vendu, _produit_vendu_cree = ProductSold.objects.get_or_create(
        product=produit,
        event=evenement,
        defaults={"categorie_article": produit.categorie_article},
    )
    tarif_vendu, _tarif_vendu_cree = PriceSold.objects.get_or_create(
        productsold=produit_vendu,
        price=tarif,
        defaults={"prix": tarif.prix},
    )
    return tarif_vendu


def _une_vente_reglee(
    articles,
    moyen,
    origine,
    heure,
    point_de_vente=None,
    client=None,
    monnaie_du_reglement=None,
):
    """
    Une vente complète par le moteur : ouverte, ses articles, UN règlement du total
    (aucun si le total est 0 : une vente gratuite n'a pas de règlement), puis encaissée
    à l'heure donnée (heure scellée dans l'empreinte, comme la reprise).
    / One full sale through the engine, settled at the given time.

    `timezone.now` vaut `heure` pendant toute l'écriture : les dates `auto_now_add`
    (article, règlement, création de la vente) sont celles de la vente, pas celles du
    lancement du seed. Sans cela, un article d'il y a deux ans serait daté d'aujourd'hui.
    / `timezone.now` is `heure` during the whole write: auto_now_add dates are the
    sale's own.

    :param articles: liste de dict :
        - "produit", "tarif_vendu", "quantite" (obligatoires) ;
        - "prix_unitaire" : centimes (int), sinon le prix du tarif vendu ;
        - "offert" : True pour un article entièrement offert (bouton OFFRIR) ;
        - "en_jetons" : True pour un article payé en jetons cadeau (part en jetons =
          son net, hors TVA, D8 bis) ;
        - "champs" : champs de la ligne (reservation, membership, asset…). Le moyen
          historique `payment_method` vaut `moyen` s'il n'est pas donné.
    :param moyen: `PaymentMethod` du règlement
    :param origine: `SaleOrigin` de la vente
    :param heure: datetime avec fuseau
    :param point_de_vente: `laboutik.PointDeVente`, ou None
    :param client: l'utilisateur acheteur, ou None
    :param monnaie_du_reglement: uuid de la monnaie (cashless LE, LG), ou None
    :return: la `Vente` réglée
    """
    from BaseBillet.models import LigneArticle, PaymentMethod
    from BaseBillet.models_vente import Vente
    from BaseBillet.services_vente import (
        ouvrir_vente, ajouter_article, ajouter_reglement, calculer_montants_article,
        encaisser_vente,
    )
    from laboutik.views import _taux_tva_de_la_ligne_de_caisse

    with patch("django.utils.timezone.now", return_value=heure):
        vente = ouvrir_vente(
            origine=origine,
            nature=Vente.Nature.VENTE,
            point_de_vente=point_de_vente,
            client=client,
        )
        total_de_la_vente = 0
        for article in articles:
            tarif_vendu = article["tarif_vendu"]
            quantite = Decimal(article["quantite"])
            if "prix_unitaire" in article:
                prix_unitaire = article["prix_unitaire"]
            else:
                prix_unitaire = int(tarif_vendu.prix * 100)

            champs_de_la_ligne = dict(article.get("champs", {}))
            if "payment_method" not in champs_de_la_ligne:
                champs_de_la_ligne["payment_method"] = moyen

            # Un article offert est une ligne FREE (taux 0) ; un article payé en jetons
            # garde le taux du produit, sa part en jetons le sort de la TVA.
            # / An offered item is a FREE line (rate 0); a token-paid item keeps the
            # product's rate.
            article_offert = article.get("offert", False)
            if article_offert:
                champs_de_la_ligne["payment_method"] = PaymentMethod.FREE
            taux_tva = _taux_tva_de_la_ligne_de_caisse(
                article["produit"], champs_de_la_ligne["payment_method"]
            )

            part_en_jetons = 0
            if article.get("en_jetons", False):
                montants_sans_jetons = calculer_montants_article(
                    prix_unitaire=prix_unitaire, quantite=quantite, taux_tva=taux_tva,
                )
                part_en_jetons = montants_sans_jetons["total_ttc"]

            if "status" not in champs_de_la_ligne:
                champs_de_la_ligne["status"] = LigneArticle.VALID

            ligne = ajouter_article(
                vente,
                pricesold=tarif_vendu,
                quantite=quantite,
                prix_unitaire=prix_unitaire,
                taux_tva=taux_tva,
                offert_en_totalite=article_offert,
                part_en_jetons=part_en_jetons,
                sale_origin=origine,
                point_de_vente=point_de_vente,
                **champs_de_la_ligne,
            )
            total_de_la_vente += ligne.total_ttc

        if total_de_la_vente != 0:
            ajouter_reglement(
                vente, moyen=moyen, montant=total_de_la_vente, asset=monnaie_du_reglement,
            )
        return encaisser_vente(vente, datetime_encaissement=heure)


def _monnaie_du_lieu(categorie):
    """
    L'uuid de la monnaie du lieu de cette catégorie (`fedow_core.Asset` : TLF monnaie
    locale, TNF cadeau), ou None. Aucun appel à Fedow : une lecture.
    / The venue's currency uuid of this category, or None. A read, no Fedow call.

    La monnaie FED est celle de l'ancien Fedow (`AssetFedowPublic` STRIPE_FED_FIAT),
    comme pour les virements reçus (`ecrire_la_vente_d_un_virement_recu`,
    BaseBillet/services_vente.py) : c'est elle que le plan comptable relie au compte du
    réseau fédéré. À défaut, le FED de `fedow_core`.
    / The FED currency is the legacy Fedow one, as for received transfers; else the
    fedow_core FED.
    """
    from fedow_core.models import Asset
    from fedow_public.models import AssetFedowPublic

    if categorie == Asset.FED:
        monnaie = AssetFedowPublic.objects.filter(
            category=AssetFedowPublic.STRIPE_FED_FIAT
        ).first()
        if monnaie is None:
            monnaie = Asset.objects.filter(category=Asset.FED).first()
    else:
        monnaie = Asset.objects.filter(
            tenant_origin__schema_name=connection.schema_name,
            category=categorie,
            active=True,
        ).first()
    if monnaie is None:
        return None
    return monnaie.uuid


def _a_l_heure(jour, heure, minute, fuseau_du_lieu):
    """Le datetime `jour` à `heure:minute`, heure du lieu. / Local datetime."""
    return datetime.combine(jour, time(heure, minute), tzinfo=fuseau_du_lieu)


# ============================================================================
# Le catalogue de la démo : produits en ligne [DEMO] et produits de caisse.
# / The demo catalogue: [DEMO] online products and POS products.
# ============================================================================


def _catalogue_de_la_demo(fuseau_du_lieu, premier_jour, dernier_jour):
    """
    Les produits, tarifs, événements et monnaies du programme, créés une fois.
    / The programme's products, prices, events and currencies, created once.

    - Produits en ligne : `[DEMO] …`, créés ici, avec leur TVA (billets de concert
      5,5 %, ateliers 10 %, adhésions et recharges 0 %).
    - Produits de caisse : ceux de `create_test_pos_data` (Bière, Coca, Vin rouge,
      Chips, Sandwich, Café, « Recharge Monnaie locale »), points de vente « Bar » et
      « Cashless ». Leur catégorie de caisse a le compte 707000 : le FEC ne manque
      d'aucun compte. Absents : None, les ventes de caisse sont sautées.
    / Online products are created here; POS products come from create_test_pos_data.

    :return: dict des objets du programme
    """
    from BaseBillet.models import Price, Product
    from fedow_core.models import Asset
    from laboutik.models import PointDeVente

    taux_5_5 = Decimal("5.50")
    taux_10 = Decimal("10.00")
    taux_0 = Decimal("0.00")

    catalogue = {"client": _user_demo()}

    # --- Événements : un concert, un atelier / Events ---
    catalogue["concert"] = _event_demo(
        "Concert Jazz",
        _a_l_heure(premier_jour, 20, 30, fuseau_du_lieu),
    )
    catalogue["atelier"] = _event_demo(
        "Atelier menuiserie",
        _a_l_heure(dernier_jour, 14, 0, fuseau_du_lieu),
    )

    # --- Produits en ligne [DEMO] / Online [DEMO] products ---
    produits_en_ligne = [
        # (clé, nom, catégorie, TVA, nom du tarif, prix)
        ("billet_plein", "Concert Jazz - Plein", Product.BILLET, taux_5_5, "Plein", "20.00"),
        ("billet_reduit", "Concert Jazz - Reduit", Product.BILLET, taux_5_5, "Reduit", "16.00"),
        ("billet_offert", "Concert Jazz - Offert", Product.FREERES, taux_0, "Offert", "0.00"),
        ("atelier_normal", "Atelier - Normal", Product.BILLET, taux_10, "Normal", "30.00"),
        ("atelier_solidaire", "Atelier - Solidaire", Product.BILLET, taux_10, "Solidaire", "10.00"),
        ("atelier_libre", "Atelier - Prix libre", Product.BILLET, taux_10, "Prix libre", "0.00"),
        ("adhesion_annuelle", "Adhesion annuelle", Product.ADHESION, taux_0, "Adhesion standard", "25.00"),
        ("adhesion_soutien", "Adhesion Soutien", Product.ADHESION, taux_0, "Soutien", "50.00"),
        ("adhesion_virement", "Adhesion par virement", Product.ADHESION, taux_0, "Don associatif", "100.00"),
        ("adhesion_sepa", "Adhesion Stripe SEPA", Product.ADHESION, taux_0, "Cotisation pro SEPA", "30.00"),
        ("adhesion_mensuelle", "Adhesion mensuelle", Product.ADHESION, taux_0, "Mensuel", "10.00"),
        ("adhesion_libre", "Adhesion prix libre", Product.ADHESION, taux_0, "Prix libre a partir de 0", "0.00"),
        ("recharge_en_ligne", "Recharge cashless en ligne", Product.RECHARGE_CASHLESS, taux_0, "Recharge 20", "20.00"),
        ("recharge_federee", "Recharge federee en ligne", Product.RECHARGE_CASHLESS_FED, taux_0, "Recharge 10", "10.00"),
    ]
    for cle, nom, categorie, taux, nom_du_tarif, prix in produits_en_ligne:
        produit = _produit_demo(nom, categorie, taux)
        tarif = _prix_demo(produit, nom_du_tarif, Decimal(prix))
        if cle.startswith("billet_"):
            evenement = catalogue["concert"]
        elif cle.startswith("atelier_"):
            evenement = catalogue["atelier"]
        else:
            evenement = None
        catalogue[cle] = {
            "produit": produit,
            "tarif": tarif,
            "tarif_vendu": _tarif_vendu_par_le_moteur(produit, tarif, evenement),
        }

    # --- Produits de caisse (create_test_pos_data) / POS products ---
    catalogue["bar"] = PointDeVente.objects.filter(name="Bar").first()
    catalogue["cashless"] = PointDeVente.objects.filter(name="Cashless").first()
    noms_des_produits_de_caisse = {
        "biere": "Biere",
        "coca": "Coca",
        "vin_rouge": "Vin rouge",
        "chips": "Chips",
        "sandwich": "Sandwich",
        "cafe": "Cafe",
    }
    for cle, nom in noms_des_produits_de_caisse.items():
        produit = Product.objects.filter(name=nom, methode_caisse=Product.VENTE).first()
        tarif = Price.objects.filter(product=produit, name=f"Tarif {nom}").first()
        if produit is None or tarif is None:
            catalogue[cle] = None
            continue
        catalogue[cle] = {
            "produit": produit,
            "tarif": tarif,
            "tarif_vendu": _tarif_vendu_par_le_moteur(produit, tarif),
        }

    # La recharge en euros de la caisse (créée par le signal de la monnaie locale) et
    # son tarif « 10 ».
    # / The POS euro top-up (created by the local currency's signal), its "10" price.
    produit_de_recharge = Product.objects.filter(
        methode_caisse=Product.RECHARGE_EUROS
    ).first()
    tarif_de_recharge = Price.objects.filter(
        product=produit_de_recharge, prix=Decimal("10.00")
    ).first()
    if produit_de_recharge is None or tarif_de_recharge is None:
        catalogue["recharge_caisse"] = None
    else:
        catalogue["recharge_caisse"] = {
            "produit": produit_de_recharge,
            "tarif": tarif_de_recharge,
            "tarif_vendu": _tarif_vendu_par_le_moteur(produit_de_recharge, tarif_de_recharge),
        }

    # --- Monnaies du lieu / Venue currencies ---
    catalogue["monnaie_locale"] = _monnaie_du_lieu(Asset.TLF)
    catalogue["monnaie_cadeau"] = _monnaie_du_lieu(Asset.TNF)
    catalogue["monnaie_federee"] = _monnaie_du_lieu(Asset.FED)
    return catalogue


# ============================================================================
# Le programme d'un mois : la soirée concert (le 6) et la journée atelier (le 20).
# / A month's programme: the concert evening (6th) and the workshop day (20th).
# ============================================================================


def _ecrire_la_soiree_concert(jour, catalogue, fuseau_du_lieu, resultat):
    """
    La soirée concert d'un jour : billets et adhésions en ligne, recharges en ligne,
    caisse du Bar et du Cashless, puis deux avoirs. 24 ventes, 670 € de CA.
    / The concert evening: online tickets and memberships, online top-ups, the Bar and
    Cashless registers, then two credit notes. 24 sales, 670 € revenue.

    :param resultat: dict des stats, complété ici ("nombre_de_ventes", "cas_sautes")
    """
    from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin
    from BaseBillet.models_vente import Vente
    from BaseBillet.services_vente import (
        ecrire_la_vente_d_avoir_d_une_ligne, ecrire_la_vente_d_avoir_d_une_vente,
    )

    client = catalogue["client"]
    concert = catalogue["concert"]

    def heure(h, m):
        return _a_l_heure(jour, h, m, fuseau_du_lieu)

    def en_ligne(cle, quantite, moyen, h, m, origine=SaleOrigin.LESPASS, champs=None):
        champs_de_la_ligne = dict(champs or {})
        # Un règlement SF (Stripe fédéré) est de la monnaie fédérée : il porte sa
        # monnaie FED, c'est elle qui donne son compte (`compte_pour_reglement`,
        # laboutik/plan_comptable.py). Sans elle, l'export de la J est refusé.
        # / An SF payment is federated currency: it carries its FED currency, which
        # gives its account. Without it, the J export is refused.
        monnaie_du_reglement = None
        if moyen == PaymentMethod.STRIPE_FED:
            monnaie_du_reglement = catalogue["monnaie_federee"]
            if "asset" not in champs_de_la_ligne:
                champs_de_la_ligne["asset"] = monnaie_du_reglement
        article = {
            "produit": catalogue[cle]["produit"],
            "tarif_vendu": catalogue[cle]["tarif_vendu"],
            "quantite": quantite,
            "champs": champs_de_la_ligne,
        }
        vente = _une_vente_reglee(
            articles=[article], moyen=moyen, origine=origine, heure=heure(h, m),
            client=client, monnaie_du_reglement=monnaie_du_reglement,
        )
        resultat["nombre_de_ventes"] += 1
        return vente

    def reservation_a_l_heure(h, m):
        with patch("django.utils.timezone.now", return_value=heure(h, m)):
            return _reservation_demo(client, concert)

    def adhesion_a_l_heure(cle, moyen, h, m):
        with patch("django.utils.timezone.now", return_value=heure(h, m)):
            return _membership_demo(client, catalogue[cle]["tarif"], moyen)

    # --- En ligne : billets du concert (TVA 5,5 %) / Online: concert tickets ---
    vente_des_billets_pleins = en_ligne(
        "billet_plein", 10, PaymentMethod.STRIPE_FED, 10, 0,
        champs={"reservation": reservation_a_l_heure(10, 0)},
    )
    en_ligne(
        "billet_reduit", 5, PaymentMethod.STRIPE_NOFED, 11, 0,
        champs={"reservation": reservation_a_l_heure(11, 0)},
    )
    # Billets offerts et atelier à prix libre payé 0 € : ventes sans règlement.
    # / Free tickets and a 0 € open-price workshop: sales without payment.
    en_ligne(
        "billet_offert", 2, PaymentMethod.FREE, 12, 0,
        champs={
            "reservation": reservation_a_l_heure(12, 0),
            "status": LigneArticle.FREERES,
        },
    )
    en_ligne(
        "atelier_libre", 1, PaymentMethod.STRIPE_NOFED, 13, 0,
        champs={"reservation": reservation_a_l_heure(13, 0)},
    )

    # --- En ligne : 8 adhésions à 25 €, une vente chacune / 8 memberships ---
    for numero_de_l_adhesion in range(8):
        minute = numero_de_l_adhesion * 5
        en_ligne(
            "adhesion_annuelle", 1, PaymentMethod.STRIPE_FED, 14, minute,
            champs={"membership": adhesion_a_l_heure(
                "adhesion_annuelle", PaymentMethod.STRIPE_FED, 14, minute,
            )},
        )
    en_ligne(
        "adhesion_libre", 1, PaymentMethod.FREE, 15, 0,
        champs={"membership": adhesion_a_l_heure(
            "adhesion_libre", PaymentMethod.FREE, 15, 0,
        )},
    )

    # --- En ligne : recharges cashless (hors chiffre d'affaires) / Online top-ups ---
    en_ligne(
        "recharge_en_ligne", 1, PaymentMethod.STRIPE_NOFED, 16, 0,
        champs={"asset": catalogue["monnaie_locale"]},
    )
    en_ligne(
        "recharge_federee", 1, PaymentMethod.STRIPE_FED, 16, 30,
        champs={"asset": catalogue["monnaie_federee"]},
    )

    # --- Caisse du Bar et du Cashless / Bar and Cashless registers ---
    produits_de_caisse = ["biere", "coca", "vin_rouge", "chips", "sandwich", "cafe"]
    caisse_complete = catalogue["bar"] is not None
    for cle in produits_de_caisse:
        if catalogue[cle] is None:
            caisse_complete = False
    if not caisse_complete:
        resultat["cas_sautes"].add(
            "Caisse du Bar : point de vente « Bar » ou produits de "
            "create_test_pos_data introuvables."
        )
    vente_des_chips_a_annuler = None
    if caisse_complete:
        bar = catalogue["bar"]

        def au_bar(articles, moyen, h, m, monnaie=None):
            articles_de_la_vente = []
            for cle, quantite, options in articles:
                article = {
                    "produit": catalogue[cle]["produit"],
                    "tarif_vendu": catalogue[cle]["tarif_vendu"],
                    "quantite": quantite,
                }
                article.update(options)
                articles_de_la_vente.append(article)
            vente = _une_vente_reglee(
                articles=articles_de_la_vente, moyen=moyen, origine=SaleOrigin.LABOUTIK,
                heure=heure(h, m), point_de_vente=bar, monnaie_du_reglement=monnaie,
            )
            resultat["nombre_de_ventes"] += 1
            return vente

        au_bar(
            [("biere", 20, {"champs": {"asset": catalogue["monnaie_locale"]}})],
            PaymentMethod.LOCAL_EURO, 19, 0, monnaie=catalogue["monnaie_locale"],
        )
        au_bar([("coca", 10, {})], PaymentMethod.CC, 20, 0)
        au_bar([("vin_rouge", 4, {}), ("chips", 10, {})], PaymentMethod.CASH, 20, 30)
        au_bar(
            [("sandwich", 5, {
                "en_jetons": True,
                "champs": {"asset": catalogue["monnaie_cadeau"]},
            })],
            PaymentMethod.LOCAL_GIFT, 21, 0, monnaie=catalogue["monnaie_cadeau"],
        )
        au_bar([("cafe", 1, {"offert": True})], PaymentMethod.FREE, 22, 0)
        vente_des_chips_a_annuler = au_bar([("chips", 5, {})], PaymentMethod.CASH, 22, 30)

    if catalogue["recharge_caisse"] is None:
        resultat["cas_sautes"].add(
            "Recharge de caisse : produit « Recharge Monnaie locale » (tarif 10 €) "
            "introuvable."
        )
    else:
        point_de_vente_des_recharges = catalogue["cashless"] or catalogue["bar"]
        _une_vente_reglee(
            articles=[{
                "produit": catalogue["recharge_caisse"]["produit"],
                "tarif_vendu": catalogue["recharge_caisse"]["tarif_vendu"],
                "quantite": 3,
                "champs": {"asset": catalogue["monnaie_locale"]},
            }],
            moyen=PaymentMethod.CASH,
            origine=SaleOrigin.LABOUTIK,
            heure=heure(22, 45),
            point_de_vente=point_de_vente_des_recharges,
        )
        resultat["nombre_de_ventes"] += 1

    # --- Les avoirs, après les ventes qu'ils annulent / Credit notes ---
    # Ils sont encaissés « maintenant » par le service : `timezone.now` vaut leur heure.
    # Le billet est remboursé par virement, comme le ferait l'admin (« Remboursé par »,
    # `MOYENS_DU_CHAMP_REMBOURSE_PAR`) : la ligne n'a pas de paiement Stripe relié.
    # / The service settles them "now": `timezone.now` is their time. The ticket is
    # refunded by bank transfer, as the admin would ("Refunded by").
    ligne_d_un_billet_plein = LigneArticle.objects.get(vente=vente_des_billets_pleins)
    with patch("django.utils.timezone.now", return_value=heure(23, 0)):
        ecrire_la_vente_d_avoir_d_une_ligne(
            ligne_d_un_billet_plein,
            Decimal("1"),
            moyen_rembourse=PaymentMethod.TRANSFER,
            origine=SaleOrigin.ADMIN,
        )
    resultat["nombre_de_ventes"] += 1

    if vente_des_chips_a_annuler is not None:
        vente_relue = Vente.objects.get(pk=vente_des_chips_a_annuler.pk)
        with patch("django.utils.timezone.now", return_value=heure(23, 15)):
            ecrire_la_vente_d_avoir_d_une_vente(
                vente_relue,
                moyen_rembourse=PaymentMethod.CASH,
                origine=SaleOrigin.ADMIN,
            )
        resultat["nombre_de_ventes"] += 1


def _ecrire_la_journee_atelier(jour, catalogue, fuseau_du_lieu, resultat):
    """
    La journée atelier d'un jour : billets d'atelier et adhésions saisis à l'admin,
    adhésion SEPA en ligne, échéance d'adhésion mensuelle. 6 ventes, 330 € de CA.
    / The workshop day: admin tickets and memberships, SEPA, monthly installment.
    """
    from BaseBillet.models import PaymentMethod, SaleOrigin

    client = catalogue["client"]
    atelier = catalogue["atelier"]

    def heure(h, m):
        return _a_l_heure(jour, h, m, fuseau_du_lieu)

    def vente(cle, quantite, moyen, origine, h, m, champs):
        _une_vente_reglee(
            articles=[{
                "produit": catalogue[cle]["produit"],
                "tarif_vendu": catalogue[cle]["tarif_vendu"],
                "quantite": quantite,
                "champs": champs,
            }],
            moyen=moyen, origine=origine, heure=heure(h, m), client=client,
        )
        resultat["nombre_de_ventes"] += 1

    def reservation_a_l_heure(h, m):
        with patch("django.utils.timezone.now", return_value=heure(h, m)):
            return _reservation_demo(client, atelier)

    def adhesion_a_l_heure(cle, moyen, h, m):
        with patch("django.utils.timezone.now", return_value=heure(h, m)):
            return _membership_demo(client, catalogue[cle]["tarif"], moyen)

    vente(
        "atelier_normal", 4, PaymentMethod.CC, SaleOrigin.ADMIN, 10, 0,
        {"reservation": reservation_a_l_heure(10, 0)},
    )
    vente(
        "atelier_solidaire", 2, PaymentMethod.CASH, SaleOrigin.ADMIN, 10, 30,
        {"reservation": reservation_a_l_heure(10, 30)},
    )
    vente(
        "adhesion_soutien", 1, PaymentMethod.CHEQUE, SaleOrigin.ADMIN, 11, 0,
        {"membership": adhesion_a_l_heure("adhesion_soutien", PaymentMethod.CHEQUE, 11, 0)},
    )
    vente(
        "adhesion_virement", 1, PaymentMethod.TRANSFER, SaleOrigin.ADMIN, 11, 30,
        {"membership": adhesion_a_l_heure("adhesion_virement", PaymentMethod.TRANSFER, 11, 30)},
    )
    vente(
        "adhesion_sepa", 1, PaymentMethod.STRIPE_SEPA_NOFED, SaleOrigin.LESPASS, 12, 0,
        {"membership": adhesion_a_l_heure(
            "adhesion_sepa", PaymentMethod.STRIPE_SEPA_NOFED, 12, 0,
        )},
    )
    vente(
        "adhesion_mensuelle", 1, PaymentMethod.STRIPE_RECURENT, SaleOrigin.WEBHOOK, 12, 30,
        {"membership": adhesion_a_l_heure(
            "adhesion_mensuelle", PaymentMethod.STRIPE_RECURENT, 12, 30,
        )},
    )


def _mois_de_l_historique(aujourd_hui, nombre_de_mois):
    """
    Les (année, mois) des `nombre_de_mois` mois complets avant le mois en cours, du plus
    ancien au plus récent.
    / The (year, month) of the full months before the current one, oldest first.
    """
    mois_de_l_historique = []
    annee = aujourd_hui.year
    mois = aujourd_hui.month
    for _numero in range(nombre_de_mois):
        mois = mois - 1
        if mois == 0:
            mois = 12
            annee = annee - 1
        mois_de_l_historique.append((annee, mois))
    mois_de_l_historique.reverse()
    return mois_de_l_historique


def le_lieu_a_deja_des_ventes_ou_des_clotures():
    """
    Vrai si le lieu courant a une vente réglée ou une clôture. Des ventes datées du
    passé, encaissées après elles, auraient des numéros plus grands que des ventes plus
    récentes, et n'entreraient dans aucune J (une J commence à la fin de la précédente).
    / True if the current venue has a settled sale or a closure.
    """
    from BaseBillet.models_vente import Vente
    from comptabilite.models import ClotureCaisse

    a_une_vente_reglee = Vente.objects.filter(statut=Vente.Statut.REGLEE).exists()
    a_une_cloture = ClotureCaisse.objects.exists()
    return a_une_vente_reglee or a_une_cloture


def seed_ventes_demo(*, reset=False, nombre_de_mois=NOMBRE_DE_MOIS_DE_VENTES_PAR_DEFAUT):
    """
    L'historique des ventes de démo du lieu courant : `nombre_de_mois` mois complets
    avant le mois en cours, le même programme chaque mois (1 000,00 € de CA).
    Doit être appelé DANS tenant_context(lieu), APRÈS `create_test_pos_data` (caisse
    du Bar, produits, monnaies) ; sans elle, les ventes de caisse sont sautées.
    / The demo sales history of the current venue. Call inside tenant_context, after
    create_test_pos_data.

    RIEN n'est écrit si le lieu a déjà une vente réglée ou une clôture
    (`le_lieu_a_deja_des_ventes_ou_des_clotures`) : relancer ne double rien.
    `reset=True` efface d'abord les ventes et clôtures du lieu
    (`reinitialiser_les_ventes_du_lieu`, passage à blanc puis réel, garde-fou DEBUG +
    TEST).
    / Nothing is written if the venue has sales or closures. reset=True wipes them first.

    :return: dict {"nombre_de_ventes", "nombre_d_articles", "mois_ecrits" (list de
        "AAAA-MM"), "chiffre_d_affaires_attendu_par_mois_en_centimes", "cas_sautes"
        (list), "deja_des_ventes" (bool), "reset_a_blanc", "reset" (dicts ou None)}
    """
    from BaseBillet.models import Configuration, LigneArticle
    from laboutik.plan_comptable import charger_le_plan_comptable_par_defaut

    resultat = {
        "nombre_de_ventes": 0,
        "nombre_d_articles": 0,
        "mois_ecrits": [],
        "chiffre_d_affaires_attendu_par_mois_en_centimes": (
            CHIFFRE_D_AFFAIRES_D_UN_MOIS_EN_CENTIMES
        ),
        "cas_sautes": set(),
        "deja_des_ventes": False,
        "reset_a_blanc": None,
        "reset": None,
    }

    if reset:
        resultat["reset_a_blanc"] = reinitialiser_les_ventes_du_lieu(passage_a_blanc=True)
        resultat["reset"] = reinitialiser_les_ventes_du_lieu(passage_a_blanc=False)

    if le_lieu_a_deja_des_ventes_ou_des_clotures():
        resultat["deja_des_ventes"] = True
        resultat["cas_sautes"] = sorted(resultat["cas_sautes"])
        return resultat

    # Le plan comptable par défaut, complété de ce qui manque (rien n'est écrasé) : la
    # monnaie FED des règlements SF y est reliée au compte du réseau fédéré. Sans elle,
    # l'export des J (FEC, API comptable) est refusé. C'est ce que fait « Plan
    # complet ? » dans l'admin.
    # / The default chart of accounts, completed (nothing overwritten): the FED of the
    # SF payments gets its account. Without it, the J export is refused.
    charger_le_plan_comptable_par_defaut()

    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
    aujourd_hui = timezone.localtime(timezone.now(), fuseau_du_lieu).date()
    mois_a_ecrire = _mois_de_l_historique(aujourd_hui, nombre_de_mois)

    premier_annee, premier_mois = mois_a_ecrire[0]
    dernier_annee, dernier_mois = mois_a_ecrire[-1]
    catalogue = _catalogue_de_la_demo(
        fuseau_du_lieu,
        date(premier_annee, premier_mois, JOUR_DE_LA_SOIREE_CONCERT),
        date(dernier_annee, dernier_mois, JOUR_DE_LA_JOURNEE_ATELIER),
    )

    articles_avant_le_seed = LigneArticle.objects.filter(vente__isnull=False).count()
    for annee, mois in mois_a_ecrire:
        # Un mois par transaction : un échec n'en laisse pas la moitié.
        # / One month per transaction: a failure never leaves half of it.
        with transaction.atomic():
            _ecrire_la_soiree_concert(
                date(annee, mois, JOUR_DE_LA_SOIREE_CONCERT),
                catalogue, fuseau_du_lieu, resultat,
            )
            _ecrire_la_journee_atelier(
                date(annee, mois, JOUR_DE_LA_JOURNEE_ATELIER),
                catalogue, fuseau_du_lieu, resultat,
            )
        resultat["mois_ecrits"].append(f"{annee}-{mois:02d}")

    # Les articles des ventes écrites par ce seed. / The items written by this seed.
    articles_apres_le_seed = LigneArticle.objects.filter(vente__isnull=False).count()
    resultat["nombre_d_articles"] = articles_apres_le_seed - articles_avant_le_seed
    resultat["cas_sautes"] = sorted(resultat["cas_sautes"])
    return resultat


# ============================================================================
# Le reset : toutes les ventes et clôtures du lieu (dev seulement).
# / The reset: every sale and closure of the venue (dev only).
# ============================================================================


def reinitialiser_les_ventes_du_lieu(passage_a_blanc):
    """
    Efface toutes les ventes et clôtures du lieu courant, et les objets de la démo.
    / Deletes every sale and closure of the current venue, and the demo objects.

    LOCALISATION : Administration/management/commands/_demo_data_v2_ventes.py

    GARDE-FOU : refus (RuntimeError, rien n'est touché) si `settings.DEBUG` ou
    `settings.TEST` est faux. Une base de production n'a jamais les deux.
    / Guard: refused unless both DEBUG and TEST are on.

    TOUT OU RIEN, dans une seule transaction. `passage_a_blanc=True` compte tout, puis
    annule tout : rien n'est supprimé. Une relation protégée inattendue lève
    `ProtectedError` : rien n'est supprimé non plus.
    / All or nothing; a dry run counts then rolls everything back.

    CE QUI EST EFFACÉ, dans cet ordre (les clés PROTECT l'imposent) :
    1. les impressions et corrections reliées aux clôtures ou aux articles vendus ;
    2. toutes les clôtures du lieu (une seule chaîne, tous niveaux) ;
    3. tous les règlements, puis les articles des ventes (avoirs d'abord : ils citent
       la ligne qu'ils annulent), puis les ventes (avoirs d'abord : `vente_liee`).
       La chaîne des ventes est celle du lieu ENTIER : en garder une partie ferait des
       trous de numéro ;
    4. les anciennes lignes `[DEMO]` sans vente (seed d'avant le chantier 05) ;
    5. les objets des personnes de démo (`demo-ventes@example.com`,
       `recap-*@example.com`) : adhésions, réservations, réservations de ressources,
       inscriptions bénévoles, pour que la veille et le récap se réécrivent ;
    6. les objets `[DEMO]` : réservations, adhésions, événements, tarifs vendus,
       tarifs, produits.
    Les lignes sans vente qui ne sont pas `[DEMO]` (ex. celles de
    `create_test_pos_data`) ne sont pas touchées.
    / Order forced by PROTECT keys: prints and corrections, closures, payments, items
    (credit notes first), sales (credit notes first), old [DEMO] lines, demo people's
    objects, [DEMO] objects.

    :param passage_a_blanc: True pour compter sans rien supprimer
    :return: dict {nom: nombre supprimé (ou qui le serait)}
    """
    from AuthBillet.models import TibilletUser
    from BaseBillet.models import (
        Event, LigneArticle, Membership, PriceSold, Price, Product, ProductSold,
        Reservation,
    )
    from BaseBillet.models_vente import Reglement, Vente
    from booking.models import Booking, InscriptionBenevole
    from comptabilite.models import ClotureCaisse
    from laboutik.models import CorrectionPaiement, ImpressionLog

    environnement_de_dev = settings.DEBUG and settings.TEST
    if not environnement_de_dev:
        raise RuntimeError(
            f"Reset des ventes refusé : DEBUG={settings.DEBUG}, TEST={settings.TEST}. "
            f"Il faut DEBUG=1 et TEST=1 (jamais en production)."
        )

    nombres = {}
    with transaction.atomic():
        articles_des_ventes = LigneArticle.objects.filter(vente__isnull=False)

        # 1. Impressions et corrections reliées. / Linked prints and corrections.
        impressions = ImpressionLog.objects.filter(cloture__isnull=False) | (
            ImpressionLog.objects.filter(ligne_article__in=articles_des_ventes)
        )
        nombres["impressions"] = impressions.count()
        impressions.delete()
        corrections = CorrectionPaiement.objects.filter(ligne_article__in=articles_des_ventes)
        nombres["corrections"] = corrections.count()
        corrections.delete()

        # 2. Les clôtures. / Closures.
        nombres["clotures"] = ClotureCaisse.objects.count()
        ClotureCaisse.objects.all().delete()

        # 3. Règlements, articles, ventes. / Payments, items, sales.
        nombres["reglements"] = Reglement.objects.count()
        Reglement.objects.all().delete()
        # La garde `pre_delete` de `LigneArticle` (BaseBillet/models.py) refuse
        # d'effacer un article d'une vente réglée : une vente réglée est scellée. Le
        # reset efface la chaîne ENTIÈRE du lieu, en dev seulement (garde-fou plus
        # haut) : les articles sont d'abord détachés de leur vente par un `.update()`,
        # qui ne passe pas par la garde, puis effacés (avoirs d'abord), puis les ventes.
        # / The LigneArticle pre_delete guard refuses to delete a settled sale's item.
        # The reset wipes the WHOLE chain, dev only: items are detached by .update()
        # (no guard), then deleted (credit notes first), then the sales.
        uuids_des_articles_des_ventes = list(articles_des_ventes.values_list("uuid", flat=True))
        nombres["articles_des_ventes"] = len(uuids_des_articles_des_ventes)
        articles_detaches = LigneArticle.objects.filter(uuid__in=uuids_des_articles_des_ventes)
        articles_detaches.update(vente=None)
        articles_detaches.filter(credit_note_for__isnull=False).delete()
        articles_detaches.delete()
        nombres["ventes"] = Vente.objects.count()
        Vente.objects.filter(vente_liee__isnull=False).delete()
        Vente.objects.all().delete()

        # 4. Les anciennes lignes [DEMO] sans vente. / Old [DEMO] lines without a sale.
        anciennes_lignes_de_demo = LigneArticle.objects.filter(
            pricesold__productsold__product__name__startswith=DEMO_PRODUCT_PREFIX,
        )
        nombres["anciennes_lignes_demo"] = anciennes_lignes_de_demo.count()
        anciennes_lignes_de_demo.filter(credit_note_for__isnull=False).delete()
        anciennes_lignes_de_demo.delete()

        # 5. Les objets des personnes de démo. / Demo people's objects.
        personnes_de_demo = TibilletUser.objects.filter(email=EMAIL_DU_CLIENT_DE_DEMO) | (
            TibilletUser.objects.filter(
                email__startswith=PREFIXE_DES_EMAILS_DU_RECAP,
                email__endswith=DOMAINE_DES_EMAILS_DE_DEMO,
            )
        )
        inscriptions = InscriptionBenevole.objects.filter(user__in=personnes_de_demo)
        nombres["inscriptions_benevoles"] = inscriptions.count()
        inscriptions.delete()
        reservations_de_ressources = Booking.objects.filter(user__in=personnes_de_demo)
        nombres["reservations_de_ressources"] = reservations_de_ressources.count()
        reservations_de_ressources.delete()

        # 6. Les objets [DEMO], et ceux des personnes de démo. / [DEMO] objects.
        reservations = Reservation.objects.filter(
            event__name__startswith=DEMO_PRODUCT_PREFIX
        ) | Reservation.objects.filter(user_commande__in=personnes_de_demo)
        nombres["reservations"] = reservations.count()
        reservations.delete()
        adhesions = Membership.objects.filter(
            price__product__name__startswith=DEMO_PRODUCT_PREFIX
        ) | Membership.objects.filter(user__in=personnes_de_demo)
        nombres["adhesions"] = adhesions.count()
        adhesions.delete()
        # Les tarifs vendus avant les événements et les produits qu'ils citent.
        # / Sold prices before the events and products they point to.
        PriceSold.objects.filter(price__product__name__startswith=DEMO_PRODUCT_PREFIX).delete()
        ProductSold.objects.filter(product__name__startswith=DEMO_PRODUCT_PREFIX).delete()
        evenements = Event.objects.filter(name__startswith=DEMO_PRODUCT_PREFIX)
        nombres["evenements"] = evenements.count()
        evenements.delete()
        Price.objects.filter(product__name__startswith=DEMO_PRODUCT_PREFIX).delete()
        produits = Product.objects.filter(name__startswith=DEMO_PRODUCT_PREFIX)
        nombres["produits"] = produits.count()
        produits.delete()

        if passage_a_blanc:
            transaction.set_rollback(True)

    # INDISPENSABLE après un passage à blanc (tests/PIEGES.md 15.1) : l'annulation de la
    # transaction remet aussi le `search_path` de PostgreSQL d'avant (`public`), mais
    # django-tenants croit l'avoir déjà posé (`TENANT_LIMIT_SET_CALLS`). Sans ce
    # rappel, la requête suivante tournerait sur `public` (« relation does not exist »).
    # / REQUIRED after a dry run: the rollback also resets PostgreSQL's search_path,
    # but django-tenants believes it is still set. This call makes it set it again.
    if passage_a_blanc:
        connection.set_tenant(connection.tenant)

    logger.info(f"Reset des ventes du lieu (à blanc : {passage_a_blanc}) : {nombres}")
    return nombres


# ============================================================================
# Les clôtures des périodes finies, jour après jour.
# / The closures of finished periods, one day after another.
# ============================================================================


def seed_clotures_demo(schema_name):
    """
    Les clôtures J, H, M, A des périodes finies du lieu, comme la tâche horaire les
    aurait créées un jour après l'autre (comptabilite/tasks.py).
    / The J, H, M, A closures of the venue's finished periods, as the hourly task
    would have created them, one day after another.

    LOCALISATION : Administration/management/commands/_demo_data_v2_ventes.py

    Doit être appelé HORS de toute transaction : le temps 1 d'une clôture est
    `atomic(durable=True)`, qui lève RuntimeError dans une transaction ouverte. Le
    `tenant_context` est posé ici.
    / Must be called OUTSIDE any transaction (durable atomic). Sets its own tenant_context.

    POUR CHAQUE JOUR, du jour de la première vente réglée à aujourd'hui (seuil passé) :
    1. le filet J du jour (`_creer_la_cloture_journaliere(seuil_du_filet=...)`) : la J
       du service qui finit au seuil (heure de fermeture + 2 h), s'il a des ventes ;
    2. puis les H, M, A qui finissent à minuit ce jour-là
       (`_creer_la_cloture_d_une_periode`) : après le filet du jour où elle finit, une
       période porte les perpétuels de la J de sa dernière soirée.
    PUIS un Z demandé (`_creer_la_cloture_journaliere()`) pour les ventes restées hors
    J (le service d'hier quand le seuil de ce matin n'est pas passé).
    / For each day: the day's net J, then the H, M, A ending that midnight; then a
    requested Z for sales left outside any J.

    La tâche `generer_les_clotures_automatiques_du_lieu` n'est pas appelée : elle ne
    fait qu'une J par passage (une J de 24 mois ici), plafonne les H, M, A à
    `PLAFOND_DES_CLOTURES_CALENDAIRES_PAR_PASSAGE`, et envoie le récap du matin.
    Aucun e-mail n'est demandé ici. Une période déjà clôturée ne l'est jamais deux fois :
    relancer ne crée rien de plus.
    / The hourly task is not called (one J per run, capped H/M/A, morning recap). No
    e-mail. Re-running creates nothing more.

    :param schema_name: le schéma du lieu
    :return: dict {"J": n, "H": n, "M": n, "A": n} des clôtures créées
    """
    from BaseBillet.models import Configuration
    from BaseBillet.models_vente import Vente
    from comptabilite.models import ClotureCaisse
    from comptabilite.tasks import (
        NIVEAUX_CALENDAIRES,
        _bornes_de_la_periode_qui_contient,
        _creer_la_cloture_d_une_periode,
        _creer_la_cloture_journaliere,
        _seuil_du_filet_d_un_jour,
    )
    from Customers.models import Client
    from django_tenants.utils import tenant_context

    clotures_creees = {
        ClotureCaisse.NIVEAU_JOURNALIER: 0,
        ClotureCaisse.NIVEAU_HEBDOMADAIRE: 0,
        ClotureCaisse.NIVEAU_MENSUEL: 0,
        ClotureCaisse.NIVEAU_ANNUEL: 0,
    }

    tenant = Client.objects.get(schema_name=schema_name)
    with tenant_context(tenant):
        configuration = Configuration.get_solo()
        fuseau_du_lieu = configuration.get_tzinfo()
        heure_de_fermeture = configuration.heure_de_fermeture

        premiere_heure_de_vente = Vente.objects.filter(
            statut=Vente.Statut.REGLEE
        ).aggregate(premiere_heure=Min("datetime_encaissement"))["premiere_heure"]
        if premiere_heure_de_vente is None:
            return clotures_creees

        maintenant = timezone.now()
        aujourd_hui = timezone.localtime(maintenant, fuseau_du_lieu).date()
        jour = premiere_heure_de_vente.astimezone(fuseau_du_lieu).date()
        while jour <= aujourd_hui:
            seuil_du_jour = _seuil_du_filet_d_un_jour(jour, fuseau_du_lieu, heure_de_fermeture)
            if seuil_du_jour > maintenant:
                break

            # 1. Le filet J du jour. / 1. The day's net J.
            cloture_j = _creer_la_cloture_journaliere(seuil_du_filet=seuil_du_jour)
            if cloture_j is not None:
                clotures_creees[ClotureCaisse.NIVEAU_JOURNALIER] += 1

            # 2. Les semaines, mois, années qui finissent à minuit ce jour-là.
            # / 2. The weeks, months, years ending at this day's midnight.
            veille = jour - timedelta(days=1)
            for niveau in NIVEAUX_CALENDAIRES:
                debut, fin = _bornes_de_la_periode_qui_contient(niveau, veille, fuseau_du_lieu)
                la_periode_finit_ce_jour_la = fin.date() == jour
                if not la_periode_finit_ce_jour_la:
                    continue
                cloture_de_la_periode = _creer_la_cloture_d_une_periode(niveau, debut, fin)
                if cloture_de_la_periode is not None:
                    clotures_creees[niveau] += 1

            jour = jour + timedelta(days=1)

        # 3. Le Z demandé : les ventes encore hors J. / 3. Requested Z.
        cloture_du_service_en_cours = _creer_la_cloture_journaliere()
        if cloture_du_service_en_cours is not None:
            clotures_creees[ClotureCaisse.NIVEAU_JOURNALIER] += 1

    logger.info(f"[{schema_name}] Clôtures de démo créées : {clotures_creees}")
    return clotures_creees


# ============================================================================
# Ventes d'hier, écrites par le VRAI moteur de vente.
# / Yesterday's sales, written by the REAL sales engine.
# ============================================================================


def les_ventes_d_hier_sont_deja_faites_ou_cloturees(debut_d_hier):
    """
    Vrai si une vente est déjà encaissée depuis hier 0 h (les ventes d'hier sont déjà
    écrites), ou si une J finit après hier 0 h (une vente d'hier, encaissée après elle,
    n'entrerait dans aucune clôture : la J suivante commence à la fin de la
    précédente). L'historique (`seed_ventes_demo`) est plus ancien : il ne bloque rien.
    / True if a sale is settled since yesterday 0 am, or a J ends after it.

    LU PAR : `seed_ventes_de_la_veille_par_le_moteur` (ce module) et
    `seed_activite_de_la_veille_pour_le_recap` (`_demo_data_v2_recap.py`).

    :param debut_d_hier: hier à 0 h, heure du lieu (datetime avec fuseau)
    """
    from BaseBillet.models_vente import Vente
    from comptabilite.models import ClotureCaisse

    une_vente_depuis_hier = Vente.objects.filter(
        statut=Vente.Statut.REGLEE,
        datetime_encaissement__gte=debut_d_hier,
    ).exists()
    une_j_finit_apres_le_debut_d_hier = ClotureCaisse.objects.filter(
        niveau=ClotureCaisse.NIVEAU_JOURNALIER,
        datetime_fin__gt=debut_d_hier,
    ).exists()
    return une_vente_depuis_hier or une_j_finit_apres_le_debut_d_hier


def seed_ventes_de_la_veille_par_le_moteur():
    """
    Quelques ventes d'HIER soir, écrites par le vrai moteur (`services_vente`) : la
    caisse du Bar (espèces, CB), un billet de concert et une adhésion en ligne
    (Stripe). La clôture J qui les reprend est créée ensuite par l'appelant
    (`seed_clotures_demo`, ou `generer_cloture_pour_tenant`).
    / A few sales from YESTERDAY evening, through the real engine. The J closure is
    created afterwards by the caller.

    Doit être appelé DANS tenant_context(lieu), APRÈS `create_test_pos_data` (point de
    vente « Bar », ses produits et leur TVA) et les fixtures du mode complet (concert
    « What the Funk ? », « Adhésion associative Tiers Lustre »), et APRÈS l'historique
    (`seed_ventes_demo`) : ces ventes sont plus récentes, leurs numéros suivent.

    RIEN n'est écrit si une vente est déjà encaissée depuis hier 0 h, ou si une J finit
    après (`les_ventes_d_hier_sont_deja_faites_ou_cloturees`). Relancer la commande sans
    flush ne double donc rien.
    / Nothing is written if a sale is already settled since yesterday, or a J ends after.

    :return: dict {"ecrites": [phrases], "sautees": [phrases]} ; "ecrites" vide si
        rien n'est écrit
    """
    from BaseBillet.models import Configuration, Event, PaymentMethod, Price, Product, SaleOrigin
    from laboutik.models import PointDeVente

    resultat = {"ecrites": [], "sautees": []}

    # Hier, en heure du lieu. / Yesterday, in the venue's time zone.
    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
    hier = timezone.localtime(timezone.now(), fuseau_du_lieu) - timedelta(days=1)
    debut_d_hier = hier.replace(hour=0, minute=0, second=0, microsecond=0)

    if les_ventes_d_hier_sont_deja_faites_ou_cloturees(debut_d_hier):
        resultat["sautees"].append(
            "Ventes d'hier : déjà écrites, ou une clôture J couvre déjà hier : rien "
            "d'ajouté."
        )
        return resultat

    def a_l_heure(heure, minute):
        return hier.replace(hour=heure, minute=minute, second=0, microsecond=0)

    def produit_de_caisse(nom):
        # Le tarif en euros « Tarif <nom> » (la Bière a aussi un tarif en temps).
        # / The euro price (the beer also has a time-currency price).
        produit = Product.objects.filter(name=nom, methode_caisse=Product.VENTE).first()
        tarif = Price.objects.filter(product=produit, name=f"Tarif {nom}").first()
        return produit, _tarif_vendu_par_le_moteur(produit, tarif)

    client = _user_demo()

    with transaction.atomic():
        # --- En ligne : 2 billets du concert (TVA 5,5 %), Stripe ---
        # / Online: 2 concert tickets, Stripe.
        concert = Event.objects.filter(name="What the Funk ? — Spectacle payant").first()
        billet = Product.objects.filter(name="Billet", categorie_article=Product.BILLET).first()
        tarif_du_billet = Price.objects.filter(product=billet, name="Plein tarif").first()
        if concert is None or tarif_du_billet is None:
            resultat["sautees"].append(
                "Billets en ligne : concert « What the Funk ? » introuvable (mode --quick ?)."
            )
        else:
            reservation = _reservation_demo(client, concert)
            _une_vente_reglee(
                articles=[{
                    "produit": billet,
                    "tarif_vendu": _tarif_vendu_par_le_moteur(billet, tarif_du_billet, concert),
                    "quantite": 2,
                    "champs": {"reservation": reservation, "payment_method": PaymentMethod.STRIPE_NOFED},
                }],
                moyen=PaymentMethod.STRIPE_NOFED,
                origine=SaleOrigin.LESPASS,
                heure=a_l_heure(15, 30),
                client=client,
            )
            resultat["ecrites"].append("15:30 en ligne : 2 billets « What the Funk ? », Stripe")

        # --- En ligne : 1 adhésion (sans TVA), Stripe ---
        # / Online: 1 membership, Stripe.
        adhesion = Product.objects.filter(
            name="Adhésion associative Tiers Lustre", categorie_article=Product.ADHESION,
        ).first()
        tarif_de_l_adhesion = Price.objects.filter(product=adhesion, name="Plein tarif").first()
        if tarif_de_l_adhesion is None:
            resultat["sautees"].append(
                "Adhésion en ligne : « Adhésion associative Tiers Lustre » introuvable."
            )
        else:
            membership = _membership_demo(client, tarif_de_l_adhesion, PaymentMethod.STRIPE_NOFED)
            _une_vente_reglee(
                articles=[{
                    "produit": adhesion,
                    "tarif_vendu": _tarif_vendu_par_le_moteur(adhesion, tarif_de_l_adhesion),
                    "quantite": 1,
                    "champs": {"membership": membership, "payment_method": PaymentMethod.STRIPE_NOFED},
                }],
                moyen=PaymentMethod.STRIPE_NOFED,
                origine=SaleOrigin.LESPASS,
                heure=a_l_heure(16, 10),
                client=client,
            )
            resultat["ecrites"].append("16:10 en ligne : 1 adhésion Tiers Lustre, Stripe")

        # --- Caisse du Bar : alcool à 20 %, le reste à 10 % ---
        # / Bar POS: alcohol at 20 %, the rest at 10 %.
        bar = PointDeVente.objects.filter(name="Bar").first()
        if bar is None:
            resultat["sautees"].append("Caisse : point de vente « Bar » introuvable.")
        else:
            biere, biere_vendue = produit_de_caisse("Biere")
            coca, coca_vendu = produit_de_caisse("Coca")
            vin, vin_vendu = produit_de_caisse("Vin rouge")
            chips, chips_vendues = produit_de_caisse("Chips")
            ventes_du_bar = [
                (19, 5, PaymentMethod.CASH, [(biere, biere_vendue, 2), (coca, coca_vendu, 1)],
                 "2 bières + 1 coca, espèces"),
                (20, 30, PaymentMethod.CC, [(vin, vin_vendu, 1), (chips, chips_vendues, 1)],
                 "1 vin rouge + 1 chips, CB"),
                (22, 15, PaymentMethod.CC, [(biere, biere_vendue, 3)],
                 "3 bières, CB"),
            ]
            for heure, minute, moyen, articles, phrase in ventes_du_bar:
                _une_vente_reglee(
                    articles=[
                        {"produit": produit, "tarif_vendu": tarif_vendu, "quantite": quantite}
                        for produit, tarif_vendu, quantite in articles
                    ],
                    moyen=moyen,
                    origine=SaleOrigin.LABOUTIK,
                    heure=a_l_heure(heure, minute),
                    point_de_vente=bar,
                )
                resultat["ecrites"].append(f"{heure:02d}:{minute:02d} caisse Bar : {phrase}")

    return resultat


# ============================================================================
# Cas NON couverts par le seed. A documenter en sortie de commande.
# / Cases NOT covered by the seed. To print at command end.
# ============================================================================
CAS_NON_COUVERTS = [
    "Remboursements Stripe réels (REFUNDED) : ils appellent Stripe ; remplacés par "
    "l'avoir d'un billet, remboursé par virement comme à l'admin",
    "Contributions et remboursements de crowdfunding",
    "Versements bancaires inter-tenants (clearance monnaie locale)",
    "Vidage de carte, correction de moyen de paiement, ventes en points ou en temps",
    "Les 13 lignes de démo de create_test_pos_data restent sans vente",
]


WARNING_FOOTER = """
====================================================================
VENTES DE DÉMO : écrites par le vrai moteur de vente (Vente, Reglement)
====================================================================

Cas NON couverts par le seed :
{cas_non_couverts}

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-07-seed-ventes-reelles.md
====================================================================
"""


def afficher_warning_cas_non_couverts(stdout):
    """
    Imprime le warning sur les cas non couverts.
    / Print the warning about uncovered cases.
    """
    lignes_des_cas = []
    for cas in CAS_NON_COUVERTS:
        lignes_des_cas.append(f"  - {cas}")
    stdout.write(WARNING_FOOTER.format(cas_non_couverts="\n".join(lignes_des_cas)))
