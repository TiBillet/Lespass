# M-To-V2 — Migration progressive de Lespass V1 vers V2

> Branche de travail : `main-to-v2` (partie de `main` = V1)
> Référence d'inspiration : dépôt `lespass-main` sur branche `V2`
> Démarrage : 2026-05-11

---

## 1. Contexte

Deux dépôts coexistent localement :

| Dépôt | Branche actuelle | Rôle |
|---|---|---|
| `/home/jonas/TiBillet/dev/lespass-main` | `V2` | **Référence prototype.** Contient toutes les expérimentations (fedow_core, laboutik, inventaire, admin découpée, dashboard groupware…). N'est plus considéré comme une cible de merge. |
| `/home/jonas/TiBillet/dev/Lespass` | `main-to-v2` | **Cible de travail.** Branche neuve partie de `main` (V1). On y migre, feature par feature, ce qui mérite d'être conservé de V2. |

La branche `V2` du dépôt prototype ne sera **jamais mergée** sur `main`. On
pioche dedans pour s'inspirer, on porte ce qui marche, on adapte au passage.

## 2. Pourquoi cette stratégie

- **V2 a accumulé trop de chantiers couplés** (fedow_core SHARED_APPS,
  laboutik TENANT_APP, inventaire, refactorings admin profonds, mocks
  remplacés, signaux ajoutés…). Un merge en bloc serait ingérable.
- **V1 est en prod** (lespass-main avait livré jusqu'à v1.7.18). Le risque
  de régression est réel.
- **Petit pas = revue facile**. Chaque chantier est un PR (ou un commit
  isolé) lisible, testable, réversible.
- **On garde la liberté de couper court** : si une feature V2 s'avère
  inutile en V1, on la laisse en V2. Pas de dette d'import obligatoire.

## 3. Méthode

### 3.1 Principes non-négociables

1. **Non destructif** — chaque port préserve le comportement existant tant
   que la nouvelle feature n'est pas activée (champ `BooleanField` avec
   `default=True` pour ne rien casser sur les tenants existants).
2. **Surface API stable** — les imports externes (`urls_tenants.py`,
   `discovery/admin.py`, callbacks dans `settings.py`) doivent continuer
   à fonctionner après chaque étape. On utilise des re-exports si besoin.
3. **Un chantier = un focus** — on ne mélange pas refactoring d'admin
   et ajout de modèles. Soit l'un, soit l'autre.
4. **Tests d'abord** — pour chaque feature portée, vérifier qu'un test
   existant continue à passer ou écrire un test minimal de
   non-régression.
5. **Documentation au fil de l'eau** — chaque chantier produit une
   sous-section dans ce dossier `M-To-V2/` (1 fichier `.md` par
   chantier) + entrée CHANGELOG.

### 3.2 Cadence — une étape de migration type

```
1. Identifier la feature à porter (depuis ce backlog ou demande utilisateur)
2. Lire le code V2 correspondant dans lespass-main
3. Repérer les dépendances (modèles, signaux, settings, templates)
4. Proposer un plan (le maintainer valide)
5. Implémenter dans Lespass (branche main-to-v2)
6. Vérifier : manage.py check + tests ciblés
7. Documenter dans TECH DOC/SESSIONS/M-To-V2/<nom-chantier>.md
8. Ajouter une entrée CHANGELOG
9. Commit (par le maintainer)
```

### 3.3 Règles de portage

- **Préférer copier-coller-adapter** plutôt que `git cherry-pick` : la
  divergence entre V2 et V1 est trop grande pour des merges automatiques.
- **Renommer si ambigu** — par exemple, V2 a deux `Asset` (un dans
  `fedow_core`, un dans `fedow_public`). Si on porte l'admin V2 dans V1,
  préciser quel modèle on cible.
- **Pas de port en cascade** — si la feature V2 X dépend de la feature
  V2 Y qui dépend de Z, on commence par Z, on valide, puis Y, puis X. Pas
  de "tout d'un coup".
- **Documenter ce qu'on NE porte PAS** — important pour expliquer plus
  tard pourquoi telle feature V2 n'existe pas en V1.

## 4. État courant

### 4.1 Déjà fait (issu de la session précédente)

- **Étape 1.1 — Extraction `StaffAdminSite`** :
  - Créé `Administration/admin/__init__.py` (marqueur de package)
  - Créé `Administration/admin/site.py` (65 lignes) : `StaffAdminSite`,
    `staff_admin_site`, `sanitize_textfields`
  - Modifié `admin_tenant.py` (4984 → 4968 lignes) : remplace la
    définition par un re-export
  - Surface externe préservée : `from Administration.admin_tenant import
    staff_admin_site` fonctionne toujours
  - Validation `ast.parse()` OK ; `manage.py check` à valider côté
    container (port 8002 occupé par V2)

### 4.2 Chantier en cours

**Découpage de l'admin V1 (`admin_tenant.py` monobloc)** — voir
`01-decoupage-admin.md` (à créer).

## 5. Backlog ordonné

Priorité fonctionnelle (du plus simple/utile au plus risqué).

### Chantier 1 — Découpage admin + dashboard 3 modules ⏳ EN COURS

**But.** Rendre `admin_tenant.py` maintenable + permettre la
désactivation tenant-par-tenant des grosses sections (billetterie /
adhésion / budget contributif).

Sous-étapes :
- [x] 1.1 Squelette `Administration/admin/` + `site.py` + `__init__.py`
- [ ] 1.2 Pilote `tags.py` (Carrousel + Tag) — petit, indépendant
- [ ] 1.3 Déplacer `configuration.py` (Configuration, ExternalApiKey,
      ScanApp, Webhook, OptionGenerale)
- [ ] 1.4 Déplacer `users.py` (HumanUser)
- [ ] 1.5 Déplacer `prices.py` (Price, PromotionalCode)
- [ ] 1.6 Déplacer `products.py` (Product, Tva, PriceInline,
      ProductFormFieldInline) — gros morceau
- [ ] 1.7 Déplacer `events.py` (Event + EventChildrenInline)
- [ ] 1.8 Déplacer `reservations.py` (Reservation, Ticket)
- [ ] 1.9 Déplacer `membership.py` (Membership, LigneArticleInline)
- [ ] 1.10 Déplacer `sales.py` (Paiement_stripe, LigneArticle,
       PostalAddress)
- [ ] 1.11 Déplacer `crowds.py` (Initiative + 4 inlines, CrowdConfig)
- [ ] 1.12 Déplacer `fedow.py` (AssetFedowPublic)
- [ ] 1.13 Déplacer `settings_apps.py` (Client, FederatedPlace, Brevo,
       Formbricks, Waiting, Ghost)
- [ ] 1.14 Vider `admin_tenant.py` → orchestrateur ~20 lignes
- [ ] 1.15 Ajouter `module_billetterie` / `module_adhesion` /
       `module_crowdfunding` sur `Configuration` (migration AddField,
       défauts `True`)
- [ ] 1.16 Créer `dashboard.py` (callbacks dashboard + sidebar
       conditionnelle + modules)
- [ ] 1.17 Templates `dashboard.html` + `dashboard_module_modal.html`
- [ ] 1.18 Toggle HTMX + CSRF + admin_view + whitelist field_name

### Chantier 2 — Port app `seo/` allegee (landing ROOT lieux + events) ✅ CODE PORTE

**But.** Servir une vraie landing page sur le schema public (ROOT) avec agregation
multi-tenant lieux + evenements. Remplace la redirection MetaBillet vers tibillet.org.

Voir `02-app-seo.md` pour le detail. Statut :
- Code, migrations, settings, celery beat : ✅ FAIT
- `manage.py check` : OK
- Refresh execute (DB de dev vide donc 0 resultats)
- Test visuel `https://tibillet.localhost/` : bloque par django-tenants tant qu'aucun
  Domain n'existe en DB (besoin de bootstrap dev via `install` ou demo command)

### Chantier 3 — Améliorations admin V2 (sans modèles nouveaux)

À détailler après les chantiers 1 et 2. Inclut potentiellement :
- Refonte `PriceInline` unique → inlines spécialisés par proxy product
  (mais ça suppose des proxy models, donc à voir)
- Améliorations UX Unfold (sections, badges, filtres avancés)
- Templates admin (`change_form_before`, sections custom)

### Chantier 3 — Imports API v2 ou autres améliorations non-couplées

À identifier au fil de l'eau (api_v2 a déjà été poussé sur V1 d'après le
CLAUDE.md V1).

### Hors backlog M-To-V2 (resteront en V2 seulement)

- **fedow_core** (SHARED_APPS) — moteur fédération V2, remplace
  HTTP/RSA par DB direct. Trop couplé, on garde `fedow_connect` en V1.
- **laboutik** (TENANT_APP) — POS complet, dépend de fedow_core. Pas de
  port prévu en V1.
- **inventaire** (TENANT_APP) — dépend de laboutik.
- Dashboard groupware avec module_caisse / module_monnaie_locale —
  spécifique aux 2 modules ci-dessus.
- Refonte profonde des signaux Stripe / cascade NFC / HMAC LNE.
- Sessions LaBoutik 12-22 (clôture, HMAC, FEC, mode école…).

Si tu veux qu'une de ces features arrive en V1 plus tard, on rouvrira
le débat — mais à priori non.

## 6. Format des docs de chantier

Chaque chantier produit un fichier `NN-nom-chantier.md` dans ce dossier.
Structure recommandée :

```
# Chantier NN — Titre

## Objectif

Une ou deux phrases sur le pourquoi.

## Source d'inspiration

Chemins exacts dans lespass-main (V2) qui inspirent le portage.

## Plan

Liste ordonnée des sous-étapes, avec cases à cocher.

## Décisions / Adaptations

Ce qui change entre V2 et le portage V1 (noms renommés, fonctionnalités
réduites, valeurs par défaut différentes…).

## Vérifications

Commandes à passer après chaque sous-étape (manage.py check, tests
ciblés, navigation manuelle).

## CHANGELOG

Une ligne par sous-étape une fois terminée.
```

## 7. Garde-fous

- **Ne jamais committer ce que je n'ai pas relu** — relire les diffs
  avant chaque commit (le maintainer s'en occupe, pas Claude Code).
- **Préserver le port 8002 côté V2** — pour le dev V1, lancer sur un
  autre port ou stopper le V2 d'abord.
- **Ne pas écraser les travaux V2 par mégarde** — toujours travailler
  dans `/home/jonas/TiBillet/dev/Lespass`, jamais dans `lespass-main`.
- **Tests** — la branche `main-to-v2` repart de V1, donc la suite de
  tests V1 (tests pytest existants) doit rester verte à chaque étape.
- **Pas d'opérations git par Claude Code** — sauf demande explicite.
