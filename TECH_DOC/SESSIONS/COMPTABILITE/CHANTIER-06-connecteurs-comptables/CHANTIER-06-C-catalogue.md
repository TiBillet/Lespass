# Chantier 06-C — Le catalogue de TiBillet dans Dolibarr (mode « articles et ventes »)

> **Statut** : ✅ **CODÉE le 2026-10-15, non commitée** (Django : 14 tests, mutations §11 ;
> module : essai 1 à 15 vert). Spec relue par Fable le même jour (§10). C13 : la clé a les
> droits « Produits » + « Comptabilité » (mainteneur). C15 validée. CHANGELOG
> `CHANGELOG/2026-10-15-catalogue-comptable.md`.
> Contexte : [`README.md`](README.md) du chantier 06 (§5 R1/R7, §7), fiches
> [`06-A`](CHANTIER-06-A-api-comptable.md) (l'API) et [`06-B`](CHANTIER-06-B-module-dolibarr.md)
> (le module). Code lu le 2026-10-15 (branche `main`, Dolibarr `develop` ≈ 24).
> **Revérifier les numéros de ligne avant de coder.**
> Migration : **non**.

---

## 1. Le but, en une phrase

Un lieu peut choisir, à la place du FEC, de laisser **Dolibarr tenir sa comptabilité à
partir de ses propres factures**. TiBillet n'est alors qu'un « front » de vente. Cette
fiche couvre la **première marche** : chaque nuit, Dolibarr recopie le **catalogue** de
TiBillet (articles, catégories, TVA, compte de vente). Les ventes (factures, paiements)
feront l'objet d'une fiche suivante.

## 2. Expliqué simplement (FALC)

- Sur la page du module, le lieu choisit **un seul** mode : « écritures comptables » (le
  FEC, comme aujourd'hui) **ou** « articles et ventes ». Jamais les deux : sinon chaque
  vente serait comptée deux fois.
- En mode « articles et ventes », chaque nuit, Dolibarr demande à TiBillet **tout son
  catalogue**. Il est petit (sur le lieu de dev : 272 produits, 333 tarifs, 8 catégories).
- Si rien n'a changé depuis la veille, TiBillet répond « rien de neuf » (code `304`) et
  Dolibarr ne touche à rien.
- Sinon, pour chaque **tarif** vendu en euros (« Bière — Pinte », « Bière — Demi »),
  Dolibarr crée ou met à jour **un produit**, avec son prix TTC, sa TVA, son compte de
  vente et ses catégories.
- Un tarif archivé dans TiBillet devient « hors vente » dans Dolibarr. **Rien n'est jamais
  supprimé** : un produit déjà facturé ne peut pas l'être.
- Les recharges, les virements et les tarifs en jetons **ne sont pas des ventes** : ils
  ne vont pas dans Dolibarr.

## 3. Ce qu'on sait déjà (lu le 2026-10-15)

### Côté TiBillet

| Quoi | Où |
|---|---|
| Article, tarifs | `BaseBillet/models.py` : `Product` (l.1231 : `uuid`, `name`, `tva`, `categorie_article`, `methode_caisse`, `categorie_pos`, `archive`, `publish`) ; `Price` (l.1941 : `uuid`, `name`, `prix` **Decimal en euros**, `free_price` l.1953, `archived` l.1961, `poids_mesure` l.1984 = prix au kg ou au litre, `asset` / `non_fiduciaire` l.2005-2026 = prix en jetons) |
| Catégorie de caisse | `CategorieProduct` (l.1118) : `uuid`, `name`, `poid_liste`, `tva` (valeur par défaut d'admin), `compte_comptable`. **Plate** (pas de parent) |
| Règle de TVA d'un article | `laboutik/views.py` `_taux_tva_de_la_ligne_de_caisse(produit, methode_db)` (l.7021) : 0 si offert ou en points, 0 si recharge (D10), taux de la consigne pour un retour (D11), sinon **TVA du produit, sinon TVA du lieu** (`Configuration.vat_taxe`). **Jamais celle de la catégorie** (aide du champ : `Administration/admin/products.py:1918`). Seuls 50 produits sur 272 ont une TVA sur le lieu de dev |
| Règle « article → compte » | `laboutik/plan_comptable.py` `compte_pour_article(ligne, …)` (l.715) : 0 hors CA (écarts, jetons cadeau, recharges → 419100, virement `VR` → compte de la monnaie **de la ligne**), 0 bis `TM`/`FD` erreur, 1 retour de consigne, 2 catégorie de caisse, 3 mode de caisse, 4 type de produit, 5 erreur. Appelée par `comptabilite/ventilation.py` (l.213, 243, 270) et `plan_comptable.py:1208` |
| Natures de compte | `laboutik/models.py` `CompteComptable` (l.2080) : `VENTE`, `TVA`, `TRESORERIE`, `TIERS`, `CHARGE`, `PRODUIT_EXCEPTIONNEL` |
| API produits | `api_v2/views.py` `ProductViewSet` (l.580) : liste = `archive=False, publish=True` ; `api_v2/serializers.py` `ProductSchemaSerializer` (l.906) : schema.org, `offers[]` = tarifs non archivés. **Ni TVA, ni catégorie de caisse, ni compte, ni état archivé** |
| Droits des clés | `BaseBillet/models.py` `ExternalApiKey.api_permissions()` (l.5349) : un droit **par route** (`"product"`, `"price"` → `self.product`), **sans distinction lecture / écriture** (`ApiBillet/permissions.py:58`). Le droit `product` ouvre donc aussi `POST /products/`. La clé Dolibarr n'a que `comptabilite` |
| Dates de modification | **Aucune** sur `Product`, `Price`, `CategorieProduct`, `Tva`, `CompteComptable` : pas de synchro « depuis la dernière fois » possible |

### Côté Dolibarr (sources `/home/jonas/Gits/dolibarr/htdocs`)

| Quoi | Où |
|---|---|
| Unicité | `ref` unique par entité (`install/mysql/tables/llx_product.key.sql:24`) ; `ref_ext` varchar(128) **sans index ni unicité** ; `import_key` = 14 caractères (trop court pour un uuid) |
| Créer | `Product::create($user)` (`product/class/product.class.php:968`) : `ref` et `label` obligatoires ; **`status` = 0 (hors vente) si non rempli** (l.1018) ; ref déjà prise → `ErrorProductAlreadyExists`, pas d'upsert |
| Modifier | `Product::update()` (l.1405) **réécrit tous les champs** : `fetch()` d'abord. `updatePrice($prix, 'TTC', $user, $tva)` (l.2970) écrit l'historique `llx_product_price` |
| Retrouver | `Product::fetch(0, '', $ref_ext)` filtre par entité |
| Supprimer | refusé si le produit est sur une facture (`childtables` → `facturedet`) : on passe `status=0` |
| Prix libre | le prix du produit n'est qu'une valeur par défaut : chaque ligne de facture a son prix. `price_min` / `price_min_ttc` (`llx_product.sql:46-47`) refusent un prix plus bas |
| Au poids | `llx_facturedet.qty` est un `real` (quantité décimale) ; unité `fk_unit` si `PRODUCT_USE_UNITS` |
| Catégories | `llx_categorie` : `fk_parent`, `ref_ext`, unicité `(entity, fk_parent, label, type)`. **Pas de compte comptable sur une catégorie.** `Categorie::fetch(…, $ref_ext)` fait un `LIKE` sans filtre de type (`categories/class/categorie.class.php:485`). `Product::setCategories($ids)` remplace toutes les catégories du produit (l.7499) |
| TVA France | `llx_c_tva` (base de dev) : 0, 2,1, 5,5, 10, 20 actifs ; 8,5 (DOM) inactif. `tva_tx` n'est pas contrôlé à l'enregistrement du produit ; à la facture, un taux absent du dictionnaire retombe sur `ACCOUNTING_VAT_SOLD_ACCOUNT` |
| Compte de vente d'une facture | `accountancy/class/accountingaccount.class.php:751` : `accountancy_code_sell` du produit, sinon `ACCOUNTING_PRODUCT_SOLD_ACCOUNT` / `ACCOUNTING_SERVICE_SOLD_ACCOUNT` |
| Modules | `modProduct`, `modService`, `modCategorie` **inactifs** sur la base de dev (actifs : Factures, Comptabilité, Banques, Cron) |

## 4. Décisions

| # | Sujet | Décision | Pourquoi |
|---|---|---|---|
| C1 | Mode | **Fait (2026-10-15)** : constante `TIBILLET_MODE` = `ecritures` (défaut) ou `ventes`, boutons radio sur la page du module. En mode `ventes`, l'import des clôtures et « Réimporter » n'écrivent rien. **Changement libre, avec une alerte** si des clôtures sont déjà dans le grand livre (mainteneur) | Pas de double compta |
| C2 | Un produit Dolibarr = ? | **Un tarif TiBillet** (`Price`), pas un `Product` (mainteneur). `ref_ext` = uuid du tarif ; `label` = « Produit — Tarif » | Dolibarr n'a pas de couple produit/prix « à la Stripe » : les multiprix sont une grille par client, les variantes un module lourd. C'est le tarif qui porte le prix facturé |
| C3 | Prix | `price_base_type = 'TTC'`, `price_ttc` = `Price.prix`, `tva_tx` = taux effectif. Prix libre : `price_min_ttc` = `Price.prix` (le minimum de TiBillet ; imposé par l'écran de facture seulement, `compta/facture/card.php:174`, pas par la classe). Au poids : prix au kg / litre, unité laissée vide pour l'instant (§8). **À la création, tout est posé avant `create()`** (qui écrit déjà une ligne d'historique, `product.class.php:1225`) ; jamais d'`updatePrice` juste après. **À la mise à jour**, `updatePrice($prix, 'TTC', $user, $tva, $prix_minimum)` : le 5ᵉ argument est obligatoire, sinon le minimum repasse à 0 (l.2971) | Les prix TiBillet sont TTC |
| C4 | Type Dolibarr | **Service** (`type=1`) pour billets, réservations, badges, QR, ressources, adhésions (`B F G Q C A`) ; **produit** (`type=0`) pour le reste (caisse). Mise à jour : `update(…, $updatetype = true)` (l.1405), sinon le type n'est jamais réécrit | Sens commun Dolibarr ; sans effet sur le compte (C5 le fixe) |
| C5 | Compte de vente | `accountancy_code_sell` = le compte que **TiBillet** calcule (même règle que le FEC), passé par `numeroDeCompteDolibarr()` du module (zéros de fin). Les comptes manquants sont créés comme aujourd'hui (`creerLesComptesManquants`) | Une catégorie Dolibarr ne porte pas de compte. Mêmes comptes qu'en mode FEC |
| C6 | Ce qui ne va pas dans Dolibarr | Recharges (`RE`, `RC`, types `R`, `E`), virement reçu `VR`, vider carte `VC`, `TM`, `FD`, **retour de consigne `CR`** (il vaut *moins* le prix du gobelet, D11, `laboutik/views.py:2975-2998` : ce sera une ligne négative ou un avoir, en 06-D), ~~fût `U`~~ (**corrigé le 2026-10-16** : la tireuse vend le fût lui-même au litre, `controlvanne/billing.py` ; le fût EST une vente), produits système (écarts d'encaissement, jetons cadeau repris : **les mêmes constantes de noms** que la règle 0, `plan_comptable.py:109-118`, pas une copie), **tarifs en jetons** (`asset` renseigné). **Décidé par TiBillet** (un booléen par article, §5) : le module PHP ne connaît pas les codes de TiBillet | Pas des ventes : TiBillet est un « front » de vente (mainteneur). Les virements pourront revenir plus tard |
| C7 | Catégories | Deux catégories mères dans Dolibarr : **« Caisse TiBillet »** (une fille par catégorie de caisse, `ref_ext` = son uuid) et **« Types TiBillet »** (une fille par type : Billets, Adhésions, Réservations gratuites…, `ref_ext` = `type:<code>`). Un produit est rangé dans sa catégorie de caisse **et** dans celle de son type. **Seules les filles des deux mères TiBillet** sont retirées ou ajoutées : `setCategoriesCommon($ids, 'product', false)` pour ajouter, retrait explicite des seules catégories TiBillet en trop. `setCategories()` est interdit : il retire aussi les catégories posées à la main (`commonobject.class.php:12012`, `to_del` l.12038). Catégorie de caisse supprimée dans TiBillet (`SET_NULL`) ou produit déplacé : le produit quitte l'ancienne fille ; la fille reste (C8) | Les types sont automatiques (`categorie_article`). Deux mères : une catégorie de caisse « Adhésions » ne bloque pas le type « Adhésions » (unicité par parent) |
| C8 | Ce que le module ne fait jamais | Supprimer un produit ou une catégorie ; toucher un produit ou une catégorie **sans** `ref_ext` TiBillet | Un produit facturé ne se supprime pas ; le lieu peut avoir ses propres produits |
| C9 | En vente ou non | `status` (en vente) = 1 si ni l'article (`Product.archive`) ni le tarif (`Price.archived`) n'est archivé ; sinon 0. `publish` est ignoré | Un tarif non publié sur le site peut se vendre en caisse |
| C10 | Changements | **Tout le catalogue à chaque passage**, avec un **`ETag`** (empreinte du JSON). Le module renvoie l'`ETag` de la dernière synchro réussie dans `If-None-Match` ; `304` = rien à faire. Il n'enregistre l'`ETag` qu'**après un passage sans erreur** | Pas de date de modification dans TiBillet (§3). Petit volume |
| C11 | Mise à jour d'un produit | `fetch` par `ref_ext`, **comparer**, et n'appeler `update` / `updatePrice` que si une valeur a changé | **Nécessaire** : hors multiprix, `updatePrice` écrit une ligne d'historique **à chaque appel**, même sans changement (`product.class.php:3170-3171`) |
| C12 | Route | **Pas de nouvelle route** : `GET /api/v2/products/?accounting=true` (mainteneur). Sans le paramètre, rien ne change | Une seule route produits |
| C13 | Droit | En mode `ventes`, la clé Dolibarr a **deux droits** : `comptabilite` (plan comptable) **et** `product` (lecture **et** écriture). **Aucun changement** à `get_apikey_valid` ni aux droits (mainteneur, 2026-10-15) | Méthode en production, on n'y touche pas. Dolibarr aura besoin de **créer** des produits plus tard |
| C14 | Modules Dolibarr | Au passage en mode `ventes`, la page active `modProduct`, `modService` et `modCategorie` (`activateModule()`, `core/lib/admin.lib.php`). Ils ne sont **pas** des dépendances du module | Le mode FEC n'en a pas besoin |
| C15 | Tâche de nuit | **Une seule tâche**, méthode `passageDeLaNuit()`, qui lance selon le mode l'import des clôtures **ou** la synchro du catalogue (puis, en 06-D, celle des ventes, dans cet ordre). Remplace la méthode `importerLesClotures` dans le descripteur ; la tâche existante est mise à jour, pas recréée (à vérifier sur le Dolibarr de dev). *(proposé, à valider)* | Un seul réglage d'heure ; l'ordre catalogue → ventes est garanti. Aucune installation hors dev (README §11) |
| C16 | Heure de la tâche | **Réglable sur la page du module** (`HH:MM`, constante `TIBILLET_HEURE`, défaut `06:00` depuis le 2026-10-16 : après la clôture J automatique de TiBillet, fermeture + 2 h). À l'enregistrement, la page recale `datenextrun` de la tâche (`Cronjob::fetch` puis `update`, `cron/class/cronjob.class.php:529` et 792) sur la prochaine occurrence de cette heure. Le descripteur lit la même constante pour une installation neuve. La page affiche le **prochain passage** | Dolibarr garde l'heure de `datenextrun` d'un passage à l'autre (`reprogram_jobs`, `cronjob.class.php:1665`, + 86 400 s). Précision : celle du cron de la pile (toutes les 5 min). **Limite** : + 86 400 s décale d'une heure au changement d'heure d'été / d'hiver ; réenregistrer la page recale. La tâche n'est pas supprimée à la désactivation (`test` ≠ `'1'`, `DolibarrModules::delete_cronjobs`), donc l'heure survit à une réactivation |

## 5. Côté TiBillet

### 5.1 Deux règles sorties de leur fonction, sans être recopiées

1. **Compte** : `compte_pour_produit(produit, comptes_du_plan_par_defaut=None,
   monnaie_de_la_ligne=None)` dans `laboutik/plan_comptable.py` = **toutes** les règles de
   `compte_pour_article`, **dans le même ordre** (`VR` reste après écarts, jetons repris
   et recharges : monnaie `None` → `CompteComptableManquant`, comme l.797-801).
   `compte_pour_article(ligne, comptes)` devient
   `compte_pour_produit(ligne.pricesold.productsold.product, comptes, ligne.asset)`. Les
   appelants (`ventilation.py:213, 243, 270`, `plan_comptable.py:1208`) ne changent pas.
   **Comportement identique par construction** : les tests du chantier 05 et de 06-A
   passent sans retouche. Le catalogue ne demande pas de compte aux articles écartés (C6).
2. **TVA** : `taux_de_tva_du_produit(produit, taux_du_lieu)` = les points 2 à 4 de
   `_taux_tva_de_la_ligne_de_caisse` (recharge 0 avec **la même** liste
   `METHODES_CAISSE_DES_RECHARGES`, `plan_comptable.py:685` ; consigne ; produit ; lieu).
   Retour de consigne **sans** consigne reliée (`SET_NULL`, `models.py:1549`) → **erreur
   nommée**, pas un `AttributeError` (aujourd'hui l.7063-7069 : un `CR` orphelin ferait
   planter tout le catalogue en `500`). La fonction de la caisse garde son point 1
   (offert / points) puis l'appelle. `taux_du_lieu` est lu **une fois** par l'appelant
   (`Configuration.get_solo()`, sinon une lecture par produit). Rangée dans
   `laboutik/plan_comptable.py` ; `_taux_tva_de_la_ligne_de_caisse` garde son nom et sa
   place (17 appelants, dont `api_v2/views.py:28` et `serializers.py:26` : rien à
   déplacer).

### 5.2 `GET /api/v2/products/?accounting=true`

- Rend **tous** les produits, publiés ou non, archivés ou non, et pour chacun **tous** ses
  tarifs (archivés compris).
- Ajoute dans `additionalProperty` du produit :

| `name` | Valeur |
|---|---|
| `productType` | `{"code": "B", "label": "Billet"}` (`categorie_article`) |
| `posCategory` | `{"identifier": uuid, "name": …, "order": poid_liste}` ou absent |
| `vatRate` | `"20.00"` : `taux_de_tva_du_produit` (§5.1) |
| `accountingAccount` | `{"number": "707000", "label": …}`, **ou** absent si la règle lève `CompteComptableManquant` |
| `accountingAccountError` | la phrase de `CompteComptableManquant` (si erreur) |
| `forAccountingSync` | `true` si l'article est une vente en euros, `false` sinon (C6) |
| `archived` | `Product.archive` |

- Ajoute dans `additionalProperty` de chaque tarif (`offers[]`) : `archived`
  (`Price.archived`) et `soldByWeightOrVolume` (`Price.poids_mesure`). `freePrice` et
  `priceCurrency` existent déjà (un tarif en jetons a un `priceCurrency` ≠ `EUR` : le
  module l'écarte aussi).
- **`ETag`** : `sha256` du JSON rendu (clés triées). `If-None-Match` égal → `304` sans
  corps. **Pièges** : nginx compresse le JSON (`nginx_prod/lespass_prod.conf:108-116`) et
  rend l'`ETag` « faible » (`W/"…"`) : comparer sans le préfixe `W/`. Le JSON contient
  des libellés traduits (`category`, `productType.label`, phrases d'erreur) et
  `LocaleMiddleware` suit `Accept-Language` : rendre la réponse `accounting` **dans une
  langue fixe** (`translation.override("fr")`), sinon l'`ETag` change avec le client.
- Pas de pagination (comme `/closures/` : A11 de 06-A). `select_related("tva",
  "categorie_pos__compte_comptable", "consigne_remboursee__tva")` et
  `Prefetch("prices", to_attr=…)` ; le sérialiseur lit cette liste en mode `accounting`
  (aujourd'hui `instance.prices.filter(…)`, `serializers.py:915`, refait une requête par
  produit et ignorerait le prefetch).
- `api_v2/openapi-schema.yaml` : paramètre `accounting`, réponse `304`, nouvelles
  propriétés. `api_v2/GUIDELINES.md` si la convention `additionalProperty` y est décrite.

### 5.3 Le droit

**Rien à coder.** La route `/products/` garde sa permission (`SemanticApiKeyPermission`,
basename `product`). La clé du lieu doit avoir le droit **Produits** en plus de
**Comptabilité (lecture)** (C13). Écarté : une permission « lecture seule » propre à
`/products/`, qui obligeait à découper `get_apikey_valid` (en production).

Conséquences :
- la clé Dolibarr peut **créer** des produits (`POST /products/`) : voulu, pour plus tard ;
- une clé `product` sans `comptabilite` voit aussi les propriétés comptables de
  `?accounting=true` (numéros de compte, TVA) : rien de sensible ;
- l'aide du champ « Clé d'API » de la page du module (`TiBilletCleAide`) dit, selon le
  mode, quels droits cocher ; « Tester la connexion » essaie aussi `/products/` en mode
  `ventes` (le `403` dit alors : « ajoutez le droit Produits à la clé »).

## 6. Côté module Dolibarr

Nouvelle classe `class/catalogue.class.php` (`CatalogueTiBillet`), qui réutilise l'appel
HTTP de `ImportTiBillet` (`appelerTiBillet`, rendu `protected` ou sorti dans une petite
classe commune : à trancher au code, sans recopier la sécurité https / mode dev).

**Un passage** (`synchroniserLeCatalogue()`, retour 0 = OK) :

1. Mode `ecritures` → ne rien faire, le dire. Module non configuré → le dire.
2. Modules Produits / Services / Catégories inactifs → échec avec une phrase claire.
3. `GET /api/v2/products/?accounting=true` avec `If-None-Match` = `TIBILLET_CATALOGUE_ETAG`.
   `304` → « Catalogue inchangé », fin.
4. Les comptes manquants : `creerLesComptesManquants` (comme l'import des clôtures).
5. Les catégories : les deux mères, puis une fille par catégorie de caisse et par type
   rencontrés. Recherche par `ref_ext` **exact, type produit, entité** (requête SQL du
   module : `Categorie::fetch` fait un `LIKE`). Libellé changé → renommer ; libellé déjà
   pris sous la même mère (`Categorie::already_exists`, l.1589) → erreur notée.
6. Pour chaque tarif d'un produit `forAccountingSync`, en euros : chercher par `ref_ext`
   (requête exacte, entité), créer ou comparer puis mettre à jour (C2 à C5, C9, C11),
   puis ranger dans ses catégories (C7). `label` = varchar(255) (`llx_product.sql:37`) :
   « Produit — Tarif » tronqué à 255 (`dol_trunc`). **Une transaction par tarif** : une erreur n'arrête
   pas les autres, elle est notée.
7. Produit sans `accountingAccount` : **voir Q2**.
8. Aucune erreur → enregistrer le nouvel `ETag`. Sinon ne pas l'enregistrer : la nuit
   suivante refait tout.
9. Résumé dans `$this->output` : créés, mis à jour, passés hors vente, inchangés, écartés,
   erreurs.

**Page du module** : champ « Heure de la tâche de nuit » (`HH:MM`) et prochain passage
(C16) ; en mode `ventes`, bouton « Synchroniser le catalogue maintenant », et la date et
le résumé du dernier passage.

## 7. Tests

### TiBillet (`tests/pytest/test_api_v2_catalogue_comptable.py`, `django_db`)

| # | Cas | Attendu |
|---|---|---|
| 1 | Clé `product` + `comptabilite` : `GET /products/?accounting=true` ; clé `comptabilite` seule : même appel | `200` ; `403` (inchangé) |
| 2 | Clé `product` : `GET /products/` sans paramètre | Réponse inchangée (pas d'archivé, pas de propriété comptable) |
| 3 | TVA : produit avec TVA ; produit sans TVA (lieu à 10 %) dans une catégorie à 20 % ; recharge ; `CR` relié à un gobelet à 20 % ; `CR` sans gobelet | Son taux ; `10.00` (jamais la catégorie) ; `0.00` ; `20.00` ; pas de `500` (erreur nommée sur ce produit) |
| 4 | Compte : catégorie de caisse reliée ; billet ; adhésion ; `VT` sans catégorie | Son compte ; 706000 ; 756000 ; `accountingAccountError` |
| 5 | `forAccountingSync` : bière, billet / recharge `RE`, `VR`, `CR`, `U`, écart, `TM` | `true` / `false` |
| 7 bis | `ETag` avec `Accept-Language: en` puis `fr` | Même `ETag` |
| 6 | Produit archivé, tarif archivé, produit non publié | Présents, avec `archived` |
| 7 | `ETag` : deux appels ; `If-None-Match` ; prix changé | Même `ETag` ; `304` ; nouvel `ETag` |
| 8 | Non-régression | Suites `comptabilite`, `laboutik` (plan comptable, caisse) et `test_api_v2_comptabilite.py` vertes |

**Mutations** : TVA de la catégorie prise ;
`compte_pour_produit` qui saute la règle 2 ; recharge en `forAccountingSync=true` ; tarif
archivé filtré ; `ETag` sans tri des clés ; `304` qui renvoie un corps ; consigne ignorée dans la TVA ;
langue non figée.

### Module (`scripts/essai.php`, mode `ventes`, contre le lieu de dev)

| # | Cas | Attendu |
|---|---|---|
| 8 | Un passage | Un produit par tarif synchronisable, avec `ref_ext`, prix TTC, TVA et compte = TiBillet ; rangé sous ses deux catégories ; **une seule** ligne `llx_product_price` par produit créé |
| 8 bis | Catégorie posée à la main sur un produit TiBillet, puis passage (`ETag` effacé) | La catégorie manuelle reste |
| 9 | Second passage | `304`, aucune écriture (`llx_product` et `llx_product_price` inchangés) |
| 10 | Prix modifié à la main dans Dolibarr, `ETag` effacé | Le passage remet le prix de TiBillet, une ligne d'historique de plus |
| 11 | Écartés | Aucun produit Dolibarr pour une recharge ou un tarif en jetons |
| 12 | Mode `ecritures` | La synchro ne fait rien |
| 13 | Produit Dolibarr sans `ref_ext` | Jamais modifié |
| 14 | Heure enregistrée `21:45` (C16) | `datenextrun` de la tâche = prochain 21:45 ; une heure invalide (`25:00`) est refusée, la tâche ne bouge pas |

**Mutations** : `status` non posé ; `update` sans `fetch` ; `ETag` enregistré malgré une
erreur ; recherche par `ref_ext` en `LIKE` ; `updatePrice` après `create` ;
`setCategories` à la place du retrait ciblé ; `updatePrice` sans le prix minimum.

## 8. Hors de cette fiche

- **Les ventes** : factures (une par vente ? par J ?), paiements (espèces, CB, monnaie
  locale, chèque…), tiers « client anonyme », ventilation (pas automatique dans Dolibarr),
  avoirs. Fiche 06-D. Prérequis : `TODO/API-v2-ventes-reglements.md`.
- **Unité des tarifs au poids** (`fk_unit`) : le kg ou le litre n'est pas rangé sur le
  tarif dans TiBillet.
- **Stock**, images, descriptions longues.
- **Virements reçus** (`VR`) dans Dolibarr : plus tard si un lieu en a besoin.

## 9. Questions au mainteneur

Réponses du 2026-10-15 :

| # | Question | Décision |
|---|---|---|
| Q1 | La `ref` lisible du produit Dolibarr (unique, affichée partout) | **`TIB-` + 8 premiers caractères de l'uuid du tarif.** Collision (très improbable) → erreur notée, pas d'écrasement |
| Q2 | Un article vendable **sans compte** (ex. `VT` sans catégorie de caisse) | **Ne pas le créer**, et le dire dans le résumé, avec la phrase de TiBillet. Sinon Dolibarr le rangerait au compte par défaut, différent du FEC |
| Q3 | Le libellé quand le produit n'a qu'un tarif | **« Produit — Tarif » toujours** (simple et stable) |
| Q4 | Heure de la synchro | **Réglable sur la page du module** (C16) ; une seule tâche (C15, à valider) |

## 10. Relecture Fable (2026-10-15) — ce qui a été appliqué

Numéros de ligne du §3 vérifiés exacts. Points confirmés dans le code puis corrigés :

| # | Point | Où c'est corrigé |
|---|---|---|
| B1 | `get_apikey_valid` ne permet pas la lecture seule (rend `None` sans le droit de la route) | **Résolu autrement** (mainteneur) : on ne touche pas à `get_apikey_valid` ; la clé Dolibarr reçoit le droit `product` (lecture et écriture). C13, §5.3 |
| B2 | Retour de consigne : prix faux (D11) et `AttributeError` → `500` sur tout le catalogue si la consigne manque | C6 (`CR` écarté, renvoyé à 06-D), §5.1 (erreur nommée), test 3 |
| I1 | L'ordre des règles du compte changeait (`VR` sorti) | §5.1 : `compte_pour_produit(…, monnaie_de_la_ligne)` garde toutes les règles dans l'ordre |
| I2 | `updatePrice` écrit l'historique à chaque appel ; `create` en écrit déjà une | C3, C11, test 8, mutation |
| I3 | `updatePrice` sans 5ᵉ argument remet le minimum à 0 | C3, mutation |
| I4 | `setCategories` retire les catégories posées à la main | C7, test 8 bis, mutation |
| I5 | `update` ne réécrit pas le type sans `$updatetype = true` | C4 |
| I6 | `ETag` dépendant de la langue ; `W/` confirmé (nginx) | §5.2, test 7 bis |
| I7 | Tests : `CR`, `U` (la régression `POST` et l'IP n'ont plus d'objet : permission inchangée) | §7 |
| M1-M10 | `label` 255 ; prefetch inopérant ; `get_solo()` par produit ; la vue est déjà importée par l'API ; renommage en collision ; fût `U` ; mêmes constantes de noms système ; catégorie supprimée ou produit déplacé | C6, C7, §5.1, §5.2, §6 |

Remarques sans changement : multi-entité couvert par R5 (un Dolibarr par lieu) ; les classes
Dolibarr ne contrôlent pas les droits (`activateModule`, `Product::create`,
`Categorie::create`) : page réservée aux admins, cron sous `firstadmin` ; `create()` fait
son propre `begin/commit`, imbriqué dans la transaction par tarif (Dolibarr compte les
niveaux).

## 11. Tests et mutations (2026-10-15)

**Django** — `tests/pytest/test_api_v2_catalogue_comptable.py` : 14 tests, 12 rouges avant
le code (les 2 verts : droit et réponse par défaut, qui ne changent pas). Suite complète :
**3886 passed, 1 failed, 1 xfailed**. L'échec, `test_pos_views_data.py::test_bt_groupement_par_methode_caisse`,
ne vient pas de la session : le test réutilise le premier asset TLF actif du lieu
`lespass`, qui est en base de dev un asset **archivé** (« E2E Fed V2 », laissé par un E2E) ;
la caisse écarte alors la recharge (`product.asset.archive`). Code non touché ; le filtre du
test ne regarde pas `archive`.
Mutations tuées : TVA de la catégorie prise ; règle 2 (catégorie de caisse) sautée ;
recharge comptée comme vente ; consigne ignorée dans la TVA ; tarif archivé filtré ;
préfixe `W/` non retiré ; archivés et non publiés filtrés ; propriété `archived` retirée ;
`translation.override` retiré. Équivalentes (survivent sans défaut) : « 304 avec un corps »
(le protocole et le client de test retirent le corps d'un 304) ; `override(None)` (langue
par défaut du site, fixe elle aussi).

**Module** — `scripts/essai.php`, 1 à 15 : **TOUT EST OK** sur le Dolibarr de dev
(261 produits créés, 106 tarifs écartés, 60 non créés faute de compte : produits de test
et de démo sans catégorie de caisse). Mutations tuées : `status` non posé ; `update` sans
`fetch` ; ETag enregistré malgré une erreur ; `updatePrice` après `create` ; retrait de
toute catégorie non voulue ; `updatePrice` sans prix minimum ; `passageDeLaNuit` qui
ignore le mode ; prochaine occurrence toujours demain (tuée par l'essai 14 renforcé).
Recherche par `ref_ext` en `LIKE` : équivalente (un uuid n'a pas de joker).

**Trouvé en essai réel et corrigé** : produit sans tarif (pas de clé `offers`) ;
`transnoentities()` limité à 5 paramètres (résumé en deux phrases) ; retours à la ligne
du résumé (`dol_escape_htmltag(…, 0, 1)`) ; un essai interrompu laissait le mode « ventes »
(l'essai force maintenant « écritures » au départ et remet le mode d'origine).

**Piège** : la suite pytest écrit dans le lieu `lespass` (produits `TEST_vente…`) ; un essai
du module lancé en même temps voit le catalogue changer entre deux passages. Ne pas lancer
les deux ensemble.

**Dev** : la clé « Dolibarr (dev) 2026-10-15 » du lieu `lespass` a reçu le droit
`product` (C13). Le module a été réactivé (nouvelle tâche `passageDeLaNuit`, l'ancienne
retirée) ; Produits, Services et Catégories activés ; mode remis à « écritures ».

## 12. Relecture Fable du code (2026-10-16) — 9 points corrigés

Aucun bloquant. Corrigé (tests vus rouges, puis mutations) :

| # | Défaut | Correction | Preuve |
|---|---|---|---|
| 1 | Un produit déjà créé restait en vente quand son tarif ne pouvait plus être recopié (compte retiré, plus une vente, plus en euros) ; le résumé disait « Non créé » | `passerHorsVenteSiDejaCree` : statut hors vente, phrase « Passé hors vente » | essai 16, mutation |
| 2 | Type `N` → catégorie « Sélectionner une catégorie » | `productType.label` = « Article de caisse » | test Django, rouge vu |
| 3 | Une requête par tarif (`adhesions_obligatoires`) | préchargement + `.all()` | test du nombre de requêtes, 2 mutations |
| 4 | Heure lue dans le fuseau du serveur, affichée dans celui de la personne | `prochaineOccurrence` lit `dol_tz_string` de la session, sinon le serveur | essai 21, mutation |
| 5 | Réponse sans `results` : 0 produit, ETag gardé | `TiBilletReponseIllisible`, contrôle du produit, du type et du tarif | essai 17, 2 mutations |
| 6 | Noms TiBillet sans échappement dans la fiche de la tâche (`cron/card.php`) | `dol_string_nohtmltag` sur le résumé | essai 18, mutation |
| 7 | Un `304` effaçait le résumé | seule la date avance ; la page dit « résumé du dernier passage complet (date) » | essai 19, mutation |
| 8 | Sans `trim()`, réécriture chaque nuit | `trim()` du libellé et des catégories | essai 20, 2 mutations |
| 9 | README « 24 », module « 19 » | `need_dolibarr_version = 24` | — |

Aussi : ETag testé sur le nom, l'archivage et le compte ; langue figée vérifiée en français.
**Non repris** (suggestions) : classe de base commune au catalogue et à l'import ; phrase
du `403` ; « sha256 du JSON rendu » à reformuler ; deux `SELECT` de catégories par produit ;
ordre d'imports dans `laboutik/views.py`.
