"""
fedow_core/admin.py — Enregistrement des modeles fedow_core dans Unfold.
fedow_core/admin.py — Registration of fedow_core models in Unfold admin.

Les modeles sont enregistres sur staff_admin_site (le site admin Unfold du projet).
Token et Transaction sont en lecture seule : on ne les modifie jamais a la main.
Asset et Federation sont editables par l'admin.

Models are registered on staff_admin_site (the project's Unfold admin site).
Token and Transaction are read-only: they are never modified manually.
Asset and Federation are editable by admin.

IMPORTANT — Filtrage par tenant :
fedow_core est en SHARED_APPS (schema public PostgreSQL).
Il n'y a PAS d'isolation automatique par schema.
Chaque admin DOIT overrider get_queryset() pour filtrer par tenant.
Sans ca, un admin verrait les donnees de TOUS les lieux.

IMPORTANT — Tenant filtering:
fedow_core is in SHARED_APPS (public PostgreSQL schema).
There is NO automatic schema isolation.
Every admin MUST override get_queryset() to filter by tenant.
Without this, an admin would see data from ALL venues.
"""

import logging

from django.contrib import admin, messages
from django.db import connection
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import re_path, reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from unfold.admin import ModelAdmin

from Administration.admin_tenant import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from AuthBillet.models import Wallet
from Customers.models import Client
from fedow_core.models import Asset, Federation, Token, Transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Asset : monnaies et types de tokens (editable)
# Asset: currencies and token types (editable)
#
# Flow d'invitation per-asset (inspire du pattern V1 AssetFedowPublicAdmin) :
# Per-asset invitation flow (inspired by V1 AssetFedowPublicAdmin pattern):
#   1. Le createur cree un asset (tenant_origin + wallet_origin auto-set)
#      Creator creates an asset (tenant_origin + wallet_origin auto-set)
#   2. Le createur invite des lieux via pending_invitations (autocomplete)
#      Creator invites venues via pending_invitations (autocomplete)
#   3. Le lieu invite voit l'invitation dans la changelist et accepte (POST)
#      Invited venue sees invitation in changelist and accepts (POST)
#   4. Le lieu est deplace de pending_invitations vers federated_with
#      Venue is moved from pending_invitations to federated_with
# ---------------------------------------------------------------------------

@admin.register(Asset, site=staff_admin_site)
class AssetAdmin(ModelAdmin):
    """
    Admin pour les assets (monnaies/tokens).
    Admin for assets (currencies/tokens).

    Permissions par role :
    - Le createur (tenant_origin) peut modifier l'asset et inviter d'autres lieux.
    - Les lieux federes (dans federated_with) voient l'asset en lecture seule.

    Permissions by role:
    - The creator (tenant_origin) can edit the asset and invite other venues.
    - Federated venues (in federated_with) see the asset as read-only.

    Filtre tenant : affiche les assets propres (tenant_origin)
    ET les assets federes avec ce lieu (federated_with).
    Tenant filter: shows own assets (tenant_origin)
    AND assets federated with this venue (federated_with).
    """
    list_display = [
        'name',
        'category',
        'currency_code',
        'active',
        'lieux_federes',
    ]
    list_filter = ['category', 'active', 'archive']
    search_fields = ['name', 'currency_code']

    # pending_invitations en autocomplete (le createur invite via ce champ).
    # federated_with en readonly (rempli automatiquement par accept_asset_invitation).
    # pending_invitations as autocomplete (creator invites via this field).
    # federated_with as readonly (filled automatically by accept_asset_invitation).
    autocomplete_fields = ['pending_invitations']

    # Template au-dessus de la liste : invitations en attente pour ce tenant.
    # Template above the list: pending invitations for this tenant.
    list_before_template = 'admin/asset/asset_changelist_invitations.html'

    compressed_fields = True
    warn_unsaved_form = True

    def lieux_federes(self, obj):
        """
        Affiche la liste des lieux federes dans la changelist.
        Shows the list of federated venues in the changelist.
        """
        noms_des_lieux = [lieu.name for lieu in obj.federated_with.all()]
        # Ajouter le createur en premier.
        # Add the creator first.
        noms_des_lieux.insert(0, obj.tenant_origin.name)
        return ', '.join(noms_des_lieux)
    lieux_federes.short_description = _('Lieux federes')

    # --- Permissions par role / Role-based permissions ---

    def has_change_permission(self, request, obj=None):
        """
        Seul le createur peut modifier l'asset.
        Only the creator can edit the asset.

        Si obj est None (appel generique pour la liste),
        on renvoie True pour que tous voient le lien "modifier"
        (qui mene a la vue lecture seule pour les non-createurs).
        If obj is None (generic call for the list),
        return True so everyone sees the "edit" link
        (which leads to read-only view for non-creators).
        """
        if obj is None:
            return True

        tenant_actuel = connection.tenant
        tenant_est_createur = (obj.tenant_origin_id == tenant_actuel.pk)
        return tenant_est_createur

    def has_delete_permission(self, request, obj=None):
        """
        Personne ne peut supprimer un asset depuis l'admin.
        Nobody can delete an asset from the admin.

        La suppression d'un asset est une operation dangereuse
        (les tokens et transactions en dependent). On archive a la place.
        Deleting an asset is dangerous (tokens and transactions depend on it).
        We archive instead.
        """
        return False

    # --- Queryset filtre par tenant / Tenant-filtered queryset ---

    def get_queryset(self, request):
        """
        Filtre les assets par tenant courant.
        Filters assets by current tenant.

        Affiche les assets propres (tenant_origin) ET les assets
        federes avec ce lieu (federated_with). Exclut les archives.
        Shows own assets (tenant_origin) AND assets federated
        with this venue (federated_with). Excludes archived.
        """
        queryset = super().get_queryset(request)
        tenant_actuel = connection.tenant
        assets_visibles = queryset.filter(
            Q(tenant_origin=tenant_actuel) | Q(federated_with=tenant_actuel)
        ).filter(
            archive=False,
        ).distinct().select_related('tenant_origin')
        return assets_visibles

    # --- Champs dynamiques / Dynamic fields ---

    def get_fields(self, request, obj=None):
        """
        Champs affiches selon le contexte (creation vs edition vs lecture).
        Fields shown depending on context (create vs edit vs read).

        Creation : nom, code devise, categorie.
        Edition (createur) : nom, code devise, categorie, pending_invitations, federated_with.
        Lecture (federe) : nom, code devise, categorie, federated_with.
        """
        # Formulaire de creation : champs minimaux.
        # Add form: minimal fields.
        if obj is None:
            return ['name', 'currency_code', 'category']

        tenant_actuel = connection.tenant
        tenant_est_createur = (obj.tenant_origin_id == tenant_actuel.pk)

        if tenant_est_createur:
            # Le createur voit pending_invitations + federated_with.
            # Creator sees pending_invitations + federated_with.
            return [
                'name', 'currency_code', 'category',
                'active',
                'pending_invitations', 'federated_with',
            ]
        else:
            # Un lieu federe voit tout en readonly (via get_readonly_fields).
            # A federated venue sees everything readonly (via get_readonly_fields).
            return ['name', 'currency_code', 'category', 'federated_with']

    def get_readonly_fields(self, request, obj=None):
        """
        Champs en lecture seule selon le role.
        Read-only fields depending on role.

        Creation : uuid et tenant_origin seulement.
        Edition (createur) : uuid, tenant_origin, dates, federated_with,
          + nom/code devise/categorie (immutables apres creation).
        Lecture (federe) : tout en readonly.
        """
        base_readonly = ['uuid', 'tenant_origin', 'created_at', 'last_update']

        if obj is None:
            return base_readonly

        tenant_actuel = connection.tenant
        tenant_est_createur = (obj.tenant_origin_id == tenant_actuel.pk)

        if tenant_est_createur:
            # Le createur ne peut pas changer nom/code/categorie apres creation.
            # federated_with est rempli automatiquement (pas editable).
            # Creator can't change name/code/category after creation.
            # federated_with is filled automatically (not editable).
            return base_readonly + ['name', 'currency_code', 'category', 'federated_with']
        else:
            # Un lieu federe voit tout en readonly.
            # A federated venue sees everything readonly.
            return base_readonly + [
                'name', 'currency_code', 'category', 'federated_with',
            ]

    def get_form(self, request, obj=None, **kwargs):
        """
        Limite les choix de categorie au formulaire de creation.
        Limits category choices on the add form.

        FED (federee) n'est pas proposee : c'est un asset systeme unique.
        FED (federated) is not offered: it's a unique system asset.
        """
        form = super().get_form(request, obj, **kwargs)
        if obj is None and 'category' in form.base_fields:
            categories_autorisees = [
                (Asset.TLF, dict(Asset.CATEGORY_CHOICES)[Asset.TLF]),
                (Asset.TNF, dict(Asset.CATEGORY_CHOICES)[Asset.TNF]),
                (Asset.TIM, dict(Asset.CATEGORY_CHOICES)[Asset.TIM]),
                (Asset.FID, dict(Asset.CATEGORY_CHOICES)[Asset.FID]),
            ]
            form.base_fields['category'].choices = categories_autorisees
        return form

    # --- Sauvegarde / Save ---

    def save_model(self, request, obj, form, change):
        """
        A la creation : auto-set tenant_origin et wallet_origin.
        On creation: auto-set tenant_origin and wallet_origin.

        L'admin ne choisit ni le tenant ni le wallet :
        un lieu cree toujours ses propres assets avec son propre wallet.
        Admin can't choose tenant or wallet:
        a venue always creates its own assets with its own wallet.
        """
        asset_est_nouveau = not change
        if asset_est_nouveau:
            tenant_actuel = connection.tenant
            obj.tenant_origin = tenant_actuel

            # Obtenir le wallet principal du tenant (le premier cree).
            # Un tenant peut avoir plusieurs wallets (utilisateur, lieu, etc.).
            # Get the tenant's primary wallet (first created).
            # A tenant can have multiple wallets (user, venue, etc.).
            wallet_du_tenant = Wallet.objects.filter(
                origin=tenant_actuel,
            ).first()

            if wallet_du_tenant is None:
                # Creer un wallet si le tenant n'en a pas encore.
                # Create a wallet if the tenant doesn't have one yet.
                wallet_du_tenant = Wallet.objects.create(
                    origin=tenant_actuel,
                    name=tenant_actuel.name,
                )

            obj.wallet_origin = wallet_du_tenant

        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        """
        Protege pending_invitations : seul le createur peut modifier ce champ.
        Protects pending_invitations: only the creator can modify this field.

        Si un lieu federe (non-createur) soumet le formulaire (ne devrait
        pas arriver grace a has_change_permission, mais defense en profondeur),
        on revert les pending_invitations a leur etat precedent.
        If a federated venue (non-creator) submits the form (shouldn't happen
        thanks to has_change_permission, but defense in depth),
        we revert pending_invitations to their previous state.
        """
        obj = form.instance

        # Sauvegarder l'etat avant le save M2M de Django.
        # Save state before Django's M2M save.
        invitations_precedentes = set()
        if obj.pk:
            invitations_precedentes = set(
                obj.pending_invitations.values_list('pk', flat=True)
            )

        super().save_related(request, form, formsets, change)

        # Verifier que le tenant est bien le createur.
        # Check that the tenant is the creator.
        tenant_actuel = connection.tenant
        tenant_est_createur = (obj.tenant_origin_id == tenant_actuel.pk)

        if obj.pk and not tenant_est_createur:
            # Revert les invitations au precedent etat.
            # Revert invitations to previous state.
            obj.pending_invitations.set(list(invitations_precedentes))
            messages.error(
                request,
                _("Seul le lieu createur peut envoyer des invitations."),
            )

    # --- URLs custom / Custom URLs ---

    def get_urls(self):
        """
        Ajoute la route POST pour accepter une invitation d'asset.
        Adds the POST route for accepting an asset invitation.
        """
        urls_par_defaut = super().get_urls()
        urls_custom = [
            re_path(
                r'^accept_asset_invitation/(?P<asset_pk>[^/]+)/$',
                self.admin_site.admin_view(
                    csrf_protect(require_POST(self.accept_asset_invitation))
                ),
                name='asset-accept-invitation',
            ),
        ]
        return urls_custom + urls_par_defaut

    # --- Actions POST / POST actions ---

    def accept_asset_invitation(self, request, asset_pk):
        """
        Accepte une invitation de partage d'asset pour le tenant courant.
        Accepts an asset sharing invitation for the current tenant.

        Deplace le tenant de pending_invitations vers federated_with.
        Moves tenant from pending_invitations to federated_with.
        """
        tenant_actuel = connection.tenant

        # Verifier les permissions admin.
        # Check admin permissions.
        tenant_admin_a_la_permission = TenantAdminPermissionWithRequest(request)
        if not tenant_admin_a_la_permission:
            messages.error(request, _("Permission refusee."))
            return redirect(self._url_changelist())

        asset = get_object_or_404(Asset, pk=asset_pk)

        # Verifier que ce tenant est bien dans les invitations en attente.
        # Check that this tenant is in pending invitations.
        invitation_existe = asset.pending_invitations.filter(pk=tenant_actuel.pk).exists()
        if not invitation_existe:
            messages.error(request, _("Aucune invitation en attente pour ce lieu."))
            return redirect(self._url_changelist())

        # Deplacer de pending_invitations vers federated_with.
        # Move from pending_invitations to federated_with.
        asset.pending_invitations.remove(tenant_actuel)
        asset.federated_with.add(tenant_actuel)

        logger.info(
            f"Asset '{asset.name}' : "
            f"tenant '{tenant_actuel.name}' a accepte l'invitation."
        )
        messages.success(
            request,
            _("Invitation acceptee ! Vous partagez maintenant l'asset « %(name)s ».") % {
                'name': asset.name,
            },
        )
        return redirect(self._url_changelist())

    # --- Vues / Views ---

    def changelist_view(self, request, extra_context=None):
        """
        Ajoute les invitations d'asset en attente au contexte de la liste.
        Adds pending asset invitations to the list context.
        """
        extra_context = extra_context or {}
        tenant_actuel = connection.tenant

        invitations_asset_en_attente = Asset.objects.filter(
            pending_invitations=tenant_actuel,
        ).select_related('tenant_origin')

        extra_context['invitations_asset_en_attente'] = invitations_asset_en_attente
        return super().changelist_view(request, extra_context=extra_context)

    # --- Helpers ---

    def _url_changelist(self):
        """
        Raccourci pour l'URL de la changelist Asset.
        Shortcut for Asset changelist URL.
        """
        return reverse(
            f'{self.admin_site.name}:'
            f'{self.model._meta.app_label}_{self.model._meta.model_name}_changelist'
        )


# ---------------------------------------------------------------------------
# Token : soldes des wallets (lecture seule)
# Token: wallet balances (read-only)
# ---------------------------------------------------------------------------

@admin.register(Token, site=staff_admin_site)
class TokenAdmin(ModelAdmin):
    """
    Admin pour les tokens (soldes des wallets).
    Admin for tokens (wallet balances).

    LECTURE SEULE : les soldes sont modifies uniquement
    par les services (WalletService.crediter / debiter).
    On ne cree et on ne modifie jamais un Token a la main.
    READ-ONLY: balances are modified only
    by services (WalletService.crediter / debiter).
    A Token is never created or modified manually.

    Filtre tenant : affiche les tokens lies aux assets de ce lieu.
    Tenant filter: shows tokens linked to this venue's assets.
    """
    list_display = [
        'wallet',
        'asset',
        'value',
    ]
    list_filter = ['asset']
    search_fields = ['wallet__name']

    def get_queryset(self, request):
        """
        Filtre les tokens par tenant courant (via l'asset).
        Filters tokens by current tenant (via the asset).

        Un lieu voit les soldes pour ses propres assets uniquement.
        A venue sees balances for its own assets only.
        """
        queryset = super().get_queryset(request)
        tenant_actuel = connection.tenant
        tokens_du_tenant = queryset.filter(
            asset__tenant_origin=tenant_actuel,
        ).select_related('wallet', 'asset')
        return tokens_du_tenant

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Transaction : historique des mouvements (lecture seule)
# Transaction: movement history (read-only)
# ---------------------------------------------------------------------------

@admin.register(Transaction, site=staff_admin_site)
class TransactionAdmin(ModelAdmin):
    """
    Admin pour les transactions (historique des mouvements financiers).
    Admin for transactions (financial movement history).

    LECTURE SEULE : une transaction est IMMUABLE.
    On ne cree, ne modifie, ne supprime jamais une transaction a la main.
    Pour annuler, on cree une nouvelle transaction REFUND ou VOID via les services.
    READ-ONLY: a transaction is IMMUTABLE.
    A transaction is never created, modified, or deleted manually.
    To cancel, create a new REFUND or VOID transaction via services.

    Filtre tenant : affiche les transactions de ce lieu uniquement.
    Tenant filter: shows this venue's transactions only.
    """
    list_display = [
        'id',
        'action',
        'asset',
        'amount',
        'sender',
        'receiver',
        'datetime',
    ]
    list_filter = ['action', 'asset']
    search_fields = ['id', 'comment']
    readonly_fields = [
        'id',
        'uuid',
        'hash',
        'migrated',
        'sender',
        'receiver',
        'asset',
        'amount',
        'action',
        'card',
        'primary_card',
        'datetime',
        'comment',
        'metadata',
        'subscription_type',
        'subscription_start_datetime',
        'checkout_stripe',
        'tenant',
        'ip',
    ]

    def get_queryset(self, request):
        """
        Filtre les transactions par tenant courant.
        Filters transactions by current tenant.

        Un lieu ne voit que ses propres transactions.
        A venue only sees its own transactions.
        """
        queryset = super().get_queryset(request)
        tenant_actuel = connection.tenant
        transactions_du_tenant = queryset.filter(
            tenant=tenant_actuel,
        ).select_related('sender', 'receiver', 'asset')
        return transactions_du_tenant

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Federation : partage d'assets entre lieux (editable)
# Federation: asset sharing across venues (editable)
#
# Flow d'invitation (inspire du pattern V1 AssetFedowPublic) :
# Invitation flow (inspired by V1 AssetFedowPublic pattern):
#   1. Le createur cree la federation, ajoute ses assets
#      Creator creates federation, adds their assets
#   2. Le createur invite des lieux via pending_tenants
#      Creator invites venues via pending_tenants
#   3. Le lieu invite voit l'invitation dans la changelist et accepte (POST)
#      Invited venue sees invitation in changelist and accepts (POST)
#   4. Le lieu est deplace de pending_tenants → tenants
#      Venue is moved from pending_tenants → tenants
# ---------------------------------------------------------------------------

@admin.register(Federation, site=staff_admin_site)
class FederationAdmin(ModelAdmin):
    """
    Admin pour les federations (groupement de lieux partageant des assets).
    Admin for federations (grouping of venues sharing assets).

    Permissions par role :
    - Le createur (created_by) peut modifier tous les champs et supprimer.
    - Les autres membres voient la federation en lecture seule.

    Permissions by role:
    - The creator (created_by) can edit all fields and delete.
    - Other members see the federation as read-only.

    Filtre tenant : affiche les federations dont ce lieu fait partie
    OU qu'il a creees.
    Tenant filter: shows federations this venue is a member of
    OR that it created.
    """
    list_display = [
        'name',
        'description',
        'nombre_de_membres',
    ]
    search_fields = ['name']

    # Autocomplete au lieu de filter_horizontal : plus simple pour l'utilisateur.
    # Autocomplete instead of filter_horizontal: simpler for the user.
    autocomplete_fields = ['pending_tenants']

    # tenants est exclu du formulaire : les membres s'ajoutent
    # uniquement via le flow d'invitation (accept) ou sont retires
    # par le createur (remove_member).
    # assets est exclu du formulaire : la gestion des assets se fait
    # per-asset via AssetAdmin (pending_invitations / federated_with).
    # tenants is excluded from form: members are added
    # only via invitation flow (accept) or removed
    # by the creator (remove_member).
    # assets is excluded from form: asset management is done
    # per-asset via AssetAdmin (pending_invitations / federated_with).
    exclude = ['tenants', 'assets']

    readonly_fields = ['uuid', 'created_by']

    # Template au-dessus de la liste : invitations en attente.
    # Template above the list: pending invitations.
    list_before_template = 'admin/federation/federation_list_before.html'

    # Template au-dessus du formulaire d'edition : liste des membres.
    # Template above the edit form: members list.
    change_form_before_template = 'admin/federation/federation_members.html'

    compressed_fields = True
    warn_unsaved_form = True

    def nombre_de_membres(self, obj):
        """
        Affiche le nombre de lieux membres dans la liste.
        Shows the member count in the list.
        """
        return obj.tenants.count()
    nombre_de_membres.short_description = _('Membres')

    # --- Permissions par role / Role-based permissions ---

    def has_change_permission(self, request, obj=None):
        """
        Seul le createur peut modifier la federation.
        Only the creator can edit the federation.

        Si obj est None (appel generique pour la liste),
        on renvoie True pour que tous les membres voient
        le lien "modifier" (qui mene a la vue lecture seule).
        If obj is None (generic call for the list),
        return True so all members see the "edit" link
        (which leads to the read-only view).
        """
        if obj is None:
            return True

        tenant_actuel = connection.tenant
        tenant_est_createur = (obj.created_by_id == tenant_actuel.pk)
        return tenant_est_createur

    def has_delete_permission(self, request, obj=None):
        """
        Seul le createur peut supprimer la federation.
        Only the creator can delete the federation.
        """
        if obj is None:
            return True

        tenant_actuel = connection.tenant
        tenant_est_createur = (obj.created_by_id == tenant_actuel.pk)
        return tenant_est_createur

    # --- Queryset filtre par tenant / Tenant-filtered queryset ---

    def get_queryset(self, request):
        """
        Filtre les federations par tenant courant.
        Filters federations by current tenant.

        Un lieu voit les federations dont il fait partie (tenants)
        OU qu'il a creees (created_by). Cela permet au createur
        de voir sa federation meme avant d'avoir des membres.
        A venue sees federations it's a member of (tenants)
        OR that it created (created_by). This lets the creator
        see their federation even before it has members.
        """
        queryset = super().get_queryset(request)
        tenant_actuel = connection.tenant
        federations_du_tenant = queryset.filter(
            Q(tenants=tenant_actuel) | Q(created_by=tenant_actuel)
        ).distinct()
        return federations_du_tenant

    # --- Sauvegarde / Save ---

    def save_model(self, request, obj, form, change):
        """
        A la creation : force created_by au tenant courant.
        On creation: sets created_by to current tenant.

        Note : l'ajout du createur comme membre se fait dans save_related(),
        car save_related() ecrase les M2M avec les valeurs du formulaire.
        Si on ajoutait ici, save_related() supprimerait l'ajout.
        Note: adding creator as member is done in save_related(),
        because save_related() overwrites M2M with form values.
        If we added here, save_related() would remove it.
        """
        federation_est_nouvelle = not change
        if federation_est_nouvelle:
            obj.created_by = connection.tenant

        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        """
        Apres sauvegarde des M2M : ajoute le createur comme premier membre.
        After M2M save: adds creator as first member.

        Plus besoin de proteger pending_tenants ici :
        has_change_permission() bloque l'edition pour les non-createurs,
        donc seul le createur peut soumettre le formulaire.
        No longer need to protect pending_tenants here:
        has_change_permission() blocks editing for non-creators,
        so only the creator can submit the form.
        """
        super().save_related(request, form, formsets, change)

        # A la creation, ajouter le createur comme premier membre.
        # On creation, add creator as first member.
        federation_est_nouvelle = not change
        if federation_est_nouvelle:
            obj = form.instance
            obj.tenants.add(connection.tenant)

    # --- URLs custom / Custom URLs ---

    def get_urls(self):
        """
        Ajoute les routes POST pour accepter une invitation
        et exclure un membre.
        Adds POST routes for accepting an invitation
        and removing a member.
        """
        urls_par_defaut = super().get_urls()
        urls_custom = [
            re_path(
                r'^accept_invitation/(?P<federation_pk>[^/]+)/$',
                self.admin_site.admin_view(
                    csrf_protect(require_POST(self.accept_invitation))
                ),
                name='federation-accept-invitation',
            ),
            re_path(
                r'^remove_member/(?P<federation_pk>[^/]+)/(?P<tenant_pk>[^/]+)/$',
                self.admin_site.admin_view(
                    csrf_protect(require_POST(self.remove_member))
                ),
                name='federation-remove-member',
            ),
        ]
        return urls_custom + urls_par_defaut

    # --- Actions POST / POST actions ---

    def accept_invitation(self, request, federation_pk):
        """
        Accepte une invitation de federation pour le tenant courant.
        Accepts a federation invitation for the current tenant.

        Deplace le tenant de pending_tenants vers tenants.
        Moves tenant from pending_tenants to tenants.
        """
        tenant_actuel = connection.tenant

        # Verifier les permissions admin.
        # Check admin permissions.
        tenant_admin_a_la_permission = TenantAdminPermissionWithRequest(request)
        if not tenant_admin_a_la_permission:
            messages.error(request, _("Permission refusee."))
            return redirect(self._url_changelist())

        federation = get_object_or_404(Federation, pk=federation_pk)

        # Verifier que ce tenant est bien dans les invitations en attente.
        # Check that this tenant is in pending invitations.
        invitation_existe = federation.pending_tenants.filter(pk=tenant_actuel.pk).exists()
        if not invitation_existe:
            messages.error(request, _("Aucune invitation en attente pour ce lieu."))
            return redirect(self._url_changelist())

        # Deplacer de pending_tenants vers tenants.
        # Move from pending_tenants to tenants.
        federation.pending_tenants.remove(tenant_actuel)
        federation.tenants.add(tenant_actuel)

        logger.info(
            f"Federation '{federation.name}' : "
            f"tenant '{tenant_actuel.name}' a accepte l'invitation."
        )
        messages.success(
            request,
            _("Invitation acceptee ! Vous faites maintenant partie de la federation « %(name)s ».") % {
                'name': federation.name,
            },
        )
        return redirect(self._url_changelist())

    def remove_member(self, request, federation_pk, tenant_pk):
        """
        Exclut un membre de la federation (action du createur uniquement).
        Removes a member from the federation (creator action only).

        Le createur ne peut pas s'exclure lui-meme.
        The creator cannot remove themselves.
        """
        tenant_actuel = connection.tenant

        # Verifier les permissions admin.
        # Check admin permissions.
        tenant_admin_a_la_permission = TenantAdminPermissionWithRequest(request)
        if not tenant_admin_a_la_permission:
            messages.error(request, _("Permission refusee."))
            return redirect(self._url_changelist())

        federation = get_object_or_404(Federation, pk=federation_pk)

        # Seul le createur peut exclure un membre.
        # Only the creator can remove a member.
        tenant_est_createur = (federation.created_by_id == tenant_actuel.pk)
        if not tenant_est_createur:
            messages.error(
                request,
                _("Seul le createur de la federation peut exclure un membre."),
            )
            return redirect(self._url_change(federation.pk))

        # Le createur ne peut pas s'exclure lui-meme.
        # The creator cannot remove themselves.
        if str(tenant_pk) == str(tenant_actuel.pk):
            messages.error(
                request,
                _("Vous ne pouvez pas vous exclure vous-meme de votre federation."),
            )
            return redirect(self._url_change(federation.pk))

        # Verifier que le tenant cible est bien membre.
        # Check that the target tenant is a member.
        membre_existe = federation.tenants.filter(pk=tenant_pk).exists()
        if not membre_existe:
            messages.error(request, _("Ce lieu n'est pas membre de cette federation."))
            return redirect(self._url_change(federation.pk))

        # Exclure le membre.
        # Remove the member.
        tenant_a_exclure = get_object_or_404(Client, pk=tenant_pk)
        federation.tenants.remove(tenant_a_exclure)

        logger.info(
            f"Federation '{federation.name}' : "
            f"tenant '{tenant_a_exclure.name}' a ete exclu par '{tenant_actuel.name}'."
        )
        messages.success(
            request,
            _("Le lieu « %(name)s » a ete exclu de la federation.") % {
                'name': tenant_a_exclure.name,
            },
        )
        return redirect(self._url_change(federation.pk))

    # --- Vues / Views ---

    def changelist_view(self, request, extra_context=None):
        """
        Ajoute les invitations en attente au contexte de la liste.
        Adds pending invitations to the list context.
        """
        extra_context = extra_context or {}
        tenant_actuel = connection.tenant

        invitations_en_attente = Federation.objects.filter(
            pending_tenants=tenant_actuel,
        ).select_related('created_by')

        extra_context['invitations_en_attente'] = invitations_en_attente
        return super().changelist_view(request, extra_context=extra_context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        """
        Ajoute la liste des membres et le role du tenant au contexte.
        Adds the members list and the tenant's role to the context.

        Le template federation_members.html utilise ces donnees
        pour afficher les membres et les boutons "Exclure" (createur only).
        The federation_members.html template uses this data
        to display members and "Remove" buttons (creator only).
        """
        extra_context = extra_context or {}

        try:
            federation = Federation.objects.get(pk=object_id)
            tenant_actuel = connection.tenant

            # Liste des membres pour le template.
            # Members list for the template.
            membres_de_la_federation = federation.tenants.all()
            extra_context['membres_de_la_federation'] = membres_de_la_federation
            extra_context['federation'] = federation

            # Le createur voit les boutons "Exclure".
            # The creator sees the "Remove" buttons.
            tenant_est_createur = (federation.created_by_id == tenant_actuel.pk)
            extra_context['tenant_est_createur'] = tenant_est_createur
        except Federation.DoesNotExist:
            pass

        return super().change_view(request, object_id, form_url, extra_context)

    # --- Helpers ---

    def _url_changelist(self):
        """
        Raccourci pour l'URL de la changelist Federation.
        Shortcut for Federation changelist URL.
        """
        return reverse(
            f'{self.admin_site.name}:'
            f'{self.model._meta.app_label}_{self.model._meta.model_name}_changelist'
        )

    def _url_change(self, pk):
        """
        Raccourci pour l'URL de modification d'une federation.
        Shortcut for a federation change URL.
        """
        return reverse(
            f'{self.admin_site.name}:'
            f'{self.model._meta.app_label}_{self.model._meta.model_name}_change',
            args=[pk],
        )
