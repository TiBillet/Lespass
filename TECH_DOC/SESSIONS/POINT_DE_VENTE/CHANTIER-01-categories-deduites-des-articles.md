# Chantier 01 — Les boutons de catégorie viennent des articles

**Statut :** étapes 1 et 2 codées le 2026-11-24, non commitées. Fiche : `CHANGELOG/2026-11-24-pv-categories-deduites-des-articles.md`.
**Date :** 2026-11-24

## 1. Le constat

Un point de vente a deux M2M à remplir dans l'admin : `products` et `categories`.

- `products` choisit les **articles** vendus (tuiles).
- `categories` choisit seulement les **boutons de filtre** à gauche de la caisse
  (« Tous », « Bar », « Snacks »…). Il ne charge aucun article.

Chaque article porte déjà sa catégorie : `Product.categorie_pos`. C'est elle qui donne la
couleur, l'icône par défaut et la classe CSS `cat-<uuid>` de la tuile
(`_construire_donnees_articles`, `laboutik/views.py`). Le M2M `categories` fait donc doublon.

Quand les deux ne sont pas d'accord :
- un article dont la catégorie n'est pas cochée n'a pas de bouton : on le voit seulement
  sous « Tous » ;
- une catégorie cochée sans article donne un bouton qui affiche une grille vide.

En base de dev, ça arrive déjà : « Accueil Festival » a un bouton « Billetterie » vide ;
plusieurs points de vente de test vendent une catégorie qui n'a pas de bouton.

Le chantier voisin « mode recharge » (`TECH_DOC/SESSIONS/RECHARGE_CAISSE/SPEC.md` §4) note le
même défaut : un caissier sans droit de recharge verra un bouton « Cashless » vide.

## 2. Ce qui lit le M2M `categories` (enquête complète)

| Endroit | Usage |
|---|---|
| `laboutik/views.py` `_construire_donnees_categories()` | **Seul lecteur en production** : construit les boutons |
| `Administration/admin/laboutik.py` `PointDeVenteAdmin` | `fieldsets` (« Products & categories ») et `filter_horizontal` |
| `laboutik/management/commands/create_test_pos_data.py` | 6 × `.categories.set(...)` |
| `tests/pytest/test_pos_models.py:80, 328-333, 509` | crée / vérifie le M2M |
| `tests/pytest/test_pos_views_data.py:81, 109, 645-700` | test des icônes des boutons |
| `tests/pytest/test_stock_visuel_pos.py:105` | `.categories.clear()` au nettoyage |

Aucun autre lecteur : pas d'API v2, pas de serializer, pas de websocket
(`wsocket/broadcast.py` ne touche pas aux catégories), pas d'accès inverse
`CategorieProduct.points_de_vente`, pas de fixture JSON, pas de JS (le JS filtre seulement
sur la classe `cat-<uuid>` des tuiles, `laboutik/static/js/articles.js`).

`_construire_donnees_categories()` a un seul appelant : `CaisseViewSet` (vue du point de
vente, `laboutik/views.py`, appel juste après `_construire_donnees_articles()`).

## 3. Le changement

### Étape 1 — sans migration

1. **`_construire_donnees_categories(point_de_vente_instance, articles, events_billetterie=None)`**
   reçoit la liste `articles` déjà construite. Elle en tire les boutons :
   - on parcourt les articles et on garde les `article["categorie"]["id"]` distincts ;
   - les tuiles billet portent l'uuid de leur événement comme catégorie : aucune
     `CategorieProduct` ne l'a, la requête l'ignore (pas de saut explicite) ;
   - on saute la catégorie par défaut `"default"` (voir la question Q1) ;
   - **une** requête : `CategorieProduct.objects.filter(uuid__in=ids).order_by("poid_liste", "name")`,
     pour garder l'ordre actuel des boutons ;
   - la partie « événements en pseudo-catégories » ne change pas.

   Partir des **articles affichés**, et non du M2M `products`, compte : les filtres de
   `_construire_donnees_articles()` (recharge sans Asset, sans tarif vendable, recharge
   masquée sans « mode recharge »…) s'appliquent aussi aux boutons. Pas de bouton vide.

2. **L'appel dans `CaisseViewSet`** passe `articles`.

3. **Admin** : retirer `categories` du fieldset et de `filter_horizontal`. Le fieldset
   devient « Produits ». `PointDeVenteForm` a `fields = '__all__'`, mais l'admin ne garde que
   les champs des `fieldsets` : rien d'autre à faire.

4. **Tests** (`tests/pytest/test_pos_views_data.py`, test 6 réécrit + nouveaux) :
   - une catégorie d'article non cochée dans le M2M a son bouton ;
   - une catégorie cochée dans le M2M sans article n'a pas de bouton ;
   - l'ordre suit `poid_liste` puis `name` ;
   - une tuile de recharge masquée ne crée pas de bouton (dépend du chantier voisin) ;
   - mutation : remettre la lecture du M2M doit faire échouer les deux premiers.

5. **CHANGELOG** + mise à jour de cet index.

Comportement visible : dans un lieu qui avait coché moins de catégories que ses articles
n'en ont, de nouveaux boutons apparaissent. C'est voulu.

### Étape 2 — plus tard, avec migration

- `RemoveField` de `PointDeVente.categories` (une migration `laboutik`, suppression d'une
  table de liaison : rapide, mais sur ~500 schémas).
- Retirer les `.categories.set/add/clear` de `create_test_pos_data.py` et des tests.
- À faire **après** le commit du chantier voisin : sa migration
  `laboutik/0003_carteprimaire_mode_recharge.py` n'est pas commitée. Deux migrations
  `laboutik` en parallèle sur la même base se marchent dessus.

## 4. Questions au mainteneur

- **Q1. Les articles sans catégorie existent.** `Product.categorie_pos` est
  `null=True, blank=True` (`BaseBillet/models.py:1490`) et le champ est facultatif dans
  l'admin des articles de caisse (`Administration/admin/products.py`, fieldset « General »).
  Surtout, **l'admin des adhésions n'a pas ce champ** : une adhésion ajoutée à un point de
  vente n'a jamais de catégorie. En dev : 51 articles de point de vente sans catégorie, dont
  44 adhésions. Ces tuiles portent la classe `cat-default` (`CATEGORIE_PAR_DEFAUT`) et n'ont
  aucun bouton aujourd'hui.
  **Décision (2026-11-24) : deux boutons de repli, affichés seulement s'ils ont des articles.**
  - « Adhésions » pour les adhésions sans catégorie ;
  - « Divers » pour les autres articles sans catégorie.

  Mise en œuvre :
  - `laboutik/views.py` : à côté de `CATEGORIE_PAR_DEFAUT` (id `"default"`), une seconde
    constante `CATEGORIE_ADHESIONS_PAR_DEFAUT` (id `"adhesions"`, icône `card_membership`).
    Les deux noms passent par `gettext_lazy` : le fichier importe `gettext as _`, qui
    figerait la langue au chargement du module. `"Divers"` devient traduisible.
  - `_construire_donnees_articles()` : sans `categorie_pos`, une adhésion
    (`categorie_article == Product.ADHESION`) reçoit `CATEGORIE_ADHESIONS_PAR_DEFAUT`, le
    reste `CATEGORIE_PAR_DEFAUT`.
  - `_construire_donnees_categories()` : les deux boutons de repli viennent **après** les
    catégories réelles, « Adhésions » puis « Divers », et **avant** les événements.
  - Tests en plus : un bouton « Adhésions » pour une adhésion sans catégorie ; un bouton
    « Divers » pour un article sans catégorie ; aucun des deux quand tout est catégorisé.
- **Q2. L'étape 2** : décidée le 2026-11-24, **dans la foulée** de l'étape 1.

## 5. Coordination avec le chantier « mode recharge »

L'autre agent modifie en ce moment `_construire_donnees_articles()` (paramètre
`afficher_les_recharges`) et l'appel dans `CaisseViewSet`, à deux lignes de
`_construire_donnees_categories()`. Il modifie aussi `laboutik/models.py`,
`create_test_pos_data.py` et ajoute la migration `0003`.

**Décision (2026-11-24) :** coder les étapes 1 et 2 **après** la fin de son chantier (tests
verts, fichiers stables). Le mainteneur relance. La migration `0004` dépendra de sa `0003`.

**Conséquence sur le chantier 00 :** le chantier voisin remplace la règle « bouton Recharger
du check carte = la carte primaire a un PV Cashless » par « la carte primaire est en mode
recharge ». La description du type Cashless dans `Administration/admin/laboutik.py`
(`DESCRIPTIONS_DES_TYPES_DE_POINT_DE_VENTE`, point 2) deviendra fausse. Il faudra la
corriger quand ce chantier sera fusionné.
