# Session 03 — Composant Cotton `<c-footer>`

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django + HTMX + Cotton components).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune opération git.**

Le CSS du footer a été extrait dans `laboutik/static/css/footer.css` (Session 02).
Le HTML du footer est encore dupliqué dans 3 templates de vue.

## TÂCHE — Créer le composant et remplacer

### 1. Lire les 3 footers existants

Lis le HTML du footer dans :
- `laboutik/templates/laboutik/views/common_user_interface.html`
- `laboutik/templates/laboutik/views/kiosk.html`
- `laboutik/templates/laboutik/views/tables.html`

Note les différences :
- `common_user_interface.html` : 3 boutons (RESET, CHECK CARTE, VALIDER avec total)
- `kiosk.html` : 2 boutons (CHECK CARTE, SERVICE DIRECT) — pas de VALIDER classique
- `tables.html` : 2 boutons (identique à kiosk)

Note les IDs (`#bt-reset`, `#bt-check-card`, `#bt-valider`), les `data-testid`
(`footer-reset`, `footer-check-carte`, `footer-valider`), et les attributs HTMX
(`hx-post`, `hx-trigger`, `onclick`).

### 2. Créer le composant Cotton

Fichier : `laboutik/templates/cotton/footer.html`

Le composant accepte des attributs booléens pour les variantes.
Utilise la syntaxe Cotton de Django :
```html
{% load cotton %}
{# Attributs : show_reset, show_check_carte, show_valider, show_service_direct #}
```

**Les IDs et data-testid doivent être IDENTIQUES** au code original.
Le JS `addition.js` référence `#bt-valider` directement — si l'ID disparaît, le POS casse.

### 3. Remplacer dans les 3 templates

```html
<!-- common_user_interface.html -->
<c-footer show_reset="true" show_check_carte="true" show_valider="true" />

<!-- kiosk.html -->
<c-footer show_reset="false" show_check_carte="true" show_service_direct="true" />

<!-- tables.html -->
<c-footer show_reset="false" show_check_carte="true" show_service_direct="true" />
```

Supprimer TOUT le HTML du footer hardcodé dans chaque fichier.

### 4. Vérifier les variables de contexte

Le footer VALIDER affiche le total (`{{ total }}`). Vérifier que la variable
`total` est disponible dans le contexte template de `common_user_interface.html`.
Si le total est mis à jour par JS (via `#addition-total`), vérifier que l'ID
est préservé dans le composant Cotton.

## VÉRIFICATION

### Tests E2E (CRITIQUES — le footer est dans CHAQUE flow)

```bash
docker exec lespass_django poetry run pytest tests/e2e/ -v -s
```

Spécifiquement :
```bash
# Le bouton VALIDER déclenche le paiement
docker exec lespass_django poetry run pytest tests/e2e/test_pos_paiement.py -v -s

# Le footer en mode adhésion
docker exec lespass_django poetry run pytest tests/e2e/test_pos_adhesion_nfc.py -v -s

# Les data-testid du footer
docker exec lespass_django poetry run pytest tests/e2e/test_pos_tiles_visual.py -v -s
```

### Tests unitaires

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
```

### Critère de succès

- [ ] `cotton/footer.html` créé avec attributs show_reset/check_carte/valider/service_direct
- [ ] Les 3 templates de vue utilisent `<c-footer ... />`
- [ ] Plus de HTML footer dupliqué dans les 3 fichiers
- [ ] `#bt-valider`, `#bt-reset`, `#bt-check-card` existent dans le DOM
- [ ] Les `data-testid` sont identiques
- [ ] TOUS les tests E2E passent
- [ ] TOUS les tests pytest passent
