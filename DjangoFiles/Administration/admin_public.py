from django.contrib import admin, messages
from django.contrib.auth.models import Group

from django.contrib.admin import AdminSite
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django_tenants.utils import tenant_context
from solo.admin import SingletonModelAdmin

from AuthBillet.utils import get_client_ip
from BaseBillet.models import Configuration
from Customers.models import Client, Domain
from AuthBillet.models import TibilletUser, HumanUser, TermUser, SuperHumanUser
from django.utils.translation import gettext, gettext_lazy as _

from MetaBillet.models import EventDirectory, ProductDirectory
from QrcodeCashless.models import Detail, CarteCashless, FederatedCashless, SyncFederatedLog

# from boutique.models import Category, Product, Tag, VAT, Event, LandingPageContent, Price
# from solo.admin import SingletonModelAdmin
from root_billet.models import RootConfiguration
import logging

logger = logging.getLogger(__name__)


class PublicAdminSite(AdminSite):
    site_header = "TiBillet Public Admin"
    site_title = "TiBillet Public Admin"
    site_url = '/'

    def has_permission(self, request):
        logger.warning(f"Tenant AdminSite.has_permission : {request.user} - {request.user.client_source if request.user.is_authenticated else 'No client source'} - ip : {get_client_ip(request)}")

        # import ipdb; ipdb.set_trace()
        try:
            if request.user.client_source.categorie == Client.ROOT:
                return request.user.is_superuser
        except AttributeError as e:
            logger.warning(f"{e} : AnonymousUser for admin ?")
            return False
        except Exception as e:
            raise e
        return False


public_admin_site = PublicAdminSite(name='public_admin')


# USER
# -------------------------------------/

class UserAdminTibillet(UserAdmin):
    list_display = (
        'email',
        'email_error',
        'is_active',
        'is_staff',
        'is_superuser',
        # 'can_create_tenant',
        'client_source',
        # 'achat',
        'administre',
        # 'espece',
        # 'groups',
    )

    list_filter = (
        'email',
        'is_active',
        'client_source',
        'espece',
    )

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {
            'fields': (
                'first_name',
                'last_name',
                'email',
                'email_error',
                'phone',
                'client_source',
                'client_admin',
                'client_achat',
                'offre',
            )}),
        (_('Permissions'), {
            'fields': (
                'is_active',
                'is_staff',
                'is_superuser',
                'can_create_tenant',
                'groups',
                'user_permissions',
            ),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    #
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email',
                'password1',
                'password2',
                'is_active',
                'client_source',
                'client_achat',
                'espece',
            )}
         ),
    )

    search_fields = ('email',)
    ordering = ('email',)

    # def save_model(self, request, obj, form, change):
    #     obj.client_source = request.tenant
    #     obj.save()
    #
    #     staff_group = Group.objects.get_or_create(name="staff")[0]
    #     obj.groups.add(staff_group)
    #     obj.client_achat.add(request.tenant)
    #
    #     super(UserAdminTibillet, self).save_model(request, obj, form, change)


public_admin_site.register(TibilletUser, UserAdminTibillet)


class CustomGroupAdmin(GroupAdmin):
    pass


public_admin_site.register(Group, CustomGroupAdmin)


# -------------------------------------/
# USER
# -------------------------------------/

class DomainInline(admin.TabularInline):
    model = Domain


class ClientAdmin(admin.ModelAdmin):
    inlines = [DomainInline]
    list_display = (
        'schema_name',
        'name',
        'categorie',
        # 'paid_until',
        # 'on_trial',
        'created_on',
    )


public_admin_site.register(Client, ClientAdmin)

public_admin_site.register(Domain, admin.ModelAdmin)


class DetailAdmin(admin.ModelAdmin):
    list_display = (
        'slug',
        'base_url',
        'origine',
        'generation',
        'img_url',
        'img',
    )


public_admin_site.register(Detail, DetailAdmin)


class CarteCashlessAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'tag_id',
        'wallets',
        'number',
        'uuid',
        'get_origin',
    )

    def get_origin(self, obj):
        return obj.detail.origine

    get_origin.short_description = 'Origine'

    search_fields = ('tag_id', 'uuid', 'number')
    list_filter = ('tag_id', 'uuid', 'number', 'detail__origine')


public_admin_site.register(CarteCashless, CarteCashlessAdmin)

public_admin_site.register(ProductDirectory, admin.ModelAdmin)
public_admin_site.register(EventDirectory, admin.ModelAdmin)
public_admin_site.register(RootConfiguration, SingletonModelAdmin)

class FederatedCashlessAdmin(admin.ModelAdmin):
    list_display = (
        'client',
        'asset',
        'server_cashless',
        'cashless_up',
    )

    def cashless_up(self, obj):
        with tenant_context(obj.client):
            conf = Configuration.get_solo()
            return conf.check_serveur_cashless()

    def save_model(self, request, obj, form, change):
        obj: FederatedCashless
        if obj.server_cashless and obj.key_cashless:
            with tenant_context(obj.client):
                conf = Configuration.get_solo()
                if obj.key_cashless != conf.key_cashless \
                        or obj.server_cashless != conf.server_cashless:
                    conf.key_cashless = obj.key_cashless
                    conf.server_cashless = obj.server_cashless

                    if conf.check_serveur_cashless():
                        messages.add_message(request, messages.INFO, f"Cashless server ONLINE")
                    else:
                        messages.add_message(request, messages.ERROR, "Cashless server OFFLINE or BAD KEY")

        super().save_model(request, obj, form, change)


public_admin_site.register(FederatedCashless, FederatedCashlessAdmin)

class SyncFederatedLogAdmin(admin.ModelAdmin):
    list_display = (
        'categorie',
        'date',
        'card',
        'old_qty',
        'new_qty',
        'client_source',
        'wallet',
        'first_uuid',
        'etat_client_sync',
        'is_sync',
    )
    readonly_fields = list_display

    def first_uuid(self, obj):
        return f"{str(obj.uuid).split('-')[0]}"

public_admin_site.register(SyncFederatedLog, SyncFederatedLogAdmin)

