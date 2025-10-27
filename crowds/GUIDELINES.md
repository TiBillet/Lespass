---
id: crowds-guidelines
title: CROWDS — Guide de fabrication
sidebar_label: Guide CROWDS
slug: /crowds/guidelines
---

Ce document résume ce que nous avons appris en construisant l’app de financement participatif « CROWDS » dans TiBillet, et la manière de l’étendre proprement.

Objectif: des pages rapides, accessibles, sans « blink », en HTML rendu côté serveur avec un minimum de JavaScript. HTMX orchestre les interactions.


## Principes clés (à toujours respecter)

- Rendu côté serveur uniquement
  - Les vues retournent des templates Django (pages complètes) ou des partiels (partials) HTML. Pas de JSON pour l’UI.
  - Conserver des `href`/`action` pour le repli sans JS.
- HTMX partout, mais fin et ciblé
  - Utiliser `hx-get`/`hx-post`, `hx-target`, `hx-swap`, `hx-push-url` pour éviter le rechargement complet et garder l’historique.
  - Ne remplacer que ce qui doit l’être (conteneurs précis) pour supprimer tout clignotement.
- Anti‑blink
  - Navigation liste ⇄ détail: `hx-target="body"` + `hx-swap="innerHTML"` pour ne pas toucher au `<head>`.
  - Pagination/recherche: swap du conteneur liste uniquement (`#crowds_list`).
- Minimal JS, préférence au HTML/CSS
  - JS seulement pour de petits dialogues (SweetAlert2), et pour appliquer la largeur de barres de progression après swap.
- FALC (Facile à Lire et à Comprendre)
  - Mots simples, phrases courtes, pictos explicites, code couleur cohérent, hiérarchie visuelle claire.
- Accessibilité et thèmes
  - `aria-label`, `visually-hidden`, contraste fort (clair/sombre), focus visibles.
- Internationalisation
  - Utiliser `{% translate %}` / `gettext` pour tout texte visible.
- Sécurité
  - CSRF via `hx-headers` sur `<body>`, contrôles d’accès au niveau des actions.
- Performances
  - Précharger relations (`select_related`, `prefetch_related`).
  - Paginer la liste. Éviter le N+1.


## Architecture fonctionnelle

- Modèles (schema.org friendly)
  - `Initiative` (Project): nom, description, image, objectif en centimes (`funding_goal`), devise via `asset`.
  - `Contribution`: montants financiers reçus (en centimes), `amount_eur` en propriété.
  - `Vote`: un vote de pertinence par utilisateur·ice et par initiative (unicité), compteur exposé via `initiative.votes_count`.
  - `Participation`: proposition d’aide avec budget demandé; états: `requested` → `approved_admin` → `completed_user` → `validated_admin`; `time_spent_minutes`.
  - `Tag`: `name`, `slug`, `color_bg` (hex). Couleur de texte automatique (noir/blanc) via contraste YIQ; rendu inline via `style_attr`.
  - `CrowdConfig` (singleton): titres/description, libellé bouton « voter ».

- Vues (DRF ViewSet, mais rendu templates)
  - `InitiativeViewSet.list`: tri par votes puis date; filtrage par `?q=` (titre/description/tags) et `?tag=`; pagination; HTMX renvoie `crowds/partial/list.html` si `HX-Target == 'crowds_list'`.
  - `InitiativeViewSet.retrieve`: page détail; passe contributions, votes, participations et métriques d’avancement au template.
  - `@action vote (POST)`: crée le vote si besoin; retourne toujours le partiel `crowds/partial/votes_badge.html` et émet un `HX-Trigger` `crowds:vote` (payload `{created, uuid}`).
  - `@action participate/complete/approve/validate (POST)`: contrôlent strictement droits/états; retournent toujours `crowds/partial/participations.html`.

- Templates (emplacement)
  - Pages: `crowds/views/list.html`, `crowds/views/detail.html` (étendent `reunion/base.html`).
  - Partiels: `crowds/partial/list.html`, `crowds/partial/card.html`, `crowds/partial/votes_badge.html`, `crowds/partial/participations.html`.
  - Base TiBillet: `BaseBillet/templates/reunion/base.html` charge Bootstrap, HTMX, sweetalert, thème clair/sombre…


## Règles HTMX concrètes

- Navigation liste ⇄ détail (anti‑blink)
  - Détail depuis une carte:
    ```html
    <a href="{{ initiative.get_absolute_url }}"
       hx-get="{{ initiative.get_absolute_url }}"
       hx-target="body" hx-swap="innerHTML" hx-push-url="true">Détails</a>
    ```
  - Bouton « Retour » en détail:
    ```html
    <a href="{% url 'crowds-list' %}"
       hx-get="{% url 'crowds-list' %}"
       hx-target="body" hx-swap="innerHTML" hx-push-url="true">← Retour</a>
    ```
- Pagination + recherche + tags (sur la liste)
  - Conteneur liste: `id="crowds_list" hx-boost="true" hx-target="#crowds_list" hx-swap="outerHTML"`.
  - Formulaire de recherche: `hx-get="" hx-target="#crowds_list" hx-swap="outerHTML" hx-push-url="true" hx-trigger="keyup changed delay:500ms from:#crowds_q, submit"`.
  - Liens de pagination: toujours conditionner `previous_page_number/next_page_number` par `has_previous/has_next` pour éviter `EmptyPage`.
  - Liens de tags: conservent `q` et filtrent via `hx-get` vers `body` (page complète) ou vers `#crowds_list` selon l’UX voulue; garder `hx-push-url`.
- Votes (swap fin et feedback utilisateur)
  - Bouton connecté:
    ```html
    <button hx-post="{{ initiative.get_absolute_url }}vote/"
            hx-target="#votes-{{ initiative.uuid }}" hx-swap="outerHTML">Voter</button>
    ```
  - Le serveur renvoie le badge HTML et émet `HX-Trigger: {"crowds:vote": {"created": true|false, "uuid": "…"}}`.
  - Côté client, un listener affiche un toast SweetAlert2 sur `document.body`:
    ```js
    document.body.addEventListener('crowds:vote', e => {
      const created = !!(e && e.detail && e.detail.created);
      Swal.fire({toast:true,position:'top',timer:1600,showConfirmButton:false,
                 icon: created?'success':'info',
                 title: created? 'Merci pour votre vote !' : 'Votre vote est déjà pris en compte.'});
    });
    ```
- Participations (création et transitions d’état)
  - Dialogues SweetAlert pour saisir description, montant (euros) et temps passé.
  - `hx-post` vers `…/participate/`, `…/participations/{pid}/complete|approve|validate/` avec `hx-target="#participations_list"` + `hx-swap="outerHTML"`.
  - Le serveur renvoie le tableau `participations.html` mis à jour (HTML uniquement).


## FALC: règles UI rapides

- Toujours expliquer avec des mots simples ce que l’on voit (« Argent reçu », « Demandes validées »).
- Utiliser des pictos explicites (ex: `bi-piggy-bank`, `bi-clipboard-check`).
- Afficher les montants au format « 1 234,56 € EUR » (via `floatformat:2` et code devise). 
- Code couleur intuitif et constant:
  - Avancement financement: `info` < 80% < `warning` < 100% ≤ `success`.
  - Ratio demandes/financements: `success` (<80%), `warning` (80–99%), `danger` (≥100%).
- Pastilles de tags colorées avec contraste automatique (lisible en clair/sombre).
- Textes d’aide courts (`role="note"`, `aria-label`), et blocs compacts (`bg-body-tertiary`).


## Accessibilité et thèmes

- `aria-label` pour les groupes d’info, `visually-hidden` pour décrire les valeurs.
- Ne pas encoder de texte dans les icônes; elles sont décoratives (`aria-hidden="true"`).
- Utiliser les classes Bootstrap (`text-body`, `text-muted`, `bg-body-tertiary`, etc.) pour respecter clair/sombre.


## Contrôles d’accès et transitions d’état

- Votes: user authentifié; idempotent (un seul vote par couple user×initiative).
- Participations:
  - `participate`: user connecté.
  - `complete`: propriétaire uniquement; états autorisés: `requested` ou `approved_admin` → `completed_user` (+ minutes > 0).
  - `approve`: admin/staff uniquement; `requested` → `approved_admin`.
  - `validate`: admin/staff uniquement; `completed_user` → `validated_admin`.
- Barre « demandes vs financements »: ne comptabilise que les participations `approved_admin`.


## Bonnes pratiques de templates

- Étendre `reunion/base.html` pour obtenir la charte, les assets et les en‑têtes.
- Laisser `<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>` pour les POST HTMX.
- Conserver `href`/`action` pour le fallback sans JS.
- Factoriser les éléments réutilisables en partiels (`partial/*.html`).


## Admin

- Tous les ModelAdmin sont enregistrés sur `staff_admin_site` (Unfold): évite les `NoReverseMatch`.
- `InitiativeAdmin`: inlines Contributions/Participations/Votes, filtres par tags, badges de couleur pour les demandes validées.
- `ParticipationAdmin`: `list_editable = ("state",)` + actions « Approuver » et « Valider ».
- `TagAdmin`: aperçu couleur via `style_attr`.


## Démo data (en DEV uniquement)

- Module: `crowds/demo_data.py`, fonction `seed()` idempotente.
- Appelée depuis la liste quand `DEBUG` est vrai.
- Crée ~10 initiatives, des tags colorés, images, descriptions Markdown, et quelques contributions pour varier les jauges.


## Schéma.org (sémantique)

- `Initiative` ≈ `Project`.
- `Participation` ≈ `Action` avec `ActionStatusType` et `MonetaryAmount` (stocké en centimes, exposé en euros pour l’UI).
- Les pages `detail` peuvent exposer du JSON‑LD si besoin (à calquer sur les pages « Event » existantes).


## Check‑list avant merge

- [ ] Toutes les interactions renvoient du HTML (partials) — pas de JSON UI.
- [ ] Pas de « blink »: navigations `body` et swaps ciblés.
- [ ] Recherche/pagination/tag OK, URLs mises à jour (`hx-push-url`).
- [ ] FALC: libellés simples, pictos, contrastes, aides d’accessibilité.
- [ ] i18n: tous les labels dans `{% translate %}`.
- [ ] Sécurité: droits des actions, CSRF OK.
- [ ] Admin: URLs fonctionnelles dans Unfold.


## Exemples rapides (copier‑coller)

- Conteneur de liste paginée (anti‑blink):
```html
<main id="crowds_list" hx-boost="true" hx-target="#crowds_list" hx-swap="outerHTML">
  {% include "crowds/partial/list.html" %}
</main>
```

- Lien de détail sans rechargement complet:
```html
<a href="{{ initiative.get_absolute_url }}" hx-get="{{ initiative.get_absolute_url }}"
   hx-target="body" hx-swap="innerHTML" hx-push-url="true">Détails</a>
```

- Bouton voter (connecté), swap fin sur le badge:
```html
<button hx-post="{{ initiative.get_absolute_url }}vote/"
        hx-target="#votes-{{ initiative.uuid }}" hx-swap="outerHTML">
  Voter
</button>
```

- Lien de pagination (activer seulement si `has_previous`):
```django
{% if page_obj.has_previous %}
  <a class="page-link" href="?page={{ page_obj.previous_page_number }}">&laquo;</a>
{% else %}
  <span class="page-link" aria-disabled="true">&laquo;</span>
{% endif %}
```


## Anti‑patterns (à éviter)

- Réponses JSON pour piloter l’UI (préférer HTML + `HX-Trigger` si nécessaire pour les toasts).
- Swapper `html`/`head` (provoque des clignotements et recharge les assets).
- JS volumineux pour des comportements que HTMX gère nativement.
- `previous_page_number`/`next_page_number` utilisés sans vérifier `has_previous/has_next`.


## Aller plus loin

- Ajouter des tests d’intégration HTMX (ex: vérif des headers et du contenu partiel).
- Marqueurs Schema.org sur la page détail.
- Éventuel renderer Markdown (actuellement, la description est affichée en texte/linebreaks).
