import logging
from uuid import uuid4

from django.contrib import admin, messages
from django.db import connection
from django.forms import ModelForm
from django.shortcuts import redirect
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import action, display
from unfold.widgets import UnfoldAdminColorInputWidget

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from BaseBillet.models import Tag, Carrousel, FederatedPlace
from Customers.models import Client

logger = logging.getLogger(__name__)


class TagForm(ModelForm):
    class Meta:
        model = Tag
        fields = '__all__'
        widgets = {
            'color': UnfoldAdminColorInputWidget(),
        }


@admin.register(Carrousel, site=staff_admin_site)
class CarrouselAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    ordering = ('order', 'name')
    list_display = ('name', 'on_event_list_page', 'order', 'link', 'events_names')
    list_editable = ('on_event_list_page', 'order')

    search_fields = ('name',)

    @display(description=_("Included in events"))
    def events_names(self, instance: Carrousel):
        return ", ".join([event.name for event in instance.events.all()])

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


@admin.register(Tag, site=staff_admin_site)
class TagAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    actions_list = ["sync_tags_action"]

    form = TagForm
    fields = ("name", "color")
    list_display = [
        "name",
        "_color",
    ]
    readonly_fields = ['uuid', ]
    search_fields = ['name']

    def _color(self, obj):
        # Add link to change page around color div
        return format_html(
            '<a href="{url}">'
            '<div style="width: 20px; height: 20px; background-color: {color}; border: 1px solid #000;"></div>'
            '</a>',
            url=reverse('staff_admin:BaseBillet_tag_change', args=[obj.pk]),
            color=obj.color,
        )

    _color.short_description = _("Color")

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_sync_tags_action_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    @action(
        description=_("Synchronize tags"),
        url_path="sync_tags",
        permissions=["sync_tags_action"],
    )
    def sync_tags_action(self, request):
        current_tenant = connection.tenant

        # 1. Identifier les parents (ceux qui nous fédèrent)
        # On utilise une requête SQL optimisée pour éviter 600 changements de contexte
        from django.db import connection as db_connection
        cursor = db_connection.cursor()

        # On récupère les schémas possédant la table FederatedPlace
        cursor.execute("SELECT table_schema FROM information_schema.tables WHERE table_name = 'BaseBillet_federatedplace'")
        schemas_with_fed = {row[0] for row in cursor.fetchall()}

        # On exclut le public, le nôtre et les schémas système
        schemas_to_check = [s for s in schemas_with_fed if s not in ['public', 'information_schema', 'pg_catalog', current_tenant.schema_name]]

        parents_pks = []
        if schemas_to_check:
            batch_size = 50
            for i in range(0, len(schemas_to_check), batch_size):
                batch = schemas_to_check[i:i + batch_size]
                query_parts = []
                params = []
                for schema in batch:
                    query_parts.append(f'SELECT %s WHERE EXISTS (SELECT 1 FROM "{schema}"."BaseBillet_federatedplace" WHERE tenant_id = %s)')
                    params.extend([schema, current_tenant.pk])

                if query_parts:
                    full_query = " UNION ALL ".join(query_parts)
                    cursor.execute(full_query, params)
                    for row in cursor.fetchall():
                        parents_pks.append(row[0])

        parents = list(Client.objects.filter(schema_name__in=parents_pks))

        # 2. Identifier les enfants (ceux que nous fédérons)
        children = [fp.tenant for fp in FederatedPlace.objects.all().select_related('tenant')]

        # Combiner et dédupliquer en gardant l'ordre (parents d'abord)
        seen = {current_tenant.pk}
        tenants_to_sync = []
        for t in parents + children:
            if t.pk not in seen:
                tenants_to_sync.append(t)
                seen.add(t.pk)

        # 3. Collecter tous les tags distants en une seule fois
        all_remote_tags = {}
        if tenants_to_sync:
            # On vérifie quels schémas ont la table Tag
            cursor.execute("SELECT table_schema FROM information_schema.tables WHERE table_name = 'BaseBillet_tag'")
            schemas_with_tags = {row[0] for row in cursor.fetchall()}

            schemas_to_fetch = [t.schema_name for t in tenants_to_sync if t.schema_name in schemas_with_tags]

            if schemas_to_fetch:
                batch_size = 50
                for i in range(0, len(schemas_to_fetch), batch_size):
                    batch = schemas_to_fetch[i:i + batch_size]
                    query_parts = []
                    for schema in batch:
                        query_parts.append(f'SELECT name, color FROM "{schema}"."BaseBillet_tag"')

                    full_query = " UNION ALL ".join(query_parts)
                    cursor.execute(full_query)
                    for name, color in cursor.fetchall():
                        # Le dernier rencontré gagne (priorité aux enfants sur les parents si conflit)
                        all_remote_tags[name] = color

        # 4. Appliquer les changements localement en masse
        local_tags = {t.name: t for t in Tag.objects.all()}
        tags_created = 0
        tags_updated = 0

        to_create = []
        to_update = []

        for name, color in all_remote_tags.items():
            cleaned_color = Tag._clean_hex(color, "#0dcaf0")
            if name in local_tags:
                tag = local_tags[name]
                if tag.color != cleaned_color:
                    tag.color = cleaned_color
                    to_update.append(tag)
            else:
                to_create.append(Tag(
                    uuid=uuid4(),
                    name=name,
                    slug=slugify(name),
                    color=cleaned_color
                ))

        if to_create:
            Tag.objects.bulk_create(to_create)
            tags_created = len(to_create)

        if to_update:
            Tag.objects.bulk_update(to_update, ['color'])
            tags_updated = len(to_update)

        messages.success(request, _("Synchronization complete: {} tags created, {} tags updated.").format(tags_created, tags_updated))
        return redirect(request.META.get("HTTP_REFERER", reverse("staff_admin:BaseBillet_tag_changelist")))
