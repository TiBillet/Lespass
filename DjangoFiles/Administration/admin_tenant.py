from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth.models import Group
from solo.admin import SingletonModelAdmin

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


staff_admin_site.register(Reservation, ReservationAdmin)


class TicketAdmin(admin.ModelAdmin):
    list_display = [
        'first_name',
        'last_name',
        'event',
        'reservation',
        'status',
        'datetime',
    ]
    readonly_fields = list_display
    ordering = ('-reservation__datetime', )


staff_admin_site.register(Ticket, TicketAdmin)


class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'publish',
        'img',
        'categorie_article',
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
        'adhesion_obligatoire'
    )
    ordering = ('product', 'name')


staff_admin_site.register(Price, PriceAdmin)


class ProductSoldAdmin(admin.ModelAdmin):
    list_display = (
        'product',
        'event',
        'img',
        'id_product_stripe',
    )


staff_admin_site.register(ProductSold, ProductSoldAdmin)


class PricesSoldAdmin(admin.ModelAdmin):
    list_display = (
        'productsold',
        'price',
        'qty_solded',
        'id_price_stripe',
    )


staff_admin_site.register(PriceSold, PricesSoldAdmin)


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
