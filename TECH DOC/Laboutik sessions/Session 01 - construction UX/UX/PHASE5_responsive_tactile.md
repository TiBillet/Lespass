# UX Phase 5 — Responsive et ecrans tactiles

## Prompt

```
On travaille sur l'UX de l'interface POS LaBoutik.
Lis le plan UX : laboutik/doc/UX/PLAN_UX_LABOUTIK.md (section "Session 5").
Cette session optimise l'interface pour les tablettes POS (ecran cible : Sunmi D3mini 1278x800).

Contexte technique :
- Interface POS tactile (caisse de bar/restaurant)
- Stack : Django + HTMX + CSS custom, JS vanilla
- Breakpoints existants : 599px, 1022px, 1199px, 1278px (Sunmi D3mini)
- Variables CSS : sizes.css (--bt-article-width: 120px, --cat-width: 80px, etc.)
- Police : Luciole-regular (ne pas changer)
- User-select desactive globalement (interface tactile)

L'interface doit fonctionner parfaitement sur :
1. Tablette Sunmi D3mini (1278x800, paysage)
2. Tablette generique (1024x768, paysage)
3. Desktop (1920x1080)

Tache 1 — Audit responsive tablette Sunmi D3mini :

1. Ouvre Chrome DevTools, active "Toggle device toolbar", configure 1278x800.
2. Navigue vers l'interface POS.
3. Verifie que :
   - Tous les articles sont visibles sans scroll vertical (ou avec scroll naturel)
   - Les boutons de paiement sont assez gros pour le tactile (>= 48x48px)
   - Le panier (addition) est visible a droite
   - Le footer est visible et cliquable
   - Le header n'est pas tronque

4. Si des problemes sont detectes, corrige les breakpoints dans les templates cotton
   et/ou dans sizes.css.

Tache 2 — Mode portrait tablette (optionnel) :

Si la tablette est en portrait (800x1278) :
1. Verifier que le layout ne casse pas.
2. Si necessaire, adapter :
   - Les articles sur moins de colonnes (flex-wrap)
   - Le panier en overlay ou en bas au lieu d'a droite
   - Le footer reste accessible

Tache 3 — Taille des zones tactiles :

Regle : minimum 48x48px pour chaque zone cliquable (Google Material Design).

1. Articles : 120x120px → OK, rien a faire.
2. Categories sidebar : verifier hauteur de chaque item.
   Si < 48px, augmenter --cat-height ou le padding.
3. Boutons footer (RESET, CHECK CARTE, VALIDER) : verifier hauteur.
   --footer-container-height est 90px → OK pour le conteneur,
   mais verifier la zone cliquable reelle de chaque bouton.
4. Boutons "-" dans le panier (supprimer un article) : potentiellement trop petits.
   Verifier et agrandir si necessaire (min 44x44px).
5. Boutons de paiement (CASHLESS, ESPECE, CB) : --bt-basic-height est 120px → OK.
6. Bouton RETOUR : verifier taille.

Tache 4 — Contraste et lisibilite :

1. Verifier le contraste texte/fond sur tous les ecrans avec un outil
   (Chrome DevTools → Accessibility → Contrast ratio).
2. Cibles minimales :
   - Texte normal : ratio >= 4.5:1 (WCAG AA)
   - Texte gros (>= 18px bold ou >= 24px) : ratio >= 3:1
3. Points a verifier en priorite :
   - Labels des categories sidebar (texte gris clair sur fond sombre)
   - Prix des articles (texte sombre sur fond colore)
   - Texte du footer (blanc sur rouge/bleu/vert)

Regles :
- Modifier les CSS existants (palette.css, sizes.css, modele00.css, inline <style>)
- Ne pas ajouter de framework CSS
- Ne pas casser les breakpoints existants
- Tester sur au moins 3 tailles d'ecran
```

## Verification Chrome

### Test 1 : Sunmi D3mini (1278x800)
1. Chrome DevTools → Toggle device toolbar → Responsive → 1278x800
2. Ouvrir la page POS
   - **Attendu** : toute l'interface visible sans scroll vertical
   - **Attendu** : sidebar categories visible et cliquable
   - **Attendu** : grille d'articles occupe l'espace disponible
   - **Attendu** : panier (addition) visible a droite
   - **Attendu** : footer visible en bas
3. Ajouter des articles → le panier se met a jour
4. VALIDER → les boutons de paiement sont assez gros pour taper au doigt

### Test 2 : Tablette portrait (800x1278)
1. Chrome DevTools → Responsive → 800x1278
   - **Attendu** : le layout ne casse pas (pas de texte tronque, pas de scroll horizontal)
   - **Attendu** : le footer reste accessible

### Test 3 : Desktop (1920x1080)
1. Chrome DevTools → Responsive → 1920x1080
   - **Attendu** : l'interface occupe l'espace sans etre etree
   - **Attendu** : les articles ne sont pas minuscules

### Test 4 : Zones tactiles
1. Sur la taille 1278x800, utiliser l'inspecteur pour mesurer :
   - Chaque categorie sidebar : hauteur >= 48px
   - Chaque bouton footer : hauteur >= 48px
   - Boutons "-" dans le panier : >= 44x44px
2. Simuler le mode tactile (Chrome DevTools → Toggle device toolbar → Touch)
   - Taper sur chaque zone → doit reagir au premier tap

### Test 5 : Contraste
1. Chrome DevTools → Elements → Accessibility → Contrast ratio
2. Verifier les zones signalees en orange/rouge
3. Corriger si le ratio est < 4.5:1 (texte normal) ou < 3:1 (texte gros)

## Fichiers concernes

- `laboutik/static/css/sizes.css` — variables dimensions, breakpoints
- `laboutik/static/css/palette.css` — couleurs (si contraste insuffisant)
- `laboutik/static/css/modele00.css` — classes BF, media queries
- `laboutik/templates/cotton/articles.html` — responsive articles
- `laboutik/templates/cotton/categories.html` — taille items sidebar
- `laboutik/templates/cotton/addition.html` — responsive panier
- `laboutik/templates/cotton/header.html` — responsive header
