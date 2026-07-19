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
            "additionalType": "LIEU",
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
            "additionalType": "IMAGES",
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
    # Les 7 types d'intention, et rien d'autre : le catalogue est ferme.
    # / The 7 intent types and nothing else: the catalogue is closed.
    assert types == {
        "TEXTE", "SECTION", "IMAGES", "INTEGRATION", "LIEU", "FAQ", "LISTE"}
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
            "additionalType": "IMAGES",
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
                "additionalType": "IMAGES",
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


@pytest.mark.django_db
def test_bloc_images_bande_logos_cree_logos_cliquables(monkeypatch):
    """PARTENAIRES : liste d'ImageObject (contentUrl + caption + url) -> logos avec lien_url ;
    url dangereuse neutralisee ; sortie expose `url` seulement si lien present."""
    import io
    from PIL import Image as PILImage
    from pages.models import Page
    from api_v2.serializers import BlocCreateSerializer, BlocSchemaSerializer

    buf = io.BytesIO()
    PILImage.new("RGB", (8, 8), "blue").save(buf, format="PNG")
    png = buf.getvalue()

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "image/png"}
        content = png
        def raise_for_status(self): pass
        def iter_content(self, chunk_size=65536): yield self.content
        def close(self): pass

    monkeypatch.setattr("api_v2.serializers._hote_est_interne", lambda h: False)
    monkeypatch.setattr("api_v2.serializers.requests.get", lambda *a, **k: FakeResp())

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="p", slug="partenaires-api")
        ser = BlocCreateSerializer(data={
            "additionalType": "IMAGES",
            "headline": "Ils nous soutiennent",
            # Une bande de logos : plusieurs images, donc la relation
            # ImageGalerie. / A logo strip: several images, hence ImageGalerie.
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "affichage", "value": "BANDE_LOGOS"},
            ],
            "image": [
                {"@type": "ImageObject", "contentUrl": "https://ex.fr/a.png",
                 "caption": "Alpha", "url": "https://alpha.example/"},
                {"@type": "ImageObject", "contentUrl": "https://ex.fr/b.png",
                 "caption": "Beta"},
                {"@type": "ImageObject", "contentUrl": "https://ex.fr/c.png",
                 "caption": "Mechant", "url": "javascript:alert(1)"},
            ],
        }, context={"page": page})
        assert ser.is_valid(), ser.errors
        bloc = ser.save()
        assert bloc.type_bloc == "IMAGES"
        assert bloc.affichage == "BANDE_LOGOS"
        assert bloc.images_galerie.count() == 3
        logos = list(bloc.images_galerie.order_by("position"))
        assert logos[0].lien_url == "https://alpha.example/"
        assert logos[1].lien_url == ""              # pas de lien fourni
        assert logos[2].lien_url == ""              # javascript: neutralise
        out = BlocSchemaSerializer(bloc).data
        assert out["image"][0]["url"] == "https://alpha.example/"
        assert "url" not in out["image"][1]


# ---------------------------------------------------------------------------
# Bloc TEXTE : source Markdown preservee, images referencees importees
# ---------------------------------------------------------------------------
def _monkey_download_ok(monkeypatch):
    """
    Fait reussir le telechargement d'une image distante, sans reseau.

    Neutralise le garde SSRF (qui refuserait un hote interne) et remplace la
    requete HTTP par une reponse portant un PNG minimal.
    / Makes a remote image download succeed without network access: disables
    the SSRF guard and replaces the HTTP request with a tiny PNG response.
    """
    contenu_png = _png_bytes()

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "image/png", "Content-Length": str(len(contenu_png))}
        content = contenu_png

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=65536):
            yield self.content

        def close(self):
            pass

    monkeypatch.setattr("api_v2.serializers._hote_est_interne", lambda h: False)
    monkeypatch.setattr("api_v2.serializers.requests.get", lambda *a, **k: FakeResp())



@pytest.mark.django_db
def test_bloc_texte_importe_images_et_preserve_source(monkeypatch):
    """MARKDOWN : ![](http-url) -> importee en galerie:N (ImageGalerie) ; la source
    markdown n'est PAS mutilee par clean_html (les autoliens/gras restent)."""
    from pages.models import Page
    from api_v2.serializers import BlocCreateSerializer

    _monkey_download_ok(monkeypatch)
    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="md", slug="pytest-md-img")
        md = ("## Titre\n\nDu **gras** et un autolien <https://exemple.fr>.\n\n"
              "![une image](https://ex.fr/a.png)\n\nFin.")
        ser = BlocCreateSerializer(data={"additionalType": "TEXTE", "text": md},
                                   context={"page": page})
        assert ser.is_valid(), ser.errors
        bloc = ser.save()
        # Image importee et texte reecrit.
        assert bloc.images_galerie.count() == 1
        assert "![une image](galerie:1)" in bloc.texte
        # Source markdown preservee (clean_html l'aurait mutilee).
        assert "**gras**" in bloc.texte
        assert "<https://exemple.fr>" in bloc.texte


@pytest.mark.django_db
def test_bloc_texte_image_morte_garde_url(monkeypatch):
    """Une image markdown inaccessible ne casse PAS le POST : on garde l'URL externe."""
    from rest_framework import serializers as drf
    from pages.models import Page
    from api_v2.serializers import BlocCreateSerializer

    def _leve(*a, **k):
        raise drf.ValidationError("image morte")
    monkeypatch.setattr("api_v2.serializers.telecharger_et_valider_image", _leve)

    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        page = Page.objects.create(titre="md2", slug="pytest-md-dead")
        md = "Texte.\n\n![morte](https://ex.fr/introuvable.png)\n\nFin."
        ser = BlocCreateSerializer(data={"additionalType": "TEXTE", "text": md},
                                   context={"page": page})
        assert ser.is_valid(), ser.errors
        bloc = ser.save()  # ne leve pas
        assert bloc.images_galerie.count() == 0
        assert "https://ex.fr/introuvable.png" in bloc.texte  # URL gardee


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
