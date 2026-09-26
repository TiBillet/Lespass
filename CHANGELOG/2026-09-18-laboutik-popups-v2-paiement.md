# LaBoutik : popups V2 — check carte + recharge, choix du paiement, échelle `--k`

## C. Écran d'attente de la carte primaire au style V2 / Primary card screen in V2 style

**Quoi / What :** l'écran d'entrée de la caisse (`views/ask_primary_card.html`) utilise le même composant que les autres attentes NFC : `c-V2.read-nfc`. On y voit :
- une popup centrée, avec le logo TiBillet en tête (le même que l'en-tête de l'écran de vente) ;
- le disque NFC et son onde ;
- « Approchez la carte primaire », puis « Carte du caissier ou du responsable ».

Les erreurs du serveur (carte inconnue, non primaire, aucun point de vente) s'affichent sous la consigne, dans un encart rouge discret, au lieu du grand titre jaune. Il n'y a ni croix ni fermeture par le fond : rien ne se trouve derrière cet écran.

/ The POS entry screen uses the shared V2 NFC wait component: logo, NFC signal, instruction; server errors show in a soft red box under it.

**Composant :** `cotton/V2/read_nfc.html` reçoit deux emplacements optionnels (slots nommés Cotton) :
- `entete`, en haut de la boîte ;
- `contenu`, sous la consigne.

Les autres écrans ne les utilisent pas et restent identiques.

**Logique inchangée / Unchanged logic :**
- `#form-nfc` garde `hx-target=".message-nfc"` et `hx-on::after-request="initNfc()"` ;
- `ask_primary_card.js` est inchangé ;
- aucune modification Python.

Le partial `hx_primary_card_message.html` renvoie maintenant `<p class="card-wait-erreur" role="alert">` au lieu d'un `<h1>` jaune en style inline.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templates/laboutik/views/ask_primary_card.html` | `c-read-nfc` → `c-V2.read-nfc`, logo, zone de message |
| `laboutik/templates/laboutik/partial/hx_primary_card_message.html` | Message d'erreur V2 (`.card-wait-erreur`) |
| `laboutik/templates/cotton/V2/read_nfc.html` | Slots nommés optionnels `entete` et `contenu` |
| `laboutik/static/css/overlay.css` | `.card-wait-logo`, `.card-wait-erreur`, `.message-nfc` neutralisé dans la popup |

### Tests à réaliser / How to test
1. Ouvrir `/laboutik/caisse/` : la popup montre le logo, l'onde NFC, « Approchez la carte primaire ».
2. Poser une carte inconnue (ou via le simulateur NFC) : l'encart rouge « Carte inconnue » apparaît sous la consigne, et on peut reposer une autre carte tout de suite.
3. Poser une carte primaire valide : la caisse ouvre le premier point de vente.
4. Vérifier que le check carte, l'attente cashless et l'attente de la 2ᵉ carte n'ont pas changé.

Nouvelles chaînes pour `makemessages` : « Approchez la carte primaire », « Carte du caissier ou du responsable ».

### Migration
- **Migration necessaire / Migration required:** Non

---

## B. Complément de paiement au style V2 (« ticket de répartition ») / Payment complement in V2 style

**Quoi / What :** `hx_complement_paiement.html` s'affiche quand la carte cashless ne couvre qu'une partie du panier. Il passe dans la popup `.card-modal` avec le design **A** validé sur artefact. On le lit comme une addition, de haut en bas :
- **titre** « Complément de paiement » en haut à gauche, aligné sur la croix ;
- **lignes ticket** : « Total panier 15,00 € », puis « Payé par la carte ·· 4F2A − 6,00 € », avec le détail des monnaies en pastilles ;
- **encart ambre « ⚠ Reste à payer 9,00 € »** : fond et filet ambre, comme l'ancien encadré. C'est le seul bloc teinté de la popup ; en petit écran, le montant passe sous le libellé ;
- **« Payer le reste avec »** puis les tuiles `c-V2.bt.paiement` Espèce / CB / 2ᵉ carte, qui ne répètent plus le montant ;
- la **croix et le fond** ferment la popup et remettent l'URL de l'addition (`initUrlAddition()`), comme l'ancien bouton RETOUR.

L'attente de la 2ᵉ carte (`hx_lire_nfc_complement.html`) passe en `c-V2.read-nfc` : « Approchez la 2ᵉ carte ». Le complément s'efface pendant l'attente (règle « Rien ne s'empile »).

**Logique inchangée / Unchanged logic :** mêmes `onclick` et `hx-get`, `#complement-form` caché inchangé, tuiles hors du formulaire (piège 58), tous les `data-testid` conservés. Aucun changement Python. L'ancien `type="text"` des boutons (invalide) devient `type="button"`.

/ The complement screen moves to the V2 popup: receipt rows, amber "Remaining" box, payment tiles. Same requests, same test ids.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templates/laboutik/partial/hx_complement_paiement.html` | Popup V2, ticket de répartition, encart reste, tuiles |
| `laboutik/templates/laboutik/partial/hx_lire_nfc_complement.html` | Attente 2ᵉ carte en `c-V2.read-nfc` (script inchangé) |
| `laboutik/static/css/overlay.css` | Motifs génériques `.card-titre`, `.card-ticket`, `.card-ticket-ligne`, `.card-encart-reste` |
| `tests/pytest/test_paiement_complementaire.py` | `_extraire_reste()` accepte la virgule (« 9,00 € ») et renvoie toujours un point |
| `tests/pytest/test_popups_paiement_v2.py` | +5 tests : ticket et encart, tuiles hors du formulaire, re-rendu sans 2ᵉ carte, moyens du PV, attente V2 |

Les anciennes classes (`.cascade-badge*`, `.give-back-box`, `.bt-complement-*`) restent : les écrans de succès et « vider la carte » s'en servent encore.

### Tests à réaliser / How to test
1. Point de vente Bar : prendre un panier plus cher que le solde d'une carte qui a un peu de monnaie locale, puis Valider, CASHLESS et lecture de la carte. On voit la popup avec total, payé par la carte, pastilles et encart ambre « Reste à payer ».
2. Toucher ESPÈCE : l'écran de succès s'affiche. Refaire le parcours, puis toucher CB.
3. Refaire le parcours, puis toucher 2ᵉ CARTE : la popup « Approchez la 2ᵉ carte » s'affiche. La croix ramène au complément. Avec une 2ᵉ carte insuffisante, le complément revient sans la tuile 2ᵉ carte.
4. Croix ou fond : la popup se ferme et l'addition reste utilisable.

Attention : `test_paiement_complementaire.py` échoue dans la base de dev actuelle (colonne `postal_address_id` manquante, antérieur à ce travail). La modification de sa regex n'a donc pas pu y être exécutée ; elle est couverte par les tests de rendu de `test_popups_paiement_v2.py`.

Nouvelles chaînes pour `makemessages` : « Payé par la carte », « Payer le reste avec », « Détail de la carte », « 2ᵉ CARTE », « Approchez la 2ᵉ carte ».

### Migration
- **Migration necessaire / Migration required:** Non

---

## A. Confirmation de paiement et fonds insuffisants au style V2 / Payment confirmation and insufficient funds in V2 style

**Quoi / What :** les deux derniers écrans de paiement de l'ancien style passent dans la popup `.card-modal`.
- **`hx_confirm_payment.html`** (dans `#confirm`) : moyen de paiement et total en grand, croix, fond qui ferme, boutons Annuler et Valider.
  - **Espèces :** pavé `c-numpad` (mode ⌫) pour la somme donnée, avec « Somme donnée » et « À rendre » calculés en direct.
    - Sans saisie : « Valider · compte juste », comme avant avec un champ vide.
    - Somme trop petite : la ligne devient « Il manque 2,50 € » en rouge et Valider est bloqué.
    - Sinon : « Valider · rendre 7,50 € ». Sur V2s, le détail du bouton est masqué pour qu'il tienne sur une ligne ; le montant à rendre reste affiché au-dessus.
  - **CB / chèque / offert :** pictogramme dans un disque et une consigne (« Encaissez sur le terminal de paiement, puis validez. », etc.).
  - `askManageAddition()`, `openCashDrawer()`, `#given-sum` (en point décimal) et tous les `data-testid` d'origine sont conservés. La logique d'envoi ne change pas.
- **`hx_funds_insufficient.html`** (dans `#messages`) : même gabarit que « Carte inconnue » :
  - disque rouge, « Fonds insuffisants », « Il manque 3,50 € », puis « carte ·· 8E2A » ;
  - les soldes de la carte en pastilles ;
  - « Compléter avec » suivi des tuiles `c-V2.bt.paiement` Espèce / CB / Cashless, avec les mêmes requêtes qu'avant.

/ The last two legacy payment screens move to the `.card-modal` popup. Cash uses the keypad with live change; submission logic unchanged.

**Corrections / Fixes (`_payer_par_nfc`) :**
- les soldes étaient vides : le template attendait `wallets`, qu'aucune vue ne fournissait. Nouveau helper `_soldes_locaux_pour_affichage(wallet)` (lecture locale, sans Fedow distant) et nouvelle clé de contexte `soldes` ;
- le tag complet s'affichait comme un nom : nouvelle clé `carte_ref` (4 derniers caractères) ;
- la branche « deuxième carte » (`step == 2`) était morte, aucune vue n'envoie `step` : elle est supprimée ;
- `c-status-wallets` n'est plus utilisé ; le fichier est laissé en place.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templates/laboutik/partial/hx_confirm_payment.html` | Popup V2, pavé espèces + monnaie à rendre, consigne CB/chèque/offert |
| `laboutik/templates/laboutik/partial/hx_funds_insufficient.html` | Popup V2 : erreur, pastilles, tuiles « Compléter avec » ; branche `step == 2` supprimée |
| `laboutik/views.py` | `_soldes_locaux_pour_affichage()` ; `soldes` et `carte_ref` dans les deux contextes de `_payer_par_nfc` |
| `laboutik/static/css/overlay.css` | `.confirm-signal`, `.card-manque`, état `.is-insuffisant`, erreur vide masquée, bouton sur une ligne en petit écran |
| `tests/pytest/test_popups_paiement_v2.py` | Nouveau : 5 tests (espèces, CB, fonds insuffisants avec et sans espèces/CB, helper des soldes) |

### Tests à réaliser / How to test
1. Panier, puis Valider, puis ESPÈCE. Sans rien taper : « Valider · compte juste ». Taper 10 pour 12,50 € : « Il manque 2,50 € » en rouge, Valider grisé. ⌫ ⌫ puis 20 : « À rendre 7,50 € ». Valider : écran de succès, monnaie à rendre 7,50 €, et le tiroir s'ouvre (Sunmi).
2. Panier, puis Valider, puis CB : disque carte, consigne, Annuler ramène au choix du paiement, Valider encaisse.
3. Payer en CASHLESS avec une carte pas assez créditée : « Fonds insuffisants », « Il manque … », pastilles de soldes, tuiles. Toucher ESPÈCE : l'écran de confirmation s'ouvre avec le montant manquant.

Nouvelles chaînes pour `makemessages` : « À rendre », « compte juste », « rendre », « Compléter avec », « Encaissez sur le terminal de paiement, puis validez. », « Vérifiez le montant et l'ordre du chèque, puis validez. », « Montant offert : rien à encaisser. ».

### Migration
- **Migration necessaire / Migration required:** Non

---

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
3. **Montant libre** : pavé numérique `cotton/numpad.html` (1-2-3 en haut, virgule, ⌫), montant affiché en grand et bouton « Valider · 12,50 € », comme la maquette. Un petit script dans `hx_card_recharge.html` assemble les touches dans un champ caché : une seule virgule, deux décimales, 7 chiffres au plus. Le serveur valide ensuite avec `RechargeMontantLibreSerializer` (minimum = prix de base du tarif).
4. **Confirmer** : montant, puis nouveau solde de la monnaie.
   - Recharge payante (RE) : tuiles Espèce / CB / Chèque selon le point de vente. Elles postent vers `payer()`.
   - Recharge offerte (RC / TM) : bouton « Offrir », qui poste vers `identifier_client()` (crédit immédiat).

Pendant les étapes 3 et 4, le détail des soldes et les adhésions se retirent, pour que la popup tienne dans les 800 px du D3 Mini. À l'étape du pavé, la référence de la carte et le titulaire se retirent aussi (739 px mesurés en 1280 × 800).

**Pavé numérique `cotton/numpad.html` refait / Keypad redone :** style de la maquette (`.card-keypad` / `.card-key`) sur l'échelle `--k` (`var(--k, 1)` hors popup). Les touches deviennent de vrais `<button>` avec `data-key`. L'ordre suit la maquette : 1-2-3 en haut, puis `,` 0 et effacer. Un nouveau paramètre `effacer` choisit la dernière touche : `"C"` (défaut, tout effacer) ou `"retour"` (⌫, envoie `Backspace`). La cible est lue dans `data-cible`, et la fonction s'appelle `numpadEnvoyerTouche` (plus de conflit avec le `manageKeyboard` de `keypad.html`).
Compatibilité : `hx_managed_card.html` reçoit toujours `.` et `C` et garde ses touches de 80 px (règle `#mc-container .numpad-touch`). Seuls changent pour lui l'ordre des touches (1-2-3 en haut) et le libellé `,` de la touche décimale, qui envoie toujours `.`.

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
| `laboutik/templates/cotton/numpad.html` | Refait : `<button data-key>`, ordre de la maquette, paramètre `effacer` (C / ⌫), cible via `data-cible` |
| `laboutik/static/css/numpad.css` | Refait au style de la maquette, échelle `var(--k, 1)` ; grandes touches conservées pour `hx_managed_card` |
| `tests/pytest/test_retour_carte_recharge.py` | Nouveau : 10 tests (tuiles, étapes, montant libre avec pavé, parcours payé en espèces et offert) |

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
- Pavé : « Pavé numérique », « virgule », « Effacer le dernier chiffre », « Tout effacer ».
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
4. Montant libre : le pavé s'affiche, et « Valider » reste grisé tant que rien n'est tapé. Taper 1 2 , 5 0 : on lit « 12,50 € » et « Valider · 12,50 € ». ⌫ efface un chiffre. Valider : la confirmation affiche 12,50 €.
5. Écran « carte gérée » : le pavé fonctionne toujours (touches C et virgule).
6. Lire une carte inconnue : message d'erreur. « Scanner une autre carte » relance l'attente.

Tests pytest : `poetry run pytest tests/pytest/test_retour_carte_recharge.py -v`

## Reste à faire / Left to do
- `hx_confirm_payment.html` et `hx_funds_insufficient.html` sont encore dans l'ancien style.
