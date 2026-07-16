# Fix : liens morts de la home ff de repli + nettoyage vues sans route / Fix: dead links in ff fallback home + dead views cleanup

**Date :** 2026-07-05
**Migration :** Non / No

Contexte (audit « que se passe-t-il si module_pages est désactivé ? ») : les
routes en dur `/infos-pratiques/` et `/le-faire-festival/` avaient été retirées
de `BaseBillet/urls.py` (remplacées par des pages CMS servies par le catch-all
`/<slug>/`), mais deux restes traînaient :
- **La vieille home ff** (`pages/faire_festival/vues/accueil.html`, gabarit de
  repli quand module_pages est off ou sans page d'accueil publiée) gardait ses
  deux boutons en dur → 404 garanti précisément quand cette home s'affiche.
  Fix : `index()` expose `slugs_pages_publiees` et les boutons ne s'affichent
  que si la page CMS correspondante est publiée.
- **Code mort** : vues `infos_pratiques()` / `le_faire_festival()` (plus aucune
  route) et gabarits `pages/faire_festival/vues/{infos_pratiques,le_faire_festival}.html`
  (jamais rendus — les 200 observés venaient des pages CMS homonymes) SUPPRIMÉS.

Comportement module_pages OFF (vérifié) : `/` → home de repli du skin,
`/<slug>/` → 404 (y compris préview admin), navbar sans pages, section admin
« Site web » masquée, carte du dashboard pour réactiver.

**Fix test fragile** : `test_bloc_evenements_liste_les_a_venir` échouait selon
l'état de la base dev (200+ évènements futurs accumulés par les suites E2E →
l'évènement du test à +3 jours sortait du slice `[:100]`). `nombre_max=32000`
dans le test = déterministe. À noter pour plus tard : les E2E ne nettoient pas
leurs évènements (~160 résidus E2E/API/Playwright/Refund/Smoke sur lespass).
