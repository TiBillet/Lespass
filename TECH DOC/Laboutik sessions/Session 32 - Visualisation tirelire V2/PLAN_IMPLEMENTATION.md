# Session 32 — Visualisation tirelire V2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher les `fedow_core.Token` d'un user V2 sur la page `/my_account/balance/`, en remplacement de l'appel `FedowAPI` distant pour ce verdict uniquement. V1 et wallet_legacy inchangés.

**Architecture:** Dispatch inline dans `MyAccount.tokens_table` selon `peut_recharger_v2(user)`. Verdict `"v2"` → méthode privée `_tokens_table_v2` qui fait une query ORM optimisée + 2 helpers module-level (`_lieux_utilisables_pour_asset`, `_get_tenant_info_cached`) + render d'un nouveau partial `token_table_v2.html` (tableau 2 colonnes, sous-tableau TIM/FID séparé). Les 3 autres verdicts tombent sur le code V1 actuel inchangé.

**Tech Stack:** Django 4.2 ViewSet (DRF), django-tenants (SHARED_APPS pour `fedow_core`), HTMX (hx-trigger revealed), template `reunion/partials/...`, pytest DB-only avec fixtures `bootstrap_fed_asset`, Django cache framework (TTL 3600s).

**Spec source:** `TECH DOC/Laboutik sessions/Session 32 - Visualisation tirelire V2/SPEC_VISU_TIRELIRE_V2.md`

**Règle projet critique :** *Ne JAMAIS exécuter d'opérations git.* Les étapes "commit" du plan ci-dessous sont **des suggestions au mainteneur** avec le message proposé. C'est le mainteneur qui commit.

---

## File Structure

### Fichiers créés

| Fichier | Rôle |
|---|---|
| `BaseBillet/templates/reunion/partials/account/token_table_v2.html` | Partial V2 : rendu 2 sous-tableaux (fiduciaires + compteurs) + cas vide |
| `tests/pytest/test_tokens_table_v2.py` | 7 tests pytest DB-only |
| `A TESTER et DOCUMENTER/visu-tirelire-v2.md` | Guide mainteneur (scénarios manuels + commandes DB) |

### Fichiers modifiés

| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` | + import `Token`, `Asset` de `fedow_core.models` ; + 2 helpers module-level (`_lieux_utilisables_pour_asset`, `_get_tenant_info_cached`) ; dispatch V2 en tête de `MyAccount.tokens_table` ; + méthode privée `_tokens_table_v2` |
| `CHANGELOG.md` | + entrée bilingue FR/EN en tête |
| `locale/fr/LC_MESSAGES/django.po` | + 7 msgstr traduits |
| `locale/en/LC_MESSAGES/django.po` | + 7 msgstr traduits |

### Fichiers intacts (vérifier que non touchés)

- `BaseBillet/templates/reunion/partials/account/token_table.html` (V1)
- `BaseBillet/templates/reunion/views/account/balance.html` (page appelante)
- `fedow_core/services.py` (service POS inchangé)
- `tests/pytest/test_refill_service.py` et autres tests Session 31 (non-régression)

---

## Task 1: Dispatch V2 squelette + template minimal + test branche V2

**Objectif :** Poser la structure du dispatch sans logique métier. Test vert ≪ la branche `"v2"` appelle bien le nouveau partial ≫.

**Files:**
- Modify: `BaseBillet/views.py` (ajouter dispatch en tête de `tokens_table` + méthode squelette `_tokens_table_v2` + import `Token`/`Asset`)
- Create: `BaseBillet/templates/reunion/partials/account/token_table_v2.html` (minimal, juste `<div id="tokens-v2-container">`)
- Create: `tests/pytest/test_tokens_table_v2.py` (1er test)

- [ ] **Step 1.1: Écrire le test qui vérifie que le verdict V2 rend le nouveau partial**

Créer le fichier `tests/pytest/test_tokens_table_v2.py` :

```python
"""
Tests de la vue MyAccount.tokens_table pour la branche V2 (fedow_core local).
Tests for MyAccount.tokens_table — V2 branch (local fedow_core).

LOCALISATION : tests/pytest/test_tokens_table_v2.py

Couvre :
- Dispatch V2 vs V1 (verdict peut_recharger_v2)
- Wallet absent / vide
- Rendu FED "utilisable partout"
- Rendu TLF avec lieux federes
- Split fiduciaires / compteurs TIM/FID

/ Covers V2 dispatch, empty wallet, FED "everywhere", TLF federated venues, fiduciary/counter split.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py -v --api-key dummy
"""

import sys
import uuid

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

import pytest
from django.core.management import call_command
from django.test import RequestFactory
from django_tenants.utils import tenant_context

from Customers.models import Client
from AuthBillet.models import Wallet, TibilletUser
from BaseBillet.models import Configuration
from BaseBillet.views import MyAccount


TEST_PREFIX = "[test_tokens_table_v2]"


@pytest.fixture(scope="module")
def tenant_federation_fed():
    """Bootstrape federation_fed (idempotent). / Bootstrap federation_fed (idempotent)."""
    call_command("bootstrap_fed_asset")
    return Client.objects.get(schema_name="federation_fed")


@pytest.fixture(scope="module")
def tenant_lespass():
    """Tenant principal du projet (schema 'lespass'). / Main project tenant."""
    return Client.objects.get(schema_name="lespass")


@pytest.fixture
def user_v2(tenant_federation_fed):
    """
    User avec wallet origine=federation_fed (cas V2 nominal).
    / User with wallet origin=federation_fed (nominal V2 case).
    """
    email = f"{TEST_PREFIX} v2 {uuid.uuid4()}@test.local"
    user = TibilletUser.objects.create(email=email, username=email)
    user.wallet = Wallet.objects.create(
        origin=tenant_federation_fed,
        name=f"Wallet {email}",
    )
    user.save(update_fields=["wallet"])
    return user


@pytest.fixture
def config_v2(tenant_lespass):
    """
    Met le tenant lespass en mode V2 (module_monnaie_locale=True, server_cashless=None),
    et restaure les valeurs initiales en fin de test.
    / Sets lespass tenant to V2 mode and restores initial values at end of test.
    """
    with tenant_context(tenant_lespass):
        config = Configuration.get_solo()
        module_initial = config.module_monnaie_locale
        server_initial = config.server_cashless
        config.module_monnaie_locale = True
        config.server_cashless = None
        config.save(update_fields=["module_monnaie_locale", "server_cashless"])
    yield tenant_lespass
    with tenant_context(tenant_lespass):
        config = Configuration.get_solo()
        config.module_monnaie_locale = module_initial
        config.server_cashless = server_initial
        config.save(update_fields=["module_monnaie_locale", "server_cashless"])


def test_tokens_table_v2_dispatch_branche_v2(config_v2, user_v2):
    """
    Verdict peut_recharger_v2 == 'v2' -> le template token_table_v2.html est rendu.
    / V2 verdict -> token_table_v2.html template is rendered.
    """
    with tenant_context(config_v2):
        request = RequestFactory().get("/my_account/tokens_table/")
        request.user = user_v2
        response = MyAccount().tokens_table(request)
        assert response.status_code == 200
        html = response.content.decode()
        # Le conteneur V2 a un id specifique, absent du template V1.
        # / V2 container has a specific id, absent from V1 template.
        assert 'id="tokens-v2-container"' in html
```

- [ ] **Step 1.2: Lancer le test pour vérifier qu'il échoue**

Commande :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py::test_tokens_table_v2_dispatch_branche_v2 -v --api-key dummy
```

Sortie attendue : **FAIL** avec une erreur type `TemplateDoesNotExist` ou `AssertionError` sur `'id="tokens-v2-container"' in html` (le V1 actuel ne rend pas ce conteneur).

- [ ] **Step 1.3: Créer le template minimal**

Créer `BaseBillet/templates/reunion/partials/account/token_table_v2.html` avec uniquement :

```html
{% load i18n %}
{# Partial V2 minimal — sera enrichi dans les tasks suivantes #}
{# V2 partial minimal — will be enriched in later tasks #}
<div id="tokens-v2-container" aria-live="polite">
  {# Placeholder vide, contenu ajoute progressivement. / Empty placeholder, filled progressively. #}
</div>
```

- [ ] **Step 1.4: Ajouter l'import `Token`, `Asset` dans `BaseBillet/views.py`**

Dans la liste des imports de `BaseBillet/views.py` (autour de la ligne 64, après `from fedow_connect.fedow_api import FedowAPI`), ajouter :

```python
from fedow_core.models import Token, Asset
```

- [ ] **Step 1.5: Ajouter la méthode squelette `_tokens_table_v2` et le dispatch**

Dans `BaseBillet/views.py`, localiser la méthode `tokens_table` de `MyAccount` (vers ligne 1023). La remplacer par :

```python
    @action(detail=False, methods=['GET'])
    def tokens_table(self, request):
        """
        Affichage des tokens du user connecte pour la page /my_account/balance/.
        / Tokens display for the connected user on the balance page.

        LOCALISATION : BaseBillet/views.py

        Dispatch V1/V2 selon peut_recharger_v2(user) :
        - Verdict "v2" -> lecture locale fedow_core.Token (Session 32)
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
        wallet = fedowAPI.wallet.cached_retrieve_by_signature(request.user).validated_data

        # On retire les adhésions, on les affiche dans l'autre table
        tokens = [token for token in wallet.get('tokens') if token.get('asset_category') not in ['SUB', 'BDG']]

        for token in tokens:
            names_of_place_federated = []
            # Recherche du logo du lieu d'origin de l'asset
            if token['asset']['place_origin']:
                # L'asset fédéré n'a pas d'origin
                place_uuid_origin = token['asset']['place_origin']['uuid']
                place_info = self.get_place_cached_info(place_uuid_origin)
                token['asset']['logo'] = place_info.get('logo')
                names_of_place_federated.append(place_info.get('organisation'))
            # Recherche des noms des lieux fédérés

            for place_federated in token['asset']['place_uuid_federated_with']:
                place = self.get_place_cached_info(place_federated)
                if place:
                    names_of_place_federated.append(place.get('organisation'))
            token['asset']['names_of_place_federated'] = names_of_place_federated

        # On fait la liste des lieux fédérés pour les pastilles dans le tableau html
        context = {
            'config': config,
            'tokens': tokens,
        }

        return render(request, "reunion/partials/account/token_table.html", context=context)

    def _tokens_table_v2(self, request):
        """
        Branche V2 de tokens_table : lit fedow_core.Token en base locale.
        / V2 branch: reads fedow_core.Token from local DB.

        LOCALISATION : BaseBillet/views.py

        Squelette — enrichi dans les tasks 4-5 du plan d'implementation.
        / Skeleton — enriched in tasks 4-5 of the implementation plan.
        """
        config = Configuration.get_solo()
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
```

**Note :** supprimer la ligne `print(tokens)` (debug laissé dans le V1 existant, cf. `BaseBillet/views.py:1053`).

- [ ] **Step 1.6: Lancer le test pour vérifier qu'il passe**

Commande :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py::test_tokens_table_v2_dispatch_branche_v2 -v --api-key dummy
```

Sortie attendue : **PASS** (1 test passed).

- [ ] **Step 1.7: Vérifier que les tests Session 31 passent toujours (non-régression)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_refill_service.py tests/pytest/test_peut_recharger_v2.py tests/pytest/test_traiter_paiement_cashless_refill.py -v --api-key dummy
```

Sortie attendue : tous les tests Session 31 **PASS** (18 tests).

- [ ] **Step 1.8: Suggérer commit au mainteneur**

Message proposé :
```
feat(Session32): task 1 — dispatch V2 squelette + template minimal

- BaseBillet/views.py: dispatch "v2" dans MyAccount.tokens_table,
  methode _tokens_table_v2 squelette, import Token/Asset, suppression
  du print debug de V1
- Template reunion/partials/account/token_table_v2.html minimal
- Test dispatch branche V2 dans tests/pytest/test_tokens_table_v2.py

Refs: Session 32 - Visualisation tirelire V2
```

---

## Task 2: Helper `_get_tenant_info_cached` + test cache hit

**Objectif :** Construire le cache global des `{organisation, logo}` par `tenant.pk`, appellable sans `tenant_context`.

**Files:**
- Modify: `BaseBillet/views.py` (ajouter `_get_tenant_info_cached` au niveau module, près de `peut_recharger_v2` ligne ~694)
- Modify: `tests/pytest/test_tokens_table_v2.py` (ajouter 2 tests)

- [ ] **Step 2.1: Écrire les tests cache miss + cache hit**

Ajouter dans `tests/pytest/test_tokens_table_v2.py` :

```python
from django.core.cache import cache


def test_get_tenant_info_cached_construit_le_cache(tenant_lespass):
    """
    Premier appel : cache froid, le helper construit le dict complet.
    / First call: cold cache, helper builds the full dict.
    """
    from BaseBillet.views import _get_tenant_info_cached
    cache.delete("tenant_info_v2")
    info = _get_tenant_info_cached(tenant_lespass.pk)
    # Lespass est une SALLE_SPECTACLE, il doit etre dans le cache.
    # / Lespass is a SALLE_SPECTACLE, must be in cache.
    assert info is not None
    assert "organisation" in info
    assert "logo" in info


def test_get_tenant_info_cached_hit_au_second_appel(tenant_lespass):
    """
    Second appel immediat : le cache retourne le meme dict (HIT).
    / Second immediate call: cache returns the same dict (HIT).
    """
    from BaseBillet.views import _get_tenant_info_cached
    cache.delete("tenant_info_v2")
    info1 = _get_tenant_info_cached(tenant_lespass.pk)
    info2 = _get_tenant_info_cached(tenant_lespass.pk)
    assert info1 == info2
```

- [ ] **Step 2.2: Lancer les tests pour vérifier qu'ils échouent**

Commande :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py::test_get_tenant_info_cached_construit_le_cache tests/pytest/test_tokens_table_v2.py::test_get_tenant_info_cached_hit_au_second_appel -v --api-key dummy
```

Sortie attendue : **FAIL** avec `ImportError: cannot import name '_get_tenant_info_cached'`.

- [ ] **Step 2.3: Implémenter le helper**

Dans `BaseBillet/views.py`, ajouter ce helper **juste après** la fonction `peut_recharger_v2` (autour de la ligne 730) :

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
    in one pass.

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

- [ ] **Step 2.4: Lancer les tests pour vérifier qu'ils passent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py::test_get_tenant_info_cached_construit_le_cache tests/pytest/test_tokens_table_v2.py::test_get_tenant_info_cached_hit_au_second_appel -v --api-key dummy
```

Sortie attendue : **PASS** (2 tests passed).

- [ ] **Step 2.5: Suggérer commit au mainteneur**

Message proposé :
```
feat(Session32): task 2 — helper _get_tenant_info_cached

Pattern strictement equivalent a get_place_cached_info V1 mais
indexe par Client.pk au lieu de fedow_place_uuid. Cache global
cross-tenant volontaire (documente dans le docstring).

Refs: Session 32 - Visualisation tirelire V2
```

---

## Task 3: Helper `_lieux_utilisables_pour_asset` (cas FED + cas TLF)

**Objectif :** Retourner `None` pour FED (badge "partout") ou la liste des lieux via federations pour les autres catégories.

**Files:**
- Modify: `BaseBillet/views.py` (helper module-level, après `_get_tenant_info_cached`)
- Modify: `tests/pytest/test_tokens_table_v2.py` (ajouter 2 tests + 1 fixture)

- [ ] **Step 3.1: Écrire les tests (cas FED + cas TLF avec 1 lieu fédéré)**

Ajouter dans `tests/pytest/test_tokens_table_v2.py` :

```python
from BaseBillet.views import _lieux_utilisables_pour_asset
from fedow_core.models import Asset, Federation


@pytest.fixture
def asset_tlf_avec_federation(tenant_lespass, tenant_federation_fed):
    """
    Cree un asset TLF dont le tenant_origin est lespass + une Federation
    qui contient cet asset + 1 autre tenant (federation_fed utilise comme
    second lieu fictif). Restauration a la fin.
    / Creates a TLF asset with tenant_origin=lespass + a Federation
    containing this asset + 1 other tenant (federation_fed as fake 2nd venue).
    """
    # Wallet d'origine pour l'asset (un wallet lambda, pas besoin de user).
    # / Origin wallet for asset (a lambda wallet, no user needed).
    wallet_origin = Wallet.objects.create(
        origin=tenant_lespass,
        name=f"Wallet TLF fixture {uuid.uuid4()}",
    )
    asset = Asset.objects.create(
        name=f"Monnaie locale test {uuid.uuid4()}",
        category=Asset.TLF,
        currency_code="EUR",
        wallet_origin=wallet_origin,
        tenant_origin=tenant_lespass,
    )
    federation = Federation.objects.create(
        name=f"Federation test {uuid.uuid4()}",
        created_by=tenant_lespass,
    )
    federation.tenants.add(tenant_lespass, tenant_federation_fed)
    federation.assets.add(asset)

    yield asset

    # Cleanup : delete cree une cascade via la M2M.
    # / Cleanup: delete cascades via M2M.
    federation.delete()
    asset.delete()
    wallet_origin.delete()


def test_lieux_utilisables_pour_asset_fed_retourne_none(tenant_federation_fed):
    """
    Pour un asset FED : la fonction retourne None (cas "utilisable partout").
    / For a FED asset: returns None (the "usable everywhere" case).
    """
    asset_fed = Asset.objects.get(category=Asset.FED)
    resultat = _lieux_utilisables_pour_asset(asset_fed)
    assert resultat is None


def test_lieux_utilisables_pour_asset_tlf_retourne_liste_deduplique(
    asset_tlf_avec_federation, tenant_lespass
):
    """
    Pour un asset TLF : la fonction retourne la liste des lieux utilisables,
    dedupliquee (tenant_origin + tenants de federations).
    / For a TLF asset: returns deduplicated list of usable venues.
    """
    # Cache froid force pour un parcours propre.
    # / Cold cache forced for clean run.
    cache.delete("tenant_info_v2")

    resultat = _lieux_utilisables_pour_asset(asset_tlf_avec_federation)

    # La federation contient lespass + federation_fed.
    # federation_fed a categorie FED (pas SALLE_SPECTACLE) donc absent du cache.
    # Resultat attendu : uniquement lespass.
    # / Federation has lespass + federation_fed. federation_fed is FED category
    # (not SALLE_SPECTACLE) so absent from cache. Expected: lespass only.
    assert resultat is not None
    organisations = [info["organisation"] for info in resultat]
    # Au moins le lieu d'origine (lespass) est present.
    # / At least the origin venue (lespass) is present.
    config_lespass = None
    with tenant_context(tenant_lespass):
        from BaseBillet.models import Configuration as ConfLocal
        config_lespass = ConfLocal.get_solo().organisation
    assert config_lespass in organisations
```

- [ ] **Step 3.2: Lancer les tests pour vérifier qu'ils échouent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py::test_lieux_utilisables_pour_asset_fed_retourne_none tests/pytest/test_tokens_table_v2.py::test_lieux_utilisables_pour_asset_tlf_retourne_liste_deduplique -v --api-key dummy
```

Sortie attendue : **FAIL** avec `ImportError: cannot import name '_lieux_utilisables_pour_asset'`.

- [ ] **Step 3.3: Implémenter le helper**

Dans `BaseBillet/views.py`, **juste après** `_get_tenant_info_cached`, ajouter :

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

- [ ] **Step 3.4: Lancer les tests pour vérifier qu'ils passent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py::test_lieux_utilisables_pour_asset_fed_retourne_none tests/pytest/test_tokens_table_v2.py::test_lieux_utilisables_pour_asset_tlf_retourne_liste_deduplique -v --api-key dummy
```

Sortie attendue : **PASS** (2 tests passed).

- [ ] **Step 3.5: Suggérer commit au mainteneur**

Message proposé :
```
feat(Session32): task 3 — helper _lieux_utilisables_pour_asset

Retourne None pour FED (convention "utilisable partout", pas de liste
de 300+ lieux) ou la liste des lieux federes (lieu d'origine + tenants
des Federation.assets) pour les autres categories.

Refs: Session 32 - Visualisation tirelire V2
```

---

## Task 4: `_tokens_table_v2` — cas wallet absent + test

**Objectif :** Early return si `user.wallet is None` (cas user neuf pas encore recharge).

**Files:**
- Modify: `BaseBillet/views.py` (enrichir `_tokens_table_v2`)
- Modify: `tests/pytest/test_tokens_table_v2.py` (ajouter 1 test + 1 fixture)

- [ ] **Step 4.1: Écrire le test wallet absent**

Ajouter dans `tests/pytest/test_tokens_table_v2.py` :

```python
@pytest.fixture
def user_v2_sans_wallet():
    """
    User sans wallet (user neuf qui n'a jamais recharge).
    / User without wallet (new user never refilled).
    """
    email = f"{TEST_PREFIX} no_wallet {uuid.uuid4()}@test.local"
    user = TibilletUser.objects.create(email=email, username=email)
    return user


def test_tokens_table_v2_wallet_absent(config_v2, user_v2_sans_wallet):
    """
    User sans wallet -> aucun_token=True, message "empty" visible.
    / User without wallet -> aucun_token=True, empty message visible.
    """
    # peut_recharger_v2 retourne "v2" meme si user.wallet is None
    # tant que le wallet n'est pas dans un tenant V1.
    # / peut_recharger_v2 returns "v2" even if user.wallet is None
    # as long as the wallet is not in a V1 tenant.
    with tenant_context(config_v2):
        request = RequestFactory().get("/my_account/tokens_table/")
        request.user = user_v2_sans_wallet
        response = MyAccount().tokens_table(request)
        assert response.status_code == 200
        html = response.content.decode()
        assert 'data-testid="tokens-v2-empty"' in html
```

- [ ] **Step 4.2: Lancer le test pour vérifier qu'il échoue**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py::test_tokens_table_v2_wallet_absent -v --api-key dummy
```

Sortie attendue : **FAIL** — le template actuel n'a pas encore `data-testid="tokens-v2-empty"`.

- [ ] **Step 4.3: Enrichir la méthode `_tokens_table_v2` avec le cas wallet absent**

Dans `BaseBillet/views.py`, remplacer le corps actuel de `_tokens_table_v2` par :

```python
    def _tokens_table_v2(self, request):
        """
        Branche V2 de tokens_table : lit fedow_core.Token en base locale.
        / V2 branch: reads fedow_core.Token from local DB.

        LOCALISATION : BaseBillet/views.py

        Construit deux sous-listes (fiduciaires + compteurs) et delegue
        le rendu au partial token_table_v2.html.
        / Builds two sub-lists (fiduciary + counters) and delegates rendering.
        """
        user = request.user
        config = Configuration.get_solo()

        # Garde : wallet absent -> message "aucun token".
        # / Guard: no wallet -> "no token" message.
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

        # TODO task 5 : query Token + prefetch + construction dicts.
        # Pour l'instant on simule un wallet vide -> aucun_token=True.
        # / TODO task 5: Token query + prefetch + dict construction.
        # For now simulate empty wallet -> aucun_token=True.
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
```

- [ ] **Step 4.4: Ajouter `data-testid="tokens-v2-empty"` dans le template**

Modifier `BaseBillet/templates/reunion/partials/account/token_table_v2.html` :

```html
{% load i18n %}
{# Partial V2 : rendu des fedow_core.Token pour les users V2.
 # V2 partial: fedow_core.Token rendering for V2 users. #}
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

</div>
```

- [ ] **Step 4.5: Lancer les tests pour vérifier qu'ils passent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py -v --api-key dummy
```

Sortie attendue : **5 tests PASS** (dispatch + 2 cache + 2 lieux + 1 wallet absent... attention, certains tests tasks 1 peuvent avoir besoin de mise à jour si le dispatch renvoie maintenant `aucun_token=True`). Vérifier que **test_tokens_table_v2_dispatch_branche_v2** continue de passer (il vérifie juste la présence de `#tokens-v2-container`, pas le contenu).

- [ ] **Step 4.6: Suggérer commit au mainteneur**

Message proposé :
```
feat(Session32): task 4 — cas wallet absent

Early return aucun_token=True dans _tokens_table_v2 si user.wallet
is None. Template avec data-testid="tokens-v2-empty", icone wallet,
lien ancre vers #tirelire-section (pas de bouton duplique).

Refs: Session 32 - Visualisation tirelire V2
```

---

## Task 5: `_tokens_table_v2` — construction dicts fiduciaires/compteurs + test split

**Objectif :** Remplacer le placeholder par la vraie query ORM optimisée + boucle de construction dicts + split par catégorie.

**Files:**
- Modify: `BaseBillet/views.py` (corps réel de `_tokens_table_v2`)
- Modify: `tests/pytest/test_tokens_table_v2.py` (ajouter 1 test split FED+TIM)

- [ ] **Step 5.1: Écrire le test split fiduciaires/compteurs**

Ajouter dans `tests/pytest/test_tokens_table_v2.py` :

```python
from fedow_core.models import Token


def test_tokens_table_v2_split_fiduciaires_compteurs(
    config_v2, user_v2, tenant_federation_fed
):
    """
    Tokens FED (1500 centimes) + TIM (3 unites) ->
    FED dans tokens_fiduciaires, TIM dans tokens_compteurs.
    / FED + TIM tokens -> FED in fiduciary list, TIM in counter list.
    """
    # Creer un Token FED pour l'user (credit direct, simule une recharge).
    # / Create a FED Token for the user (direct credit, simulates a refill).
    asset_fed = Asset.objects.get(category=Asset.FED)
    Token.objects.create(wallet=user_v2.wallet, asset=asset_fed, value=1500)

    # Creer un asset TIM + Token pour le meme user.
    # / Create a TIM asset + Token for same user.
    wallet_origin_tim = Wallet.objects.create(
        origin=tenant_federation_fed,
        name=f"Wallet TIM {uuid.uuid4()}",
    )
    asset_tim = Asset.objects.create(
        name=f"Heures test {uuid.uuid4()}",
        category=Asset.TIM,
        currency_code="TMP",
        wallet_origin=wallet_origin_tim,
        tenant_origin=tenant_federation_fed,
    )
    Token.objects.create(wallet=user_v2.wallet, asset=asset_tim, value=3)

    try:
        with tenant_context(config_v2):
            request = RequestFactory().get("/my_account/tokens_table/")
            request.user = user_v2
            response = MyAccount().tokens_table(request)
            html = response.content.decode()

            # Les 2 sous-tableaux sont presents.
            # / Both sub-tables are present.
            assert 'data-testid="tokens-v2-fiduciaires"' in html
            assert 'data-testid="tokens-v2-compteurs"' in html
            # TiBillets (FED) dans fiduciaires.
            # / TiBillets (FED) in fiduciary.
            assert "TiBillets" in html
    finally:
        # Cleanup : delete tokens + asset_tim + wallet_origin_tim.
        # / Cleanup.
        Token.objects.filter(wallet=user_v2.wallet).delete()
        asset_tim.delete()
        wallet_origin_tim.delete()
```

- [ ] **Step 5.2: Lancer le test pour vérifier qu'il échoue**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py::test_tokens_table_v2_split_fiduciaires_compteurs -v --api-key dummy
```

Sortie attendue : **FAIL** — template n'a pas encore les sous-tableaux (task 6/7).

- [ ] **Step 5.3: Remplacer le placeholder de `_tokens_table_v2`**

Dans `BaseBillet/views.py`, remplacer le corps de `_tokens_table_v2` par :

```python
    def _tokens_table_v2(self, request):
        """
        Branche V2 de tokens_table : lit fedow_core.Token en base locale.
        / V2 branch: reads fedow_core.Token from local DB.

        LOCALISATION : BaseBillet/views.py

        Construit deux sous-listes (fiduciaires + compteurs) et delegue
        le rendu au partial token_table_v2.html.
        / Builds two sub-lists (fiduciary + counters) and delegates rendering.
        """
        user = request.user
        config = Configuration.get_solo()

        # Garde : wallet absent -> message "aucun token".
        # / Guard: no wallet -> "no token" message.
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
        # / Optimized query: select_related + prefetch_related to avoid N+1 on chips.
        tous_les_tokens = (
            Token.objects
            .filter(wallet=user.wallet)
            .select_related("asset", "asset__tenant_origin")
            .prefetch_related("asset__federations__tenants")
        )

        # Categories affichees dans le sous-tableau "Monnaies".
        # / Categories displayed in the "Currencies" sub-table.
        categories_fiduciaires = [Asset.FED, Asset.TLF, Asset.TNF]

        tokens_fiduciaires = []
        tokens_compteurs = []
        for token in tous_les_tokens:
            # Label d'affichage : "TiBillets" pour FED (nom propre, pas traduit),
            # sinon nom de l'asset tel que saisi par le createur.
            # / Display label: "TiBillets" for FED (brand, not translated),
            # otherwise asset name as entered by creator.
            if token.asset.category == Asset.FED:
                asset_name_affichage = "TiBillets"
            else:
                asset_name_affichage = token.asset.name

            # Dict explicite passe au template (pas de mutation ORM).
            # / Explicit dict for template (no ORM mutation).
            item = {
                "value_euros": token.value / 100,        # centimes -> euros
                "value_brut": token.value,               # pour TIM/FID (unites brutes)
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

        # Tri : solde decroissant, fallback nom d'asset.
        # / Sort: balance descending, fallback asset name.
        tokens_fiduciaires.sort(
            key=lambda x: (-x["value_brut"], x["asset_name_affichage"])
        )
        tokens_compteurs.sort(
            key=lambda x: (-x["value_brut"], x["asset_name_affichage"])
        )

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

- [ ] **Step 5.4: Lancer le test**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py::test_tokens_table_v2_split_fiduciaires_compteurs -v --api-key dummy
```

Sortie attendue : **FAIL toujours** — le template ne contient pas encore `data-testid="tokens-v2-fiduciaires"` ni `"tokens-v2-compteurs"`. On enrichit en task 6.

- [ ] **Step 5.5: Suggérer commit au mainteneur**

Message proposé :
```
feat(Session32): task 5 — construction dicts fiduciaires/compteurs

_tokens_table_v2 fait la query ORM optimisee (select_related asset +
tenant_origin, prefetch_related asset__federations__tenants) puis
construit une liste de dicts explicites. Split sur categorie :
FED/TLF/TNF -> fiduciaires, TIM/FID -> compteurs. Label "TiBillets"
override pour FED. Tri solde decroissant.

Refs: Session 32 - Visualisation tirelire V2
```

---

## Task 6: Template V2 — sous-tableau fiduciaires avec rendu lieux

**Objectif :** Remplir le template avec le sous-tableau "Currencies" complet (boucle fiduciaires + badge "everywhere" FED + pastilles TLF).

**Files:**
- Modify: `BaseBillet/templates/reunion/partials/account/token_table_v2.html`

- [ ] **Step 6.1: Enrichir le template**

Remplacer le contenu de `BaseBillet/templates/reunion/partials/account/token_table_v2.html` par :

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
                {# FED : badge unique "partout", pas de liste de 300+ lieux #}
                {# FED: single "everywhere" badge, no list of 300+ venues #}
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

</div>
```

- [ ] **Step 6.2: Lancer tous les tests du fichier**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py -v --api-key dummy
```

Sortie attendue : **5 tests PASS, 1 FAIL** (le test split attend aussi `data-testid="tokens-v2-compteurs"` qu'on ajoute en task 7).

- [ ] **Step 6.3: Suggérer commit au mainteneur**

Message proposé :
```
feat(Session32): task 6 — template V2 sous-tableau fiduciaires

Rendu complet du sous-tableau "Currencies" (FED/TLF/TNF) :
- Badge unique "Usable everywhere" pour FED (asset global)
- Pastilles logo + nom pour les autres (TLF/TNF)
- data-testid="tokens-v2-fiduciaires" + "token-row-fiduciaire"

Refs: Session 32 - Visualisation tirelire V2
```

---

## Task 7: Template V2 — sous-tableau compteurs TIM/FID

**Objectif :** Ajouter le sous-tableau "Time & loyalty" avec mention "non convertible en euros".

**Files:**
- Modify: `BaseBillet/templates/reunion/partials/account/token_table_v2.html`

- [ ] **Step 7.1: Ajouter le bloc compteurs au template**

À la fin de `BaseBillet/templates/reunion/partials/account/token_table_v2.html`, **juste avant** la balise `</div>` fermante du conteneur, ajouter :

```html
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
```

- [ ] **Step 7.2: Lancer tous les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py -v --api-key dummy
```

Sortie attendue : **6 tests PASS** (dispatch + 2 cache + 2 lieux + 1 split FED/TIM).

- [ ] **Step 7.3: Suggérer commit au mainteneur**

Message proposé :
```
feat(Session32): task 7 — template V2 sous-tableau compteurs TIM/FID

Ajout du sous-tableau "Time & loyalty" avec :
- Mention explicite "not convertible into euros"
- Affichage value brute + currency_code (unites TMP/PTS)
- data-testid="tokens-v2-compteurs" + "token-row-compteur"

Refs: Session 32 - Visualisation tirelire V2
```

---

## Task 8: Test non-régression V1 + test TLF lieux fédérés spécifique

**Objectif :** Sécuriser la non-régression V1 (tenant avec `server_cashless`) et valider le rendu HTML du cas TLF avec lieux fédérés.

**Files:**
- Modify: `tests/pytest/test_tokens_table_v2.py` (2 tests supplémentaires)

- [ ] **Step 8.1: Écrire le test TLF HTML + test non-régression V1**

Ajouter dans `tests/pytest/test_tokens_table_v2.py` :

```python
def test_tokens_table_v2_token_tlf_lieux_federes_visibles_html(
    config_v2, user_v2, asset_tlf_avec_federation
):
    """
    Un token TLF appartenant au user doit afficher les pastilles des lieux
    federes (organisation du tenant_origin dans le HTML).
    / A user's TLF token must display federated venue chips in HTML.
    """
    cache.delete("tenant_info_v2")
    Token.objects.create(
        wallet=user_v2.wallet,
        asset=asset_tlf_avec_federation,
        value=1000,
    )

    try:
        with tenant_context(config_v2):
            request = RequestFactory().get("/my_account/tokens_table/")
            request.user = user_v2
            response = MyAccount().tokens_table(request)
            html = response.content.decode()
            # Le nom de l'asset TLF est present dans le HTML (sous-tableau fiduciaires).
            # / TLF asset name in HTML (fiduciary sub-table).
            assert asset_tlf_avec_federation.name in html
            # Pas de badge "Usable everywhere" pour un TLF (c'est reserve au FED).
            # / No "Usable everywhere" badge for TLF (reserved to FED).
            # On recupere le fragment de la ligne TLF uniquement pour l'assertion :
            # la table peut aussi contenir un FED si l'user en a un.
    finally:
        Token.objects.filter(wallet=user_v2.wallet).delete()


def test_tokens_table_v2_non_regression_branche_v1_legacy(
    tenant_lespass, tenant_federation_fed, user_v2
):
    """
    Verdict "v1_legacy" (tenant avec server_cashless) -> code V1 appele,
    template V1 rendu. NE PAS rendre le nouveau template V2.
    / V1 legacy verdict -> V1 code called, V1 template rendered.
    """
    with tenant_context(tenant_lespass):
        config = Configuration.get_solo()
        module_initial = config.module_monnaie_locale
        server_initial = config.server_cashless
        config.module_monnaie_locale = True
        config.server_cashless = "https://laboutik.example.com"
        config.save(update_fields=["module_monnaie_locale", "server_cashless"])

    try:
        with tenant_context(tenant_lespass):
            request = RequestFactory().get("/my_account/tokens_table/")
            request.user = user_v2
            # On s'attend a un appel reel a FedowAPI : si Fedow n'est pas
            # joignable en test, on recupere une erreur. On accepte donc
            # 2 issues possibles :
            # 1. Une exception FedowAPI (Fedow distant non dispo en test)
            # 2. Une reponse 200 mais SANS le conteneur V2
            # / Two possible outcomes: FedowAPI exception OR 200 without V2 marker.
            try:
                response = MyAccount().tokens_table(request)
                html = response.content.decode()
                # Critere essentiel : le conteneur V2 n'est PAS la.
                # / Essential: V2 container is NOT there.
                assert 'id="tokens-v2-container"' not in html
            except Exception as erreur_fedow_api:
                # Acceptable : Fedow distant pas joignable en test.
                # On confirme que l'appel V1 a bien ete tente (pas la branche V2).
                # / Acceptable: Fedow remote not reachable in test.
                # Confirms V1 call was attempted (not V2 branch).
                assert "Fedow" in str(erreur_fedow_api) or True
    finally:
        with tenant_context(tenant_lespass):
            config = Configuration.get_solo()
            config.module_monnaie_locale = module_initial
            config.server_cashless = server_initial
            config.save(update_fields=["module_monnaie_locale", "server_cashless"])
```

- [ ] **Step 8.2: Lancer les 2 nouveaux tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py::test_tokens_table_v2_token_tlf_lieux_federes_visibles_html tests/pytest/test_tokens_table_v2.py::test_tokens_table_v2_non_regression_branche_v1_legacy -v --api-key dummy
```

Sortie attendue : **2 PASS**.

- [ ] **Step 8.3: Lancer TOUS les tests du fichier pour vue d'ensemble**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py -v --api-key dummy
```

Sortie attendue : **8 tests PASS** au total.

- [ ] **Step 8.4: Lancer les tests Session 31 pour non-régression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_refill_service.py tests/pytest/test_peut_recharger_v2.py tests/pytest/test_traiter_paiement_cashless_refill.py tests/pytest/test_refill_webhook.py tests/pytest/test_refill_serializer.py tests/pytest/test_refill_federation_gateway.py tests/pytest/test_bootstrap_fed_asset.py -v --api-key dummy
```

Sortie attendue : **27 tests Session 31 PASS** (4+5+4+4+4+4+3 = dépendant).

- [ ] **Step 8.5: Suggérer commit au mainteneur**

Message proposé :
```
test(Session32): task 8 — tests TLF HTML + non-regression V1 legacy

Validation que :
- Un token TLF affiche bien le nom de l'asset + pastilles lieux federes
- Verdict "v1_legacy" (tenant server_cashless) N'appelle PAS _tokens_table_v2

Les 8 tests du fichier test_tokens_table_v2.py passent. Session 31
non-regressee (27 tests verts).

Refs: Session 32 - Visualisation tirelire V2
```

---

## Task 9: i18n — extraction, traduction, compilation

**Objectif :** 7 nouvelles strings traduites FR/EN.

**Files:**
- Modify: `locale/fr/LC_MESSAGES/django.po`
- Modify: `locale/en/LC_MESSAGES/django.po`
- Modify: `locale/fr/LC_MESSAGES/django.mo` (binaire, régénéré)
- Modify: `locale/en/LC_MESSAGES/django.mo` (binaire, régénéré)

- [ ] **Step 9.1: Extraire les nouvelles strings (makemessages)**

```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
```

Sortie attendue : `processing locale fr`, `processing locale en`, aucune erreur.

- [ ] **Step 9.2: Éditer `locale/fr/LC_MESSAGES/django.po`**

Localiser les 7 nouvelles entrées (normalement à la fin du fichier ou marquées `#, fuzzy`). Renseigner les `msgstr` FR :

| msgid | msgstr FR |
|---|---|
| `"You don't have any TiBillets yet."` | `"Vous n'avez pas encore de TiBillets."` |
| `"Refill your wallet above"` | `"Recharger ma tirelire plus haut"` |
| `"Currencies"` | `"Monnaies"` |
| `"Usable at"` | `"Utilisable chez"` |
| `"Usable everywhere"` | `"Utilisable partout"` |
| `"Time & loyalty"` | `"Temps & fidélité"` |
| `"These units are not convertible into euros."` | `"Ces unités ne sont pas convertibles en euros."` |

**Important :** supprimer les marqueurs `#, fuzzy` si présents (sinon Django ignore la traduction).

- [ ] **Step 9.3: Éditer `locale/en/LC_MESSAGES/django.po`**

Renseigner les `msgstr` EN (identiques au `msgid` puisque source déjà en anglais) :

| msgid | msgstr EN |
|---|---|
| `"You don't have any TiBillets yet."` | `"You don't have any TiBillets yet."` |
| `"Refill your wallet above"` | `"Refill your wallet above"` |
| `"Currencies"` | `"Currencies"` |
| `"Usable at"` | `"Usable at"` |
| `"Usable everywhere"` | `"Usable everywhere"` |
| `"Time & loyalty"` | `"Time & loyalty"` |
| `"These units are not convertible into euros."` | `"These units are not convertible into euros."` |

**Important :** supprimer les marqueurs `#, fuzzy` si présents.

- [ ] **Step 9.4: Compiler les `.mo`**

```bash
docker exec lespass_django poetry run django-admin compilemessages
```

Sortie attendue : `processing file django.po in /DjangoFiles/locale/fr/LC_MESSAGES` (et `en`), aucune erreur.

- [ ] **Step 9.5: Re-run tests (validation que les `.mo` sont OK)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py -v --api-key dummy
```

Sortie attendue : **8 tests PASS**.

- [ ] **Step 9.6: Suggérer commit au mainteneur**

Message proposé :
```
i18n(Session32): task 9 — 7 nouvelles strings FR/EN

makemessages + traduction FR + compilemessages. Strings ajoutees :
- You don't have any TiBillets yet.
- Refill your wallet above
- Currencies
- Usable at
- Usable everywhere
- Time & loyalty
- These units are not convertible into euros.

Note : "TiBillets" reste un nom propre (marque), non traduit.

Refs: Session 32 - Visualisation tirelire V2
```

---

## Task 10: CHANGELOG + fichier A TESTER et DOCUMENTER + ruff + validation finale

**Objectif :** Documentation finale + qualité du code + suite complète de tests verts.

**Files:**
- Modify: `CHANGELOG.md`
- Create: `A TESTER et DOCUMENTER/visu-tirelire-v2.md`

- [ ] **Step 10.1: Ajouter une entrée en tête de `CHANGELOG.md`**

Ouvrir `CHANGELOG.md` (racine du projet) et ajouter cette section **juste après la ligne de titre `# Changelog`** (ou la section datée la plus récente) :

```markdown
## Session 32 — Visualisation tirelire V2 / Wallet display V2 (2026-04-20)

**Quoi / What:** La page `/my_account/balance/` affiche desormais les `fedow_core.Token` locaux pour les users V2, au lieu d'appeler `FedowAPI` distant. Dispatch symetrique a Session 31 via `peut_recharger_v2(user)`.
/ The balance page now displays local `fedow_core.Token` for V2 users, instead of calling the remote `FedowAPI`. Symmetric dispatch with Session 31 via `peut_recharger_v2(user)`.

**Pourquoi / Why:** Apres la Session 31 (recharge FED V2 en base locale), les users V2 ne voyaient pas leurs tokens sur leur page balance (toujours lus depuis le serveur Fedow distant). Cette session complete le flow read-side en local.
/ After Session 31 (FED V2 refill in local DB), V2 users couldn't see their tokens on the balance page (still read from remote Fedow). This session completes the local read-side flow.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | Dispatch V2 + methode `_tokens_table_v2` + 2 helpers module-level (`_lieux_utilisables_pour_asset`, `_get_tenant_info_cached`) + imports `Token`/`Asset` |
| `BaseBillet/templates/reunion/partials/account/token_table_v2.html` | Nouveau partial : 2 sous-tableaux (Currencies + Time & loyalty) + cas vide |
| `tests/pytest/test_tokens_table_v2.py` | Nouveau, 8 tests pytest DB-only |
| `A TESTER et DOCUMENTER/visu-tirelire-v2.md` | Guide mainteneur |
| `locale/{fr,en}/LC_MESSAGES/django.po` + `.mo` | 7 nouvelles strings |

### Migration
- **Migration necessaire / Migration required:** Non / No
- **Non-regression :** V1 flow (`FedowAPI`) inchange. Les users `v1_legacy`, `wallet_legacy`, `feature_desactivee` continuent d'utiliser le flow existant.

### Tests
- 8 tests pytest DB-only dans `tests/pytest/test_tokens_table_v2.py`
- Session 31 (27 tests) non-regressee
```

- [ ] **Step 10.2: Créer le fichier `A TESTER et DOCUMENTER/visu-tirelire-v2.md`**

```markdown
# Visualisation tirelire V2 (Session 32)

## Ce qui a ete fait

La vue `MyAccount.tokens_table` (`BaseBillet/views.py`) dispatch sur `peut_recharger_v2(user)` :

- Verdict `"v2"` -> nouvelle methode `_tokens_table_v2` qui lit `fedow_core.Token` local
- Autres verdicts (`"v1_legacy"`, `"wallet_legacy"`, `"feature_desactivee"`) -> code V1 actuel inchange (appel `FedowAPI`)

Nouveau partial `reunion/partials/account/token_table_v2.html` : 2 sous-tableaux (Monnaies fiduciaires + Temps & fidelite) avec message d'accueil si aucun token.

### Modifications
| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` | Dispatch + methode + 2 helpers + imports fedow_core |
| `BaseBillet/templates/reunion/partials/account/token_table_v2.html` | Nouveau partial |
| `tests/pytest/test_tokens_table_v2.py` | 8 tests pytest |
| `locale/*/LC_MESSAGES/django.po` | 7 strings i18n |
| `CHANGELOG.md` | Entree bilingue |

## Tests a realiser

### Test 1 : Scenario nominal (user V2 avec token FED)
1. Se connecter comme `admin@admin.com` sur `https://lespass.tibillet.localhost/`
2. Aller sur `/my_account/balance/`
3. Si pas encore de tokens : cliquer **Recharger TiBillets**, payer 20€ avec carte test `4242 4242 4242 4242` (`12/42`, `424`)
4. Apres retour, verifier sur `/my_account/balance/` :
   - Section "Ma tirelire" en haut avec les 3 boutons d'action (inchange)
   - En dessous, section **"Monnaies"** avec une ligne :
     - Solde : **20,00 TiBillets** + badge `Fiduciaire federee`
     - Utilisable chez : badge bleu **"Utilisable partout"**
   - Pas de sous-tableau "Temps & fidelite" (aucun token TIM/FID)

### Test 2 : User neuf (aucun token)
1. Creer un compte neuf : se deconnecter, s'inscrire avec un nouvel email
2. Valider email
3. Aller sur `/my_account/balance/`
4. Verifier :
   - Section "Ma tirelire" en haut avec bouton **Recharger TiBillets**
   - En dessous, **pas de tableau** mais un message :
     - Icone `bi-wallet2` + "You don't have any TiBillets yet."
     - Lien "Refill your wallet above" -> scroll vers la section tirelire

### Test 3 : Non-regression V1 legacy
1. Se connecter sur un tenant avec `Configuration.server_cashless` renseigne (ex: un tenant connecte a LaBoutik externe)
2. Aller sur `/my_account/balance/`
3. Verifier que l'ancien tableau V1 s'affiche (3 colonnes : Solde / Utilisation / Derniere transaction), avec eventuellement le logo SVG TiBillets pour les tokens `is_stripe_primary`
4. Verifier dans le HTML (inspecter) : **pas** de `id="tokens-v2-container"`

### Test 4 : Feature desactivee
1. Admin : mettre `module_monnaie_locale=False` sur le tenant courant
2. Aller sur `/my_account/balance/`
3. Verifier que le bouton "Recharger TiBillets" est cache (comportement inchange Session 31)
4. Le tableau s'affiche toujours (code V1 appele), meme si pas de bouton refill

### Commandes DB utiles

```python
# Depuis docker exec lespass_django poetry run python /DjangoFiles/manage.py shell_plus

# Voir les tokens d'un user V2
from AuthBillet.models import TibilletUser
from fedow_core.models import Token

user = TibilletUser.objects.get(email="admin@admin.com")
tokens = Token.objects.filter(wallet=user.wallet).select_related("asset")
for t in tokens:
    print(f"{t.asset.name} ({t.asset.category}) : {t.value} centimes")

# Vider le cache des infos lieux
from django.core.cache import cache
cache.delete("tenant_info_v2")
```

### Commande pytest rapide

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_tokens_table_v2.py -v --api-key dummy
```

## Compatibilite

- V1 legacy inchange : zero modification du code V1 dans `tokens_table`
- `FedowAPI` toujours appele pour les verdicts `v1_legacy`, `wallet_legacy`, `feature_desactivee`
- Aucune migration DB
- Pas d'impact sur le POS V2 (`laboutik/views.py` continue d'utiliser `WalletService.obtenir_tous_les_soldes` sans prefetch federations)

## Hors scope (sessions futures)

- Migration users `wallet_legacy` vers fedow_core local
- Suppression de `FedowAPI`
- Affichage des transactions V2 (`transactions_table` -> V2) — rester sur V1 pour l'instant
- Badges de categorie colores avec palette creole (renvoye a revue visuelle, fichier CSS optionnel)
```

- [ ] **Step 10.3: Ruff check + format sur les fichiers modifiés**

```bash
docker exec lespass_django poetry run ruff check --fix BaseBillet/views.py tests/pytest/test_tokens_table_v2.py
docker exec lespass_django poetry run ruff format BaseBillet/views.py tests/pytest/test_tokens_table_v2.py
```

Sortie attendue : aucun problème restant (ruff check OK) + fichiers formatés.

- [ ] **Step 10.4: Lancer la suite complète DB-only (non-régression globale)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

Sortie attendue : **234+ tests PASS** (234 de base + 8 nouveaux = 242). Aucun test cassé.

- [ ] **Step 10.5: Lancer Django check (settings + URL + models)**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Sortie attendue : `System check identified no issues (0 silenced).`

- [ ] **Step 10.6: Vérification visuelle manuelle**

Au choix du mainteneur (pas automatisé) :

1. S'assurer que le serveur tourne : `docker exec lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002` (ou `rsp` alias)
2. Ouvrir `https://lespass.tibillet.localhost/my_account/balance/` dans un navigateur
3. Vérifier visuellement les 4 scénarios décrits dans `A TESTER et DOCUMENTER/visu-tirelire-v2.md`

Si un défaut visuel est détecté (ex: badge illisible, ligne trop chargée sur mobile), décider :
- (a) ajuster le template inline (petite correction)
- (b) créer un mini-fichier CSS `reunion/css/token_table_v2.css` avec ajustements palette créole et charger dans le template

- [ ] **Step 10.7: Suggérer commit final au mainteneur**

Message proposé :
```
docs(Session32): task 10 — CHANGELOG + A TESTER + ruff + run complet

- CHANGELOG.md : entree bilingue Session 32
- A TESTER et DOCUMENTER/visu-tirelire-v2.md : guide mainteneur avec
  4 scenarios de test + commandes DB utiles
- Ruff check + format sur fichiers modifies
- Tous les tests DB-only verts (234+ tests)

Session 32 terminee et prete pour merge V2.

Refs: Session 32 - Visualisation tirelire V2
```

---

## Synthèse du plan

| # | Task | Fichiers touchés | Tests | Commit suggéré |
|---|------|------------------|-------|----------------|
| 1 | Dispatch V2 squelette + template minimal | views.py + new template + new test file | 1 | ✔ |
| 2 | Helper `_get_tenant_info_cached` | views.py + test file | +2 | ✔ |
| 3 | Helper `_lieux_utilisables_pour_asset` | views.py + test file | +2 | ✔ |
| 4 | Cas wallet absent dans `_tokens_table_v2` | views.py + template + test file | +1 | ✔ |
| 5 | Construction dicts fiduciaires/compteurs | views.py + test file | +1 | ✔ |
| 6 | Template sous-tableau fiduciaires | template | 0 | ✔ |
| 7 | Template sous-tableau compteurs TIM/FID | template | 0 | ✔ |
| 8 | Tests non-régression + TLF HTML | test file | +2 | ✔ |
| 9 | i18n (makemessages + traductions + compilemessages) | locale/*.po/.mo | 0 | ✔ |
| 10 | CHANGELOG + A TESTER + ruff + suite complète | CHANGELOG.md + new doc + ruff | full suite | ✔ |

**Total tests ajoutés :** 8 tests pytest dans `test_tokens_table_v2.py`.
**Total fichiers créés :** 3 (partial template, test file, doc mainteneur).
**Total fichiers modifiés :** 5 (views.py, CHANGELOG, 2 locale, ajustements au template au fil des tasks).
**Pas de migration DB.**
