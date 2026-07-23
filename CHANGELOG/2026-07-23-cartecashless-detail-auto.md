# Cartes cashless invisibles : fabrication auto de la génération / Cashless cards invisible: auto-create the card generation

**Date :** 2026-07-23
**Migration :** Non

## Resume / Summary
**Quoi / What :** À l'ajout d'une carte cashless dans l'admin, si le gestionnaire
ne choisit pas de génération (`detail`), une génération par défaut du lieu courant
est désormais fabriquée (ou réutilisée) automatiquement, puis rattachée à la carte.
/ When adding a cashless card in the admin without picking a generation (`detail`),
a default generation for the current venue is now auto-created (or reused) and
attached to the card.

**Pourquoi / Why :** Le champ `detail` était facultatif. Une carte créée sans
`detail` restait invisible dans la liste admin (le changelist filtre sur
`detail.origine == lieu courant`) ET n'était jamais créée chez Fedow (le flux Fedow
n'est déclenché que si `detail` est présent). La carte était donc fantôme et cassée
(ni `number` ni `uuid`). / The `detail` field was optional. A card created without a
`detail` stayed invisible in the admin list (changelist filters on
`detail.origine == current venue`) AND was never created on Fedow. It was a broken
ghost card (no `number`, no `uuid`).

Confort d'affichage complémentaire : le formulaire d'ajout **pré-sélectionne** la
génération **la plus haute (la plus récente)** du lieu. Si le lieu n'en a aucune, le
select reste vide sans planter (le filet de `clean()` prend le relais).
/ Extra display comfort: the add form pre-selects the venue's highest (most recent)
generation; if the venue has none, the select stays empty without crashing.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `QrcodeCashless/admin.py` | Nouveau helper module-level `_obtenir_la_generation_par_defaut_du_lieu()` (réutilise la génération la plus haute, sinon crée la génération 1) ; branché dans `CarteCashlessAddForm.clean()` quand `detail` est vide ; `__init__` du form qui pré-sélectionne la génération la plus haute |
| `tests/pytest/test_carte_cashless_admin.py` | 3 tests : rattachement au lieu + idempotence du helper ; carte sans génération choisie visible dans la liste ; pré-sélection de la génération la plus haute |

---

## Comment tester (a la main) / Manual test

### Test 1 — scénario nominal (le bug corrigé)
1. Se connecter à l'admin d'un lieu appairé à Fedow (`admin@admin.com`).
2. Cartes NFC → « Ajouter ».
3. Saisir uniquement un **Tag ID** (8 caractères hexa), **laisser le select
   « génération » vide**, enregistrer.
4. Vérification attendue : la carte **apparaît** dans la liste, avec un `number` et
   un `wallet`/UUID renseignés. Une génération par défaut a été créée pour le lieu.

### Test 2 — génération déjà existante réutilisée
1. Créer d'abord une génération via le bouton « + » à côté du select (ex. génération 2).
2. Ajouter une carte en laissant le select vide.
3. Vérification : la carte est rattachée à une génération **du lieu** (la première
   existante), pas à une génération d'un autre lieu.

### Test 3 — lieu non appairé à Fedow
1. Sur un lieu sans configuration Fedow, tenter d'ajouter une carte.
2. Vérification : erreur inline « Ce lieu n'est pas appairé à Fedow » — aucune carte
   fantôme n'est créée.

### Verifs DB / Playwright
- `docker exec lespass_django poetry run pytest tests/pytest/test_carte_cashless_admin.py -q`
  (nécessite une base de dev seedée : tenant `lespass` présent).
