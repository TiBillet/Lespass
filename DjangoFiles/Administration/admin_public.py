from django.contrib import admin
from django.contrib.auth.models import Group

from django.contrib.admin import AdminSite
from django.contrib.auth.admin import UserAdmin, GroupAdmin

from Customers.models import Client, Domain
from AuthBillet.models import TibilletUser, HumanUser, TermUser, SuperHumanUser
from django.utils.translation import gettext, gettext_lazy as _


# from boutique.models import Category, Product, Tag, VAT, Event, LandingPageContent, Billet
# from solo.admin import SingletonModelAdmin

class PublicAdminSite(AdminSite):
    site_header = "TiBillet Public Admin"
    site_title = "TiBillet Public Admin"
    site_url = '/'

    def has_permission(self, request):
        return request.user.is_superuser


public_admin_site = PublicAdminSite(name='public_admin')


# USER
# -------------------------------------/

class UserAdminTibillet(UserAdmin):
    list_display = (
        'email',
        'is_active',
        'is_staff',
        'is_superuser',
        'client_source',
        'achat',
        'administre',
        'espece',
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
        'paid_until',
        'on_trial',
        'created_on',
    )


public_admin_site.register(Client, ClientAdmin)
