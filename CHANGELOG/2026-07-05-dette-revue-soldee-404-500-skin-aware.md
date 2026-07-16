# Dette de revue soldée : 404/500 skin-aware et parlantes sous HTMX + rangements / Review debt paid: skin-aware and HTMX-visible 404/500 + housekeeping

**Date :** 2026-07-05
**Migration :** Non / No

- **`handler404` (nouveau) + `handler500` enrichi** : les pages d'erreur
  passent par `get_context` → elles prennent le skin du tenant (fini la 404
  au look classic sur un tenant faire_festival) ET sont servies en fragment
  headless sous HTMX. Repli minimal si `get_context` échoue (une page
  d'erreur doit TOUJOURS s'afficher). Actifs quand DEBUG=0 — d'où le test
  direct `tests/pytest/test_handlers_erreur.py` (3 tests, RequestFactory).
- **Listener `htmx:beforeSwap` global (2 shells)** : par défaut htmx ignore
  les réponses non-2xx — un clic qui tombait en 404/500 ne produisait RIEN.
  Désormais la page d'erreur est swappée dans le body entier (HTML
  uniquement, les réponses JSON gardent leur traitement).
- **Rangements** : param `bloc` → `objet_cible` dans `_poser_fichier`
  (recevait aussi une Configuration), commentaire obsolète corrigé dans
  `seo/partials/tibillet_community_links.html`.
- **Finding retiré** : le `#paginator` « dupliqué en scroll infini » n'existe
  pas — les 4 emplacements (classic + ff) utilisent `hx-swap="outerHTML"`
  (remplacement, pas imbrication). L'agent d'audit avait supposé le swap par
  défaut sans lire l'attribut.
