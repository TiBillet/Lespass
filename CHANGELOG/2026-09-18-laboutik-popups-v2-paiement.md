# LaBoutik : popups V2 — choix du paiement + socle commun (échelle `--k`)

## 1. Popup après « Valider » au style de la maquette / Payment popup in the mockup style

**Quoi / What:** Après « Valider », le choix du paiement s'affiche maintenant dans la popup centrée de la maquette (`TEMP-tibillet-laboutik-main/caisse`, `renderPaymentModal`) :
- le total, une seule fois en haut ;
- une grille de tuiles (pictogramme + nom) ;
- une croix en haut à droite, et un toucher sur le fond qui ferme aussi.

Les trois cas (consigne, identification client, vente normale) et le point de vente cashless utilisent ce gabarit. L'attente de la carte pour un paiement cashless (`hx_read_nfc.html`) aussi.
/ The payment choice after "Validate" now uses the mockup's centred popup: total once at the top, tile grid, close cross, backdrop tap closes. All branches, and the cashless card wait, share it.

**Pourquoi / Why:** Intégration de la refonte de l'écran de vente. L'ancien écran était une page pleine avec de gros boutons colorés.

**Logique inchangée / Unchanged logic:** mêmes conditions Django, mêmes `hx-*` et mêmes `data-testid`. Aucune modification Python ni JS.

## 2. Agrandissement « par l'échelle » / Scale-based enlargement

**Quoi / What:** Toutes les tailles de la popup (boîte, marges, polices, icônes, tuiles) valent `valeur maquette × --k`.
- `--k = 1` sur le terminal de poche (V2s) : identique à la maquette.
- `--k = 1.4` sur un écran d'au moins 600 × 600 (D3 Mini) : boîte de 532 px.

La hauteur suit le contenu : on retire l'ancien `min-height: 50%`, qui étirait la boîte à vide. Plancher de 14,5 px (`--fs-min`) sur les petits textes. Croix d'au moins 44 px. L'attente NFC est un disque teinté d'où sort une onde (coupée si `prefers-reduced-motion`).

Un seul voile : `#messages` / `#confirm` deviennent transparents quand ils contiennent une `.card-modal`. Rien ne s'empile : quand une popup s'ouvre dans `#confirm`, celle de `#messages` s'efface, puis revient à la fermeture.

/ Every popup size = mockup value × `--k` (1 on pocket, 1.4 on large screens). Height hugs content, 14.5px floor, one veil, no stacking.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/static/css/overlay.css` | Bloc « POPUP CENTREE V2 » réécrit (échelle `--k`, tuiles, grille 3 par ligne / 2 × 2 pour 4 tuiles, voile unique, pas d'empilement, fragments recharge prêts) ; fonds de `.cf-wrapper` / `.nfc-container` restaurés |
| `laboutik/static/css/palette.css` | Jetons `--shade-3` et `--modal-veil` |
| `laboutik/templates/cotton/V2/bt/paiement.html` | Tuile de paiement V2 : `{{ attrs }}` transmis, pictogrammes SVG de la maquette, `pressed` optionnel |
| `laboutik/templates/cotton/V2/read_nfc.html` | Paramètres `title` / `hint`, halo NFC, fermeture par le fond, ARIA dialog. Script inchangé |
| `laboutik/templates/cotton/V2/bt/return.html` | `aria-label` traduit, commentaire |
| `laboutik/templates/laboutik/partial/hx_display_type_payment.html` | Popup V2 (logique et `data-testid` conservés) |
| `laboutik/templates/laboutik/partial/hx_read_nfc.html` | Attente cashless en V2 |

### Migration
- **Migration necessaire / Migration required:** Non

### Traductions / Translations
Nouvelles chaînes, à passer dans `makemessages` par le mainteneur : « Approchez la carte », « lecture du solde », « Choisir un moyen de paiement ».

## Tests à réaliser / How to test

Dans le navigateur, en 1280 × 800 puis en 360 × 720 :
1. **Vente normale** : ajouter un article, puis Valider. On voit le total en haut, puis 3 à 5 tuiles. Avec exactement 4 tuiles, la grille est en 2 × 2.
2. **Cashless** : toucher CASHLESS. La popup « Approchez la carte / Cashless » remplace la première. La croix ramène au choix du paiement.
3. **Espèces / CB** : l'écran de confirmation (ancien style) s'ouvre bien.
4. **Consigne** : panier avec seulement un retour de consigne. On voit « Rembourser la consigne par : » avec les tuiles Cashless et Espèces.
5. **Recharge ou adhésion** : on voit les tuiles « Scanner une carte TiBillet » et « Saisir email / nom » (la seconde est absente s'il y a une recharge).
6. **Point de vente cashless (comportement C)** : Valider ouvre directement « Approchez la carte ».
7. **Check carte** : attente avec l'onde, puis le solde. Les proportions suivent l'échelle ; il n'y a plus de boîte étirée.
8. Toucher le fond ferme la popup. Pas de défilement horizontal en 360 px.

Tests pytest : `poetry run pytest tests/pytest/test_pos_retour_consigne.py tests/pytest/test_pos_paiement_cheque.py tests/pytest/test_billetterie_pos.py -q`

## Reste à faire / Left to do
- Popup après le check carte (`hx_card_feedback.html`) : données réelles, erreur, recharge. Voir le plan « Lot 1 ».
- `hx_confirm_payment.html` et `hx_funds_insufficient.html` sont encore dans l'ancien style.
