# SEO — Desindexation des instances DEV / DEMO / TEST

**Date :** 2026-05-17
**Migration :** Non

Procedure de test manuel apres deploiement du CHANTIER 01.

Voir `TECH_DOC/SESSIONS/SEO/CHANTIER-01-noindex-dev.md` pour la spec
complete et `TiBillet/seo_indexing.py` pour le helper.

## Ce qui a ete fait

Une reponse HTTP est marquee `noindex, nofollow` (via `robots.txt`
ET `<meta name="robots">`) quand AU MOINS UN flag d'environnement
est a `1` :

- `DEBUG=1`
- `TEST=1`
- `DEMO=1`
- `STRIPE_TEST=1`

(Une regle supplementaire sur le host a ete envisagee puis ecartee :
elle etait redondante avec les 4 flags en pratique.)

## Modifications

| Fichier | Changement |
|---|---|
| `TiBillet/seo_indexing.py` | NOUVEAU helper + context processor |
| `TiBillet/settings.py` | +1 ligne context_processors |
| `seo/views_common.py::robots_txt` | Disallow:/ si noindex |
| `BaseBillet/views_robots.py::robots_txt` | Idem cote tenant |
| `seo/templates/seo/base.html` | block meta_robots conditionnel |
| `BaseBillet/templates/{reunion,faire_festival,htmx}/base.html` | block meta_robots conditionnel |

## Tests automatises (deja verts)

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_indexing.py --api-key dummy -v
# 5 passed
```

## Tests manuels a realiser

### Test 1 : Instance dev locale (au moins un flag a 1)

Le `.env` local a `DEBUG=1, TEST=1, DEMO=1, STRIPE_TEST=1`.

1. Lancer le serveur : `docker exec lespass_django poetry run python manage.py runserver_plus 0.0.0.0:8002`
2. `curl http://tibillet.localhost:8002/robots.txt`
   - **Attendu** : `User-agent: *\nDisallow: /`
3. Ouvrir `http://tibillet.localhost:8002/` dans Chrome
   - Faire "View page source"
   - **Attendu** : `<meta name="robots" content="noindex, nofollow">` dans le `<head>`
4. Ouvrir une page tenant : `http://lespass.tibillet.localhost:8002/`
   - **Attendu** : meme `<meta name="robots" content="noindex, nofollow">`
   - **Verification** `curl http://lespass.tibillet.localhost:8002/robots.txt` -> `Disallow: /`

### Test 2 : Simulation prod (tous les flags a 0)

Editer temporairement `.env` pour forcer :
```env
TEST=0
DEBUG=0
DEMO=0
STRIPE_TEST=0
```

Redemarrer le container Django.

1. `http://tibillet.localhost:8002/` -> **indexable**
   - `<meta name="robots" content="index, follow">`
   - `robots.txt` -> `User-agent: *\nAllow: /\n\nSitemap: ...`
2. `http://lespass.tibillet.localhost:8002/` -> **indexable**
3. **Restauration obligatoire** : remettre `DEBUG=1, TEST=1, DEMO=1,
   STRIPE_TEST=1` apres le test.

### Test 3 : Chaque flag declenche le noindex independamment

Repeter en isolant chaque flag (les 3 autres a 0) :

| Flag actif | Attendu |
|---|---|
| Seul `DEBUG=1` | noindex |
| Seul `TEST=1` | noindex |
| Seul `DEMO=1` | noindex |
| Seul `STRIPE_TEST=1` | noindex |

Apres chaque test, restaurer la config initiale.

## Verification sur les instances deja indexees

Apres deploiement en prod sur filaos.re et devtib.fr :

1. **Verifier les headers et le HTML** :
   ```bash
   curl -I https://filaos.re/
   curl -s https://filaos.re/ | grep -i "name=\"robots\""
   curl -s https://filaos.re/robots.txt
   ```
   Tous doivent indiquer noindex.

2. **Demander la suppression d'URLs** :
   - Google Search Console > Suppression d'URLs > Nouvelle demande
   - Bing Webmaster > Configurer mon site > Bloquer des URL
   - Soumettre les URLs racines : `https://filaos.re/`, `https://devtib.fr/`
   - Sans cette demande, Google peut mettre plusieurs semaines a
     desindexer naturellement.

3. **Verifier dans 2 semaines** : Search Console > Couverture > URL
   exclues. Les pages doivent etre passees en "Exclue par balise
   noindex".

## Compatibilite

- Aucune migration de base de donnees necessaire.
- Aucun changement dans le comportement des pages prod (host =
  `tibillet.coop` + flags a 0 -> `index, follow` comme avant).
- Si un projet downstream definit son propre block `meta_robots` dans
  un template qui herite d'un base modifie, le child override reste
  prioritaire (comportement Django standard).

## Hors scope (chantier 02 a venir)

- Enrichir `htmx/base.html` avec meta description, OG, Twitter Card,
  canonical, JSON-LD `Organization` / `Event` / `Place`.
- Generer des sitelinks Google sur la landing ROOT (pages dediees
  `/fonctionnalites/`, `/cooperative/`, `/demonstration/`).
