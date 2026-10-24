# Chantier 02 — Afficher ou masquer le stock sur la tuile de caisse

**Date :** 2026-10-24
**Statut :** spec écrite, rien de codé
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
| D2 | Masquer = ne rendre **aucune pastille**, **sauf** « Épuisé » quand l'article est **bloquant** (rupture + vente hors stock interdite). | Une tuile bloquée sans explication est incompréhensible pour le caissier. Pas besoin de lier les deux réglages ni d'ajouter une validation. |
| D3 | Les `data-*` du badge **restent rendus**. | La garde au clic (`articles.js:174`) et le pavé poids (`tarif.js:463`) doivent continuer à bloquer comme le serveur. On ne masque que le visuel. |
| D4 | Rien d'autre ne change : décompte, mouvements, récap quotidien, badges et filtres de l'admin, panel d'appui long. | Le lieu compte toujours son stock. Il le consulte dans l'admin ou dans le panel. |
| D5 | Le réglage se modifie dans la section Stock de la fiche produit (à côté de « Autoriser vente hors stock ») et dans la liste `StockAdmin`. | Même mécanisme que les 3 réglages actuels. |
| D6 | Avec le chantier 01 : un stock **inactif** n'a pas de badge, quel que soit `afficher_en_caisse`. La valeur est gardée et reprend effet au retour du suivi. | Pas d'interaction à coder : le chantier 01 renvoie `stock_quantite = None` avant de lire ce réglage. |

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
    verbose_name=_("Afficher le stock en caisse"),
    help_text=_(
        "Décoché : la tuile n'affiche plus le stock restant. Le stock est toujours "
        "compté. Un article bloqué affiche quand même « Épuisé »."
    ),
)
```

## 5. Endroits à modifier

### 5.1 Caisse

| Fichier | Changement |
|---|---|
| `laboutik/views.py:943` `_construire_donnees_articles` | `article_dict["stock_afficher_en_caisse"] = stock_du_produit.afficher_en_caisse`. |
| `wsocket/broadcast.py` `donnees_badge_stock` | ajoute `"afficher_en_caisse": stock.afficher_en_caisse`. Les 4 producteurs du badge passent par cette fonction. |
| `laboutik/templates/cotton/articles.html` (pastilles, l. 72-79) | `{% if article.stock_afficher_en_caisse %}` → les 2 pastilles actuelles ; `{% elif article.stock_bloquant %}` → « Épuisé » seul. Les `data-*` du `<div>` ne changent pas (D3). |
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
| `Administration/admin/inventaire.py` `StockAdmin` | champ dans `list_display`, `list_editable`, `fields` et les deux listes de `get_fields` ; passé à `creer_stock_initial` dans `save_model`. |
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

### pytest (`tests/pytest/test_stock_fiche_produit.py`, à compléter)

5. Enregistrer la fiche d'un produit avec stock, case laissée cochée → reste `True`.
   Décochée → `False`, quantité inchangée, aucun mouvement.
6. Création par la fiche avec la case décochée → stock créé avec `afficher_en_caisse=False`.

Un test du chantier existant appelle `enregistrer_section_stock` avec un `cleaned_data`
écrit à la main (`test_stock_fiche_produit.py:181-221`, test_05). Il faudra y ajouter
`"stock_afficher_en_caisse": True`, sinon le stock passe en masqué.

Chaque test est vu échouer sur une mutation volontaire avant livraison.

### E2E

Pas d'E2E nouveau : le rendu est couvert par pytest (HTML de la tuile et du badge).
Vérification visuelle dans Chrome à la fin (tuile masquée, tuile bloquée).

## 7. Estimation

| Étape | Durée |
|---|---|
| Champ + migration + caisse + WebSocket (§ 4, § 5.1) | ~45 min |
| Admin (§ 5.2) | ~45 min |
| Tests + vérification visuelle | ~1 h 30 |
| CHANGELOG `CHANGELOG/2026-10-24-stock-afficher-en-caisse.md` | inclus |

**Total : ~3 h.**

Nouvelles chaînes traduisibles (msgid FR) : « Afficher le stock en caisse » et son aide
(modèle et formulaire). Le workflow i18n sera à lancer par le mainteneur.
