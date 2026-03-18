import logging
from datetime import timedelta

from django.conf import settings
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from BaseBillet.models import Configuration, Membership

logger = logging.getLogger(__name__)


# Le petit badge route a droite du titre "adhésion"
def adhesion_badge_callback(request):
    # Recherche de la quantité de nouvelles adhésions ces 14 dernièrs jours
    return f"+ {Membership.objects.filter(last_contribution__gte=timezone.localtime() - timedelta(days=7)).count()}"


def get_sidebar_navigation(request):
    """Sidebar dynamique : masque les sections liees aux modules inactifs.
    Appelee par Unfold via SIDEBAR.navigation (string importable)."""
    from BaseBillet.models import Configuration

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
                    "link": reverse_lazy("admin:index"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Settings"),
                    "icon": "manufacturing",
                    "link": reverse_lazy("staff_admin:BaseBillet_configuration_changelist"),
                    "permission": admin_permission,
                },
            ],
        },
    ]

    # --- Comptes utilisateurs dans Informations generales ---
    # --- User accounts in Global information ---
    navigation[0]["items"].append({
        "title": _("User accounts"),
        "icon": "person_add",
        "link": reverse_lazy("staff_admin:AuthBillet_humanuser_changelist"),
        "permission": admin_permission,
    })

    # --- module_adhesion : section Adhesions ---
    # --- module_adhesion: Memberships section ---
    if configuration.module_adhesion:
        navigation.append({
            "title": _("Memberships"),
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": _("Membership products"),
                    "icon": "loyalty",
                    "link": reverse_lazy("staff_admin:BaseBillet_membershipproduct_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Subscriptions"),
                    "icon": "card_membership",
                    "link": reverse_lazy("staff_admin:BaseBillet_membership_changelist"),
                    "badge": "Administration.admin.dashboard.adhesion_badge_callback",
                    "permission": admin_permission,
                },
            ],
        })

    # --- module_billetterie : tout ce qui concerne la billetterie ---
    # --- module_billetterie: everything related to ticketing ---
    if configuration.module_billetterie:
        navigation.append({
            "title": _("Ticketing"),
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": _("Ticket products"),
                    "icon": "storefront",
                    "link": reverse_lazy("staff_admin:BaseBillet_ticketproduct_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Carousel"),
                    "icon": "photo_library",
                    "link": reverse_lazy("staff_admin:BaseBillet_carrousel_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Promotional codes"),
                    "icon": "local_offer",
                    "link": reverse_lazy("staff_admin:BaseBillet_promotionalcode_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Tags"),
                    "icon": "style",
                    "link": reverse_lazy("staff_admin:BaseBillet_tag_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Addresses"),
                    "icon": "signpost",
                    "link": reverse_lazy("staff_admin:BaseBillet_postaladdress_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Events"),
                    "icon": "event",
                    "link": reverse_lazy("staff_admin:BaseBillet_event_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Bookings"),
                    "icon": "event_upcoming",
                    "link": reverse_lazy("staff_admin:BaseBillet_reservation_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Tickets"),
                    "icon": "confirmation_number",
                    "link": reverse_lazy("staff_admin:BaseBillet_ticket_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Scan App"),
                    "icon": "qr_code_scanner",
                    "link": reverse_lazy("staff_admin:BaseBillet_scanapp_changelist"),
                    "permission": admin_permission,
                },
            ],
        })

    # --- module_caisse : Caisse LaBoutik ---
    # --- module_caisse: POS LaBoutik ---
    if configuration.module_caisse:
        navigation.append({
            "title": _("Caisse LaBoutik"),
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": _("POS products"),
                    "icon": "point_of_sale",
                    "link": reverse_lazy("staff_admin:BaseBillet_posproduct_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("POS categories"),
                    "icon": "category",
                    "link": reverse_lazy("staff_admin:BaseBillet_categorieproduct_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Points of sale"),
                    "icon": "store",
                    "link": reverse_lazy("staff_admin:laboutik_pointdevente_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Primary cards"),
                    "icon": "badge",
                    "link": reverse_lazy("staff_admin:laboutik_carteprimaire_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Device pairing (PIN)"),
                    "icon": "phonelink_setup",
                    "link": reverse_lazy("staff_admin:discovery_pairingdevice_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Orders"),
                    "icon": "receipt",
                    "link": reverse_lazy("staff_admin:laboutik_commandesauvegarde_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Closures"),
                    "icon": "summarize",
                    "link": reverse_lazy("staff_admin:laboutik_cloturecaisse_changelist"),
                    "permission": admin_permission,
                },
            ],
        })

    # --- module_monnaie_locale : Fedow (monnaies, tokens, transactions) ---
    # --- module_monnaie_locale: Fedow (currencies, tokens, transactions) ---
    if configuration.module_monnaie_locale:
        navigation.append({
            "title": _("Fedow"),
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": _("Monnaies et tokens"),
                    "icon": "toll",
                    "link": reverse_lazy("staff_admin:fedow_core_asset_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Soldes"),
                    "icon": "account_balance_wallet",
                    "link": reverse_lazy("staff_admin:fedow_core_token_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Transactions"),
                    "icon": "receipt_long",
                    "link": reverse_lazy("staff_admin:fedow_core_transaction_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Federations"),
                    "icon": "hub",
                    "link": reverse_lazy("staff_admin:fedow_core_federation_changelist"),
                    "permission": admin_permission,
                },
            ],
        })

    # --- Toujours visible : Sales ---
    navigation.append({
        "title": _("Sales"),
        "separator": True,
        "collapsible": True,
        "items": [
            {
                "title": _("Entries"),
                "icon": "receipt_long",
                "link": reverse_lazy("staff_admin:BaseBillet_lignearticle_changelist"),
                "permission": admin_permission,
            },
        ],
    })

    # --- Toujours visible : Fédération ---
    navigation.append({
        "title": _("Fédération"),
        "separator": True,
        "collapsible": True,
        "items": [
            {
                "title": _("Espaces"),
                "icon": "linked_services",
                "link": reverse_lazy("staff_admin:BaseBillet_federatedplace_changelist"),
                "permission": admin_permission,
            },
            {
                "title": _("Assets"),
                "icon": "currency_exchange",
                "link": reverse_lazy("staff_admin:fedow_public_assetfedowpublic_changelist"),
                "permission": admin_permission,
            },
        ],
    })

    # --- module_crowdfunding : Contributions ---
    if configuration.module_crowdfunding:
        navigation.append({
            "title": _("Contributions"),
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": _("Configuration"),
                    "icon": "manufacturing",
                    "link": reverse_lazy("staff_admin:crowds_crowdconfig_changelist"),
                    "permission": admin_permission,
                },
                {
                    "title": _("Initiative"),
                    "icon": "crowdsource",
                    "link": reverse_lazy("staff_admin:crowds_initiative_changelist"),
                    "permission": admin_permission,
                },
            ],
        })

    # --- Toujours visible : External tools ---
    navigation.append({
        "title": _("External tools"),
        "separator": True,
        "collapsible": True,
        "items": [
            {
                "title": _("API Key"),
                "icon": "api",
                "link": reverse_lazy("staff_admin:BaseBillet_externalapikey_changelist"),
                "permission": admin_permission,
            },
            {
                "title": _("Webhook"),
                "icon": "webhook",
                "link": reverse_lazy("staff_admin:BaseBillet_webhook_changelist"),
                "permission": admin_permission,
            },
            {
                "title": _("Ghost"),
                "icon": "circle",
                "link": reverse_lazy("staff_admin:BaseBillet_ghostconfig_changelist"),
                "permission": admin_permission,
            },
            {
                "title": _("Formbricks"),
                "icon": "list_alt",
                "link": reverse_lazy("staff_admin:BaseBillet_formbricksforms_changelist"),
                "permission": admin_permission,
            },
            {
                "title": _("Brevo"),
                "icon": "alternate_email",
                "link": reverse_lazy("staff_admin:BaseBillet_brevoconfig_changelist"),
                "permission": admin_permission,
            },
        ],
    })

    # --- Root seulement : Root Configuration ---
    navigation.append({
        "title": _("Root Configuration"),
        "separator": True,
        "collapsible": True,
        "items": [
            {
                "title": _("Waiting Configuration"),
                "icon": "linked_services",
                "link": reverse_lazy("staff_admin:MetaBillet_waitingconfiguration_changelist"),
                "permission": root_permission,
            },
            {
                "title": _("Tenants"),
                "icon": "domain",
                "link": reverse_lazy("staff_admin:Customers_client_changelist"),
                "permission": root_permission,
            },
        ],
    })

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
}


def _build_modules_context(configuration):
    """Construit la liste de modules pour le dashboard.
    Utilise par dashboard_callback et par le toggle HTMX."""
    modules = []
    for field_name, info in MODULE_FIELDS.items():
        is_caisse = field_name == "module_caisse"
        modules.append({
            "field": field_name,
            "name": info["name"],
            "description": info["description"],
            "testid": info["testid"],
            "active": getattr(configuration, field_name),
            "disabled": is_caisse and bool(configuration.server_cashless),
            "modal_url": reverse(
                'staff_admin:configuration-module-modal',
                args=[field_name],
            ),
            "link_url": info.get("link_url"),
            "link_label": info.get("link_label"),
            "link_icon": info.get("link_icon"),
        })
    return modules


def dashboard_callback(request, context):
    from BaseBillet.models import Configuration

    configuration = Configuration.get_solo()

    context.update({
        "modules": _build_modules_context(configuration),
    })

    return context
