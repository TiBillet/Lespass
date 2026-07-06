# API v2 pour l'app `pages` — Plan d'implémentation

> **Pour exécution agentique :** suivre `superpowers:subagent-driven-development`
> ou `superpowers:executing-plans`. Étapes en cases à cocher (`- [ ]`).
> Spec de référence : `TECH_DOC/SESSIONS/PAGES/CHANTIER-05-api-v2-pages.md`.

**Goal :** Exposer l'app `pages` (Page + Bloc) via l'API v2 schema.org/JSON-LD pour
fabriquer un site complet par API (création nested + édition bloc par bloc),
protégé par une nouvelle permission de clé API.

**Architecture :** `viewsets.ViewSet` explicites (pattern api_v2), serializers
input/output séparés. Page → `WebPage` (`hasPart` = blocs), Bloc →
`WebPageElement` (`additionalType` = type_bloc ; champs exotiques en
`additionalProperty[]` typé). Une seule source pour le catalogue de champs
(`pages/blocs_catalogue.py`). Permission booléenne `page` sur `ExternalApiKey`.

**Tech Stack :** Django, DRF, django-tenants (table par schéma), Pillow (validation
image), `requests` (download image par URL), StdImage.

## Global Constraints (copiées du spec, valent pour TOUTES les tâches)

- **AUCUNE opération git par l'assistant** : pas de `commit/add/push/checkout/stash/
  reset/restore/clean`. Les étapes « Commit » = **proposer le message au mainteneur
  et s'arrêter**, jamais exécuter git.
- **Pas de Co-Authored-By** dans les messages de commit suggérés.
- `ruff format` **uniquement sur fichiers neufs** ; sur l'existant, `ruff check` seul.
- **FALC** : code verbeux, noms explicites, commentaires bilingues FR/EN.
- **i18n** : libellés `_()` source **FR** ; ne PAS lancer makemessages/compilemessages.
- **ViewSet explicite** (jamais ModelViewSet), validation par `serializers.Serializer`.
- **Serveur** : tourne dans byobu (port 8002) — NE PAS lancer `runserver_plus`.
- **Tests** : `docker exec lespass_django poetry run pytest <chemin> -q`.
- **Multi-tenant** : tout `create()`/accès tenant dans un `tenant_context(tenant)`
  (cf. `tests/PIEGES.md`). `ExternalApiKey` et `Page`/`Bloc` sont tenant-scoped.
- **basename = clé de `api_permissions()`** : `page` pour pages, `bloc` pour blocs.

---

# SESSION A — Permission + CRUD blocs/pages « plats »

Périmètre : permission `page`, catalogue de champs (constante), serializers
Bloc + Page (champs plats + 4 propriétés standard + additionalProperty texte),
ViewSets + routes. **Pas** d'images (Session B), **pas** d'endpoint catalogue HTTP.

## Task A1 : Permission `page` sur ExternalApiKey

**Files:**
- Modify: `BaseBillet/models.py` (classe `ExternalApiKey`, ~3389-3467)
- Create: `BaseBillet/migrations/0XXX_externalapikey_page.py` (numéro réel via makemigrations)
- Modify: `Administration/admin_tenant.py` (`ExternalApiKeyAdmin`, ~137-170)
- Test: `tests/pytest/test_pages_api.py` (nouveau)

**Interfaces:**
- Produces: `ExternalApiKey.page` (BooleanField) ; `api_permissions()["page"]` et
  `["bloc"]` = `self.page`.

- [ ] **Step 1 : Écrire le test d'échec (permission mapping)**

```python
# tests/pytest/test_pages_api.py
import pytest
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import ExternalApiKey


@pytest.mark.django_db
def test_apikey_page_permission_maps_page_and_bloc():
    """La permission `page` ouvre les basenames `page` ET `bloc`.
    / The `page` permission opens both `page` and `bloc` basenames."""
    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        cle = ExternalApiKey(name="cle-test-pages", page=True)
        perms = cle.api_permissions()
        assert perms["page"] is True
        assert perms["bloc"] is True

        cle_sans = ExternalApiKey(name="cle-sans-pages", page=False)
        perms_sans = cle_sans.api_permissions()
        assert perms_sans["page"] is False
        assert perms_sans["bloc"] is False
```

- [ ] **Step 2 : Lancer le test, vérifier l'échec**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages_api.py::test_apikey_page_permission_maps_page_and_bloc -q`
Expected : FAIL (`TypeError: ... unexpected keyword 'page'` ou KeyError "page").

- [ ] **Step 3 : Ajouter le champ + le mapping**

Dans `BaseBillet/models.py`, classe `ExternalApiKey`, après `crowd` (~3426) :
```python
    # Droit sur l'API du site web (app pages) : ouvre la creation/edition des
    # Pages ET des Blocs (un seul booleen pour fabriquer un site via l'API).
    # / Website API right (pages app): opens create/edit of Pages AND Blocs.
    page = models.BooleanField(default=False, verbose_name=_("Pages / Site web"))
```
Dans `api_permissions()`, ajouter au dict :
```python
            # Site web (app pages) : meme droit pour pages et blocs.
            # / Website (pages app): same right for pages and blocs.
            "page": self.page,
            "bloc": self.page,
```

- [ ] **Step 4 : Générer + appliquer la migration**

Run :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas
```
Expected : migration `0XXX_externalapikey_page` créée, appliquée à tous les schémas.

- [ ] **Step 5 : Exposer le champ dans l'admin**

Dans `Administration/admin_tenant.py`, `ExternalApiKeyAdmin` :
- ajouter `'page'` à `list_display` (après `'sale'`),
- ajouter une ligne dans `fields`, ex. après `('membership', 'crowd'),` :
```python
        # Droit API du site web (app pages) / Website API right (pages app)
        ('page',),
```

- [ ] **Step 6 : Lancer le test + check**

Run :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_pages_api.py::test_apikey_page_permission_maps_page_and_bloc -q
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```
Expected : PASS + 0 issue.

- [ ] **Step 7 : Commit (proposer au mainteneur, NE PAS exécuter git)**

Message suggéré :
`feat(api_v2): add 'page' API key permission for pages app`

---

## Task A2 : Catalogue des champs par type de bloc (source unique)

**Files:**
- Create: `pages/blocs_catalogue.py`
- Test: `tests/pytest/test_pages_api.py`

**Interfaces:**
- Produces :
  - `CHAMPS_PAR_TYPE: dict[str, list[str]]` — pour chaque `type_bloc`, la liste
    des noms de champs modèle autorisés.
  - `CHAMPS_BLOC_AUTORISES: frozenset[str]` — union de tous les champs (whitelist
    pour `additionalProperty`).
  - `TYPES_BLOC: list[str]` — les 14 codes de type.

- [ ] **Step 1 : Écrire le test d'échec**

```python
@pytest.mark.django_db
def test_catalogue_blocs_couvre_les_14_types():
    from pages.blocs_catalogue import CHAMPS_PAR_TYPE, CHAMPS_BLOC_AUTORISES, TYPES_BLOC
    from pages.models import Bloc
    # Les 14 types du modele sont presents dans le catalogue.
    types_modele = {code for code, _label in Bloc.TYPE_BLOC_CHOICES}
    assert set(CHAMPS_PAR_TYPE.keys()) == types_modele
    assert len(TYPES_BLOC) == 14
    # La whitelist est l'union, et ne contient que de vrais champs du modele.
    noms_champs_modele = {f.name for f in Bloc._meta.get_fields()}
    assert CHAMPS_BLOC_AUTORISES <= noms_champs_modele
    # Exemple cible : FAQ porte titre + texte + repliable.
    assert set(CHAMPS_PAR_TYPE["FAQ"]) == {"titre", "texte", "repliable"}
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages_api.py::test_catalogue_blocs_couvre_les_14_types -q`
Expected : FAIL (`ModuleNotFoundError: pages.blocs_catalogue`).

- [ ] **Step 3 : Créer le catalogue**

```python
# pages/blocs_catalogue.py
"""
Source UNIQUE du catalogue des champs par type de bloc.
/ SINGLE source of the per-type block field catalogue.

LOCALISATION : pages/blocs_catalogue.py

Utilise par : l'API v2 (validation + endpoint block-types/) et, a terme,
l'admin (conditional_fields derive). Derive de la matrice SPEC.md.
/ Used by: API v2 (validation + block-types endpoint) and, later, the admin.
"""

# Pour chaque type de bloc : la liste des champs modele qu'il utilise.
# / For each block type: the list of model fields it uses.
CHAMPS_PAR_TYPE = {
    "HERO": ["titre", "sous_titre", "image", "image_secondaire",
             "bouton_label", "bouton_url", "bouton2_label", "bouton2_url"],
    "PARAGRAPHE": ["titre", "texte"],
    "IMAGE_TEXTE": ["titre", "texte", "image", "image_position",
                    "bouton_label", "bouton_url"],
    "CTA": ["titre", "sous_titre", "texte",
            "bouton_label", "bouton_url", "bouton2_label", "bouton2_url"],
    "TEMOIGNAGE": ["texte", "auteur_nom", "auteur_role", "auteur_photo"],
    "VIDEO_TEXTE": ["titre", "texte", "video"],
    "CARTE": ["surtitre", "titre", "badge", "texte", "image",
              "bouton_label", "bouton_url"],
    "IMAGE": ["titre", "image"],
    "CARTE_LEAFLET": ["titre", "badge", "image", "image_secondaire", "points_gps"],
    "INFOS": ["contenu"],
    "FAQ": ["titre", "texte", "repliable"],
    "EVENEMENTS": ["titre", "nombre_max"],
    "GALERIE": ["titre"],  # les images sont portees par ImageGalerie (cf. Session B)
    "EMBED": ["titre", "embed_url"],
}

# Les 14 codes de type, dans l'ordre du catalogue.
# / The 14 type codes, in catalogue order.
TYPES_BLOC = list(CHAMPS_PAR_TYPE.keys())

# Union de tous les champs : whitelist pour additionalProperty (securite : on ne
# laisse JAMAIS setattr un champ hors de cette liste, ex. page/uuid/position).
# / Union of all fields: whitelist for additionalProperty (never setattr outside).
CHAMPS_BLOC_AUTORISES = frozenset(
    champ for champs in CHAMPS_PAR_TYPE.values() for champ in champs
)
```

- [ ] **Step 4 : Lancer le test**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages_api.py::test_catalogue_blocs_couvre_les_14_types -q`
Expected : PASS.

- [ ] **Step 5 : Commit (proposer, NE PAS exécuter git)**

Message : `feat(pages): add single-source block field catalogue`

---

## Task A3 : Serializers Bloc (output schema + input create)

**Files:**
- Modify: `api_v2/serializers.py` (ajouter en fin de fichier)
- Test: `tests/pytest/test_pages_api.py`

**Interfaces:**
- Consumes : `CHAMPS_BLOC_AUTORISES`, `clean_html` (déjà importé `api_v2/serializers.py:14`).
- Produces :
  - `BlocSchemaSerializer(instance)` → dict JSON-LD `WebPageElement`.
  - `BlocCreateSerializer(data=..., context={"page": page})` → `.save()` crée un `Bloc`.
  - Constantes module : `MAPPING_STANDARD_VERS_CHAMP` = `{"headline":"titre",
    "alternativeHeadline":"sous_titre","text":"texte"}`.

**Mapping (rappel spec) :** `headline`↔titre, `alternativeHeadline`↔sous_titre,
`text`↔texte (sanitizé), `additionalType`↔type_bloc, `image`↔image.url (sortie),
tout le reste ↔ `additionalProperty[]` (`{"@type":"PropertyValue","name":<champ>,"value":..}`).

- [ ] **Step 1 : Écrire le test d'échec (round-trip create → représentation)**

```python
@pytest.mark.django_db
def test_bloc_create_serializer_cree_un_bloc_faq():
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page, Bloc
    from api_v2.serializers import BlocCreateSerializer, BlocSchemaSerializer

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="Test", slug="test-bloc-faq")
        payload = {
            "additionalType": "FAQ",
            "headline": "Une question ?",
            "text": "<p>Une reponse <script>alert(1)</script></p>",
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "repliable", "value": True},
            ],
        }
        ser = BlocCreateSerializer(data=payload, context={"page": page})
        assert ser.is_valid(), ser.errors
        bloc = ser.save()
        assert bloc.type_bloc == "FAQ"
        assert bloc.titre == "Une question ?"
        assert bloc.repliable is True
        # Sanitize : le <script> est retire du texte.
        assert "<script>" not in bloc.texte
        # Representation JSON-LD.
        out = BlocSchemaSerializer(bloc).data
        assert out["@type"] == "WebPageElement"
        assert out["additionalType"] == "FAQ"
        assert out["headline"] == "Une question ?"
        assert out["identifier"] == str(bloc.uuid)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages_api.py::test_bloc_create_serializer_cree_un_bloc_faq -q`
Expected : FAIL (`ImportError: BlocCreateSerializer`).

- [ ] **Step 3 : Implémenter les serializers Bloc**

Ajouter en fin de `api_v2/serializers.py` :
```python
# ---------------------------------------------------------------------------
# App pages : Bloc <-> schema.org/WebPageElement
# / pages app: Bloc <-> schema.org/WebPageElement
# ---------------------------------------------------------------------------
from pages.models import Bloc, Page
from pages.blocs_catalogue import CHAMPS_BLOC_AUTORISES

# Champs « standard » schema.org mappes a un champ modele (les autres passent
# par additionalProperty). / schema.org standard fields mapped to a model field.
MAPPING_STANDARD_VERS_CHAMP = {
    "headline": "titre",
    "alternativeHeadline": "sous_titre",
    "text": "texte",
}
# Champs modele dont la valeur est du texte riche a nettoyer (clean_html).
# / Model fields whose value is rich text to sanitize.
CHAMPS_TEXTE_RICHE = {"texte"}


class BlocSchemaSerializer(serializers.Serializer):
    """Represente un Bloc en JSON-LD schema.org/WebPageElement (lecture seule).
    / Renders a Bloc as schema.org/WebPageElement JSON-LD (read-only)."""

    def to_representation(self, instance: "Bloc") -> Dict[str, Any]:
        # Image principale -> URL (vide si pas d'image). / Main image -> URL.
        image_url = None
        try:
            if instance.image:
                image_url = instance.image.url
        except Exception:
            image_url = None

        # additionalProperty : tous les champs du catalogue NON mappes en standard,
        # exposes sous {"@type":"PropertyValue","name":<champ>,"value":..}.
        # / additionalProperty: all catalogue fields not in the standard mapping.
        champs_standard = set(MAPPING_STANDARD_VERS_CHAMP.values()) | {"image"}
        props: List[Dict[str, Any]] = []
        for nom_champ in CHAMPS_BLOC_AUTORISES:
            if nom_champ in champs_standard:
                continue
            valeur = getattr(instance, nom_champ, None)
            # Les FileField/StdImage exposent .url ; on serialise en URL.
            # / FileField/StdImage expose .url; serialise as URL.
            if hasattr(valeur, "url"):
                try:
                    valeur = valeur.url if valeur else None
                except Exception:
                    valeur = None
            if valeur in (None, "", [], {}):
                continue
            props.append({"@type": "PropertyValue", "name": nom_champ, "value": valeur})

        payload = {
            "@context": "https://schema.org",
            "@type": "WebPageElement",
            "identifier": str(instance.uuid),
            "additionalType": instance.type_bloc,
            "headline": instance.titre or None,
            "alternativeHeadline": instance.sous_titre or None,
            "text": instance.texte or None,
            "image": image_url,
            "position": instance.position,
            "additionalProperty": props or None,
        }
        return {k: v for k, v in payload.items() if v not in (None, "", [])}


class BlocCreateSerializer(serializers.Serializer):
    """Valide un WebPageElement entrant et cree un Bloc rattache a une Page.
    / Validates an incoming WebPageElement and creates a Bloc on a Page.

    Contexte requis : context={"page": <Page>}.
    """
    additionalType = serializers.CharField()  # type_bloc (pivot)
    headline = serializers.CharField(required=False, allow_blank=True)
    alternativeHeadline = serializers.CharField(required=False, allow_blank=True)
    text = serializers.CharField(required=False, allow_blank=True)
    image = serializers.CharField(required=False, allow_blank=True, allow_null=True)  # URL (Session B)
    position = serializers.IntegerField(required=False)
    additionalProperty = serializers.ListField(child=serializers.DictField(), required=False)

    def validate_additionalType(self, value: str) -> str:
        codes = {code for code, _ in Bloc.TYPE_BLOC_CHOICES}
        if value not in codes:
            raise serializers.ValidationError(
                _("Type de bloc inconnu : %(t)s") % {"t": value})
        return value

    def create(self, validated_data: Dict[str, Any]) -> "Bloc":
        page = self.context["page"]
        bloc = Bloc(page=page, type_bloc=validated_data["additionalType"])
        if "position" in validated_data:
            bloc.position = validated_data["position"]

        # Champs standard -> champs modele. / Standard fields -> model fields.
        for cle_std, nom_champ in MAPPING_STANDARD_VERS_CHAMP.items():
            if cle_std in validated_data:
                valeur = validated_data[cle_std]
                if nom_champ in CHAMPS_TEXTE_RICHE:
                    valeur = clean_html(valeur or "")
                setattr(bloc, nom_champ, valeur or "")

        # additionalProperty -> champs modele (whitelist stricte).
        # / additionalProperty -> model fields (strict whitelist).
        for prop in (validated_data.get("additionalProperty") or []):
            nom = prop.get("name")
            valeur = prop.get("value")
            if nom not in CHAMPS_BLOC_AUTORISES:
                continue  # securite : jamais setattr hors whitelist
            if nom in CHAMPS_TEXTE_RICHE:
                valeur = clean_html(valeur or "")
            setattr(bloc, nom, valeur)

        bloc.save()
        return bloc
```
> Note : `_` (gettext) est déjà importé dans `api_v2/serializers.py` (vérifier
> en tête de fichier ; sinon `from django.utils.translation import gettext_lazy as _`).

- [ ] **Step 4 : Lancer le test**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages_api.py::test_bloc_create_serializer_cree_un_bloc_faq -q`
Expected : PASS.

- [ ] **Step 5 : Commit (proposer)**

Message : `feat(api_v2): add Bloc schema.org serializers (WebPageElement)`

---

## Task A4 : Serializers Page (output `WebPage` + input nested)

**Files:**
- Modify: `api_v2/serializers.py`
- Test: `tests/pytest/test_pages_api.py`

**Interfaces:**
- Consumes : `BlocSchemaSerializer`, `BlocCreateSerializer`, `valider_slug_non_reserve`.
- Produces :
  - `PageSchemaSerializer(instance)` → JSON-LD `WebPage` avec `hasPart`.
  - `PageCreateSerializer(data=..., context={"request": request})` → `.save()`
    crée la Page **et** ses blocs (nested via `hasPart`).

- [ ] **Step 1 : Écrire le test d'échec (création nested)**

```python
@pytest.mark.django_db
def test_page_create_serializer_nested_cree_page_et_blocs():
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page
    from api_v2.serializers import PageCreateSerializer, PageSchemaSerializer

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        payload = {
            "@type": "WebPage",
            "name": "Accueil API",
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "slug", "value": "accueil-api"},
                {"@type": "PropertyValue", "name": "publie", "value": True},
            ],
            "hasPart": [
                {"additionalType": "HERO", "headline": "Bienvenue"},
                {"additionalType": "PARAGRAPHE", "text": "<p>Bonjour</p>"},
            ],
        }
        ser = PageCreateSerializer(data=payload, context={"request": None})
        assert ser.is_valid(), ser.errors
        page = ser.save()
        assert page.slug == "accueil-api"
        assert page.publie is True
        assert page.blocs.count() == 2
        out = PageSchemaSerializer(page).data
        assert out["@type"] == "WebPage"
        assert len(out["hasPart"]) == 2
        assert out["hasPart"][0]["additionalType"] == "HERO"


@pytest.mark.django_db
def test_page_create_serializer_rejette_slug_reserve():
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from api_v2.serializers import PageCreateSerializer

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        payload = {
            "name": "X",
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "slug", "value": "admin"},
            ],
            "hasPart": [],
        }
        ser = PageCreateSerializer(data=payload, context={"request": None})
        assert not ser.is_valid()
        assert "slug" in str(ser.errors).lower() or "reserv" in str(ser.errors).lower()
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages_api.py -k page_create_serializer -q`
Expected : FAIL (`ImportError: PageCreateSerializer`).

- [ ] **Step 3 : Implémenter les serializers Page**

Ajouter à `api_v2/serializers.py` (après les serializers Bloc) :
```python
from pages.models import valider_slug_non_reserve
from django.core.exceptions import ValidationError as DjangoValidationError

# Champs meta de Page acceptes via additionalProperty (whitelist).
# / Page meta fields accepted via additionalProperty (whitelist).
CHAMPS_PAGE_AUTORISES = frozenset({
    "slug", "position", "publie", "est_accueil", "noindex",
    "meta_title", "meta_description",
})


class PageSchemaSerializer(serializers.Serializer):
    """Represente une Page en JSON-LD schema.org/WebPage (lecture seule).
    / Renders a Page as schema.org/WebPage JSON-LD (read-only)."""

    def to_representation(self, instance: "Page") -> Dict[str, Any]:
        blocs = [BlocSchemaSerializer(b).data
                 for b in instance.blocs.all().order_by("position")]
        props: List[Dict[str, Any]] = []
        for nom_champ in CHAMPS_PAGE_AUTORISES:
            if nom_champ == "meta_description":
                continue  # expose en `description`
            valeur = getattr(instance, nom_champ, None)
            if valeur in (None, "", [], {}):
                continue
            props.append({"@type": "PropertyValue", "name": nom_champ, "value": valeur})

        payload = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "identifier": str(instance.uuid),
            "name": instance.titre,
            "url": f"/{instance.slug}/",
            "description": instance.meta_description or None,
            "hasPart": blocs or None,
            "additionalProperty": props or None,
        }
        return {k: v for k, v in payload.items() if v not in (None, "", [])}


class PageCreateSerializer(serializers.Serializer):
    """Cree une Page et (option) ses blocs imbriques via hasPart.
    / Creates a Page and (optionally) its nested blocks via hasPart."""
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    additionalProperty = serializers.ListField(child=serializers.DictField(), required=False)
    hasPart = serializers.ListField(child=serializers.DictField(), required=False)

    def _meta_depuis_props(self, validated_data: Dict[str, Any]) -> Dict[str, Any]:
        # Deballe additionalProperty -> dict de champs meta autorises.
        # / Unpack additionalProperty -> dict of allowed meta fields.
        meta: Dict[str, Any] = {}
        for prop in (validated_data.get("additionalProperty") or []):
            nom = prop.get("name")
            if nom in CHAMPS_PAGE_AUTORISES:
                meta[nom] = prop.get("value")
        return meta

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        meta = self._meta_depuis_props(attrs)
        slug = meta.get("slug")
        # Slug obligatoire (sinon collision/SlugField unique) + anti-reserve.
        # / Slug required + reserved check.
        if not slug:
            raise serializers.ValidationError({"slug": _("Le slug est obligatoire.")})
        try:
            valider_slug_non_reserve(slug)
        except DjangoValidationError as e:
            raise serializers.ValidationError({"slug": e.messages})
        return attrs

    def create(self, validated_data: Dict[str, Any]) -> "Page":
        meta = self._meta_depuis_props(validated_data)
        page = Page(titre=validated_data["name"])
        if validated_data.get("description"):
            page.meta_description = validated_data["description"]
        for nom_champ, valeur in meta.items():
            setattr(page, nom_champ, valeur)
        page.full_clean(exclude=["uuid"])  # valide slug unique + reserves
        page.save()

        # Blocs imbriques (hasPart). / Nested blocks (hasPart).
        for index, donnees_bloc in enumerate(validated_data.get("hasPart") or []):
            donnees_bloc.setdefault("position", index)
            bloc_ser = BlocCreateSerializer(data=donnees_bloc, context={"page": page})
            bloc_ser.is_valid(raise_exception=True)
            bloc_ser.save()
        return page
```

- [ ] **Step 4 : Lancer les tests**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages_api.py -k page_create_serializer -q`
Expected : PASS (les deux).

- [ ] **Step 5 : Commit (proposer)**

Message : `feat(api_v2): add Page schema.org serializers (WebPage + nested hasPart)`

---

## Task A5 : ViewSets + routes + tests HTTP de bout en bout

**Files:**
- Modify: `api_v2/views.py` (ajouter `PageViewSet`, `BlocViewSet`)
- Modify: `api_v2/urls.py` (register routes)
- Test: `tests/pytest/test_pages_api.py`

**Interfaces:**
- Consumes : serializers A3/A4, `SemanticApiKeyPermission`.
- Produces : routes `/api/v2/pages/`, `/api/v2/pages/{uuid}/`,
  `/api/v2/pages/{uuid}/blocs/`, `/api/v2/blocs/{uuid}/`.

- [ ] **Step 1 : Écrire le test HTTP d'échec (CRUD via APIClient + clé)**

```python
@pytest.fixture
def cle_pages(db):
    """Cree une cle API avec droit `page` sur le tenant lespass et renvoie (raw_key).
    / Creates an API key with `page` right and returns the raw key string."""
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from BaseBillet.models import ExternalApiKey
    from rest_framework_api_key.models import APIKey
    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        api_key_obj, raw = APIKey.objects.create_key(name="pages-e2e")
        ExternalApiKey.objects.create(name="pages-e2e", key=api_key_obj, page=True)
    return raw


@pytest.mark.django_db
def test_http_create_page_nested_puis_patch_et_delete_bloc(cle_pages):
    from rest_framework.test import APIClient
    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}

    # Create nested
    body = {
        "@type": "WebPage", "name": "Page E2E",
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "slug", "value": "page-e2e"},
        ],
        "hasPart": [{"additionalType": "PARAGRAPHE", "text": "<p>Hi</p>"}],
    }
    r = client.post("/api/v2/pages/", body, format="json", **auth)
    assert r.status_code == 201, r.content
    page_uuid = r.json()["identifier"]
    bloc_uuid = r.json()["hasPart"][0]["identifier"]

    # Patch bloc
    r2 = client.patch(f"/api/v2/blocs/{bloc_uuid}/",
                      {"headline": "Titre ajoute"}, format="json", **auth)
    assert r2.status_code == 200, r2.content
    assert r2.json()["headline"] == "Titre ajoute"

    # Delete bloc
    r3 = client.delete(f"/api/v2/blocs/{bloc_uuid}/", **auth)
    assert r3.status_code == 204


@pytest.mark.django_db
def test_http_sans_permission_page_renvoie_403(db):
    from rest_framework.test import APIClient
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from BaseBillet.models import ExternalApiKey
    from rest_framework_api_key.models import APIKey
    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        api_key_obj, raw = APIKey.objects.create_key(name="pages-noperm")
        ExternalApiKey.objects.create(name="pages-noperm", key=api_key_obj, page=False)
    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {raw}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    r = client.post("/api/v2/pages/", {"name": "X"}, format="json", **auth)
    assert r.status_code == 403
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages_api.py -k http_ -q`
Expected : FAIL (404 sur `/api/v2/pages/` — route absente).

- [ ] **Step 3 : Implémenter les ViewSets**

Ajouter à `api_v2/views.py` (imports en tête : les serializers + `Page`, `Bloc`,
`get_object_or_404`) :
```python
class PageViewSet(viewsets.ViewSet):
    """API semantique des Pages (WebPage). / Semantic Pages API (WebPage).

    Header: Authorization: Api-Key <key> (droit `page`).
    """
    permission_classes = [SemanticApiKeyPermission]
    lookup_field = "uuid"
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def list(self, request):
        qs = Page.objects.all().order_by("position", "titre")
        return Response({"results": PageSchemaSerializer(qs, many=True).data})

    def retrieve(self, request, uuid=None):
        # uuid OU slug. / uuid OR slug.
        page = Page.objects.filter(uuid=uuid).first() if _ressemble_uuid(uuid) \
            else Page.objects.filter(slug=uuid).first()
        if not page:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(PageSchemaSerializer(page).data)

    def create(self, request):
        ser = PageCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        page = ser.save()
        return Response(PageSchemaSerializer(page).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, uuid=None):
        page = get_object_or_404(Page, uuid=uuid)
        # PATCH meta seulement : on reutilise le deballage additionalProperty.
        # / PATCH meta only.
        ser = PageCreateSerializer(data=request.data, context={"request": request},
                                   partial=True)
        # Validation legere : on autorise name + meta sans exiger le slug.
        meta = {}
        for prop in (request.data.get("additionalProperty") or []):
            if prop.get("name") in CHAMPS_PAGE_AUTORISES:
                meta[prop["name"]] = prop.get("value")
        if "name" in request.data:
            page.titre = request.data["name"]
        if "description" in request.data:
            page.meta_description = request.data["description"]
        for nom_champ, valeur in meta.items():
            if nom_champ == "slug":
                valider_slug_non_reserve(valeur)
            setattr(page, nom_champ, valeur)
        page.full_clean(exclude=["uuid"])
        page.save()
        return Response(PageSchemaSerializer(page).data)

    def destroy(self, request, uuid=None):
        page = get_object_or_404(Page, uuid=uuid)
        page.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="blocs")
    def ajouter_bloc(self, request, uuid=None):
        page = get_object_or_404(Page, uuid=uuid)
        donnees = dict(request.data)
        donnees.setdefault("position", page.blocs.count())
        ser = BlocCreateSerializer(data=donnees, context={"page": page})
        ser.is_valid(raise_exception=True)
        bloc = ser.save()
        return Response(BlocSchemaSerializer(bloc).data, status=status.HTTP_201_CREATED)


class BlocViewSet(viewsets.ViewSet):
    """API semantique des Blocs (WebPageElement). / Semantic Blocs API."""
    permission_classes = [SemanticApiKeyPermission]
    lookup_field = "uuid"
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def retrieve(self, request, uuid=None):
        bloc = get_object_or_404(Bloc, uuid=uuid)
        return Response(BlocSchemaSerializer(bloc).data)

    def partial_update(self, request, uuid=None):
        bloc = get_object_or_404(Bloc, uuid=uuid)
        # Edition d'un bloc : on remappe standard + additionalProperty (whitelist).
        # / Edit a block: remap standard + additionalProperty (whitelist).
        if "headline" in request.data:
            bloc.titre = request.data["headline"] or ""
        if "alternativeHeadline" in request.data:
            bloc.sous_titre = request.data["alternativeHeadline"] or ""
        if "text" in request.data:
            bloc.texte = clean_html(request.data["text"] or "")
        for prop in (request.data.get("additionalProperty") or []):
            nom = prop.get("name")
            if nom in CHAMPS_BLOC_AUTORISES:
                valeur = prop.get("value")
                if nom in CHAMPS_TEXTE_RICHE:
                    valeur = clean_html(valeur or "")
                setattr(bloc, nom, valeur)
        bloc.save()
        return Response(BlocSchemaSerializer(bloc).data)

    def destroy(self, request, uuid=None):
        bloc = get_object_or_404(Bloc, uuid=uuid)
        bloc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
```
Helper en haut de `api_v2/views.py` (après imports) :
```python
import uuid as _uuid_module

def _ressemble_uuid(valeur) -> bool:
    """True si la chaine est un UUID valide. / True if the string is a valid UUID."""
    try:
        _uuid_module.UUID(str(valeur))
        return True
    except (ValueError, TypeError):
        return False
```
Imports à compléter en tête (`from api_v2.serializers import ...`,
`from pages.models import Page, Bloc, valider_slug_non_reserve`,
`from api_v2.serializers import CHAMPS_PAGE_AUTORISES, CHAMPS_BLOC_AUTORISES, CHAMPS_TEXTE_RICHE`,
`from Administration.utils import clean_html`, `from django.shortcuts import get_object_or_404`).

- [ ] **Step 4 : Enregistrer les routes**

Dans `api_v2/urls.py` :
```python
from .views import PageViewSet, BlocViewSet
# basename = cle de api_permissions() (page / bloc)
router.register(r"pages", PageViewSet, basename="page")
router.register(r"blocs", BlocViewSet, basename="bloc")
```

- [ ] **Step 5 : Lancer les tests HTTP + check**

Run :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run pytest tests/pytest/test_pages_api.py -q
```
Expected : 0 issue + tous les tests PASS.

- [ ] **Step 6 : Commit (proposer)**

Message : `feat(api_v2): add Page/Bloc viewsets and routes (create nested, edit, delete)`

---

# SESSION B — Images, catalogue HTTP, types structurés, docs

## Task B1 : Images par URL (création nested)

**Files:**
- Modify: `api_v2/serializers.py` (helper download + branche image dans Bloc create)
- Test: `tests/pytest/test_pages_api.py`

**Interfaces:**
- Produces : `telecharger_et_valider_image(url) -> ContentFile|None` (validée Pillow,
  réutilise `_validate_uploaded_image`).

- [ ] **Step 1 : Test d'échec (image par URL, requests mocké)**

```python
@pytest.mark.django_db
def test_bloc_image_par_url(monkeypatch):
    import io
    from PIL import Image as PILImage
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page
    from api_v2.serializers import BlocCreateSerializer

    # Fabrique une vraie image PNG en memoire. / Build a real in-memory PNG.
    buf = io.BytesIO()
    PILImage.new("RGB", (10, 10), "blue").save(buf, format="PNG")
    contenu_png = buf.getvalue()

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "image/png"}
        content = contenu_png
        def raise_for_status(self): pass

    monkeypatch.setattr("api_v2.serializers.requests.get", lambda *a, **k: FakeResp())

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="img", slug="img-url")
        ser = BlocCreateSerializer(data={
            "additionalType": "IMAGE",
            "image": "https://exemple.fr/photo.png",
        }, context={"page": page})
        assert ser.is_valid(), ser.errors
        bloc = ser.save()
        assert bloc.image  # fichier enregistre
```

- [ ] **Step 2 : Lancer, vérifier l'échec** — `pytest ... -k image_par_url -q` → FAIL.

- [ ] **Step 3 : Implémenter le helper + brancher**

En tête de `api_v2/serializers.py` : `import requests`,
`from django.core.files.base import ContentFile`.
```python
def telecharger_et_valider_image(url: str):
    """Telecharge une image distante, la valide (Pillow), renvoie un ContentFile.
    / Downloads a remote image, validates it (Pillow), returns a ContentFile.

    Securite : timeout, content-type image/*, taille max 10 MiB, verify Pillow.
    Renvoie None si url vide. Leve ValidationError si invalide.
    """
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=10, stream=False)
        resp.raise_for_status()
    except Exception:
        raise serializers.ValidationError(_("Image distante inaccessible : %(u)s") % {"u": url})
    ctype = resp.headers.get("Content-Type", "")
    if ctype and not ctype.lower().startswith("image/"):
        raise serializers.ValidationError(_("L'URL ne pointe pas vers une image."))
    contenu = resp.content
    if len(contenu) > 10 * 1024 * 1024:
        raise serializers.ValidationError(_("Image trop grande (> 10 Mo)."))
    fichier = ContentFile(contenu)
    fichier.content_type = ctype or "image/*"
    _validate_uploaded_image(fichier)
    # Nom de fichier derive de l'URL (sans query). / Filename from URL.
    nom = url.split("?")[0].rsplit("/", 1)[-1] or "image"
    fichier.name = nom
    return fichier
```
Dans `BlocCreateSerializer.create`, après les champs standard, gérer `image` URL :
```python
        url_image = validated_data.get("image")
        if url_image:
            fichier = telecharger_et_valider_image(url_image)
            if fichier:
                bloc.image = fichier
```
(Placer ce bloc **avant** `bloc.save()`.)

- [ ] **Step 4 : Lancer** — PASS.
- [ ] **Step 5 : Commit (proposer)** — `feat(api_v2): accept block images by remote URL`

---

## Task B2 : Upload multipart (édition bloc)

**Files:** Modify `api_v2/views.py` (`BlocViewSet.partial_update`, `PageViewSet.ajouter_bloc`) ; Test idem.

- [ ] **Step 1 : Test multipart** (POST `/pages/{uuid}/blocs/` avec `format="multipart"`
  et un fichier image valide → bloc.image rempli). Utiliser
  `SimpleUploadedFile("p.png", contenu_png, content_type="image/png")`.
- [ ] **Step 2 : Lancer → FAIL.**
- [ ] **Step 3 : Brancher `request.FILES`** dans `ajouter_bloc` et `partial_update` :
```python
        # Upload multipart eventuel (image, image_secondaire, auteur_photo, video).
        # / Optional multipart upload.
        for nom_fichier in ("image", "image_secondaire", "auteur_photo", "video"):
            f = request.FILES.get(nom_fichier) if hasattr(request, "FILES") else None
            if f:
                if nom_fichier != "video":
                    _validate_uploaded_image(f)
                setattr(bloc, nom_fichier, f)
        bloc.save()
```
  (Pour `ajouter_bloc`, l'appliquer sur le `bloc` retourné par `ser.save()` avant
  la `Response`.) Importer `_validate_uploaded_image` depuis `api_v2.serializers`.
- [ ] **Step 4 : Lancer → PASS.**
- [ ] **Step 5 : Commit (proposer)** — `feat(api_v2): accept multipart image upload on block edit`

---

## Task B3 : Endpoint catalogue `block-types/` + dérivation admin

**Files:** Modify `api_v2/views.py` (action), `pages/admin.py` (conditional_fields dérivé) ; Test idem.

**Interfaces:** `GET /api/v2/pages/block-types/` → `{"blockTypes": [{"type","label","fields"}]}`.

- [ ] **Step 1 : Test catalogue HTTP** (auth clé `page`) :
```python
@pytest.mark.django_db
def test_http_block_types_catalogue(cle_pages):
    from rest_framework.test import APIClient
    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    r = client.get("/api/v2/pages/block-types/", **auth)
    assert r.status_code == 200
    types = {b["type"] for b in r.json()["blockTypes"]}
    assert len(types) == 14
    faq = next(b for b in r.json()["blockTypes"] if b["type"] == "FAQ")
    assert set(faq["fields"]) == {"titre", "texte", "repliable"}
```
- [ ] **Step 2 : Lancer → FAIL.**
- [ ] **Step 3 : Implémenter l'action** dans `PageViewSet` :
```python
    @action(detail=False, methods=["get"], url_path="block-types")
    def block_types(self, request):
        from pages.blocs_catalogue import CHAMPS_PAR_TYPE
        libelles = dict(Bloc.TYPE_BLOC_CHOICES)
        types = [{"type": code, "label": str(libelles.get(code, code)),
                  "fields": champs}
                 for code, champs in CHAMPS_PAR_TYPE.items()]
        return Response({"blockTypes": types})
```
> ⚠️ DRF route `block-types/` AVANT `{uuid}/` car `detail=False` → pas de collision,
> mais vérifier que `retrieve` ne capte pas « block-types » (uuid invalide → 404 propre
> grâce à `_ressemble_uuid` → recherche par slug → 404). OK.

- [ ] **Step 4 : Lancer → PASS.**
- [ ] **Step 5 : (Dérivation admin — optionnel, avec garde-fou)** Ajouter dans
  `pages/blocs_catalogue.py` un helper qui régénère le dict Alpine, PUIS un test
  d'équivalence AVANT de toucher l'admin :
```python
# Test (tests/pytest/test_pages_api.py) — garde-fou non-regression admin :
def test_conditional_fields_admin_equivaut_au_catalogue():
    from pages.admin import BlocAdmin  # ou la classe reelle
    from pages.blocs_catalogue import conditional_fields_alpine
    assert conditional_fields_alpine() == BlocAdmin.conditional_fields
```
  Si l'équivalence n'est pas exacte (l'admin a des nuances), **ne pas** refactoriser
  l'admin : laisser `conditional_fields` tel quel et documenter que le catalogue est
  la source de l'API uniquement. (YAGNI — ne pas risquer l'admin qui fonctionne.)
- [ ] **Step 6 : Commit (proposer)** — `feat(api_v2): add block-types catalogue endpoint`

---

## Task B4 : Types structurés (GALERIE, JSON points_gps/contenu)

**Files:** Modify `api_v2/serializers.py` ; Test idem.

- [ ] **Step 1 : Tests round-trip** :
  - `CARTE_LEAFLET` avec `points_gps` (liste d'objets) passé en additionalProperty
    → persisté en JSONField, ré-exposé identique.
  - `INFOS` avec `contenu` (liste typée) idem.
  - `GALERIE` : `image` = liste d'ImageObject `[{"contentUrl": "...", "caption": ".."}]`
    → crée des `ImageGalerie` ; en sortie, `image` = liste d'ImageObject.
- [ ] **Step 2 : Lancer → FAIL.**
- [ ] **Step 3 : Implémenter** :
  - `points_gps`/`contenu` : déjà gérés par la branche additionalProperty générique
    (ce sont des champs du catalogue → ajouter `"points_gps"`, `"contenu"` aux listes
    `CARTE_LEAFLET`/`INFOS` du catalogue — déjà fait en A2). `value` JSON passe tel quel.
    Vérifier qu'aucun `clean_html` ne s'applique (pas dans `CHAMPS_TEXTE_RICHE`). OK.
  - `GALERIE` : dans `BlocCreateSerializer.create`, après save, si
    `type_bloc == "GALERIE"` et `image` est une liste → créer les `ImageGalerie` :
```python
        from pages.models import ImageGalerie
        images_galerie = self.initial_data.get("image")
        if bloc.type_bloc == "GALERIE" and isinstance(images_galerie, list):
            for i, img in enumerate(images_galerie):
                url = img.get("contentUrl") if isinstance(img, dict) else img
                fichier = telecharger_et_valider_image(url)
                if fichier:
                    ImageGalerie.objects.create(
                        bloc=bloc, image=fichier,
                        legende=(img.get("caption") if isinstance(img, dict) else "") or "",
                        position=i)
```
    > Note : `image` est déclaré `CharField` dans BlocCreateSerializer ; pour GALERIE
    > la liste arrive via `self.initial_data` (non validée par le CharField). Adapter :
    > rendre `image` tolérant (`required=False`) et lire la liste depuis `initial_data`.
  - En sortie (`BlocSchemaSerializer`), si `GALERIE` : remplacer `image` par
    `[{"@type":"ImageObject","contentUrl": ig.image.url, "caption": ig.legende}
    for ig in instance.images_galerie.all()]`.
- [ ] **Step 4 : Lancer → PASS.**
- [ ] **Step 5 : Commit (proposer)** — `feat(api_v2): support gallery (ImageObject[]) and JSON blocks`

---

## Task B5 : Documentation (openapi, GUIDELINES, CHANGELOG, A TESTER)

**Files:** `api_v2/openapi-schema.yaml`, `api_v2/GUIDELINES.md`,
`CHANGELOG.md`, `A TESTER et DOCUMENTER/api-v2-pages.md`.

- [ ] **Step 1 : openapi-schema.yaml** — ajouter `/pages/`, `/pages/{uuid}/`,
  `/pages/{uuid}/blocs/`, `/pages/block-types/`, `/blocs/{uuid}/` (payloads WebPage /
  WebPageElement, exemples nested, multipart, additionalProperty).
- [ ] **Step 2 : GUIDELINES.md** — section « Pages API (schema.org/WebPage) » :
  mapping Page→WebPage, Bloc→WebPageElement, additionalType=type_bloc, additionalProperty
  fourre-tout, images URL+multipart, catalogue.
- [ ] **Step 3 : CHANGELOG.md** — entrée bilingue numérotée (Quoi/What, Pourquoi/Why,
  fichiers, migration **Oui** = `0XXX_externalapikey_page`).
- [ ] **Step 4 : `A TESTER et DOCUMENTER/api-v2-pages.md`** — scénarios manuels :
  créer une clé `page`, `curl` create nested, ajouter un bloc, patch, delete, catalogue,
  vérif rendu sur `https://lespass.tibillet.localhost/<slug>/`.
- [ ] **Step 5 : Suite complète + check final**

Run :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run pytest tests/pytest/test_pages_api.py -q
```
Expected : 0 issue + tous PASS.
- [ ] **Step 6 : Commit (proposer)** — `docs(api_v2): document pages API (openapi, guidelines, changelog)`

---

## Notes d'exécution

- **Isolation cross-tenant** : ajouter en fin de Session A un test créant une page
  sur `lespass` et vérifiant qu'une clé d'un AUTRE tenant ne la voit pas (HTTP_HOST
  du second tenant + clé du second tenant → 404 sur l'uuid de la 1ère).
- **Pièges** : `tenant_context` obligatoire pour tout `create()` ; `clean_html` vient
  de `Administration.utils` ; ne pas lancer le serveur (byobu) ; ruff format fichiers
  neufs uniquement (`pages/blocs_catalogue.py`, `tests/pytest/test_pages_api.py`).
- **Vérif visuelle** : après Session B, créer une page via API puis l'ouvrir sur
  `https://lespass.tibillet.localhost/<slug>/` pour confirmer le rendu des blocs.
