# Vendoring de htmx : copier le source plutôt que dépendre de npm/CDN

## Sources

- Vendoring (essai de Carson Gross) : https://htmx.org/essays/vendoring/
- Le futur de htmx (stabilité, releases trimestrielles) : https://htmx.org/essays/future/
- Alternatives à htmx : https://htmx.org/essays/alternatives/

## Contexte

L'article "Vendoring" de Carson Gross (créateur de htmx) plaide pour copier
directement le code source des bibliothèques dans son projet plutôt que de passer
par un gestionnaire de paquets. Il illustre avec htmx lui-même : 13 dépendances
directes de développement → 411 dépendances au total → 110 Mo de node_modules.

L'article "The future of htmx" confirme cette approche : htmx passe en releases
trimestrielles avec une politique de stabilité assumée. Le fichier htmx.min.js
ne va quasiment plus changer — c'est le candidat idéal pour le vendoring.

## Constat actuel sur Lespass

htmx est déjà vendored dans le projet (fichier JS dans les statics), ce qui est
la bonne approche. Ce TODO est surtout un rappel de continuer à suivre ce pattern
pour les autres dépendances JS et de ne pas revenir vers npm pour les librairies
front légères.

## Recommandation

Maintenir le pattern actuel. Pour toute nouvelle dépendance JS :
1. Se demander si on en a vraiment besoin
2. Si oui, copier le fichier source dans `static/js/vendor/` ou équivalent
3. Documenter la version dans un commentaire en tête du fichier
4. Ne pas passer par npm/CDN sauf pour les outils de build (pas le runtime)

## Priorité

Information / veille — pas d'action immédiate nécessaire.
Garder en tête pour les décisions futures.
