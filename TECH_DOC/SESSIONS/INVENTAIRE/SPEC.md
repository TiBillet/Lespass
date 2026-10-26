# Chantier 01 — Désactiver le suivi de stock d'un produit

**Date :** 2026-10-23
**Statut :** **codé le 2026-10-24, non commité** (migration appliquée en dev). D10 validée
par le mainteneur le 2026-10-24. CHANGELOG : `CHANGELOG/2026-10-24-stock-desactivation.md`.
**Migration :** Oui — `inventaire/migrations/0003_stock_actif.py` (`AddField`, `default=True`).
Interaction avec le chantier 02 : un stock inactif n'a pas de badge, quel que soit
`afficher_en_caisse` (voir `CHANTIER-02-afficher-en-caisse.md`, D6).

---

## 1. Le besoin

Un gestionnaire active « Suivre le stock » sur un produit de caisse ou un fût.
Ensuite, il ne peut plus revenir en arrière : aucun écran ne permet d'arrêter le suivi.

On veut pouvoir **désactiver** le suivi, puis le **reprendre** plus tard.

## 2. Ce qui existe aujourd'hui

- Suivre le stock = une ligne `inventaire.Stock` liée au produit
  (`OneToOneField`, `related_name="stock_inventaire"`, `inventaire/models.py:48`).
- Le code teste l'existence de cette ligne pour savoir si le stock est suivi
  (`try: produit.stock_inventaire / except Stock.DoesNotExist`, ou `hasattr`).
- La section Stock de la fiche produit (`Administration/admin/stock_fiche_produit.py`)
  n'affiche la case « Suivre le stock » que si le produit n'a **pas** de stock.
  Une fois le stock créé, elle affiche les réglages et le **panneau d'opérations** HTMX
  (`stock_actions.html` → `stock_actions_partial.html`, POST vers `stock_action_view`).
  Ce même panneau est affiché sur la fiche `StockAdmin`.
- `StockAdmin.has_delete_permission` renvoie `False` (`Administration/admin/inventaire.py:318`).
- **Supprimer le stock n'est pas une option** : `MouvementStock.stock` est en
  `on_delete=CASCADE`. Supprimer le stock efface tout son journal.
  C'est la raison du blocage actuel (`A TESTER et DOCUMENTER/stock-onglet-produit.md:59`).
- Un **fût**, ou un produit de caisse avec un tarif **au poids**, reçoit un stock
  automatiquement dans `save_related` (`Administration/admin/products.py:2082-2119` et
  `:2538-2592`), même si « Suivre le stock » n'était pas coché. Ce stock sert surtout à
  porter l'unité (g / cl). Il est aujourd'hui créé **suivi**.

## 3. Décisions

| # | Décision | Raison |
|---|---|---|
| D1 | Désactiver = `Stock.actif = False`. La ligne `Stock` n'est **jamais** supprimée. | Le journal des mouvements est conservé. |
| D2 | Un stock inactif **garde son unité**. Les lecteurs d'unité (§ 6) ne changent pas. | L'unité d'une vente au poids ou au volume (kg / L) vient de `Stock.unite`. Tickets, rapports et compta la lisent. |
| D3 | Un stock inactif se comporte **exactement comme un produit sans stock** pour le décompte : pas de badge, pas de blocage, pas de mouvement, pas d'alerte. | Une seule règle à retenir. |
| D4 | Désactiver ne crée **pas** de mouvement. La quantité reste figée en base. | Rien ne sort ni n'entre. Aucun type de mouvement ne correspond. |
| D5 | **Reprendre le suivi demande la quantité réellement comptée** (obligatoire, 0 accepté). Elle est enregistrée comme un ajustement `AJ`, motif « Reprise du suivi », via `StockService.ajuster_inventaire`. | Pendant la désactivation, les ventes n'ont pas été décomptées : l'ancienne quantité est fausse. L'ajustement est tracé. Le récap quotidien ignore déjà les `AJ` pour les ruptures (`Administration/recap_quotidien.py:287`). |
| D6 | **La bascule se fait dans le panneau d'opérations HTMX**, pas dans le formulaire du produit. Stock suivi : un bouton « Désactiver le suivi » à côté des 4 opérations. Stock inactif : le panneau n'affiche qu'un message et un formulaire « Reprendre le suivi » (quantité comptée obligatoire). | Le formulaire principal reste à deux états, comme aujourd'hui. Pas de case à rendre dans tous les cas, pas de piège `BooleanField` (non rendu = `False`), pas de `clean()` (que `POSProductForm.clean` et `FutProductForm.clean` sauteraient : ils appellent `super(ProductAdminCustomForm, self).clean()`). Le même panneau sert la fiche produit et la fiche `StockAdmin` : D5 s'applique partout. |
| D7 | Sur un stock inactif, **toutes les opérations manuelles sont refusées** (réception, perte, offert, ajustement, débitmètre, API, panel caisse). | Ajouter des mouvements à un stock non suivi n'a pas de sens. La reprise passe par D5. |
| D8 | Un **fût branché** peut être désactivé. Il se comporte comme un fût sans stock (cf. § 7.2). | Comportement déjà géré par controlvanne. |
| D9 | Désactiver ou reprendre **prévient les caisses ouvertes** par WebSocket : le badge apparaît ou disparaît sans recharger. | Même règle que les autres changements de stock hors vente. |
| D10 | **(validée 2026-10-24)** Le stock créé automatiquement par `save_related` (fût, tarif au poids) est créé **inactif**. | Sinon, décocher « Suivre le stock » sur un fût neuf donne quand même un stock suivi : le flux principal du chantier contredirait D3. `save_related` passe après `save_model` : si la case était cochée, `enregistrer_section_stock` a déjà créé le stock suivi et `save_related` ne fait rien. **Changement de comportement** assumé : un produit au poids garde son unité (kg / L) mais n'est plus décompté d'office. Les stocks déjà créés restent suivis (`default=True`). |

**Alternative écartée** : porter la bascule par la case « Suivre le stock » du formulaire
produit (trois états). Écartée après relecture : le `clean()` du mixin ne serait jamais
appelé (MRO de `POSProductForm` / `FutProductForm`), une case non rendue désactiverait le
stock à chaque enregistrement, et deux tests existants cassaient
(`test_stock_fiche_produit.py` test_05, `test_admin_stock_fiche_produit.py:172-179`).

## 4. Modèle

`inventaire/models.py`, classe `Stock` :

```python
# Suivi du stock actif. Faux = le produit se comporte comme un produit sans stock :
# pas de décompte, pas de badge, pas de blocage. La ligne est gardée pour son
# journal (MouvementStock en CASCADE) et pour son unité (ventes au poids/volume).
# / Stock tracking on. False = behaves like a product without stock; the row is
# kept for its movement log and its unit.
actif = models.BooleanField(
    default=True,
    verbose_name=_("Suivi actif"),
    help_text=_("Décoché : le stock n'est plus compté, mais son journal est conservé"),
)
```

Migration `inventaire/migrations/0002_stock_actif.py` : un seul `AddField`.
`default=True` : tous les stocks existants restent suivis, aucune reprise de données.
`inventaire` est une TENANT_APP (`settings.py:297`) : migration sur tous les schémas.

## 5. Fonction commune et service

### 5.1 `stock_suivi_du_produit_ou_none` (`inventaire/models.py`, après `Stock`)

```python
def stock_suivi_du_produit_ou_none(produit):
    """
    Renvoie le Stock du produit s'il est suivi (actif), sinon None.
    / Returns the product's Stock if tracked (active), else None.

    LOCALISATION : inventaire/models.py

    À utiliser partout où l'on DÉCOMPTE, BLOQUE ou AFFICHE le stock.
    Ne pas l'utiliser pour lire l'UNITÉ d'une vente au poids : un stock
    inactif garde son unité (voir TECH_DOC/SESSIONS/INVENTAIRE/SPEC.md, D2).
    """
    try:
        stock_du_produit = produit.stock_inventaire
    except Stock.DoesNotExist:
        return None
    if not stock_du_produit.actif:
        return None
    return stock_du_produit
```

`Administration/admin/stock_fiche_produit.py:stock_du_produit_ou_none` **reste** : l'admin a
besoin du stock même inactif (panneau de reprise, unité).

### 5.2 Deux méthodes dans `StockService` (`inventaire/services.py`)

```python
@staticmethod
def desactiver_suivi(stock):
    # actif=False, update_fields=["actif"]. Aucun mouvement (D4).
    # Prévient les caisses (_prevenir_les_caisses_apres_commit) : le badge disparaît.

@staticmethod
def reprendre_suivi(stock, quantite_comptee, utilisateur=None):
    # actif=True, update_fields=["actif"], puis
    # ajuster_inventaire(stock, stock_reel=quantite_comptee,
    #                    motif=gettext("Reprise du suivi"), utilisateur=utilisateur).
    # ajuster_inventaire prévient déjà les caisses : pas de second broadcast.
    # Dans un transaction.atomic() : le broadcast on_commit relit un stock actif à jour.
```

## 6. Endroits à NE PAS modifier — lecteurs d'unité

Ils lisent `stock_inventaire` ou `stock_inventaire__unite` pour savoir si une vente au poids
est en kg ou en L. Un stock inactif doit continuer à répondre (D2).

| Fichier:ligne | Rôle |
|---|---|
| `laboutik/views.py:6331` | diviseur du prix au poids (1000 ou 100) |
| `laboutik/views.py:5387` | `select_related` pour l'affichage des ventes |
| `laboutik/reports.py:377` | unité des poids totaux du rapport |
| `laboutik/printing/formatters.py:199` | ticket client |
| `laboutik/affichage_des_ventes.py:447` | ligne en vrac dans le détail d'une vente |
| `comptabilite/rapport.py:402, 1614, 2174` | unité dans les rapports comptables |
| `Administration/admin_tenant.py:2431, 2912` | unité d'une ligne dans l'admin des ventes |
| `Administration/recap_quotidien.py:279` | lit les mouvements ; un stock inactif n'en produit plus |
| `laboutik/views.py:707, 6505`, `Administration/admin/products.py:2212, 2657` | `select_related` seulement |

## 7. Endroits à modifier

### 7.1 Caisse (`laboutik/views.py`)

| Ligne | Fonction | Changement |
|---|---|---|
| 943 | `_construire_donnees_articles` | `stock_suivi_du_produit_ou_none(product)`. `None` → `article_dict["stock_quantite"] = None` (pas de badge). |
| 850 | `_construire_donnees_articles` (poids/mesure) | Garder la lecture de `product.stock_inventaire` (même inactif) pour l'**unité** (labels g / cl). Ne remplir `stock_disponible_pm` et `autoriser_hors_stock_pm` que si le stock est **actif** ; sinon `None` et `True`. |
| 7045 | `_valider_stock_panier` | `stock_suivi_du_produit_ou_none` → `None` = `continue`. |
| 7373 | `_creer_lignes_articles` | idem → pas de `decrementer_pour_vente`, pas de badge mis à jour. |
| 7716 | `_creer_lignes_articles_cascade` | idem. |
| 8947 | `stock_insuffisant` | idem (inactif = « pas de stock géré »). |
| 15609 | `panel` (appui long) | `Stock.objects.filter(product=product, actif=True).first()` → bouton Stock grisé si inactif. |
| ~15620 / ~15640 / 15711 | `stock_detail`, `stock_action`, `toggle_bloquant` | `get_object_or_404(Stock, product=product, actif=True)` (D7). `toggle_bloquant` est joignable par POST direct même si l'UI le cache. |

### 7.2 Tireuse (`controlvanne/`)

| Fichier:ligne | Changement |
|---|---|
| `billing.py:829` | `stock_suivi_du_produit_ou_none(produit)` → `None` = pas de décompte. Garder le SAVEPOINT existant tel quel. |
| `signals.py:191` | `Stock.objects.filter(product_id=..., actif=True).first()` → inactif = branche « fût sans stock ». |
| `models.py:340` (`reservoir_max_ml`) | `Stock.objects.filter(product=..., actif=True).first()`. |

Ce que voit l'opérateur quand il désactive un **fût branché** (à écrire dans le message du
bouton « Désactiver le suivi » pour un fût) :
- le tirage continue sur la réserve en cours (`reservoir_ml` n'est pas touché :
  `signals.py:186-206` ne joue qu'au changement de `fut_actif`) ;
- la jauge s'affiche à 100 % (`reservoir_max_ml` retombe sur `reservoir_ml`, comme un fût
  sans stock) ;
- au **prochain changement de fût**, le réservoir repart à 0 : le tirage est bloqué
  (« Fût vide ») sauf si la tireuse est en réservoir illimité.

### 7.3 Inventaire : vues, API, service (`inventaire/`)

| Fichier:ligne | Changement |
|---|---|
| `views.py:39-106` `StockViewSet.reception` / `perte` / `offert` (`/api/inventaire/stock/{pk}/…`, clés LaBoutik) | `if not stock.actif:` → 400 `{"detail": _("Le suivi de stock est désactivé pour ce produit.")}`. |
| `views.py:131` (débitmètre) | `stock_suivi_du_produit_ou_none(product)` → `None` = 400, message existant. |
| `views.py` `stock_action_view` | `if not stock.actif:` → aucun mouvement, `erreur_feedback` = même message. Le partial renvoyé est celui de l'état inactif (formulaire de reprise). |
| `views.py` (nouveau) `stock_desactiver_suivi_view(request, stock_uuid)` | POST → `StockService.desactiver_suivi(stock)` → rend `stock_actions_partial.html`. |
| `views.py` (nouveau) `stock_reprendre_suivi_view(request, stock_uuid)` | POST → `ReprendreSuiviSerializer` (`quantite_comptee` : `IntegerField(min_value=0)`, obligatoire) → `StockService.reprendre_suivi(...)` → rend le partial (feedback ou erreur). |
| `serializers.py` | `ReprendreSuiviSerializer` (nouveau). |
| `services.py:283` `ResumeStockService.generer_resume` | `Stock.objects.filter(actif=True)` pour les alertes. **Code non branché en production** (seul appelant : `tests/pytest/test_inventaire.py`). Changement fait pour la cohérence (D3), priorité basse. |

Les deux nouvelles vues sont routées dans `StockAdmin.get_urls()`
(`Administration/admin/inventaire.py`), à côté de `inventaire_stock_action`, via
`self.admin_site.admin_view(...)` : mêmes droits que les opérations actuelles.
Noms : `inventaire_stock_desactiver_suivi`, `inventaire_stock_reprendre_suivi`.

### 7.4 WebSocket et JS de la caisse

- `wsocket/broadcast.py` `donnees_badge_stock(stock)` : ajoute `"suivi": stock.actif`.
  Les 4 producteurs du badge passent par cette fonction : la clé est toujours présente.
- `laboutik/templates/laboutik/partial/hx_stock_badge.html` : si `not produit.suivi`, rendre
  le `<div id="stock-badge-…" hx-swap-oob="outerHTML" aria-live="polite" data-testid=…>`
  **vide et sans** `data-stock-quantite`, `data-autoriser-hors-stock`, `data-stock-bloquant`.
  - `articles.js:174` : la garde au clic ignore déjà un badge sans `data-stock-quantite`.
  - `articles.js:427-450` (`syncStockBloquantApresWebSocket`) retire déjà `article-bloquant`.
- **`laboutik/static/js/tarif.js:463-468` (pavé poids) — à corriger.** Aujourd'hui, un badge
  sans `data-stock-quantite` fait retomber la garde sur `btn.dataset.stockDisponible`, figé
  au chargement. Après une désactivation, une pesée serait refusée côté client alors que le
  serveur l'accepte. Correction : si le badge existe **sans** `data-stock-quantite`, poser
  `stockDisponibleStr = ''` (→ `null`, pas de garde). Même règle que `articles.js:174`.
  Sans effet pour un produit jamais suivi : son bouton porte déjà un `data-stock-disponible` vide.

### 7.5 Admin — panneau d'opérations et fiche produit

**Templates `Administration/templates/admin/inventaire/`**

- `stock_actions_partial.html` : deux branches.
  - `{% if stock.actif %}` : contenu actuel (4 opérations, derniers mouvements) + un bouton
    « Désactiver le suivi » (`hx-post` vers `inventaire_stock_desactiver_suivi`, `hx-confirm`
    avec le texte d'effet, plus le texte « fût branché » du § 7.2 pour un fût).
  - `{% else %}` : message « Le suivi de stock est désactivé. Les ventes ne sont plus
    décomptées. Dernière quantité connue : … » + formulaire « Reprendre le suivi » :
    champ « Quantité comptée » (obligatoire) + bouton (`hx-post` vers
    `inventaire_stock_reprendre_suivi`).
  - `data-testid` : `stock-btn-desactiver-suivi`, `stock-form-reprendre-suivi`,
    `stock-input-quantite-comptee`, `stock-btn-reprendre-suivi`, `stock-suivi-desactive`.
- `stock_actions.html` : le contexte passe les deux nouvelles URLs. La vue
  `panneau_operations_stock` (`stock_fiche_produit.py:182`) et
  `StockAdmin.changeform_view` (`inventaire.py:256`) les ajoutent au contexte.
  Les trois vues qui rendent le partial (`stock_action_view` + les deux nouvelles) aussi.

**Fiche produit (`Administration/admin/stock_fiche_produit.py`)**

- Formulaire, case « Suivre le stock », `enregistrer_section_stock`, `get_readonly_fields` :
  **inchangés**. Le panneau reste affiché dès qu'un stock existe, actif ou non.
- `html_badge_stock_avec_lien` : stock inactif → « Non suivi » en badge gris, avec le lien
  vers la section Stock. Le lien est utile : c'est là qu'on reprend le suivi.
- `display_stock_produit_caisse` / `display_stock_fut` : garder
  `ordering="stock_inventaire__quantite"` (un stock inactif est trié sur sa quantité figée,
  accepté).
- `EtatStockFilter` : `rupture` / `alerte` / `ok` ajoutent `stock_inventaire__actif=True` ;
  `non_suivi` = `Q(stock_inventaire__isnull=True) | Q(stock_inventaire__actif=False)`.

**`save_related` (`Administration/admin/products.py:2104-2111` et `:2577-2584`)** — D10 :
ajouter `actif=False` au `Stock.objects.create(...)` automatique, et adapter le message
`messages.info` qui suit (« … le stock n'est pas suivi : activez-le depuis la section Stock »).

**Problème que crée D10, à traiter dans le même chantier.** Un stock inactif créé
automatiquement fait **disparaître la case « Suivre le stock »** de la fiche (un stock
existe). Pour suivre ce produit, le gestionnaire passe par « Reprendre le suivi » dans le
panneau, avec la quantité comptée. C'est le même geste qu'une première activation : le
libellé du formulaire doit donc rester neutre (« Suivre le stock — quantité comptée »)
plutôt que « Reprendre ».

**`StockAdmin` (`Administration/admin/inventaire.py`)** : `actif` dans `list_display`
(lecture seule) et `list_filter`. La bascule se fait dans le panneau, déjà affiché sur sa
fiche (`change_form_after_template`).

**Commentaires à mettre à jour** : en-tête de `stock_actions.html` et
`stock_actions_partial.html` (deux états), docstring de `StockService`,
`A TESTER et DOCUMENTER/stock-onglet-produit.md:58-60`.

## 8. Tests

### Tests existants

Aucun test existant ne devrait casser : le formulaire produit ne change pas, et aucun test
ne vérifie l'état du stock créé automatiquement par `save_related` (D10). Vérifié le
2026-10-23 sur `tests/pytest/test_stock_fiche_produit.py` et
`tests/e2e/test_admin_stock_fiche_produit.py`. La suite du domaine stock reste à relancer
après le code.

### pytest (`tests/pytest/test_stock_desactivation.py`, nouveau)

1. `StockService.desactiver_suivi` → `actif=False`, quantité inchangée, aucun mouvement.
2. `StockService.reprendre_suivi(stock, 12)` → `actif=True`, quantité 12, un mouvement `AJ`
   « Reprise du suivi ».
3. Vue de reprise sans quantité → erreur dans le partial, stock toujours inactif.
4. Vente en caisse d'un produit au stock inactif → aucun `MouvementStock`, quantité inchangée.
5. Vente bloquante (`autoriser_vente_hors_stock=False`, quantité 0) sur stock inactif → acceptée.
6. `_construire_donnees_articles` : stock inactif → `stock_quantite is None` ; tarif au poids
   → `stock_disponible None`, unité toujours lue (labels cl / L).
7. Produit au poids, stock inactif en `CL` → diviseur 100, ticket et rapport en « L ».
8. Opérations refusées sur stock inactif, aucun mouvement créé : `stock_action_view`,
   `StockViewSet.reception/perte/offert`, débitmètre (400), panel caisse `stock_action` et
   `toggle_bloquant` (404).
9. Tirage tireuse sur fût au stock inactif → facture créée, aucun mouvement.
10. `EtatStockFilter` : stock inactif dans « Non suivi », pas dans « Épuisé ».
11. `donnees_badge_stock` → `suivi: False` ; le HTML du badge n'a pas `data-stock-quantite`.
12. D10 : fût neuf enregistré sans cocher « Suivre le stock » (via `admin_client.post`) →
    stock créé, unité `CL`, `actif=False`. Avec la case cochée → stock `actif=True`.
13. `generer_resume` : stock inactif absent des alertes (priorité basse, cf. § 7.3).

Chaque test est vu échouer sur une mutation volontaire avant livraison.

### E2E (`tests/e2e/test_admin_stock_fiche_produit.py`, à compléter)

- Fiche produit avec stock : « Désactiver le suivi » → le panneau passe en état inactif,
  la colonne Stock de la liste affiche « Non suivi ».
- Caisse ouverte dans un second onglet : le badge de la tuile disparaît sans recharger ;
  un tarif au poids qui était bloqué (rupture, hors stock interdit) accepte la pesée.
- « Reprendre le suivi » sans quantité → refus ; avec 12 → badge revenu avec 12.

## 9. Découpage et estimation

| Étape | Contenu | Durée |
|---|---|---|
| 1 | Champ + migration + fonction commune + `StockService` (§ 4, § 5) | ~1 h |
| 2 | Caisse, tireuse, inventaire (§ 7.1 à 7.3) | ~2,5 h |
| 3 | Badge WebSocket + `tarif.js` (§ 7.4) | ~1 h |
| 4 | Panneau, vues, URLs, liste, `StockAdmin`, `save_related` (§ 7.5) | ~2 h |
| 5 | Tests pytest | ~3 h |
| 6 | E2E | ~1,5 h |
| 7 | CHANGELOG `CHANGELOG/2026-10-23-stock-desactivation.md` + `stock-onglet-produit.md` | inclus |

**Total : ~11 h (1,5 jour).**

Nouvelles chaînes traduisibles (msgid FR) : « Suivi actif » et son aide, « Désactiver le
suivi », texte de confirmation (et variante fût), « Le suivi de stock est désactivé… »,
« Suivre le stock — quantité comptée », « Reprise du suivi », message d'erreur de
quantité, « Non suivi », message `save_related`. Le workflow i18n sera à lancer par le
mainteneur.

## 9 bis. Écarts entre la spec et le code livré (2026-10-24)

- **URLs de bascule** : construites dans `stock_actions_partial.html` avec la balise `url`,
  au lieu d'être passées dans les cinq contextes (§ 7.5). Même résultat, aucun contexte à
  modifier.
- **Rendu du panneau** : une fonction `_rendre_panneau_stock` (`inventaire/views.py`)
  sert les trois vues HTMX (opération, désactiver, reprendre).
- **Test du panel d'appui long** (§ 8, test 8) : les méthodes `stock_action` et
  `toggle_bloquant` sont appelées directement (pas de client HTTP de terminal en pytest).
- **Non couvert par un test** : la correction de `tarif.js` (§ 7.4) et
  `reservoir_max_ml` (§ 7.2). L'E2E « caisse ouverte, le badge disparaît en direct »
  (§ 8) n'est pas écrit : le badge WebSocket est vérifié par pytest (HTML rendu).

## 10. Hors périmètre — questions ouvertes

- **Historique des désactivations** : aucune trace de qui a désactivé et quand (D4).
  Un champ date ou un journal d'admin serait possible si le besoin apparaît.
- **Écartés par le mainteneur (2026-10-24)** : filtre « Actifs » par défaut dans Inventaire > Stocks, et retrait du bouton « Ajouter un stock ». La liste montre tous les stocks avec la colonne « Suivi actif ».
- **Panel caisse (appui long)** : pas de bascule depuis la caisse, seulement depuis l'admin.
