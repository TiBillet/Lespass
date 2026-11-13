"""
Observatoire des instances : le calcul des compteurs de tout le reseau.
/ Instance observatory: computing the counters of the whole network.

LOCALISATION : seo/observatoire.py

QUI L'APPELLE
Seulement la commande `seo/management/commands/refresh_observatoire.py`, lancee
chaque nuit par le beat Celery (`TiBillet/celery.py`, `cron_refresh_observatoire`)
ou a la main par `manage.py`. AUCUNE vue ne l'appelle : un clic ne doit jamais
pouvoir charger le serveur.
/ Only called by the refresh_observatoire command (nightly beat or manage.py).
No view calls it.

CE QUE CA PRODUIT
Un dictionnaire pret pour le JSON : pour chaque lieu, un tableau de valeurs
mensuelles par compteur. Le classement des lieux (actif, festival...) n'est PAS
fait ici : il est fait par la page, dans le navigateur, pour regler les seuils
sans relancer le calcul.
/ A JSON-ready dict: per venue, one monthly array per counter. Classification is
done by the page.

D'OU VIENNENT LES CHIFFRES
- L'argent (CA, recharges) vient des CLOTURES COMPTABLES du lieu
  (`comptabilite.ClotureCaisse`) : ce sont les chiffres des tickets Z. On ne
  recalcule pas le chiffre d'affaires.
  Mois finis : clotures mensuelles (M). Mois sans M (le mois en cours) : somme
  des clotures journalieres (J).
- L'usage vient des tables du lieu, en une requete agregee chacun : evenements,
  billets (gratuits, payants, scannes), adhesions, locations, usagers, points de
  vente. Les billets gratuits ne passent pas tous par une vente : les clotures ne
  les voient pas.
- La caisse cashless : Fedow V2 (schema public) et Fedow legacy (un appel HTTP,
  les ventes NFC et QR code de chaque Place).
- Les comptes admin viennent du schema public.
/ Money comes from the accounting closures (Z figures). Usage comes from the
  venue's tables. Cashless from Fedow V2 and legacy.

- Le bloc « depuis le debut » (presentation) : comptes et recharges V2 sur le
  schema public, recharges et cartes de Fedow legacy (le meme appel HTTP), billets
  et heures de benevolat de chaque lieu.

COUT : 4 requetes sur le schema public et 1 appel a Fedow, puis 12 requetes par
lieu. Aucune ne charge des lignes une par une : ce sont des agregats, ou des cles
extraites en SQL du rapport de chaque cloture.
/ Cost: 4 public queries and 1 Fedow call, then 12 aggregated queries per venue.
"""

import logging
import time
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import requests

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import Event, FederatedPlace, LigneArticle, PaymentMethod, Ticket
from BaseBillet.models_vente import Vente
from booking.models import BesoinBenevole, Booking
from comptabilite.models import ClotureCaisse
from Customers.models import Client
from fedow_connect.models import FedowConfig
from fedow_core.models import Asset, Transaction
from laboutik.models import PointDeVente
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)

# Les compteurs mensuels, dans l'ordre du tableau envoye a la page.
# Cette liste est LE CONTRAT avec seo/static/seo/observatoire.js : elle est
# copiee dans le resultat (cle "cles") et le JS la lit, il ne la redefinit pas.
# / The monthly counters, in the order of the array sent to the page. This list is
#   the contract with the JS: it is copied into the result and read by the JS.
CLES_DES_COMPTEURS = [
    "evenements",
    "billets_gratuits",
    "billets_payants",
    "billets_scannes",
    "adhesions",
    "ca_total",
    "ca_billetterie",
    "ca_adhesions",
    "ca_caisse",
    "recharges_ligne",
    "recharges_place",
    "locations",
    "transactions_cashless",
    "portemonnaies_actifs",
    "usagers",
]

# Les statuts d'une ligne de vente d'adhesion comptee comme une adhesion du mois.
# Une adhesion a 0 EUR ouvre aussi une ligne (statut FREERES). Un avoir ou un
# remboursement n'est pas une adhesion de plus.
# / Sale-line statuses counted as a membership of the month (0 EUR ones included).
STATUTS_DES_LIGNES_D_ADHESION = [
    LigneArticle.PAID,
    LigneArticle.VALID,
    LigneArticle.FREERES,
]

# Les locations comptees : payees ou confirmees. Une demande en attente, refusee ou
# annulee n'est pas un usage.
# / Counted bookings: paid or confirmed. Pending, refused or cancelled ones are not.
STATUTS_DES_LOCATIONS_COMPTEES = [
    Booking.PAID_BY_USER,
    Booking.NO_ADMIN_VALID,
    Booking.ADMIN_VALID,
    Booking.FREERES_USERACTIV,
]

# Les moyens de paiement d'une recharge EN LIGNE : tous les moyens Stripe.
# Une recharge payee par un autre moyen (especes, carte bancaire au TPE...) est
# une recharge SUR PLACE.
# / Online top-up methods: every Stripe method. Any other method is on-site.
MOYENS_DE_RECHARGE_EN_LIGNE = [
    PaymentMethod.STRIPE_NOFED,
    PaymentMethod.STRIPE_SEPA_NOFED,
    PaymentMethod.STRIPE_RECURENT,
]

# Les cles du rapport d'une cloture lues par l'observatoire. Elles sont extraites
# EN SQL (cle JSON par cle JSON) : on ne charge jamais le rapport entier, dont la
# partie « ventes par produit » peut etre longue.
# / The closure report keys read here, extracted in SQL: never the whole report.
CHEMIN_DU_FUSEAU = "rapport_json__en_tete__fuseau_horaire"
CHEMIN_DU_CA_TOTAL = "rapport_json__chiffre_affaires__total_ttc_en_centimes"
CHEMIN_DU_CA_CAISSE = (
    "rapport_json__chiffre_affaires__par_origine__LB__total_ttc_en_centimes"
)
CHEMIN_DES_RECHARGES = (
    "rapport_json__annexe__recharges_et_cartes__recharges_encaissees__par_moyen"
)
CHEMIN_DES_BILLETS = "rapport_json__detail__billets"
CHEMIN_DES_ADHESIONS = "rapport_json__detail__adhesions"
CHEMINS_LUS_DANS_UNE_CLOTURE = [
    "datetime_debut",
    "datetime_fin",
    CHEMIN_DU_FUSEAU,
    CHEMIN_DU_CA_TOTAL,
    CHEMIN_DU_CA_CAISSE,
    CHEMIN_DES_RECHARGES,
    CHEMIN_DES_BILLETS,
    CHEMIN_DES_ADHESIONS,
]


# ---------------------------------------------------------------------------
# La periode / The period
# ---------------------------------------------------------------------------


def liste_des_mois(nombre_de_mois):
    """
    Les N derniers mois au format AAAA-MM, du plus ancien au mois en cours.
    Le mois en cours est lu en heure locale (`timezone.localtime()`).
    / The last N months as YYYY-MM, oldest first, in local time.
    """
    aujourd_hui = timezone.localtime().date()
    annee = aujourd_hui.year
    mois = aujourd_hui.month
    mois_du_plus_recent_au_plus_ancien = []
    for _numero in range(nombre_de_mois):
        mois_du_plus_recent_au_plus_ancien.append(f"{annee}-{mois:02d}")
        if mois > 1:
            mois = mois - 1
        else:
            mois = 12
            annee = annee - 1
    mois_du_plus_recent_au_plus_ancien.reverse()
    return mois_du_plus_recent_au_plus_ancien


def premier_jour_de_la_periode(mois_de_la_periode):
    """
    Le 1er jour du mois le plus ancien, a 00:00 heure locale.
    / The first day of the oldest month, at 00:00 local time.

    :param mois_de_la_periode: la liste rendue par `liste_des_mois`
    """
    mois_le_plus_ancien = mois_de_la_periode[0]
    annee = int(mois_le_plus_ancien[:4])
    mois = int(mois_le_plus_ancien[5:7])
    return timezone.make_aware(datetime(annee, mois, 1))


def mois_d_un_moment(moment, nom_du_fuseau=None):
    """
    Le mois AAAA-MM d'un datetime, lu dans un fuseau donne (sinon le fuseau local).
    / The YYYY-MM month of a datetime, read in a given time zone (else local).
    """
    if moment is None:
        return None
    if nom_du_fuseau:
        moment_dans_le_fuseau = moment.astimezone(ZoneInfo(nom_du_fuseau))
    else:
        moment_dans_le_fuseau = timezone.localtime(moment)
    return moment_dans_le_fuseau.strftime("%Y-%m")


# ---------------------------------------------------------------------------
# Les clotures d'un lieu / A venue's closures
# ---------------------------------------------------------------------------


def _en_nombre(valeur):
    """
    Une valeur lue dans un rapport, en nombre. Une cle absente vaut 0.
    Les quantites sont stockees en texte decimal (« 3.000000 »).
    / A report value as a number. A missing key is 0; quantities are decimal text.
    """
    if valeur is None:
        return 0
    return Decimal(str(valeur))


def ajouter_une_cloture_aux_compteurs(compteurs_du_mois, extrait_de_la_cloture):
    """
    Ajoute les chiffres d'une cloture (M ou J) aux compteurs d'un mois.
    / Adds the figures of one closure (M or J) to a month's counters.

    :param compteurs_du_mois: dict cle du compteur -> valeur, modifie sur place
    :param extrait_de_la_cloture: une ligne de `.values(*CHEMINS_LUS_DANS_UNE_CLOTURE)`
    """
    compteurs_du_mois["ca_total"] += _en_nombre(
        extrait_de_la_cloture[CHEMIN_DU_CA_TOTAL]
    )
    compteurs_du_mois["ca_caisse"] += _en_nombre(
        extrait_de_la_cloture[CHEMIN_DU_CA_CAISSE]
    )

    # Recharges : un total par moyen de paiement. Stripe = en ligne, le reste = sur place.
    # / Top-ups: one total per payment method. Stripe = online, the rest = on site.
    recharges_par_moyen = extrait_de_la_cloture[CHEMIN_DES_RECHARGES] or {}
    for code_du_moyen, somme_du_moyen in recharges_par_moyen.items():
        montant_du_moyen = _en_nombre(somme_du_moyen.get("total_en_centimes"))
        if code_du_moyen in MOYENS_DE_RECHARGE_EN_LIGNE:
            compteurs_du_mois["recharges_ligne"] += montant_du_moyen
        else:
            compteurs_du_mois["recharges_place"] += montant_du_moyen

    # CA des billets : articles du chiffre d'affaires relies a une reservation, par
    # evenement puis par tarif (comptabilite/rapport.py, _detail_des_billets). Le
    # NOMBRE de billets ne se lit pas ici : une reservation gratuite ne passe pas
    # par une vente (activite_du_lieu, requete 4).
    # / Ticket revenue only. The ticket COUNT comes from the Ticket table.
    billets_par_evenement = extrait_de_la_cloture[CHEMIN_DES_BILLETS] or {}
    for evenement in billets_par_evenement.values():
        tarifs_de_l_evenement = evenement.get("par_tarif") or {}
        for tarif in tarifs_de_l_evenement.values():
            compteurs_du_mois["ca_billetterie"] += _en_nombre(
                tarif.get("total_ttc_en_centimes")
            )

    # CA des adhesions : articles du chiffre d'affaires relies a une adhesion, par
    # produit (comptabilite/rapport.py, _detail_des_adhesions). Le NOMBRE
    # d'adhesions ne se lit pas ici (activite_du_lieu, requete 5).
    # / Membership revenue only. The COUNT comes from the sale lines.
    adhesions_par_produit = extrait_de_la_cloture[CHEMIN_DES_ADHESIONS] or {}
    for adhesion in adhesions_par_produit.values():
        compteurs_du_mois["ca_adhesions"] += _en_nombre(
            adhesion.get("total_ttc_en_centimes")
        )


def compteurs_vides():
    """Un mois sans activite : tous les compteurs a 0. / A month with no activity."""
    compteurs = {}
    for cle_du_compteur in CLES_DES_COMPTEURS:
        compteurs[cle_du_compteur] = 0
    return compteurs


def activite_du_lieu(premier_jour):
    """
    Les compteurs mensuels du lieu COURANT. A appeler dans `tenant_context(lieu)`.
    / Monthly counters of the CURRENT venue. Call inside tenant_context.

    FLUX : 10 requetes, toutes en lecture.
    1. Clotures mensuelles (M) de la periode.
    2. Clotures journalieres (J) commencees apres la derniere M lue : elles couvrent
       les mois qui n'ont pas encore leur M (le mois en cours).
    3. Evenements publies par mois.
    4. Billets gratuits, payants et scannes, par mois de l'evenement.
    5. Adhesions par mois (lignes de vente d'adhesion).
    6. Locations par mois.
    7. Usagers distincts (clients des ventes reglees) par mois.
    8. Points de vente visibles.
    9. La Place Fedow legacy du lieu.
    10. Les lieux dont ce lieu affiche l'agenda (FederatedPlace).

    :param premier_jour: datetime avec fuseau, debut de la periode
    :return: dict avec
        compteurs_par_mois (mois AAAA-MM -> compteurs), points_de_vente (nombre),
        place_fedow (uuid hex ou None), lieux_affiches (liste d'uuid de Client)
    """
    compteurs_par_mois = {}

    def compteurs_de(mois):
        if mois not in compteurs_par_mois:
            compteurs_par_mois[mois] = compteurs_vides()
        return compteurs_par_mois[mois]

    # 1. Clotures mensuelles. Le mois se lit dans le fuseau du lieu, comme les
    # bornes de la cloture : une M d'octobre commence le 1er octobre a 00:00 locale.
    # On filtre sur la FIN, pas sur le debut : la M du mois le plus ancien d'un lieu
    # a l'est du serveur (Europe/Paris, serveur en UTC) commence la veille au soir
    # en UTC, avant `premier_jour`. Une M plus ancienne que la periode tombe dans un
    # mois hors de la liste : elle est ignoree a la sortie.
    # / 1. Monthly closures, month read in the venue's time zone. Filtered on the END:
    #      the oldest M of a venue east of the server starts before premier_jour in UTC.
    clotures_mensuelles = (
        ClotureCaisse.objects.filter(
            niveau=ClotureCaisse.NIVEAU_MENSUEL,
            datetime_fin__gt=premier_jour,
        )
        .order_by("datetime_debut")
        .values(*CHEMINS_LUS_DANS_UNE_CLOTURE)
    )
    fin_de_la_derniere_cloture_mensuelle = None
    for cloture_mensuelle in clotures_mensuelles:
        mois_de_la_cloture = mois_d_un_moment(
            cloture_mensuelle["datetime_debut"], cloture_mensuelle[CHEMIN_DU_FUSEAU]
        )
        ajouter_une_cloture_aux_compteurs(
            compteurs_de(mois_de_la_cloture), cloture_mensuelle
        )
        fin_de_la_derniere_cloture_mensuelle = cloture_mensuelle["datetime_fin"]

    # 2. Clotures journalieres qui COMMENCENT apres la fin de la derniere M. Une J
    # est rangee dans le mois de sa fin. Une J finit a l'heure de fermeture + 2 h, pas
    # a minuit : celle qui est a cheval sur la fin de la M (la soiree du 31) est deja
    # comptee dans la M, elle n'est pas reprise. On perd ainsi les ventes du 1er entre
    # minuit et la fermeture, jusqu'a la M suivante, plutot que de compter une soiree
    # deux fois.
    # La J « reprise » est exclue : elle couvre tout l'historique d'avant la bascule
    # (comptabilite/tasks.py, la_j_de_reprise_du_lieu) et ferait un pic faux.
    # / 2. Daily closures after the last M, filed under the month of their end.
    #      The "reprise" J (whole pre-switch history) is excluded.
    if fin_de_la_derniere_cloture_mensuelle is not None:
        debut_des_journalieres = fin_de_la_derniere_cloture_mensuelle
    else:
        debut_des_journalieres = premier_jour
    clotures_journalieres = (
        ClotureCaisse.objects.filter(
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            datetime_debut__gte=debut_des_journalieres,
        )
        # INDISPENSABLE : `contains` sur le rapport entier, et PAS
        # `.exclude(rapport_json__en_tete__reprise=True)`. Une J ordinaire n'a pas
        # de cle « reprise » : la comparaison vaut NULL en SQL, et NOT NULL exclut
        # aussi la J. `@>` sur le rapport (jamais vide) vaut toujours vrai ou faux.
        # / MANDATORY: `contains` on the whole report. A key comparison gives NULL
        #   when the key is missing, and the exclude would drop every ordinary J.
        .exclude(rapport_json__contains={"en_tete": {"reprise": True}})
        .values(*CHEMINS_LUS_DANS_UNE_CLOTURE)
    )
    for cloture_journaliere in clotures_journalieres:
        mois_de_la_cloture = mois_d_un_moment(
            cloture_journaliere["datetime_fin"], cloture_journaliere[CHEMIN_DU_FUSEAU]
        )
        ajouter_une_cloture_aux_compteurs(
            compteurs_de(mois_de_la_cloture), cloture_journaliere
        )

    # 3. Evenements publies dont la date tombe dans le mois. Sans parent : un creneau
    # de benevolat est un sous-evenement, il ne fait pas un evenement de plus.
    # / 3. Published events of the month. No parent: a volunteer slot is a sub-event.
    evenements_par_mois = (
        Event.objects.filter(
            datetime__gte=premier_jour,
            published=True,
            parent__isnull=True,
        )
        .annotate(mois=TruncMonth("datetime"))
        .values("mois")
        .annotate(nombre=Count("pk"))
    )
    for ligne in evenements_par_mois:
        compteurs_de(mois_d_un_moment(ligne["mois"]))["evenements"] = ligne["nombre"]

    # 4. Billets valides (non scannes et scannes), au mois de l'EVENEMENT.
    # INDISPENSABLE : pas le mois de la reservation. `Reservation.created_at` a ete
    # rempli par sa migration (BaseBillet 0235) : tous les anciens billets portent
    # la meme date d'octobre 2026.
    # Un billet est gratuit s'il a ete offert depuis l'admin (il garde alors le tarif
    # payant dans `pricesold`), s'il n'a pas de tarif vendu (creneau benevole), ou si
    # son tarif vendu vaut 0 (tarif gratuit, prix libre a 0, code promo a 100 %).
    # / 4. Valid tickets, by EVENT month (Reservation.created_at was filled by its
    #      migration). Free = offered by an admin, no sold price, or a 0 sold price.
    billet_gratuit = (
        Q(payment_method=PaymentMethod.FREE)
        | Q(pricesold__isnull=True)
        | Q(pricesold__prix=0)
    )
    billets_par_mois = (
        Ticket.objects.filter(
            status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED],
            reservation__event__datetime__gte=premier_jour,
        )
        .annotate(mois=TruncMonth("reservation__event__datetime"))
        .values("mois")
        .annotate(
            nombre_de_billets=Count("pk"),
            nombre_de_billets_gratuits=Count("pk", filter=billet_gratuit),
            nombre_de_billets_scannes=Count("pk", filter=Q(status=Ticket.SCANNED)),
        )
    )
    for ligne in billets_par_mois:
        compteurs_du_mois = compteurs_de(mois_d_un_moment(ligne["mois"]))
        compteurs_du_mois["billets_gratuits"] = ligne["nombre_de_billets_gratuits"]
        compteurs_du_mois["billets_payants"] = (
            ligne["nombre_de_billets"] - ligne["nombre_de_billets_gratuits"]
        )
        compteurs_du_mois["billets_scannes"] = ligne["nombre_de_billets_scannes"]

    # 5. Adhesions : les lignes de vente d'adhesion du mois, gratuites comprises.
    # Pas `Membership.date_added` : la fiche est creee avant le paiement, et un
    # renouvellement (caisse, abonnement Stripe) met a jour la meme fiche.
    # / 5. Memberships: the month's membership sale lines, free ones included.
    adhesions_par_mois = (
        LigneArticle.objects.filter(
            membership__isnull=False,
            status__in=STATUTS_DES_LIGNES_D_ADHESION,
            datetime__gte=premier_jour,
        )
        .annotate(mois=TruncMonth("datetime"))
        .values("mois")
        .annotate(nombre=Count("pk"))
    )
    for ligne in adhesions_par_mois:
        compteurs_de(mois_d_un_moment(ligne["mois"]))["adhesions"] = ligne["nombre"]

    # 6. Locations de salle ou de materiel, payees ou confirmees, au mois du debut.
    # / 6. Paid or confirmed bookings, by start month.
    locations_par_mois = (
        Booking.objects.filter(
            status__in=STATUTS_DES_LOCATIONS_COMPTEES,
            start_datetime__gte=premier_jour,
        )
        .annotate(mois=TruncMonth("start_datetime"))
        .values("mois")
        .annotate(nombre=Count("pk"))
    )
    for ligne in locations_par_mois:
        compteurs_de(mois_d_un_moment(ligne["mois"]))["locations"] = ligne["nombre"]

    # 7. Usagers distincts : les clients des ventes reglees du mois. Un compte
    # TibilletUser est commun a tous les lieux : c'est son activite qui le
    # rattache a un lieu. distinct=True : un client qui achete deux fois ne compte
    # qu'une fois.
    # / 7. Distinct users: clients of the month's settled sales, counted once.
    usagers_par_mois = (
        Vente.objects.filter(
            statut=Vente.Statut.REGLEE,
            datetime_encaissement__gte=premier_jour,
        )
        .annotate(mois=TruncMonth("datetime_encaissement"))
        .values("mois")
        .annotate(nombre=Count("client", distinct=True))
    )
    for ligne in usagers_par_mois:
        compteurs_de(mois_d_un_moment(ligne["mois"]))["usagers"] = ligne["nombre"]

    # 8. Points de vente visibles dans la caisse.
    # / 8. Point of sale visible in the POS.
    nombre_de_points_de_vente = PointDeVente.objects.filter(hidden=False).count()

    # 9. La Place Fedow legacy du lieu, pour retrouver ses ventes dans la reponse de
    # Fedow. INDISPENSABLE : pas `FedowConfig.get_solo()`, qui CREE la ligne quand
    # elle manque. Le calcul ne doit rien ecrire dans les lieux.
    # / 9. The venue's legacy Fedow Place. Never get_solo(): it creates the row.
    uuid_de_la_place = FedowConfig.objects.values_list(
        "fedow_place_uuid", flat=True
    ).first()
    place_fedow = uuid_de_la_place.hex if uuid_de_la_place else None

    # 10. Les lieux dont ce lieu affiche l'agenda. `FederatedPlace` vit chez le lieu
    # qui affiche ; son champ `tenant` designe le lieu affiche.
    # / 10. Venues whose agenda this venue shows (FederatedPlace.tenant).
    lieux_affiches = list(FederatedPlace.objects.values_list("tenant_id", flat=True))

    return {
        "compteurs_par_mois": compteurs_par_mois,
        "points_de_vente": nombre_de_points_de_vente,
        "place_fedow": place_fedow,
        "lieux_affiches": lieux_affiches,
    }


# ---------------------------------------------------------------------------
# Le schema public / The public schema
# ---------------------------------------------------------------------------


def lieux_du_reseau():
    """
    Les lieux a lire, avec leur nombre de comptes admin, en UNE requete.
    On exclut le schema public, le lieu ROOT et les emplacements vides
    WAITING_CONFIG (comme seo/services.py et comptabilite/tasks.py) : lire un
    emplacement pendant que cron_morning le migre provoque un interblocage.
    / Venues to read, with their admin count, in ONE query. Public, ROOT and empty
      WAITING_CONFIG slots are excluded.
    """
    return list(
        Client.objects.exclude(schema_name="public")
        .exclude(categorie__in=[Client.ROOT, Client.WAITING_CONFIG])
        .annotate(nombre_de_comptes_admin=Count("user_admin", distinct=True))
        .order_by("name")
    )


def ventes_cashless_v2_par_lieu_et_par_mois(premier_jour):
    """
    Les ventes cashless du moteur Fedow V2, par lieu et par mois, en UNE requete :
    le nombre de transactions de vente et de porte-monnaie distincts qui ont paye.
    Lu dans fedow_core.Transaction (schema public). Les lieux encore sur Fedow
    legacy y ont peu ou pas de lignes : leurs ventes viennent de l'appel a Fedow.
    / Fedow V2 cashless sales per venue and per month, in ONE query.

    :return: dict uuid du lieu -> dict mois AAAA-MM -> {"transactions", "portemonnaies"}
    """
    ventes_par_lieu = {}
    lignes = (
        Transaction.objects.filter(action=Transaction.SALE, datetime__gte=premier_jour)
        .annotate(mois=TruncMonth("datetime"))
        .values("tenant_id", "mois")
        .annotate(
            transactions=Count("pk"),
            portemonnaies=Count("sender", distinct=True),
        )
    )
    for ligne in lignes:
        mois = mois_d_un_moment(ligne["mois"])
        if ligne["tenant_id"] not in ventes_par_lieu:
            ventes_par_lieu[ligne["tenant_id"]] = {}
        ventes_par_lieu[ligne["tenant_id"]][mois] = {
            "transactions": ligne["transactions"],
            "portemonnaies": ligne["portemonnaies"],
        }
    return ventes_par_lieu


def ajouter_les_ventes_cashless(compteurs_par_mois, ventes_par_mois):
    """
    Ajoute des ventes cashless (V2 ou legacy) aux compteurs mensuels d'un lieu.
    / Adds cashless sales (V2 or legacy) to a venue's monthly counters.

    Les transactions s'additionnent. Les porte-monnaie, non : un meme porte-monnaie
    peut payer en V2 et en legacy dans le meme mois (un panier en assets locaux,
    complete en FED). On garde le plus grand des deux nombres.
    / Transactions add up. Wallets do not (the same wallet may pay in both): max.

    :param compteurs_par_mois: dict mois -> compteurs, modifie sur place
    :param ventes_par_mois: dict mois AAAA-MM -> {"transactions", "portemonnaies"}
    """
    for mois, ventes_du_mois in ventes_par_mois.items():
        if mois not in compteurs_par_mois:
            compteurs_par_mois[mois] = compteurs_vides()
        compteurs_du_mois = compteurs_par_mois[mois]
        compteurs_du_mois["transactions_cashless"] += ventes_du_mois["transactions"]
        compteurs_du_mois["portemonnaies_actifs"] = max(
            compteurs_du_mois["portemonnaies_actifs"], ventes_du_mois["portemonnaies"]
        )


# ---------------------------------------------------------------------------
# Le reseau depuis le debut / The network since the beginning
# ---------------------------------------------------------------------------
#
# Des totaux cumules, pour une presentation : lieux, comptes, recharges, billets,
# cartes, heures de benevolat. « A peu pres » suffit : chaque chiffre dit ce qu'il
# couvre. Les recharges et les cartes viennent surtout de Fedow legacy (le moteur
# de monnaie separe) : la migration vers fedow_core n'est pas finie.
# / Cumulative totals for a presentation. Top-ups and cards mostly come from the
#   legacy Fedow engine: the migration to fedow_core is not finished.

# Les categories d'asset en euros : leurs recharges s'additionnent. Les heures
# (monnaie temps) et les points ne s'additionnent pas a des euros.
# / Euro asset categories: their top-ups add up. Hours and points do not.
CATEGORIES_D_ASSET_EN_EUROS = ["FED", "TLF"]

# Les tokens cadeaux (TNF) de Fedow legacy servaient souvent a remercier les
# benevoles : on les compte en heures de benevolat, a raison de 3 tokens pour 1 h
# (usage courant du reseau). Seulement ceux de Fedow legacy : en V2, les heures
# viennent du planning benevole seul. Fedow stocke tous les montants en centiemes.
# / Legacy gift tokens (TNF) were often used to thank volunteers: 3 tokens = 1 hour.
#   Legacy only; in V2 hours come from the volunteer planning. Amounts are in 1/100.
CATEGORIE_DES_TOKENS_CADEAUX = "TNF"
TOKENS_CADEAUX_PAR_HEURE_DE_BENEVOLAT = 3


def totaux_du_lieu_depuis_le_debut():
    """
    Les totaux cumules du lieu COURANT. A appeler dans `tenant_context(lieu)`.
    / Cumulative totals of the CURRENT venue. Call inside tenant_context.

    2 requetes : les billets (valides, dont scannes), puis les creneaux de
    benevolat qui ont au moins une inscription.
    / 2 queries: tickets, then volunteer slots with at least one sign-up.

    :return: dict billets_valides, billets_scannes, minutes_de_benevolat
    """
    # Un billet vendu est valide, scanne ou non. Les billets crees, inactifs ou
    # annules ne comptent pas.
    # / A sold ticket is valid, scanned or not.
    billets = Ticket.objects.filter(
        status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED]
    ).aggregate(
        valides=Count("pk"),
        scannes=Count("pk", filter=Q(status=Ticket.SCANNED)),
    )

    # Les heures de benevolat : la duree de chaque creneau, fois le nombre de
    # personnes inscrites. Une fin plus tot que le debut veut dire le lendemain
    # (21:00 -> 00:00), comme dans BesoinBenevole.fin(). Un besoin « journee
    # entiere » (sans heure de debut) n'a pas de duree : il n'est pas compte.
    # / Volunteer hours: slot duration times sign-ups. End before start = next day.
    #   Whole-day needs have no duration and are not counted.
    creneaux_avec_inscriptions = (
        BesoinBenevole.objects.filter(heure_debut__isnull=False)
        .annotate(nombre_d_inscriptions=Count("inscriptions"))
        .filter(nombre_d_inscriptions__gt=0)
        .values("heure_debut", "heure_fin", "nombre_d_inscriptions")
    )
    minutes_de_benevolat = 0
    for creneau in creneaux_avec_inscriptions:
        minute_de_debut = (
            creneau["heure_debut"].hour * 60 + creneau["heure_debut"].minute
        )
        minute_de_fin = creneau["heure_fin"].hour * 60 + creneau["heure_fin"].minute
        duree_en_minutes = minute_de_fin - minute_de_debut
        if duree_en_minutes <= 0:
            duree_en_minutes += 24 * 60
        minutes_de_benevolat += duree_en_minutes * creneau["nombre_d_inscriptions"]

    return {
        "billets_valides": billets["valides"],
        "billets_scannes": billets["scannes"],
        "minutes_de_benevolat": minutes_de_benevolat,
    }


def recharges_du_moteur_v2():
    """
    Les recharges du moteur interne (fedow_core), asset par asset, en UNE requete.
    Le FED est exclu : tant que la migration n'est pas finie, on ne compte que le FED
    de Fedow legacy. Aujourd'hui Asset.save() refuse un FED local ; la garde sautera a
    la migration, et ce filtre evitera alors de compter le FED deux fois.
    / Top-ups of the internal engine, per asset, ONE query. FED excluded: only the
      legacy FED counts until the migration is done.
    """
    recharges = []
    lignes = (
        Transaction.objects.filter(action=Transaction.REFILL)
        .exclude(asset__category=Asset.FED)
        .values("asset__uuid", "asset__name", "asset__category", "asset__currency_code")
        .annotate(total=Sum("amount"), nombre=Count("pk"))
        .order_by("asset__name")
    )
    for ligne in lignes:
        recharges.append(
            {
                "uuid": str(ligne["asset__uuid"]),
                "nom": ligne["asset__name"],
                "categorie": ligne["asset__category"],
                "devise": ligne["asset__currency_code"],
                "total": ligne["total"] or 0,
                "nombre": ligne["nombre"],
            }
        )
    return recharges


def statistiques_de_fedow_legacy():
    """
    Les recharges par asset, les cartes et les ventes par lieu, lues dans Fedow legacy.
    Route GET /statistiques_reseau/ de Fedow, avec la cle root de la billetterie.
    Fedow garde la reponse 1 h en cache : cet appel ne charge pas sa base.
    / Top-ups per asset and cards, read from legacy Fedow with the root key.

    Si Fedow ne repond pas, l'erreur est journalisee (Sentry) et on rend None :
    le reste de l'observatoire est quand meme calcule, et la page dit que Fedow
    n'a pas repondu.
    / If Fedow does not answer: logged, None returned, the rest still computed.

    :return: dict recharges_par_asset, cartes, ventes_par_lieu ; ou None
    """
    try:
        configuration_root = RootConfiguration.get_solo()
        # La variable DOIT s'appeler api_key : Sentry recopie les variables locales
        # dans ses evenements, et ne masque que des noms precis (api_key, apikey,
        # secret, token...). Un autre nom enverrait la cle root en clair dans Sentry.
        # / MUST be named api_key: Sentry masks only exact names among local variables.
        api_key = configuration_root.get_fedow_create_place_apikey()
        # Meme appel que fedow_connect/fedow_api.py (_get) : certificat verifie hors
        # DEBUG, timeout obligatoire. Pas de signature : la cle root suffit.
        # / Same call as fedow_connect _get: certificate checked outside DEBUG, timeout.
        reponse = requests.get(
            f"https://{configuration_root.fedow_domain}/statistiques_reseau/",
            headers={"Authorization": f"Api-Key {api_key}"},
            verify=not settings.DEBUG,
            timeout=30,
        )
        reponse.raise_for_status()
        return reponse.json()
    except Exception:
        logger.exception("Observatoire : Fedow legacy n'a pas répondu")
        return None


def reseau_depuis_le_debut(
    nombre_de_lieux, totaux_cumules_des_lieux, statistiques_legacy
):
    """
    Le bloc « Le reseau depuis le debut ». Lu sur le schema public.
    / The "network since the beginning" block. Read on the public schema.

    :param nombre_de_lieux: nombre de lieux du reseau (requete P1)
    :param totaux_cumules_des_lieux: somme des totaux_du_lieu_depuis_le_debut()
    :param statistiques_legacy: la reponse de Fedow legacy, ou None s'il n'a pas repondu
    """
    nombre_de_comptes_humains = TibilletUser.objects.filter(
        espece=TibilletUser.TYPE_HUM
    ).count()

    recharges_v2 = recharges_du_moteur_v2()
    recharges_legacy = []
    cartes_legacy = None
    if statistiques_legacy is not None:
        recharges_legacy = statistiques_legacy.get("recharges_par_asset") or []
        cartes_legacy = statistiques_legacy.get("cartes")

    # Le total des recharges en euros : legacy + V2, assets en euros seulement.
    # / Euro top-up total: legacy + V2, euro assets only.
    total_des_recharges_en_centimes = 0
    for recharge in recharges_legacy + recharges_v2:
        if recharge["categorie"] in CATEGORIES_D_ASSET_EN_EUROS:
            total_des_recharges_en_centimes += recharge["total"]

    # Les heures de benevolat : le planning (tous les lieux), plus les tokens
    # cadeaux distribues dans Fedow legacy (pas ceux du moteur V2).
    # / Volunteer hours: the planning, plus legacy gift tokens (not V2 ones).
    tokens_cadeaux_legacy_en_centiemes = 0
    for recharge in recharges_legacy:
        if recharge["categorie"] == CATEGORIE_DES_TOKENS_CADEAUX:
            tokens_cadeaux_legacy_en_centiemes += recharge["total"]
    heures_du_planning = round(totaux_cumules_des_lieux["minutes_de_benevolat"] / 60)
    heures_des_tokens_cadeaux_legacy = round(
        tokens_cadeaux_legacy_en_centiemes / 100 / TOKENS_CADEAUX_PAR_HEURE_DE_BENEVOLAT
    )

    return {
        "lieux": nombre_de_lieux,
        "comptes": nombre_de_comptes_humains,
        "fedow_legacy_a_repondu": statistiques_legacy is not None,
        "total_des_recharges_en_centimes": total_des_recharges_en_centimes,
        "recharges_legacy": recharges_legacy,
        "recharges_v2": recharges_v2,
        "cartes": cartes_legacy,
        "billets_valides": totaux_cumules_des_lieux["billets_valides"],
        "billets_scannes": totaux_cumules_des_lieux["billets_scannes"],
        "heures_de_benevolat": heures_du_planning + heures_des_tokens_cadeaux_legacy,
        "heures_du_planning": heures_du_planning,
        "heures_des_tokens_cadeaux_legacy": heures_des_tokens_cadeaux_legacy,
    }


# ---------------------------------------------------------------------------
# Le calcul complet / The full computation
# ---------------------------------------------------------------------------


def _valeur_pour_le_json(valeur):
    """
    Un compteur en nombre JSON : entier si possible (les centimes, les quantites
    entieres), sinon flottant arrondi au centieme (une quantite au poids).
    / A counter as a JSON number: int when whole, else a float rounded to 0.01.
    """
    if isinstance(valeur, Decimal):
        if valeur == valeur.to_integral_value():
            return int(valeur)
        return round(float(valeur), 2)
    return valeur


def calculer_observatoire_du_reseau(
    nombre_de_mois=24, calcule_par="manage.py", journal=None
):
    """
    Lit tous les lieux et rend le dictionnaire de l'observatoire.
    / Reads every venue and returns the observatory dict.

    LOCALISATION : seo/observatoire.py

    Un lieu en erreur ne bloque pas les autres : son erreur est notee dans le
    bilan et journalisee, et la boucle continue.
    / A failing venue does not stop the others: logged, noted, loop goes on.

    :param nombre_de_mois: profondeur de l'historique (au moins 13 pour la page)
    :param calcule_par: "cron" ou "manage.py", affiche par la page
    :param journal: fonction appelee avec chaque ligne de suivi (ex. stderr.write)
    :return: dict avec cles, mois, calcule_le, calcule_par, bilan, inst
    """
    if journal is None:
        journal = logger.info

    debut_du_calcul = time.monotonic()
    mois_de_la_periode = liste_des_mois(nombre_de_mois)
    premier_jour = premier_jour_de_la_periode(mois_de_la_periode)

    # Schema public : les lieux et les ventes cashless V2, pour tout le reseau.
    # / Public schema: venues and V2 cashless sales for the whole network.
    tous_les_lieux = lieux_du_reseau()
    ventes_v2_par_lieu = ventes_cashless_v2_par_lieu_et_par_mois(premier_jour)

    # Fedow legacy : UN appel, avant la boucle. Il sert aux ventes de chaque lieu et
    # au bloc « depuis le debut ». S'il ne repond pas, les ventes legacy valent 0 et
    # la page le dit (fedow_legacy_a_repondu).
    # / Legacy Fedow: ONE call, before the loop. If it fails, legacy sales are 0.
    statistiques_legacy = statistiques_de_fedow_legacy()
    ventes_legacy_par_place = {}
    if statistiques_legacy is not None:
        ventes_legacy_par_place = statistiques_legacy.get("ventes_par_lieu") or {}

    erreurs = []
    lignes_des_instances = []
    uuids_des_lieux_federes = set()
    totaux_cumules_des_lieux = {
        "billets_valides": 0,
        "billets_scannes": 0,
        "minutes_de_benevolat": 0,
    }

    for lieu in tous_les_lieux:
        debut_du_lieu = time.monotonic()
        try:
            with tenant_context(lieu):
                activite = activite_du_lieu(premier_jour)
                totaux_du_lieu = totaux_du_lieu_depuis_le_debut()
        except Exception as erreur:
            # Un lieu casse ne doit pas bloquer les autres : on note et on continue.
            # / A broken venue must not block the others: note it and go on.
            logger.exception(f"Observatoire : erreur sur {lieu.schema_name}")
            erreurs.append(f"{lieu.schema_name} : {erreur}")
            journal(f"  {lieu.schema_name} : ERREUR {erreur}")
            continue

        for cle_du_total, valeur_du_lieu in totaux_du_lieu.items():
            totaux_cumules_des_lieux[cle_du_total] += valeur_du_lieu

        # Les ventes cashless : V2 (schema public, par uuid du lieu) et legacy (reponse
        # de Fedow, par uuid de la Place du lieu).
        # / Cashless sales: V2 by venue uuid, legacy by the venue's Place uuid.
        compteurs_par_mois = activite["compteurs_par_mois"]
        ajouter_les_ventes_cashless(
            compteurs_par_mois, ventes_v2_par_lieu.get(lieu.pk, {})
        )
        if activite["place_fedow"] is not None:
            ajouter_les_ventes_cashless(
                compteurs_par_mois,
                ventes_legacy_par_place.get(activite["place_fedow"], {}),
            )

        # Federation : le lieu qui affiche ET les lieux affiches sont « federes ».
        # Un lieu affiche n'a aucune ligne chez lui : on le note depuis l'autre lieu.
        # / Federation: the showing venue AND the shown venues are "federated".
        if activite["lieux_affiches"]:
            uuids_des_lieux_federes.add(lieu.pk)
            for uuid_du_lieu_affiche in activite["lieux_affiches"]:
                uuids_des_lieux_federes.add(uuid_du_lieu_affiche)

        # Un tableau de valeurs mensuelles par compteur, dans l'ordre des cles.
        # / One monthly array per counter, in key order.
        tableaux_des_compteurs = []
        for cle_du_compteur in CLES_DES_COMPTEURS:
            valeurs_du_compteur = []
            for mois in mois_de_la_periode:
                compteurs_du_mois = compteurs_par_mois.get(mois)
                if compteurs_du_mois is None:
                    valeurs_du_compteur.append(0)
                else:
                    valeurs_du_compteur.append(
                        _valeur_pour_le_json(compteurs_du_mois[cle_du_compteur])
                    )
            tableaux_des_compteurs.append(valeurs_du_compteur)

        # L'ordre de ces positions est lu par observatoire.js (charger_les_donnees).
        # La position 5 (« federe ») est remplie apres la boucle : un lieu peut etre
        # affiche par un lieu lu plus tard.
        # / The JS reads these positions. Position 5 ("federated") is set after the loop.
        lignes_des_instances.append(
            [
                lieu.schema_name,
                lieu.name,
                lieu.created_on.isoformat() if lieu.created_on else "",
                activite["points_de_vente"],
                lieu.nombre_de_comptes_admin,
                lieu.pk,
                tableaux_des_compteurs,
            ]
        )
        duree_du_lieu = time.monotonic() - debut_du_lieu
        journal(f"  {lieu.schema_name} : {duree_du_lieu:.2f} s")

    for ligne_du_lieu in lignes_des_instances:
        uuid_du_lieu = ligne_du_lieu[5]
        ligne_du_lieu[5] = uuid_du_lieu in uuids_des_lieux_federes

    duree_totale = round(time.monotonic() - debut_du_calcul, 1)
    bilan = {
        "lieux_lus": len(lignes_des_instances),
        "erreurs": erreurs,
        "duree_s": duree_totale,
    }
    journal(
        f"{bilan['lieux_lus']} lieux lus, {len(erreurs)} en erreur, {duree_totale} s"
    )

    return {
        "cles": CLES_DES_COMPTEURS,
        "mois": mois_de_la_periode,
        "calcule_le": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
        "calcule_par": calcule_par,
        "bilan": bilan,
        "inst": lignes_des_instances,
        "reseau": reseau_depuis_le_debut(
            len(lignes_des_instances), totaux_cumules_des_lieux, statistiques_legacy
        ),
    }
