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

    # --- Toujours visible : Global information ---
    navigation = [
        {
            "title": _("Global information"),
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
                "title": _("Site web"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        # Edition principale : les blocs (approche inversee).
                        # / Primary editing: the blocks (inverted approach).
                        "title": _("Blocs"),
                        "icon": "dashboard",
                        "link": reverse_lazy("staff_admin:pages_bloc_changelist"),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Pages"),
                        "icon": "web",
                        "link": reverse_lazy("staff_admin:pages_page_changelist"),
                        "permission": admin_permission,
                    },
                    {
                        "title": _("Configuration du site"),
                        "icon": "palette",
                        "link": reverse_lazy(
                            "staff_admin:pages_configurationsite_changelist"
                        ),
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
                "title": _("Memberships"),
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
                "title": _("Ticketing"),
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
                "title": _("Fédération"),
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
                "title": _("Caisse LaBoutik"),
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
                    # « Device pairing (PIN) » retiré d'ici : l'appairage vit
                    # dans la section « Hardware terminals » plus bas (l'entrée
                    # pointait déjà sur la même changelist PairingDevice).
                    # / "Device pairing (PIN)" removed from here: pairing lives
                    # in the "Hardware terminals" section below (same
                    # PairingDevice changelist).
                    {
                        "title": _("Printers"),
                        "icon": "print",
                        "link": _safe_rev("staff_admin:laboutik_printer_changelist"),
                        "permission": admin_permission,
                    },
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
    # --- Hardware terminals section: visible if caisse, local currency or taps ---
    # L'entree pointe vers les PairingDevice (discovery) : c'est la que vit
    # tout le process d'appairage — creation du PIN (caisse LB, kiosque KI),
    # suivi des PIN en attente et des appareils reclames. Les comptes
    # TermUser crees par les claims restent visibles via l'app AuthBillet.
    # / The entry points to PairingDevices (discovery): the whole pairing
    # process lives there — PIN creation (LB pos, KI kiosk), pending PINs
    # and claimed devices. The TermUser accounts created by claims remain
    # reachable through the AuthBillet app.
    if (
        configuration.module_caisse
        or configuration.module_monnaie_locale
        or configuration.module_tireuse
    ):
        navigation.append(
            {
                "title": _("Hardware terminals"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Terminals"),
                        "icon": "tablet",
                        "link": _safe_rev(
                            "staff_admin:discovery_pairingdevice_changelist"
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
                "title": _("Fedow"),
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

    # --- module_inventaire : Stock et mouvements ---
    # / --- module_inventaire: Stock and movements ---
    if configuration.module_inventaire:
        navigation.append(
            {
                "title": _("Inventaire"),
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
                "title": _("Tireuses"),
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

    # --- module_kiosk : Bornes libre-service (Stripe Terminal) ---
    # / --- module_kiosk: Self-service kiosks (Stripe Terminal) ---
    if configuration.module_kiosk:
        navigation.append(
            {
                "title": _("Kiosk"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("TPE Bancaires"),
                        "icon": "tablet_mac",
                        "link": _safe_rev("staff_admin:kiosk_terminal_changelist"),
                        "permission": admin_permission,
                    },
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
                "title": _("Contributions"),
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

    # --- Toujours visible : External tools ---
    navigation.append(
        {
            "title": _("External tools"),
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": _("API Key"),
                    "icon": "api",
                    "link": _safe_rev(
                        "staff_admin:BaseBillet_externalapikey_changelist"
                    ),
                    "permission": admin_permission,
                },
                {
                    "title": _("Webhook"),
                    "icon": "webhook",
                    "link": _safe_rev("staff_admin:BaseBillet_webhook_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Ghost"),
                    "icon": "circle",
                    "link": _safe_rev(
                        "staff_admin:BaseBillet_ghostconfig_changelist"
                    ),
                    "permission": admin_permission,
                },
                {
                    "title": _("Formbricks"),
                    "icon": "list_alt",
                    "link": _safe_rev(
                        "staff_admin:BaseBillet_formbricksforms_changelist"
                    ),
                    "permission": admin_permission,
                },
                {
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

    # --- Root seulement : Root Configuration ---
    navigation.append(
        {
            "title": _("Root Configuration"),
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


def environment_callback(request):
    if settings.DEBUG:
        return [_("Development"), "primary"]

    return [_("Production"), "primary"]


MODULE_FIELDS = {
    "module_billetterie": {
        "name": _("Event ticketing"),
        "description": _("Events, reservations, and ticket sales"),
        "testid": "dashboard-card-billetterie",
        "required": [""]
    },
    "module_adhesion": {
        "name": _("Membership"),
        "description": _("Memberships and subscriptions"),
        "testid": "dashboard-card-adhesion",
    },
    "module_crowdfunding": {
        "name": _("Crowdfunding"),
        "description": _("Participatory funding and adaptive contributions"),
        "testid": "dashboard-card-crowdfunding",
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
    "module_pages": {
        "name": _("Pages / site web"),
        "description": _(
            "Composez des pages publiques en empilant des blocs (hero, texte, "
            "image, appel à l'action, témoignage). Une page peut devenir la page "
            "d'accueil du site."
        ),
        "testid": "dashboard-card-pages",
    },
    # FROM V2 : TO IMPLEMENT LATER ON
    "module_monnaie_locale": {
        "name": _("Local currency & cashless"),
        "description": _("Local currency tokens, federated wallet"),
        "testid": "dashboard-card-monnaie-locale",
    },
    "module_caisse": {
        "name": _("POS & restaurant"),
        "description": _("Point of sale, orders, and cash register"),
        "testid": "dashboard-card-caisse",
        "link_url": "/laboutik/caisse/",
        "link_label": _("Open POS"),
        "link_icon": "fa-cash-register",
    },
    "module_inventaire": {
        "name": _("Inventory"),
        "description": _(
            "Stock management for POS products: tracking, alerts, movements."
        ),
        "testid": "dashboard-card-inventaire",
    },
    # Tireuses connectees avec paiement NFC (controlvanne)
    # / Connected beer taps with NFC payment (controlvanne)
    "module_tireuse": {
        "name": _("Connected taps"),
        "description": _(
            "Connected beer tap management: RFID authorization, flow metering, kiosk display."
        ),
        "testid": "dashboard-card-tireuse",
        "link_url": "/controlvanne/kiosk/",
        "link_label": _("Open kiosk"),
        "link_icon": "fa-display",
    },
    # "module_booking": {
    #     "name": _("Booking"),
    #     "description": _("Resource booking: rooms, equipment, coworking desks."),
    #     "testid": "dashboard-card-booking",
    # },
    # Kiosk / borne libre-service (Stripe Terminal, paiement autonome)
    # / Kiosk / self-service (Stripe Terminal, unattended payment)
    "module_kiosk": {
        "name": _("Kiosk / borne libre-service"),
        "description": _(
            "Bornes de paiement en autonomie : recharge cashless, Stripe Terminal."
        ),
        "testid": "dashboard-card-kiosk",
        "icon": "storefront",
    },
}


def _build_modules_context(configuration):
    """Construit la liste de modules pour le dashboard.
    Utilise par dashboard_callback et par le toggle HTMX.

    La caisse (module_caisse) est EXCLUE de cette grille : elle est rendue par
    la carte POS unifiee (_build_pos_card_context), qui fusionne LaBoutik V1,
    LaBoutik V2 et l'activation du module en une seule carte a 3 etats.
    / module_caisse is excluded here: it is rendered by the unified POS card."""
    modules = []
    for field_name, info in MODULE_FIELDS.items():
        # La caisse a sa propre carte (carte POS unifiee). On la saute ici.
        # / The cash register has its own (unified POS) card; skip it here.
        if field_name == "module_caisse":
            continue
        modules.append(
            {
                "field": field_name,
                "name": info["name"],
                "description": info["description"],
                "testid": info["testid"],
                "active": getattr(configuration, field_name),
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
            "modules": _build_modules_context(configuration),
            # Carte POS unifiee (remplace les anciennes cartes V1/V2 + caisse).
            # / Unified POS card (replaces the old V1/V2 + cash register cards).
            "pos_card": _build_pos_card_context(configuration),
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
