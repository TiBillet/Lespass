from django.contrib import admin
from django.contrib.admin import AdminSite
from solo.admin import SingletonModelAdmin

from BaseBillet.models import Configuration, Event, OptionGenerale


class StaffAdminSite(AdminSite):
    site_header = "TiBillet Staff Admin"
    site_title = "TiBillet Staff Admin"
    site_url = '/'

    def has_permission(self, request):
        return request.user.is_superuser


staff_admin_site = StaffAdminSite(name='staff_admin')


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
