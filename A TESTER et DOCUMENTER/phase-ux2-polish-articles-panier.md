# Phase UX 2 — Polish articles et panier (Session 2)

**Branche** : `integration_laboutik`
**Date** : 2026-03-16
**Audit FALC** : conforme (stack-ccc)

## Ce qui a ete fait

Ameliorations visuelles sur la grille d'articles et le panier :
reduction du bruit visuel, ajout de feedback tactile, placeholder panier vide,
et alignement numerique propre avec `tabular-nums`.

La tache 2.3 (couleurs articles sans categorie) a ete SKIP car les fixtures
assignent deja des categories avec couleurs a tous les produits.

## Fichiers modifies

| Fichier | Modification |
|---------|-------------|
| `laboutik/templates/cotton/articles.html` | CSS : badge invisible quand qty=0 (opacity 0 + transition 200ms), feedback tactile `:active` scale(0.95), `tabular-nums` sur prix et badge, anti-debordement prix (`text-overflow: ellipsis`) |
| `laboutik/static/js/articles.js` | `addArticle()` : `classList.add('badge-visible')` ; `articlesRemove()` : `classList.remove` si qty <= 0 ; `articlesReset()` : `classList.remove` dans forEach |
| `laboutik/templates/cotton/addition.html` | HTML : placeholder "Panier vide" avec icone + texte traduit + `data-testid` ; CSS : `.addition-placeholder` + `tabular-nums` sur prix et quantites |
| `laboutik/static/js/addition.js` | `additionInsertArticle()` : supprime placeholder ; `additionReset()` : recree placeholder avec texte i18n |
| `locale/fr/LC_MESSAGES/django.po` | Correction fuzzy "Panier vide" (etait "Fournie par") |
| `locale/en/LC_MESSAGES/django.po` | Traduction "Panier vide" → "Empty cart" |

## Tests a realiser

### Test 1 : Badge invisible quand quantite = 0 (tache 2.1)

1. Ouvrir `https://lespass.tibillet.localhost/laboutik/caisse/point_de_vente/`
2. **Attendu au chargement** : aucun badge "0" visible sur les articles
3. Cliquer sur un article (ex: Biere)
   - **Attendu** : le badge "1" apparait en fondu (transition opacity 200ms)
4. Cliquer encore sur le meme article
   - **Attendu** : le badge passe a "2" (reste visible)
5. Dans le panier, cliquer "-" jusqu'a ce que la quantite revienne a 0
   - **Attendu** : le badge disparait en fondu
6. Ajouter plusieurs articles differents, puis cliquer RESET
   - **Attendu** : tous les badges disparaissent d'un coup

### Test 2 : Feedback tactile au clic (tache 2.2)

1. Cliquer sur n'importe quel article
   - **Attendu** : l'article "retrecit" brievement (scale 0.95, 100ms)
2. Cliquer sur un article verrouille (overlay gris)
   - **Attendu** : le feedback `:active` se declenche visuellement mais rien ne se passe (JS ignore le clic)

### Test 3 : Panier vide — placeholder (tache 2.4)

1. Au chargement, regarder la zone panier (a droite sur desktop)
   - **Attendu** : icone panier + texte "Panier vide" centre, gris, discret (opacity 0.4)
2. Ajouter un article
   - **Attendu** : le placeholder disparait, la ligne article s'affiche
3. Cliquer RESET
   - **Attendu** : le placeholder "Panier vide" reapparait
4. Sur mobile : cliquer "Note" pour afficher le panier
   - **Attendu** : le placeholder est visible si le panier est vide

### Test 4 : Prix alignes et anti-debordement (tache 2.5)

1. Regarder les prix sur les articles
   - **Attendu** : les chiffres sont alignes verticalement (`tabular-nums`)
2. Regarder les prix et quantites dans le panier
   - **Attendu** : alignement propre (`tabular-nums`)
3. Chrome DevTools → 1278px (Sunmi D3mini)
   - **Attendu** : les prix ne debordent pas (tronques avec "..." si trop longs)

### Test 5 : Responsive

1. Chrome DevTools → 375px (mobile)
   - **Attendu** : articles et panier s'affichent correctement
2. Chrome DevTools → 1024px (desktop)
   - **Attendu** : panier visible a droite avec placeholder si vide
3. Chrome DevTools → 1278px (Sunmi D3mini)
   - **Attendu** : articles plus grands, prix non tronques sauf cas extreme

### Test 6 : i18n

1. Verifier que "Panier vide" s'affiche en francais
2. Changer la langue du navigateur en EN
   - **Attendu** : "Empty cart" s'affiche

## Compatibilite

- **Pas d'impact sur les tests existants** : les modifications sont CSS + micro-JS (classList toggle)
- **Pas de migration** necessaire
- **Pas de nouvelle dependance**
- **Fallback** : si JS ne charge pas, le badge "0" reste invisible (opacity: 0 par defaut) → mieux qu'avant
