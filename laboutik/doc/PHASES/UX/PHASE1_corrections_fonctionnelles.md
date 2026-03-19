# UX Phase 1 — Corrections fonctionnelles (prerequis)

## Prompt

```
On travaille sur l'UX de l'interface POS LaBoutik.
Lis le plan UX complet : laboutik/doc/UX/PLAN_UX_LABOUTIK.md (sections "Bugs fonctionnels" et "Ecran principal").
Cette session corrige les 3 bugs fonctionnels identifies lors de l'audit visuel.

Contexte technique :
- Interface POS tactile (caisse de bar/restaurant)
- Stack : Django + HTMX + CSS custom (pas de framework), JS vanilla
- Skill /stack-ccc : commentaires FALC bilingues FR/EN, data-testid, aria-live
- Police : Luciole-regular (ne pas changer)
- Variables CSS : palette.css (couleurs), sizes.css (dimensions)
- Composants cotton : laboutik/templates/cotton/

Tache 1 — Implementer le filtre par categorie (BUG-1, CRITIQUE) :

1. Lis `laboutik/static/js/articles.js` — cherche `articlesDisplayCategory` (ligne ~156).
   C'est un TODO. Le corps de la fonction est vide.

2. Lis `laboutik/static/js/categories.js` — comprends comment l'evenement
   `articlesDisplayCategory` est emis. Note le format de event.detail.category
   (ex: "cat-c2bab741-14c0-4af5-ab90-e61c3e8d202d" ou "cat-all").

3. Implemente le filtre dans `articlesDisplayCategory()` :
   - Selectionne tous les `.article-container`
   - Si category === 'cat-all' : tous visibles (display = '')
   - Sinon : masquer ceux qui n'ont pas la classe `category` (display = 'none')
   - Commentaires FALC bilingues FR/EN

4. Lis `laboutik/templates/cotton/categories.html` — ajoute un highlight
   sur la categorie active :
   - Ajouter une classe `.category-item-selected` quand on clique
   - Retirer la classe des autres
   - CSS : background-color rgba(255,255,255,0.08) + border-left 3px solid var(--vert01)

Tache 2 — Corriger le formatage du total (BUG-2) :

1. Lis `laboutik/templates/cotton/bt/paiement.html` — le total est affiche
   en float brut (6.5 au lieu de 6.50).
2. Lis `laboutik/views.py` — cherche `total_en_euros` dans `moyens_paiement()`.
   Le calcul `total_centimes / 100` produit un float Python sans formatage.
3. Corrige : soit passer le total en centimes au template et diviser avec le filtre
   `divide_by:100`, soit utiliser `floatformat:2` sur le float.
4. Verifie aussi dans `hx_card_feedback.html` : "Tirelire 0,0" → doit etre "0,00".

Tache 3 — Masquer uuid_transaction (BUG-3) :

1. Lis `laboutik/templates/laboutik/partial/hx_confirm_payment.html`
2. Ligne 5 : `<div>uuid_transaction = {{ uuid_transaction }}</div>` est visible.
3. Supprime cette ligne ou mets-la en `display:none` (c'est du debug).

Regles :
- Ne pas casser les tests existants (46 pytest verts)
- Commentaires FALC bilingues FR/EN sur tout le code modifie
- data-testid sur les nouveaux elements interactifs
- Lancer `manage.py check` apres les modifications
```

## Verification Chrome

Ouvrir : `https://lespass.tibillet.localhost/laboutik/caisse/point_de_vente/?uuid_pv=a788a85a-f955-4209-b8f4-82faa8ba5543&tag_id_cm=A49E8E2A`

### Test 1 : Filtre par categorie
1. L'ecran affiche tous les articles (categorie "Tous" active)
2. Cliquer sur "Bar" dans la sidebar gauche
   - **Attendu** : seuls les articles bleus (Biere, Coca, Eau, Jus d'orange, Limonade) sont visibles
   - **Attendu** : les articles Snacks, Vins, Recharges, Adhesion sont masques
3. Cliquer sur "Snacks"
   - **Attendu** : seuls Chips, Cacahuetes, Cookies sont visibles
4. Cliquer sur "Vins & Spiritueux"
   - **Attendu** : seuls Vin rouge, Vin blanc, Pastis sont visibles
5. Cliquer sur "Tous"
   - **Attendu** : tous les articles sont a nouveau visibles

### Test 2 : Highlight categorie active
1. Au chargement, "Tous" doit avoir un fond legerement plus clair ou une bordure gauche verte
2. Cliquer sur "Bar" → "Bar" est highlighte, "Tous" ne l'est plus
3. Cliquer sur "Snacks" → "Snacks" highlighte, "Bar" ne l'est plus

### Test 3 : Panier conserve lors du changement de categorie
1. Ajouter 1 Biere (categorie Bar) → panier affiche "1 Biere 5€"
2. Cliquer sur "Snacks" → Biere disparait de la grille
3. Le panier doit TOUJOURS afficher "1 Biere 5€" (pas de reset)
4. Cliquer sur "Tous" → Biere reapparait avec badge "1"

### Test 4 : Formatage total
1. Ajouter 1 Biere (5,00€) + 1 Eau (1,50€) → total 6,50€
2. Cliquer VALIDER → ecran moyens de paiement
   - **Attendu** : "TOTAL 6,50 €" (pas "6,5 €")
3. Cliquer RETOUR, puis CHECK CARTE, scanner carte client 1
   - **Attendu** : "Tirelire : 0,00 €" (pas "0,0")

### Test 5 : uuid_transaction masque
1. Ajouter un article, VALIDER, cliquer ESPECE
   - **Attendu** : l'ecran de confirmation n'affiche PAS "uuid_transaction ="

## Fichiers concernes

- `laboutik/static/js/articles.js` — articlesDisplayCategory()
- `laboutik/static/js/categories.js` — emission evenement (lecture seule)
- `laboutik/templates/cotton/categories.html` — highlight CSS
- `laboutik/templates/cotton/bt/paiement.html` — formatage total
- `laboutik/templates/laboutik/partial/hx_confirm_payment.html` — masquer uuid_transaction
- `laboutik/templates/laboutik/partial/hx_card_feedback.html` — formatage tirelire
