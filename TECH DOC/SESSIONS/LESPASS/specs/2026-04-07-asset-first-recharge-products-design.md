# Asset-first recharge products

> L'Asset fedow_core drive la creation des produits de recharge.
> Plus de bouton "Recharge" sans Asset, plus de lookup par categorie.

Date : 2026-04-07

---

## Contexte

### Probleme

L'erreur "Monnaie locale non configuree" apparait sur LaBoutik quand un
caissier tente une recharge cashless. La cause : `_executer_recharges()`
cherche un `fedow_core.Asset` par categorie (`Asset.objects.filter(category=TLF)`),
mais aucun Asset n'existe en base. Les Products de recharge (Recharge 10EUR,
Cadeau 5EUR, etc.) sont crees par `create_test_pos_data` sans lien avec un Asset.

### 3 modeles Asset coexistent

| Modele | App | Schema | Statut |
|--------|-----|--------|--------|
| `fedow_connect.Asset` | fedow_connect | TENANT | Legacy V1 |
| `fedow_public.AssetFedowPublic` | fedow_public | PUBLIC | Legacy V1.5 ("en attendant le grand nettoyage V2") |
| `fedow_core.Asset` | fedow_core | PUBLIC (SHARED_APPS) | V2 — utilise par laboutik |

### Decision

On travaille sur V2 uniquement. Les deux mondes (legacy et V2) restent etanches.
Le pont legacy vers V2 et la migration des soldes sont hors scope.

---

## Design

### Principe : l'Asset drive tout

```
fedow_core.Asset cree (ex: TLF "Monnaie locale Reunion")
    |
    | post_save signal
    v
1 Product auto-cree :
    name = "Recharge Monnaie locale Reunion"
    methode_caisse = RE
    asset = FK vers cet Asset
    categorie_pos = CategorieProduct "Cashless"
    |
    +--- Price "1 EUR"   (prix=1.00, free_price=False, order=1)
    +--- Price "5 EUR"   (prix=5.00, free_price=False, order=2)
    +--- Price "10 EUR"  (prix=10.00, free_price=False, order=3)
    +--- Price "Libre"   (prix=0, free_price=True, order=4)
```

Le caissier voit une tuile "Recharge Monnaie locale Reunion" qui ouvre
l'overlay multi-tarif (1 / 5 / 10 / Libre). Pattern identique aux
adhesions multi-tarif existantes.

### 1. Modele de donnees

**Nouveau champ sur Product :**

```python
# BaseBillet/models.py — Product
asset = models.ForeignKey(
    "fedow_core.Asset",
    on_delete=models.SET_NULL,
    blank=True, null=True,
    related_name="products",
)
```

- `null=True` pour les produits non-cashless (VT, AD, BI, etc.)
- Pour les produits de recharge (RE/RC/TM), ce champ est rempli
  automatiquement par le signal post_save de l'Asset.

**Mapping Asset category vers Product methode_caisse :**

| Asset.category | methode_caisse | Product.name auto-genere |
|---|---|---|
| TLF (Token Local Fiduciaire) | RE (Recharge euros) | "Recharge {asset.name}" |
| TNF (Token Local Non-Fiduciaire) | RC (Recharge cadeau) | "Recharge cadeau {asset.name}" |
| TIM (Monnaie Temps) | TM (Recharge temps) | "Recharge temps {asset.name}" |

Les autres categories (FED, FID) ne generent pas de Product de recharge.

**1 migration** : ajout de la FK `Product.asset`.

### 2. Signal post_save sur fedow_core.Asset

**Emplacement** : `fedow_core/signals.py` (nouveau fichier), enregistre
dans `fedow_core/apps.py` via `ready()`.

**A la creation (`created=True`)** pour TLF, TNF ou TIM :

1. Trouver ou creer la `CategorieProduct "Cashless"` (couleurs/icone par defaut)
2. Creer le Product (name, methode_caisse, asset FK, categorie_pos, couleurs)
3. Creer 4 Price : 1 EUR, 5 EUR, 10 EUR, Libre
4. Ajouter le Product au M2M `products` de tous les
   `PointDeVente(comportement=CASHLESS)` du tenant courant

**A la modification (`created=False`)** :

- `archive` passe a `True` → `Product.archive = True`
- `archive` repasse a `False` → `Product.archive = False`
- `name` change → met a jour `Product.name`

**Ce que le signal ne fait PAS** :

- Pas de creation pour FED, FID
- Pas de suppression de Product (archivage seulement)
- Pas de modification des Price (l'admin les gere manuellement apres creation)

### 3. Refactoring de `_executer_recharges()`

**Avant** — 3 blocs dupliques avec lookup par categorie :

```python
asset_tlf = Asset.objects.filter(
    tenant_origin=tenant_courant,
    category=Asset.TLF,
    active=True,
).first()
if asset_tlf is None:
    raise ValueError(_("Monnaie locale non configuree"))
```

**Apres** — 1 boucle generique avec lien direct :

```python
for article in articles_panier:
    asset = article["product"].asset
    TransactionService.creer_recharge(
        sender_wallet=asset.wallet_origin,
        receiver_wallet=wallet_client,
        asset=asset,
        montant_en_centimes=montant,
        tenant=tenant_courant,
        ip=ip_client,
    )
```

L'erreur "Monnaie locale non configuree" ne peut plus arriver : si l'Asset
n'existe pas, le Product n'existe pas, le bouton n'apparait pas.

**Meme refactoring pour `_payer_par_nfc()`** : le lookup
`Asset.objects.filter(category=TLF)` est remplace par
`article["product"].asset`.

### 4. Filtre a l'affichage dans le POS

Dans `_construire_donnees_articles()`, apres le chargement des produits M2M :

```python
# Produits de recharge sans Asset lie, ou Asset archive/inactif → ne pas afficher
if product.methode_caisse in METHODES_RECHARGE:
    if product.asset is None or product.asset.archive or not product.asset.active:
        continue
```

Ajout de `select_related("asset")` sur la requete produits pour eviter N+1.

En fonctionnement normal, le signal empeche la situation "Product sans Asset".
Ce filtre protege contre les donnees legacy ou une creation manuelle erronee.

### 5. Wallet du lieu

Le wallet du lieu est cree par `FedowAPI.create_place()` (flow legacy).
L'UUID vient du serveur Fedow distant. Ce wallet est stocke dans
`FedowConfig.wallet`.

Le `fedow_core.Asset` pointe dessus via `wallet_origin` — c'est le meme
objet `AuthBillet.Wallet`.

**En dev/test** (`create_test_pos_data`, sans serveur Fedow) : si
`FedowConfig.wallet` est None, on cree un wallet local :

```python
wallet_du_lieu, _ = Wallet.objects.get_or_create(
    origin=tenant,
    defaults={"name": tenant.name},
)
```

**En prod** : le wallet existe deja via le flow legacy. Les Assets sont
crees par l'admin via l'interface Unfold.

### 6. Impact sur les fixtures

**`create_test_pos_data`** :

- Supprime la creation manuelle des Products de recharge
  (Recharge 10 EUR, Recharge 20 EUR, Cadeau 5 EUR, etc.)
- Cree les 3 `fedow_core.Asset` en debut de commande :
  - Asset TLF ("Monnaie locale", currency_code="EUR")
  - Asset TNF ("Cadeau", currency_code="CAD")
  - Asset TIM ("Temps", currency_code="TMP")
- Le signal post_save cree automatiquement les Products + Prices
  + les attache aux PV CASHLESS
- Le reste de la commande (PV, cartes primaires, lignes de demo) ne change pas

**`demo_data_v2`** : pas de changement (legacy etanche).

### 7. Comptabilite

Pas d'impact sur la ventilation comptable :

- La `CategorieProduct "Cashless"` reste la meme, avec son `compte_comptable`
- Le Product auto-cree y est rattache via `categorie_pos`
- Les `MappingMoyenDePaiement` ne changent pas (CA, CC, LE)
- Le paiement NFC cashless (LE) reste sans compte de tresorerie
  (l'encaissement a eu lieu a la recharge)
- Les recharges cadeau (RC) et temps (TM) sont gratuites
  (`PaymentMethod.FREE`), pas d'ecriture de tresorerie

### 8. Archivage

Quand `Asset.archive` passe a `True` :

- Le signal propage `Product.archive = True`
- Le Product disparait du POS (filtre dans `_construire_donnees_articles`)
- Les `LigneArticle`, `ProductSold`, `PriceSold`, `Transaction` restent
  intacts — l'historique de vente est preserve

Reversible : remettre `Asset.archive = False` reactive le Product.

---

## Perimetre

### Ce qui change

| Fichier | Modification |
|---------|-------------|
| `BaseBillet/models.py` | FK `Product.asset → fedow_core.Asset` (nullable) |
| `BaseBillet/migrations/` | 1 migration |
| `fedow_core/signals.py` | Nouveau — post_save Asset |
| `fedow_core/apps.py` | Enregistre le signal |
| `laboutik/views.py` | Refactor `_executer_recharges`, `_payer_par_nfc`, filtre `_construire_donnees_articles` |
| `laboutik/management/commands/create_test_pos_data.py` | Cree Assets au lieu de Products recharge |
| `tests/pytest/` | Nouveaux tests signal + adaptation tests existants |

### Ce qui ne change PAS

- `fedow_core/services.py` — TransactionService, WalletService inchanges
- `fedow_core/models.py` — Asset a deja `archive`, `active`, `category`
- `fedow_connect/`, `fedow_public/` — legacy etanche
- Ventilation comptable (`ventilation.py`, `csv_comptable.py`, `fec.py`)
- `demo_data_v2.py`
- Templates POS (multi-tarif + prix libre deja gere cote JS)

### Hors scope

- Pont legacy → V2 (sync AssetFedowPublic → fedow_core.Asset)
- Migration des soldes entre V1 et V2
- Creation d'Assets dans `create_tenant()` en prod
  (l'admin le fait via Unfold)
