"""
Site admin root historique — DESACTIVE.
Historic root admin site — DISABLED.

Tout l'admin transite par staff_admin_site (Unfold) defini dans
Administration/admin/site.py et enregistre dans Administration/admin/*.py.

Ce fichier est conserve pour reference pendant la migration V1 -> V2.
Toutes les declarations sont commentees ; les imports restent pour
ne pas casser un eventuel import side-effect ailleurs dans le code.

This file is kept for reference during V1 -> V2 migration.
All declarations are commented out; imports stay to avoid breaking
any side-effect import elsewhere in the code.
"""
import logging



logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tout le code historique de ce fichier est commente.
# Voir Administration/admin/*.py pour l'admin actuel.
# All historical code in this file is commented out.
# See Administration/admin/*.py for the current admin.
# ---------------------------------------------------------------------------

#
# class PublicAdminSite(AdminSite):
#     site_header = "TiBillet Public Admin"
#     site_title = "TiBillet Public Admin"
#     site_url = '/'
#
#     def has_permission(self, request):
#         logger.warning(
#             f"Tenant AdminSite.has_permission : {request.user} - {request.user.client_source if request.user.is_authenticated else 'No client source'} - ip : {get_client_ip(request)}")
#
#         try:
#             if request.user.client_source.categorie == Client.ROOT:
#                 return request.user.is_superuser
#         except AttributeError as e:
#             logger.warning(f"{e} : AnonymousUser for admin ?")
#             return False
#         except Exception as e:
#             raise e
#         return False
#
# root_admin_site = PublicAdminSite(name='public_admin')
#
# # USER
# class UserAdminTibillet(UserAdmin):
#     ...
# root_admin_site.register(TibilletUser, UserAdminTibillet)
#
# class CustomGroupAdmin(GroupAdmin):
#     pass
# root_admin_site.register(Group, CustomGroupAdmin)
#
# # CLIENT / DOMAIN
# class DomainInline(admin.TabularInline):
#     model = Domain
#
# class ClientAdmin(admin.ModelAdmin):
#     inlines = [DomainInline]
#     list_display = ('schema_name', 'name', 'categorie', 'created_on')
# root_admin_site.register(Client, ClientAdmin)
# root_admin_site.register(Domain, admin.ModelAdmin)
#
# # CARTE CASHLESS (deplace vers Administration/admin/cards.py)
# # CARTE CASHLESS (moved to Administration/admin/cards.py)
# # class CarteCashlessAdmin(admin.ModelAdmin):
# #     list_display = ('user', 'tag_id', 'wallets', 'number', 'uuid', 'get_origin')
# # root_admin_site.register(CarteCashless, CarteCashlessAdmin)
#
# # AUTRES
# root_admin_site.register(ProductDirectory, admin.ModelAdmin)
# root_admin_site.register(EventDirectory, admin.ModelAdmin)
# root_admin_site.register(RootConfiguration, SingletonModelAdmin)
