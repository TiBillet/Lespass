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
def event_proposals_badge_callback(request):
    """
    Compte des propositions d'event en attente de validation.
    / Count of pending event proposals.

    Affiche un badge "+ N" sur le menu "Events" si des propositions
    publiques attendent moderation (is_proposal=True, published=False).
    """
    from BaseBillet.models import Event
    count = Event.objects.filter(is_proposal=True, published=False).count()
    return f"+ {count}" if count else None


def get_sidebar_navigation(request):
    """Sidebar dynamique : masque les sections liees aux modules inactifs.
    Appelee par Unfold via SIDEBAR.navigation (string importable)."""

    configuration = Configuration.get_solo()

    admin_permission = "ApiBillet.permissions.TenantAdminPermissionWithRequest"
    root_permission = "ApiBillet.permissions.RootPermissionWithRequest"

    # --- Toujours visible : Configuration générale ---
    navigation = [
        {
            "title": _("Configuration générale"),
            "_order": 0.0,  # Famille 0 : pilotage / Family 0: control
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": _("Dashboard"),
                    "icon": "dashboard",
                    "link": _safe_rev("admin:index"),
                    "permission": admin_permission,
                },
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
                "_order": 1.0,  # Famille 1 : vitrine & communication
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
                "_order": 2.1,  # Famille 2 : billetterie & adhesions
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
                "_order": 2.0,  # Famille 2 : billetterie & adhesions
                "separator": True,
                "collapsible": True,
                "items": [
                    # FROM V2 : PAGES TO IMPLEMENT
                    # {
                    #     "title": _("Dashboard"),
                    #     "icon": "monitoring",
                    #     "link": _safe_rev("staff_admin:BaseBillet_event_dashboard"),
                    #     "permission": admin_permission,
                    # },
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
                "_order": 1.1,  # Famille 1 : vitrine & communication
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


    # FROM V2 : TO ADD LATER
    # --- module_caisse : Caisse LaBoutik ---
    # --- module_caisse: POS LaBoutik ---
    if configuration.module_caisse:
        navigation.append(
            {
                "title": _("Caisse & Restaurant"),
                "_order": 3.0,  # Famille 3 : point de vente
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
                "_order": 3.5,  # Famille 3 : point de vente (materiel)
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
                "_order": 3.2,  # Famille 3 : point de vente
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
                "_order": 3.1,  # Famille 3 : point de vente
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
                "_order": 3.4,  # Famille 3 : point de vente
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
                "_order": 3.3,  # Famille 3 : point de vente
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
                "_order": 2.3,  # Famille 2 : billetterie, adhesions & reservations
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Resources"),
                        "icon": "chair",
                        "link": _safe_rev("staff_admin:booking_resource_changelist"),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Resource groups"),
                        "icon": "stacks",
                        "link": _safe_rev("staff_admin:booking_resourcegroup_changelist"),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Calendars"),
                        "icon": "calendar_month",
                        "link": _safe_rev("staff_admin:booking_calendar_changelist"),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Weekly openings"),
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
            "_order": 4.0,  # Famille 4 : comptabilite / Family 4: accounting
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
                "_order": 2.2,  # Famille 2 : billetterie & adhesions
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
                "_order": 1.2,  # Famille 1 : vitrine & communication
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
            "_order": 5.0,  # Famille 5 : reseau (root) / Family 5: network (root)
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

    # ------------------------------------------------------------------ #
    # Rangement des sections en FAMILLES (approche « ordre + separateurs ») #
    # ------------------------------------------------------------------ #
    # Chaque section porte un champ "_order" = X.Y :
    #   - X (partie entiere) = la famille (0 = pilotage, 1 = vitrine & com,
    #     2 = billetterie & adhesions, 3 = point de vente, 4 = comptabilite,
    #     5 = reseau).
    #   - Y (partie decimale) = la position DANS la famille.
    # On trie les sections par "_order", puis on n'affiche le filet separateur
    # QU'AU DEBUT de chaque famille : les sections d'une meme famille apparaissent
    # collees (regroupees), et un filet marque le passage a la famille suivante.
    # Le tri gere aussi les sections absentes (module inactif) sans trou visuel.
    # Pour changer un regroupement : il suffit d'ajuster les "_order" ci-dessus,
    # nul besoin de deplacer le code.
    # / Group sections into families: sort by "_order", show the separator only at
    # / each family boundary so same-family sections read as one block.
    navigation.sort(key=lambda section: section.get("_order", 999))
    famille_precedente = None
    for section in navigation:
        famille_courante = int(section.get("_order", 999))
        section["separator"] = famille_courante != famille_precedente
        famille_precedente = famille_courante
        section.pop("_order", None)

    return navigation


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
    },
    "module_billetterie": {
        "name": _("Agenda et Billetterie"),
        "description": _("Events, reservations, and ticket sales"),
        "testid": "dashboard-card-billetterie",
    },
    "module_adhesion": {
        "name": _("Adhésion, abonnement et pass"),
        "description": _("Memberships and subscriptions"),
        "testid": "dashboard-card-adhesion",
    },
    "module_federation": {
        "name": _("Fédération et agenda participatif"),
        "description": _(
            "Reliez votre lieu au réseau TiBillet pour partager vos évènements. "
            "Vous pouvez aussi laisser le public proposer des évènements : "
            "c'est l'agenda participatif. Tout se règle dans « Options de fédération »."
        ),
        "testid": "dashboard-card-federation",
    },
    "module_crowdfunding": {
        "name": _("Financement participatif & budgets contributifs"),
        "description": _("Participatory funding and adaptive contributions"),
        "testid": "dashboard-card-crowdfunding",
    },
    "module_caisse": {
        "name": _("Caisse & Restaurant"),
        "description": _("Point of sale, orders, and cash register"),
        "testid": "dashboard-card-caisse",
        "beta": True,
        "link_url": "/laboutik/caisse/",
        "link_label": _("Open POS"),
        "link_icon": "fa-cash-register",
    },
    "module_monnaie_locale": {
        "name": _("Monnaies locales, temps et cashless"),
        "description": _("Local currency tokens, federated wallet"),
        "testid": "dashboard-card-monnaie-locale",
    },
    "module_kiosk": {
        "name": _("Kiosk : borne libre-service"),
        "description": _(
            "Bornes de paiement en autonomie : recharge cashless, Stripe Terminal."
        ),
        "testid": "dashboard-card-kiosk",
        "icon": "storefront",
    },
    "module_tireuse": {
        "name": _("Tireuses connectées"),
        "description": _(
            "Connected beer tap management: RFID authorization, flow metering, kiosk display."
        ),
        "testid": "dashboard-card-tireuse",
        "link_url": "/controlvanne/kiosk/",
        "link_label": _("Open kiosk"),
        "link_icon": "fa-display",
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
    },
}


def _build_modules_context(configuration):
    """Construit la liste ordonnee des cartes de la grille principale « Modules ».
    Utilise par dashboard_callback et par le toggle HTMX.

    Chaque carte porte un champ "type" que le gabarit lit pour choisir son rendu :
      - "pos"     : la carte POS unifiee (LaBoutik V1/V2 + activation), inseree
                    a la position de module_caisse dans l'ordre de MODULE_FIELDS.
      - "generic" : une carte a interrupteur simple (les autres modules).

    La newsletter est EXCLUE ici : elle a sa propre carte dans la section
    « Outils externes » (cf. _build_external_cards_context).
    / Ordered list of the main "Modules" grid cards. Each card has a "type" the
    / template reads. The POS card is inserted at module_caisse's rank; the
    / newsletter is excluded (it belongs to the "External tools" section)."""
    modules = []
    for field_name, info in MODULE_FIELDS.items():
        # La newsletter est rendue a part, dans « Outils externes ».
        # / Newsletter is rendered apart, in "External tools".
        if field_name == "module_newsletter":
            continue

        # La caisse est rendue par la carte POS unifiee, a son rang dans l'ordre.
        # / The cash register is rendered by the unified POS card, at its rank.
        if field_name == "module_caisse":
            pos_card = _build_pos_card_context(configuration)
            pos_card["type"] = "pos"
            modules.append(pos_card)
            continue

        modules.append(
            {
                "type": "generic",
                "field": field_name,
                "name": info["name"],
                "description": info["description"],
                "testid": info["testid"],
                "active": getattr(configuration, field_name),
                # Acces anticipe : la carte affiche l'encart BETA et la modal
                # d'activation demande une confirmation « J'ai compris et je teste ! ».
                # / Early access: card shows the BETA notice, modal asks to confirm.
                "beta": info.get("beta", False),
                "beta_notice": BETA_NOTICE,
                "modal_url": reverse(
                    "staff_admin:configuration-module-modal",
                    args=[field_name],
                ),
                "link_url": info.get("link_url"),
                "link_label": info.get("link_label"),
                "link_icon": info.get("link_icon"),
            }
        )
    return modules


def _build_external_cards_context(configuration):
    """Cartes de la section « Outils externes » du dashboard.
    / Cards of the dashboard "External tools" section.

    Deux cartes :
      - Newsletter : interrupteur du module (Ghost ou Brevo), en acces anticipe (BETA).
      - Reseaux sociaux : Postiz, pas encore disponible. Carte informative grisee,
        sans interrupteur (type "coming_soon")."""
    newsletter_info = MODULE_FIELDS["module_newsletter"]
    return [
        {
            "type": "generic",
            "field": "module_newsletter",
            "name": newsletter_info["name"],
            "description": newsletter_info["description"],
            "testid": newsletter_info["testid"],
            "active": configuration.module_newsletter,
            "beta": newsletter_info.get("beta", False),
            "beta_notice": BETA_NOTICE,
            "modal_url": reverse(
                "staff_admin:configuration-module-modal",
                args=["module_newsletter"],
            ),
            "link_url": None,
            "link_label": None,
            "link_icon": None,
        },
        {
            # Postiz : integration reseaux sociaux, pas encore livree.
            # Carte informative uniquement (grisee, sans interrupteur).
            # / Postiz: social networks integration, not shipped yet. Info-only card.
            "type": "coming_soon",
            "name": _("Réseaux sociaux"),
            "description": _("Postiz"),
            "testid": "dashboard-card-postiz",
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


def dashboard_callback(request, context):

    configuration = Configuration.get_solo()

    context.update(
        {
            # Grille principale « Modules » : liste ordonnee, la carte POS unifiee
            # y est inseree a son rang (type "pos").
            # / Main "Modules" grid: ordered list, POS card inserted at its rank.
            "modules": _build_modules_context(configuration),
            # Section « Outils externes » : newsletter (Ghost/Brevo) + reseaux sociaux.
            # / "External tools" section: newsletter (Ghost/Brevo) + social networks.
            "external_cards": _build_external_cards_context(configuration),
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
