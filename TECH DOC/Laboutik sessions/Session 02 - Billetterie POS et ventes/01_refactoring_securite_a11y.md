# Session 01 — Sécurité + Accessibilité

## CONTEXTE

Tu travailles sur le projet Lespass (Django, HTMX, django-tenants).
Le module `laboutik/` est un POS (caisse tactile).

Lis les règles du projet : `GUIDELINES.md` et `CLAUDE.md` à la racine.
Le code est FALC (Facile À Lire et Comprendre) : commentaires bilingues FR/EN,
`viewsets.ViewSet`, `serializers.Serializer`, HTML partials HTMX.

**Ne fais aucune opération git.** Le mainteneur s'en occupe.

## TÂCHE 1 — Validation prix libre côté serveur

### Ce qu'il faut comprendre

Le POS permet des "prix libres" (l'utilisateur saisit le montant). Actuellement
la validation du montant minimum est faite uniquement en JavaScript (`tarif.js`).
Un utilisateur malveillant pourrait envoyer un montant inférieur au minimum via curl.

### Ce qu'il faut faire

1. Lis `laboutik/views.py` — cherche la fonction qui traite les articles du panier
   après le POST de paiement. Cherche `custom_amount_centimes` ou `custom-` dans le code.

2. Lis `laboutik/serializers.py` — cherche `extraire_articles_du_post()` pour comprendre
   comment le `custom_amount_centimes` est extrait du POST.

3. Trouve l'endroit où les articles sont chargés depuis la DB (Product + Price) après
   l'extraction du POST. C'est là qu'il faut ajouter la validation.

4. Ajoute la vérification :
   ```python
   if custom_amount_centimes is not None:
       prix_minimum_centimes = int(round(price.prix * 100))
       if custom_amount_centimes < prix_minimum_centimes:
           raise ValueError(_(
               f"Montant libre ({custom_amount_centimes/100:.2f}€) "
               f"inférieur au minimum ({prix_minimum_centimes/100:.2f}€)"
           ))
   ```

5. Vérifie que cette validation est atteinte par TOUS les chemins de paiement
   (espèces, CB, chèque, NFC). Cherche les appels vers la fonction de chargement
   des articles.

## TÂCHE 2 — Fix XSS dans tarif.js

### Ce qu'il faut comprendre

`laboutik/static/laboutik/js/tarif.js` construit l'overlay de sélection de tarif
avec `innerHTML` et des template literals contenant le nom du produit.
Si un nom de produit contient `<script>` ou `<img onerror=...>`, il s'exécute.

### Ce qu'il faut faire

1. Lis `laboutik/static/laboutik/js/tarif.js` en entier.

2. Dans la fonction `tarifSelection()`, trouve les endroits où `name`, `displayName`,
   `tarif.name` sont injectés dans le HTML via template literals.

3. Pour chaque injection de texte dynamique, remplace par une construction sûre.
   Par exemple, au lieu de :
   ```javascript
   boutonsHtml += `<div class="tarif-btn-label">${tarif.name}</div>`
   ```
   Crée l'élément via DOM API et utilise `textContent` :
   ```javascript
   const label = document.createElement('div')
   label.className = 'tarif-btn-label'
   label.textContent = tarif.name
   ```
   Ou utilise une fonction d'échappement HTML si la construction DOM est trop lourde.

4. **Ne change PAS la logique** du JS (pas de refactoring). Juste sécuriser l'injection.

5. Teste manuellement : ouvrir la caisse, cliquer sur un article multi-tarif,
   vérifier que l'overlay s'affiche correctement.

## TÂCHE 3 — Accessibilité aria-live

### Ce qu'il faut faire

1. Lis `laboutik/templates/laboutik/partial/hx_messages.html`.
   Trouve le conteneur principal (la div racine du partial).
   Ajoute `aria-live="assertive"` dessus (les messages d'erreur doivent être annoncés immédiatement).

2. Lis `laboutik/templates/cotton/addition.html`.
   Trouve l'élément `#addition-list` (la liste des articles du panier).
   Ajoute `aria-live="polite"` dessus (les mises à jour du panier sont moins urgentes).

## VÉRIFICATION

Après chaque tâche, lance les tests pour vérifier qu'il n'y a pas de régression.

### Tests unitaires

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_paiement_especes_cb.py -v
docker exec lespass_django poetry run pytest tests/pytest/test_pos_views_data.py -v
docker exec lespass_django poetry run pytest tests/pytest/test_caisse_navigation.py -v
```

Tous doivent passer. Si un test échoue, c'est que la validation prix libre casse un
cas existant — lis le test pour comprendre pourquoi.

### Tests E2E

```bash
docker exec lespass_django poetry run pytest tests/e2e/test_pos_tiles_visual.py -v -s
docker exec lespass_django poetry run pytest tests/e2e/test_pos_adhesion_nfc.py -v -s
```

Le test `test_pos_tiles_visual` vérifie le rendu des tuiles (dont le multi-tarif modifié par le fix XSS).
Le test `test_pos_adhesion_nfc` vérifie l'adhésion (qui utilise le prix libre).

### Critère de succès

- [ ] Tous les tests pytest passent
- [ ] Tous les tests E2E passent
- [ ] `aria-live="assertive"` est sur le conteneur de `hx_messages.html`
- [ ] `aria-live="polite"` est sur `#addition-list` dans `addition.html`
- [ ] L'overlay multi-tarif s'affiche sans HTML cassé après le fix textContent
