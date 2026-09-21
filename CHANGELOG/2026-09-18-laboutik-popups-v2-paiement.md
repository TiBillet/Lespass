# LaBoutik : popups V2 — check carte + recharge, choix du paiement, échelle `--k`

## 0. Popup « check carte » terminée, la recharge fonctionne / Card check popup done, top-up works

**Quoi / What :** La popup qui s'ouvre après la lecture d'une carte affiche maintenant les vraies données :
- la référence de la carte (4 derniers caractères) ;
- le titulaire : prénom, « Carte liée » ou « Carte anonyme » ;
- le solde total ;
- le détail par monnaie, en **pastilles** (une par monnaie, nom en gris et montant en gras, à la ligne si besoin), avec la pastille réseau FED ;
- les adhésions actives.

Une carte inconnue affiche un message et un bouton « Scanner une autre carte ».

La zone « Recharger » fonctionne. Elle avance par étapes, rendues par le serveur (HTMX) :
1. **Quoi** : une tuile par produit de recharge **du lieu** (monnaie locale, cadeau, temps), **depuis n'importe quel point de vente**. Toucher la tuile déjà choisie la désélectionne.
2. **Combien** : les tarifs du produit (1, 5, 10, Montant libre).
3. **Montant libre** : champ de saisie validé par `RechargeMontantLibreSerializer`. La virgule est acceptée, le minimum est le prix de base du tarif.
4. **Confirmer** : montant, puis nouveau solde de la monnaie.
   - Recharge payante (RE) : tuiles Espèce / CB / Chèque selon le point de vente. Elles postent vers `payer()`.
   - Recharge offerte (RC / TM) : bouton « Offrir », qui poste vers `identifier_client()` (crédit immédiat).

Pendant les étapes 3 et 4, le détail des soldes et les adhésions se retirent, pour que la popup tienne dans les 800 px du D3 Mini.

/ The card popup shows real data (reference, holder, total, per-currency detail, FED, memberships, unknown-card state). The "Top up" zone works step by step (what, how much, free amount, confirm). Paid top-ups post to `payer()`, free ones to `identifier_client()`.

**Pourquoi / Why :** Les boutons « Recharger » de la maquette étaient écrits en dur et ne faisaient rien.

**Choix d'architecture / Design choice :** aucune nouvelle logique de paiement. Les champs envoyés à la fin (`repid-<produit>--<tarif>`, `custom-…`, `total`, `tag_id`, `uuid_pv`, plus `tag_id_cm` / `hostname_client` lus dans `#addition-form`) sont exactement ceux du panier. Ce sont donc `payer()` et `identifier_client()`, déjà testés, qui font la recharge, les lignes comptables et l'écran de succès. La nouvelle vue `recharge_carte()` ne fait que du rendu : elle n'écrit rien en base.
Cela tranche la question « une rangée ou deux étapes » : on choisit d'abord la monnaie, puis le montant. Le moyen de paiement ne vient qu'à la confirmation, et seulement pour les recharges payantes. C'est le modèle de données : un produit de recharge par monnaie, avec ses tarifs.

**Règle métier modifiée : recharge depuis tous les points de vente (décision du 2026-09-18) / Business rule changed: top-up from every POS :**
Avant, `payer()` ignorait un article qui n'était pas dans le M2M du point de vente. Les recharges n'étaient donc possibles que sur les PV « Cashless » et « Mix ». Désormais, `_extraire_articles_du_panier()` accepte aussi les produits de recharge du lieu (publiés, non archivés, liés à un Asset actif, via le helper `_produits_de_recharge_du_lieu()`), même hors M2M. La vente est enregistrée sur le point de vente où elle a lieu (ex : le Bar). Les autres produits restent limités au M2M du PV.
/ `_extraire_articles_du_panier()` now also accepts the venue top-up products outside the POS M2M; the sale is recorded on the current POS.

**Limites connues / Known limits :**
- Espèces = paiement exact : pas de saisie de la somme donnée, et le tiroir-caisse ne s'ouvre pas (`openCashDrawer` n'existe que dans `hx_confirm_payment.html`).
- Après le succès, le bouton RETOUR appelle `manageReset()`, qui vide aussi le panier en cours s'il y en avait un.
- Sans point de vente connu (pas de `#addition-form` dans la page), la zone « Recharger » ne s'affiche pas.
- Dans la base de dev, toute monnaie de test restée active apparaît dans les tuiles de tous les PV. `test_retour_carte_recharge.py` archive et désactive les siennes en fin de module.
- Le lien « Historique » est masqué (TODO) tant que la vue n'existe pas.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `ICONES_RECHARGE`, `_produits_de_recharge_du_lieu()`, `_construire_contexte_recharge()`, `retour_carte()` lit `uuid_pv` et passe `recharge`, nouvelle action `recharge_carte()` (GET, rendu seul) ; `_extraire_articles_du_panier()` accepte les recharges hors M2M du PV |
| `laboutik/serializers.py` | `RechargeMontantLibreSerializer` |
| `laboutik/templates/laboutik/partial/hx_card_feedback.html` | Réécrit avec les vraies données, l'état d'erreur et l'inclusion de la zone de recharge |
| `laboutik/templates/laboutik/partial/hx_card_recharge.html` | Nouveau : zone « Recharger » (4 étapes) |
| `laboutik/templates/laboutik/partial/hx_check_card.html` | `hx-include` de `uuid_pv` ; `<h1>` en doublon supprimé |
| `laboutik/static/css/overlay.css` | Titulaire, pastilles de monnaies (`.card-pastilles`), adhésions, erreur, montant libre (`.card-clavier` porté), montants 3 par ligne |
| `tests/pytest/test_retour_carte_recharge.py` | Nouveau : 9 tests (tuiles, étapes, montant libre, parcours payé en espèces et offert) |

### Migration
- **Migration necessaire / Migration required:** Non

---

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
Nouvelles chaînes, à passer dans `makemessages` par le mainteneur :
- Popups V2 : « Approchez la carte », « lecture du solde », « Choisir un moyen de paiement ».
- Recharge : « Recharger », « Montant », « Montant libre », « Retour aux montants », « Nouveau solde %(nom_monnaie)s », « Payé en », « Offrir », « carte », « Solde total », « Détail du solde », « Scanner une autre carte ».
- Sérialiseur : « Saisissez un montant », « Montant invalide », « Le montant doit être positif », « Montant trop élevé », « Montant inférieur au minimum ».

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

## Tests à réaliser : recharge depuis le check carte / How to test: top-up from the card check
1. Sur **n'importe quel** point de vente (ex : Bar), toucher « check carte » puis lire une carte. On voit le solde, les pastilles de monnaies et les tuiles « Recharger ».
2. Choisir la monnaie locale puis 5 €. On voit « + 5,00 € », le nouveau solde et les tuiles Espèce / CB. Toucher Espèce : l'écran de succès s'affiche. Refaire un check carte : le solde a augmenté de 5 €.
3. Choisir une monnaie cadeau puis 10, et toucher « Offrir » : la carte est créditée, sans paiement.
4. Montant libre : taper « abc », on voit « Montant invalide ». Taper « 12,50 » : la confirmation affiche 12,50 €.
5. Lire une carte inconnue : message d'erreur. « Scanner une autre carte » relance l'attente.

Tests pytest : `poetry run pytest tests/pytest/test_retour_carte_recharge.py -v`

## Reste à faire / Left to do
- `hx_confirm_payment.html` et `hx_funds_insufficient.html` sont encore dans l'ancien style.
