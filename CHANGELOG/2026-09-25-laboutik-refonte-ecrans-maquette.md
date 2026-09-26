# LaBoutik : écrans de la caisse au style de la maquette / LaBoutik: POS screens in the mockup style

**Date :** 2026-09-25
**Migration :** Non
**Commits :** `56425264`, `f586fcf4`, `44ecdf39` (+ tests `tests/e2e/test_tarif_popup.py`, non committés)

## Resume / Summary

**Quoi / What :** les écrans de la caisse qui gardaient l'ancien style (plein écran de
couleur saturée, icônes FontAwesome, tailles en rem, Luciole) passent au style de la
maquette `TEMP-tibillet-laboutik-main` : popups `.card-modal`, jetons OKLCH de `palette.css`.
/ POS screens still in the old style move to the mockup style: `.card-modal` popups, OKLCH tokens.

**Pourquoi / Why :** homogénéiser la caisse avec l'écran de vente et l'écran Ventes déjà
portés. Une erreur, un succès ou une clôture s'affichent maintenant dans la même famille
de boîtes que le paiement.
/ Make the POS consistent with the already-ported sale and Sales screens.

### Écrans refaits / Redesigned screens

| Écran / Screen | Avant / Before | Après / After |
|---|---|---|
| Bouton **Valider** | `scale(.98)` à l'appui, encre `--vert04` | Relief « touche » de la maquette : tranche 4 px `--valid-deep`, descente instantanée, remontée 170 ms, encre `--valid-ink` |
| **Succès de paiement** (`hx_return_payment_success.html`) | Plein écran vert, icône FA 4rem, « RETOUR » | Popup : pastille verte + « Paiement réussi », monnaie à rendre en gros, total / moyen, alertes en teinte warn, « Imprimer » + « Nouvelle vente » |
| Cartes cashless dans le succès (`_succes_carte.html`, nouveau) | Pastilles « nom : solde » | Un cadre par carte : **avant → montant payé → après** ; tableau Monnaie · Avant · Payé · Après si plusieurs monnaies ; étiquette « 1re / 2e carte » |
| **Message serveur** (`hx_messages.html`) | Plein écran `var(--{{ msg_type }})`, icône FA 3,5rem, texte noir | Popup : pastille teintée (warn / danger / nfc / valid), le message en titre, un bouton « Retour » (focus à l'ouverture) |
| **Retour d'impression** (`hx_print_feedback.html`) | Fond saturé plein, texte noir 1,4rem | Bandeau teinté + pastille ; « Impression impossible » en titre pour les erreurs |
| **Rapport de clôture** (`hx_cloture_rapport.html`) | `.BF-col`, 5 styles inline, emojis, montants « 12.5 » | Blocs de l'écran Ventes : total, exports PDF / CSV / email, tableaux par moyen et TVA ; montants via `\|euros` |
| **Correction du moyen de paiement** (`hx_corriger_moyen_paiement.html`) | Radios en `display:none` (inaccessibles au clavier), contraste faible | Contrôle segmenté `.seg` (radio réel en `sr-only`), `.note-preview`, boutons de popup |
| **Vider carte** (3 écrans) | Lecteur NFC V1, plein écran orange puis vert, boutons `bt-basic` | Lecteur V2 ; confirmation en popup orange (« À rendre en espèces », soldes, 2 choix) ; succès comme « Paiement réussi » |
| **Popup de tarif** (`tarif.js`, `tarif.css`) | Boutons translucides, « RETOUR », champ `<input>` pour le prix libre, pavé maison | Boîte de popup, croix, tarifs fixes en lignes nom / prix ; prix libre = tuile qui ouvre le pavé `cotton/numpad.html` ; poids = même pavé sans virgule, « Ajouter · 8,40 € » |

### Code partagé / Shared code
- **Pavé numérique :** la popup de tarif (construite en JS) clone le composant serveur
  `cotton/numpad.html`, rendu une fois dans des `<template>` de `cotton/articles.html`.
  Nouvelle option `virgule="non"` (saisie entière, g / cl).
- **Règle de saisie d'un montant :** `montantAppliquerTouche()` dans `tibilletUtils.js`
  (virgule unique, 2 décimales, 7 chiffres, effacer). Elle était copiée dans 3 gabarits
  (recharge, fond de caisse, espèces) ; ils l'utilisent maintenant, ainsi que le prix libre.

### Nettoyage / Cleanup
- `overlay.css` : ~800 lignes de CSS mort retirées (81 classes sans utilisateur, 2 id,
  anciens fonds plein écran). `tarif.css` réécrit.
- Supprimés : `cotton/read_nfc.html` (V1), `views/Sunmi_D3_Mini.html`, `views/test.html`,
  `partial/test.html`, `views/cash_float.html`, `views/ventes_V1.html`.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/static/css/addition.css` | Relief « touche » du bouton Valider |
| `laboutik/static/css/overlay.css` | Blocs ÉCRAN DE SUCCÈS, message serveur, retour d'impression, vider carte ; CSS mort retiré |
| `laboutik/static/css/ventes.css` | Rapport de clôture, correction (`.seg`, `.note-preview`), zone de ré-impression |
| `laboutik/static/css/tarif.css` | Réécrit : popup, tarifs fixes neutres, prix libre, poids, remise à zéro des boutons |
| `laboutik/static/css/numpad.css` | Case vide `.numpad-vide` |
| `laboutik/static/css/components.css` | Nettoyage du lecteur NFC V1 |
| `laboutik/static/js/tarif.js` | Popup refaite, clone du pavé, prix libre en tuile |
| `laboutik/static/js/tibilletUtils.js` | `montantAppliquerTouche()` |
| `laboutik/templates/laboutik/partial/hx_return_payment_success.html` | Popup de succès |
| `laboutik/templates/laboutik/partial/_succes_carte.html` | **Nouveau** : cadre d'une carte (avant / payé / après) |
| `laboutik/templates/laboutik/partial/hx_messages.html` | Popup de message |
| `laboutik/templates/laboutik/partial/hx_print_feedback.html` | Bandeau d'impression |
| `laboutik/templates/laboutik/partial/hx_cloture_rapport.html` | Rapport de clôture |
| `laboutik/templates/laboutik/partial/hx_corriger_moyen_paiement.html` | Formulaire de correction |
| `laboutik/templates/laboutik/partial/hx_vider_carte_*.html` | 3 écrans vider carte |
| `laboutik/templates/cotton/numpad.html` | Option `virgule` |
| `laboutik/templates/cotton/articles.html` | `<template>` des pavés de la popup de tarif |
| `laboutik/templates/laboutik/partial/hx_card_recharge.html`, `hx_fond_de_caisse.html`, `hx_confirm_payment.html` | Utilisent `montantAppliquerTouche()` |
| `laboutik/views.py` | `_calculer_soldes_apres_paiement()`, `cartes_apres_paiement` ; Ticket X → `hx_print_feedback.html` |
| `tests/e2e/test_tarif_popup.py` | **Nouveau** : 22 tests Playwright de la popup de tarif (sans serveur) |

### Migration
- **Migration necessaire / Migration required:** Non

### Chaînes à traduire / Strings to translate
« Paiement réussi », « Nouvelle vente », « Avant », « Après », « Sur la carte », « Payé »,
« Monnaie », « 1re carte », « 2e carte », « Carte créditée de », « Retour »,
« Impression impossible », « Total clôturé », « Télécharger le PDF / CSV », « Moyen actuel »,
« Nouveau moyen de paiement », « Raison », « Approchez la carte du client »,
« À rendre en espèces », « Rembourser et réinitialiser la carte », « Rembourser et garder
le compte », « Rendu en espèces », « Imprimer le reçu », « Terminé », « Fermer ».
Textes en dur dans `tarif.js` : « Ajouter », « Prix libre · min », « Fermer le pavé », « Minimum : ».

## Tests a realiser / How to test

### Automatiques
```bash
poetry run pytest tests/pytest/test_pos_*.py tests/pytest/test_paiement_*.py tests/pytest/test_caisse_*.py tests/pytest/test_cloture_*.py tests/pytest/test_corrections_fond_sortie.py tests/pytest/test_pos_vider_carte.py -q
poetry run pytest tests/e2e/test_tarif_popup.py -v   # navigateur, sans serveur
```

### Test 1 : Bouton Valider
1. Ajouter un article, appuyer longuement sur **Valider**.
2. Attendu : le bouton descend de 4 px (tranche verte foncée), remonte au relâchement.

### Test 2 : Succès de paiement
1. Payer en **espèces** en donnant plus que le total → popup verte, « Monnaie à rendre » en gros.
2. Payer en **cashless** (une monnaie) → cadre bleu « Avant → − payé → Sur la carte ».
3. Payer avec une carte qui débite **plusieurs monnaies** → tableau Avant · Payé · Après.
4. « Imprimer » → bandeau « Impression lancée » ; « Nouvelle vente » (ou toucher le fond) → panier vidé.

### Test 3 : Messages et impression
1. Provoquer une erreur (carte inconnue, somme donnée insuffisante) → popup orange, bouton « Retour » focalisé (Entrée ferme).
2. Terminal sans imprimante → « Imprimer » → bandeau orange « Impression impossible ».
3. Ventes → Historique → une vente → **Ré-imprimer** → le bandeau s'affiche **sous** les boutons, « Corriger moyen » reste visible.

### Test 4 : Clôture et correction
1. Ventes → Clôturer toutes les caisses → Confirmer → rapport : total, 4 moyens, TVA, montants « 12,50 € ».
2. Ventes → Historique → une vente espèces → Corriger moyen → choisir au **clavier** (Tab, flèches) → Corriger.

### Test 5 : Vider carte
1. Toucher l'article « Vider carte » → popup de scan V2.
2. Scanner une carte de membre → popup orange, 2 boutons, email affiché.
3. Scanner une carte anonyme → un seul bouton.
4. Rembourser → popup de succès, « Imprimer le reçu », « Terminé ».

### Test 6 : Popup de tarif
1. Article à plusieurs tarifs → lignes neutres nom / prix, relief à l'appui, croix en haut à droite.
2. Prix libre → toucher la tuile → pavé ; 1,50 € sous un minimum de 2 € → refus ; 3,50 € → ajouté, le pavé se replie.
3. Tarif au poids → 350 g à 24 €/kg → « Ajouter · 8,40 € ».
4. Toucher la grille voilée → la popup se ferme.
5. Sur **SUNMI V2s** (360 px) : tout tient, rien ne déborde.

### Test 7 : Pavé partagé
Recharge en montant libre, fond de caisse, somme donnée en espèces : une seule virgule,
2 décimales max, ⌫ efface un chiffre.
