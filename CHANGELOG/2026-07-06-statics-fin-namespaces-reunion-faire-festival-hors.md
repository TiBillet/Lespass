# Statics : fin des namespaces reunion/ et faire_festival hors de leur app / Statics: reunion/ namespace removed, faire_festival moved to its app

**Date :** 2026-07-06
**Migration :** Non / No

Les templates avaient migré mais pas les statics. Nettoyage vérifié par
références :
- **Déplacés vers `commun/js/`** (5 réfs template mises à jour) :
  form-spinner.mjs, booking-calculator.mjs, qrcode.min.js,
  qr-scanner.min.js + worker (+ source maps, déplacés ensemble : le worker
  est importé en chemin relatif).
- **`static/faire_festival/` → app pages** (`pages/static/faire_festival/`),
  namespace d'URL inchangé → zéro référence à modifier (templates ff et
  seeders continuent de pointer `faire_festival/...`).
- **Supprimés (zéro référence)** : reunion/leaflet/ (remplacé par
  pages/vendor/leaflet), reunion/js/htmx.min.1.9.12.js (tout le monde charge
  mvt_htmx/js/), reunion/media/*.jpg (3 photos orphelines). Le dossier
  `BaseBillet/static/reunion/` n'existe plus.
- **Vérifié** : findstatic sur chaque fichier migré, statuts HTTP 200 sur
  les URLs servies, page événement (réservation) chargeant commun/js/*,
  home ff chargeant ses statics — et suite pytest complète : 368 passed.
