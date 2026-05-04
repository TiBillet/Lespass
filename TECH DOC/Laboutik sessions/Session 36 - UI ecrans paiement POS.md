# Session 36 — UI écrans de paiement POS

**Date** : 2026-04-28
**Branche** : V2
**Statut** : Design validé, en attente d'implémentation
**Mainteneur** : Jonas
**Pré-prod** : ~15 jours

## Contexte

Audit frontend laboutik effectué (cf. `Session 35 - Audit front HTMX et NfcReader.md`). Bug visuel rapporté sur l'écran « complément de paiement » (NFC fractionné) : layout cassé, fond manquant, badges débordants. L'audit a mis au jour 10 items HTML/CSS distincts.

Le JS (tarif.js, tibilletUtils.js, vider_carte.js) est traité séparément par Nico. Cette session ne touche que le HTML et le CSS.

## Périmètre

**4 fichiers seulement** :

| Fichier | Type |
|---|---|
| `laboutik/static/css/overlay.css` | CSS — règles `:has()`, classes extraites, breakpoints, `clamp()` |
| `laboutik/templates/laboutik/partial/hx_complement_paiement.html` | Template |
| `laboutik/templates/laboutik/partial/hx_funds_insufficient.html` | Template |
| `laboutik/templates/laboutik/partial/hx_display_type_payment.html` | Template |

**Pas de modification** : JS, Python, modèles, URLs, vues, serializers.

## Hardware cible

- **Sunmi V2s** — 5.45" portrait, ~720×1440 (cas le plus contraint)
- **Sunmi D3 mini** — 10.1" paysage, ~1280×800
- **Desktop** — 1920×1080

## Découpe en 3 lots

Pause + vérification visuelle Chrome après chaque lot.

---

### Lot 1 — Bugs visuels (items 1, 2, 6)

**Estimation** : ~20 min.

**Objectif** : régler le bug rapporté + a11y critique sur les zones « Reste à payer ».

**`overlay.css`** :

1. Ajouter une règle `#confirm:has([data-testid="complement-paiement"])` calquée sur `#messages:has([data-testid="paiement-nfc-insuffisant"])` (overlay.css:885) — fond + layout cohérents avec les autres écrans de paiement.
2. Nouvelle classe `.cascade-badges-list` :
   ```css
   display: flex;
   flex-wrap: wrap;
   gap: 4px;
   justify-content: center;
   max-width: 100%;
   ```
3. Nouvelle classe `.cascade-badge` :
   ```css
   max-width: 100%;
   white-space: nowrap;
   overflow: hidden;
   text-overflow: ellipsis;
   background-color: var(--gris02);
   color: #fff;
   padding: 4px 8px;
   border-radius: 4px;
   ```

**`hx_complement_paiement.html`** :

- Remplacer `<div style="margin: 0.5rem 0; font-size: 0.95rem;">` (ligne 45) par `<div class="cascade-badges-list">`.
- Remplacer chaque `<span class="badge" style="...">` (ligne 47) par `<span class="cascade-badge">`.
- Ajouter `role="alert"` sur `.give-back-box` (ligne 61) — annonce immédiate du « Reste à payer » par le lecteur d'écran.

**`hx_funds_insufficient.html`** :

- Identifier la zone équivalente au « Reste à payer » et y ajouter `role="alert"`.

**Test visuel** : déclencher un paiement NFC fractionné (panier > solde de la carte) → l'écran complément doit avoir un fond cohérent avec les autres écrans de paiement, et les badges cascade doivent passer à la ligne au-delà de 3 entrées sans déborder.

---

### Lot 2 — Extraction des styles inline (items 3, 5, 7)

**Estimation** : ~45 min.

**Objectif** : sortir tous les `style="..."` inline des 3 partials vers `overlay.css`. Maintenance + cohérence visuelle entre les 3 écrans.

**`overlay.css`** — nouvelles classes :

| Classe | Rôle | Valeur principale |
|---|---|---|
| `.bt-paiement-base` | Commun aux 4 boutons paiement | `width: 100%; cursor: pointer; border: none; margin-top: 0.5rem; display: flex; gap: 0.75rem;` |
| `.bt-paiement-especes` | Bouton ESPÈCES | `background-color: var(--vert01);` |
| `.bt-paiement-cb` | Bouton CB | `background-color: var(--bleu03);` |
| `.bt-paiement-cashless` | Bouton CASHLESS | (couleur à confirmer en lisant le partial) |
| `.bt-paiement-2eme-carte` | Bouton 2ème carte NFC | `background-color: var(--warning00);` |
| `.fi-payment-detail` | Total panier / Reste à payer | `font-variant-numeric: tabular-nums; margin-top: 0.5rem;` |

**Templates** : remplacer chaque `style="..."` inline par les classes ci-dessus. Aucun changement de comportement, juste du déplacement.

**`data-testid` racines** (item 7) : audit rapide des 3 partials pour vérifier que chacun a un `data-testid` unique sur son conteneur racine. Convention : `<nom-écran>` (ex: `complement-paiement`, `funds-insufficient`, `paiement-moyens`). Ajout si manquant.

**Test visuel** : flow complet espèces / CB / NFC / NFC fractionné → aspect identique avant/après.

---

### Lot 3 — Responsive + harmonisation (items 4, 8, 9, 10)

**Estimation** : ~1h.

**Objectif** : faire fonctionner les écrans de paiement sur les 3 hardware cibles.

**`overlay.css` — `clamp()` sur les titres** :

- `.fi-title1` : `font-size: clamp(1.5rem, 4vw, 2.5rem);`
- `.fi-msg1` : `font-size: clamp(1rem, 3vw, 1.5rem);`

**`overlay.css` — 2 breakpoints** :

```css
/* Tablettes / Sunmi D3 mini portrait */
@media (max-width: 768px) {
  .give-back-box { padding: 0.75rem 1rem; }
  .bt-paiement-base { padding: 0.5rem 0.75rem; }
  .cascade-badge { font-size: 0.85rem; }
}

/* Sunmi V2s portrait */
@media (max-width: 540px) {
  .give-back-box { padding: 0.5rem 0.75rem; margin: 0.5rem 0; }
  .bt-paiement-base { padding: 0.5rem; }
  .cascade-badge { font-size: 0.8rem; padding: 2px 6px; }
  .fi-payment-detail { font-size: 1rem; }
}
```

**Harmonisation `hx-swap`** (item 4) : audit rapide des 3 partials → tous les `hx-target="#messages"` passent à `hx-swap="innerHTML"`. Cohérent avec le pattern « `#messages` = layer permanent, on remplace son contenu ».

**TODO chèque** (item 10) : suppression du `<!-- TODO: chèque ? -->` dans `hx_funds_insufficient.html` ligne 44. Décision produit : pas de chèque pour cette version.

**Test visuel** : Chrome DevTools, simulation des 3 résolutions :
- 1920×1080 (desktop)
- 1280×800 (D3 mini paysage)
- 720×1440 (V2s portrait)

---

## Plan de test

### Visuel — pendant la session

Après chaque lot, lancer un flow complet dans Chrome :

1. Connexion caisse → ajouter articles → VALIDER
2. Tester les 3 chemins :
   - Espèces
   - CB
   - Cashless avec fonds insuffisants → écran fractionné NFC complément

### E2E — après lot 3

```bash
docker exec lespass_django poetry run pytest tests/e2e/test_pos_*.py -v
```

44 tests E2E POS existants. Ils ne doivent pas régresser.

### Pas de pytest unitaires nécessaires

Aucune modification Python ou serializer.

## Refonte lot 5 (2026-04-28 fin de session)

Le lot 5 d'origine cristallisait un mauvais design préexistant : modale flottante
`max-width 500px margin 80px auto background white` complètement incohérente avec
le reste du POS qui utilise un overlay plein écran via `#messages` avec fond de
couleur signature par écran.

**Refonte appliquée** : passage en plein écran cohérent avec les autres écrans de
paiement (`paiement-nfc-insuffisant`, `complement-paiement`, `paiement-succes`).

### Direction visuelle
- `vider_carte_confirm` : fond `var(--warning00)` orange — tension avant l'action
  irréversible. Box `.give-back-box` rouge sombre + bordure dorée pour le montant
  « À rendre » : contraste fort, le caissier voit en 0,5 s combien rendre.
- `vider_carte_success` : fond `var(--success)` vert — soulagement, cohérent avec
  l'écran `paiement-succes` existant. Icône check animée `scale-in`.

### Composants
Réutilisation max des classes existantes : `.BF-col`, `.fi-title1`, `.fi-msg1`,
`.give-back-box`, `.bt-basic-container`, `.success-icon`, `<c-bt.return />`.

Une seule petite classe ajoutée : `.cascade-tokens-table` (table légère sur fond
sombre pour le détail des soldes, sans alourdir).

### Suppressions
Toutes les classes `.modal-*` créées au lot 5 d'origine sont retirées d'overlay.css
(orphelines après refonte) :
- `.modal-content`, `.modal-amount-large`, `.modal-amount-xlarge`
- `.modal-table` + variantes thead/tbody
- `.modal-info-box`, `.modal-warning-box`
- `.modal-actions`, `.modal-btn`, `.modal-btn--confirm/secondary/imprimer`

### 2 règles `:has()` ajoutées dans la section overlay backgrounds
- `#messages:has([data-testid="vider-carte-confirm"])` — fond orange
- `#messages:has([data-testid="vider-carte-success"])` — fond vert succès

## Bugs JS découverts pendant la session — pour Nico

### 1. `htmx:targetError` après cycle de paiement complet

**Symptôme** : après VALIDER → moyen → scan/saisie → succès → RETOUR, le clic suivant
sur CASHLESS génère `htmx:targetError` dans la console. Bouton ne réagit pas.

**Cause probable** : `cotton/addition.html:26` → `hx-on::after-request="hideAndEmptyElement('#confirm')"`
vide `#confirm` après paiement. Au cycle suivant le swap `outerHTML` du bouton CASHLESS
échoue par intermittence.

**Pistes** : modifier `hideAndEmptyElement('#confirm')` pour ne plus vider mais juste
cacher (`classList.add('hide')`), OU restaurer `#confirm` proprement dans `manageReset()`.
Attention au piège : un retour arrière naïf vers `class="hide"` provoque des doublons
`<c-read-nfc id="confirm">` imbriqués. La solution propre nécessite probablement de
retirer aussi `id="confirm"` du composant interne (déjà fait pour les 3 partials NFC
dans cette session 36).

### 2bis. `_obtenir_ou_creer_wallet` ignore `carte.user.wallet`

**Symptôme** : avec une carte ayant `user` non-null + `wallet_ephemere=None`, et le wallet
du user crédité (15€ TLF), la vue `vider_carte_preview` retourne `« Aucun solde
remboursable sur cette carte. »`.

**Cause probable** : `_obtenir_ou_creer_wallet(carte)` retourne probablement uniquement
`carte.wallet_ephemere` ou crée un nouveau wallet vide. Il devrait fallback sur
`carte.user.wallet` quand le user est attaché à la carte.

**Conséquence pour la session 36** : impossible de tester end-to-end le cas « 2 boutons »
(carte avec user) — la modale `confirm` ne s'affiche pas (vue retourne erreur dès le
preview).

**Test bypass effectué quand même** : avec un user attaché à la carte mais en injection
manuelle du contexte (sans passer par la vue preview), la modale `confirm` affiche bien
2 boutons distincts, contrastes OK, layout plein écran cohérent.

### 2. `viderCarteManageForm` jamais implémenté

**Symptôme** : le scan NFC simulé dans l'écran « Vider la carte » détecte le tag
(logs `nfc.js:SendTagIdAndSubmit`) mais aucune requête HTTP n'est envoyée. Le flow
est complètement bloqué : pas de modale `confirm`, pas de remboursement.

**Cause** : le composant `<c-read-nfc event-manage-form="viderCarteManageForm">` dans
`hx_vider_carte_overlay.html:21` attend un handler JS `viderCarteManageForm` qui
n'existe nulle part :
- Pas dans la table `switches` de `tibilletUtils.js` (à côté de `additionManageForm`,
  `primaryCardManageForm`, `checkCardManageForm`).
- Aucune fonction `viderCarteManageForm()` définie dans le projet.
- Seule mention : un commentaire dans `vider_carte.js:15`.

**Pattern à implémenter** (similaire à `checkCardManageForm` dans `hx_check_card.html:28`) :
```javascript
function viderCarteManageForm(event) {
  // 1. Mettre tag_id dans #vider-carte-form
  // 2. POST vers submit-url avec les hidden fields du form (tag_id + tag_id_cm + uuid_pv + csrf)
  // 3. Injecter la réponse dans #messages (innerHTML)
}
// Enregistrer dans tibilletUtils.js:switches :
//   viderCarteManageForm: [{ name: 'viderCarteManageForm', selector: '#vider-carte-form' }],
```

**Backend complet** : 3 routes prêtes (`/vider_carte/overlay/`, `/vider_carte/preview/`,
`/vider_carte/`) + serializer `ViderCarteSerializer` + 3 templates HTML (lot 5 refacté
dans cette session).

**Test bypass effectué** : un POST direct sur `/vider_carte/preview/` (avec carte
créditée 15€ TLF) renvoie correctement la modale `hx_vider_carte_confirm.html` avec
le pattern `.modal-*` du lot 5. La refacto CSS/HTML est validée visuellement.

## Hors scope

- Modifications JS (tarif.js, tibilletUtils.js, vider_carte.js, etc.) — gérées par Nico.
- Refonte des autres écrans POS (cloture, scan article, ouverture caisse, etc.).
- Ajout du moyen de paiement « chèque » — décidé hors scope pour cette version.
- Refonte du composant cotton `<c-bt.paiement>` (sauf si nécessaire pour les classes de bouton).
- Tests unitaires Python (aucune modif Python).

## Risques

- **Lot 3 — responsive sur hardware réel** : Chrome DevTools simule les résolutions mais pas les comportements tactiles. Test sur Sunmi V2s en condition réelle recommandé avant prod.
- **Lot 2 — couleur `.bt-paiement-cashless`** : la couleur exacte est à confirmer en lisant `hx_display_type_payment.html` (variable CSS à utiliser).
- **`#confirm:has(...)` vs `#messages:has(...)`** : vérifier que le partial `complement-paiement` est bien injecté dans `#confirm` (pas `#messages`). À confirmer en relisant `_payer_par_nfc()` côté Python.

## Suite

Implémentation lot par lot, avec validation visuelle Chrome entre chaque lot. Le mainteneur fait les commits.
