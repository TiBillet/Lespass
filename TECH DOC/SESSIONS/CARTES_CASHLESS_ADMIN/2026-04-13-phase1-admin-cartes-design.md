# Phase 1 — Admin web cartes NFC + remboursement en espèces

**Date** : 2026-04-13
**Statut** : design validé en brainstorming, à revoir par le mainteneur avant plan d'implémentation
**Branche cible** : V2

## Contexte

Aujourd'hui aucune interface admin pour `QrcodeCashless.CarteCashless` ni `Detail` (lots de cartes).
`Administration/admin_root.py` contient un brouillon entièrement commenté de `CarteCashlessAdmin` (lignes 184-203).
Le besoin terrain : superuser doit pouvoir consulter toutes les cartes du système ; admin tenant doit pouvoir
consulter ses propres cartes (filtrées par `Detail.origine`) et déclencher des actions limitées.

Le mécanisme de remboursement reproduit le legacy `OLD_REPOS/Fedow` + `OLD_REPOS/LaBoutik` :
1 lieu rembourse en espèces ses propres tokens locaux (TLF où `asset.tenant_origin == tenant`)
plus la part fédérée Stripe (FED). Ces opérations sont tracées dans `LigneArticle` pour apparaître
dans les rapports comptables. Le pot central reverse les FED remboursés en virement bancaire mensuel
au lieu — le suivi de cette dette est repoussé en Phase 2.

## Scope de la Phase 1

**In :**
- Admin Unfold pour `CarteCashless` (consultation + actions limitées).
- Admin Unfold pour `Detail` (consultation + édition pour le tenant propriétaire).
- Page dédiée `/admin/cards/<uuid>/refund/` (ViewSet FALC) pour le remboursement.
- Service `WalletService.rembourser_en_especes()` réutilisable (Phase 3 POS).
- Helper `get_or_create_product_remboursement()` qui crée le Product système partagé.
- Nouveau code `Product.MethodeCaisse.VC = "VC"` (Vider Carte / Refund).
- Section sidebar « Cartes NFC » et « Lots de cartes » sous Fedow, conditionnée à `module_monnaie_locale`.
- Nettoyage `Administration/admin_root.py` (commenter le reliquat actif).
- README `fedow_core/REFUND.md` documente la mécanique de bout en bout.

**Out :**
- `Transaction.BANK_TRANSFER` + suivi de la dette pot central → Phase 2.
- Bouton POS Cashless « Rembourser carte / Vider carte » → Phase 3.
- Vue admin séparée pour les CartePrimaire (déjà éditables via l'admin laboutik existant).
- Refund vers CB d'origine via Stripe (`refund_fed_by_signature` legacy) — autre cas d'usage,
  hors scope de la fusion mono-repo pour l'instant.

## Architecture

Découpage en modules à responsabilités isolées :

| Module | Responsabilité |
|---|---|
| `fedow_core/services.py` (PATCH) | Logique métier : `WalletService.rembourser_en_especes(carte, tenant, ip, vider_carte)` atomic. Réutilisable Phase 3. |
| `fedow_core/exceptions.py` (PATCH) | Nouvelle exception `NoEligibleTokens`. |
| `fedow_core/REFUND.md` (NEW) | Doc mécanisme TLF + FED + dette pot central (roadmap). |
| `BaseBillet/models.py` (PATCH) | Ajout `Product.MethodeCaisse.VC = "VC"` (Vider Carte). |
| `BaseBillet/services_refund.py` (NEW) | Helper `get_or_create_product_remboursement()` qui retourne le Product système partagé. Réutilisable Phase 3. |
| `Administration/admin/cards.py` (NEW) | `CarteCashlessAdmin` + `DetailAdmin` enregistrés sur `staff_admin_site`. |
| `Administration/admin/dashboard.py` (PATCH) | +2 items dans la section Fedow conditionnée à `module_monnaie_locale`. |
| `Administration/views_cards.py` (NEW) | `CardRefundViewSet(viewsets.ViewSet)` patterns FALC `/djc`. |
| `Administration/serializers.py` (PATCH ou NEW) | `CardRefundConfirmSerializer` (champ `vider_carte: bool`). |
| `Administration/urls.py` (PATCH) | Routes `path('cards/<uuid>/refund/', ...)`. |
| `Administration/templates/admin/cards/refund.html` (NEW) | Page Unfold étendue, formulaire HTMX. |
| `Administration/admin_root.py` (PATCH) | Commenter les 3 lignes actives + bandeau d'en-tête. |

**Principe d'isolation :** la logique métier vit dans `fedow_core/services.py` et `BaseBillet/services_refund.py`.
L'admin et le futur POS l'appellent. Le ViewSet ne contient que la collecte des inputs, les permissions
et le rendu HTML/HTMX.

## Composants

### `WalletService.rembourser_en_especes()` — cœur métier

Signature :
```python
@staticmethod
def rembourser_en_especes(
    carte: CarteCashless,
    tenant: Client,
    ip: str = "0.0.0.0",
    vider_carte: bool = False,
) -> dict:
    """
    Rembourse en espèces les tokens éligibles d'une carte.

    Tokens éligibles :
    - TLF avec asset.tenant_origin == tenant
    - FED (toutes valeurs, sans filtre origine — il n'y a qu'un seul Asset FED dans le système)

    Crée :
    - 1 Transaction(action=REFUND, sender=wallet_carte, receiver=tenant.wallet) par asset
    - 1 LigneArticle FED (encaissement positif STRIPE_FED) si solde FED > 0
    - 1 LigneArticle CASH négative (sortie cash totale TLF + FED)
    - Si vider_carte=True : carte.user=None, carte.wallet_ephemere=None,
      CartePrimaire.objects.filter(carte=carte).delete()
    Tout dans un seul transaction.atomic().

    :return: {"transactions": [...], "lignes_articles": [...],
              "total_centimes": int, "total_tlf_centimes": int, "total_fed_centimes": int}
    :raises NoEligibleTokens: si aucun token éligible n'a value > 0
    :raises ImproperlyConfigured: si tenant.wallet est absent
    """
```

Comportement détaillé :
1. Charge le wallet de la carte : `user.wallet` si carte identifiée, sinon `wallet_ephemere`.
   Si les deux sont absents, lève `NoEligibleTokens` (carte vierge).
2. Vérifie que `tenant.wallet` existe (sinon `ImproperlyConfigured`).
3. Filtre les tokens éligibles via la requête décrite plus bas.
4. Si `not exists()` → `NoEligibleTokens`.
5. Dans `transaction.atomic()` :
   - Pour chaque token : `TransactionService.creer(action=REFUND, ...)` (utilise `select_for_update` interne).
   - Récupère le Product système via `get_or_create_product_remboursement()`.
   - Si `total_fed > 0` : crée `LigneArticle(payment_method=STRIPE_FED, amount=total_fed, ...)`.
   - Crée `LigneArticle(payment_method=CASH, amount=-(total_tlf + total_fed), ...)`.
   - Si `vider_carte=True` : reset des champs.

### `_tokens_eligibles()` — helper privé

```python
def _tokens_eligibles(wallet: Wallet, tenant: Client) -> QuerySet[Token]:
    return Token.objects.filter(
        wallet=wallet,
        value__gt=0,
    ).filter(
        Q(asset__category=Asset.TLF, asset__tenant_origin=tenant)
        | Q(asset__category=Asset.FED)
    ).select_related('asset', 'asset__tenant_origin')
```

### `get_or_create_product_remboursement()` — Product système partagé

```python
def get_or_create_product_remboursement() -> Product:
    """
    Retourne le Product système 'Remboursement carte' partagé.
    Crée le Product et un PriceSold associé au premier appel.
    Réutilisé par l'admin (Phase 1) et le POS LaBoutik (Phase 3).
    """
    product, _ = Product.objects.get_or_create(
        methode_caisse=Product.MethodeCaisse.VC,
        defaults={
            "name": _("Remboursement carte"),
            "categorie_article": Product.DON,  # ou autre catégorie système, à valider en plan
            # publish=False pour ne pas l'exposer sur la billetterie publique
        },
    )
    return product
```

### `CarteCashlessAdmin`

- `list_display` : `tag_id`, `number`, `user_link`, `detail_origine`, `wallet_status` (badge identifié/anonyme/vierge), `solde_total_euros` (annotation Sum sur Token).
- `search_fields` : `tag_id`, `number`, `user__email`.
- `list_filter` : `detail__origine` (caché pour les non-superusers), filtre custom « identifiée / anonyme / vierge ».
- `get_queryset()` : filtre `detail__origine=request.tenant` si `not request.user.is_superuser`.
- `has_add_permission()` / `has_delete_permission()` : `request.user.is_superuser`.
- `has_change_permission()` / `has_view_permission()` : `TenantAdminPermissionWithRequest(request)`.
- **Vue détail enrichie** (`change_view` overridée) injecte dans le contexte :
  - `tokens_eligibles` (TLF du tenant + FED, value > 0)
  - `tokens_autres` (TNF, TIM, FID, TLF d'autres tenants — read-only)
  - `transactions_recentes` (20 dernières `Transaction.objects.filter(card=carte).order_by('-id')`)
  - Bouton « Rembourser en espèces » → lien vers `/admin/cards/<uuid>/refund/`
  - Bouton « Détacher utilisateur·ice » (modal Unfold + POST simple `/admin/cards/<uuid>/detach/`)
- Toutes les méthodes helper sont définies **au niveau module**, jamais dans la classe (cf. `tests/PIEGES.md`
  « Ne JAMAIS définir de méthodes helper dans un ModelAdmin Unfold »).

### `DetailAdmin`

- `list_display` : `slug`, `base_url`, `origine`, `generation`, `nb_cartes` (annotation Count).
- `get_queryset()` : filtre `origine=request.tenant` si pas superuser.
- Permissions identiques à `CarteCashlessAdmin`.
- Édition libre (changer image, slug, generation) pour le tenant propriétaire ; superuser peut tout.

### `CardRefundViewSet(viewsets.ViewSet)`

Patterns FALC `/djc` : pas de `ModelViewSet`, methodes explicites, `serializers.Serializer`, HTMX server-rendered.

```python
class CardRefundViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def retrieve(self, request, pk):
        # GET /admin/cards/<uuid>/refund/
        carte = get_object_or_404(CarteCashless, uuid=pk)
        _check_admin_or_superuser_for_card(request, carte)
        wallet = _wallet_de_la_carte(carte)
        if wallet is None:
            return _render_carte_vide(request, carte)
        tokens = _tokens_eligibles(wallet, request.tenant)
        contexte = {
            "carte": carte,
            "wallet": wallet,
            "tokens_eligibles": list(tokens),
            "total_tlf_centimes": sum(t.value for t in tokens if t.asset.category == Asset.TLF),
            "total_fed_centimes": sum(t.value for t in tokens if t.asset.category == Asset.FED),
        }
        return render(request, "admin/cards/refund.html", contexte)

    @action(detail=True, methods=["POST"])
    def confirm(self, request, pk):
        # POST /admin/cards/<uuid>/refund/confirm/
        carte = get_object_or_404(CarteCashless, uuid=pk)
        _check_admin_or_superuser_for_card(request, carte)
        serializer = CardRefundConfirmSerializer(data=request.POST)
        serializer.is_valid(raise_exception=True)
        try:
            resultat = WalletService.rembourser_en_especes(
                carte=carte,
                tenant=request.tenant,
                ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
                vider_carte=serializer.validated_data["vider_carte"],
            )
        except NoEligibleTokens:
            messages.warning(request, _("Aucun solde remboursable sur cette carte."))
            return _redirect_to_card_change(carte)
        montant_total_euros = resultat["total_centimes"] / 100
        messages.success(request, _("Remboursement effectué : {amount}€").format(
            amount=montant_total_euros))
        return _redirect_to_card_change(carte)
```

### Permissions helper

```python
def _check_admin_or_superuser_for_card(request, carte: CarteCashless):
    if request.user.is_superuser:
        return
    if not TenantAdminPermissionWithRequest(request):
        raise PermissionDenied()
    if carte.detail is None or carte.detail.origine != request.tenant:
        raise PermissionDenied()
```

### Sidebar

Dans `Administration/admin/dashboard.py`, dans la section Fedow déjà conditionnée à
`configuration.module_monnaie_locale`, ajouter en début de liste `items` :

```python
{
    "title": _("Cartes NFC"),
    "icon": "credit_card",
    "link": reverse_lazy("staff_admin:QrcodeCashless_cartecashless_changelist"),
    "permission": admin_permission,
},
{
    "title": _("Lots de cartes"),
    "icon": "inventory_2",
    "link": reverse_lazy("staff_admin:QrcodeCashless_detail_changelist"),
    "permission": admin_permission,
},
```

### Cleanup `admin_root.py`

- Commenter les lignes 205-207 (`root_admin_site.register(...)` ProductDirectory, EventDirectory, RootConfiguration).
- Ajouter en en-tête de fichier (après les imports) un docstring :
  ```python
  """
  Site admin root historique — DESACTIVE.

  Tout l'admin transite par staff_admin_site (Unfold) défini dans Administration/admin/site.py.
  Ce fichier est conservé pour référence pendant la migration V1 -> V2.
  Toutes les déclarations sont commentées.
  """
  ```

## Data flow

### Flow nominal — Carte identifiée avec TLF + FED, sans réinitialisation

```
[1] Admin clique « Rembourser en espèces » sur la fiche carte
    → GET /admin/cards/<uuid>/refund/

[2] CardRefundViewSet.retrieve() :
    a. get_object_or_404 carte
    b. _check_admin_or_superuser_for_card → OK (carte.detail.origine == request.tenant)
    c. wallet = carte.user.wallet (priorité user.wallet, sinon wallet_ephemere)
    d. tokens = _tokens_eligibles(wallet, tenant)
    e. Render refund.html (tableau tokens + totaux + checkbox VV + bouton confirmer)

[3] Admin clique « Confirmer le remboursement » (checkbox VV non cochée)
    → POST /admin/cards/<uuid>/refund/confirm/  (HTMX hx-post)

[4] CardRefundViewSet.confirm() :
    a. Re-permission check
    b. CardRefundConfirmSerializer.validate({vider_carte: False})
    c. WalletService.rembourser_en_especes(carte, tenant, ip, False) :
       with transaction.atomic():
         tokens = _tokens_eligibles(...)
         total_tlf, total_fed = 0, 0
         transactions_creees = []
         for token in tokens:
           tx = TransactionService.creer(
             action=Transaction.REFUND,
             sender=wallet, receiver=tenant.wallet,
             asset=token.asset, montant_en_centimes=token.value,
             tenant=tenant, card=carte, ip=ip,
             comment="Remboursement espèces admin",
             metadata={"admin_email": request.user.email, "vider_carte": False},
           )
           transactions_creees.append(tx)
           if token.asset.category == Asset.TLF: total_tlf += token.value
           elif token.asset.category == Asset.FED: total_fed += token.value
         product_refund = get_or_create_product_remboursement()
         price_sold = _get_or_create_pricesold_for(product_refund)
         lignes = []
         if total_fed > 0:
           fed_asset = Asset.objects.get(category=Asset.FED)
           lignes.append(LigneArticle.objects.create(
             pricesold=price_sold,
             qty=1, amount=total_fed,
             payment_method=PaymentMethod.STRIPE_FED,
             status=LigneArticle.VALID,
             sale_origin=SaleOrigin.ADMIN,
             carte=carte, wallet=wallet,
             asset=fed_asset.uuid,
             metadata={"refund": True, "transactions_uuids": [...]}
           ))
         lignes.append(LigneArticle.objects.create(
           pricesold=price_sold,
           qty=1, amount=-(total_tlf + total_fed),
           payment_method=PaymentMethod.CASH,
           status=LigneArticle.VALID,
           sale_origin=SaleOrigin.ADMIN,
           carte=carte, wallet=wallet,
           metadata={"refund": True, "tlf_centimes": total_tlf, "fed_centimes": total_fed}
         ))
         return {...}
    d. messages.success(...)
    e. Redirect vers /admin/QrcodeCashless/cartecashless/<uuid>/change/
```

### Flow VV — Carte avec checkbox « Réinitialiser »

Identique au flow nominal jusqu'à la fin de l'atomic, plus :
```
f. CartePrimaire.objects.filter(carte=carte).delete()
g. carte.user = None
   carte.wallet_ephemere = None
   carte.save(update_fields=["user", "wallet_ephemere"])
```

## Error handling

| Cas | Détection | Réaction |
|---|---|---|
| Carte sans wallet (vierge, jamais scannée) | `_wallet_de_la_carte() is None` | retrieve renvoie un partial info « Carte vierge », pas de bouton confirmer. |
| Aucun token éligible (solde 0 sur tous les assets éligibles) | `_tokens_eligibles().exists() is False` | Idem, message « Aucun solde remboursable. » |
| Permission refusée (admin tenant sur carte d'un autre tenant) | `_check_admin_or_superuser_for_card` | `PermissionDenied` 403, log warning. |
| Race condition : token modifié entre GET et POST | Re-fetch dans `confirm` + `select_for_update` via `WalletService.debiter()` interne | Si solde toujours > 0 : continue avec le solde actuel (montant final peut différer de l'affichage). Si solde tombé à 0 : `NoEligibleTokens` → message warning, redirect. |
| `SoldeInsuffisant` levé par `TransactionService.creer()` | rollback automatique du `transaction.atomic()` | Message warning, log error, redirect. Filet de sécurité, ne devrait pas arriver. |
| `tenant.wallet` absent (config incomplète) | guard en début de `rembourser_en_especes` | `ImproperlyConfigured` → message error admin, log critical. |
| `module_monnaie_locale=False` | sidebar masquée + middleware admin (cohérent avec autres modules) | Route 404 si accès direct. |

## Testing

### Tests pytest DB-only (`tests/pytest/test_card_refund_service.py`)

```
test_rembourser_carte_avec_user_tlf_seul       → 1 Transaction REFUND, 1 LigneArticle CASH négative, solde TLF=0
test_rembourser_carte_avec_user_fed_seul       → 1 Transaction REFUND, 1 LigneArticle FED + 1 LigneArticle CASH
test_rembourser_carte_avec_user_tlf_et_fed     → 2 Transactions REFUND, 2 LigneArticles
test_rembourser_carte_anonyme_wallet_ephemere  → idem mais via wallet_ephemere
test_rembourser_exclut_tnf_tim_fid             → tokens non éligibles ignorés, restent intacts
test_rembourser_exclut_tlf_autre_tenant        → TLF dont asset.tenant_origin != tenant ignoré
test_rembourser_carte_vide_raise_no_eligible   → NoEligibleTokens si aucun token éligible
test_rembourser_avec_vider_carte_reset         → carte.user=None, wallet_ephemere=None, CartePrimaire supprimée
test_rembourser_atomic_rollback_on_failure     → mock TransactionService raise, vérifier rollback complet
test_get_or_create_product_remboursement       → helper crée le Product la 1re fois, réutilise ensuite
```

### Tests admin (`tests/pytest/test_admin_cards.py`)

```
test_card_admin_filter_by_tenant               → admin tenant ne voit que ses cartes
test_card_admin_superuser_voit_tout            → superuser voit toutes les cartes
test_card_admin_add_forbidden_for_tenant_admin → POST add → 403
test_card_admin_add_allowed_for_superuser      → POST add → 200/302
test_card_admin_delete_forbidden_for_tenant    → DELETE → 403
test_detail_admin_filter_by_origine            → admin tenant ne voit que ses Detail
test_refund_view_get_eligible_tokens           → GET retrieve renvoie tokens TLF tenant + FED, exclut autres
test_refund_view_post_creates_transactions     → POST confirm crée Transactions et LigneArticle
test_refund_view_permission_carte_autre_tenant → admin tenant → 403 sur carte d'un autre tenant
test_refund_view_carte_vierge_no_button        → carte sans wallet : pas de bouton confirmer
```

### Tests E2E Playwright (`tests/e2e/test_admin_card_refund.py`)

```
test_e2e_admin_refund_flow_complet :
  1. login admin tenant lespass
  2. fixture : carte de test avec wallet TLF (10€) + FED (5€)
  3. naviguer vers /admin/QrcodeCashless/cartecashless/
  4. cliquer la carte
  5. cliquer "Rembourser en espèces"
  6. vérifier l'affichage des 2 montants (10€ TLF + 5€ FED)
  7. cliquer "Confirmer"
  8. vérifier toast succès "Remboursement effectué : 15.0€"
  9. retour fiche carte → solde affiché à 0
  10. vérifier en DB : 2 Transactions REFUND, 2 LigneArticles (FED + CASH)
```

### Pièges anticipés

- **`schema_context('lespass')` + `tenant_context`** : toutes les opérations sur `CarteCashless`
  (SHARED_APPS) doivent passer par `tenant_context(tenant)` dès qu'on touche au `connection.tenant`.
  Cf. `tests/PIEGES.md` 9.30 et 9.1.
- **`tag_id` et `number` max 8 caractères** dans les fixtures de test (PIEGES 9.31).
- **`LigneArticle` est en TENANT_APPS, `Transaction` en SHARED_APPS** — le service doit gérer correctement
  les deux schémas via `tenant_context`.
- **`SaleOrigin.ADMIN` est déjà utilisé ailleurs** (`BaseBillet/models.py:2870, 2896`) — la distinction
  des refunds admin se fait via `pricesold.product.methode_caisse=VC` ou `metadata.refund=True`.
  À documenter dans `REFUND.md`.
- **Helpers ModelAdmin Unfold** : jamais dans la classe (PIEGES « Ne JAMAIS définir de méthodes helper
  dans un ModelAdmin Unfold »). Toutes les méthodes utilitaires au niveau module.
- **Toujours définir les 4 `has_*_permission`** sur chaque ModelAdmin (PIEGES sur les permissions).

## Compatibilité V1 / V2

- V1 (anciens tenants avec `Configuration.server_cashless` renseigné) : `module_monnaie_locale=False`
  → la section sidebar est masquée, les routes admin renvoient 404. Pas d'impact.
- V2 (nouveaux tenants) : admin pleinement fonctionnel.
- Phase 3 (POS LaBoutik V2) : code mutualisé via `WalletService.rembourser_en_especes()`.

## Migration

- Pas de migration de schéma DB.
- Ajout `Product.MethodeCaisse.VC = "VC"` → migration `BaseBillet` (alter `Product.methode_caisse choices`).
- Pas de data migration : le Product « Remboursement carte » est créé à la demande par
  `get_or_create_product_remboursement()`.

## i18n

Toutes les chaînes user-facing utilisent `_("...")`. Lancer après implémentation :
```
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
docker exec lespass_django poetry run django-admin compilemessages
```

## Décisions transversales (rappel du brainstorming)

- Scope admin = consultation + actions ciblées (B). Création/suppression réservées au superuser.
- Filtre par `Detail.origine == request.tenant` sauf superuser.
- Detail admin séparé, mêmes règles.
- Remboursement = TLF (`asset.tenant_origin == tenant`) + FED (un seul Asset FED dans le système).
- VC + VV unifiés via une checkbox « Réinitialiser la carte ».
- Page dédiée via `viewsets.ViewSet` patterns FALC `/djc`.
- Product système partagé (réutilisé Phase 3 POS).
- `SaleOrigin.ADMIN` réutilisé (déjà existant).
- Suivi de la dette pot central FED → Phase 2.
- Bouton POS « Vider Carte / Refund » → Phase 3.

## Roadmap suivante

- Phase 2 : `Transaction.BANK_TRANSFER` (action), vue admin pour saisir un virement reçu, calcul de la dette
  pot central → tenant pour les FED remboursés.
- Phase 3 : Bouton POS Cashless, `Product.MethodeCaisse.VV` (à ajouter), vue dans `laboutik/views.py`
  qui réutilise `WalletService.rembourser_en_especes()`.

## Notes pour l'implémentation

- Vérifier en début de plan que `LigneArticle.pricesold` accepte le Product système partagé
  (potentiellement `null=True` pas activé — adapter le helper).
- Le helper `_get_or_create_pricesold_for(product)` doit créer un `ProductSold` + `PriceSold` à 0€
  (montant porté par `LigneArticle.amount` directement). Inspirer de `_creer_lignes_articles` dans
  `laboutik/views.py`.
- L'event `_check_admin_or_superuser_for_card` doit être identique entre `retrieve` et `confirm`
  pour éviter une fenêtre d'incohérence.
