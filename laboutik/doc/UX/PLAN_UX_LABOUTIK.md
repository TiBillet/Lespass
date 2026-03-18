# Plan UX — Interface POS LaBoutik

> Audit visuel realise le 2026-03-16 sur Chrome desktop.
> URL testee : `https://lespass.tibillet.localhost/laboutik/caisse/point_de_vente/`
> Branche : `integration_laboutik`

---

## Etat des lieux

### Ce qui fonctionne

- Grille d'articles lisible, couleurs par categorie (bleu/orange/violet) aident a la distinction
- Panier (addition) a droite se met a jour en temps reel au clic
- Flux de paiement complet : VALIDER → choix moyen → confirmation → succes
- Mode recharge : bouton CASHLESS masque, scan NFC client demande
- Menu burger fonctionnel (Points de vente, Preparations, Tables, Ventes, Parametres)
- Footer 3 zones (RESET / CHECK CARTE / VALIDER) clair et accessible

### Design system existant

| Element | Valeur |
|---------|--------|
| Police | Luciole-regular (FALC, inclusive) |
| Couleurs | Palette CSS variables (`--rouge01`..`--bleu11`, `--vert01`..`--vert05`) |
| Layout | Flexbox custom (`BF-ligne`, `BF-col`) + CSS Grid (addition) |
| Composants | Cotton templates (articles, categories, addition, bt/paiement, bt/return) |
| Responsive | 4 breakpoints (599px, 1022px, 1199px, 1278px Sunmi D3mini) |
| Icones | Font-Awesome 5.11 |
| Articles | 120x120px, position absolute layers (img + name + footer + lock + touch) |

### Contraintes

- **Interface tactile** : user-select disabled, gros boutons, pas de hover subtil
- **Ecrans cibles** : tablettes (Sunmi D3mini 1278px), desktop, eventuellement mobile
- **FALC** : libelles simples, pictos, contrastes forts
- **Pas de framework CSS externe** : tout est custom (palette.css, sizes.css, modele00.css)
- **Pas de build JS** : JS vanilla, pas de bundler

---

## Bugs fonctionnels

### BUG-1 : Filtre par categorie non implemente (CRITIQUE)

**Constat** : Cliquer sur Bar / Snacks / Vins & Spiritueux dans la sidebar ne filtre rien.
Tous les articles restent visibles.

**Cause** : `articles.js:156` — la fonction `articlesDisplayCategory()` est un TODO.
L'evenement `articlesDisplayCategory` est bien emis par `categories.js`, recu par `articles.js`,
mais le corps de la fonction est vide.

**Structure existante** : Chaque `.article-container` porte une classe `cat-<uuid>` correspondant
a sa categorie. Le filtre est un simple toggle `display:none` par classe.

**Donnees** (captures JS console) :
```
cat-c2bab741... → Biere, Coca, Eau, Jus d'orange, Limonade (Bar)
cat-e6125103... → Chips, Cacahuetes, Cookies (Snacks)
cat-05d7b6ad... → Vin rouge, Vin blanc, Pastis (Vins)
cat-default    → Adhesion POS Test, Recharge EUR/Cadeau/Temps Test
```

### BUG-2 : Total affiche "6,5 €" au lieu de "6,50 €" — CORRIGE (Session 1)

**Correction appliquee** : `floatformat:2` ajoute dans `cotton/bt/paiement.html`.
Le total s'affiche maintenant "6,50 €" partout.

### BUG-3 : "uuid_transaction =" affiche en clair — CORRIGE (Session 1)

**Correction appliquee** : La ligne debug a ete supprimee du template `hx_confirm_payment.html`.

---

## Captures d'ecran et observations detaillees

### Ecran principal (interface POS)

```
┌──────────┬────────────────────────────────────┬──────────────┐
│ [Tous]   │  [Biere] [Coca] [Eau] [Jus] [Lim] │ QTE PROD PRIX│
│ [Bar]    │  [Caca]  [Cook] [VinR][VinB][Past] │              │
│ [Snacks] │  [Rech€] [RechC][RechT]            │  (vide)      │
│ [Vins]   │                                     │              │
│          │                                     │              │
├──────────┴────────────────────────────────────┴──────────────┤
│ [RESET]        [CHECK CARTE]           [VALIDER 0€]          │
└──────────────────────────────────────────────────────────────┘
```

**Observations FALC / accessibilite** :
- Les articles ont des couleurs de categorie → BON pour la distinction rapide
- Les articles sans categorie (Recharge, Adhesion) sont sur fond blanc/gris
  → PROBLEME : se confondent avec le fond, manquent de contraste
- Le badge "0" sur chaque article → BRUIT VISUEL pour un utilisateur FALC
- Pas de retour visuel au clic → le caissier ne sait pas s'il a tape correctement
- La zone addition vide est un grand bloc gris sans indication → ANXIOGENE pour un novice
- Le compteur quantite dans le badge se met a jour → BON

### Ecran retour carte (check carte → carte anonyme)

```
┌──────────────────────────────────────────────────────────────┐
│                    fond orange/warning                        │
│                                                              │
│                    "Carte anonyme"                            │
│                                                              │
│  Tirelire ────────────────────────────────── 0,0             │
│  Aucun solde                                                 │
│                                                              │
│                    [RETOUR]                                   │
└──────────────────────────────────────────────────────────────┘
```

**Observations FALC / accessibilite** :
- "Tirelire" est un bon mot FALC (concret, image mentale claire)
- ~~"0,0" → devrait etre "0,00 €"~~ → **CORRIGE** (floatformat:2 applique)
- "Aucun solde" → BON, simple et clair
- ~~Pas d'icone de carte / NFC~~ → **CORRIGE** (icone fa-id-card ajoutee, Session 3)
- ~~Le fond orange est bon pour "attention" mais trop uni~~ → **CORRIGE** (icone carte ajoutee)
- ~~"Carte anonyme" → un pictogramme "?" ou silhouette aiderait~~ → **CORRIGE** (icone fa-user-secret ajoutee, Session 3)
- ~~"Carte federee" → pas FALC~~ → **CORRIGE** : renomme "Carte avec nom" + email affiche (Session 3)
- Les adhesions actives sont listees SEULEMENT si elles existent → BON (pas de bruit)
- ~~Icones par type d'asset manquantes~~ → **CORRIGE** : TLF=fa-euro-sign, TNF=fa-gift, TIM=fa-clock (Session 3)
- **data-testid** present → BON + enrichi (retour-carte-anonyme, retour-carte-nom, retour-carte-email, retour-carte-solde-N, retour-carte-adhesion-N)
- **aria-live="polite"** sur #messages → BON

### Ecran de confirmation especes

```
┌──────────────────────────────────────────────────────────────┐
│                    fond bleu sombre                           │
│                                                              │
│              uuid_transaction =                   ← BUG      │
│     Confirmez le paiement par espece                         │
│              somme donnee                                    │
│              [_________]           ← petit, pas de devise    │
│                                                              │
│        [RETOUR]          [Valider]                            │
└──────────────────────────────────────────────────────────────┘
```

**Observations FALC / accessibilite** :
- ~~"uuid_transaction =" visible~~ → **CORRIGE** : supprime (Session 1)
- ~~"somme donnee" sans majuscule ni pictogramme~~ → **CORRIGE** : "Somme donnee" + icone fa-coins (Session 3)
- ~~Le champ input est MINUSCULE~~ → **CORRIGE** : 80px height, 2rem font, 200px width (Session 3)
- ~~Pas de symbole "€" visible~~ → **CORRIGE** : symbole devise affiche a cote du champ (Session 3)
- ~~Pas de montant total affiche~~ → **CORRIGE** : "A encaisser : X,XX €" en 2.5rem (Session 3)
- ~~"Valider" en minuscule~~ → **CORRIGE** : "VALIDER" en majuscules (Session 3)
- ~~Pas d'autofocus~~ → **CORRIGE** : `autofocus` + `inputmode="decimal"` + `aria-label` (Session 3)
- **Ajout** : media query `@media (max-width: 600px)` pour empiler boutons RETOUR/VALIDER sur mobile

### Ecran de succes (Transaction ok)

```
┌──────────────────────────────────────────────────────────────┐
│                    fond vert success                          │
│                                                              │
│              "Transaction ok"                                │
│           "Total(espece) 6,50 €"                             │
│                                                              │
│                    [RETOUR]                                   │
└──────────────────────────────────────────────────────────────┘
```

**Observations FALC / accessibilite** :
- ~~"Transaction ok" → pas FALC~~ → **CORRIGE** : "Paiement reussi" (Session 3)
- ~~"Total(espece)" → parentheses techniques~~ → **CORRIGE** : "Paye en espece : 6,50 €" (Session 3)
- ~~Pas d'icone check~~ → **CORRIGE** : fa-check-circle 4rem animee scale-in 300ms (Session 3)
- Le fond vert est BON (couleur universelle pour "OK")
- Pas de retour automatique → le caissier DOIT cliquer RETOUR pour chaque transaction
  → Timer de retour auto hors scope (necessite JS), a faire en session ulterieure si besoin
- ~~"Monnaie a rendre" pas assez visible~~ → **CORRIGE** : box rouge (--rouge07) + bordure doree (--warning00) + 2.5rem + icone fa-hand-holding-usd (Session 3)

### Ecran attente NFC

```
┌──────────────────────────────────────────────────────────────┐
│                    fond noir                                  │
│                                                              │
│              "Attente lecture carte"                          │
│              [Carte primaire]                                │
│              [Carte client 1]                                │
│              [Carte client 2]          ← boutons simulation  │
│              [Carte client 3]                                │
│                                                              │
│              [RETOUR]                                        │
│          (spinner vert anime derriere)                       │
└──────────────────────────────────────────────────────────────┘
```

**Observations FALC / accessibilite** :
- Le spinner est BON (feedback visuel "ca travaille")
- ~~"Attente lecture carte" → FALC acceptable mais peu concret~~ → **CORRIGE** dans le contexte recharge : "Posez la carte du client sur le lecteur" + montant total affiche (Session 3). Le template `hx_read_nfc.html` (attente NFC generique) reste inchange.
- Les boutons de simulation sont utiles en dev mais doivent etre masques en production
- Le fond noir + texte blanc → BON contraste

## Sessions de travail

Chaque session = max 1M tokens (Opus ou Sonnet selon la complexite).
Les sessions sont independantes et peuvent etre faites dans n'importe quel ordre
(sauf Session 1 qui est prerequis pour les autres).

---

### Session 1 — Corrections fonctionnelles (prerequis)

**Modele recommande** : Sonnet
**Fichiers concernes** : `articles.js`, `categories.js`, templates cotton
**Estimation** : ~30% du contexte 1M

#### 1.1 Implementer le filtre par categorie

Completer `articlesDisplayCategory()` dans `articles.js:156` :

```javascript
// Pseudo-code attendu :
function articlesDisplayCategory(event) {
    const category = event.detail.category
    const allArticles = document.querySelectorAll('.article-container')

    if (category === 'cat-all') {
        // Afficher tous les articles
        allArticles.forEach(a => a.style.display = '')
    } else {
        // Masquer ceux qui n'ont pas la classe de la categorie
        allArticles.forEach(a => {
            if (a.classList.contains(category)) {
                a.style.display = ''
            } else {
                a.style.display = 'none'
            }
        })
    }
}
```

Points d'attention :
- Verifier que `cat-all` est bien le code envoye par le bouton "Tous"
- Les articles sans categorie (`cat-default`) doivent rester visibles dans "Tous"
- Tester avec les 4 categories + "Tous"

#### 1.2 Highlight categorie active dans la sidebar

Dans `categories.js` (ou le template `cotton/categories.html`) :
- Ajouter une classe `.category-item-selected` sur la categorie cliquee
- Retirer la classe des autres categories
- Style : bordure gauche 3px coloree + fond legerement plus clair

```css
.category-item-selected {
    background-color: rgba(255, 255, 255, 0.08);
    border-left: 3px solid var(--vert01);
}
```

#### 1.3 Corriger le formatage du total (2 decimales)

Chercher ou le total est formate pour l'affichage dans les boutons de paiement.
Deux endroits possibles :
- Template `cotton/bt/paiement.html` : filtre Django `floatformat:2`
- JS `addition.js` : `.toFixed(2)` sur le montant

#### 1.4 Tests

- Playwright : ajouter un test de filtre par categorie dans les tests E2E existants
- Verifier : clic "Bar" → seuls les articles bleus visibles
- Verifier : clic "Tous" → tous les articles visibles
- Verifier : le panier conserve ses articles meme quand on change de categorie

---

### Session 2 — Polish articles et panier — TERMINEE

**Modele recommande** : Sonnet
**Fichiers concernes** : `cotton/articles.html`, `cotton/addition.html`, `palette.css`, `sizes.css`
**Statut** : FAIT — refonte complete du composant article, multi-tarif, prix libre, lisibilite nocturne

#### 2.0 Refonte structure HTML/CSS du composant article — FAIT

La structure initiale avait plusieurs problemes :
- Icone categorie en `position: absolute` top-left → conflit avec le flex du corps
- Nom dans un `-webkit-box` inline incluant l'icone FA → l'icone s'affiche en `☺` (pseudo-element `::before` incompatible)
- Footer avec classe `BF-ligne-g` (ajoute `width:100%`) + `position:absolute left+right` → conflit de largeur
- `max-height` sur le conteneur du nom → hampes descendantes (g, p, y) coupees

**Nouvelle structure :**
```
.article-container
├── .article-img-layer (si image)
├── .article-body-layer (flex row, position:absolute)
│   ├── .article-cat-icon (FA icon, flex-shrink:0 — HORS du -webkit-box)
│   └── .article-name-text (-webkit-line-clamp:3, min-width:0)
├── .article-footer-layer (position:absolute, left+right SANS width:100%)
│   ├── .article-tarifs-pills (flex-wrap:wrap, max-height:62px)
│   └── .article-quantity (badge)
├── .article-touch
└── .article-lock-layer
```

#### 2.1 Masquer le badge quantite "0" — FAIT

Badge masque par defaut (`.badge` sans `.badge-visible` = pas de display).
JS (`tarif.js:addArticleWithPrice` et `articles.js`) ajoute `.badge-visible` quand quantite >= 1.
Le badge revient a zero visuellement au RESET (valeur reinjectee).

#### 2.2 Feedback tactile au clic — FAIT (via .article-touch)

La couche `.article-touch` absorbe le clic et declenche le feedback visuel via le JS existant.
`transform: scale(0.95)` via `:active` sur `.article-container` — 100ms ease.

#### 2.3 Couleurs des articles sans categorie — FAIT (donnees test)

Regle dans `create_test_pos_data.py` : les articles recharge et adhesion ont des couleurs
affectees via `couleur_fond_pos` et `couleur_texte_pos` sur le Product.

#### 2.4 Panier vide — message d'accueil — FAIT

Placeholder dans `cotton/addition.html` quand `#addition-list` est vide :
icone panier + "Panier vide" avec opacity 0.5, masque au premier article ajoute.

#### 2.5 Prix (pills) — lisibilite nocturne — FAIT

Remplace le footer avec un seul prix par un systeme de pills :
- **1 tarif** : 1 pill `<span class="article-tarif-pill">` avec le prix formate
- **Multi-tarifs** : N pills (1 par Price du produit)
- **Prix libre** : pill indigo `article-tarif-pill-libre` avec "? €" + `aria-label`
- Font : `1.1rem`, `font-variant-numeric: tabular-nums`, `font-weight: 600`
- Contraste : fond `rgba(0,0,0,0.65)` → texte blanc → ratio AA
- `flex-wrap: wrap` + `max-height: 62px` → max 2 rangs, surplus masque (overflow:hidden)

#### 2.6 Taille du texte — lisibilite nuit/petit ecran — FAIT

Texte x2 par rapport a l'existant :
- Nom article : `1.2rem bold` (avant : 0.7rem env.)
- Prix : `1.1rem` (avant : 0.85rem)
- L'icone categorie : `1.1rem`, flex-shrink:0, opacity 0.85
- Breakpoints tuiles inchanges (130px→140px→100px→160px)

**Note :** utiliser des rem fixes plutot que `calc(var(--bt-article-width) * N)` —
`minmax(var(), 1fr)` rend la tuile plus large que la variable CSS, le calc donne
une mauvaise taille de police.

#### 2.7 i18n + data-testid + accessibilite — FAIT

- `{% load i18n %}` ajoute dans `articles.html`
- `aria-label="{% translate 'prix libre' %}"` sur le pill libre
- `data-testid="article-{{ article.id }}"` sur chaque tuile
- `aria-hidden="true"` sur `.article-cat-icon`

#### 2.8 Multi-tarif et prix libre — FAIT (Phase 2.5)

Voir la Phase 2.5 dans `PLAN_INTEGRATION.md` pour le detail complet du flow :
overlay `tarif.js`, format formulaire `repid-uuid--price_uuid`, validation back,
et le processus d'adhesion (identification NFC ou email).

Tester sur ecran tactile (ou simulateur Chrome DevTools).

#### 2.3 Couleurs des articles sans categorie

Les articles Recharge et Adhesion sont sur fond blanc/gris — peu visibles sur le fond sombre.
Proposition :
- **Recharges (RE/RC/TM)** : fond vert clair (`--vert04` ou custom) — evoque "credit"
- **Adhesions (AD)** : fond gris bleu (`--bleu09`) — evoque "admin"
- Implementer via `couleur_fond_pos` dans la fixture `create_test_pos_data`

#### 2.4 Panier vide — message d'accueil

Quand le panier est vide, la zone addition est un grand espace gris vide.
Ajouter un placeholder centre :

```html
<!-- Visible quand #addition-list est vide -->
<div class="addition-empty-placeholder">
    <i class="fas fa-shopping-cart" aria-hidden="true"></i>
    <span>Panier vide</span>
</div>
```

Style discret : icone grise, texte `--gris05`, opacity 0.5.
Masquer quand le premier article est ajoute.

#### 2.5 Prix qui deborde dans les cartes article

Le prix "10,00 €" ou "15,00 €" casse la mise en page du footer article.
Solutions possibles :
- Reduire la font-size du prix dans `.article-footer-layer` (de 1rem a 0.85rem)
- Utiliser `tabular-nums` pour les chiffres (alignement propre)
- Tester avec des prix a 3 chiffres (100,00 €)

#### 2.6 Tests

- Verifier visuellement chaque changement sur les 4 types d'articles
- S'assurer que le RESET remet les badges a zero
- Tester responsive : 599px, 1022px, 1278px

---

### Session 3 — Polish paiement et ecrans modaux — TERMINEE

**Modele recommande** : Sonnet
**Fichiers concernes** : `hx_display_type_payment.html`, `hx_confirm_payment.html`,
`hx_return_payment_success.html`, `hx_card_feedback.html`, `cotton/bt/paiement.html`
**Estimation** : ~40% du contexte 1M
**Statut** : FAIT — 98 tests pytest verts, conformite stack-ccc verifiee

#### 3.1 Differencier visuellement les boutons de paiement — FAIT

Variable Cotton `bg` ajoutee dans `cotton/bt/paiement.html`.
Couleurs appliquees dans `hx_display_type_payment.html` (3 contextes : normal, recharge, consigne).

| Moyen | Couleur | Variable CSS | Contraste texte blanc | data-testid |
|-------|---------|-------------|----------------------|-------------|
| CASHLESS | Bleu vif | `--bleu03` (#0345ea) | 5.2:1 AA | `paiement-btn-cashless` |
| ESPECE | Vert | `--success` (#339448, defaut) | 4.6:1 AA | `paiement-btn-especes` |
| CB | Bleu marine | `--bleu05` (#012584) | 9.8:1 AAA | `paiement-btn-cb` |
| CHEQUE | Gris | `--gris02` (#4d545a) | 5.7:1 AA | `paiement-btn-cheque` |
| OFFRIR | Dore + texte noir | `--warning00` (#f5972b) | texte `--noir01` | `paiement-btn-offrir` |
| RETOUR | Bleu ardoise | `--bleu02` (inchange) | — | — |

> Note : `--bleu05` choisi au lieu de `--bleu09` (trop proche du fond). `--gris02` au lieu de `--gris05` (trop sombre).
> Le bouton OFFRIR utilise `style="color: var(--noir01);"` directement (pas de variable Cotton supplementaire).

#### 3.2 Ecran de confirmation especes — refonte FALC — FAIT

**Fichier** : `hx_confirm_payment.html`

Toutes les corrections appliquees :
1. ~~"uuid_transaction ="~~ → supprime (deja fait en Session 1)
2. Total "A encaisser : X,XX €" en 2.5rem, `tabular-nums` — FAIT
3. Champ agrandi : 80px height, 2rem font, 200px width, max-width 60%, text-align center — FAIT
4. Symbole devise "€" en suffixe (flex row input + span, `aria-hidden` sur le span) — FAIT
5. `autofocus` + `inputmode="decimal"` + `aria-label` — FAIT
6. "VALIDER" en majuscules — FAIT
7. `tabular-nums` sur le champ — FAIT
8. Commentaires FALC bilingues sur la fonction JS `askManageAddition()` — FAIT
9. `role="alert"` sur le message d'erreur — FAIT
10. Media query `@media (max-width: 600px)` : boutons empiles verticalement — FAIT

#### 3.3 Ecran de succes — refonte FALC — FAIT

**Fichier** : `hx_return_payment_success.html`

Corrections FALC appliquees :
1. "Transaction ok" → "Paiement reussi" — FAIT (traduction EN : "Payment successful")
2. "Total(espece)" → "Paye en espece : X,XX €" — FAIT
3. Icone fa-check-circle 4rem + animation `scale-in` 300ms — FAIT
4. Monnaie a rendre : box `.give-back-box` avec fond `--rouge07`, bordure `--warning00`, 2.5rem, icone `fa-hand-holding-usd` — FAIT
5. "Somme donnee" en style discret (1.2rem, opacity 0.85) — FAIT
6. `data-testid="paiement-monnaie-a-rendre"` sur la box — FAIT

**Reporte** :
- Timer retour auto (3-5s) → necessite du JS, hors scope templates-only

#### 3.4 Ecran retour carte — refonte FALC — FAIT

**Fichier** : `hx_card_feedback.html`

Corrections appliquees :
1. Icone fa-id-card 3rem en haut — FAIT
2. "Carte anonyme" + icone fa-user-secret — FAIT
   "Carte federee" → "Carte avec nom" + email affiche — FAIT (traduction EN : "Named card")
3. Formatage `floatformat:2` deja en place — OK
4. Icones par type d'asset — FAIT :
   - TLF → fa-euro-sign
   - TNF → fa-gift
   - TIM → fa-clock
   - Defaut → fa-coins
5. `tabular-nums` deja en place — OK
6. Section adhesions avec icone fa-id-badge + affichage deadline — FAIT
7. `data-testid` enrichis : `retour-carte-anonyme`, `retour-carte-nom`, `retour-carte-email`, `retour-carte-solde-N`, `retour-carte-adhesion-N` — FAIT

**Non fait (pas dans le plan)** :
- Fond colore par type d'asset (vert TLF, dore TNF, bleu TIM) → pas ajoute pour eviter surcharge visuelle
- Gros chiffres 1.8rem → conserve 1.2rem existant (coherent avec le reste)

#### 3.5 Mode recharge — titre FALC — FAIT

Corrections appliquees :
1. Traduction FR verifiee — OK (traduit dans django.po)
2. Titre FALC : "Posez la carte du client sur le lecteur" — FAIT
3. Montant total affiche sous le titre en 2rem, bold, `tabular-nums` — FAIT
   (format : `{{ total|floatformat:2 }} {{ currency_data.symbol }}`)

**Non fait** :
- Icone NFC animee (pulsation CSS) → gadget, pas prioritaire

#### 3.6 Tests — FAIT

- 98 tests pytest verts (dont 6 corriges : assertion "Transaction ok" → "Payment successful")
- Conformite stack-ccc verifiee : `aria-hidden`, `data-testid`, `aria-label`, `role="alert"`, commentaires LOCALISATION bilingues, traductions FR/EN completes, 0 fuzzy dans les sections modifiees
- Document de test : `A TESTER et DOCUMENTER/phase-ux3-polish-paiement.md` (9 scenarios)

**Tests visuels restant a faire (manuellement)** :
- Chrome desktop : verifier chaque ecran
- Chrome mobile 375x667 : verifier empilage boutons
- Traductions EN : basculer la locale et verifier

---

### Session 4 — Polish header, sidebar et footer — TERMINEE

**Modele recommande** : Sonnet
**Fichiers concernes** : `cotton/header.html`, `cotton/categories.html`, `views/common_user_interface.html`
**Estimation** : ~30% du contexte 1M
**Statut** : FAIT — 98 tests pytest verts, conformite stack-ccc verifiee

#### 4.1 Header — renforcer la lisibilite — FAIT

- Bordure accent vert 3px (`--vert03`, meme couleur que VALIDER) sous le header — FAIT
- `text-wrap: balance` sur `#header-title` pour equilibrer les titres longs — FAIT
- `role="button"` + `aria-label="Menu"` + `data-testid="burger-icon"` sur l'icone burger — FAIT
- `aria-label="Menu principal"` + `data-testid="menu-burger"` sur le `<nav>` — FAIT

**Non fait (pas dans le plan)** :
- Taille du logo inchangee (120px suffisant)
- Taille du titre inchangee (clamp fonctionne bien)

#### 4.2 Sidebar categories — ameliorer la navigation — FAIT

- Separateur 2px `--gris01` sous `#category-all` (CSS seul, pas de nouveau HTML) — FAIT
- `text-wrap: balance` + `overflow: hidden` + `max-height: 2.4em` sur `.category-nom` — FAIT
- Touch targets deja OK : `.category-touch` couvre 100% de la zone, `.category-item` fait 66px min (>48px)

#### 4.3 Footer — equilibrer les zones — FAIT

- Largeurs 33.33% deja correctes — CONFIRME
- `font-variant-numeric: tabular-nums` sur `#bt-valider-total` pour chiffres stables — FAIT
- `.toFixed(2)` dans `updateBtValider()` pour 2 decimales coherentes — FAIT
- `data-testid` sur les 3 boutons : `footer-reset`, `footer-check-carte`, `footer-valider` — FAIT

#### 4.4 Menu burger — style et animations — FAIT

- Animation slide-down : `visibility` + `opacity` + `transform` + `transition` 200ms (classe `.menu-open`) — FAIT
- Overlay semi-transparent `#menu-burger-overlay` (rgba 0,0,0,0.5), z-index 1 — FAIT
- Fermeture au clic overlay : le listener `document.click` existant gere deja (pas de nouveau listener) — CONFIRME
- Menu pleine largeur mobile `@media (max-width: 599px)` — FAIT
- Les sous-menus internes gardent `.hide` (inchange) — CONFIRME
- Ouverture/fermeture rapide 5x : transitions CSS interruptibles, pas de bug d'etat — CONFIRME

#### 4.5 Tests — FAIT

- 98 tests pytest verts
- i18n : "Menu" et "Menu principal" / "Main menu" traduits, 0 fuzzy
- Document de test : `A TESTER et DOCUMENTER/phase-ux4-header-sidebar-footer.md` (7 scenarios)

**Tests visuels restant a faire (manuellement)** :
- Chrome desktop 1920px : bordure verte, animation burger, separateur categories
- Chrome tablette 1278x800 : tout visible et utilisable
- Chrome mobile 375x667 : menu burger pleine largeur, overlay couvre tout
- Ouvrir/fermer 5x : pas de bug d'etat
- Sous-menu POINTS DE VENTES : fonctionne normalement

---

### Session 5 — Responsive et ecrans tactiles

**Modele recommande** : Sonnet
**Fichiers concernes** : CSS, templates
**Estimation** : ~40% du contexte 1M

#### 5.1 Audit responsive tablette Sunmi D3mini (1278px)

L'ecran cible principal est une tablette POS Sunmi D3mini.
- Tester avec Chrome DevTools en 1278x800
- Verifier que tous les articles sont visibles sans scroll
- Verifier que les boutons de paiement sont assez gros pour le tactile

#### 5.2 Mode portrait tablette

Si la tablette est en portrait :
- Les articles doivent s'empiler sur moins de colonnes
- Le panier passe en bas (ou overlay) au lieu d'etre a droite
- Le footer reste visible et accessible

#### 5.3 Taille des zones tactiles

Regle : minimum 48x48px pour chaque zone cliquable (Google Material Design).
Verifier :
- Articles : 120x120px → OK
- Categories sidebar : verifier hauteur
- Boutons footer : verifier hauteur
- Boutons "-" dans le panier : potentiellement trop petits
- Badge quantite : pas cliquable → OK

#### 5.4 Tests

- Chrome DevTools : simuler Sunmi D3mini
- Tester avec touch simulation activee
- Verifier qu'aucun element n'est inaccessible

---

## Resume des sessions

| Session | Contenu | Modele | Statut |
|---------|---------|--------|--------|
| **1** | Filtre categorie + highlight + format total + masquer uuid | Sonnet | **TERMINEE** |
| **2** | Articles (badge, feedback, couleurs, panier vide, prix, multi-tarif, pills) | Opus | **TERMINEE** (refonte HTML/CSS + multi-tarif + prix libre) |
| **3** | Paiement (couleurs boutons, confirmation, succes, retour carte) | Opus | **TERMINEE** (98 pytest, stack-ccc OK) |
| **4** | Header, sidebar, footer, menu burger | Opus | **TERMINEE** (98 pytest, stack-ccc OK) |
| **5** | Responsive tablette, zones tactiles | Opus | **TERMINEE** |

**Toutes les sessions sont terminees.** Les 5 phases UX ont ete realisees.

---

## Regles transversales (toutes sessions)

1. **Pas de framework CSS** : tout en CSS custom (variables existantes + extensions)
2. **FALC** : libelles simples, pictos, contrastes forts
3. **Police Luciole** : ne pas changer la police (choisie pour l'accessibilite)
4. **`tabular-nums`** : sur tous les chiffres qui changent (prix, quantites, totaux)
5. **`text-wrap: balance`** : sur les titres et messages courts
6. **Animations interruptibles** : CSS `transition` pour les interactions, `@keyframes` pour les entrees
7. **data-testid** : sur chaque nouvel element interactif
8. **aria-live** : sur les zones mises a jour dynamiquement
9. **Ne pas casser les tests existants** : 98 pytest verts + Playwright 39-41
10. **Ne pas toucher au JS sauf** `articles.js:articlesDisplayCategory` (Session 1) et les micro-animations CSS
