# Fixes SEO (audit du 2026-07-05)

**Date :** 2026-07-06
**Migration :** Non

## Ce qui a été fait
Voir CHANGELOG (entrée « Audit SEO ») — 6 lots : JSON-LD Event valide via le
nouveau tag `jsonld_event` (+ `offers` enfin émis), og:image absolues
(événement ×2 skins + adhésions), sitemap sans les 63 fragments HTMX,
h1 partout (secours pages CMS + visually-hidden agendas + démotion markdown),
skin ff aligné (JSON-LD/breadcrumb/metas), srcset vides éradiqués.

## Tests à réaliser (mainteneur)

### Test 1 : Google Rich Results Test (LE test qui compte, après déploiement)
https://search.google.com/test/rich-results sur une page événement de prod →
le type « Événement » doit être détecté avec date, lieu, prix. Avant le fix :
JSON rejeté en bloc (invalide).

### Test 2 : partage social d'un événement
Coller l'URL d'un événement dans Discord/Signal/LinkedIn (ou
https://www.opengraph.xyz/) → l'image sociale doit s'afficher (avant : URL
relative, image absente partout).

### Test 3 : h1
- Page CMS sans bloc HERO (ex. un article de blog) → titre de la page affiché
  en haut (h1 visible, `data-testid="page-titre"`).
- Page CMS avec HERO → PAS de doublon (le HERO garde le h1).
- Écrire `# Un titre` dans un bloc markdown → rendu en h2 (démotion), jamais
  de double h1.
- /event/ : h1 présent mais invisible (visually-hidden) — inspecter le DOM.

### Test 4 : sitemap
`/sitemap.xml` : plus aucune URL `/memberships/<uuid>/` ; `/memberships/`,
les événements et les pages CMS publiées toujours là.

### Test 5 : pages CMS faire_festival
Sur chantefrein, /infos-pratiques/ : source de la page → un bloc
`application/ld+json` avec WebPage + FAQPage ; fil d'Ariane sur
/notre-demarche/ (sous-page).

## Points laissés en l'état (opportunités notées à l'audit)
- Leaflet en CDN (unpkg) sur le détail événement classic — vendoriser un jour.
- `loading="lazy"` manquant sous la ligne de flottaison de la home ff.
- `width/height` absents sur les images de blocs (CLS mineur).
- Canonical avec querystring sur les listes filtrées (self-canonical, correct
  mais perfectible).
- alt="" sur des images décoratives des pages CMS ff : légitime (décoratif),
  laissé tel quel.
- RAPPEL prod : les flags env DEBUG/TEST/DEMO/STRIPE_TEST doivent tous être
  absents/à 0 en production, sinon noindex global (mécanisme voulu).
