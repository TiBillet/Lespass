# Gestion globale des erreurs htmx (4xx/5xx)

## Sources

- htmx quirks : https://htmx.org/quirks/
  - Quirk #4 : "Error Status Code Handling — HTTP 4xx and 5xx responses don't trigger swaps by default"
- Port WASM → htmx (retour d'expérience) : https://htmx.org/essays/a-real-world-wasm-to-htmx-port/
- Le futur de htmx (stabilité et quirks assumés) : https://htmx.org/essays/future/
- Alternatives à htmx : https://htmx.org/essays/alternatives/
- Skill DJC — section "Quirks htmx", point 2

## Constat actuel sur Lespass

L'audit du code révèle une gestion d'erreurs htmx **partielle et fragmentée** :

**Ce qui existe :**
- `htmx:afterRequest` listener pour SweetAlert2 dans `BaseBillet/templates/htmx/base.html`
- `htmx:beforeSwap` dans `crowds/templates/crowds/views/detail.html` — bloque le swap
  pour les réponses JSON (Stripe), mais ne gère pas les erreurs HTML
- Validation client avec `validateForm()` dans `BaseBillet/static/mvt_htmx/js/commun.js`
  (HTML5 checkValidity avant la requête)
- Loading states extension custom

**Ce qui manque :**
- **Aucun handler global pour les erreurs 4xx/5xx** → si le serveur renvoie une 422
  (validation) ou une 500, htmx ne swap pas et l'utilisateur ne voit rien
- Pas de `htmx:responseError` handler
- Pas de toast automatique sur erreur serveur
- La gestion est faite au cas par cas dans chaque template au lieu d'être centralisée

## Impact concret

Scénario type : un utilisateur soumet un formulaire d'adhésion, le serializer
renvoie une erreur 422 avec le HTML du formulaire + messages d'erreur.
Aujourd'hui, **htmx ignore la réponse** et l'utilisateur ne voit aucun feedback.

## Actions possibles

### 1. Handler global htmx:beforeOnLoad (priorité haute)

Ajouter dans le base template (`BaseBillet/templates/htmx/base.html`) :

```javascript
/**
 * Gestion globale des erreurs HTTP pour htmx
 * Par défaut htmx ignore les réponses 4xx et 5xx.
 * Ce handler force le swap pour les erreurs de validation (422)
 * et affiche un toast pour les erreurs serveur (500).
 * / Global HTTP error handling for htmx — forces swap on 422, shows toast on 500
 *
 * LOCALISATION : BaseBillet/templates/htmx/base.html
 *
 * Source : https://htmx.org/quirks/ (quirk #4)
 */
document.addEventListener("htmx:beforeOnLoad", function(event) {
    const status_code_de_la_reponse = event.detail.xhr.status;
    const content_type_de_la_reponse = (
        event.detail.xhr.getResponseHeader('Content-Type') || ''
    ).toLowerCase();
    const la_reponse_est_du_html = content_type_de_la_reponse.includes('text/html');

    // Erreur de validation (422) : le serveur renvoie le formulaire avec les erreurs
    // On force le swap pour que l'utilisateur voie les messages d'erreur
    // / Validation error (422): server returns form with errors, force swap
    if (status_code_de_la_reponse === 422 && la_reponse_est_du_html) {
        event.detail.shouldSwap = true;
        event.detail.isError = false;
    }

    // Erreur serveur (500) : afficher un toast d'erreur
    // / Server error (500): show error toast
    if (status_code_de_la_reponse >= 500) {
        Swal.fire({
            icon: 'error',
            title: 'Erreur serveur',
            text: 'Une erreur est survenue. Veuillez réessayer.',
            toast: true,
            position: 'top-end',
            timer: 5000,
        });
    }

    // Erreur 403 (permission) : afficher un toast
    // / Permission error (403): show toast
    if (status_code_de_la_reponse === 403) {
        Swal.fire({
            icon: 'warning',
            title: 'Accès refusé',
            text: 'Vous n\'avez pas les droits pour cette action.',
            toast: true,
            position: 'top-end',
            timer: 5000,
        });
    }
});
```

### 2. Côté Django : renvoyer 422 pour les erreurs de validation

Standardiser dans tous les ViewSets : quand un serializer est invalide,
renvoyer le partial HTML avec `status=422` au lieu de `status=200` :

```python
# Pattern à appliquer dans tous les ViewSets
if not serializer_de_validation.is_valid():
    return render(request, "module/partials/form.html", {
        "serializer": serializer_de_validation,
    }, status=422)
```

### 3. Handler htmx:responseError pour les erreurs réseau

```javascript
/**
 * Gestion des erreurs réseau (timeout, serveur injoignable)
 * / Network error handling (timeout, server unreachable)
 */
document.addEventListener("htmx:responseError", function(event) {
    Swal.fire({
        icon: 'error',
        title: 'Erreur de connexion',
        text: 'Le serveur ne répond pas. Vérifiez votre connexion.',
        toast: true,
        position: 'top-end',
        timer: 5000,
    });
});
```

## Fichiers concernés

| Fichier | Changement |
|---|---|
| `BaseBillet/templates/htmx/base.html` | Ajouter handlers globaux htmx:beforeOnLoad et htmx:responseError |
| Tous les ViewSets avec formulaires | Standardiser status=422 pour les erreurs de validation |
| `BaseBillet/static/mvt_htmx/js/commun.js` | Éventuellement déplacer les handlers dans un fichier dédié |

## Priorité

**Haute** — c'est un bug UX silencieux. Les utilisateurs soumettent des formulaires,
le serveur renvoie une erreur, et rien ne se passe visuellement. Ça donne
l'impression que l'application est cassée alors que le serveur fait son travail.
