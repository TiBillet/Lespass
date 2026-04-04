# Session 27 — Long press POS : actions rapides stock caissier

## Contexte

On a construit un système d'inventaire complet (sessions 23-25) :
- App `inventaire/` : modèles Stock, MouvementStock, StockService
- Affichage visuel stock dans le POS (pastilles alerte/rupture/bloquant)
- Broadcast WebSocket temps réel après chaque vente
- Admin Stock avec formulaire HTMX (4 boutons : réception, ajustement, offert, perte)
- ViewSets API existants : `StockViewSet` (reception, perte, offert) dans `inventaire/views.py`
- Serializers existants : `MouvementRapideSerializer` (quantite + motif)

**Ce qui manque :** l'interface POS pour que le caissier fasse des actions stock
sans quitter la caisse (réception rapide, perte, offert, consultation stock).

## Spec de référence

`TECH DOC/Laboutik sessions/Session 03 - Inventaire et stock/SPEC_INVENTAIRE.md` — Section 8 :
- Menu contextuel sur le produit (long press ou bouton `...`)
- Modale HTMX : `hx-get` charge un partial, `hx-post` soumet vers le ViewSet
- Conversion d'unité dans la modale (l'utilisateur saisit en L/kg, conversion côté serveur)
- Toast via `django.messages` + `HX-Trigger`

## Objectif

Implémenter un **appui long** (ou clic droit / bouton `...`) sur une tuile article POS
qui ouvre une modale/panel avec :
1. **Infos stock** : quantité actuelle, unité, état (alerte/rupture)
2. **Actions rapides** : réception (+stock), offert (-stock), perte (-stock)
3. **Lien admin** : vers la fiche Stock dans l'admin (pour ajustement, historique)

Le tout en modale HTMX (pas de navigation, pas de rechargement de page).

## Ce qui existe déjà (ne pas recréer)

- `inventaire/views.py` : `StockViewSet` avec 3 actions (reception, perte, offert)
- `inventaire/serializers.py` : `MouvementRapideSerializer` (quantite + motif)
- `inventaire/services.py` : `StockService` (décrémentation atomique F())
- `laboutik/static/js/articles.js` : gestion clics tuiles, event delegation sur `#products`
- `laboutik/templates/cotton/articles.html` : template tuiles avec `data-uuid`, `data-name`
- `wsocket/broadcast.py` : `broadcast_stock_update()` pour mise à jour temps réel

## Contraintes

- Le long press doit fonctionner sur **tactile** (tablettes Sunmi) ET **souris** (desktop)
- Ne pas casser le clic simple (ajouter au panier) — le long press est un geste distinct
- La modale doit être accessible (aria, data-testid)
- Pas de logique métier côté JS — le serveur calcule, le template affiche
- Permission : seul l'admin connecté (session admin) peut faire les actions stock
- Le clic normal (court) continue d'ajouter l'article au panier comme avant
- Le broadcast WebSocket met à jour les badges stock après l'action (déjà en place)

## Points de design à décider

1. **Geste d'activation** : long press seul ? long press + bouton `...` visible ? clic droit ?
2. **Type d'overlay** : modale centrée ? panel latéral ? dropdown sous la tuile ?
3. **Actions dans la modale** : juste stock (reception/offert/perte) ? Ou aussi modifier le produit (prix, nom) ?
4. **Ajustement** : inclure l'ajustement (inventaire physique) dans la modale POS ou le garder uniquement dans l'admin ?

## Skills à charger

```
/brainstorming
/djc
/unfold
```

## Fichiers à explorer

- `TECH DOC/Laboutik sessions/Session 03 - Inventaire et stock/SPEC_INVENTAIRE.md` (section 8)
- `laboutik/static/js/articles.js` — event delegation, manageKey()
- `laboutik/templates/cotton/articles.html` — structure tuiles
- `laboutik/static/css/articles.css` — styles tuiles
- `inventaire/views.py` — StockViewSet existant
- `inventaire/serializers.py` — MouvementRapideSerializer
- `laboutik/views.py` — vues POS existantes
- `laboutik/templates/laboutik/views/common_user_interface.html` — layout POS principal

## Approche suggérée

/brainstorming pour le design (geste, overlay, UX tactile), puis /writing-plans.
Le ViewSet existe déjà — il faut principalement du JS (détection long press),
un template partial HTMX (modale), et du CSS.
