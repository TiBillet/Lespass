import datetime

from django.conf.urls import url
from django.contrib import admin, messages
from django.contrib.admin import AdminSite, SimpleListFilter
from django.contrib.admin.views.main import ChangeList
from django.contrib.auth.models import Group
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from solo.admin import SingletonModelAdmin
from django.utils.translation import ugettext_lazy as _

from AuthBillet.models import HumanUser, SuperHumanUser, TermUser
from BaseBillet.models import Configuration, Event, OptionGenerale, Product, Price, Reservation, LigneArticle, Ticket, \
    Paiement_stripe, ProductSold, PriceSold, Membership
from django.contrib.auth.admin import UserAdmin

from Customers.models import Client


class StaffAdminSite(AdminSite):
    site_header = "TiBillet Staff Admin"
    site_title = "TiBillet Staff Admin"
    site_url = '/'

    def has_permission(self, request):
        """
        Removed check for is_staff.
        """
        try:
            if request.tenant in request.user.client_admin.all():
                return request.user.is_staff
            elif request.user.client_source == Client.objects.get(schema_name="public"):
                return request.user.is_superuser
            else:
                return False
        except AttributeError:
            # AttributeError: 'AnonymousUser' object has no attribute 'client_source'
            return False
        except Exception as e:
            raise e


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
            'fields': ('email', 'password1', 'password2', 'is_active')}
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


class HumanUserAdmin(UserAdminTibillet):
    pass


staff_admin_site.register(HumanUser, HumanUserAdmin)


class SuperHumanUserAdmin(UserAdminTibillet):
    def save_model(self, request, obj, form, change):
        super(SuperHumanUserAdmin, self).save_model(request, obj, form, change)

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


########################################################################
class ConfigurationAdmin(SingletonModelAdmin):
    # readonly_fields = []

    fieldsets = (
        (None, {
            'fields': (
                'organisation',
                'short_description',
                'long_description',
                'logo',
                'img',
                'adress',
                'phone',
                'email',
                'site_web',
                'map_img',
            )
        }),
        ('Restaurant', {
            'fields': (
                'carte_restaurant',
            ),
        }),
        ('Social', {
            'fields': (
                'twitter',
                'facebook',
                'instagram',
            ),
        }),
        ('Adhésions', {
            'fields': (
                'adhesion_obligatoire',
                'button_adhesion',
            ),
        }),
        ('Paiements', {
            'fields': (
                # 'stripe_api_key',
                # 'stripe_test_api_key',
                'stripe_mode_test',
            ),
        }),
        ('Billetterie', {
            'fields': (
                'activer_billetterie',
                # 'template_billetterie',
                # 'template_meta',
                'jauge_max',
                'option_generale_radio',
                'option_generale_checkbox',
            ),
        }),
        ('Cashless', {
            'fields': (
                'server_cashless',
                'key_cashless',
            ),
        }),
        # ('Mailing', {
        #     'fields': (
        #         'activate_mailjet',
        #         'email_confirm_template',
        #     ),
        # }),
    )


staff_admin_site.register(Configuration, ConfigurationAdmin)


class EventAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'reservations',
        'datetime',
    )
    readonly_fields = (
        'reservations',
    )
    search_fields = ['name']


staff_admin_site.register(Event, EventAdmin)


class OptionGeneraleAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'poids',
    )
    list_editable = (
        'poids',
    )


staff_admin_site.register(OptionGenerale, OptionGeneraleAdmin)


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


staff_admin_site.register(Reservation, ReservationAdmin)


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
        else :
            return obj.status

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


class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'publish',
        'img',
        'categorie_article',
        'send_to_cashless',
    )

    list_editable = (
        'publish',
    )


staff_admin_site.register(Product, ProductAdmin)


class PriceAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'product',
        'prix',
        'adhesion_obligatoire',
        'subscription_type'
    )
    ordering = ('product', 'name')


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
    )
    ordering = ('-order_date',)


staff_admin_site.register(Paiement_stripe, PaiementStripeAdmin)


class LigneArticleAdmin(admin.ModelAdmin):
    list_display = (
        'datetime',
        'pricesold',
        'qty',
        'carte',
        'status',
        'paiement_stripe',
        'status_stripe'
    )
    ordering = ('-datetime',)


staff_admin_site.register(LigneArticle, LigneArticleAdmin)


class MembershipAdmin(admin.ModelAdmin):
    list_display = (
        'last_name',
        'first_name',
        'user',
        'product_name',
        'price',
        'is_valid',
        'deadline',
        'date_added',
        'first_contribution',
        'last_contribution',
        'contribution_value',
        'last_action',
        'postal_code',
        'birth_date',
        'phone',
        'commentaire',
    )
    ordering = ('-date_added',)


staff_admin_site.register(Membership, MembershipAdmin)
