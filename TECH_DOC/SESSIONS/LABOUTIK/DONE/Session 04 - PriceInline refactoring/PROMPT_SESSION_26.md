# Session 26 — Refactoring PriceInline par proxy product

## Contexte

On a un seul `PriceInline` (dans `Administration/admin/products.py`) partagé entre
4 admins : ProductAdmin, TicketProductAdmin, MembershipProductAdmin, POSProductAdmin.
Chacun a des besoins différents sur les champs prix :
- Billetterie : stock (jauge), max_per_user
- Adhésions : subscription_type, recurring_payment, iteration, commitment
- POS : contenance (volume par vente, ex: pinte=50cl)

Actuellement on empile des conditions dans `get_fields()` et `PriceChangeForm.__init__()`.
C'est fragile et pas FALC.

## Objectif

Créer un PriceInline par proxy :
- `PriceInline` (base) : name, prix, free_price, publish, order
- `TicketPriceInline` : + stock, max_per_user
- `MembershipPriceInline` : + subscription_type, recurring_payment, iteration, commitment, adhesions_obligatoires
- `POSPriceInline` : + contenance, avec show_change_link bien visible

Chaque inline a ses propres fields, son propre formulaire si nécessaire, et zéro condition.

## Contraintes

- Rétrocompatible : pas de migration, les données ne changent pas (c'est du admin-only)
- Le PriceAdmin standalone (/admin/BaseBillet/price/) garde son get_fieldsets conditionnel
  (il affiche le bon fieldset selon le product lié — c'est un cas différent de l'inline)
- Le bouton "modifier le prix" dans l'inline POS doit être visible sans hover
- Tester que les 4 pages admin fonctionnent : ProductAdmin, TicketProductAdmin,
  MembershipProductAdmin, POSProductAdmin
- Garder le clean_prix (validation > 1€) dans un form partagé ou dupliqué

## Fichiers à explorer

- `Administration/admin/products.py` : PriceInline, PriceInlineChangeForm, les 4 *Admin
- `Administration/admin/prices.py` : PriceAdmin, PriceChangeForm
- `BaseBillet/models.py` : Price model (tous les champs)
- Skill /unfold pour les patterns inline
- Skill /djc pour les conventions

## Approche suggérée

/brainstorming puis /writing-plans. Pas de sur-ingénierie : 4 classes inline
qui héritent d'une base, chacune avec ses fields en dur. Pas d'abstraction magique.
