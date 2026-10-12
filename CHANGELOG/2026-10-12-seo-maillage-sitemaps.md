# Liens entre lieux et sitemaps / Links between venues and sitemaps

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- **Voisins en liens HTML** sur « Autour de nous » (skins V2 et classic) : la liste `#explorer-list` contient, avant le JavaScript, un `<a href>` par lieu voisin (`seo/templates/seo/partials/explorer_liste_serveur.html`). explorer.js la remplace ensuite par ses cartes. Le `/explorer/` racine n'est pas touché.
- **Sitemap des événements** = l'agenda du lieu : publiés, non archivés, sans les actions bénévoles, passés depuis moins de 6 mois (`BaseBillet/sitemap.py:evenements_du_sitemap`). Les événements « non fédérables » restent : ils sont visibles sur l'agenda du lieu.
- **`lastmod` retirés** là où ils étaient faux : événements (date de création), sitemap index racine (date du jour pour les 481 lieux), sitemap des pages racine. Celui des pages CMS (`updated_at`) est vrai et reste.
- **« Autour de nous »** n'est déclaré au sitemap que s'il y a vraiment des voisins : déclarés, entrants (si l'option est active) ou trouvés par tags — les mêmes sources que `FederationViewset.list`.
- **Sitemap index racine** : un lieu dont l'accueil est vide (ni événement à venir, ni image, ni description écrite, ni accueil CMS publié) n'y est plus, même avec un produit publié. Il reste sur la carte et la landing. Nouveau champ `accueil_sans_contenu` dans le résumé SEO du lieu (`seo/services.py:build_tenant_config_data`) ; tant qu'un résumé n'est pas recalculé (beat toutes les 4 h), le lieu est gardé.

/ HTML links to neighbour venues; event sitemap aligned with the agenda; wrong lastmod removed; "Around us" only declared with neighbours; empty-home venues out of the root sitemap index.

**Pourquoi / Why :** Audit SEO du 2026-10-12 (`TECH_DOC/SESSIONS/SEO/AUDIT-ACCUEIL-V2/RECAP.md`, chantier 11).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/sitemap.py` | `evenements_du_sitemap()`, pas de `lastmod`, condition de `federation-list` |
| `seo/views.py` | `sitemap_index_view` et `sitemap_root_view` sans `<lastmod>` |
| `seo/services.py` | `accueil_sans_contenu` dans `build_tenant_config_data` |
| `seo/tasks.py` (`rebuild_seo_aggregates`) | lieux à accueil vide hors de `SITEMAP_INDEX` |
| `seo/templates/seo/partials/explorer_liste_serveur.html` | nouveau : liste HTML des voisins |
| `pages/templates/pages/V2/vues/reseau.html`, `pages/templates/pages/classic/vues/reseau.html`, `seo/templates/seo/partials/explorer_widget.html` | inclusion de la liste |
| `tests/pytest/test_seo_maillage_sitemaps.py` | 13 tests (vérifiés par mutation) |
| `tests/pytest/test_sitemap_sections_vides.py` | faux manager avec `exclude`, test des lieux entrants adapté à la nouvelle règle |

---

## Comment tester (a la main) / Manual test
1. `curl -s https://la-filature.tibillet.coop/federation/ | grep -A5 reseau-liste-lieux-html` → un `<a href>` par voisin (UPV, Relief).
2. `curl -s https://la-filature.tibillet.coop/sitemap.xml | grep -c lastmod` → 0 ; plus d'événement de plus de 6 mois.
3. `curl -s https://zamm.tibillet.coop/sitemap.xml | grep federation` → rien (lieu sans voisin).
4. `curl -s https://tibillet.coop/sitemap.xml | grep -E 'lastmod|test.tibillet'` → rien, après le prochain recalcul SEO (beat 4 h ou `refresh_seo_cache`).

`docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_seo_maillage_sitemaps.py /DjangoFiles/tests/pytest/test_sitemap_sections_vides.py -q`
