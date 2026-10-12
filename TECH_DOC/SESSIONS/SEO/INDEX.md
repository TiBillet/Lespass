# SEO Lespass — Hub permanent

Suivi du chantier SEO de Lespass sur plusieurs sessions. Ce dossier est
le point d'entree unique pour toute personne (humain ou agent) qui
travaille sur les questions de referencement, visibilite IA, sitelinks,
ou desindexation.

## Documents

- **SPEC.md** — Vision globale, principes (Google AI Optimization Guide
  du 15 mai 2026), etat actuel de l'app `seo/` et du base template
  tenant, et liste priorisee des chantiers a faire.
- **AUDIT-MOTEUR-PAGES.md** — Audit du moteur de pages (skins classic et
  faire_festival, 2026-07-20) : constats, corrections appliquées, reste à faire.
- **AUDIT-ACCUEIL-V2/** — Audit de l'accueil par défaut du skin V2 en prod
  (2026-10-12) : synthèse dans `RECAP.md`, rapports technique / contenu /
  plateforme. Origine des chantiers 09 à 12.
- **CHANTIER-NN-*.md** — Specs actionables, une par chantier. Chaque
  spec contient le contexte, le design, les fichiers a modifier, le
  plan de tests, et le journal d'avancement.

## Chantiers

| # | Titre | Statut | Priorite | Spec |
|---|-------|--------|----------|------|
| 01 | Desindexation des instances DEV / DEMO / TEST | Implemente — a tester / deployer | Urgent | [CHANTIER-01-noindex-dev.md](./CHANTIER-01-noindex-dev.md) |
| 02 | Enrichir le base template tenant (meta, OG, JSON-LD) | En grande partie fait par les shells des skins (meta, OG, Twitter, canonical, robots, JSON-LD Event en Python). Reste le JSON-LD Organization ecrit a la main -> chantier 10 | Eleve | _absorbe par 09/10_ |
| 03 | Pages indexables ROOT pour sitelinks Google | A faire | Moyen | _a creer_ |
| 04 | Breadcrumbs JSON-LD + `sameAs` Organization | A faire (le `sameAs` des lieux passe dans le chantier 10) | Bas | _a creer_ |
| 05 | Carte explorer ROOT : 1 marker par PostalAddress | Implemente (backend + frontend + cache), E2E Task 10 non ecrit | Moyen | [CHANTIER-05-explorer-markers-per-pa.md](./CHANTIER-05-explorer-markers-per-pa.md) + [PLAN-05-explorer-markers-per-pa.md](./PLAN-05-explorer-markers-per-pa.md) |
| 06 | Carte explorer ROOT : pills exclusives, tag chips, URL partageable | Implemente — a tester / commiter (12 tasks faites, E2E a valider serveur up) | Moyen | [CHANTIER-06-explorer-ux-pills-tags.md](./CHANTIER-06-explorer-ux-pills-tags.md) + [PLAN-06-explorer-ux-pills-tags.md](./PLAN-06-explorer-ux-pills-tags.md) |
| 07 | Cache SEO en fragments par tenant + agregats par recombinaison | Implemente | Eleve | [CHANTIER-07-cache-fragments.md](./CHANTIER-07-cache-fragments.md) + [PLAN-07-cache-fragments.md](./PLAN-07-cache-fragments.md) |
| 08 | Carte reseau : rebuild d'agregats en debounce « trailing » (fix events/adresses invisibles) | Implemente — pytest verts, a tester (worker+beat) / deployer | Urgent | [CHANTIER-08-rebuild-trailing-debounce.md](./CHANTIER-08-rebuild-trailing-debounce.md) |
| 09 | Canonical sans parametres, `noindex` embed/apercu, fiches evenement federees canoniques vers l'original | Implemente — tests verts, a deployer / verifier en prod | Urgent | [CHANTIER-09-canonical-doublons.md](./CHANTIER-09-canonical-doublons.md) |
| 10 | Accueil V2 : title « lieu — ville », bug meta « None », `noindex` des accueils vides, JSON-LD Organization en Python, prechargement du hero | Implemente — 12 tests verts, a deployer (CHANGELOG/2026-10-12-seo-accueil-et-gzip.md) | Eleve | [AUDIT-ACCUEIL-V2/RECAP.md](./AUDIT-ACCUEIL-V2/RECAP.md) |
| 11 | Maillage et sitemaps : voisins en HTML, sitemap des evenements filtre (archives, actions, passes > 6 mois), `lastmod` retires, « Autour de nous » seulement avec des voisins, lieux a accueil vide hors du sitemap racine | Implemente — 13 tests verts, a deployer (CHANGELOG/2026-10-12-seo-maillage-sitemaps.md) | Moyen | [AUDIT-ACCUEIL-V2/RECAP.md](./AUDIT-ACCUEIL-V2/RECAP.md) |
| 12 | Compression gzip et cache HTTP dans nginx (infra, aucun CDN devant : verifie 2026-10-12) | gzip ecrit dans `nginx_prod/lespass_prod.conf` (teste en local : V2.css 140 -> 41 Ko), a deployer ; cache de `/media` reste a faire | Urgent | [AUDIT-ACCUEIL-V2/RECAP.md](./AUDIT-ACCUEIL-V2/RECAP.md) |

## Regles de fond (issues de Google AI Optimization Guide, 15 mai 2026)

Pour eviter de retomber dans les pieges :

- **Pas de `llms.txt`**. Ni Google, ni OpenAI, ni Anthropic ne le
  recuperent. Ne pas en creer, supprimer ceux qui trainent.
- **Pas de schema markup "special IA"**. Ca n'existe pas. On garde le
  JSON-LD classique (Organization, Event, Place, ItemList,
  BreadcrumbList) pour les rich results, sans surcharge IA.
- **Pas de chunking pour LLMs**, pas de reecriture pour IA, pas de
  generation de pages quasi-identiques par variation de keyword
  (scaled content abuse = penalite explicite depuis le Core Update
  mars 2024).
- **Oui au contenu non-commodity** : du vecu, des donnees originales,
  une perspective qu'on est seul a avoir. C'est ce que Google et les
  AI Overviews favorisent.

Pour plus de detail, voir `SPEC.md` section "Principes".

## Decision de reference

Atom Atomic `491b2fe3-049c-4b2d-86bf-ae2fc41b6b31` —
"Decision : pas de llms.txt sur les projets Jonas — position Google 2026"
(cree le 2026-05-17).
