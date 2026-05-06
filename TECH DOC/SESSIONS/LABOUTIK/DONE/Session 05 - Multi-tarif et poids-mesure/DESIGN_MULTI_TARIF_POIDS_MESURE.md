# Design : Refonte tarif-overlay multi-clic + vente au poids/mesure

**Date :** 2026-04-05
**Branche :** integration_laboutik
**Session :** 28 (dossier Session 05)

---

## 1. Probleme

### 1.1 Tarif-overlay actuel

L'overlay de selection de tarif (`tarif.js`) est plein ecran et se ferme apres chaque clic.
Impossible de commander 3 demis + 1 pinte du meme produit sans rouvrir l'overlay 4 fois.
Le panier est cache derriere l'overlay — le caissier ne voit pas ce qu'il a ajoute.

Le pense-bete existant (session 02, `99_pense_bete_futur.md`) note :
*"La modal JS qui apparait lors d'un multi prix sur laboutik doit etre clicable plusieurs fois."*

### 1.2 Vente au poids/mesure

Pas de mecanisme pour vendre des articles au poids (fromage, charcuterie) ou au volume
(vin en vrac, huile). Le caissier doit calculer le prix a la main et utiliser le prix libre,
ce qui ne trace ni la quantite pesee ni l'unite.

---

## 2. Solution

### 2.1 Refonte overlay multi-clic

```
┌──────────────────────────────────┬──────────────┐
│                                  │   PANIER     │
│  ┌────────────────────────────┐  │              │
│  │        Biere IPA           │  │  Demi    x3  │
│  │     Choisir un tarif       │  │  Pinte   x1  │
│  │                            │  │              │
│  │  ┌──────────┐ ┌─────────┐ │  │              │
│  │  │  Demi    │ │  Pinte  │ │  │              │
│  │  │  3,50 E  │ │  7,00 E │ │  │              │
│  │  └──────────┘ └─────────┘ │  │              │
│  │                            │  │  Total: 17,5E│
│  │         [ RETOUR ]         │  │              │
│  └────────────────────────────┘  │              │
└──────────────────────────────────┴──────────────┘
```

**Regles :**
- L'overlay couvre `#articles-zone` uniquement, le panier reste visible
- Clic tarif fixe = ajout immediat au panier, overlay reste ouvert
- Clic tarif prix libre = affiche l'input, validation, ajout, overlay reste ouvert
- Seul le bouton RETOUR ferme l'overlay
- Le panier se met a jour en temps reel a chaque clic

**Responsive mobile (V2s) :**
- L'overlay couvre la grille articles (pleine largeur)
- Le total reste visible en bas de l'ecran

### 2.2 Nouveau type : vente au poids/mesure

Nouveau `BooleanField poids_mesure` sur `Price`. Troisieme type de tarif a cote de
fixe et prix libre.

**Tuile article POS :**
```
┌──────────┐
│  Comte   │
│ 28E/kg   │
│   (balance)  │
└──────────┘
```
Icone balance (FontAwesome `fa-balance-scale`) + prix au kg ou au litre.

**Pavé numerique dans l'overlay :**

Desktop / tablette (V3 mix, D3mini) :
```
┌──────────────────────────────────┬──────────────┐
│                                  │   PANIER     │
│  ┌────────────────────────────┐  │              │
│  │        Comte AOP           │  │  Comte 350g  │
│  │      28,00 E / kg          │  │      9,80 E  │
│  │                            │  │              │
│  │  Poids :  [ 350 ] g        │  │              │
│  │  = 9,80 E                  │  │              │
│  │                            │  │              │
│  │  ┌─────┬─────┬─────┐      │  │              │
│  │  │  7  │  8  │  9  │      │  │              │
│  │  ├─────┼─────┼─────┤      │  │              │
│  │  │  4  │  5  │  6  │      │  │              │
│  │  ├─────┼─────┼─────┤      │  │              │
│  │  │  1  │  2  │  3  │      │  │              │
│  │  ├─────┼─────┼─────┤      │  │              │
│  │  │  C  │  0  │ OK  │      │  │              │
│  │  └─────┴─────┴─────┘      │  │  Total: 9,80E│
│  │                            │  │              │
│  │         [ RETOUR ]         │  │              │
│  └────────────────────────────┘  │              │
└──────────────────────────────────┴──────────────┘
```

Mobile (V2s) :
```
┌──────────────────────────┐
│      Comte AOP            │
│    28,00 E / kg            │
│                            │
│  Poids : [ 350 ] g        │
│  = 9,80 E                  │
│                            │
│  ┌──────┬──────┬──────┐    │
│  │  7   │  8   │  9   │    │
│  ├──────┼──────┼──────┤    │
│  │  4   │  5   │  6   │    │
│  ├──────┼──────┼──────┤    │
│  │  1   │  2   │  3   │    │
│  ├──────┼──────┼──────┤    │
│  │  C   │  0   │  OK  │    │
│  └──────┴──────┴──────┘    │
│                            │
│        [ RETOUR ]          │
├────────────────────────────┤
│  Total: 9,80 E             │
└────────────────────────────┘
```

**Flux :**
1. Clic sur tuile "Comte" → overlay avec pave numerique
2. Le caissier tape `350` (entiers uniquement, pas de virgule)
3. Le prix se calcule en temps reel : `350 / 1000 x 28,00 = 9,80 E`
4. Clic OK → ajout au panier avec `displayName = "Comte 350g"`, prix = 980 centimes
5. L'overlay reste ouvert, le champ se vide (pret pour la prochaine pesee)
6. `C` efface la saisie en cours
7. RETOUR ferme l'overlay

---

## 3. Modele et admin

### 3.1 Nouveau champ sur Price

```python
poids_mesure = models.BooleanField(
    default=False,
    verbose_name=_("Sale by weight/volume"),
    help_text=_("If checked, the cashier enters the weight or volume at each sale. "
                "The price is per kg or per liter."),
)
```

**Migration :** `BaseBillet/migrations/XXXX_price_poids_mesure.py` — 1 BooleanField.

### 3.2 Regles de validation (admin)

Validation dans `POSPriceInlineForm.clean()` :

| Regle | Condition | Message |
|-------|-----------|---------|
| Exclusion prix libre | `poids_mesure AND free_price` | "Un tarif ne peut pas etre a la fois prix libre et au poids/mesure" |
| Exclusion contenance | `poids_mesure AND contenance` | "La contenance est incompatible avec la vente au poids/mesure (la quantite est saisie a chaque vente)" |
| Unite stock invalide | `poids_mesure AND Stock.unite == UN` | "La vente au poids/mesure necessite un stock en grammes (GR) ou centilitres (CL), pas en pieces" |

### 3.3 Creation automatique du Stock

Si `poids_mesure=True` et le produit n'a pas de Stock :
- Creation automatique `Stock(product=product, quantite=0, unite=GR)`
- Message admin : "Stock cree automatiquement en grammes (quantite=0). Pensez a l'approvisionner."

L'unite par defaut est GR (grammes). Le gerant peut la changer en CL dans l'admin Stock.

### 3.4 Champs conditionnels dans POSPriceInline

Reutilise le mecanisme `inline_conditional_fields` construit en session 26 :

```python
class POSPriceInline(BasePriceInline):
    inline_conditional_fields = {
        "contenance": "poids_mesure == false",
    }
```

`contenance` est cache quand `poids_mesure` est coche (mutuellement exclusif).

### 3.5 Affichage dans POSPriceInline

Le champ `poids_mesure` est ajoute dans `POSPriceInline.fields` :

```python
fields = ("name", "prix", "poids_mesure", "contenance", ("publish", "order"))
```

---

## 4. Frontend POS

### 4.1 Donnees articles enrichies

Dans `_construire_donnees_articles()` (laboutik/views.py), enrichir chaque tarif :

```python
{
    "price_uuid": str(p.uuid),
    "name": p.name,
    "prix_centimes": int(round(p.prix * 100)),
    "free_price": p.free_price,
    "poids_mesure": p.poids_mesure,          # NOUVEAU
    "unite_stock": stock_unite or None,       # NOUVEAU : "g" ou "cl"
    "prix_reference": prix_reference or None, # NOUVEAU : "E/kg" ou "E/L"
}
```

L'unite d'affichage est deduite de `Stock.unite` :
- `GR` → saisie en `g`, prix reference `E/kg`, diviseur = 1000
- `CL` → saisie en `cl`, prix reference `E/L`, diviseur = 100

### 4.2 Tuile article

Dans `cotton/articles.html`, si le produit a au moins un tarif `poids_mesure=True` :
- Afficher le prix avec `/kg` ou `/L` au lieu du prix brut
- Ajouter l'icone balance (`fa-balance-scale`)

### 4.3 Overlay refactore (tarif.js)

**3 types de boutons dans l'overlay :**

1. **Tarif fixe** (existant) : clic = ajout immediat
2. **Prix libre** (existant) : input montant + validation minimum
3. **Poids/mesure** (NOUVEAU) : pave numerique + calcul prix temps reel

**Injection dans `#articles-zone`** au lieu de `#messages` :
- Le panier (`#addition`) reste visible
- L'overlay utilise `position: absolute` sur `#articles-zone` (pas `fixed` sur tout l'ecran)

**Multi-clic :**
- L'overlay ne se ferme plus apres un ajout
- Seul RETOUR ferme l'overlay

### 4.4 Pave numerique

- Saisie en entiers uniquement (pas de virgule) — les unites sont GR et CL
- Calcul prix en temps reel : `quantite_saisie / diviseur x prix_unitaire`
- Diviseur : 1000 pour GR (grammes → kg), 100 pour CL (centilitres → litre)
- `C` efface la saisie
- `OK` valide et ajoute au panier (si quantite > 0)
- Apres OK le champ se vide, pret pour la prochaine pesee

### 4.5 Format du panier (formulaire HTML)

Nouveau format pour les ventes au poids/mesure :
```html
<!-- Article au poids : 350g de Comte a 9,80E -->
<input type="number" name="repid-<product_uuid>--<price_uuid>" value="1" />
<input type="hidden" name="custom-<product_uuid>--<price_uuid>" value="980" />
<input type="hidden" name="weight-<product_uuid>--<price_uuid>" value="350" />
```

Le backend `_extraire_articles_du_panier()` parse `weight-*` en plus de `custom-*` et `repid-*`.

### 4.6 Donnees transmises au panier (event JS)

```javascript
{
    uuid: productUuid,
    priceUuid: priceUuid,
    price: 980,              // prix calcule en centimes
    quantity: 1,             // toujours 1 (chaque pesee = 1 ligne)
    name: "Comte 350g",      // nom avec quantite
    currency: "E",
    customAmount: 980,        // prix calcule
    weightAmount: 350,        // NOUVEAU : quantite saisie en unite stock
    weightUnit: "g"           // NOUVEAU : unite pour affichage
}
```

---

## 5. Backend vente et comptabilite

### 5.1 Nouveau champ sur LigneArticle

```python
weight_quantity = models.IntegerField(
    null=True, blank=True,
    verbose_name=_("Quantity by weight/volume"),
    help_text=_("Amount entered by cashier in stock unit (g or cl). "
                "Null for standard sales."),
)
```

**Migration :** dans la meme migration que `Price.poids_mesure`.

### 5.2 Decrementation stock

Dans `_creer_lignes_articles()`, adaptation de l'appel a `StockService.decrementer_pour_vente()` :

```python
if weight_quantity:
    # Poids/mesure : la quantite saisie par le caissier remplace contenance x qty
    StockService.decrementer_pour_vente(
        stock=stock_du_produit,
        contenance=weight_quantity,  # ex: 350 (grammes)
        qty=1,
        ligne_article=ligne,
    )
else:
    # Tarif classique : contenance fixe x quantite
    StockService.decrementer_pour_vente(
        stock=stock_du_produit,
        contenance=prix_obj.contenance,
        qty=quantite,
        ligne_article=ligne,
    )
```

### 5.3 HMAC — conformite LNE exigence 8

Le referentiel LNE v1.7 (Exigence 3, page 30) exige l'enregistrement de
*"toute autre donnee elementaire necessaire au calcul du total HT de la ligne"*.
`weight_quantity` est une donnee elementaire : sans elle, on ne peut pas retrouver
`350g x 28E/kg = 9,80E`.

L'Exigence 8 (page 36) exige que le mecanisme d'inalterabilite couvre
*"toutes les donnees d'encaissement definies a l'exigence 3"*.

**Ajout de `weight_quantity` dans `calculer_hmac()`** (`laboutik/integrity.py`) :

```python
donnees = json.dumps([
    str(ligne.uuid),
    str(ligne.datetime.isoformat()) if ligne.datetime else '',
    ligne.amount,
    ligne.total_ht,
    f"{float(ligne.qty):.6f}",
    f"{float(ligne.vat):.2f}",
    ligne.payment_method or '',
    ligne.status or '',
    ligne.sale_origin or '',
    str(ligne.weight_quantity) if ligne.weight_quantity is not None else '',  # NOUVEAU
    previous_hmac,
])
```

Les anciennes lignes ont `weight_quantity=None` → `''` dans le hash.
Cela ne casse pas la chaine existante car `calculer_hmac()` n'est appele
qu'au moment de la creation de la ligne (pas de recalcul retroactif).

**ATTENTION : ce changement rend les HMAC de la nouvelle version incompatibles avec
l'ancienne version de `calculer_hmac()`.** Il faut documenter ce changement de version
dans la documentation LNE et incrementer la version du perimetre fiscal (Exigence 20).

### 5.4 Rapports comptables

| Rapport | Impact |
|---------|--------|
| `calculer_detail_ventes()` | `qty_vendus` reste correct (somme des `qty=1`). Ajout optionnel `poids_total` par produit (sum de `weight_quantity` groupe par produit) pour les articles au poids. |
| `calculer_totaux_par_moyen()` | Aucun impact (somme des `amount`) |
| Ticket imprime | La ligne affiche "Comte 350g — 9,80E" au lieu de "Comte x1 — 9,80E" |
| FEC / CSV comptable | Aucun impact (1 ecriture par cloture) |
| Ticket X (recap en cours) | Aucun impact (somme des `amount`) |

### 5.5 Ticket imprime

Pour les lignes avec `weight_quantity` :
```
Comte AOP                    9,80 E
  350g x 28,00E/kg
```
Au lieu de :
```
Comte AOP              x1   9,80 E
```

---

## 6. Metrologie legale — note

La saisie manuelle du poids dans un logiciel de caisse n'est pas interdite en France.
La reglementation metrologique (Decret 2001-387) porte sur les **instruments de pesage**
(balances), pas sur les logiciels de caisse. Le logiciel ne se substitue pas a un
instrument de mesure — le caissier lit le poids sur une balance homologuee et le saisit
manuellement.

**Documentation utilisateur a inclure :**
- La balance utilisee doit etre homologuee IPFNA et verifiee tous les 2 ans (COFRAC)
- Le logiciel ne remplace pas un instrument de mesure legal
- La precision du prix depend de la precision de la balance et de la saisie du caissier

---

## 7. Fichiers impactes

### Modeles et migrations

| Fichier | Action |
|---------|--------|
| `BaseBillet/models.py` | Ajout `Price.poids_mesure` BooleanField |
| `laboutik/models.py` | Ajout `LigneArticle.weight_quantity` IntegerField nullable |
| `BaseBillet/migrations/XXXX_*.py` | 1 migration (2 champs) |

### Admin

| Fichier | Action |
|---------|--------|
| `Administration/admin/products.py` | `poids_mesure` dans `POSPriceInline.fields`, `inline_conditional_fields`, validation `clean()` sur `POSPriceInlineForm` |

### Frontend POS

| Fichier | Action |
|---------|--------|
| `laboutik/static/js/tarif.js` | Refonte : injection `#articles-zone`, multi-clic, pave numerique, donnees `weightAmount`/`weightUnit` |
| `laboutik/static/css/tarif.css` | Nouveau : styles overlay (`#articles-zone`), pave numerique, responsive V2s |
| `laboutik/static/js/addition.js` | Gerer `weightAmount`/`weightUnit` dans les inputs hidden `weight-*` |
| `laboutik/templates/cotton/articles.html` | Tuile : affichage "28E/kg" + icone balance si `poids_mesure` |

### Backend

| Fichier | Action |
|---------|--------|
| `laboutik/views.py` | Enrichir dict article (`poids_mesure`, `unite_stock`, `prix_reference`). Parser `weight-*` dans `_extraire_articles_du_panier()`. Adapter decrementation stock dans `_creer_lignes_articles()` |
| `laboutik/integrity.py` | Ajout `weight_quantity` dans `calculer_hmac()` |
| `laboutik/reports.py` | Ajout optionnel `poids_total` dans `calculer_detail_ventes()` |
| `laboutik/printing/formatters.py` | Format ticket "350g x 28,00E/kg" pour les ventes au poids |
| `laboutik/serializers.py` | Parser `weight_amount` dans les donnees du panier |

### Ce qui ne change PAS

- `free_price` et tout son code existant (billetterie, adhesions, POS)
- `Price.contenance` (reste pour les tarifs POS classiques : pinte=50cl)
- `PriceAdmin` standalone (prices.py)
- `TicketPriceInline`, `MembershipPriceInline`, `BasePriceInline`
- Le modele Stock (pas de nouveau champ)
- Le JS `inline_conditional_fields.js` (deja generique)
- Les unites de stock (UN, CL, GR) — pas de KG/L pour l'instant

---

## 8. Tests

### pytest

- Validation admin : `poids_mesure + free_price` → erreur
- Validation admin : `poids_mesure + contenance` → erreur
- Validation admin : `poids_mesure + Stock.unite=UN` → erreur
- Creation auto Stock quand `poids_mesure=True` sans Stock existant
- Calcul prix poids/mesure : 350g x 28E/kg = 980 centimes
- Calcul prix poids/mesure : 25cl x 12E/L = 300 centimes
- Decrementation stock avec `weight_quantity` (350g decrmente 350 du stock GR)
- HMAC inclut `weight_quantity` (verification chaine)
- `weight_quantity=None` dans le HMAC → meme resultat que avant (retrocompatibilite)
- Rapport detail ventes avec `poids_total` pour les articles au poids

### E2E Playwright

- Overlay multi-clic : 3 demis + 1 pinte du meme produit sans fermer l'overlay
- Overlay prix libre : saisie montant, overlay reste ouvert
- Overlay poids/mesure : saisie pave → calcul prix → ajout panier
- Panier visible pendant l'overlay (non couvert)
- Responsive mobile : overlay sur `#articles-zone`, total visible en bas
- Pave numerique : touche C efface, OK valide, champ se vide apres OK

---

## 9. Contraintes

- **1 migration** pour les 2 nouveaux champs (Price.poids_mesure + LigneArticle.weight_quantity)
- **Retrocompatible** : les anciennes lignes ont `weight_quantity=None`, le HMAC produit `''` pour ce champ
- **Incrementer la version du perimetre fiscal** (Exigence 20 LNE) car `calculer_hmac()` change
- **Pas de KG/L** : saisie en sous-unites (GR/CL) uniquement. A ajouter si reclame par les utilisateurs
- **Entiers uniquement** dans le pave numerique (pas de virgule)
- **Balance homologuee requise** — le logiciel ne fait pas de metrologie
