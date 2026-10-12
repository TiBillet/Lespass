# Carte primaire : plus de création de carte NFC depuis le formulaire / Primary card: no NFC card creation from the form

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** le champ « Carte NFC » du formulaire d'ajout d'une carte primaire
(`/admin/laboutik/carteprimaire/add/`) n'affiche plus le bouton « + ». On choisit une
carte qui existe déjà, on n'en crée plus depuis ici.
/ The "NFC card" field of the primary card add form no longer shows the "+" button.
An existing card is picked; no card is created from here.

**Pourquoi / Why :** une carte NFC se crée dans l'admin des cartes NFC, qui la déclare
à Fedow. Le bouton « + » ouvrait ce formulaire en popup, au mauvais endroit du parcours.
/ An NFC card is created in the NFC cards admin, which declares it to Fedow. The "+"
popup opened that form at the wrong step of the flow.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/laboutik.py` | `CartePrimaireAdmin.get_form()` : `can_add_related = False` sur le champ `carte` |

---

## Comment tester (a la main) / Manual test
### Test 1 — ajout
1. Admin → Caisse → Cartes primaires → Ajouter.
2. Le champ « Carte NFC » est une recherche (autocomplete), **sans** bouton « + » à côté.
3. Chercher une carte du lieu par numéro ou tag, choisir des points de vente, enregistrer : OK.

### Test 2 — modification
1. Ouvrir une carte primaire existante.
2. La carte NFC est en lecture seule (inchangé), la page s'affiche sans erreur.
