# Blog dans la fixture de démo + zéro CDN (Leaflet et Plotly vendorisés) / Demo fixture blog + zero CDN (Leaflet and Plotly vendored)

**Date :** 2026-07-05
**Migration :** Non / No

- **Blog de démo** : `charger_site_lespass` construit désormais une page
  « Journal » (blocs PARAGRAPHE + LISTE_SOUS_PAGES) et 2 articles complets en
  blocs MARKDOWN (fresque participative, bilan repair café — titres, listes,
  citation, tableau, liens internes), avec images de partage et
  meta_description. Vitrine du duo CHANTIER-09 dans la démo. Les 2 pages de
  démo manuelles (`demo-journal`/`demo-article-1`) sont supprimées, la fixture
  fait foi.
- **Plus aucun CDN dans les templates publics** :
  - Leaflet du détail événement classic (`evenement_geoloc.html`) : unpkg →
    `pages/vendor/leaflet/` (déjà vendorisé pour le bloc CARTE_LEAFLET et
    l'explorer), avec `L.Icon.Default.imagePath` local.
  - Plotly du sankey crowds : cdn.plot.ly → `crowds/static/crowds/vendor/
    plotly-2.27.0.min.js` (3,5 Mo, chargé paresseusement uniquement quand un
    diagramme s'affiche — comportement inchangé).
