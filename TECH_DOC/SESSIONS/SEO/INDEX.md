# SEO Lespass — Hub permanent

Suivi du chantier SEO de Lespass sur plusieurs sessions. Ce dossier est
le point d'entree unique pour toute personne (humain ou agent) qui
travaille sur les questions de referencement, visibilite IA, sitelinks,
ou desindexation.

## Documents

- **SPEC.md** — Vision globale, principes (Google AI Optimization Guide
  du 15 mai 2026), etat actuel de l'app `seo/` et du base template
  tenant, et liste priorisee des chantiers a faire.
- **CHANTIER-NN-*.md** — Specs actionables, une par chantier. Chaque
  spec contient le contexte, le design, les fichiers a modifier, le
  plan de tests, et le journal d'avancement.

## Chantiers

| # | Titre | Statut | Priorite | Spec |
|---|-------|--------|----------|------|
| 01 | Desindexation des instances DEV / DEMO / TEST | Implemente — a tester / deployer | Urgent | [CHANTIER-01-noindex-dev.md](./CHANTIER-01-noindex-dev.md) |
| 02 | Enrichir le base template tenant (meta, OG, JSON-LD) | A faire | Eleve | _a creer_ |
| 03 | Pages indexables ROOT pour sitelinks Google | A faire | Moyen | _a creer_ |
| 04 | Breadcrumbs JSON-LD + `sameAs` Organization | A faire | Bas | _a creer_ |
| 05 | Carte explorer ROOT : 1 marker par PostalAddress | Implemente (backend + frontend + cache), E2E Task 10 non ecrit | Moyen | [CHANTIER-05-explorer-markers-per-pa.md](./CHANTIER-05-explorer-markers-per-pa.md) + [PLAN-05-explorer-markers-per-pa.md](./PLAN-05-explorer-markers-per-pa.md) |
| 06 | Carte explorer ROOT : pills exclusives, tag chips, URL partageable | Implemente — a tester / commiter (12 tasks faites, E2E a valider serveur up) | Moyen | [CHANTIER-06-explorer-ux-pills-tags.md](./CHANTIER-06-explorer-ux-pills-tags.md) + [PLAN-06-explorer-ux-pills-tags.md](./PLAN-06-explorer-ux-pills-tags.md) |

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
