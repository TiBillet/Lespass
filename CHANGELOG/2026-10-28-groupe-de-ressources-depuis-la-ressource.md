# Groupes de ressources : gérés depuis la ressource / Resource groups: managed from the resource

**Date :** 2026-10-28
**Migration :** Oui (`booking 0010_suppression_image_groupe_de_ressources`)

## Resume / Summary
**Quoi / What :** l'entrée « Groupe de ressources » quitte le module Réservations de l'admin. On choisit le groupe dans le formulaire de la ressource (liste déroulante « Groupe »), et le menu « ⋮ » à côté permet d'en créer ou d'en modifier un. La fiche d'un groupe n'ajoute plus de ressource : elle liste et modifie seulement les ressources existantes.
/ The "Resource groups" entry leaves the admin booking module. The group is picked in the resource form, whose "⋮" menu creates or edits a group. A group page no longer adds resources.

**Pourquoi / Why :** une ressource exige un produit, et l'inline du groupe ne montrait pas ce champ. Ajouter une ressource depuis un groupe plantait en 500 (`IntegrityError` sur `booking_resource.product_id`, Sentry BILLETTERIE-COOP-VA).
/ A resource needs a product, which the group inline did not show: adding one crashed with a 500.

**Aussi / Also :** le champ `ResourceGroup.image` (une URL) est supprimé. Il n'était affiché nulle part.
/ `ResourceGroup.image` (a URL) is removed: it was never displayed.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/resources.py` | `ResourceInline.has_add_permission` renvoie `False`. `ResourceGroupAdmin` reste enregistré : le menu « ⋮ » du champ Groupe en a besoin. |
| `booking/models.py`, `booking/migrations/0010_suppression_image_groupe_de_ressources.py` | Suppression du champ `ResourceGroup.image`. |
| `Administration/admin/dashboard.py` | Retrait de l'entrée « Groupe de ressources » et de sa description/catégorie. |
| `tests/pytest/test_admin_groupe_de_ressources.py` | Nouveau : menu sans groupe, lien de création sur la ressource, groupe qui ne crée pas de ressource. |

---

## Comment tester (a la main) / Manual test
### Test 1 — le menu
1. Admin → Réservations.
2. Attendu : Produit ressources, Ressources, Calendriers… mais plus « Groupe de ressources ».

### Test 2 — créer un groupe depuis une ressource
1. Ressources → Ajouter.
2. Champ « Groupe » → menu « ⋮ » → Ajouter. Remplir le nom, enregistrer.
3. Attendu : la fenêtre se ferme, le nouveau groupe est sélectionné dans la liste.

### Test 3 — la fiche d'un groupe
1. Depuis le menu « ⋮ » → Modifier, ouvrir un groupe.
2. Attendu : les ressources du groupe sont listées, sans bouton « Ajouter une ligne ».

### Verifs
- `docker exec lespass_django poetry run pytest tests/pytest/test_admin_groupe_de_ressources.py -v`
