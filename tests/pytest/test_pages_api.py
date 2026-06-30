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


@pytest.fixture
def cle_pages(db):
    """Cree une cle API avec droit `page` sur le tenant lespass et renvoie la cle brute.
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

    r2 = client.patch(f"/api/v2/blocs/{bloc_uuid}/",
                      {"headline": "Titre ajoute"}, format="json", **auth)
    assert r2.status_code == 200, r2.content
    assert r2.json()["headline"] == "Titre ajoute"

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


@pytest.mark.django_db
def test_http_isolation_cross_tenant(cle_pages):
    """Une page creee sur lespass n'est PAS accessible avec une cle d'un autre tenant.
    / A page created on lespass is NOT reachable with another tenant's key."""
    from rest_framework.test import APIClient
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from BaseBillet.models import ExternalApiKey
    from rest_framework_api_key.models import APIKey

    client = APIClient()
    auth_lespass = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
                    "HTTP_HOST": "lespass.tibillet.localhost"}
    # Cree une page sur lespass.
    body = {"name": "Privee", "additionalProperty": [
        {"@type": "PropertyValue", "name": "slug", "value": "privee-lespass"}], "hasPart": []}
    r = client.post("/api/v2/pages/", body, format="json", **auth_lespass)
    assert r.status_code == 201, r.content
    page_uuid = r.json()["identifier"]

    # Cle sur un AUTRE tenant. On choisit le premier tenant != lespass/public.
    autre = Client.objects.exclude(schema_name__in=["lespass", "public"]).first()
    assert autre is not None, "Besoin d'un second tenant pour le test cross-tenant"
    with tenant_context(autre):
        api_key_obj, raw_autre = APIKey.objects.create_key(name="autre-pages")
        ExternalApiKey.objects.create(name="autre-pages", key=api_key_obj, page=True)
    auth_autre = {"HTTP_AUTHORIZATION": f"Api-Key {raw_autre}",
                  "HTTP_HOST": f"{autre.schema_name}.tibillet.localhost"}
    # L'uuid de la page lespass n'existe pas dans le schema de l'autre tenant -> 404.
    r2 = client.get(f"/api/v2/pages/{page_uuid}/", **auth_autre)
    assert r2.status_code == 404
