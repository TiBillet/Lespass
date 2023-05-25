import datetime
import uuid

from django import forms
from django.conf.urls import url
from django.contrib import admin, messages
from django.contrib.admin import AdminSite, SimpleListFilter
from django.contrib.admin.views.main import ChangeList
from django.contrib.auth.models import Group
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse, NoReverseMatch
from django.utils.html import format_html
from django.utils.text import capfirst
# from rest_framework_api_key.models import APIKey
from rest_framework_api_key.models import APIKey
from solo.admin import SingletonModelAdmin
from django.utils.translation import ugettext_lazy as _

from AuthBillet.models import HumanUser, SuperHumanUser, TermUser
from AuthBillet.utils import get_client_ip
from BaseBillet.models import Configuration, Event, OptionGenerale, Product, Price, Reservation, LigneArticle, Ticket, \
    Paiement_stripe, ProductSold, PriceSold, Membership, ExternalApiKey, Webhook, Tag
from django.contrib.auth.admin import UserAdmin
from Customers.models import Client

import logging

logger = logging.getLogger(__name__)


class StaffAdminSite(AdminSite):
    site_header = "TiBillet Staff Admin"
    site_title = "TiBillet Staff Admin"
    site_url = '/'


    def get_app_list(self, request):
        # app_dict = self._build_app_dict(request)

        ordering = {
            "Billetterie": [
                "Paramètres",
                "Produits",
                "Tarifs",
                "Tags",
                "Evenements",
                "Options",
                "Paiements Stripe",
                "Réservations",
                "Adhésions",
                "Api keys",
                "Webhooks",
            ]
        }

        logger.info("")
        app_dict = self._build_app_dict(request)
        # logger.info(f"user perm : {len(request.user.get_all_permissions())}")
        # logger.info(f"_registry : {len(self._registry.items())}")
        # logger.info(app_dict)
        # import ipdb; ipdb.set_trace()

        # models = self._registry
        # for model, model_admin in models.items():
        #     app_label = model._meta.app_label
        #     has_module_perms = model_admin.has_module_permission(request)
        #     perms = model_admin.get_model_perms(request)
        #     import ipdb; ipdb.set_trace()
        logger.info("")

        # a.sort(key=lambda x: b.index(x[0]))
        # Sort the apps alphabetically.
        app_list = sorted(app_dict.values(), key=lambda x: x['name'].lower())

        # Sort the models alphabetically within each app.
        for app in app_list:
            order = ordering.get(app['name'])
            if order:
                app['models'].sort(key=lambda x: order.index(x['name']))

        return app_list

    def has_permission(self, request):
        """
        Removed check for is_staff.
        Ensure that the tenant is in client_admin for the current user.
        Return SuperUser : Bug in contentype permission with tenant ... BIG TODO !
        """
        logger.warning(f"Tenant AdminSite.has_permission : {request.user} - {request.user.client_source if request.user.is_authenticated else 'No client'} - ip : {get_client_ip(request)}")

        try:
            if request.tenant in request.user.client_admin.all():
                return request.user.is_superuser
            if request.user.client_source.categorie == Client.ROOT:
                return request.user.is_superuser
        except AttributeError as e:
            logger.error(f"{e} : AnonymousUser for admin ?")
            return False
        except Exception as e:
            raise e

        return False

    # def get_app_list(self, request):
    #     import ipdb; ipdb.set_trace()
    #     return super().get_app_list(request)


staff_admin_site = StaffAdminSite(name='staff_admin')


# USER
# -------------------------------------/
class UserAdminTibillet(UserAdmin):
    # list_display = ('email', 'client_source', 'achat')
    list_display = ('email', 'is_active', 'last_see')
    list_filter = ('email', 'is_active',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        # ('Permissions', {'fields': ('is_staff', 'is_active')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email',)}
            # 'fields': ('email', 'password1', 'password2', 'is_active')}
         ),
    )

    search_fields = ('email',)
    ordering = ('-last_see',)

    def save_model(self, request, obj, form, change):
        if not obj.client_source:
            obj.client_source = request.tenant
            obj.username = obj.email
            obj.save()
        obj.client_achat.add(request.tenant)

    def has_delete_permission(self, request, obj=None):
        # return request.user.is_superuser
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
class HumanUserAdmin(UserAdminTibillet):
    pass

staff_admin_site.register(HumanUser, HumanUserAdmin)


class SuperHumanUserAdmin(UserAdminTibillet):
    def save_model(self, request, obj, form, change):
        staff_group = Group.objects.get_or_create(name="staff")[0]
        obj.groups.add(staff_group)
        obj.client_achat.add(request.tenant)
        obj.client_admin.add(request.tenant)

        # execution du save de la classe orginale user admin ( heritage de l'hérité )
        super(UserAdminTibillet, self).save_model(request, obj, form, change)


staff_admin_site.register(SuperHumanUser, SuperHumanUserAdmin)


class TermUserAdmin(UserAdminTibillet):
    pass


staff_admin_site.register(TermUser, TermUserAdmin)


class ExtApiKeyAdmin(admin.ModelAdmin):
    readonly_fields = ["key", ]

    list_display = [
        "name",
        "created",
        "ip",
        "api_permissions",
        "user"
    ]

    fields = [
        "name",
        "ip",
        "revoquer_apikey",
        "event",
        "product",
        "place",
        "artist",
        "reservation",
        "ticket",
    ]

    def save_model(self, request, instance, form, change):
        # obj.user = request.user
        ex_api_key = None
        if instance.revoquer_apikey:
            if instance.key:
                ex_api_key = APIKey.objects.get(id=instance.key.id)
                instance.key = None
                messages.add_message(request, messages.WARNING, "API Key deleted")

            else:
                api_key = None
                key = " "
                # On affiche le string Key sur l'admin de django en message
                # et django.message capitalize chaque message...
                # Du coup, on fait bien gaffe à ce que je la clée générée ai bien une majusculle au début ...
                while key[0].isupper() == False:
                    api_key, key = APIKey.objects.create_key(name=instance.name)
                    if key[0].isupper() == False:
                        api_key.delete()

                instance.key = api_key

                messages.add_message(
                    request,
                    messages.SUCCESS,
                    f"Copiez bien la clé suivante et mettez la en lieu sur ! Elle est chifrée coté serveur et ne sera affichée qu'une seule fois ici :"
                )
                messages.add_message(
                    request,
                    messages.WARNING,
                    f"{key}"
                )

            instance.revoquer_apikey = False

        instance.user = request.user

        super().save_model(request, instance, form, change)
        if ex_api_key:
            ex_api_key.delete()


staff_admin_site.register(ExternalApiKey, ExtApiKeyAdmin)


class WebhookAdmin(admin.ModelAdmin):
    readonly_fields = ['last_response', ]
    fields = [
        "url",
        "active",
        "event",
        "last_response",
    ]

    list_display = [
        "url",
        "active",
        "event",
        "last_response",
    ]


staff_admin_site.register(Webhook, WebhookAdmin)

########################################################################
class ConfigurationAdmin(SingletonModelAdmin):

    fieldsets = (
        (None, {
            'fields': (
                'organisation',
                'short_description',
                'long_description',
                'img',
                'logo',
                'adress',
                'phone',
                'email',
                'site_web',
                # 'map_img',
            )
        }),
        # ('Restaurant', {
        #     'fields': (
        #         'carte_restaurant',
        #     ),
        # }),
        # ('Social', {
        #     'fields': (
        #         'twitter',
        #         'facebook',
        #         'instagram',
        #     ),
        # }),
        # ('Adhésions', {
        #     'fields': (
        #         'adhesion_obligatoire',
                # 'button_adhesion',
            # ),
        # }),
        ('Paiements', {
            'fields': (
                # 'stripe_api_key',
                # 'stripe_test_api_key',
                'stripe_mode_test',
            ),
        }),
        ('Billetterie options générales', {
            'fields': (
                # 'activer_billetterie',
                # 'template_billetterie',
                # 'template_meta',
                'jauge_max',
                # 'option_generale_radio',
                # 'option_generale_checkbox',
            ),
        }),
        ('Cashless', {
            'fields': (
                'server_cashless',
                'key_cashless',
            ),
        }),
        ('Ghost', {
            'fields': (
                'ghost_url',
                'ghost_key',
                'ghost_last_log',
            ),
        }),
        # ('Mailing', {
        #     'fields': (
        #         'activate_mailjet',
        #         'email_confirm_template',
        #     ),
        # }),
    )
    readonly_fields = ['ghost_last_log',]

    def save_model(self, request, obj, form, change):
        obj: Configuration
        if obj.server_cashless and obj.key_cashless:
            if obj.check_serveur_cashless():
                messages.add_message(request, messages.INFO, f"Cashless server ONLINE")
            else:
                messages.add_message(request, messages.ERROR, "Cashless server OFFLINE or BAD KEY")

        super().save_model(request, obj, form, change)


staff_admin_site.register(Configuration, ConfigurationAdmin)


class TagAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "color",
    ]
    fields = list_display
    readonly_fields = ['uuid', ]

staff_admin_site.register(Tag, TagAdmin)


class CustomEventForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        config = Configuration.get_solo()
        self.fields['jauge_max'].initial = config.jauge_max


class EventAdmin(admin.ModelAdmin):
    form = CustomEventForm
    fieldsets = (
        ('Nouvel évènement', {
            'fields': (
                'name',
                'datetime',
                'img',
                'short_description',
                'long_description',
                'published',
            )
        }),
        ('Articles', {
            'fields': (
                'products',
            )
        }),
        ('Options', {
            'fields': (
                'jauge_max',
                # 'max_per_user',
                'tag',
                'options_radio',
                'options_checkbox',
            )
        }),
        ('Cashless', {
            'fields': (
                # 'cashless',
                'minimum_cashless_required',
            )
        }),
    )

    list_display = [
        'name',
        'reservations',
        'datetime',
    ]
    readonly_fields = (
        'reservations',
    )
    search_fields = ['name']

    # pour selectionner uniquement les articles ventes et retour consigne
    def formfield_for_manytomany(self, db_field, request, **kwargs):

        produits_non_affichables = [Product.RECHARGE_CASHLESS, Product.DON, Product.ADHESION, Product.FREERES]
        if db_field.name == "products":
            kwargs["queryset"] = Product.objects \
                .exclude(
                categorie_article__in=produits_non_affichables) \
                .exclude(archive=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        # On check si le cashless est opé.
        # if obj.recharge_cashless:
        #     config = Configuration.get_solo()
        #     if config.check_serveur_cashless():
        #         messages.add_message(request, messages.INFO, f"Cashless server ONLINE")
        #     else:
        #         obj.recharge_cashless = False
        #         messages.add_message(request, messages.ERROR, "Cashless server OFFLINE or BAD KEY")

        super().save_model(request, obj, form, change)

        # import ipdb; ipdb.set_trace()


staff_admin_site.register(Event, EventAdmin)


# class OptionGeneraleAdmin(admin.ModelAdmin):
#     list_display = (
#         'name',
#         'poids',
#     )
#     list_editable = (
#         'poids',
#     )
#
#
# staff_admin_site.register(OptionGenerale, OptionGeneraleAdmin)


# class QuantitiesSoldAdmin(admin.ModelAdmin):
#     list_display = (
#         'price',
#         'event',
#         'qty',
#     )
# staff_admin_site.register(QuantitiesSold, QuantitiesSoldAdmin)


class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        'datetime',
        'user_commande',
        'event',
        'status',
        'total_paid',
    )
    # readonly_fields = list_display
    # search_fields = ['event']


# staff_admin_site.register(Reservation, ReservationAdmin)


class EventFilter(SimpleListFilter):
    title = _('Évènement')
    parameter_name = 'reservation__event__name'

    def lookups(self, request, model_admin):
        events = Event.objects.filter(
            datetime__gt=(datetime.datetime.now() - datetime.timedelta(days=2)).date(),
        )

        tuples_list = []
        for event in events:
            if event.reservation.count() > 0:
                t = (event.uuid, event.name.capitalize())
                tuples_list.append(t)
        return tuples_list

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        else:
            return queryset.filter(reservation__event__uuid=self.value())


def valider_ticket(modeladmin, request, queryset):
    queryset.update(status=Ticket.SCANNED)


valider_ticket.short_description = "Valider le/les tickets"


class TicketAdmin(admin.ModelAdmin):
    list_display = [
        'reservations',
        'first_name',
        'last_name',
        'event',
        'options',
        'state',
    ]

    # list_editable = ['status',]
    readonly_fields = list_display
    actions = [valider_ticket, ]
    ordering = ('-reservation__datetime',)

    # list_filter = [EventFilter, ]

    # list_filter = (
    #     EventFilter,
    # 'reservation__uuid'
    # )

    search_fields = (
        'first_name',
        'last_name',
        'reservation__user_commande__email'
    )

    def state(self, obj):
        if obj.status == Ticket.NOT_SCANNED:
            return format_html(
                f'<a  href="{reverse("staff_admin:ticket-scann", args=[obj.pk])}" class="button">Valider</a>&nbsp;',
            )
        elif obj.status == Ticket.SCANNED:
            return 'Validé'
        else:
            for choice in Reservation.TYPE_CHOICES:
                if choice[0] == obj.reservation.status:
                    return choice[1]

    state.short_description = 'Etat'
    state.allow_tags = True

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            url(
                r'^(?P<ticket_pk>.+)/scanner/$',
                self.admin_site.admin_view(self.scanner),
                name='ticket-scann',
            ),
        ]
        return custom_urls + urls

    def scanner(self, request, ticket_pk, *arg, **kwarg):
        print(ticket_pk)
        ticket = Ticket.objects.get(pk=ticket_pk)
        ticket.status = Ticket.SCANNED
        ticket.save()
        messages.add_message(
            request,
            messages.SUCCESS,
            f"Ticket validé. Statut scanné."
        )
        # context = self.admin_site.each_context(request)
        return HttpResponseRedirect(
            reverse("staff_admin:BaseBillet_ticket_changelist")
        )

    def reservations(self, obj):
        return format_html(
            '<a  '
            f'href="{reverse("staff_admin:BaseBillet_ticket_changelist")}?reservation__uuid={obj.reservation.pk}">'
            f'{obj.reservation}'
            f'</a>&nbsp;'
        )

    reservations.short_description = 'Reservations'
    reservations.allow_tags = True

    def has_delete_permission(self, request, obj=None):
        # return request.user.is_superuser
        return False

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        qs = super(TicketAdmin, self).get_queryset(request)
        future_events = qs.filter(
            reservation__event__datetime__gt=(datetime.datetime.now() - datetime.timedelta(days=2)).date(),
        )
        return future_events


staff_admin_site.register(Ticket, TicketAdmin)


class ProductAdminCustomForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = (
            'name',
            'categorie_article',
            'short_description',
            'long_description',
            'img',
            'poids',
            "tag",
            "option_generale_radio",
            "option_generale_checkbox",
            "legal_link",
        )

    def clean(self):
        cleaned_data = self.cleaned_data
        categorie = cleaned_data.get('categorie_article')
        if categorie == Product.NONE:
            raise forms.ValidationError(_("Merci de renseigner une catégorie pour cet article."))
        return cleaned_data


class ProductAdmin(admin.ModelAdmin):
    exclude = ('publish',)
    form = ProductAdminCustomForm
    list_display = (
        'name',
        'img',
        'poids',
        'categorie_article',
        'send_to_cashless',
    )

    list_editable = (
        'poids',
    )

    def get_queryset(self, request):
        # On retire les recharges cashless et l'article Don
        # Pas besoin de les afficher, ils se créent automatiquement.
        qs = super().get_queryset(request)
        return qs.exclude(categorie_article__in=[Product.RECHARGE_CASHLESS, Product.DON])


staff_admin_site.register(Product, ProductAdmin)


class PriceAdmin(admin.ModelAdmin):
    list_display = (
        'product',
        'name',
        'prix',
        'adhesion_obligatoire',
        'subscription_type',
        'recurring_payment'
    )
    ordering = ('product',)

    def get_queryset(self, request):
        # On retire les recharges cashless et l'article Don
        # Pas besoin de les afficher, ils se créent automatiquement.
        qs = super().get_queryset(request)
        return qs.exclude(product__categorie_article__in=[Product.RECHARGE_CASHLESS, Product.DON])


staff_admin_site.register(Price, PriceAdmin)


# class ProductSoldAdmin(admin.ModelAdmin):
#     list_display = (
#         'product',
#         'event',
#         'img',
#         'id_product_stripe',
#     )
#
#
# staff_admin_site.register(ProductSold, ProductSoldAdmin)
#
#
# class PricesSoldAdmin(admin.ModelAdmin):
#     list_display = (
#         'productsold',
#         'price',
#         'qty_solded',
#         'id_price_stripe',
#     )
#
#
# staff_admin_site.register(PriceSold, PricesSoldAdmin)


class PaiementStripeAdmin(admin.ModelAdmin):
    list_display = (
        'uuid_8',
        'user',
        'total',
        'order_date',
        'status',
        'traitement_en_cours',
        'source_traitement',
        'source',
        'articles',
    )
    readonly_fields = list_display
    ordering = ('-order_date',)

    def has_delete_permission(self, request, obj=None):
        # return request.user.is_superuser
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

staff_admin_site.register(Paiement_stripe, PaiementStripeAdmin)


# class LigneArticleAdmin(admin.ModelAdmin):
#     list_display = (
#         'datetime',
#         'pricesold',
#         'qty',
#         'carte',
#         'status',
#         'paiement_stripe',
#         'status_stripe'
#     )
#     ordering = ('-datetime',)
#
#
# staff_admin_site.register(LigneArticle, LigneArticleAdmin)


class MembershipAdmin(admin.ModelAdmin):
    list_display = (
        # 'last_name',
        # 'first_name',
        'user',
        'product_name',
        'price',
        'options',
        'deadline',
        'is_valid',
        'date_added',
        'first_contribution',
        'last_contribution',
        'contribution_value',
        # 'last_action',
        'postal_code',
        'status',
        # 'birth_date',
        # 'phone',
        # 'commentaire',
    )
    ordering = ('-date_added',)
    search_fields = ('user__email','user__first_name', 'user__last_name')

staff_admin_site.register(Membership, MembershipAdmin)

staff_admin_site.register(OptionGenerale, admin.ModelAdmin)
