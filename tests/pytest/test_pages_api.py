import pytest
from rest_framework import serializers
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
def test_catalogue_blocs_couvre_tous_les_types():
    from pages.blocs_catalogue import CHAMPS_PAR_TYPE, CHAMPS_BLOC_AUTORISES, TYPES_BLOC
    from pages.models import Bloc
    # Le catalogue couvre EXACTEMENT les types du modele (aucun oubli).
    # / The catalogue covers EXACTLY the model's types (no omission).
    types_modele = {code for code, _label in Bloc.TYPE_BLOC_CHOICES}
    assert set(CHAMPS_PAR_TYPE.keys()) == types_modele
    assert len(TYPES_BLOC) == len(types_modele)
    # La whitelist est l'union, et ne contient que de vrais champs du modele.
    noms_champs_modele = {f.name for f in Bloc._meta.get_fields()}
    assert CHAMPS_BLOC_AUTORISES <= noms_champs_modele
    # Un type a rendu unique ne porte que ses champs de contenu.
    # / A single-rendering type only carries its content fields.
    assert set(CHAMPS_PAR_TYPE["FAQ"]) == {"titre", "texte"}
    # Un type a plusieurs rendus declare `affichage` : sans lui, l'API ne
    # pourrait pas choisir la forme du bloc.
    # / A multi-rendering type declares `affichage`: without it the API could
    # not pick the block's shape.
    assert "affichage" in CHAMPS_PAR_TYPE["INTEGRATION"]
    assert set(CHAMPS_PAR_TYPE["INTEGRATION"]) == {
        "affichage", "titre", "sous_titre", "embed_url", "hauteur_px"}
    assert set(CHAMPS_PAR_TYPE["IMAGES"]) == {"affichage", "titre", "image"}
    # La source d'une liste choisit une requete, pas un rendu : ce n'est donc
    # pas un affichage. / A list's source picks a query, not a rendering.
    assert "source" in CHAMPS_PAR_TYPE["LISTE"]
    assert "affichage" not in CHAMPS_PAR_TYPE["LISTE"]


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
            ],
        }
        ser = BlocCreateSerializer(data=payload, context={"page": page})
        assert ser.is_valid(), ser.errors
        bloc = ser.save()
        assert bloc.type_bloc == "FAQ"
        assert bloc.titre == "Une question ?"
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
                {"additionalType": "SECTION", "headline": "Bienvenue"},
                {"additionalType": "TEXTE", "text": "<p>Bonjour</p>"},
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
        assert out["hasPart"][0]["additionalType"] == "SECTION"


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
        "hasPart": [{"additionalType": "TEXTE", "text": "<p>Hi</p>"}],
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
    # order_by pour un choix de tenant DETERMINISTE (evite un test flaky selon
    # l'ordre non garanti de la base). / order_by for a DETERMINISTIC tenant pick
    # (avoids a flaky test depending on the DB's unguaranteed ordering).
    autre = Client.objects.exclude(
        schema_name__in=["lespass", "public"]
    ).order_by("schema_name").first()
    assert autre is not None, "Besoin d'un second tenant pour le test cross-tenant"
    with tenant_context(autre):
        api_key_obj, raw_autre = APIKey.objects.create_key(name="autre-pages")
        ExternalApiKey.objects.create(name="autre-pages", key=api_key_obj, page=True)
    auth_autre = {"HTTP_AUTHORIZATION": f"Api-Key {raw_autre}",
                  "HTTP_HOST": f"{autre.schema_name}.tibillet.localhost"}
    # L'uuid de la page lespass n'existe pas dans le schema de l'autre tenant -> 404.
    r2 = client.get(f"/api/v2/pages/{page_uuid}/", **auth_autre)
    assert r2.status_code == 404


@pytest.mark.django_db
def test_bloc_create_neutralise_url_javascript():
    """Un bouton_url avec schema javascript: est vide a la creation (anti-XSS).
    / A bouton_url with a javascript: scheme is emptied on create (anti-XSS)."""
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page
    from api_v2.serializers import BlocCreateSerializer

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="x", slug="xss-bouton")
        ser = BlocCreateSerializer(data={
            "additionalType": "SECTION",
            "headline": "Clique",
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "bouton_label", "value": "Go"},
                {"@type": "PropertyValue", "name": "bouton_url", "value": "javascript:alert(document.cookie)"},
                {"@type": "PropertyValue", "name": "embed_url", "value": "vbscript:msgbox(1)"},
            ],
        }, context={"page": page})
        assert ser.is_valid(), ser.errors
        bloc = ser.save()
        assert bloc.bouton_url == ""   # neutralise
        assert bloc.embed_url == ""    # neutralise
        assert bloc.bouton_label == "Go"  # champ sain conserve


@pytest.mark.django_db
def test_bloc_create_ignore_champ_video_en_additional_property():
    """Un champ fichier NON telechargeable (video) passe en string via additionalProperty
    est IGNORE (jamais de string brute sur un FileField).
    / A non-downloadable file field (video) passed as a string via additionalProperty is
    IGNORED (never a raw string on a FileField)."""
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page
    from api_v2.serializers import BlocCreateSerializer

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="x", slug="video-string")
        ser = BlocCreateSerializer(data={
            "additionalType": "SECTION",
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "video", "value": "javascript:alert(1)"},
            ],
        }, context={"page": page})
        assert ser.is_valid(), ser.errors
        bloc = ser.save()
        assert not bloc.video  # vide, pas de corruption


def test_url_a_schema_dangereux_promu_dans_utils():
    """La fonction de neutralisation est disponible dans Administration.utils.
    / The neutralization function is available in Administration.utils."""
    from Administration.utils import url_a_schema_dangereux
    assert url_a_schema_dangereux("javascript:alert(1)") is True
    assert url_a_schema_dangereux("java\tscript:alert(1)") is True  # obfuscation
    assert url_a_schema_dangereux("https://exemple.fr") is False
    assert url_a_schema_dangereux("/event/") is False
    assert url_a_schema_dangereux("") is False


@pytest.mark.django_db
def test_http_patch_bloc_neutralise_url_javascript(cle_pages):
    """PATCH d'un bloc : un bouton_url javascript: est neutralise (gap B0).
    / PATCH a block: a javascript: bouton_url is neutralized."""
    from rest_framework.test import APIClient
    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    body = {"@type": "WebPage", "name": "XSS patch",
            "additionalProperty": [{"@type": "PropertyValue", "name": "slug", "value": "xss-patch"}],
            "hasPart": [{"additionalType": "SECTION", "headline": "x"}]}
    r = client.post("/api/v2/pages/", body, format="json", **auth)
    assert r.status_code == 201, r.content
    bloc_uuid = r.json()["hasPart"][0]["identifier"]
    # PATCH avec une URL dangereuse via additionalProperty.
    r2 = client.patch(f"/api/v2/blocs/{bloc_uuid}/", {
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "bouton_url", "value": "javascript:alert(1)"},
        ]}, format="json", **auth)
    assert r2.status_code == 200, r2.content
    # La sortie ne doit PAS exposer une URL javascript: ; le champ est vide.
    props = {p["name"]: p["value"] for p in (r2.json().get("additionalProperty") or [])}
    assert props.get("bouton_url", "") == ""


def _png_bytes():
    import io
    from PIL import Image as PILImage
    buf = io.BytesIO()
    PILImage.new("RGB", (8, 8), "red").save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.django_db
def test_http_ajouter_bloc_multipart_upload_image(cle_pages):
    """POST multipart sur /pages/{uuid}/blocs/ : le fichier image est enregistre.
    / Multipart POST on the sub-action: the uploaded image file is stored."""
    from rest_framework.test import APIClient
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page, Bloc

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="m", slug="multipart-add")
        page_uuid = str(page.uuid)

    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    fichier = SimpleUploadedFile("p.png", _png_bytes(), content_type="image/png")
    r = client.post(f"/api/v2/pages/{page_uuid}/blocs/",
                    {"additionalType": "IMAGES", "image": fichier},
                    format="multipart", **auth)
    assert r.status_code == 201, r.content
    with tenant_context(tenant):
        bloc = Bloc.objects.get(uuid=r.json()["identifier"])
        assert bloc.image  # fichier enregistre


@pytest.mark.django_db
def test_http_patch_bloc_multipart_upload_image(cle_pages):
    """PATCH multipart sur /blocs/{uuid}/ : le fichier image remplace l'image.
    / Multipart PATCH: the uploaded image replaces the block image."""
    from rest_framework.test import APIClient
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page, Bloc

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="m2", slug="multipart-patch")
        bloc = Bloc.objects.create(page=page, type_bloc="IMAGES", affichage="PLEINE_LARGEUR")
        bloc_uuid = str(bloc.uuid)

    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    fichier = SimpleUploadedFile("q.png", _png_bytes(), content_type="image/png")
    r = client.patch(f"/api/v2/blocs/{bloc_uuid}/", {"image": fichier},
                     format="multipart", **auth)
    assert r.status_code == 200, r.content
    with tenant_context(tenant):
        bloc.refresh_from_db()
        assert bloc.image


@pytest.mark.django_db
def test_http_block_types_catalogue(cle_pages):
    from rest_framework.test import APIClient
    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    r = client.get("/api/v2/pages/block-types/", **auth)
    assert r.status_code == 200, r.content
    types = {b["type"] for b in r.json()["blockTypes"]}
    # Le catalogue expose tous les types du modele (dont les nouveaux CHANTIER-06).
    # / The catalogue exposes all model types (including the new CHANTIER-06 ones).
    from pages.models import Bloc
    assert types == {code for code, _ in Bloc.TYPE_BLOC_CHOICES}
    # Les 8 types d'intention, et rien d'autre : le catalogue est ferme.
    # / The 8 intent types and nothing else: the catalogue is closed.
    assert types == {
        "TEXTE", "SECTION", "IMAGES", "INTEGRATION", "LIEU", "FAQ", "LISTE",
        "CARTE_FIGEE"}
    # INTEGRATION expose hauteur_px et l'affichage qui choisit son pipeline.
    # / INTEGRATION exposes hauteur_px and the affichage picking its pipeline.
    integration = next(
        b for b in r.json()["blockTypes"] if b["type"] == "INTEGRATION")
    assert "hauteur_px" in integration["fields"]
    assert "affichage" in integration["fields"]
    faq = next(b for b in r.json()["blockTypes"] if b["type"] == "FAQ")
    assert set(faq["fields"]) == {"titre", "texte"}
    # Chaque entree a un label non vide (i18n display).
    assert all(b["label"] for b in r.json()["blockTypes"])


@pytest.mark.django_db
def test_bloc_carte_leaflet_points_gps_roundtrip():
    """points_gps (JSON) via additionalProperty est stocke et re-expose tel quel.
    / points_gps (JSON) via additionalProperty is stored and re-exposed as-is."""
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page
    from api_v2.serializers import BlocCreateSerializer, BlocSchemaSerializer

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="c", slug="leaflet-rt")
        pts = [{"lat": 43.6, "lng": 1.44, "label": "La Cite"}]
        ser = BlocCreateSerializer(data={
            "additionalType": "LIEU",
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "points_gps", "value": pts},
            ],
        }, context={"page": page})
        assert ser.is_valid(), ser.errors
        bloc = ser.save()
        assert bloc.points_gps == pts
        out = BlocSchemaSerializer(bloc).data
        props = {p["name"]: p["value"] for p in (out.get("additionalProperty") or [])}
        assert props["points_gps"] == pts


@pytest.mark.django_db
def test_bloc_points_gps_doit_etre_une_liste():
    """points_gps non-liste -> 400 (garde de structure).
    / points_gps not a list -> 400 (structure guard)."""
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page
    from api_v2.serializers import BlocCreateSerializer
    from rest_framework import serializers as drf
    import pytest as _pytest

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="c2", slug="leaflet-bad")
        ser = BlocCreateSerializer(data={
            "additionalType": "LIEU",
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "points_gps", "value": {"lat": 1}},
            ],
        }, context={"page": page})
        assert ser.is_valid(), ser.errors
        with _pytest.raises(drf.ValidationError):
            ser.save()


@pytest.mark.django_db
def test_http_patch_bloc_points_gps_doit_etre_liste(cle_pages):
    """PATCH d'un bloc avec points_gps non-liste -> 400 (coherence avec CREATE).
    / PATCH a block with a non-list points_gps -> 400 (consistency with CREATE)."""
    from rest_framework.test import APIClient
    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    body = {"@type": "WebPage", "name": "pg",
            "additionalProperty": [{"@type": "PropertyValue", "name": "slug", "value": "patch-gps"}],
            "hasPart": [{"additionalType": "LIEU", "headline": "c"}]}
    r = client.post("/api/v2/pages/", body, format="json", **auth)
    assert r.status_code == 201, r.content
    bloc_uuid = r.json()["hasPart"][0]["identifier"]
    r2 = client.patch(f"/api/v2/blocs/{bloc_uuid}/", {
        "additionalProperty": [{"@type": "PropertyValue", "name": "points_gps", "value": {"lat": 1}}],
    }, format="json", **auth)
    assert r2.status_code == 400, r2.content


@pytest.mark.django_db
def test_http_ajouter_bloc_multipart_video_est_ignoree(cle_pages):
    """L'API n'uploade plus de fichier video (multipart) : le champ video reste vide.
    Pour une video, utiliser le bloc EMBED. / The API no longer uploads a video file;
    the video field stays empty. Use the EMBED block for videos."""
    from rest_framework.test import APIClient
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page, Bloc

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="v", slug="no-video-upload")
        page_uuid = str(page.uuid)

    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    faux_video = SimpleUploadedFile("clip.mp4", b"\x00\x00\x00\x18ftypmp42", content_type="video/mp4")
    r = client.post(f"/api/v2/pages/{page_uuid}/blocs/",
                    {"additionalType": "SECTION", "video": faux_video},
                    format="multipart", **auth)
    assert r.status_code == 201, r.content
    with tenant_context(tenant):
        bloc = Bloc.objects.get(uuid=r.json()["identifier"])
        assert not bloc.video  # la video n'a PAS ete uploadee par l'API


@pytest.mark.django_db
def test_page_create_avec_parent_ispartof(cle_pages):
    """Créer une page enfant en référençant le parent via isPartOf (slug).
    / Create a child page referencing the parent via isPartOf (slug)."""
    from rest_framework.test import APIClient
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page
    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    # Page parente
    rp = client.post("/api/v2/pages/", {
        "name": "Parent", "additionalProperty": [
            {"@type": "PropertyValue", "name": "slug", "value": "le-parent"}], "hasPart": []},
        format="json", **auth)
    assert rp.status_code == 201, rp.content
    # Page enfant avec isPartOf = slug du parent
    re = client.post("/api/v2/pages/", {
        "name": "Enfant", "isPartOf": "le-parent",
        "additionalProperty": [{"@type": "PropertyValue", "name": "slug", "value": "l-enfant"}],
        "hasPart": []}, format="json", **auth)
    assert re.status_code == 201, re.content
    # Sortie : isPartOf expose le parent
    assert re.json()["isPartOf"]["@type"] == "WebPage"
    assert re.json()["isPartOf"]["name"] == "Parent"
    # En base : le parent est bien relie
    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        enfant = Page.objects.get(slug="l-enfant")
        assert enfant.parent is not None
        assert enfant.parent.slug == "le-parent"


@pytest.mark.django_db
def test_page_create_parent_introuvable_400(cle_pages):
    """isPartOf pointant vers une page inexistante -> 400.
    / isPartOf pointing to a non-existent page -> 400."""
    from rest_framework.test import APIClient
    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    r = client.post("/api/v2/pages/", {
        "name": "Orphelin", "isPartOf": "slug-qui-nexiste-pas",
        "additionalProperty": [{"@type": "PropertyValue", "name": "slug", "value": "orphelin"}],
        "hasPart": []}, format="json", **auth)
    assert r.status_code == 400, r.content


@pytest.mark.django_db
def test_page_create_hierarchie_profonde_puis_trop_profonde(cle_pages):
    """
    L'API accepte un arbre profond, et refuse le niveau de trop en 400.

    La profondeur est bornee cote modele : sans ce garde, un arbre sans fin
    rendrait la navigation illisible et l'admin inutilisable.
    """
    from rest_framework.test import APIClient
    from pages.models import PROFONDEUR_MAX_ARBRE

    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}

    parent_slug = None
    for rang in range(1, PROFONDEUR_MAX_ARBRE + 1):
        charge = {
            "name": f"Niveau {rang}",
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "slug", "value": f"niveau-{rang}"}],
            "hasPart": [],
        }
        if parent_slug:
            charge["isPartOf"] = parent_slug
        reponse = client.post("/api/v2/pages/", charge, format="json", **auth)
        assert reponse.status_code == 201, reponse.content
        parent_slug = f"niveau-{rang}"

    # Un niveau de plus est refuse, avec un 400 et non un 500.
    de_trop = client.post("/api/v2/pages/", {
        "name": "De trop", "isPartOf": parent_slug,
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "slug", "value": "niveau-de-trop"}],
        "hasPart": [],
    }, format="json", **auth)
    assert de_trop.status_code == 400, de_trop.content


@pytest.mark.django_db
def test_page_patch_retire_le_parent(cle_pages):
    """PATCH isPartOf vide -> la page redevient top-level (parent = None).
    / PATCH with empty isPartOf -> page becomes top-level again (parent = None)."""
    from rest_framework.test import APIClient
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page
    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    client.post("/api/v2/pages/", {"name": "P", "additionalProperty": [
        {"@type": "PropertyValue", "name": "slug", "value": "patch-parent"}], "hasPart": []},
        format="json", **auth)
    re = client.post("/api/v2/pages/", {"name": "E", "isPartOf": "patch-parent",
        "additionalProperty": [{"@type": "PropertyValue", "name": "slug", "value": "patch-enfant"}],
        "hasPart": []}, format="json", **auth)
    enfant_uuid = re.json()["identifier"]
    rp = client.patch(f"/api/v2/pages/{enfant_uuid}/", {"isPartOf": ""}, format="json", **auth)
    assert rp.status_code == 200, rp.content
    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        assert Page.objects.get(uuid=enfant_uuid).parent is None


# ---------------------------------------------------------------------------
# CHANTIER 06 — Création via API v2 des blocs IFRAME / NEWSLETTER / PARTENAIRES
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_bloc_integration_widget_cree_avec_hauteur_px():
    """IFRAME : embed_url + hauteur_px (additionalProperty) -> settés ; roundtrip lecture."""
    from pages.models import Page
    from api_v2.serializers import BlocCreateSerializer, BlocSchemaSerializer

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="i", slug="iframe-api")
        ser = BlocCreateSerializer(data={
            "additionalType": "INTEGRATION",
            "headline": "Le plan",
            "additionalProperty": [
                # L'affichage choisit le pipeline de securite du contenu
                # integre : il se pose explicitement, jamais depuis l'URL.
                # / The affichage picks the embedded content's security
                # pipeline: set explicitly, never inferred from the URL.
                {"@type": "PropertyValue", "name": "affichage", "value": "WIDGET"},
                {"@type": "PropertyValue", "name": "embed_url",
                 "value": "https://www.openstreetmap.org/export/embed.html"},
                {"@type": "PropertyValue", "name": "hauteur_px", "value": 420},
            ],
        }, context={"page": page})
        assert ser.is_valid(), ser.errors
        bloc = ser.save()
        assert bloc.type_bloc == "INTEGRATION"
        assert bloc.affichage == "WIDGET"
        assert bloc.embed_url == "https://www.openstreetmap.org/export/embed.html"
        assert bloc.hauteur_px == 420
        out = BlocSchemaSerializer(bloc).data
        props = {p["name"]: p["value"] for p in out.get("additionalProperty", [])}
        assert props.get("hauteur_px") == 420


@pytest.mark.django_db
def test_bloc_integration_newsletter_cree_avec_embed_url():
    """NEWSLETTER : headline/alternativeHeadline + embed_url (data-site Ghost)."""
    from pages.models import Page
    from api_v2.serializers import BlocCreateSerializer

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="n", slug="newsletter-api")
        ser = BlocCreateSerializer(data={
            "additionalType": "INTEGRATION",
            "headline": "Les news de TiBillet",
            "alternativeHeadline": "La boite a outils d'organisation collective",
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "affichage", "value": "NEWSLETTER"},
                {"@type": "PropertyValue", "name": "embed_url",
                 "value": "https://ghost.tibillet.coop/"},
            ],
        }, context={"page": page})
        assert ser.is_valid(), ser.errors
        bloc = ser.save()
        assert bloc.type_bloc == "INTEGRATION"
        assert bloc.affichage == "NEWSLETTER"
        assert bloc.titre == "Les news de TiBillet"
        assert bloc.sous_titre == "La boite a outils d'organisation collective"
        assert bloc.embed_url == "https://ghost.tibillet.coop/"


# ---------------------------------------------------------------------------
# Bloc TEXTE : source Markdown preservee
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_http_patch_bloc_texte_ne_mutile_pas(cle_pages, monkeypatch):
    """PATCH d'un bloc MARKDOWN ne passe pas par clean_html (source preservee)."""
    from rest_framework.test import APIClient
    from pages.models import Page, Bloc

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="mdp", slug="pytest-md-patch")
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.TEXTE, texte="ancien")
        uuid = str(bloc.uuid)

    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    r = client.patch(f"/api/v2/blocs/{uuid}/",
                     {"text": "## H\n\n<https://exemple.fr> et **gras**."},
                     format="json", **auth)
    assert r.status_code == 200, r.content
    with tenant_context(tenant):
        bloc.refresh_from_db()
        assert "<https://exemple.fr>" in bloc.texte
        assert "**gras**" in bloc.texte
        Page.objects.filter(slug="pytest-md-patch").delete()


@pytest.mark.django_db
def test_api_refuse_un_affichage_etranger_au_type():
    """
    L'API refuse un couple (type, affichage) que le catalogue n'autorise pas.

    Sans ce garde, l'API stocke un couple qu'AUCUN gabarit ne sait rendre : la
    page publique qui porte le bloc sort alors en 500, loin de l'appel fautif.
    La table AFFICHAGES_PAR_TYPE doit donc s'appliquer a la creation comme au
    PATCH, pas seulement dans l'admin.
    """
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page
    from api_v2.serializers import BlocCreateSerializer

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="Garde", slug="pytest-garde-affichage")
        ser = BlocCreateSerializer(data={
            "additionalType": "SECTION",
            "headline": "Une section",
            "additionalProperty": [
                # BANDE_LOGOS appartient au type IMAGES, pas a SECTION.
                {"@type": "PropertyValue", "name": "affichage", "value": "BANDE_LOGOS"},
            ],
        }, context={"page": page})
        ser.is_valid()
        with pytest.raises(serializers.ValidationError) as erreur:
            ser.save()
        assert "affichage" in erreur.value.detail
        page.delete()


def test_chaque_couple_type_affichage_a_un_gabarit():
    """
    Tout couple (type, affichage) stockable sait se rendre.

    Le rendu cherche `bloc_<type>_<affichage>.html` puis retombe sur
    `bloc_<type>.html`. Un couple sans aucun des deux fait sortir la page
    entiere en TemplateDoesNotExist — et rien avant le rendu ne l'annonce.
    """
    from django.template.loader import select_template
    from django.template import TemplateDoesNotExist
    from pages.blocs_catalogue import AFFICHAGES_PAR_TYPE

    manquants = []
    for type_bloc, affichages in AFFICHAGES_PAR_TYPE.items():
        # Un type a rendu unique n'a qu'un gabarit ; sinon un par affichage.
        for affichage in (affichages or ("",)):
            candidats = []
            if affichage:
                candidats.append(
                    f"pages/classic/partials/bloc_{type_bloc.lower()}_{affichage.lower()}.html")
            candidats.append(f"pages/classic/partials/bloc_{type_bloc.lower()}.html")
            try:
                select_template(candidats)
            except TemplateDoesNotExist:
                manquants.append((type_bloc, affichage))

    assert manquants == [], f"couples sans gabarit : {manquants}"


def test_champs_par_affichage_est_un_sous_ensemble_du_type():
    """
    Tout champ declare pour un affichage existe dans son type.

    CHAMPS_PAR_AFFICHAGE resserre CHAMPS_PAR_TYPE au niveau de l'affichage
    (c'est lui qui pilote conditional_fields dans l'admin). Un champ qui y
    figure sans etre dans le type ne serait jamais rendu visible : le
    formulaire n'a pas ce champ a montrer.
    """
    from pages.blocs_catalogue import CHAMPS_PAR_AFFICHAGE, CHAMPS_PAR_TYPE

    intrus = []
    for type_bloc, par_affichage in CHAMPS_PAR_AFFICHAGE.items():
        champs_du_type = set(CHAMPS_PAR_TYPE[type_bloc])
        for affichage, champs in par_affichage.items():
            for champ in champs:
                if champ not in champs_du_type:
                    intrus.append((type_bloc, affichage, champ))

    assert intrus == [], f"champs hors du type : {intrus}"


def test_chaque_affichage_declare_ses_champs():
    """
    Un type liste dans CHAMPS_PAR_AFFICHAGE couvre TOUS ses affichages.

    Un affichage oublie retomberait sur « aucun champ » dans
    `_visibilite_des_champs()` : sa fiche s'ouvrirait vide dans l'admin, sans
    aucun message d'erreur.
    """
    from pages.blocs_catalogue import AFFICHAGES_PAR_TYPE, CHAMPS_PAR_AFFICHAGE

    oublies = []
    for type_bloc, par_affichage in CHAMPS_PAR_AFFICHAGE.items():
        for affichage in AFFICHAGES_PAR_TYPE[type_bloc]:
            if affichage not in par_affichage:
                oublies.append((type_bloc, affichage))

    assert oublies == [], f"affichages sans champs declares : {oublies}"


def test_chaque_champ_du_catalogue_est_visible_quelque_part():
    """
    Aucun champ du catalogue n'est rendu inatteignable par le resserrage.

    Si un champ est declare pour un type mais pour AUCUN de ses affichages, il
    reste dans le formulaire sans jamais s'afficher : impossible a saisir.
    """
    from pages.admin import _CHAMPS_DU_CATALOGUE, _visibilite_des_champs

    visibilite = _visibilite_des_champs()
    invisibles = [
        champ
        for champ in _CHAMPS_DU_CATALOGUE
        if champ != "affichage" and not visibilite.get(champ)
    ]

    assert invisibles == [], f"champs jamais affichables : {invisibles}"


@pytest.mark.django_db
def test_http_patch_bloc_change_sa_position(cle_pages):
    """PATCH {"position": n} deplace le bloc : la page relue le range a sa nouvelle place.
    / PATCH {"position": n} moves the block: the page lists it at its new place."""
    from rest_framework.test import APIClient
    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    body = {"@type": "WebPage", "name": "Ordre",
            "additionalProperty": [{"@type": "PropertyValue", "name": "slug", "value": "patch-position"}],
            "hasPart": [
                {"additionalType": "TEXTE", "headline": "Premier", "position": 1},
                {"additionalType": "TEXTE", "headline": "Deuxieme", "position": 2},
                {"additionalType": "TEXTE", "headline": "Dernier", "position": 3},
            ]}
    r = client.post("/api/v2/pages/", body, format="json", **auth)
    assert r.status_code == 201, r.content
    page_uuid = r.json()["identifier"]
    bloc_dernier = next(b for b in r.json()["hasPart"] if b["headline"] == "Dernier")

    # Le dernier bloc passe en tete de page.
    # / The last block moves to the top of the page.
    r2 = client.patch(f"/api/v2/blocs/{bloc_dernier['identifier']}/",
                      {"position": 0}, format="json", **auth)
    assert r2.status_code == 200, r2.content
    assert r2.json()["position"] == 0

    r3 = client.get(f"/api/v2/pages/{page_uuid}/", **auth)
    blocs_ranges = sorted(r3.json()["hasPart"], key=lambda b: b["position"])
    assert [b["headline"] for b in blocs_ranges] == ["Dernier", "Premier", "Deuxieme"]


@pytest.mark.django_db
@pytest.mark.parametrize("position_invalide", ["pas-un-nombre", -1])
def test_http_patch_bloc_position_invalide_400(cle_pages, position_invalide):
    """PATCH avec une position qui n'est pas un entier positif -> 400, bloc inchange.
    / PATCH with a position that is not a non-negative integer -> 400, block unchanged."""
    from rest_framework.test import APIClient
    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    body = {"@type": "WebPage", "name": "Position invalide",
            "additionalProperty": [{"@type": "PropertyValue", "name": "slug", "value": "patch-position-ko"}],
            "hasPart": [{"additionalType": "TEXTE", "headline": "Seul", "position": 4}]}
    r = client.post("/api/v2/pages/", body, format="json", **auth)
    assert r.status_code == 201, r.content
    bloc_uuid = r.json()["hasPart"][0]["identifier"]

    r2 = client.patch(f"/api/v2/blocs/{bloc_uuid}/",
                      {"position": position_invalide}, format="json", **auth)
    assert r2.status_code == 400, r2.content

    r3 = client.get(f"/api/v2/blocs/{bloc_uuid}/", **auth)
    assert r3.json()["position"] == 4


# ---------------------------------------------------------------------------
# Bloc CARTE_FIGEE via l'API : donnees_carte_figee arrive par additionalProperty,
# sans passer par l'import de l'admin. Seul Bloc.clean() (appele par
# _valider_le_bloc) le verifie : ces tests figent ce controle.
# / CARTE_FIGEE via the API: the data arrives through additionalProperty; only
# Bloc.clean() checks it.
# ---------------------------------------------------------------------------
def _lieu_de_carte_figee(**cles_a_changer):
    """Un lieu valide pour une carte figee. / A valid frozen-map venue."""
    lieu = {
        "nom": "Lieu API",
        "latitude": 45.75,
        "longitude": 4.83,
        "url": "https://lieu.example.org/",
        "evenements": [{"nom": "Atelier API", "date": "2026-10-02"}],
    }
    lieu.update(cles_a_changer)
    return lieu


def _corps_page_avec_carte_figee(slug, lieux):
    return {
        "@type": "WebPage", "name": f"Carte API {slug}",
        "additionalProperty": [{"@type": "PropertyValue", "name": "slug", "value": slug}],
        "hasPart": [{
            "additionalType": "CARTE_FIGEE",
            "headline": "Bilan",
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "donnees_carte_figee", "value": lieux},
            ],
        }],
    }


@pytest.mark.django_db
def test_http_carte_figee_avec_url_a_guillemet_est_refusee(cle_pages):
    """Un guillemet dans l'URL refermerait l'attribut href : 400, rien n'est cree."""
    from rest_framework.test import APIClient
    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    lieux = [_lieu_de_carte_figee(url='https://x.org/" autofocus onfocus="alert(1)')]

    r = client.post("/api/v2/pages/", _corps_page_avec_carte_figee("carte-api-xss", lieux),
                    format="json", **auth)

    assert r.status_code == 400, r.content


@pytest.mark.django_db
def test_http_carte_figee_valide_est_rangee_nettoyee(cle_pages):
    """Nombres en texte convertis, cle inconnue retiree : la version propre est stockee."""
    from rest_framework.test import APIClient
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Bloc
    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    lieux = [_lieu_de_carte_figee(latitude="45.75", couleur="rouge")]

    r = client.post("/api/v2/pages/", _corps_page_avec_carte_figee("carte-api-ok", lieux),
                    format="json", **auth)

    assert r.status_code == 201, r.content
    bloc_uuid = r.json()["hasPart"][0]["identifier"]
    with tenant_context(Client.objects.get(schema_name="lespass")):
        bloc = Bloc.objects.get(pk=bloc_uuid)
        assert bloc.donnees_carte_figee[0]["latitude"] == 45.75
        assert "couleur" not in bloc.donnees_carte_figee[0]


@pytest.mark.django_db
def test_http_patch_carte_figee_avec_url_javascript_est_refuse(cle_pages):
    from rest_framework.test import APIClient
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Bloc
    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    r = client.post("/api/v2/pages/",
                    _corps_page_avec_carte_figee("carte-api-patch", [_lieu_de_carte_figee()]),
                    format="json", **auth)
    assert r.status_code == 201, r.content
    bloc_uuid = r.json()["hasPart"][0]["identifier"]

    r2 = client.patch(f"/api/v2/blocs/{bloc_uuid}/", {
        "additionalProperty": [{
            "@type": "PropertyValue", "name": "donnees_carte_figee",
            "value": [_lieu_de_carte_figee(url="javascript:alert(1)")],
        }]}, format="json", **auth)

    assert r2.status_code == 400, r2.content
    with tenant_context(Client.objects.get(schema_name="lespass")):
        bloc = Bloc.objects.get(pk=bloc_uuid)
        assert bloc.donnees_carte_figee[0]["url"] == "https://lieu.example.org/"


@pytest.mark.django_db
def test_http_patch_d_un_bloc_texte_ne_garde_pas_de_donnees_de_carte(cle_pages):
    """Hors CARTE_FIGEE, donnees_carte_figee est vide par Bloc.clean() : rien de non verifie ne reste."""
    from rest_framework.test import APIClient
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Bloc
    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    body = {"@type": "WebPage", "name": "Texte API",
            "additionalProperty": [{"@type": "PropertyValue", "name": "slug", "value": "texte-api-carte"}],
            "hasPart": [{"additionalType": "TEXTE", "text": "Bonjour"}]}
    r = client.post("/api/v2/pages/", body, format="json", **auth)
    assert r.status_code == 201, r.content
    bloc_uuid = r.json()["hasPart"][0]["identifier"]

    r2 = client.patch(f"/api/v2/blocs/{bloc_uuid}/", {
        "additionalProperty": [{
            "@type": "PropertyValue", "name": "donnees_carte_figee",
            "value": [_lieu_de_carte_figee(url="javascript:alert(1)")],
        }]}, format="json", **auth)

    assert r2.status_code == 200, r2.content
    with tenant_context(Client.objects.get(schema_name="lespass")):
        assert Bloc.objects.get(pk=bloc_uuid).donnees_carte_figee == []


# --------------------------------------------------------------------------- #
#  PATCH d'un bloc : les images s'envoient en multipart, jamais par URL       #
#  / Block PATCH: images are sent as multipart, never by URL                  #
# --------------------------------------------------------------------------- #


def _creer_un_bloc_pour_le_patch(slug_de_la_page, type_bloc, affichage):
    """Cree une page et un bloc sans image dans le tenant lespass. Renvoie l'uuid du bloc.
    / Creates a page and an image-less block in the lespass tenant. Returns the block uuid."""
    from pages.models import Page, Bloc
    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="Patch image", slug=slug_de_la_page)
        bloc = Bloc.objects.create(page=page, type_bloc=type_bloc, affichage=affichage)
        return str(bloc.uuid)


def _lire_le_bloc(bloc_uuid):
    """Relit le bloc depuis la base du tenant lespass. / Reloads the block from the DB."""
    from pages.models import Bloc
    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        return Bloc.objects.get(uuid=bloc_uuid)



@pytest.mark.django_db
def test_http_patch_bloc_json_image_par_url_refusee_400(cle_pages):
    """PATCH JSON avec `image` = URL : 400 explicite, rien n'est enregistre.
    / JSON PATCH with an image URL: explicit 400, nothing saved."""
    from rest_framework.test import APIClient
    bloc_uuid = _creer_un_bloc_pour_le_patch("patch-json-image", "IMAGES", "PLEINE_LARGEUR")

    client = APIClient()
    reponse = client.patch(f"/api/v2/blocs/{bloc_uuid}/", {
        "headline": "Ne doit pas etre enregistre",
        "image": "https://exemple.org/photo.png",
    }, format="json", **_entetes_api(cle_pages))

    assert reponse.status_code == 400, reponse.content
    assert "image" in reponse.json()
    bloc = _lire_le_bloc(bloc_uuid)
    assert not bloc.image
    assert bloc.titre != "Ne doit pas etre enregistre"


@pytest.mark.django_db
def test_http_patch_bloc_json_liste_d_images_refusee_400(cle_pages):
    """PATCH JSON avec une liste dans `image` (galerie) : 400 explicite.
    / JSON PATCH with a list in `image` (gallery): explicit 400."""
    from rest_framework.test import APIClient
    bloc_uuid = _creer_un_bloc_pour_le_patch("patch-json-liste-images", "IMAGES", "GRILLE")

    client = APIClient()
    reponse = client.patch(f"/api/v2/blocs/{bloc_uuid}/", {
        "image": [{"contentUrl": "https://exemple.org/a.png"}],
    }, format="json", **_entetes_api(cle_pages))

    assert reponse.status_code == 400, reponse.content
    assert "image" in reponse.json()


@pytest.mark.django_db
def test_http_patch_bloc_json_auteur_photo_en_additional_property_refusee_400(cle_pages):
    """PATCH JSON avec `auteur_photo` dans additionalProperty : 400 explicite.
    / JSON PATCH with `auteur_photo` in additionalProperty: explicit 400."""
    from rest_framework.test import APIClient
    bloc_uuid = _creer_un_bloc_pour_le_patch("patch-json-auteur-photo", "SECTION", "CITATION")

    client = APIClient()
    reponse = client.patch(f"/api/v2/blocs/{bloc_uuid}/", {
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "auteur_photo",
             "value": "https://exemple.org/portrait.png"},
        ]}, format="json", **_entetes_api(cle_pages))

    assert reponse.status_code == 400, reponse.content
    assert "auteur_photo" in reponse.json()
    assert not _lire_le_bloc(bloc_uuid).auteur_photo


# --------------------------------------------------------------------------- #
#  CHANTIER 09 — Les images s'envoient en fichier, le serveur ne telecharge   #
#  plus rien (TECH_DOC/SESSIONS/PAGES/CHANTIER-09-images-sans-telechargement) #
#  / Images are sent as files, the server downloads nothing                   #
# --------------------------------------------------------------------------- #

def _entetes_api(cle_brute):
    """Entetes HTTP d'un appel a l'API v2 sur le tenant lespass.
    / HTTP headers of an API v2 call on the lespass tenant."""
    return {"HTTP_AUTHORIZATION": f"Api-Key {cle_brute}",
            "HTTP_HOST": "lespass.tibillet.localhost"}


def _png_dont_l_en_tete_annonce(largeur, hauteur):
    """Fabrique un petit PNG (69 octets) dont l'en-tete annonce largeur x hauteur.
    Pillow lit les dimensions dans l'en-tete sans rien decoder : on teste ainsi la
    limite en pixels sans allouer la memoire d'une image geante.
    / Builds a tiny PNG whose header claims width x height, so the pixel limit can
    be tested without allocating a huge image."""
    import io
    import struct
    import zlib
    from PIL import Image as PILImage

    tampon = io.BytesIO()
    PILImage.new("RGB", (1, 1)).save(tampon, "PNG")
    octets = bytearray(tampon.getvalue())
    assert octets[12:16] == b"IHDR"
    donnees_ihdr = bytearray(octets[16:29])
    donnees_ihdr[0:4] = struct.pack(">I", largeur)
    donnees_ihdr[4:8] = struct.pack(">I", hauteur)
    octets[16:29] = donnees_ihdr
    octets[29:33] = struct.pack(">I", zlib.crc32(b"IHDR" + bytes(donnees_ihdr)) & 0xFFFFFFFF)
    return bytes(octets)


def _image_en_octets(format_pillow, **options_d_enregistrement):
    """Une petite image 4x4 enregistree dans le format demande (TIFF, MPO...).
    / A tiny 4x4 image saved in the requested format."""
    import io
    from PIL import Image as PILImage
    tampon = io.BytesIO()
    PILImage.new("RGB", (4, 4), "orange").save(tampon, format_pillow, **options_d_enregistrement)
    return tampon.getvalue()


def _fichier_envoye(nom, contenu, type_declare="image/png"):
    """Un fichier tel que Django le recoit d'un formulaire multipart.
    / A file as Django receives it from a multipart form."""
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(nom, contenu, content_type=type_declare)


@pytest.fixture
def connexions_sortantes_tentees(monkeypatch):
    """Espion sur la resolution DNS : prouve qu'aucune connexion sortante n'est
    tentee. Renvoie la liste des hotes demandes (elle doit rester vide).
    / Spy on DNS resolution: proves no outgoing connection is attempted."""
    import socket
    hotes_demandes = []

    def fausse_resolution(hote, *args, **kwargs):
        hotes_demandes.append(hote)
        raise AssertionError(f"Connexion sortante interdite : {hote}")

    monkeypatch.setattr(socket, "getaddrinfo", fausse_resolution)
    return hotes_demandes


# --- Lot A : validation d'un fichier image ------------------------------------

def test_valider_image_png_renvoie_l_extension_png():
    """Un vrai PNG passe, et la fonction renvoie l'extension de son format reel.
    / A real PNG passes and the function returns its real format's extension."""
    from api_v2.serializers import _validate_uploaded_image
    fichier = _fichier_envoye("nimporte-quoi.php", _png_bytes())
    assert _validate_uploaded_image(fichier) == ".png"


def test_valider_image_accepte_un_mpo_et_l_enregistre_en_jpg():
    """Pillow lit certaines photos d'appareil comme MPO (JPEG multi-image) : acceptees, en .jpg.
    / Some camera photos are read as MPO (multi-picture JPEG): accepted, stored as .jpg."""
    from PIL import Image as PILImage
    from api_v2.serializers import _validate_uploaded_image
    contenu_mpo = _image_en_octets("MPO", append_images=[PILImage.new("RGB", (4, 4))])
    fichier = _fichier_envoye("photo.jpg", contenu_mpo, "image/jpeg")
    assert _validate_uploaded_image(fichier) == ".jpg"


def test_valider_image_refuse_un_tiff():
    """Un TIFF valide est refuse : seuls JPEG, PNG, GIF et WebP sont acceptes.
    / A valid TIFF is refused: only JPEG, PNG, GIF and WebP are accepted."""
    from api_v2.serializers import _validate_uploaded_image
    fichier = _fichier_envoye("scan.tiff", _image_en_octets("TIFF"), "image/tiff")
    with pytest.raises(serializers.ValidationError):
        _validate_uploaded_image(fichier)


def test_valider_image_refuse_plus_de_50_megapixels():
    """Un PNG de 8000 x 8000 (64 Mpx) est refuse, sans erreur 500.
    / An 8000 x 8000 PNG (64 Mpx) is refused, without a 500."""
    from api_v2.serializers import _validate_uploaded_image
    fichier = _fichier_envoye("geant.png", _png_dont_l_en_tete_annonce(8000, 8000))
    with pytest.raises(serializers.ValidationError):
        _validate_uploaded_image(fichier)


def test_valider_image_refuse_une_bombe_de_decompression():
    """Au-dela de 178 Mpx, Pillow leve DecompressionBombError (qui n'est pas une
    OSError) : elle doit devenir une erreur de validation, pas un 500.
    / Above 178 Mpx Pillow raises DecompressionBombError: it must become a 400."""
    from api_v2.serializers import _validate_uploaded_image
    fichier = _fichier_envoye("bombe.png", _png_dont_l_en_tete_annonce(20000, 20000))
    with pytest.raises(serializers.ValidationError):
        _validate_uploaded_image(fichier)


@pytest.mark.django_db
def test_http_patch_bloc_multipart_nomme_le_fichier_cote_serveur(cle_pages):
    """Le nom du fichier enregistre est choisi par le serveur : le nom et
    l'extension envoyes par le client ne sont pas gardes.
    / The stored file name is chosen by the server, never the client's."""
    from rest_framework.test import APIClient
    bloc_uuid = _creer_un_bloc_pour_le_patch("patch-nom-serveur", "IMAGES", "PLEINE_LARGEUR")

    client = APIClient()
    reponse = client.patch(f"/api/v2/blocs/{bloc_uuid}/",
                           {"image": _fichier_envoye("photo.php", _png_bytes())},
                           format="multipart", **_entetes_api(cle_pages))

    assert reponse.status_code == 200, reponse.content
    nom_enregistre = _lire_le_bloc(bloc_uuid).image.name
    assert nom_enregistre.endswith(".png")
    assert "photo" not in nom_enregistre


# --- Lot B : POST /api/v2/blocs/{uuid}/images/ -------------------------------

def _ajouter_une_image(cle_pages, bloc_uuid, donnees):
    """Appelle l'endpoint d'ajout d'image en multipart. / Calls the add-image endpoint."""
    from rest_framework.test import APIClient
    return APIClient().post(f"/api/v2/blocs/{bloc_uuid}/images/", donnees,
                            format="multipart", **_entetes_api(cle_pages))


@pytest.mark.django_db
def test_http_ajouter_des_images_a_une_grille_donne_des_rangs_successifs(cle_pages):
    """Deux images ajoutees a une GRILLE : 201, rangs galerie:1 puis galerie:2,
    nom de fichier choisi par le serveur, et le bloc expose ses ImageObject.
    / Two images added to a grid: 201, ranks 1 then 2, server-side file name."""
    from rest_framework.test import APIClient
    bloc_uuid = _creer_un_bloc_pour_le_patch("galerie-endpoint", "IMAGES", "GRILLE")

    premiere = _ajouter_une_image(cle_pages, bloc_uuid, {
        "image": _fichier_envoye("a.png", _png_bytes()), "caption": "A"})
    seconde = _ajouter_une_image(cle_pages, bloc_uuid, {
        "image": _fichier_envoye("b.png", _png_bytes()), "caption": "B"})

    assert premiere.status_code == 201, premiere.content
    assert seconde.status_code == 201, seconde.content
    assert premiere.json()["@type"] == "ImageObject"
    assert premiere.json()["galerieReference"] == "galerie:1"
    assert seconde.json()["galerieReference"] == "galerie:2"
    assert seconde.json()["contentUrl"].endswith(".png")
    assert "/b.png" not in seconde.json()["contentUrl"]

    lecture_du_bloc = APIClient().get(f"/api/v2/blocs/{bloc_uuid}/", **_entetes_api(cle_pages))
    legendes = [image["caption"] for image in lecture_du_bloc.json()["image"]]
    assert legendes == ["A", "B"]


@pytest.mark.django_db
def test_http_ajouter_un_logo_avec_lien_et_lien_dangereux_vide(cle_pages):
    """Bande de logos : `url` devient le lien du logo ; un lien javascript: est vide,
    comme partout dans l'API. / Logo strip: `url` is the logo link; a dangerous one is emptied."""
    bloc_uuid = _creer_un_bloc_pour_le_patch("logos-endpoint", "IMAGES", "BANDE_LOGOS")

    logo_avec_lien = _ajouter_une_image(cle_pages, bloc_uuid, {
        "image": _fichier_envoye("alpha.png", _png_bytes()),
        "caption": "Alpha", "url": "https://alpha.example/"})
    logo_mechant = _ajouter_une_image(cle_pages, bloc_uuid, {
        "image": _fichier_envoye("c.png", _png_bytes()),
        "caption": "Mechant", "url": "javascript:alert(1)"})

    assert logo_avec_lien.status_code == 201, logo_avec_lien.content
    assert logo_avec_lien.json()["url"] == "https://alpha.example/"
    assert logo_mechant.status_code == 201, logo_mechant.content
    assert "url" not in logo_mechant.json()


@pytest.mark.django_db
def test_http_ajouter_une_image_a_un_bloc_sans_galerie_refuse_400(cle_pages):
    """Un bloc qui n'affiche pas de galerie (FAQ) refuse l'ajout d'image.
    / A block that shows no gallery (FAQ) refuses the image."""
    from pages.models import ImageGalerie
    bloc_uuid = _creer_un_bloc_pour_le_patch("faq-sans-galerie", "FAQ", "")

    reponse = _ajouter_une_image(cle_pages, bloc_uuid, {
        "image": _fichier_envoye("a.png", _png_bytes())})

    assert reponse.status_code == 400, reponse.content
    with tenant_context(Client.objects.get(schema_name="lespass")):
        assert not ImageGalerie.objects.filter(bloc__uuid=bloc_uuid).exists()


@pytest.mark.django_db
def test_http_ajouter_une_image_sans_fichier_a_une_grille_refuse_400(cle_pages):
    """Une grille d'images exige un fichier. / An image grid requires a file."""
    bloc_uuid = _creer_un_bloc_pour_le_patch("grille-sans-fichier", "IMAGES", "GRILLE")
    reponse = _ajouter_une_image(cle_pages, bloc_uuid, {"caption": "Sans fichier"})
    assert reponse.status_code == 400, reponse.content


@pytest.mark.django_db
def test_http_ajouter_une_image_envoyee_en_texte_refuse_400(cle_pages):
    """Une URL envoyee a la place du fichier est refusee (le serveur ne telecharge rien).
    / A URL sent instead of a file is refused (the server downloads nothing)."""
    bloc_uuid = _creer_un_bloc_pour_le_patch("grille-image-texte", "IMAGES", "GRILLE")
    reponse = _ajouter_une_image(cle_pages, bloc_uuid, {"image": "https://exemple.org/a.png"})
    assert reponse.status_code == 400, reponse.content
    assert "image" in reponse.json()


@pytest.mark.django_db
def test_http_ajouter_une_personne_sans_photo_a_une_equipe(cle_pages):
    """SECTION Equipe : la photo est facultative, nom et badges suffisent.
    / EQUIPE section: the photo is optional, name and badges are enough."""
    bloc_uuid = _creer_un_bloc_pour_le_patch("equipe-sans-photo", "SECTION", "EQUIPE")

    reponse = _ajouter_une_image(cle_pages, bloc_uuid, {
        "caption": "Theo Marchand", "keywords": "Vie associative, Benevole"})

    assert reponse.status_code == 201, reponse.content
    assert reponse.json()["caption"] == "Theo Marchand"
    assert reponse.json()["keywords"] == "Vie associative, Benevole"
    assert "contentUrl" not in reponse.json()


@pytest.mark.django_db
def test_http_image_ajoutee_a_un_bloc_texte_est_resolue_par_galerie_1(cle_pages):
    """Bloc TEXTE : l'image envoyee est resolue au rendu par ![...](galerie:1).
    / TEXTE block: the uploaded image is resolved by ![...](galerie:1)."""
    from pages.models import Bloc, Page
    from pages.templatetags.pages_tags import rendre_bloc_markdown
    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="Article", slug="article-galerie-1")
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.TEXTE,
                                   texte="Intro\n\n![une photo](galerie:1)")
        bloc_uuid = str(bloc.uuid)

    reponse = _ajouter_une_image(cle_pages, bloc_uuid, {
        "image": _fichier_envoye("photo.png", _png_bytes())})

    assert reponse.status_code == 201, reponse.content
    assert reponse.json()["galerieReference"] == "galerie:1"
    with tenant_context(tenant):
        html_rendu = str(rendre_bloc_markdown(Bloc.objects.get(uuid=bloc_uuid)))
        assert "introuvable" not in html_rendu
        assert "<img" in html_rendu


# --- Lot C : plus aucun telechargement a la creation -------------------------

@pytest.mark.django_db
def test_http_creer_un_bloc_json_avec_une_url_d_image_refuse_400(cle_pages, connexions_sortantes_tentees):
    """POST /pages/{uuid}/blocs/ en JSON avec `image` = URL : 400, aucun bloc cree,
    aucune connexion sortante. / JSON create with an image URL: 400, nothing created."""
    from rest_framework.test import APIClient
    from pages.models import Page
    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="Page", slug="creation-url-refusee")
        page_uuid = str(page.uuid)

    reponse = APIClient().post(f"/api/v2/pages/{page_uuid}/blocs/", {
        "additionalType": "IMAGES", "image": "https://exemple.org/photo.png",
    }, format="json", **_entetes_api(cle_pages))

    assert reponse.status_code == 400, reponse.content
    assert "image" in reponse.json()
    assert connexions_sortantes_tentees == []
    with tenant_context(tenant):
        assert Page.objects.get(uuid=page_uuid).blocs.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("valeur_image", [
    {"@type": "ImageObject", "contentUrl": "https://exemple.org/a.png"},
    [{"@type": "ImageObject", "contentUrl": "https://exemple.org/a.png"}],
    42,
])
def test_creer_un_bloc_images_avec_une_image_en_json_refuse(valeur_image):
    """Liste blanche : un dict, une liste ou toute autre valeur dans `image` d'un
    bloc IMAGES est refuse par is_valid(). / Whitelist: any non-empty image value is refused."""
    from api_v2.serializers import BlocCreateSerializer
    serializer_du_bloc = BlocCreateSerializer(
        data={"additionalType": "IMAGES", "image": valeur_image}, context={"page": None})
    assert not serializer_du_bloc.is_valid()
    assert "image" in serializer_du_bloc.errors


@pytest.mark.parametrize("valeur_vide", [None, "", []])
def test_creer_un_bloc_avec_une_image_vide_reste_accepte(valeur_vide):
    """`image` vide (None, "", []) est ignore : compatibilite avec les clients actuels.
    / An empty `image` is ignored, for compatibility."""
    from api_v2.serializers import BlocCreateSerializer
    serializer_du_bloc = BlocCreateSerializer(
        data={"additionalType": "FAQ", "headline": "Q ?", "image": valeur_vide},
        context={"page": None})
    assert serializer_du_bloc.is_valid(), serializer_du_bloc.errors


@pytest.mark.parametrize("valeur_photo", [
    "https://exemple.org/portrait.png",
    {"contentUrl": "https://exemple.org/portrait.png"},
    ["https://exemple.org/portrait.png"],
])
def test_creer_un_bloc_avec_une_photo_d_auteur_en_json_refuse(valeur_photo):
    """`auteur_photo` dans additionalProperty, quel que soit son type : refuse.
    / `auteur_photo` in additionalProperty, whatever its type: refused."""
    from api_v2.serializers import BlocCreateSerializer
    serializer_du_bloc = BlocCreateSerializer(data={
        "additionalType": "SECTION",
        "additionalProperty": [
            {"name": "affichage", "value": "CITATION"},
            {"name": "auteur_photo", "value": valeur_photo},
        ],
    }, context={"page": None})
    assert not serializer_du_bloc.is_valid()
    assert "auteur_photo" in serializer_du_bloc.errors


def test_creer_une_equipe_dont_une_personne_porte_une_photo_par_url_refuse():
    """SECTION Equipe : une personne avec `contentUrl` est refusee (la photo
    s'envoie par l'endpoint images). / A person with contentUrl is refused."""
    from api_v2.serializers import BlocCreateSerializer
    serializer_du_bloc = BlocCreateSerializer(data={
        "additionalType": "SECTION",
        "additionalProperty": [{"name": "affichage", "value": "EQUIPE"}],
        "image": [{"@type": "ImageObject", "caption": "Awa",
                   "contentUrl": "https://exemple.org/awa.png"}],
    }, context={"page": None})
    assert not serializer_du_bloc.is_valid()
    assert "image" in serializer_du_bloc.errors


@pytest.mark.django_db
def test_creer_une_page_dont_un_bloc_porte_une_galerie_par_url_ne_cree_rien(connexions_sortantes_tentees):
    """Page avec hasPart : un bloc IMAGES avec une liste d'URL fait echouer toute
    la creation, sans page ni bloc. / A hasPart IMAGES list fails the whole creation."""
    from pages.models import Page
    from api_v2.serializers import PageCreateSerializer
    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        nombre_de_pages_avant = Page.objects.count()
        serializer_de_la_page = PageCreateSerializer(data={
            "name": "Galerie par URL",
            "additionalProperty": [{"@type": "PropertyValue", "name": "slug", "value": "galerie-par-url"}],
            "hasPart": [
                {"additionalType": "FAQ", "headline": "Valide"},
                {"additionalType": "IMAGES",
                 "image": [{"@type": "ImageObject", "contentUrl": "https://exemple.org/a.png"}]},
            ],
        }, context={"request": None})
        assert serializer_de_la_page.is_valid(), serializer_de_la_page.errors
        with pytest.raises(serializers.ValidationError):
            serializer_de_la_page.save()
        assert Page.objects.count() == nombre_de_pages_avant
        assert not Page.objects.filter(slug="galerie-par-url").exists()
    assert connexions_sortantes_tentees == []


@pytest.mark.django_db
def test_creer_un_bloc_texte_garde_ses_images_markdown_externes(connexions_sortantes_tentees):
    """Bloc TEXTE : une image markdown externe n'est plus importee. Le texte est
    garde tel quel, sans clean_html. / External markdown images are kept as-is."""
    from pages.models import Page
    from api_v2.serializers import BlocCreateSerializer
    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="md", slug="pytest-md-externe")
        texte_markdown = ("## Titre\n\nDu **gras** et un autolien <https://exemple.fr>.\n\n"
                          "![une image](https://exemple.org/a.png)\n\nFin.")
        serializer_du_bloc = BlocCreateSerializer(
            data={"additionalType": "TEXTE", "text": texte_markdown}, context={"page": page})
        assert serializer_du_bloc.is_valid(), serializer_du_bloc.errors
        bloc = serializer_du_bloc.save()
        assert bloc.texte == texte_markdown
        assert bloc.images_galerie.count() == 0
    assert connexions_sortantes_tentees == []


@pytest.mark.django_db
def test_http_ajouter_un_bloc_multipart_avec_une_image_en_texte_refuse_400(cle_pages):
    """POST multipart avec `image` en texte (une URL) : 400 au lieu d'un retrait
    silencieux. / Multipart POST with `image` as text: 400, not silently dropped."""
    from rest_framework.test import APIClient
    from pages.models import Page
    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="Page", slug="multipart-image-texte")
        page_uuid = str(page.uuid)

    reponse = APIClient().post(f"/api/v2/pages/{page_uuid}/blocs/", {
        "additionalType": "IMAGES", "image": "https://exemple.org/a.png",
    }, format="multipart", **_entetes_api(cle_pages))

    assert reponse.status_code == 400, reponse.content
    assert "image" in reponse.json()
    with tenant_context(tenant):
        assert Page.objects.get(uuid=page_uuid).blocs.count() == 0


@pytest.mark.django_db
def test_http_ajouter_un_bloc_multipart_avec_un_tiff_ne_cree_aucun_bloc(cle_pages):
    """POST multipart avec un fichier refuse (TIFF) : 400 et aucun bloc orphelin.
    / Multipart POST with a refused file (TIFF): 400 and no orphan block."""
    from rest_framework.test import APIClient
    from pages.models import Page
    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="Page", slug="multipart-tiff")
        page_uuid = str(page.uuid)

    reponse = APIClient().post(f"/api/v2/pages/{page_uuid}/blocs/", {
        "additionalType": "IMAGES",
        "image": _fichier_envoye("scan.tiff", _image_en_octets("TIFF"), "image/tiff"),
    }, format="multipart", **_entetes_api(cle_pages))

    assert reponse.status_code == 400, reponse.content
    with tenant_context(tenant):
        assert Page.objects.get(uuid=page_uuid).blocs.count() == 0


# Toutes les routes /pages/ et /blocs/ qui lisent un uuid dans l'URL.
# Le routeur DRF accepte n'importe quel texte a cet endroit.
# / Every /pages/ and /blocs/ route that reads a uuid from the URL.
ROUTES_PAGES_ET_BLOCS_AVEC_UUID_DANS_L_URL = [
    ("get", "/api/v2/blocs/{identifiant}/"),
    ("patch", "/api/v2/blocs/{identifiant}/"),
    ("delete", "/api/v2/blocs/{identifiant}/"),
    ("post", "/api/v2/blocs/{identifiant}/images/"),
    ("patch", "/api/v2/pages/{identifiant}/"),
    ("delete", "/api/v2/pages/{identifiant}/"),
    ("post", "/api/v2/pages/{identifiant}/blocs/"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("methode, gabarit_de_route", ROUTES_PAGES_ET_BLOCS_AVEC_UUID_DANS_L_URL)
def test_http_identifiant_qui_n_est_pas_un_uuid_renvoie_404(cle_pages, methode, gabarit_de_route):
    """Un identifiant mal forme (uuid tronque, faute de frappe) donne un 404 :
    la ressource ne peut pas exister. Jamais un 500.
    / A malformed identifier gives a 404, never a 500."""
    from rest_framework.test import APIClient
    client = APIClient()
    client.raise_request_exception = False
    route = gabarit_de_route.format(identifiant="8d22a6b4-x")

    appel_http = getattr(client, methode)
    reponse = appel_http(route, {}, format="json", **_entetes_api(cle_pages))

    assert reponse.status_code == 404, reponse.content


@pytest.mark.django_db
def test_http_page_modifiee_enrichie_puis_supprimee_par_son_slug(cle_pages):
    """PATCH, ajout d'un bloc et DELETE acceptent le slug de la page, comme le GET.
    / PATCH, block creation and DELETE accept the page slug, like GET."""
    from rest_framework.test import APIClient
    from pages.models import Page
    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="Mentions", slug="mentions-par-slug")
        page_uuid = page.uuid
    client = APIClient()

    reponse_patch = client.patch("/api/v2/pages/mentions-par-slug/",
                                 {"name": "Mentions légales"}, format="json",
                                 **_entetes_api(cle_pages))
    assert reponse_patch.status_code == 200, reponse_patch.content
    assert reponse_patch.json()["identifier"] == str(page_uuid)

    reponse_bloc = client.post("/api/v2/pages/mentions-par-slug/blocs/",
                               {"additionalType": "TEXTE", "text": "Bonjour"},
                               format="json", **_entetes_api(cle_pages))
    assert reponse_bloc.status_code == 201, reponse_bloc.content

    with tenant_context(tenant):
        page.refresh_from_db()
        assert page.titre == "Mentions légales"
        assert page.blocs.count() == 1

    reponse_delete = client.delete("/api/v2/pages/mentions-par-slug/", **_entetes_api(cle_pages))
    assert reponse_delete.status_code == 204
    with tenant_context(tenant):
        assert not Page.objects.filter(uuid=page_uuid).exists()
