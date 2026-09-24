# LaBoutik : le complément de paiement NFC passe par la confirmation / NFC complement goes through confirmation

## A. Espèces : pavé numérique. CB : rappel du TPE / Cash: keypad. Card: terminal reminder

**Quoi / What :** quand une carte cashless ne suffit pas, la popup « Complément de paiement » proposait ESPÈCE et CB. Un clic validait **tout de suite** le paiement. Maintenant, ces deux tuiles ouvrent la même popup de confirmation qu'un paiement classique (`confirmer()` → `hx_confirm_payment.html`) :
- **CB** : « Encaissez sur le terminal de paiement, puis validez ».
- **Espèces** : pavé numérique, somme donnée, monnaie à rendre. Laisser vide = compte juste.

L'en-tête affiche « Espèce · Reste à payer 9,00 € ». Annuler (ou la croix) ramène à la popup Complément. Elle est seulement masquée, pas vidée.
/ Cash and card tiles on the complement popup now open the regular confirmation popup (keypad / terminal reminder) instead of paying instantly.

**Comment / How :**
1. `hx_complement_paiement.html` : les tuiles font `hx-get confirmer?method=…&total=<reste>&complement=1` vers `#confirm`, et écrivent `moyen_complement` dans `#addition-form`. Fermeture de `#confirm` : voir point 3.
   **Piège htmx 2** : un `hx-on` sur `#complement-form` ne peut pas fermer la popup. `htmx:beforeSwap` se déclenche sur la **cible** (`#messages`), pas sur le formulaire, et un événement ne descend pas vers les enfants. `htmx:afterRequest` arrive après le remplacement de `#messages`, donc après la suppression du formulaire et de son handler.
2. `confirmer()` : lit `complement=1` et le passe au gabarit (`est_complement`).
3. `hx_confirm_payment.html` : si `est_complement`, Valider soumet `#complement-form` (→ `payer_complementaire`) au lieu de `#addition-form` (→ `payer`). Juste avant, on pose un écouteur `htmx:beforeSwap` (`once`) sur `#messages`. Il ferme `#confirm` à l'arrivée de la réponse. Le contrôle de la somme donnée côté navigateur ne change pas.
4. `payer_complementaire()` : lit `given_sum` (en centimes, arrondi, puisque le JS envoie `somme × 100`). Pour les espèces :
   - somme donnée > 0 mais inférieure à la part payée en espèces → 400 « Somme donnée insuffisante ». On vérifie **avant** le débit legacy, donc rien n'est débité.
   - sinon, `give_back` est calculé (même règle que `payer()`). L'écran de succès affiche « Somme donnée » et « Monnaie à rendre ».
   La part payée en espèces vaut `reste − part couverte par le FED legacy`.

**Limite connue / Known limit (pas modifié) :** après une 2ᵉ carte insuffisante, la popup affiche le reste *après* la carte 2. Pourtant, `payer_complementaire` en espèces/CB ne débite que la carte 1 : le montant réellement encaissé est donc le reste après la carte 1. C'était déjà le cas avant. Le pavé le rend visible : si le caissier saisit juste le montant affiché, le serveur répond « Somme donnée insuffisante ».

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templates/laboutik/partial/hx_complement_paiement.html` | Tuiles espèces/CB → `confirmer(complement=1)` ; fermeture de `#confirm` après envoi |
| `laboutik/templates/laboutik/partial/hx_confirm_payment.html` | Branche `est_complement` : soumet `#complement-form` ; libellé « Reste à payer » |
| `laboutik/views.py` | `confirmer()` : `est_complement` ; `payer_complementaire()` : `given_sum`, refus si insuffisant, `give_back` |
| `tests/pytest/test_popups_paiement_v2.py` | 3 tests (confirmation en mode complément / classique, tuiles vers confirmer) |
| `tests/pytest/test_paiement_complementaire.py` | 3 tests (monnaie à rendre, somme insuffisante sans débit, compte juste) |

### Tests à réaliser / How to test
Carte avec 2 € de monnaie locale, panier à 5 € sur un PV qui accepte espèces et CB. Payer en CASHLESS → popup « Complément de paiement », reste 3,00 €.
1. **CB** : la popup « CB · Reste à payer 3,00 € » demande d'encaisser sur le TPE. Annuler → retour au Complément. Recliquer CB → Valider → « Paiement réussi ».
2. **Espèces, avec monnaie** : taper 5 sur le pavé → « À rendre 2,00 € ». Valider → succès avec « Somme donnée : 5,00 € » et « Monnaie à rendre : 2 € ». Le tiroir-caisse s'ouvre (Sunmi).
3. **Espèces, compte juste** : Valider sans rien taper → succès, pas de monnaie à rendre.
4. **Espèces, somme trop petite** : taper 1 → le bouton Valider est désactivé (« Il manque 2,00 € »).
5. **2ᵉ carte** : la tuile 2ᵉ CARTE marche comme avant (attente NFC).

Tests auto : `poetry run pytest tests/pytest/test_paiement_complementaire.py tests/pytest/test_popups_paiement_v2.py -q`

### Traductions
Nouvelle chaîne : « Somme donnée insuffisante ». « Reste à payer » existait déjà. `makemessages` n'a **pas** été lancé.

### Migration
- **Migration necessaire / Migration required:** Non
