# Session 02 — Extraction CSS des templates

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django + HTMX + Cotton components).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune opération git.**

Les templates contiennent ~2171 lignes de CSS inline (`<style>` blocks).
Le but est de les extraire dans des fichiers `.css` séparés dans `laboutik/static/css/`.

**Règles absolues** :
- Ne PAS renommer de classes CSS (les tests Playwright les utilisent)
- Ne PAS modifier le HTML ni le JS
- Ne PAS fusionner les styles entre composants
- Le rendu visuel doit être IDENTIQUE avant et après

## TÂCHE 1 — Identifier tous les `<style>` blocks

Cherche tous les `<style>` blocks dans les templates laboutik :

```bash
grep -rn "<style>" laboutik/templates/ | head -40
```

Note chaque fichier, le nombre de lignes CSS, et le contenu du block.

## TÂCHE 2 — Extraire les styles overlay (14 partials dupliqués)

Les fichiers `laboutik/templates/laboutik/partial/hx_*.html` partagent des styles
overlay similaires (`#messages`, `#confirm`, `.message-title`, boutons, etc.).

1. Lis chaque partial qui a un `<style>` block
2. Crée `laboutik/static/css/overlay.css`
3. Copie tous les styles overlay dedans, en dédupliquant (beaucoup sont identiques)
4. Supprime les `<style>` blocks des partials
5. Ajoute dans `laboutik/templates/laboutik/base.html` :
   ```html
   <link rel="stylesheet" href="{% static 'css/overlay.css' %}">
   ```

## TÂCHE 3 — Extraire les styles des composants Cotton

Pour chaque fichier Cotton qui a un `<style>` block :

| Source | Destination |
|--------|-------------|
| `cotton/articles.html` | `laboutik/static/css/articles.css` |
| `cotton/addition.html` | `laboutik/static/css/addition.css` |
| `cotton/header.html` | `laboutik/static/css/header.css` |
| `cotton/categories.html` | `laboutik/static/css/categories.css` |

Pour chaque :
1. Couper le `<style>...</style>` entier
2. Coller dans le fichier .css
3. Ajouter le `<link>` dans `base.html`

## TÂCHE 4 — Extraire les styles footer des 3 views

Les fichiers de vue contiennent du CSS footer dupliqué :
- `laboutik/templates/laboutik/views/common_user_interface.html`
- `laboutik/templates/laboutik/views/kiosk.html`
- `laboutik/templates/laboutik/views/tables.html`

1. Crée `laboutik/static/css/footer.css`
2. Copie les styles footer (boutons RESET/CHECK/VALIDER), déduplique
3. Supprime des templates
4. Ajoute le `<link>` dans `base.html`

Si d'autres styles restent dans ces views (pas le footer), les extraire aussi
dans des fichiers dédiés ou dans un `views.css`.

## TÂCHE 5 — Vérifier qu'aucun `<style>` ne reste

```bash
grep -rn "<style>" laboutik/templates/
```

Si des `<style>` restent (ex: styles très spécifiques à un seul partial), c'est OK
tant qu'ils ne sont PAS dupliqués dans d'autres fichiers. Documenter pourquoi.

## VÉRIFICATION

### Commande collectstatic

```bash
docker exec lespass_django poetry run python manage.py collectstatic --noinput
```

Les nouveaux fichiers CSS doivent être collectés dans `www/static/css/`.

### Tests E2E (CRITIQUES — valident le rendu visuel)

```bash
cd /home/jonas/TiBillet/dev/Lespass/tests/playwright && npx playwright test tests/laboutik/ --reporter=list
```

TOUS les tests Playwright doivent passer. Si un test échoue sur un sélecteur CSS
(élément invisible, mauvaise couleur, etc.), c'est que l'extraction a cassé quelque chose.

Spécifiquement :
```bash
npx playwright test tests/laboutik/45-laboutik-pos-tiles-visual.spec.ts
npx playwright test tests/laboutik/44-laboutik-adhesion-identification.spec.ts
```

### Tests unitaires (doivent toujours passer)

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
```

### Critère de succès

- [ ] Tous les `<style>` blocks sont extraits (sauf exceptions documentées)
- [ ] Fichiers CSS créés dans `laboutik/static/css/`
- [ ] `base.html` charge tous les fichiers CSS
- [ ] `collectstatic` réussit
- [ ] TOUS les tests Playwright passent (rendu identique)
- [ ] TOUS les tests pytest passent
