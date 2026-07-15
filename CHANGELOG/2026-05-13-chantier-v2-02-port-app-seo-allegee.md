# Chantier M-To-V2 #02 — Port app `seo/` allegee (landing ROOT lieux + events) / Port lightweight `seo/` app

**Date :** 2026-05-13
**Migration :** Oui (`seo/0001_initial.py` sur le schema public)
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** Portage de l'app `seo` de V2 (lespass-main) vers V1 en version allegee.
On agrege uniquement les **lieux + evenements** du reseau (pas d'adhesions, pas
d'initiatives crowdfunding, pas de monnaies fedow_core). La landing ROOT remplace
l'ancienne redirection MetaBillet vers tibillet.org. Cache 2 niveaux (Memcached
L1 + DB L2) rafraichi toutes les 4h par Celery Beat. 7 routes : `/`, `/lieux/`,
`/evenements/`, `/recherche/`, `/explorer/`, `/robots.txt`, `/sitemap.xml`.

**EN :** Port of the V2 `seo` app to V1 in a lightweight version. Aggregates only
**venues + events** (no memberships, no crowdfunding initiatives, no fedow_core
currencies). The ROOT landing replaces the previous MetaBillet redirect to
tibillet.org. 2-tier cache (Memcached L1 + DB L2) refreshed every 4h by Celery
Beat. 7 routes: `/`, `/lieux/`, `/evenements/`, `/recherche/`, `/explorer/`,
`/robots.txt`, `/sitemap.xml`.

**Fichiers crees :** voir `TECH DOC/SESSIONS/M-To-V2/02-app-seo.md`
**Fichiers modifies :** `TiBillet/settings.py`, `TiBillet/urls_public.py`, `TiBillet/celery.py`

---
