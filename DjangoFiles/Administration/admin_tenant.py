from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth.models import Group
from solo.admin import SingletonModelAdmin

from AuthBillet.models import HumanUser, SuperHumanUser, TermUser
from BaseBillet.models import Configuration, Event, OptionGenerale
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
    list_display = ('email', 'is_active')
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
    ordering = ('email',)

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


staff_admin_site.register(Configuration, SingletonModelAdmin)


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
