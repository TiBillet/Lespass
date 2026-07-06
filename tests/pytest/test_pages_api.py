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
def test_catalogue_blocs_couvre_les_16_types():
    from pages.blocs_catalogue import CHAMPS_PAR_TYPE, CHAMPS_BLOC_AUTORISES, TYPES_BLOC
    from pages.models import Bloc
    # Les 16 types du modele sont presents dans le catalogue
    # (14 d'origine + MARKDOWN + LISTE_SOUS_PAGES, CHANTIER-09).
    # / The model's 16 types are in the catalogue (14 original +
    # MARKDOWN + LISTE_SOUS_PAGES, CHANTIER-09).
    types_modele = {code for code, _label in Bloc.TYPE_BLOC_CHOICES}
    assert set(CHAMPS_PAR_TYPE.keys()) == types_modele
    assert len(TYPES_BLOC) == 16
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
            "additionalType": "CTA",
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
            "additionalType": "VIDEO_TEXTE",
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "video", "value": "javascript:alert(1)"},
            ],
        }, context={"page": page})
        assert ser.is_valid(), ser.errors
        bloc = ser.save()
        assert not bloc.video  # vide, pas de corruption


@pytest.mark.django_db
def test_bloc_create_image_secondaire_url_dangereuse_leve_400():
    """Une URL d'image dangereuse/interne via additionalProperty leve ValidationError
    (coherence avec le champ standard image, pas d'echec silencieux).
    / A dangerous/internal image URL via additionalProperty raises ValidationError
    (consistent with the standard image field, no silent failure)."""
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page
    from api_v2.serializers import BlocCreateSerializer
    from rest_framework import serializers as drf_serializers
    import pytest as _pytest

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="x", slug="img-sec-danger")
        ser = BlocCreateSerializer(data={
            "additionalType": "CARTE_LEAFLET",
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "image_secondaire", "value": "javascript:alert(1)"},
            ],
        }, context={"page": page})
        assert ser.is_valid(), ser.errors
        with _pytest.raises(drf_serializers.ValidationError):
            ser.save()


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
def test_bloc_image_par_url_ok(monkeypatch):
    import io
    from PIL import Image as PILImage
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page
    from api_v2.serializers import BlocCreateSerializer

    buf = io.BytesIO()
    PILImage.new("RGB", (10, 10), "blue").save(buf, format="PNG")
    contenu_png = buf.getvalue()

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "image/png"}
        content = contenu_png
        def raise_for_status(self): pass
        def iter_content(self, chunk_size=65536):
            # Renvoie le contenu en un seul bloc (suffit pour le test).
            yield self.content
        def close(self): pass

    # On neutralise le check SSRF (hote public simule) + la requete reseau.
    monkeypatch.setattr("api_v2.serializers._hote_est_interne", lambda h: False)
    monkeypatch.setattr("api_v2.serializers.requests.get", lambda *a, **k: FakeResp())

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="img", slug="img-url-ok")
        ser = BlocCreateSerializer(data={
            "additionalType": "IMAGE",
            "image": "https://exemple.fr/photo.png",
        }, context={"page": page})
        assert ser.is_valid(), ser.errors
        bloc = ser.save()
        assert bloc.image  # fichier enregistre


@pytest.mark.django_db
def test_telecharger_image_bloque_ssrf_loopback():
    """Une URL pointant vers une IP loopback/interne est refusee (anti-SSRF).
    / A URL pointing to a loopback/internal IP is refused (anti-SSRF)."""
    from rest_framework import serializers as drf_serializers
    from api_v2.serializers import telecharger_et_valider_image
    import pytest as _pytest
    for url in ("http://127.0.0.1/x.png",
                "http://169.254.169.254/latest/meta-data/",
                "http://localhost/x.png",
                "file:///etc/passwd",
                "ftp://exemple.fr/x.png"):
        with _pytest.raises(drf_serializers.ValidationError):
            telecharger_et_valider_image(url)


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
            "hasPart": [{"additionalType": "CTA", "headline": "x"}]}
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
                    {"additionalType": "IMAGE", "image": fichier},
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
        bloc = Bloc.objects.create(page=page, type_bloc="IMAGE")
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
    # 16 types : 14 d'origine + MARKDOWN + LISTE_SOUS_PAGES (CHANTIER-09).
    # / 16 types: 14 original + MARKDOWN + LISTE_SOUS_PAGES (CHANTIER-09).
    assert len(types) == 16
    assert {"MARKDOWN", "LISTE_SOUS_PAGES"} <= types
    faq = next(b for b in r.json()["blockTypes"] if b["type"] == "FAQ")
    assert set(faq["fields"]) == {"titre", "texte", "repliable"}
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
            "additionalType": "CARTE_LEAFLET",
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
            "additionalType": "CARTE_LEAFLET",
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "points_gps", "value": {"lat": 1}},
            ],
        }, context={"page": page})
        assert ser.is_valid(), ser.errors
        with _pytest.raises(drf.ValidationError):
            ser.save()


@pytest.mark.django_db
def test_bloc_galerie_cree_et_expose_imageobjects(monkeypatch):
    """GALERIE : liste d'ImageObject (URL) -> ImageGalerie ; sortie = ImageObject[].
    / GALLERY: list of ImageObject (URL) -> ImageGalerie; output = ImageObject[]."""
    import io
    from PIL import Image as PILImage
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page
    from api_v2.serializers import BlocCreateSerializer, BlocSchemaSerializer

    buf = io.BytesIO()
    PILImage.new("RGB", (8, 8), "green").save(buf, format="PNG")
    png = buf.getvalue()

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "image/png"}
        content = png
        def raise_for_status(self): pass
        def iter_content(self, chunk_size=65536):
            # Renvoie le contenu en un seul bloc (suffit pour le test).
            yield self.content
        def close(self): pass

    monkeypatch.setattr("api_v2.serializers._hote_est_interne", lambda h: False)
    monkeypatch.setattr("api_v2.serializers.requests.get", lambda *a, **k: FakeResp())

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="g", slug="galerie-rt")
        ser = BlocCreateSerializer(data={
            "additionalType": "GALERIE",
            "image": [
                {"@type": "ImageObject", "contentUrl": "https://ex.fr/a.png", "caption": "A"},
                {"@type": "ImageObject", "contentUrl": "https://ex.fr/b.png", "caption": "B"},
            ],
        }, context={"page": page})
        assert ser.is_valid(), ser.errors
        bloc = ser.save()
        assert bloc.images_galerie.count() == 2
        out = BlocSchemaSerializer(bloc).data
        # En sortie, image = liste d'ImageObject.
        assert isinstance(out["image"], list)
        assert out["image"][0]["@type"] == "ImageObject"
        assert [img["caption"] for img in out["image"]] == ["A", "B"]


@pytest.mark.django_db
def test_telecharger_image_refuse_corps_trop_gros(monkeypatch):
    """Un corps distant > 10 Mo est refuse SANS tout charger en memoire (cap borne).
    / A remote body > 10 MB is refused without loading it all in memory (bounded cap)."""
    from rest_framework import serializers as drf
    from api_v2.serializers import telecharger_et_valider_image
    import pytest as _pytest

    class GrosResp:
        status_code = 200
        headers = {"Content-Type": "image/png"}  # pas de Content-Length -> lecture bornee
        def raise_for_status(self): pass
        def iter_content(self, chunk_size=65536):
            # 3 blocs de 5 Mo = 15 Mo > 10 Mo : doit stopper avant la fin.
            for _ in range(3):
                yield b"x" * (5 * 1024 * 1024)
        def close(self): pass

    monkeypatch.setattr("api_v2.serializers._hote_est_interne", lambda h: False)
    monkeypatch.setattr("api_v2.serializers.requests.get", lambda *a, **k: GrosResp())
    with _pytest.raises(drf.ValidationError):
        telecharger_et_valider_image("https://exemple.fr/gros.png")


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
            "hasPart": [{"additionalType": "CARTE_LEAFLET", "headline": "c"}]}
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
                    {"additionalType": "VIDEO_TEXTE", "video": faux_video},
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
def test_page_create_hierarchie_deux_niveaux_refusee_400(cle_pages):
    """Un seul niveau : rattacher une page à un parent qui a déjà un parent -> 400.
    / One level only: attaching to a parent that already has a parent -> 400."""
    from rest_framework.test import APIClient
    client = APIClient()
    auth = {"HTTP_AUTHORIZATION": f"Api-Key {cle_pages}",
            "HTTP_HOST": "lespass.tibillet.localhost"}
    for slug in ("niveau-a",):
        client.post("/api/v2/pages/", {"name": "A", "additionalProperty": [
            {"@type": "PropertyValue", "name": "slug", "value": "niveau-a"}], "hasPart": []},
            format="json", **auth)
    # B enfant de A (OK)
    rb = client.post("/api/v2/pages/", {"name": "B", "isPartOf": "niveau-a",
        "additionalProperty": [{"@type": "PropertyValue", "name": "slug", "value": "niveau-b"}],
        "hasPart": []}, format="json", **auth)
    assert rb.status_code == 201, rb.content
    # C enfant de B -> refuse (B a deja un parent = 2 niveaux)
    rc = client.post("/api/v2/pages/", {"name": "C", "isPartOf": "niveau-b",
        "additionalProperty": [{"@type": "PropertyValue", "name": "slug", "value": "niveau-c"}],
        "hasPart": []}, format="json", **auth)
    assert rc.status_code == 400, rc.content


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


@pytest.mark.django_db
def test_page_nested_galerie_url_dangereuse_ne_cree_rien(monkeypatch):
    """Si une URL de galerie est dangereuse, la creation ECHOUE en 400 et NE laisse
    NI page NI bloc NI image (atomicite preservee malgre le pre-telechargement).
    / If a gallery URL is dangerous, creation fails 400 and leaves NO page/block/image."""
    from django_tenants.utils import tenant_context
    from Customers.models import Client
    from pages.models import Page
    from api_v2.serializers import PageCreateSerializer
    from rest_framework import serializers as drf
    import pytest as _pytest

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        nb_pages_avant = Page.objects.count()
        payload = {
            "name": "Galerie KO",
            "additionalProperty": [{"@type": "PropertyValue", "name": "slug", "value": "galerie-ko"}],
            "hasPart": [{
                "additionalType": "GALERIE",
                "image": [{"@type": "ImageObject", "contentUrl": "javascript:alert(1)"}],
            }],
        }
        ser = PageCreateSerializer(data=payload, context={"request": None})
        assert ser.is_valid(), ser.errors
        with _pytest.raises(drf.ValidationError):
            ser.save()
        # Rien n'a ete cree (ni la page au slug galerie-ko).
        assert Page.objects.count() == nb_pages_avant
        assert not Page.objects.filter(slug="galerie-ko").exists()
