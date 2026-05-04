# Phase 2 — Suivi de la dette pot central → tenant pour les FED remboursés

**Date** : 2026-04-13
**Statut** : design validé en brainstorming, à revoir par le mainteneur avant plan d'implémentation
**Branche cible** : V2
**Spec source précédente** : Phase 1 (`2026-04-13-phase1-admin-cartes-design.md`)

## Contexte

Quand le pot central Stripe (TiBillet) rembourse à un tenant les FED qu'il a rendus
en espèces à des utilisateur·ices (mécanisme Phase 1, `WalletService.rembourser_en_especes()`),
il accumule une **dette** envers ce tenant. Cette dette est soldée mensuellement par un
**virement bancaire externe** depuis le compte du pot central vers le compte bancaire du tenant.

Phase 2 instrumente la traçabilité de cette dette :
- Calcul de la dette en temps réel par requête sur `Transaction`.
- Saisie superuser du virement bancaire reçu (action `Transaction.BANK_TRANSFER`).
- Affichage côté superuser (dashboard global tous tenants) et côté tenant (widget sur dashboard).
- Sortie comptable via `LigneArticle` pour intégration aux rapports caisse/admin.

## Scope de la Phase 2

**In :**
- Nouveau code `Transaction.BANK_TRANSFER = 'BTR'` (action immutable, pas de mutation Token).
- Service `BankTransferService` : `calculer_dette`, `obtenir_dettes_par_tenant_et_asset`,
  `obtenir_dette_pour_tenant`, `enregistrer_virement`.
- Validation hard : `montant <= dette_actuelle`, sinon rejet.
- Page dédiée superuser `/admin/bank-transfers/` (tableau dettes + saisie virement).
- Page historique global `/admin/bank-transfers/historique/` (toutes les BANK_TRANSFER).
- Page historique tenant `/admin/bank-transfers/historique-tenant/` (BANK_TRANSFER reçues par le tenant courant).
- Widget sur le dashboard tenant : « le pot central vous doit X € — dernier virement Y € le Z ».
- Sidebar item « Virements pot central » dans la section « Root Configuration » (`root_permission`).
- Nouveau code `Product.VIREMENT_RECU = "VR"` et helper `get_or_create_product_virement_recu()`.
- LigneArticle d'encaissement (positif, `payment_method=TRANSFER`, `sale_origin=ADMIN`)
  pour chaque BANK_TRANSFER, intégrée aux rapports comptables.

**Out :**
- Sens inverse tenant → pot central (YAGNI — décision brainstorming).
- Mécanisme de cancellation/édition d'une BANK_TRANSFER (immutable strict ; sous-versement noté
  en commentaire et compensé au virement suivant).
- Justificatif fichier (URL/PDF) — peut s'ajouter via `metadata` plus tard si besoin.
- Export CSV/PDF de l'historique (Phase 4 si besoin).
- Bouton POS Cashless (Phase 3 séparée).

## Architecture

Découpage en modules à responsabilités isolées. **Aucune logique métier dans `Administration/admin/`**
au-delà du strict minimum admin-side (sidebar item, dashboard_callback minimal). Toute la logique
vit dans `fedow_core/services.py` et `Administration/views_bank_transfers.py`.

| Module | Action | Responsabilité |
|---|---|---|
| `fedow_core/exceptions.py` | PATCH | +`MontantSuperieurDette` |
| `fedow_core/models.py` | PATCH | +`Transaction.BANK_TRANSFER = 'BTR'` dans `ACTION_CHOICES` |
| `fedow_core/services.py` | PATCH | +`actions_sans_credit = [BANK_TRANSFER]` étendre `actions_sans_debit`. Nouvelle classe `BankTransferService` (4 méthodes statiques). |
| `BaseBillet/models.py` | PATCH | +`Product.VIREMENT_RECU = "VR"` dans `METHODE_CAISSE_CHOICES` |
| `BaseBillet/services_refund.py` | PATCH | +`get_or_create_product_virement_recu()` (à côté de l'existant `get_or_create_product_remboursement()`) |
| `Administration/serializers.py` | PATCH | +`BankTransferCreateSerializer` |
| `Administration/views_bank_transfers.py` | NEW | `BankTransfersViewSet(viewsets.ViewSet)` patterns FALC `/djc` |
| `Administration/admin/site.py` | PATCH | Override `StaffAdminSite.get_urls()` pour monter 3 URLs custom |
| `Administration/admin/dashboard.py` | PATCH | +sidebar item « Virements pot central » dans Root Configuration ; +`dashboard_callback` enrichi (1 ligne d'appel au service) |
| `Administration/templates/admin/bank_transfers/dashboard.html` | NEW | Page superuser, style inspiré `templates/admin/event/bilan.html` |
| `Administration/templates/admin/bank_transfers/create_form.html` | NEW | Formulaire HTMX (modal ou page dédiée) |
| `Administration/templates/admin/bank_transfers/historique.html` | NEW | Liste BANK_TRANSFER (global + filtré tenant) |
| `Administration/templates/admin/partials/widget_dette_pot_central.html` | NEW | Widget tenant à inclure dans `dashboard.html` |
| `Administration/templates/admin/dashboard.html` | PATCH | `{% include "admin/partials/widget_dette_pot_central.html" %}` |
| 2 migrations Django (alter choices) | NEW | `BaseBillet` (Product.methode_caisse) + `fedow_core` (Transaction.action) |

## Composants

### `BankTransferService` — cœur métier

```python
class BankTransferService:
    """
    Service de gestion des virements bancaires pot central -> tenant.
    Tracks the central pot's debt to tenants for refunded FED tokens.

    La dette = somme(REFUND FED vers tenant) - somme(BANK_TRANSFER FED vers tenant).
    Aucune mutation Token (les BANK_TRANSFER sont des evenements bancaires externes,
    enregistres pour audit + reporting comptable).
    """

    @staticmethod
    def calculer_dette(tenant: Client, asset: Asset) -> int:
        """Retourne la dette actuelle en centimes (>= 0)."""

    @staticmethod
    def obtenir_dettes_par_tenant_et_asset() -> list[dict]:
        """
        Pour le dashboard superuser : toutes les dettes en cours (et historiques).
        Inclut les couples (tenant, asset) avec dette > 0 OU au moins 1 REFUND historique.
        Trie par dette decroissante.
        Chaque dict : {tenant, asset, dette_centimes, total_refund_centimes,
                       total_virements_centimes, dernier_virement: Transaction|None}.
        """

    @staticmethod
    def obtenir_dette_pour_tenant(tenant: Client) -> list[dict]:
        """Pour le widget tenant : meme structure mais filtree au tenant courant."""

    @staticmethod
    def enregistrer_virement(
        tenant: Client,
        asset: Asset,
        montant_en_centimes: int,
        date_virement: date,
        reference_bancaire: str,
        comment: str = "",
        ip: str = "0.0.0.0",
        admin_email: str = "",
    ) -> Transaction:
        """
        Enregistre un virement bancaire recu par le tenant.
        Cree atomiquement :
          - 1 Transaction(action=BANK_TRANSFER, sender=asset.wallet_origin,
                          receiver=tenant.wallet_lieu, asset=asset, amount=...).
            Aucune mutation Token (cf. actions_sans_credit/sans_debit).
          - 1 LigneArticle(payment_method=TRANSFER, +amount, sale_origin=ADMIN,
                           pricesold=pricesold_virement_recu, asset=asset.uuid,
                           wallet=receiver_wallet).

        Validation :
          - Re-check `montant <= calculer_dette(tenant, asset)` dans l'atomic.
          - Sinon : raise MontantSuperieurDette.

        :return: Transaction creee
        :raises MontantSuperieurDette
        """
```

### Patch `TransactionService.creer()`

Étendre les listes d'exclusion existantes :

```python
actions_sans_debit = [
    Transaction.FIRST,
    Transaction.CREATION,
    Transaction.REFILL,
    Transaction.BANK_TRANSFER,  # NEW : virement bancaire externe, pas de mutation Token
]

actions_sans_credit = [Transaction.BANK_TRANSFER]  # NEW liste

if action not in actions_sans_debit:
    WalletService.debiter(...)

if receiver is not None and action not in actions_sans_credit:
    WalletService.crediter(...)
```

Le sender (`asset.wallet_origin`) et le receiver (`tenant.wallet`) sont enregistrés sur la Transaction
mais leurs Token respectifs ne bougent pas.

### `BankTransferCreateSerializer`

```python
class BankTransferCreateSerializer(serializers.Serializer):
    tenant_uuid     = serializers.UUIDField()
    asset_uuid      = serializers.UUIDField()
    montant_euros   = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    date_virement   = serializers.DateField()
    reference       = serializers.CharField(max_length=100)
    comment         = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_tenant_uuid(self, value):
        try: return Client.objects.get(uuid=value)
        except Client.DoesNotExist: raise serializers.ValidationError(_("Tenant introuvable."))

    def validate_asset_uuid(self, value):
        try: return Asset.objects.get(uuid=value, category=Asset.FED)
        except Asset.DoesNotExist: raise serializers.ValidationError(_("Asset FED introuvable."))

    def validate(self, attrs):
        attrs["montant_centimes"] = int(round(attrs["montant_euros"] * 100))
        dette = BankTransferService.calculer_dette(
            tenant=attrs["tenant_uuid"], asset=attrs["asset_uuid"],
        )
        if attrs["montant_centimes"] > dette:
            raise serializers.ValidationError(
                _("Montant superieur a la dette actuelle (%(dette)s EUR).") % {
                    "dette": dette / 100,
                }
            )
        return attrs
```

### `BankTransfersViewSet(viewsets.ViewSet)`

Patterns FALC `/djc` : pas de `ModelViewSet`, méthodes explicites, helpers au niveau module.

```python
class BankTransfersViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        """GET /admin/bank-transfers/ : dashboard superuser (table de toutes les dettes)."""
        _check_superuser(request)
        dettes = BankTransferService.obtenir_dettes_par_tenant_et_asset()
        return render(request, "admin/bank_transfers/dashboard.html", {
            "dettes": dettes,
            "total_global_centimes": sum(d["dette_centimes"] for d in dettes),
        })

    def create(self, request):
        """POST /admin/bank-transfers/ : enregistre un virement."""
        _check_superuser(request)
        serializer = BankTransferCreateSerializer(data=request.POST)
        serializer.is_valid(raise_exception=True)
        try:
            tx = BankTransferService.enregistrer_virement(
                tenant=serializer.validated_data["tenant_uuid"],
                asset=serializer.validated_data["asset_uuid"],
                montant_en_centimes=serializer.validated_data["montant_centimes"],
                date_virement=serializer.validated_data["date_virement"],
                reference_bancaire=serializer.validated_data["reference"],
                comment=serializer.validated_data.get("comment", ""),
                ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
                admin_email=request.user.email,
            )
        except MontantSuperieurDette:
            messages.error(request, _("Sur-versement detecte. Verifier la dette actuelle."))
            return redirect(reverse("staff_admin:bank_transfers_dashboard"))
        messages.success(
            request,
            _("Virement enregistre : %(amount)s EUR vers %(tenant)s.") % {
                "amount": tx.amount / 100, "tenant": tx.tenant.name,
            },
        )
        return redirect(reverse("staff_admin:bank_transfers_dashboard"))

    @action(detail=False, methods=["GET"], url_path="historique")
    def historique(self, request):
        """GET /admin/bank-transfers/historique/ : liste globale (superuser)."""
        _check_superuser(request)
        transactions = Transaction.objects.filter(
            action=Transaction.BANK_TRANSFER,
        ).select_related("receiver", "asset", "tenant").order_by("-datetime")
        return render(request, "admin/bank_transfers/historique.html", {
            "transactions": transactions,
            "scope": "global",
        })

    @action(detail=False, methods=["GET"], url_path="historique-tenant")
    def historique_tenant(self, request):
        """GET /admin/bank-transfers/historique-tenant/ : liste filtree au tenant courant (lecture seule)."""
        if not TenantAdminPermissionWithRequest(request):
            raise PermissionDenied()
        transactions = Transaction.objects.filter(
            action=Transaction.BANK_TRANSFER,
            tenant=connection.tenant,
        ).select_related("asset").order_by("-datetime")
        return render(request, "admin/bank_transfers/historique.html", {
            "transactions": transactions,
            "scope": "tenant",
        })
```

### Helpers privés (module-level dans `views_bank_transfers.py`)

```python
def _check_superuser(request):
    if not request.user.is_superuser:
        raise PermissionDenied(_("Superuser uniquement."))
```

### URLs custom — override `StaffAdminSite.get_urls()`

Dans `Administration/admin/site.py`, ajouter à `StaffAdminSite` :

```python
class StaffAdminSite(UnfoldAdminSite):
    # ... methodes existantes ...

    def get_urls(self):
        from django.urls import path
        from Administration import views_bank_transfers
        custom = [
            path(
                "bank-transfers/",
                self.admin_view(views_bank_transfers.BankTransfersViewSet.as_view({
                    "get": "list", "post": "create",
                })),
                name="bank_transfers_dashboard",
            ),
            path(
                "bank-transfers/historique/",
                self.admin_view(views_bank_transfers.BankTransfersViewSet.as_view({
                    "get": "historique",
                })),
                name="bank_transfers_historique",
            ),
            path(
                "bank-transfers/historique-tenant/",
                self.admin_view(views_bank_transfers.BankTransfersViewSet.as_view({
                    "get": "historique_tenant",
                })),
                name="bank_transfers_historique_tenant",
            ),
        ]
        return custom + super().get_urls()
```

### Sidebar — section « Root Configuration »

Dans `Administration/admin/dashboard.py:600-623`, ajouter un 3e item :

```python
{
    "title": _("Virements pot central"),
    "icon": "account_balance",
    "link": reverse_lazy("staff_admin:bank_transfers_dashboard"),
    "permission": root_permission,
},
```

### Widget tenant — enrichir `dashboard_callback`

```python
def dashboard_callback(request, context):
    config = Configuration.get_solo()
    if config.module_monnaie_locale:
        from fedow_core.services import BankTransferService
        context["dettes_pot_central"] = BankTransferService.obtenir_dette_pour_tenant(
            connection.tenant
        )
    # ... reste du callback existant ...
    return context
```

Le template `dashboard.html` (déjà existant) inclut au bon endroit :

```html
{% include "admin/partials/widget_dette_pot_central.html" %}
```

Le partial `widget_dette_pot_central.html` boucle sur `dettes_pot_central` et affiche le solde +
dernière transaction de virement reçue + lien vers `/admin/bank-transfers/historique-tenant/`.
Si la liste est vide ou les dettes sont à 0, le widget retourne un bloc vide invisible.

### Helper Product système

Ajout dans `BaseBillet/services_refund.py` (à côté de l'existant `get_or_create_product_remboursement`) :

```python
def get_or_create_product_virement_recu() -> Product:
    """
    Retourne le Product systeme "Virement pot central" partage.
    Returns the system Product "Central pot transfer".

    Cree le Product la premiere fois, le reutilise ensuite.
    Identifie par methode_caisse=VIREMENT_RECU (un seul par tenant).
    """
    product, _created = Product.objects.get_or_create(
        methode_caisse=Product.VIREMENT_RECU,
        defaults={
            "name": str(_("Virement pot central")),
            "publish": False,
        },
    )
    return product
```

Le helper existant `get_or_create_pricesold_refund(product)` reste réutilisable tel quel
(le nom devient générique : « PriceSold systeme à 0 attaché à un Product systeme »).

## Data flow

### Flow nominal — Saisie d'un virement reçu

```
[1] Superuser ouvre la sidebar "Root Configuration" -> clique "Virements pot central"
    -> GET /admin/bank-transfers/

[2] BankTransfersViewSet.list() :
    a. _check_superuser
    b. dettes = BankTransferService.obtenir_dettes_par_tenant_et_asset()
       Requete optimisee :
         - 1 Sum sur Transaction filtre action=REFUND, asset.category=FED, group by (tenant, asset)
         - 1 Sum sur Transaction filtre action=BANK_TRANSFER, asset.category=FED, group by (tenant, asset)
         - Merge en python pour calculer dette = refund - virement par couple
         - 1 query supplementaire pour dernier_virement (max(datetime) par couple)
    c. Render dashboard.html avec : tableau (tenant, asset, dette, dernier_virement, bouton),
       total global, lien Historique global.

[3] Superuser clique "Enregistrer un virement" sur la ligne tenant X / FED
    -> Modal HTMX (hx-get) ouvre create_form.html prefilled tenant_uuid + asset_uuid
       (champs caches, juste un titre "Virement vers Tenant X (FED)")
    -> Le superuser remplit montant_euros, date_virement, reference, comment
    -> Soumet (hx-post)

[4] BankTransfersViewSet.create() :
    a. _check_superuser
    b. BankTransferCreateSerializer.is_valid(raise_exception=True)
       Validation cross-fields : montant_centimes <= calculer_dette(tenant, asset).
       Si NOK : 422 avec erreur dans la modal.
    c. BankTransferService.enregistrer_virement(...) :
       with transaction.atomic():
         dette = calculer_dette(tenant, asset)        # re-check race
         if montant > dette: raise MontantSuperieurDette
         receiver_wallet = _get_or_create_wallet_lieu(tenant)
         tx = TransactionService.creer(
             sender=asset.wallet_origin,
             receiver=receiver_wallet,
             asset=asset,
             montant_en_centimes=montant,
             action=Transaction.BANK_TRANSFER,
             tenant=tenant,
             ip=ip,
             comment=comment,
             metadata={
                 "reference_bancaire": reference,
                 "date_virement": date_virement.isoformat(),
                 "saisi_par": admin_email,
             },
         )
         product = get_or_create_product_virement_recu()
         pricesold = get_or_create_pricesold_refund(product)
         LigneArticle.objects.create(
             pricesold=pricesold,
             qty=1, amount=montant,
             payment_method=PaymentMethod.TRANSFER,
             status=LigneArticle.VALID,
             sale_origin=SaleOrigin.ADMIN,
             asset=asset.uuid,
             wallet=receiver_wallet,
             carte=None,
             metadata={
                 "reference_bancaire": reference,
                 "date_virement": date_virement.isoformat(),
                 "transaction_uuid": str(tx.uuid),
             },
         )
       return tx
    d. messages.success("Virement enregistre : 200€ vers Tenant X.")
    e. Redirect vers /admin/bank-transfers/ (dette mise a jour).
```

### Flow widget tenant

```
[1] Tenant admin va sur /admin/ (dashboard d'accueil).

[2] dashboard_callback(request, context) :
    a. config = Configuration.get_solo()
    b. if config.module_monnaie_locale:
         context["dettes_pot_central"] = BankTransferService.obtenir_dette_pour_tenant(
             connection.tenant
         )

[3] Template dashboard.html inclut partials/widget_dette_pot_central.html :
    - Pour chaque entree : solde + derniere date virement + lien historique tenant.
    - Si dettes_pot_central absent (module inactif) ou liste vide : widget ne rend rien.

[4] Tenant admin clique "Voir l'historique"
    -> GET /admin/bank-transfers/historique-tenant/
    -> BankTransfersViewSet.historique_tenant() :
       a. TenantAdminPermissionWithRequest check
       b. Liste BANK_TRANSFER WHERE tenant=connection.tenant ORDER BY datetime DESC
       c. Render historique.html (lecture seule, pas de bouton create).
```

## Error handling

| Cas | Détection | Réaction |
|---|---|---|
| Non-superuser tente d'accéder à `/admin/bank-transfers/` | `_check_superuser` | `PermissionDenied` 403, log warning. |
| Tenant introuvable / asset introuvable / asset pas FED | `validate_tenant_uuid` / `validate_asset_uuid` du serializer | 422 dans la modal avec message champ-précis. |
| Montant ≤ 0 | `montant_euros = DecimalField(min_value=0.01)` | 422 dans la modal. |
| Montant > dette | `validate()` cross-fields du serializer + re-check atomic | 422 dans la modal « Montant supérieur à la dette actuelle (X €). » |
| Race condition (entre validation serializer et atomic) | Re-check dans `enregistrer_virement()` sous `transaction.atomic()` | Si race : `MontantSuperieurDette` levée, message error, redirect dashboard. Cas ultra-rare (1 superuser actif). |
| `module_monnaie_locale=False` côté tenant | `dashboard_callback` ne renseigne pas le contexte | Widget invisible. Cohérent avec autres modules. Sidebar item « Virements pot central » reste visible côté superuser indépendamment. |
| Aucun asset FED dans le système | `obtenir_dettes_par_tenant_et_asset()` retourne `[]` | Dashboard affiche « Aucune dette en cours. » |
| `tenant.wallet` (helper `_get_or_create_wallet_lieu`) absent | Le helper crée à la demande (Phase 1) | Pas d'erreur. |

## Testing

### Tests pytest DB-only (`tests/pytest/test_bank_transfer_service.py`)

```
test_calculer_dette_zero_si_aucune_transaction
test_calculer_dette_apres_un_refund                 → dette = montant_refund
test_calculer_dette_apres_refund_et_virement        → dette = refund - virement
test_calculer_dette_isole_par_tenant                → 2 tenants indépendants
test_calculer_dette_isole_par_asset                 → 2 assets FED hypothétiques
test_obtenir_dettes_par_tenant_et_asset             → tri décroissant + dernier_virement
test_obtenir_dette_pour_tenant_courant              → filtré sur 1 tenant
test_enregistrer_virement_cree_transaction_et_lignearticle
test_enregistrer_virement_no_token_mutation         → solde Token tenant inchangé
test_enregistrer_virement_rejette_si_montant_superieur_dette
test_enregistrer_virement_atomic_rollback_on_failure
test_get_or_create_product_virement_recu_creates_once
test_metadata_porte_reference_bancaire_et_date_virement
```

### Tests admin (`tests/pytest/test_admin_bank_transfers.py`)

```
test_dashboard_403_pour_non_superuser
test_dashboard_200_pour_superuser_affiche_table
test_create_403_pour_non_superuser
test_create_serializer_rejette_montant_superieur_dette
test_historique_global_affiche_toutes_bank_transfers
test_historique_tenant_filtre_au_tenant_courant
test_historique_tenant_lecture_seule_pour_admin_tenant
test_widget_tenant_dashboard_si_module_monnaie_locale_actif
test_widget_tenant_dashboard_invisible_si_module_inactif
test_widget_tenant_dashboard_invisible_si_aucune_dette
```

### Test E2E Playwright (`tests/e2e/test_admin_bank_transfer_flow.py`)

```
test_e2e_superuser_enregistre_virement :
  Setup (django_shell) :
    - Carte avec FED 500c, refund admin → dette = 500c
  Flow :
    1. login_as_superuser
    2. goto /admin/bank-transfers/
    3. assert tenant lespass + asset FED + dette 5,00€ visibles
    4. click "Enregistrer un virement"
    5. fill montant=3, date=today, reference="VIR-TEST-001", comment=""
    6. submit
    7. assert success message OR redirect dashboard
    8. assert nouvelle dette = 2,00€
    9. verif DB : 1 Transaction BANK_TRANSFER + 1 LigneArticle TRANSFER (200c)

test_e2e_widget_dashboard_tenant :
  Setup : dette de 200c après flow précédent
  Flow :
    1. login_as_admin (admin tenant)
    2. goto /admin/
    3. assert widget "Dette pot central" visible avec 2,00€
    4. assert "Dernier virement reçu : 3,00€ le ..." visible
    5. click "Voir l'historique"
    6. assert table avec 1 ligne BANK_TRANSFER de 3€

test_e2e_validation_sur_versement :
  Setup : dette = 100c
  Flow :
    1. login_as_superuser
    2. open create modal pour le tenant
    3. fill montant=5 (= 500c, > dette)
    4. submit
    5. assert message erreur "Montant superieur a la dette actuelle (1,00€)."
    6. assert AUCUNE nouvelle Transaction BANK_TRANSFER en DB
```

### Pièges anticipés (extraits de `tests/PIEGES.md`)

- **`tenant_context` requis** pour toute création de Transaction (touche `connection.tenant`).
- **Cleanup fixture** rigoureux : Transactions, LigneArticles, Wallets, Assets de test à supprimer
  pour éviter la pollution cross-file (cf. expérience Phase 1).
- **`schema_context('lespass')`** pour les ORM sur SHARED_APPS.
- **`StaffAdminSite.get_urls()` override** doit retourner `custom + super().get_urls()` pour
  préserver les routes admin Unfold standard.
- **`dashboard_callback`** est appelé à chaque chargement de `/admin/` — pas de calculs lourds,
  utiliser des agrégations efficaces dans `BankTransferService` (Sum + Max).
- **`Product.publish=False`** sur le Product système pour ne pas l'exposer en billetterie publique.
- **`PaymentMethod.TRANSFER = "TR"`** existe déjà — ne pas créer de doublon.
- **`Transaction.tenant`** champ existant indexé — utiliser pour filtrer par tenant côté historique tenant.

## Compatibilité V1/V2

- V1 (anciens tenants avec `Configuration.server_cashless` renseigné) : `module_monnaie_locale=False`
  → widget invisible côté tenant, et superuser n'a aucune dette à enregistrer pour eux (les FED legacy
  sont gérés sur le serveur Fedow distant, pas dans `fedow_core`).
- V2 (nouveaux tenants) : flow complet fonctionnel.

## Migration

- Migration `BaseBillet` : alter `Product.methode_caisse` choices (ajout `VR=Virement recu`).
- Migration `fedow_core` : alter `Transaction.action` choices (ajout `BTR=Bank transfer`).
- Pas de data migration : Product « Virement pot central » créé à la demande par le helper.

## i18n

Toutes les chaînes user-facing utilisent `_()`. Lancer après implémentation :
```
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
docker exec lespass_django poetry run django-admin compilemessages
```

## Décisions transversales (rappel du brainstorming)

- Action `Transaction.BANK_TRANSFER = 'BTR'` (option C — réutilisation de la table Transaction).
- Saisie superuser uniquement (option A).
- Sens unique pot central → tenant (option A).
- Affichage double : superuser + tenant (option C).
- Granularité tenant : solde + dernier virement reçu (option B).
- Granularité agrégation : par tenant × asset (option B — future-proof).
- Champs minimum : tenant, asset, montant, date, référence, commentaire (option B).
- Mécanique : sender=`asset.wallet_origin`, receiver=`tenant.wallet`, no token mutation
  (réutilisation du modèle Transaction avec extension `actions_sans_credit`).
- Validation : `montant <= dette_actuelle` (rejet hard, pas de cancellation).
- Localisation : page dédiée `/admin/bank-transfers/` dans la section « Root Configuration ».
- Style inspiré de `vue_bilan` / `templates/admin/event/bilan.html`.
- LigneArticle d'encaissement positif (`payment_method=TRANSFER`, `sale_origin=ADMIN`)
  pour intégration aux rapports comptables.
- Code Product `VIREMENT_RECU = "VR"` (option A — sémantique propre).

## Roadmap suivante

- **Phase 3** : bouton POS Cashless « Vider Carte / Void Carte » utilisant le service
  `WalletService.rembourser_en_especes()` de Phase 1 + le nouveau `BankTransferService` n'est PAS
  appelé côté POS (le POS ne gère que les remboursements aux utilisateurs, pas les virements bancaires).

## Notes pour l'implémenteur

- `Transaction.datetime` du BANK_TRANSFER : utiliser `now()` (date système de saisie) ou
  `date_virement` (date bancaire réelle) ? Recommandation : utiliser `now()` pour `datetime`
  (date de saisie en BDD) et conserver `date_virement` dans `metadata` (date bancaire). Le tri
  par date dans le dashboard utilise `datetime` (cohérent avec le reste de la table).
  À reconfirmer en début de plan.
- Le helper `_check_superuser(request)` peut vivre dans `Administration/views_bank_transfers.py`
  (module-level) ou dans un fichier utils partagé si on en a besoin ailleurs. Module-level
  suffit pour Phase 2.
- Le `dashboard_callback` existant a peut-être déjà beaucoup de logique — ajouter notre 1 ligne
  doit être fait sans casser l'existant. Tests d'intégration sur le dashboard à prévoir si besoin.
