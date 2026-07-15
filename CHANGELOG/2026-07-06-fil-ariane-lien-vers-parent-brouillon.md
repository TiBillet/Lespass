# Fil d'ariane : plus de lien vers un parent brouillon / Breadcrumb: no more link to a draft parent

**Date :** 2026-07-06
**Migration :** Non / No

Backlog re-vérifié (3 points) : jsonld_page dans ff/page.html ✅ déjà réglé ;
références motif/*.svg fantômes ✅ parties avec static/reunion ; restait le
fil d'ariane d'une sous-page dont le PARENT est dépublié — lien visible ET
maillon BreadcrumbList JSON-LD pointaient vers un brouillon (→ 404, et
signal SEO incohérent). Le maillon parent est désormais conditionné à
`parent.publie` aux 3 endroits (page.html classic + ff, jsonld_page), le
fil retombe sur « Accueil › page ». Test pytest aller-retour
(brouillon → masqué, republié → maillon de retour).
