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

### BUG-2 : Total affiche "6,5 €" au lieu de "6,50 €"

**Constat** : Sur l'ecran des moyens de paiement (boutons CASHLESS/ESPECE/CB), le total
affiche un seul chiffre decimal ("6,5 €", "11,0 €"). L'ecran de succes affiche
correctement "6,50 €" (il utilise le filtre `divide_by:100`).

**Cause** : Le total est passe au template via `total_en_euros = total_centimes / 100` (Python float).
650 / 100 = 6.5 (pas 6.50). Le template `cotton/bt/paiement.html` affiche ce float brut.
L'ecran de succes utilise `payment.total|divide_by:100` sur les centimes, qui formate correctement.

**Correction** : Utiliser `floatformat:2` dans le template bt/paiement.html, ou passer le total
en centimes et diviser dans le template.

### BUG-3 : "uuid_transaction =" affiche en clair sur l'ecran de confirmation

**Constat** : L'ecran `hx_confirm_payment.html` affiche le texte debug
"uuid_transaction =" en haut de page. C'est une info technique qui ne devrait pas
etre visible par le caissier.

**Cause** : Ligne 5 du template : `<div>uuid_transaction = {{ uuid_transaction }}</div>`

**Correction** : Masquer cette div (display:none ou supprimer la ligne).

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
- "0,0" → devrait etre "0,00 €" (meme bug de formatage + devise manquante)
- "Aucun solde" → BON, simple et clair
- Pas d'icone de carte / NFC → ajouter un pictogramme pour le FALC
- Le fond orange est bon pour "attention" mais trop uni — ajouter une icone ou un emoji carte
- "Carte anonyme" → le caissier comprend, mais un pictogramme "?" ou silhouette aiderait
- "Carte federee" (pour carte liee a un user) → pas FALC. "Carte avec nom" serait plus clair.
- Les adhesions actives sont listees SEULEMENT si elles existent → BON (pas de bruit)
- **data-testid** present → BON
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
- "uuid_transaction =" visible → **A MASQUER** (info technique, anxiogene)
- "somme donnee" sans majuscule ni pictogramme → ajouter icone pieces
- Le champ input est MINUSCULE → un caissier en festival ne verra pas ce qu'il tape
- Pas de symbole "€" visible → le caissier ne sait pas quelle unite saisir
- Pas de montant total affiche → le caissier ne se souvient plus combien encaisser
- "Valider" en minuscule vs "RETOUR" en majuscule → incoherence typographique
- Pas d'autofocus sur le champ → le caissier doit taper dans le champ (perte de temps tactile)

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
- "Transaction ok" → pas FALC. "C'est paye !" ou "Paiement reussi" serait plus clair
- "Total(espece)" → parentheses techniques. "Paye en espece : 6,50 €" serait mieux
- Pas d'icone check / validation → ajouter une icone fa-check-circle animee
- Le fond vert est BON (couleur universelle pour "OK")
- Pas de retour automatique → le caissier DOIT cliquer RETOUR pour chaque transaction
  → En festival a haut debit, ajouter un timer de retour auto (3-5s) en option
- Si "monnaie a rendre" : affiche "Monnaie a rendre : X €" → BON mais devrait etre
  en GROS et en ROUGE pour attirer l'attention du caissier

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
- "Attente lecture carte" → FALC acceptable, mais "Posez la carte sur le lecteur" serait plus concret
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

### Session 2 — Polish articles et panier

**Modele recommande** : Sonnet
**Fichiers concernes** : `cotton/articles.html`, `cotton/addition.html`, `palette.css`, `sizes.css`
**Estimation** : ~40% du contexte 1M

#### 2.1 Masquer le badge quantite "0"

Actuellement chaque article affiche un badge "0" en permanence → bruit visuel.

- Masquer le badge quand quantite = 0 (CSS `opacity: 0` ou `display: none`)
- Afficher avec une micro-animation quand quantite >= 1 (transition opacity 200ms)
- Le badge "0" doit reapparaitre quand on fait un RESET (evenement `articlesReset`)

#### 2.2 Feedback tactile au clic

Ajouter un retour visuel quand on tapote un article :

```css
.article-container:active {
    transform: scale(0.95);
    transition: transform 100ms ease;
}
.article-container {
    transition: transform 100ms ease;
}
```

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

### Session 3 — Polish paiement et ecrans modaux

**Modele recommande** : Sonnet
**Fichiers concernes** : `hx_display_type_payment.html`, `hx_confirm_payment.html`,
`hx_return_payment_success.html`, `hx_card_feedback.html`, `cotton/bt/paiement.html`
**Estimation** : ~40% du contexte 1M

#### 3.1 Differencier visuellement les boutons de paiement

Tous les boutons sont verts identiques → le caissier doit lire le texte pour distinguer.
Proposition de couleurs :

| Moyen | Couleur | Variable CSS | Icone |
|-------|---------|-------------|-------|
| CASHLESS | Bleu/violet | `--bleu03` | fa-address-card |
| ESPECE | Vert | `--vert03` (actuel) | fa-coins |
| CB | Bleu marine | `--bleu09` | fa-credit-card |
| CHEQUE | Gris | `--gris05` | fa-money-check |
| OFFRIR | Dore | `--warning00` | fa-gift |
| RETOUR | Bleu ardoise | `--bleu02` (actuel) | fa-undo-alt |

Implementer dans `cotton/bt/paiement.html` :
- Ajouter un attribut `color` ou `bg` au composant cotton
- Mapper les couleurs par moyen de paiement dans `hx_display_type_payment.html`

#### 3.2 Ecran de confirmation especes — refonte FALC

**Fichier** : `hx_confirm_payment.html`

L'ecran actuel est brut et pas FALC. Problemes constates :
- "uuid_transaction =" affiche en clair (info technique anxiogene)
- Champ "somme donnee" minuscule (60px height, font 1rem)
- Pas de symbole "€" visible
- Pas de rappel du montant a encaisser
- "Valider" en minuscule vs "RETOUR" en majuscule (incoherence)
- Pas d'autofocus

Corrections :
1. Supprimer ou masquer la ligne `uuid_transaction = {{ uuid_transaction }}`
2. Afficher le total en gros au-dessus du champ : "A encaisser : 6,50 €" (font-size 2.5rem)
3. Agrandir le champ (font-size 2rem, height 80px, width 200px, text-align center)
4. Ajouter "€" en suffixe visuel (flex row : input + span "€")
5. Ajouter `autofocus` sur le champ
6. Harmoniser les boutons : "RETOUR" et "VALIDER" en majuscules
7. Ajouter `tabular-nums` sur le champ de saisie
8. Ajouter `inputmode="decimal"` pour clavier numerique tactile

#### 3.3 Ecran de succes — refonte FALC

**Fichier** : `hx_return_payment_success.html`

L'ecran actuel affiche "Transaction ok" — pas FALC.

Corrections FALC :
1. Remplacer "Transaction ok" par "Paiement reussi" ou "C'est paye !"
   (plus concret, comprehensible par tous)
2. Remplacer "Total(espece) 6,50 €" par "Paye en espece : 6,50 €"
   (pas de parentheses techniques)
3. Ajouter une icone fa-check-circle en gros (font-size 4rem) animee (scale-in 300ms)
4. Si monnaie a rendre : afficher en GROS et en fond ROUGE
   "Monnaie a rendre : X,XX €" (le caissier ne doit pas rater cette info)
5. Ajouter un timer optionnel de retour auto (3-5s)
   → Utile en festival haut debit
   → Afficher une barre de progression en bas
   → Annulable au clic (reset le timer)

#### 3.4 Ecran retour carte — refonte FALC

**Fichier** : `hx_card_feedback.html`

L'ecran actuel est fonctionnel mais pas FALC.

Corrections :
1. Ajouter une icone carte NFC en haut (fa-id-card ou fa-address-card, font-size 3rem)
2. "Carte anonyme" → ajouter un picto silhouette "?"
   "Carte federee" → renommer en "Carte avec nom" (FALC) + afficher l'email
3. "Tirelire 0,0" → "Tirelire : 0,00 €" (ajouter devise + formatage 2 decimales)
4. Soldes par type d'asset : afficher avec des icones distinctes
   - TLF (euros) : icone fa-euro-sign, fond vert
   - TNF (cadeau) : icone fa-gift, fond dore
   - TIM (temps) : icone fa-clock, fond bleu
5. Chaque solde en gros chiffres (`tabular-nums`, font-size 1.8rem)
6. Section adhesions : si presente, afficher avec icone fa-id-badge
   et badge vert "Valide jusqu'au XX/XX/XXXX"
7. Ajouter `data-testid` sur chaque section solde

#### 3.5 Mode recharge — titre FALC

L'ecran affiche "Top-up: scan the client card" (en anglais car locale navigateur EN).

Corrections :
1. Verifier que la traduction FR "Recharge : scannez la carte client" s'affiche
   quand la locale est FR
2. Rendre le titre plus FALC : "Posez la carte du client sur le lecteur"
   (action concrete, pas d'anglicisme)
3. Afficher le montant de la recharge dans le titre :
   "Recharge 10,00 € : posez la carte client"
4. Ajouter une icone NFC animee (pulsation CSS)

#### 3.6 Tests

- Tester chaque ecran visuellement sur Chrome
- Verifier les textes FALC en FR et EN
- Verifier `data-testid` et `aria-live` sur chaque ecran
- Tester le timer de retour auto si implemente
- Tester le retour carte avec soldes, sans solde, avec adhesion, sans adhesion

---

### Session 4 — Polish header, sidebar et footer

**Modele recommande** : Sonnet
**Fichiers concernes** : `cotton/header.html`, `cotton/categories.html`, templates `views/*.html`
**Estimation** : ~30% du contexte 1M

#### 4.1 Header — renforcer la lisibilite

- Le titre "Service direct - Bar" est en `clamp(1rem, 3.5vw, 2.5rem)` — OK sur desktop
  mais verifier sur tablette
- Ajouter un accent de couleur de la categorie du PV (bordure bottom coloree)
- Le logo TiBillet en haut a gauche est petit — verifier qu'il est bien visible

#### 4.2 Sidebar categories — ameliorer la navigation

- Icones actuelles (Font-Awesome) sont generiques — verifier qu'elles matchent les categories
- Ajouter un separateur entre "Tous" et les categories specifiques
- Le texte "Vins & Spiritueux" est tronque — verifier overflow
- Touch target : verifier que chaque categorie fait au moins 48x48px (regle tactile)

#### 4.3 Footer — equilibrer les zones

Les 3 boutons du footer (RESET / CHECK CARTE / VALIDER) ont des largeurs differentes.
- RESET (rouge) : 33%
- CHECK CARTE (bleu) : 33%
- VALIDER (vert) : 33%
Verifier l'equilibre visuel et le contraste texte/fond.

#### 4.4 Menu burger — style et animations

Le menu burger s'affiche/masque sans animation.
- Ajouter une transition slide-down (transform + opacity, 200ms)
- Ajouter un overlay semi-transparent sur le reste de l'interface
- Fermer au clic en dehors du menu

#### 4.5 Tests

- Tester responsive sur 3 tailles (mobile, tablette, desktop)
- Verifier la navigation entre PV via le menu
- Verifier que le menu se ferme correctement

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

| Session | Contenu | Modele | Priorite |
|---------|---------|--------|----------|
| **1** | Filtre categorie + highlight + format total | Sonnet | **CRITIQUE** |
| **2** | Articles (badge, feedback, couleurs, panier vide, prix) | Sonnet | Haute |
| **3** | Paiement (couleurs boutons, confirmation, succes, retour carte) | Sonnet | Moyenne |
| **4** | Header, sidebar, footer, menu burger | Sonnet | Moyenne |
| **5** | Responsive tablette, zones tactiles | Sonnet | Haute |

**Ordre recommande** : Session 1 → Session 2 → Session 5 → Session 3 → Session 4

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
9. **Ne pas casser les tests existants** : 46 pytest verts + Playwright 39-41
10. **Ne pas toucher au JS sauf** `articles.js:articlesDisplayCategory` (Session 1) et les micro-animations CSS
