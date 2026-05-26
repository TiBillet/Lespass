# Changelog / Journal des modifications

## Sentry — tracing désactivé (budget spans saturé) / Sentry tracing disabled

**Date :** 2026-05-25
**Migration :** Non · **Déploiement requis :** Oui (redémarrage prod)

**Quoi / What :** `sentry_sdk.init` (settings) : `traces_sample_rate` et
`profiles_sample_rate` passés de **0.3 → 0.0**. Le tracing/performance monitoring
(spans) est coupé ; les **events d'erreur (issues) restent captés normalement**.
/ Tracing/profiling sampling 0.3 → 0.0. Spans off, error events unaffected.

**Pourquoi / Why :** le volume festival (4000 users + tâches Celery) avec 30 % de
transactions tracées a **saturé le budget de spans** Sentry (100 % consommé → spans
droppés). On coupe le tracing pour ne plus exploser le budget. Remonter prudemment
(0.01–0.05) plus tard si besoin de perf.

**Note :** ne restaure pas l'ingestion de la **période en cours** (déjà consommée) —
ça nécessite un ajustement budget côté Sentry ou le reset de période. Prend effet
**au déploiement** (l'init ne tourne qu'en prod : `not DEBUG and SENTRY_DNS`).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/settings.py` | `sentry_sdk.init` : `traces_sample_rate=0.0`, `profiles_sample_rate=0.0` |

### Migration
- **Migration nécessaire / Migration required :** Non

## API v1 — validation réservation loggée en `warning` (anti-bruit Sentry) / Reservation validation logged at warning

**Date :** 2026-05-25
**Migration :** Non

**Quoi / What :** `ApiReservationViewset.create` (v1) loggeait les **échecs de validation
(400 client)** en `logger.error` → events Sentry. Passé en **`logger.warning`** : la
`LoggingIntegration` Sentry (défaut `event_level=ERROR`, aucune surcharge dans
`settings.py`) ne crée **plus d'event** pour ces 400 (juste un breadcrumb). Le 400 + le
corps d'erreur informent déjà l'appelant.
/ v1 reservation `create` logged client 400 validation failures at `error` (Sentry events).
Now `warning` → no Sentry event (default `event_level=ERROR`).

**Pourquoi / Why :** une validation 400 côté client (payload incomplet) n'est pas une
erreur applicative ; elle ne doit pas solliciter Sentry.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `ApiBillet/views.py` | `ApiReservationViewset.create` : `logger.error` → `logger.warning` sur `validator.errors` |

### Migration
- **Migration nécessaire / Migration required :** Non

## API v1 (ApiBillet) — en-têtes de dépréciation vers /api/v2/ / API v1 deprecation headers

**Date :** 2026-05-25
**Migration :** Non

**Quoi / What :**
- Les réponses des endpoints **consommateur** de l'API v1 (`ApiBillet`) portent
  désormais des en-têtes HTTP **non bloquants** orientant vers v2 :
  `Deprecation: true`, `Link: </api/v2/>; rel="successor-version"`,
  `Warning: 299 - "TiBillet API v1 is deprecated, migrate to /api/v2/"`.
- Mécanisme : mixin **`DeprecatedV1Mixin`** (override `finalize_response`) placé en
  **première base** des viewsets/APIViews consommateur. Marche pour `ViewSet` **et**
  `APIView` (les deux héritent `finalize_response` de DRF — vérifié).
- 12 classes concernées : `ApiReservationViewset`, `EventsViewSet`, `EventsSlugViewSet`,
  `ProductViewSet`, `TarifBilletViewSet`, `TicketViewset`, `Wallet`, `OptionTicket`,
  `HereViewSet`, `Gauge`, `TicketPdf`, `CancelSubscription`.
- **Exclus** (plomberie, pas de successeur v2) : `Webhook_stripe`, `Onboard_laboutik`,
  `Onboard_stripe_return`, `Get_user_pub_pem`.
- **Pas de `Sunset`** (aucune date de retrait décidée — à ajouter dans
  `API_V1_DEPRECATION_HEADERS` le jour venu).

**Pourquoi / Why :** orienter les intégrateurs (ex. client « codex-api » repéré sur le
tenant `raffinerie`) vers l'API v2 sémantique, sans casser les clients v1 existants.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `ApiBillet/views.py` | + `API_V1_DEPRECATION_HEADERS` + `DeprecatedV1Mixin` ; mixin ajouté en 1ʳᵉ base de 12 classes consommateur |

### Migration
- **Migration nécessaire / Migration required :** Non

## API v2 — Fix `retrieve` Product (lookup_field manquant) / Fix Product retrieve (missing lookup_field)

**Date :** 2026-05-25
**Migration :** Non

**Quoi / What :**
- `GET /api/v2/products/{uuid}/` levait `TypeError: retrieve() got an unexpected
  keyword argument 'pk'` (**HTTP 500**), même avec un uuid valide. `ProductViewSet`
  n'avait pas `lookup_field = "uuid"` : le routeur DRF passait `pk`, alors que
  `retrieve(self, request, uuid=None)` attend `uuid`. L'endpoint détail Product
  n'avait donc jamais fonctionné.
- Ajout de `lookup_field = "uuid"` sur `ProductViewSet` (cohérent avec
  Event/Reservation/Membership/Initiative ; aligne le code sur l'OpenAPI qui
  documente déjà `/products/{uuid}/`).

**Pourquoi / Why :** Issue Sentry 7368726717 (crawler appelant l'endpoint détail
Product avec un uuid valide).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `api_v2/views.py` | `ProductViewSet` : + `lookup_field = "uuid"` |
| `tests/pytest/test_product_retrieve.py` | Nouveau test DB-only : retrieve par uuid → 200, uuid inconnu → 404 |

### Migration
- **Migration nécessaire / Migration required :** Non

## API v2 — `GET /events/{id}/` accepte uuid OU slug front (+ 404 propre) / Event retrieve by uuid OR front slug

**Date :** 2026-05-25
**Migration :** Non

**Quoi / What :**
- **Résolution par slug.** `GET /api/v2/events/{id}/` accepte désormais, en plus
  de l'uuid, le **slug** utilisé par le contrôleur front (ex :
  `mon-evenement-260620-0900-7d51dee7`). Logique miroir d'`EventMVT.retrieve` :
  les 8 derniers caractères hex du slug = début de l'uuid → `uuid__startswith`,
  puis fallback `slug__startswith`. Nouvelle fonction
  `get_event_par_identifiant_ou_404(identifiant)`.
- **Plus de filtre `published`** sur la résolution `retrieve` (uuid **et** slug),
  pour coller au comportement du front (`EventMVT.retrieve` ne filtre pas
  `published`). ⚠️ Conséquence : un évènement non publié devient récupérable par
  l'API v2 via son uuid/slug.
- **404 propre sur identifiant inconnu/malformé.** Avant, un slug envoyé sur
  `retrieve`/`destroy`/`link-address` faisait lever `ValidationError` à Django
  (conversion `UUIDField`) → **HTTP 500**. `destroy` et `link-address` utilisent
  un helper `get_objet_par_uuid_ou_404` (uuid-only → 404 si malformé) ; `retrieve`
  résout uuid+slug et renvoie 404 si rien ne correspond.

**Pourquoi / Why :** Issue Sentry 7504311969 — un client/crawler (clé API valide)
appelait l'API avec le **slug** du front au lieu de l'uuid → 500. On rend l'API
robuste (404, jamais 500) **et** on accepte le slug front pour que la même URL
fonctionne des deux côtés. Même classe de bug que le piège 9.76 (`detail_vente`).

**Périmètre / Scope :** Event uniquement. Les autres endpoints détail par uuid
(Product, Reservation, Membership, Initiative) gardent le même défaut latent
(500 sur slug) ; le helper `get_objet_par_uuid_ou_404` est prêt à y être appliqué.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `api_v2/views.py` | + `import re` ; + helpers `get_objet_par_uuid_ou_404` et `get_event_par_identifiant_ou_404` ; `retrieve` résout uuid+slug ; `destroy`/`link_address` migrés sur le helper uuid-only |
| `tests/pytest/test_event_retrieve_invalid_uuid.py` | Test DB-only : retrieve par uuid → 200, par slug → 200, slug inconnu → 404, uuid inconnu → 404 |

### Migration
- **Migration nécessaire / Migration required :** Non

### Note appelant / Caller note
Le « spider » Sentry possède une clé API valide et appelle avec un slug : il
existe probablement une intégration qui construit des URLs `/api/v2/events/<slug>/`.
Ce correctif rend l'API robuste et compatible, mais l'appelant peut être revu.

## Admin — Recherche par adhésion + renommage « Adhésion / Abonnement / Pass »

**Date :** 2026-05-21
**Migration :** Oui (`BaseBillet/0213_alter_membership_options` — options only, no-op DB)

**Quoi / What :**
- **Recherche users élargie** : la barre de recherche du changelist
  `HumanUserAdmin` cherche désormais aussi dans les **nom/prénom saisis sur les
  adhésions** (`memberships__first_name`, `memberships__last_name`), en plus du
  nom/prénom/email de l'user. Permet de retrouver un compte par le nom de
  l'adhérent·e (parfois différent du compte). Django ajoute `distinct()` au besoin.
- **Renommage** du modèle `Membership` : `verbose_name` / `verbose_name_plural`
  → **« Adhésion / Abonnement / Pass »** (titre de la page d'administration).
- **Sidebar** : l'item de menu vers les adhésions → **« Adhésion / Pass »**.

**Pourquoi / Why :** Accueil festival/forum/salon : retrouver vite un compte par
le nom de l'adhésion ; libellés reflétant les trois usages (adhésion ponctuelle,
abonnement récurrent, pass).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `HumanUserAdmin.search_fields` : + `memberships__first_name`, `memberships__last_name` |
| `BaseBillet/models.py` | `Membership.Meta` : `verbose_name`/`verbose_name_plural` = « Adhésion / Abonnement / Pass » |
| `BaseBillet/migrations/0213_alter_membership_options.py` | Migration d'options (no-op DB) |
| `Administration/admin/dashboard.py` | Item sidebar adhésions → « Adhésion / Pass » |

### Migration
- **Migration nécessaire / Migration required :** Oui (options only)
- `BaseBillet/0213_alter_membership_options` · `manage.py migrate_schemas --executor=multiprocessing`

### i18n
Nouvelles chaînes (source FR) : `Adhésion / Abonnement / Pass`, `Adhésion / Pass`
(remplacent les anciens `Subscription`/`Subscriptions`). makemessages/compilemessages
par le mainteneur.

## Admin — Évènements et adhésions sur la fiche user / Admin — bookings & memberships on user profile

**Date :** 2026-05-21
**Migration :** Non

**Quoi / What :** La fiche utilisateur·ice de l'admin affiche deux encarts
riches, alimentés **en local** (ORM, tenant courant — aucun appel Fedow),
pensés pour l'accueil d'un festival / forum / salon :
- **Évènements** : toutes les réservations de l'user, séparées « À venir » /
  « Passés ». Colonnes : évènement (lien cliquable vers la réservation), date,
  nombre de billets, montant payé, moyen(s) de paiement, statut (badge couleur).
- **Adhésions** : séparées « En cours » / « Passées ». Colonnes : adhésion
  (lien cliquable), montant (contribution), moyen de paiement, échéance, statut.
- Montants alignés en chiffres tabulaires ; badges de statut en styles inline
  (couleur **+** texte, lisibles en thème clair comme sombre).
- **Performance** : `prefetch_related('tickets', 'lignearticles', 'paiements__lignearticles')`
  + helper `_lignes_payees_prefetch` (montant + moyens calculés en mémoire) →
  **nombre de requêtes SQL constant** quel que soit le nombre de réservations,
  pas de N+1. Mesuré : 6 réservations + 13 adhésions = **5 requêtes**.
- **Robustesse** : la collecte évènements/adhésions est isolée dans son propre
  `try/except` (logge + dégrade) — un cas de données limite ne peut **jamais
  faire planter (500)** la fiche utilisateur. Tri réservations en `NULLS LAST`
  (les réservations sans évènement ne remontent plus en tête).
- **Vérifié visuellement** (Chrome) : encarts remplis, liens cliquables, badges
  de statut colorés (vert/bleu/ambre/rouge), montants alignés, toggles de droits
  fonctionnels, bouton Tirelire OK, aucune erreur console.

**Correctif au passage / Fix :** `HumanUserAdmin` contenait **deux**
`changeform_view` (doublon préexistant) ; la 2ᵉ écrasait la 1ʳᵉ. Les deux sont
fusionnées en une seule méthode (états des droits + évènements + adhésions),
ce qui rend les encarts réellement alimentés.

**Pourquoi / Why :** Donner à l'accueil une vue complète et scannable de
l'activité de la personne, sans dépendre de Fedow.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | Helpers badges + `_admin_url_basebillet` (niveau module) ; fusion des deux `changeform_view` de `HumanUserAdmin` (droits + évènements + adhésions enrichis) ; import `NoReverseMatch` |
| `Administration/templates/admin/human_user/right_and_wallet_info.html` | Encarts « Évènements » et « Adhésions » : tableaux enrichis (badges, montants tabulaires, liens cliquables) |

### Migration
- **Migration nécessaire / Migration required :** Non

### i18n
Nouvelles chaînes, **texte source en français** : `Évènements`, `À venir`,
`Passés`, `Évènement`, `Date`, `Billets`, `Payé`, `Paiement`, `Statut`,
`Aucun évènement à venir`, `Aucun évènement passé`, `Adhésions`, `Adhésion`,
`En cours`, `Passées`, `Montant`, `Échéance`, `Aucune adhésion en cours`,
`Aucune adhésion passée`. Le mainteneur lance makemessages/compilemessages.

## Admin — Dernières transactions Fedow (72 h) dans la fiche user / Admin — last 72h Fedow transactions in user profile

**Date :** 2026-05-21
**Migration :** Non

**Quoi / What :** Le bloc « Tirelire » de la fiche utilisateur·ice de l'admin
affiche désormais, en plus des cartes et du solde, les **transactions des
72 dernières heures** récupérées depuis Fedow.
- Vue `admin_my_cards` enrichie : appel `FedowAPI.transaction.paginated_list_by_wallet_signature(user)`
  filtré sur 72 h. Encadré `try/except` : si Fedow est indisponible, le bloc
  cartes/tokens reste affiché (les transactions sont simplement omises).
- Nouveau bloc « Last transactions (72h) » dans `wallet_info.html` (style Unfold,
  réutilise les filtres `dround` / `get_choice_string` / `naturaltime`).
- L'historique inclut les transactions d'un éventuel **wallet éphémère fusionné**
  (actions `FUS`), car la signature de l'user retrouve tout l'historique du wallet.
- Les transactions d'**adhésion** (asset de catégorie `SUB` / SUBSCRIPTION) sont
  **exclues** du bloc, par cohérence avec l'exclusion des adhésions du solde de tokens.

**Pourquoi / Why :** Donner à l'admin une vue rapide de l'activité récente de la
tirelire d'un membre (support, surveillance des abus).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `admin_my_cards` : transactions 72 h ajoutées au contexte (try/except Fedow) |
| `Administration/templates/admin/membership/wallet_info.html` | Bloc « Last transactions (72h) » |

### Migration
- **Migration nécessaire / Migration required :** Non

### i18n
Nouvelles chaînes, **texte source en français** : `Dernières transactions (72h)`,
`Aucune transaction sur les 72 dernières heures`, `Valeur`, `Sens`.
(`Action`, `Date` identiques FR/EN.) Le mainteneur lance makemessages/compilemessages
(traduction EN générée depuis le FR).

## API v2 — Recharge de tokens non fiduciaires / API v2 — non-fiat wallet refill

**Date :** 2026-05-21
**Migration :** Oui (`BaseBillet/0211_externalapikey_gift_asset`,
`BaseBillet/0212_alter_externalapikey_gift_asset`)

**Quoi / What :** Nouvelle route `POST /api/v2/wallet-refills/` qui crédite des
tokens **non adossés à l'euro** sur la tirelire d'un user à partir de son email,
sans paiement — réplique en API du trigger `Price.fedow_reward_*`.
- Catégories rechargeables (`AssetFedowPublic.REFILLABLE_CATEGORIES`) : `TNF`
  (cadeau), `TIM` (monnaie temps), `FID` (fidélité), `BDG` (badgeuse). Exclues :
  fiduciaires (`TLF`, `FED`) et adhésion (`SUB`).
- Authentification par clé API (`SemanticApiKeyPermission`).
- Nouveau champ `ExternalApiKey.gift_asset` (FK → `fedow_public.AssetFedowPublic`,
  `limit_choices_to={'category__in':['TNF','TIM','FID','BDG']}`). Sa présence
  active le droit `walletrefill` **et** restreint la clé à ce seul asset.
- Payload : `email` + `asset` (uuid TNF) + `amount` (entier, unité brute).
- Plafond hardcodé par recharge : `GIFT_REFILL_MAX_AMOUNT = 10000`.
- Header optionnel `Idempotency-Key` : anti double-crédit (cache best-effort,
  TTL ~48 h ; renvoie la transaction stockée avec un `208 Already Reported`).
- Réponse schema.org `MoneyTransfer`.

**Pourquoi / Why :** Permettre à un service externe d'offrir des tokens cadeau
de façon contrôlée (un asset par clé, catégorie cadeau uniquement, plafond).
La route v1 `/api/wallet/get_stripe_checkout_with_email/` (recharge **payante**
Stripe) reste inchangée.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `fedow_public/models.py` | Constante `AssetFedowPublic.REFILLABLE_CATEGORIES` (TNF/TIM/FID/BDG) |
| `BaseBillet/models.py` | Champ `gift_asset` sur `ExternalApiKey` + entrée `api_permissions()` |
| `BaseBillet/migrations/0211_externalapikey_gift_asset.py` | Ajout du champ |
| `BaseBillet/migrations/0212_alter_externalapikey_gift_asset.py` | Élargissement `limit_choices_to` + libellés |
| `api_v2/serializers.py` | `WalletRefillCreateSerializer` |
| `api_v2/views.py` | `WalletRefillViewSet` + `GIFT_REFILL_MAX_AMOUNT` + import `gettext` |
| `api_v2/urls.py` | Route `wallet-refills` (basename `walletrefill`) |
| `Administration/admin_tenant.py` | `gift_asset` dans `ExternalApiKeyAdmin.fields` |
| `api_v2/openapi-schema.yaml` | Path + schéma `MoneyTransfer` |
| `api_v2/README.md`, `api_v2/GUIDELINES.md` | Documentation de la route |
| `tests/pytest/test_api_v2_wallet_refill.py` | 11 tests (FedowAPI mockée) |

### Migration
- **Migration nécessaire / Migration required :** Oui
- `BaseBillet/0211_externalapikey_gift_asset` + `BaseBillet/0212_alter_externalapikey_gift_asset`
- `manage.py migrate_schemas --executor=multiprocessing`

### i18n
Nouvelles chaînes `_()` côté serveur (messages d'erreur de la vue + `verbose_name`/
`help_text` du champ `gift_asset`). Le mainteneur lance makemessages/compilemessages.

## Module « Agenda participatif » / "Participatory agenda" module

**Date :** 2026-05-21
**Migration :** Oui (`BaseBillet/0210_configuration_module_agenda_participatif`)
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**Quoi / What :** Le wizard public de proposition d'évènement est désormais
piloté par un module Groupware dédié, désactivé par défaut.
- Nouveau champ `Configuration.module_agenda_participatif` (`BooleanField`,
  `default=False`).
- Nouvelle carte « Agenda participatif » sur le dashboard admin (toggle HTMX),
  avec le texte d'aide : « un formulaire pour que vos users puissent proposer
  des évènements sur la page agenda ; évènements à valider dans l'admin ».
- Sur la page agenda, le bouton « Proposer un évènement » ne s'affiche que si
  le module est actif (`{% if config.module_agenda_participatif %}`).
- `WizardEventPublicSerializer.validate()` refuse la création de proposition si
  le module est désactivé (garde côté serveur, même en atteignant l'URL
  directement).

**Pourquoi / Why :** Permettre à chaque tenant d'activer ou non l'agenda
participatif. Le parcours admin de création d'évènement reste inchangé.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | Champ `module_agenda_participatif` sur `Configuration` |
| `BaseBillet/migrations/0210_configuration_module_agenda_participatif.py` | Migration du champ |
| `Administration/admin/dashboard.py` | Entrée `MODULE_FIELDS` (carte + texte d'aide) |
| `BaseBillet/templates/reunion/views/event/list.html` | Bouton public conditionné au module |
| `BaseBillet/validators.py` | Garde module dans `WizardEventPublicSerializer.validate()` |

### Migration
- **Migration nécessaire / Migration required :** Oui
- `BaseBillet/0210_configuration_module_agenda_participatif`
- `manage.py migrate_schemas --executor=multiprocessing`

### i18n
Carte dashboard : texte source **en français** (« Agenda participatif » + texte
d'aide), affichée directement sans attendre de traduction. Le mainteneur lance
makemessages/compilemessages pour générer la traduction EN. Autres chaînes `_()` :
`Participatory agenda module` (verbose_name modèle, EN),
`La proposition d'évènement n'est pas activée.` (erreur serializer, FR).

## Triggers Fedow dans les inlines de tarif (adhésion + billet) / Fedow triggers in price inlines (membership + ticket)

**Date :** 2026-05-21
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Depuis que les tarifs (`Price`) sont des inlines dans les proxys
produit, l'onglet « Triggers » de l'ancienne vue `PriceAdmin` n'était plus
atteignable (lien désactivé, absent de la sidebar). Les deux déclencheurs Fedow
sont désormais exposés **directement dans l'inline du bon proxy** :
- **Adhésion** (`MembershipPriceInline`) : `fedow_reward_enabled` → recharge le
  wallet du membre à l'achat de l'adhésion.
- **Billet** (`TicketPriceInline`) : `reward_on_ticket_scanned` → récompense le
  wallet de l'acheteur au scan du billet.

Dans les deux cas, `fedow_reward_asset` + `fedow_reward_amount` ne s'affichent que
si le toggle est coché, via le mécanisme JS `inline_conditional_fields` existant.

**Pourquoi / Why :** Redonner l'accès à un réglage rare (très peu de tenants) sans
polluer l'inline du cas courant. Comme chaque proxy n'a qu'un seul toggle, la
limite « une source par règle » du JS conditionnel n'est jamais atteinte (pas de
`OU` à gérer). Le câblage conditionnel est remonté dans la base `ProductAdmin`
pour que `TicketProductAdmin` en bénéficie aussi (avant : uniquement adhésion).

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/products.py` | `BasePriceInline.formfield_for_foreignkey` (filtre `fedow_reward_asset` sur `AssetFedowPublic` local du tenant) ; `BasePriceInlineForm.__init__` désactive les boutons +/✎/🗑/👁 du dropdown asset (aucune création/édition/consultation d'asset depuis l'inline) ; champs trigger + règles conditionnelles ajoutés à `MembershipPriceInline` et `TicketPriceInline` (+ `Media.js`) ; `change_form_after_template` + `changeform_view` remontés dans `ProductAdmin` (base), retirés de `MembershipProductAdmin` (devenus redondants) ; **nettoyage** : correction i18n (`_(f"…")` → placeholders `%`) dans `duplicate_product`/`archive`/`desarchive`, suppression d'un `logger.error(self.actions_row)` de debug |
| `Administration/admin_tenant.py` | **nettoyage** : suppression du code mort `PriceInlineChangeForm` + `PriceInline` (ancien inline orphelin, remplacé par le package `Administration/admin/`) |
| `A TESTER et DOCUMENTER/triggers-fedow-inline-tarif.md` | NOUVEAU — scénarios de test manuel |

> **i18n :** les correctifs `_(f"…")` → `_("…%(x)s…") % {…}` **changent les msgid** de
> `duplicate_product`/`archive`/`desarchive`. Lancer le workflow traductions
> (`makemessages` + `.po` + `compilemessages`) — non lancé ici (le mainteneur s'en charge).

### Décisions clés / Key decisions

- **Un toggle par proxy** : adhésion = `fedow_reward_enabled` (recharge à l'achat),
  billet = `reward_on_ticket_scanned` (récompense au scan). Sémantique confirmée
  dans le code consommateur (`tasks.py:refill_..._from_price_solded` vs
  `signals.py:check_reward` → `tasks.py:refill_..._from_ticket_scanned`).
- **JS inchangé** : la séparation par proxy évite le besoin d'un `OU` dans
  `inline_conditional_fields.js`.
- **`PriceAdmin` standalone conservé** (onglet Triggers intact) — sert toujours
  d'autocomplete et de cible de redirection, mais n'est plus le chemin nominal.

### Migration

- **Migration nécessaire / Migration required:** Non (aucun changement de modèle ;
  les 4 champs `Price` existent déjà depuis les migrations 0163 / 0180).

## Wizard évènement V2 : connexion classique, lieu en 2 pages, multi-évènements / Event wizard V2: classic login, 2-page place, multi-events

**Date :** 2026-05-21
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Évolution du wizard évènement (cf. entrée du 2026-05-19). Le
wizard public n'utilise plus l'OTP mais la **connexion classique** (l'OTP est
conservé en code, parqué pour un futur offcanvas de connexion). Le choix de lieu
passe en **2 pages** comme l'onboarding (page 1 : adresse existante filtrable OU
nom d'un nouveau lieu ; page 2 : carte pré-remplie avec recherche auto). On peut
désormais **proposer / créer plusieurs évènements** d'un coup (liste HTMX
add/remove, lieu partagé). Le routage des 2 wizards passe sur un **router DRF**
(plus de `path()` manuels). La liste d'adresses **plafonne l'affichage à 50** (la
recherche couvre la totalité) pour rester navigable avec 300+ adresses, et le
toggle de mode passe en **vertical sur mobile**.

**Pourquoi / Why :** `authentication_classes = []` faisait afficher « Connexion »
à un visiteur déjà connecté et imposait un OTP redondant. Le multi-évènements
reproduit le formulaire onboarding (annoncer plusieurs dates d'un lieu). Le
plafond d'adresses et le toggle mobile préparent les tenants « agenda régional ».

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | Auth session + garde `_require_login_or_redirect`, split lieu (2 helpers), multi-events (3 helpers + 2 fabriques `_creer_event_*`), `@action` + `url_name` |
| `BaseBillet/validators.py` | `WizardPlaceSelectSerializer` + `WizardPlaceMapSerializer` (remplacent `WizardPlaceSerializer`) |
| `BaseBillet/urls.py` | `SimpleRouter` `wizard_router` (avant le routeur principal), suppression des `as_view`/`path` manuels du wizard |
| `BaseBillet/templates/reunion/views/event/wizard/_form_lieu.html` | Toggle full-width + liste filtrable + plafond 50 + media query mobile |
| `BaseBillet/templates/reunion/views/event/wizard/_form_carte.html` + `{admin,public}_step_map.html` | NOUVEAU — page carte (étape 2 du lieu) |
| `BaseBillet/templates/reunion/views/event/wizard/_events_inner.html` | NOUVEAU — liste brouillons + sous-form HTMX add |
| `BaseBillet/templates/reunion/views/event/wizard/{admin,public}_step2_event.html` | Réécrits en étape multi-évènements |
| `Administration/admin/dashboard.py` | Fix badge sidebar « None » (`event_proposals_badge_callback(request) or ""`) |
| `BaseBillet/templates/reunion/partials/navbar.html` | Ouverture auto de l'offcanvas connexion via `?login=1` |
| `static/widgets/widget_carte_adresse.js` | Repli reverse-geocode quand la recherche par nom renvoie une adresse incomplète |
| `TECH_DOC/SESSIONS/EVENT_WIZARD/CHANTIER-02-*.md` | NOUVEAU — recap du chantier |
| `TECH_DOC/SESSIONS/WIDGET_GEO/03-fix-reverse-geocode-fallback.md` | NOUVEAU — note de correctif |
| `A TESTER et DOCUMENTER/event-wizards.md` | Mis à jour (nouveau flux login + multi-events) |

### Décisions clés / Key decisions

- **OTP parqué** (code conservé) → réintégration future dans l'offcanvas de connexion.
- **Lieu partagé** : tous les évènements d'une proposition au même lieu choisi à l'étape 1.
- **Image de brouillon** : `event.img.name = chemin` au finalize (une seule sauvegarde → signaux 1×).
- **HTMX add** : renvoi **200** sur erreur de validation (pas de config swap-on-422 dans le skin reunion).
- **Routage** : `SimpleRouter` inclus avant `EventMVT` pour que `event/propose/...` résolve avant `event/{pk}/`.

### Migration

- **Migration nécessaire / Migration required:** Non (aucun changement de modèle ; `Event.is_proposal` existe déjà depuis la migration 0209).

### À surveiller / Watch out

- Tests `tests/pytest/test_event_wizard_public.py` à adapter (testaient le flow OTP/anonyme) — différé.
- i18n : `makemessages` / `compilemessages` à lancer (nouvelles chaînes).
- Images de brouillons abandonnés (wizard quitté sans finaliser) : restent dans `event_wizard_drafts/` (pas de purge auto).


## Carte explorer ROOT : pills exclusives, tag chips, URL partageable / Exclusive pills, tag chips, shareable URL

**Date :** 2026-05-21
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Refonte UX de la carte explorer ROOT (`/explorer/`). La pill
"Tous" est supprimée — il reste "Lieux" et "Événements" exclusives. En mode
Événements, la liste affiche 1 card par event futur (au lieu de cards lieu).
Une nouvelle barre de tag chips (top 10 par fréquence parmi les events visibles)
permet de filtrer par tag, avec bouton "+ N tags" pour le reste. Les filtres
(`v`, `q`, `tag`) sont synchronisés dans l'URL via `history.replaceState`,
ce qui rend la carte partageable. L'accordéon "Prochains événements" sur les
cards lieu est réparé (régression CHANTIER-05 résolue). Un bug 1-ligne sur
le JSON-LD federation des explorers tenant est corrigé en parallèle.

**Pourquoi / Why :** Suite à CHANTIER-05, le filtre "Événements" ne changeait
plus visuellement la vue, et la liste d'événements avait disparu. En parallèle,
l'arrivée de tenants type "réseau régional" ou "agenda culturel régional"
(200+ PostalAddress) demandait une UX de filtrage par thématique pour rester
navigable. Les tags `Event.tag` existaient en DB depuis longtemps mais
n'étaient pas exposés côté SEO.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `seo/services.py` | +`get_event_tags_for_tenants` (helper SQL cross-schema), propagation `tags` dans `events_pour_popup`, `get_events_for_tenants` retourne aussi `uuid` |
| `seo/tasks.py` | Enrichissement events avec tags dans `refresh_seo_cache` (1 requête SQL supplémentaire) |
| `BaseBillet/views.py` | Fix bug 1-ligne : `lieux` → `tenants` dans le JSON-LD federation des explorers tenant |
| `seo/templates/seo/partials/explorer_widget.html` | Suppression pill "Tous", ajout `#explorer-tags`, data-i18n |
| `seo/static/seo/explorer.js` | Refonte `applyFilters`, chips top 10, URL sync, accordéon réparé |
| `seo/static/seo/explorer.css` | +Styles `.explorer-tag-chip*`, `.explorer-empty-state`, `.explorer-card-tags` |
| `tests/pytest/test_seo_event_tags.py` | NOUVEAU — tests unitaires (3) du nouveau helper |
| `tests/pytest/test_seo_aggregate_points.py` | +2 tests propagation tags |
| `tests/e2e/test_explorer_ux_pills_tags.py` | NOUVEAU — 8 tests Playwright (pills, chips, URL, empty state) |
| `tests/e2e/conftest.py` | NOUVEAU sur la branche — fixtures Playwright (page, browser) |
| `pytest.ini` | +marker `e2e` |
| `CHANGELOG.md` | Cette entrée |
| `A TESTER et DOCUMENTER/explorer-ux-pills-tags.md` | NOUVEAU — scénarios test manuel |

### Activation

Aucune migration DB. Le nouveau format de cache (events avec `tags`) est rétro-
compatible : le JS lit avec `.tags || []`. Activation au prochain cycle Celery
Beat de `refresh_seo_cache` (4h max), ou refresh manuel :

```bash
docker exec lespass_django poetry run python manage.py shell -c "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"
```

## Wizards de création et proposition d'évènement / Event creation & proposal wizards

**Date :** 2026-05-19
**Migration :** Oui (`BaseBillet/migrations/0209_event_is_proposal.py`, additive, default=False)
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Refonte de la création d'évènement en wizard 2 étapes (admin)
avec carte interactive Leaflet pour les nouvelles adresses. Ajout d'un wizard
public anonyme protégé par OTP email permettant à tout visiteur de proposer un
évènement soumis à modération admin (badge sidebar Unfold + filtre + action bulk).

**Pourquoi / Why :** Améliorer l'UX admin (offcanvas → wizard plus FALC) et
ouvrir la plateforme aux contributions publiques avec modération. Mettre en
place un service OTP DRY (`AuthBillet/otp_service.py`) réutilisable pour de
futurs flows (login OTP, SSO).

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `AuthBillet/otp_service.py` | NOUVEAU — service OTP stateless DRY |
| `AuthBillet/otp_session.py` | NOUVEAU — helper session HTTP |
| `AuthBillet/templates/auth/emails/otp_code.{html,txt}` | NOUVEAU — templates email génériques |
| `BaseBillet/models.py` | +`Event.is_proposal` (BooleanField default=False) |
| `BaseBillet/migrations/0209_event_is_proposal.py` | NOUVEAU — migration additive |
| `BaseBillet/views.py` | +`EventWizardAdmin`, +`EventWizardPublic` ViewSets. Suppression `EventMVT.simple_*` |
| `BaseBillet/validators.py` | +4 serializers wizard |
| `BaseBillet/urls.py` | +8 routes (admin + public) |
| `BaseBillet/templates/reunion/views/event/wizard/` | NOUVEAU (9 templates) |
| `BaseBillet/templates/reunion/views/event/list.html` | Suppression offcanvas, ajout 2 boutons (admin + public) |
| `BaseBillet/templates/faire_festival/views/event/list.html` | Adaptation skin Faire Festival |
| `BaseBillet/templates/reunion/views/event/partial/simple_add_event.html` | supprimé |
| `BaseBillet/templates/reunion/views/event/partial/address_simple_add.html` | supprimé |
| `Administration/admin/dashboard.py` | +`event_proposals_badge_callback` + badge sur item Events |
| `Administration/admin_tenant.py` | +`IsProposalFilter` + action `approuver_propositions` sur `EventAdmin` |
| `tests/pytest/test_otp_service.py` | NOUVEAU — 16 tests |
| `tests/pytest/test_otp_session.py` | NOUVEAU — 12 tests |
| `tests/pytest/test_event_is_proposal_field.py` | NOUVEAU — 2 tests |
| `tests/pytest/test_event_wizard_admin.py` | NOUVEAU — 9 tests |
| `tests/pytest/test_event_wizard_public.py` | NOUVEAU — 12 tests |
| `tests/pytest/test_event_proposal_admin.py` | NOUVEAU — 5 tests |
| `TECH_DOC/SESSIONS/EVENT_WIZARD/` | NOUVEAU hub : INDEX + SPEC + PLAN |
| `TECH_DOC/SESSIONS/OTP/` | NOUVEAU hub : INDEX + SPEC |
| `A TESTER et DOCUMENTER/event-wizards.md` | NOUVEAU — scénarios de test manuel |

### Décisions clés / Key decisions

- **Service OTP DRY** : `OtpService` stateless + `OtpSession` HTTP helper, réutilisable (login OTP, SSO, migration onboard future).
- **Anti-spam** : Throttle DRF (3 demandes/heure/IP) + honeypot champ `website` + garde de session entre les étapes.
- **Modération** : `Event.is_proposal=True, published=False` → badge sidebar Unfold + filtre `Proposals pending` + action bulk `Approve and publish`.
- **Compatibilité** : onboard inchangé (logique OTP custom conservée), events existants restent `is_proposal=False` (défaut migration).

### Migration

- **Migration nécessaire / Migration required:** Oui
- `BaseBillet/migrations/0209_event_is_proposal.py` (additive, default=False, aucune data migration)


## SEO Chantier 05 : carte explorer ROOT — 1 marker par PostalAddress / SEO Chantier 05: 1 marker per PostalAddress on ROOT explorer map

**Date :** 2026-05-17
**Migration :** Non (juste une nouvelle valeur dans CharField choices)
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Refonte de la carte `/explorer/` du tenant ROOT. Avant :
1 marker par tenant (positionne sur Configuration.postal_address). Apres :
1 marker par PostalAddress active, avec popup riche listant le nom du lieu,
l'adresse, le tenant + un lien, et les 5 prochains events futurs.

**Pourquoi / Why :** Suite a l'import de 327 PostalAddress geolocalisees
(via outil nominatim-review), les tenants comme l'Universite Populaire de
Villeurbanne (24 lieux d'evenements differents) etaient invisibles. La carte
ROOT devient une vraie cartographie des lieux du reseau, pas juste des sieges.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `seo/models.py` | +constante `SEOCache.AGGREGATE_POINTS` |
| `seo/services.py` | +`get_postal_addresses_for_tenants`, +`build_aggregate_points`, refacto `build_explorer_data_for_tenants` (retourne `{points, tenants}`) |
| `seo/tasks.py` | +Etape 6 dans `refresh_seo_cache` (ecriture `AGGREGATE_POINTS`) |
| `seo/views.py` | `explorer()` itere sur `explorer_data["tenants"]` pour federation JSON-LD |
| `seo/templates/seo/partials/explorer_widget.html` | Commentaires mis a jour |
| `seo/static/seo/explorer.js` | Boucle sur `state.data.points` (1 marker par PA), popup riche avec `events_futurs`, `state.markers` indexes par `pa_id` |
| `seo/static/seo/explorer.css` | +styles popup riche (.explorer-popup-address, -tenant, -logo, -events-list, -events-more) |
| `tests/pytest/test_seo_aggregate_points.py` | +6 tests unitaires (mocks, sans DB) |
| `tests/playwright/tests/35-explorer-markers-per-pa.spec.ts` | +2 tests E2E (structure JSON + markers visibles) |
| `TECH_DOC/SESSIONS/SEO/CHANTIER-05-explorer-markers-per-pa.md` | Spec |
| `TECH_DOC/SESSIONS/SEO/PLAN-05-explorer-markers-per-pa.md` | Plan d'implementation |

### Decisions cles / Key decisions
- **1 marker par PA** : popup riche listant tout (vs. markers superposes)
- **Filtre "tenant vivant"** : PA incluse si tenant a >=1 event futur OU >=1 produit publie
- **Cache dedie** `AGGREGATE_POINTS` : zero impact sur `AGGREGATE_LIEUX` (utilise par les autres vues `/lieu/<slug>/`, `/lieux/`, recherche)
- **Top 5 events** par popup + `events_futurs_count_total` pour afficher "+ N autres"

### Compatibilite / Compatibility
- `AGGREGATE_LIEUX` reste maintenu en parallele -> vues `/lieu/<slug>/`, `/lieux/`, recherche ROOT, JSON-LD federation continuent de fonctionner comme avant.
- **Activation** : prochain cycle Celery Beat de `refresh_seo_cache` (4h max), ou manuel :
  ```bash
  docker exec lespass_django poetry run python manage.py shell -c \
    "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"
  ```


## Liste des évènements : filtre par date en SQL + filtres conservés à la pagination / Event list: date filter in SQL + filters kept on pagination

**Quoi / What :** Correction d'un bug de la page liste des évènements (`EventMVT`)
visible sur les gros agendas (festival > 300 évènements). Le filtre par date
était appliqué en Python **après** la pagination (100 évènements/page) : filtrer
un jour situé au-delà de la page 1 (ex : samedi d'un festival jeu/ven/sam) ne
renvoyait rien. Désormais le filtre par date est appliqué en base (SQL) et,
quand un jour est sélectionné, **tous** les évènements de ce jour s'affichent
sans pagination. De plus, le bouton « CHARGER PLUS » conserve maintenant tous
les filtres actifs (recherche, thématique, tags multiples), au lieu du seul
premier tag — la recherche ne « perdait » plus son filtre après un chargement
supplémentaire.

Les pages filtrées par **date seule** sont désormais mises en cache (1 h), comme
la page principale — c'est l'action la plus fréquente sur un festival. Le cache
de la liste utilise un **jeton de version par tenant** réécrit dans `Event.save()` :
modifier un évènement invalide d'un coup la page principale ET toutes les pages
par date (pas de `cache.incr`, qui est piégeux avec memcached).

**Pourquoi / Why :** Sur un festival, la pagination s'arrêtait au milieu et le
filtre par jour affichait « aucun résultat » pour les jours non encore chargés.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `federated_events_filter` : param `date_filter`, filtre SQL `datetime__date`, pagination désactivée si date filtrée. Cache versionné (page principale + page par date seule). Helpers `_parse_date_filter` + `_querystring_filtres`. `list()` : filtre date en SQL (suppression du filtrage Python post-pagination). `partial_list()` : lecture/propagation du filtre date. Querystring des filtres actifs exposée au contexte. |
| `BaseBillet/models.py` | `Event.save()` : invalidation du cache liste par réécriture d'un jeton de version (`event_list_version_{tenant.uuid}`) au lieu de la suppression d'une clé unique. |
| `BaseBillet/templates/faire_festival/views/event/list.html` | Bouton CHARGER PLUS : `{{ querystring_filtres }}` au lieu de `&tag={{ tags.0 }}`. |
| `BaseBillet/templates/faire_festival/views/event/partial/list_append.html` | Idem bouton CHARGER PLUS. |

### Migration
- **Migration nécessaire / Migration required :** Non

## Home publique : section « Ils contribuent » + mention France 2030 dans le footer / Public home: "They contribute" section + France 2030 footer mention

**Quoi / What :** Ajout d'une section « Ils contribuent » sur la landing
page du tenant public (app `seo`), à la suite des bandeaux lieux et
événements de la fédération : panneau gris doux, grille de tuiles
blanches (logo + nom dessous), logos cliquables, pilotée par une liste
explicite dans la vue. Un logo blanc sur transparent (CoopCircuit) a été
inversé pour rester visible sur tuile blanche. Ajout aussi de la mention
obligatoire de financement France 2030 dans le footer de la home publique
(séparateur + texte à gauche / logo aligné à droite), qui en était
dépourvue alors que les footers des tenants l'affichent déjà.

**Pourquoi / Why :** Valoriser les contributeurs du commun sur la page
d'accueil du réseau, et homogénéiser la mention légale France 2030
(« Solutions de billetteries innovantes », Caisse des Dépôts) présente
sur les footers tenants mais absente du footer ROOT.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/views.py` | Constante `CONTRIBUTEURS` (nom + logo + url) + ajout au contexte de `landing` |
| `seo/templates/seo/landing.html` | Section `contributeurs-section` (grille de logos cliquables, masquée si liste vide) |
| `seo/static/seo/seo.css` | Styles `.contributeurs-*` (grille auto-fit centrée, logos couleur, relief au survol) |
| `seo/templates/seo/base.html` | Mention France 2030 + logo `reunion/img/france_2030.png` dans le footer |

### Migration
- **Migration nécessaire / Migration required :** Non
- **i18n :** Nouvelles chaînes (`Ils contribuent`, sous-titre, mention France 2030…) — lancer `makemessages` + `compilemessages` (à la charge du mainteneur).

## SEO Chantier 01 : desindexer les instances DEV / DEMO / TEST / SEO Chantier 01: deindex DEV / DEMO / TEST instances

**Date :** 2026-05-17
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Les instances de dev / demo / test (filaos.re, devtib.fr)
etaient publiquement indexees sur Google et Bing alors qu'elles ne
devraient pas l'etre. Mise en place d'une regle metier simple :
`noindex, nofollow` (via `robots.txt` ET `<meta name="robots">`) quand
au moins un flag d'environnement est a `1` :
- `DEBUG=1` ou `TEST=1` ou `DEMO=1` ou `STRIPE_TEST=1`.

**Pourquoi / Why :** Aligne le projet sur le **Google AI Optimization
Guide** publie le 15 mai 2026 (cf. `TECH_DOC/SESSIONS/SEO/SPEC.md` et
Atomic atom `491b2fe3-049c-4b2d-86bf-ae2fc41b6b31`). Les instances dev
qui apparaissent dans la SERP volent la place du tenant principal sur
les requetes "TiBillet" et brouillent la marque. Une regle
supplementaire sur le host (DOMAIN / ADDITIONAL_DOMAINS) a ete
envisagee puis ecartee : redondante en pratique avec les 4 flags +
Django bloque deja les hosts inconnus via `ALLOWED_HOSTS`.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/seo_indexing.py` | NOUVEAU. Helper `should_noindex(request) -> bool` (regle metier complete, FALC bilingue) + context processor `noindex_context` |
| `TiBillet/settings.py` | +1 ligne dans `TEMPLATES.OPTIONS.context_processors` (`'TiBillet.seo_indexing.noindex_context'`) |
| `seo/views_common.py::robots_txt` | Branche sur `should_noindex(request)` : si True, sert `Disallow: /`. Sinon : `Allow: /` + sitemap |
| `BaseBillet/views_robots.py::robots_txt` | Meme logique cote tenant. Supprime imports inutiles (`connection`, `get_current_site`) |
| `seo/templates/seo/base.html` | Block `meta_robots` etend la logique : `noindex_seo` -> `noindex, nofollow`, sinon `index, follow` |
| `BaseBillet/templates/reunion/base.html` | Idem |
| `BaseBillet/templates/faire_festival/base.html` | Idem |
| `BaseBillet/templates/htmx/base.html` | NOUVEAU bloc `meta_robots` (n'en avait pas) + commentaire FALC bilingue |
| `tests/pytest/test_seo_indexing.py` | NOUVEAU. 5 tests unitaires : 4 flags d'env + 1 cas indexable |
| `TECH_DOC/SESSIONS/SEO/INDEX.md` | NOUVEAU. Hub du chantier SEO sur plusieurs sessions |
| `TECH_DOC/SESSIONS/SEO/SPEC.md` | NOUVEAU. Vision globale, principes Google 2026, etat actuel, anti-patterns |
| `TECH_DOC/SESSIONS/SEO/CHANTIER-01-noindex-dev.md` | NOUVEAU. Spec actionable de ce chantier |
| `A TESTER et DOCUMENTER/seo-noindex-dev.md` | NOUVEAU. Scenarios de test manuel |

### Migrations

- **Migration necessaire / Migration required :** Non

### Tests

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_indexing.py --api-key dummy -v
# 5 passed in 0.27s
```

### Note importante

Pour faire desindexer effectivement filaos.re et devtib.fr (deja
presents dans la SERP), il faut **en plus** soumettre une demande
de suppression via Google Search Console + Bing Webmaster apres le
deploiement. Sinon Google peut mettre plusieurs semaines a les
oublier tout seul.

---

## Session marathon onboard + landing : hotfix prod + UX + i18n / Onboard marathon: prod hotfix + UX + i18n

**Date :** 2026-05-17
**Migration :** Oui (2 migrations)
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Session multi-axes regroupant un hotfix prod critique
(PostalAddress lat/lng overflow sur les longitudes hors [-99, +99]),
plusieurs bugs UX du wizard onboarding (perte de session après login,
mailer en anglais non traduit, prénom/nom non répercutés sur l'user, long
description / logo non transférés au tenant, polling infini après erreur),
le polish de la landing root (4 nouvelles fonctionnalités + section
roadmap accordéon, JSON-LD WebSite + searchbox SERP, og:locale) et la
réécriture des deux templates email (OTP + ready) avec le wording riche
du flow legacy `/tenant/new/` adapté au contexte wizard.

**Pourquoi / Why :** Avant push prod. Sentry a remonté l'overflow lat/long
(création tenant cassée pour Asie / Pacifique / Amériques). Les autres
bugs étaient bloquants ou dégradants UX. La landing root manquait des
fonctionnalités différenciantes (open-data, AGPLv3, fédération) et n'avait
pas de roadmap visible pour engager la communauté.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `PostalAddress.latitude/longitude` 18/16 → 9/6 (overflow longitude hors [-99, +99]) |
| `BaseBillet/migrations/0207_fix_postaladdress_latlng_precision.py` | NOUVEAU |
| `MetaBillet/models.py` | + champ `language` sur `WaitingConfiguration` (CharField max 10) |
| `MetaBillet/migrations/0016_add_wc_language.py` | NOUVEAU |
| `onboard/views.py::_finalize_otp_success` | + `_set_session_wc()` après login (perte session avec SESSION_SAVE_EVERY_REQUEST=True) ; + report `wc.first_name/last_name` sur user (si user n'a pas déjà ces champs) |
| `onboard/views.py` POST identity | + capture `get_language()` dans `wc.language` |
| `onboard/tasks.py::onboard_otp_mailer` | + `translation.override(wc.language)` autour du sujet + render templates |
| `onboard/tasks.py::onboard_ready_mailer` | idem + nouveau context var `instance_url` |
| `onboard/tasks.py::create_tenant_from_draft` | NOUVEAU bloc "3ter" transfert `wc.long_description` + `wc.logo` vers `Configuration.long_description` + `Configuration.img` (try/except sans re-raise pour préserver l'idempotence Celery, cf. piège #23) |
| `onboard/templates/onboard/steps/06_launch.html` | Fix polling infini : retrait `hx-trigger="load, every 2s"` du parent `#status` (le swap innerHTML ne touche pas les attributs du parent, donc le polling continuait après status_error) |
| `onboard/templates/onboard/emails/ready.html` | Réécrit avec wording riche du legacy `welcome_email.html` adapté au contexte post-création (bouton "ACCÉDER À MON ESPACE", liste "Informations importantes", section "Voici ce que vous pouvez faire", signature équipe coopérative) |
| `onboard/templates/onboard/emails/ready.txt` | Version texte cohérente |
| `onboard/templates/onboard/emails/otp_code.html` | Réécrit dans le style général (table imbriquée, palette `#009058`, Arial) ; capsule vert clair encadrée avec code PIN en `Courier New 36px` letter-spacing 12px |
| `onboard/templates/onboard/emails/otp_code.txt` | Réécrit |
| `seo/templates/seo/landing.html` | Philo réécrite (Code Commun + Ostrom) ; + 4 nouvelles cartes Fonctionnalités (Données ouvertes, Logiciel libre AGPLv3, Agenda participatif, Référencement et SEO) ; + nouvelle section roadmap `<details>` natif "Futur de TiBillet" (Newsletter, Réseaux sociaux, Fédiverse, Cascade) ; + `<h2 visually-hidden>` pour hiérarchie SEO |
| `seo/templates/seo/base.html` | + `<meta property="og:locale">` mappé `fr_FR` / `en_US` |
| `seo/views.py::landing` | Split JSON-LD en 2 blocs : Organization (`json_ld_org`) + WebSite/SearchAction (`json_ld`) pour éligibilité sitelinks searchbox SERP Google |
| `seo/static/seo/seo.css` | + section "ROADMAP / FUTURE" (~85 lignes) — accordéon stylé, chevron rotate, palette orange pour "futur" vs vert pour "actuel", `prefers-reduced-motion` respecté |

### Migrations

- **Migration nécessaire / Migration required :** Oui
- `BaseBillet/migrations/0207_fix_postaladdress_latlng_precision.py` — 2 AlterField sur PostalAddress (latitude, longitude) de DecimalField(18,16) à DecimalField(9,6). Compatible avec les données existantes (précision tronquée si > 6 décimales, aucune perte de range).
- `MetaBillet/migrations/0016_add_wc_language.py` — AddField `language` CharField(max_length=10, blank=True, default="") sur WaitingConfiguration.
- Commande : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`

### Pièges documentés / Pitfalls documented

Voir `tests/PIEGES.md` section "Onboarding wizard (session 2026-05-17)" :
- DecimalField lat/lng : max_digits - decimal_places ≥ 3 obligatoire
- Polling HTMX : ne JAMAIS doubler `hx-trigger="every Xs"` sur parent + child
- `login()` peut perdre les clés de session avec `SESSION_SAVE_EVERY_REQUEST=True`
- `cron_morning` create_waiting_tenant fragile : `raise` global peut laisser le pool dans un état hybride
- gettext dans tasks Celery sans LocaleMiddleware → fallback `LANGUAGE_CODE`
- `wc.create_tenant()` ne transfère PAS automatiquement long_description, logo, ni first_name/last_name

---

## Widget de saisie d'adresse géolocalisée / Geolocated address input widget

**Date :** 2026-05-15
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**Quoi / What:** nouveau widget Django+Leaflet+leaflet-geosearch réutilisable
pour saisir une adresse (search live, marqueur draggable, géocodage inverse).
Refonte de la step 03_place du wizard onboard pour l'utiliser.
**Architecture full client** : recherche live ET reverse geocode appellent
Nominatim direct depuis le navigateur (pas de proxy serveur).

**Pourquoi / Why:** UX précédente (saisie en 4 champs séparés + géocodage HTMX
au change) trop friction. Pattern GPS standard (suggestions live + drag) plus
intuitif et réutilisable dans d'autres formulaires (Event admin, etc.).

**Décision architecturale 2026-05-15** : la spec initiale proposait une approche
"Hybride" (search client + reverse via endpoint serveur `/widgets/geocode-reverse/`
avec cache Redis). Bascule en **full client** après découverte d'un problème
multi-tenant routing : la route `BaseBillet/urls.py` n'est inclus que dans
`urls_tenants.py`, pas dans `urls_public.py` → 404 sur ROOT (où tourne le
wizard onboard). Plutôt que dupliquer l'URL dans 2 fichiers, on a supprimé
l'endpoint serveur et on appelle Nominatim direct (CORS open, déjà fait par
leaflet-geosearch pour le forward). Trade-off : pas de cache mutualisé, mais
acceptable pour notre volume.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `templates/widgets/widget_carte_adresse.html` | NOUVEAU — widget réutilisable |
| `static/widgets/widget_carte_adresse.js` | NOUVEAU — init IIFE multi-widget, fetch Nominatim direct |
| `static/widgets/widget_carte_adresse.css` | NOUVEAU — surcharges palette TiBillet |
| `BaseBillet/form_fields.py` | NOUVEAU — `AdresseGeolocaliseeField` helper (validation serveur) |
| `TiBillet/settings.py` | + `BASE_DIR / "templates"` dans TEMPLATES dirs, + `BASE_DIR / "static"` dans STATICFILES_DIRS |
| `onboard/templates/onboard/steps/03_place.html` | utilise le widget |
| `onboard/serializers.py` | `OnboardPlaceSerializer` : nouveaux champs `place_*` |
| `onboard/views.py` | mapping persistance + suppression action `geocode` |
| `onboard/urls.py` | suppression route geocode |
| `onboard/templates/onboard/partials/map_widget.html` | SUPPRIMÉ |
| `onboard/templates/onboard/partials/geocode_result.html` | SUPPRIMÉ |
| `tests/pytest/test_widget_form_field_geo.py` | NOUVEAU (6 tests `AdresseGeolocaliseeField`) |
| `onboard/tests/test_step_place.py` | adapté + suppression test endpoint geocode |

### Migration
- **Migration nécessaire / Migration required:** Non
- Pas de modification de schéma DB.

### Breaking changes
- Endpoint `POST /onboard/geocode/` supprimé. Aucun consommateur externe (uniquement utilisé en interne par l'ex-step 03_place).

## Chantier landing #04 — Filtre "lieu vivant" + UX "Voir tous" → explorer

**Date :** 2026-05-14
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** Le cache SEO listait tous les tenants ayant un domaine, sans
verifier s'il y avait quelque chose a voir/acheter chez eux. En prod
avec 375 tenants, le marquee, `/lieux/`, la carte explorer et le
sitemap pointaient vers des dizaines de pages quasi-vides — bruit UX
et crawl budget gaspille pour Google + bots LLM.

1. **Filtre "lieu vivant"** sur `AGGREGATE_LIEUX` et `SITEMAP_INDEX` :
   un tenant n'apparait que s'il a un domaine ET (au moins 1 event
   futur publie OU au moins 1 produit BILLET/FREERES/ADHESION publie).
   Implementation : `seo/services.py::get_active_tenants_with_counts()`
   ramene `event_count` + `product_count` par tenant en 1 seule requete
   SQL (UNION ALL avec sous-selects scalaires). `seo/tasks.py` applique
   le filtre `lieu_est_vivant` avant de remplir `lieux` et
   `sitemap_tenants`. `TENANT_SUMMARY` / `TENANT_EVENTS` (caches
   per-tenant) restent inchanges.
2. **Chiffres cles supprimes** : "X lieux", "Y events" sur la landing
   — vanity metrics SaaS qui jurent avec le ton commun cooperatif. Bloc
   `stats-row` retire du template. `GLOBAL_COUNTS` n'est plus genere
   (suppression de `get_global_event_count()` dans `seo/services.py` et
   du bloc de generation dans `tasks.py`). Constante
   `SEOCache.GLOBAL_COUNTS` laissee dans `choices` pour eviter une
   migration de schema sur du code mort.
3. **UX "Voir tous"** : les 2 boutons sous les marquees pointent
   maintenant vers `/explorer/` (carte + filtres, vue interactive)
   plutot que `/lieux/` et `/evenements/`. Ces deux pages restent
   indexables pour le SEO/ranking mais ne sont plus mises en avant
   dans la navigation humaine.

**EN :** SEO cache listed every tenant with a domain, no check if there
was anything to see/buy there. In prod with 375 tenants, the marquee,
`/lieux/`, the explorer map and the sitemap pointed to dozens of
near-empty pages — UX noise and wasted crawl budget for Google + LLM
bots. Added an "alive venue" filter, removed vanity counters on the
landing, redirected "See all" buttons to `/explorer/` for humans.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `seo/services.py` | `get_active_tenants_with_event_count()` → `get_active_tenants_with_counts()` (+ `product_count`). `get_global_event_count()` supprime. Constante `CATEGORIES_PRODUIT_LIEU_VIVANT = ("B","F","A")`. |
| `seo/tasks.py` | Filtre `lieu_est_vivant` sur `aggregate_lieux` + `sitemap_tenants`. Suppression du bloc `GLOBAL_COUNTS`. Log final reflete `lieux_vivants` au lieu de `lieux totaux`. |
| `seo/views.py` | `landing()` : suppression de `lieux_count`, `events_count`, lecture `GLOBAL_COUNTS`. |
| `seo/templates/seo/landing.html` | Bloc `stats-row` retire. 2 boutons "Voir tous" → `/explorer/`. |

### Migration / Migration
- **Migration necessaire / Migration required :** Non.
- Anciennes entrees `SEOCache(cache_type='global_counts')` deviennent du
  data mort, ignorees a la lecture. Nettoyage automatique au prochain
  refresh ? Non — la step 6 ne supprime que les entrees rattachees a un
  tenant disparu, pas les entrees globales obsoletes. Pas grave : 1 ligne.

## Chantier landing #03 — Marquee scalable + textes V2 + icone cashless + flush cache

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

## Chantier SEO #02 — Review critique + 10 fixes prod / Critical review + 10 prod fixes

**Date :** 2026-05-13
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** Review critique de la session SEO/FEDERATION par un agent + navigation
Chrome MCP. Score initial 79/100, 10 fixes appliques pour atteindre la qualite
prod :

1. **Critical XSS JSON-LD** : helper `json_for_html()` qui translate `<>&` en
   sequences unicode `< > &`. Empeche qu'un admin tenant qui met
   `</script>` dans son nom de configuration casse le HTML des pages de ses
   voisins (qui consomment le SEOCache).
2. **`<h1>` ajoutes** sur `/federation/` tenant et `/explorer/` public (etaient
   absents, 21+ H3 seulement). Visually-hidden, n'affecte pas l'UI.
3. **Open Graph + Twitter tags** : override `og_title`, `twitter_title`,
   `og_description`, `twitter_description` sur le wrapper `/federation/`
   (etaient au fallback "Accueil | <tenant>").
4. **`SECURE_PROXY_SSL_HEADER`** dans settings.py : canonical URLs et JSON-LD
   contiennent maintenant `https://` (etaient en `http://` car Traefik forwarde
   en HTTP au container Django).
5. **N+1 cache landing** : `event_count` lu directement de `AGGREGATE_LIEUX`
   au lieu de 20 appels `get_seo_cache(TENANT_SUMMARY, ...)`.
6. **`_('Local network')`** : navbar label maintenant traduisible (etait
   hardcode).
7. **XML escape sitemap_index** : `xml.sax.saxutils.escape` sur les URLs et
   timestamps (defense en profondeur).
8. **BreadcrumbList shape** : `"item": {"@id": ..., "name": ...}` (forme
   recommandee Google Rich Results, au lieu du string brut qui passe les tests
   mais genere des warnings).
9. **`config.organisation or tenant.name`** : fallback si organisation vide.
10. **`CSS.escape()`** : remplace l'echappement regex maison dans explorer.js,
    avec fallback pour vieux navigateurs.

**EN :** Critical review of the SEO/FEDERATION session by an agent + Chrome MCP
navigation. Initial score 79/100, 10 fixes applied to reach prod quality:

1. **Critical XSS JSON-LD**: `json_for_html()` helper translating `<>&` to
   `< > &` unicode sequences. Prevents a tenant admin who puts
   `</script>` in their configuration name from breaking the HTML of neighbor
   pages (which consume SEOCache).
2. **`<h1>` added** on tenant `/federation/` and public `/explorer/` (were
   missing, 21+ H3 only). Visually-hidden, doesn't affect UI.
3. **Open Graph + Twitter tags**: override `og_title`, `twitter_title`,
   `og_description`, `twitter_description` on the `/federation/` wrapper
   (defaulted to "Accueil | <tenant>").
4. **`SECURE_PROXY_SSL_HEADER`** in settings.py: canonical URLs and JSON-LD
   now contain `https://` (were `http://` because Traefik forwards HTTP to
   the Django container).
5. **N+1 cache landing**: `event_count` read directly from `AGGREGATE_LIEUX`
   instead of 20 `get_seo_cache(TENANT_SUMMARY, ...)` calls.
6. **`_('Local network')`**: navbar label now translatable (was hardcoded).
7. **XML escape sitemap_index**: `xml.sax.saxutils.escape` on URLs and
   timestamps (defense in depth).
8. **BreadcrumbList shape**: `"item": {"@id": ..., "name": ...}` (Google Rich
   Results recommended shape, instead of raw string that passes tests but
   generates warnings).
9. **`config.organisation or tenant.name`**: fallback when organisation empty.
10. **`CSS.escape()`**: replaces homemade regex escaping in explorer.js, with
    fallback for legacy browsers.

**Validation** : tous les fixes verifies via curl + Chrome MCP. Helper
`json_for_html()` teste avec input malicieux (`Foo</script><script>alert(1)`)
→ tous les caracteres dangereux echappes.

---

## Chantier SEO #01 — Decouverte LLM/Google du reseau federe / LLM and Google discovery of the federated network

**Date :** 2026-05-13
**Migration :** Oui (`seo/0002_alter_seocache_cache_type.py`)
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** Trois axes pour rendre le reseau TiBillet visible aux LLMs (GPTBot,
ClaudeBot, PerplexityBot, CommonCrawl) et a Google.

1. **Voisins bidirectionnels** : la carte d'un tenant affiche les voisins
   declarations dans les 2 sens. Si X federate avec moi mais que je n'ai pas
   declare X dans mes `FederatedPlace`, X apparait quand meme. Pre-calcul
   cross-schema dans le Celery task `refresh_seo_cache`, stockage en
   `SEOCache.FEDERATION_INCOMING`. La navbar "Reseau local" est desormais
   pilotee uniquement par `config.module_federation`.

2. **JSON-LD federation** : nouvelle helper
   `seo.views_common.build_json_ld_federation()` qui produit un schema.org/
   Organization + `subOrganization` + `memberOf`. Injecte sur `/federation/`
   tenant (racine = tenant, subOrg = voisins federes, memberOf = reseau
   TiBillet) et sur `/explorer/` public (racine = TiBillet, subOrg = tous les
   tenants). Les crawlers no-JS recoivent immediatement la structure du
   reseau sans avoir besoin d'executer Leaflet. Fix collateral : `meta_robots`
   devient un `{% block %}` dans `seo/base.html`.

3. **Quick wins SEO** :
   - `/humans.txt` sur le ROOT public (manquait avant)
   - `/federation/` ajoute au `StaticViewSitemap` tenant
   - Helper `build_json_ld_breadcrumb()` + BreadcrumbList sur `/federation/`

**EN :** Three axes to make the TiBillet network visible to LLMs (GPTBot,
ClaudeBot, PerplexityBot, CommonCrawl) and Google.

1. **Bidirectional neighbors**: a tenant's map shows neighbors declared in
   both directions. If X federates with me but I haven't declared X in my
   `FederatedPlace`, X still appears. Cross-schema pre-computation in the
   `refresh_seo_cache` Celery task, stored in `SEOCache.FEDERATION_INCOMING`.
   The "Local network" navbar is now driven solely by `config.module_federation`.

2. **Federation JSON-LD**: new helper
   `seo.views_common.build_json_ld_federation()` produces a schema.org/
   Organization + `subOrganization` + `memberOf`. Injected on `/federation/`
   tenant (root = tenant, subOrg = federated neighbors, memberOf = TiBillet
   network) and on `/explorer/` public (root = TiBillet, subOrg = all
   tenants). No-JS crawlers immediately receive the network structure without
   executing Leaflet. Collateral fix: `meta_robots` becomes a `{% block %}`
   in `seo/base.html`.

3. **SEO quick wins**:
   - `/humans.txt` on public ROOT (was missing)
   - `/federation/` added to tenant `StaticViewSitemap`
   - `build_json_ld_breadcrumb()` helper + BreadcrumbList on `/federation/`

**Fichiers :** voir `TECH DOC/SESSIONS/FEDERATION/03-explorer-federation-CHANGELOG.md`

---

## Chantier FEDERATION #01 — Explorer in-tenant + refactor JS prod / In-tenant explorer + production-grade JS refactor

**Date :** 2026-05-13
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** `/federation/` (Réseau local) sur chaque tenant rend maintenant l'explorer
(carte Leaflet + filtres) avec uniquement le tenant courant + ses FederatedPlace.
Le code de la carte est consolidé en source unique dans `seo/` (JS + CSS + widget
HTML + data builder), partagé avec le public `/explorer/`. Le JS a été refactoré
pour la prod : IIFE encapsulé (zéro pollution `window`), event delegation (zéro
`onclick=` inline), i18n via `data-i18n-*`, garde-fous défensifs (try/catch JSON,
DOM presence), Leaflet vendoré (plus de CDN externe unpkg.com), event Leaflet
`animationend` au lieu de `setTimeout(...,400)`. Marker visuel "Vous êtes ici"
pour le tenant courant.

**EN :** `/federation/` (Local network) on each tenant now renders the explorer
(Leaflet map + filters) limited to the current tenant + its FederatedPlace.
Map code is consolidated as a single source under `seo/` (JS + CSS + widget HTML +
data builder), shared with the public `/explorer/`. The JS has been refactored
for production: encapsulated IIFE (zero `window` pollution), event delegation
(zero inline `onclick=`), i18n via `data-i18n-*`, defensive guards (try/catch
JSON, DOM presence), vendored Leaflet (no external unpkg.com CDN), Leaflet
`animationend` event instead of `setTimeout(...,400)`. Visual "You are here"
marker for the current tenant.

**Fichiers :** voir `TECH DOC/SESSIONS/FEDERATION/03-explorer-federation-CHANGELOG.md`

---

## Chantier M-To-V2 #02 — Port app `seo/` allegee (landing ROOT lieux + events) / Port lightweight `seo/` app

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

## v1.8 — Modules Groupware + refacto admin + proxies Product / Groupware modules + admin refactor + Product proxies

**Date :** 2026-05-13
**Migration :** Oui (`0204_configuration_module_adhesion_and_more`, `0205_futproduct_membershipproduct_posproduct_and_more`)
**Contributeurs / Contributors :** NothRen (Antoine), JonasFW13 (Jonas)

---

### Vue d'ensemble / Overview

**FR :**
Premiere etape d'integration de la V2 (mono-repo TiBillet/Lespass + LaBoutik + Fedow)
dans la V1 actuelle. On introduit la notion de **Groupware** (activation modulaire par
tenant) et on prepare l'admin pour accueillir les nouveaux types de produits (POS, fut)
sans casser la compatibilite. Refacto majeur de `admin_tenant.py` (~1000 lignes
deplacees) en modules separes. Ajout de proxy models pour separer les vues admin par
type de produit. Fix bug timezone sur les filtres datetime de l'admin (#384).

**EN :**
First step of integrating the V2 mono-repo (TiBillet/Lespass + LaBoutik + Fedow)
into the current V1. Introduces the **Groupware** concept (per-tenant modular activation)
and prepares admin for upcoming product types (POS, keg) without breaking compatibility.
Major refactor of `admin_tenant.py` (~1000 lines moved) into separate modules. Adds proxy
models to split admin views by product type. Fixes timezone bug on admin datetime filters (#384).

---

### 1. Modules Groupware : activation par tenant / Groupware modules: per-tenant activation

**FR :**
Ajout de **9 booleens** `module_*` sur `Configuration` pour activer/desactiver des
sections fonctionnelles par tenant. Les modules deja en production sont actives par
defaut (`module_billetterie`, `module_adhesion`, `module_crowdfunding`,
`module_federation`). Les modules V2 a venir sont desactives par defaut
(`module_monnaie_locale`, `module_caisse`, `module_inventaire`, `module_tireuse`,
`module_booking`).

**Dashboard admin** : nouvelles cartes avec switches HTMX et modal de confirmation.
Apres bascule, `HX-Refresh` recharge la page pour mettre a jour la sidebar.
**Sidebar dynamique** : `get_sidebar_navigation(request)` (callable string) construit
la navigation selon les modules actifs.
**NavBar publique** : les liens `/memberships/`, `/event/`, `/federation/`, `/contrib/`
n'apparaissent dans la barre publique que si le module correspondant est actif (cf.
`BaseBillet/views.py:get_context()`).

**Dependance** : `module_caisse` necessite `module_monnaie_locale`. Validation cote
serveur dans `module_toggle()` qui renvoie un message d'erreur via `django.messages` si
on tente de violer cette regle.

**EN :**
Adds **9 module_* booleans** on `Configuration` to enable/disable functional sections
per tenant. Currently-live modules default to True; upcoming V2 modules default to False.
Admin dashboard gets module cards with HTMX switches and a confirmation modal.
Sidebar is now dynamic (`get_sidebar_navigation` callable). Public navbar links only
show if the matching module is active. `module_caisse` requires `module_monnaie_locale`.

---

### 2. Refacto `admin_tenant.py` : split en modules / `admin_tenant.py` refactor: split into modules

**FR :**
`Administration/admin_tenant.py` faisait ~3000 lignes. On extrait :

- `Administration/admin/site.py` — `StaffAdminSite` + `sanitize_textfields` (utilitaire XSS).
- `Administration/admin/dashboard.py` — `get_sidebar_navigation`, `dashboard_callback`,
  `MODULE_FIELDS`, `_build_modules_context`, `adhesion_badge_callback`, `environment_callback`.
- `Administration/admin/products.py` — `ProductAdmin`, `TicketProductAdmin`,
  `MembershipProductAdmin`, inlines `BasePriceInline`/`TicketPriceInline`/`MembershipPriceInline`,
  `ProductFormFieldInline`, palettes/icones POS (commente, pour V2), validation.
- `Administration/admin/prices.py` — `PriceAdmin`, `PromotionalCodeAdmin`, `PriceChangeForm`.

`admin_tenant.py` re-exporte les noms publics (`get_sidebar_navigation`, etc.) via
`from Administration.admin.dashboard import ...` pour ne rien casser cote `settings.py`
qui pointe encore sur `Administration.admin_tenant.get_sidebar_navigation`.

**EN :**
Splits the ~3000-line `admin_tenant.py` into 4 modules under `Administration/admin/`.
Public names re-exported from the original module to keep `settings.py` references valid.

---

### 3. Proxy models Product : 4 vues admin filtrees / Product proxy models: 4 filtered admin views

**FR :**
Sans toucher a la table `BaseBillet_product`, on cree **4 proxy models** :
- `TicketProduct` — filtre `categorie_article IN ('B', 'F')` (Billet, FreeRes).
- `MembershipProduct` — filtre `categorie_article = 'A'` (Adhesion).
- `POSProduct` — filtre `methode_caisse IS NOT NULL` (V2, admin commente).
- `FutProduct` — filtre `categorie_article = 'U'` (V2, admin commente).

Chaque proxy a son propre `ModelAdmin` avec un formulaire restreint et un `get_queryset`
filtre. La sidebar affiche separement "Ticket products" (section Billetterie) et
"Membership products" (section Adhesions). Le `ProductAdmin` original reste enregistre
pour preserver les autocomplete `EventAdmin` et les URLs existantes.

`MembershipProductAdmin` recupere `ProductFormFieldInline` (formulaires dynamiques pour
adhesions). `TicketProductAdmin` ne l'a pas (champs dynamiques inutiles pour la billetterie).

**EN :**
Adds 4 proxy models filtered by product type. Each has its own admin with a restricted
form and filtered queryset. Original `ProductAdmin` is kept to preserve existing URLs
and autocomplete behavior in `EventAdmin`.

---

### 4. Champs conditionnels dans les inlines / Conditional fields in inlines

**FR :**
Unfold supporte `conditional_fields` au niveau ModelAdmin mais **pas** au niveau inline.
Pour le besoin "afficher `iteration` seulement si `recurring_payment` coche" sur l'inline
`MembershipPriceInline`, on ajoute un systeme generique :

- Chaque `Inline` declare un dict `inline_conditional_fields = {"champ": "expression"}`.
- `MembershipProductAdmin.changeform_view()` collecte ces dicts et les injecte en JSON
  via `extra_context["inline_conditional_rules"]`.
- Template `admin/product/inline_conditional_fields.html` rend le JSON dans
  `<script id="inline-conditional-rules" type="application/json">`.
- JS `Administration/static/admin/js/inline_conditional_fields.js` lit le JSON, ecoute
  les `change`/`input` sur les sources, applique cascade (source cachee = condition fausse),
  anime apparition/disparition, observe les nouvelles lignes inline (MutationObserver).

Expressions supportees : `champ == true`, `champ == false`, `champ > N`.

**EN :**
Generic conditional-field system for Django admin inlines (Unfold doesn't support
`conditional_fields` on inlines). Each inline declares `inline_conditional_fields`,
the changeform view collects them and injects JSON, JS reads the JSON, listens on
sources, handles cascade, animates show/hide, observes new inline rows.

---

### 5. Fix bug timezone sur les filtres datetime admin (#384) / Fix timezone bug on admin datetime filters (#384)

**FR :**
`RangeDateTimeFilter` (Unfold) parsait les bornes saisies dans le filtre admin sans
tenir compte de la timezone du tenant, ce qui entrainait des decalages d'une heure sur
les filtrages d'historique. Nouveau filtre `RangeDateTimeFilterWithTimeZone` qui :

1. Recupere la timezone du tenant via `Configuration.get_solo().get_tzinfo()`.
2. Localise les `datetime` parses avec `new_timezone.localize(...)` avant le filtrage.
3. Retourne `None` proprement en cas d'erreur de parsing.

Applique sur `LigneArticleAdmin` et `LigneArticlePosAdmin`.

**EN :**
Fixes one-hour offset in admin datetime range filters by localizing parsed datetimes
with the tenant's timezone (`Configuration.get_solo().get_tzinfo()`).

---

### 6. Fix divers / Miscellaneous fixes

**FR :**
- **Subscription duration** (commit 32e035e2, NothRen) : interdit la creation d'un
  `Price` avec `recurring_payment=True` mais `subscription_type=NA`. Validation cote
  serveur dans `MembershipPriceInlineForm.clean_subscription_type()`.
- **`SyntaxWarning: "is" with a literal`** (commit 5ddeb7ca, JonasFW13) : remplace
  `field_name is "module_caisse"` par `field_name == "module_caisse"` dans
  `module_toggle()`. Le `is` ne doit pas etre utilise pour comparer des strings.
- **`poids` → "Display order"** (commit 0cce7f1b, NothRen) : renomme le `verbose_name`
  pour clarifier le sens metier ("ordre d'affichage", plus petit = en premier). La colonne
  DB reste `poids`.
- **Doc technique V1-to-V2 + Stripe Checkout fix** (commit 1a3f2c0f, JonasFW13) :
  ajout de `TECH DOC/SESSIONS/M-To-V2/INDEX.md` et
  `Administration/Unfold_docs/stripe-checkout-account-business-name.md`.

**EN :**
- Subscription duration validation: `recurring_payment=True` requires `subscription_type != NA`.
- Replaces `is` with `==` for string comparison (PEP 8).
- Renames `poids` verbose_name to "Display order" for clarity.
- Adds technical migration docs.

---

### 7. NavBar publique conditionnelle / Conditional public navbar

**FR :**
Dans `BaseBillet/views.py:get_context()`, les liens publics `/memberships/`, `/event/`,
`/federation/` et `/contrib/` n'apparaissent dans `main_nav` que si le module correspondant
est actif. Avant : ces liens etaient toujours visibles, meme si la fonctionnalite etait
desactivee (404 a la cle).

**EN :**
Public navbar links are now conditional on the matching module flag.

---

### 8. `DATETIME_INPUT_FORMATS` ajoute aux settings / `DATETIME_INPUT_FORMATS` added to settings

**FR :**
Ajout de plusieurs formats de saisie datetime (FR `dd/mm/yyyy hh:mm`, ISO
`yyyy-mm-dd hh:mm:ss`, etc.) pour que les formulaires admin acceptent les variantes
courantes lors du parsing manuel des dates.

**EN :**
Adds several datetime input formats (FR and ISO variants) for admin form parsing.

---

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | +9 champs `module_*` sur `Configuration`, +4 proxy models (`TicketProduct`, `MembershipProduct`, `POSProduct`, `FutProduct`), +`RECHARGE_CASHLESS_FED` et `FUT` dans `CATEGORIE_ARTICLE_CHOICES`, renommage `poids` verbose_name |
| `BaseBillet/migrations/0204_configuration_module_adhesion_and_more.py` | Migration des 9 booleens `module_*` |
| `BaseBillet/migrations/0205_futproduct_membershipproduct_posproduct_and_more.py` | Migration des 4 proxy models |
| `BaseBillet/views.py` | NavBar publique conditionnelle aux modules dans `get_context()` |
| `Administration/admin_tenant.py` | Refacto majeur (~1000 lignes deplacees), re-export des symboles publics, ajout `module_toggle_modal` / `module_toggle`, dependance `module_caisse` ↔ `module_monnaie_locale`, nouveau `RangeDateTimeFilterWithTimeZone` |
| `Administration/admin/__init__.py` | Nouveau (package) |
| `Administration/admin/site.py` | Nouveau : `StaffAdminSite`, `sanitize_textfields` |
| `Administration/admin/dashboard.py` | Nouveau : `get_sidebar_navigation` (sidebar dynamique), `dashboard_callback`, `MODULE_FIELDS`, `_build_modules_context` |
| `Administration/admin/products.py` | Nouveau : `ProductAdmin` + proxy admins `TicketProductAdmin` / `MembershipProductAdmin`, inlines `BasePriceInline`/`TicketPriceInline`/`MembershipPriceInline`, `ProductFormFieldInline`, code POS commente pour V2 |
| `Administration/admin/prices.py` | Nouveau : `PriceAdmin`, `PromotionalCodeAdmin`, `PriceChangeForm` |
| `Administration/templates/admin/index.html` | `+include "admin/dashboard.html"` (cartes modules) |
| `Administration/templates/admin/dashboard.html` | Nouveau : grille de cartes modules avec switches HTMX |
| `Administration/templates/admin/dashboard_module_modal.html` | Nouveau : modal de confirmation pour bascule module |
| `Administration/templates/admin/product/inline_conditional_fields.html` | Nouveau : injection JSON des regles conditionnelles |
| `Administration/static/admin/js/inline_conditional_fields.js` | Nouveau : 400 lignes JS, gestion cascade + animation + MutationObserver |
| `Administration/static/admin/css/price_inline.css` | Nouveau : style des titres `StackedInline` (scope `#prices-group`) |
| `TiBillet/settings.py` | `SIDEBAR.navigation` → callable string, ancien dump renomme `SIDEBAR-TEMP-OLD` (a supprimer plus tard), `+DATETIME_INPUT_FORMATS` |
| `PaiementStripe/views.py` | Branche `elif 'account or business name'` (fix v1.7.18, deja documente) |
| `VERSION` | `VERSION=1.8`, `MIGRATE=1` |
| `locale/fr/LC_MESSAGES/django.{po,mo}` | +1500 lignes (modules, proxies, validations) |
| `locale/en/LC_MESSAGES/django.{po,mo}` | +1500 lignes |
| `TECH DOC/SESSIONS/M-To-V2/INDEX.md` | Nouveau : doc technique V1-to-V2 |
| `Administration/Unfold_docs/stripe-checkout-account-business-name.md` | Nouveau : explication + fix Stripe Checkout |

### Migration
- **Migration necessaire / Migration required:** Oui — `MIGRATE=1` dans `VERSION`.
- Commande : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`
- Les nouveaux booleens ont des `default` : aucun risque sur les tenants existants. Les
  modules deja en production (`billetterie`, `adhesion`, `crowdfunding`, `federation`)
  sont actives par defaut.

### Compatibilite / Compatibility
- **Coexistence V1/V2** : carte "Caisse V2" du dashboard est grisee si `server_cashless`
  est configure (= ancien tenant en V1). Les modules V2 (`monnaie_locale`, `caisse`,
  `inventaire`, `tireuse`, `booking`) restent desactives.
- **`SIDEBAR-TEMP-OLD`** dans `settings.py` : ancien dump conserve commente pour reference,
  a supprimer apres une periode de stabilisation.
- **Code POS/Fut/Categorie** dans `Administration/admin/products.py` : commente bloc par
  bloc (`FROM V2 : TODO`), reactive quand on integre l'app `laboutik` et `inventaire`.

### i18n
- ~1500 lignes ajoutees/modifiees dans `locale/{fr,en}/LC_MESSAGES/django.po`.
- `compilemessages` deja execute (les `.mo` sont a jour dans le commit).

---

## v1.7.18 — Fix 500 sur compte Stripe Connect sans nom commercial / Fix 500 on Stripe Connect account missing business name

**Date :** 2026-05-12
**Migration :** Non

---

### Gestion gracieuse de `account or business name` (Stripe Checkout) / Graceful handling of `account or business name` (Stripe Checkout)

**FR :**
Quand un tenant tente de creer une session Stripe Checkout (adhesion, reservation) alors
que son compte Stripe Connect n'a pas de nom commercial configure, Stripe leve
`InvalidRequestError: In order to use Checkout, you must set an account or business name`.

Avant : l'erreur tombait dans le fallback `else` de `_checkout_session()` qui retentait
betement avec `force=True` sur les line_items (corrige rien) → l'exception bubblait jusqu'a
la vue → **500** pour l'utilisateur final.

Apres : le cas est detecte explicitement, on logge le `schema_name` du tenant concerne pour
que l'admin sache ou intervenir, et on leve `serializers.ValidationError` avec un message
generique. Le `MembershipMVT.create()` (et autres ViewSets qui consomment `is_valid()` sans
`raise_exception=True`) recoit l'erreur dans `.errors`, l'affiche via `django.messages`, et
redirige proprement vers le `Referer`.

**EN :**
When a tenant tries to create a Stripe Checkout session while its Connect account is
missing a business name, Stripe raises `InvalidRequestError`. The error used to fall into
the `else` fallback that retried with `force=True` on line_items — useless, since the
issue is on the account side. Now caught explicitly: we log the tenant schema_name and
raise a user-friendly `ValidationError`. No more 500, the user sees a clear message.

### Decision : pas de patch preventif cote Lespass / Decision: no preventive patch on Lespass side

**FR :**
On a envisage de pre-remplir `business_profile.name` dans
`Configuration.get_stripe_connect_account()` (BaseBillet/models.py) pour que les nouveaux
tenants n'aient jamais l'erreur. **Decision finale : non.** Le bug racine est gere
**cote Stripe** (le gerant doit completer son `business_profile.name` lors du onboarding,
le dashboard Stripe le demande explicitement). Cote Lespass, on se contente donc de :

1. Faire remonter l'erreur a l'utilisateur final via `serializers.ValidationError`
   (message generique).
2. Logger en `ERROR` avec le `schema_name` du tenant pour que Sentry remonte l'incident
   et que l'admin sache ou intervenir.

`Configuration.get_stripe_connect_account()` reste donc inchange : il cree le compte avec
seulement `type="standard"` et `country="FR"`. C'est volontaire.

**Tenants existants deja sans nom commercial :** ils doivent fixer manuellement via
dashboard Stripe ou `stripe accounts update <acct_id> -d "business_profile[name]=..."`.

**EN :**
We considered pre-filling `business_profile.name` in
`Configuration.get_stripe_connect_account()` so that new tenants would never hit the error.
**Final decision: no.** The root cause is handled on the Stripe side (tenant admins now
explicitly fill `business_profile.name` during Connect onboarding). On Lespass we just
surface the error to the user and log it in Sentry.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `PaiementStripe/views.py` | Nouveau branch `elif 'account or business name'` dans `CreationPaiementStripe._checkout_session()` (avant le fallback retry). Loggue l'erreur avec le `schema_name` du tenant (visible dans Sentry), leve `ValidationError` avec un message generique. |

### Migration
- **Migration necessaire / Migration required:** Non

### i18n
Une nouvelle chaine traduisible ajoutee :
- `"Online payment is temporarily unavailable. Please contact the site administrator."`

A executer : `makemessages -l fr -l en` puis `compilemessages`.

---

## v1.7.17 — Améliorations SEO home Faire Festival + humans.txt / SEO improvements on Faire Festival home + humans.txt

**Date :** 2026-05-05
**Migration :** Non

---

### Améliorations SEO sur la home du skin Faire Festival / SEO improvements on Faire Festival skin home

**FR :**
Suite à l'audit RoastMyUrl sur `fairefestival.fr` (score 69/100), correction des points SEO
sur la home du skin Faire Festival :

- **Title trop court (24 char)** : enrichi en `Festival du Faire — Toulouse, 28-30 mai 2026 | <organisation>` (61 char). Inclut désormais les mots-clés métier (`Festival`, `Faire`), géo (`Toulouse`) et la date.
- **Meta description courte (113 char)** : étendue à 158 char avec `fablabs`, `22 thématiques`, et la date.
- **og:title / twitter:title** : alignés sur le nouveau title.
- **og:description / twitter:description** : alignées sur la meta description longue.
- **Bug HTML** : 3 balises `<h3>` étaient fermées par `</h4>` (typo lors du merge `template-faire-festival`). Corrigées en `</h3>`.
- **Hiérarchie H2** : la baseline `Le grand rendez-vous toulousain...` était dans un `<p>`. Passée en `<h2>` (classes Bootstrap conservées, rendu visuel identique). On passe de 1 H2 à 2 H2.
- **Alts d'images génériques** (`Billets`, `Programmation`, `Faire Festival`) : enrichis pour le SEO et l'accessibilité (`Prendre vos billets pour le Faire Festival`, `Programmation du Faire Festival : 22 thématiques`, `Infos pratiques du Faire Festival, 28-30 mai`).

**EN :**
Following the RoastMyUrl audit on `fairefestival.fr` (score 69/100), SEO fixes on the Faire
Festival skin home:

- Title extended from 24 to 61 char with geo + date keywords.
- Meta description extended to 158 char with metier keywords.
- og/twitter title and description aligned.
- Fixed 3 `<h3>` tags closed with `</h4>` (typo from the merge).
- Tagline `<p>` upgraded to `<h2>` for proper heading hierarchy.
- Generic image alts replaced with descriptive ones.

### Ajout de humans.txt dynamique / Dynamic humans.txt added

**FR :**
Ajout d'un endpoint `/humans.txt` dynamique au standard [humanstxt.org](https://humanstxt.org/Standard.html).
Crédite la Coopérative Code Commun comme équipe de développement. Le contenu est identique
pour tous les tenants (même réponse quel que soit le `Host`). La version et la date du
dernier bump sont lues depuis le fichier `VERSION` à la racine.

**EN :**
Added a dynamic `/humans.txt` endpoint following the [humanstxt.org standard](https://humanstxt.org/Standard.html).
Credits Coopérative Code Commun as the dev team. Same content for all tenants. Version
and last update date read from the root `VERSION` file.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/templates/faire_festival/views/home.html` | Title / og / twitter enrichis ; meta description étendue ; fix `<h3>...</h4>` ×3 ; baseline `<p>` → `<h2>` ; alts d'images enrichis |
| `BaseBillet/views_humans.py` | **Nouveau** — vue `humans_txt`, parse le fichier `VERSION` (version + mtime) au chargement du module |
| `BaseBillet/urls.py` | Import `humans_txt` + route `path('humans.txt', humans_txt, name='humans_txt')` |

### Migration
- **Migration necessaire / Migration required:** Non

### À faire en config admin / Admin config TODO (no code)
Pour activer pleinement le SEO en prod sur `fairefestival.fr` :
- Uploader la social card sur `Configuration > img` (1200×630 → génère `og:image`)
- Renseigner `Configuration > facebook` / `instagram` / `twitter` (alimente `JSON-LD sameAs`)
- Compléter `Configuration > postal_address` (alimente `JSON-LD address`)

### À faire i18n / i18n TODO
Les nouvelles chaînes (`Festival du Faire — Toulouse, 28-30 mai 2026`, meta description longue,
3 alts enrichis) sont en `{% translate %}` mais pas encore dans les `.po`. À traiter dans
une session de traduction dédiée (`makemessages` + `compilemessages`).

---

## Unreleased — Fix message trompeur sur reservation gratuite anonyme / Misleading message on anonymous free booking

**Date :** 2026-04-21
**Migration :** Non

---

### Correction de la page de confirmation de reservation gratuite / Free booking confirmation page fix

**FR :**
Lorsqu'un visiteur non connecte reservait une activite gratuite avec l'email d'un compte
deja existant et actif, la page de confirmation affichait « Veuillez valider votre e-mail »
alors que les billets etaient deja envoyes (resa en `FREERES_USERACTIV`) et que la
reservation etait confirmee en back-office.

Cause : la vue `EventViewset.reservation` passait `request.user` au template. Quand le
visiteur n'est pas connecte, `request.user` vaut `AnonymousUser` dont `is_active` est
toujours `False`. Le template basculait alors sur la branche « validez votre email »
en ignorant l'etat reel de l'user retrouve en base par email.

Fix : passer `validator.reservation.user_commande` au template. Cet user est celui
resolu par `get_or_create_user(email)` dans le validator, donc coherent avec la
decision prise par `TicketCreator.method_F` pour envoyer (ou non) les billets
immediatement.

**EN :**
When an unauthenticated visitor booked a free activity using the email of an
already-existing active account, the confirmation page showed "Please validate your
e-mail" even though the tickets were already sent and the booking was confirmed.

Root cause: the view passed `request.user` (an `AnonymousUser` with `is_active=False`)
to the template. Fix: pass `validator.reservation.user_commande` instead — the user
resolved by the validator from the submitted email.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `EventViewset.reservation` : passe `validator.reservation.user_commande` au template au lieu de `request.user` |

### Migration
- **Migration necessaire / Migration required:** Non

---

## v1.7.7 — Unification actions admin Membership dans MembershipMVT

**Date :** Mars 2026
**Migration :** Non

---

### Unification des actions admin sur les adhésions / Membership admin actions unified

**FR :**
Les actions admin sur les adhésions sont désormais centralisées dans `MembershipMVT` (viewset DRF),
exposées via HTMX dans un panneau inline affiché avant le formulaire admin.

- **Supprimé** : `actions_detail` / `actions_row` Unfold dans `MembershipAdmin` (5 méthodes `@action`)
- **Supprimé** : `has_custom_actions_row_permission`, `has_custom_actions_detail_permission`
- **Supprimé** : templates orphelins `cancel_confirm.html` et `ajouter_paiement.html`
- **Ajouté** : `change_form_before_template = "admin/membership/actions_panel.html"` sur `MembershipAdmin`
- **Ajouté** : 3 nouvelles actions dans `MembershipMVT` : `send_invoice`, `ajouter_paiement`, `cancel`
- **Ajouté** : `PaiementHorsLigneSerializer` dans `BaseBillet/validators.py`
- **Ajouté** : 4 nouveaux partials HTMX dans `admin/membership/partials/`

**EN :**
Admin actions on memberships are now centralised in `MembershipMVT` (DRF viewset),
exposed via HTMX in an inline panel displayed before the admin change form.

**Fichiers modifiés :**
- `BaseBillet/validators.py` : + `PaiementHorsLigneSerializer`
- `BaseBillet/views.py` : + imports `get_or_create_price_sold`, `dec_to_int`, `reverse`, `PaiementHorsLigneSerializer` + 3 actions + update `get_permissions`
- `Administration/admin_tenant.py` : - 5 `@action` Unfold + enrichissement `changeform_view` + `change_form_before_template`
- `Administration/templates/admin/membership/actions_panel.html` : Nouveau — panneau HTMX
- `Administration/templates/admin/membership/partials/send_invoice_success.html` : Nouveau
- `Administration/templates/admin/membership/partials/cancel_form.html` : Nouveau
- `Administration/templates/admin/membership/partials/ajouter_paiement_form.html` : Nouveau
- `Administration/templates/admin/membership/partials/ajouter_paiement_success.html` : Nouveau

---

## v1.7.6 — Skin Faire Festival + Corrections UX et Sentry

**Date :** Mars 2026
**Migration :** Non

---

### 1. Skin Faire Festival — ameliorations CSS et templates / Faire Festival skin — CSS and template improvements

**FR :**
Ameliorations du skin "Faire Festival" suite aux retours terrain :
- Bordures arrondies (`border-radius`) sur les cartes et le bouton burger mobile
- Titres des evenements en police mono, taille reduite, avec `hyphens: auto`
- Bordure image evenement epaissie (1px → 3px)
- Badge de date repositionne (`margin-left: 0` au lieu de -100px)
- Padding horizontal des cartes ajuste

**EN:**
Improvements to the "Faire Festival" skin based on field feedback:
- Rounded borders (`border-radius`) on cards and mobile burger button
- Event titles in mono font, smaller size, with `hyphens: auto`
- Event image border thickened (1px → 3px)
- Date badge repositioned (`margin-left: 0` instead of -100px)
- Card horizontal padding adjusted

**Fichiers / Files:**
- `BaseBillet/static/faire_festival/css/faire_festival.css`

---

### 2. Lazy-load video sur la page d'accueil / Video lazy-load on homepage

**FR :**
La video motion-table de la page d'accueil bloquait le chargement sur Firefox mobile.
Remplacement de `autoplay` + `src` par un mecanisme `IntersectionObserver` :
la video n'est telechargee et lue que lorsqu'elle entre dans le viewport.
`preload="none"` empeche tout telechargement au chargement initial de la page.

**EN:**
The motion-table video on the homepage was blocking page load on Firefox mobile.
Replaced `autoplay` + `src` with an `IntersectionObserver` mechanism:
the video is only downloaded and played when it enters the viewport.
`preload="none"` prevents any download on initial page load.

**Fichiers / Files:**
- `BaseBillet/templates/faire_festival/views/home.html`

---

### 3. Description adhesion en accordeon intelligent / Smart collapsible membership description

**FR :**
La description longue de la page d'adhesion est desormais tronquee automatiquement
si elle depasse ~10-12 lignes (250px). Un bouton "Lire la suite" / "Reduire" apparait.
Si la description est courte, elle s'affiche en entier sans bouton.

**EN:**
The long description on the membership page is now automatically truncated
if it exceeds ~10-12 lines (250px). A "Read more" / "Show less" button appears.
If the description is short, it displays fully without a button.

**Fichiers / Files:**
- `BaseBillet/templates/faire_festival/views/membership/list.html`

---

### 4. Filtre par date sur la page evenements / Date filter on events page

**FR :**
Le dropdown "Trier par date" etait present dans le template mais non branche cote back.
Le parametre `?date=` est maintenant lu par la vue `list()`, et le dict `dated_events`
est filtre pour n'afficher que les evenements de la date selectionnee.
Le dropdown conserve toutes les dates disponibles meme quand un filtre est actif.
Le bouton affiche la date selectionnee en format lisible ("lundi 15 mars").

**EN:**
The "Sort by date" dropdown was present in the template but not wired to the backend.
The `?date=` parameter is now read by the `list()` view, and the `dated_events` dict
is filtered to display only events for the selected date.
The dropdown keeps all available dates even when a filter is active.
The button shows the selected date in readable format ("Monday March 15").

**Fichiers / Files:**
- `BaseBillet/views.py` — `EventMVT.list()` : lecture param `date`, filtrage du dict
- `BaseBillet/templates/faire_festival/views/event/list.html` — affichage date active, format ISO dans les liens

---

### 5. Correction erreur Sentry : confirmation email reservation expiree / Fix Sentry error: expired reservation email confirmation

**FR :**
Quand un utilisateur confirmait son email plus de 15 minutes apres une reservation gratuite
et que l'evenement etait presque complet, le signal levait un `ValueError` qui remontait
en `Http404` generique. L'utilisateur voyait une page 404 sans explication.
Desormais le `ValueError` est intercepte dans `emailconfirmation()` et le message
est affiche a l'utilisateur via `django.messages` sur la page d'accueil.
Les messages d'erreur sont maintenant traduits via `_()`.

**EN:**
When a user confirmed their email more than 15 minutes after a free reservation
and the event was nearly full, the signal raised a `ValueError` that surfaced
as a generic `Http404`. The user saw a 404 page with no explanation.
Now the `ValueError` is caught in `emailconfirmation()` and the message
is displayed to the user via `django.messages` on the homepage.
Error messages are now translated via `_()`.

**Fichiers / Files:**
- `BaseBillet/views.py` — `emailconfirmation()` : catch `ValueError` separement
- `BaseBillet/signals.py` — `activator_free_reservation()` : messages avec `_()`

---

### 6. Section produits retiree de la page evenement / Products section removed from event detail page

**FR :**
La section "Tickets and prices" a ete retiree de la page detail evenement du skin Faire Festival.
Le label "Intervenant-e-s" en dur a egalement ete supprime.

**EN:**
The "Tickets and prices" section was removed from the event detail page of the Faire Festival skin.
The hardcoded "Intervenant-e-s" label was also removed.

**Fichiers / Files:**
- `BaseBillet/templates/faire_festival/views/event/retrieve.html`

---

### 7. Correction calcul paiement adhesion sans contribution / Fix membership payment calculation without contribution

**FR :**
Correction d'un crash quand `contribution_value` etait absente lors du calcul
du montant de paiement d'une adhesion. La valeur manquante est maintenant traitee gracieusement.

**EN:**
Fixed a crash when `contribution_value` was missing during membership payment amount calculation.
The missing value is now handled gracefully.

**Fichiers / Files:**
- Commit `50132e35`

---

### Autres ameliorations / Other improvements

- **Admin breadcrumb** : affiche le nom du produit au lieu du nom du tarif dans le fil d'Ariane
- **Admin product archive filter** : filtre pour afficher/masquer les produits archives
- **Redirect tarif → produit** : retour automatique vers le produit parent apres sauvegarde d'un tarif
- **Widget adhesions obligatoires** : passage en `MultipleHiddenInput`
- **Integration Fedow** : gestion d'erreur non-bloquante lors de la creation d'assets et validation d'adhesion
- **Newsletter** : ajout de l'URL newsletter dans le skin
- **Traductions** : nouvelles chaines FR/EN pour les filtres, messages d'erreur, et boutons

**Migration necessaire / Migration required:** Non

---

## v1.7.2 — Corrections production + Paiement admin adhesions + Avoir comptable

**Date :** Mars 2026
**Migration :** Oui (`migrate_schemas --executor=multiprocessing`)

---

### 0. Protection doublon paiement adhesion (SEPA) / Duplicate membership payment protection (SEPA)

**FR :**
Quand un utilisateur cliquait plusieurs fois sur le lien de paiement d'adhesion
(recu par email apres validation admin), un nouveau checkout Stripe etait cree a chaque clic.
Cela pouvait entrainer des **doubles prelevements SEPA** (signaie en production).

La vue `get_checkout_for_membership` verifie maintenant si un paiement Stripe existe deja :
- **Session Stripe encore ouverte** : reutilise l'URL existante (pas de doublon).
- **Session "complete" (SEPA en cours)** : affiche une page d'information expliquant
  que le prelevement est en cours de traitement (jusqu'a 14 jours).
- **Session expiree** : cree un nouveau checkout normalement.

**EN:**
When a user clicked multiple times on the membership payment link
(received by email after admin validation), a new Stripe checkout was created each time.
This could cause **duplicate SEPA debits** (reported in production).

The `get_checkout_for_membership` view now checks for an existing Stripe payment:
- **Stripe session still open**: reuses the existing URL (no duplicate).
- **Session "complete" (SEPA pending)**: displays an info page explaining
  the debit is being processed (up to 14 days).
- **Session expired**: creates a new checkout normally.

**Fichiers / Files:**
- `BaseBillet/views.py` — protection doublon dans `get_checkout_for_membership`
- `BaseBillet/templates/reunion/views/membership/payment_already_pending.html` — nouveau template

**Migration necessaire / Migration required:** Non

---

### 1. Avoir comptable (credit note) sur les ventes / Credit note on sales

**FR :**
Les admins peuvent emettre un **avoir** sur une ligne de vente depuis l'admin (bouton "Avoir" dans la liste des ventes).
Un avoir cree une ligne miroir avec quantite negative pour annuler comptablement la vente,
sans supprimer l'ecriture originale (conformite fiscale francaise).
Gardes : uniquement sur lignes confirmees ou payees, et un seul avoir par ligne.
L'avoir est envoye a LaBoutik si un serveur cashless est configure.
L'export CSV inclut une colonne "Ref. avoir" pour la tracabilite.

**EN:**
Admins can issue a **credit note** on a sale line from the admin (row action button in the sales list).
A credit note creates a mirror line with negative quantity to cancel the sale for accounting purposes,
without deleting the original entry (French fiscal compliance).
Guards: only on confirmed or paid lines, and only one credit note per line.
The credit note is sent to LaBoutik if a cashless server is configured.
CSV export includes a "Credit note ref." column for traceability.

**Fichiers / Files:**
- `BaseBillet/models.py` — status `CREDIT_NOTE`, FK `credit_note_for`
- `BaseBillet/signals.py` — transition CREATED → CREDIT_NOTE
- `Administration/admin_tenant.py` — `LigneArticleAdmin.emettre_avoir()`
- `Administration/importers/lignearticle_exporter.py` — colonne export
- `BaseBillet/migrations/0199_credit_note_lignearticle.py`

**Annulation adhesion avec avoir :**
L'action "Annuler" sur une adhesion affiche desormais une page de confirmation.
Si l'adhesion a des lignes de vente payees, l'admin peut choisir "Annuler et creer un avoir".
Les avoirs sont crees pour chaque ligne VALID/PAID liee a l'adhesion.

**Fichiers / Files:**
- `Administration/admin_tenant.py` — `MembershipAdmin.cancel()` (GET/POST avec confirmation)
- `Administration/templates/admin/membership/cancel_confirm.html` (nouveau)

---

### 2. Correction annulation reservation admin (cheque, especes) / Fix admin reservation cancellation (non-Stripe)

**FR :**
Quand un admin annulait une reservation creee manuellement (payee par cheque, especes, etc.),
aucune ligne de remboursement ou d'avoir n'etait creee. La reservation passait en "annulee"
sans trace comptable, car `cancel_and_refund_resa` ne cherchait les LigneArticle que via
les `Paiement_stripe` (FK), et les reservations admin n'en ont pas.
Desormais, lors de l'annulation, un avoir (CREDIT_NOTE) est automatiquement cree pour chaque
LigneArticle hors-Stripe (sale_origin=ADMIN) liee a la reservation.
Meme correction pour l'annulation de ticket individuel (`cancel_and_refund_ticket`).

**EN:**
When an admin cancelled a manually created reservation (paid by check, cash, etc.),
no refund or credit note line was created. The reservation was marked as cancelled
with no accounting trace, because `cancel_and_refund_resa` only looked for LigneArticle
via `Paiement_stripe` (FK), and admin reservations don't have one.
Now, upon cancellation, a credit note (CREDIT_NOTE) is automatically created for each
non-Stripe LigneArticle (sale_origin=ADMIN) linked to the reservation.
Same fix for single ticket cancellation (`cancel_and_refund_ticket`).

**Fichiers / Files:**
- `BaseBillet/models.py` — `Reservation._lignes_hors_stripe()`, `Reservation._creer_avoir()`,
  `cancel_and_refund_resa()`, `cancel_and_refund_ticket()`

---

### 3. FK reservation sur LigneArticle / Reservation FK on LigneArticle

**FR :**
Ajout d'une FK directe `LigneArticle.reservation` pour lier une ligne comptable a sa reservation
sans dependre de `Paiement_stripe` comme intermediaire.
Avant, les reservations admin (cheque, especes) n'avaient aucun lien vers leurs LigneArticle.
La FK est renseignee dans les 4 flows de creation (front, API v1, API v2, admin).
Une data migration backfill les lignes existantes depuis `paiement_stripe.reservation`.
Les methodes `articles_paid()` et `_lignes_hors_stripe()` utilisent la FK directe
avec fallback sur l'ancien chemin pour compatibilite.

**EN:**
Added a direct FK `LigneArticle.reservation` to link an accounting line to its reservation
without relying on `Paiement_stripe` as intermediary.
Previously, admin reservations (check, cash) had no link to their LigneArticle.
The FK is set in all 4 creation flows (front, API v1, API v2, admin).
A data migration backfills existing lines from `paiement_stripe.reservation`.
`articles_paid()` and `_lignes_hors_stripe()` use the direct FK with legacy fallback.

**Fichiers / Files:**
- `BaseBillet/models.py` — FK `reservation` + simplification `articles_paid()`, `_lignes_hors_stripe()`
- `BaseBillet/validators.py` — `reservation=reservation` (front)
- `ApiBillet/serializers.py` — `reservation=reservation` (API v1)
- `api_v2/serializers.py` — `reservation=reservation` (API v2)
- `Administration/admin_tenant.py` — `reservation=reservation` (admin)
- `BaseBillet/migrations/0200_add_reservation_fk_to_lignearticle.py`
- `BaseBillet/migrations/0201_backfill_lignearticle_reservation.py`

---

### 4. Correction niveau de log API Brevo / Fix Brevo API log level

**FR :**
Quand un admin testait sa cle API Brevo depuis la configuration et que la cle etait invalide,
l'erreur 401 remontait en `logger.error` dans Sentry, polluant les alertes.
C'est une erreur de configuration utilisateur, pas un bug applicatif.
Le niveau de log est passe a `logger.warning`.

**EN:**
When an admin tested their Brevo API key from the configuration and the key was invalid,
the 401 error was logged as `logger.error` in Sentry, polluting alerts.
This is a user configuration error, not an application bug.
Log level changed to `logger.warning`.

**Fichiers / Files:** `Administration/admin_tenant.py` — `BrevoConfigAdmin.test_api_brevo()`

---

### 5. Correction deconnexion automatique apres 3 mois / Fix automatic logout after 3 months

**FR :**
Les utilisateurs etaient deconnectes apres exactement 3 mois, meme s'ils utilisaient le site quotidiennement.
Cause : `SESSION_SAVE_EVERY_REQUEST` n'etait pas defini (defaut Django = `False`),
donc le cookie de session n'etait renouvele que lors de modifications de la session, pas a chaque visite.
Ajout de `SESSION_SAVE_EVERY_REQUEST = True` pour que chaque visite renouvelle le cookie.

**EN:**
Users were logged out after exactly 3 months, even when using the site daily.
Cause: `SESSION_SAVE_EVERY_REQUEST` was not set (Django default = `False`),
so the session cookie was only renewed when the session was modified, not on every visit.
Added `SESSION_SAVE_EVERY_REQUEST = True` so every visit renews the cookie.

**Fichiers / Files:** `TiBillet/settings.py`

---

### 6. Bouton "Ajouter un paiement" sur les adhesions en attente / "Add payment" button on pending memberships

**FR :**
Les admins de lieux recoivent des adhesions remplies en ligne mais payees sur place
(especes, cheque, virement). Ces adhesions restaient bloquees en "attente de paiement"
sans moyen de les valider depuis l'admin.
Nouveau bouton "Ajouter un paiement" sur la page detail d'une adhesion en attente (WP ou AW).
Le formulaire demande le montant et le moyen de paiement, puis declenche toute la chaine :
creation de la ligne de vente, calcul de la deadline, envoi de l'email de confirmation,
transaction Fedow, et notification LaBoutik.

**EN:**
Venue admins receive memberships filled out online but paid on-site
(cash, check, bank transfer). These memberships were stuck in "waiting for payment"
with no way to validate them from the admin.
New "Add payment" button on the detail page of a pending membership (WP or AW).
The form asks for the amount and payment method, then triggers the full chain:
sale line creation, deadline calculation, confirmation email,
Fedow transaction, and LaBoutik notification.

**Fichiers / Files:**
- `Administration/admin_tenant.py` — `MembershipAdmin.ajouter_paiement()`
- `Administration/templates/admin/membership/ajouter_paiement.html` (nouveau / new)

---

## v1.6.8 — Corrections Sentry + Import/Export Events

**Date :** Fevrier 2026
**Migration :** Non

---

### 1. Correction boucle infinie sur ProductFormField.save() / Fix infinite loop on ProductFormField.save()

**FR :**
Quand le label d'un champ de formulaire dynamique generait un slug de 64 caracteres ou plus,
la generation de nom unique entrait dans une boucle infinie (le suffixe etait tronque puis identique a chaque tour).
Le serveur finissait par un `SystemExit`.
On utilise maintenant un fragment d'UUID pour garantir l'unicite en un seul essai.

**EN:**
When a dynamic form field label produced a slug of 64+ characters,
the unique name generation entered an infinite loop (the suffix was truncated to the same value each iteration).
The server ended up with a `SystemExit`.
We now use a UUID fragment to guarantee uniqueness in a single attempt.

**Fichiers / Files:** `BaseBillet/models.py` — `ProductFormField.save()`

---

### 2. Correction timeout cashless / Fix cashless ReadTimeout

**FR :**
L'appel HTTP vers le serveur cashless avait un timeout de 1 seconde, trop court en production.
Passe a 10 secondes.

**EN:**
The HTTP call to the cashless server had a 1-second timeout, too short for production.
Increased to 10 seconds.

**Fichiers / Files:** `BaseBillet/tasks.py`

---

### 3. Correction creation de tenant en doublon / Fix duplicate tenant creation

**FR :**
Quand un utilisateur cliquait deux fois sur le lien de confirmation email,
la creation du tenant pouvait echouer car le lien `WaitingConfiguration → tenant` n'etait pas assigne assez tot.
On assigne maintenant le tenant des sa creation, et on ajoute un fallback qui repare le lien si le tenant existe deja.

**EN:**
When a user clicked the email confirmation link twice,
tenant creation could fail because the `WaitingConfiguration → tenant` link was not assigned early enough.
We now assign the tenant immediately after creation, and added a fallback that repairs the link if the tenant already exists.

**Fichiers / Files:** `BaseBillet/validators.py`, `BaseBillet/views.py`

---

### 4. Correction carte perdue 404 / Fix lost_my_card 404

**FR :**
Quand un utilisateur cliquait deux fois sur "carte perdue", le deuxieme appel a Fedow renvoyait un 404
car la carte etait deja detachee. On attrape maintenant cette erreur proprement.

**EN:**
When a user double-clicked "lost my card", the second call to Fedow returned a 404
because the card was already detached. We now catch this error gracefully.

**Fichiers / Files:** `BaseBillet/views.py` — `admin_lost_my_card`, `lost_my_card`

---

### 5. Correction formulaire adhesion admin sans wallet / Fix admin membership form without wallet

**FR :**
Dans l'admin, le formulaire d'adhesion plantait si on validait le numero de carte
sans avoir d'abord renseigne un email valide (attribut `user_wallet_serialized` absent).
On verifie maintenant que le wallet existe avant d'y acceder.

**EN:**
In the admin, the membership form crashed when validating the card number
without first providing a valid email (missing `user_wallet_serialized` attribute).
We now check the wallet exists before accessing it.

**Fichiers / Files:** `Administration/admin_tenant.py` — `MembershipForm.clean_card_number()`

---

### 6. Verification SEPA Stripe avant activation / Stripe SEPA capability check before activation

**FR :**
Activer le paiement SEPA dans la configuration alors que le compte Stripe Connect n'a pas la capacite SEPA
provoquait une erreur au moment du paiement. On verifie maintenant la capacite SEPA via l'API Stripe
au moment de la sauvegarde de la configuration. Si le checkout echoue malgre tout, le SEPA est desactive automatiquement.

**EN:**
Enabling SEPA payment in the configuration while the Stripe Connect account lacked SEPA capability
caused an error at checkout time. We now verify SEPA capability via the Stripe API
when saving the configuration. If checkout still fails, SEPA is automatically disabled.

**Fichiers / Files:** `BaseBillet/models.py` — `Configuration.check_stripe_sepa_capability()`, `PaiementStripe/views.py`

---

### 7. Tri des produits par poids / Product weight ordering

**FR :**
Les prix affiches sur la page evenement ignoraient le poids (`poids`) du produit parent.
Les produits sont maintenant tries par `product__poids`, puis `order`, puis `prix`.

**EN:**
Prices displayed on the event page ignored the parent product's weight (`poids`).
Products are now sorted by `product__poids`, then `order`, then `prix`.

**Fichiers / Files:** `BaseBillet/views.py`

---

### 8. Import/Export CSV des evenements (PR #351) / CSV import/export for events (PR #351)

**FR :**
Contribution de @AoiShidaStr : ajout de l'import/export CSV des evenements depuis l'admin Django.
Ameliore ensuite avec : export de l'adresse postale par nom (pas par ID),
lignes identiques ignorees a l'import, et rapport des lignes ignorees.

**EN:**
Contribution by @AoiShidaStr: added CSV import/export for events from the Django admin.
Then improved with: postal address exported by name (not ID),
unchanged rows skipped on import, and skipped rows reported.

**Fichiers / Files:** `Administration/admin_tenant.py` — `EventResource`

---

*Lespass est un logiciel libre sous licence AGPLv3, developpe par la Cooperative Code Commun.*
*Lespass is free software under AGPLv3 license, developed by Cooperative Code Commun.*

---

## v1.6.4 — Migration requise

**Date :** Fevrier 2025
**Migration :** Oui (`migrate_schemas --executor=multiprocessing`)

---

### 1. Moteur de skin configurable / Configurable skin engine

**FR :**
Nous pouvons maintenant choisir son theme graphique depuis l'administration.
Un nouveau champ `skin` a ete ajoute au modele `Configuration`.
Le systeme cherche d'abord le template dans le dossier du skin choisi,
puis retombe automatiquement sur le theme par defaut (`reunion`) si le template n'existe pas.
Cela permet de creer un nouveau skin en ne surchargeant que les templates souhaités.

**EN:**
Each venue can now choose its visual theme from the admin panel.
A new `skin` field has been added to the `Configuration` model.
The system first looks for the template in the chosen skin folder,
then automatically falls back to the default theme (`reunion`) if the template does not exist.
This allows creating a new skin by only overriding the desired templates.

**Details techniques / Technical details:**

- Nouveau champ `Configuration.skin` (CharField, defaut `"reunion"`)
  New field `Configuration.skin` (CharField, default `"reunion"`)
- Nouvelle fonction `get_skin_template(config, path)` avec logique de fallback
  New function `get_skin_template(config, path)` with fallback logic
- Ajout du skin `faire_festival` (theme brutaliste) avec templates et CSS dedies
  Added `faire_festival` skin (brutalist theme) with dedicated templates and CSS
- Migration : `BaseBillet/migrations/0195_configuration_skin.py`

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — resolution dynamique des templates
- `BaseBillet/models.py` — champ `skin` sur `Configuration`
- `BaseBillet/templates/faire_festival/` — nouveau dossier skin complet
- `BaseBillet/static/faire_festival/css/` — styles dedies
- `Administration/admin_tenant.py` — champ expose dans l'admin

---

### 2. Pre-remplissage des formulaires d'adhesion / Membership form pre-fill

**FR :**
Quand un utilisateur connecte remplit un formulaire d'adhesion,
le systeme recherche sa derniere adhesion au meme produit.
Si une adhesion precedente existe, tous les champs du formulaire dynamique
sont pre-remplis avec les valeurs deja saisies.
L'utilisateur n'a plus a re-saisir son adresse, telephone, etc. a chaque renouvellement.

**EN:**
When a logged-in user fills out a membership form,
the system looks up their most recent membership for the same product.
If a previous membership exists, all dynamic form fields
are pre-filled with the previously entered values.
The user no longer has to re-enter their address, phone, etc. on each renewal.

**Details techniques / Technical details:**

- Recherche de la derniere `Membership` du user pour le meme produit avec `custom_form` non vide
  Lookup of the user's latest `Membership` for the same product with non-empty `custom_form`
- Construction d'un dict `prefill` qui mappe `field.name` vers la valeur stockee
  Builds a `prefill` dict mapping `field.name` to the stored value
- Tous les types de champs supportes : texte, textarea, select, radio, checkbox, multi-select
  All field types supported: text, textarea, select, radio, checkbox, multi-select
- Nouveau filtre de template `get_item` pour acceder aux cles d'un dict dans le template
  New `get_item` template filter for dict key lookup in templates

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — logique de pre-remplissage dans `MembershipMVT.retrieve()`
- `BaseBillet/templates/reunion/views/membership/form.html` — affichage des valeurs pre-remplies
- `BaseBillet/templatetags/tibitags.py` — filtre `get_item`

---

### 3. Edition des formulaires dynamiques depuis l'admin / Admin custom form field editing

**FR :**
Les administrateurs peuvent maintenant modifier les reponses d'un formulaire dynamique
directement depuis la fiche adhesion dans l'admin, sans passer par le shell ou la base de donnees.
Ils peuvent aussi ajouter des champs libres (non definis dans le produit).
Tout se fait en HTMX, sans rechargement de page.

**EN:**
Admins can now edit dynamic form responses
directly from the membership detail page in the admin panel, without using the shell or database.
They can also add free-form fields (not defined in the product).
Everything works via HTMX, without page reload.

**Details techniques / Technical details:**

- 5 nouvelles actions HTMX sur `MembershipMVT` :
  5 new HTMX actions on `MembershipMVT`:
  - `admin_edit_json_form` (GET) — affiche le formulaire editable / shows editable form
  - `admin_cancel_edit` (GET) — annule l'edition / cancels editing
  - `admin_change_json_form` (POST) — valide et sauvegarde / validates and saves
  - `admin_add_custom_field_form` (GET) — formulaire d'ajout de champ / add field form
  - `admin_add_custom_field` (POST) — sauvegarde le nouveau champ / saves new field
- Validation des champs requis, anti-doublon sur les labels, sanitisation HTML via `nh3`
  Required field validation, duplicate label check, HTML sanitization via `nh3`
- Chaque type de champ (`ProductFormField`) est rendu avec le bon widget HTML
  Each field type (`ProductFormField`) is rendered with the appropriate HTML widget
- Support des champs "orphelins" (presents dans le JSON mais pas dans le produit)
  Support for "orphan" fields (present in JSON but not defined in the product)
- Protection par `TenantAdminPermission`

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — actions HTMX
- `Administration/utils.py` — fonction `clean_text()` (sanitisation `nh3`)
- `Administration/templates/admin/membership/custom_form.html` — vue lecture avec boutons
- `Administration/templates/admin/membership/partials/custom_form_edit.html` — formulaire editable
- `Administration/templates/admin/membership/partials/custom_form_edit_success.html` — confirmation
- `Administration/templates/admin/membership/partials/custom_form_add_field.html` — ajout de champ
- `BaseBillet/models.py` — correction de `ProductFormField.save()` (ne pas ecraser `name`)
- `BaseBillet/validators.py` — recherche de cle robuste avec fallback UUID/label

---

### Autres ameliorations / Other improvements

- **Duplication de produit** : nouvelle action admin pour dupliquer un produit existant
  New admin action to duplicate an existing product
- **Validation anti-doublon d'evenement** : empeche la creation d'evenements avec le meme nom et la meme date
  Prevents creating events with same name and date
- **Accessibilite** : ameliorations `aria-label`, `visually-hidden`, meilleur support des themes clair/sombre
  Accessibility improvements: `aria-label`, `visually-hidden`, better light/dark theme support
- **Tests E2E** : nouveau test Playwright pour le cycle complet d'edition des formulaires dynamiques
  New Playwright test for the full dynamic form editing cycle

---

*Lespass est un logiciel libre sous licence AGPLv3, developpe par la Cooperative Code Commun.*
*Lespass is free software under AGPLv3 license, developed by Cooperative Code Commun.*
