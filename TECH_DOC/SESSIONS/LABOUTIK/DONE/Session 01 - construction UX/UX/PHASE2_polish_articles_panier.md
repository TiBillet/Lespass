# UX Phase 2 — Polish articles et panier

## Prompt

```
On travaille sur l'UX de l'interface POS LaBoutik.
Lis le plan UX : laboutik/doc/UX/PLAN_UX_LABOUTIK.md (section "Session 2" et "Ecran principal").
Prerequis : la Phase 1 UX doit etre faite (filtre categories fonctionne).

Contexte technique :
- Interface POS tactile (caisse de bar/restaurant)
- Stack : Django + HTMX + CSS custom, JS vanilla
- Skill /stack-ccc : commentaires FALC bilingues FR/EN
- Variables CSS : palette.css, sizes.css
- Composants cotton : laboutik/templates/cotton/
- Fichier CSS principal : laboutik/static/css/modele00.css

Tache 1 — Masquer le badge quantite "0" :

1. Lis `laboutik/templates/cotton/articles.html` — repere le badge quantite.
2. Par defaut, le badge affiche "0" sur chaque article → bruit visuel inutile.
3. En CSS : masquer le badge quand il contient "0" (opacity: 0 ou visibility: hidden).
4. En JS : quand la quantite passe de 0 a 1, rendre le badge visible
   avec une micro-animation (transition opacity 200ms ease).
5. Quand RESET (evenement `articlesReset`) : remettre opacity a 0.
6. Le badge sur l'article et le compteur dans le panier doivent rester synchronises.

Tache 2 — Feedback tactile au clic :

1. Dans `laboutik/templates/cotton/articles.html`, ajouter dans le <style> :
   - `.article-container { transition: transform 100ms ease; }`
   - `.article-container:active { transform: scale(0.95); }`
2. L'animation doit etre interruptible (transition CSS, pas @keyframes).
3. Ne pas casser le onclick existant.

Tache 3 — Couleurs des articles sans categorie :

Les articles Recharge (RE/RC/TM) et Adhesion (AD) n'ont pas de `categorie_pos`
et s'affichent sur fond blanc/gris → peu visibles sur le fond sombre.

1. Lis `laboutik/management/commands/create_test_pos_data.py` — repere ou les
   produits de test sont crees.
2. Ajoute des couleurs via `couleur_fond_pos` et `couleur_texte_pos` :
   - Recharges (RE/RC/TM) : fond `#2e7d32` (vert fonce), texte blanc
   - Adhesion (AD) : fond `#37474f` (gris bleu fonce), texte blanc
3. Relance la commande `create_test_pos_data` pour appliquer.

Tache 4 — Panier vide : message d'accueil :

1. Lis `laboutik/templates/cotton/addition.html` — repere la zone #addition-list.
2. Ajoute un placeholder visible quand le panier est vide :
   - Icone fa-shopping-cart, texte "Panier vide" (traduit avec {% translate %})
   - Style : centre vertical/horizontal, couleur --gris05, opacity 0.4
   - Masque quand le premier article est ajoute (via JS ou CSS :has())
3. data-testid="addition-empty-placeholder"

Tache 5 — Prix qui deborde :

1. Lis `laboutik/templates/cotton/articles.html` — repere `.article-footer-layer`.
2. Le prix "10,00 €" ou "15,00 €" depasse de la zone footer.
3. Corrige : reduire font-size du prix (0.85rem), ajouter `tabular-nums`,
   eventuellement `overflow: hidden; text-overflow: ellipsis`.
4. Tester avec des prix longs (100,00 €).

Regles :
- Commentaires FALC bilingues FR/EN
- data-testid sur les nouveaux elements
- Ne pas casser les tests existants
- `manage.py check` apres modifications
```

## Verification Chrome

Ouvrir : `https://lespass.tibillet.localhost/laboutik/caisse/point_de_vente/?uuid_pv=a788a85a-f955-4209-b8f4-82faa8ba5543&tag_id_cm=A49E8E2A`

### Test 1 : Badge quantite masque
1. Au chargement, aucun badge "0" ne doit etre visible sur les articles
2. Cliquer sur "Biere" → badge "1" apparait avec une transition douce
3. Cliquer encore → badge passe a "2"
4. Cliquer RESET → tous les badges disparaissent (opacity 0)

### Test 2 : Feedback tactile
1. Cliquer sur un article et maintenir le clic
   - **Attendu** : l'article se reduit legerement (scale 0.95)
2. Relacher → l'article revient a sa taille normale
3. Tester sur Chrome DevTools avec "Toggle device toolbar" (mode tactile)

### Test 3 : Couleurs recharges/adhesion
1. Les articles "Recharge EUR Test", "Recharge Cadeau Test", "Recharge Temps Test"
   doivent avoir un fond vert fonce (pas blanc)
2. L'article "Adhesion POS Test" doit avoir un fond gris-bleu (pas blanc)
3. Le texte doit etre blanc et lisible sur ces fonds

### Test 4 : Panier vide
1. Au chargement (panier vide), la zone addition a droite doit afficher
   une icone panier + "Panier vide" en gris discret
2. Ajouter un article → le placeholder disparait, l'article s'affiche
3. RESET → le placeholder reapparait

### Test 5 : Prix lisibles
1. L'article "Adhesion POS Test" (15,00 €) doit avoir son prix
   entierement visible sans debordement
2. L'article "Recharge EUR Test" (10,00 €) idem
3. Les prix doivent etre en `tabular-nums` (chiffres alignes)

## Fichiers concernes

- `laboutik/templates/cotton/articles.html` — badge, feedback, prix
- `laboutik/templates/cotton/addition.html` — placeholder panier vide
- `laboutik/static/js/articles.js` — logique badge (si necessaire)
- `laboutik/management/commands/create_test_pos_data.py` — couleurs fixtures
- `laboutik/static/css/modele00.css` ou inline <style> dans cotton — CSS
