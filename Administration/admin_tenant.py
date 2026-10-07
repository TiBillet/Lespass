from Administration.admin.dashboard import (  # noqa: F401
    dashboard_callback, environment_callback, get_sidebar_navigation,
    get_tabs, nom_du_lieu,
    MODULE_FIELDS, BETA_NOTICE, _build_modules_context, adhesion_badge_callback,
)


from Administration.admin.resources import (  # noqa: F401
    CalendarAdmin, WeeklyOpeningAdmin, BookingAdmin, ResourceGroupAdmin, ResourceAdmin
)
from Administration.admin import (
    products,
    prices
)
from Administration.admin.help_messages_dictionnary import HELP_MESSAGES_DICT
from Administration.admin.mixins import ExportCsvLisibleParExcelMixin, HelpDisplayMixin

from Administration.admin.site import staff_admin_site, sanitize_textfields

# IMPORT A EFFET DE BORD — NE PAS SUPPRIMER, MEME S'IL PARAIT INUTILISE.
# Importer ces modules EXECUTE leurs decorateurs @admin.register(...), qui enregistrent
# ProductAdmin, PriceAdmin et les admins laboutik / inventaire sur staff_admin_site.
# Sans cet import, ils ne sont jamais enregistres, et Django refuse de demarrer :
#   admin.E039 — An admin for model "Product" has to be registered to be referenced by
#   EventAdmin.autocomplete_fields
# La directive noqa F401 ci-dessous est INDISPENSABLE : sans elle, `ruff check --fix`
# supprime l'import (il le voit comme mort) et casse tout l'admin.
# / SIDE-EFFECT IMPORT — DO NOT REMOVE. It runs the @admin.register decorators that
# register ProductAdmin, PriceAdmin and the laboutik / inventaire admins. Without it
# Django refuses to boot (admin.E039).
# The noqa F401 directive below is REQUIRED, otherwise `ruff check --fix` deletes it.
from Administration.admin import (  # noqa: F401
    products,
    prices,
    laboutik,
    inventaire,
)

# Meme mecanisme pour l'app pages : le projet n'utilise pas l'autodiscover admin,
# il faut importer le module pour declencher les @admin.register.
# / Same side-effect mechanism for the pages app: the project does not use admin
# autodiscover, importing the module triggers the @admin.register calls.
import pages.admin  # noqa: F401

import hmac
import json
from functools import partial
import logging
import re
from datetime import timedelta
from decimal import Decimal
from typing import Any, Optional, Dict
from urllib.parse import urlencode
from uuid import UUID, uuid4
from unfold.utils import parse_datetime_str
from django.core.validators import EMPTY_VALUES
from django.urls import path, reverse, NoReverseMatch

from django.contrib import admin
from django.contrib.admin.options import ModelAdmin
from django.db.models import Model
from django.forms import ValidationError
from django.http import HttpRequest


import requests
import segno
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.signing import TimestampSigner
from django.db import models, connection, IntegrityError, transaction as db_transaction
from django.db.models import Count, Q, Prefetch, F, Exists, OuterRef, Subquery, Sum
from django.db import OperationalError
from django.forms import ModelForm, Form
from django.http import HttpResponse
from django.shortcuts import redirect, get_object_or_404, render
from django.template.defaultfilters import floatformat, slugify
from django.template.loader import render_to_string
from django.urls import re_path
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django_htmx.http import HttpResponseClientRedirect
from django_tenants.utils import tenant_context
from import_export.admin import ImportExportModelAdmin, ExportActionModelAdmin
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from rest_framework_api_key.models import APIKey
from solo.admin import SingletonModelAdmin
from django.core.cache import cache
from root_billet.models import RootConfiguration
# ModelAdmin vient de Administration/admin/base.py : c'est le ModelAdmin
# d'Unfold plus le placeholder de recherche tire de search_fields.
# / Project ModelAdmin: Unfold's, plus the search placeholder.
from Administration.admin.base import ModelAdmin
from unfold.admin import TabularInline
from unfold.components import register_component, BaseComponent
from unfold.contrib.filters.admin import (
    DropdownFilter,
    RelatedDropdownFilter,
    # AutocompleteSelectMultipleFilter,
    # ChoicesDropdownFilter,
    # MultipleRelatedDropdownFilter,
    # RangeDateFilter,
    RangeDateTimeFilter,
    # RangeNumericFilter,
    # SingleNumericFilter,
    # TextFilter,
)
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.contrib.import_export.forms import ExportForm, ImportForm
from unfold.decorators import display, action
from unfold.sections import TableSection, TemplateSection
from unfold.widgets import (
    UnfoldAdminEmailInputWidget,
    UnfoldAdminColorInputWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminTextInputWidget,
    UnfoldAdminSelect2Widget,
    UnfoldAdminDecimalFieldWidget,
)

from Administration.importers.ticket_exporter import TicketExportResource
from Administration.importers.lignearticle_exporter import LigneArticleExportResource
from ApiBillet.permissions import TenantAdminPermissionWithRequest, RootPermissionWithRequest
from ApiBillet.serializers import get_or_create_price_sold, dec_to_int
from AuthBillet.models import HumanUser, TibilletUser, Wallet
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Configuration, Product, Price, Paiement_stripe, Membership, Webhook, Tag, \
    LigneArticle, PaymentMethod, Reservation, ExternalApiKey, GhostConfig, Event, Ticket, PriceSold, SaleOrigin, \
    FormbricksConfig, FormbricksForms, FederatedPlace, PostalAddress, Carrousel, BrevoConfig, ScanApp, MembershipProduct, FederationConfiguration, ProductSold
from BaseBillet.tasks import webhook_reservation, \
    webhook_membership, create_ticket_pdf, ticket_celery_mailer, send_ticket_cancellation_user, \
    send_reservation_cancellation_user, forge_connexion_url, send_sale_to_laboutik
from BaseBillet.models_vente import Reglement, Vente
from BaseBillet.services_vente import (
    NOM_ECART_RECU_EN_MOINS,
    NOM_ECART_RECU_EN_PLUS,
    MOYENS_DU_CHAMP_REMBOURSE_PAR,
    EgaliteDeVenteRompue,
    MESSAGE_AVOIR_LIGNE_VENTE_AVEC_UN_ECART,
    ajouter_article,
    ajouter_reglement,
    apercu_des_montants_d_un_avoir,
    article_vendu_au_poids_ou_a_la_tireuse,
    choix_du_champ_rembourse_par,
    ecrire_la_vente_d_avoir_d_une_ligne,
    ecrire_la_vente_d_avoir_d_une_vente,
    encaisser_vente,
    encaisser_vente_stripe,
    ligne_entierement_offerte,
    ligne_sans_argent_a_rendre,
    monnaie_et_carte_des_jetons_de_la_vente,
    moyen_d_argent_unique_de_la_vente,
    moyen_d_origine_de_la_ligne,
    ouvrir_vente,
    vente_contient_une_recharge,
    vente_porte_un_ecart_d_encaissement,
)
from Customers.bascule_vers_v2 import raisons_qui_retiennent_le_lieu_courant
from Customers.models import (
    MODULES_V2_FERMES_AUX_LIEUX_LEGACY,
    Client,
    lieu_en_moteur_legacy,
)
from crowds.models import Contribution, Vote, Participation, CrowdConfig, Initiative, BudgetItem
from fedow_connect.fedow_api import FedowAPI
from fedow_connect.models import FedowConfig
from fedow_connect.utils import dround
from fedow_public.models import AssetFedowPublic as Asset, AssetFedowPublic
from laboutik.views import _taux_tva_de_la_ligne_de_caisse
from laboutik.affichage_des_ventes import (
    badge_de_la_nature_d_une_vente,
    nom_de_l_unite_de_la_vente,
    noms_des_monnaies_des_ventes,
    reglements_pour_l_affichage,
)
from laboutik.integrity import calculer_hmac_vente
from laboutik.models import LaboutikConfiguration
from comptabilite.presentation import (
    euros_a_la_francaise,
    montant_a_la_francaise_dans_l_unite,
    quantite_au_poids_a_la_francaise,
    quantite_lisible,
)
from comptabilite.rapport import nom_du_moyen_de_paiement, unite_d_une_vente_au_poids

# from simple_history.admin import SimpleHistoryAdmin

logger = logging.getLogger(__name__)


@admin.register(ExternalApiKey, site=staff_admin_site)
class ExternalApiKeyAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = [
        'name',
        'user',
        'created',
        'event',
        'product',
        'reservation',
        'ticket',
        'wallet',
        'sale',
        'page',
    ]

    fields = [
        'name',
        'ip',
        'created',
        # Les boutons de permissions :
        ('event', 'product',),
        ('reservation', 'ticket'),
        ('wallet', 'sale'),
        # membership : requis pour que LaBoutik lise les adhesions (route by-wallet).
        # / membership: required so LaBoutik can read memberships (by-wallet route).
        ('membership', 'crowd'),
        # Droit API du site web (app pages) / Website API right (pages app)
        ('page',),
        # Recharge cadeau : asset TNF que cette cle peut crediter via l'API v2
        # / Gift refill: TNF asset this key may top-up via API v2
        'gift_asset',
        'user',
        'key',
    ]

    readonly_fields = [
        'created',
        'user',
        'key',
    ]

    def save_model(self, request: HttpRequest, obj: ExternalApiKey, form: Form, change: Any) -> None:
        if not obj.pk and not obj.key and obj.name:

            # On affiche la string Key sur l'admin de django en message
            # et django.message capitalize chaque message...
            # du coup on fait bien gaffe à ce que je la clée générée ai bien une majusculle au début ...
            api_key, key = APIKey.objects.create_key(name=obj.name)
            while key[0].isupper() == False:
                api_key, key = APIKey.objects.create_key(name=obj.name)
                if key[0].isupper() == False:
                    api_key.delete()

            messages.add_message(
                request,
                messages.SUCCESS,
                _("Copy this key and save it somewhere safe! It will not be saved on our servers and can only be displayed this one time.")
            )
            messages.add_message(
                request,
                messages.WARNING,
                f"{key}"
            )
            obj.key = api_key
            obj.user = request.user
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Etancheite multi-tenant : pour le champ "gift_asset", on ne propose
        # QUE les assets rechargeables dont le tenant courant est l'origine
        # (c'est-a-dire ses propres assets). Sans cela, le menu deroulant
        # listait les assets de TOUS les lieux (AssetFedowPublic vit dans le
        # schema public, partage), et un lieu pouvait choisir l'asset cadeau
        # d'un autre lieu. On filtre aussi sur les categories rechargeables,
        # comme le fait limit_choices_to sur le modele.
        # / Multi-tenant isolation: on "gift_asset", only offer refillable
        # assets owned by the CURRENT tenant (its own assets). Otherwise the
        # dropdown listed every place's assets (AssetFedowPublic lives in the
        # shared public schema) and a place could pick another place's gift
        # asset. We also keep the refillable-category filter (like the model's
        # limit_choices_to).
        if db_field.name == "gift_asset":
            kwargs["queryset"] = AssetFedowPublic.objects.filter(
                origin=connection.tenant,
                category__in=AssetFedowPublic.REFILLABLE_CATEGORIES,
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # Pour le champ "gift_asset" (asset cadeau a recharger), on retire les
        # petites icones "ajouter / modifier / voir l'asset" affichees a cote
        # du menu deroulant. Ces raccourcis ouvrent l'admin des assets, qui
        # masque volontairement les assets de type badgeuse (BDG) : cliquer
        # dessus renvoyait une erreur "cet asset n'existe pas". Le simple choix
        # dans la liste suffit ici : on ne gere pas les assets depuis la cle API.
        # On surcharge formfield_for_dbfield (et non formfield_for_foreignkey)
        # car Django enveloppe le widget dans le RelatedFieldWidgetWrapper APRES
        # formfield_for_foreignkey : il faut donc agir une fois l'enveloppe posee.
        # / Remove the add/change/view related-object icons on "gift_asset".
        # They open the Asset admin, which hides BDG assets and raised a
        # "does not exist" error. We override formfield_for_dbfield (not
        # formfield_for_foreignkey) because Django wraps the widget in the
        # RelatedFieldWidgetWrapper AFTER formfield_for_foreignkey runs.
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "gift_asset" and formfield is not None:
            formfield.widget.can_add_related = False
            formfield.widget.can_change_related = False
            formfield.widget.can_delete_related = False
            formfield.widget.can_view_related = False
        return formfield

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(ScanApp, site=staff_admin_site)
class ScanAppAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_before_template = "admin/scanapp/list_before.html"

    list_display = [
        'name',
        'claimed',
        'archive',
    ]

    fields = [
        'name',
        'archive',
        'pairing_code',
    ]

    readonly_fields = [
        'pairing_code',
    ]

    def pairing_code(self, obj):
        if obj.pk and obj.name and not obj.claimed:
            base_url = f"https://{connection.tenant.get_primary_domain().domain}"

            signer = TimestampSigner()
            token = urlsafe_base64_encode(signer.sign(f"{obj.uuid}").encode('utf8'))
            qrcode_data = f"{base_url}/scan/{token}/pair"

            logger.info(qrcode_data)

            ### VERIFICATION SIGNATURE AVANT D'ENVOYER
            scanapp_uuid = signer.unsign(urlsafe_base64_decode(token).decode('utf8'), max_age=(300))  # 5 min
            sc = ScanApp.objects.get(uuid=scanapp_uuid)
            if not obj == sc:
                raise Exception("signature check error")

            # Generate QR code using segno
            qr = segno.make(qrcode_data)

            # Get SVG as string with white background
            svg_string = qr.svg_inline(scale=4, light="white")

            # Use mark_safe for the SVG content to prevent escaping
            return format_html(f'{mark_safe(svg_string)}')
        elif obj.pk and obj.name and obj.claimed:
            return "Claimed"
        return "Sauvegarder pour afficher le qr code de pairing. ( bouton Enregistrer et afficher )"

    pairing_code.short_description = _("Pairing Code")

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)



@admin.register(Webhook, site=staff_admin_site)
class WebhookAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    readonly_fields = ['last_response', ]
    fields = [
        "url",
        "event",
        "active",
        "last_response",
    ]

    list_display = [
        "url",
        "event",
        "active",
        "last_response",
    ]

    actions_detail = ["test_webhook"]

    @action(
        description=_("Test"),
        url_path="test_webhook",
        permissions=["custom_actions_detail"],
    )
    def test_webhook(self, request, object_id):
        # import ipdb; ipdb.set_trace()
        # Lancement d'un test de webhook :
        webhook = Webhook.objects.get(pk=object_id)
        try:
            if webhook.event == Webhook.MEMBERSHIP_V:
                # On va chercher le membership le plus récent
                membership = Membership.objects.filter(contribution_value__isnull=False).first()
                webhook_membership(membership.pk)
                webhook.refresh_from_db()
            elif webhook.event == Webhook.RESERVATION_V:
                # On va chercher le membership le plus récent
                reservation = Reservation.objects.filter(status=Reservation.VALID).first()
                webhook_reservation(reservation.pk)
                webhook.refresh_from_db()

            messages.info(
                request,
                f"{webhook.last_response}",
            )
            return redirect(request.META["HTTP_REFERER"])

        except Exception as e:
            messages.error(
                request,
                f"{e}",
            )

    def has_custom_actions_detail_permission(self, request, object_id):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(Configuration, site=staff_admin_site)
class ConfigurationAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    # Mis à None, parce que "SingletonModelAdmin" est une classe de django,
    # et que le template d'unfold n'est pas atteint si on ne fais rien. Permet de respecter les settings.py
    change_form_template = None

    # form = ConfigurationAdminForm

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('postal_address').prefetch_related(
            'federated_with',
            # 'option_generale_radio',
            # 'option_generale_checkbox'
        )

    # Les quatre sections deviennent quatre ONGLETS. Unfold ne transforme un
    # fieldset en onglet que s'il porte « classes: ["tab"] » ET UN NOM
    # (unfold/templatetags/unfold.py, filtre `tabs`) : la premiere section,
    # anonyme jusqu'ici, en recoit donc un. Sans nom elle se rendrait au-dessus
    # de la barre d'onglets, ce qui n'est pas ce qu'on veut.
    # / A fieldset becomes a tab only with classes:["tab"] AND a name; the
    #   first section was anonymous and now has one.
    #
    # AUCUN CHAMP N'EST AJOUTE NI RETIRE. 45 champs de Configuration restent
    # invisibles (cles d'API, modules, champs legaux) : les exposer est une
    # decision distincte, deliberement hors de ce lot. Ce changement est
    # PUREMENT une mise en forme.
    # / No field added or removed: this is purely a layout change.
    fieldsets = (
        (_("Identité du lieu"), {
            'classes': ["tab"],
            'fields': (
                'organisation',
                'short_description',
                'long_description',
                'img',
                'logo',
                'postal_address',
                # 'adress',
                'phone',
                'email',
                'site_web',
                # 'skin' deplace vers pages.ConfigurationSite (admin « Site web »).
                # / 'skin' moved to pages.ConfigurationSite (« Site web » admin).
            )
        }),
        (_("Réglages"), {
            'classes': ["tab"],
            'fields': (
                'fuseau_horaire',
                'heure_de_fermeture',
                'language',
                'jauge_max',
                'allow_concurrent_bookings',
                'currency_code',
            ),
        }),
        (_("Personnalisation"), {
            'classes': ["tab"],
            'fields': (
                'event_menu_name',
                'membership_menu_name',
                'description_membership_page',
                'description_event_page',
                'first_input_label_membership',
                'second_input_label_membership',
                'additional_text_in_membership_mail',
            ),
        }),
        (_("Paiement (Stripe)"), {
            'classes': ["tab"],
            'fields': (
                # 'vat_taxe',
                'onboard_stripe',
                'stripe_invoice',
                'stripe_accept_sepa',
            ),
        }),
        # ('Danger !', {
        #     'fields': (
        #         'domain_name',  # Virtual field to set slug
        #     ),
        # }),
    )

    readonly_fields = ['onboard_stripe', ]
    # « federated_with » n'est dans AUCUN fieldset : cet autocomplete ne
    # s'appliquait a rien. On le retire plutot que de le laisser mentir sur
    # ce que fait la page. Le jour ou le champ sera expose, il se remettra.
    # / The field is in no fieldset, so this autocomplete applied to nothing.
    # autocomplete_fields = ['federated_with', ]

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'module-toggle-modal/<str:field_name>/',
                self.admin_site.admin_view(self.module_toggle_modal),
                name='configuration-module-modal',
            ),
            path(
                'module-toggle/<str:field_name>/',
                self.admin_site.admin_view(csrf_protect(require_POST(self.module_toggle))),
                name='configuration-module-toggle',
            ),
        ]
        return custom_urls + urls

    def module_toggle_modal(self, request, field_name):
        """HTMX GET : renvoie le modal de confirmation pour activer/desactiver un module."""
        if field_name not in MODULE_FIELDS:
            return HttpResponse("", status=400)

        configuration = Configuration.get_solo()
        is_active = getattr(configuration, field_name)
        module_info = MODULE_FIELDS[field_name]
        module_name = str(module_info["name"])
        # Module en acces anticipe : la modal affiche l'encart BETA et le bouton
        # de confirmation devient « J'ai compris et je teste ! ».
        # / Early-access module: modal shows the BETA notice and a dedicated button.
        is_beta = module_info.get("beta", False)

        toggle_url = reverse(
            'staff_admin:configuration-module-toggle',
            args=[field_name],
        )

        # Verrou de moteur (spec 15 §5.8) : un lieu legacy qui veut ALLUMER un module V2.
        # - des raisons le retiennent : la fenetre les liste, sans bouton de confirmation ;
        # - aucune raison : la fenetre annonce le passage au nouveau moteur.
        # Eteindre un module : fenetre inchangee.
        # / Engine lock: reasons listed without a confirm button, or the switch announced.
        raisons_qui_retiennent_le_lieu = []
        passage_au_moteur_v2_annonce = False
        allumage_d_un_module_v2_par_un_lieu_legacy = (
            field_name in MODULES_V2_FERMES_AUX_LIEUX_LEGACY
            and not is_active
            and lieu_en_moteur_legacy()
        )
        if allumage_d_un_module_v2_par_un_lieu_legacy:
            raisons_qui_retiennent_le_lieu = raisons_qui_retiennent_le_lieu_courant()
            passage_au_moteur_v2_annonce = not raisons_qui_retiennent_le_lieu

        html = render_to_string(
            'admin/dashboard_module_modal.html',
            {
                "module_name": module_name,
                "is_active": is_active,
                "is_beta": is_beta,
                "beta_notice": BETA_NOTICE,
                "toggle_url": toggle_url,
                "csrf_token": request.META.get("CSRF_COOKIE", ""),
                "raisons_qui_retiennent_le_lieu": raisons_qui_retiennent_le_lieu,
                "passage_au_moteur_v2_annonce": passage_au_moteur_v2_annonce,
            },
            request=request,
        )
        return HttpResponse(html)

    def module_toggle(self, request, field_name):
        """
        HTMX POST : bascule un module et recharge la page (`HX-Refresh`).
        / HTMX POST: toggles a module and reloads the page.

        LOCALISATION : Administration/admin_tenant.py

        Verrou de moteur (spec 15 §5.1, §5.8). Un lieu legacy (ancien Fedow) qui ALLUME
        un module V2 (caisse, monnaie locale, kiosk, tireuse) :
        - si quelque chose le retient sur l'ancien Fedow : refus avant toute ecriture,
          le message cite les raisons ;
        - sinon : il passe au moteur V2 (bascule en un clic), puis le module s'allume.
          La bascule et l'enregistrement du module sont dans UNE transaction : un echec
          de l'enregistrement annule aussi la bascule.
        Eteindre un module, ou toucher un module qui n'est pas V2 : jamais de bascule.
        Un lieu v2 : aucun verrou.
        / Engine lock: a legacy venue held by a reason is refused; otherwise it moves to
        V2, then the module switches on, in one transaction.
        """
        if field_name not in MODULE_FIELDS:
            return HttpResponse("", status=400)

        configuration = Configuration.get_solo()
        current_value = getattr(configuration, field_name)

        # Verrou de moteur : un lieu legacy qui allume un module V2 doit d'abord passer
        # au moteur V2. Le refus arrive avant toute ecriture : l'interrupteur cache ne
        # suffit pas, un POST direct arrive ici.
        # / Engine lock: a legacy venue switching ON a V2 module must move to V2 first.
        allumage_demande = not current_value
        bascule_vers_v2_demandee = (
            field_name in MODULES_V2_FERMES_AUX_LIEUX_LEGACY
            and allumage_demande
            and lieu_en_moteur_legacy()
        )
        if bascule_vers_v2_demandee:
            raisons_qui_retiennent_le_lieu = raisons_qui_retiennent_le_lieu_courant()
            if raisons_qui_retiennent_le_lieu:
                phrases_du_message = [
                    str(_("Ce module n'est pas encore disponible pour votre lieu :"))
                ]
                for raison in raisons_qui_retiennent_le_lieu:
                    phrases_du_message.append(str(raison))
                phrases_du_message.append(
                    str(_("Contactez l'équipe TiBillet pour lui indiquer que vous souhaitez faire une migration."))
                )
                messages.add_message(request, messages.ERROR, " ".join(phrases_du_message))
                response = HttpResponse("")
                response["HX-Refresh"] = "true"
                return response

        setattr(configuration, field_name, not current_value)
        new_value = getattr(configuration, field_name)

        if field_name == "module_monnaie_locale" and not new_value and configuration.module_caisse:
            messages.add_message(request, messages.ERROR, _("The \"POS & restaurant\" module required this module. You must disable it before disabling "))
            setattr(configuration, field_name, current_value)

        # La caisse V2 exige la monnaie locale (pas de caisse sans cashless).
        # On l'active automatiquement plutot que de bloquer l'activation,
        # pour une mise en route BETA en un seul clic.
        # / The V2 cash register requires local currency; auto-enable it instead
        # / of blocking, for a one-click BETA activation.
        if field_name == "module_caisse" and new_value and not configuration.module_monnaie_locale:
            configuration.module_monnaie_locale = True
            messages.add_message(request, messages.INFO, _("\"Local currency & cashless\" was enabled automatically (required by the POS)."))


        configuration.clean()

        # Configuration.save() peut lever ValidationError (ex: SEPA pas actif cote Stripe).
        # Sans ce try/except, l'exception remonte en 500 silencieux cote HTMX.
        # On capture comme ConfigurationAdmin.save_model() le fait deja plus bas.
        # / Configuration.save() may raise ValidationError (e.g. SEPA not active on Stripe).
        #
        # CONTRAINTES (spec 15 §5.8) :
        # - La transaction n'entoure `save()` QUE pendant une bascule. `save()` enregistre
        #   la ligne PUIS leve l'erreur du SEPA : sans bascule, cet enregistrement partiel
        #   est voulu (le module reste allume, le SEPA eteint, un message le dit). Une
        #   transaction autour de chaque `save()` l'annulerait.
        # - Pendant une bascule, la transaction annule tout : le moteur ET la ligne.
        #   Mais `save()` a deja ecrit le cache du singleton (django-solo) : on le vide,
        #   sinon le prochain `get_solo()` rendrait le module allume que la base n'a pas.
        # - Toute autre erreur remet le moteur legacy sur `connection.tenant`, puis remonte.
        # - Le `filter(moteur_monnaie=LEGACY)` rend la bascule unique : un double clic
        #   envoie deux POST ; le second ne trouve plus de ligne legacy, il ne journalise
        #   rien.
        # / Transaction only while switching; on failure clear the singleton cache and
        # / reset the tenant; the LEGACY filter makes the switch happen once.
        lieu_courant = connection.tenant
        if bascule_vers_v2_demandee:
            nombre_de_lieux_bascules = 0
            try:
                with db_transaction.atomic():
                    nombre_de_lieux_bascules = Client.objects.filter(
                        pk=lieu_courant.pk,
                        moteur_monnaie=Client.MOTEUR_LEGACY,
                    ).update(moteur_monnaie=Client.MOTEUR_V2)
                    lieu_courant.moteur_monnaie = Client.MOTEUR_V2
                    configuration.save()
            except ValidationError as e:
                lieu_courant.moteur_monnaie = Client.MOTEUR_LEGACY
                Configuration.clear_cache()
                error_message = e.message if hasattr(e, "message") else str(e)
                messages.error(request, error_message)
            except Exception:
                lieu_courant.moteur_monnaie = Client.MOTEUR_LEGACY
                Configuration.clear_cache()
                raise
            else:
                if nombre_de_lieux_bascules == 1:
                    logger.info(
                        f"Bascule en un clic : le lieu {lieu_courant.schema_name} "
                        f"passe au moteur V2 en allumant {field_name}"
                    )
        else:
            try:
                configuration.save()
            except ValidationError as e:
                error_message = e.message if hasattr(e, "message") else str(e)
                messages.error(request, error_message)

        # HX-Refresh force un reload complet : la sidebar se met a jour
        # et les messages d'erreur eventuels apparaissent en toast.
        # / HX-Refresh forces a full reload: sidebar updates and any error
        # / messages show up as toast notifications.
        response = HttpResponse("")
        response["HX-Refresh"] = "true"
        return response

    def save_model(self, request, obj, form, change):
        obj: Configuration
        # Sanitize all TextField inputs to avoid XSS via WYSIWYG/TextField
        sanitize_textfields(obj)

        if obj.server_cashless and obj.key_cashless:
            if obj.check_serveur_cashless():
                messages.add_message(request, messages.INFO, _("Cashless server ONLINE"))
            else:
                messages.add_message(request, messages.ERROR, _("Cashless server OFFLINE or BAD KEY"))

        try:
            super().save_model(request, obj, form, change)
        except ValidationError as e:
            # Le ValidationError vient de Configuration.save() (ex: SEPA pas activé dans Stripe)
            # On le transforme en message d'erreur admin au lieu d'un 500
            # / ValidationError from Configuration.save() (e.g. SEPA not active in Stripe)
            # / Convert to admin error message instead of 500
            messages.error(request, e.message)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False


class TagForm(ModelForm):
    class Meta:
        model = Tag
        fields = '__all__'
        widgets = {
            'color': UnfoldAdminColorInputWidget(),
        }


@admin.register(Carrousel, site=staff_admin_site)
class CarrouselAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    ordering = ('order', 'name')
    list_display = ('name', 'on_event_list_page', 'order', 'link', 'events_names')
    list_editable = ('on_event_list_page', 'order')

    search_fields = ('name',)

    @display(description=_("Included in events"))
    def events_names(self, instance: Carrousel):
        return ", ".join([event.name for event in instance.events.all()])

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(Tag, site=staff_admin_site)
class TagAdmin(ModelAdmin):
    compressed_fields = True  # Default: False 
    warn_unsaved_form = True  # Default: False

    actions_list = ["sync_tags_action"]

    form = TagForm
    fields = ("name", "color")
    list_display = [
        "name",
        "_color",
    ]
    readonly_fields = ['uuid', ]
    search_fields = ['name']

    def _color(self, obj):
        # Add link to change page around color div
        return format_html(
            '<a href="{url}">'
            '<div style="width: 20px; height: 20px; background-color: {color}; border: 1px solid #000;"></div>'
            '</a>',
            url=reverse('staff_admin:BaseBillet_tag_change', args=[obj.pk]),
            color=obj.color,
        )

    _color.short_description = _("Color")

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_sync_tags_action_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    @action(
        description=_("Synchronize tags"),
        url_path="sync_tags",
        permissions=["sync_tags_action"],
    )
    def sync_tags_action(self, request):
        current_tenant = connection.tenant

        # 1. Identifier les parents (ceux qui nous fédèrent)
        # On utilise une requête SQL optimisée pour éviter 600 changements de contexte
        from django.db import connection as db_connection
        cursor = db_connection.cursor()

        # On récupère les schémas possédant la table FederatedPlace
        cursor.execute("SELECT table_schema FROM information_schema.tables WHERE table_name = 'BaseBillet_federatedplace'")
        schemas_with_fed = {row[0] for row in cursor.fetchall()}

        # On exclut le public, le nôtre et les schémas système
        schemas_to_check = [s for s in schemas_with_fed if s not in ['public', 'information_schema', 'pg_catalog', current_tenant.schema_name]]

        parents_pks = []
        if schemas_to_check:
            batch_size = 50
            for i in range(0, len(schemas_to_check), batch_size):
                batch = schemas_to_check[i:i + batch_size]
                query_parts = []
                params = []
                for schema in batch:
                    query_parts.append(f'SELECT %s WHERE EXISTS (SELECT 1 FROM "{schema}"."BaseBillet_federatedplace" WHERE tenant_id = %s)')
                    params.extend([schema, current_tenant.pk])

                if query_parts:
                    full_query = " UNION ALL ".join(query_parts)
                    cursor.execute(full_query, params)
                    for row in cursor.fetchall():
                        parents_pks.append(row[0])

        parents = list(Client.objects.filter(schema_name__in=parents_pks))

        # 2. Identifier les enfants (ceux que nous fédérons)
        children = [fp.tenant for fp in FederatedPlace.objects.all().select_related('tenant')]

        # Combiner et dédupliquer en gardant l'ordre (parents d'abord)
        seen = {current_tenant.pk}
        tenants_to_sync = []
        for t in parents + children:
            if t.pk not in seen:
                tenants_to_sync.append(t)
                seen.add(t.pk)

        # 3. Collecter tous les tags distants en une seule fois
        all_remote_tags = {}
        if tenants_to_sync:
            # On vérifie quels schémas ont la table Tag
            cursor.execute("SELECT table_schema FROM information_schema.tables WHERE table_name = 'BaseBillet_tag'")
            schemas_with_tags = {row[0] for row in cursor.fetchall()}

            schemas_to_fetch = [t.schema_name for t in tenants_to_sync if t.schema_name in schemas_with_tags]

            if schemas_to_fetch:
                batch_size = 50
                for i in range(0, len(schemas_to_fetch), batch_size):
                    batch = schemas_to_fetch[i:i + batch_size]
                    query_parts = []
                    for schema in batch:
                        query_parts.append(f'SELECT name, color FROM "{schema}"."BaseBillet_tag"')

                    full_query = " UNION ALL ".join(query_parts)
                    cursor.execute(full_query)
                    for name, color in cursor.fetchall():
                        # Le dernier rencontré gagne (priorité aux enfants sur les parents si conflit)
                        all_remote_tags[name] = color

        # 4. Appliquer les changements localement en masse
        local_tags = {t.name: t for t in Tag.objects.all()}
        tags_created = 0
        tags_updated = 0

        to_create = []
        to_update = []

        for name, color in all_remote_tags.items():
            cleaned_color = Tag._clean_hex(color, "#0dcaf0")
            if name in local_tags:
                tag = local_tags[name]
                if tag.color != cleaned_color:
                    tag.color = cleaned_color
                    to_update.append(tag)
            else:
                to_create.append(Tag(
                    uuid=uuid4(),
                    name=name,
                    slug=slugify(name),
                    color=cleaned_color
                ))

        if to_create:
            Tag.objects.bulk_create(to_create)
            tags_created = len(to_create)

        if to_update:
            Tag.objects.bulk_update(to_update, ['color'])
            tags_updated = len(to_update)

        messages.success(request, _("Synchronization complete: {} tags created, {} tags updated.").format(tags_created, tags_updated))
        return redirect(request.META.get("HTTP_REFERER", reverse("staff_admin:BaseBillet_tag_changelist")))

"""

@admin.register(OptionGenerale, site=staff_admin_site)
class OptionGeneraleAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    search_fields = ('name',)
    list_display = (
        'name',
        'poids',
    )

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
"""


@admin.register(Paiement_stripe, site=staff_admin_site)
class PaiementStripeAdmin(ModelAdmin):
    compressed_fields = True  # Default: False

    list_display = (
        'user',
        'order_date',
        'status',
        # 'traitement_en_cours',
        'source_traitement',
        'source',
        'articles',
        'total',
        'uuid_8',
    )
    readonly_fields = list_display
    ordering = ('-order_date',)
    search_fields = ('user__email', 'order_date')
    list_filter = ('status', 'order_date',)

    def has_delete_permission(self, request, obj=None):
        # return request.user.is_superuser
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True


"""
USER
"""


class is_tenant_admin_filter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _("Administrator")

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "client_admin"

    def lookups(self, request, model_admin):
        return [("Y", _("Yes")), ("N", _("No"))]

    def queryset(self, request, queryset):
        if self.value() == "Y":
            return queryset.filter(
                client_admin__in=[connection.tenant],
                espece=TibilletUser.TYPE_HUM
            ).distinct()
        if self.value() == "N":
            return queryset.exclude(
                client_admin__in=[connection.tenant],
            ).distinct()


class can_init_paiement_filter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _("Can initiate payments")

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "initiate_payment"

    def lookups(self, request, model_admin):
        return [("Y", _("Yes")), ("N", _("No"))]

    def queryset(self, request, queryset):
        if self.value() == "Y":
            return queryset.filter(
                initiate_payment__in=[connection.tenant],
                espece=TibilletUser.TYPE_HUM
            ).distinct()
        if self.value() == "N":
            return queryset.exclude(
                initiate_payment__in=[connection.tenant],
            ).distinct()


class UserWithMembershipValid(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _("Valid subscription")

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "membership_valid"

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return [
            ("Y", _("Yes")),
            ("N", _("No")),
            ("B", _("Expires soon (2 weeks)")),
        ]

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value (either '80s' or '90s')
        # to decide how to filter the queryset.
        if self.value() == "Y":
            return queryset.filter(
                memberships__deadline__gte=timezone.localtime(),
            ).distinct()
        if self.value() == "N":
            return queryset.exclude(
                memberships__deadline__gte=timezone.localtime()
            ).distinct()
        if self.value() == "B":
            return queryset.filter(
                memberships__deadline__lte=timezone.localtime() + timedelta(weeks=2),
                memberships__deadline__gte=timezone.localtime(),
            ).distinct()


# ---------------------------------------------------------------------------
# Badges de statut pour la fiche utilisateur (évènements + adhésions).
# Styles inline (hex) : le bundle Unfold n'inclut pas toutes les classes Tailwind ;
# un fond saturé + texte blanc reste lisible en thème clair comme sombre.
# Helpers AU NIVEAU MODULE (hors classe) — Unfold wrappe les méthodes des ModelAdmin.
# / Status badges for the user profile. Inline hex styles, readable in light/dark.
# Module-level helpers (NOT inside the admin class) — Unfold wraps ModelAdmin methods.
# ---------------------------------------------------------------------------
BADGE_VERT = ("#16a34a", "#ffffff")    # validé / payé
BADGE_BLEU = ("#2563eb", "#ffffff")    # gratuit / en ligne
BADGE_AMBRE = ("#d97706", "#ffffff")   # en attente / non payé
BADGE_ROUGE = ("#dc2626", "#ffffff")   # annulé
BADGE_GRIS = ("#6b7280", "#ffffff")    # autre


def _badge_couleur_reservation(status_code):
    """Couleur (fond, texte) du badge selon le statut de réservation.
    / Badge color (bg, fg) for a booking status."""
    if status_code in (Reservation.VALID, Reservation.PAID,
                       Reservation.PAID_NOMAIL, Reservation.PAID_ERROR):
        return BADGE_VERT
    if status_code in (Reservation.FREERES, Reservation.FREERES_USERACTIV):
        return BADGE_BLEU
    if status_code in (Reservation.CREATED, Reservation.UNPAID):
        return BADGE_AMBRE
    if status_code == Reservation.CANCELED:
        return BADGE_ROUGE
    return BADGE_GRIS


def _badge_couleur_adhesion(est_valide, status_code):
    """Couleur (fond, texte) du badge selon l'état d'adhésion.
    / Badge color (bg, fg) for a membership state."""
    if est_valide:
        return BADGE_VERT
    if status_code in (Membership.CANCELED, Membership.ADMIN_CANCELED):
        return BADGE_ROUGE
    return BADGE_GRIS


def _admin_url_basebillet(model_name, pk):
    """URL admin de modification d'un objet BaseBillet, ou None si introuvable.
    / Admin change URL for a BaseBillet object, or None if not found."""
    try:
        return reverse(f"staff_admin:BaseBillet_{model_name}_change", args=[pk])
    except NoReverseMatch:
        return None


# Statuts de ligne comptés dans le montant payé (cf Reservation.articles_paid) :
# remboursements et avoirs y entrent en négatif.
# / Line statuses counted in the paid amount: refunds and credit notes count negatively.
LIGNE_PAYEE_STATUTS = (LigneArticle.PAID, LigneArticle.VALID, LigneArticle.REFUNDED, LigneArticle.CREDIT_NOTE)


def _lignes_payees_prefetch(reservation):
    """Lignes payées/confirmées/remboursées d'une réservation, en exploitant les
    relations préchargées (prefetch_related) : zéro requête par réservation.
    Réplique la logique de Reservation.articles_paid() mais en mémoire — la méthode
    du modèle, elle, fait un .filter() (donc une requête) à chaque appel.
    / Prefetch-aware version of Reservation.articles_paid() — no per-row query.
    """
    # Lignes liées directement à la réservation (données récentes)
    # / Lines linked directly to the reservation (recent data)
    lignes_directes = [
        ligne for ligne in reservation.lignearticles.all()
        if ligne.status in LIGNE_PAYEE_STATUTS
    ]
    if lignes_directes:
        return lignes_directes

    # Fallback : anciennes lignes liées via le paiement Stripe
    # / Fallback: legacy lines linked via the Stripe payment
    lignes_legacy = []
    for paiement in reservation.paiements.all():
        lignes_legacy += [
            ligne for ligne in paiement.lignearticles.all()
            if ligne.status in LIGNE_PAYEE_STATUTS
        ]
    return lignes_legacy


# Tout les utilisateurs de type HUMAIN
@admin.register(HumanUser, site=staff_admin_site)
class HumanUserAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = False  # Default: False

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.prefetch_related('memberships', 'client_admin')

    change_form_after_template = "admin/human_user/right_and_wallet_info.html"

    list_display = [
        'email',
        'first_name',
        'last_name',
        'display_memberships_valid',
    ]

    search_fields = [
        # Nom / prénom / email portés par l'user lui-même
        # / Name / first name / email carried by the user itself
        'email',
        'first_name',
        'last_name',
        # Nom / prénom saisis sur les adhésions de l'user (souvent l'adhérent·e
        # réel·le, parfois différent de l'user). Django ajoute distinct() au besoin.
        # / Name / first name entered on the user's memberships (the actual member,
        # sometimes different from the account user). Django adds distinct() if needed.
        'memberships__first_name',
        'memberships__last_name',
    ]

    fieldsets = (
        ('Général', {
            'fields': (
                'email',
                ('first_name', 'last_name'),
                "email_valid",
            )
        }),
    )

    readonly_fields = [
        "email",
        "email_valid",
        "administre",
    ]

    list_filter = [
        "is_active",
        UserWithMembershipValid,
        is_tenant_admin_filter,
        can_init_paiement_filter,
        "email_valid",
    ]

    def changeform_view(self, request: HttpRequest, object_id: Optional[str] = None, form_url: str = "",
                        extra_context: Optional[Dict[str, bool]] = None) -> Any:
        extra_context = extra_context or {}
        extra_context['object_id'] = object_id
        if object_id:
            # Bloc 1 — états initiaux des toggles de droits.
            # Conserve le comportement existant : re-lève une erreur inattendue.
            # / Rights toggles initial states. Keeps existing behaviour (re-raises).
            try:
                user = TibilletUser.objects.get(pk=object_id)
                tenant = connection.tenant
                extra_context['is_client_admin'] = user.client_admin.filter(pk=tenant.pk).exists()
                extra_context['can_initiate_payment'] = user.initiate_payment.filter(pk=tenant.pk).exists()
                extra_context['can_create_event'] = user.create_event.filter(pk=tenant.pk).exists()
                extra_context['can_manage_crowd'] = user.manage_crowd.filter(pk=tenant.pk).exists()
            except HumanUser.DoesNotExist:
                extra_context['is_client_admin'] = False
                extra_context['can_initiate_payment'] = False
                extra_context['can_create_event'] = False
                extra_context['can_manage_crowd'] = False
            except ValidationError:
                # Requete POST pour les actions (object_id pas un uuid) : on ignore.
                # / POST for actions (object_id not a uuid): ignore.
                pass
            except Exception as e:
                raise e

            # Bloc 2 — évènements + adhésions (tenant courant), préparés en listes de
            # dictionnaires. ISOLÉ dans son propre try/except : un cas de données
            # limite ne doit JAMAIS faire planter (500) la fiche utilisateur — on
            # logge et on affiche la page sans (ou avec moins d') encarts.
            # / Bookings + memberships. Isolated try/except: an edge case must never
            # 500 the user change page; we log and render the page anyway.
            try:
                user = TibilletUser.objects.get(pk=object_id)
                extra_context['devise'] = Configuration.get_solo().currency_code
                maintenant = timezone.now()

                # Prefetch des relations : nombre de requêtes constant (pas de N+1).
                # Tri NULLS LAST : les réservations sans évènement ne remontent pas en tête.
                # / Prefetch relations (no N+1); NULLS LAST so event-less bookings stay last.
                reservations = (
                    Reservation.objects
                    .filter(user_commande=user)
                    .select_related('event')
                    .prefetch_related(
                        'tickets',
                        'lignearticles__vente__reglements',
                        'lignearticles__vente__ventes_derivees__reglements',
                        'paiements__lignearticles__vente__reglements',
                        'paiements__lignearticles__vente__ventes_derivees__reglements',
                    )
                    .order_by(F('event__datetime').desc(nulls_last=True))
                )
                evenements_a_venir = []
                evenements_passes = []
                for reservation in reservations:
                    badge_fond, badge_texte = _badge_couleur_reservation(reservation.status)
                    # Lignes payées calculées UNE seule fois sur les relations préchargées.
                    # / Paid lines computed once from prefetched relations.
                    lignes_payees = _lignes_payees_prefetch(reservation)

                    # Montant payé : la somme des nets vendus (`total_ttc`) des lignes,
                    # avoirs et remboursements compris (négatifs). Moyens : les moyens
                    # nets des ventes de ces lignes, corrections comprises, sans l'offert,
                    # sans doublon, dans l'ordre des moyens.
                    # / Paid amount: sum of the lines' net sold. Methods: the net methods
                    # of the lines' sales, corrections included, offered left out.
                    montant_paye_en_centimes = 0
                    moyens_de_paiement = []
                    for ligne_payee in lignes_payees:
                        montant_paye_en_centimes += ligne_payee.total_ttc
                        for nom_du_moyen in ligne_payee.moyens_de_paiement_de_sa_vente():
                            if nom_du_moyen not in moyens_de_paiement:
                                moyens_de_paiement.append(nom_du_moyen)
                    montant_paye = dround(montant_paye_en_centimes)
                    date_evenement = reservation.event.datetime if reservation.event else None
                    if date_evenement and date_evenement >= maintenant:
                        liste_cible = evenements_a_venir
                    else:
                        liste_cible = evenements_passes
                    liste_cible.append({
                        'nom': reservation.event.name if reservation.event else _("(évènement supprimé)"),
                        'date': date_evenement,
                        'nb_billets': len(reservation.tickets.all()),
                        'montant': montant_paye,
                        'moyens': ", ".join(moyens_de_paiement),
                        'statut': reservation.get_status_display(),
                        'badge_fond': badge_fond,
                        'badge_texte': badge_texte,
                        'url': _admin_url_basebillet('reservation', reservation.pk),
                    })
                extra_context['evenements_a_venir'] = evenements_a_venir
                extra_context['evenements_passes'] = evenements_passes

                adhesions = (
                    Membership.objects
                    .filter(user=user)
                    .select_related('price', 'price__product')
                    .order_by('-deadline')
                )
                adhesions_en_cours = []
                adhesions_passees = []
                for adhesion in adhesions:
                    est_valide = adhesion.is_valid()
                    badge_fond, badge_texte = _badge_couleur_adhesion(est_valide, adhesion.status)
                    if est_valide:
                        liste_cible = adhesions_en_cours
                    else:
                        liste_cible = adhesions_passees
                    liste_cible.append({
                        'produit': adhesion.product_name() or "—",
                        'tarif': adhesion.price_name() or "",
                        'montant': adhesion.contribution_value,
                        # Unite du montant : vide pour de l'argent (devise du lieu),
                        # nom de la monnaie pour une adhesion payee en points
                        # / Amount unit: empty for money, currency name for points
                        'unite': (
                            adhesion.unite_de_la_contribution()
                            if adhesion.payment_method == PaymentMethod.NON_MONETAIRE
                            else ""
                        ),
                        'moyen': adhesion.get_payment_method_display() if adhesion.payment_method else "",
                        'deadline': adhesion.deadline,
                        'statut': _("En cours") if est_valide else adhesion.get_status_display(),
                        'badge_fond': badge_fond,
                        'badge_texte': badge_texte,
                        'url': _admin_url_basebillet('membership', adhesion.pk),
                    })
                extra_context['adhesions_en_cours'] = adhesions_en_cours
                extra_context['adhesions_passees'] = adhesions_passees
            except Exception as erreur_encarts:
                logger.error(
                    f"HumanUserAdmin : encarts évènements/adhésions indisponibles "
                    f"pour {object_id} : {erreur_encarts}"
                )

        return super().changeform_view(request, object_id, form_url, extra_context)

    # noinspection PyTypeChecker
    @display(description=_("Subscriptions"), label={None: "danger", True: "success"})
    def display_memberships_valid(self, instance: HumanUser):
        count = instance.memberships_valid()
        if count > 0:
            # Lien cliquable vers la liste des adhésions filtrée par l'email
            url = "/admin/BaseBillet/membership/"
            query = urlencode({"q": instance.email})
            return True, format_html('<a href="{}?{}">{}</a>', url, query, _(f"Valid: {count}"))
        return None, _("None")

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False  # Autoriser l'ajout

    def has_custom_actions_detail_permission(self, request, object_id):
        perm = TenantAdminPermissionWithRequest(request)
        logger.info(request.user, perm)
        return perm

    actions_row = ["login_as_user", ]

    def has_custom_actions_row_permission(self, request, obj=None):
        return RootPermissionWithRequest(request)

    @action(
        description=_("Login as this user"),
        permissions=["custom_actions_row"],
    )
    def login_as_user(self, request, object_id):
        if not RootPermissionWithRequest(request):
            messages.error(request, _("You do not have permission to perform this action."))
            return redirect(request.META.get("HTTP_REFERER", "/admin/"))

        user = get_object_or_404(HumanUser, pk=object_id)
        tenant = connection.tenant
        try:
            domain = tenant.get_primary_domain().domain
            base_url = f"https://{domain}"
        except Exception:
            base_url = "https://tibillet.coop"

        connexion_url = forge_connexion_url(user, base_url)
        return redirect(connexion_url)


### ADHESION

from Administration.importers.membership_importers import (
    MembershipExportResource,
    MembershipImportResource
)


# from Administration.importers.event_importers import PostalAddressForeignKeyWidget
class MembershipAddForm(ModelForm):
    '''
    Formulaire d'ajout d'adhésion sur l'interface d'administration.
    '''

    # Un formulaire d'email qui va générer les action get_or_create_user
    email = forms.EmailField(
        required=True,
        widget=UnfoldAdminEmailInputWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label="Email",
    )

    # Uniquement les tarif Adhésion
    # / Only membership prices
    price = forms.ModelChoiceField(
        queryset=Price.objects.filter(
            product__categorie_article=Product.ADHESION, product__archive=False, archived=False
        ).select_related('product', 'fedow_reward_asset').order_by("-free_price","name"),
        # Remplis le champ select avec les objets Price
        # / Fills the select with Price objects
        empty_label=_("Select an subscription"),  # Texte affiché par défaut
        required=True,
        widget=UnfoldAdminSelectWidget(),
        label=_("Subscriptions"),
        help_text=_("Si un déclencheur de tokens est configuré sur le tarif, il sera activé à l'enregistrement du paiement. Une ligne comptable sera aussi créée dans les Ventes."),
    )

    # Fabrication au cas ou = 0
    contribution = forms.FloatField(
        required=False,
        widget=UnfoldAdminTextInputWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label=_("Contribution (€)"),
    )

    payment_method = forms.ChoiceField(
        required=False,
        choices=PaymentMethod.classic(),  # on retire les choix stripe
        widget=UnfoldAdminSelectWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label=_("Payment method"),
    )

    card_number = forms.CharField(
        required=False,
        min_length=8,
        max_length=8,
        label=_("Card number"),
        # validators=[validate_hex8],
        widget=UnfoldAdminTextInputWidget(),
    )

    class Meta:
        model = Membership
        fields = [
            'last_name',
            'first_name',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Affiche l'info du déclencheur tokens dans le label du select
        # / Shows token trigger info in the select label
        def _label_price_avec_declencheur(price_obj):
            label = str(price_obj)
            if price_obj.fedow_reward_enabled and price_obj.fedow_reward_asset and price_obj.fedow_reward_amount:
                label += f" ⚡ +{price_obj.fedow_reward_amount} {price_obj.fedow_reward_asset.name}"
            return label

        self.fields['price'].label_from_instance = _label_price_avec_declencheur

    def clean_email(self):
        cleaned_data = self.cleaned_data
        email = cleaned_data.get('email')
        user = get_or_create_user(email, send_mail=False)
        self.fedowAPI = FedowAPI()
        self.fedowAPI.wallet.get_or_create_wallet(user)
        self.user_wallet_serialized = self.fedowAPI.wallet.cached_retrieve_by_signature(user).validated_data
        return email

    def clean_card_number(self):
        cleaned_data = self.cleaned_data
        card_number = cleaned_data.get('card_number')
        if card_number:

            # Si clean_email a echoue, le wallet n'existe pas encore — on ne peut pas valider la carte
            # If clean_email failed, the wallet doesn't exist yet — we can't validate the card
            if not hasattr(self, 'user_wallet_serialized'):
                raise forms.ValidationError(_("Please provide a valid email address first."))

            if self.user_wallet_serialized.get('has_user_card'):
                raise forms.ValidationError(_("A card is already linked to this email address."))

            if not re.match(r'^[0-9A-Fa-f]{8}$', card_number):
                raise forms.ValidationError(_("Card number must be exactly 8 hexadecimal characters."))

            fedowApi = FedowAPI()
            card_serialized = fedowApi.NFCcard.card_number_retrieve(card_number)

            if not card_serialized:
                raise forms.ValidationError(_("Unknown card number"))
            if not card_serialized.get('is_wallet_ephemere'):
                raise forms.ValidationError(_("This card is already linked to a user."))

            self.card_serialized = card_serialized
        self.card_number = card_number
        return card_number

    def clean(self):
        # On vérifie que le moyen de paiement est bien entré si > 0
        cleaned_data = self.cleaned_data
        if cleaned_data.get("contribution"):
            if cleaned_data.get("contribution") > 0 and cleaned_data.get("payment_method") == PaymentMethod.FREE:
                raise forms.ValidationError(_("Please add a payment method for the contribution."),
                                            code="invalid")

            # Une contribution sans moyen de paiement est refusée : la vente de
            # l'adhésion écrit un règlement au moyen choisi, il en faut un.
            # / A contribution without payment method is refused: the sale writes a
            #   payment at the chosen method.
            if cleaned_data.get("contribution") > 0 and not cleaned_data.get("payment_method"):
                raise forms.ValidationError(
                    _("Choisissez un moyen de paiement pour la contribution."),
                    code="invalid",
                )

        if cleaned_data.get("payment_method") != PaymentMethod.FREE:
            if not cleaned_data.get("contribution"):
                raise forms.ValidationError(_("Please fill in the value of the contribution."), code="invalid")
            if not cleaned_data.get("contribution") > 0:
                raise forms.ValidationError(_("Please fill in a positive value of the contribution."), code="invalid")

        return super().clean()

    def save(self, commit=True):
        self.instance: Membership
        # On indique que l'adhésion a été créé sur l'admin
        self.instance.status = Membership.ADMIN

        # Associez l'utilisateur au champ 'user' du formulaire
        email = self.cleaned_data.pop('email')
        user = get_or_create_user(email)

        self.instance.user = user

        # Numéro de carte saisi (8 hexa) -> enregistré sur l'adhésion
        # card_number = self.cleaned_data.get('card_number')
        # if card_number:
        #     self.instance.card_number = card_number

        # Flotant (FALC) vers Decimal
        contribution = self.cleaned_data.pop('contribution')
        self.instance.contribution_value = dround(Decimal(contribution)) if contribution else 0

        # Mise à jour des dates de contribution :
        self.instance.first_contribution = timezone.localtime()
        self.instance.last_contribution = timezone.localtime()
        # self.instance.set_deadline()

        if self.card_number:
            # Ne lier la carte chez Fedow QU'APRES le commit de la transaction.
            # L'admin Django appelle form.save() AVANT de valider les inlines :
            # si un formset est invalide, la transaction DB est annulee mais un
            # appel HTTP deja parti vers Fedow ne peut pas l'etre — la carte
            # serait liee chez Fedow sans adhesion cote Lespass.
            # (Bug trouve par tests/pytest/test_membership_card_wallet_fedow.py)
            # / Only link the card on Fedow AFTER the DB transaction commits.
            # Django admin calls form.save() BEFORE validating inlines: on an
            # invalid formset the DB transaction rolls back, but an HTTP call
            # already sent to Fedow cannot — the card would be linked on Fedow
            # with no membership on the Lespass side.
            utilisateur_a_lier = user
            numero_carte_a_lier = self.card_number
            fedow_api = self.fedowAPI
            db_transaction.on_commit(
                lambda: fedow_api.NFCcard.linkwallet_card_number(
                    user=utilisateur_a_lier,
                    card_number=numero_carte_a_lier,
                )
            )

        # Le post save BaseBillet.signals.create_lignearticle_if_membership_created_on_admin s'executera
        # # Création de la ligne Article vendu qui envera à la caisse si besoin
        return super().save(commit=commit)


class MembershipChangeForm(ModelForm):
    # Le formulaire pour changer une adhésion
    class Meta:
        model = Membership
        fields = (
            'last_name',
            'first_name',
            'deadline',
            'commentaire',
            'newsletter',
        )



class MembershipStatusFilter(admin.SimpleListFilter):
    title = _("Statut d'adhésion (par défaut filtré)")
    parameter_name = "membership_status"

    def lookups(self, request, model_admin):
        return [
            ("valid", _("Valids")),
            ("wa", _("Attente de validation")),
            ("wp", _("Attente de paiement")),
            ("canceled", _("Canceled")),
            ("all", _("Sans distinction")),
        ]

    def queryset(self, request, queryset):
        value = self.value()

        # Filtrage par défaut
        if value is None:
            return queryset.exclude(status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED])

        if value == "valid":
            # On masque les annulées
            return queryset.exclude(
                Q(status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED]) |
                Q(deadline__lt=timezone.localtime()))

        if value == "wa":
            return queryset.filter(status=Membership.ADMIN_WAITING)

        if value == "wp":
            # PAYMENT_PENDING : paiement soumis mais débit pas encore confirmé (SEPA).
            # / PAYMENT_PENDING: payment submitted but debit not confirmed yet (SEPA).
            return queryset.filter(status__in=[
                Membership.WAITING_PAYMENT,
                Membership.ADMIN_VALID,
                Membership.PAYMENT_PENDING,
            ])

        if value == "canceled":
            return queryset.filter(status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED])

        if value == "all":
            return queryset
        return queryset


@register_component
class MembershipComponent(BaseComponent):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Les adhésions en cours :
        active_count = Membership.objects.filter(deadline__gte=timezone.localtime()).exclude(
            status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED]).count()
        # Les user qui n'ont pas d'adhésion en cours :
        inactive_count = HumanUser.objects.exclude(
            memberships__deadline__gte=timezone.localtime(),
            memberships__status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED],
        ).distinct().count()

        pending_count = Membership.objects.filter(status=Membership.ADMIN_WAITING).count()

        context["children"] = render_to_string(
            "admin/membership/membership_component.html",
            {
                "type": kwargs.get('type'),
                "active": active_count,
                "inactive": inactive_count,
                "pending": pending_count,
            },
        )
        return context


class MembershipCustomFormSection(TemplateSection):
    template_name = "admin/membership/custom_form_section.html"
    verbose_name = _("Custom form answers")


class LigneArticleInline(TabularInline):
    model = LigneArticle
    fk_name = "membership"
    extra = 0
    # Pas de lien vers une fiche : les lignes n'ont plus de page dans l'admin. Les
    # avoirs se font depuis la fiche « Vente ».
    # / No link: lines have no admin page any more; credit notes go through the sale.
    show_change_link = False
    # Pas de titre au-dessus de chaque ligne (option Unfold `hide_title`) : les
    # colonnes disent déjà tout ce qu'un titre répéterait.
    # / No title above each row (Unfold `hide_title`): the columns already say it.
    hide_title = True
    can_delete = False
    verbose_name = _("Ventes / Ligne comptables")
    verbose_name_plural = _("Ventes / Ligne comptables")

    fields = (
        "datetime",
        "amount_decimal",
        "qty_decimal",
        "vat",
        "total_decimal",
        "display_status",
        "moyens_de_paiement",
        "sale_origin",
    )
    readonly_fields = fields

    def get_queryset(self, request):
        # La vente de chaque ligne, ses règlements et ceux de ses corrections sont
        # préchargés : la colonne « Moyen de paiement » ne fait pas une requête par
        # ligne.
        # / Each line's sale, its payments and its corrections' payments are
        # prefetched: no query per line.
        queryset = super().get_queryset(request)
        return queryset.select_related('vente').prefetch_related(
            'vente__reglements',
            'vente__ventes_derivees__reglements',
        )

    @display(description=_("Value"))
    def amount_decimal(self, obj):
        # Une pesée affiche le prix du kg ou du litre (« 12,90 €/kg », Q-H4).
        # / A weighing shows the price per kg or litre.
        if _unite_d_une_pesee(obj) is not None:
            return _prix_unitaire_d_une_ligne(obj, euros_a_la_francaise(obj.amount))
        return obj.amount_decimal()

    @display(description=_("Quantité"))
    def qty_decimal(self, obj):
        return _quantite_d_une_ligne(obj)

    @display(description=_("TVA"))
    def vat(self, obj):
        return obj.vat

    @display(description=_("Total"))
    def total_decimal(self, obj):
        return obj.total_decimal()

    @display(description=_("Moyen de paiement"))
    def moyens_de_paiement(self, obj):
        # Les moyens nets de la vente de la ligne, corrections comprises, sans
        # l'offert. « — » quand il n'y en a aucun : ligne sans vente, ou vente
        # entièrement offerte.
        # / The net methods of the line's sale; "—" when there is none.
        return ", ".join(obj.moyens_de_paiement_de_sa_vente()) or "—"

    @display(description=_("Statut"), label={None: "danger", True: "success"})
    def display_status(self, instance: LigneArticle):
        return instance.get_status_display()

    def has_view_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class MembershipPublishedFilter(DropdownFilter):
    """
    Filtre les adhésions par produit d'adhésion non archivé.
    / Filter for filtering Membership by MembershipProduct that are not archived

    LOCALISATION : Administration/admin_tenant.py

    DropdownFilter (Unfold) affiche une liste déroulante avec un champ de recherche.
    Un SimpleListFilter classique affiche tous les produits les uns sous les autres :
    illisible dès qu'il y a beaucoup de produits.
    Le filtre est un champ de formulaire, envoyé par le bouton « Filtrer »
    (list_filter_submit = True, posé sur le ModelAdmin de base du projet).
    / Unfold DropdownFilter: searchable dropdown instead of a long list of links.
    Sent by the "Filter" button (list_filter_submit, set on the project base ModelAdmin).
    """
    title = _('Product')
    parameter_name = 'price' # Get the product from the price

    def lookups(self, request, model_admin):
        # Return only product that are not archived to display in the filter
        return [
            (product.pk, product.name)
            for product in MembershipProduct.objects.filter(archive=False).order_by("name")
        ]

    def queryset(self, request, queryset):
        if self.value():
            # Return only membership where the product correspond to the selected product
            return queryset.filter(price__product=self.value())
        return queryset



@admin.register(Membership, site=staff_admin_site)
class MembershipAdmin(ExportCsvLisibleParExcelMixin, HelpDisplayMixin, ModelAdmin, ImportExportModelAdmin):

    inlines = [LigneArticleInline]
    # Expandable section to display custom form answers in changelist
    list_sections = [MembershipCustomFormSection]
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    exclude = ["commande"]

    # Ajoute un bloc personnalisé après le formulaire dans la vue change
    change_form_after_template = "admin/membership/custom_form.html"

    resource_classes = [MembershipExportResource, MembershipImportResource]
    export_form_class = ExportForm
    import_form_class = ImportForm

    list_before_template = "admin/membership/membership_list_before.html"  # appelle le MembershipComponent plus haut pour le contexte

    # Help info for HelpModelAdmin
    list_help_text = HELP_MESSAGES_DICT["ADHESION"]["list_help_text"]
    list_help_url = HELP_MESSAGES_DICT["ADHESION"]["list_help_url"]

    changeform_help_text = HELP_MESSAGES_DICT["ADHESION"]["changeform_help_text"]
    changeform_help_url = HELP_MESSAGES_DICT["ADHESION"]["changeform_help_url"]

    # Formulaire de modification
    form = MembershipChangeForm
    # Formulaire de création. A besoin de get_form pour fonctionner
    add_form = MembershipAddForm

    list_display = (
        'email',
        'date_added',
        'first_name',
        'last_name',
        'price',
        'contribution_value',
        # 'options',
        'display_last_contribution',
        'display_deadline',
        'display_is_valid',
        'status',
        'recurrence',
        # 'state',
        # 'payment_method',
        # 'state_display',
        # 'commentaire',
    )

    ordering = ('-date_added',)
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'card_number', 'last_contribution',
                     'custom_form')
    list_filter = [MembershipStatusFilter, MembershipPublishedFilter, 'last_contribution', 'deadline', ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return (
            qs.select_related('user', 'price', 'price__product')
            .prefetch_related('price__product__form_fields')
        )

    def get_export_formats(self):
        """
        Met le format Excel (XLSX) en premier dans le menu d'export.
        / Put the Excel (XLSX) format first in the export dropdown.

        LOCALISATION : Administration/admin_tenant.py (MembershipAdmin)

        Pourquoi : un fichier CSV s'ouvre mal dans Excel en langue francaise.
        Excel attend le point-virgule comme separateur de colonnes, mais le
        CSV utilise la virgule. Du coup toutes les colonnes (email, nom...)
        se retrouvent dans une seule cellule et on ne peut pas recuperer
        facilement la liste des mails.
        Le format Excel (XLSX) n'a pas ce probleme : il s'ouvre toujours en
        colonnes propres. On le remonte donc en tete de la liste pour que les
        utilisateur-ices le voient et le choisissent en premier.
        / A CSV opens badly in French Excel (comma vs semicolon separator),
        / so XLSX is moved to the top of the export format list.
        """
        # On recupere la liste des formats fournie par django-import-export
        # / Get the export formats provided by django-import-export
        formats_disponibles = super().get_export_formats()

        # On separe le format Excel (XLSX) des autres formats
        # / Split the Excel (XLSX) format from the others
        formats_excel = []
        autres_formats = []
        for format_export in formats_disponibles:
            if format_export().get_extension() == "xlsx":
                formats_excel.append(format_export)
            else:
                autres_formats.append(format_export)

        # XLSX en premier, puis les autres formats dans leur ordre d'origine
        # / XLSX first, then the other formats in their original order
        return formats_excel + autres_formats

    @display(description=_("User"))
    def user_email_link(self, obj):
        if obj.user:
            url = reverse("staff_admin:AuthBillet_humanuser_change", args=[obj.user.pk])
            return format_html(
                '<a href="{}" class="font-medium text-primary-600 underline decoration-primary-500 decoration-2 underline-offset-4 hover:text-primary-800 dark:text-primary-500 dark:decoration-primary-600 dark:hover:text-primary-400">{}</a>',
                url,
                obj.user.email
            )
        return "-"

    @display(description=_("Produit / Tarif"))
    def price_product_display(self, obj: Membership):
        return f"{obj.price.product.name} / {obj.price.name}"

    @display(description=_("Statut de l'adhésion"))
    def display_status_membership(self, obj: Membership):
        # Badge couleur selon l'état : vert = valide, rouge = annulé, gris = autre
        # (dont "Paiement soumis, en attente"). En lecture seule : le statut est
        # piloté par la machine à états du paiement, il ne se modifie jamais a la main.
        # / Colored badge by state: green = valid, red = cancelled, grey = other.
        # Read-only: the status is driven by the payment state machine, never edited by hand.
        badge_fond, badge_texte = _badge_couleur_adhesion(obj.is_valid(), obj.status)
        return format_html(
            '<span style="background-color:{}; color:{}; padding:2px 10px; '
            'border-radius:9999px; font-size:.85em;">{}</span>',
            badge_fond, badge_texte, obj.get_status_display(),
        )

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super().get_readonly_fields(request, obj)
        if obj:  # On est en train de modifier
            return list(readonly_fields) + [
                'display_status_membership', 'user_email_link', 'price_product_display',
            ]
        return readonly_fields

    # def get_fields(self, request, obj=None):
    #     fields = super().get_fields(request, obj)
    #     if obj:
    #         # Si on est en modif, on s'assure que user_email_link est présent et au début
    #         if 'user_email_link' or 'price_product_display' not in fields:
    #             fields = ['user_email_link', 'price_product_display'] + list(fields)
    #     return fields

    ### FORMULAIRES
    # autocomplete_fields = ['option_generale', ]

    def get_form(self, request, obj=None, **kwargs):
        """ Si c'est un add, on modifie un peu le formulaire pour avoir un champs email """
        defaults = {}
        if obj is None:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    def get_changeform_initial_data(self, request):
        """Prefill the add form with values provided in the query string.

        Supports simple fields and ManyToMany 'option_generale' via repeated
        query params (e.g. ?option_generale=1&option_generale=2).
        """
        initial = super().get_changeform_initial_data(request)
        params = request.GET

        # Simple scalar params that map to form fields
        for key in [
            'email',
            'price',
            'contribution',
            'payment_method',
            'first_name',
            'last_name',
            # 'card_number',
        ]:
            value = params.get(key)
            if value not in [None, ""]:
                initial[key] = value

        # ManyToMany: option_generale (allow multiple ids)
        # option_ids = params.getlist('option_generale')
        # if option_ids:
            # Keep as list of IDs (ModelMultipleChoiceField accepts IDs as initial)
            # initial['option_generale'] = option_ids

        return initial

    # Panneau d'actions HTMX affiché AVANT le formulaire dans la vue change
    # / HTMX action panel displayed BEFORE the form in the change view
    change_form_before_template = "admin/membership/actions_panel.html"

    def changeform_view(self, request: HttpRequest, object_id: Optional[str] = None, form_url: str = "",
                        extra_context: Optional[Dict[str, bool]] = None):
        extra_context = extra_context or {}
        extra_context["show_validation_buttons"] = False

        if object_id:
            try:
                membership = Membership.objects.select_related('user', 'price', 'price__product').get(pk=object_id)
                extra_context['membership'] = membership
                if membership.status == Membership.ADMIN_WAITING:
                    extra_context["show_validation_buttons"] = True

                # Lien de paiement copiable pour les adhésions validées manuellement (état AV)
                # Même URL que celle envoyée par email — la vue gère l'idempotence (pas de double paiement)
                # / Copyable payment link for manually validated memberships (state AV)
                # Same URL as sent by email — the view handles idempotency (no double payment)
                if membership.status in [Membership.ADMIN_VALID, Membership.ADMIN_WAITING]:
                    try:
                        domaine_tenant = connection.tenant.get_primary_domain().domain
                        extra_context['lien_paiement'] = f"https://{domaine_tenant}/memberships/{membership.uuid}/get_checkout_for_membership"
                    except Exception:
                        pass

                # Statuts qui permettent l'ajout d'un paiement hors-ligne (pour conditionnel template)
                # / Statuses that allow offline payment (for template conditional)
                extra_context['statuts_attente_paiement'] = [
                    Membership.WAITING_PAYMENT,
                    Membership.ADMIN_WAITING,
                    Membership.ADMIN_VALID,
                ]

            except Membership.DoesNotExist:
                extra_context["show_validation_buttons"] = False

        return super().changeform_view(request, object_id, form_url, extra_context)

    @display(description=_("Payment"), ordering="last_contribution")
    def display_last_contribution(self, instance: Membership):
        if instance.last_contribution:
            return instance.last_contribution.strftime("%d/%m/%Y")
        return "-"

    @display(description=_("End"), ordering="deadline")
    def display_deadline(self, instance: Membership):
        if instance.deadline:
            return instance.deadline.strftime("%d/%m/%Y")
        return "-"

    @display(description=_("Valid"), boolean=True)
    def display_is_valid(self, instance: Membership):
        return instance.is_valid()

    @display(description=_("Recurence"), ordering="current_iteration")
    def recurrence(self, instance: Membership):
        if instance.max_iteration and instance.current_iteration:
            return f"{instance.current_iteration}/{instance.max_iteration}"
        elif instance.current_iteration:
            return f"{instance.current_iteration}"
        elif instance.stripe_id_subscription:
            return "∞"
        return ""

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        # return request.user.is_superuser
        return False


### VENTES ###

class RangeDateTimeFilterWithTimeZone(RangeDateTimeFilter):
    """
    This just override the 'RangeDateTimeFilter' 'queryset' method to take the timezone into account
    """
    def queryset(self, request, queryset):
        filters = {}

        # Get the timezone from the tenant config
        config = Configuration.get_solo()
        new_timezone = config.get_tzinfo()

        date_value_from = self.used_parameters.get(f"{self.parameter_name}_from_0")
        time_value_from = self.used_parameters.get(f"{self.parameter_name}_from_1")

        date_value_to = self.used_parameters.get(f"{self.parameter_name}_to_0")
        time_value_to = self.used_parameters.get(f"{self.parameter_name}_to_1")

        if date_value_from not in EMPTY_VALUES and time_value_from not in EMPTY_VALUES:
            # Add the timezone to the datetime for the filter to work correctly
            value_from = parse_datetime_str(f"{date_value_from} {time_value_from}").replace(tzinfo=new_timezone)

            filters.update(
                {
                    f"{self.parameter_name}__gte": value_from,
                }
            )

        if date_value_to not in EMPTY_VALUES and time_value_to not in EMPTY_VALUES:
            # Add the timezone to the datetime for the filter to work correctly
            value_to = parse_datetime_str(f"{date_value_to} {time_value_to}").replace(tzinfo=new_timezone)

            filters.update(
                {
                    f"{self.parameter_name}__lte": value_to
                }
            )
        try:
            return queryset.filter(**filters)
        except (ValueError, ValidationError):
            return None


class EmettreAvoirAvecMoyenForm(forms.Form):
    """
    Formulaire d'un avoir quand de l'argent est rendu hors Stripe : l'admin dit comment
    l'argent a été rendu. Champ obligatoire.
    / Credit note form when money is given back outside Stripe: how it was given back.

    LOCALISATION : Administration/admin_tenant.py (utilisé par VenteAdmin.avoir_total
    et par l'écran « Annuler et rembourser », `afficher_ou_valider_l_ecran_d_annulation`)
    """

    moyen_rembourse = forms.ChoiceField(
        label=_("Remboursé par"),
        choices=choix_du_champ_rembourse_par,
        required=True,
        help_text=_("Le moyen par lequel l'argent est rendu au client."),
        widget=UnfoldAdminSelectWidget(attrs={"data-testid": "avoir-moyen-rembourse"}),
    )


class EmettreAvoirSansMoyenForm(forms.Form):
    """
    Formulaire d'un avoir sans champ : simple confirmation. Sert quand aucun argent
    n'est rendu à la main : paiement Stripe (on rembourse depuis Stripe), article offert,
    ou payé en jetons.
    / Field-less form: plain confirmation (Stripe, offered or token-paid).

    LOCALISATION : Administration/admin_tenant.py (utilisé par VenteAdmin.avoir_total
    et par l'écran « Annuler et rembourser », `afficher_ou_valider_l_ecran_d_annulation`)
    """


class AvoirSurUnArticleForm(forms.Form):
    """
    Formulaire de l'écran « Avoir sur un article » de la fiche « Vente » : la quantité
    rendue, et « Remboursé par » quand de l'argent est rendu à la main.
    / "Credit note on one item" form: the quantity given back, and "Refunded by" when
    money is given back by hand.

    LOCALISATION : Administration/admin_tenant.py (utilisé par VenteAdmin.avoir_sur_un_article)

    - `champ_rembourse_par_demande=False` : le champ « Remboursé par » est retiré
      (article payé par Stripe, entièrement offert, ou entièrement en jetons) ;
    - `quantite_figee=True` : la quantité est en lecture seule (pesée ou tirage, Q-H5).
      Ce n'est qu'un affichage : une quantité forgée est refusée par le service
      (`ecrire_la_vente_d_avoir_d_une_ligne`), jamais remplacée en silence.
    / Without the "Refunded by" field when no money is given back by hand; read-only
    quantity for a weighing or a pour (display only: the service refuses a forged one).
    """

    quantite = forms.DecimalField(
        label=_("Quantité rendue"),
        max_digits=12,
        decimal_places=6,
        help_text=_("Au plus la quantité qui reste à rendre."),
        widget=UnfoldAdminDecimalFieldWidget(attrs={"data-testid": "avoir-quantite"}),
    )
    moyen_rembourse = forms.ChoiceField(
        label=_("Remboursé par"),
        choices=choix_du_champ_rembourse_par,
        required=True,
        help_text=_("Le moyen par lequel l'argent est rendu au client."),
        widget=UnfoldAdminSelectWidget(attrs={"data-testid": "avoir-moyen-rembourse"}),
    )

    def __init__(self, *args, champ_rembourse_par_demande=True, quantite_figee=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not champ_rembourse_par_demande:
            del self.fields["moyen_rembourse"]
        if quantite_figee:
            self.fields["quantite"].widget.attrs["readonly"] = True


# ==========================================================================
# LA FICHE « VENTE » — liste et fiche des ventes, en lecture seule
# / THE "SALE" PAGE — sales list and detail, read-only
# ==========================================================================
#
# LOCALISATION : Administration/admin_tenant.py
#
# Chaque `Vente` du lieu, toutes origines (caisse, en ligne, admin, tireuse…). Une
# vente réglée est scellée par son empreinte : l'admin ne permet ni ajout, ni
# modification, ni suppression. Les montants sont ceux écrits à la vente (centimes
# entiers), jamais recalculés. Les libellés des moyens et des natures sont ceux de la
# caisse (laboutik/affichage_des_ventes.py).
# / Every sale of the venue, read-only; frozen amounts; register labels.
#
# Les helpers d'affichage sont au NIVEAU DU MODULE : Unfold enveloppe les méthodes
# d'un ModelAdmin (skill unfold §23).
# / Display helpers live at module level: Unfold wraps ModelAdmin methods.

# Les ventes « en attente » depuis plus longtemps que ce délai sont à vérifier : un
# encaissement en ligne en échec (le client a payé, la vente n'est pas réglée).
# / Sales pending for longer than this are to be checked (failed online settlement).
DELAI_AU_DELA_DUQUEL_UNE_VENTE_EN_ATTENTE_EST_A_VERIFIER = timedelta(hours=1)


def _unite_d_une_vente(vente):
    """
    L'unité des montants d'une vente : "" pour l'euro, sinon le nom de sa monnaie de
    points. Sans requête : un nom de monnaie introuvable s'écrit par un nom générique.
    / A sale's amount unit, without any query.
    """
    return nom_de_l_unite_de_la_vente(vente, {})


def _montant_d_une_vente(montant_en_centimes, vente):
    """Un montant de la vente, à la française, dans son unité. / A sale amount."""
    return montant_a_la_francaise_dans_l_unite(montant_en_centimes, _unite_d_une_vente(vente))


def _unite_d_une_pesee(ligne):
    """
    L'unité de la quantité d'une vente au poids ou au volume (D15), de la caisse ou de
    la tireuse : « kg » ou « L » (`unite_d_une_vente_au_poids`, qui lit le stock et le
    type du produit : un fût est toujours en litres), ou None pour un article à la
    pièce. Le produit n'est lu que pour une ligne qui porte un poids : aucune requête
    de plus pour un article à la pièce.
    / The quantity unit of a weight / volume line, register or tap ("kg" or "L"; a keg
    is always in litres), or None.
    """
    ligne_au_poids_ou_au_volume = bool(ligne.weight_quantity)
    if not ligne_au_poids_ou_au_volume:
        return None
    produit = ligne.pricesold.productsold.product
    stock_du_produit = getattr(produit, "stock_inventaire", None)
    unite_du_stock = None
    if stock_du_produit is not None:
        unite_du_stock = stock_du_produit.unite
    return unite_d_une_vente_au_poids(unite_du_stock, produit.categorie_article)


def _quantite_d_une_ligne(ligne):
    """
    La quantité d'une ligne, pour l'admin, à la française : « 0,355 kg » ou « 0,33 L »
    pour une pesée (Q-H4) ; sinon 3 décimales au plus, sans zéros inutiles (« 3 »,
    « 1,571 » pour une part d'historique de 1,571429).
    / A line's quantity for the admin, French style: "0,355 kg" for a weighing,
    otherwise at most 3 decimals without useless zeros.
    """
    unite_de_la_pesee = _unite_d_une_pesee(ligne)
    if unite_de_la_pesee is None:
        quantite_a_trois_decimales = Decimal(ligne.qty).quantize(Decimal("0.001"))
        return quantite_lisible(str(quantite_a_trois_decimales))
    return quantite_au_poids_a_la_francaise(ligne.qty, unite_de_la_pesee)


def _prix_unitaire_d_une_ligne(ligne, montant_a_la_francaise):
    """
    Le prix unitaire d'une ligne, pour l'admin : « 12,90 €/kg » pour une pesée (le prix
    du kg ou du litre), le montant tel quel sinon.
    / A line's unit price for the admin: "12,90 €/kg" for a weighing.

    :param montant_a_la_francaise: le prix unitaire déjà écrit à la française
    """
    unite_de_la_pesee = _unite_d_une_pesee(ligne)
    if unite_de_la_pesee is None:
        return montant_a_la_francaise
    return f"{montant_a_la_francaise}/{unite_de_la_pesee}"


def _badge_unfold(couleur_du_badge, texte_du_badge):
    """
    Un badge Unfold (« success », « warning », « danger », « info »), rendu par le
    gabarit des badges d'Unfold (`unfold/helpers/label.html`).
    / An Unfold badge, rendered by Unfold's label template.

    LOCALISATION : Administration/admin_tenant.py

    Le HTML est rendu ici, et pas par `@display(label=...)` : Unfold ne dessine ce
    badge que dans la LISTE. Sur la FICHE, un champ en lecture seule afficherait le
    tuple brut `('VENTE', 'Vente')`. Rendu ici, le même badge vaut pour les deux.
    / Rendered here: `@display(label=...)` only works in the list; on the detail page
    a read-only field would show the raw tuple.

    :param couleur_du_badge: « success », « warning », « danger » ou « info »
    :param texte_du_badge: le texte du badge (déjà traduit)
    :return: HTML sûr (SafeString)
    """
    return render_to_string(
        "unfold/helpers/label.html",
        {"type": couleur_du_badge, "text": texte_du_badge},
    )


def _lien_vers_la_fiche_d_une_vente(vente):
    """
    Un lien vers la fiche d'une vente : « Vente n° 12 », ou « Vente en attente » sans
    numéro.
    / A link to a sale's detail page.
    """
    adresse_de_la_fiche = reverse("staff_admin:BaseBillet_vente_change", args=[vente.pk])
    if vente.numero is None:
        texte_du_lien = f"{vente.get_nature_display()} — {vente.get_statut_display()}"
    else:
        texte_du_lien = f"{vente.get_nature_display()} n° {vente.numero}"
    return format_html(
        '<a href="{}" data-testid="vente-lien" style="color: var(--color-primary-600); text-decoration: underline;">{}</a>',
        adresse_de_la_fiche,
        texte_du_lien,
    )


def _adresse_stripe_d_un_reglement(reglement):
    """
    L'adresse d'un règlement dans le tableau de bord Stripe, ou None :
    - un remboursement Stripe (référence externe `re_…`) : la page du remboursement ;
    - un règlement relié à un paiement Stripe qui a son identifiant de paiement
      (`payment_intent_id`) : la page du paiement.
    / A payment's address in the Stripe dashboard (refund page or payment page), or None.
    """
    reference_externe = reglement.reference_externe or ""
    if reference_externe.startswith("re_"):
        return f"https://dashboard.stripe.com/refunds/{reference_externe}"
    if reglement.paiement_stripe_id is not None:
        identifiant_du_paiement = reglement.paiement_stripe.payment_intent_id
        if identifiant_du_paiement:
            return f"https://dashboard.stripe.com/payments/{identifiant_du_paiement}"
    return None


def _lignes_de_la_vente_avec_un_reste_a_rendre(vente):
    """
    Les lignes vendues de la vente (quantité positive) dont une quantité reste à rendre :
    la quantité vendue, moins celle de leurs avoirs et remboursements. Chaque ligne rendue
    porte ce reste dans `quantite_restante`. Lecture simple, pour l'écran : le service
    relit sous verrou au moment d'écrire (`quantite_restante_de_la_ligne_sous_verrou`).
    / The sale's sold lines with a quantity left to give back, each carrying it in
    `quantite_restante` (plain read, for the screen; the service reads again under lock).
    """
    lignes_avec_un_reste = []
    lignes_vendues = (
        LigneArticle.objects.filter(vente=vente, qty__gt=0)
        .select_related("paiement_stripe", "vente")
        .prefetch_related("credit_notes")
    )
    for ligne_vendue in lignes_vendues:
        quantite_restante = ligne_vendue.qty
        for ligne_qui_rend_une_partie in ligne_vendue.credit_notes.all():
            quantite_restante += ligne_qui_rend_une_partie.qty
        if quantite_restante > 0:
            # Le reste est gardé sur l'objet, pour l'écran « Avoir sur un article ».
            # / The remainder is kept on the object, for the item credit note screen.
            ligne_vendue.quantite_restante = quantite_restante
            lignes_avec_un_reste.append(ligne_vendue)
    return lignes_avec_un_reste


def _raison_du_refus_de_l_avoir_total(vente):
    """
    Pourquoi « Avoir total » est refusé sur cette vente, ou None s'il est permis :
    nature autre que VENTE, vente pas réglée, vente qui n'est pas en euros, vente avec
    un écart d'encaissement, vente avec une recharge de carte, vente déjà remboursée en
    totalité. Une vente couverte par une clôture J n'est PAS refusée : l'avoir est une
    nouvelle opération, comptée dans le service en cours.
    Le service refuse les mêmes ventes (`ecrire_la_vente_d_avoir_d_une_vente`) : cette
    lecture sert à refuser AVANT d'afficher l'écran.
    / Why the full credit note is refused, or None. The service refuses the same sales.
    """
    if vente.nature != Vente.Nature.VENTE:
        return _("Seule une vente de nature « Vente » reçoit un avoir total.")
    if vente.statut != Vente.Statut.REGLEE:
        return _("La vente n'est pas réglée : l'avoir est impossible.")
    if vente.unite != "EUR":
        return _(
            "Cette vente n'est pas en euros (points ou temps) : l'avoir total n'est "
            "pas possible."
        )
    if vente_porte_un_ecart_d_encaissement(vente):
        return _("Cette vente a un écart d'encaissement : aucun avoir n'est possible.")
    if vente_contient_une_recharge(vente):
        return _(
            "Cette vente contient une recharge de carte : l'avoir total n'est pas "
            "possible."
        )
    if not _lignes_de_la_vente_avec_un_reste_a_rendre(vente):
        return _("La vente est déjà remboursée en totalité : rien n'est à rendre.")
    return None


def _sommes_rendues_par_l_avoir_total(vente):
    """
    Ce que « Avoir total » rendrait, par catégorie, SANS rien écrire : la même lecture
    que le service (quantités restantes, montants de `apercu_des_montants_d_un_avoir`).
    Lecture simple, pour l'écran : le service relit sous verrou au moment d'écrire.
    / What the full credit note would give back, by category, without writing.

    Les catégories (centimes, positifs) : `stripe` (à rembourser depuis Stripe),
    `rembourse_par` (l'argent rendu au moyen choisi), `jetons` (dette en jetons cadeau
    rendue), `offert` (part offerte annulée). Plus `ligne_entierement_offerte` : vrai
    quand tout ce qui reste est entièrement offert (même règle que l'avoir d'une ligne).
    Lève ValueError, comme l'écriture, si les jetons de la vente sont de plusieurs
    monnaies (`monnaie_et_carte_des_jetons_de_la_vente`).
    / Categories in cents: stripe, chosen method, gift tokens, offered. Raises
    ValueError like the writing when the tokens have several currencies.
    """
    sommes = {
        "stripe": 0,
        "rembourse_par": 0,
        "jetons": 0,
        "offert": 0,
    }
    tout_ce_qui_reste_est_offert = True
    for ligne_avec_un_reste in _lignes_de_la_vente_avec_un_reste_a_rendre(vente):
        quantite_restante = ligne_avec_un_reste.qty
        for ligne_qui_rend_une_partie in ligne_avec_un_reste.credit_notes.all():
            quantite_restante += ligne_qui_rend_une_partie.qty
        montants_de_l_avoir = apercu_des_montants_d_un_avoir(
            ligne_avec_un_reste, quantite_restante
        )
        net_rendu = -montants_de_l_avoir["total_ttc"]
        sommes["offert"] += -montants_de_l_avoir["part_offerte"]
        if not ligne_entierement_offerte(ligne_avec_un_reste):
            tout_ce_qui_reste_est_offert = False
        # La part en jetons rendue (dette du lieu), puis le reste en argent.
        # / The token part given back (venue debt), then the rest in money.
        jetons_rendus = -montants_de_l_avoir["part_en_jetons"]
        sommes["jetons"] += jetons_rendus
        argent_rendu = net_rendu - jetons_rendus
        if argent_rendu == 0:
            continue
        if ligne_avec_un_reste.paiement_stripe_id is not None:
            sommes["stripe"] += argent_rendu
        else:
            sommes["rembourse_par"] += argent_rendu

    # Des jetons à rendre : la même lecture de leur monnaie que l'écriture. Des jetons
    # de plusieurs monnaies lèvent ici le refus (ValueError) que l'écriture lèverait :
    # l'écran l'annonce au lieu de proposer un avoir qui échouerait.
    # / Tokens to give back: same currency read as the writing; several currencies
    # raise here the refusal the writing would raise.
    if sommes["jetons"] != 0:
        monnaie_et_carte_des_jetons_de_la_vente(vente)

    sommes["ligne_entierement_offerte"] = tout_ce_qui_reste_est_offert
    return sommes


def _moyen_pre_rempli_de_l_avoir_total(vente):
    """
    Le moyen « Remboursé par » proposé d'avance : le seul moyen d'argent net de la
    vente, corrections comprises (`moyen_d_argent_unique_de_la_vente`), s'il est dans
    la liste du champ (espèces, CB, chèque, virement), comme l'avoir d'une ligne.
    Plusieurs moyens, ou un moyen hors de la liste : rien (l'admin choisit).
    / The pre-filled method: the sale's single net money method, if it is in the list.
    """
    seul_moyen = moyen_d_argent_unique_de_la_vente(vente)
    if seul_moyen in MOYENS_DU_CHAMP_REMBOURSE_PAR:
        return seul_moyen
    return None


def _lignes_du_chiffre_d_affaires(lignes):
    """
    Les lignes de cette liste qui sont dans le chiffre d'affaires. Une ligne hors
    chiffre d'affaires (recharge de carte, article d'écart) n'a pas d'avoir sur un
    article : le service le refuserait.
    / The lines of this list that are in the revenue.

    LU PAR : `_raison_du_refus_de_l_avoir_sur_un_article` et l'écran
    `VenteAdmin.avoir_sur_un_article`. « Avoir total » ne l'utilise pas.
    """
    lignes_du_chiffre_d_affaires = []
    for ligne in lignes:
        if not ligne.hors_chiffre_affaires:
            lignes_du_chiffre_d_affaires.append(ligne)
    return lignes_du_chiffre_d_affaires


def _raison_du_refus_de_l_avoir_sur_un_article(vente):
    """
    Pourquoi « Avoir sur un article » est refusé sur cette vente, ou None s'il est
    permis : nature autre que VENTE, vente pas réglée, vente qui n'est pas en euros,
    vente qui porte un écart d'encaissement (le message du service, Q-H13), aucun
    article avec un reste à rendre, ou seulement des articles hors chiffre d'affaires.
    Cette lecture sert à refuser AVANT d'afficher l'écran et à cacher le bouton. Les
    autres refus (recharge, quantité, pesée) viennent du service au moment d'écrire
    (`ecrire_la_vente_d_avoir_d_une_ligne`), et l'écran affiche son message.
    / Why the item credit note is refused on this sale, or None. Other refusals come
    from the service when writing.
    """
    if vente.nature != Vente.Nature.VENTE:
        return _("Seule une vente de nature « Vente » reçoit un avoir sur un article.")
    if vente.statut != Vente.Statut.REGLEE:
        return _("La vente n'est pas réglée : l'avoir est impossible.")
    if vente.unite != "EUR":
        return _(
            "Cette vente n'est pas en euros (points ou temps) : l'avoir n'est pas "
            "possible."
        )
    if vente_porte_un_ecart_d_encaissement(vente):
        return MESSAGE_AVOIR_LIGNE_VENTE_AVEC_UN_ECART
    lignes_avec_un_reste = _lignes_de_la_vente_avec_un_reste_a_rendre(vente)
    if not lignes_avec_un_reste:
        return _("La vente est déjà remboursée en totalité : rien n'est à rendre.")
    if not _lignes_du_chiffre_d_affaires(lignes_avec_un_reste):
        return _(
            "Les articles qui restent sont hors chiffre d'affaires (recharge de "
            "carte) : un avoir sur un article n'est pas possible."
        )
    return None


def _quantite_restante_affichee(ligne):
    """
    Le reste à rendre d'une ligne, pour l'écran : « 0,350 kg » pour une pesée (Q-H4),
    le nombre à la française sinon (« 2 », « 1,429 »). La ligne porte son reste dans
    `quantite_restante` (`_lignes_de_la_vente_avec_un_reste_a_rendre`).
    / A line's remainder for the screen: "0,350 kg" for a weighing, the number otherwise.
    """
    unite_de_la_pesee = _unite_d_une_pesee(ligne)
    if unite_de_la_pesee is None:
        return floatformat(ligne.quantite_restante, "-3")
    return quantite_au_poids_a_la_francaise(ligne.quantite_restante, unite_de_la_pesee)


def _quantite_restante_proposee_dans_le_champ(ligne):
    """
    Le reste à rendre d'une ligne, arrondi pour le champ « Quantité rendue » de
    l'écran « Avoir sur un article » : 3 décimales pour les kg, 2 pour les litres
    (la précision de la caisse), sinon 3 décimales au plus, sans zéros inutiles
    (« 2 », « 1.571 »). Une part d'historique (1,571429) reste ainsi lisible.
    / A line's remainder, rounded for the quantity field: kg 3 decimals, litres 2,
    otherwise at most 3 decimals without trailing zeros.

    LOCALISATION : Administration/admin_tenant.py

    Ce n'est qu'un affichage : renvoyée telle quelle, cette valeur vaut tout le reste
    EXACT (`VenteAdmin.avoir_sur_un_article`). La quantité rendue ne change donc pas.
    / Display only: posted back unchanged, it means the whole EXACT remainder.
    """
    unite_de_la_pesee = _unite_d_une_pesee(ligne)
    if unite_de_la_pesee == "L":
        pas_d_arrondi = Decimal("0.01")
    else:
        pas_d_arrondi = Decimal("0.001")
    quantite_arrondie = Decimal(ligne.quantite_restante).quantize(pas_d_arrondi)
    if unite_de_la_pesee is not None:
        return quantite_arrondie
    # À la pièce : sans zéros inutiles (« 2 » et pas « 2.000 »). `normalize()` écrit
    # 10 en « 1E+1 » : on repasse par un texte à virgule fixe.
    # / By the piece: no trailing zeros; fixed-point text to avoid "1E+1".
    return Decimal(format(quantite_arrondie.normalize(), "f"))


def _paiement_paye_de_la_vente(vente):
    """
    Le paiement Stripe PAYÉ (ou validé) le plus récent de la vente, ou None. Les
    paiements pas payés (session expirée, annulée, en attente) sont écartés AVANT de
    prendre le plus récent : une session abandonnée après le paiement ne le cache pas.
    / The most recent PAID (or valid) Stripe payment of the sale, or None.
    """
    return (
        vente.paiements_stripe.filter(
            status__in=[Paiement_stripe.PAID, Paiement_stripe.VALID]
        )
        .order_by("-order_date")
        .first()
    )


def _raison_du_refus_du_rejeu(vente):
    """
    Pourquoi « Rejouer l'encaissement » est refusé sur cette vente, ou None s'il est
    permis : vente pas en attente, vente sans paiement Stripe, paiement Stripe pas
    payé.
    / Why replaying the settlement is refused, or None.
    """
    if vente.statut != Vente.Statut.EN_ATTENTE:
        return _("Seule une vente en attente peut être encaissée de nouveau.")
    if not vente.paiements_stripe.exists():
        return _("Cette vente n'a pas de paiement Stripe : rien à rejouer.")
    if _paiement_paye_de_la_vente(vente) is None:
        return _("Le paiement Stripe de cette vente n'est pas payé : rien à rejouer.")
    return None


def _ligne_partira_a_l_ancien_laboutik(ligne):
    """
    Dit si une ligne vendue en ligne part à l'ancien LaBoutik : un billet ou une
    adhésion, comme les déclencheurs du paiement (BaseBillet/triggers.py, trigger_B et
    trigger_A, qui appellent `send_sale_to_laboutik`). La catégorie est celle du produit
    vendu, sinon celle du produit (même lecture que les déclencheurs).
    / Tells whether an online line is sent to legacy LaBoutik: a ticket or a membership,
    like the payment triggers.
    """
    categorie_de_la_ligne = ligne.pricesold.productsold.categorie_article
    if categorie_de_la_ligne == Product.NONE:
        categorie_de_la_ligne = ligne.pricesold.productsold.product.categorie_article
    return categorie_de_la_ligne in [Product.BILLET, Product.ADHESION]


class VentesAVerifierFilter(admin.SimpleListFilter):
    """
    « À vérifier » :
    - les ventes en attente depuis plus d'une heure dont le client a PAYÉ (un paiement
      Stripe payé ou validé) : un encaissement en ligne en échec. Une vente en attente
      sans aucun paiement Stripe y est aussi (personne ne l'a encore expliquée). Un
      panier abandonné (session Stripe expirée ou annulée, rien de payé) n'y est pas ;
    - les ventes qui portent un article « Écart d'encaissement » (Stripe a encaissé un
      autre montant que les articles).
    / "To check": sales pending for more than an hour that were paid (or have no Stripe
    payment at all) — not abandoned carts —, and sales with a gap item.
    """

    title = _("À vérifier")
    parameter_name = "a_verifier"

    def lookups(self, request, model_admin):
        return [("oui", _("À vérifier"))]

    def queryset(self, request, queryset):
        if self.value() != "oui":
            return queryset
        limite_d_attente = timezone.now() - DELAI_AU_DELA_DUQUEL_UNE_VENTE_EN_ATTENTE_EST_A_VERIFIER
        paiements_payes_de_la_vente = Paiement_stripe.objects.filter(
            vente=OuterRef("pk"),
            status__in=[Paiement_stripe.PAID, Paiement_stripe.VALID],
        )
        paiements_de_la_vente = Paiement_stripe.objects.filter(vente=OuterRef("pk"))
        payee_ou_sans_paiement_stripe = Q(Exists(paiements_payes_de_la_vente)) | ~Q(
            Exists(paiements_de_la_vente)
        )
        en_attente_depuis_trop_longtemps = (
            Q(
                statut=Vente.Statut.EN_ATTENTE,
                datetime_creation__lt=limite_d_attente,
            )
            & payee_ou_sans_paiement_stripe
        )
        avec_un_ecart_d_encaissement = Q(
            articles__pricesold__productsold__product__name__in=[
                NOM_ECART_RECU_EN_PLUS,
                NOM_ECART_RECU_EN_MOINS,
            ]
        )
        return queryset.filter(
            en_attente_depuis_trop_longtemps | avec_un_ecart_d_encaissement
        ).distinct()


class MoyenDeReglementFilter(admin.SimpleListFilter):
    """
    Par moyen : les ventes qui ont au moins un règlement de ce moyen.
    / By method: sales with at least one payment of this method.
    """

    title = _("Moyen de paiement")
    parameter_name = "moyen"

    def lookups(self, request, model_admin):
        choix_des_moyens = []
        for code_du_moyen, _libelle in PaymentMethod.choices:
            choix_des_moyens.append((code_du_moyen, nom_du_moyen_de_paiement(code_du_moyen)))
        return choix_des_moyens

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        reglements_de_ce_moyen = Reglement.objects.filter(
            vente=OuterRef("pk"), moyen=self.value()
        )
        return queryset.filter(Exists(reglements_de_ce_moyen))


class ArticlesDeLaVenteInline(TabularInline):
    """
    Les articles d'une vente : produit, tarif, quantité, prix unitaire, part offerte,
    total (net vendu) et TVA. En lecture seule.
    / A sale's items, read-only.
    """

    model = LigneArticle
    fk_name = "vente"
    extra = 0
    can_delete = False
    show_change_link = False
    # Pas de titre au-dessus de chaque ligne (option Unfold `hide_title`) : les
    # colonnes disent déjà tout ce qu'un titre répéterait.
    # / No title above each row (Unfold `hide_title`): the columns already say it.
    hide_title = True
    verbose_name = _("Article")
    verbose_name_plural = _("Articles")
    fields = (
        "produit",
        "tarif",
        "quantite",
        "prix_unitaire",
        "offert",
        "total",
        "taux_de_tva",
    )
    readonly_fields = fields

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related(
            "vente",
            "pricesold__price",
            "pricesold__productsold__product__stock_inventaire",
        )

    @display(description=_("Produit"))
    def produit(self, ligne):
        return ligne.pricesold.productsold.product.name

    @display(description=_("Tarif"))
    def tarif(self, ligne):
        return ligne.pricesold.price.name

    @display(description=_("Quantité"))
    def quantite(self, ligne):
        # « 0,355 kg » pour une pesée (Q-H4), le nombre sinon.
        # / "0,355 kg" for a weighing, the number otherwise.
        return _quantite_d_une_ligne(ligne)

    @display(description=_("Prix unitaire"))
    def prix_unitaire(self, ligne):
        # « 12,90 €/kg » pour une pesée, le prix de l'article sinon.
        # / "12,90 €/kg" for a weighing, the item price otherwise.
        return _prix_unitaire_d_une_ligne(
            ligne, _montant_d_une_vente(ligne.amount, ligne.vente)
        )

    @display(description=_("Offert"))
    def offert(self, ligne):
        return _montant_d_une_vente(ligne.part_offerte, ligne.vente)

    @display(description=_("Total"))
    def total(self, ligne):
        return _montant_d_une_vente(ligne.total_ttc, ligne.vente)

    @display(description=_("TVA"))
    def taux_de_tva(self, ligne):
        return f"{ligne.vat} %"

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReglementsDeLaVenteInline(TabularInline):
    """
    Les règlements d'une vente : moyen, monnaie, montant, référence externe
    (identifiant Stripe, numéro de chèque…). En lecture seule.
    / A sale's payments, read-only.
    """

    model = Reglement
    fk_name = "vente"
    extra = 0
    can_delete = False
    show_change_link = False
    # Pas de titre au-dessus de chaque ligne (option Unfold `hide_title`) : les
    # colonnes disent déjà tout ce qu'un titre répéterait.
    # / No title above each row (Unfold `hide_title`): the columns already say it.
    hide_title = True
    verbose_name = _("Règlement")
    verbose_name_plural = _("Règlements")
    fields = ("moyen_affiche", "monnaie", "montant_affiche", "reference_et_lien_stripe")
    readonly_fields = fields

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related("vente", "paiement_stripe")

    @display(description=_("Référence"))
    def reference_et_lien_stripe(self, reglement):
        # La référence externe du règlement ; un lien vers le tableau de bord Stripe
        # quand le règlement vient de Stripe (remboursement `re_…`, ou paiement).
        # / The external reference; a link to the Stripe dashboard for Stripe payments.
        adresse_chez_stripe = _adresse_stripe_d_un_reglement(reglement)
        texte_de_la_reference = reglement.reference_externe or "—"
        if adresse_chez_stripe is None:
            return texte_de_la_reference
        if not reglement.reference_externe:
            texte_de_la_reference = _("Voir sur Stripe")
        return format_html(
            '<a href="{}" target="_blank" rel="noopener" data-testid="vente-lien-stripe" style="color: var(--color-primary-600); text-decoration: underline;">{}</a>',
            adresse_chez_stripe,
            texte_de_la_reference,
        )

    @display(description=_("Moyen de paiement"))
    def moyen_affiche(self, reglement):
        return nom_du_moyen_de_paiement(reglement.moyen)

    @display(description=_("Monnaie"))
    def monnaie(self, reglement):
        # Le nom de la monnaie, lu par la même règle que la liste et le détail des
        # ventes (`noms_des_monnaies_des_ventes`). Les noms sont lus UNE fois pour la
        # vente, au premier règlement, puis gardés sur cette instance de l'inline :
        # Django crée une instance par requête, la mémoire ne dure donc qu'une page.
        # « — » sans monnaie, ou pour une monnaie introuvable.
        # / The currency name, same rule as the sales list and detail, read ONCE per
        # sale for the whole inline (one inline instance per request); "—" otherwise.
        if reglement.asset is None:
            return "—"
        noms_des_monnaies_par_vente = getattr(self, "noms_des_monnaies_par_vente", None)
        if noms_des_monnaies_par_vente is None:
            noms_des_monnaies_par_vente = {}
            self.noms_des_monnaies_par_vente = noms_des_monnaies_par_vente
        if reglement.vente_id not in noms_des_monnaies_par_vente:
            noms_des_monnaies_par_vente[reglement.vente_id] = noms_des_monnaies_des_ventes(
                [reglement.vente]
            )
        nom_par_uuid_de_monnaie = noms_des_monnaies_par_vente[reglement.vente_id]
        return nom_par_uuid_de_monnaie.get(str(reglement.asset), "—")

    @display(description=_("Montant"))
    def montant_affiche(self, reglement):
        return _montant_d_une_vente(reglement.montant, reglement.vente)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


def _articles_des_ventes_pour_l_export(ventes):
    """
    Les articles (`LigneArticle`) des ventes données, pour l'export tableur de la liste
    des ventes : la liste filtrée, ou la sélection cochée. Les objets lus par chaque
    colonne de l'export (`LigneArticleExportResource`) sont préchargés : exporter
    1 000 articles ne fait pas 1 000 requêtes.
    / The items of the given sales, for the sales list export (filtered list or
    ticked selection), with everything the export columns read prefetched.

    LOCALISATION : Administration/admin_tenant.py (lu par VenteAdmin.get_data_for_export)

    :param ventes: un queryset de `Vente`
    :return: un queryset de `LigneArticle`, le plus récent d'abord
    """
    cles_des_ventes = ventes.values("pk")
    return (
        LigneArticle.objects.filter(vente__in=cles_des_ventes)
        .select_related(
            "pricesold__productsold",
            "pricesold__productsold__product",
            "pricesold__productsold__event",
            "pricesold__price",
            "reservation__user_commande",
            "paiement_stripe",
            "paiement_stripe__user",
            "membership",
            "membership__user",
            "vente",
        )
        .prefetch_related(
            "vente__reglements",
            "vente__ventes_derivees__reglements",
        )
        .order_by("-datetime")
    )


@admin.register(Vente, site=staff_admin_site)
class VenteAdmin(ExportCsvLisibleParExcelMixin, ModelAdmin, ExportActionModelAdmin):
    """
    La liste et la fiche des ventes du lieu, en lecture seule.
    / The venue's sales list and detail page, read-only.

    LOCALISATION : Administration/admin_tenant.py

    LISTE : numéro, date (heure du lieu), origine, point de vente, client (e-mail, ou
    numéro de carte), total, moyens (badges), nature, statut. Filtres : à vérifier,
    moyen, origine, point de vente, nature, statut, date d'encaissement. Recherche :
    numéro (exact), e-mail du client, carte. Nombre de requêtes constant (point de
    vente, client, carte et règlements préchargés).
    FICHE : en-tête, articles et règlements (inlines), vente liée et ventes dérivées
    (liens), badge d'intégrité (empreinte recalculée par `calculer_hmac_vente`).
    ACTIONS DE LA FICHE (montrées seulement quand elles ont un sens,
    `get_actions_detail`) :
    - « Avoir total » (`avoir_total`) : l'avoir de tout ce qui reste à rendre ;
    - « Avoir sur un article » (`avoir_sur_un_article`) : l'avoir d'une quantité d'un
      seul article ;
    - « Rejouer l'encaissement » (`rejouer_encaissement`) : une vente en ligne restée
      en attente alors que le client a payé.
    EXPORT TABLEUR (bouton « Exporter » de la liste, ou action sur la sélection) : un
    fichier des ARTICLES des ventes, une ligne par article, mêmes colonnes que l'ancien
    export des lignes (`LigneArticleExportResource`). CSV et TSV avec BOM pour Excel
    (`ExportCsvLisibleParExcelMixin`, placé AVANT `ExportActionModelAdmin`).
    / List with filters and search; detail with items, payments, links and integrity;
    three detail actions, shown only when they make sense; spreadsheet export of the
    sales' items.
    """

    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True

    # L'export porte sur les articles des ventes, pas sur les ventes : la ressource
    # est celle des lignes, et `get_data_for_export` change le queryset.
    # / The export is about the sales' items: the line resource, queryset swapped.
    resource_classes = [LigneArticleExportResource]
    export_form_class = ExportForm
    # Pas de bouton d'export sur la fiche : elle est en lecture seule, et l'export se
    # fait depuis la liste.
    # / No export button on the read-only detail page: export from the list.
    show_change_form_export = False

    def get_data_for_export(self, request, queryset, **kwargs):
        # La liste (filtrée) ou la sélection donne des VENTES ; le fichier liste leurs
        # ARTICLES (`_articles_des_ventes_pour_l_export`).
        # / The list or selection gives SALES; the file lists their ITEMS.
        articles_des_ventes = _articles_des_ventes_pour_l_export(queryset)
        return super().get_data_for_export(request, articles_des_ventes, **kwargs)

    list_display = [
        "numero_affiche",
        "date_locale",
        "origine_affichee",
        "point_de_vente_affiche",
        "client_affiche",
        "total_affiche",
        "moyens_affiches",
        "nature_affichee",
        "statut_affiche",
    ]
    list_display_links = ["numero_affiche"]
    list_filter = [
        VentesAVerifierFilter,
        MoyenDeReglementFilter,
        "origine",
        "point_de_vente",
        "nature",
        "statut",
        ("datetime_encaissement", RangeDateTimeFilterWithTimeZone),
    ]
    # Le numéro se cherche à part (`get_search_results`) : un nombre exact.
    # / The number is searched separately: an exact number.
    search_fields = ["client__email", "carte__tag_id", "carte__number"]
    ordering = ("-datetime_creation",)
    inlines = [ArticlesDeLaVenteInline, ReglementsDeLaVenteInline]

    fieldsets = (
        (
            _("Vente"),
            {
                "fields": (
                    "numero_affiche",
                    "nature_affichee",
                    "statut_affiche",
                    "origine_affichee",
                    "point_de_vente_affiche",
                    "client_affiche",
                    "operateur",
                    "date_locale",
                    "total_catalogue_affiche",
                    "total_offert_affiche",
                    "total_affiche",
                    "total_ht_affiche",
                    "total_tva_affiche",
                    "vente_liee_affichee",
                    "ventes_derivees_affichees",
                    "integrite",
                ),
            },
        ),
    )
    readonly_fields = (
        "numero_affiche",
        "nature_affichee",
        "statut_affiche",
        "origine_affichee",
        "point_de_vente_affiche",
        "client_affiche",
        "operateur",
        "date_locale",
        "total_catalogue_affiche",
        "total_offert_affiche",
        "total_affiche",
        "total_ht_affiche",
        "total_tva_affiche",
        "vente_liee_affichee",
        "ventes_derivees_affichees",
        "integrite",
        "raison",
    )

    def get_fieldsets(self, request, obj=None):
        """
        Les blocs de champs de la fiche : ceux de `fieldsets`, plus la raison d'une
        correction (écrite par le caissier, `Vente.raison`) quand elle n'est pas
        vide. La plupart des ventes n'en ont pas : le champ n'apparaît pas.
        / The page's fieldsets, plus the correction reason when it is not empty.

        LOCALISATION : Administration/admin_tenant.py
        """
        fieldsets_de_la_fiche = super().get_fieldsets(request, obj)
        la_vente_a_une_raison = obj is not None and obj.raison != ""
        if not la_vente_a_une_raison:
            return fieldsets_de_la_fiche
        titre_du_bloc, options_du_bloc = fieldsets_de_la_fiche[0]
        # Une copie du dictionnaire : `fieldsets` est un attribut de la classe, il
        # ne doit pas grandir à chaque affichage.
        # / A copy: `fieldsets` is a class attribute, it must not grow on each page.
        options_du_bloc_avec_la_raison = dict(options_du_bloc)
        champs_avec_la_raison = list(options_du_bloc["fields"]) + ["raison"]
        options_du_bloc_avec_la_raison["fields"] = champs_avec_la_raison
        bloc_avec_la_raison = (titre_du_bloc, options_du_bloc_avec_la_raison)
        return (bloc_avec_la_raison,) + tuple(fieldsets_de_la_fiche[1:])

    def get_queryset(self, request):
        # Les objets lus par chaque ligne de la liste sont préchargés : le nombre de
        # requêtes ne grandit pas avec le nombre de ventes.
        # / Objects read by each list row are prefetched: constant query count.
        # Le total des articles d'une vente pas encore réglée (ses totaux ne sont posés
        # qu'à l'encaissement) est calculé par une sous-requête : une seule requête,
        # quel que soit le nombre de ventes, et aucune jointure qui doublerait la somme.
        # / The items total of an unsettled sale, by a subquery (one query, no join).
        queryset = super().get_queryset(request)
        total_des_articles_de_la_vente = (
            LigneArticle.objects.filter(vente=OuterRef("pk"))
            .values("vente")
            .annotate(total=Sum("total_ttc"))
            .values("total")
        )
        return (
            queryset.select_related(
                "point_de_vente", "client", "carte", "operateur", "vente_liee"
            )
            .prefetch_related("reglements")
            .annotate(total_des_articles=Subquery(total_des_articles_de_la_vente))
        )

    def get_search_results(self, request, queryset, search_term):
        # Un terme fait de chiffres cherche AUSSI le numéro exact de la vente. Le
        # numéro est un entier : il ne peut pas être dans `search_fields`, qui
        # comparerait du texte (une adresse e-mail ferait échouer la requête).
        # / A digits-only term ALSO searches the exact sale number.
        resultats, peut_avoir_des_doublons = super().get_search_results(
            request, queryset, search_term
        )
        terme_cherche = search_term.strip()
        if terme_cherche.isdigit():
            resultats = resultats | queryset.filter(numero=int(terme_cherche))
        return resultats, peut_avoir_des_doublons

    def get_actions_detail(self, request, object_id):
        # Les boutons de la fiche ne sont montrés que quand l'action a un sens :
        # « Avoir total » et « Avoir sur un article » si la vente les accepte, « Rejouer l'encaissement » pour une
        # vente en attente qui a un paiement Stripe payé. Les actions gardent leurs
        # propres refus (message d'erreur) pour un appel direct à leur adresse.
        # / Detail buttons are shown only when the action makes sense; the actions
        # keep their own refusals for a direct call.
        actions_permises = super().get_actions_detail(request, object_id)
        vente = Vente.objects.filter(pk=object_id).first()
        if vente is None:
            return actions_permises
        actions_montrees = []
        for action_de_la_fiche in actions_permises:
            if action_de_la_fiche.path == "avoir_total":
                if _raison_du_refus_de_l_avoir_total(vente) is not None:
                    continue
            if action_de_la_fiche.path == "avoir_sur_un_article":
                if _raison_du_refus_de_l_avoir_sur_un_article(vente) is not None:
                    continue
            if action_de_la_fiche.path == "rejouer_encaissement":
                if _raison_du_refus_du_rejeu(vente) is not None:
                    continue
            actions_montrees.append(action_de_la_fiche)
        return actions_montrees

    @display(description=_("N°"), ordering="numero")
    def numero_affiche(self, vente):
        if vente.numero is None:
            return "—"
        return vente.numero

    @display(description=_("Date"), ordering="datetime_creation")
    def date_locale(self, vente):
        # L'heure du lieu : l'encaissement, ou la création d'une vente pas réglée.
        # / The venue's time: settlement, or creation for an unsettled sale.
        moment = vente.datetime_encaissement or vente.datetime_creation
        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        return moment.astimezone(fuseau_du_lieu).strftime("%d/%m/%Y %H:%M")

    @display(description=_("Origine"))
    def origine_affichee(self, vente):
        return vente.get_origine_display()

    @display(description=_("Point de vente"))
    def point_de_vente_affiche(self, vente):
        if vente.point_de_vente is None:
            return "—"
        return vente.point_de_vente.name

    @display(description=_("Client"))
    def client_affiche(self, vente):
        # L'e-mail du client ; sans client connu, le numéro de la carte.
        # / The customer's e-mail; without a known customer, the card number.
        if vente.client is not None:
            return vente.client.email
        if vente.carte is not None:
            return vente.carte.number
        return "—"

    @display(description=_("Total"))
    def total_affiche(self, vente):
        # Une vente réglée a son total stocké. Une vente pas encore réglée, pas encore :
        # on montre la somme de ses articles (`total_des_articles`, `get_queryset`).
        # / A settled sale has its stored total; otherwise the sum of its items.
        if vente.statut == Vente.Statut.REGLEE:
            return _montant_d_une_vente(vente.total_ttc, vente)
        total_des_articles = getattr(vente, "total_des_articles", None) or 0
        return _montant_d_une_vente(total_des_articles, vente)

    @display(description=_("Total catalogue"))
    def total_catalogue_affiche(self, vente):
        return _montant_d_une_vente(vente.total_catalogue, vente)

    @display(description=_("Total offert"))
    def total_offert_affiche(self, vente):
        return _montant_d_une_vente(vente.total_offert, vente)

    @display(description=_("Total HT"))
    def total_ht_affiche(self, vente):
        return _montant_d_une_vente(vente.total_ht, vente)

    @display(description=_("Total TVA"))
    def total_tva_affiche(self, vente):
        return _montant_d_une_vente(vente.total_tva, vente)

    @display(description=_("Moyens"))
    def moyens_affiches(self, vente):
        # Un badge par moyen d'argent de la vente, montant compris, dans l'ordre et
        # avec les libellés de la caisse. L'offert n'est pas un moyen de paiement.
        # / One badge per money method, register order and labels; offered left out.
        reglements_affiches = reglements_pour_l_affichage(
            vente.reglements.all(), {}, _unite_d_une_vente(vente)
        )
        badges_des_moyens = []
        for reglement_affiche in reglements_affiches:
            if reglement_affiche["moyen"] == PaymentMethod.FREE:
                continue
            badges_des_moyens.append(
                (
                    reglement_affiche["montant_a_la_francaise"],
                    reglement_affiche["libelle"],
                )
            )
        if not badges_des_moyens:
            return "—"
        return format_html_join(
            " ",
            '<span data-testid="vente-moyen-badge" style="display: inline-block; padding: 2px 8px; border-radius: 9999px; background: var(--color-base-100, #f3f4f6); color: var(--color-base-700, #374151); font-size: 12px; white-space: nowrap;">{} {}</span>',
            badges_des_moyens,
        )

    @display(description=_("Nature"))
    def nature_affichee(self, vente):
        # Le badge est rendu en HTML (`_badge_unfold`) : il s'affiche dans la liste
        # ET sur la fiche (en lecture seule).
        # / The badge is rendered as HTML: shown in the list AND on the detail page.
        couleurs_par_nature = {
            Vente.Nature.VENTE: "success",
            Vente.Nature.AVOIR: "warning",
            Vente.Nature.CORRECTION: "info",
            Vente.Nature.VIDAGE_CARTE: "info",
        }
        couleur_du_badge = couleurs_par_nature.get(vente.nature, "info")
        return _badge_unfold(couleur_du_badge, badge_de_la_nature_d_une_vente(vente.nature))

    @display(description=_("Statut"))
    def statut_affiche(self, vente):
        # Même badge HTML que la nature, dans la liste et sur la fiche.
        # / Same HTML badge as the nature, in the list and on the detail page.
        couleurs_par_statut = {
            Vente.Statut.REGLEE: "success",
            Vente.Statut.EN_ATTENTE: "warning",
            Vente.Statut.ANNULEE: "danger",
        }
        couleur_du_badge = couleurs_par_statut.get(vente.statut, "info")
        return _badge_unfold(couleur_du_badge, vente.get_statut_display())

    @display(description=_("Vente liée"))
    def vente_liee_affichee(self, vente):
        if vente.vente_liee is None:
            return "—"
        return _lien_vers_la_fiche_d_une_vente(vente.vente_liee)

    @display(description=_("Ventes dérivées"))
    def ventes_derivees_affichees(self, vente):
        liens_des_ventes_derivees = []
        for vente_derivee in vente.ventes_derivees.all():
            liens_des_ventes_derivees.append((_lien_vers_la_fiche_d_une_vente(vente_derivee),))
        if not liens_des_ventes_derivees:
            return "—"
        return format_html_join(" ", "{}", liens_des_ventes_derivees)

    @display(description=_("Intégrité"))
    def integrite(self, vente):
        # L'empreinte de la vente, recalculée (vente, articles et règlements relus en
        # base) et comparée à l'empreinte enregistrée à l'encaissement. Une vente pas
        # réglée n'est pas encore scellée.
        # / The sale fingerprint, recomputed and compared with the stored one.
        cle_du_lieu = None
        if vente.statut == Vente.Statut.REGLEE:
            cle_du_lieu = LaboutikConfiguration.get_solo().get_hmac_key()
        if vente.statut != Vente.Statut.REGLEE:
            texte_du_badge = _("Pas encore scellée")
            couleur_du_badge = "#6b7280"
        elif not cle_du_lieu:
            texte_du_badge = _("Pas de clé d'intégrité pour ce lieu")
            couleur_du_badge = "#6b7280"
        else:
            empreinte_recalculee = calculer_hmac_vente(
                vente, cle_du_lieu, vente.previous_hmac
            )
            # Comparaison à temps constant, comme toute comparaison d'empreintes.
            # / Constant-time comparison, as for any fingerprint comparison.
            empreinte_identique = hmac.compare_digest(
                empreinte_recalculee, vente.hmac_hash or ""
            )
            if empreinte_identique:
                texte_du_badge = _("Intégrité OK")
                couleur_du_badge = "#15803d"
            else:
                texte_du_badge = format_html(
                    "{} — {}",
                    _("Intégrité KO"),
                    _(
                        "L'empreinte recalculée ne correspond pas : la vente, un "
                        "article ou un règlement a été modifié après l'encaissement."
                    ),
                )
                couleur_du_badge = "#b91c1c"
        return format_html(
            '<span data-testid="vente-integrite" style="display: inline-block; padding: 2px 10px; border-radius: 9999px; color: #fff; background: {}; font-size: 12px; font-weight: 600;">{}</span>',
            couleur_du_badge,
            texte_du_badge,
        )

    # --- Actions de la fiche / Detail page actions ---
    actions_detail = ["avoir_total", "avoir_sur_un_article", "rejouer_encaissement"]

    @action(
        description=_("Avoir total"),
        url_path="avoir_total",
        permissions=["action_sur_une_vente"],
    )
    def avoir_total(self, request, object_id):
        """
        « Avoir total » : l'avoir de tout ce qui reste à rendre sur la vente. GET affiche
        l'écran de confirmation, POST écrit l'avoir.
        / "Full credit note": everything left to give back. GET = screen, POST = write.

        LOCALISATION : Administration/admin_tenant.py
        Gabarit : Administration/templates/admin/vente/avoir_total.html
        (récapitulatif de la vente et de ce qui sera rendu).

        REFUS (GET et POST, message d'erreur, retour à la fiche) : nature autre que
        VENTE, vente pas réglée, vente qui n'est pas en euros, vente avec un écart
        d'encaissement ou une recharge, vente déjà remboursée en totalité. Une vente
        couverte par une clôture J n'est PAS refusée : l'avoir est une nouvelle
        opération.

        L'ÉCRAN : il annonce ce qui sera rendu, par catégorie (Stripe, « Remboursé
        par », jetons, offert), avec la même lecture que le service. Le champ
        « Remboursé par » (un seul moyen pour tout l'argent rendu à la main) n'apparaît
        que s'il reste de l'argent hors Stripe et hors jetons ; il est pré-rempli quand
        la vente n'a qu'un moyen d'argent, de la liste. Une vente payée par Stripe
        rappelle la somme à rembourser depuis le tableau de bord Stripe (aucun appel à
        Stripe ici).

        FLUX DU POST : `ecrire_la_vente_d_avoir_d_une_vente` (BaseBillet/services_vente.py),
        origine ADMIN, tout ou rien. Un refus du service, une égalité rompue ou une
        erreur de la base deviennent un message d'erreur, jamais une page 500.
        / Refusals, then a screen announcing the amounts; POST through the sale service.
        """
        vente = get_object_or_404(Vente, pk=object_id)
        adresse_de_la_fiche = reverse("staff_admin:BaseBillet_vente_change", args=[vente.pk])

        raison_du_refus = _raison_du_refus_de_l_avoir_total(vente)
        if raison_du_refus is not None:
            messages.error(request, raison_du_refus)
            return redirect(adresse_de_la_fiche)

        # Que reste-t-il à rendre ? Lecture simple pour l'écran : le service relit tout
        # sous verrou au moment d'écrire.
        # / What is left? Plain read for the screen; the service reads again under lock.
        try:
            sommes_rendues = _sommes_rendues_par_l_avoir_total(vente)
        except ValueError as refus_du_service:
            logger.warning(f"Avoir total refusé pour la vente {vente.uuid} : {refus_du_service}")
            messages.error(
                request,
                _("L'avoir n'a pas pu être émis : %(raison)s") % {"raison": refus_du_service},
            )
            return redirect(adresse_de_la_fiche)
        reste_de_l_argent_stripe = sommes_rendues["stripe"] != 0
        champ_rembourse_par_demande = sommes_rendues["rembourse_par"] != 0

        if request.method == "POST":
            if champ_rembourse_par_demande:
                formulaire = EmettreAvoirAvecMoyenForm(request.POST)
            else:
                formulaire = EmettreAvoirSansMoyenForm(request.POST)
        else:
            if champ_rembourse_par_demande:
                valeurs_initiales = {}
                moyen_pre_rempli = _moyen_pre_rempli_de_l_avoir_total(vente)
                if moyen_pre_rempli is not None:
                    valeurs_initiales["moyen_rembourse"] = moyen_pre_rempli
                formulaire = EmettreAvoirAvecMoyenForm(initial=valeurs_initiales)
            else:
                formulaire = EmettreAvoirSansMoyenForm()

        formulaire_a_afficher = request.method != "POST" or not formulaire.is_valid()
        if formulaire_a_afficher:
            if vente.numero is None:
                titre_de_l_ecran = _("Avoir total de la vente")
            else:
                titre_de_l_ecran = _("Avoir total de la vente n° %(numero)s") % {
                    "numero": vente.numero
                }
            contexte_de_l_ecran = {
                **self.admin_site.each_context(request),
                "title": titre_de_l_ecran,
                "form": formulaire,
                "vente": vente,
                "total_de_la_vente": _montant_d_une_vente(vente.total_ttc, vente),
                "somme_rendue_par_stripe": _montant_d_une_vente(sommes_rendues["stripe"], vente),
                "somme_rendue_par_le_moyen_choisi": _montant_d_une_vente(
                    sommes_rendues["rembourse_par"], vente
                ),
                "somme_rendue_en_jetons": _montant_d_une_vente(sommes_rendues["jetons"], vente),
                "somme_offerte_annulee": _montant_d_une_vente(sommes_rendues["offert"], vente),
                "il_y_a_des_jetons_rendus": sommes_rendues["jetons"] != 0,
                "il_y_a_de_l_offert_annule": sommes_rendues["offert"] != 0,
                "ligne_payee_par_stripe": reste_de_l_argent_stripe,
                "ligne_entierement_offerte": sommes_rendues["ligne_entierement_offerte"],
                "champ_rembourse_par_demande": champ_rembourse_par_demande,
                "url_de_la_liste_des_ventes": adresse_de_la_fiche,
            }
            return render(
                request,
                "admin/vente/avoir_total.html",
                contexte_de_l_ecran,
            )

        if champ_rembourse_par_demande:
            moyen_choisi = formulaire.cleaned_data["moyen_rembourse"]
        else:
            moyen_choisi = None

        try:
            vente_d_avoir = ecrire_la_vente_d_avoir_d_une_vente(
                vente, moyen_rembourse=moyen_choisi, origine=SaleOrigin.ADMIN
            )
        except ValueError as refus_du_service:
            # Une règle du service refuse l'avoir : rien n'est écrit (transaction).
            # Un refus métier est attendu : un avertissement au journal, pas une erreur.
            # / A service rule refuses: nothing written; logged as a warning.
            logger.warning(f"Avoir total refusé pour la vente {vente.uuid} : {refus_du_service}")
            messages.error(
                request,
                _("L'avoir n'a pas pu être émis : %(raison)s") % {"raison": refus_du_service},
            )
            return redirect(adresse_de_la_fiche)
        except (EgaliteDeVenteRompue, OperationalError, IntegrityError) as erreur_d_ecriture:
            # Une égalité rompue ou une erreur de la base (verrou, contrainte) : rien
            # n'est écrit (transaction). L'admin reçoit un message, pas une page 500.
            # / A broken equality or a database error: nothing written, a message.
            logger.error(f"Avoir total en échec pour la vente {vente.uuid} : {erreur_d_ecriture!r}")
            messages.error(
                request,
                _("L'avoir n'a pas pu être émis : %(raison)s") % {"raison": erreur_d_ecriture},
            )
            return redirect(adresse_de_la_fiche)

        messages.success(request, _("Avoir émis."))
        if reste_de_l_argent_stripe:
            # Aucun appel à Stripe ici : l'argent n'est pas encore rendu.
            # / No Stripe call here: the money is not given back yet.
            messages.warning(
                request,
                _("Remboursez cette somme depuis votre tableau de bord Stripe."),
            )
        return redirect(
            reverse("staff_admin:BaseBillet_vente_change", args=[vente_d_avoir.pk])
        )

    @action(
        description=_("Avoir sur un article"),
        url_path="avoir_sur_un_article",
        permissions=["action_sur_une_vente"],
    )
    def avoir_sur_un_article(self, request, object_id):
        """
        « Avoir sur un article » : l'avoir d'une quantité d'un seul article de la vente
        (par exemple 1 jus sur 3). Même prix unitaire, quantité négative (D13).
        / "Credit note on one item": a quantity of one item, same unit price, negative
        quantity.

        LOCALISATION : Administration/admin_tenant.py
        Gabarit : Administration/templates/admin/vente/avoir_sur_un_article.html

        DEUX ÉCRANS, à la même adresse :
        - sans paramètre : la liste des articles qui ont encore un reste à rendre
          (`_lignes_de_la_vente_avec_un_reste_a_rendre`), chacun avec un lien ;
        - `?ligne=<pk>` : l'article choisi. Champ « Quantité rendue », pré-rempli avec
          le reste ; en lecture seule pour une pesée ou un tirage (Q-H5). Champ
          « Remboursé par » seulement pour de l'argent rendu à la main (D27 : pas pour
          un article payé par Stripe, entièrement offert ou entièrement en jetons),
          pré-rempli par le moyen d'origine (`moyen_d_origine_de_la_ligne`).

        REFUS AVANT L'ÉCRAN (message d'erreur, retour à la fiche) : nature autre que
        VENTE, vente pas réglée, vente pas en euros, rien à rendre ; article absent de
        la vente ou déjà rendu en totalité (retour à la liste).

        FLUX DU POST (`?ligne=<pk>`) : `ecrire_la_vente_d_avoir_d_une_ligne`
        (BaseBillet/services_vente.py), origine ADMIN. Le service relit le reste sous
        verrou et porte les refus (quantité, part offerte ou en jetons, pesée, écart
        d'encaissement, recharge) : un refus devient un message d'erreur, rien n'est
        écrit. Une égalité rompue ou une erreur de la base aussi, jamais une page 500.
        / Two screens (list, chosen item); POST through the sale service, whose refusals
        become error messages.
        """
        vente = get_object_or_404(Vente, pk=object_id)
        adresse_de_la_fiche = reverse("staff_admin:BaseBillet_vente_change", args=[vente.pk])
        adresse_de_la_liste_des_articles = reverse(
            "staff_admin:BaseBillet_vente_avoir_sur_un_article", args=[vente.pk]
        )

        raison_du_refus = _raison_du_refus_de_l_avoir_sur_un_article(vente)
        if raison_du_refus is not None:
            messages.error(request, raison_du_refus)
            return redirect(adresse_de_la_fiche)

        # Seuls les articles du chiffre d'affaires sont proposés : ni recharge, ni
        # article d'écart. « Avoir total » garde sa propre lecture.
        # / Only revenue items are offered; the full credit note keeps its own read.
        lignes_avec_un_reste = _lignes_du_chiffre_d_affaires(
            _lignes_de_la_vente_avec_un_reste_a_rendre(vente)
        )
        if vente.numero is None:
            titre_de_l_ecran = _("Avoir sur un article")
        else:
            titre_de_l_ecran = _("Avoir sur un article de la vente n° %(numero)s") % {
                "numero": vente.numero
            }

        # Premier écran : la liste des articles qui ont un reste à rendre.
        # / First screen: the items with something left to give back.
        cle_de_la_ligne_choisie = request.GET.get("ligne", "")
        if cle_de_la_ligne_choisie == "":
            articles_proposes = []
            for ligne_avec_un_reste in lignes_avec_un_reste:
                articles_proposes.append(
                    {
                        "ligne": ligne_avec_un_reste,
                        "quantite_restante": _quantite_restante_affichee(ligne_avec_un_reste),
                        "prix_unitaire": _montant_d_une_vente(ligne_avec_un_reste.amount, vente),
                        "adresse": f"{adresse_de_la_liste_des_articles}?ligne={ligne_avec_un_reste.pk}",
                    }
                )
            contexte_de_la_liste = {
                **self.admin_site.each_context(request),
                "title": titre_de_l_ecran,
                "vente": vente,
                "ligne": None,
                "articles_proposes": articles_proposes,
                "url_de_la_fiche_de_la_vente": adresse_de_la_fiche,
            }
            return render(
                request, "admin/vente/avoir_sur_un_article.html", contexte_de_la_liste
            )

        # Second écran : l'article choisi, s'il est dans la vente et a un reste.
        # / Second screen: the chosen item, if it is in the sale and has a remainder.
        ligne_choisie = None
        for ligne_avec_un_reste in lignes_avec_un_reste:
            if str(ligne_avec_un_reste.pk) == cle_de_la_ligne_choisie:
                ligne_choisie = ligne_avec_un_reste
        if ligne_choisie is None:
            messages.error(
                request,
                _("Cet article n'est pas dans cette vente, ou il est déjà rendu en totalité."),
            )
            return redirect(adresse_de_la_liste_des_articles)

        ligne_payee_par_stripe = ligne_choisie.paiement_stripe_id is not None
        champ_rembourse_par_demande = (
            not ligne_payee_par_stripe and not ligne_sans_argent_a_rendre(ligne_choisie)
        )
        quantite_figee = article_vendu_au_poids_ou_a_la_tireuse(ligne_choisie)

        if request.method == "POST":
            formulaire = AvoirSurUnArticleForm(
                request.POST,
                champ_rembourse_par_demande=champ_rembourse_par_demande,
                quantite_figee=quantite_figee,
            )
        else:
            # Le champ propose le reste arrondi (lisible) ; renvoyé tel quel, il vaut
            # tout le reste exact (voir plus bas).
            # / The field offers the rounded remainder; posted back, it means it all.
            valeurs_initiales = {
                "quantite": _quantite_restante_proposee_dans_le_champ(ligne_choisie)
            }
            moyen_d_origine = moyen_d_origine_de_la_ligne(ligne_choisie)
            if moyen_d_origine in MOYENS_DU_CHAMP_REMBOURSE_PAR:
                valeurs_initiales["moyen_rembourse"] = moyen_d_origine
            formulaire = AvoirSurUnArticleForm(
                initial=valeurs_initiales,
                champ_rembourse_par_demande=champ_rembourse_par_demande,
                quantite_figee=quantite_figee,
            )

        formulaire_a_afficher = request.method != "POST" or not formulaire.is_valid()
        if formulaire_a_afficher:
            contexte_de_l_ecran = {
                **self.admin_site.each_context(request),
                "title": titre_de_l_ecran,
                "vente": vente,
                "ligne": ligne_choisie,
                "form": formulaire,
                "quantite_restante": _quantite_restante_affichee(ligne_choisie),
                "prix_unitaire": _montant_d_une_vente(ligne_choisie.amount, vente),
                "quantite_figee": quantite_figee,
                "ligne_payee_par_stripe": ligne_payee_par_stripe,
                "ligne_entierement_offerte": ligne_entierement_offerte(ligne_choisie),
                "champ_rembourse_par_demande": champ_rembourse_par_demande,
                "url_de_la_liste_des_articles": adresse_de_la_liste_des_articles,
            }
            return render(
                request, "admin/vente/avoir_sur_un_article.html", contexte_de_l_ecran
            )

        quantite_rendue = formulaire.cleaned_data["quantite"]
        # La valeur proposée par le champ est le reste ARRONDI pour la lecture
        # (`_quantite_restante_proposee_dans_le_champ`). Renvoyée telle quelle, elle
        # veut dire « tout le reste » : on rend alors le reste exact (1,571429 et pas
        # 1,571). Sans cette règle, le service refuserait une partie non entière.
        # / The offered value is the rounded remainder; posted back unchanged, it
        # means "all of it": the exact remainder is given back.
        quantite_proposee_dans_le_champ = _quantite_restante_proposee_dans_le_champ(
            ligne_choisie
        )
        if quantite_rendue == quantite_proposee_dans_le_champ:
            quantite_rendue = ligne_choisie.quantite_restante
        if champ_rembourse_par_demande:
            moyen_choisi = formulaire.cleaned_data["moyen_rembourse"]
        else:
            moyen_choisi = None

        try:
            article_d_avoir = ecrire_la_vente_d_avoir_d_une_ligne(
                ligne_choisie,
                quantite=quantite_rendue,
                moyen_rembourse=moyen_choisi,
                origine=SaleOrigin.ADMIN,
            )
        except ValueError as refus_du_service:
            # Une règle du service refuse l'avoir : rien n'est écrit (transaction).
            # Un refus métier est attendu : un avertissement au journal, pas une erreur.
            # / A service rule refuses: nothing written; logged as a warning.
            logger.warning(
                f"Avoir sur un article refusé pour la ligne {ligne_choisie.uuid} : {refus_du_service}"
            )
            messages.error(
                request,
                _("L'avoir n'a pas pu être émis : %(raison)s") % {"raison": refus_du_service},
            )
            return redirect(adresse_de_la_fiche)
        except (EgaliteDeVenteRompue, OperationalError, IntegrityError) as erreur_d_ecriture:
            # Une égalité rompue ou une erreur de la base (verrou, contrainte) : rien
            # n'est écrit (transaction). L'admin reçoit un message, pas une page 500.
            # / A broken equality or a database error: nothing written, a message.
            logger.error(
                f"Avoir sur un article en échec pour la ligne {ligne_choisie.uuid} : {erreur_d_ecriture!r}"
            )
            messages.error(
                request,
                _("L'avoir n'a pas pu être émis : %(raison)s") % {"raison": erreur_d_ecriture},
            )
            return redirect(adresse_de_la_fiche)

        messages.success(request, _("Avoir émis."))
        if ligne_payee_par_stripe:
            # Aucun appel à Stripe ici : l'argent n'est pas encore rendu.
            # / No Stripe call here: the money is not given back yet.
            messages.warning(
                request,
                _("Remboursez cette somme depuis votre tableau de bord Stripe."),
            )
        return redirect(
            reverse("staff_admin:BaseBillet_vente_change", args=[article_d_avoir.vente_id])
        )

    @action(
        description=_("Rejouer l'encaissement"),
        url_path="rejouer_encaissement",
        permissions=["action_sur_une_vente"],
    )
    def rejouer_encaissement(self, request, object_id):
        """
        « Rejouer l'encaissement » d'une vente en ligne restée en attente (l'encaissement
        a échoué alors que le client a payé). GET affiche l'écran, POST rejoue.
        / Replays the settlement of a pending online sale. GET = screen, POST = replay.

        LOCALISATION : Administration/admin_tenant.py

        LE REJEU : un appel à `encaisser_vente_stripe(paiement)` (BaseBillet/services_vente.py),
        le point d'encaissement unique des ventes en ligne. JAMAIS `paiement.save()` : le
        paiement est déjà VALID, et une transition VALID → VALID ne rejoue rien.
        REFUS (message d'erreur, retour à la fiche) : vente pas en attente, vente sans
        paiement Stripe, paiement pas encore payé, refus du service (montant ou moyen
        vides, vente annulée…).
        / One call to encaisser_vente_stripe, never payment.save(). Refusals: not pending,
        no Stripe payment, payment not paid, service refusal.
        """
        vente = get_object_or_404(Vente, pk=object_id)
        adresse_de_la_fiche = reverse("staff_admin:BaseBillet_vente_change", args=[vente.pk])

        raison_du_refus = _raison_du_refus_du_rejeu(vente)
        if raison_du_refus is not None:
            messages.error(request, raison_du_refus)
            return redirect(adresse_de_la_fiche)
        paiement_de_la_vente = _paiement_paye_de_la_vente(vente)

        if request.method != "POST":
            contexte_de_l_ecran = {
                **self.admin_site.each_context(request),
                "title": _("Rejouer l'encaissement"),
                "vente": vente,
                "url_de_la_fiche_de_la_vente": adresse_de_la_fiche,
            }
            return render(
                request,
                "admin/vente/rejouer_encaissement.html",
                contexte_de_l_ecran,
            )

        try:
            encaisser_vente_stripe(paiement_de_la_vente)
        except ValueError as refus_du_service:
            # Un refus métier (montant ou moyen vides, vente annulée) : attendu, un
            # avertissement au journal.
            # / A business refusal: expected, logged as a warning.
            logger.warning(
                f"Rejeu de l'encaissement refusé pour la vente {vente.uuid} : {refus_du_service}"
            )
            messages.error(
                request,
                _("L'encaissement n'a pas pu être rejoué : %(raison)s")
                % {"raison": refus_du_service},
            )
            return redirect(adresse_de_la_fiche)
        except (EgaliteDeVenteRompue, OperationalError, IntegrityError) as erreur_d_ecriture:
            # Une égalité rompue ou une erreur de la base : rien n'est écrit
            # (transaction). Un message, pas une page 500.
            # / A broken equality or a database error: nothing written, a message.
            logger.error(
                f"Rejeu de l'encaissement en échec pour la vente {vente.uuid} : "
                f"{erreur_d_ecriture!r}"
            )
            messages.error(
                request,
                _("L'encaissement n'a pas pu être rejoué : %(raison)s")
                % {"raison": erreur_d_ecriture},
            )
            return redirect(adresse_de_la_fiche)

        # La vente est réglée : ses billets et adhésions repartent vers l'ancien
        # LaBoutik, comme après un encaissement normal (les déclencheurs du paiement
        # l'avaient demandé, mais la tâche a pu abandonner pendant que la vente
        # attendait). Après la validation en base (`on_commit`) : le worker relit la
        # ligne. La tâche ne poste jamais deux fois la même ligne (`sended_to_laboutik`).
        # / The sale is settled: its tickets and memberships are sent again to legacy
        # LaBoutik, after the commit; the task never posts a line twice.
        lignes_a_renvoyer = (
            LigneArticle.objects.filter(vente=vente, status=LigneArticle.VALID)
            .select_related("pricesold__productsold__product")
            .order_by("datetime", "pk")
        )
        for ligne_a_renvoyer in lignes_a_renvoyer:
            if _ligne_partira_a_l_ancien_laboutik(ligne_a_renvoyer):
                pk_de_la_ligne = ligne_a_renvoyer.pk
                db_transaction.on_commit(
                    partial(send_sale_to_laboutik.delay, pk_de_la_ligne)
                )

        messages.success(request, _("Vente encaissée."))
        return redirect(adresse_de_la_fiche)

    def has_action_sur_une_vente_permission(self, request, object_id=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PostalAddress, site=staff_admin_site)
class PostalAddressAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    list_display = [
        "name",
        "street_address",
        "address_locality",
        "address_region",
        "postal_code",
        "address_country",
        "latitude",
        "longitude",
        "comment",
        "is_main",
    ]

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def save_model(self, request, obj, form, change):
        # Une seule adresse principale par lieu. Cocher "adresse principale" ici
        # decoche automatiquement toutes les autres : la derniere cochee gagne.
        # La requete tourne dans le schema du tenant courant -> portee par tenant.
        # / Only one main address per venue. Ticking "main address" here silently
        # unticks all the others: the last one ticked wins. The query runs in the
        # current tenant schema, so it is naturally tenant-scoped.
        super().save_model(request, obj, form, change)
        if obj.is_main:
            PostalAddress.objects.exclude(pk=obj.pk).filter(is_main=True).update(
                is_main=False
            )


##### EVENT ADMIN


class EventForm(ModelForm):
    class Meta:
        model = Event
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['products'].widget.can_change_related = False
        self.fields['products'].widget.can_add_related = False
        self.fields['products'].help_text = _("Leave empty to avoid reservations.")
        self.fields['short_description'].help_text = _("Used for social network descriptions.")

        try:
            # On mets la valeur de la jauge réglée dans la config par default
            config = Configuration.get_solo()
            self.fields['jauge_max'].initial = config.jauge_max
        except Exception as e:
            logger.error(f"set gauge max error : {e}")
            pass


class EventPricesSummaryTable(TableSection):
    verbose_name = _("Résumé par tarif")
    height = 240
    related_name = "pricesold_for_sections"  # Event property returning Ticket queryset with annotations
    fields = ["price_name", "qty_reserved", "total_euros"]

    def price_name(self, instance: Ticket):
        # Prefer annotated name to avoid extra queries
        name = getattr(instance, "section_price_name", None)
        if name:
            return name
        try:
            return instance.pricesold.price.name if instance.pricesold and instance.pricesold.price else "—"
        except Exception:
            return "—"

    def qty_reserved(self, instance: Ticket):
        qty = getattr(instance, "section_qty_reserved", None)
        if qty is None:
            qty = 0
        try:
            from decimal import Decimal
            if isinstance(qty, Decimal):
                return int(qty) if qty == qty.to_integral() else qty
            return int(qty) if float(qty).is_integer() else qty
        except Exception:
            return qty

    def total_euros(self, instance: Ticket):
        euros = getattr(instance, "section_euros_total", None)
        if euros is None:
            euros = 0
        try:
            from decimal import Decimal
            return (Decimal(euros)).quantize(Decimal("1.00"))
        except Exception:
            return 0


class ChildActionsSummaryTable(TableSection):
    verbose_name = _("Action bénévoles")
    height = 240
    related_name = "children_pricesold_for_sections"
    fields = ["price_name", "qty_reserved"]

    def price_name(self, instance: Ticket):
        name = getattr(instance, "section_price_name", None)
        if name:
            return name
        try:
            return instance.reservation.event.name if instance.reservation and instance.reservation.event else "Oups"
        except Exception:
            return "—"

    def qty_reserved(self, instance: Ticket):
        qty = getattr(instance, "section_qty_reserved", None)
        if qty is None:
            qty = 0
        try:
            from decimal import Decimal
            if isinstance(qty, Decimal):
                return int(qty) if qty == qty.to_integral() else qty
            return int(qty) if float(qty).is_integer() else qty
        except Exception:
            return qty

    # Hide the section entirely if the event has no children
    def render(self):
        # On lit d'abord l'annotation posee par EventAdmin.get_queryset() :
        # c'est ce qui evite une requete par ligne de la changelist.
        # Le repli sur exists() garde la section correcte hors changelist
        # (fiche, appel direct), ou l'annotation n'existe pas — meme motif
        # defensif que EventPricesSummaryTable juste au-dessus.
        # / Read the annotation first (no query); fall back to exists() when
        #   the section is used outside the annotated changelist.
        nombre_d_enfants = getattr(self.instance, "section_children_count", None)
        if nombre_d_enfants is not None:
            if not nombre_d_enfants:
                return ""
            return super().render()

        try:
            if not self.instance.children.exists():
                return ""
        except Exception:
            return ""
        return super().render()


class EventArchiveFilter(admin.SimpleListFilter):
    title = _("Archived")
    parameter_name = "archived"

    def lookups(self, request, model_admin):
        return [
            ("archived", _("Archived")),
        ]

    def queryset(self, request, queryset):
        value = self.value()
        # Filtrage par défaut
        if value is None:
            return queryset.exclude(archived=True)
        if value == "archived":
            return queryset.filter(archived=True)
        return queryset


# Import/Export Resource pour Event
# Resource for CSV import/export of events in admin
class EventResource(resources.ModelResource):
    """Ressource d'import/export pour les événements.
    Resource for import/export of events.

    Clés uniques: (name, datetime) — identifie si on crée ou met à jour.
    Unique keys: (name, datetime) — determines create vs update.

    Les ForeignKey (postal_address) sont exportées en clair (nom lisible).
    ForeignKey fields (postal_address) are exported as human-readable names.

    Les ManyToMany (products, tag) ne sont pas gérés ici.
    ManyToMany fields (products, tag) are not handled here.
    Il faudrait un widget M2MWidget personnalisé pour les gérer.
    A custom M2MWidget would be needed to handle them.
    """

    # postal_address : on exporte/importe le nom de l'adresse au lieu de l'ID
    # postal_address: export/import the address name instead of the raw PK
    postal_address = fields.Field(
        column_name='postal_address',
        attribute='postal_address',
        widget=ForeignKeyWidget(PostalAddress, field='name'),
    )

    class Meta:
        model = Event
        import_id_fields = ('name', 'datetime')
        fields = (
            'name', 'datetime', 'end_datetime', 'jauge_max', 'max_per_user',
            'short_description', 'long_description', 'published', 'archived',
            'private', 'show_time', 'show_gauge', 'slug', 'is_external',
            'full_url', 'postal_address', 'reservation_button_name',
            'minimum_cashless_required',
        )
        # Ordre des colonnes dans le CSV exporté
        # Column order in the exported CSV
        export_order = fields
        widgets = {
            'datetime': {'format': '%Y-%m-%d %H:%M:%S'},
            'end_datetime': {'format': '%Y-%m-%d %H:%M:%S'},
        }
        # Ne pas lever d'erreur sur les lignes invalides, les ignorer
        # Skip invalid rows instead of raising errors
        skip_unchanged = True
        # Afficher un diff des changements avant import
        # Show a diff of changes before import
        report_skipped = True


class IsProposalFilter(admin.SimpleListFilter):
    """
    Filtre sidebar Unfold pour distinguer propositions publiques en
    attente, propositions approuvees et events normaux.
    / Unfold sidebar filter for pending proposals, approved proposals
    and regular events.
    """
    title = _("Proposal status")
    parameter_name = "proposal_status"

    def lookups(self, request, model_admin):
        return [
            ("pending", _("Proposals pending")),
            ("approved", _("Proposals approved")),
            ("regular", _("Regular events")),
        ]

    def queryset(self, request, queryset):
        if self.value() == "pending":
            return queryset.filter(is_proposal=True, published=False)
        if self.value() == "approved":
            return queryset.filter(is_proposal=True, published=True)
        if self.value() == "regular":
            return queryset.filter(is_proposal=False)
        return queryset


@admin.register(Event, site=staff_admin_site)
class EventAdmin(ExportCsvLisibleParExcelMixin, ModelAdmin, ImportExportModelAdmin):
    form = EventForm
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    date_hierarchy = "datetime"
    ordering = ("-datetime",)
    
    # Import/Export configuration
    resource_classes = [EventResource]
    export_form_class = ExportForm
    import_form_class = ImportForm
    
    # Unfold sections (expandable rows)
    list_sections = [
        EventPricesSummaryTable,
        ChildActionsSummaryTable,
    ]
    list_per_page = 20

    change_form_template = 'admin/event/change_form.html'

    export_form_class = ExportForm
    import_form_class = ImportForm

    actions_row = ["duplicate_day_plus_one", "duplicate_week_plus_one", "duplicate_week_plus_two",
                   "duplicate_month_plus_one", "archive"]

    fieldsets = (
        (None, {
            'fields': (
                'name',
                # 'categorie',
                'datetime',
                'end_datetime',
                'show_time',
                'img',
                'sticker_img',
                'carrousel',
                'short_description',
                'long_description',
                'jauge_max',
                'show_gauge',
                'postal_address',
                'tag',
                'thematique',
            )
        }),
        (_('Bookings'), {
            'fields': (
                # 'easy_reservation',
                'products',
                'max_per_user',
                'reservation_button_name',
                'custom_confirmation_message',
                'refund_deadline',
            ),
        }),
        (_('Publish'), {
            'fields': (
                'published',
                'private',
                'archived',
                # Auteur de l'event (ex : proposeur via le wizard public), en lecture seule.
                # / Event author (e.g. public-wizard proposer), read-only.
                'display_created_by',
            ),
        }),
    )

    list_display = [
        'name',
        # 'categorie',
        'display_valid_tickets_count',
        'datetime',
        'show_time',
        'published',
    ]

    list_editable = ['published', ]
    readonly_fields = (
        'display_valid_tickets_count',
        # Affiche en lecture seule sur la fiche event (bas du bloc Publier).
        # / Read-only on the event change form (bottom of the Publish block).
        'display_created_by',
    )

    search_fields = ['name']
    list_filter = [
        IsProposalFilter,
        EventArchiveFilter,
        ('datetime', RangeDateTimeFilterWithTimeZone),
        'published',
    ]
    list_filter_submit = True

    actions = ["approuver_propositions"]

    autocomplete_fields = [
        "tag",
        "thematique",
        # "options_radio",
        # "options_checkbox",
        "carrousel",

        # Le autocomplete fields + many2many ne permet pas de filtrage facile
        # Pour filter les produits de type billet, regarder le get_search_results dans ProductAdmin
        "products",
    ]

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # Les events action et les events children doivent s'afficher dans un inline
        return (
            queryset
            .exclude(categorie=Event.ACTION)
            .exclude(parent__isnull=False)
            .select_related('postal_address')
            .prefetch_related(
                'tag', 'carrousel', 'products',
                Prefetch(
                    'reservation',
                    queryset=Reservation.objects.select_related('user_commande')
                    .only('pk', 'datetime', 'status', 'user_commande__email', 'event')
                ),
            )
            .annotate(
                valid_tickets_count_annotated=Count(
                    'reservation__tickets',
                    filter=Q(reservation__tickets__status__in=[Ticket.SCANNED, Ticket.NOT_SCANNED]),
                    distinct=True,
                ),
                # Nombre d'evenements enfants, precharge ICI plutot que
                # redemande ligne par ligne par ChildActionsSummaryTable.
                # Unfold rend TOUTES les sections de TOUTES les lignes a chaque
                # affichage — meme si personne ne deplie — donc un exists() par
                # ligne etait une N+1 payee a chaque chargement.
                # / Preloaded here instead of one exists() per row: Unfold
                #   renders every section of every row on every page load.
                section_children_count=Count('children', distinct=True),
            )
        )

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        # On enveloppe la vue d'ajout/édition pour transformer une IntegrityError
        # (contrainte unique name+datetime) en message propre plutôt qu'une 500.
        # Cas typique : double-clic sur "Enregistrer" / double soumission. La
        # validation du formulaire (unique_together) était passée, mais un INSERT
        # concurrent a déjà créé l'évènement entre temps (course / TOCTOU).
        # / Wrap the add/change view to turn an IntegrityError (unique name+datetime
        # constraint) into a clean message instead of a 500. Typical case: a
        # double "Save" submit slipping past the form's unique validation.
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except IntegrityError:
            messages.error(request, _("Un évènement avec le même nom et la même date existe déjà."))
            return redirect(reverse(f"{self.admin_site.name}:BaseBillet_event_changelist"))

    def save_model(self, request, obj: Event, form, change):
        # Sanitize all TextField inputs to avoid XSS via WysiwYG/TextField
        sanitize_textfields(obj)

        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        # Fabrication des pricesold event/prix pour pouvoir être selectionné sur le + billet
        # Doit être dans save_related (pas save_model) car les M2M products
        # ne sont disponibles qu'après que Django les a sauvées.
        for product in obj.products.all():
            for price in product.prices.filter(archived=False):
                get_or_create_price_sold(price=price, event=obj)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_custom_actions_row_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    @display(description=_("Valid tickets"))
    def display_valid_tickets_count(self, instance: Event):
        # Use annotated value to avoid N+1; fallback to method if not present (e.g., detail page)
        count = getattr(instance, 'valid_tickets_count_annotated', None)
        if count is None:
            count = instance.valid_tickets_count()
        return f"{count} / {instance.jauge_max}"

    @display(description=_("Créé par"))
    def display_created_by(self, instance: Event):
        # Affiche l'utilisateur qui a cree l'event (ex : proposeur via le wizard
        # public). Tiret si inconnu (events anciens ou crees par script/import).
        # / Show the user who created the event (e.g. public-wizard proposer).
        # Dash if unknown (legacy events or created by a script/import).
        if instance.created_by:
            return instance.created_by.email
        return "—"

    @action(
        description=_("Archive"),
        permissions=["custom_actions_row"],
    )
    def archive(self, request, object_id):
        event = Event.objects.get(pk=object_id)
        event.archived = True
        event.published = False
        event.save(update_fields=['archived', 'published'])
        return redirect(request.META["HTTP_REFERER"])

    @action(
        description=_("Duplicate (day+1)"),
        permissions=["custom_actions_row"],
    )
    def duplicate_day_plus_one(self, request, object_id):
        """Duplicate an event with the date set to the next day"""
        obj = Event.objects.get(pk=object_id)
        try:
            duplicate = self._duplicate_event(obj, date_adjustment="day")
            messages.success(request, _("Event duplicated successfully"))
        except IntegrityError:
            messages.error(request, _("Un evenement avec le même nom et date semble déja dupliqué"))

        return redirect(request.META["HTTP_REFERER"])

        # return redirect(reverse('staff:BaseBillet_event_change', args=[duplicate.uuid]))

    @action(
        description=_("Duplicate (week+1)"),
        permissions=["custom_actions_row"],
    )
    def duplicate_week_plus_one(self, request, object_id):
        """Duplicate an event with the date set to the next week"""
        obj = Event.objects.get(pk=object_id)
        try:
            duplicate = self._duplicate_event(obj, date_adjustment="week")
            messages.success(request, _("Event duplicated successfully"))
        except IntegrityError:
            messages.error(request, _("Un evenement avec le même nom et date semble déja dupliqué"))

        return redirect(request.META["HTTP_REFERER"])

        # return redirect(reverse('staff:BaseBillet_event_change', args=[duplicate.uuid]))

    @action(
        description=_("Duplicate (week+2)"),
        permissions=["custom_actions_row"],
    )
    def duplicate_week_plus_two(self, request, object_id):
        """Duplicate an event with the date set to two weeks ahead"""
        obj = Event.objects.get(pk=object_id)
        try:
            duplicate = self._duplicate_event(obj, date_adjustment="week2")
            messages.success(request, _("Event duplicated successfully"))
        except IntegrityError:
            messages.error(request, _("Un evenement avec le même nom et date semble déja dupliqué"))

        return redirect(request.META["HTTP_REFERER"])

        # return redirect(reverse('staff:BaseBillet_event_change', args=[duplicate.uuid]))

    @action(
        description=_("Duplicate (month+1)"),
        permissions=["custom_actions_row"],
    )
    def duplicate_month_plus_one(self, request, object_id):
        """Duplicate an event with the date set to the next month"""
        obj = Event.objects.get(pk=object_id)
        try:
            duplicate = self._duplicate_event(obj, date_adjustment="month")
            messages.success(request, _("Event duplicated successfully"))
        except IntegrityError:
            messages.error(request, _("Un evenement avec le même nom et date semble déja dupliqué"))
        return redirect(request.META["HTTP_REFERER"])

        # return redirect(reverse('staff:BaseBillet_event_change', args=[duplicate.uuid]))

    def _duplicate_event(self, obj, date_adjustment=None):
        """
        Helper method to duplicate an event

        Args:
            obj: The event to duplicate
            date_adjustment: Type of date adjustment to apply ("day", "week", "month", or None for same date)

        Returns:
            The duplicated event
        """
        # Create a copy of the event
        duplicate = Event.objects.get(uuid=obj.uuid)
        duplicate.pk = None  # This will create a new object on save
        duplicate.rsa_key = None  # Ensure a new RSA key is generated
        duplicate.slug = None  # Ensure a new slug is generated

        # Set the name (no prefix)
        duplicate.name = obj.name

        # Set published to False
        duplicate.published = False

        # Adjust the date based on the date_adjustment parameter
        if date_adjustment == "day":
            # Add 1 day to the date
            duplicate.datetime = obj.datetime + timedelta(days=1)
            if obj.end_datetime:
                duplicate.end_datetime = obj.end_datetime + timedelta(days=1)
        elif date_adjustment == "week":
            # Add 7 days to the date
            duplicate.datetime = obj.datetime + timedelta(days=7)
            if obj.end_datetime:
                duplicate.end_datetime = obj.end_datetime + timedelta(days=7)
        elif date_adjustment == "week2":
            # Add 14 days to the date
            duplicate.datetime = obj.datetime + timedelta(days=14)
            if obj.end_datetime:
                duplicate.end_datetime = obj.end_datetime + timedelta(days=14)
        elif date_adjustment == "month":
            # Add 1 month to the date
            from dateutil.relativedelta import relativedelta
            duplicate.datetime = obj.datetime + relativedelta(months=1)
            if obj.end_datetime:
                duplicate.end_datetime = obj.end_datetime + relativedelta(months=1)

        # Save the duplicate
        duplicate.save()

        # Copy many-to-many relationships
        duplicate.products.set(obj.products.all())
        duplicate.tag.set(obj.tag.all())
        # duplicate.options_radio.set(obj.options_radio.all())
        # duplicate.options_checkbox.set(obj.options_checkbox.all())
        duplicate.carrousel.set(obj.carrousel.all())

        # Duplicate child events of type ACTION
        for child in obj.children.filter(categorie=Event.ACTION):
            child_duplicate = Event.objects.get(uuid=child.uuid)
            child_duplicate.pk = None  # This will create a new object on save
            child_duplicate.rsa_key = None  # Ensure a new RSA key is generated
            child_duplicate.slug = None  # Ensure a new slug is generated
            child_duplicate.parent = duplicate

            # Child events should be published
            child_duplicate.published = True

            # Adjust the date based on the date_adjustment parameter
            if date_adjustment == "day":
                # Add 1 day to the date
                child_duplicate.datetime = child.datetime + timedelta(days=1)
                if child.end_datetime:
                    child_duplicate.end_datetime = child.end_datetime + timedelta(days=1)
            elif date_adjustment == "week":
                # Add 7 days to the date
                child_duplicate.datetime = child.datetime + timedelta(days=7)
                if child.end_datetime:
                    child_duplicate.end_datetime = child.end_datetime + timedelta(days=7)
            elif date_adjustment == "week2":
                # Add 14 days to the date
                child_duplicate.datetime = child.datetime + timedelta(days=14)
                if child.end_datetime:
                    child_duplicate.end_datetime = child.end_datetime + timedelta(days=14)
            elif date_adjustment == "month":
                # Add 1 month to the date
                from dateutil.relativedelta import relativedelta
                child_duplicate.datetime = child.datetime + relativedelta(months=1)
                if child.end_datetime:
                    child_duplicate.end_datetime = child.end_datetime + relativedelta(months=1)

            child_duplicate.save()

            # Copy many-to-many relationships for child
            child_duplicate.products.set(child.products.all())
            child_duplicate.tag.set(child.tag.all())
            # child_duplicate.options_radio.set(child.options_radio.all())
            # child_duplicate.options_checkbox.set(child.options_checkbox.all())
            child_duplicate.carrousel.set(child.carrousel.all())

        return duplicate

    @admin.action(description=_("Approve and publish selected proposals"))
    def approuver_propositions(self, request, queryset):
        """
        Action bulk : pour chaque event selectionne qui est une proposition
        en attente, set is_proposal=False + published=True.
        / Bulk action: approve and publish selected pending proposals.

        IMPORTANT (cf. CHANTIER-08) : on publie via save() par instance, et NON
        via queryset.update() en masse. .update() ne declenche PAS le signal
        post_save declencher_refresh_seo_cache -> sans lui, l'event approuve
        n'apparait sur la carte reseau qu'au prochain beat 4h. save() declenche
        le signal -> rebuild SEO debounce -> l'event apparait en ~15s.
        / We publish with per-instance save(), NOT bulk queryset.update():
        .update() does not fire the post_save signal that refreshes the SEO
        cache, so the approved event would only appear on the network map at the
        next 4h beat. save() fires the signal -> debounced SEO rebuild.
        """
        propositions_en_attente = queryset.filter(is_proposal=True, published=False)
        nb_approuvees = 0
        for proposition in propositions_en_attente:
            proposition.is_proposal = False
            proposition.published = True
            proposition.save(update_fields=["is_proposal", "published"])
            nb_approuvees += 1
        self.message_user(
            request,
            _("%(n)s proposal(s) approved.") % {"n": nb_approuvees},
            messages.SUCCESS,
        )


class ReservationValidFilter(admin.SimpleListFilter):
    # Pour filtrer sur les réservation valide : payée, payée et confirmée, et mail en erreur même si payés
    title = _("Valid")

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "status_valid"

    def lookups(self, request, model_admin):
        return [
            # ("Y", _("Yes")),
            ("N", _("Invalids")),
        ]

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        value = self.value()
        if value == None:  # valeur par défault
            return queryset.exclude(
                status__in=[
                    Reservation.CANCELED,
                    Reservation.CREATED,
                    Reservation.UNPAID,
                ]
            ).distinct()

        if value == "N":
            return queryset.filter(
                status__in=[
                    Reservation.CANCELED,
                    Reservation.CREATED,
                    Reservation.UNPAID,
                ]
            ).distinct()


def _build_event_price_options():
    """
    Construit les choix du select tarif du formulaire d'ajout de réservation :
    une option par couple (évènement, tarif).
    / Builds the rate select choices: one option per (event, rate) pair.

    Un même tarif (Product/Price) peut être partagé par plusieurs évènements —
    typiquement "Réservation gratuite", rattaché à tous les évènements gratuits.
    On génère donc une entrée distincte PAR évènement ; sinon les évènements qui
    partagent un tarif n'auraient pas d'entrée propre et seraient invisibles.
    / A rate can be shared across several events (e.g. "Free booking" linked to
      every free event), so we emit one entry per event; otherwise events sharing
      a rate would have no entry of their own and stay invisible.

    Valeur : "event_uuid:price_uuid" — l'évènement est explicite (pas de
    déduction ambiguë). Libellé cherchable : "03/07 - Évènement - Tarif - prix€".
    / Value: "event_uuid:price_uuid" (explicit event). Searchable label.

    La source est la même que la billetterie publique : event.products -> prices.
    / Same source as the public ticketing: event.products -> prices.

    Renvoie un tuple (choix, donnees) :
    - choix : liste [(valeur, libellé)] pour le ChoiceField.
    - donnees : dict {valeur: {"prix": float, "libre": bool}} pour le JS
      d'auto-remplissage du champ "Prix par billet".
    / Returns (choices, data): choices for the ChoiceField, and a {value: {...}}
      map used by the per-ticket price autofill JS.
    """
    limite_date = timezone.localtime() - timedelta(days=1)
    evenements = (
        Event.objects.filter(datetime__gte=limite_date)
        .order_by("datetime")
        .prefetch_related("products__prices")
    )
    choix = [("", _("Choisir un tarif"))]
    donnees = {}
    for evenement in evenements:
        date_affichee = evenement.datetime.strftime("%d/%m")
        for produit in evenement.products.all():
            for tarif in produit.prices.filter(archived=False):
                valeur = f"{evenement.uuid}:{tarif.uuid}"
                libelle = f"{date_affichee} - {evenement.name} - {tarif.name} - {tarif.prix}€"
                choix.append((valeur, libelle))
                donnees[valeur] = {"prix": float(tarif.prix), "libre": bool(tarif.free_price)}
    return choix, donnees


class ReservationAddAdmin(ModelForm):
    email = forms.EmailField(
        required=True,
        widget=UnfoldAdminEmailInputWidget(),
        label="Email",
    )

    # Une option par couple (évènement, tarif) — voir _build_event_price_choices.
    # Les choix sont construits dans __init__ (une requête à chaque affichage du
    # formulaire). La valeur est "event_uuid:price_uuid".
    # / One option per (event, rate) pair — see _build_event_price_choices.
    #   Choices are built in __init__. Value is "event_uuid:price_uuid".
    price = forms.ChoiceField(
        required=True,
        widget=UnfoldAdminSelect2Widget,
        label=_("Rate"),
        help_text=_("Tarif d'un évènement à venir. Le produit vendu est créé automatiquement si besoin."),
    )

    # Prix PAR billet (montant unitaire). Rempli automatiquement à la sélection
    # du tarif (JS), obligatoire pour un tarif à prix libre. Si laissé vide pour
    # un tarif normal, on utilise le prix du tarif. Le total = prix × quantité.
    # / Price PER ticket (unit amount). Auto-filled on rate selection (JS),
    #   required for an open-price rate. If left empty for a normal rate, the
    #   rate's price is used. Total = price × quantity.
    amount = forms.FloatField(
        required=False,
        min_value=0,
        widget=UnfoldAdminTextInputWidget(attrs={"type": "number", "step": "0.01", "min": "0"}),
        label=_("Prix par billet"),
        help_text=_("Montant payé pour UN billet (multiplié par la quantité). Obligatoire pour un tarif à prix libre."),
    )

    # options_checkbox = forms.ModelMultipleChoiceField(
    #     # Uniquement les options qui sont utilisé dans les évènements futurs
    #     required=False,
    #     queryset=OptionGenerale.objects.filter(
    #         options_checkbox__datetime__gte=timezone.localtime() - timedelta(days=1)),
    #     widget=UnfoldAdminCheckboxSelectMultiple(),
    #     label=_("Multiple choice menu"),
    # )
    #
    # options_radio = forms.ModelChoiceField(
    #     # Uniquement les options qui sont utilisé dans les évènements futurs
    #     required=False,
    #     queryset=OptionGenerale.objects.filter(options_radio__datetime__gte=timezone.localtime() - timedelta(days=1)),
    #     widget=UnfoldAdminRadioSelectWidget(),
    #     label=_("Single choice menu"),
    # )

    # Obligatoire, avec une option vide en tête : on force un choix conscient.
    # Sans ça, le 1er choix de PaymentMethod.classic() est "Offert" (FREE) et une
    # validation distraite créait une vente offerte par erreur.
    # / Required, with an empty first option: forces a conscious choice. Otherwise
    #   the first choice of PaymentMethod.classic() is "Offered" (FREE) and an
    #   inattentive submit created an offered sale by mistake.
    payment_method = forms.ChoiceField(
        required=True,
        choices=[("", _("Sélectionner un moyen de paiement"))] + PaymentMethod.classic(),
        widget=UnfoldAdminSelectWidget(),
        label=_("Payment method"),
    )

    quantity = forms.IntegerField(
        required=False,
        initial=1,
        min_value=1,
        max_value=32767,
        widget=UnfoldAdminTextInputWidget(attrs={"type": "number", "min": "1"}),
        label=_("Quantity"),
    )

    class Meta:
        model = Reservation
        fields = []
        # 'first_name',
        # 'last_name',
        # ]

    class Media:
        # JS d'auto-remplissage du "Prix par billet" à la sélection du tarif.
        # / JS that autofills the per-ticket price on rate selection.
        js = ("admin/js/reservation_price_autofill.js",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Construction des choix du select tarif (une option par couple
        # évènement/tarif) et des données pour le JS d'auto-remplissage du prix.
        # / Build the rate choices (one per event/rate pair) and the data used by
        #   the price autofill JS.
        choix, donnees = _build_event_price_options()
        self.fields["price"].choices = choix
        # Le JS lit ce mapping {valeur: {prix, libre}} pour pré-remplir le montant
        # et rendre le champ obligatoire si le tarif est à prix libre.
        # / The JS reads this {value: {prix, libre}} map to prefill the amount and
        #   make the field required for open-price rates.
        self.fields["price"].widget.attrs["data-prices"] = json.dumps(donnees)

    @staticmethod
    def _extraire_evenement_et_tarif(valeur):
        """
        Décompose la valeur "event_uuid:price_uuid" du champ price en
        (Event, Price). Renvoie (None, None) si vide ou invalide.
        / Splits the "event_uuid:price_uuid" value into (Event, Price).
        """
        if not valeur or ":" not in valeur:
            return None, None
        event_uuid, price_uuid = valeur.split(":", 1)
        try:
            evenement = Event.objects.get(uuid=event_uuid)
            tarif = Price.objects.get(uuid=price_uuid, archived=False)
        except (Event.DoesNotExist, Price.DoesNotExist, ValueError):
            return None, None
        return evenement, tarif

    def clean_payment_method(self):
        cleaned_data = self.cleaned_data
        # Le champ "price" vaut "event_uuid:price_uuid" : on récupère le tarif
        # pour vérifier la cohérence avec la méthode de paiement.
        # / "price" is "event_uuid:price_uuid": fetch the rate to check coherence.
        _evenement, tarif = self._extraire_evenement_et_tarif(cleaned_data.get('price'))
        payment_method = cleaned_data.get('payment_method')
        # On ne valide la méthode de paiement que si on a un tarif.
        # / Only check the payment method when a rate is set.
        if tarif and tarif.product.categorie_article == Product.FREERES and payment_method != PaymentMethod.FREE:
            raise forms.ValidationError(_("Une reservation gratuite doit être en paiement OFFERT"), code="invalid")
        return payment_method

    def clean(self):
        cleaned_data = super().clean()
        _evenement, tarif = self._extraire_evenement_et_tarif(cleaned_data.get('price'))
        montant = cleaned_data.get('amount')
        payment_method = cleaned_data.get('payment_method')
        # Pour un tarif à prix libre payant, le prix par billet est obligatoire
        # (le tarif n'a pas de prix fixe à appliquer).
        # / For a paid open-price rate, the per-ticket price is required
        #   (there is no fixed rate price to apply).
        if tarif and tarif.free_price and payment_method != PaymentMethod.FREE:
            if montant is None or montant <= 0:
                self.add_error('amount', _("Indiquez le prix par billet pour un tarif à prix libre."))
        return cleaned_data

    def save(self, commit=True):
        cleaned_data = self.cleaned_data

        # Le champ "email" est un EmailField : l'admin saisit une adresse.
        # get_or_create_user retrouve le compte ou le cree, et l'associe au
        # tenant courant. send_mail=False : pas de mail de validation, la
        # reservation est creee directement cote admin.
        # / The "email" field is an EmailField: get_or_create_user finds or
        #   creates the account (linked to the current tenant), no validation mail.
        email = self.cleaned_data.pop('email')
        user = get_or_create_user(email, send_mail=False)

        # Le champ "price" vaut "event_uuid:price_uuid" : l'évènement est
        # explicite (un même tarif peut être partagé entre plusieurs évènements).
        # On matérialise le produit vendu (ProductSold) et le tarif vendu
        # (PriceSold) si besoin : ils n'existent qu'après une première vente.
        # / "price" is "event_uuid:price_uuid": the event is explicit (a rate can
        #   be shared across events). Materialize ProductSold/PriceSold if needed.
        event, price = self._extraire_evenement_et_tarif(cleaned_data.pop('price'))
        productsold, _created = ProductSold.objects.get_or_create(
            product=price.product, event=event,
        )
        pricesold, _created = PriceSold.objects.get_or_create(
            productsold=productsold, price=price, prix=price.prix,
        )

        reservation: Reservation = self.instance
        reservation.user_commande = user
        reservation.event = event
        reservation.status = Reservation.VALID  # automatiquement en VALID,on est sur l'admin
        # On va chercher les options
        # options_checkbox = cleaned_data.pop('options_checkbox')
        # if options_checkbox:
        #     reservation.options.set(options_checkbox)
        # options_radio = cleaned_data.pop('options_radio')
        # if options_radio:
        #     reservation.options.add(options_radio)

        reservation = super().save(commit=commit)

        ### Création des billets associés
        payment_method = self.cleaned_data.pop('payment_method')
        quantity = self.cleaned_data.pop('quantity', 1) or 1
        montant_saisi = self.cleaned_data.pop('amount', None)
        for _ in range(quantity):
            Ticket.objects.create(
                payment_method=payment_method,
                reservation=reservation,
                status=Ticket.NOT_SCANNED,
                sale_origin=SaleOrigin.ADMIN,
                pricesold=pricesold,
            )

        # Prix unitaire PAR billet : le montant saisi s'il est fourni, sinon le
        # prix du tarif.
        # / Per-ticket price: the typed amount if provided, else the rate's price.
        if montant_saisi is not None and montant_saisi != '':
            prix_unitaire = dround(Decimal(str(montant_saisi)))
        else:
            prix_unitaire = pricesold.prix

        # LigneArticle.amount est le montant UNITAIRE en centimes : la quantité
        # est portée par le champ qty, et le total = amount × qty (cf.
        # comptabilite/services.py et LigneArticle.total()). Ne PAS multiplier
        # par quantity ici, sinon double comptage (amount × qty²).
        # / LigneArticle.amount is the UNIT amount in cents: quantity is held by
        #   the qty field and total = amount × qty. Do NOT multiply by quantity
        #   here, otherwise it is double-counted (amount × qty²).
        # Un billet « offert » garde le prix du tarif : il est écrit comme un offert
        # de la caisse (part offerte = total, règlement FREE posé par le service).
        # / An "offered" ticket keeps the rate's price, like a register gift.
        amount = dec_to_int(prix_unitaire)

        # La vente de l'admin : écrite par le service de vente, puis encaissée tout de
        # suite (l'argent est déclaré reçu par le gestionnaire). Elle est écrite dans
        # la transaction de l'admin (changeform_view est atomic) : réservation,
        # billets, ligne et vente sont enregistrés ensemble, ou pas du tout.
        # / The admin sale: written by the sale service, settled at once, inside the
        #   admin's transaction.
        # Client = l'acheteur ; opérateur vide (aucune carte de caisse dans l'admin).
        # / Client = the buyer; no operator in the admin.
        vente_de_l_admin = ouvrir_vente(
            origine=SaleOrigin.ADMIN,
            nature=Vente.Nature.VENTE,
            client=user,
        )
        billet_offert = payment_method == PaymentMethod.FREE
        ligne_des_billets = ajouter_article(
            vente_de_l_admin,
            pricesold=pricesold,
            quantite=quantity,
            prix_unitaire=amount,
            taux_tva=_taux_tva_de_la_ligne_de_caisse(price.product, payment_method),
            offert_en_totalite=billet_offert,
            payment_method=payment_method,
            status=LigneArticle.VALID,
            sale_origin=SaleOrigin.ADMIN,
            reservation=reservation,
        )

        # Un seul règlement d'argent, au moyen choisi, du montant total. Rien pour un
        # billet offert (le service a posé le règlement FREE) ni pour un total de 0
        # (une vente gratuite n'a aucun règlement).
        # / One money payment at the chosen method for the total. None for an offered
        #   ticket (FREE payment set by the service) nor for a 0 total.
        total_des_billets = ligne_des_billets.total_catalogue
        if not billet_offert and total_des_billets != 0:
            ajouter_reglement(
                vente_de_l_admin,
                moyen=payment_method,
                montant=total_des_billets,
            )

        # Encaissement en dernier, avant toute tâche Celery.
        # / Settle last, before any Celery task.
        encaisser_vente(vente_de_l_admin)

        # Une vente faite dans l'admin n'est pas envoyée à l'ancienne caisse LaBoutik.
        # Seul le mail des billets part.
        # / A sale made in the admin is not sent to the legacy LaBoutik register.
        #   Only the tickets mail is sent.
        ticket_celery_mailer.delay(reservation.pk)

        return reservation


class ReservationCustomFormSection(TemplateSection):
    template_name = "admin/reservation/custom_form_section.html"
    verbose_name = _("Custom form answers")


class EventArchivedFilter(DropdownFilter):
    # Liste déroulante avec recherche (Unfold) : la liste des événements est trop longue
    # pour être affichée en liens. Envoyée par le bouton « Filtrer ».
    # / Searchable dropdown (Unfold): the event list is too long for links.
    title = _("Archived Event")
    parameter_name = 'event_archived'

    def lookups(self, request, model_admin):
        events = Event.objects.filter(archived=True).order_by('-datetime')
        return [(str(e.pk), str(e)) for e in events]

    def queryset(self, request, queryset):
        if self.value():
            if queryset.model == Reservation:
                return queryset.filter(event_id=self.value())
            elif queryset.model == Ticket:
                return queryset.filter(reservation__event_id=self.value())
        return queryset


class EventFutureFilter(DropdownFilter):
    # Liste déroulante avec recherche (Unfold) : la liste des événements est trop longue
    # pour être affichée en liens. Envoyée par le bouton « Filtrer ».
    # / Searchable dropdown (Unfold): the event list is too long for links.
    title = _("-> Future event")
    parameter_name = 'event_future'

    def lookups(self, request, model_admin):
        now = timezone.now() - timedelta(days=1)
        events = Event.objects.filter(archived=False, datetime__gte=now).order_by('datetime')
        return [(str(e.pk), str(e)) for e in events]

    def queryset(self, request, queryset):
        if self.value():
            if queryset.model == Reservation:
                return queryset.filter(event_id=self.value())
            elif queryset.model == Ticket:
                return queryset.filter(reservation__event_id=self.value())
        return queryset


class EventPastFilter(DropdownFilter):
    # Liste déroulante avec recherche (Unfold) : la liste des événements est trop longue
    # pour être affichée en liens. Envoyée par le bouton « Filtrer ».
    # / Searchable dropdown (Unfold): the event list is too long for links.
    title = _("<- Past event")
    parameter_name = 'event_past'

    def lookups(self, request, model_admin):
        now = timezone.now()
        events = Event.objects.filter(archived=False, datetime__lt=now).order_by('-datetime')
        return [(str(e.pk), str(e)) for e in events]

    def queryset(self, request, queryset):
        if self.value():
            if queryset.model == Reservation:
                return queryset.filter(event_id=self.value())
            elif queryset.model == Ticket:
                return queryset.filter(reservation__event_id=self.value())
        return queryset


def preparer_le_champ_rembourse_par(lignes_hors_stripe):
    """
    Décide si l'écran d'annulation affiche le champ « Remboursé par », et avec quel
    moyen pré-rempli.
    / Decides whether the cancel screen shows the "Refunded by" field, and its initial
    method.

    LOCALISATION : Administration/admin_tenant.py
    (utilisé par `afficher_ou_valider_l_ecran_d_annulation`)

    RÈGLES :
    - champ affiché seulement si au moins une ligne hors Stripe a de l'argent à rendre
      (ni entièrement offerte, ni payée en jetons cadeau : `ligne_sans_argent_a_rendre`) ;
    - pré-rempli si TOUTES ces lignes ont le même moyen d'origine, et qu'il est dans
      la liste du champ (espèces, CB, chèque, virement) ; sinon vide. Le moyen
      d'origine d'une ligne est le seul moyen d'argent des règlements nets de sa vente
      (`moyen_d_origine_de_la_ligne`).
    / Field shown only when a non-Stripe line has money to give back; pre-filled when
    all those lines share the same original method (read from their sale's payments)
    from the field's list.

    :param lignes_hors_stripe: les `LigneArticle` hors Stripe de la sélection
    :return: (champ_demande, moyen_pre_rempli) ; moyen_pre_rempli vaut None si vide
    """
    moyens_d_origine_de_l_argent_a_rendre = []
    for ligne in lignes_hors_stripe:
        if ligne_sans_argent_a_rendre(ligne):
            continue
        moyens_d_origine_de_l_argent_a_rendre.append(moyen_d_origine_de_la_ligne(ligne))

    champ_demande = len(moyens_d_origine_de_l_argent_a_rendre) > 0
    if not champ_demande:
        return False, None

    premier_moyen = moyens_d_origine_de_l_argent_a_rendre[0]
    tous_les_moyens_identiques = True
    for moyen_d_origine in moyens_d_origine_de_l_argent_a_rendre:
        if moyen_d_origine != premier_moyen:
            tous_les_moyens_identiques = False

    if tous_les_moyens_identiques and premier_moyen in MOYENS_DU_CHAMP_REMBOURSE_PAR:
        return True, premier_moyen
    return True, None


def afficher_ou_valider_l_ecran_d_annulation(
    model_admin, request, objets_coches, lignes_hors_stripe, descriptions_des_objets
):
    """
    L'écran intermédiaire des actions admin d'annulation (réservations, billets).
    / The intermediate screen of the admin cancel actions (reservations, tickets).

    LOCALISATION : Administration/admin_tenant.py
    Gabarit : Administration/templates/admin/annulation/confirmer_annulation.html

    FLUX (comme la confirmation de suppression de Django) :
    1. 1er POST de la liste (l'admin lance l'action) : l'écran est rendu, rien n'est
       annulé ;
    2. 2e POST de l'écran (`post=yes`, plus `moyen_rembourse` si le champ est
       affiché) : formulaire valide → l'appelant annule ; formulaire refusé (champ
       vide) → l'écran revient, avec l'erreur.
    / First POST = screen; second POST (`post=yes`) = cancel if the form is valid,
    screen again otherwise.

    Un seul moyen vaut pour toute la sélection.
    / One method applies to the whole selection.

    :param model_admin: le ModelAdmin de la liste (réservations ou billets)
    :param request: la requête de l'action
    :param objets_coches: les objets cochés (réservations ou billets)
    :param lignes_hors_stripe: les `LigneArticle` hors Stripe touchées par l'annulation
    :param descriptions_des_objets: une ligne de texte par objet coché, pour l'écran
    :return: (reponse_de_l_ecran, moyen_choisi) : la réponse à rendre (écran) ou None ;
        le moyen choisi (None sans champ) quand le formulaire est valide
    """
    champ_demande, moyen_pre_rempli = preparer_le_champ_rembourse_par(lignes_hors_stripe)
    confirmation_envoyee = request.POST.get("post") == "yes"

    if confirmation_envoyee:
        if champ_demande:
            formulaire = EmettreAvoirAvecMoyenForm(request.POST)
        else:
            formulaire = EmettreAvoirSansMoyenForm(request.POST)
        if formulaire.is_valid():
            moyen_choisi = formulaire.cleaned_data.get("moyen_rembourse") or None
            return None, moyen_choisi
    else:
        valeurs_initiales = {}
        if moyen_pre_rempli is not None:
            valeurs_initiales["moyen_rembourse"] = moyen_pre_rempli
        if champ_demande:
            formulaire = EmettreAvoirAvecMoyenForm(initial=valeurs_initiales)
        else:
            formulaire = EmettreAvoirSansMoyenForm()

    cles_des_objets_coches = []
    for objet_coche in objets_coches:
        cles_des_objets_coches.append(str(objet_coche.pk))

    options_du_modele = model_admin.model._meta
    url_de_la_liste = reverse(
        f"{model_admin.admin_site.name}:{options_du_modele.app_label}_{options_du_modele.model_name}_changelist"
    )
    contexte_de_l_ecran = {
        **model_admin.admin_site.each_context(request),
        "title": _("Annuler et rembourser"),
        "opts": options_du_modele,
        "form": formulaire,
        "champ_rembourse_par_demande": champ_demande,
        "nom_de_l_action": request.POST.get("action", ""),
        "cles_des_objets_coches": cles_des_objets_coches,
        "descriptions_des_objets": descriptions_des_objets,
        "url_de_la_liste": url_de_la_liste,
    }
    reponse_de_l_ecran = render(
        request,
        "admin/annulation/confirmer_annulation.html",
        contexte_de_l_ecran,
    )
    return reponse_de_l_ecran, None


@admin.register(Reservation, site=staff_admin_site)
class ReservationAdmin(ModelAdmin):
    # Expandable section to display custom form answers in changelist
    list_sections = [ReservationCustomFormSection]

    # Formulaire de création. A besoin de get_form pour fonctionner
    add_form = ReservationAddAdmin
    autocomplete_fields = ["event",]

    # custom_form (les réponses au formulaire personnalisé) n'est plus affiché en JSON brut
    # dans le formulaire. Il est affiché en tableau, en lecture seule, sous le formulaire :
    # voir change_form_after_template. Même affichage que la fiche adhésion.
    # / custom_form is no longer shown as raw JSON: read-only table below the form.
    exclude = ["commande", "custom_form"]
    change_form_after_template = "admin/reservation/custom_form.html"

    def get_form(self, request, obj=None, **kwargs):
        """ Si c'est un add, on modifie le formulaire"""
        defaults = {}
        if obj is None:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    def get_readonly_fields(self, request, obj=None):
        # Sur la page de modification, tous les champs sont en lecture seule.
        # La page d'ajout n'est pas concernée : elle utilise ReservationAddAdmin.
        # / On the change page, every field is read-only. The add page uses ReservationAddAdmin.
        #
        # - status : piloté par la machine à états (BaseBillet/signals.py). Un statut changé
        #   à la main ne déclenche pas les bonnes transitions : les billets peuvent rester inactifs.
        # - user_commande : INDISPENSABLE en lecture seule. Les utilisateurs sont partagés entre
        #   tous les lieux (AuthBillet est en SHARED_APPS). Modifiable, ce champ devient une
        #   liste déroulante de TOUS les comptes de l'instance : la page met très longtemps à s'ouvrir.
        # - event, options, to_mail, mail_send, mail_error : une réservation existante ne se
        #   modifie pas à la main. On passe par les boutons d'action (envoi, annulation).
        # / user_commande MUST stay read-only: users are shared across all tenants, an editable
        #   field renders a select of every account of the instance (very slow page).
        if obj:
            return (
                "status",
                "user_commande",
                "event",
                "options",
                "to_mail",
                "mail_send",
                "mail_error",
            )
        return ()

    list_display = (
        'datetime',
        'user_commande',
        'event',
        'status',
        'tickets_count',
        # 'options_str',
        'total_paid',
    )
    # readonly_fields = list_display

    search_fields = ['event__name', 'user_commande__email', 'datetime', 'custom_form']
    list_filter = [
        EventFutureFilter,
        EventPastFilter,
        ReservationValidFilter,
        'datetime',
        # 'options',
        EventArchivedFilter,
    ]

    # Bulk actions available in changelist
    actions = ["action_cancel_refund_reservations"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return (
            queryset
            .select_related('user_commande', 'event')
            .prefetch_related(
                # 'options',
                'tickets',
                'tickets__pricesold__price__product__form_fields',
            )
        )

    @admin.action(description=_("Cancel and refund selected reservations"))
    def action_cancel_refund_reservations(self, request, queryset):
        """
        Annule et rembourse les réservations cochées, après un écran de confirmation.
        / Cancels and refunds the ticked reservations, after a confirmation screen.

        LOCALISATION : Administration/admin_tenant.py

        FLUX :
        1. l'écran (`afficher_ou_valider_l_ecran_d_annulation`) : champ « Remboursé par »
           si une ligne hors Stripe a de l'argent à rendre ;
        2. formulaire valide : `cancel_and_refund_resa(annulation_par_l_admin=True,
           moyen_rembourse=…)` pour chaque réservation (Stripe : remboursement ; hors
           Stripe : un avoir par ligne), puis le mail d'annulation.
        / Screen first, then each reservation is cancelled by the admin with the chosen
        method, then the cancellation mail.
        """
        # Only operate on queryset of reservations; prefetch to reduce queries
        qs = queryset.select_related('user_commande', 'event').prefetch_related('tickets')

        reservations_cochees = list(qs)
        lignes_hors_stripe_de_la_selection = []
        descriptions_des_reservations = []
        for reservation_cochee in reservations_cochees:
            for ligne_hors_stripe in reservation_cochee._lignes_hors_stripe():
                lignes_hors_stripe_de_la_selection.append(ligne_hors_stripe)
            descriptions_des_reservations.append(
                f"{reservation_cochee.event} — {reservation_cochee}"
            )
        reponse_de_l_ecran, moyen_choisi = afficher_ou_valider_l_ecran_d_annulation(
            self,
            request,
            reservations_cochees,
            lignes_hors_stripe_de_la_selection,
            descriptions_des_reservations,
        )
        if reponse_de_l_ecran is not None:
            return reponse_de_l_ecran

        success_count = 0
        errors = []
        for resa in reservations_cochees:
            try:
                msg = resa.cancel_and_refund_resa(
                    annulation_par_l_admin=True,
                    moyen_rembourse=moyen_choisi,
                )
                try:
                    send_reservation_cancellation_user.delay(str(resa.uuid))
                except Exception as ce:
                    logger.error(f"Failed to queue reservation cancellation email for {resa.uuid}: {ce}")
                success_count += 1
            except Exception as e:
                errors.append(str(e))
        if success_count:
            messages.success(request, _("%(count)d reservation(s) cancelled and refunded.") % {"count": success_count})
        if errors:
            unique_errors = list(dict.fromkeys(errors))
            preview = " | ".join(unique_errors[:5])
            if len(unique_errors) > 5:
                preview += _(" ... (%(more)d more)") % {"more": len(unique_errors) - 5}
            messages.error(request, _("Some reservations failed to cancel/refund: %(errors)s") % {"errors": preview})

    @display(description=_("Ticket count"))
    def tickets_count(self, instance: Reservation):
        return instance.tickets.filter(status__in=[Ticket.SCANNED, Ticket.NOT_SCANNED]).count()

    # @display(description=_("Options"))
    # def options_str(self, instance: Reservation):
    #     return " - ".join([option.name for option in instance.options.all()])

    # Deux boutons d'envoi, jamais affichés en même temps :
    # - « renvoyer les billets » : la réservation a au moins un billet valide ;
    # - « valider et envoyer » : la réservation attend la validation du mail (FREERES).
    # / Two sending buttons, never shown together.
    actions_detail = ["send_ticket_to_mail", "validate_and_send_ticket_to_mail", ]

    @action(
        description=_("Send tickets through email again"),
        url_path="send_ticket_to_mail",
        permissions=["send_ticket_to_mail"],
    )
    def send_ticket_to_mail(self, request, object_id):
        reservation = Reservation.objects.get(pk=object_id)
        ticket_celery_mailer.delay(reservation.pk)
        messages.success(
            request,
            _(f"Tickets sent to {reservation.user_commande.email}"),
        )
        page_precedente = request.META.get(
            "HTTP_REFERER",
            reverse("staff_admin:BaseBillet_reservation_change", args=[object_id]),
        )
        return redirect(page_precedente)

    @action(
        description=_("Valider et envoyer par mail"),
        url_path="validate_and_send_ticket_to_mail",
        permissions=["validate_and_send_ticket_to_mail"],
    )
    def validate_and_send_ticket_to_mail(self, request, object_id):
        """
        Valide une réservation gratuite en attente du mail, puis envoie les billets.
        / Validates a free booking waiting for email validation, then sends the tickets.

        LOCALISATION : Administration/admin_tenant.py

        Le bouton n'apparaît que si la réservation est en FREERES (F).
        Voir has_validate_and_send_ticket_to_mail_permission.

        Pas de contrôle de jauge ici : l'admin valide en connaissance de cause.
        Le compte de l'utilisateur reste non activé : seule la réservation est validée.
        / No capacity check: the admin validates on purpose. The user account stays inactive.

        FLUX :
        1. Le statut passe de FREERES (F) à FREERES_USERACTIV (FA), puis save().
        2. Le signal pre_save_signal_status (BaseBillet/signals.py) appelle reservation_paid.
        3. reservation_paid passe les billets NOT_ACTIV en NOT_SCANNED.
        4. Si mail_send vaut False et que l'utilisateur a un email,
           reservation_paid lance ticket_celery_mailer (Celery, asynchrone), qui envoie les PDF.
        5. Si le mail part, ticket_celery_mailer passe la réservation en VALID.
        """
        reservation = Reservation.objects.get(pk=object_id)
        reservation.status = Reservation.FREERES_USERACTIV
        reservation.save()
        messages.success(
            request,
            _("Réservation validée. Envoi des billets demandé à %(email)s") % {"email": reservation.user_commande.email},
        )
        page_precedente = request.META.get(
            "HTTP_REFERER",
            reverse("staff_admin:BaseBillet_reservation_change", args=[object_id]),
        )
        return redirect(page_precedente)

    def has_send_ticket_to_mail_permission(self, request, object_id):
        # Bouton « renvoyer les billets » : affiché seulement s'il y a au moins un billet valide.
        # Sans billet valide (attente du mail, annulée, non payée), le mail partirait sans PDF,
        # et ticket_celery_mailer forcerait quand même la réservation en VALID.
        # Unfold appelle cette méthode pour afficher le bouton ET à l'appel de l'URL.
        # / "Resend tickets" button: shown only if the booking has at least one valid ticket.
        if not TenantAdminPermissionWithRequest(request):
            return False
        reservation_a_au_moins_un_billet_valide = Ticket.objects.filter(
            reservation_id=object_id,
            status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED],
        ).exists()
        return reservation_a_au_moins_un_billet_valide

    def has_validate_and_send_ticket_to_mail_permission(self, request, object_id):
        # Bouton « valider et envoyer » : affiché seulement si la réservation attend
        # la validation du mail (FREERES).
        # / "Validate and send" button: shown only for bookings waiting for email validation.
        if not TenantAdminPermissionWithRequest(request):
            return False
        reservation_attend_la_validation_du_mail = Reservation.objects.filter(
            pk=object_id, status=Reservation.FREERES,
        ).exists()
        return reservation_attend_la_validation_du_mail

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        # Allow bulk actions in changelist for authorized tenant admins
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False


class TicketChangeAdmin(ModelForm):
    class Meta:
        model = Ticket
        fields = [
            'first_name',
            'last_name',
        ]


class TicketValidFilter(admin.SimpleListFilter):
    # Pour filtrer sur les réservation valide : payée, payée et confirmée, et mail en erreur même si payés
    title = _("Valid")

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "status_valid"

    def lookups(self, request, model_admin):
        return [
            # ("Y", _("Yes")),
            ("N", _("No")),
        ]

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if self.value() == None:
            return queryset.filter(
                status__in=[
                    Ticket.NOT_SCANNED,
                    Ticket.SCANNED,
                ]
            ).distinct()
        if self.value() == "N":
            return queryset.exclude(
                status__in=[
                    Ticket.NOT_SCANNED,
                    Ticket.SCANNED,
                ]
            ).distinct()


class TicketCustomFormSection(TemplateSection):
    template_name = "admin/ticket/custom_form_section.html"
    verbose_name = _("Custom form answers")


@admin.register(Ticket, site=staff_admin_site)
class TicketAdmin(ExportCsvLisibleParExcelMixin, ModelAdmin, ExportActionModelAdmin):
    ordering = ('-reservation__datetime',)
    list_filter = [
        EventFutureFilter,
        EventPastFilter,
        TicketValidFilter,
        "reservation__datetime",
        # "reservation__options",
        EventArchivedFilter,
    ]
    search_fields = (
        'uuid',
        'first_name',
        'last_name',
        'reservation__user_commande__email',
        'reservation__custom_form',
    )

    list_display = [
        'ticket',
        # 'first_name',
        # 'last_name',
        'event',
        # 'options',
        'product_name',
        'price_name',
        'state',
        'scan',
        'reservation__datetime',
    ]

    resource_classes = [TicketExportResource]
    export_form_class = ExportForm

    actions = ["action_unscan_selected", "action_cancel_refund_selected"]

    # Expandable section to display parent reservation custom form answers
    list_sections = [TicketCustomFormSection]

    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    # Formulaire de modification
    form = TicketChangeAdmin

    @admin.action(description=_("Unscan selected tickets"))
    def action_unscan_selected(self, request, queryset):
        updated = 0
        skipped = 0
        for ticket in queryset.select_related('reservation'):
            if ticket.status == Ticket.SCANNED:
                ticket.status = Ticket.NOT_SCANNED
                ticket.save()
                updated += 1
            else:
                skipped += 1
        if updated:
            messages.success(request, _("%(count)d ticket(s) unscanned successfully.") % {"count": updated})
        if skipped:
            messages.info(request, _("%(count)d ticket(s) were not scanned and were skipped.") % {"count": skipped})

    @admin.action(description=_("Cancel and refund"))
    def action_cancel_refund_selected(self, request, queryset):
        """
        Annule et rembourse les billets cochés, après un écran de confirmation. Tous
        les billets d'une réservation cochés : toute la réservation est annulée.
        / Cancels and refunds the ticked tickets, after a confirmation screen.

        LOCALISATION : Administration/admin_tenant.py

        FLUX :
        1. l'écran (`afficher_ou_valider_l_ecran_d_annulation`) : champ « Remboursé par »
           si une ligne hors Stripe a de l'argent à rendre ;
        2. formulaire valide : `cancel_and_refund_resa` ou `cancel_and_refund_ticket`
           avec `annulation_par_l_admin=True` et le moyen choisi, puis les mails.
        / Screen first, then the admin cancellation with the chosen method, then mails.
        """
        # Group selected tickets by reservation
        tickets = queryset.select_related(
            'reservation', 'reservation__event', 'reservation__user_commande', 'pricesold'
        )

        billets_coches = list(tickets)
        lignes_hors_stripe_de_la_selection = []
        descriptions_des_billets = []
        for billet_coche in billets_coches:
            # La ligne du billet est cherchée par son tarif (`Price`), comme
            # `cancel_and_refund_resa` et `cancel_and_refund_ticket` : la caisse écrit sa
            # ligne et ses billets sur deux tarifs vendus différents.
            # / The ticket's line is found by its Price, like the model methods.
            lignes_hors_stripe_du_billet = billet_coche.reservation._lignes_hors_stripe(
                price_ids=[billet_coche.pricesold.price_id]
            )
            for ligne_hors_stripe in lignes_hors_stripe_du_billet:
                lignes_hors_stripe_de_la_selection.append(ligne_hors_stripe)
            descriptions_des_billets.append(
                f"{billet_coche.reservation.event} — {billet_coche.pricesold} — "
                f"{billet_coche.reservation.user_commande.email}"
            )
        reponse_de_l_ecran, moyen_choisi = afficher_ou_valider_l_ecran_d_annulation(
            self,
            request,
            billets_coches,
            lignes_hors_stripe_de_la_selection,
            descriptions_des_billets,
        )
        if reponse_de_l_ecran is not None:
            return reponse_de_l_ecran

        res_to_tickets: Dict[str, Dict[str, Any]] = {}
        for t in billets_coches:
            resa_id = str(t.reservation_id)
            bucket = res_to_tickets.setdefault(resa_id, {"reservation": t.reservation, "tickets": []})
            bucket["tickets"].append(t)

        resa_success = 0
        ticket_success = 0
        errors = []

        for resa_id, bucket in res_to_tickets.items():
            resa = bucket["reservation"]
            selected_tickets = bucket["tickets"]
            try:
                total_in_resa = resa.tickets.count()
                if len(selected_tickets) == total_in_resa:
                    # All tickets of reservation selected -> cancel whole reservation
                    msg = resa.cancel_and_refund_resa(
                        annulation_par_l_admin=True,
                        moyen_rembourse=moyen_choisi,
                    )
                    try:
                        send_reservation_cancellation_user.delay(str(resa.uuid))
                    except Exception as ce:
                        logger.error(f"Failed to queue reservation cancellation email for {resa.uuid}: {ce}")
                    resa_success += 1
                else:
                    # Partial selection -> cancel each selected ticket
                    for t in selected_tickets:
                        try:
                            msg = resa.cancel_and_refund_ticket(
                                t,
                                annulation_par_l_admin=True,
                                moyen_rembourse=moyen_choisi,
                            )
                            try:
                                send_ticket_cancellation_user.delay(str(t.uuid))
                            except Exception as ce:
                                logger.error(f"Failed to queue ticket cancellation email for {t.uuid}: {ce}")
                            ticket_success += 1
                        except Exception as te:
                            errors.append(str(te))
            except Exception as e:
                errors.append(str(e))

        if resa_success:
            messages.success(request, _("%(count)d reservation(s) cancelled and refunded.") % {"count": resa_success})
        if ticket_success:
            messages.success(request, _("%(count)d ticket(s) cancelled and refunded.") % {"count": ticket_success})
        if errors:
            # Deduplicate and limit message length
            unique_errors = list(dict.fromkeys(errors))
            preview = " | ".join(unique_errors[:5])
            if len(unique_errors) > 5:
                preview += _(" ... (%(more)d more)") % {"more": len(unique_errors) - 5}
            messages.error(request, _("Some items failed to cancel/refund: %(errors)s") % {"errors": preview})

    @admin.display(ordering='pricesold__price', description=_('Price'))
    def price_name(self, obj: Ticket):
        if obj.pricesold:
            return obj.pricesold.price.name
        return ""

    @admin.display(ordering='pricesold__price', description=_('Product'))
    def product_name(self, obj: Ticket):
        if obj.pricesold:
            return obj.pricesold.price.product.name
        return ""

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return (
            queryset
            .select_related('reservation', 'reservation__event', 'reservation__event__parent',
                            'reservation__user_commande')
            .prefetch_related(
                # 'reservation__options',
                'reservation__tickets__pricesold__price__product__form_fields',
            )
        )

    @admin.display(ordering='reservation__datetime', description=_('Booked at'))
    def reservation__datetime(self, obj):
        return obj.reservation.datetime

    @admin.display(ordering='reservation__event', description='Event')
    def event(self, obj):
        if obj.reservation.event.parent:
            return f"{obj.reservation.event.parent} -> {obj.reservation.event}"
        return obj.reservation.event

    # noinspection PyTypeChecker
    @display(description=_("State"), label={None: "danger", True: "success", 'scanned': "warning"})
    def state(self, obj: Ticket):
        if obj.status == Ticket.NOT_SCANNED:
            return True, obj.get_status_display()
        elif obj.status == Ticket.SCANNED:
            return 'scanned', obj.get_status_display()
        # logger.info(f"state: {obj.status} - {obj.get_status_display()}")
        return None, obj.get_status_display()

    # noinspection PyTypeChecker
    @display(description=_("Scan"), label={True: "success"})
    def scan(self, obj: Ticket):
        if obj.status == Ticket.NOT_SCANNED:
            scan_one = _("SCAN 1")
            scan_all = _("SCAN")
            ticket_count = Ticket.objects.filter(reservation=obj.reservation).count()
            if ticket_count > 1:  # Si on a plusieurs ticket dans la même reservation, on permet le scan tous les tickets
                return True, format_html(
                    f'<button><a href="{reverse("staff_admin:ticket-scann", args=[obj.pk])}" class="button">{scan_one}</a></button>&nbsp;'
                    f'  --  '
                    f'<button><a href="{reverse("staff_admin:ticket-scann", args=[obj.pk])}?all=True" class="button">{scan_all} {ticket_count}</a></button>&nbsp;',
                )
            return True, format_html(
                f'<button><a href="{reverse("staff_admin:ticket-scann", args=[obj.pk])}" class="button">{scan_one}</a></button>&nbsp;')
        return None, ""

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            re_path(
                r'^(?P<ticket_pk>.+)/scanner/$',
                self.admin_site.admin_view(self.scanner),
                name='ticket-scann',
            ),
        ]
        return custom_urls + urls

    def scanner(self, request, ticket_pk, *arg, **kwarg):
        list_to_scan = []
        ticket = Ticket.objects.get(pk=ticket_pk)
        list_to_scan.append(ticket)

        if request.GET.get('all') == 'True':
            list_to_scan = Ticket.objects.filter(reservation=ticket.reservation)

        for ticket in list_to_scan:
            if ticket.status == Ticket.NOT_SCANNED:
                ticket.status = Ticket.SCANNED
                ticket.save()

        return redirect(request.META["HTTP_REFERER"])

    @display(description=_("Ticket n°"))
    def ticket(self, instance: Ticket):
        return f"{instance.reservation.user_commande.email} {str(instance.uuid)[:8]}"

    actions_row = ["get_pdf"]

    @action(description=_("PDF"),
            url_path="ticket_pdf",
            permissions=["custom_actions_row"])
    def get_pdf(self, request, object_id):
        ticket = get_object_or_404(Ticket, uuid=object_id)

        # Pas de PDF pour un billet non valide (inactif, créé, annulé).
        # On affiche un message d'erreur et on revient sur la page précédente.
        # C'est une vue admin Django : un Response DRF n'a pas de renderer ici et plante.
        # / No PDF for an invalid ticket: error message, then back to the previous page.
        VALID_TICKET_FOR_PDF = [Ticket.NOT_SCANNED, Ticket.SCANNED]
        if ticket.status not in VALID_TICKET_FOR_PDF:
            messages.error(
                request,
                _("Billet non valide (%(statut)s) : pas de PDF disponible.") % {"statut": ticket.get_status_display()},
            )
            page_precedente = request.META.get(
                "HTTP_REFERER",
                reverse("staff_admin:BaseBillet_ticket_changelist"),
            )
            return redirect(page_precedente)

        pdf_binary = create_ticket_pdf(ticket)
        response = HttpResponse(pdf_binary, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{ticket.pdf_filename()}"'
        return response

    def has_custom_actions_row_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        # Allow bulk actions in changelist for authorized tenant admins
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # return request.user.is_superuser
        return False

    # def get_queryset(self, request):
    #     qs = super(TicketAdmin, self).get_queryset(request)
    #     future_events = qs.filter(
    #         reservation__event__datetime__gt=(timezone.localtime() - timedelta(days=2)).date(),
    #     )
    #     return future_events


@admin.register(Client, site=staff_admin_site)
class TenantAdmin(ModelAdmin):
    # Doit être référencé pour le champs autocomplete_fields federated_with de configuration
    # est en CRUD total false
    # Seul le search fields est utile :
    search_fields = ['name', ]

    list_display = ['name', 'created_on', 'primary_domain', ]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # Uniquement les client qui ont un domaine
        return queryset.prefetch_related('domains').exclude(
            categorie__in=[Client.WAITING_CONFIG, Client.ROOT, Client.META])

    def get_search_results(self, request, queryset, search_term):
        """
        Pour la recherche de tenant dans la page Federation.
        On est sur un autocomplete, il faut bidouiller la réponde de ce coté
        Le but est que cela n'affiche dans le auto complete fields que les catégories Billets
        """
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if request.headers.get('Referer'):
            logger.info(request.headers.get('Referer'))
            if ("federatedplace" in request.headers['Referer']
                    and "admin/autocomplete" in request.path):  # Cela vient bien de l'admin event
                queryset = queryset.exclude(categorie__in=[Client.WAITING_CONFIG, Client.ROOT, Client.META]).exclude(
                    pk=connection.tenant.pk)  # on retire le client actuel

        # Invitations V2 (asset ou federation fedow_core) : un lieu legacy n'est jamais
        # propose. On lit les parametres GET de l'autocompletion Django, qui nomment le
        # champ source. Ce filtre ne pilote que l'affichage : la validation est faite par
        # le queryset du champ (AssetAdmin / FederationAdmin.formfield_for_manytomany).
        # / V2 invitations: a legacy venue is never offered. Display only; the field's
        # / queryset does the validation.
        champ_source_de_l_autocompletion = (
            request.GET.get("app_label"),
            request.GET.get("model_name"),
            request.GET.get("field_name"),
        )
        champs_d_invitation_v2 = [
            ("fedow_core", "asset", "pending_invitations"),
            ("fedow_core", "federation", "pending_tenants"),
        ]
        if champ_source_de_l_autocompletion in champs_d_invitation_v2:
            queryset = queryset.filter(moteur_monnaie=Client.MOTEUR_V2)
        return queryset, use_distinct

    actions_row = ["go_admin", ]

    @action(
        description=_("Go admin"),
        url_path="go_admin",
        permissions=["redirect_admin_action"],
    )
    def go_admin(self, request, object_id):
        tenant: Client = get_object_or_404(Client, pk=object_id)
        primary_domain = f"https://{tenant.get_primary_domain().domain}"
        user = request.user
        if user.is_superuser:
            token = user.get_connect_token()
            connexion_url = f"{primary_domain}/emailconfirmation/{token}"
            return redirect(connexion_url)
        return redirect(request.META["HTTP_REFERER"])

    @display(description=_("Domaine principal"))
    def primary_domain(self, instance: Client):
        primary_domain = f"https://{instance.get_primary_domain().domain}"
        return format_html(f"<a href='{primary_domain}' target='_blank'>{primary_domain}</a>")

    def has_redirect_admin_action_permission(self, request: HttpRequest, *args, **kwargs):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RootConfiguration, site=staff_admin_site)
class RootConfigurationAdmin(SingletonModelAdmin, ModelAdmin):
    """
    Config ROOT — ici on n'expose QUE la whitelist des domaines d'integration
    iframe (bloc IFRAME de l'app pages). JAMAIS les cles Stripe/Fedow. Reserve au
    SUPERADMIN strict (is_superuser) : le modele n'apparait dans la sidebar que
    pour lui. RootConfiguration est un singleton SHARED (schema public) : editer
    depuis n'importe quel tenant modifie la meme ligne globale (voulu).
    / ROOT config — expose ONLY the iframe-embed domains whitelist here, NEVER the
    Stripe/Fedow keys. STRICT superadmin only.
    """

    fields = ("domaines_embed_autorises",)

    # Mis à None, parce que "SingletonModelAdmin" est une classe de django,
    # et que le template d'unfold n'est pas atteint si on ne fais rien. Permet de respecter les settings.py
    change_form_template = None


    def save_model(self, request, obj, form, change):
        # Vide le cache django-solo (scope par schema) pour que TOUS les tenants
        # voient la nouvelle whitelist sans attendre l'expiration (~5 min).
        # / Clear the per-schema django-solo cache so ALL tenants see the new
        # whitelist immediately (meme pattern que RootConfiguration.set_stripe_api).
        super().save_model(request, obj, form, change)
        cache.clear()

    def has_view_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_add_permission(self, request):
        # Singleton : jamais d'ajout. / Singleton: no add.
        return False

    def has_change_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        # Singleton : pas de suppression. / Singleton: no deletion.
        return False


### Connect

@admin.register(FederationConfiguration, site=staff_admin_site)
class FederationConfigurationAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    # Mis à None, parce que "SingletonModelAdmin" est une classe de django,
    # et que le template d'unfold n'est pas atteint si on ne fais rien. Permet de respecter les settings.py
    change_form_template = None

    autocomplete_fields = ["tags_federation"]

    fieldsets = (
        (_("Affichage des lieux"), {"fields": (
            "afficher_lieux_sans_adresse",
            "afficher_seulement_lieux_avec_event",
            "afficher_lieux_entrants",
            "tri_des_lieux",
        )}),
        # Federation automatique par tags : le tenant s'abonne a des tags et
        # recoit les events de TOUT le reseau qui les portent (agenda + carto).
        # / Tag-based auto federation: subscribe to tags, receive matching events
        # from the WHOLE network (agenda + map).
        (_("Fédération automatique par tags"), {"fields": ("tags_federation",)}),
        (_("Présentation"), {"fields": ("texte_introduction",)}),
        # Agenda participatif : active le formulaire public de proposition
        # d'evenement (deplace depuis le dashboard des modules vers ici).
        # / Participatory agenda: enables the public event-proposal form
        # (moved from the modules dashboard to here).
        (_("Agenda participatif"), {"fields": (
            "module_agenda_participatif",
            "proposition_anonyme_autorisee",
            "tag_auto_proposition",
        )}),
    )

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    def save_model(self, request, obj, form, change):
        # Sanitize les TextField pour eviter le XSS via WYSIWYG
        # / Sanitize TextFields to avoid XSS via WYSIWYG
        sanitize_textfields(obj)
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FederatedPlace, site=staff_admin_site)
class FederatedPlaceAdmin(ModelAdmin):
    list_display = ["tenant", "str_tag_filter", "str_tag_exclude", "membership_visible", ]
    fields = ["tenant", "tag_filter", "tag_exclude", "membership_visible", ]
    autocomplete_fields = ["tag_filter", "tag_exclude", "tenant"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('tenant').prefetch_related('tag_filter', 'tag_exclude')

    # def formfield_for_foreignkey(self, db_field, request, **kwargs):
    #     if db_field.name == 'tenant':  # Replace 'user_field' with your actual field name
    #         kwargs['queryset'] = Client.objects.all().exclude(
    #             categorie__in=[Client.ROOT, Client.META, Client.WAITING_CONFIG]).exclude(
    #             pk=connection.tenant.pk)
    #     return super().formfield_for_foreignkey(db_field, request, **kwargs)

    actions_row = ["connect_to", ]

    @action(
        description=_("See this place"),
        url_path="connect_to",
        permissions=["redirect_admin_action"],
    )
    def connect_to(self, request, object_id):
        fp = get_object_or_404(FederatedPlace, pk=object_id)
        tenant = fp.tenant
        primary_domain = f"https://{tenant.get_primary_domain().domain}"
        user: TibilletUser = request.user
        token = user.get_connect_token()
        connexion_url = f"{primary_domain}/emailconfirmation/{token}"
        return redirect(connexion_url)

    def has_redirect_admin_action_permission(self, request: HttpRequest, *args, **kwargs):
        return TenantAdminPermissionWithRequest(request)

    @display(description=_("Included tags"))
    def str_tag_filter(self, instance: FederatedPlace):
        return ", ".join([tag.name for tag in instance.tag_filter.all()])

    @display(description=_("Excluded tags"))
    def str_tag_exclude(self, instance: FederatedPlace):
        return ", ".join([tag.name for tag in instance.tag_exclude.all()])

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


# Deux formulaires, un qui s'affiche si l'api est vide (ou supprimé)
# L'autre qui n'affiche pas l'input.
class GhostConfigChangeform(ModelForm):
    class Meta:
        model = GhostConfig
        fields = ['ghost_last_log']


class GhostConfigAddform(ModelForm):
    class Meta:
        model = GhostConfig
        fields = ['ghost_url', 'ghost_key', 'ghost_last_log']


@admin.register(GhostConfig, site=staff_admin_site)
class GhostConfigAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    # Mis à None, parce que "SingletonModelAdmin" est une classe de django,
    # et que le template d'unfold n'est pas atteint si on ne fais rien. Permet de respecter les settings.py
    change_form_template = None

    form = GhostConfigChangeform
    add_form = GhostConfigAddform

    readonly_fields = ["has_key", "ghost_last_log"]

    # Le panneau s'affiche AVANT le formulaire, et porte les actions de newsletter — pas le
    # bandeau `actions_detail`, qui n'offre que des libelles nus sans explication.
    # Chaque bouton doit dire ce qu'il fait, et surtout ce qu'il NE fait PAS : un brouillon
    # n'est jamais publie ni envoye. Un gestionnaire qui croirait envoyer sa newsletter en
    # cliquant, ou qui n'oserait pas cliquer de peur de l'envoyer, est un echec dans les
    # deux sens.
    # / The panel — not the bare `actions_detail` buttons — carries the newsletter actions.
    # Each button must say what it does, and above all what it does NOT do: a draft is never
    # published nor sent.
    change_form_before_template = "admin/ghost/panneau_newsletter.html"

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """
        Injecte le contexte du panneau affiche AVANT le formulaire.
        / Inject the context of the panel shown BEFORE the form.

        LOCALISATION : Administration/admin_tenant.py (GhostConfigAdmin)

        C'est TOUT ce que l'admin fait pour ce panneau : lui donner ses boutons. La logique
        (tester la connexion, generer le brouillon) vit dans `newsletter/views.py`, avec ses
        permissions DRF — pas ici, dans un module d'admin de 4000 lignes.
        / This is ALL the admin does for the panel: hand it its buttons. The logic lives in
        `newsletter/views.py`, with its own DRF permissions.

        La liste des fenetres appartient a l'app newsletter : c'est elle qui fabrique les
        brouillons, et c'est elle qui VALIDE la valeur recue (liste blanche). Le gabarit
        boucle dessus. Ajouter « 90 jours » ne demande donc qu'une valeur, a un seul endroit.
        / The window list belongs to the newsletter app: it builds the drafts and VALIDATES
        the received value. One value, one place.
        """
        from newsletter.views import FENETRES_DE_BROUILLON_EN_JOURS

        extra_context = extra_context or {}
        extra_context["fenetres_de_brouillon"] = FENETRES_DE_BROUILLON_EN_JOURS
        return super().changeform_view(request, object_id, form_url, extra_context)

    def has_key(self, instance: GhostConfig):
        return True if instance.ghost_key else False

    def get_form(self, request, obj=None, **kwargs):
        """ Si c'est un add, on modifie un peu le formulaire pour avoir un champs email """
        defaults = {}
        if not obj.ghost_key:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    def test_api_ghost(self, ghost_url, ghost_key):
        import datetime
        import jwt

        # Split the key into ID and SECRET
        id, secret = ghost_key.split(':')

        # Prepare header and payload
        iat = int(datetime.datetime.now().timestamp())

        header = {'alg': 'HS256', 'typ': 'JWT', 'kid': id}
        payload = {
            'iat': iat,
            'exp': iat + 5 * 60,
            'aud': '/admin/'
        }

        # Create the token
        token = jwt.encode(payload, bytes.fromhex(secret), algorithm='HS256', headers=header)

        # Make a request to the Ghost API
        headers = {'Authorization': f'Ghost {token}'}
        response = requests.get(f"{ghost_url}/ghost/api/admin/members/", headers=headers, params={"limit": 1})
        return response

    def save_model(self, request, obj: GhostConfig, form, change):
        if change:
            # headers = {'x-api-key': obj.api_key}
            # check_api = requests.get(f'{obj.api_host}/api/v1/me', headers=headers)
            try:
                response = self.test_api_ghost(obj.ghost_url, obj.ghost_key)
                if response.ok:
                    obj.set_api_key(obj.ghost_key)
                    messages.success(request, _("Api Key inserted"))
                else:
                    messages.error(request,
                                   _(f"Ghost API connection failed: {response.status_code} - {response.reason}"))
            except Exception as e:
                messages.error(request, _(f"Ghost API connection failed: {e}"))

            # Always save the model, even in error cases
            super().save_model(request, obj, form, change)

    def has_custom_actions_detail_permission(self, request, object_id):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return False
        #return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request: HttpRequest, obj: Model | None = None) -> bool:
        return TenantAdminPermissionWithRequest(request)


# Deux formulaires, un qui s'affiche si l'api est vide (ou supprimé)
# L'autre qui n'affiche pas l'input.
class FormbricksConfigChangeform(ModelForm):
    class Meta:
        model = FormbricksConfig
        fields = ['api_host']


class FormbricksConfigAddform(ModelForm):
    class Meta:
        model = FormbricksConfig
        fields = ['api_key', 'api_host']


@admin.register(FormbricksConfig, site=staff_admin_site)
class FormbricksConfigAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    # Mis à None, parce que "SingletonModelAdmin" est une classe de django,
    # et que le template d'unfold n'est pas atteint si on ne fais rien. Permet de respecter les settings.py
    change_form_template = None

    form = FormbricksConfigChangeform
    add_form = FormbricksConfigAddform

    readonly_fields = ["has_key", ]

    @display(description=_("Api key"), boolean=True)
    def has_key(self, instance: FormbricksConfig):
        return True if instance.api_key else False

    def get_form(self, request, obj=None, **kwargs):
        """ Si c'est un add, on modifie un peu le formulaire pour avoir un champs email """
        defaults = {}
        if not obj.api_key:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    def save_model(self, request, obj: FormbricksConfig, form, change):
        if change:
            headers = {'x-api-key': obj.api_key}
            check_api = requests.get(f'{obj.api_host}/api/v1/me', headers=headers)
            if check_api.ok:
                obj.set_api_key(obj.api_key)
                messages.success(request, _("Api OK"))
            else:
                obj.api_key = None
                messages.error(request, _("Api not OK"))

        super().save_model(request, obj, form, change)

    # Pour les boutons en haut de la vue changelist
    # chaque decorateur @action génère une nouvelle route
    actions_detail = ["test_api_formbricks", ]

    @action(description=_("Test Api"),
            url_path="test_api_formbricks",
            permissions=["custom_actions_detail"])
    def test_api_formbricks(self, request, object_id):
        fbc = FormbricksConfig.get_solo()
        api_host = fbc.api_host
        headers = {'x-api-key': fbc.get_api_key()}
        check_api = requests.get(f'{api_host}/api/v1/me', headers=headers)
        if check_api.ok:
            messages.success(request, _("Api OK"))
        else:
            messages.error(request, _("Api not OK"))
        return redirect(request.META["HTTP_REFERER"])

    def has_custom_actions_detail_permission(self, request, object_id):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    # def has_add_permission(self, request, obj=None):
    #     return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(FormbricksForms, site=staff_admin_site)
class FormbricksFormsAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    list_display = ['product', 'environmentId']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # import ipdb; ipdb.set_trace()
        if db_field.name == 'product':  # Replace 'user_field' with your actual field name
            kwargs['queryset'] = Product.objects.filter(
                archive=False,
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj: FormbricksForms, form, change):
        if obj.product:
            messages.info(request, f"product_name : {slugify(obj.product.name)}")
            for price in obj.product.prices.all():
                messages.info(request, f"price_name : {slugify(price.name)}")
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


# NOTE : `WaitingConfigAdmin` a ete migre vers `onboard/admin.py` lors
# de la session de cleanup legacy 2026-05-16. Cf.
# `TECH_DOC/SESSIONS/ONBOARD/03-session-recap.md`.
# / WaitingConfigAdmin moved to `onboard/admin.py` on 2026-05-16.


# Deux formulaires, un qui s'affiche si l'api est vide (ou supprimé)
# L'autre qui n'affiche pas l'input.
class BrevoConfigChangeform(ModelForm):
    class Meta:
        model = BrevoConfig
        fields = ['last_log']


class BrevoConfigAddform(ModelForm):
    class Meta:
        model = BrevoConfig
        fields = ['api_key', 'last_log', ]


@admin.register(BrevoConfig, site=staff_admin_site)
class BrevoConfigAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    # Mis à None, parce que "SingletonModelAdmin" est une classe de django,
    # et que le template d'unfold n'est pas atteint si on ne fais rien. Permet de respecter les settings.py
    change_form_template = None

    readonly_fields = ['last_log', "has_key", ]
    actions_detail = ["test_api_brevo", ]

    form = BrevoConfigChangeform
    add_form = BrevoConfigAddform

    @display(description=_("Has key"), boolean=True)
    def has_key(self, instance: BrevoConfig):
        return True if instance.api_key else False

    def get_form(self, request, obj=None, **kwargs):
        """ Si c'est un add, on modifie un peu le formulaire pour avoir un champs email """
        defaults = {}
        if not obj.api_key:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    def save_model(self, request, obj: FormbricksConfig, form, change):
        if change:
            obj.set_api_key(obj.api_key)
            messages.success(request, _("Clé Api chiffrée"))

        super().save_model(request, obj, form, change)

    @action(description=_("Test Api"),
            url_path="test_api_brevo",
            permissions=["custom_actions_detail"])
    def test_api_brevo(self, request, object_id):
        import sib_api_v3_sdk
        from sib_api_v3_sdk.rest import ApiException
        brevo_config = BrevoConfig.get_solo()

        try:
            configuration = sib_api_v3_sdk.Configuration()
            configuration.api_key['api-key'] = brevo_config.get_api_key()
            api_instance = sib_api_v3_sdk.AccountApi(sib_api_v3_sdk.ApiClient(configuration))
            api_response = api_instance.get_account()
            brevo_config.last_log = api_response
            messages.success(request, _("Api OK"))
        except ApiException as e:
            brevo_config.last_log = f"{e}"
            logger.warning("ApiException when calling AccountApi->get_account: %s\n" % e)
            messages.error(request, _(f"Api not OK : {e}"))
        except Exception as e:
            brevo_config.last_log = f"{type(e)} - {e}"
            logger.error("Exception when calling AccountApi->get_account: %s\n" % e)
            messages.error(request, f"Error : {type(e)} - {e}")

        brevo_config.save()
        return redirect(request.META["HTTP_REFERER"])

    def has_custom_actions_detail_permission(self, request, object_id):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return False
        # return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(AssetFedowPublic, site=staff_admin_site)
class AssetAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    change_form_before_template = "admin/asset/asset_change_form_before.html"
    list_before_template = "admin/asset/asset_list_before.html"

    list_display = [
        "name",
        "currency_code",
        "category",
        "origin",
        "_federated_with",
    ]

    readonly_fields = [
        # Identifiant unique de l'asset, affiche en lecture seule sur la fiche.
        # / Asset unique identifier, shown read-only on the change form.
        'uuid',
        'created_at',
        'wallet_origin',
        'federated_with',
    ]

    fields = [
        "uuid",
        "name",
        "currency_code",
        "category",
        "pending_invitations",
        "federated_with",
    ]

    autocomplete_fields = [
        'pending_invitations',
    ]

    actions_row = ["archive", ]

    @action(
        description=_("Archive"),
        url_path="archive",
        permissions=["changelist_row_action"],
    )
    def archive(self, request, object_id):
        asset = get_object_or_404(Asset, pk=object_id)
        fedowAPI = FedowAPI()
        fedowAPI.asset.archive_asset(asset.uuid)
        asset.archive = True
        asset.save()
        messages.success(request, _(f"{asset.name} Archived"))
        return redirect(request.META["HTTP_REFERER"])

    def has_changelist_row_action_permission(self, request: HttpRequest, *args, **kwargs):
        return TenantAdminPermissionWithRequest(request)

    def _federated_with(self, obj):
        feds = [place.name for place in obj.federated_with.all()]
        feds.append(obj.origin.name)
        return ", ".join(feds)

    # On affiche que les assets non adhésions + origin + fédéré
    def get_queryset(self, request):
        logger.info(f"get_queryset AssetAdmin : {request.user}")
        # Synchronise les assets acceptes depuis Fedow, seulement si le lieu y est
        # relie. Sinon, instancier FedowAPI lance create_place() (handshake reseau
        # involontaire) et plante sur un lieu sans admin, comme `meta` : la page
        # repondait 500. Meme garde que laboutik.views.obtenir_wallet_carte_depuis_fedow.
        # / Syncs accepted assets from Fedow, only if the venue is linked to it.
        #   Otherwise FedowAPI() triggers create_place() and crashes on a venue
        #   with no admin, like `meta`: the page answered 500.
        if FedowConfig.get_solo().can_fedow():
            fedowAPI = FedowAPI()
            fedowAPI.asset.get_accepted_assets()

        tenant = connection.tenant
        queryset = (
            super()
            .get_queryset(request)
            .exclude(category__in=[AssetFedowPublic.BADGE, AssetFedowPublic.SUBSCRIPTION])
            .filter(Q(origin=tenant) | Q(federated_with=tenant))
            .filter(archive=False)
            .distinct()
        )
        return queryset

    def save_model(self, request: HttpRequest, obj: Asset, form: Form, change: Any) -> None:
        # Vérifie si l'objet est nouveau
        new = not change or not getattr(obj, 'pk', None)
        if new:
            # Vérifie les champs choisis (ici, la catégorie) selon le contexte
            allowed_on_create = {AssetFedowPublic.TOKEN_LOCAL_FIAT, AssetFedowPublic.TOKEN_LOCAL_NOT_FIAT,
                                 AssetFedowPublic.TIME, Asset.FIDELITY}
            if obj.category not in allowed_on_create:
                messages.error(request, _("Catégorie non autorisée pour une création."))
                raise ValidationError("Invalid category on create")

            obj.origin = connection.tenant
            fedow_config = FedowConfig.get_solo()
            obj.wallet_origin = fedow_config.wallet
            # On sauvegarde dans la base de donnée
            super().save_model(request, obj, form, change)

            try:
                fedowAPI = FedowAPI(fedow_config=fedow_config)
                asset, created = fedowAPI.asset.get_or_create_token_asset(obj)
                logger.info(f"Asset créé chez fédow {asset} : {created}")
            except Exception as e:
                messages.error(request, f"{e}")
                raise ValidationError(str(e))

            if not created:
                messages.error(request, _("Asset already exists"))
                raise ValidationError("Asset already exists")

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            for f in ("name", "currency_code", "category"):
                if f not in ro:
                    ro.append(f)
        return ro

    def save_related(self, request, form, formsets, change):
        """Ensure only origin tenant admins can modify pending_invitations.
        If the current tenant is not the asset origin, any attempted change to
        pending_invitations is reverted and an error message is shown.
        """
        obj = form.instance
        # Snapshot existing pending invitations before m2m save
        prev_pending_ids = set()
        if getattr(obj, 'pk', None):
            try:
                prev_pending_ids = set(obj.pending_invitations.values_list('pk', flat=True))
            except Exception:
                prev_pending_ids = set()
        super().save_related(request, form, formsets, change)
        try:
            current_tenant_id = getattr(connection.tenant, 'pk', None)
            origin_id = getattr(obj, 'origin_id', None)
            if obj.pk and origin_id != current_tenant_id:
                # Non-origin tenant is not allowed to change invitations: revert to previous
                obj.pending_invitations.set(list(prev_pending_ids))
                messages.error(request, _("Seul le lieu d'origine peut envoyer des invitations."))
        except Exception:
            # Fail-closed: if something goes wrong, keep previous state already restored above when applicable
            pass

    def get_form(self, request, obj=None, **kwargs):
        # Limit category choices on add form to TOKEN_LOCAL_FIAT and TOKEN_LOCAL_NOT_FIAT
        form = super().get_form(request, obj, **kwargs)
        try:
            if obj is None and 'category' in form.base_fields:
                allowed = [
                    (Asset.TOKEN_LOCAL_FIAT, dict(Asset.CATEGORIES)[Asset.TOKEN_LOCAL_FIAT]),
                    (Asset.TOKEN_LOCAL_NOT_FIAT, dict(Asset.CATEGORIES)[Asset.TOKEN_LOCAL_NOT_FIAT]),
                    (Asset.TIME, dict(Asset.CATEGORIES)[Asset.TIME]),
                    (Asset.FIDELITY, dict(Asset.CATEGORIES)[Asset.FIDELITY]),
                ]
                form.base_fields['category'].choices = allowed
        except Exception:
            pass
        return form

    def get_fields(self, request, obj=None):
        # Hide "Partager cet actif" (pending_invitations) unless the current tenant is the asset origin
        fields = list(super().get_fields(request, obj))
        try:
            if obj is not None:
                current_tenant = connection.tenant
                if getattr(obj, 'origin_id', None) != getattr(current_tenant, 'pk', None):
                    if 'pending_invitations' in fields:
                        fields.remove('pending_invitations')
        except Exception:
            # In case of any unexpected issue, fall back to original fields
            pass
        return fields

    def changeform_view(self, request: HttpRequest, object_id: Optional[str] = None, form_url: str = "",
                        extra_context: Optional[Dict[str, Any]] = None):
        """Inject Fedow data for the before template on change view and handle invite form POST."""
        extra_context = extra_context or {}
        serialized_asset = {}
        error_message = None
        total_by_place_with_uuid = {}

        if object_id:
            try:
                fedow = FedowAPI()
                fedow_data = fedow.asset.total_by_place_with_uuid(uuid=object_id)
                # fedow_data is a JSON string; parse it to dict
                total_by_place_with_uuid = json.loads(fedow_data) if isinstance(fedow_data, (str, bytes)) else (
                        fedow_data or {})
                logger.info(f"fedow_data : {fedow_data}")

                # Expected new structure: {"total_by_place": [{"place_name": ..., "place_uuid": ..., "total_value": ...}, ...], "serialized_asset": {...}}
                totals_list = (total_by_place_with_uuid or {}).get("total_by_place") or []
                serialized_asset = (total_by_place_with_uuid or {}).get("serialized_asset") or {}

            except Exception as e:
                error_message = str(e)

        extra_context.update({
            "total_by_place_with_uuid": total_by_place_with_uuid,
            "serialized_asset": serialized_asset,
            "fedow_error": error_message,
            "asset_pk": object_id,
        })
        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            # Nom propre a l'admin legacy : `asset-accept-invitation` est celui de
            # l'admin fedow_core. Deux routes du meme nom, et `{% url %}` en choisit une
            # en silence (garde : tests/pytest/test_noms_de_routes_admin_uniques.py).
            # / Own name for the legacy admin; `asset-accept-invitation` is fedow_core's.
            re_path(
                r'^accept_invitation/(?P<asset_pk>.+)/$',
                self.admin_site.admin_view(csrf_protect(require_POST(self.accept_invitation))),
                name='assetfedowpublic-accept-invitation',
            ),
            re_path(
                r'^bank_deposit/(?P<asset_pk>.+)/(?P<wallet_to_deposit>.+)/$',
                self.admin_site.admin_view(csrf_protect(require_POST(self.bank_deposit))),
                name='asset-bank-deposit',
            ),
        ]
        return custom_urls + urls

    def accept_invitation(self, request: HttpRequest, asset_pk: str):
        # Accept an invitation for the current tenant on the given asset
        tenant = connection.tenant
        place_added_uuid = FedowConfig.get_solo().fedow_place_uuid

        # Basic permission check for tenant admins
        if not TenantAdminPermissionWithRequest(request):
            messages.error(request, _("Permission refusée."))
            return redirect(
                reverse(f"{self.admin_site.name}:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist")
            )

        asset = get_object_or_404(AssetFedowPublic, pk=asset_pk)

        if request.method != 'POST':
            return redirect(
                reverse(f"{self.admin_site.name}:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist")
            )

        if asset.pending_invitations.filter(pk=tenant.pk).exists():
            with tenant_context(asset.origin):
                fedowAPI = FedowAPI()
                place_origin_uuid = FedowConfig.get_solo().fedow_place_uuid
                federation = fedowAPI.federation.create_fed(
                    user=request.user,
                    asset=asset,
                    place_added_uuid=place_added_uuid,
                    place_origin_uuid=place_origin_uuid,
                )
                # Move tenant from pending to federated
                asset.pending_invitations.remove(tenant)
                asset.federated_with.add(tenant)

            messages.success(request, _("Invitation acceptée."))
        else:
            messages.error(request, _("Aucune invitation en attente pour ce lieu."))

        return redirect(
            reverse(f"{self.admin_site.name}:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist")
        )

    def bank_deposit(self, request: HttpRequest, asset_pk: str, wallet_to_deposit: str):
        """Handle HTMX POST to declare a bank deposit for a local asset.
        Expects POST params: place (str), amount (decimal), origin_wallet (uuid optional), destination_wallet (uuid optional).
        wallet_to_deposit : Le wallet qu'il faut vider
        """
        if not TenantAdminPermissionWithRequest(request):
            return HttpResponse(status=403)

        asset = get_object_or_404(AssetFedowPublic, uuid=UUID(asset_pk))
        wallet = get_object_or_404(Wallet, uuid=UUID(wallet_to_deposit))
        wallet_to_deposit = wallet.uuid

        try:
            fedow = FedowAPI()
            transaction = fedow.wallet.local_asset_bank_deposit(
                user=request.user,
                wallet_to_deposit=f"{wallet_to_deposit}",
                asset=asset,
            )
            messages.add_message(request, messages.SUCCESS, _("Remise en banque OK."))

        except Exception as e:
            logger.error(e)
            messages.add_message(request, messages.ERROR, f"{e}")

        return HttpResponseClientRedirect(request.META["HTTP_REFERER"])

    def changelist_view(self, request: HttpRequest, extra_context: Optional[Dict[str, Any]] = None):
        # Provide invitations list for the list_before_template
        extra_context = extra_context or {}
        tenant = connection.tenant
        invitations_qs = AssetFedowPublic.objects.filter(pending_invitations=tenant).select_related('origin')
        extra_context.update({
            'asset_invitations': invitations_qs,
        })
        return super().changelist_view(request, extra_context=extra_context)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    # Plus de creation d'asset dans l'ancien Fedow depuis l'admin (decision du
    # mainteneur, 2026-10-06) : en attendant la migration H-2 / H-3, on gere, invite et
    # accepte les assets existants, on n'en cree plus.
    # / No more asset creation on the old Fedow from the admin, until H-2 / H-3.
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False


# ----------------------
# ModelAdmins CROWDS
# ----------------------


@admin.register(CrowdConfig, site=staff_admin_site)
class CrowdConfigAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    # Mis à None, parce que "SingletonModelAdmin" est une classe de django,
    # et que le template d'unfold n'est pas atteint si on ne fais rien. Permet de respecter les settings.py
    change_form_template = None

    fieldsets = (
        (_("Général"), {"fields": ("active",)}),
        (_("Affichage"), {"fields": (
            "title",
            "description",
            "vote_button_name",
            "name_goal",
            "name_funding",
            "name_participations",
            "contributor_covenant",
            "pro_bono_name",
        )}),
        # (_("Financement"), {"fields": (
        #     "global_funding_button",
        #     "global_funding_button_text",
        # )}),
    )

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    def save_model(self, request, obj, form, change):
        obj: CrowdConfig
        # Sanitize all TextField inputs to avoid XSS via WYSIWYG/TextField
        sanitize_textfields(obj)
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False


# @admin.register(CrowdTag, site=staff_admin_site)
# class CrowdTagAdmin(ModelAdmin):
#     list_display = ("name", "slug", "color_bg", "color_preview")
#     search_fields = ("name", "slug")
#     prepopulated_fields = {"slug": ("name",)}
#     ordering = ("name",)
#     fields = ("name", "slug", "color_bg")
#
#     def color_preview(self, obj):
#         return format_html(
#             '<span style="display:inline-block;width:2rem;height:1rem;border-radius:.25rem;vertical-align:middle;{}"></span> '
#             '<span class="text-muted small">{}</span>',
#             obj.style_attr + ';border:1px solid rgba(0,0,0,.2)',
#             obj.color_bg,
#         )
#
#     color_preview.short_description = _("Aperçu")

# ----------------------
# INITIATIVE CROWDS
# ----------------------


class ContributionInline(TabularInline):
    """
    FR: Inline pour les contributions financières d'une initiative.
        L'ajout direct depuis l'admin est désactivé pour éviter les erreurs d'intégrité (ex: participant_id NULL).
    EN: Inline for financial contributions of an initiative.
        Direct addition from admin is disabled to prevent integrity errors (e.g. participant_id NULL).
    """
    model = Contribution
    fk_name = 'initiative'
    # FR: Ne pas proposer de nouvelle ligne par défaut / EN: No empty row by default
    extra = 0
    can_delete = True
    show_change_link = True
    # FR: Evite de charger 200k users dans un select: champ en saisie par ID
    # EN: Avoid loading 200k users in a select: field input by ID
    raw_id_fields = ("contributor",)

    fields = (
        "contributor_name",
        "contributor",
        "description",
        "amount",
        "amount_eur_display",
        "payment_status",
        "paid_at",
        "created_at",
    )
    readonly_fields = ("amount_eur_display", "created_at", "contributor")

    def amount_eur_display(self, obj):
        if not obj:
            return ""
        return f"{obj.amount_eur:.2f} {obj.initiative.currency}"

    amount_eur_display.short_description = _("Montant")

    # FR: Permissions : on INTERDIT l'ajout; seule la modification/suppression est permise
    # EN: Permissions: addition is FORBIDDEN; only modification/deletion is allowed
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("contributor", "initiative")


class VoteInline(TabularInline):
    model = Vote
    fk_name = 'initiative'
    extra = 0
    can_delete = True
    readonly_fields = ("created_at", "user")
    fields = ("user", "created_at")
    # Saisie par ID pour éviter l'autocomplete sur une très grande table user
    raw_id_fields = ("user",)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        # Pas de modification du vote: on peut supprimer/ajouter
        return False

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user")


class BudgetItemInline(TabularInline):
    """
    FR: Inline pour les lignes budgétaires (objectifs à financer).
        L'ajout direct est interdit ici pour forcer l'usage du front ou un flux contrôlé.
    EN: Inline for budget items (funding goals).
        Direct addition is forbidden here to force use of the front-end or a controlled flow.
    """
    model = BudgetItem
    fk_name = 'initiative'
    # FR: Ne pas proposer de nouvelle ligne par défaut / EN: No empty row by default
    extra = 0
    can_delete = True
    show_change_link = True
    # FR: Evite les gros menus déroulants de users / EN: Avoid large user dropdowns
    raw_id_fields = ("contributor", "validator")

    fields = (
        "contributor",
        "description",
        "amount",
        "state",
        "validator",
        "created_at",
    )
    readonly_fields = ("created_at", "contributor", "validator")

    # FR: Permissions: on INTERDIT l'ajout; seule la modification/suppression est permise
    # EN: Permissions: addition is FORBIDDEN; only modification/deletion is allowed
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("contributor", "validator")


class ParticipationInline(TabularInline):
    """
    FR: Inline pour les participations (actions des utilisateurs).
        L'ajout est bloqué car il manquait souvent le participant_id (IntegrityError).
    EN: Inline for participations (user actions).
        Addition is blocked because participant_id was often missing (IntegrityError).
    """
    model = Participation
    fk_name = 'initiative'
    # FR: On NE PROPOSE PAS de nouvelle ligne par défaut / EN: No empty row by default
    extra = 0
    # FR: Evite le chargement massif des users / EN: Avoid massive user loading
    raw_id_fields = ("participant",)
    fields = (
        "participant",
        "description",
        "amount",
        "state",
        "time_spent_minutes",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at", "participant")

    # FR: Permissions: on INTERDIT l'ajout; seule la modification/suppression est permise
    # EN: Permissions: addition is FORBIDDEN; only modification/deletion is allowed
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("participant")


# class InitiativeAdminForm(ModelForm):
#     funding_goal_eur = forms.DecimalField(
#         label=_("Objectif"),
#         help_text=_("Montant de l'objectif dans la devise de l'initiative (affiché en unités, enregistré en centimes)."),
#         decimal_places=2,
#         max_digits=12,
#         min_value=0,
#         required=True,
#         widget=UnfoldAdminTextInputWidget,
#     )
#
#     class Meta:
#         model = Initiative
#         fields = (
#             "name",
#             "short_description",
#             "description",
#             "funding_goal_eur",
#             "currency",
#             # "direct_debit",
#             "img",
#             "budget_contributif",
#         )
#
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         inst: Initiative | None = getattr(self, "instance", None)
#         if inst and getattr(inst, "pk", None):
#             try:
#                 self.fields["funding_goal_eur"].initial = (Decimal(inst.funding_goal or 0) / Decimal("100")).quantize(Decimal("0.01"))
#             except Exception:
#                 self.fields["funding_goal_eur"].initial = Decimal("0.00")
#
#     def save(self, commit=True):
#         instance: Initiative = super().save(commit=False)
#         # Convert euros to integer cents safely
#         value_eur: Decimal = self.cleaned_data.get("funding_goal_eur") or Decimal("0")
#         cents = int((value_eur.quantize(Decimal("0.01")) * 100).to_integral_value())
#         instance.funding_goal = max(0, cents)
#         if commit:
#             instance.save()
#             self.save_m2m()
#         return instance


@admin.register(Initiative, site=staff_admin_site)
class InitiativeAdmin(ModelAdmin):
    # form = InitiativeAdminForm
    list_display = (
        "name",
        "created_at",
        "funded_amount_display",
        "funding_goal_display",
        "progress_percent_int",
        "currency",
        "votes_count",
        # "requested_total_display",
    )

    fields = (
        "name",
        "short_description",
        "description",
        "currency",
        "img",
        "tags",
        "archived",
        "vote",
        "budget_contributif",
        "direct_debit",
        # "adaptative_funding_goal_on_participation",

    )

    # Filtre en liste déroulante avec recherche (Unfold), envoyé par le bouton « Filtrer ».
    # Une liste de liens devient illisible dès qu'il y a beaucoup de choix.
    # / Searchable dropdown filter (Unfold), sent by the "Filter" button.
    list_filter = ("created_at", ("tags", RelatedDropdownFilter))
    search_fields = ("name", "description", "tags__name")
    date_hierarchy = "created_at"
    inlines = [VoteInline, BudgetItemInline, ContributionInline, ParticipationInline]
    ordering = ("-created_at",)
    filter_horizontal = ("tags",)
    autocomplete_fields = ("tags",)
    # Optimise les requêtes en changelist (FK direct)
    list_select_related = ("asset",)

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    def get_queryset(self, request):
        # Optimise les agrégations et évite les N+1 en liste admin
        qs = super().get_queryset(request)
        qs = (
            qs
            .select_related("asset")
            .prefetch_related("tags")
            .annotate(
                funded_total=models.Sum("contributions__amount", distinct=True),
                funding_goal_total=models.Sum(
                    models.Case(
                        models.When(budget_items__state="approved", then=models.F("budget_items__amount")),
                        default=models.Value(0),
                        output_field=models.IntegerField(),
                    ),
                    distinct=True,
                ),
                votes_total=models.Count("votes", distinct=True),
            )
        )
        return qs

    def save_model(self, request, obj, form, change):
        obj: Initiative
        # Sanitize all TextField inputs to avoid XSS via WYSIWYG/TextField
        sanitize_textfields(obj)

        # FR: Si direct_debit est activé, vérifier qu'un compte Stripe est connecté.
        #     Sans Stripe, le paiement en ligne ne peut pas fonctionner.
        # EN: If direct_debit is enabled, check that a Stripe account is connected.
        if obj.direct_debit:
            config = Configuration.get_solo()
            stripe_est_configure = bool(
                config.stripe_connect_account or config.stripe_connect_account_test
            )
            if not stripe_est_configure:
                from django.contrib import messages
                obj.direct_debit = False
                messages.error(
                    request,
                    _("Paiement direct désactivé : aucun compte Stripe n'est connecté. "
                      "Configurez Stripe dans Paramètres avant d'activer le paiement direct.")
                )

        super().save_model(request, obj, form, change)

    def currency(self, obj: Initiative):
        if obj.asset:
            return obj.asset.currency_code
        return obj.currency

    currency.short_description = _("Devise")

    def funded_amount_display(self, obj):
        total = getattr(obj, "funded_total", None)
        if total is None:
            total = obj.total_funded_amount
        decimal_amount = Decimal(total or 0) / Decimal("100")
        return f"{decimal_amount:.2f}"

    funded_amount_display.short_description = _("Financé")

    def funding_goal_display(self, obj):
        # Objectif = somme des lignes budgétaires approuvées
        goal = getattr(obj, "funding_goal_total", None)
        if goal is None:
            goal = obj.total_funding_amount
        decimal_amount = Decimal(goal or 0) / Decimal("100")
        return f"{decimal_amount:.2f} {self.currency(obj)}"

    funding_goal_display.short_description = _("Objectif")

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


# --- Terminaux hardware POS (TermUser) — portage S6 ---
# Enregistrement minimal : le dashboard reference 'termuser_changelist'.
# / Minimal registration: the dashboard references 'termuser_changelist'.
# Alignement complet via Administration/admin/users.py prevu au chantier modulaire.
from AuthBillet.models import TermUser as _TermUserProxy
from Administration.admin.base import ModelAdmin as _UnfoldModelAdmin


@admin.register(_TermUserProxy, site=staff_admin_site)
class TermUserAdmin(_UnfoldModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ('email', 'terminal_role', 'is_active', 'last_login')
    list_filter = ('terminal_role', 'is_active')
    search_fields = ('email',)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        # Un TermUser naît UNIQUEMENT d'un claim discovery réussi (PIN).
        # L'appairage se pilote depuis l'admin PairingDevice (menu
        # « Terminaux hardware ») ; le compte apparaît ici après le claim.
        # / A TermUser is born ONLY from a successful discovery claim (PIN).
        # Pairing is driven from the PairingDevice admin ("Hardware
        # terminals" menu); the account shows up here after the claim.
        return False

    def has_change_permission(self, request, obj=None):
        # Autorisé pour révoquer un terminal (is_active) / Allowed to revoke
        # a terminal (is_active).
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
