# Désactiver le suivi de stock d'un produit / Deactivate a product's stock tracking

**Date :** 2026-10-24
**Migration :** Oui — `inventaire/migrations/0003_stock_actif.py`
(`AddField`, `default=True` : tous les stocks existants restent suivis).
TENANT_APP : `migrate_schemas` sur tous les lieux.

## Resume / Summary

**Quoi / What :** un stock peut être **désactivé** puis **repris**, sans jamais être
supprimé (`Stock.actif`). Un stock non suivi se comporte comme un produit sans stock :
pas de décompte (caisse, tireuse), pas de badge, pas de blocage, pas d'alerte, opérations
manuelles refusées. Il **garde son unité** : un article vendu au kg ou au L continue de
s'afficher et de se facturer dans la bonne unité. La bascule se fait dans le panneau
d'opérations de la section Stock (fiche produit ou fiche du stock) : « Désactiver le
suivi », puis « Suivre le stock — quantité comptée ». La reprise enregistre un ajustement
« Reprise du suivi » dans le journal.
Le stock créé automatiquement pour un fût ou un tarif au poids est désormais **non suivi**
(il ne porte que l'unité).
/ A stock can be deactivated then resumed, never deleted. An untracked stock behaves like
no stock, but keeps its unit (kg / L). Toggle from the Stock operations panel; resuming
records an "AJ" adjustment. The auto-created keg / weight-price stock is now untracked.

**Pourquoi / Why :** activer le suivi était irréversible. Supprimer le stock aurait
effacé son journal (`MouvementStock` en CASCADE) et l'unité des ventes au poids.
/ Tracking could not be turned off; deleting the stock would erase its log and unit.

Spec : `TECH_DOC/SESSIONS/INVENTAIRE/SPEC.md` (chantier 01).

**Changement de comportement :** un fût neuf, ou un produit de caisse qui reçoit un tarif
au poids, sans « Suivre le stock » coché, n'est plus décompté d'office. Pour le compter :
« Suivre le stock » dans la section Stock. Les stocks existants ne changent pas.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `inventaire/models.py` | champ `Stock.actif` + fonction `stock_suivi_du_produit_ou_none` |
| `inventaire/migrations/0003_stock_actif.py` | migration |
| `inventaire/services.py` | `StockService.desactiver_suivi` / `reprendre_suivi` ; alertes du résumé limitées aux stocks suivis |
| `inventaire/serializers.py` | `ReprendreSuiviSerializer` (quantité comptée obligatoire) |
| `inventaire/views.py` | vues « désactiver » / « reprendre » ; refus sur stock non suivi (panneau admin, API réception/perte/offert, débitmètre) |
| `Administration/admin/inventaire.py` | 2 URLs du panneau ; colonne et filtre « Suivi actif » |
| `Administration/admin/stock_fiche_produit.py` | badge « Non suivi » de la liste ; filtre « État du stock » |
| `Administration/admin/products.py` | `save_related` : stock automatique créé non suivi + message |
| `Administration/templates/admin/inventaire/stock_actions_partial.html` | deux états du panneau |
| `Administration/templates/admin/inventaire/stock_actions.html` | commentaire d'en-tête |
| `laboutik/views.py` | tuile, pavé poids, blocage, décompte (2 chemins), message de rupture, panel d'appui long |
| `laboutik/templates/laboutik/partial/hx_stock_badge.html` | badge vide sans `data-*` pour un stock non suivi |
| `laboutik/static/js/tarif.js` | pavé poids : pas de garde si le badge n'a plus de quantité |
| `wsocket/broadcast.py` | `donnees_badge_stock` porte `suivi` |
| `controlvanne/billing.py`, `signals.py`, `models.py` | tirage non décompté ; changement de fût et jauge comme un fût sans stock |
| `A TESTER et DOCUMENTER/stock-onglet-produit.md` | note « pas de bouton pour arrêter » mise à jour |
| `tests/pytest/test_stock_desactivation.py` | 19 tests (nouveau) |
| `tests/pytest/test_inventaire.py` | 3 tests (API, débitmètre, résumé) |
| `tests/pytest/test_controlvanne_facturation_lot2.py` | 1 test (tirage sans décompte) |
| `tests/e2e/test_admin_stock_fiche_produit.py` | 1 parcours désactiver → « Non suivi » → reprendre |

Nouvelles chaînes traduisibles (msgid FR) : « Suivi actif » et son aide, « Désactiver le
suivi », deux textes de confirmation (article / fût), « Le suivi de stock est désactivé. »
et le texte du panneau, « Dernière quantité connue », « Suivre le stock — quantité
comptée », « Suivre le stock », « Reprise du suivi », l'aide de la reprise, les messages
de succès et d'erreur, « Non suivi », « Stock non suivi », les deux messages de
`save_related`. Le workflow i18n est à lancer.

---

## Comment tester (a la main) / Manual test

### Test 1 — désactiver
1. Admin > Produits de caisse > un article avec stock > section Stock.
2. « Désactiver le suivi » → accepter la confirmation.
3. Le panneau affiche « Le suivi de stock est désactivé » et la dernière quantité connue.
4. Liste des produits : la colonne Stock affiche « Non suivi ».
5. Caisse : la tuile n'a plus de pastille ; vendre l'article → la quantité ne bouge pas
   (Inventaire > Stocks) et aucun mouvement n'est créé.

### Test 2 — reprendre
1. Même article : « Suivre le stock » sans quantité → message d'erreur.
2. Saisir 12 → « Suivre le stock » : les opérations reviennent, stock actuel 12.
3. Inventaire > Mouvements de stock : un ajustement « Reprise du suivi ».

### Test 3 — vente au poids
1. Produit de caisse avec un tarif au poids, stock en cl, désactivé.
2. Caisse : le pavé demande toujours des cl, le prix est au litre ; la pesée n'est jamais
   bloquée, même avec « vente hors stock » interdite.

### Test 4 — fût neuf (changement de comportement)
1. Admin > Fûts > ajouter un fût avec un tarif, sans cocher « Suivre le stock ».
2. Message : « Unité de vente enregistrée en centilitres. Le stock n'est pas suivi… ».
3. Section Stock : le panneau propose « Suivre le stock — quantité comptée ».

### Test 5 — fût branché
1. Désactiver le stock du fût d'une tireuse : le texte de confirmation parle de la tireuse.
2. Le tirage continue ; au prochain changement de fût, le réservoir repart à 0.

### Verifs DB / tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stock_desactivation.py tests/pytest/test_inventaire.py tests/pytest/test_controlvanne_facturation_lot2.py -q
docker exec lespass_django poetry run pytest tests/e2e/test_admin_stock_fiche_produit.py -q
```
