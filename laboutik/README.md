# LaBoutik — Caisse enregistreuse tactile

Application de caisse enregistreuse (POS) pour terminaux tactiles, integree dans l'ecosysteme TiBillet/Lespass.

Interface full-screen pensee pour tablettes et ecrans tactiles, avec lecture NFC pour les cartes cashless.

## Statut actuel

**Backend ORM complet.** Les donnees (articles, points de vente, cartes, paiements) viennent de la base PostgreSQL via les modeles Django. Les fichiers mock dans `utils/` sont encore presents mais ne sont plus utilises par les vues principales.

**Phases terminees :** modeles POS, paiements especes/CB/NFC, recharges, commandes restaurant, cloture caisse, POS Adhesion multi-tarif.

## Architecture

### Stack technique

| Couche | Techno |
|--------|--------|
| Backend | Django 4.2 + DRF ViewSets (pattern FALC) |
| Frontend | HTMX 2.0.6 + django-cotton (composants `<c-xxx>`) |
| CSS | CSS custom properties (palette, sizes) — pas de framework CSS |
| JS | Vanilla JS, pas de bundler. Event bus custom (`tibilletUtils.js`) |
| Icones | FontAwesome 5 |
| NFC | Web NFC API + simulation en mode demo |

### Modeles

| Modele | App | Role |
|--------|-----|------|
| `PointDeVente` | laboutik | Point de vente physique ou virtuel |
| `CartePrimaire` | laboutik | Carte NFC du caissier (acces aux PV) |
| `Table` + `CategorieTable` | laboutik | Tables restaurant (mode commande) |
| `CommandeSauvegarde` + `ArticleCommandeSauvegarde` | laboutik | Commandes restaurant persistees |
| `ClotureCaisse` | laboutik | Rapport de cloture (totaux, JSON detail) |
| `Product` | BaseBillet | Catalogue produits (unifie POS + billetterie + adhesion) |
| `Price` | BaseBillet | Tarifs (EUR ou tokens, prix libre, abonnement) |
| `CategorieProduct` | BaseBillet | Categories produits (couleurs, icones POS) |
| `Membership` | BaseBillet | Fiches adherent (deadline, statut, contribution) |

### Types de points de vente

Le champ `PointDeVente.comportement` determine le mode d'interface (pas le contenu) :

| Type | Code | Comportement |
|------|------|-------------|
| **Direct** | `D` | Vente au comptoir classique (grille + panier + footer) |
| **Avance** | `V` | Mode commande restaurant (tables, preparations) — reserve, pas code |

Le **quoi** (ventes, adhesions, billets, recharges) est determine par les articles
dans le M2M `products` du PV. Un PV peut contenir tous les types d'articles.

> **Historique** : les anciens types ADHESION ('A'), CASHLESS ('C') et KIOSK ('K')
> ont ete supprimes. La logique est pilotee par l'article (`methode_caisse`), pas le PV.
> KIOSK sera une app Django separee dans le futur.

---

## Adhesions au POS — multi-tarif et prix libre

### Principe

Les produits adhesion existent deja dans `BaseBillet.Product` (avec `categorie_article=ADHESION`).
Ils ont des tarifs (`Price`) avec duree d'abonnement, prix libre, etc.

Le POS de type ADHESION les affiche tels quels. Pas de duplication de produits.
Pas de `methode_caisse` necessaire — c'est le type du PV qui determine le contenu.

### Donnees de test

La commande `create_test_pos_data` cree :

- **Adhesion annuelle** : 3 tarifs (Plein tarif 15 EUR, Tarif reduit 8 EUR, Prix libre min 5 EUR)
- **Adhesion mensuelle** : 1 tarif (Tarif unique 5 EUR)
- **PV "Adhesions"** : type `ADHESION`, accepte especes et CB

### Multi-tarif : overlay de selection

Quand un produit a **plusieurs tarifs** ou un **prix libre**, le clic sur l'article
ouvre un overlay plein ecran au lieu d'ajouter directement au panier.

```
┌──────────────────────────────────────────┐
│         Adhesion annuelle                │
│         Choisir un tarif                 │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  Plein tarif                      │  │
│  │  15,00 EUR                        │  │
│  └────────────────────────────────────┘  │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  Tarif reduit                     │  │
│  │  8,00 EUR                         │  │
│  └────────────────────────────────────┘  │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  Prix libre (min 5,00 EUR)        │  │
│  │  ┌──────────┐  EUR  [OK]          │  │
│  │  │  ______  │                     │  │
│  │  └──────────┘                     │  │
│  └────────────────────────────────────┘  │
│                                          │
│            [ <- RETOUR ]                 │
└──────────────────────────────────────────┘
```

**Comportement :**

- **Tarif fixe** : un clic ajoute l'article au panier avec ce prix et ferme l'overlay.
- **Prix libre** : un champ input apparait. Le caissier entre le montant. Le bouton OK valide que le montant est >= au minimum. Puis l'article est ajoute au panier avec le montant saisi.
- **Produit avec 1 seul tarif fixe** : pas d'overlay. Ajout direct au panier (meme comportement qu'un article de vente classique).

### Format du panier (formulaire HTML)

Le panier est un formulaire HTML cache (`#addition-form`). Chaque article ajoute des inputs :

**Articles classiques (mono-tarif) :**
```html
<input type="number" name="repid-<product_uuid>" value="2" />
```

**Articles multi-tarif (adhesion avec tarif choisi) :**
```html
<!-- Le separateur '--' distingue le product_uuid du price_uuid -->
<input type="number" name="repid-<product_uuid>--<price_uuid>" value="1" />
```

**Articles prix libre (montant custom) :**
```html
<input type="number" name="repid-<product_uuid>--<price_uuid>" value="1" />
<!-- Montant en centimes choisi par le caissier -->
<input type="hidden" name="custom-<product_uuid>--<price_uuid>" value="2500" />
```

Le backend (`PanierSerializer.extraire_articles_du_post()`) parse les deux formats :
- `repid-<uuid>` → ancien format, `price_uuid=None`, premier prix EUR
- `repid-<uuid>--<price_uuid>` → nouveau format, charge le `Price` specifique
- `custom-<uuid>--<price_uuid>` → montant libre en centimes

### Identification client pour les adhesions

Quand le panier contient des adhesions, l'ecran de paiement affiche deux options :

```
┌──────────────────────────────────────────┐
│     Adhesion — Identifier le client      │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  SCANNER CARTE NFC                │  │
│  └────────────────────────────────────┘  │
│                                          │
│  — ou —                                  │
│                                          │
│  Email :    [___________________]        │
│  Prenom :   [___________]                │
│  Nom :      [___________]                │
│                                          │
│  [ ESPECE ]  [ CB ]  [ CHEQUE ]          │
└──────────────────────────────────────────┘
```

**Option 1 — Scan NFC** : identifie le client via `CarteCashless.user`. Meme flux que les recharges.

**Option 2 — Formulaire email** : le caissier saisit l'email du client (obligatoire) et
son nom/prenom (optionnel). Le backend appelle `get_or_create_user(email)` pour creer
ou retrouver le `TibilletUser`. Puis `_creer_ou_renouveler_adhesion()` cree ou renouvelle
la `Membership` avec le `Price` choisi et le montant paye.

**Si aucune identification** : les `LigneArticle` sont creees (comptabilite), mais pas de `Membership`.
L'adhesion pourra etre rattachee plus tard.

### Flux technique complet (adhesion CB avec email)

```
1. Caissier ouvre le PV "Adhesions"
   → _construire_donnees_articles() charge dynamiquement les Product(categorie_article=ADHESION)
   → Inclut tous les Price EUR dans les data-attributes de chaque tuile

2. Clic sur "Adhesion annuelle" (3 tarifs)
   → articles.js:manageKey() detecte data-multi-tarif="true"
   → Emet 'tarifSelection' au lieu d'appeler addArticle()

3. tibilletUtils.js route vers tarif.js:tarifSelection()
   → Genere l'overlay HTML dans #messages (cote client, pas d'aller-retour serveur)

4. Clic sur "Plein tarif — 15,00 EUR"
   → tarif.js:tarifSelectFixed() ferme l'overlay
   → Appelle addArticleWithPrice(productUuid, priceUuid, 1500, ...)
   → Emet 'articlesAdd' avec priceUuid et prixCentimes

5. addition.js:additionInsertArticle() recoit l'evenement
   → Cree input "repid-<product_uuid>--<price_uuid>" value="1"
   → Affiche la ligne dans le panier avec le nom "Adhesion annuelle (Plein tarif)"

6. Clic VALIDER
   → POST /paiement/moyens_paiement/
   → moyens_paiement() detecte panier_a_adhesions=True
   → Retourne hx_display_type_payment.html en mode adhesion (scan NFC + formulaire email)

7. Caissier saisit email + nom + prenom, clique CB
   → adhesionCopyFieldsToForm() copie les champs dans #addition-form (inputs caches)
   → hx-get /paiement/confirmer/?method=carte_bancaire

8. Clic VALIDER sur la confirmation
   → POST /paiement/payer/ avec les inputs repid-*, custom-*, email_adhesion, etc.
   → _payer_par_carte_ou_cheque() :
     a. _creer_lignes_articles() → ProductSold + PriceSold + LigneArticle
     b. _creer_adhesions_depuis_panier() :
        - Lit email_adhesion → get_or_create_user(email)
        - _creer_ou_renouveler_adhesion(user, product, price, contribution_value)
        - Membership creee avec status=LABOUTIK, deadline calculee

9. Ecran succes → RETOUR → interface POS
```

### Flux prix libre (variante de l'etape 4)

```
4b. Clic sur "Prix libre (min 5,00 EUR)"
    → L'overlay affiche un input numerique + bouton OK
    → Caissier saisit "25" (= 25 EUR)
    → tarif.js:tarifValidateFreePrix() verifie 25 >= 5
    → Appelle addArticleWithPrice(..., customAmount=2500)
    → addition.js cree DEUX inputs :
      - "repid-<product>--<price>" value="1"
      - "custom-<product>--<price>" value="2500"
    → Le total du panier utilise 2500 centimes (pas le prix de base)

Au paiement :
    → _extraire_articles_du_panier() lit custom-* → prix_centimes=2500
    → PriceSold cree avec prix=25.00 EUR
    → Membership.contribution_value = 25.00
```

---

## Flux HTMX — layers superposes

L'interface fonctionne en layers superposes :

```
Layer 0 : Interface principale (articles, categories, addition)
Layer 1 : #messages — types de paiement, verification carte, selection tarif
Layer 2 : #confirm  — confirmation paiement, lecture NFC
```

### Flux de paiement standard (especes)

```
[Articles] → clic VALIDER → trigger "validerPaiement"
    ↓
hx-post /paiement/moyens_paiement/ → swap #messages (layer 1)
    ↓
clic ESPECE → hx-get /paiement/confirmer/?method=espece → swap #confirm (layer 2)
    ↓
clic VALIDER → JS postUrl → hx-post /paiement/payer/ → swap #messages (layer 1)
    ↓
Paiement reussi → bouton RETOUR → manageReset() → retour layer 0
```

### Flux cashless (NFC)

```
clic CASHLESS → hx-get /paiement/lire_nfc/ → swap #confirm (layer 2)
    ↓
Composant <c-read-nfc> demarre NfcReader
    ↓
Lecture carte → JS injecte tag_id dans le formulaire addition
    ↓
Submit → hx-post /paiement/payer/ avec moyen_paiement=nfc + tag_id
    ↓
Si fonds insuffisants → partial hx_funds_insufficient (paiement fractionne)
```

---

## Communication JS — Event Bus

Les fichiers JS communiquent via un systeme d'evenements personnalises
route par `tibilletUtils.js`.

### Table de routage (`switches`)

```javascript
const switches = {
    articlesAdd:               → additionInsertArticle sur #addition
    additionTotalChange:       → updateBtValider sur #bt-valider
    additionRemoveArticle:     → articlesRemove sur #products
    resetArticles:             → additionReset + articlesReset
    articlesDisplayCategory:   → articlesDisplayCategory sur #products
    additionDisplayPaymentTypes: → additionDisplayPaymentTypes sur #addition
    additionManageForm:        → additionManageForm sur #addition
    tarifSelection:            → tarifSelection sur #messages
}
```

### Flux d'un evenement

```
1. articles.js:addArticle() envoie { msg: 'articlesAdd', data: { uuid, price... } }
2. eventsOrganizer() recoit et consulte switches['articlesAdd']
3. sendEvent('additionInsertArticle', '#addition', data)
4. addition.js:additionInsertArticle() est execute
```

### Fichiers JS

| Fichier | Role |
|---------|------|
| `tibilletUtils.js` | Event bus central (sendEvent, switches, eventsOrganizer) |
| `articles.js` | Grille d'articles (clic, quantite, groupes, categories) |
| `addition.js` | Panier (ajout, suppression, total, formulaire HTMX) |
| `tarif.js` | Overlay selection tarif + prix libre (multi-tarif adhesion) |
| `nfc.js` | Classe NfcReader (Web NFC + simulation demo) |

---

## Arborescence des fichiers

```
laboutik/
├── models.py                        # 6 modeles POS (PointDeVente, CartePrimaire, Table, etc.)
├── views.py                         # 3 ViewSets DRF (Caisse, Paiement, Commande)
├── serializers.py                   # 7 serializers DRF (validation POST, extraction panier)
├── urls.py                          # DRF router
├── tasks.py                         # Tache Celery (envoi rapport cloture par email)
├── pdf.py                           # Generation PDF cloture (WeasyPrint)
├── csv_export.py                    # Generation CSV cloture
├── management/commands/
│   └── create_test_pos_data.py      # Donnees de test (categories, produits, PV, cartes)
├── templates/
│   ├── cotton/                      # Composants django-cotton (reutilisables)
│   │   ├── articles.html            # Grille d'articles + styles + chargement JS
│   │   ├── addition.html            # Panier + formulaire HTMX cache
│   │   ├── categories.html          # Barre laterale categories
│   │   ├── header.html              # Header avec menu burger
│   │   └── bt/paiement.html         # Bouton moyen de paiement
│   └── laboutik/
│       ├── base.html                # Layout HTML (HTMX, FontAwesome, NFC, state JSON)
│       ├── views/
│       │   ├── common_user_interface.html  # Interface POS principale
│       │   └── tables.html                # Selection de table
│       └── partial/                 # Fragments HTMX
│           ├── hx_display_type_payment.html  # Choix paiement (normal/recharge/adhesion)
│           ├── hx_confirm_payment.html       # Confirmation paiement
│           └── hx_return_payment_success.html # Succes
├── static/js/
│   ├── tibilletUtils.js             # Event bus central
│   ├── articles.js                  # Grille articles (clic, groupes)
│   ├── addition.js                  # Panier (ajout, suppression, total)
│   ├── tarif.js                     # Overlay selection tarif + prix libre
│   └── nfc.js                       # Lecture NFC
└── doc/
    ├── PLAN_INTEGRATION.md          # Plan de fusion mono-repo (toutes les phases)
    └── UX/PLAN_UX_LABOUTIK.md       # Plan UX (5 sessions, toutes terminees)
```

---

## Commandes utiles

```bash
# Acceder a la caisse (navigateur, admin connecte)
https://lespass.tibillet.localhost/laboutik/caisse/

# Creer les donnees de test POS
docker exec lespass_django poetry run python manage.py create_test_pos_data

# Lancer les tests POS
docker exec lespass_django poetry run pytest tests/pytest/test_pos_models.py -v

# Lancer tous les tests
docker exec lespass_django poetry run pytest tests/pytest/ -x --tb=short
```
