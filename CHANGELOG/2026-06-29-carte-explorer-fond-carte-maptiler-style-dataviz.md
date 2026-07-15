# Carte explorer : fond de carte MapTiler (style dataviz) avec repli OSM France / MapTiler basemap with OSM France fallback

**Date :** 2026-06-29
**Migration :** Non / No (front + variable d'env `MAPTILER_KEY`)

**Quoi / What :** Le fond de carte utilise **MapTiler** (style `dataviz-v4`, épuré)
quand une clé est configurée, sinon **repli** sur les tuiles **Humanitarian (HOT)
d'OpenStreetMap France**. La clé MapTiler vient de `MAPTILER_KEY` (`.env`), jamais
en dur dans le code.

**Pourquoi / Why :** CARTO Voyager affichait les régions françaises en anglais.
MapTiler offre un style épuré (idéal pour faire ressortir les markers) et des
garanties de prod ; OSM France reste le repli gratuit/sans clé (et le défaut en dev
si `MAPTILER_KEY` est vide). Branchement : `settings.MAPTILER_KEY` →
contexte des vues → `data-maptiler-key` sur `#explorer-root` → `explorer.js`.

**Limite langue / Language note :** sur les tuiles **raster** MapTiler, `?language=fr`
n'a **pas** d'effet (labels figés au rendu). Les villes françaises s'affichent en
français, mais les pays/villes étrangers restent en anglais (« Geneva »,
« Switzerland »). Pour un français complet : créer un style FR dans le dashboard
MapTiler (Customize → langue), ou passer au SDK vectoriel (MapLibre, `language: 'fr'`).

**Sécurité clé :** la clé MapTiler est exposée côté client (URL des tuiles) →
**à restreindre par domaine** dans le dashboard MapTiler (Allowed origins).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/settings.py` | `MAPTILER_KEY = os.environ.get('MAPTILER_KEY', '')` |
| `seo/views.py` + `BaseBillet/views.py` | passent `maptiler_key` au contexte (explorer ROOT + federation tenant) |
| `seo/templates/seo/partials/explorer_widget.html` | `data-maptiler-key` sur `#explorer-root` |
| `seo/static/seo/explorer.js` | `tileLayer` : MapTiler `dataviz-v4` si clé, sinon repli HOT / OSM France |

### Migration
- **Migration nécessaire / Migration required :** Non / No. Renseigner `MAPTILER_KEY`
  dans `.env` (sinon repli HOT automatique) + redémarrer le conteneur pour charger l'env.
