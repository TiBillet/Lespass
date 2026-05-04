# SPEC — Visualisation tirelire V2 (lecture fedow_core local)

**Date :** 2026-04-20
**Statut :** Design validé après brainstorm du 2026-04-20, prêt pour writing-plans
**Scope :** Affichage des tokens d'un user sur `/my_account/balance/` pour les tenants V2.
Lit directement `fedow_core.Token` (DB locale) au lieu d'appeler `FedowAPI` (serveur Fedow distant).
Les tenants V1 legacy (LaBoutik externe) et les users à wallet legacy conservent leur flow V1 inchangé.

---

## 1. Contexte et problème

### Situation actuelle (Session 31 terminée)

La Session 31 a livré le flow complet de **recharge FED V2** (fedow_core local) :

- Tenant dédié `federation_fed` + asset FED unique via `bootstrap_fed_asset`
- `RefillService.process_cashless_refill()` crée `Transaction(action=REFILL)` et crédite un `fedow_core.Token`
- UI V2 avec formulaire `refill_form_v2.html`, dispatch via `peut_recharger_v2(user)` (4 verdicts)
- Pattern webhook+retour user convergent avec `select_for_update`
- 45 tests pytest verts, non-régression totale V1

**Ce qui manque** : l'utilisateur qui vient de recharger en V2 ne **voit pas** ses tokens sur la page `/my_account/balance/`. La vue `MyAccount.tokens_table` (`BaseBillet/views.py:1023`) utilise exclusivement `FedowAPI()` (remote) :

```python
def tokens_table(self, request):
    config = Configuration.get_solo()
    fedowAPI = FedowAPI()
    wallet = fedowAPI.wallet.cached_retrieve_by_signature(request.user).validated_data
    tokens = [token for token in wallet.get('tokens') if ...]
    # ... appel FedowAPI uniquement
```

Les `fedow_core.Token` locaux (créés par `RefillService`) **ne sont pas lus**. Résultat : liste vide ou incohérente pour un user V2.

### Décision stratégique

Symétrique à la décision Session 31 : **dispatch V1/V2 dans la vue**, via le helper existant `peut_recharger_v2(user)`. Le verdict `"v2"` lit `fedow_core.Token` local. Les 3 autres verdicts (`"feature_desactivee"`, `"v1_legacy"`, `"wallet_legacy"`) conservent le flow `FedowAPI()` distant.

**Coexistence V1/V2 (stricte, par verdict) :**

| Verdict | Flow de lecture |
|---|---|
| `"v2"` | `fedow_core.Token` (DB locale, cette spec) |
| `"v1_legacy"` | `FedowAPI()` distant (inchangé) |
| `"wallet_legacy"` | `FedowAPI()` distant (wallet user créé sur un tenant V1, tokens en base distante) |
| `"feature_desactivee"` | `FedowAPI()` distant (par cohérence avec le dispatch refill) |

Un user avec `"wallet_legacy"` **n'a pas** encore de tokens en V2 local — ses tokens sont sur Fedow distant. On le laisse lire là-bas tant que la migration wallet n'est pas faite (out of scope Session 32).

---

## 2. Décisions architecturales validées

| Décision | Valeur | Raison |
|---|---|---|
| **Dispatch** | Seul verdict `"v2"` lit `fedow_core.Token` | Symétrie avec Session 31, zéro régression V1 |
| **Template V2 séparé** | `reunion/partials/account/token_table_v2.html` (nouveau) | V1 `token_table.html` intact, évite spaghetti conditionnel |
| **Méthode vue** | `MyAccount._tokens_table_v2(request)` privée, dispatch inline dans `tokens_table` | Cohérence avec V1 qui fait tout dans la vue |
| **Query optimisée** | Query custom dans la vue avec `prefetch_related('asset__federations__tenants')` + `select_related('asset__tenant_origin')` | Zéro N+1 sur pastilles lieux. Pas de nouvelle méthode service (le POS n'a pas besoin des federations) |
| **Label FED** | Override template : `category == 'FED'` → `"TiBillets"` (pas `asset.name = "Euro fédéré TiBillet"`) | Cohérence marque V1/V2 |
| **Rendu pastilles FED** | Badge unique `"Utilisable partout"` — **pas de liste** | 300+ lieux en prod → illisible + coûteux à construire |
| **Rendu pastilles TLF/TNF/TIM/FID** | Liste des lieux fédérés (nom + logo thumbnail) | Signal essentiel "où ma carte fonctionne" |
| **Structure template** | 2 sous-tableaux : "Monnaies" (FED/TLF/TNF) + "Temps & fidélité" (TIM/FID) | Sépare fiduciaire (€) des compteurs (heures/points). Mention explicite "non convertible en euros" pour TIM/FID |
| **Colonnes** | Solde \| Lieux utilisables | Pas de "dernière transaction" (historique complet déjà disponible via bouton `transactions_table`) |
| **Cas "aucun token"** | Message + icône + lien ancre `#tirelire-section` vers bouton Recharger existant | Pas de bouton dupliqué, guide l'utilisateur vers l'action |
| **Valeur = 0** | Tokens affichés | Signal "tu as utilisé cette monnaie par le passé", cohérent avec V1 |
| **Cache lieux** | Clé globale `"tenant_info_v2"`, TTL 3600s, construit en itérant `Client.objects.filter(categorie=SALLE_SPECTACLE)` | Pattern strictement équivalent à `get_place_cached_info` V1. **Exception volontaire** à la règle djc "cache keys with tenant.pk" (cache cross-tenant voulu) — documentée en commentaire |
| **Helpers** | Fonctions module-level dans `BaseBillet/views.py` : `_lieux_utilisables_pour_asset(asset)` + `_get_tenant_info_cached(tenant_pk)` | FALC, testable isolément, pas de pollution ViewSet |
| **Structure données transmise au template** | Liste de dicts explicite `[{"value_euros", "asset_name_affichage", "category", "category_display", "lieux_utilisables"}, ...]` | Pas de mutation d'attribut sur ORM (`token.lieux_utilisables = ...`), explicite |
| **Conversion centimes → euros** | Côté vue (dict `value_euros = token.value / 100`) | Pas de nouveau filtre template. Simple, local |
| **Accessibility** | `aria-live="polite"` sur conteneur tokens, `aria-hidden="true"` sur icônes, `alt` sur logos | Corrige un manque de V1, djc compliance |
| **Workflow djc obligatoire** | CHANGELOG.md + `makemessages`/`compilemessages` + fichier `A TESTER et DOCUMENTER/visu-tirelire-v2.md` | Conformité stack djc |

---

## 3. Architecture

### 3.1 Dispatch dans `MyAccount.tokens_table`

```
                   GET /my_account/tokens_table/
                              │
                              ▼
                   MyAccount.tokens_table(request)
                              │
                  ┌───────────┴───────────┐
                  │ peut_recharger_v2(user)│
                  └───────────┬───────────┘
                              │
       ┌──────────────────────┼──────────────────────────┐
       │                      │                          │
       ▼                      ▼                          ▼
   "v1_legacy"           "wallet_legacy"               "v2"
   "feature_desactivee"                                  │
       │                      │                          │
       ▼                      ▼                          ▼
   Code V1 actuel       Code V1 actuel         _tokens_table_v2(request)
   (FedowAPI distant)   (FedowAPI distant)              │
       │                      │                          ▼
       ▼                      ▼                 Query Token + prefetch
   token_table.html      token_table.html                │
                                                         ▼
                                              _lieux_utilisables_pour_asset
                                                         │
                                                         ▼
                                              _get_tenant_info_cached (x N tenants)
                                                         │
                                                         ▼
                                              token_table_v2.html
```

### 3.2 Vue Python (squelette)

```python
@action(detail=False, methods=['GET'])
def tokens_table(self, request):
    """
    Affichage des tokens du user connecte pour la page /my_account/balance/.
    / Tokens display for the connected user on the balance page.

    LOCALISATION : BaseBillet/views.py

    Dispatch V1/V2 selon peut_recharger_v2(user) :
    - Verdict "v2" -> lecture locale fedow_core.Token (cette session)
    - Autres verdicts -> flow V1 FedowAPI (inchange depuis Session 31)
    / V1/V2 dispatch based on peut_recharger_v2(user).
    """
    user = request.user
    verdict_ok, verdict = peut_recharger_v2(user)

    # --- Branche V2 : lecture locale fedow_core ---
    # / V2 branch: local fedow_core read
    if verdict == "v2":
        return self._tokens_table_v2(request)

    # --- Autres verdicts : code V1 existant inchange ---
    # / Other verdicts: existing V1 code unchanged
    config = Configuration.get_solo()
    fedowAPI = FedowAPI()
    # ... (code V1 actuel, copie telle quelle de BaseBillet/views.py:1024)
```

```python
def _tokens_table_v2(self, request):
    """
    Branche V2 de tokens_table : lit fedow_core.Token en base locale.
    / V2 branch of tokens_table: reads fedow_core.Token from local DB.

    LOCALISATION : BaseBillet/views.py

    Construit deux sous-listes (fiduciaires + compteurs) et delegue
    le rendu au partial token_table_v2.html.
    / Builds two sub-lists (fiduciary + counters) and delegates rendering.
    """
    user = request.user
    config = Configuration.get_solo()

    # Garde : wallet absent -> message "aucun token"
    # / Guard: no wallet -> "no token" message
    if user.wallet is None:
        return render(
            request,
            "reunion/partials/account/token_table_v2.html",
            {
                "config": config,
                "tokens_fiduciaires": [],
                "tokens_compteurs": [],
                "aucun_token": True,
            },
        )

    # Query optimisee : select_related pour asset + tenant_origin,
    # prefetch_related pour federations et tenants (evite N+1 sur pastilles).
    # / Optimized query: select_related for asset + tenant_origin,
    # prefetch_related for federations and tenants (avoids N+1 on chips).
    tous_les_tokens = (
        Token.objects
        .filter(wallet=user.wallet)
        .select_related("asset", "asset__tenant_origin")
        .prefetch_related("asset__federations__tenants")
    )

    # Categories d'asset affichees dans le sous-tableau "Monnaies"
    # / Asset categories displayed in the "Currencies" sub-table
    categories_fiduciaires = [Asset.FED, Asset.TLF, Asset.TNF]

    tokens_fiduciaires = []
    tokens_compteurs = []
    for token in tous_les_tokens:
        # Label d'affichage : "TiBillets" pour FED (nom propre, pas traduit),
        # sinon nom de l'asset tel que saisi par le createur.
        # / Display label: "TiBillets" for FED (brand name, not translated),
        # otherwise the asset name as entered by the creator.
        if token.asset.category == Asset.FED:
            asset_name_affichage = "TiBillets"
        else:
            asset_name_affichage = token.asset.name

        # Dict explicite passe au template (pas de mutation ORM).
        # / Explicit dict passed to template (no ORM mutation).
        item = {
            "value_euros": token.value / 100,  # centimes -> euros
            "value_brut": token.value,         # pour TIM/FID (unites brutes)
            "asset_name_affichage": asset_name_affichage,
            "category": token.asset.category,
            "category_display": token.asset.get_category_display(),
            "currency_code": token.asset.currency_code,
            "lieux_utilisables": _lieux_utilisables_pour_asset(token.asset),
        }

        if token.asset.category in categories_fiduciaires:
            tokens_fiduciaires.append(item)
        else:
            tokens_compteurs.append(item)

    # Tri : solde decroissant, fallback nom d'asset
    # / Sort: balance descending, fallback asset name
    tokens_fiduciaires.sort(key=lambda x: (-x["value_brut"], x["asset_name_affichage"]))
    tokens_compteurs.sort(key=lambda x: (-x["value_brut"], x["asset_name_affichage"]))

    aucun_token = len(tokens_fiduciaires) == 0 and len(tokens_compteurs) == 0

    return render(
        request,
        "reunion/partials/account/token_table_v2.html",
        {
            "config": config,
            "tokens_fiduciaires": tokens_fiduciaires,
            "tokens_compteurs": tokens_compteurs,
            "aucun_token": aucun_token,
        },
    )
```

### 3.3 Helpers module-level

```python
def _lieux_utilisables_pour_asset(asset):
    """
    Retourne la liste des lieux ou un token de cet asset peut etre utilise.
    / Returns the list of venues where a token of this asset can be used.

    LOCALISATION : BaseBillet/views.py (helper module-level)

    Cas special FED : asset global, utilisable dans TOUS les lieux V2.
    On retourne None (convention) pour que le template affiche un badge
    unique "Utilisable partout" sans iterer 300+ lieux.
    / Special FED case: global asset, usable everywhere. Return None so
    the template shows a single "Usable everywhere" badge.

    Cas TLF/TNF/TIM/FID : le lieu createur (tenant_origin) + les lieux
    federes via les M2M Federation.assets <-> Federation.tenants.
    / TLF/TNF/TIM/FID case: the creator + federation members.

    :param asset: fedow_core.Asset
    :return: None si FED, sinon list[{organisation, logo}]
    """
    # Cas FED : pas de liste, badge "partout" cote template.
    # / FED case: no list, "everywhere" badge on template side.
    if asset.category == Asset.FED:
        return None

    # Cas autres : collecter tenants origine + federes, dedupliquer par pk.
    # / Other cases: collect origin + federated tenants, deduplicate by pk.
    tenants_utilisables = [asset.tenant_origin]
    for federation in asset.federations.all():
        for tenant in federation.tenants.all():
            tenants_utilisables.append(tenant)

    tenants_uniques_par_pk = {t.pk: t for t in tenants_utilisables}

    # Resoudre organisation + logo via cache (evite tenant_context N+1)
    # / Resolve organization + logo via cache (avoids tenant_context N+1)
    infos = []
    for tenant in tenants_uniques_par_pk.values():
        info = _get_tenant_info_cached(tenant.pk)
        if info is not None:
            infos.append(info)
    return infos
```

```python
def _get_tenant_info_cached(tenant_pk):
    """
    Retourne {organisation, logo} d'un tenant, avec cache 1h.
    / Returns {organisation, logo} of a tenant, with 1h cache.

    LOCALISATION : BaseBillet/views.py (helper module-level)

    CACHE CROSS-TENANT VOLONTAIRE : la cle "tenant_info_v2" est globale
    (pas de connection.tenant.pk dedans). C'est voulu : cette fonction
    sert a afficher les noms/logos de N lieux depuis un seul schema.
    Une cle par tenant casserait le mutualisme du cache et creerait
    N*M entrees redondantes. Pattern strictement equivalent a
    get_place_cached_info V1 (cle "place_uuid" aussi globale).
    / Intentional cross-tenant cache. Same pattern as V1's
    get_place_cached_info which also uses a global key.

    Premier appel (cache froid) : itere tous les tenants
    categorie=SALLE_SPECTACLE en une seule passe (N tenant_context).
    / First call (cold cache): iterates all SALLE_SPECTACLE tenants
    in one pass (N tenant_context).

    :param tenant_pk: UUID du tenant (Client.pk)
    :return: dict {organisation, logo} ou None si tenant inconnu
    """
    cache_key = "tenant_info_v2"
    cache_content = cache.get(cache_key)

    if cache_content is None:
        # Cache froid : on pre-construit pour tous les lieux en une passe.
        # / Cold cache: pre-build for all venues in one pass.
        cache_content = {}
        for tenant in Client.objects.filter(categorie=Client.SALLE_SPECTACLE):
            with tenant_context(tenant):
                config = Configuration.get_solo()
                cache_content[tenant.pk] = {
                    "organisation": config.organisation,
                    "logo": config.logo,
                }
        cache.set(cache_key, cache_content, 3600)

    return cache_content.get(tenant_pk)
```

### 3.4 Template `token_table_v2.html`

```html
{% load humanize i18n %}
{% comment %}
Partial V2 : affichage des tokens fedow_core.Token d'un user.

LOCALISATION : BaseBillet/templates/reunion/partials/account/token_table_v2.html

Rendu par MyAccount._tokens_table_v2() uniquement pour les users V2
(verdict peut_recharger_v2 == "v2"). Les autres branches utilisent
le partial V1 token_table.html (inchange).

/ V2 partial for fedow_core.Token display. Rendered only for V2 users.
{% endcomment %}

<div id="tokens-v2-container" aria-live="polite">

  {% if aucun_token %}
    <div class="text-center py-4 opacity-75" data-testid="tokens-v2-empty">
      <i class="bi bi-wallet2 fs-1 d-block mb-2" aria-hidden="true"></i>
      <p class="mb-2">{% translate "You don't have any TiBillets yet." %}</p>
      <a href="#tirelire-section" class="text-decoration-none">
        <i class="bi bi-arrow-up-circle" aria-hidden="true"></i>
        {% translate "Refill your wallet above" %}
      </a>
    </div>
  {% endif %}

  {% if tokens_fiduciaires %}
    <h3 class="h5 mt-3">{% translate "Currencies" %}</h3>
    <table class="table" data-testid="tokens-v2-fiduciaires">
      <thead>
        <tr>
          <th>{% translate "Balance" %}</th>
          <th>{% translate "Usable at" %}</th>
        </tr>
      </thead>
      <tbody>
        {% for item in tokens_fiduciaires %}
          <tr data-testid="token-row-fiduciaire">
            <td>
              <strong>{{ item.value_euros|floatformat:2 }}</strong>
              <span class="ms-1">{{ item.asset_name_affichage }}</span>
              <span class="badge bg-secondary ms-1">{{ item.category_display }}</span>
            </td>
            <td>
              {% if item.lieux_utilisables is None %}
                <span class="badge bg-primary">{% translate "Usable everywhere" %}</span>
              {% else %}
                {% for lieu in item.lieux_utilisables %}
                  {% if lieu.logo %}
                    <img src="{{ lieu.logo.thumbnail.url }}"
                         alt="{{ lieu.organisation }}"
                         style="height: 1.5rem"
                         class="align-baseline me-1">
                  {% endif %}
                  <span class="me-2">{{ lieu.organisation }}</span>
                {% endfor %}
              {% endif %}
            </td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  {% endif %}

  {% if tokens_compteurs %}
    <h3 class="h5 mt-4">{% translate "Time & loyalty" %}</h3>
    <p class="small opacity-75">
      {% translate "These units are not convertible into euros." %}
    </p>
    <table class="table" data-testid="tokens-v2-compteurs">
      <thead>
        <tr>
          <th>{% translate "Balance" %}</th>
          <th>{% translate "Usable at" %}</th>
        </tr>
      </thead>
      <tbody>
        {% for item in tokens_compteurs %}
          <tr data-testid="token-row-compteur">
            <td>
              <strong>{{ item.value_brut }}</strong>
              <span class="ms-1">{{ item.currency_code }}</span>
              <span class="ms-1">{{ item.asset_name_affichage }}</span>
              <span class="badge bg-info ms-1">{{ item.category_display }}</span>
            </td>
            <td>
              {% for lieu in item.lieux_utilisables %}
                {% if lieu.logo %}
                  <img src="{{ lieu.logo.thumbnail.url }}"
                       alt="{{ lieu.organisation }}"
                       style="height: 1.5rem"
                       class="align-baseline me-1">
                {% endif %}
                <span class="me-2">{{ lieu.organisation }}</span>
              {% endfor %}
            </td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  {% endif %}

</div>
```

### 3.5 Style skin reunion (optionnel, si lisibilité OK)

La palette créole du skin `reunion` peut rehausser les titres et badges
sans sacrifier la lisibilité :

- **h3 `"Currencies"` / `"Time & loyalty"`** : typographie `Staatliches`
  (déjà chargée dans le skin) pour un rendu display cohérent avec les autres
  titres de section.
- **Badges catégorie** : remplacer `bg-secondary` / `bg-info` / `bg-primary`
  par des classes CSS dédiées dans `reunion/css/` reprenant la palette du skin.
  Exemple : `badge-fed` (couleur primaire TiBillet), `badge-tlf` (couleur lieu),
  `badge-tim` (couleur profonde), `badge-fid` (couleur pépite).

**Décision finale** : à régler en revue visuelle Playwright (commit + check).
Si les badges Bootstrap standards passent le test de lisibilité sur mobile et desktop,
on garde les classes par défaut. Sinon, on ajoute un petit fichier `token_table_v2.css`
avec les variantes palette créole.

Ce choix est **orthogonal** au flux de données : la vue et le template ne changent pas.

---

## 4. Cas limites et gestion d'erreurs

| Cas | Comportement |
|---|---|
| `user.wallet is None` (jamais rechargé) | Retour précoce, template rendu avec `aucun_token=True` |
| QuerySet de tokens vide (wallet existe, 0 Token) | `aucun_token=True` calculé en fin de construction |
| Tous les tokens ont `value == 0` | Affichés quand même (signal historique) |
| `token.asset.tenant_origin == federation_fed` (tenant technique) | Filtré naturellement par `Client.objects.filter(categorie=SALLE_SPECTACLE)` dans le cache |
| Tenant dans `federation.tenants` sans `module_monnaie_locale` | Inclus quand même : le module peut être momentanément OFF, la carte reste historiquement utilisable là-bas |
| `Configuration.logo == None` pour un tenant | Template affiche juste le nom (`{% if lieu.logo %}...{% endif %}`) |
| Cache froid (premier call) | Itère `Client.objects.filter(categorie=SALLE_SPECTACLE)` en un seul passage, pose le cache 3600s |
| Cache TTL expiré en prod avec 300 lieux | Coût one-shot : ~300 × (tenant_context + Configuration.get_solo) — acceptable (1x/h max, asynchrone côté user) |

**Invalidation cache** : TTL 3600s suffit (comme V1). Pas de signal `post_save` sur `Configuration` — un admin qui change le logo voit le changement au plus tard dans l'heure. Possibilité d'ajouter l'invalidation plus tard si besoin (YAGNI).

---

## 5. Tests pytest

Fichier : `tests/pytest/test_tokens_table_v2.py` (nouveau, ~7 tests).

Fixtures réutilisées :

- `bootstrap_fed_asset` (déjà existant) pour créer tenant `federation_fed` + asset FED
- `admin_user` (TibilletUser admin)
- Helper local `recharger_user_fed(user, amount_cents)` qui appelle
  `RefillService.process_cashless_refill()` pour créer un Token FED de test

| Test | Ce qui est vérifié |
|---|---|
| `test_tokens_table_v2_dispatch_branche_v2` | Verdict `"v2"` → template `token_table_v2.html` rendu (pas `token_table.html`). Vérifier la présence de `data-testid="tokens-v2-container"` |
| `test_tokens_table_v2_dispatch_branche_v1_legacy` | Tenant avec `server_cashless` renseigné → template V1 rendu (pas V2). Non-régression. |
| `test_tokens_table_v2_wallet_absent` | User sans wallet → `aucun_token=True`, HTML contient `data-testid="tokens-v2-empty"` |
| `test_tokens_table_v2_wallet_vide` | User avec wallet mais 0 Token → `aucun_token=True` |
| `test_tokens_table_v2_token_fed_utilisable_partout` | Token FED créé via `RefillService` → HTML contient badge `"Usable everywhere"` et **pas** de liste de lieux |
| `test_tokens_table_v2_token_tlf_lieux_federes` | Asset TLF créé manuellement avec 2 lieux fédérés → HTML contient les 2 noms d'organisation |
| `test_tokens_table_v2_split_fiduciaires_compteurs` | Tokens FED (value=1500) + TIM (value=3) → bloc `"Currencies"` contient le FED, bloc `"Time & loyalty"` contient le TIM |

**Pas de test Playwright** cette session : la vue est un simple partial HTMX rendu sans interaction multi-étapes. Tests pytest + test manuel visuel sur `https://lespass.tibillet.localhost/my_account/balance/` suffisent.

---

## 6. Fichiers touchés

**Modifiés :**

| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` | Dispatch V2 dans `MyAccount.tokens_table` + nouvelle méthode `_tokens_table_v2` + 2 helpers module-level |
| `CHANGELOG.md` | Entrée bilingue FR/EN en tête |
| `locale/fr/LC_MESSAGES/django.po` + `locale/en/LC_MESSAGES/django.po` | ~7 nouvelles strings i18n (cf. section 7) |

**Créés :**

| Fichier | Rôle |
|---|---|
| `BaseBillet/templates/reunion/partials/account/token_table_v2.html` | Partial V2 dédié |
| `tests/pytest/test_tokens_table_v2.py` | Tests pytest |
| `A TESTER et DOCUMENTER/visu-tirelire-v2.md` | Guide mainteneur (scénarios manuels + commandes DB) |

**Intacts :**

| Fichier | Note |
|---|---|
| `BaseBillet/templates/reunion/partials/account/token_table.html` | Template V1 inchangé |
| `BaseBillet/templates/reunion/views/account/balance.html` | La page appelante, inchangée |
| `fedow_core/services.py` | `WalletService.obtenir_tous_les_soldes` inchangée (conservée pour POS) |
| `BaseBillet/views.py:tokens_table` code V1 | Inchangé, juste précédé par le dispatch V2 |

**Pas de migration DB** : aucun changement de schema.

---

## 7. Workflow djc obligatoire

1. **CHANGELOG.md** — entrée bilingue FR/EN en tête avec :
   - Titre : `Session 32 — Visualisation tirelire V2`
   - Quoi/What, Pourquoi/Why
   - Fichiers modifiés (tableau)
   - Migration : Non
2. **i18n** :
   ```bash
   docker exec lespass_django poetry run django-admin makemessages -l fr
   docker exec lespass_django poetry run django-admin makemessages -l en
   # éditer les .po pour ~5 nouvelles strings
   docker exec lespass_django poetry run django-admin compilemessages
   ```
   Strings ajoutées (7) : `"You don't have any TiBillets yet."`, `"Refill your wallet above"`, `"Currencies"`, `"Usable at"`, `"Usable everywhere"`, `"Time & loyalty"`, `"These units are not convertible into euros."`. Note : `"TiBillets"` est un nom propre (marque), non traduit.
3. **`A TESTER et DOCUMENTER/visu-tirelire-v2.md`** — guide mainteneur :
   - Scénario nominal : se connecter, recharger 20€ via V2, vérifier visuellement la ligne "TiBillets : 20,00 €"
   - Scénario wallet vide : user neuf → message "aucun TiBillets"
   - Scénario V1 legacy : tenant `chantefrein` → ancien tableau s'affiche
   - Commandes DB : `Token.objects.filter(wallet__user=user)` pour vérifier les tokens créés
4. **Ruff** : `ruff check --fix` + `ruff format` sur les fichiers modifiés.
5. **Tests** : `pytest tests/pytest/test_tokens_table_v2.py -v` + `pytest tests/pytest/test_fedow_core.py tests/pytest/test_refill_*.py -v` (non-régression Session 31).

---

## 8. Hors scope

**Explicitement pas dans Session 32** :

- Migration des users `wallet_legacy` vers fedow_core local (nécessite un chantier à part)
- Suppression de `FedowAPI` (36 usages non gardés, cf. Session 31 section 1.3)
- Affichage des transactions V2 (`transactions_table`) — rester sur V1 pour l'instant, cohérent avec le reste non migré
- Catégories Asset.TLF / TNF / TIM / FID réelles : pour l'instant seul FED est créé en V2 par `RefillService`. La gestion display des autres catégories est **prête** dans le template mais non testée end-to-end (les tests TLF/TIM utiliseront des assets fabriqués manuellement)
- Suppression des assets (`archive=True`) ou filtrage actif/inactif dans l'affichage balance — rester sur "tout ce qui existe s'affiche" comme V1

**Sessions futures probables** :

- Affichage transactions V2 (`transactions_table_v2`)
- Migration wallet_legacy → fedow_core
- Fin de vie `FedowAPI` (Phase E du plan mono-repo)
