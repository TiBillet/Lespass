# Newsletter Ghost — Plan d'implémentation

> **Pour les agents :** SOUS-SKILL REQUIS — utiliser `superpowers:subagent-driven-development`
> (recommandé) ou `superpowers:executing-plans` pour dérouler ce plan tâche par tâche.
> Les étapes sont en cases à cocher (`- [ ]`).
>
> **Hub :** [INDEX.md](INDEX.md) · **Spec de référence :** [SPEC.md](SPEC.md)
> **Prérequis :** [CHANTIER-01](CHANTIER-01-semantique-tags-federes.md) — **FAIT**.

**But :** Depuis l'admin Lespass, générer dans une instance Ghost auto-hébergée un **brouillon**
de newsletter listant les événements à venir du tenant **et de son réseau fédéré**. Rien n'est
jamais publié ni envoyé : le gestionnaire relit, élague et envoie à la main depuis Ghost.

**Architecture :** Une app Django `newsletter/` **sans modèle** (donc sans migration) —
`GhostConfig` existe déjà et porte l'URL et la clé chiffrée. Trois modules qui ne se connaissent
presque pas : `client_ghost` (parle à Ghost), `collecte` (rassemble les events du réseau),
`rendu` (fabrique le HTML) ; `services` les orchestre et constitue le seul point d'entrée de
l'admin. On envoie du **HTML sémantique aux conventions `kg-*`** que Ghost reconvertit en cartes
natives — **jamais** de Lexical JSON, **jamais** de style inline (voir SPEC §4, c'est le point
contre-intuitif du chantier).

**Stack :** Django 4.2 · django-tenants · django-solo · Unfold · `requests` · `pyjwt` ·
pytest. **Aucune nouvelle dépendance.**

> **Réserve sur `pyjwt`** : il n'est **pas** une dépendance *directe* de `pyproject.toml`. Il
> n'arrive que **transitivement**, via `djangorestframework-simplejwt`. Le code existant l'importe
> déjà (`BaseBillet/tasks.py`, `Administration/admin_tenant.py`), donc « aucune nouvelle
> dépendance » reste vrai — mais c'est **fragile**. À signaler au mainteneur : ajouter `pyjwt` en
> dépendance explicite serait plus sain. **Ne pas le faire dans ce chantier.**

---

## Contraintes globales

Elles s'appliquent implicitement à **chaque** tâche. Les violer casse le projet ou le poste du
mainteneur.

1. **AUCUNE opération git. Jamais.** Ni `commit`, ni `add`, ni `push`, ni `checkout --`, ni
   `stash`, ni `reset --hard`, ni `restore --`, ni `clean -f`. Le mainteneur committe lui-même.
   Les étapes « Commit » de ce plan demandent **d'AFFICHER le message suggéré** dans le rapport
   final, puis de **s'arrêter**.

2. **Toute commande Python passe par le conteneur.** Le projet est bind-monté
   (`/home/jonas/TiBillet/dev/Lespass` → `/DjangoFiles`) : le `.venv` est **partagé**, et un
   `poetry` lancé depuis l'hôte **détruit l'environnement du conteneur**.
   ```bash
   docker exec lespass_django poetry run pytest tests/pytest/<fichier>.py -v
   docker exec lespass_django poetry run ruff check --fix /DjangoFiles/<fichier>.py
   ```

3. **`ruff format` : autorisé sur un fichier NEUF, INTERDIT sur un fichier pré-existant** (il
   reformaterait des milliers de lignes sans rapport). `ruff check --fix` est sans danger partout.
   Fichiers pré-existants touchés ici : `TiBillet/settings.py`, `Administration/admin_tenant.py`.

4. **Ne jamais lancer `makemessages` ni `compilemessages`.** Écrire les `_()` / `{% translate %}`
   avec des **msgid en FRANÇAIS**, et **signaler** au mainteneur en fin de tâche que des chaînes
   traduisibles ont été ajoutées.

5. **Le serveur Django est tenu par le mainteneur** dans byobu. Ne pas lancer `runserver_plus`.
   Si les tests renvoient des `502`, c'est que le serveur est tombé : le signaler, ne pas le
   relancer.

6. **FALC** : noms de variables longs et explicites, commentaires bilingues FR (verbeux) / EN
   (une ligne). Boucles `for` simples plutôt que compréhensions savantes.

7. **La base de test est la base de DEV** (`django_db_setup` est un no-op). Les tests de ce plan
   sont donc **en lecture seule** sur le seed `demo_data_v2` : ils se mettent en `skip` (pas en
   échec) si le seed est absent. **Ne rien créer en base cross-schema** — une écriture non annulée
   corromprait les données de démonstration du mainteneur.

---

## Structure des fichiers

| Fichier | Responsabilité | Connaît |
|---|---|---|
| `newsletter/__init__.py` | — | — |
| `newsletter/apps.py` | Déclaration de l'app | — |
| `newsletter/client_ghost.py` | Forge le JWT, poste le brouillon, renvoie l'URL d'édition | **Ni** les events **ni** TiBillet |
| `newsletter/collecte.py` | Calcule le tarif d'un event ; rassemble les events du réseau fédéré | La base. **Ni** Ghost **ni** le HTML |
| `newsletter/rendu.py` | Fiches → HTML sémantique ; titre du brouillon | Le template. **Ni** Ghost **ni** la base |
| `newsletter/templates/newsletter/email_evenements.html` | Le HTML aux conventions `kg-*` | — |
| `newsletter/services.py` | Orchestre les trois. **Seul point d'entrée de l'admin** | Les trois modules |
| `TiBillet/settings.py:196` | Ajouter `'newsletter'` à `TENANT_APPS` | — |
| `Administration/admin_tenant.py:3748` | Deux actions détail sur `GhostConfigAdmin` | `newsletter.services` |
| `tests/pytest/test_newsletter_ghost.py` | Toute la couverture | — |

---

## Faits vérifiés du codebase (ne pas les redécouvrir)

| Fait | Valeur |
|---|---|
| `GhostConfig` | `BaseBillet/models.py:3700` — `ghost_url`, `ghost_key`, `get_api_key()`, `ghost_last_log` |
| `GhostConfigAdmin` | `Administration/admin_tenant.py:3740` — a **déjà** `actions_detail = ["test_api_ghost_admin_button"]` |
| Catégories produit | `Product.BILLET = 'B'`, `Product.FREERES = 'F'` |
| Champs `Product` | `categorie_article`, `publish`, `archive` |
| Champs `Price` | `prix` (Decimal), `name`, `free_price`, `publish`, `product` (FK) |
| `Event.published_prices()` | `BaseBillet/models.py:1822` — renvoie les `Price` avec `publish=True` des produits de l'event |
| `Event.full_url` | `BaseBillet/models.py:1497` — **URLField calculé au `save()`**. Gère `is_external`. **À utiliser tel quel.** |
| `Event.reservation_button_name` | `BaseBillet/models.py:1540` — libellé de bouton personnalisé, nullable |
| `Event.categorie` / `Event.ACTION` | `Event.ACTION = "ACT"` — créneaux de bénévolat, à exclure |
| `Event.parent` | FK — les events enfants sont à exclure |
| Variations de `Event.img` | `crop_hdr` = **960×540** (celle qu'on veut), `crop` = 480×270 (trop petite) |
| `build_stdimage_variation_url` | `seo/services.py:88` — renvoie `/media/<base>.<variation><ext>`, ou `None` |
| `PostalAddress` | `name`, `street_address`, `postal_code`, `address_locality` |
| `Configuration` | `organisation` (nom du lieu), `get_tzinfo()` |
| `FederationConfiguration.tags_federation` | M2M vers `Tag` — fédération automatique par tags |
| `get_tenant_uuids_with_event_tags(slugs)` | `seo/services.py` — renvoie un `set` d'uuid de tenants |
| Sémantique des tags | **`tag_filter` = n'afficher QUE / `tag_exclude` = exclure** (redressée par CHANTIER-01) |

---

## Task 1 : L'app `newsletter/` et le client Ghost

**Files:**
- Create: `newsletter/__init__.py`
- Create: `newsletter/apps.py`
- Create: `newsletter/client_ghost.py`
- Modify: `TiBillet/settings.py:196` (ajouter `'newsletter',` à `TENANT_APPS`)
- Test: `tests/pytest/test_newsletter_ghost.py`

**Interfaces:**
- Consomme : rien.
- Produit :
  - `forger_token_ghost(cle_admin_ghost: str) -> str`
  - `creer_brouillon(url_instance_ghost: str, cle_admin_ghost: str, titre: str, contenu_html: str) -> str`
    (renvoie l'**URL d'édition** du brouillon)
  - Exceptions : `ErreurGhost`, `GhostInjoignable(ErreurGhost)`, `GhostCleRefusee(ErreurGhost)`,
    `GhostReponseInattendue(ErreurGhost)`

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `tests/pytest/test_newsletter_ghost.py` :

```python
"""
Tests de la newsletter Ghost.
/ Ghost newsletter tests.

LOCALISATION : tests/pytest/test_newsletter_ghost.py
Voir TECH_DOC/SESSIONS/NEWSLETTER/SPEC.md

Aucun test ne tape une vraie instance Ghost : requests.post est mocke avec
unittest.mock (le paquet `responses` n'est PAS dans le projet).
/ No test hits a real Ghost instance: requests.post is mocked with unittest.mock.
"""

import json
from unittest.mock import MagicMock, patch

import jwt
import pytest
import requests

from newsletter.client_ghost import (
    ErreurGhost,
    GhostCleRefusee,
    GhostInjoignable,
    GhostReponseInattendue,
    creer_brouillon,
    forger_token_ghost,
)

# Une cle Ghost a la forme "<id hexa>:<secret hexa>".
# / A Ghost key looks like "<hex id>:<hex secret>".
CLE_GHOST_DE_TEST = "641f2b1a1c1d1e1f20212223:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def _fausse_reponse_ghost(status_code=201, id_du_post="abc123"):
    """Simule la reponse de Ghost a la creation d'un post."""
    reponse = MagicMock(spec=requests.Response)
    reponse.status_code = status_code
    reponse.ok = 200 <= status_code < 300
    reponse.text = json.dumps({"posts": [{"id": id_du_post}]})
    reponse.json.return_value = {"posts": [{"id": id_du_post}]}
    return reponse


class TestForgerTokenGhost:

    def test_le_token_porte_le_bon_header_et_la_bonne_audience(self):
        """
        Le JWT doit avoir alg=HS256, kid = l'id de la cle, et aud=/admin/.
        C'est le contrat de l'Admin API de Ghost.
        """
        token = forger_token_ghost(CLE_GHOST_DE_TEST)

        identifiant_attendu, secret_hexa = CLE_GHOST_DE_TEST.split(":")

        entete = jwt.get_unverified_header(token)
        assert entete["alg"] == "HS256"
        assert entete["kid"] == identifiant_attendu

        charge_utile = jwt.decode(
            token,
            bytes.fromhex(secret_hexa),
            algorithms=["HS256"],
            audience="/admin/",
        )
        assert charge_utile["aud"] == "/admin/"
        # Ghost refuse tout token dont la duree de vie depasse 5 minutes.
        assert charge_utile["exp"] - charge_utile["iat"] <= 5 * 60


class TestCreerBrouillon:

    def test_le_post_part_en_brouillon_sur_source_html(self):
        """
        Le POST doit viser ?source=html et porter status="draft".
        `status: draft` n'est PAS negociable : on ne publie jamais.
        """
        with patch("newsletter.client_ghost.requests.post",
                   return_value=_fausse_reponse_ghost()) as faux_post:
            creer_brouillon(
                url_instance_ghost="https://ghost.exemple.coop",
                cle_admin_ghost=CLE_GHOST_DE_TEST,
                titre="Agenda du 1 au 8 janvier",
                contenu_html="<h2>Un event</h2>",
            )

        url_appelee = faux_post.call_args[0][0]
        assert url_appelee == "https://ghost.exemple.coop/ghost/api/admin/posts/?source=html"

        corps_envoye = faux_post.call_args.kwargs["json"]
        post_envoye = corps_envoye["posts"][0]
        assert post_envoye["status"] == "draft"
        assert post_envoye["title"] == "Agenda du 1 au 8 janvier"
        assert post_envoye["html"] == "<h2>Un event</h2>"

        entetes = faux_post.call_args.kwargs["headers"]
        assert entetes["Authorization"].startswith("Ghost ")
        assert entetes["Accept-Version"] == "v5.0"

    def test_un_slash_final_dans_lurl_ne_produit_pas_de_double_slash(self):
        """URLField accepte un slash final : il ne doit pas donner //ghost/api/..."""
        with patch("newsletter.client_ghost.requests.post",
                   return_value=_fausse_reponse_ghost()) as faux_post:
            creer_brouillon(
                url_instance_ghost="https://ghost.exemple.coop/",
                cle_admin_ghost=CLE_GHOST_DE_TEST,
                titre="Titre",
                contenu_html="<p>x</p>",
            )

        url_appelee = faux_post.call_args[0][0]
        assert "//ghost/api" not in url_appelee
        assert url_appelee == "https://ghost.exemple.coop/ghost/api/admin/posts/?source=html"

    def test_renvoie_lurl_dedition_du_brouillon(self):
        """On rend au gestionnaire un lien cliquable vers l'editeur Ghost."""
        with patch("newsletter.client_ghost.requests.post",
                   return_value=_fausse_reponse_ghost(id_du_post="65f0a1")):
            url_edition = creer_brouillon(
                url_instance_ghost="https://ghost.exemple.coop",
                cle_admin_ghost=CLE_GHOST_DE_TEST,
                titre="Titre",
                contenu_html="<p>x</p>",
            )

        assert url_edition == "https://ghost.exemple.coop/ghost/#/editor/post/65f0a1"

    def test_une_cle_refusee_leve_GhostCleRefusee(self):
        with patch("newsletter.client_ghost.requests.post",
                   return_value=_fausse_reponse_ghost(status_code=401)):
            with pytest.raises(GhostCleRefusee):
                creer_brouillon(
                    url_instance_ghost="https://ghost.exemple.coop",
                    cle_admin_ghost=CLE_GHOST_DE_TEST,
                    titre="Titre",
                    contenu_html="<p>x</p>",
                )

    def test_un_timeout_leve_GhostInjoignable(self):
        with patch("newsletter.client_ghost.requests.post",
                   side_effect=requests.exceptions.Timeout()):
            with pytest.raises(GhostInjoignable):
                creer_brouillon(
                    url_instance_ghost="https://ghost.exemple.coop",
                    cle_admin_ghost=CLE_GHOST_DE_TEST,
                    titre="Titre",
                    contenu_html="<p>x</p>",
                )

    def test_une_reponse_500_leve_GhostReponseInattendue(self):
        with patch("newsletter.client_ghost.requests.post",
                   return_value=_fausse_reponse_ghost(status_code=500)):
            with pytest.raises(GhostReponseInattendue):
                creer_brouillon(
                    url_instance_ghost="https://ghost.exemple.coop",
                    cle_admin_ghost=CLE_GHOST_DE_TEST,
                    titre="Titre",
                    contenu_html="<p>x</p>",
                )

    def test_toutes_les_erreurs_ghost_derivent_de_ErreurGhost(self):
        """L'appelant doit pouvoir attraper ErreurGhost et rien d'autre."""
        assert issubclass(GhostInjoignable, ErreurGhost)
        assert issubclass(GhostCleRefusee, ErreurGhost)
        assert issubclass(GhostReponseInattendue, ErreurGhost)
```

- [ ] **Step 2 : Lancer les tests et vérifier qu'ils échouent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_newsletter_ghost.py -v
```
Attendu : `ModuleNotFoundError: No module named 'newsletter'` (collection error).

- [ ] **Step 3 : Créer l'app**

`newsletter/__init__.py` : fichier **vide**.

`newsletter/apps.py` :
```python
from django.apps import AppConfig


class NewsletterConfig(AppConfig):
    """
    App newsletter : fabrique des brouillons de newsletter dans une instance Ghost.
    / Newsletter app: builds newsletter drafts inside a Ghost instance.

    LOCALISATION : newsletter/apps.py

    Cette app n'a AUCUN modele : la configuration Ghost du tenant vit deja dans
    BaseBillet.models.GhostConfig (singleton django-solo). Donc aucune migration.
    / This app has NO model: the tenant's Ghost config already lives in GhostConfig.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "newsletter"
```

- [ ] **Step 4 : Déclarer l'app dans `TENANT_APPS`**

Dans `TiBillet/settings.py`, ajouter `'newsletter',` juste après `'comptabilite',` (ligne 196) :

```python
TENANT_APPS = (
    # ... inchange ...
    'crowds',
    'comptabilite',
    'newsletter',
)
```

> `ruff format` est **INTERDIT** sur `settings.py` (fichier pré-existant).

- [ ] **Step 5 : Écrire `newsletter/client_ghost.py`**

```python
"""
Client de l'Admin API de Ghost.
/ Ghost Admin API client.

LOCALISATION : newsletter/client_ghost.py

Ce module ne connait NI les evenements NI TiBillet. Il sait seulement forger un
jeton d'authentification et deposer un brouillon de post dans une instance Ghost.
/ This module knows NOTHING about events or TiBillet. It only forges an auth token
and drops a draft post into a Ghost instance.

POURQUOI DU HTML ET PAS DU LEXICAL (le point contre-intuitif) :
Le contenu d'un post Ghost est stocke en Lexical (JSON avec des cartes typees), mais
ce format n'est PAS documente. En revanche, le convertisseur `?source=html` de Ghost
reconstruit ses cartes natives a partir des conventions de balisage `kg-*` : c'est le
chemin documente et supporte. Voir SPEC §4.
/ Ghost stores Lexical (undocumented). The `?source=html` converter rebuilds native
cards from `kg-*` markup: that's the documented path.
"""

import datetime
import logging

import jwt
import requests

logger = logging.getLogger(__name__)

# Ghost refuse tout jeton dont la duree de vie depasse 5 minutes.
# / Ghost rejects any token living longer than 5 minutes.
DUREE_DE_VIE_DU_TOKEN_EN_SECONDES = 5 * 60

# Au-dela, on considere l'instance Ghost injoignable.
# / Past this, we consider the Ghost instance unreachable.
DELAI_MAX_DE_REPONSE_EN_SECONDES = 15


class ErreurGhost(Exception):
    """Erreur generique de dialogue avec Ghost. / Generic Ghost dialogue error."""


class GhostInjoignable(ErreurGhost):
    """L'instance ne repond pas : DNS, connexion refusee, timeout."""


class GhostCleRefusee(ErreurGhost):
    """Ghost a refuse la cle Admin API (401 / 403)."""


class GhostReponseInattendue(ErreurGhost):
    """Ghost a repondu, mais pas ce qu'on attendait (500, corps illisible...)."""


def forger_token_ghost(cle_admin_ghost):
    """
    Fabrique le jeton JWT court attendu par l'Admin API de Ghost.
    / Build the short-lived JWT expected by the Ghost Admin API.

    La cle Admin a la forme "<identifiant hexa>:<secret hexa>".
    L'identifiant part dans le header (champ `kid`), le secret sert a signer,
    apres avoir ete decode depuis l'hexadecimal vers des octets bruts.
    / The Admin key looks like "<hex id>:<hex secret>".

    :param cle_admin_ghost: la cle Admin API, en clair (str)
    :return: le jeton JWT signe (str)
    """
    identifiant_de_la_cle, secret_hexadecimal = cle_admin_ghost.split(":")

    instant_present = int(datetime.datetime.now().timestamp())

    entete_du_jeton = {
        "alg": "HS256",
        "typ": "JWT",
        "kid": identifiant_de_la_cle,
    }
    charge_utile_du_jeton = {
        "iat": instant_present,
        "exp": instant_present + DUREE_DE_VIE_DU_TOKEN_EN_SECONDES,
        "aud": "/admin/",
    }

    # Le secret est stocke en hexadecimal : Ghost signe avec les OCTETS, pas la chaine.
    # / The secret is hex-encoded: Ghost signs with the raw BYTES, not the string.
    secret_en_octets = bytes.fromhex(secret_hexadecimal)

    return jwt.encode(
        charge_utile_du_jeton,
        secret_en_octets,
        algorithm="HS256",
        headers=entete_du_jeton,
    )


def creer_brouillon(url_instance_ghost, cle_admin_ghost, titre, contenu_html):
    """
    Depose un BROUILLON de post dans Ghost et renvoie son URL d'edition.
    / Drop a DRAFT post into Ghost and return its edit URL.

    LOCALISATION : newsletter/client_ghost.py

    Le post est cree avec status="draft". Il n'est JAMAIS publie, JAMAIS envoye par
    email. L'envoi reste un geste humain, dans l'interface de Ghost.
    / The post is created with status="draft". Never published, never emailed.

    :param url_instance_ghost: l'URL de l'instance (ex: https://ghost.exemple.coop)
    :param cle_admin_ghost: la cle Admin API en clair
    :param titre: le titre du brouillon
    :param contenu_html: le corps, en HTML semantique aux conventions kg-*
    :return: l'URL d'edition du brouillon dans Ghost (str)
    :raises GhostInjoignable, GhostCleRefusee, GhostReponseInattendue
    """
    # URLField accepte un slash final : sans ce nettoyage on produirait //ghost/api/...
    # / URLField allows a trailing slash: without this we'd emit //ghost/api/...
    url_nettoyee = url_instance_ghost.rstrip("/")

    url_de_creation = f"{url_nettoyee}/ghost/api/admin/posts/?source=html"

    entetes = {
        "Authorization": f"Ghost {forger_token_ghost(cle_admin_ghost)}",
        # Recommande par Ghost pour figer la version de l'API.
        # / Recommended by Ghost to pin the API version.
        "Accept-Version": "v5.0",
    }

    corps_de_la_requete = {
        "posts": [
            {
                "title": titre,
                "html": contenu_html,
                # NON NEGOCIABLE : on ne publie jamais, on ne poste qu'un brouillon.
                # / NON-NEGOTIABLE: we never publish, we only post a draft.
                "status": "draft",
            }
        ]
    }

    try:
        reponse = requests.post(
            url_de_creation,
            json=corps_de_la_requete,
            headers=entetes,
            timeout=DELAI_MAX_DE_REPONSE_EN_SECONDES,
        )
    except requests.exceptions.RequestException as erreur_reseau:
        logger.warning(f"creer_brouillon : Ghost injoignable sur {url_nettoyee} — {erreur_reseau}")
        raise GhostInjoignable(f"Instance Ghost injoignable : {erreur_reseau}")

    if reponse.status_code in (401, 403):
        raise GhostCleRefusee(
            f"Ghost a refuse la cle Admin API (HTTP {reponse.status_code})."
        )

    if not reponse.ok:
        raise GhostReponseInattendue(
            f"Ghost a repondu HTTP {reponse.status_code} : {reponse.text[:300]}"
        )

    try:
        identifiant_du_post = reponse.json()["posts"][0]["id"]
    except (ValueError, KeyError, IndexError) as erreur_de_lecture:
        raise GhostReponseInattendue(
            f"Reponse de Ghost illisible : {erreur_de_lecture} — {reponse.text[:300]}"
        )

    return f"{url_nettoyee}/ghost/#/editor/post/{identifiant_du_post}"
```

- [ ] **Step 6 : Lancer les tests et vérifier qu'ils passent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_newsletter_ghost.py -v
```
Attendu : **8 passed**.

- [ ] **Step 7 : Nettoyer et vérifier**

```bash
docker exec lespass_django poetry run ruff check --fix /DjangoFiles/newsletter/
docker exec lespass_django poetry run ruff format /DjangoFiles/newsletter/
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```
`ruff format` est autorisé ici : `newsletter/` ne contient que des fichiers **neufs**.
`settings.py` est pré-existant : **ne pas le formater**.

- [ ] **Step 8 : Commit — NE PAS EXÉCUTER**

**N'exécute AUCUNE commande git.** Affiche seulement, dans ton rapport final, le message
suggéré :

```
feat(newsletter): app newsletter + client de l'Admin API Ghost

Nouvelle app `newsletter` (sans modele, sans migration) et son client Ghost :
forge du JWT court (HS256, aud=/admin/) et depot d'un BROUILLON de post via
POST /ghost/api/admin/posts/?source=html. Le post n'est jamais publie.
```

---

## Task 2 : Le calcul du tarif d'un événement

**Files:**
- Create: `newsletter/collecte.py`
- Test: `tests/pytest/test_newsletter_ghost.py` (ajouter la classe `TestCalculerTarif`)

**Interfaces:**
- Consomme : rien (fonction quasi-pure, elle lit juste les relations de l'`Event`).
- Produit : `calculer_tarif(event) -> str | None`

**L'ordre des cas est un piège.** Un event avec plusieurs prix dont un `free_price` matche à la
fois « prix libre » et « plusieurs prix ». **Le premier cas qui matche gagne**, dans cet ordre
exact : aucun prix → `None` · gratuit · prix libre · un seul prix · plusieurs prix.

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter dans `tests/pytest/test_newsletter_ghost.py` :

```python
from decimal import Decimal
from types import SimpleNamespace

from newsletter.collecte import calculer_tarif


def _faux_produit(categorie, publie=True, archive=False):
    """Simule un Product sans toucher la base. / Fake a Product, no DB."""
    return SimpleNamespace(categorie_article=categorie, publish=publie, archive=archive)


def _faux_prix(montant, produit, prix_libre=False):
    """Simule un Price. `prix` est un Decimal en base. / Fake a Price."""
    return SimpleNamespace(prix=Decimal(str(montant)), product=produit, free_price=prix_libre)


def _faux_event(prix_publies):
    """Simule un Event dont published_prices() renvoie la liste donnee."""
    return SimpleNamespace(published_prices=lambda: prix_publies)


class TestCalculerTarif:

    def test_pas_de_billetterie_renvoie_none(self):
        """Aucun prix publie -> pas de ligne tarif du tout."""
        assert calculer_tarif(_faux_event([])) is None

    def test_produit_hors_billetterie_est_ignore(self):
        """Un produit qui n'est ni BILLET ni FREERES ne fait pas un tarif d'event."""
        from BaseBillet.models import Product
        adhesion = _faux_produit(Product.ADHESION)
        event = _faux_event([_faux_prix(10, adhesion)])
        assert calculer_tarif(event) is None

    def test_produit_archive_est_ignore(self):
        from BaseBillet.models import Product
        billet_archive = _faux_produit(Product.BILLET, archive=True)
        event = _faux_event([_faux_prix(10, billet_archive)])
        assert calculer_tarif(event) is None

    def test_produit_non_publie_est_ignore(self):
        from BaseBillet.models import Product
        billet_cache = _faux_produit(Product.BILLET, publie=False)
        event = _faux_event([_faux_prix(10, billet_cache)])
        assert calculer_tarif(event) is None

    def test_reservation_gratuite_donne_gratuit(self):
        from BaseBillet.models import Product
        gratuit = _faux_produit(Product.FREERES)
        event = _faux_event([_faux_prix(0, gratuit)])
        assert calculer_tarif(event) == "Gratuit"

    def test_billet_a_zero_euro_donne_gratuit(self):
        from BaseBillet.models import Product
        billet = _faux_produit(Product.BILLET)
        event = _faux_event([_faux_prix(0, billet)])
        assert calculer_tarif(event) == "Gratuit"

    def test_prix_unique_donne_le_montant(self):
        from BaseBillet.models import Product
        billet = _faux_produit(Product.BILLET)
        event = _faux_event([_faux_prix(12, billet)])
        assert calculer_tarif(event) == "12 €"

    def test_plusieurs_prix_donne_a_partir_de_au_minimum(self):
        from BaseBillet.models import Product
        billet = _faux_produit(Product.BILLET)
        event = _faux_event([
            _faux_prix(20, billet),
            _faux_prix(12, billet),
            _faux_prix(15, billet),
        ])
        assert calculer_tarif(event) == "À partir de 12 €"

    def test_le_prix_libre_gagne_sur_a_partir_de(self):
        """
        PIEGE : un event avec plusieurs prix dont un `free_price` matche AUSSI le cas
        "plusieurs prix". L'ordre d'evaluation doit faire gagner "prix libre".
        """
        from BaseBillet.models import Product
        billet = _faux_produit(Product.BILLET)
        event = _faux_event([
            _faux_prix(5, billet, prix_libre=True),
            _faux_prix(20, billet),
        ])
        assert calculer_tarif(event) == "Prix libre, à partir de 5 €"

    def test_les_centimes_sont_affiches_seulement_si_utiles(self):
        """12.00 € s'ecrit "12 €", mais 12.50 € garde ses centimes."""
        from BaseBillet.models import Product
        billet = _faux_produit(Product.BILLET)
        assert calculer_tarif(_faux_event([_faux_prix("12.00", billet)])) == "12 €"
        assert calculer_tarif(_faux_event([_faux_prix("12.50", billet)])) == "12,50 €"
```

- [ ] **Step 2 : Lancer les tests et vérifier qu'ils échouent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_newsletter_ghost.py::TestCalculerTarif -v
```
Attendu : `ImportError: cannot import name 'calculer_tarif'`.

- [ ] **Step 3 : Écrire `newsletter/collecte.py` (première moitié)**

```python
"""
Rassemble les evenements du reseau federe et en fait des "fiches".
/ Gather the federated network's events into "fiches" (plain dicts).

LOCALISATION : newsletter/collecte.py

Ce module connait la base. Il ne connait NI Ghost NI le HTML.
/ This module knows the database. It knows NOTHING about Ghost or HTML.
"""

import logging
from decimal import Decimal

from django.utils.translation import gettext as _

from BaseBillet.models import Product

logger = logging.getLogger(__name__)


def _formater_montant(montant):
    """
    Met un Decimal en forme francaise, sans centimes inutiles.
    / Format a Decimal the French way, dropping useless cents.

    12.00 -> "12"     12.50 -> "12,50"

    ATTENTION : ne PAS passer par normalize(), qui rabote les zeros significatifs
    (Decimal("12.50").normalize() donne 12.5 -> on afficherait "12,5", pas "12,50").
    / Do NOT use normalize(): it strips meaningful zeros ("12,5" instead of "12,50").
    """
    montant_est_un_entier = montant == montant.to_integral_value()
    if montant_est_un_entier:
        return str(int(montant))

    # Deux decimales, virgule francaise. / Two decimals, French comma.
    return f"{montant:.2f}".replace(".", ",")


def calculer_tarif(event):
    """
    Rend le tarif d'un evenement, sous forme de texte pret a afficher.
    / Return an event's price as display-ready text.

    LOCALISATION : newsletter/collecte.py

    On part de event.published_prices() (les Price avec publish=True), puis on ne
    garde que les produits de BILLETTERIE (BILLET ou FREERES) publies et non archives.
    Un produit d'adhesion ou une recharge cashless ne fait pas le tarif d'un event.
    / Start from published_prices(), keep only published, non-archived ticketing products.

    L'ORDRE DES CAS EST SIGNIFICATIF : un event a plusieurs prix dont un a prix libre
    matche a la fois "prix libre" et "plusieurs prix". Le premier cas gagne.
    / CASE ORDER MATTERS: the first matching case wins.

    :param event: un Event
    :return: le tarif en texte, ou None si l'event n'a pas de billetterie
    """
    prix_de_billetterie = []
    for prix in event.published_prices():
        produit = prix.product

        produit_est_de_la_billetterie = produit.categorie_article in (
            Product.BILLET,
            Product.FREERES,
        )
        if not produit_est_de_la_billetterie:
            continue

        if not produit.publish or produit.archive:
            continue

        prix_de_billetterie.append(prix)

    # Cas 1 : pas de billetterie du tout -> aucune ligne tarif.
    # / Case 1: no ticketing at all.
    if not prix_de_billetterie:
        return None

    montants = [prix.prix for prix in prix_de_billetterie]
    categories = {prix.product.categorie_article for prix in prix_de_billetterie}

    # Cas 2 : que de la reservation gratuite, ou tous les montants a zero.
    # / Case 2: free booking only, or every amount is zero.
    tous_les_montants_sont_nuls = all(montant == 0 for montant in montants)
    if categories == {Product.FREERES} or tous_les_montants_sont_nuls:
        return _("Gratuit")

    # Cas 3 : prix libre. Le montant en base est le MINIMUM accepte.
    # / Case 3: open price. The stored amount is the MINIMUM accepted.
    montants_a_prix_libre = [prix.prix for prix in prix_de_billetterie if prix.free_price]
    if montants_a_prix_libre:
        minimum = _formater_montant(min(montants_a_prix_libre))
        return _("Prix libre, à partir de %(montant)s €") % {"montant": minimum}

    # Cas 4 : un seul tarif.
    # / Case 4: a single price.
    if len(montants) == 1:
        return _("%(montant)s €") % {"montant": _formater_montant(montants[0])}

    # Cas 5 : plusieurs tarifs -> on annonce le plus bas.
    # / Case 5: several prices -> announce the lowest.
    minimum = _formater_montant(min(montants))
    return _("À partir de %(montant)s €") % {"montant": minimum}
```

- [ ] **Step 4 : Lancer les tests et vérifier qu'ils passent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_newsletter_ghost.py -v
```
Attendu : **18 passed** (8 de la Task 1 + 10 ici). Aucun `skip` possible ici : ces tests ne
touchent pas la base.

- [ ] **Step 5 : Commit — NE PAS EXÉCUTER**

```
feat(newsletter): calcul du tarif d'un evenement

calculer_tarif() : gratuit / prix libre / prix unique / a partir de.
Ne retient que les produits de billetterie (BILLET, FREERES) publies et non
archives. L'ordre des cas fait gagner "prix libre" sur "a partir de".
```

---

## Task 3 : La collecte des événements du réseau fédéré

**Files:**
- Modify: `newsletter/collecte.py` (ajouter la collecte sous `calculer_tarif`)
- Test: `tests/pytest/test_newsletter_ghost.py` (ajouter `TestCollecte`)

**Interfaces:**
- Consomme : `calculer_tarif(event)` (Task 2).
- Produit :
  - `collecter_evenements_du_reseau(nombre_de_jours: int) -> list[dict]`
  - Chaque fiche est un `dict` aux clés : `nom`, `date_debut` (datetime aware),
    `date_fin` (datetime aware | None), `organisateur` (str), `description_courte` (str),
    `description_longue` (str — **du HTML**), `lieu` (str), `image_url` (str | None),
    `tarif` (str | None), `url_event` (str), `libelle_bouton` (str).
  - Trié par `date_debut` croissante.

**Le contrat, c'est l'agenda** — à une exception près, assumée.

La newsletter doit montrer le même ensemble d'événements que `EventMVT.federated_events_filter`
(`BaseBillet/views.py:1966-1993`). En oublier un filtre, c'est envoyer aux abonnés des événements
qu'ils ne retrouveront pas sur le site. Les filtres **exacts** du moteur sont :

```
published=True · datetime >= hier · exclude(categorie=ACTION) · private=False (voisins seulement)
· tag_filter (n'afficher QUE) · tag_exclude (exclure)
```

**Deux écarts, tous deux volontaires :**

1. **`archived=False` — filtre EN PLUS.** Le moteur de l'agenda **ne filtre pas** `archived`
   (vérifié : le mot n'apparaît nulle part dans `BaseBillet/views.py`). Or `seo/services.py` le
   filtre à **quatre** endroits, avec ce commentaire : *« un event archivé (retiré de l'agenda) ne
   doit plus apparaître »*. **C'est donc l'agenda qui a un bug**, pas la newsletter : la carte et
   l'explorateur cachent les événements archivés, l'agenda les affiche encore.
   On **garde `archived=False`** ici — envoyer par email un événement archivé serait absurde — et
   on **signale le bug de l'agenda au mainteneur** en fin de chantier. Ce n'est pas à ce plan de
   le corriger.

2. **`parent__isnull=True` — NE PAS l'ajouter.** Il serait redondant : `Event.save()`
   (`models.py:1905`) force `categorie = ACTION` sur tout event ayant un `parent`. L'`exclude(ACTION)`
   les couvre déjà.

**Sur la timezone :** les dates sont rendues dans la timezone **active** (celle du tenant qui
génère la newsletter), pas dans celle du tenant propriétaire de l'événement. C'est exactement ce
que fait l'agenda. Un abonné lit donc toutes les dates dans un même fuseau — c'est le comportement
voulu. `Configuration.get_tzinfo()` du voisin n'est **pas** utilisé.

**Deux pièges multi-tenant :**
1. Les `Tag` sont des objets **par tenant**. `FederatedPlace.tag_filter` pointe vers des `Tag` du
   tenant **courant**, les events des voisins portent des `Tag` de **leur** schéma. Le matching se
   fait **par `slug`**, et les slugs doivent être extraits **avant** d'entrer dans le
   `tenant_context()` du voisin.
2. **`tenant_context()`, jamais `schema_context()`** : ce dernier pose un `FakeTenant` et tout
   modèle lisant `connection.tenant.uuid` plante (`tests/PIEGES.md`).

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter dans `tests/pytest/test_newsletter_ghost.py` :

```python
from django_tenants.utils import tenant_context

from BaseBillet.models import Event
from Customers.models import Client
from newsletter.collecte import collecter_evenements_du_reseau


# --- Fixtures : base de DEV, lecture seule (cf. Contrainte globale 7) ---

@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de test DB).
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()


@pytest.fixture
def tenant_lespass():
    tenant = Client.objects.filter(schema_name="lespass").first()
    if not tenant:
        pytest.skip("Seed demo_data_v2 absent : pas de tenant 'lespass'.")
    return tenant


FENETRE_LARGE_EN_JOURS = 365


def _evenements_eligibles_chez(tenant, est_un_voisin, slugs_filter, slugs_exclude):
    """
    Calcule, DANS le contexte du tenant donne, les events qui DOIVENT etre collectes.
    / Compute, INSIDE the given tenant's context, the events that MUST be collected.

    C'est l'ORACLE des tests : on refait le calcul a la main, independamment du code
    teste, et on compare. Sans oracle, un `return []` ferait passer tous les tests.
    / This is the tests' ORACLE. Without it, a `return []` would pass everything.
    """
    from datetime import timedelta

    from django.utils import timezone

    debut = timezone.now() - timedelta(days=1)
    fin = timezone.now() + timedelta(days=FENETRE_LARGE_EN_JOURS)

    with tenant_context(tenant):
        evenements = Event.objects.filter(
            published=True,
            archived=False,
            datetime__gte=debut,
            datetime__lt=fin,
        ).exclude(categorie=Event.ACTION)

        if est_un_voisin:
            evenements = evenements.filter(private=False)

        eligibles = set()
        for event in evenements.distinct():
            slugs_de_levent = {tag.slug for tag in event.tag.all()}
            if slugs_filter and not (slugs_de_levent & set(slugs_filter)):
                continue
            if slugs_exclude and (slugs_de_levent & set(slugs_exclude)):
                continue
            eligibles.add(event.full_url)

    return eligibles


@pytest.mark.django_db
class TestCollecte:

    # --- Tests d'ORACLE : ils echouent si la collecte renvoie une liste vide ---

    def test_les_events_du_tenant_courant_remontent_tous(self, tenant_lespass):
        """
        ORACLE. Tout event publie, futur, non archive et non-ACTION du tenant courant
        DOIT figurer dans les fiches. Un `return []` fait echouer ce test.
        """
        attendus = _evenements_eligibles_chez(
            tenant_lespass, est_un_voisin=False, slugs_filter=[], slugs_exclude=[]
        )
        if not attendus:
            pytest.skip("Seed : le tenant courant n'a aucun event a venir.")

        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(FENETRE_LARGE_EN_JOURS)

        urls_collectees = {fiche["url_event"] for fiche in fiches}
        manquants = attendus - urls_collectees
        assert not manquants, f"Events du tenant courant NON collectes : {manquants}"

    def test_les_events_eligibles_dun_voisin_federe_remontent(self, tenant_lespass):
        """
        ORACLE — LE TEST QUI PROUVE LE CROSS-SCHEMA.
        Pour chaque FederatedPlace, on calcule dans le schema du VOISIN les events qui
        doivent remonter (en appliquant ses tag_filter / tag_exclude et le veto private),
        puis on verifie qu'ils sont bien dans les fiches.
        """
        from BaseBillet.models import FederatedPlace

        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(FENETRE_LARGE_EN_JOURS)
            urls_collectees = {fiche["url_event"] for fiche in fiches}

            lieux_federes = []
            for place in FederatedPlace.objects.select_related("tenant").prefetch_related(
                "tag_filter", "tag_exclude"
            ):
                lieux_federes.append({
                    "tenant": place.tenant,
                    "slugs_filter": [tag.slug for tag in place.tag_filter.all()],
                    "slugs_exclude": [tag.slug for tag in place.tag_exclude.all()],
                })

        if not lieux_federes:
            pytest.skip("Seed : le tenant courant ne federe aucun voisin.")

        au_moins_un_voisin_a_des_events = False
        for lieu in lieux_federes:
            if lieu["tenant"].schema_name == tenant_lespass.schema_name:
                continue

            attendus = _evenements_eligibles_chez(
                lieu["tenant"],
                est_un_voisin=True,
                slugs_filter=lieu["slugs_filter"],
                slugs_exclude=lieu["slugs_exclude"],
            )
            if attendus:
                au_moins_un_voisin_a_des_events = True

            manquants = attendus - urls_collectees
            assert not manquants, (
                f"Events du voisin '{lieu['tenant'].schema_name}' NON collectes : {manquants}"
            )

        if not au_moins_un_voisin_a_des_events:
            pytest.skip("Seed : aucun voisin n'a d'event eligible a venir.")

    def test_un_tag_exclu_dun_voisin_ne_remonte_pas(self, tenant_lespass):
        """
        ORACLE inverse. Un event d'un voisin portant un tag de son `tag_exclude` ne doit
        JAMAIS figurer dans les fiches. Matching par SLUG (les Tag sont par tenant).
        """
        from BaseBillet.models import FederatedPlace

        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(FENETRE_LARGE_EN_JOURS)
            urls_collectees = {fiche["url_event"] for fiche in fiches}

            lieux_avec_exclusion = []
            for place in FederatedPlace.objects.select_related("tenant").prefetch_related(
                "tag_exclude"
            ):
                slugs = [tag.slug for tag in place.tag_exclude.all()]
                if slugs and place.tenant.schema_name != tenant_lespass.schema_name:
                    lieux_avec_exclusion.append({"tenant": place.tenant, "slugs": slugs})

        if not lieux_avec_exclusion:
            pytest.skip("Seed : aucun voisin n'a de tag_exclude configure.")

        for lieu in lieux_avec_exclusion:
            with tenant_context(lieu["tenant"]):
                urls_a_exclure = set()
                for event in Event.objects.filter(
                    tag__slug__in=lieu["slugs"], published=True
                ).distinct():
                    urls_a_exclure.add(event.full_url)

            fuites = urls_a_exclure & urls_collectees
            assert not fuites, (
                f"Events du voisin '{lieu['tenant'].schema_name}' portant un tag exclu "
                f"{lieu['slugs']} et pourtant collectes : {fuites}"
            )

    def test_aucun_event_prive_dun_voisin_ne_remonte(self, tenant_lespass):
        """
        Un event `private` ("non federable") d'un VOISIN ne doit jamais fuiter.
        Sur le tenant courant, en revanche, il reste dans SA propre newsletter :
        `private` veut dire "non federable", pas "secret". C'est ce que fait l'agenda.

        On compare par `full_url` et non par nom : deux tenants peuvent avoir des events
        homonymes, ce qui produirait un faux echec.
        """
        from BaseBillet.models import FederatedPlace

        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(FENETRE_LARGE_EN_JOURS)
            urls_collectees = {fiche["url_event"] for fiche in fiches}
            voisins = [place.tenant for place in FederatedPlace.objects.select_related("tenant")]

        for voisin in voisins:
            if voisin.schema_name == tenant_lespass.schema_name:
                continue
            with tenant_context(voisin):
                urls_privees = set(
                    Event.objects.filter(private=True).values_list("full_url", flat=True)
                )
            fuites = urls_privees & urls_collectees
            assert not fuites, f"Events prives de '{voisin.schema_name}' ayant fuite : {fuites}"

    # --- Tests de forme ---

    def test_la_fenetre_est_respectee(self, tenant_lespass):
        """Aucun event collecte ne doit tomber hors de la fenetre demandee."""
        from datetime import timedelta

        from django.utils import timezone

        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(nombre_de_jours=30)

        borne_basse = timezone.now() - timedelta(days=2)   # marge : la collecte part d'hier
        borne_haute = timezone.now() + timedelta(days=31)  # marge d'un jour
        for fiche in fiches:
            assert borne_basse <= fiche["date_debut"] <= borne_haute, (
                f"'{fiche['nom']}' est hors de la fenetre de 30 jours."
            )

    def test_les_fiches_sont_triees_par_date_croissante(self, tenant_lespass):
        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(FENETRE_LARGE_EN_JOURS)

        dates = [fiche["date_debut"] for fiche in fiches]
        assert dates == sorted(dates)

    def test_chaque_fiche_porte_toutes_les_cles_du_contrat(self, tenant_lespass):
        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(FENETRE_LARGE_EN_JOURS)

        if not fiches:
            pytest.skip("Seed : aucun event a venir, rien a verifier.")

        cles_attendues = {
            "nom", "date_debut", "date_fin", "organisateur", "description_courte",
            "description_longue", "lieu", "image_url", "tarif", "url_event",
            "libelle_bouton",
        }
        for fiche in fiches:
            assert cles_attendues == set(fiche.keys())

    def test_les_urls_sont_absolues(self, tenant_lespass):
        """Un email ne sait pas resoudre une URL relative."""
        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(FENETRE_LARGE_EN_JOURS)

        if not fiches:
            pytest.skip("Seed : aucun event a venir.")

        for fiche in fiches:
            assert fiche["url_event"].startswith("http"), fiche["url_event"]
            if fiche["image_url"]:
                assert fiche["image_url"].startswith("http"), fiche["image_url"]
```

> **Pourquoi ces quatre premiers tests sont indispensables.** Sans eux, `TestCollecte` passerait
> **intégralement à vide** : un `return []` dans `collecter_evenements_du_reseau` ferait verdir
> tous les tests de forme (boucle sur une liste vide, `[] == sorted([])`, intersection vide). Les
> tests d'**oracle** recalculent à la main, dans le schéma de chaque tenant, l'ensemble attendu —
> et **échouent** si la collecte ne le produit pas. C'est le pattern déjà utilisé dans
> `tests/pytest/test_federation_tags_semantique.py`.

- [ ] **Step 2 : Lancer les tests et vérifier qu'ils échouent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_newsletter_ghost.py::TestCollecte -v
```
Attendu : `ImportError: cannot import name 'collecter_evenements_du_reseau'`.

- [ ] **Step 3 : Compléter `newsletter/collecte.py`**

Ajouter ces imports en tête du fichier (après ceux de la Task 2) :

```python
from datetime import timedelta

from django.db import connection
from django.utils import timezone
from django_tenants.utils import tenant_context

from BaseBillet.models import (
    Configuration,
    Event,
    FederationConfiguration,
    FederatedPlace,
    Product,
)
from Customers.models import Client
from seo.services import build_stdimage_variation_url, get_tenant_uuids_with_event_tags
```

Puis, sous `calculer_tarif`, ajouter :

```python
# La variation 960x540 : `crop` (480x270) est trop petite pour un email sur ecran dense.
# / The 960x540 variation: `crop` (480x270) is too small for a modern email.
VARIATION_IMAGE_POUR_EMAIL = "crop_hdr"


def _construire_liste_des_tenants(tenant_courant):
    """
    Construit la liste des tenants a parcourir, avec leurs filtres de tags.
    / Build the list of tenants to walk through, with their tag filters.

    LOCALISATION : newsletter/collecte.py

    Trois sources, dans cet ordre :
    1. le tenant courant lui-meme (aucun filtre) ;
    2. ses lieux federes choisis a la main (FederatedPlace, avec leurs deux filtres) ;
    3. la federation automatique par tags (FederationConfiguration.tags_federation) :
       les tenants du reseau qui ont un event public portant un des tags choisis. On ne
       veut d'eux QUE ces events-la, d'ou tag_filter (et non tag_exclude).

    Les SLUGS des tags sont extraits ICI, dans le contexte du tenant courant. Les objets
    Tag appartiennent au schema de CHAQUE tenant : comparer les pk ne marcherait pas.
    / Tag SLUGS are extracted HERE, in the current tenant's context.

    La liste est DEDOUBLONNEE : FederatedPlace.tenant n'est pas unique et peut meme
    pointer vers le tenant courant.
    / The list is DEDUPLICATED.

    :param tenant_courant: le Client du tenant qui genere la newsletter
    :return: list[dict] avec les cles `tenant`, `slugs_filter`, `slugs_exclude`
    """
    tenants_a_parcourir = []
    uuids_deja_vus = set()

    # 1. Le tenant courant, sans aucun filtre.
    # / 1. The current tenant, unfiltered.
    tenants_a_parcourir.append({
        "tenant": tenant_courant,
        "slugs_filter": [],
        "slugs_exclude": [],
    })
    uuids_deja_vus.add(str(tenant_courant.uuid))

    # 2. Les lieux federes choisis a la main.
    # / 2. Hand-picked federated places.
    lieux_federes = FederatedPlace.objects.select_related("tenant").prefetch_related(
        "tag_filter", "tag_exclude"
    )
    for lieu in lieux_federes:
        uuid_du_voisin = str(lieu.tenant.uuid)
        if uuid_du_voisin in uuids_deja_vus:
            continue
        uuids_deja_vus.add(uuid_du_voisin)

        tenants_a_parcourir.append({
            "tenant": lieu.tenant,
            "slugs_filter": [tag.slug for tag in lieu.tag_filter.all()],
            "slugs_exclude": [tag.slug for tag in lieu.tag_exclude.all()],
        })

    # 3. La federation automatique par tags.
    # / 3. Tag-based auto federation.
    slugs_de_federation = [
        tag.slug for tag in FederationConfiguration.get_solo().tags_federation.all()
    ]
    if slugs_de_federation:
        uuids_thematiques = get_tenant_uuids_with_event_tags(slugs_de_federation)
        uuids_a_ajouter = uuids_thematiques - uuids_deja_vus
        for tenant_thematique in Client.objects.filter(uuid__in=uuids_a_ajouter):
            tenants_a_parcourir.append({
                "tenant": tenant_thematique,
                # On ne veut de ce tenant QUE ses events thematiques, pas tout son agenda.
                # / We only want this tenant's thematic events, not its whole agenda.
                "slugs_filter": slugs_de_federation,
                "slugs_exclude": [],
            })

    return tenants_a_parcourir


def _formater_lieu(adresse_postale):
    """
    Met une PostalAddress en une ligne lisible. / Render a PostalAddress on one line.

    :param adresse_postale: une PostalAddress, ou None
    :return: le lieu en texte, ou "" si pas d'adresse
    """
    if not adresse_postale:
        return ""

    morceaux = []
    for morceau in (
        adresse_postale.name,
        adresse_postale.street_address,
        adresse_postale.postal_code,
        adresse_postale.address_locality,
    ):
        if morceau:
            morceaux.append(str(morceau).strip())

    return ", ".join(morceaux)


def _construire_fiche(event, domaine_du_proprietaire, nom_de_lorganisateur):
    """
    Transforme un Event en "fiche" : un dict plat, pret pour le template.
    / Turn an Event into a flat dict, ready for the template.

    LOCALISATION : newsletter/collecte.py

    APPELE DEPUIS le tenant PROPRIETAIRE de l'event (on est dans son tenant_context).
    / CALLED FROM the event's OWNING tenant context.

    :param event: un Event
    :param domaine_du_proprietaire: le domaine du tenant qui organise (str)
    :param nom_de_lorganisateur: Configuration.organisation du proprietaire (str)
    :return: le dict de la fiche
    """
    # L'image : URL ABSOLUE sur le domaine du PROPRIETAIRE. Un email ne resout pas les
    # URLs relatives, et l'event peut appartenir a un voisin.
    # / Image: ABSOLUTE URL on the OWNER's domain.
    image_url = None
    if event.img:
        chemin_de_limage = build_stdimage_variation_url(
            event.img.name, VARIATION_IMAGE_POUR_EMAIL
        )
        if chemin_de_limage:
            image_url = f"https://{domaine_du_proprietaire}{chemin_de_limage}"

    # Le lien "Reserver" : on utilise event.full_url TEL QUEL. Ce champ est calcule a
    # chaque save() et gere DEJA le cas is_external (il pointe alors vers le site tiers).
    # Le reconstruire a la main enverrait les abonnes vers une page de reservation qui
    # n'existe pas pour les events externes.
    # / Use event.full_url AS IS: it already handles is_external.
    url_event = event.full_url or ""

    libelle_bouton = event.reservation_button_name or _("Réserver")

    return {
        "nom": event.name,
        "date_debut": event.datetime,
        "date_fin": event.end_datetime,
        "organisateur": nom_de_lorganisateur,
        "description_courte": event.short_description or "",
        # ATTENTION : long_description est du HTML (widget Wysiwyg dans l'admin).
        # Le template l'emet BRUT, sans <p> autour. Voir SPEC §7.2.
        # / long_description is HTML (Wysiwyg widget). Emitted RAW by the template.
        "description_longue": event.long_description or "",
        "lieu": _formater_lieu(event.postal_address),
        "image_url": image_url,
        "tarif": calculer_tarif(event),
        "url_event": url_event,
        "libelle_bouton": libelle_bouton,
    }


def collecter_evenements_du_reseau(nombre_de_jours):
    """
    Rassemble les evenements a venir du tenant courant ET de son reseau federe.
    / Gather upcoming events from the current tenant AND its federated network.

    LOCALISATION : newsletter/collecte.py

    LA REGLE D'OR : montrer LE MEME ENSEMBLE d'evenements que l'agenda du site
    (EventMVT.federated_events_filter, BaseBillet/views.py). Chaque filtre applique ici
    existe parce que le moteur de l'agenda l'applique. En oublier un, c'est envoyer aux
    abonnes des evenements qu'ils ne retrouveront pas sur le site.
    / GOLDEN RULE: show the SAME event set as the site's agenda.

    C'est possible sans aucun appel HTTP entre instances : FederatedPlace.tenant est une
    FK vers Client, donc les voisins sont d'autres SCHEMAS de la meme base Postgres.
    / No HTTP call between instances: neighbours are other SCHEMAS of the same database.

    :param nombre_de_jours: la largeur de la fenetre (7 ou 30)
    :return: la liste des fiches, triee par date de debut croissante
    """
    tenant_courant = connection.tenant

    # On part d'hier, comme l'agenda : un event commence hier soir est encore d'actualite.
    # / Start yesterday, like the agenda does.
    debut_de_la_fenetre = timezone.now() - timedelta(days=1)
    fin_de_la_fenetre = timezone.now() + timedelta(days=nombre_de_jours)

    # Les slugs sont extraits ICI, dans le contexte du tenant courant.
    # / Slugs are extracted HERE, in the current tenant's context.
    tenants_a_parcourir = _construire_liste_des_tenants(tenant_courant)

    toutes_les_fiches = []

    for entree in tenants_a_parcourir:
        tenant = entree["tenant"]
        slugs_filter = entree["slugs_filter"]
        slugs_exclude = entree["slugs_exclude"]

        # Un voisin mal configure (sans domaine primaire) ne doit pas faire echouer TOUT
        # le brouillon : on le saute en le signalant.
        # / A misconfigured neighbour must not kill the whole draft.
        domaine_primaire = tenant.get_primary_domain()
        if not domaine_primaire:
            logger.warning(
                f"collecter_evenements_du_reseau : le tenant '{tenant.schema_name}' n'a pas "
                f"de domaine primaire. Ses evenements sont ignores."
            )
            continue

        # tenant_context() et NON schema_context() : ce dernier pose un FakeTenant, et
        # tout modele qui lit connection.tenant.uuid plante. Voir tests/PIEGES.md.
        # / tenant_context(), NOT schema_context().
        with tenant_context(tenant):
            evenements = Event.objects.select_related("postal_address").prefetch_related(
                "tag", "products", "products__prices"
            ).filter(
                published=True,
                datetime__gte=debut_de_la_fenetre,
                datetime__lt=fin_de_la_fenetre,
                # ECART ASSUME avec l'agenda : le moteur de l'agenda ne filtre PAS
                # `archived`, alors que seo/services.py le filtre partout ("un event
                # archive, retire de l'agenda, ne doit plus apparaitre"). C'est l'agenda
                # qui a un bug. On n'envoie pas un event archive par email.
                # / DELIBERATE divergence: the agenda engine forgets this filter; the SEO
                # cache applies it everywhere. We never email an archived event.
                archived=False,
            ).exclude(
                # Les Actions sont des creneaux de benevolat : ils s'affichent dans la
                # page de leur event parent, jamais seuls. Inutile d'ajouter un filtre sur
                # `parent` : Event.save() force categorie=ACTION des qu'il y a un parent.
                # / Actions are volunteering slots, shown inside their parent event.
                # No need to filter on `parent`: save() forces ACTION whenever parent is set.
                categorie=Event.ACTION,
            )

            # Le veto `private` ne s'applique QU'AUX VOISINS, comme dans l'agenda :
            # `private` veut dire "non federable", pas "secret". Un event prive du tenant
            # courant reste donc dans SA propre newsletter.
            # / The `private` veto applies to NEIGHBOURS only, like the agenda does.
            tenant_est_un_voisin = tenant.uuid != tenant_courant.uuid
            if tenant_est_un_voisin:
                evenements = evenements.filter(private=False)

            # Les deux filtres de tags, dans le sens annonce par les libelles de l'admin.
            # Matching par SLUG : les Tag appartiennent au schema de chaque tenant.
            # / The two tag filters, matching the admin labels. Slug-based.
            if slugs_filter:
                evenements = evenements.filter(tag__slug__in=slugs_filter)
            if slugs_exclude:
                evenements = evenements.exclude(tag__slug__in=slugs_exclude)

            # distinct() : un .filter() sur un M2M duplique une ligne par tag qui matche.
            # / distinct(): an M2M .filter() yields one row per matching tag.
            evenements = evenements.distinct()

            # L'organisateur est lu DANS le contexte du proprietaire : la newsletter
            # melange plusieurs lieux, il faut dire qui organise quoi.
            # / The organiser is read INSIDE the owner's context.
            nom_de_lorganisateur = Configuration.get_solo().organisation

            for event in evenements:
                toutes_les_fiches.append(
                    _construire_fiche(
                        event,
                        domaine_primaire.domain,
                        nom_de_lorganisateur,
                    )
                )

    toutes_les_fiches.sort(key=lambda fiche: fiche["date_debut"])
    return toutes_les_fiches
```

- [ ] **Step 4 : Lancer les tests et vérifier qu'ils passent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_newsletter_ghost.py -v
```
Attendu : **0 failed**. Environ 26 tests (18 + 8), dont certains peuvent se mettre en `skip` si
le seed `demo_data_v2` est incomplet — c'est prévu. **Le nombre exact importe peu ; ce qui compte,
c'est zéro échec.**

- [ ] **Step 5 : Nettoyer**

```bash
docker exec lespass_django poetry run ruff check --fix /DjangoFiles/newsletter/
docker exec lespass_django poetry run ruff format /DjangoFiles/newsletter/
```

- [ ] **Step 6 : Commit — NE PAS EXÉCUTER**

```
feat(newsletter): collecte des evenements du reseau federe

collecter_evenements_du_reseau() lit les Event COMPLETS des schemas voisins via
tenant_context() (les voisins sont d'autres schemas de la meme base). Reprend tous
les filtres de l'agenda pour montrer le meme ensemble d'evenements : private (voisins
seulement), archived, ACTION, events enfants, et les deux filtres de tags par slug.
```

---

## Task 4 : Le rendu HTML

**Files:**
- Create: `newsletter/rendu.py`
- Create: `newsletter/templates/newsletter/email_evenements.html`
- Test: `tests/pytest/test_newsletter_ghost.py` (ajouter `TestRendu`)

**Interfaces:**
- Consomme : les fiches produites par `collecter_evenements_du_reseau` (Task 3).
- Produit :
  - `rendre_newsletter_html(fiches: list[dict], date_debut, date_fin) -> str`
  - `titre_de_la_newsletter(date_debut, date_fin) -> str`

**La règle absolue : AUCUN attribut `style=`.** L'apparence de la newsletter est le travail de
Ghost (ses réglages de design : couleurs, polices, style des boutons). En stylant nous-mêmes, on
court-circuiterait ce système et on deviendrait responsable de la compatibilité Outlook / Gmail /
mode sombre. On émet du HTML **sémantique** que Ghost reconvertit en cartes natives :

| Balise émise | Carte Ghost obtenue |
|---|---|
| `<figure><img><figcaption>` | carte **image**, avec légende |
| `<div class="kg-button-card kg-align-center"><a class="kg-btn" href>` | carte **bouton** |
| `<hr>` | carte **divider** |
| `<h2>`, `<p>` | titre de section, paragraphes |

`kg-align-center` est valide ; **`kg-align-right` n'existe pas** (vérifié dans `button-parser.ts`).

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter dans `tests/pytest/test_newsletter_ghost.py` :

```python
from django.utils import timezone

from newsletter.rendu import rendre_newsletter_html, titre_de_la_newsletter


def _fiche_de_test(**surcharges):
    fiche = {
        "nom": "Concert de soutien",
        "date_debut": timezone.now(),
        "date_fin": None,
        "organisateur": "La Maison des Communs",
        "description_courte": "Un concert pour la caisse de solidarité",
        "description_longue": "<p>Venez <strong>nombreux</strong> !</p>",
        "lieu": "L'atelier partagé, 12 rue des Lilas, 69100, Villeurbanne",
        "image_url": "https://demo-tibillet.ovh/media/images/concert.crop_hdr.jpg",
        "tarif": "Prix libre, à partir de 5 €",
        "url_event": "https://demo-tibillet.ovh/event/concert-de-soutien/",
        "libelle_bouton": "Réserver",
    }
    fiche.update(surcharges)
    return fiche


class TestRendu:

    def test_le_html_ne_contient_aucun_style_inline(self):
        """
        NON-REGRESSION sur la regle du chantier : l'apparence est le travail de Ghost.
        Un style inline court-circuiterait ses reglages de design newsletter.
        """
        html = rendre_newsletter_html(
            [_fiche_de_test()], timezone.now(), timezone.now()
        )
        assert "style=" not in html
        assert "<table" not in html  # pas de mise en page par tableau

    def test_le_bouton_utilise_les_conventions_kg_de_ghost(self):
        """Sans ces classes exactes, Ghost n'en fait PAS une carte bouton native."""
        html = rendre_newsletter_html(
            [_fiche_de_test()], timezone.now(), timezone.now()
        )
        assert 'class="kg-button-card kg-align-center"' in html
        assert 'class="kg-btn"' in html
        assert 'href="https://demo-tibillet.ovh/event/concert-de-soutien/"' in html
        assert "Réserver" in html

    def test_limage_est_une_figure_avec_legende(self):
        """<figure><img><figcaption> -> carte image native AVEC legende."""
        html = rendre_newsletter_html(
            [_fiche_de_test()], timezone.now(), timezone.now()
        )
        assert "<figure>" in html
        assert 'src="https://demo-tibillet.ovh/media/images/concert.crop_hdr.jpg"' in html
        assert "<figcaption>" in html

    def test_un_event_sans_image_ne_produit_pas_de_figure_vide(self):
        html = rendre_newsletter_html(
            [_fiche_de_test(image_url=None)], timezone.now(), timezone.now()
        )
        assert "<figure>" not in html

    def test_la_description_longue_est_emise_en_html_brut(self):
        """
        long_description vient d'un widget Wysiwyg : c'est DEJA du HTML.
        L'echapper afficherait "&lt;strong&gt;" aux abonnes.
        """
        html = rendre_newsletter_html(
            [_fiche_de_test()], timezone.now(), timezone.now()
        )
        assert "<strong>nombreux</strong>" in html
        assert "&lt;strong&gt;" not in html

    def test_chaque_event_est_precede_dun_separateur(self):
        """
        <hr> -> carte divider dans Ghost. Le template en emet UN par fiche.
        On COMPTE : un simple `"<hr>" in html` passerait deja avec une seule fiche et
        ne prouverait donc pas la separation.
        """
        html = rendre_newsletter_html(
            [_fiche_de_test(nom="Premier"), _fiche_de_test(nom="Second")],
            timezone.now(), timezone.now(),
        )
        assert html.count("<hr>") == 2
        assert "Premier" in html
        assert "Second" in html

    def test_un_event_sans_tarif_naffiche_pas_de_ligne_tarif(self):
        html = rendre_newsletter_html(
            [_fiche_de_test(tarif=None)], timezone.now(), timezone.now()
        )
        assert "Prix libre" not in html

    def test_le_titre_porte_les_deux_dates(self):
        from datetime import datetime
        debut = timezone.make_aware(datetime(2026, 8, 1))
        fin = timezone.make_aware(datetime(2026, 8, 31))
        titre = titre_de_la_newsletter(debut, fin)
        assert "2026" in titre
        assert len(titre) > 0
```

- [ ] **Step 2 : Lancer les tests et vérifier qu'ils échouent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_newsletter_ghost.py::TestRendu -v
```
Attendu : `ImportError: cannot import name 'rendre_newsletter_html'`.

- [ ] **Step 3 : Écrire le template**

`newsletter/templates/newsletter/email_evenements.html` :

```html
{% load i18n %}{% comment %}
CORPS DE LA NEWSLETTER — HTML SEMANTIQUE AUX CONVENTIONS GHOST
/ Newsletter body — semantic HTML using Ghost's kg-* conventions

LOCALISATION : newsletter/templates/newsletter/email_evenements.html

Ce HTML est poste a Ghost via POST /ghost/api/admin/posts/?source=html. Ghost le
reconvertit en CARTES NATIVES (image, bouton, divider) grace aux conventions kg-* :
    <figure><img><figcaption>                     -> carte image avec legende
    <div class="kg-button-card kg-align-center">  -> carte bouton
    <hr>                                          -> carte divider
Le brouillon s'ouvre donc dans l'editeur Ghost en blocs manipulables, et non en un
pave HTML opaque.

REGLE ABSOLUE : AUCUN attribut style=, AUCUN <table> de mise en page.
L'apparence (couleurs, polices, forme des boutons) est pilotee par les REGLAGES DE
DESIGN NEWSLETTER de l'instance Ghost. Styler ici court-circuiterait ce systeme et
nous rendrait responsables de la compatibilite Outlook / Gmail / mode sombre.
Voir TECH_DOC/SESSIONS/NEWSLETTER/SPEC.md §4.
{% endcomment %}<p>{% blocktranslate %}Voici les événements du réseau, du {{ date_debut_affichee }} au {{ date_fin_affichee }}.{% endblocktranslate %}</p>
{% for fiche in fiches %}
<hr>
<h2>{{ fiche.nom }}</h2>
{% if fiche.image_url %}<figure><img src="{{ fiche.image_url }}" alt="{{ fiche.nom }}"><figcaption>{{ fiche.nom }}</figcaption></figure>{% endif %}
<p>{{ fiche.organisateur }}{% if fiche.lieu %} — {{ fiche.lieu }}{% endif %}</p>
<p>{{ fiche.date_debut|date:"l j F Y, H\hi" }}{% if fiche.date_fin %} → {{ fiche.date_fin|date:"l j F Y, H\hi" }}{% endif %}</p>
{% if fiche.tarif %}<p>{{ fiche.tarif }}</p>{% endif %}
{% if fiche.description_courte %}<p>{{ fiche.description_courte }}</p>{% endif %}
{% comment %}
description_longue vient d'un widget Wysiwyg : c'est DEJA du HTML (<p>, <strong>,
listes). On l'emet BRUT, sans <p> autour — l'envelopper produirait du HTML invalide,
et l'echapper afficherait "&lt;strong&gt;" aux abonnes. Voir SPEC §7.2.
/ long_description is ALREADY HTML (Wysiwyg widget). Emitted RAW.
{% endcomment %}{% if fiche.description_longue %}{{ fiche.description_longue|safe }}{% endif %}
{% if fiche.url_event %}<div class="kg-button-card kg-align-center"><a class="kg-btn" href="{{ fiche.url_event }}">{{ fiche.libelle_bouton }}</a></div>{% endif %}
{% endfor %}
```

- [ ] **Step 4 : Écrire `newsletter/rendu.py`**

```python
"""
Fabrique le HTML de la newsletter a partir des fiches d'evenements.
/ Build the newsletter HTML from event fiches.

LOCALISATION : newsletter/rendu.py

Ce module ne touche NI la base NI Ghost. Il transforme des dicts en HTML.
/ This module touches NEITHER the database NOR Ghost.

POURQUOI PAS DE STYLE INLINE :
L'apparence de la newsletter (couleurs, polices, forme des boutons, en-tete, pied de
page) est pilotee par les REGLAGES DE DESIGN NEWSLETTER de l'instance Ghost. On emet
du HTML SEMANTIQUE aux conventions kg-*, que Ghost reconvertit en cartes natives.
Voir TECH_DOC/SESSIONS/NEWSLETTER/SPEC.md §4.
/ Styling is Ghost's job, via its newsletter design settings.
"""

from django.template.loader import render_to_string
from django.utils.formats import date_format
from django.utils.translation import gettext as _

GABARIT_DE_LA_NEWSLETTER = "newsletter/email_evenements.html"


def titre_de_la_newsletter(date_debut, date_fin):
    """
    Compose le titre du brouillon. / Compose the draft's title.

    C'est un BROUILLON : le gestionnaire le reecrira s'il veut.
    / It's a DRAFT: the manager will rewrite it if they want to.

    :param date_debut: datetime du debut de la fenetre
    :param date_fin: datetime de la fin de la fenetre
    :return: le titre (str)
    """
    debut_affiche = date_format(date_debut, "DATE_FORMAT")
    fin_affichee = date_format(date_fin, "DATE_FORMAT")

    return _("Agenda du %(debut)s au %(fin)s") % {
        "debut": debut_affiche,
        "fin": fin_affichee,
    }


def rendre_newsletter_html(fiches, date_debut, date_fin):
    """
    Rend le corps HTML de la newsletter. / Render the newsletter's HTML body.

    LOCALISATION : newsletter/rendu.py

    :param fiches: la liste des fiches (cf. newsletter.collecte)
    :param date_debut: datetime du debut de la fenetre
    :param date_fin: datetime de la fin de la fenetre
    :return: le HTML (str), sans aucun attribut style=
    """
    contexte = {
        "fiches": fiches,
        "date_debut_affichee": date_format(date_debut, "DATE_FORMAT"),
        "date_fin_affichee": date_format(date_fin, "DATE_FORMAT"),
    }

    return render_to_string(GABARIT_DE_LA_NEWSLETTER, contexte)
```

- [ ] **Step 5 : Lancer les tests et vérifier qu'ils passent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_newsletter_ghost.py -v
```
Attendu : **0 failed** (environ 34 tests).

- [ ] **Step 6 : Nettoyer**

```bash
docker exec lespass_django poetry run ruff check --fix /DjangoFiles/newsletter/
docker exec lespass_django poetry run ruff format /DjangoFiles/newsletter/
```

- [ ] **Step 7 : Commit — NE PAS EXÉCUTER**

```
feat(newsletter): rendu HTML semantique aux conventions Ghost

Le template emet <figure><img><figcaption>, kg-button-card/kg-btn et <hr>, que
Ghost reconvertit en cartes natives (image, bouton, divider) via ?source=html.
AUCUN style inline : l'apparence est pilotee par les reglages de design newsletter
de l'instance Ghost. Un test verrouille l'absence de style=.
```

---

## Task 5 : L'orchestration

**Files:**
- Create: `newsletter/services.py`
- Test: `tests/pytest/test_newsletter_ghost.py` (ajouter `TestServices`)

**Interfaces:**
- Consomme : `collecter_evenements_du_reseau` (Task 3), `rendre_newsletter_html` /
  `titre_de_la_newsletter` (Task 4), `creer_brouillon` + les exceptions (Task 1).
- Produit :
  - `creer_brouillon_newsletter(nombre_de_jours: int) -> dict`
    → `{"url_edition": str, "nombre_evenements": int}`
  - Exceptions : `GhostNonConfigure`, `AucunEvenement`
  - Ré-émet telles quelles les `ErreurGhost` du client.

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter dans `tests/pytest/test_newsletter_ghost.py` :

```python
from newsletter.services import (
    AucunEvenement,
    GhostNonConfigure,
    creer_brouillon_newsletter,
)


@pytest.mark.django_db
class TestServices:

    def test_ghost_non_configure_leve_GhostNonConfigure(self, tenant_lespass):
        """Sans URL ni cle, on ne tente meme pas l'appel reseau."""
        faux_ghost_config = MagicMock()
        faux_ghost_config.ghost_url = ""
        faux_ghost_config.get_api_key.return_value = ""

        with tenant_context(tenant_lespass):
            with patch("newsletter.services.GhostConfig.get_solo",
                       return_value=faux_ghost_config):
                with pytest.raises(GhostNonConfigure):
                    creer_brouillon_newsletter(nombre_de_jours=7)

    def test_aucun_evenement_ne_cree_pas_de_brouillon_vide(self, tenant_lespass):
        """
        Zero event sur la periode -> on leve AucunEvenement et on NE POSTE RIEN.
        Un brouillon vide dans Ghost serait du bruit pour le gestionnaire.
        """
        faux_ghost_config = MagicMock()
        faux_ghost_config.ghost_url = "https://ghost.exemple.coop"
        faux_ghost_config.get_api_key.return_value = CLE_GHOST_DE_TEST

        with tenant_context(tenant_lespass):
            with patch("newsletter.services.GhostConfig.get_solo",
                       return_value=faux_ghost_config), \
                 patch("newsletter.services.collecter_evenements_du_reseau",
                       return_value=[]), \
                 patch("newsletter.services.creer_brouillon") as faux_creer:
                with pytest.raises(AucunEvenement):
                    creer_brouillon_newsletter(nombre_de_jours=7)

        faux_creer.assert_not_called()

    def test_succes_renvoie_lurl_et_le_nombre_devenements(self, tenant_lespass):
        faux_ghost_config = MagicMock()
        faux_ghost_config.ghost_url = "https://ghost.exemple.coop"
        faux_ghost_config.get_api_key.return_value = CLE_GHOST_DE_TEST

        fiches = [_fiche_de_test(nom="A"), _fiche_de_test(nom="B")]

        with tenant_context(tenant_lespass):
            with patch("newsletter.services.GhostConfig.get_solo",
                       return_value=faux_ghost_config), \
                 patch("newsletter.services.collecter_evenements_du_reseau",
                       return_value=fiches), \
                 patch("newsletter.services.creer_brouillon",
                       return_value="https://ghost.exemple.coop/ghost/#/editor/post/xyz"):
                resultat = creer_brouillon_newsletter(nombre_de_jours=7)

        assert resultat["nombre_evenements"] == 2
        assert resultat["url_edition"] == "https://ghost.exemple.coop/ghost/#/editor/post/xyz"

    def test_le_journal_est_ecrit_meme_en_cas_decheche(self, tenant_lespass):
        """ghost_last_log doit tracer l'echec : c'est le seul indice du gestionnaire."""
        faux_ghost_config = MagicMock()
        faux_ghost_config.ghost_url = "https://ghost.exemple.coop"
        faux_ghost_config.get_api_key.return_value = CLE_GHOST_DE_TEST

        with tenant_context(tenant_lespass):
            with patch("newsletter.services.GhostConfig.get_solo",
                       return_value=faux_ghost_config), \
                 patch("newsletter.services.collecter_evenements_du_reseau",
                       return_value=[_fiche_de_test()]), \
                 patch("newsletter.services.creer_brouillon",
                       side_effect=GhostInjoignable("timeout")):
                with pytest.raises(GhostInjoignable):
                    creer_brouillon_newsletter(nombre_de_jours=7)

        # Le journal a bien ete ecrit puis sauvegarde.
        assert faux_ghost_config.save.called
        assert "Erreur" in faux_ghost_config.ghost_last_log
```

- [ ] **Step 2 : Lancer les tests et vérifier qu'ils échouent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_newsletter_ghost.py::TestServices -v
```
Attendu : `ModuleNotFoundError: No module named 'newsletter.services'`.

- [ ] **Step 3 : Écrire `newsletter/services.py`**

```python
"""
Orchestration : collecte -> rendu -> depot du brouillon dans Ghost.
/ Orchestration: collect -> render -> drop the draft into Ghost.

LOCALISATION : newsletter/services.py

C'est le SEUL point d'entree de l'admin. Les trois modules qu'il assemble ne se
connaissent pas entre eux.
/ This is the admin's ONLY entry point.
"""

import logging
from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext as _

from BaseBillet.models import GhostConfig
from newsletter.client_ghost import ErreurGhost, creer_brouillon
from newsletter.collecte import collecter_evenements_du_reseau
from newsletter.rendu import rendre_newsletter_html, titre_de_la_newsletter

logger = logging.getLogger(__name__)


class GhostNonConfigure(Exception):
    """Le tenant n'a pas renseigne son instance Ghost. / No Ghost instance configured."""


class AucunEvenement(Exception):
    """Aucun evenement sur la periode : on ne cree pas de brouillon vide."""


def _journaliser(ghost_config, message):
    """
    Ecrit une ligne horodatee dans GhostConfig.ghost_last_log.
    / Write a timestamped line into GhostConfig.ghost_last_log.

    Le champ est ECRASE, pas complete : c'est ce que fait deja le code Ghost existant
    (GhostConfigAdmin.test_api_ghost_admin_button), on reste coherent.
    / The field is OVERWRITTEN, not appended: consistent with the existing Ghost code.
    """
    ghost_config.ghost_last_log = f"{timezone.now()} - {message}"
    ghost_config.save()


def creer_brouillon_newsletter(nombre_de_jours):
    """
    Fabrique un brouillon de newsletter dans l'instance Ghost du tenant courant.
    / Build a newsletter draft in the current tenant's Ghost instance.

    LOCALISATION : newsletter/services.py

    FLUX :
    1. Lire la config Ghost du tenant (GhostConfig, singleton chiffre)
    2. Collecter les evenements du tenant ET de son reseau federe sur la fenetre
    3. S'il n'y en a aucun : lever AucunEvenement, sans rien poster
    4. Rendre le HTML semantique (conventions kg-* de Ghost)
    5. Deposer le BROUILLON et renvoyer son URL d'edition
    6. Journaliser, succes comme echec

    Le post est cree en status="draft". Il n'est JAMAIS publie ni envoye : l'envoi
    reste un geste humain, dans l'interface de Ghost.
    / The post is a DRAFT. Sending stays a human action, inside Ghost.

    :param nombre_de_jours: la largeur de la fenetre (7 ou 30)
    :return: {"url_edition": str, "nombre_evenements": int}
    :raises GhostNonConfigure: ni URL ni cle renseignees
    :raises AucunEvenement: aucun evenement sur la periode
    :raises ErreurGhost: Ghost injoignable, cle refusee, reponse inattendue
    """
    ghost_config = GhostConfig.get_solo()
    url_instance_ghost = ghost_config.ghost_url
    cle_admin_ghost = ghost_config.get_api_key()

    if not url_instance_ghost or not cle_admin_ghost:
        raise GhostNonConfigure(
            _("L'instance Ghost n'est pas configurée (URL ou clé Admin API manquante).")
        )

    date_debut = timezone.now()
    date_fin = timezone.now() + timedelta(days=nombre_de_jours)

    fiches = collecter_evenements_du_reseau(nombre_de_jours)

    # On ne cree JAMAIS un brouillon vide : ce serait du bruit dans le Ghost du
    # gestionnaire. / We NEVER create an empty draft.
    if not fiches:
        message = _("Aucun événement sur les %(jours)s prochains jours.") % {
            "jours": nombre_de_jours
        }
        _journaliser(ghost_config, message)
        raise AucunEvenement(message)

    contenu_html = rendre_newsletter_html(fiches, date_debut, date_fin)
    titre = titre_de_la_newsletter(date_debut, date_fin)

    try:
        url_edition = creer_brouillon(
            url_instance_ghost=url_instance_ghost,
            cle_admin_ghost=cle_admin_ghost,
            titre=titre,
            contenu_html=contenu_html,
        )
    except ErreurGhost as erreur_ghost:
        # On journalise AVANT de re-lever : ghost_last_log est le seul indice que le
        # gestionnaire aura apres coup. / Log BEFORE re-raising.
        _journaliser(ghost_config, f"Erreur - {type(erreur_ghost).__name__} : {erreur_ghost}")
        logger.warning(f"creer_brouillon_newsletter : {erreur_ghost}")
        raise

    _journaliser(
        ghost_config,
        f"Brouillon de newsletter cree ({len(fiches)} evenements) : {url_edition}",
    )

    return {
        "url_edition": url_edition,
        "nombre_evenements": len(fiches),
    }
```

- [ ] **Step 4 : Lancer les tests et vérifier qu'ils passent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_newsletter_ghost.py -v
```
Attendu : **0 failed** (environ 38 tests).

- [ ] **Step 5 : Nettoyer**

```bash
docker exec lespass_django poetry run ruff check --fix /DjangoFiles/newsletter/
docker exec lespass_django poetry run ruff format /DjangoFiles/newsletter/
```

- [ ] **Step 6 : Commit — NE PAS EXÉCUTER**

```
feat(newsletter): orchestration collecte -> rendu -> brouillon Ghost

creer_brouillon_newsletter() est le seul point d'entree de l'admin. Zero evenement
sur la periode -> AucunEvenement, et AUCUN brouillon vide n'est poste. Succes comme
echec sont traces dans GhostConfig.ghost_last_log.
```

---

## Task 6 : Les deux boutons dans l'admin

**Files:**
- Modify: `Administration/admin_tenant.py:3748` (la liste `actions_detail` de `GhostConfigAdmin`)
- Modify: `Administration/admin_tenant.py` (ajouter les deux méthodes `@action` dans
  `GhostConfigAdmin`, juste après `test_api_ghost_admin_button`)

**Interfaces:**
- Consomme : `newsletter.services.creer_brouillon_newsletter` et ses exceptions (Task 5).
- Produit : rien (bout de chaîne).

**⚠️ `GhostConfigAdmin` a DÉJÀ `actions_detail = ["test_api_ghost_admin_button"]`.** On **ajoute**
à la liste. **L'écraser supprimerait le bouton de test de connexion Ghost.**

`admin_tenant.py` est **pré-existant** : `ruff check --fix` autorisé, **`ruff format` INTERDIT**.

- [ ] **Step 1 : Étendre `actions_detail`**

Dans `Administration/admin_tenant.py`, remplacer la ligne 3748 :

```python
    actions_detail = ["test_api_ghost_admin_button"]
```

par :

```python
    actions_detail = [
        "test_api_ghost_admin_button",
        "brouillon_newsletter_7_jours",
        "brouillon_newsletter_30_jours",
    ]
```

- [ ] **Step 2 : Ajouter les deux actions**

Dans la classe `GhostConfigAdmin`, **juste après** la méthode `test_api_ghost_admin_button` et
**avant** `has_custom_actions_detail_permission`, insérer :

```python
    def _generer_le_brouillon_de_newsletter(self, request, nombre_de_jours):
        """
        Fabrique un brouillon de newsletter et rend le resultat en toast.
        / Build a newsletter draft and report the outcome as a toast.

        LOCALISATION : Administration/admin_tenant.py (GhostConfigAdmin)

        Partage par les deux boutons (7 jours / 30 jours) : seule la fenetre change.
        Execution SYNCHRONE : quelques requetes + un POST (< 2 s). Le gestionnaire a un
        retour immediat et un lien cliquable vers son brouillon.
        / Shared by both buttons. SYNCHRONOUS: the manager gets an immediate clickable link.

        Le post est cree en BROUILLON. Il n'est jamais publie ni envoye.
        / The post is a DRAFT. Never published, never emailed.
        """
        from newsletter.client_ghost import (
            GhostCleRefusee,
            GhostInjoignable,
            GhostReponseInattendue,
        )
        from newsletter.services import (
            AucunEvenement,
            GhostNonConfigure,
            creer_brouillon_newsletter,
        )

        try:
            resultat = creer_brouillon_newsletter(nombre_de_jours=nombre_de_jours)

        except GhostNonConfigure:
            messages.warning(
                request,
                _("Ghost n'est pas configuré : renseignez l'URL et la clé Admin API."),
            )

        except AucunEvenement:
            messages.info(
                request,
                _("Aucun événement sur les %(jours)s prochains jours : aucun brouillon créé.")
                % {"jours": nombre_de_jours},
            )

        except GhostInjoignable:
            messages.error(request, _("Instance Ghost injoignable."))

        except GhostCleRefusee:
            messages.error(request, _("La clé Admin API est refusée par Ghost."))

        except GhostReponseInattendue as erreur:
            messages.error(
                request,
                _("Réponse inattendue de Ghost : %(erreur)s") % {"erreur": erreur},
            )

        else:
            # format_html : sans lui, django.messages ECHAPPE le HTML et le lien
            # s'afficherait en texte brut, non cliquable.
            # / format_html: without it, django.messages escapes the HTML and the link
            # would render as plain, unclickable text.
            messages.success(
                request,
                format_html(
                    '{} <a href="{}" target="_blank" rel="noopener">{}</a>',
                    _("Brouillon créé avec %(nombre)s événement(s).")
                    % {"nombre": resultat["nombre_evenements"]},
                    resultat["url_edition"],
                    _("Ouvrir dans Ghost"),
                ),
            )

        return redirect(request.META["HTTP_REFERER"])

    @action(
        description=_("Brouillon newsletter — 7 jours"),
        url_path="brouillon_newsletter_7_jours",
        permissions=["custom_actions_detail"],
    )
    def brouillon_newsletter_7_jours(self, request, object_id):
        return self._generer_le_brouillon_de_newsletter(request, nombre_de_jours=7)

    @action(
        description=_("Brouillon newsletter — 30 jours"),
        url_path="brouillon_newsletter_30_jours",
        permissions=["custom_actions_detail"],
    )
    def brouillon_newsletter_30_jours(self, request, object_id):
        return self._generer_le_brouillon_de_newsletter(request, nombre_de_jours=30)
```

> **Aucun import à ajouter en tête de `admin_tenant.py`** : `messages` (l.46), `redirect` (l.54),
> `_` = `gettext_lazy` (l.62), `action` d'Unfold (l.88) et **`format_html` (l.59)** y sont déjà.
> Les imports de `newsletter` sont **locaux à la méthode**, pour ne pas alourdir le module d'admin
> ni risquer un import circulaire.

- [ ] **Step 3 : Vérifier que Django démarre et que rien n'est cassé**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run ruff check --fix /DjangoFiles/Administration/admin_tenant.py
```
Attendu : `System check identified no issues`.
**Ne PAS lancer `ruff format` sur `admin_tenant.py`** (fichier pré-existant).

- [ ] **Step 4 : Lancer TOUTE la suite**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```
Attendu : **0 failed**. La suite comptait 270 tests avant ce chantier ; elle en compte environ
308 après. Des `skip` sont normaux (tests dépendant du seed) — **c'est le zéro échec qui fait foi**,
pas le total.

- [ ] **Step 5 : Vérification manuelle (à faire décrire au mainteneur)**

Ne PAS lancer le serveur (il est tenu dans byobu). Décrire au mainteneur la procédure :

1. Aller sur `https://lespass.tibillet.localhost/admin/BaseBillet/ghostconfig/`
2. Renseigner l'URL et la clé Admin API d'une instance Ghost
3. Cliquer **« Brouillon newsletter — 30 jours »**
4. Attendu : un toast vert avec le nombre d'événements **et le lien vers l'éditeur Ghost**
5. Ouvrir le lien : le brouillon contient une **carte image**, une **carte bouton** et des
   **séparateurs** — pas un pavé HTML opaque
6. Vérifier que le bouton **« Test Api »** (préexistant) fonctionne toujours

> Les images ne s'afficheront **pas** en dev local (`*.tibillet.localhost` n'est pas joignable
> depuis Ghost). C'est **normal** : le rendu des images se vérifie sur `demo-tibillet.ovh`.

- [ ] **Step 6 : Documentation**

Créer `A TESTER et DOCUMENTER/newsletter-brouillon-ghost.md` (procédure de test manuelle,
au format du dossier) et ajouter une section en **haut** de `CHANGELOG.md` (format bilingue
FR/EN, tableau des fichiers modifiés, flag migration = **Non**).

- [ ] **Step 7 : Signaler au mainteneur (trois points)**

Dans le rapport final, écrire ces trois signalements :

1. **i18n** — « Cette feature ajoute N chaînes traduisibles (msgid en français). Le workflow i18n
   est à lancer par le mainteneur. » Compter les `_()` / `{% translate %}` / `{% blocktranslate %}`
   ajoutés. **Ne JAMAIS lancer `makemessages` ni `compilemessages`.**

2. **Bug trouvé dans l'agenda, hors périmètre** — « `EventMVT.federated_events_filter`
   (`BaseBillet/views.py:1966`) **ne filtre pas `archived`**, alors que `seo/services.py` le filtre
   à quatre endroits (*"un event archivé, retiré de l'agenda, ne doit plus apparaître"*).
   Conséquence : **un événement archivé disparaît de la carte et de l'explorateur, mais reste
   affiché sur l'agenda.** La newsletter, elle, le filtre. Correctif probable : ajouter
   `archived=False` au `.filter()` du moteur. Non fait ici — hors périmètre. »

3. **`pyjwt` en dépendance transitive** — voir la réserve en tête de ce plan.

- [ ] **Step 8 : Commit — NE PAS EXÉCUTER**

```
feat(newsletter): deux boutons de generation dans l'admin Ghost

Ajout de "Brouillon newsletter — 7 jours" et "— 30 jours" aux actions_detail de
GhostConfigAdmin (l'action Test Api existante est conservee). Execution synchrone :
toast avec le nombre d'evenements et le lien vers l'editeur Ghost. Zero evenement ->
message d'information, aucun brouillon vide poste.
```

---

## Couverture de la spec

| Exigence de la SPEC | Tâche |
|---|---|
| §5 App `newsletter/` sans modèle, dans `TENANT_APPS` | Task 1 |
| §8.1 JWT (HS256, `kid`, `aud=/admin/`, exp ≤ 5 min) | Task 1 |
| §8.2 `POST ?source=html`, `status: draft`, `rstrip('/')`, `Accept-Version`, URL d'édition | Task 1 |
| §6.6 Tarif (5 cas, dans l'ordre), produits publiés et non archivés | Task 2 |
| §6.3 Fenêtre depuis hier, `published`, `ACTION` | Task 3 |
| §6.3 `private` **uniquement** pour les voisins | Task 3 |
| §6.3 `archived` — **écart assumé** : le moteur de l'agenda ne le filtre pas (son bug), la newsletter si | Task 3 |
| §6.3 events enfants — **abandonné** : `Event.save()` force `categorie=ACTION` sur tout enfant, l'`exclude(ACTION)` suffit | Task 3 |
| §6.5 timezone du propriétaire — **abandonnée** : on rend dans la timezone active, comme l'agenda. Un abonné lit toutes les dates dans un même fuseau | Task 3 |
| §6.3 Dédoublonnage des tenants · fédération auto par tags | Task 3 |
| §6.4 Matching par slug · `tenant_context()` | Task 3 |
| §6.5 Les 11 clés de la fiche, dont `organisateur` | Task 3 |
| §6.7 `event.full_url` (gère `is_external`) · `crop_hdr` · garde-fou `get_primary_domain()` | Task 3 |
| §4.5 Mapping `kg-*` → cartes natives | Task 4 |
| §4.4 **Aucun style inline** (verrouillé par un test) | Task 4 |
| §7.2 `long_description` émis en HTML brut | Task 4 |
| §7.3 Titre du brouillon | Task 4 |
| §9 Deux actions Unfold, `actions_detail` **étendu** (non écrasé) | Task 6 |
| §9 Les 6 cas de sortie en toast · journal dans `ghost_last_log` | Tasks 5 & 6 |
| §10 Mock via `unittest.mock` (pas `responses`) | Toutes |
| §11 Hors périmètre : cron, upload d'images, MCP, `module_newsletter` | — (non implémentés) |
