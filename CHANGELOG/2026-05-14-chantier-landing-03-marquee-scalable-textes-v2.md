# Chantier landing #03 — Marquee scalable + textes V2 + icone cashless + flush cache

**Date :** 2026-05-14
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**Quoi / What :** Quatre fixes sur la landing root `/` qui se voyaient
en prod avec 375 tenants ou apres un `flush`.

1. **Marquee "Nos lieux vivants" scalable** : la duree d'animation etait
   figee a 30s dans le CSS. Avec 6 lieux, vitesse ~41 px/sec (lisible).
   Avec 375 lieux, vitesse ~2580 px/sec (illisible, eclair). Fix :
   - `seo/views.py::landing()` calcule `marquee_lieux_duration_sec` pour
     viser ~40 px/sec constants.
   - Liste melangee aleatoirement (`random.shuffle`) a chaque chargement
     pour valoriser tous les lieux du reseau equitablement.
   - Plafonnee a 30 lieux pour ne pas alourdir le DOM (doublee par le
     `{% for copy in "ab" %}`).
   - `seo/static/seo/seo.css` consomme la duree via la CSS variable
     `--marquee-duration` (fallback 30s pour les autres pages).

2. **Textes V2 portes sur la landing** : hero title "Adhesion,
   billetterie, caisse enregistreuse et outils libres et federes"
   (etait "Lieux culturels, billetterie, outils libres et federes").
   Philosophie etoffee (encaisser au bar, boite a outils complete avec
   cashless/caisse/monnaie locale/budget contributif, "une seule carte
   pour plusieurs lieux"). Subheading features "Une solution complete"
   (au lieu de "Une boite a outils"). Source : prototype V2
   `../lespass-main/seo/templates/seo/landing.html`.

3. **Icone cashless invisible** : `bi-contactless` n'existe pas dans
   Bootstrap Icons 1.11.3. La feature card etait sans icone visible
   (width 0, `content: none`). Remplace par `bi-credit-card-2-front`
   (carte bancaire avec puce).

4. **Cache SEO ne se recharge pas apres `flush.sh` / `flush_dev.sh`** :
   la landing root affichait "0 lieux 0 events" tant que Celery beat
   n'avait pas tourne (toutes les 4h). Ajout de
   `python manage.py refresh_seo_cache` en fin de chaque script de flush.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `seo/views.py` | `landing()` : `random.shuffle`, cap 30 lieux, calcul `marquee_lieux_duration_sec` |
| `seo/templates/seo/landing.html` | Hero V2, philosophie V2, subheading V2, `bi-contactless` → `bi-credit-card-2-front`, `style="--marquee-duration: ...s"` sur la track |
| `seo/static/seo/seo.css` | `.marquee-content` lit `var(--marquee-duration, 30s)` |
| `flush.sh` | Ajout `manage.py refresh_seo_cache` apres collectstatic |
| `flush_dev.sh` | Ajout etape 6/6 `manage.py refresh_seo_cache` |

### Migration / Migration
- **Migration necessaire / Migration required :** Non
- Pas de nouvelle chaine `_()` ajoutee — les `{% translate %}` du hero
  V2 ("Adhesion", "billetterie,", "caisse enregistreuse") n'avaient pas
  d'entree dans les `.po`. **makemessages + compilemessages reportes**
  (le francais s'affiche correctement comme fallback).
