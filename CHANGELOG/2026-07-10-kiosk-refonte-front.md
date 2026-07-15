# Kiosk — refonte du front + 5 correctifs

**Date :** 2026-07-10
**Migration :** Non

## Ce qui a été fait

Refonte des templates et du CSS de l'app `kiosk`, et correction de cinq bugs trouvés
en relisant le HTML. Aucune migration, aucune vue Python modifiée.

Le parti pris : une borne de recharge est un **distributeur**, pas une page web.
Plus d'ombre portée, plus de carte flottante, plus de survol sur un écran tactile.

### Modifications

| Fichier | Changement |
|---|---|
| `kiosk/static/kiosk/css/tokens.css` | **Neuf** — jetons OKLCH + `@font-face` Luciole/Staatliches |
| `kiosk/static/kiosk/css/kiosk.css` | Réécrit |
| `kiosk/static/kiosk/js/main.js` | Réécrit — thème `data-theme`, code mort purgé |
| `kiosk/templates/kiosk/*.html` | Réécrits |
| `kiosk/templates/kiosk/partial/topbar.html` | **Neuf** |
| `kiosk/templates/kiosk/partial/state_screen.html` | **Neuf** |

### Bugs corrigés

1. **Double compte à rebours** sur `success.html` / `cancel.html` (redirection à ~7,5 s au lieu de 15 s).
2. **`id="tb-kiosque"` en double** dans le DOM pendant l'écran d'attente.
3. **Spinner « paiement en cours » invisible** en mode jour (aucune règle CSS de base).
4. **Voile de chargement** en `position: absolute` au lieu de `fixed`.
5. **Mode nuit** qui écrasait le libellé traduit du bouton par du français codé en dur.

---

## Tests à réaliser

### Test 1 : parcours nominal (mode DEMO)

1. Ouvrir `https://lespass.tibillet.localhost/kiosk/` connecté en admin du tenant.
2. Appuyer sur `+ 20 €` deux fois, `+ 5 €`, `+ 1 €` trois fois.
   → l'afficheur de gauche indique **48**, et le bouton VALIDER indique **48 €**.
   → les deux doivent bouger **ensemble** (mêmes chiffres, aucun décalage).
3. Appuyer sur `EFFACER`.
   → l'afficheur retombe à **0**, en gris.
   → le bouton VALIDER passe en gris et devient `aria-disabled="true"` (inspecteur).
4. Appuyer sur VALIDER avec 0 € : **rien ne doit se passer** (pas de modal).
5. Remettre 10 €, appuyer sur VALIDER.
   → modal de scan, trois chevrons ambrés qui montent, barre de progression 30 s.
6. Choisir une carte du simulateur.
   → écran « Paiement », montant `10,00 €`, illustration carte → TPE animée, spinner **visible**.

### Test 2 : le compte à rebours ne tombe qu'une fois par seconde (régression n°1)

1. Atteindre l'écran de réussite ou d'annulation.
2. Chronométrer : le compteur doit passer de **15 à 12 en 3 secondes**, pas à 9.
3. Console : `window.minuteurRetourAccueil` doit être défini, et **un seul**.

### Test 3 : pas de `#tb-kiosque` en double (régression n°2)

Pendant l'écran « Paiement », dans la console :

```js
document.querySelectorAll('#tb-kiosque').length   // doit valoir 1
```

### Test 4 : mode nuit

1. Appuyer sur « Mode nuit » → fond encre, accent ambre plus clair, libellé devient « Mode jour »,
   icône lune → soleil.
2. Recharger la page : le thème doit être **déjà sombre au premier rendu**, sans flash blanc.
3. Console : `document.documentElement.dataset.theme === "dark"`.
4. Vérifier qu'**aucun** `style="..."` n'a été injecté sur `.card`, `.btn-cancel` ou le spinner.
5. Passer l'interface en anglais → le libellé doit devenir « Night mode » / « Day mode »
   (et non rester en français comme avant).

### Test 5 : responsive

Ouvrir les DevTools, mode responsive, et vérifier ces six tailles :

| Taille | Attendu |
|---|---|
| 1920×1080 | deux colonnes, contenu centré, max 1600 px |
| 1280×720 | deux colonnes |
| 1024×600 | deux colonnes ; le bouton **ANNULER** de l'écran d'attente doit être **entièrement visible** |
| 768×1024 (tablette portrait) | une colonne |
| 375×667 | une colonne, barre VALIDER collée en bas, aucune touche sur deux lignes |
| 320×568 | idem, aucun débordement horizontal |

Aucune barre de défilement horizontale, à aucune taille.

### Test 6 : erreurs métier

Passer une carte inconnue au scan.
→ retour sur l'écran du montant avec un encadré d'erreur à filet brique sous la consigne,
   et le total remis à **0**.

---

## Vérification automatique déjà passée

- `pytest tests/pytest/test_kiosk_*.py` → **17 / 18**.
- Captures Playwright sur 5 écrans × 5 résolutions × 2 thèmes : **0 débordement**,
  **0 cible tactile < 44 px**, **0 libellé replié**, **0 action hors écran**.
- Compte à rebours mesuré : `15 → 12` en 3,2 s sur `success` et `cancel`.

---

## Points ouverts pour le mainteneur

1. **`test_module_kiosk_existe_et_defaut_false` échoue** — sans lien avec cette session.
   Le test lit `Configuration.get_solo().module_kiosk` sur la **base de dev**, où le module a été
   activé, au lieu de tester le défaut du champ. À corriger côté test.
2. **`makemessages` + `compilemessages`** à lancer (liste des nouvelles chaînes dans le `CHANGELOG.md`).
3. **`collectstatic`** nécessaire en prod : `tokens.css` est un fichier neuf.

## Code mort supprimé

`index.js`, `cash.js`, `CB.js` et `recapsolde.js` ont été supprimés de
`kiosk/static/kiosk/js/` **et** de leurs copies `collectstatic` dans `www/static/kiosk/js/`.

Aucun n'était chargé : `base.html` ne charge que `nfc.js` et `main.js`. Les clients Cordova et
Pi référencent leur **propre** `assets/js/index.js`, pas celui du kiosque. `index.js` aurait de
toute façon planté s'il avait été chargé (`messageElement.textContent` sur un `null`).

## Compatibilité

- Les hooks JS publics sont **inchangés** : `totalAmount`, `selectAmount()`, `clearAmount()`,
  `toggleDarkMode()`, `readNfc()`, `rfid`. `nfc.js` n'a pas été touché.
- Les contrats HTMX sont inchangés : `hx-post` refill, `hx-target="#tb-kiosque"`,
  `hx-trigger="confirmed"`, swap OOB du websocket.
- `wsocket/consumers.py` rend `success.html` / `cancel.html` avec un **contexte vide, hors requête**.
  Les deux templates n'utilisent donc aucune variable, aucun `csrf_token`, aucun processeur de contexte.
- Seul changement d'attribut : `tag-id` → `data-tag-id` sur `#scan_button` (lu uniquement par
  `hx-vals` et `listenTagId`, tous deux dans `sweet_scan_button.html`).
