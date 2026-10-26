# Chantier 02 — Afficher ou masquer le stock sur la tuile de caisse

**Date :** 2026-10-24
**Statut :** spec relue (Fable 5, 2026-10-24) et corrigée, rien de codé
**Migration :** Oui — prochaine migration `inventaire` (`AddField`, `default=True`).
Si ce chantier passe avant le chantier 01, c'est `0002` et `actif` prendra `0003`.

---

## 1. Le besoin

Un lieu veut **continuer à compter** le stock d'un article, sans que la caisse affiche
le stock sur la tuile.

Ce chantier est indépendant du chantier 01 (`SPEC.md`, désactiver le suivi) :

| | Chantier 02 — masquer | Chantier 01 — désactiver |
|---|---|---|
| Le stock est décompté | oui | non |
| Mouvements, récap, alertes admin | oui | non |
| Badge sur la tuile | non (sauf « Épuisé » bloquant, § 3) | non |
| Blocage en rupture | oui, si vente hors stock interdite | non |

## 2. Ce qui existe aujourd'hui

Le badge de la tuile (`laboutik/templates/cotton/articles.html:50-80`) a trois états :
- stock sous le seuil d'alerte → pastille orange avec la quantité ;
- rupture (0 ou moins) → pastille rouge « Épuisé » ;
- sinon → rien.

Le WebSocket le remplace après chaque changement
(`laboutik/partial/hx_stock_badge.html`, données de `wsocket/broadcast.py:donnees_badge_stock`).
Le `<div id="stock-badge-…">` porte aussi les `data-*` lus par la garde JS
(`data-stock-quantite`, `data-autoriser-hors-stock`, `data-stock-bloquant`).

## 3. Décisions

| # | Décision | Raison |
|---|---|---|
| D1 | Nouveau champ `Stock.afficher_en_caisse` (`BooleanField`, `default=True`). | Les stocks existants restent affichés. |
| D2 | Masquer = ne rendre **aucune pastille**, **sauf** « Épuisé » quand l'article est **bloquant** (rupture + vente hors stock interdite). Les **messages de refus** continuent d'afficher la quantité : popup `stock_insuffisant` (`laboutik/views.py:8906-8975`) et alerte du pavé poids (« En stock : X », `tarif.js:510-516`). | Un refus doit s'expliquer. Une tuile bloquée sans « Épuisé » serait incompréhensible. Pas besoin de lier les deux réglages ni d'ajouter une validation. Rien à coder pour les refus. |
| D3 | Les `data-*` du badge **restent rendus**. | La garde au clic (`articles.js:174`) et le pavé poids (`tarif.js:465-472`) doivent continuer à bloquer comme le serveur. On ne masque que le visuel. |
| D4 | Rien d'autre ne change : décompte, mouvements, récap quotidien, badges et filtres de l'admin, panel d'appui long de la caisse (« Stock actuel », `article_panel_stock.html`), jauge en % de l'écran de la tireuse (`controlvanne/models.py:330-352`). | Le lieu compte toujours son stock. Il le consulte dans l'admin ou dans le panel. |
| D5 | Le réglage se modifie dans la section Stock de la fiche produit (à côté de « Autoriser vente hors stock ») et dans la liste `StockAdmin`. | Même mécanisme que les 3 réglages actuels. |
| D6 | Avec le chantier 01 : un stock **inactif** n'a pas de badge, quel que soit `afficher_en_caisse`. La valeur est gardée et reprend effet au retour du suivi. | Côté vue, rien à coder : le chantier 01 renvoie `stock_quantite = None`. Côté `hx_stock_badge.html`, le **second** chantier livré emboîte sa condition dans celle du premier. |
| D7 | **(retenue 2026-10-24)** Stock masqué : **pas d'alerte « Stock négatif »** sur l'écran de succès de la vente. | Cette alerte (`hx_return_payment_success.html:153-161`) affiche le nom et la quantité **à chaque vente** tant que le stock reste négatif. C'est justement le cas d'usage du chantier (compté, vente hors stock autorisée, masqué) : le caissier verrait le stock qu'on a voulu lui cacher. |

## 4. Modèle

`inventaire/models.py`, classe `Stock`, après `autoriser_vente_hors_stock` :

```python
# Afficher le stock sur la tuile de la caisse. Décoché : le stock est toujours
# compté, mais la tuile n'affiche plus de pastille. Un article bloqué
# (rupture + vente hors stock interdite) affiche quand même « Épuisé ».
# / Show stock on the POS tile. Unchecked: still counted, no badge shown,
# except "Épuisé" when the item is blocked.
afficher_en_caisse = models.BooleanField(
    default=True,
    verbose_name=_("Afficher le stock sur la tuile"),
    help_text=_(
        "Décoché : la tuile n'affiche plus le stock restant. Le stock est toujours "
        "compté. Un article bloqué affiche quand même « Épuisé ». "
        "Le panel d'appui long et l'admin montrent toujours le stock."
    ),
)
```

Le nom du champ reste `afficher_en_caisse` ; seul le libellé visible parle de la tuile,
car le panel d'appui long de la caisse montre toujours le stock (D4).

## 5. Endroits à modifier

### 5.1 Caisse

| Fichier | Changement |
|---|---|
| `laboutik/views.py:943` `_construire_donnees_articles` | `article_dict["stock_afficher_en_caisse"] = stock_du_produit.afficher_en_caisse`. |
| `wsocket/broadcast.py` `donnees_badge_stock` | ajoute `"afficher_en_caisse": stock.afficher_en_caisse`. Les 4 producteurs du badge passent par cette fonction. |
| `laboutik/views.py:7416` `_creer_lignes_articles` et `:7748` `_creer_lignes_articles_cascade` | D7 : `if stock_devenu_negatif and stock_du_produit.afficher_en_caisse:` avant d'ajouter à `produits_stock_negatif`. |
| `laboutik/templates/cotton/articles.html` (pastilles, l. 73-79) | `{% if article.stock_afficher_en_caisse %}` → les 2 pastilles actuelles ; `{% elif article.stock_bloquant %}` → « Épuisé » seul. Les `data-*` du `<div>` ne changent pas (D3). |
| `laboutik/templates/laboutik/partial/hx_stock_badge.html` | même condition avec `produit.afficher_en_caisse` / `produit.bloquant`. |

Les deux templates restent **identiques** dans leur logique : le commentaire de
`articles.html` le rappelle déjà, ajouter la nouvelle condition au commentaire.

### 5.2 Admin

| Fichier | Changement |
|---|---|
| `Administration/admin/stock_fiche_produit.py` `ChampsStockFicheProduitMixin` | nouveau champ `stock_afficher_en_caisse` (`BooleanField`, `required=False`, `initial=True`, `UnfoldBooleanSwitchWidget`) ; `__init__` le préremplit depuis le stock existant. |
| même fichier, `REGLES_CONDITIONNELLES_SECTION_STOCK` | `"stock_afficher_en_caisse": "stock_suivi == true"`. |
| même fichier, `fieldset_section_stock` | ajouter le champ dans les deux listes (sans stock / avec stock), après `stock_vente_hors_stock`. |
| même fichier, `enregistrer_section_stock` | passer la valeur à `creer_stock_initial` ; 4ᵉ réglage dans `reglages_modifies` (même code que les 3 autres, `update_fields`). |
| `inventaire/services.py` `StockService.creer_stock_initial` | nouveau paramètre `afficher_en_caisse=True`, passé à `Stock.objects.create`. |
| `Administration/admin/inventaire.py` `StockAdmin` | champ dans `list_display`, `list_editable` et les deux listes de `get_fields` (l. 190-204) ; passé à `creer_stock_initial` dans `save_model`. L'attribut `fields` (l. 152-158) n'est pas lu (`get_fields` le remplace) : l'y ajouter pour la cohérence seulement. |
| `stock_fiche_produit.py:113-116` (aide de « Suivre le stock ») | « La caisse affichera le stock restant sur la tuile » → ajouter « (réglable ci-dessous) ». |
| `Administration/templates/admin/inventaire/stock_list_before.html` | le texte d'aide cite les réglages modifiables dans la liste : ajouter celui-ci. |

**Piège à connaître** : `enregistrer_section_stock` lit les réglages pour un stock existant.
Un `BooleanField` non rendu vaut `False` dans `cleaned_data`. Le nouveau champ doit donc
être dans **les deux** listes de `fieldset_section_stock`, comme `stock_vente_hors_stock`.
Sinon, chaque enregistrement de la fiche masquerait le stock. Le test 5 le vérifie.

## 6. Tests

### pytest (`tests/pytest/test_stock_visuel_pos.py`, à compléter)

1. Stock en alerte, `afficher_en_caisse=False` → la tuile n'a pas la pastille orange ;
   `data-stock-quantite` est toujours là.
2. Rupture non bloquante, masqué → pas de pastille « Épuisé ».
3. Rupture **bloquante**, masqué → pastille « Épuisé » présente, `data-stock-bloquant="true"`.
4. `donnees_badge_stock` porte `afficher_en_caisse` ; le HTML de `hx_stock_badge.html` suit
   les mêmes règles que 1 à 3.
5. D7 : vente qui fait passer sous 0 un stock masqué (vente hors stock autorisée) →
   `produits_stock_negatif == []`. Stock affiché → l'alerte est toujours là.

D3 pour le chemin WebSocket est déjà couvert par
`tests/pytest/test_stock_broadcast_hors_vente.py:220-235` (le badge porte
`data-stock-quantite` et `data-autoriser-hors-stock`) : il doit rester vert.

### pytest (`tests/pytest/test_stock_fiche_produit.py`, à compléter)

6. Enregistrer la fiche d'un produit avec stock, case laissée cochée → reste `True`.
   Décochée → `False`, quantité inchangée, aucun mouvement.
7. Création par la fiche avec la case décochée → stock créé avec `afficher_en_caisse=False`.

### Tests existants

Aucun test existant ne casse (vérifié par la relecture : aucun n'affirme ce champ). Quatre
endroits sont à mettre à jour pour rester fidèles, parce qu'une clé absente vaut `False`
(`stock_fiche_produit.py:305`, `bool(donnees_validees.get(...))`) :
- `test_stock_fiche_produit.py` test_03 (l. 142-152) et test_05 (l. 181-219) : `cleaned_data`
  écrit à la main → ajouter `"stock_afficher_en_caisse": True` ;
- même fichier, test_14 (l. 471-491, POST réel de la page d'ajout) → ajouter
  `"stock_afficher_en_caisse": "on"` **et** une assertion `stock.afficher_en_caisse is True` ;
- `tests/e2e/test_garde_stock_au_clic.py:68-120` : les fabriques `_article_a_l_unite` et
  `_article_multi_tarif_en_cl` copient la forme des dicts de la vue → ajouter
  `"stock_afficher_en_caisse": True`.

Chaque test est vu échouer sur une mutation volontaire avant livraison.

### E2E

Pas d'E2E nouveau : le rendu est couvert par pytest (HTML de la tuile et du badge).
Une ligne à ajouter dans un test existant : `"#id_stock_afficher_en_caisse"` dans la liste
des champs cachés tant que « Suivre le stock » n'est pas coché
(`tests/e2e/test_admin_stock_fiche_produit.py:151-156`).
Vérification visuelle dans Chrome à la fin (tuile masquée, tuile bloquée).

## 7. Estimation

| Étape | Durée |
|---|---|
| Champ + migration + caisse + WebSocket (§ 4, § 5.1) | ~45 min |
| Admin (§ 5.2) | ~45 min |
| Tests (nouveaux + 4 mises à jour) + vérification visuelle | ~2 h |
| CHANGELOG `CHANGELOG/2026-10-24-stock-afficher-en-caisse.md` | inclus |

**Total : ~3 h 30.**

Nouvelles chaînes traduisibles (msgid FR) : « Afficher le stock en caisse » et son aide
(modèle et formulaire). Le workflow i18n sera à lancer par le mainteneur.
