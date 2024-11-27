import logging

from django.conf import settings
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth import login
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import Group
from django.db import connection
from django.utils.translation import gettext_lazy as _
from solo.admin import SingletonModelAdmin

from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_client_ip
from Customers.models import Client, Domain
from MetaBillet.models import EventDirectory, ProductDirectory
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)


class PublicAdminSite(AdminSite):
    site_header = "TiBillet Public Admin"
    site_title = "TiBillet Public Admin"
    site_url = '/'

    def has_permission(self, request):
        logger.warning(
            f"Tenant AdminSite.has_permission : {request.user} - {request.user.client_source if request.user.is_authenticated else 'No client source'} - ip : {get_client_ip(request)}")

        # Dans le cas ou on debug, on se log auto :
        # if settings.DEBUG:
        #     tenant : Client = connection.tenant
        #     admin_user = tenant.user_admin.first()
        #     if admin_user:
        #         login(request, admin_user)
        #         return True


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

"""
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
"""

# class CarteCashlessAdmin(admin.ModelAdmin):
#     list_display = (
#         'user',
#         'tag_id',
#         'wallets',
#         'number',
#         'uuid',
#         'get_origin',
#     )
#
#     def get_origin(self, obj):
#         return obj.detail.origine
#
#     get_origin.short_description = 'Origine'
#
#     search_fields = ('tag_id', 'uuid', 'number')
#     list_filter = ('tag_id', 'uuid', 'number', 'detail__origine')


# public_admin_site.register(CarteCashless, CarteCashlessAdmin)

public_admin_site.register(ProductDirectory, admin.ModelAdmin)
public_admin_site.register(EventDirectory, admin.ModelAdmin)
public_admin_site.register(RootConfiguration, SingletonModelAdmin)
