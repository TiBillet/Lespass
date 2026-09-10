import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.urls import reverse_lazy, reverse, NoReverseMatch
from django.utils.functional import lazy as _lazy


# Portage S6 : certains liens du dashboard/sidebar pointent vers des admins d'apps
# pas encore portees en V1 (booking, controlvanne, cards/QrcodeCashless). On tolere
# les liens absents (-> "#") au lieu de faire planter tout l'admin.
# / Tolerate missing admin reverse links (-> "#") instead of crashing the whole admin.
def _safe_rev_inner(*args, **kwargs):
    try:
        return reverse(*args, **kwargs)
    except NoReverseMatch:
        return "#"
_safe_rev = _lazy(_safe_rev_inner, str)
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from BaseBillet.models import Configuration, Membership

logger = logging.getLogger(__name__)


# Le petit badge route a droite du titre "adhésion"
def adhesion_badge_callback(request):
    # Recherche de la quantité de nouvelles adhésions ces 14 dernièrs jours
    return f"+ {Membership.objects.filter(last_contribution__gte=timezone.localtime() - timedelta(days=7)).count()}"


# Badge "+ N" sur le menu Events si des propositions publiques attendent moderation
# / "+ N" badge on Events menu if public proposals are pending moderation
# Sentinelle pour distinguer « pas encore calcule » de « calcule, et vaut None ».
# / Sentinel: "not computed yet" is not the same as "computed, and it is None".
_PAS_ENCORE_CALCULE = object()


def event_proposals_badge_callback(request):
    """
    Compte des propositions d'event en attente de validation.
    / Count of pending event proposals.

    Affiche un badge "+ N" sur le menu "Events" si des propositions
    publiques attendent moderation (is_proposal=True, published=False).

    POURQUOI CE COMPTAGE EST MEMORISE SUR LA REQUETE.
    _construire_sections_modules() est executee QUATRE fois par page d'admin :
    une fois par get_sidebar_navigation(), DEUX fois par get_tabs() (Unfold lit
    UNFOLD["TABS"] a deux endroits, sites.py:351 et :431) et une fois par le
    templatetag du fil d'Ariane. Sans memorisation, ce COUNT partait donc
    quatre fois pour afficher un seul badge.
    / Built four times per admin page; without memoisation this COUNT ran four
      times to render a single badge.

    On ne memorise QUE ce comptage, pas les sections entieres : un cache sur les
    sections rendrait get_sidebar_navigation() dependante de l'ORDRE des appels
    et casserait les tests qui basculent un module puis reconstruisent le rail.
    C'est l'erreur commise en revision 12, puis corrigee.
    / Only the count is cached, not the sections: caching those would make the
      sidebar depend on call order.

    :param request: objet Request Django
    :return: la chaine du badge, ou None s'il n'y a rien a signaler
    """
    memorise = getattr(request, "_tb_badge_propositions", _PAS_ENCORE_CALCULE)
    if memorise is not _PAS_ENCORE_CALCULE:
        return memorise

    from BaseBillet.models import Event
    count = Event.objects.filter(is_proposal=True, published=False).count()
    badge = f"+ {count}" if count else None

    try:
        request._tb_badge_propositions = badge
    except AttributeError:
        # Objet request exotique qui refuse les attributs : on recalculera.
        # / Exotic request object refusing attributes: recompute next time.
        pass
    return badge


# --------------------------------------------------------------------------- #
# LES CINQ DOMAINES                                                             #
# --------------------------------------------------------------------------- #
# Reprend l'arborescence de la maquette (TEMP-tibillet-admin-main).
# L'ordre de ce dictionnaire est l'ordre d'affichage dans la sidebar.
#
# Un DOMAINE regroupe des MODULES. Un module, c'est une section construite
# dans get_sidebar_navigation : elle porte la cle "_domaine" qui dit a quel
# domaine elle appartient.
#
# Les icones sont des Material Symbols (le jeu embarque par Unfold), choisies
# comme equivalents des icones Tabler de la maquette.
# / The five domains from the mockup. Dict order = sidebar order.
DOMAINES = {
    "lespass": {
        "titre": _("Lespass"),
        "icone": "calendar_month",  # maquette : ti-calendar-star
        "sous_titre": _("La vitrine du lieu et tout ce qui parle à votre public."),
    },
    "laboutik": {
        "titre": _("Laboutik"),
        "icone": "storefront",  # maquette : ti-basket
        "sous_titre": _("Le nerf de la guerre : vendre, encaisser, suivre."),
    },
    "lerezo": {
        "titre": _("Lerézo"),
        "icone": "hub",  # maquette : ti-affiliate
        "sous_titre": _("Vous n'êtes pas seuls : tissez le réseau."),
    },
    "lekontrib": {
        "titre": _("Lékontrib"),
        "icone": "volunteer_activism",  # maquette : ti-heart-handshake
        "sous_titre": _("Faites financer et décider par celles et ceux qui suivent."),
    },
    "lemachines": {
        "titre": _("Lémachines"),
        "icone": "devices",  # maquette : ti-device-desktop
        "sous_titre": _("Le materiel qui fait tourner le lieu."),
    },
}


def _construire_sections_modules(request):
    """
    Construit la liste brute des sections, une par MODULE.
    / Builds the raw list of sections, one per module.

    LOCALISATION : Administration/admin/dashboard.py

    Une section = un module (Agenda, Caisse, Inventaire...) avec toutes ses
    pages. Les modules desactives dans la Configuration du lieu sont absents.

    Chaque section porte trois cles privees, lues plus loin :
      - "_domaine" : cle du domaine, ou None pour une entree autonome
      - "_order"   : rang du module dans son domaine
      - "_icone"   : icone du module dans la sidebar

    Deux fonctions consomment cette liste :
      - get_sidebar_navigation() la replie en groupes-domaines
      - get_tabs() en tire la barre d'onglets de chaque module
    / Consumed by get_sidebar_navigation() and get_tabs().

    :param request: objet Request Django
    :return: liste de sections (dicts), cles privees incluses
    """

    configuration = Configuration.get_solo()

    admin_permission = "ApiBillet.permissions.TenantAdminPermissionWithRequest"
    root_permission = "ApiBillet.permissions.RootPermissionWithRequest"

    # --- Le tableau de bord, seul en tete ---
    # Un groupe SANS titre ne rend que ses liens : c'est ainsi qu'Unfold
    # permet une entree autonome, sans en-tete ni chevron. La maquette met
    # « Tableau de bord » tout en haut du rail, hors de tout groupe.
    # / A group with no title renders only its links: that is how Unfold
    #   allows a standalone entry, as the mockup has it.
    navigation = [
        {
            "_order": -1.0,  # tout en haut / very top
            "_domaine": None,
            "separator": False,
            "collapsible": False,
            "items": [
                {
                    "title": _("Tableau de bord"),
                    "icon": "dashboard",
                    "link": _safe_rev("admin:index"),
                    "permission": admin_permission,
                },
            ],
        },
        {
            "title": _("Configuration générale"),
            "_order": 0.0,  # rang dans le domaine / rank inside domain
            "_domaine": None,  # entree autonome / standalone entry
            "separator": True,
            "collapsible": False,
            "items": [
                {
                    "title": _("Settings"),
                    "icon": "manufacturing",
                    "link": _safe_rev(
                        "staff_admin:BaseBillet_configuration_changelist"
                    ),
                    "permission": admin_permission,
                },
                {
                    "title": _("User accounts"),
                    "icon": "person_add",
                    "link": _safe_rev("staff_admin:AuthBillet_humanuser_changelist"),
                    "permission": admin_permission,
                },
                # This menu option is here only for debug purpose
                # {
                #     "title": _("Produit"),
                #     "icon": "sports_bar",
                #     "link": _safe_rev(
                #         "staff_admin:BaseBillet_product_changelist"
                #     ),
                #     "permission": admin_permission,
                # }
            ],
        },
    ]

    # --- module_pages : section Site web (constructeur de pages) ---
    # --- module_pages: Website section (page builder) ---
    if configuration.module_pages:
        navigation.append(
            {
                "title": _("Site web personnalisé"),
                "_order": 2.0,  # rang dans le domaine / rank inside domain
                "_domaine": "lespass",
                "_icone": "web",
                "_slug": "site-web",  # identifiant de la page de module
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Configuration du site"),
                        "icon": "palette",
                        "link": reverse_lazy(
                            "staff_admin:pages_configurationsite_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        # Les blocs n'ont pas d'entree propre : on les edite
                        # depuis l'onglet « Blocs » de la page qui les porte.
                        # / Blocks get no entry of their own: they are edited
                        # from the "Blocks" tab of the page carrying them.
                        "title": _("Pages"),
                        "icon": "web",
                        "link": reverse_lazy("staff_admin:pages_page_changelist"),
                        "permission": admin_permission,
                    },
                ],
            }
        )

    # --- module_adhesion : section Adhesions ---
    # --- module_adhesion: Memberships section ---
    if configuration.module_adhesion:
        navigation.append(
            {
                "title": _("Adhésion, abonnement et pass"),
                "_order": 2.0,  # rang dans le domaine / rank inside domain
                "_domaine": "lespass",
                "_icone": "card_membership",
                "_slug": "adhesion",  # identifiant de la page de module
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Membership products"),
                        "icon": "loyalty",
                        "link": _safe_rev(
                            "staff_admin:BaseBillet_membershipproduct_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Adhésion / Pass"),
                        "icon": "card_membership",
                        "link": _safe_rev(
                            "staff_admin:BaseBillet_membership_changelist"
                        ),
                        "badge": "Administration.admin.dashboard.adhesion_badge_callback",
                        "permission": admin_permission,
                    },
                ],
            }
        )

    # --- module_billetterie : tout ce qui concerne la billetterie ---
    # --- module_billetterie: everything related to ticketing ---
    if configuration.module_billetterie:
        navigation.append(
            {
                "title": _("Agenda et Billetterie"),
                "_order": 1.0,  # rang dans le domaine / rank inside domain
                "_domaine": "lespass",
                "_icone": "event",
                "_slug": "agenda",  # identifiant de la page de module
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Ticket products"),
                        "icon": "storefront",
                        "link": _safe_rev(
                            "staff_admin:BaseBillet_ticketproduct_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Carousel"),
                        "icon": "photo_library",
                        "link": _safe_rev(
                            "staff_admin:BaseBillet_carrousel_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Promotional codes"),
                        "icon": "local_offer",
                        "link": _safe_rev(
                            "staff_admin:BaseBillet_promotionalcode_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Tags"),
                        "icon": "style",
                        "link": _safe_rev("staff_admin:BaseBillet_tag_changelist"),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Addresses"),
                        "icon": "signpost",
                        "link": _safe_rev(
                            "staff_admin:BaseBillet_postaladdress_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Events"),
                        "icon": "event",
                        "link": _safe_rev("staff_admin:BaseBillet_event_changelist"),
                        # Badge "+ N" uniquement s'il y a des propositions en attente.
                        # On appelle le callback ici et on passe "" quand il n'y a rien.
                        # Le template Unfold teste {% if item.badge %} : une chaine vide
                        # masque completement le badge (sinon il affichait "None").
                        # / "+ N" badge only when proposals are pending. Empty string
                        # hides the badge entirely (Unfold tests {% if item.badge %}).
                        "badge": event_proposals_badge_callback(request) or "",
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Bookings"),
                        "icon": "event_upcoming",
                        "link": _safe_rev(
                            "staff_admin:BaseBillet_reservation_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Tickets"),
                        "icon": "confirmation_number",
                        "link": _safe_rev(
                            "staff_admin:BaseBillet_ticket_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Scan App"),
                        "icon": "qr_code_scanner",
                        "link": _safe_rev(
                            "staff_admin:BaseBillet_scanapp_changelist"
                        ),
                        "permission": admin_permission,
                    },
                ],
            }
        )

    # --- module_federation : tout ce qui est lié a la fédération ---
    # --- module_federation : everything linked to the federation ---
    if configuration.module_federation:
        navigation.append(
            {
                "title": _("Fédération et agenda participatif"),
                "_order": 0.0,  # rang dans le domaine / rank inside domain
                "_domaine": "lerezo",
                "_icone": "hub",
                "_slug": "federation",  # identifiant de la page de module
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Options"),
                        "icon": "tune",
                        "link": _safe_rev(
                            "staff_admin:BaseBillet_federationconfiguration_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Espaces"),
                        "icon": "linked_services",
                        "link": _safe_rev(
                            "staff_admin:BaseBillet_federatedplace_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Assets"),
                        "icon": "currency_exchange",
                        "link": _safe_rev(
                            "staff_admin:fedow_public_assetfedowpublic_changelist"
                        ),
                        "permission": admin_permission,
                    },
                ],
            }
        )


    # --- module_caisse : Caisse LaBoutik ---
    # --- module_caisse: POS LaBoutik ---
    if configuration.module_caisse:
        navigation.append(
            {
                "title": _("Caisse & Restaurant"),
                "_order": 0.0,  # rang dans le domaine / rank inside domain
                "_domaine": "laboutik",
                "_icone": "point_of_sale",
                "_slug": "caisse",  # identifiant de la page de module
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("POS products"),
                        "icon": "point_of_sale",
                        "link": _safe_rev(
                            "staff_admin:BaseBillet_posproduct_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("POS categories"),
                        "icon": "category",
                        "link": _safe_rev(
                            "staff_admin:BaseBillet_categorieproduct_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Points of sale"),
                        "icon": "store",
                        "link": _safe_rev(
                            "staff_admin:laboutik_pointdevente_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Primary cards"),
                        "icon": "badge",
                        "link": _safe_rev(
                            "staff_admin:laboutik_carteprimaire_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    # Les imprimantes ne sont PAS ici : ce sont du materiel, elles vivent
                    # dans « Terminaux materiels » avec les appareils sur lesquels on les
                    # branche. Les codes PIN non plus — ils s'affichent sur leur terminal.
                    # / Printers are NOT here: they are hardware, they live in "Hardware
                    # terminals" alongside the devices they plug into.
                    # {
                    #     "title": _("Orders"),
                    #     "icon": "receipt",
                    #     "link": _safe_rev("staff_admin:laboutik_commandesauvegarde_changelist"),
                    #     "permission": admin_permission,
                    # },
                    {
                        "title": _("Closures"),
                        "icon": "summarize",
                        "link": _safe_rev(
                            "staff_admin:laboutik_cloturecaisse_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Cash float history"),
                        "icon": "account_balance_wallet",
                        "link": _safe_rev(
                            "staff_admin:laboutik_historiquefonddecaisse_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("POS settings"),
                        "icon": "settings",
                        "link": _safe_rev(
                            "staff_admin:laboutik_laboutikconfiguration_changelist"
                        ),
                        "permission": admin_permission,
                    },
                ],
            }
        )

    # --- Section terminaux hardware : visible si caisse, monnaie locale ou tireuse ---
    # --- Terminaux materiels : tout le hardware du lieu, au meme endroit ---
    #
    # 1. « Terminaux » (laboutik.Terminal) — LES APPAREILS. Caisses LaBoutik, bornes
    #    kiosque, Raspberry Pi des tireuses. On les cree ici (ce qui fabrique leur code
    #    PIN), on leur branche une imprimante ou un lecteur de carte, et on les revoque.
    #
    # 2. « Imprimantes » (laboutik.Printer) — le materiel qu'on branche sur un terminal.
    #
    # Le code PIN (discovery.PairingDevice) N'A PAS d'entree : ce n'est pas un objet que
    # l'on manipule, c'est une plomberie. Il s'affiche sur le terminal qu'il appaire.
    #
    # module_kiosk EST dans la condition : sans lui, un lieu qui n'a QUE des bornes
    # n'aurait aucun chemin vers ses propres terminaux.
    # / All the venue's hardware in one place. The PIN has no entry: it is plumbing, shown
    # on the terminal it pairs. module_kiosk belongs in the condition.
    if (
        configuration.module_caisse
        or configuration.module_monnaie_locale
        or configuration.module_tireuse
        or configuration.module_kiosk
    ):
        navigation.append(
            {
                "title": _("Terminaux matériels"),
                "_order": 2.0,  # rang dans le domaine / rank inside domain
                "_domaine": "lemachines",
                "_icone": "tablet",
                "_slug": "terminaux",  # identifiant de la page de module
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Terminaux"),
                        "icon": "tablet",
                        "link": _safe_rev(
                            "staff_admin:laboutik_terminal_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Imprimantes"),
                        "icon": "print",
                        "link": _safe_rev(
                            "staff_admin:laboutik_printer_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("TPE bancaires"),
                        "icon": "contactless",
                        "link": _safe_rev(
                            "staff_admin:laboutik_tpebancaire_changelist"
                        ),
                        "permission": admin_permission,
                    },
                ],
            }
        )

    # --- module_monnaie_locale : Fedow (monnaies, tokens, transactions) ---
    # --- module_monnaie_locale: Fedow (currencies, tokens, transactions) ---
    if configuration.module_monnaie_locale:
        navigation.append(
            {
                "title": _("Monnaies locales, temps et cashless"),
                "_order": 1.0,  # rang dans le domaine / rank inside domain
                "_domaine": "lerezo",
                "_icone": "toll",
                "_slug": "monnaies",  # identifiant de la page de module
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Monnaies et tokens"),
                        "icon": "toll",
                        "link": _safe_rev("staff_admin:fedow_core_asset_changelist"),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Transactions"),
                        "icon": "receipt_long",
                        "link": _safe_rev(
                            "staff_admin:fedow_core_transaction_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Federations"),
                        "icon": "hub",
                        "link": _safe_rev(
                            "staff_admin:fedow_core_federation_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Cartes NFC"),
                        "icon": "credit_card",
                        "link": _safe_rev(
                            "staff_admin:QrcodeCashless_cartecashless_changelist"
                        ),
                        "permission": admin_permission,
                    },
                ],
            }
        )

    # --- Inventaire : Stock et mouvements ---
    # L'inventaire n'est plus un module active a part : il suit la caisse.
    # Des que « Caisse & Restaurant » est active, la section Inventaire apparait.
    # / Inventory is no longer a standalone toggle: it follows the POS module.
    if configuration.module_caisse:
        navigation.append(
            {
                "title": _("Inventaire"),
                "_order": 1.0,  # rang dans le domaine / rank inside domain
                "_domaine": "laboutik",
                "_icone": "inventory_2",
                "_slug": "inventaire",  # identifiant de la page de module
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Stocks"),
                        "icon": "warehouse",
                        "link": _safe_rev("staff_admin:inventaire_stock_changelist"),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Mouvements de stock"),
                        "icon": "inventory_2",
                        "link": _safe_rev(
                            "staff_admin:inventaire_mouvementstock_changelist"
                        ),
                        "permission": admin_permission,
                    },
                ],
            }
        )

    # --- module_tireuse : Tireuses connectees ---
    # / --- module_tireuse: Connected beer taps ---
    if configuration.module_tireuse:
        navigation.append(
            {
                "title": _("Tireuses connectées"),
                "_order": 1.0,  # rang dans le domaine / rank inside domain
                "_domaine": "lemachines",
                "_icone": "sports_bar",
                "_slug": "tireuses",  # identifiant de la page de module
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Kiosk dashboard"),
                        "icon": "monitoring",
                        "link": "/controlvanne/kiosk/",
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Taps"),
                        "icon": "local_bar",
                        "link": _safe_rev(
                            "staff_admin:controlvanne_tireusebec_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Keg products"),
                        "icon": "sports_bar",
                        "link": _safe_rev(
                            "staff_admin:BaseBillet_futproduct_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Flow meters"),
                        "icon": "speed",
                        "link": _safe_rev(
                            "staff_admin:controlvanne_debimetre_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Maintenance cards"),
                        "icon": "build",
                        "link": _safe_rev(
                            "staff_admin:controlvanne_cartemaintenance_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Sessions"),
                        "icon": "history",
                        "link": _safe_rev(
                            "staff_admin:controlvanne_rfidsession_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Tap history"),
                        "icon": "timeline",
                        "link": _safe_rev(
                            "staff_admin:controlvanne_historiquetireuse_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Card history"),
                        "icon": "manage_search",
                        "link": _safe_rev(
                            "staff_admin:controlvanne_historiquecarte_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Maintenance history"),
                        "icon": "plumbing",
                        "link": _safe_rev(
                            "staff_admin:controlvanne_historiquemaintenance_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Calibration"),
                        "icon": "tune",
                        "link": _safe_rev(
                            "staff_admin:controlvanne_sessioncalibration_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Server configuration"),
                        "icon": "settings",
                        "link": _safe_rev(
                            "staff_admin:controlvanne_configurationtireuse_changelist"
                        ),
                        "permission": admin_permission,
                    },
                ],
            }
        )

    # --- module_kiosk : Bornes libre-service ---
    #
    # Le lecteur de carte bancaire n'a PAS d'entree ici : ce n'est pas un objet a part,
    # c'est une capacite d'un terminal appaire (une caisse LaBoutik peut en avoir un).
    # On l'active en editant le terminal, dans « Terminaux materiels ».
    # / The card reader has NO entry here: it is not a separate object, it is a capability
    # of a paired terminal. It is enabled by editing the terminal.
    if configuration.module_kiosk:
        navigation.append(
            {
                "title": _("Kiosk : borne libre-service"),
                "_order": 0.0,  # rang dans le domaine / rank inside domain
                "_domaine": "lemachines",
                "_icone": "smart_display",
                "_slug": "kiosk",  # identifiant de la page de module
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Paiements"),
                        "icon": "payments",
                        "link": _safe_rev(
                            "staff_admin:kiosk_paymentsintent_changelist"
                        ),
                        "permission": admin_permission,
                    },
                ],
            }
        )

    # --- module_booking : Réservation de ressources ---
    # / --- module_booking: Resource booking ---
    if configuration.module_booking:
        navigation.append(
            {
                "title": _("Ressources"),
                "_order": 3.0,  # rang dans le domaine / rank inside domain
                "_domaine": "lespass",
                "_icone": "meeting_room",
                "_slug": "ressources",  # identifiant de la page de module
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Produit ressources"),
                        "icon": "chair",
                        "link": reverse_lazy("staff_admin:BaseBillet_resourceproduct_changelist"),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Ressources"),
                        "icon": "chair",
                        "link": _safe_rev("staff_admin:booking_resource_changelist"),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Groupe de ressources"),
                        "icon": "stacks",
                        "link": _safe_rev("staff_admin:booking_resourcegroup_changelist"),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Calendriers"),
                        "icon": "calendar_month",
                        "link": _safe_rev("staff_admin:booking_calendar_changelist"),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Période d'ouverture"),
                        "icon": "schedule",
                        "link": _safe_rev("staff_admin:booking_weeklyopening_changelist"),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Bookings"),
                        "icon": "event_available",
                        "link": _safe_rev("staff_admin:booking_booking_changelist"),
                        "permission": admin_permission,
                    },
                ],
            }
        )

    # --- Toujours visible : Ventes & comptabilite ---
    # / --- Always visible: Sales & accounting ---
    navigation.append(
        {
            "title": _("Sales & accounting"),
            "_order": 9.0,  # rang dans le domaine / rank inside domain
            "_domaine": None,  # entree autonome / standalone entry
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": _("Rapports"),
                    "icon": "lock",
                    "link": _safe_rev(
                        "staff_admin:comptabilite_cloturecaisse_changelist"
                    ),
                    "permission": admin_permission,
                },
                {
                    "title": _("Entries"),
                    "icon": "receipt_long",
                    "link": _safe_rev(
                        "staff_admin:BaseBillet_lignearticle_changelist"
                    ),
                    "permission": admin_permission,
                },
                # FROM V2 : TO ADD LATER (laboutik viendra plus tard)
                # {
                #     "title": _("Operation logs"),
                #     "icon": "history",
                #     "link": _safe_rev("staff_admin:laboutik_journaloperation_changelist"),
                #     "permission": admin_permission,
                # },
                # {
                #     "title": _("Accounting accounts"),
                #     "icon": "account_balance",
                #     "link": _safe_rev(
                #         "staff_admin:comptabilite_comptecomptable_changelist"
                #     ),
                #     "permission": admin_permission,
                # },
                # {
                #     "title": _("Payment method mapping"),
                #     "icon": "swap_horiz",
                #     "link": _safe_rev(
                #         "staff_admin:comptabilite_mappingmoyendepaiement_changelist"
                #     ),
                #     "permission": admin_permission,
                # },
            ],
        }
    )


    # --- module_crowdfunding : Contributions ---
    if configuration.module_crowdfunding:
        navigation.append(
            {
                "title": _("Financement participatif & budgets contributifs"),
                "_order": 0.0,  # rang dans le domaine / rank inside domain
                "_domaine": "lekontrib",
                "_icone": "volunteer_activism",
                "_slug": "financement",  # identifiant de la page de module
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Configuration"),
                        "icon": "manufacturing",
                        "link": _safe_rev(
                            "staff_admin:crowds_crowdconfig_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Initiative"),
                        "icon": "crowdsource",
                        "link": _safe_rev(
                            "staff_admin:crowds_initiative_changelist"
                        ),
                        "permission": admin_permission,
                    },
                ],
            }
        )

    # --- Newsletter : visible SEULEMENT si le module est actif ---
    #
    # Le module est desactive par defaut. Tant qu'il est inactif, la section n'existe pas
    # dans la sidebar : inutile de montrer une config Ghost a un lieu qui n'a pas de serveur
    # Ghost.
    #
    # La configuration Ghost vit ICI, et nulle part ailleurs : c'est le serveur d'envoi de
    # la newsletter. La ranger dans « Outils externes », a cote de Webhook et Brevo, la
    # rendrait introuvable pour qui cherche a piloter sa newsletter.
    # / Newsletter: shown ONLY when the module is active. The Ghost config belongs HERE — it
    # is the newsletter's sending server, not a generic "external tool".
    if configuration.module_newsletter:
        navigation.append(
            {
                "title": _("Newsletter"),
                "_order": 4.0,  # rang dans le domaine / rank inside domain
                "_domaine": "lespass",
                "_icone": "mail",
                "_slug": "newsletter",  # identifiant de la page de module
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Serveur Ghost"),
                        "icon": "mail",
                        "link": reverse_lazy(
                            "staff_admin:BaseBillet_ghostconfig_changelist"
                        ),
                        "permission": admin_permission,
                    },
                    {
                        # Brevo : outil d'emailing de la newsletter. Il vit ICI,
                        # avec le serveur Ghost, et non plus dans « Outils externes ».
                        # / Brevo: newsletter emailing tool, lives here with Ghost.
                        "title": _("Brevo"),
                        "icon": "alternate_email",
                        "link": _safe_rev(
                            "staff_admin:BaseBillet_brevoconfig_changelist"
                        ),
                        "permission": admin_permission,
                    },
                ],
            }
        )

    # La section « Outils externes » de la sidebar a ete demontee :
    #   - Cle API + Webhook -> onglets de la page « Paramètres » (UNFOLD["TABS"]).
    #   - Formbricks -> retire du menu (le ModelAdmin reste enregistre).
    #   - Brevo -> deplace dans la section « Newsletter » (ci-dessus).
    # / The sidebar "External tools" section was dismantled: API key + webhook moved
    # to the Settings page tabs, Formbricks removed from the menu, Brevo moved to
    # the Newsletter section.

    # --- Root seulement : Root Configuration ---
    navigation.append(
        {
            "title": _("Root Configuration"),
            "_order": 9.1,  # rang dans le domaine / rank inside domain
            "_domaine": None,  # entree autonome / standalone entry
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": _("Waiting Configuration"),
                    "icon": "linked_services",
                    "link": _safe_rev(
                        "staff_admin:MetaBillet_waitingconfiguration_changelist"
                    ),
                    "permission": root_permission,
                },
                {
                    "title": _("Tenants"),
                    "icon": "domain",
                    "link": _safe_rev("staff_admin:Customers_client_changelist"),
                    "permission": root_permission,
                },
                {
                    # Whitelist des domaines d'integration iframe (RootConfiguration).
                    # Visible UNIQUEMENT par le superadmin ROOT. / iframe-embed
                    # domains whitelist — ROOT superadmin only.
                    "title": _("Domaines iframe autorises"),
                    "icon": "shield",
                    "link": _safe_rev(
                        "staff_admin:root_billet_rootconfiguration_changelist"
                    ),
                    "permission": root_permission,
                },
                # {
                #     "title": _("Virements pot central"),
                #     "icon": "account_balance",
                #     "link": _safe_rev("staff_admin:bank_transfers_dashboard"),
                #     "permission": root_permission,
                # },
            ],
        }
    )

    return navigation


def _chemin_correspond(lien, chemin):
    """
    Le chemin courant est-il celui de ce lien, ou une page en dessous ?
    / Is the current path this link, or a page below it?

    LOCALISATION : Administration/admin/dashboard.py

    Meme regle qu'Unfold (_get_is_active, unfold/sites.py) : on compare les
    CHEMINS, sans la query-string, et un lien vaut pour tout ce qui est en
    dessous de lui. C'est ce qui fait que /admin/BaseBillet/event/12/change/
    et /admin/BaseBillet/event/add/ designent bien la meme page d'admin.
    / Same rule as Unfold: compare paths without the query string, a link
      covering everything below it.

    Unfold ecrit « lien in chemin » ; on ecrit « chemin.startswith(lien) »,
    qui est strictement plus sur pour un resultat identique sur toutes nos
    URLs (elles finissent toutes par « / », donc le prefixe ne peut pas
    deborder : /admin/BaseBillet/product/ ne matche PAS productsold).
    / Tightened to a real prefix; same result, no accidental substring match.

    :param lien: l'URL du lien (str, ou proxy paresseux de _safe_rev)
    :param chemin: request.path
    :return: True si le lien designe la page courante
    """
    from urllib.parse import urlparse

    lien = urlparse(str(lien or "")).path
    # « # » est le repli de _safe_rev quand l'admin vise n'existe pas, et un
    # lien vide ne designe rien. Ni l'un ni l'autre ne doit matcher.
    # / "#" is _safe_rev's fallback for a missing admin; never match it.
    if not lien.startswith("/"):
        return False
    return chemin.startswith(lien)


def _module_du_chemin(chemin, sections, inclure_page_du_module=True):
    """
    A quel module appartient la page que l'on regarde ?
    / Which module does the page being viewed belong to?

    LOCALISATION : Administration/admin/dashboard.py

    C'est la brique commune aux deux moities de la revision 11 :
      - le rail s'en sert pour surligner le module courant ;
      - le fil d'Ariane s'en sert pour nommer le bon parent.

    Verifie sur les lieux lespass / festival / meta : AUCUNE page n'appartient
    a deux modules. Si un rangement futur creait l'ambiguite, on retient la
    correspondance la plus LONGUE — le module le plus specifique gagne — pour
    que le resultat reste deterministe plutot que dependant de l'ordre.
    / No page belongs to two modules today; on a tie the longest match wins.

    :param chemin: request.path
    :param sections: sections telles que produites par _construire_sections_modules
    :param inclure_page_du_module: si True, /admin/module/<slug>/ compte comme
        une correspondance. Le rail en a besoin (on EST dans le module) ; le
        fil d'Ariane non (le module serait alors son propre parent).
    :return: la section correspondante, ou None
    """
    if not chemin:
        return None

    meilleure, longueur_max = None, 0
    for section in sections:
        # Seules les sections rangees dans un domaine sont des modules. Les
        # entrees autonomes (Parametres, Ventes & comptabilite, Configuration
        # racine) gardent leurs pages dans le rail : Unfold les surligne deja
        # tout seul, et leur fil d'Ariane n'a pas de module a nommer.
        # / Only domain-bound sections are modules; standalone entries are
        #   already handled by Unfold.
        if not section.get("_domaine"):
            continue

        liens = [str(page.get("link") or "") for page in section.get("items") or []]
        if inclure_page_du_module and section.get("_slug"):
            liens.append(
                str(_safe_rev("staff_admin:page_de_module", args=[section["_slug"]]))
            )

        for lien in liens:
            if _chemin_correspond(lien, chemin) and len(lien) > longueur_max:
                meilleure, longueur_max = section, len(lien)

    return meilleure

def get_sidebar_navigation(request):
    """
    Sidebar dynamique, rangee par domaine.
    / Dynamic sidebar, grouped by domain.

    LOCALISATION : Administration/admin/dashboard.py
    Appelee par Unfold via UNFOLD["SIDEBAR"]["navigation"].

    Chaque section construite par _construire_sections_modules() est un
    MODULE (Agenda, Caisse, Inventaire...). La maquette veut les ranger
    sous 5 DOMAINES.

    La sidebar d'Unfold n'a que DEUX niveaux : un groupe, et ses liens.
    On choisit donc : groupe = DOMAINE, lien = MODULE. Les pages d'un
    module ne sont plus dans la sidebar : elles deviennent les onglets de
    ce module, construits par get_tabs().
    / Unfold's sidebar has only two levels, so: group = domain, link =
      module. A module's pages become its tabs (see get_tabs).

    :param request: objet Request Django
    :return: liste de groupes au format attendu par Unfold
    """
    return _regrouper_sections_par_domaine(
        _construire_sections_modules(request),
        chemin_courant=request.path,
    )


def _regrouper_sections_par_domaine(sections, chemin_courant=""):
    """
    Transforme une liste de sections-modules en groupes-domaines.
    / Turns a list of module sections into domain groups.

    LOCALISATION : Administration/admin/dashboard.py

    Chaque section porte trois cles privees posees plus haut :
      - "_domaine" : la cle du domaine, ou None pour une entree autonome
        (Configuration generale, Ventes & comptabilite, Root Configuration).
      - "_order"   : le rang du module DANS son domaine.
      - "_icone"   : l'icone du module dans la sidebar.

    Les entrees autonomes gardent leur forme actuelle : elles restent des
    groupes depliants avec leurs liens. Leur "_order" les place avant le
    bloc des domaines (moins de 1) ou apres (9 et plus).

    :param sections: liste de sections telles que construites plus haut
    :param chemin_courant: request.path, pour savoir si on est deja sur la
        page d'un domaine — auquel cas son groupe s'affiche deplie
    :return: liste de groupes au format attendu par Unfold
    """
    # On separe les sections qui appartiennent a un domaine des autres.
    # / Split domain-bound sections from standalone ones.
    autonomes = [s for s in sections if not s.get("_domaine")]
    dans_un_domaine = [s for s in sections if s.get("_domaine")]

    # Quel module regarde-t-on ? Calcule UNE fois, pas une fois par module.
    # On compare ensuite par identite (« is ») plutot que par slug : une
    # section rangee dans un domaine mais sans slug reste ainsi gerable.
    # / Which module are we in? Computed once; compared by identity so that a
    #   domain-bound section without a slug still works.
    section_courante = _module_du_chemin(chemin_courant, sections)

    # --- Un groupe par domaine, dans l'ordre de DOMAINES ---
    # / One group per domain, in DOMAINES order.
    groupes_domaines = []
    for cle_domaine, domaine in DOMAINES.items():
        modules_du_domaine = [
            s for s in dans_un_domaine if s["_domaine"] == cle_domaine
        ]
        modules_du_domaine.sort(key=lambda s: s.get("_order", 999))

        liens_des_modules = []
        for section in modules_du_domaine:
            lien = _module_en_lien(section, est_courant=section is section_courante)
            if lien:
                liens_des_modules.append(lien)

        # Un domaine dont aucun module n'est actif n'a rien a montrer.
        # Unfold masque de toute facon les groupes sans liens.
        # / Skip domains with no active module; Unfold hides empty groups.
        if not liens_des_modules:
            continue

        lien_du_domaine = _safe_rev("staff_admin:page_de_domaine", args=[cle_domaine])

        groupes_domaines.append(
            {
                "title": domaine["titre"],
                "separator": True,
                "collapsible": True,
                # « link » n'est PAS une cle d'Unfold : c'est nous qui la
                # lisons, dans notre surcharge de unfold/helpers/app_list.html.
                # Elle rend le titre du domaine cliquable, comme la maquette.
                # / Not an Unfold key: read by our app_list.html override to
                #   make the domain title a link, as in the mockup.
                "link": lien_du_domaine,
                # Quand on est SUR la page d'un domaine, son sous-menu doit
                # deja etre deplie : sinon on arrive sur la page sans voir ou
                # on se trouve dans le rail. Unfold ne deplie un groupe que si
                # l'un de ses liens est actif, et le lien du domaine n'en est
                # pas un — c'est notre surcharge d'app_list.html qui lit cette
                # cle.
                # / Unfold only opens a group when one of its items is active;
                #   the domain link is not one, hence this key.
                "ouvert": bool(chemin_courant) and chemin_courant == str(lien_du_domaine),
                "items": liens_des_modules,
            }
        )

    # --- Assemblage : entrees de tete, domaines, entrees de pied ---
    # / Assembly: head entries, domains, tail entries.
    tete = sorted(
        [s for s in autonomes if s.get("_order", 0) < 1],
        key=lambda s: s.get("_order", 0),
    )
    pied = sorted(
        [s for s in autonomes if s.get("_order", 0) >= 1],
        key=lambda s: s.get("_order", 0),
    )

    navigation = tete + groupes_domaines + pied

    # Un filet separateur au-dessus de chaque groupe, sauf le premier.
    # On retire au passage les cles privees, qu'Unfold ne connait pas.
    # / One separator above each group but the first; drop private keys.
    for rang, groupe in enumerate(navigation):
        groupe["separator"] = rang > 0
        groupe.pop("_order", None)
        groupe.pop("_domaine", None)
        groupe.pop("_icone", None)

    return navigation


# --------------------------------------------------------------------------- #
# LES TROIS CATEGORIES D'ONGLETS                                                #
# --------------------------------------------------------------------------- #
# Reprises de la maquette : chaque module range ses pages en trois familles.
# L'ordre de ce dictionnaire est l'ordre des onglets.
# / The mockup's three tab categories. Dict order = tab order.
CATEGORIES = {
    "gerer": _("Gérer"),          # le quotidien   / day-to-day objects
    "configurer": _("Configurer"),  # les reglages / settings
    "analyser": _("Analyser"),      # les bilans   / reports and history
}

# Rangement de chaque page d'admin dans sa categorie.
#
# La cle est le modele ("BaseBillet.event"), ou l'URL brute pour les pages qui
# ne sont pas des changelists. Une page absente de ce tableau tombe dans
# « Gérer » : c'est le defaut le plus sur, une page oubliee reste visible.
# / Key = model string, or raw URL for non-changelist pages. Unlisted pages
#   fall back to "gerer" so a forgotten page stays visible.
# Une phrase sous le nom de chaque page, dans la liste d'un module.
#
# Reprises de la maquette (TEMP-tibillet-admin-main/data.js) la ou elle en
# proposait, redigees pour les autres. Meme cle que CATEGORIE_DES_PAGES :
# le modele, ou l'URL brute pour les pages qui n'en sont pas.
#
# Une page absente de ce tableau s'affiche SANS description. On n'invente
# pas de texte pour combler un trou : mieux vaut une ligne sobre qu'une
# phrase approximative.
# / One sentence under each page name. A page missing from this table simply
#   shows no description: we never invent filler text.
DESCRIPTION_DES_PAGES = {
    # --- Site web personnalise ---
    "pages.page": _("Composez votre site, bloc par bloc."),
    "pages.configurationsite": _("Domaine, apparence, page d'accueil."),
    # --- Adhesion, abonnement et pass ---
    "BaseBillet.membership": _("Celles et ceux qui vous suivent."),
    "BaseBillet.membershipproduct": _("Les formules d'adhésion proposées."),
    # --- Agenda et Billetterie ---
    "BaseBillet.event": _("Ce que le lieu programme."),
    "BaseBillet.reservation": _("Les demandes entrantes."),
    "BaseBillet.ticket": _("Les billets émis."),
    "BaseBillet.ticketproduct": _("Les types de billets proposés."),
    "BaseBillet.promotionalcode": _("Les réductions ponctuelles."),
    "BaseBillet.carrousel": _("Les visuels mis en avant sur l'agenda."),
    "BaseBillet.tag": _("Les étiquettes de classement."),
    "BaseBillet.postaladdress": _("Les lieux où se passent vos évènements."),
    "BaseBillet.scanapp": _("Le contrôle des billets à l'entrée."),
    # --- Federation et agenda participatif ---
    "BaseBillet.federatedplace": _("Les lieux avec qui vous faites réseau."),
    "fedow_public.assetfedowpublic": _("Les monnaies qui circulent dans le réseau."),
    "BaseBillet.federationconfiguration": _("Ce que vous partagez, et avec qui."),
    # --- Caisse & Restaurant ---
    "laboutik.pointdevente": _("Vos comptoirs et leurs écrans."),
    "laboutik.carteprimaire": _("Les cartes du personnel."),
    "BaseBillet.posproduct": _("Ce que vous vendez au comptoir."),
    "BaseBillet.categorieproduct": _("Le rangement des produits à l'écran."),
    "laboutik.laboutikconfiguration": _("Les réglages du point de vente."),
    "laboutik.cloturecaisse": _("Le bilan de chaque journée."),
    "laboutik.historiquefonddecaisse": _("Les mouvements du fond de caisse."),
    # --- Terminaux materiels ---
    "laboutik.terminal": _("Les appareils appairés au lieu."),
    "laboutik.printer": _("Les imprimantes à tickets."),
    "laboutik.tpebancaire": _("Les terminaux de paiement bancaire."),
    # --- Monnaies locales, temps et cashless ---
    "fedow_core.asset": _("Vos monnaies et vos jetons."),
    "QrcodeCashless.cartecashless": _("Les cartes remises au public."),
    "fedow_core.federation": _("Les réseaux de monnaie auxquels vous participez."),
    "fedow_core.transaction": _("Tout ce qui a circulé."),
    # --- Inventaire ---
    "inventaire.stock": _("Ce qu'il vous reste."),
    "inventaire.mouvementstock": _("Ce qui est entré et sorti."),
    # --- Tireuses connectees ---
    "controlvanne.tireusebec": _("Vos becs et ce qu'ils servent."),
    "controlvanne.cartemaintenance": _("Les cartes qui ouvrent les vannes."),
    "BaseBillet.futproduct": _("Ce qui est en fût."),
    "controlvanne.debimetre": _("Les compteurs de volume."),
    "controlvanne.configurationtireuse": _("Les réglages du serveur de tirage."),
    "controlvanne.sessioncalibration": _("L'étalonnage des débitmètres."),
    "controlvanne.rfidsession": _("Les sessions de tirage."),
    "controlvanne.historiquetireuse": _("Ce qui a coulé, bec par bec."),
    "controlvanne.historiquecarte": _("Ce que chaque carte a consommé."),
    "controlvanne.historiquemaintenance": _("Les interventions sur le matériel."),
    "/controlvanne/kiosk/": _("L'écran public des tireuses."),
    # --- Kiosk : borne libre-service ---
    "kiosk.paymentsintent": _("Les paiements passés en autonomie."),
    # --- Ressources ---
    "booking.booking": _("Les réservations de salles et de matériel."),
    "BaseBillet.resourceproduct": _("Les ressources mises à la réservation."),
    "booking.resource": _("Ce qui peut être réservé."),
    "booking.resourcegroup": _("Le rangement des ressources."),
    "booking.calendar": _("Les calendriers de disponibilité."),
    "booking.weeklyopening": _("Les horaires d'ouverture habituels."),
    # --- Financement participatif ---
    "crowds.initiative": _("Les projets soumis au financement."),
    "crowds.crowdconfig": _("Les mots et les règles de vos campagnes."),
    # --- Newsletter ---
    "BaseBillet.ghostconfig": _("Votre serveur Ghost."),
    "BaseBillet.brevoconfig": _("Votre compte Brevo."),
}


CATEGORIE_DES_PAGES = {
    # --- Site web personnalise ---
    "pages.page": "gerer",
    "pages.configurationsite": "configurer",
    # --- Adhesion, abonnement et pass ---
    "BaseBillet.membership": "gerer",
    "BaseBillet.membershipproduct": "configurer",
    # --- Agenda et Billetterie ---
    "BaseBillet.event": "gerer",
    "BaseBillet.reservation": "gerer",
    "BaseBillet.ticket": "gerer",
    "BaseBillet.ticketproduct": "configurer",
    "BaseBillet.promotionalcode": "configurer",
    "BaseBillet.carrousel": "configurer",
    "BaseBillet.tag": "configurer",
    "BaseBillet.postaladdress": "configurer",
    "BaseBillet.scanapp": "configurer",
    # --- Federation et agenda participatif ---
    "BaseBillet.federatedplace": "gerer",
    "fedow_public.assetfedowpublic": "gerer",
    "BaseBillet.federationconfiguration": "configurer",
    # --- Caisse & Restaurant ---
    "laboutik.pointdevente": "gerer",
    "laboutik.carteprimaire": "gerer",
    "BaseBillet.posproduct": "configurer",
    "BaseBillet.categorieproduct": "configurer",
    "laboutik.laboutikconfiguration": "configurer",
    "laboutik.cloturecaisse": "analyser",
    "laboutik.historiquefonddecaisse": "analyser",
    # --- Terminaux materiels ---
    "laboutik.terminal": "gerer",
    "laboutik.printer": "gerer",
    "laboutik.tpebancaire": "gerer",
    # --- Monnaies locales, temps et cashless ---
    "fedow_core.asset": "gerer",
    "QrcodeCashless.cartecashless": "gerer",
    "fedow_core.federation": "configurer",
    "fedow_core.transaction": "analyser",
    # --- Inventaire ---
    "inventaire.stock": "gerer",
    "inventaire.mouvementstock": "analyser",
    # --- Tireuses connectees ---
    "controlvanne.tireusebec": "gerer",
    "controlvanne.cartemaintenance": "gerer",
    "BaseBillet.futproduct": "configurer",
    "controlvanne.debimetre": "configurer",
    "controlvanne.configurationtireuse": "configurer",
    "controlvanne.sessioncalibration": "configurer",
    "controlvanne.rfidsession": "analyser",
    "controlvanne.historiquetireuse": "analyser",
    "controlvanne.historiquecarte": "analyser",
    "controlvanne.historiquemaintenance": "analyser",
    "/controlvanne/kiosk/": "analyser",
    # --- Kiosk : borne libre-service ---
    "kiosk.paymentsintent": "gerer",
    # --- Ressources ---
    "booking.booking": "gerer",
    "BaseBillet.resourceproduct": "configurer",
    "booking.resource": "configurer",
    "booking.resourcegroup": "configurer",
    "booking.calendar": "configurer",
    "booking.weeklyopening": "configurer",
    # --- Financement participatif ---
    "crowds.initiative": "gerer",
    "crowds.crowdconfig": "configurer",
    # --- Newsletter ---
    "BaseBillet.ghostconfig": "configurer",
    "BaseBillet.brevoconfig": "configurer",
}


def _sections_par_slug(request):
    """
    Range les modules par identifiant, pour les retrouver depuis une URL.
    / Indexes modules by slug so a URL can find them.

    :param request: objet Request Django
    :return: dict {slug: section}
    """
    return {
        section["_slug"]: section
        for section in _construire_sections_modules(request)
        if section.get("_slug")
    }


def page_de_module(request, slug):
    """
    Page d'accueil d'un module : ses onglets et la liste de ses pages d'admin.
    / A module's landing page: its category tabs and the list of its admin pages.

    LOCALISATION : Administration/admin/dashboard.py
    Routee par StaffAdminSite.get_urls() sur /admin/module/<slug>/.

    C'est la page decrite par la maquette : on choisit un module dans la
    sidebar, on arrive ici, et on voit ses pages rangees sous les onglets
    Gerer / Configurer / Analyser. Chaque ligne mene a l'admin correspondante.
    / The mockup's module page: pick a module in the sidebar, land here, see
      its pages grouped under the three tabs.

    FLUX :
    1. La sidebar pointe vers cette vue (voir _module_en_lien).
    2. On reconstruit les sections pour retrouver le module par son slug.
    3. On range ses pages en categories (_categoriser_les_pages).
    4. L'onglet ouvert vient de ?onglet=..., sinon c'est le premier.

    :param request: objet Request Django
    :param slug: identifiant du module (ex. « agenda »)
    :return: HttpResponse
    """
    from django.http import Http404
    from django.shortcuts import render

    from Administration.admin.site import staff_admin_site

    section = _sections_par_slug(request).get(slug)
    if section is None:
        # Module inconnu, ou desactive dans la Configuration du lieu.
        # / Unknown module, or disabled in the venue's Configuration.
        raise Http404(f"Module inconnu : {slug}")

    pages = section.get("items") or []
    par_categorie = _categoriser_les_pages(pages, _carte_des_liens_vers_modeles())

    # L'onglet demande, s'il existe et s'il contient quelque chose.
    # / The requested tab, if it exists and holds anything.
    onglet_demande = request.GET.get("onglet")
    if onglet_demande not in par_categorie:
        onglet_demande = next(iter(par_categorie), None)

    onglets = [
        {
            "cle": cle,
            "titre": CATEGORIES[cle],
            "lien": f"{request.path}?onglet={cle}",
            "actif": cle == onglet_demande,
            "nombre": len(pages_de_la_categorie),
        }
        for cle, pages_de_la_categorie in par_categorie.items()
    ]

    domaine = DOMAINES.get(section.get("_domaine")) or {}

    # La barre haute d'Unfold et le contenu ne doivent PAS dire la meme chose.
    # `title` alimente {% header_title %}, qui est en realite un fil d'Ariane :
    # on lui donne donc le PARENT (le domaine), et le contenu porte le titre
    # de la page. Sans cela, « Agenda » s'affichait deux fois, et la page avait
    # deux <h1>.
    # / Unfold's header is a breadcrumb: give it the parent, keep the page
    #   title in the content. Otherwise the name shows twice, in two <h1>.
    contexte = {
        **staff_admin_site.each_context(request),
        "title": domaine.get("titre") or section["title"],
        "titre_du_module": section["title"],
        "icone_du_module": section.get("_icone"),
        "titre_du_domaine": domaine.get("titre"),
        "sous_titre_du_domaine": domaine.get("sous_titre"),
        # Le chemin de retour vers le domaine. La maquette a un « ← Lespass »
        # en haut de la page ; sans lui, le seul retour est la sidebar.
        # / The way back to the domain; without it the sidebar is the only way.
        "lien_du_domaine": (
            _safe_rev("staff_admin:page_de_domaine", args=[section["_domaine"]])
            if section.get("_domaine")
            else None
        ),
        "onglets": onglets,
        # La categorie ouverte : le gabarit la pose sur la liste pour colorer
        # les pastilles, comme la maquette (vert / orange / bleu).
        # / The open category, used to colour the list's icon tiles.
        "categorie_ouverte": onglet_demande,
        "pages_de_l_onglet": par_categorie.get(onglet_demande, []),
    }
    return render(request, "admin/module_page.html", contexte)


def page_de_domaine(request, cle):
    """
    Page d'accueil d'un domaine : la liste de ses modules.
    / A domain's landing page: the list of its modules.

    LOCALISATION : Administration/admin/dashboard.py
    Routee par StaffAdminSite.get_urls() sur /admin/domaine/<cle>/.

    C'est l'ecran de la maquette : on clique « Lespass » dans le rail, on
    arrive ici, et on voit ses modules avec leur interrupteur. Cliquer un
    module allume ouvre sa page ; cliquer un module eteint ne fait rien.
    / The mockup's domain screen: click a domain in the rail, land here.

    L'interrupteur est exactement celui du tableau de bord : meme modale,
    meme POST. Ce POST repond « HX-Refresh », donc il recharge la page ou
    qu'on soit — il n'y a rien a adapter pour cet ecran.
    / The toggle is the dashboard's, unchanged: its POST answers HX-Refresh,
      so it reloads whatever page you are on.

    :param request: objet Request Django
    :param cle: identifiant du domaine (ex. « lespass »)
    :return: HttpResponse
    """
    from django.http import Http404
    from django.shortcuts import render

    from Administration.admin.site import staff_admin_site

    domaine = DOMAINES.get(cle)
    if domaine is None:
        raise Http404(f"Domaine inconnu : {cle}")

    configuration = Configuration.get_solo()
    groupes = _grouper_les_cartes_par_domaine(_build_modules_context(configuration))

    groupe = next((g for g in groupes if g["cle"] == cle), None)
    if groupe is None:
        # Domaine connu mais sans aucune carte : on affiche la page vide
        # plutot qu'une 404, l'utilisateur a bien clique sur quelque chose.
        # / Known domain with no card: show an empty page, not a 404.
        groupe = {
            "cartes": [],
            "total": 0,
            "actifs": 0,
        }

    # Meme regle que sur le tableau de bord : un lien seulement si le module
    # a vraiment une page.
    # / Same rule as the dashboard: link only when the module has a page.
    _poser_les_liens_des_modules(request, [groupe])

    # Meme regle que sur la page de module : la barre haute porte le parent.
    # / Same rule as the module page: the header carries the parent.
    contexte = {
        **staff_admin_site.each_context(request),
        "title": _("Tableau de bord"),
        "cle_du_domaine": cle,
        "titre_du_domaine": domaine["titre"],
        "icone_du_domaine": domaine["icone"],
        "sous_titre_du_domaine": domaine["sous_titre"],
        "cartes": groupe["cartes"],
        "total": groupe["total"],
        "actifs": groupe["actifs"],
    }
    return render(request, "admin/domaine_page.html", contexte)


def _poser_les_liens_des_modules(request, groupes):
    """
    Donne a chaque carte allumee l'adresse de la page de son module.
    / Gives each lit card the URL of its module page.

    LOCALISATION : Administration/admin/dashboard.py

    On ne pose un lien que si le module a VRAIMENT une entree dans la
    sidebar. Un module eteint n'en a pas, et la caisse en V1 non plus : sa
    carte affiche « V1 active » mais aucune page d'admin V2 n'existe. Poser
    un lien mort ferait une carte cliquable qui tombe sur une 404.
    / Only link when the module really has a sidebar section: a switched-off
      module has none, and neither does a V1 POS.

    :param request: objet Request Django
    :param groupes: liste de groupes de domaine, modifiee sur place
    :return: None
    """
    slugs_existants = set(_sections_par_slug(request))

    for groupe in groupes:
        for carte in groupe["cartes"]:
            slug = carte.get("slug")
            carte["lien_du_module"] = (
                _safe_rev("staff_admin:page_de_module", args=[slug])
                if slug in slugs_existants
                else None
            )


def _carte_des_liens_vers_modeles():
    """
    Associe l'URL d'une changelist au modele qu'elle affiche.
    / Maps a changelist URL to the model it lists.

    LOCALISATION : Administration/admin/dashboard.py

    POURQUOI : les sections de la sidebar stockent une URL deja calculee
    (« /admin/BaseBillet/event/ »), alors que les onglets d'Unfold attendent
    un nom de modele (« BaseBillet.event »). On reconstruit donc la
    correspondance a partir des modeles reellement enregistres dans l'admin.

    Une page qui n'est pas une changelist (un tableau de bord maison, un
    rapport) n'apparait pas dans cette carte : c'est voulu, elle ne
    declenchera simplement pas de barre d'onglets.
    / Pages that are not changelists are absent on purpose.

    :return: dict {url: "app_label.modelname"}
    """
    from django.urls import NoReverseMatch, reverse

    from Administration.admin.site import staff_admin_site

    carte = {}
    for modele in staff_admin_site._registry:
        options = modele._meta
        nom_url = (
            f"staff_admin:{options.app_label}_{options.model_name}_changelist"
        )
        try:
            carte[reverse(nom_url)] = f"{options.app_label}.{options.model_name}"
        except NoReverseMatch:
            # Modele enregistre mais sans changelist accessible : on l'ignore.
            # / Registered model with no reachable changelist: skip it.
            continue
    return carte


# Onglets qui ne decoulent pas d'un module. Ils existaient avant le passage
# aux domaines et sont conserves tels quels.
# / Tabs that do not come from a module; kept as they were.
def _onglets_hors_modules():
    """
    Les deux barres d'onglets historiques du projet.
    / The project's two pre-existing tab bars.

    LOCALISATION : Administration/admin/dashboard.py

    - Formbricks : formulaires et reglages.
    - Parametres : la Configuration du lieu, les cles API et les webhooks.
      Ces trois modeles n'ont aucun lien de base de donnees entre eux : ce ne
      sont donc PAS des inlines, mais bien des onglets de navigation.
    / No DB relation between these models: they are navigation tabs.

    POURQUOI CERTAINS MODELES SONT CITES DEUX FOIS (chaine + dict).
    Unfold (_get_tabs_list, unfold/templatetags/unfold.py) ne fait
    correspondre une entree ECRITE EN CHAINE que si la page est une
    changelist :

        if isinstance(tab_model, str):
            if str(opts) == tab_model and page == "changelist":

    Pour qu'une barre s'affiche sur un FORMULAIRE, il faut une entree dict
    portant « detail »: True.

    Or Configuration et FormbricksConfig sont des singletons django-solo :
    ils rendent un formulaire A L'URL DE LISTE. Avec la seule chaine, leur
    barre ne s'affichait donc JAMAIS — et comme « Parametres » est la seule
    page du groupe presente dans le rail, « Cles API » et « Webhooks »
    n'etaient atteignables que par la recherche. Un cul-de-sac.
    / Unfold matches a string entry only on changelists; a form needs a dict
      with "detail": True. Both singletons render a form at their list URL,
      so their tab bar never appeared and the sibling pages were unreachable.

    On cite donc ces deux modeles DEUX fois : la chaine (inoffensive) et le
    dict qui fait le travail.

    :return: liste de groupes d'onglets au format Unfold
    """
    return [
        {
            "models": [
                # FormbricksConfig est un singleton : voir le commentaire
                # ci-dessus. / Singleton, see the docstring above.
                {"name": "BaseBillet.formbricksconfig", "detail": True},
                "BaseBillet.formbricksconfig",
                "BaseBillet.formbricksforms",
            ],
            "items": [
                {
                    "title": _("Formulaires"),
                    "link": _safe_rev("staff_admin:BaseBillet_formbricksforms_changelist"),
                },
                {
                    "title": _("Réglages"),
                    "link": _safe_rev("staff_admin:BaseBillet_formbricksconfig_changelist"),
                },
            ],
        },
        {
            "models": [
                # Configuration est un singleton : sans cette entree dict, la
                # barre ne s'affiche pas sur sa page et « Cles API » devient
                # inatteignable. / Singleton: without this dict entry the bar
                # never renders and the sibling tabs become unreachable.
                {"name": "BaseBillet.configuration", "detail": True},
                "BaseBillet.configuration",
                "BaseBillet.externalapikey",
                "BaseBillet.webhook",
            ],
            "items": [
                {
                    "title": _("Paramètres"),
                    "link": _safe_rev("staff_admin:BaseBillet_configuration_changelist"),
                },
                {
                    "title": _("Clés API"),
                    "link": _safe_rev("staff_admin:BaseBillet_externalapikey_changelist"),
                },
                {
                    "title": _("Webhooks"),
                    "link": _safe_rev("staff_admin:BaseBillet_webhook_changelist"),
                },
            ],
        },
    ]


def _categoriser_les_pages(pages, lien_vers_modele):
    """
    Range les pages d'un module dans les trois categories de la maquette.
    / Sorts a module's pages into the mockup's three categories.

    LOCALISATION : Administration/admin/dashboard.py

    Une page inconnue de CATEGORIE_DES_PAGES tombe dans « Gérer ». C'est
    volontaire : une page oubliee reste visible plutot que de disparaitre.
    / An unlisted page falls back to "gerer" so it never disappears.

    :param pages: liste des pages du module
    :param lien_vers_modele: dict {url: "app.modele"}
    :return: dict {cle_de_categorie: [pages]}, dans l'ordre de CATEGORIES
    """
    par_categorie = {cle: [] for cle in CATEGORIES}

    for page in pages:
        lien = str(page.get("link") or "")
        # On cherche d'abord par modele, puis par URL brute pour les pages
        # qui ne sont pas des changelists.
        # / Look up by model first, then by raw URL for non-changelist pages.
        cle_de_recherche = lien_vers_modele.get(lien, lien)
        categorie = CATEGORIE_DES_PAGES.get(cle_de_recherche, "gerer")
        # Une page sans description s'affiche sans description : on n'invente
        # pas de texte pour combler.
        # / A page with no description shows none: we invent nothing.
        page["description"] = DESCRIPTION_DES_PAGES.get(cle_de_recherche)
        par_categorie[categorie].append(page)

    # On retire les categories vides : un module sans reglages n'a pas
    # besoin d'un onglet « Configurer » vide.
    # / Drop empty categories.
    return {cle: liste for cle, liste in par_categorie.items() if liste}


def _categorie_active(par_categorie, chemin_courant):
    """
    Devine quelle categorie contient la page affichee.
    / Guesses which category holds the page being displayed.

    LOCALISATION : Administration/admin/dashboard.py

    On compare le debut du chemin courant au lien de chaque page : sur une
    fiche (« /admin/BaseBillet/event/12/change/ ») le chemin est plus long
    que le lien de la changelist (« /admin/BaseBillet/event/ »), mais il
    commence pareil.
    / Prefix match, so a change form still resolves to its changelist's tab.

    :param par_categorie: dict {cle_de_categorie: [pages]}
    :param chemin_courant: request.path
    :return: la cle de la categorie active
    """
    for cle, pages in par_categorie.items():
        for page in pages:
            lien = str(page.get("link") or "")
            if lien and chemin_courant.startswith(lien):
                return cle

    # Aucune correspondance : on ouvre sur la premiere categorie.
    # / No match: fall back to the first category.
    return next(iter(par_categorie))


def get_tabs(request):
    """
    Construit la barre d'onglets d'un module, affichee sur ses pages d'admin.
    / Builds a module's tab bar, shown on its admin pages.

    LOCALISATION : Administration/admin/dashboard.py
    Appelee par Unfold via UNFOLD["TABS"].

    UNE seule rangee, comme la maquette : Gerer / Configurer / Analyser.
    Chaque onglet ramene a la page du module, sur la bonne categorie. Depuis
    une changelist, on peut donc sauter d'une categorie a l'autre sans
    repasser par la sidebar.
    / One row only. Each tab goes back to the module page on that category.

    L'etat actif est calcule ICI, et non par Unfold : ses liens pointent vers
    la page de module, jamais vers la changelist affichee, donc sa comparaison
    d'URL ne trouverait jamais rien. Unfold respecte notre valeur — il ne
    recalcule `active` que si la cle est absente (voir sites.py).
    / We compute `active` ourselves: Unfold only computes it when missing.

    :param request: objet Request Django
    :return: liste de groupes d'onglets au format attendu par Unfold
    """
    onglets = _onglets_hors_modules()
    lien_vers_modele = _carte_des_liens_vers_modeles()
    chemin_courant = request.path

    for section in _construire_sections_modules(request):
        # Les entrees autonomes gardent tous leurs liens dans la sidebar.
        # / Standalone entries keep all their links in the sidebar.
        if not section.get("_domaine") or not section.get("_slug"):
            continue

        pages = section.get("items") or []
        if len(pages) < 2:
            continue

        # Les modeles sur lesquels la barre doit apparaitre.
        # / The models the tab bar should show up on.
        #
        # CHAQUE MODELE EST CITE DEUX FOIS, et ce n'est pas une coquille.
        # _get_tabs_list (unfold/templatetags/unfold.py) ne fait correspondre une
        # entree ECRITE EN CHAINE que si la page est une changelist :
        #
        #     if isinstance(tab_model, str):
        #         if str(opts) == tab_model and page == "changelist":
        #
        # Pour qu'une barre s'affiche sur un FORMULAIRE, il faut une entree dict
        # portant « detail »: True. Or les singletons django-solo
        # (ConfigurationSite, CrowdConfig, LaboutikConfiguration...) rendent un
        # formulaire A L'URL DE LISTE : sans le dict, leur barre disparaissait et
        # on ne pouvait plus revenir vers les autres pages du module autrement
        # que par le rail. Le meme correctif est applique dans
        # _onglets_hors_modules().
        # / A string entry only matches changelists; django-solo singletons render
        #   a form at their list URL, so they need the dict form too.
        modeles = []
        for page in pages:
            modele = lien_vers_modele.get(str(page.get("link", "")))
            if modele and modele not in modeles:
                modeles.append(modele)

        # On double la liste APRES coup : le dedoublonnage ci-dessus travaille sur
        # des chaines, et melanger les deux formes dans la meme boucle le
        # casserait. / Doubled afterwards: the de-duplication above works on
        # strings and would break if both forms were mixed in.
        modeles = [{"name": nom, "detail": True} for nom in modeles] + modeles

        if not modeles:
            continue

        par_categorie = _categoriser_les_pages(pages, lien_vers_modele)
        categorie_ouverte = _categorie_active(par_categorie, chemin_courant)
        adresse_du_module = _safe_rev(
            "staff_admin:page_de_module", args=[section["_slug"]]
        )

        onglets.append(
            {
                "models": modeles,
                "items": [
                    {
                        "title": CATEGORIES[cle],
                        "link": f"{adresse_du_module}?onglet={cle}",
                        "permission": pages_de_la_categorie[0].get("permission"),
                        "active": cle == categorie_ouverte,
                    }
                    for cle, pages_de_la_categorie in par_categorie.items()
                ],
            }
        )

    return onglets


def _page_d_accueil_du_module(pages):
    """
    Choisit la page sur laquelle ouvre le lien du module.
    / Picks the page a module link opens on.

    LOCALISATION : Administration/admin/dashboard.py

    POURQUOI CETTE FONCTION EXISTE : prendre bêtement la premiere page de la
    liste ne marche pas. Le module « Tireuses connectees » commence par un
    lien vers /controlvanne/kiosk/, qui est une page du site public : cliquer
    sur le module faisait donc SORTIR de l'admin, et l'admin des tireuses
    devenait inatteignable.
    / Naively taking the first page fails: the "Tireuses" module starts with a
      link to the public site, which kicked the user out of the admin.

    On prefere donc la premiere page qui est une vraie page d'admin (elle
    commence par /admin/). Si le module n'en a aucune, on retombe sur la
    premiere page de la liste, faute de mieux.
    / Prefer the first real admin page; fall back to the first page.

    :param pages: liste des pages du module (dicts avec une cle "link")
    :return: la page choisie (dict)
    """
    for page in pages:
        lien = str(page.get("link") or "")
        if lien.startswith("/admin/"):
            return page

    # Aucune page d'admin : on ne peut pas faire mieux que la premiere.
    # / No admin page at all: the first one is the best we can do.
    return pages[0]


def _module_en_lien(section, est_courant=False):
    """
    Reduit une section-module a UN seul lien de sidebar.
    / Collapses a module section into a single sidebar link.

    LOCALISATION : Administration/admin/dashboard.py

    Le lien pointe vers la page d'accueil du module, choisie par
    _page_d_accueil_du_module(). Les autres pages restent atteignables par
    les onglets construits dans get_tabs().

    Si un badge etait pose sur une page du module (par exemple le compteur
    d'adhesions recentes), on le fait remonter sur le lien du module : sinon
    il disparaitrait de la sidebar en meme temps que la page qui le portait.
    / A badge set on one of the module's pages bubbles up to the module link.

    :param section: une section telle que construite dans get_sidebar_navigation
    :param est_courant: True si la page affichee appartient a ce module —
        calcule par _module_du_chemin() dans _regrouper_sections_par_domaine
    :return: un dict de lien Unfold, ou None si le module n'a aucune page
    """
    pages = section.get("items") or []
    if not pages:
        return None

    page_d_accueil = _page_d_accueil_du_module(pages)

    # Un module identifie mene a SA page : la liste de ses admins, rangee
    # sous les onglets Gerer / Configurer / Analyser.
    #
    # Sauf s'il n'a qu'UNE page : lui faire traverser une page intermediaire
    # qui ne montre qu'une seule ligne serait de la friction pure. On va
    # alors droit au but.
    # / A one-page module links straight to that page: an intermediate page
    #   showing a single row would be pure friction.
    if section.get("_slug") and len(pages) > 1:
        destination = _safe_rev(
            "staff_admin:page_de_module", args=[section["_slug"]]
        )
    else:
        destination = page_d_accueil.get("link")

    lien = {
        "title": section["title"],
        "icon": section.get("_icone", "widgets"),
        "link": destination,
        "permission": page_d_accueil.get("permission"),
        # Sans cette cle, une changelist n'allume RIEN dans le rail : les
        # pages d'un module ont quitte la sidebar (revision 3), donc la
        # comparaison d'URL d'Unfold ne trouve plus rien a rapprocher de
        # request.path. On lui donne donc la reponse : sites.py:377 respecte
        # un « active » deja pose et ne recalcule que s'il est absent.
        # / A changelist highlights nothing without this: a module's pages
        #   left the sidebar, so Unfold's URL comparison finds no match.
        #
        # ATTENTION : poser la cle DESACTIVE le calcul d'Unfold pour ce lien.
        # La valeur doit donc aussi couvrir le cas qui marchait deja — etre
        # SUR /admin/module/<slug>/ — d'ou le « inclure_page_du_module » de
        # _module_du_chemin(). L'oublier serait une regression.
        # / Setting the key DISABLES Unfold's own computation: our value must
        #   also cover being on the module page itself.
        #
        # Le depliage du domaine suit tout seul : notre surcharge de
        # unfold/helpers/app_list.html ouvre un groupe des qu'un de ses liens
        # est actif ({% has_nav_item_active %}), et la classe est posee cote
        # serveur — donc aucune animation au chargement (revision 10).
        # / The domain group expands on its own via has_nav_item_active.
        "active": est_courant,
    }

    # On remonte le premier badge non vide trouve sur les pages du module.
    # / Bubble up the first non-empty badge found on the module's pages.
    for page in pages:
        badge = page.get("badge")
        if badge:
            lien["badge"] = badge
            break

    return lien


def nom_du_lieu(request):
    """
    Le nom du lieu, affiche en haut du rail.
    / The venue name, shown at the top of the sidebar.

    LOCALISATION : Administration/admin/dashboard.py
    Appelee par Unfold via UNFOLD["SITE_HEADER"].

    La maquette met le nom du lieu en haut de la colonne de gauche. C'est
    utile des qu'on gere plusieurs lieux : on sait tout de suite ou l'on est.
    / The mockup puts the venue name at the top of the rail: with several
      venues, you immediately know where you are.

    Deux gardes :
      - un lieu peut ne pas avoir de nom (le champ « organisation » est
        vide) : on retombe alors sur « TiBillet » plutot que d'afficher un
        rail sans titre ;
      - la lecture peut echouer hors contexte de lieu (schema public) : on
        ne fait pas planter l'admin pour un titre.
    / Falls back to "TiBillet" when the venue has no name, and never crashes
      the admin over a heading.

    :param request: objet Request Django
    :return: le nom a afficher (str)
    """
    try:
        organisation = Configuration.get_solo().organisation
    except Exception:
        # Hors contexte de lieu : pas de Configuration a lire.
        # / Outside a tenant context: no Configuration to read.
        return "TiBillet"

    return organisation or "TiBillet"


def environment_callback(request):
    if settings.DEBUG:
        return [_("Development"), "primary"]

    return [_("Production"), "primary"]


# Texte affiche sur les modules en acces anticipe (BETA).
# On l'ecrit UNE seule fois ici : il est repris a l'identique sur la carte du
# dashboard ET dans la fenetre de confirmation d'activation. Un module est
# marque BETA en posant "beta": True dans son entree ci-dessous.
# / Notice for early-access (BETA) modules. Written once, reused on the dashboard
# / card and the activation confirmation modal. Mark a module BETA with "beta": True.
BETA_NOTICE = _(
    "BETA ! Attention, en accès anticipé, nous avons besoin de vos retours "
    "d'usage et vos remontées de bug. Merci de participer à la construction "
    "de ce commun numérique !"
)


# Ordre des cles = ordre d'affichage des cartes du dashboard.
# La caisse (module_caisse) est a son rang : elle est rendue par la carte POS
# unifiee, inseree a cette position par _build_modules_context.
# La newsletter est en fin de dict : elle n'est PAS dans la grille principale,
# elle a sa propre carte dans la section « Outils externes ».
# / Key order = card display order. POS sits at its rank (unified card).
# / Newsletter is last: it lives in the "External tools" section, not the main grid.
MODULE_FIELDS = {
    "module_pages": {
        "name": _("Site web personnalisé"),
        "description": _(
            "Composez des pages publiques en empilant des blocs (hero, texte, "
            "image, appel à l'action, témoignage). Une page peut devenir la page "
            "d'accueil du site."
        ),
        "testid": "dashboard-card-pages",
        "domaine": "lespass",  # groupe du tableau de bord / dashboard group
        "icone": "web",
        "slug": "site-web",  # module correspondant dans la sidebar
    },
    "module_billetterie": {
        "name": _("Agenda et Billetterie"),
        "description": _("Events, reservations, and ticket sales"),
        "testid": "dashboard-card-billetterie",
        "domaine": "lespass",  # groupe du tableau de bord / dashboard group
        "icone": "event",
        "slug": "agenda",  # module correspondant dans la sidebar
    },
    "module_adhesion": {
        "name": _("Adhésion, abonnement et pass"),
        "description": _("Memberships and subscriptions"),
        "testid": "dashboard-card-adhesion",
        "domaine": "lespass",  # groupe du tableau de bord / dashboard group
        "icone": "card_membership",
        "slug": "adhesion",  # module correspondant dans la sidebar
    },
    "module_federation": {
        "name": _("Fédération et agenda participatif"),
        "description": _(
            "Reliez votre lieu au réseau TiBillet pour partager vos évènements. "
            "Vous pouvez aussi laisser le public proposer des évènements : "
            "c'est l'agenda participatif. Tout se règle dans « Options de fédération »."
        ),
        "testid": "dashboard-card-federation",
        "domaine": "lerezo",  # groupe du tableau de bord / dashboard group
        "icone": "hub",
        "slug": "federation",  # module correspondant dans la sidebar
    },
    "module_crowdfunding": {
        "name": _("Financement participatif & budgets contributifs"),
        "description": _("Participatory funding and adaptive contributions"),
        "testid": "dashboard-card-crowdfunding",
        "domaine": "lekontrib",  # groupe du tableau de bord / dashboard group
        "icone": "volunteer_activism",
        "slug": "financement",  # module correspondant dans la sidebar
    },
    "module_booking": {
        "name": _("Réservation de ressources"),
        "description": _("Réservation de salles, machines ou autres."),
        "testid": "dashboard-card-booking",
        "domaine": "lespass",  # groupe du tableau de bord / dashboard group
        "icone": "meeting_room",
        "slug": "ressources",  # module correspondant dans la sidebar
    },
    "module_caisse": {
        "name": _("Caisse & Restaurant"),
        "description": _("Point of sale, orders, and cash register"),
        "testid": "dashboard-card-caisse",
        "beta": True,
        "link_url": "/laboutik/caisse/",
        "link_label": _("Open POS"),
        "link_icon": "fa-cash-register",
        "domaine": "laboutik",  # groupe du tableau de bord / dashboard group
        "icone": "point_of_sale",
        "slug": "caisse",  # module correspondant dans la sidebar
    },
    "module_monnaie_locale": {
        "name": _("Monnaies locales, temps et cashless"),
        "description": _("Local currency tokens, federated wallet"),
        "testid": "dashboard-card-monnaie-locale",
        "domaine": "lerezo",  # groupe du tableau de bord / dashboard group
        "icone": "toll",
        "slug": "monnaies",  # module correspondant dans la sidebar
    },
    "module_kiosk": {
        "name": _("Kiosk : borne libre-service"),
        "description": _(
            "Bornes de paiement en autonomie : recharge cashless, Stripe Terminal."
        ),
        "testid": "dashboard-card-kiosk",
        "domaine": "lemachines",  # groupe du tableau de bord / dashboard group
        "icone": "smart_display",
        "slug": "kiosk",  # module correspondant dans la sidebar
    },
    "module_tireuse": {
        "name": _("Tireuses connectées"),
        "description": _(
            "Connected beer tap management: RFID authorization, flow metering, kiosk display."
        ),
        "testid": "dashboard-card-tireuse",
        "lien_externe": "/controlvanne/kiosk/",
        "libelle_externe": _("Open kiosk"),
        "testid_externe" : "dashboard-controlvanne-link",
        "externe_nouvel_onglet" : True,
        "link_icon": "fa-display",
        "domaine": "lemachines",  # groupe du tableau de bord / dashboard group
        "icone": "sports_bar",
        "slug": "tireuses",  # module correspondant dans la sidebar
    },
    # Newsletter : hors grille principale, affichee dans la section « Outils externes ».
    # Pilotee par un serveur Ghost ou Brevo. En acces anticipe (BETA).
    # / Newsletter: outside the main grid, shown in the "External tools" section.
    "module_newsletter": {
        "name": _("Newsletter"),
        "description": _(
            "Evènements, rappels d'adhésions, résumé de vos activités : pilotez "
            "votre newsletter avec TiBillet, à partir des évènements de votre agenda ! "
            "Propulsée par un serveur Ghost ou par Brevo."
        ),
        "testid": "dashboard-card-newsletter",
        "beta": True,
        "domaine": "lespass",  # groupe du tableau de bord / dashboard group
        "icone": "mail",
        "slug": "newsletter",  # module correspondant dans la sidebar
    },
}


# Ecart entre l'entree de deux cartes eteintes successives, en millisecondes.
# Valeur de la maquette (TEMP-tibillet-admin-main/script.js) : 40 ms.
# / Stagger between two successive off-card entrances; the mockup's value.
PAS_DE_LA_CASCADE_MS = 40


def _grouper_les_cartes_par_domaine(cartes):
    """
    Range les cartes de module sous leur domaine, pour le tableau de bord.
    / Groups module cards under their domain, for the dashboard.

    LOCALISATION : Administration/admin/dashboard.py

    Reprend l'arborescence de la maquette : un bloc par domaine, avec son
    icone, son sous-titre et un compteur « actifs / total ».

    Une carte sans domaine connu est rangee dans le dernier groupe plutot que
    d'etre jetee : mieux vaut une carte mal rangee qu'une carte disparue.
    / A card with no known domain lands in the last group rather than vanishing.

    :param cartes: liste de cartes (dicts avec au moins "domaine" et "active")
    :return: liste de groupes, dans l'ordre de DOMAINES
    """
    par_domaine = {cle: [] for cle in DOMAINES}

    for carte in cartes:
        cle = carte.get("domaine")
        if cle not in par_domaine:
            # Domaine inconnu : on ne perd pas la carte.
            # / Unknown domain: do not lose the card.
            cle = list(par_domaine)[-1]
        par_domaine[cle].append(carte)

    groupes = []
    for cle, cartes_du_domaine in par_domaine.items():
        if not cartes_du_domaine:
            continue

        domaine = DOMAINES[cle]

        # Delai d'entree de chaque carte ETEINTE, pour l'apparition en cascade
        # quand on ouvre « Decouvrir plus de modules ».
        #
        # Le calcul est fait ICI, en Python, et pas en JavaScript comme la
        # maquette : nos cartes sont rendues cote serveur et leur ordre est
        # deja connu. La maquette avait besoin de JS parce qu'elle construit
        # son DOM a l'execution.
        # / Computed here rather than in JS: our cards are server-rendered and
        #   their order is already known.
        #
        # Le compteur repart de ZERO a chaque domaine, comme la maquette : les
        # domaines demarrent en parallele. Sinon la derniere carte du dernier
        # domaine attendrait pres d'une seconde avant d'apparaitre.
        # / Reset per domain, as in the mockup: domains start in parallel.
        rang = 0
        for carte in cartes_du_domaine:
            if carte.get("active"):
                # Une carte allumee est visible en permanence : elle n'entre
                # jamais, donc aucun delai. / Always visible: never animates.
                carte["delai_ms"] = 0
                continue
            carte["delai_ms"] = rang * PAS_DE_LA_CASCADE_MS
            rang += 1

        groupes.append(
            {
                "cle": cle,
                "titre": domaine["titre"],
                "icone": domaine["icone"],
                "sous_titre": domaine["sous_titre"],
                "lien": _safe_rev("staff_admin:page_de_domaine", args=[cle]),
                "cartes": cartes_du_domaine,
                # Le compteur ne parle que des modules REELS. Une carte
                # « bientot disponible » n'a pas d'interrupteur : l'inclure
                # ferait afficher « 4/6 » alors que seuls 5 modules existent,
                # et laisserait croire qu'il reste deux choses a activer.
                # / The counter only covers real modules: a "coming soon" card
                #   has no toggle, so counting it would promise a switch that
                #   does not exist.
                "total": _compter_les_cartes_reelles(cartes_du_domaine),
                "actifs": _compter_les_cartes_actives(cartes_du_domaine),
            }
        )
    return groupes


def _compter_les_cartes_reelles(cartes):
    """
    Compte les modules qui existent vraiment, interrupteur ou non.
    / Counts modules that actually exist, toggleable or not.

    LOCALISATION : Administration/admin/dashboard.py

    Exclut les cartes « bientot disponible », qui annoncent un module a venir
    mais n'en sont pas un.
    / Excludes "coming soon" cards, which announce a module rather than being one.

    :param cartes: liste de cartes
    :return: nombre de modules reels (int)
    """
    return sum(1 for carte in cartes if carte.get("type") != "coming_soon")


def _compter_les_cartes_actives(cartes):
    """
    Compte les cartes allumees d'un groupe.
    / Counts the lit cards of a group.

    LOCALISATION : Administration/admin/dashboard.py

    La carte POS ne porte pas de booleen "active" mais un "state" a trois
    valeurs : elle compte comme allumee des que la V1 ou la V2 tourne.
    / The POS card has a three-valued "state" instead of a boolean.

    :param cartes: liste de cartes
    :return: nombre de cartes allumees (int)
    """
    nombre = 0
    for carte in cartes:
        if carte.get("type") == "pos":
            if carte.get("state") in ("v1_active", "v2_active"):
                nombre += 1
        elif carte.get("active"):
            nombre += 1
    return nombre


def _compter_les_cartes_eteintes(groupes):
    """
    Compte les modules eteints, tous domaines confondus.
    / Counts the switched-off modules across all domains.

    Sert la pastille de « Decouvrir plus de modules » : elle annonce combien
    de modules restent a decouvrir.
    / Feeds the "discover more modules" pill.

    :param groupes: liste de groupes de domaine
    :return: nombre de cartes eteintes (int)
    """
    return sum(
        groupe["total"] - groupe["actifs"] for groupe in groupes
    )


def _build_modules_context(configuration):
    """
    Construit la liste des cartes de module, dans l'ordre de MODULE_FIELDS.
    / Builds the list of module cards, in MODULE_FIELDS order.

    LOCALISATION : Administration/admin/dashboard.py

    Chaque carte porte un "type" que le gabarit lit pour choisir son rendu :
      - "pos"         : la carte LaBoutik unifiee, a trois etats (V1 / V2 /
                        eteinte), inseree au rang de module_caisse ;
      - "generic"     : une carte a interrupteur simple ;
      - "coming_soon" : une carte informative, grisee, sans interrupteur.

    Chaque carte porte aussi son "domaine" : c'est ce qui permet au tableau
    de bord de les ranger par domaine, comme dans la maquette.
    / Each card carries its domain, which is what lets the dashboard group them.

    :param configuration: la Configuration du lieu
    :return: liste de cartes (dicts)
    """
    cartes = []
    for nom_du_champ, info in MODULE_FIELDS.items():
        # La caisse a sa carte a part : trois etats, pas un interrupteur.
        # / The POS has its own three-state card.
        if nom_du_champ == "module_caisse":
            carte_pos = _build_pos_card_context(configuration)
            carte_pos["type"] = "pos"
            carte_pos["domaine"] = info["domaine"]
            carte_pos["icone"] = info["icone"]
            carte_pos["slug"] = info["slug"]
            # En V1, la caisse ne se desactive pas depuis le tableau de bord :
            # on montre son etat, pas un interrupteur qui mentirait.
            # / In V1 the POS cannot be switched off from here.
            carte_pos["montre_interrupteur"] = carte_pos["state"] != "v1_active"
            carte_pos["allume"] = carte_pos["state"] == "v2_active"
            carte_pos["url_modale"] = carte_pos["toggle_modal_url"]
            carte_pos["testid_interrupteur"] = "dashboard-card-pos-switch"
            _poser_le_lien_d_ouverture(carte_pos, info)
            cartes.append(carte_pos)
            continue

        cartes.append(
            {
                "type": "generic",
                "field": nom_du_champ,
                "name": info["name"],
                "description": info["description"],
                "testid": info["testid"],
                "domaine": info["domaine"],
                "icone": info["icone"],
                "slug": info["slug"],
                "active": getattr(configuration, nom_du_champ),
                "beta": info.get("beta", False),
                "beta_notice": BETA_NOTICE,
                # Ce que le gabarit a besoin de savoir, decide ICI plutot que
                # dans des conditions de template : un module generique a
                # toujours un interrupteur, et il est allume si le module l'est.
                # / Decided here rather than in template conditions.
                "montre_interrupteur": True,
                "allume": getattr(configuration, nom_du_champ),
                "url_modale": reverse(
                    "staff_admin:configuration-module-modal",
                    args=[nom_du_champ],
                ),
                "testid_interrupteur": f"{info['testid']}-switch",
                "modal_url": reverse(
                    "staff_admin:configuration-module-modal",
                    args=[nom_du_champ],
                ),
                "lien_externe": info.get("lien_externe"),
                "libelle_externe": info.get("libelle_externe"),
                "testid_externe": info.get("testid_externe"),
                "externe_nouvel_onglet": info.get("externe_nouvel_onglet"),
            }
        )

    cartes.extend(_build_cartes_a_venir())
    return cartes


def _poser_le_lien_d_ouverture(carte, info):
    """
    Donne a la carte de la caisse son lien vers l'interface LaBoutik.
    / Gives the POS card its link to the LaBoutik interface.

    LOCALISATION : Administration/admin/dashboard.py

    POURQUOI CETTE FONCTION EXISTE : la carte de la caisse portait ce lien,
    et il a disparu quand la carte est devenue generique. Sans lui, on
    n'accede plus a la caisse depuis l'admin — ni a LaBoutik V1 pour un lieu
    reste en V1.
    / The POS card used to carry this link; it vanished when the card became
      generic, leaving no way into LaBoutik from the admin.

    Rien n'est affiche quand la caisse est eteinte : la permission de la
    caisse (HasLaBoutikTerminalAccess) refuse toute route POS dans ce cas,
    le lien menerait droit a un 403.
    / Nothing when the POS is off: its permission denies every POS route
      then, so the link would lead straight to a 403.

    La decision se prend ICI et non dans le gabarit : celui-ci se contente
    d'afficher `lien_externe` s'il existe.
    / Decided here, not in the template, which merely displays the result.

    :param carte: la carte POS, modifiee sur place
    :param info: son entree de MODULE_FIELDS
    :return: None
    """
    if carte["state"] == "v2_active":
        # Caisse V2 en service : on ouvre l'interface.
        # / V2 POS running: open the interface.
        carte["lien_externe"] = info.get("link_url")
        carte["libelle_externe"] = info.get("link_label")
        carte["testid_externe"] = "dashboard-card-pos-open-link"
        carte["externe_nouvel_onglet"] = False

    elif carte["state"] == "v1_active":
        # LaBoutik V1 : le serveur est ailleurs, on ouvre dans un onglet.
        # / LaBoutik V1 lives on another server: open in a new tab.
        carte["lien_externe"] = carte.get("v1_url")
        carte["libelle_externe"] = _("Open LaBoutik V1")
        carte["testid_externe"] = "dashboard-card-pos-v1-link"
        carte["externe_nouvel_onglet"] = True

    else:
        carte["lien_externe"] = None
        carte["libelle_externe"] = None
        carte["testid_externe"] = None
        carte["externe_nouvel_onglet"] = False


def _build_cartes_a_venir():
    """
    Les modules annonces mais pas encore livres.
    / Modules announced but not shipped yet.

    LOCALISATION : Administration/admin/dashboard.py

    Ils n'ont pas de champ dans la Configuration : pas d'interrupteur, juste
    une carte grisee qui dit que ca arrive.
    / No Configuration field, hence no toggle: just a greyed-out card.

    :return: liste de cartes (dicts)
    """
    return [
        {
            # Postiz : integration reseaux sociaux, pas encore livree.
            # / Postiz: social-network integration, not shipped yet.
            "type": "coming_soon",
            "name": _("Réseaux sociaux"),
            "description": _("Postiz"),
            "testid": "dashboard-card-postiz",
            "domaine": "lespass",
            "icone": "share",
            "montre_interrupteur": False,
            "allume": False,
            "coming_soon_label": _("En cours de développement"),
        },
    ]


def _build_pos_card_context(configuration):
    """Carte unifiee "POS & restaurant" du dashboard (3 etats exclusifs).
    / Unified "POS & restaurant" dashboard card (3 mutually exclusive states).

    LOCALISATION : Administration/admin/dashboard.py

    Remplace les anciennes cartes separees (carte module_caisse + cartes
    d'integration LaBoutik V1 / V2). Un seul etat est calcule a partir de la
    configuration du tenant :

      - "v1_active" : server_cashless renseigne -> LaBoutik V1 en service.
                      Lien vers V1, AUCUN toggle (desactivation impossible :
                      la migration V2 se demande a l'equipe TiBillet).
      - "v2_active" : module_caisse=True -> caisse V2 active.
                      Lien vers l'ouverture de la caisse (/laboutik/caisse/).
      - "inactive"  : ni V1 ni V2 -> switch d'activation de la V2 (badge BETA).

    Priorite : V1 d'abord (un tenant V1 ne peut pas activer la V2).
    / Replaces the old separate cards. One state from config: v1_active (link,
    no toggle, migration note), v2_active (open-POS link), inactive (BETA
    activation switch). V1 wins (a V1 tenant cannot enable V2).
    """
    # V1 : presence de server_cashless = configuration V1 branchee.
    # V2 : module_caisse actif.
    # / V1: server_cashless set. V2: module_caisse enabled.
    v1_configure = bool(configuration.server_cashless)
    v2_active = bool(configuration.module_caisse)

    if v1_configure:
        etat = "v1_active"
    elif v2_active:
        etat = "v2_active"
    else:
        etat = "inactive"

    # Statut online/offline de la V1 (health-check HTTP, cache 60s par tenant).
    # Uniquement utile pour l'affichage de l'etat "v1_active".
    # / V1 online/offline status (HTTP health check, 60s cache per tenant).
    # / Only used for the "v1_active" display.
    v1_online = False
    if etat == "v1_active" and configuration.key_cashless:
        cache_key = f"dashboard:laboutik_v1_status:{connection.tenant.pk}"
        cached_status = cache.get(cache_key)
        if cached_status is None:
            try:
                cached_status = configuration.check_serveur_cashless()
            except Exception as exc:
                # Erreur reseau (timeout, DNS, etc.) — on logge, on considere offline.
                # / Network error — log and consider offline.
                logger.warning(f"LaBoutik V1 health check failed: {exc}")
                cached_status = False
            cache.set(cache_key, cached_status, timeout=60)
        v1_online = bool(cached_status)

    return {
        "testid": "dashboard-card-pos",
        "name": MODULE_FIELDS["module_caisse"]["name"],
        "description": MODULE_FIELDS["module_caisse"]["description"],
        # Acces anticipe : encart BETA sur la carte + confirmation dans la modal.
        # / Early access: BETA notice on the card + confirmation in the modal.
        "beta": MODULE_FIELDS["module_caisse"].get("beta", False),
        "beta_notice": BETA_NOTICE,
        "state": etat,
        # V1 : lien vers l'interface historique + statut de connexion.
        # / V1: link to the historical interface + connection status.
        "v1_url": configuration.server_cashless or None,
        "v1_online": v1_online,
        # V2 : URL d'ouverture de la caisse (depuis MODULE_FIELDS).
        # / V2: open-POS URL (from MODULE_FIELDS).
        "v2_open_url": MODULE_FIELDS["module_caisse"].get("link_url"),
        # Modal de confirmation pour (de)activer le module caisse.
        # / Confirmation modal to enable/disable the cash register module.
        "toggle_modal_url": reverse(
            "staff_admin:configuration-module-modal",
            args=["module_caisse"],
        ),
    }


def _build_taches_referencement_context(configuration):
    """Liste des informations manquantes qui penalisent le referencement du site.
    / List of missing settings that hurt the website's search-engine visibility.

    Chaque entree decrit UNE information a completer dans la page Configuration.
    La liste est vide quand tout est rempli : l'encart disparait alors du dashboard.
    / Each entry describes ONE setting to fill in the Configuration page.
    Empty list when everything is filled: the dashboard notice then disappears.

    Volontairement hors de toute classe ModelAdmin : Unfold wrappe les methodes
    de classe via son systeme d'actions (cf. skill unfold, piege 23).
    / Deliberately outside any ModelAdmin class: Unfold wraps class methods
    through its actions system.
    """
    # Lien unique vers la page de configuration du tenant. Le reverse tolerant
    # renvoie "#" si l'admin n'est pas disponible, plutot que de tout casser.
    # Attention : l'app_label est "BaseBillet" avec ses majuscules, le nom
    # d'URL n'est donc PAS en minuscules comme le veut l'usage Django.
    # / Single link to the tenant configuration page; tolerant reverse -> "#".
    # Note: app_label is "BaseBillet" (mixed case), so the URL name is NOT
    # lowercase as usual in Django.
    lien_configuration = _safe_rev_inner(
        "staff_admin:BaseBillet_configuration_change",
        args=[configuration.pk],
    )

    taches = []

    # Image de partage : elle alimente la balise og:image (apercu sur les
    # reseaux sociaux et dans les messageries). Sans elle, aucune vignette.
    # / Sharing image: feeds the og:image tag. Without it, no social preview.
    if not configuration.img:
        taches.append({
            "testid": "tache-image",
            "icone": "image",
            "titre": _("Ajouter une image de partage"),
            "explication": _(
                "Sans image, aucun aperçu ne s'affiche quand votre site est "
                "partagé sur les réseaux sociaux ou dans une messagerie."
            ),
        })

    # Description courte : utilisee comme meta description dans les resultats
    # de recherche. C'est le texte que voit un visiteur avant de cliquer.
    # / Short description: used as the meta description in search results.
    if not configuration.short_description:
        taches.append({
            "testid": "tache-description-courte",
            "icone": "short_text",
            "titre": _("Écrire une description courte"),
            "explication": _(
                "C'est le texte affiché sous votre titre dans les résultats "
                "de recherche. Une à deux phrases suffisent."
            ),
        })

    # Description longue : contenu indexable, utile aux moteurs de recherche
    # comme aux moteurs generatifs (IA) qui citent des sources.
    # / Long description: indexable content, useful to search and AI engines.
    if not configuration.long_description:
        taches.append({
            "testid": "tache-description-longue",
            "icone": "notes",
            "titre": _("Écrire une description longue"),
            "explication": _(
                "Présentez votre activité en détail. Ce texte est lu par les "
                "moteurs de recherche et par les assistants IA."
            ),
        })

    # Mentions legales / CGV : obligation legale des qu'on vend en ligne.
    # On accepte DEUX sources : le lien externe historique (legal_documents)
    # ou une page interne dediee. Si l'une des deux existe, la tache disparait.
    # / Legal notice / T&C: accepts either the legacy external link or an
    # internal page. Task disappears as soon as one of them exists.
    if not configuration.legal_documents and not _page_legale_existe():
        taches.append({
            "testid": "tache-mentions-legales",
            "icone": "gavel",
            "titre": _("Renseigner vos mentions légales"),
            "explication": _(
                "Obligatoire dès que vous vendez en ligne. Renseignez le lien "
                "vers vos conditions générales dans la configuration."
            ),
        })

    # Identite legale : necessaire pour generer des mentions legales completes
    # et pour les tickets de caisse.
    # / Legal identity: required for complete legal notices and POS receipts.
    if not configuration.siren and not configuration.tva_number:
        taches.append({
            "testid": "tache-identite-legale",
            "icone": "badge",
            "titre": _("Renseigner votre numéro SIREN ou TVA"),
            "explication": _(
                "Ces informations identifient votre organisation dans vos "
                "mentions légales et sur vos justificatifs de vente."
            ),
        })

    # Telephone : signal de contact direct, pris en compte par les moteurs
    # de recherche locaux et par les agents IA qui cherchent a vous joindre.
    # / Phone: direct contact signal for local search and AI agents.
    if not configuration.phone:
        taches.append({
            "testid": "tache-telephone",
            "icone": "call",
            "titre": _("Ajouter un numéro de téléphone"),
            "explication": _(
                "Un contact direct rassure les visiteurs et améliore votre "
                "référencement local."
            ),
        })

    return {
        "lien_configuration": lien_configuration,
        "taches": taches,
    }


def _page_legale_existe():
    """Vrai si une page interne de mentions legales est publiee sur ce tenant.
    / True if an internal legal-notice page is published on this tenant.

    Import local : l'app `pages` n'est pas toujours chargee au moment ou le
    module admin est importe. On tolere son absence sans casser le dashboard.
    / Local import: the `pages` app may not be loaded when this admin module is
    imported. Tolerate its absence without breaking the dashboard.
    """
    try:
        from pages.models import Page
    except ImportError:
        return False

    return Page.objects.filter(
        slug__in=["mentions-legales", "cgv", "cgu", "confidentialite"],
        publie=True,
    ).exists()


def dashboard_callback(request, context):

    configuration = Configuration.get_solo()

    groupes_de_domaines = _grouper_les_cartes_par_domaine(
        _build_modules_context(configuration)
    )
    _poser_les_liens_des_modules(request, groupes_de_domaines)

    context.update(
        {
            # Encart « Ce qu'il reste a faire » : informations manquantes qui
            # penalisent le referencement. Affiche tout en haut du dashboard.
            # / "What's left to do" notice: missing settings hurting SEO.
            "taches_referencement": _build_taches_referencement_context(configuration),
            # Les cartes de module, rangees par domaine — c'est la structure de
            # la maquette : un bloc par domaine, avec son compteur.
            # La section « Outils externes » a disparu : la newsletter et les
            # reseaux sociaux sont de la communication publique, ils vivent
            # donc dans le domaine Lespass comme le reste.
            # / Module cards grouped by domain, as in the mockup. The "external
            #   tools" section is gone: newsletter and social networks are public
            #   communication, so they live in the Lespass domain.
            "groupes_de_domaines": groupes_de_domaines,
            # Combien de modules restent eteints : c'est la pastille de la ligne
            # « Decouvrir plus de modules ».
            # / How many modules are still off: the "discover more" pill.
            "modules_eteints": _compter_les_cartes_eteintes(groupes_de_domaines),
            # Adresse de contact du bouton « Proposer une idee ». La meme que
            # celle du bouton « Contacter l'equipe » de admin/service.html.
            # / Contact address for the "suggest an idea" button.
            "lien_contact": "mailto:contact@tibillet.re",
        }
    )

    # --- Phase 2 : injecter la dette du pot central pour le widget tenant ---
    # / Phase 2: inject central pot debt for the tenant widget
    # Cf. tests/PIEGES.md 9.1b : verifier isinstance(connection.tenant, Client)
    # car en contexte de test connection.tenant peut etre un FakeTenant.

    # FROM V2 : TO ADD WHEN FEDOW IS IMPLEMENTED
    # try:
    #     config_phase2 = Configuration.get_solo()
    # except Exception:
    #     config_phase2 = None
    # if config_phase2 is not None and getattr(config_phase2, "module_monnaie_locale", False):
    #     from fedow_core.services import BankTransferService
    #     from Customers.models import Client as CustomersClient
    #     if isinstance(connection.tenant, CustomersClient):
    #         context["dettes_pot_central"] = BankTransferService.obtenir_dette_pour_tenant(
    #             connection.tenant
    #         )
    #
    # NEW V2 END

    return context
