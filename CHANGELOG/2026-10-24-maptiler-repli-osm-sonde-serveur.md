# Repli OSM quand MapTiler refuse les tuiles : sonde serveur / OSM fallback when MapTiler refuses tiles: server probe

**Date :** 2026-10-24
**Migration :** Non

## Resume / Summary
**Quoi / What :** le serveur sonde MapTiler (une tuile) et retient le resultat dans le cache **global** (schema public). MapTiler refuse (403, 429, tout statut non OK) → toutes les cartes de tous les lieux recoivent une cle vide pendant **24 h** et prennent OSM France HOT. MapTiler OK → la cle est exposee et l'etat est resonde **toutes les heures**. Reseau en panne pendant la sonde → on garde MapTiler, rien n'est retenu.
/ The server probes MapTiler (one tile) and keeps the result in the global cache. Refused → every map gets an empty key for 24 h and uses OSM France HOT. OK → key exposed, re-probed every hour.

**Pourquoi / Why :** quota epuise ou cle refusee, MapTiler repond 403 **avec une image PNG valide** (« Invalid key »). Le navigateur l'affiche comme une tuile normale : `tileerror` ne part jamais, le repli JS de `tb_fond_de_carte.js` ne se declenchait pas. Les cartes affichaient les vignettes d'erreur MapTiler.
/ When the quota is used up, MapTiler answers 403 with a valid PNG image. The browser shows it as a normal tile, so the JS fallback never fired.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/maptiler.py` | `sonder_maptiler()` + `cle_maptiler_a_exposer()` (cache global 1 h OK / 24 h KO) ; le context processor l'utilise |
| `BaseBillet/templatetags/tibitags.py` | Tag `{% maptiler_key %}` → `cle_maptiler_a_exposer()` |
| `BaseBillet/views.py` | `get_context()` et la vue reseau → `cle_maptiler_a_exposer()` |
| `seo/views.py` | Explorer du ROOT → `cle_maptiler_a_exposer()` |
| `tests/pytest/test_maptiler_repli_quota.py` | Nouveau : 403/429, durees de cache, panne reseau, une seule sonde, etat global entre tenants, sans cle |
| `tests/pytest/test_widget_carte_adresse_tiles.py` | Le test « avec cle » simule un MapTiler OK (sinon il sonderait le vrai) |

### A verifier en prod / To check in prod
La sonde envoie `Referer`/`Origin` = `https://<DOMAIN>/` (domaine racine). Si ce domaine n'est **pas** dans les « Allowed origins » de la cle MapTiler, la sonde verra un 403 et coupera MapTiler a tort. Verification :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "from django.conf import settings; from TiBillet.maptiler import sonder_maptiler; print(sonder_maptiler(settings.MAPTILER_KEY))"
```
Attendu : `ok` (si le quota n'est pas epuise).

---

## Comment tester (a la main) / Manual test

### Test 1 — MapTiler refuse (cas du dev : la cle du `.env` est refusee)
1. Ouvrir `https://lespass.tibillet.localhost/federation/` (ou une fiche evenement avec adresse).
2. Inspecter le conteneur de la carte : `data-maptiler-key=""`.
3. La carte affiche le fond OSM France HOT, aucune vignette « Invalid key ».
4. Dans les logs du serveur : `MapTiler refuse les tuiles (HTTP 403) : repli OSM France HOT pendant 86400 s`, une seule fois (pas a chaque page).

### Test 2 — MapTiler OK (cle valide)
1. Mettre une cle valide dans `MAPTILER_KEY`, redemarrer le serveur.
2. Vider l'etat retenu :
   ```bash
   docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
   from django.core.cache import cache
   from django_tenants.utils import schema_context
   from TiBillet.maptiler import CLE_CACHE_ETAT_MAPTILER
   with schema_context('public'):
       cache.delete(CLE_CACHE_ETAT_MAPTILER)
   "
   ```
3. Recharger la page : `data-maptiler-key` porte la cle, fond MapTiler « dataviz ».

### Test 3 — etat global
1. Apres le Test 1, ouvrir la carte d'un **autre** lieu et l'explorer du ROOT : fond OSM directement, aucune nouvelle ligne `MapTiler refuse` dans les logs.

### Verifs auto
- `tests/pytest/test_maptiler_repli_quota.py` (8 tests) ; mutations verifiees : sans `schema_context("public")` → le test « global » echoue ; cle exposee meme en KO → les tests 403/429 echouent.
