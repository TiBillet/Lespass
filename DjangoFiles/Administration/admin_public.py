from django.contrib import admin
from django.contrib.admin import AdminSite
from Customers.models import Client, Domain
# Register your models here.

class PublicAdminSite(AdminSite):
    site_header = "TiBillet Public Admin"
    site_title = "TiBillet Public Admin"
    site_url = '/'

    def has_permission(self, request):
        return request.user.is_superuser


public_admin_site = PublicAdminSite(name='public_admin')


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
