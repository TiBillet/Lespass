import datetime
import logging

from django import forms
from django.contrib import admin
from django.db import models
from django.contrib import messages
from django.contrib.admin import SimpleListFilter
from django.forms import ModelForm, TextInput
from django.http import HttpResponseRedirect
from django.urls import reverse, re_path
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from solo.admin import SingletonModelAdmin
from unfold.admin import ModelAdmin
from unfold.sites import UnfoldAdminSite

from BaseBillet.models import Configuration, Event, OptionGenerale, Product, Price, Reservation, Ticket, \
    Paiement_stripe, Membership, Webhook, Tag

logger = logging.getLogger(__name__)


class StaffAdminSite(UnfoldAdminSite):
    pass


staff_admin_site = StaffAdminSite(name='staff_admin')

""" Configuration UNFOLD """


def badge_callback(request):
    return 3


@admin.register(Webhook, site=staff_admin_site)
class WebhookAdmin(ModelAdmin):
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


########################################################################
@admin.register(Configuration, site=staff_admin_site)
class ConfigurationAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

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
                'fuseau_horaire',
                # 'map_img',
            )
        }),
        ('Stripe', {
            'fields': (
                # 'vat_taxe',
                'onboard_stripe',
                # 'stripe_mode_test',
            ),
        }),
        ('Fédération', {
            'fields': (
                'federated_with',
            ),
        }),
        # ('Options générales', {
        #     'fields': (
        #         'need_name',
        #         'jauge_max',
        #         'option_generale_radio',
        #         'option_generale_checkbox',
        #     ),
        # }),
        ('Ghost', {
            'fields': (
                'ghost_url',
                'ghost_key',
                'ghost_last_log',
            ),
        }),

    )
    readonly_fields = ['ghost_last_log', 'onboard_stripe', ]

    def save_model(self, request, obj, form, change):
        obj: Configuration
        if obj.server_cashless and obj.key_cashless:
            if obj.check_serveur_cashless():
                messages.add_message(request, messages.INFO, f"Cashless server ONLINE")
            else:
                messages.add_message(request, messages.ERROR, "Cashless server OFFLINE or BAD KEY")

        super().save_model(request, obj, form, change)


class TagForm(ModelForm):
    class Meta:
        model = Tag
        fields = '__all__'
        widgets = {
            'color': TextInput(attrs={'type': 'color'}),
        }


@admin.register(Tag, site=staff_admin_site)
class TagAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    form = TagForm
    fields = ("name", "color")
    list_display = [
        "name",
        "_color",
    ]
    readonly_fields = ['uuid', ]

    def _color(self, obj):
        return format_html(
            '<div style="width: 20px; height: 20px; background-color: {}; border: 1px solid #000;"></div>',
            obj.color, )

    _color.short_description = _("Couleur")

    # def has_view_or_change_permission(self, request, obj=None):
    #     return True
    #
    # def has_delete_permission(self, request, obj=None):
    # return False
    #
    # def has_add_permission(self, request):
    #     return False


"""



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
                'max_per_user',
                'tag',
                'options_radio',
                'options_checkbox',
            )
        }),
        ('Recurence', {
            'fields': (
                'recurrent',
                'booking',
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
        produits_non_affichables = [Product.RECHARGE_CASHLESS, Product.DON, Product.ADHESION]
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
            re_path(
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
            'nominative',
            'short_description',
            'long_description',
            'img',
            'poids',
            "tag",
            "option_generale_radio",
            "option_generale_checkbox",
            "legal_link",
            'publish',
            'archive',
        )

    def clean(self):
        cleaned_data = self.cleaned_data
        categorie = cleaned_data.get('categorie_article')
        if categorie == Product.NONE:
            raise forms.ValidationError(_("Merci de renseigner une catégorie pour cet article."))
        return cleaned_data


class ProductAdmin(admin.ModelAdmin):
    # exclude = ('publish',)
    form = ProductAdminCustomForm
    list_display = (
        'name',
        'img',
        'poids',
        'categorie_article',
        # 'send_to_cashless',
        'publish',
    )

    list_editable = (
        'poids',
    )

    def get_queryset(self, request):
        # On retire les recharges cashless et l'article Don
        # Pas besoin de les afficher, ils se créent automatiquement.
        qs = super().get_queryset(request)
        return qs.exclude(categorie_article__in=[Product.RECHARGE_CASHLESS, Product.DON]).exclude(archive=True)


staff_admin_site.register(Product, ProductAdmin)


class PriceAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'product',
        'prix',
        'adhesion_obligatoire',
        'subscription_type',
        'recurring_payment',
        'publish',
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
        # 'traitement_en_cours',
        # 'source_traitement',
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


def send_invoice(modeladmin, request, queryset):
    pass

def send_to_ghost(modeladmin, request, queryset):
    pass

class MembershipAdmin(admin.ModelAdmin):
    list_display = (
        'str_user',
        'last_name',
        'first_name',
        'product_name',
        'price',
        'options',
        'deadline',
        'is_valid',
        'date_added',
        # 'first_contribution',
        'last_contribution',
        'contribution_value',
        # 'last_action',
        # 'postal_code',
        'status',
        # 'birth_date',
        # 'phone',
        'commentaire',
    )

    fields = (
        'str_user',
        'last_name',
        'first_name',
        ('product_name', 'price'),
        ('last_contribution', 'contribution_value'),
        'options',
        'card_number',
        'commentaire',
    )

    readonly_fields = (
        'str_user',
        'date_added',
        'deadline',
        'is_valid',
        'options',
        'product_name',
        'last_contribution',
        'contribution_value',
        'card_number',
    )

    def str_user(self, obj: Membership):
        if obj.user :
            return obj.user.email
        elif obj.card_number:
            return obj.card_number
        return "Anonyme"
    str_user.short_description = 'User'

    def has_delete_permission(self, request, obj=None):
        # return request.user.is_superuser
        return False

    def has_add_permission(self, request):
        return False

    # def has_change_permission(self, request, obj=None):
    #     return False

    #TODO : actions
    # actions = [send_invoice, send_to_ghost ]
    ordering = ('-date_added',)
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'card_number')


staff_admin_site.register(Membership, MembershipAdmin)

staff_admin_site.register(OptionGenerale, admin.ModelAdmin)


"""
