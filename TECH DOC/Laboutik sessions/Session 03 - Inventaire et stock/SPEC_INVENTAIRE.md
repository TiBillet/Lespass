# Spec : Gestion d'inventaire et stock POS

> Design validé le 2026-04-03.
> Concerne uniquement les produits POS (pas la billetterie).

---

## 1. Vue d'ensemble

Nouvelle app Django `inventaire` (TENANT_APP) pour gérer le stock des articles
vendus au POS : boissons (dont pression via tireuse), nourriture, merch.

Activable par tenant via `module_inventaire` sur Configuration (dashboard Groupware).

### Principes

- **Stock optionnel par produit** : pas de `Stock` lié = pas de gestion
- **Unités de base** : pièces (UN), centilitres (CL), grammes (GR) — toujours la plus petite unité
- **Journal de mouvements** : chaque entrée/sortie est tracée avec type, motif, auteur
- **Décrémentation atomique** : `F()` + `filter()` en PostgreSQL, pas de verrou bloquant
- **Non bloquant par défaut** : un produit peut être vendu même à stock ≤ 0 (configurable)

---

## 2. App `inventaire`

**Type :** TENANT_APP (chaque lieu a son propre stock).

**Fichiers :**

| Fichier | Rôle |
|---------|------|
| `inventaire/__init__.py` | App init |
| `inventaire/apps.py` | AppConfig |
| `inventaire/models.py` | Stock, MouvementStock |
| `inventaire/services.py` | Logique métier (décrémentation, résumé clôture) |
| `inventaire/serializers.py` | Validation DRF (jamais Django Forms) |
| `inventaire/views.py` | StockViewSet, DebitMetreViewSet |
| `inventaire/urls.py` | Routes API |
| `inventaire/migrations/` | Migrations |

---

## 3. Modèle `Stock`

OneToOne vers Product. Pas de Stock = pas de gestion de stock pour ce produit.

| Champ | Type | Description |
|-------|------|-------------|
| `uuid` | UUIDField (PK) | Clé primaire |
| `product` | OneToOneField(Product, related_name='stock') | Le produit lié |
| `quantite` | IntegerField(default=0) | Stock actuel en unité de base. Peut être négatif si `autoriser_vente_hors_stock=True` |
| `unite` | CharField(2, choices, default='UN') | `UN` (pièces), `CL` (centilitres), `GR` (grammes) |
| `seuil_alerte` | PositiveIntegerField(null=True, blank=True) | Seuil bas pour alerte visuelle POS. null = pas d'alerte |
| `autoriser_vente_hors_stock` | BooleanField(default=True) | Si False, produit bloqué quand stock ≤ 0. True par défaut (non bloquant) |

### Contraintes

- `product` unique (OneToOne)
- `quantite` peut être négatif (pas de CheckConstraint — le comportement dépend de `autoriser_vente_hors_stock`)

---

## 4. Champ `contenance` sur Price

Ajouté sur `BaseBillet.Price` (migration BaseBillet).

| Champ | Type | Description |
|-------|------|-------------|
| `contenance` | PositiveIntegerField(null=True, blank=True) | Quantité consommée par unité vendue, dans l'unité du Stock parent. Ex : pinte = 50 (cl), demi = 25 (cl), part = 1 (pièce), portion = 150 (g). null = 1 unité par défaut |

### Logique

- Quand `unite_stock = CL` : chaque Price peut avoir une contenance différente (pinte/demi/galopin)
- Quand `unite_stock = UN` : contenance = 1 (ou null, même effet). Chaque vente décrémente de `qty`
- Quand `unite_stock = GR` : contenance en grammes par portion (ex : 150g)
- Consommation par vente = `qty × (contenance or 1)`

---

## 5. Modèle `MouvementStock`

Journal de tous les mouvements de stock. Immutable (lecture seule dans l'admin).

| Champ | Type | Description |
|-------|------|-------------|
| `uuid` | UUIDField (PK) | Clé primaire |
| `stock` | ForeignKey(Stock, related_name='mouvements') | Le stock concerné |
| `type_mouvement` | CharField(2, choices) | Type du mouvement (voir ci-dessous) |
| `quantite` | IntegerField | Delta signé : positif = entrée, négatif = sortie |
| `quantite_avant` | IntegerField | Snapshot du stock avant le mouvement (pour audit) |
| `motif` | CharField(200, blank=True) | Texte libre optionnel (ex : "fût tombé", "offert au DJ", "pi-tireuse-01") |
| `ligne_article` | ForeignKey(LigneArticle, null=True, blank=True) | Lien vers la vente POS (pour type VENTE uniquement) |
| `cloture` | ForeignKey(ClotureCaisse, null=True, blank=True) | Clôture de rattachement |
| `cree_par` | ForeignKey(TibilletUser, null=True, blank=True) | Utilisateur. null = système (vente auto, capteur) |
| `cree_le` | DateTimeField(auto_now_add=True) | Horodatage |

### Types de mouvement

| Code | Label | Signe | Déclenchement |
|------|-------|-------|---------------|
| `VE` | Vente | − | Automatique à la vente POS |
| `RE` | Réception | + | Manuel (admin ou POS) |
| `AJ` | Ajustement inventaire | ± | Manuel — corrige le stock réel |
| `OF` | Offert | − | Manuel |
| `PE` | Perte / casse | − | Manuel |
| `DM` | Débit mètre | − | API capteur Pi (futur) |

### Notes

- `quantite` est toujours exprimé dans l'unité de base du Stock (cl, g, ou pièces)
- Pour une vente : `quantite = -(qty × contenance)`. Ex : 2 pintes = `-(2 × 50)` = −100 cl
- `quantite_avant` permet de reconstruire l'historique sans agrégation
- `AJ` : l'utilisateur saisit le stock réel, le système calcule `réel - actuel`
- `DM` : le `capteur_id` est stocké dans le champ `motif`

---

## 6. Décrémentation atomique

### À la vente POS

Branchée dans le flux de paiement, après validation, dans la même `transaction.atomic()`
que la création des `LigneArticle`.

```python
# Calcul de la consommation
# / Compute consumption in base unit
contenance = price.contenance or 1
delta = qty * contenance

if stock.autoriser_vente_hors_stock:
    # Non bloquant : décrémente même si stock passe en négatif
    # / Non-blocking: decrements even if stock goes negative
    Stock.objects.filter(pk=stock.pk).update(
        quantite=F('quantite') - delta
    )
else:
    # Bloquant : échoue si stock insuffisant
    # / Blocking: fails if insufficient stock
    updated = Stock.objects.filter(
        pk=stock.pk,
        quantite__gte=delta
    ).update(quantite=F('quantite') - delta)

    if not updated:
        raise StockInsuffisant(product, delta, stock.quantite)
```

### Protection race condition

- `F()` + `filter()` = atomique en PostgreSQL, pas de verrou explicite
- Gère nativement la concurrence multi-caisse (2 terminaux vendent en même temps)
- Pas de `select_for_update()` — le pattern `F()` est suffisant et non bloquant

### Création du mouvement

Juste après l'update atomique :

```python
MouvementStock.objects.create(
    stock=stock,
    type_mouvement='VE',
    quantite=-delta,
    quantite_avant=stock_avant,
    ligne_article=ligne_article,
    cree_par=None,  # Système
)
```

### Annulation / remboursement

Un mouvement `AJ` inverse est créé pour recréditer le stock (pas de suppression
du mouvement `VE` original).

---

## 7. Affichage visuel dans le POS

### 3 états

| État | Condition | Rendu |
|------|-----------|-------|
| **Normal** | `quantite > seuil_alerte` (ou pas de seuil) | Apparence standard |
| **Alerte** | `quantite ≤ seuil_alerte` et `quantite > 0` | Bordure ou pastille orange + quantité restante |
| **Rupture** | `quantite ≤ 0` | Si bloquant : grisé + barré, non cliquable. Si non bloquant : pastille rouge, reste cliquable |

### Pas de Stock lié = aucun indicateur

Comportement actuel inchangé.

### Affichage quantité restante

- `UN` : "3 restants"
- `CL` : "1.5 L restants" (conversion cl → L pour l'affichage)
- `GR` : "800 g restants" ou "1.2 kg" si ≥ 1000g

### Technique

- `select_related('stock')` dans la requête produits POS
- État calculé côté template/serializer
- Rafraîchissement après chaque vente (HTMX swap existant ou WebSocket)
- `aria-live="polite"` sur la zone quantité (accessibilité)

---

## 8. Actions rapides dans le POS

### 3 actions

| Action | Type mouvement | Cas d'usage |
|--------|----------------|-------------|
| **Réception rapide** | `RE` | Un fût arrive (+3000 cl) |
| **Perte / casse** | `PE` | Bouteille cassée |
| **Offert** | `OF` | Tournée offerte |

### Architecture (conforme DJC)

**ViewSet** — `StockViewSet(viewsets.ViewSet)` dans `inventaire/views.py` :

```python
class StockViewSet(viewsets.ViewSet):
    permission_classes = [HasLaBoutikAccess]

    @action(detail=True, methods=["POST"])
    def reception(self, request, pk=None): ...

    @action(detail=True, methods=["POST"])
    def perte(self, request, pk=None): ...

    @action(detail=True, methods=["POST"])
    def offert(self, request, pk=None): ...
```

**Validation** — DRF `Serializer` (jamais Django Forms) :

```python
class MouvementRapideSerializer(serializers.Serializer):
    quantite = serializers.IntegerField(min_value=1)
    motif = serializers.CharField(required=False, allow_blank=True)
```

**Interface** — modale HTMX :
- Menu contextuel sur le produit (long press ou bouton `...`)
- `hx-get` charge `inventaire/partial/modale_mouvement.html`
- `hx-post` soumet vers l'action du ViewSet
- Réponse = partial HTML qui rafraîchit l'affichage du produit
- Toast via `django.messages` + `HX-Trigger`

**Conversion d'unité dans la modale :**
- L'utilisateur saisit en unité pratique : litres (CL), kg (GR), pièces (UN)
- La conversion en unité de base se fait côté serveur dans le serializer
- Affichage : "Ajouter 30 L → +3000 cl au stock"

---

## 9. Admin Unfold

### StockInline sur POSProductAdmin

```python
class StockInline(TabularInline):
    model = Stock
    extra = 0
    max_num = 1
    fields = ("quantite", "unite", "seuil_alerte", "autoriser_vente_hors_stock")
```

Uniquement sur `POSProductAdmin` (pas ProductAdmin ni TicketProductAdmin).

### MouvementStockAdmin (lecture seule)

Colonnes : date, produit, type (badge coloré via `@display`), quantité, stock après,
motif, auteur, clôture.

Filtres : type de mouvement, produit, date, clôture.

Lecture seule : `has_add_permission = False`, `has_change_permission = False`,
`has_delete_permission = False`.

**Helpers** (conversion unité, formatage) : fonctions module-level,
**jamais dans la classe** (piège Unfold wrapping).

### Action "Ajustement inventaire"

Via `get_urls()` + bouton dans `change_form_after_template` (pas `actions_row` —
piège permissions Unfold).

L'utilisateur saisit le stock réel compté → le système calcule `réel - actuel`
→ crée `MouvementStock(type=AJ)`.

### module_inventaire

Nouveau champ `BooleanField(default=False)` sur Configuration.

Entrée dans `MODULE_FIELDS` :
```python
"module_inventaire": {"name": _("Inventory"), "icon": "inventory_2"},
```

Carte sur le dashboard Groupware + toggle HTMX.

### Sidebar conditionnelle

Section "Inventaire" visible si `config.module_inventaire` :
- "Mouvements de stock" → `MouvementStockAdmin` changelist

---

## 10. Endpoint API — Débit mètre (capteur Pi)

Récepteur minimaliste pour un futur capteur de débit sur Raspberry Pi.
On prépare juste le endpoint, le protocole capteur viendra plus tard.

**URL :** `POST /api/inventaire/debit-metre/`

**Auth :** API Key (header `Authorization: Api-Key <key>`)

**Payload :**
```json
{
    "product_uuid": "uuid-du-produit",
    "quantite_cl": 850,
    "capteur_id": "pi-tireuse-01"
}
```

**Comportement :**
- Vérifie que le Product a un Stock avec `unite=CL`
- Crée un `MouvementStock(type=DM, quantite=-quantite_cl, motif=capteur_id)`
- Met à jour `Stock.quantite` via `F()` atomique
- Retourne `201` avec le stock restant

**ViewSet :** `DebitMetreViewSet(viewsets.ViewSet)` dans `inventaire/views.py`,
une seule méthode `create()`.

**Validation :** `DebitMetreSerializer(serializers.Serializer)`.

**Ce qu'on ne fait PAS maintenant :**
- Pas d'enregistrement des capteurs en base
- Pas de WebSocket temps réel
- Pas de réconciliation automatique stock vs capteur

---

## 11. Intégration avec la clôture de caisse

### Données ajoutées au rapport de clôture

| Info | Description |
|------|-------------|
| Mouvements de la période | Tous les `MouvementStock` créés entre la clôture précédente et celle-ci |
| Consommation par produit | Somme des ventes (`VE`) par produit, en unité lisible |
| Pertes / offerts | Somme des types `PE` et `OF` par produit |
| Écarts débit mètre | Si `DM` existe : comparaison ventes enregistrées vs consommation capteur |
| Alertes stock bas | Produits dont `quantite ≤ seuil_alerte` au moment de la clôture |

### Technique

- `MouvementStock.cloture` (FK nullable) est rempli au moment de la clôture :
  tous les mouvements sans clôture sont rattachés à la clôture en cours
- Le résumé stock est calculé par `inventaire/services.py` →
  `ResumeStockService.generer_resume_cloture(cloture)`
- Résumé stocké en JSON dans le rapport de clôture
- Affiché dans le template rapport existant, section supplémentaire

### Ce qu'on ne fait PAS

- Pas de remise à zéro du stock à la clôture
- Pas de blocage de la clôture si stock négatif
- Pas d'inventaire obligatoire avant clôture

---

## 12. Fichiers impactés

### Fichiers à créer

| Fichier | Rôle |
|---------|------|
| `inventaire/__init__.py` | App init |
| `inventaire/apps.py` | AppConfig |
| `inventaire/models.py` | Stock, MouvementStock |
| `inventaire/services.py` | Logique métier |
| `inventaire/serializers.py` | Validation DRF |
| `inventaire/views.py` | StockViewSet, DebitMetreViewSet |
| `inventaire/urls.py` | Routes |
| `inventaire/migrations/0001_initial.py` | Migration initiale |
| `Administration/templates/admin/inventaire/` | Templates admin (ajustement, section clôture) |
| `inventaire/templates/inventaire/partial/` | Partials HTMX POS (modale mouvement) |

### Fichiers à modifier

| Fichier | Changement |
|---------|-----------|
| `BaseBillet/models.py` | `module_inventaire` sur Configuration + `contenance` sur Price |
| `TiBillet/settings.py` | `'inventaire'` dans TENANT_APPS |
| `Administration/admin_tenant.py` | StockInline, MouvementStockAdmin, sidebar, MODULE_FIELDS, dashboard |
| `laboutik/views.py` (ou service paiement) | Branchement décrémentation stock à la vente |
| `laboutik/reports.py` | Section résumé stock dans le rapport de clôture |

---

## 13. Ce qui est explicitement hors périmètre

- Multi-entrepôt, transferts inter-sites
- Recettes / nomenclatures (1 fût = 120 verres)
- FIFO/LIFO, valorisation du stock
- Dates de péremption (DLC)
- Fournisseurs, bons de commande
- Numéros de série, codes-barres EAN
- Prévision de demande
- Enregistrement des capteurs en base
- Réconciliation automatique capteur vs ventes
