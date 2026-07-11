# CHANTIER 06 — Plan d'implémentation : blocs `IFRAME` + `PARTENAIRES`

> **Pour l'exécutant (humain ou agent)** : implémenter tâche par tâche, dans l'ordre.
> Chaque tâche finit par un livrable testable. Spec de référence :
> `CHANTIER-06-blocs-iframe-partenaires.md`.

**Goal :** ajouter deux blocs à l'app `pages` — `IFRAME` (intégration hauteur-libre type
newsletter Ghost, bornée par une whitelist ROOT) et `PARTENAIRES` (bande de logos
cliquables) — et **tout valider dans Chrome** (admin + rendu public).

**Architecture :** réutilisation maximale de l'existant. `IFRAME` réutilise `Bloc.embed_url`
+ nouveau `hauteur_px` ; rendu par un tag `iframe_libre` calqué sur `embed_iframe` mais
borné par `RootConfiguration.domaines_embed_autorises` (nouveau champ, éditable superadmin
strict). `PARTENAIRES` réutilise l'inline `ImageGalerie` + nouveau `lien_url` (mécanisme
« image cliquable » valable aussi pour `GALERIE`).

**Tech Stack :** Django multi-tenant (django-tenants), Unfold admin (conditional_fields
Alpine), django-solo (singletons), pytest (base dev live), MCP claude-in-chrome (validation).

## Global Constraints (copiées de la spec — valent pour TOUTES les tâches)

- **AUCUNE opération git par l'exécutant s'il est l'assistant/un subagent.** Les étapes
  « Commit » ci-dessous **listent le message suggéré** ; c'est le **mainteneur** qui commit.
- **i18n** : texte source des `_()` / `{% translate %}` en **FRANÇAIS**. `makemessages` /
  `compilemessages` = **mainteneur** (ne pas les lancer).
- **Serveur** : tourne déjà dans **byobu** (port 8002, Traefik). **NE PAS** lancer
  `runserver_plus`. Check visuel : `https://<tenant>.tibillet.localhost/`.
- **`ruff format`** : uniquement sur fichiers **neufs**. Sur l'existant : `ruff check` seul.
- **FALC** : code verbeux, commentaires bilingues FR/EN.
- **Sécurité iframe** : rendu SEULEMENT si schéma `https` **et** hôte dans la whitelist ROOT.
  Ne JAMAIS whitelister un domaine de la plateforme/tenant (avec `allow-same-origin` le
  sandbox tomberait).
- **Tests** : `docker exec lespass_django poetry run pytest tests/pytest/test_pages.py -q`.

---

## Structure des fichiers

| Fichier | Responsabilité | Tâche |
|---|---|---|
| `pages/models.py` | +choices IFRAME/PARTENAIRES, +`hauteur_px`, +`lien_url`, validator | 1 |
| `root_billet/models.py` | +`domaines_embed_autorises` | 1 |
| `pages/migrations/000X` + `root_billet/migrations/000Y` | migrations | 1 |
| `pages/templatetags/pages_tags.py` | tag `iframe_libre` + helper whitelist | 2 |
| `pages/admin.py` | conditional_fields, get_inlines, inline fields, `fields` | 3 |
| `Administration/admin_tenant.py` | `RootConfigurationAdmin` (superadmin strict) + imports | 3 |
| `Administration/admin/dashboard.py` | item sidebar « Domaines iframe (ROOT) » (superadmin) | 3 |
| `pages/templates/pages/classic/partials/bloc_iframe.html` | rendu IFRAME | 4 |
| `pages/templates/pages/classic/partials/bloc_partenaires.html` | rendu PARTENAIRES | 4 |
| `pages/templates/pages/classic/partials/bloc_galerie.html` | +lien cliquable | 4 |
| `pages/static/pages/css/tb-blocs.css` | styles `.tb-iframe`, `.tb-partenaires` | 4 |
| `tests/pytest/test_pages.py` | tests unitaires/rendu | 1-4 |
| `CHANGELOG.md`, `A TESTER et DOCUMENTER/` | doc | 5 |

---

## Task 1 : Modèles + migrations

**Files:**
- Modify: `pages/models.py` (Bloc : choices, `hauteur_px` ; ImageGalerie : `lien_url` ;
  + validator `valider_url_sans_schema_dangereux`)
- Modify: `root_billet/models.py` (RootConfiguration : `domaines_embed_autorises`)
- Create: `pages/migrations/000X_iframe_partenaires.py`, `root_billet/migrations/000Y_domaines_embed.py`
- Test: `tests/pytest/test_pages.py`

**Interfaces produites :**
- `Bloc.IFRAME = "IFRAME"`, `Bloc.PARTENAIRES = "PARTENAIRES"` (constantes + choices)
- `Bloc.hauteur_px` (PositiveIntegerField, défaut 600, bornes 100..4000)
- `ImageGalerie.lien_url` (CharField 500, blank, validé anti-schéma-dangereux)
- `RootConfiguration.domaines_embed_autorises` (TextField, blank)
- `pages.models.valider_url_sans_schema_dangereux(valeur)`

- [ ] **Step 1 — Écrire les tests (échouent)** dans `tests/pytest/test_pages.py` (à la fin) :

```python
# ---------------------------------------------------------------------------
# CHANTIER 06 — Blocs IFRAME + PARTENAIRES
# ---------------------------------------------------------------------------
def test_creation_bloc_iframe(tenant, nettoyer_pages):
    """Un bloc IFRAME se crée avec embed_url + hauteur_px."""
    from pages.models import Bloc, Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Pytest Iframe", slug="pytest-iframe")
        bloc = Bloc.objects.create(
            page=page,
            type_bloc=Bloc.IFRAME,
            embed_url="https://newsletter.ghost.io/abonnement",
            hauteur_px=500,
        )
        assert bloc.type_bloc == "IFRAME"
        assert bloc.hauteur_px == 500


def test_hauteur_px_bornee(tenant, nettoyer_pages):
    """hauteur_px hors bornes (100..4000) est rejetée au full_clean()."""
    from pages.models import Bloc, Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Pytest Iframe H", slug="pytest-iframe-h")
        bloc = Bloc(page=page, type_bloc=Bloc.IFRAME, hauteur_px=50)
        with pytest.raises(ValidationError) as exc:
            bloc.full_clean()
        assert "hauteur_px" in exc.value.error_dict


def test_image_galerie_lien_url_ok(tenant, nettoyer_pages):
    """Une ImageGalerie accepte un lien_url http(s) normal."""
    from pages.models import Bloc, ImageGalerie, Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Pytest Part", slug="pytest-part")
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.PARTENAIRES)
        img = ImageGalerie(bloc=bloc, lien_url="https://partenaire.example/", position=1)
        img.full_clean()  # ne lève pas
        img.save()
        assert img.lien_url == "https://partenaire.example/"


def test_image_galerie_lien_url_dangereux_rejete(tenant, nettoyer_pages):
    """lien_url = javascript:… est rejeté au full_clean() (anti-XSS)."""
    from pages.models import Bloc, ImageGalerie, Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Pytest Part X", slug="pytest-part-x")
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.PARTENAIRES)
        img = ImageGalerie(bloc=bloc, lien_url="javascript:alert(1)", position=1)
        with pytest.raises(ValidationError):
            img.full_clean()


def test_rootconfig_champ_whitelist(tenant):
    """RootConfiguration porte domaines_embed_autorises (lisible depuis un tenant)."""
    from root_billet.models import RootConfiguration

    with tenant_context(tenant):
        config = RootConfiguration.get_solo()
        assert hasattr(config, "domaines_embed_autorises")
```

- [ ] **Step 2 — Lancer, vérifier l'échec**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages.py -k "iframe or galerie_lien or rootconfig_champ or hauteur_px" -q`
Attendu : FAIL (`AttributeError: IFRAME` / champ inexistant).

- [ ] **Step 3 — `pages/models.py` : validator** (après `valider_taille_image`, ~ligne 90) :

```python
def valider_url_sans_schema_dangereux(valeur):
    """
    Rejette une URL a schema dangereux (javascript:, data:, vbscript:).
    / Rejects a dangerous-scheme URL (javascript:, data:, vbscript:).

    Utilise pour les champs lien saisis hors save_model de BlocAdmin (ex.
    ImageGalerie.lien_url, edite par le formset inline qui ne passe PAS par
    la neutralisation de BlocAdmin.save_model).
    / Used for link fields saved outside BlocAdmin.save_model (e.g.
    ImageGalerie.lien_url, saved by the inline formset).
    """
    # Import local : evite tout cycle d'import au chargement du module.
    # / Local import: avoids any import cycle at module load time.
    from Administration.utils import url_a_schema_dangereux

    if url_a_schema_dangereux(valeur):
        raise ValidationError(
            _("Lien non autorise (schema dangereux)."),
            code="url_dangereuse",
        )
```

- [ ] **Step 4 — `pages/models.py` : imports validators** (en haut, après `from django.db import models`) :

```python
from django.core.validators import MaxValueValidator, MinValueValidator
```

- [ ] **Step 5 — `pages/models.py` : constantes + choices** (dans `Bloc`, après
`LISTE_SOUS_PAGES = "LISTE_SOUS_PAGES"` ~ligne 378) :

```python
    IFRAME = "IFRAME"
    PARTENAIRES = "PARTENAIRES"
```

Et dans `TYPE_BLOC_CHOICES`, à la fin de la liste (avant `]`) :

```python
        (IFRAME, _("Contenu integre libre (newsletter, formulaire — domaines autorises par le ROOT)")),
        (PARTENAIRES, _("Partenaires (bande de logos cliquables)")),
```

- [ ] **Step 6 — `pages/models.py` : champ `hauteur_px`** (dans `Bloc`, juste après le
champ `embed_url`, ~ligne 610) :

```python
    # Hauteur en pixels de l'iframe du bloc IFRAME. Un formulaire newsletter n'a
    # pas de ratio fixe (contrairement a une video 16:9) : on fixe une hauteur.
    # / Iframe height in pixels for the IFRAME block. A newsletter form has no
    # fixed ratio (unlike a 16:9 video): we set an explicit height.
    hauteur_px = models.PositiveIntegerField(
        default=600,
        validators=[MinValueValidator(100), MaxValueValidator(4000)],
        verbose_name=_("Hauteur de l'iframe (pixels)"),
        help_text=_("Hauteur du cadre integre, en pixels (bloc Contenu integre libre)."),
    )
```

- [ ] **Step 7 — `pages/models.py` : généraliser `embed_url`** — remplacer le `help_text`
existant du champ `embed_url` par le texte ci-dessous, et actualiser le commentaire
au-dessus du champ (models.py:597-603, encore « Bloc EMBED ») pour mentionner aussi IFRAME :

```python
        help_text=_("Lien du contenu a integrer. EMBED : video YouTube/Vimeo/PeerTube. "
                    "IFRAME : newsletter/formulaire (hote autorise par le ROOT)."),
```

- [ ] **Step 8 — `pages/models.py` : champ `lien_url` sur `ImageGalerie`** (après `legende`,
~ligne 745) :

```python
    # Lien optionnel de l'image : si renseigne, l'image devient cliquable (nouvel
    # onglet). Utilise par le bloc PARTENAIRES (logo -> site du partenaire) mais
    # valable pour TOUT bloc a ImageGalerie (ex. GALERIE). Le HTML du lien est dans
    # le template. Validator anti-XSS : l'inline ne passe pas par BlocAdmin.save_model.
    # / Optional image link: if set, the image becomes clickable (new tab). Used by
    # PARTENAIRES (logo -> partner site), valid for ANY ImageGalerie block. Anti-XSS
    # validator: the inline does not go through BlocAdmin.save_model.
    lien_url = models.CharField(
        max_length=500,
        blank=True,
        validators=[valider_url_sans_schema_dangereux],
        verbose_name=_("Lien de l'image"),
        help_text=_("Lien optionnel : rend l'image cliquable (nouvel onglet). Ex. site d'un partenaire."),
    )
```

- [ ] **Step 9 — `root_billet/models.py` : champ whitelist** (dans `RootConfiguration`,
après `stripe_mode_test`, ~ligne 31 ; `_` est déjà importé) :

```python
    # Liste blanche GLOBALE des hotes autorises a etre integres dans un bloc IFRAME
    # (app pages), un domaine par ligne. Editable UNIQUEMENT par le superadmin ROOT.
    # Partagee par tous les tenants (RootConfiguration est SHARED_APPS, schema public).
    # / GLOBAL whitelist of hosts allowed in an IFRAME block (pages app), one domain
    # per line. ROOT-superadmin only. Shared across tenants (SHARED_APPS, public).
    domaines_embed_autorises = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Domaines d'integration autorises (iframe)"),
        help_text=_("Un domaine par ligne (ex. newsletter.ghost.io). Ces hotes seuls "
                    "peuvent etre integres dans un bloc « Contenu integre libre »."),
    )
```

- [ ] **Step 10 — Générer les migrations**

Run :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations pages root_billet -n iframe_partenaires
```
Attendu : 2 migrations créées (pages : `0002_iframe_partenaires` = AlterField type_bloc +
AddField hauteur_px + AddField lien_url ; root_billet : `0007_iframe_partenaires` = AddField
domaines_embed_autorises). Vérifier qu'aucune dépendance croisée entre les deux (aucune FK).

- [ ] **Step 11 — Appliquer les migrations**

Run :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```
Attendu : OK sur public + tenants.

- [ ] **Step 12 — Lancer les tests, vérifier PASS**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages.py -k "iframe or galerie_lien or rootconfig_champ or hauteur_px" -q`
Attendu : PASS.

- [ ] **Step 13 — `ruff check` (fichiers modifiés, pas de format)**

Run : `docker exec lespass_django poetry run ruff check pages/models.py root_billet/models.py`
Attendu : pas de nouvelle erreur (rapporter au mainteneur si l'existant en a déjà).

- [ ] **Step 14 — Commit (message suggéré, exécuté par le mainteneur)**

```
feat(pages): modeles blocs IFRAME + PARTENAIRES (hauteur_px, lien_url, whitelist ROOT)
```

---

## Task 2 : Tag `iframe_libre` + helper whitelist

**Files:**
- Modify: `pages/templatetags/pages_tags.py` (helper + tag, après `embed_iframe`, ~ligne 232)
- Test: `tests/pytest/test_pages.py`

**Interfaces :**
- Consomme : `RootConfiguration.domaines_embed_autorises` (Task 1)
- Produit : `iframe_libre(url, hauteur)` → HTML `<iframe>` (whitelist+https) ou `""`

- [ ] **Step 1 — Écrire les tests (échouent)** :

```python
def _set_whitelist_embed(valeur):
    """Pose la whitelist ROOT + vide le cache django-solo (scope par schema)."""
    from django.core.cache import cache
    from root_billet.models import RootConfiguration

    config = RootConfiguration.get_solo()
    config.domaines_embed_autorises = valeur
    config.save()
    cache.clear()


@pytest.fixture
def whitelist_embed(tenant):
    """Sauvegarde/restaure domaines_embed_autorises autour d'un test."""
    from root_billet.models import RootConfiguration

    with tenant_context(tenant):
        avant = RootConfiguration.get_solo().domaines_embed_autorises
    yield
    with tenant_context(tenant):
        _set_whitelist_embed(avant)


def test_iframe_libre_hote_autorise(tenant, whitelist_embed):
    """Hote whiteliste + https -> <iframe> avec le src fourni et la hauteur."""
    from pages.templatetags.pages_tags import iframe_libre

    with tenant_context(tenant):
        _set_whitelist_embed("newsletter.ghost.io")
        html = iframe_libre("https://newsletter.ghost.io/abo", 480)
        assert "<iframe" in html
        assert "https://newsletter.ghost.io/abo" in html
        assert 'height="480"' in html
        assert "sandbox=" in html


def test_iframe_libre_hote_refuse(tenant, whitelist_embed):
    """Hote absent de la whitelist -> chaine vide (jamais d'iframe arbitraire)."""
    from pages.templatetags.pages_tags import iframe_libre

    with tenant_context(tenant):
        _set_whitelist_embed("newsletter.ghost.io")
        assert iframe_libre("https://evil.example/x", 480) == ""


def test_iframe_libre_refuse_http(tenant, whitelist_embed):
    """Schema http (hote pourtant whiteliste) -> chaine vide."""
    from pages.templatetags.pages_tags import iframe_libre

    with tenant_context(tenant):
        _set_whitelist_embed("newsletter.ghost.io")
        assert iframe_libre("http://newsletter.ghost.io/abo", 480) == ""


def test_iframe_libre_url_vide(tenant, whitelist_embed):
    """URL vide/invalide -> chaine vide (pas de crash)."""
    from pages.templatetags.pages_tags import iframe_libre

    with tenant_context(tenant):
        _set_whitelist_embed("newsletter.ghost.io")
        assert iframe_libre("", 480) == ""
        assert iframe_libre(None, 480) == ""


def test_iframe_libre_whitelist_normalisee(tenant, whitelist_embed):
    """La whitelist tolere schema/slash/casse/lignes vides."""
    from pages.templatetags.pages_tags import iframe_libre

    with tenant_context(tenant):
        _set_whitelist_embed("  https://Newsletter.Ghost.IO/  \n\n autre.example \n")
        assert "<iframe" in iframe_libre("https://newsletter.ghost.io/abo", 480)
        assert "<iframe" in iframe_libre("https://autre.example/form", 480)
```

- [ ] **Step 2 — Lancer, vérifier l'échec**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages.py -k iframe_libre -q`
Attendu : FAIL (`ImportError: iframe_libre`).

- [ ] **Step 3 — `pages/templatetags/pages_tags.py` : helper + tag** (après `embed_iframe`,
avant `jsonld_event`) :

```python
def _domaines_embed_autorises():
    """
    Ensemble des hotes autorises pour un bloc IFRAME (whitelist GLOBALE ROOT).
    Lit RootConfiguration.domaines_embed_autorises (SHARED_APPS, schema public ;
    lisible depuis un tenant via le search_path). Normalise chaque ligne : on
    retire espaces, casse, et un eventuel schema/slash (un ROOT collera souvent
    "https://newsletter.ghost.io/").
    / Set of allowed hosts for an IFRAME block (GLOBAL ROOT whitelist). Reads
    RootConfiguration.domaines_embed_autorises (SHARED, public schema; readable
    from a tenant). Normalizes each line: strip spaces/case and an optional
    scheme/slash.
    """
    from urllib.parse import urlparse

    from root_billet.models import RootConfiguration

    brut = RootConfiguration.get_solo().domaines_embed_autorises or ""
    hotes = set()
    for ligne in brut.splitlines():
        valeur = ligne.strip().lower()
        if not valeur:
            continue
        # Si le ROOT a colle un schema/slash, on extrait juste l'hote.
        # / If the ROOT pasted a scheme/slash, extract just the host.
        if "://" in valeur:
            valeur = urlparse(valeur).hostname or ""
        else:
            valeur = valeur.split("/")[0]
        if valeur:
            hotes.add(valeur)
    return hotes


@register.simple_tag
def iframe_libre(url, hauteur=600):
    """
    Rend un <iframe> pour une URL HTTPS dont l'hote est dans la whitelist GLOBALE
    ROOT (RootConfiguration.domaines_embed_autorises). Tout autre cas -> chaine
    vide : on n'injecte JAMAIS un iframe vers un hote arbitraire (securite). Le
    src est ECHAPPE, la hauteur CASTEE en int. Contrairement a embed_iframe, on
    garde l'URL telle quelle (principe d'un iframe libre : formulaire/newsletter).
    / Renders an <iframe> for an HTTPS URL whose host is in the GLOBAL ROOT
    whitelist. Any other case -> empty string. src ESCAPED, height cast to int.
    Unlike embed_iframe, we keep the URL as-is (free iframe: form/newsletter).

    Utilisation : {% iframe_libre bloc.embed_url bloc.hauteur_px %}
    """
    from urllib.parse import urlparse

    from django.utils.html import escape

    if not url or not isinstance(url, str):
        return ""
    try:
        decoupage = urlparse(url)
    except (ValueError, TypeError):
        return ""
    # HTTPS obligatoire (un iframe http: serait bloque en mixed content de toute
    # facon) + hote non vide. / HTTPS required + non-empty host.
    if decoupage.scheme != "https":
        return ""
    hote = (decoupage.hostname or "").lower()
    if not hote or hote not in _domaines_embed_autorises():
        return ""

    # Hauteur bornee/castee (defense en profondeur, meme si le modele valide deja).
    # / Height bounded/cast (defense in depth, even though the model validates).
    try:
        hauteur_int = max(100, min(4000, int(hauteur)))
    except (ValueError, TypeError):
        hauteur_int = 600

    iframe = (
        f'<div class="tb-iframe">'
        f'<iframe src="{escape(url)}" title="Contenu integre" height="{hauteur_int}" '
        f'loading="lazy" referrerpolicy="no-referrer" '
        f'sandbox="allow-scripts allow-same-origin allow-forms allow-popups">'
        f"</iframe></div>"
    )
    return mark_safe(iframe)
```

- [ ] **Step 4 — Lancer les tests, vérifier PASS**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages.py -k iframe_libre -q`
Attendu : PASS (6 tests).

- [ ] **Step 5 — `ruff check`**

Run : `docker exec lespass_django poetry run ruff check pages/templatetags/pages_tags.py`

- [ ] **Step 6 — Commit (suggéré)** : `feat(pages): tag iframe_libre borne par la whitelist ROOT`

---

## Task 3 : Admin (blocs + RootConfigurationAdmin superadmin-strict)

**Files:**
- Modify: `pages/admin.py` (`fields`, `conditional_fields`, `get_inlines`, `ImageGalerieInline.fields`, commentaire)
- Modify: `Administration/admin_tenant.py` (`RootConfigurationAdmin`)
- Test: `tests/pytest/test_pages.py`

**Interfaces :**
- Consomme : Task 1 (champs), `staff_admin_site`, `RootConfiguration`
- Produit : inline visible pour PARTENAIRES ; champ `domaines_embed_autorises` éditable
  superadmin strict

- [ ] **Step 1 — Écrire les tests (échouent)** :

```python
def test_get_inlines_partenaires(tenant, nettoyer_pages):
    """L'inline ImageGalerie apparait pour un bloc PARTENAIRES."""
    from django.test import RequestFactory

    from Administration.admin.site import staff_admin_site
    from pages.admin import BlocAdmin, ImageGalerieInline
    from pages.models import Bloc, Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Pytest Adm", slug="pytest-adm")
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.PARTENAIRES)
        admin = BlocAdmin(Bloc, staff_admin_site)
        request = RequestFactory().get("/")
        inlines = admin.get_inlines(request, bloc)
        assert ImageGalerieInline in inlines


def test_conditional_fields_nouveaux_types():
    """titre visible pour IFRAME/PARTENAIRES ; hauteur_px pour IFRAME."""
    from Administration.admin.site import staff_admin_site
    from pages.admin import BlocAdmin
    from pages.models import Bloc

    admin = BlocAdmin(Bloc, staff_admin_site)
    assert "IFRAME" in admin.conditional_fields["titre"]
    assert "PARTENAIRES" in admin.conditional_fields["titre"]
    assert admin.conditional_fields["hauteur_px"] == "type_bloc == 'IFRAME'"
    assert "IFRAME" in admin.conditional_fields["embed_url"]
    assert "hauteur_px" in admin.fields


def test_rootconfig_admin_superadmin_strict(tenant):
    """RootConfigurationAdmin : perms reservees au superadmin (is_superuser)."""
    from django.test import RequestFactory

    from Administration.admin.site import staff_admin_site
    from Administration.admin_tenant import RootConfigurationAdmin
    from root_billet.models import RootConfiguration

    admin = RootConfigurationAdmin(RootConfiguration, staff_admin_site)
    request = RequestFactory().get("/")

    class _User:
        is_superuser = False
    request.user = _User()
    assert admin.has_view_permission(request) is False
    request.user.is_superuser = True
    assert admin.has_view_permission(request) is True
    assert list(admin.get_fields(request)) == ["domaines_embed_autorises"]
```

- [ ] **Step 2 — Vérifier l'échec**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages.py -k "get_inlines_partenaires or conditional_fields_nouveaux or rootconfig_admin" -q`
Attendu : FAIL.

- [ ] **Step 3 — `pages/admin.py` : `ImageGalerieInline.fields`** (ligne 211) — ajouter
`lien_url` :

```python
    fields = ("image", "legende", "lien_url", "position")
```

- [ ] **Step 4 — `pages/admin.py` : `BlocAdmin.fields`** — ajouter `hauteur_px` juste après
`"embed_url",` (ligne 417) :

```python
        "embed_url",
        "hauteur_px",
```

- [ ] **Step 5 — `pages/admin.py` : `get_inlines`** (ligne 346) — ajouter `Bloc.PARTENAIRES` :

```python
        if obj is not None and obj.type_bloc in (Bloc.GALERIE, Bloc.MARKDOWN, Bloc.PARTENAIRES):
```

- [ ] **Step 6 — `pages/admin.py` : `conditional_fields`** — modifier `titre`, ajouter
`hauteur_px`, étendre `embed_url` (lignes 436, 439) :

```python
        "titre": "['HERO','PARAGRAPHE','IMAGE_TEXTE','CTA','VIDEO_TEXTE','CARTE','IMAGE','CARTE_LEAFLET','FAQ','EVENEMENTS','GALERIE','EMBED','MARKDOWN','LISTE_SOUS_PAGES','IFRAME','PARTENAIRES'].includes(type_bloc)",
```
```python
        "embed_url": "['EMBED','IFRAME'].includes(type_bloc)",
        "hauteur_px": "type_bloc == 'IFRAME'",
```

- [ ] **Step 7 — `pages/admin.py` : commentaire « 16 types »** (lignes 373 et 378) —
remplacer « 16 types » par « 18 types ».

- [ ] **Step 8 — `Administration/admin_tenant.py` : imports requis** — `RootConfiguration`
et `cache` sont **absents** de ce fichier (confirmé review). Les DEUX sont **obligatoires**
(sinon `NameError` au chargement). Ajouter en tête :

```python
from django.core.cache import cache
from root_billet.models import RootConfiguration
```

- [ ] **Step 8b — `Administration/admin_tenant.py` : `RootConfigurationAdmin`** — ajouter
juste après `TenantAdmin` (~ligne 3628) :

```python
@admin.register(RootConfiguration, site=staff_admin_site)
class RootConfigurationAdmin(SingletonModelAdmin, ModelAdmin):
    """
    Config ROOT — ici on n'expose QUE la whitelist des domaines d'integration
    iframe (bloc IFRAME de l'app pages). JAMAIS les cles Stripe/Fedow. Reserve au
    SUPERADMIN strict (is_superuser) : le modele n'apparait dans la sidebar que
    pour lui. RootConfiguration est un singleton SHARED (schema public) : editer
    depuis n'importe quel tenant modifie la meme ligne globale (voulu).
    / ROOT config — expose ONLY the iframe-embed domains whitelist here, NEVER the
    Stripe/Fedow keys. STRICT superadmin only.
    """

    fields = ("domaines_embed_autorises",)

    def save_model(self, request, obj, form, change):
        # Vide le cache django-solo (scope par schema) pour que TOUS les tenants
        # voient la nouvelle whitelist sans attendre l'expiration (~5 min).
        # / Clear the per-schema django-solo cache so ALL tenants see the new
        # whitelist immediately (pattern de RootConfiguration.set_stripe_api).
        super().save_model(request, obj, form, change)
        cache.clear()

    def has_view_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_add_permission(self, request):
        # Singleton : jamais d'ajout. / Singleton: no add.
        return False

    def has_change_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        # Singleton : pas de suppression. / Singleton: no deletion.
        return False
```

> Note d'implémentation : `SingletonModelAdmin` (solo) + `ModelAdmin` (Unfold) sont déjà
> combinés dans `pages/admin.py:54` (`ConfigurationSiteAdmin`) — même pattern, éprouvé.

- [ ] **Step 8c — Sidebar : rendre la whitelist accessible au superadmin** — sans entrée
sidebar, le modèle n'apparaît nulle part (`get_sidebar_navigation` est une liste explicite,
`show_all_applications: False`). Dans `Administration/admin/dashboard.py`, section
« Site web » (dans le bloc `if configuration.module_pages:`, ~ligne 122), **ajouter un item**
à la fin de la liste `"items"` (après « Configuration du site »). `root_permission`
(= `RootPermissionWithRequest`, `is_authenticated and is_superuser`) est déjà défini
ligne 57 et utilisé ailleurs :

```python
                    {
                        # Whitelist des domaines d'integration iframe (RootConfiguration).
                        # Visible UNIQUEMENT par le superadmin ROOT. / iframe-embed
                        # domains whitelist — ROOT superadmin only.
                        "title": _("Domaines iframe (ROOT)"),
                        "icon": "shield",
                        "link": reverse_lazy(
                            "staff_admin:root_billet_rootconfiguration_changelist"
                        ),
                        "permission": root_permission,
                    },
```

> `SingletonModelAdmin` redirige `_changelist` vers l'unique instance : le lien ouvre
> directement le formulaire. (Fallback si besoin : URL directe
> `/<prefixe-admin>/root_billet/rootconfiguration/`.)

- [ ] **Step 9 — Lancer les tests, vérifier PASS**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages.py -k "get_inlines_partenaires or conditional_fields_nouveaux or rootconfig_admin" -q`
Attendu : PASS.

- [ ] **Step 10 — `manage.py check`** (l'admin doit charger)

Run : `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`
Attendu : 0 issue.

- [ ] **Step 11 — `ruff check`** sur `pages/admin.py` et `Administration/admin_tenant.py`.

- [ ] **Step 12 — Commit (suggéré)** : `feat(pages): admin blocs IFRAME/PARTENAIRES + RootConfigurationAdmin superadmin`

---

## Task 4 : Templates + CSS

**Files:**
- Create: `pages/templates/pages/classic/partials/bloc_iframe.html`
- Create: `pages/templates/pages/classic/partials/bloc_partenaires.html`
- Modify: `pages/templates/pages/classic/partials/bloc_galerie.html` (+lien cliquable)
- Modify: `pages/static/pages/css/tb-blocs.css` (+`.tb-iframe`, +`.tb-partenaires`)
- Test: `tests/pytest/test_pages.py`

**Interfaces :** consomme le tag `iframe_libre` (Task 2), `bloc.images_galerie`, `img.lien_url`.

- [ ] **Step 1 — Écrire les tests de rendu (échouent)** :

```python
def test_rendu_bloc_iframe(tenant, whitelist_embed, nettoyer_pages):
    """bloc_iframe : hote autorise -> <iframe> ; hote refuse -> message honnete."""
    from django.template.loader import render_to_string

    from pages.models import Bloc, Page

    with tenant_context(tenant):
        _set_whitelist_embed("newsletter.ghost.io")
        page = Page.objects.create(titre="Pytest Rif", slug="pytest-rif")
        bloc_ok = Bloc.objects.create(
            page=page, type_bloc=Bloc.IFRAME,
            embed_url="https://newsletter.ghost.io/abo", hauteur_px=400,
        )
        html_ok = render_to_string("pages/classic/partials/bloc_iframe.html", {"bloc": bloc_ok})
        assert "<iframe" in html_ok
        assert 'data-testid="bloc-iframe"' in html_ok

        bloc_ko = Bloc.objects.create(
            page=page, type_bloc=Bloc.IFRAME,
            embed_url="https://evil.example/x", hauteur_px=400,
        )
        html_ko = render_to_string("pages/classic/partials/bloc_iframe.html", {"bloc": bloc_ko})
        assert "<iframe" not in html_ko
        assert ("hote non autoris" in html_ko.lower()) or ("host" in html_ko.lower())


def test_rendu_bloc_partenaires_lien(tenant, nettoyer_pages):
    """bloc_partenaires : logo avec lien_url -> <a target=_blank rel=noopener> ; sans -> pas de lien."""
    from django.template.loader import render_to_string

    from pages.models import Bloc, ImageGalerie, Page

    with tenant_context(tenant):
        page = Page.objects.create(titre="Pytest Rpart", slug="pytest-rpart")
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.PARTENAIRES)
        # Sans image reelle, le template ne rendra pas d'<img> (garde {% if img.image %}) ;
        # on verifie la logique du lien via le CONTEXTE d'un item factice n'est pas
        # possible ici -> on teste la presence des classes/testid du conteneur.
        html = render_to_string("pages/classic/partials/bloc_partenaires.html", {"bloc": bloc})
        assert 'data-testid="bloc-partenaires"' in html
```

> Note test : `ImageGalerie` sans fichier image réel ne rend pas d'`<img>` (le template
> garde `{% if img.image %}`). Le test de rendu du lien cliquable **avec** image se fait en
> Chrome (Task 5), où l'on uploade un vrai logo. Le test pytest ci-dessus verrouille le
> conteneur + testid ; la logique `lien_url` est verrouillée par le rendu HTML inspecté
> dans Task 5.

- [ ] **Step 2 — Vérifier l'échec**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages.py -k "rendu_bloc_iframe or rendu_bloc_partenaires" -q`
Attendu : FAIL (`TemplateDoesNotExist`).

- [ ] **Step 3 — Créer `pages/templates/pages/classic/partials/bloc_iframe.html`** :

```django
{% load i18n pages_tags %}
{% comment %}
    BLOC IFRAME — skin classic. Contenu integre LIBRE (newsletter, formulaire) via
    le tag iframe_libre, borne par la whitelist ROOT (domaines_embed_autorises).
    Hauteur libre (pas de ratio 16:9, contrairement a EMBED). Hote non autorise ->
    message honnete, pas de section muette.
    / IFRAME block — classic skin. FREE embedded content via iframe_libre, bounded
    by the ROOT whitelist. Free height (no 16:9 ratio). Unauthorized host -> honest
    message.
{% endcomment %}
{% iframe_libre bloc.embed_url bloc.hauteur_px as integre %}
{# Condition externe : on rend la section aussi quand l'URL est fournie mais l'hote #}
{# refuse, pour afficher le message honnete (sinon section muette). #}
{% if integre or bloc.titre or bloc.embed_url %}
    <section class="tb-bloc tb-bloc--iframe" data-testid="bloc-iframe">
        <div class="tb-bloc__contenu">
            {% if bloc.titre %}<h2 class="tb-bloc__titre">{{ bloc.titre }}</h2>{% endif %}
            {% if integre %}
                {{ integre }}
            {% elif bloc.embed_url %}
                {# URL fournie mais hote non autorise : message honnete (comme bloc_embed). #}
                {# / URL provided but host not allowed: honest message. #}
                <p class="tb-bloc__texte">{% translate "Ce contenu ne peut pas etre integre (hote non autorise)." %}</p>
            {% endif %}
        </div>
    </section>
{% endif %}
```

- [ ] **Step 4 — Créer `pages/templates/pages/classic/partials/bloc_partenaires.html`** :

```django
{% load i18n %}
{% comment %}
    BLOC PARTENAIRES — skin classic. Bande de logos (modele ImageGalerie, reutilise).
    Chaque logo est cliquable si img.lien_url est renseigne (nouvel onglet, rel=noopener).
    Logos monochromes au repos, couleur au survol (CSS filter, conforme Hallmark).
    / PARTENAIRES block — classic skin. Logo strip (ImageGalerie reused). Each logo is
    clickable if img.lien_url is set (new tab, rel=noopener). Grayscale at rest.
{% endcomment %}
<section class="tb-bloc tb-bloc--partenaires" data-testid="bloc-partenaires">
    <div class="tb-bloc__contenu">
        {% if bloc.titre %}<h2 class="tb-bloc__titre">{{ bloc.titre }}</h2>{% endif %}
        {% with images=bloc.images_galerie.all %}
            {% if images %}
                <div class="tb-partenaires">
                    {% for img in images %}
                        {% if img.image %}
                            {% if img.lien_url %}
                                <a class="tb-partenaires__lien" href="{{ img.lien_url }}"
                                   target="_blank" rel="noopener"
                                   aria-label="{% blocktranslate with nom=img.legende %}Site du partenaire {{ nom }}{% endblocktranslate %}">
                                    <img class="tb-partenaires__logo" src="{{ img.image.med.url }}"
                                         alt="{{ img.legende }}" loading="lazy">
                                </a>
                            {% else %}
                                <img class="tb-partenaires__logo" src="{{ img.image.med.url }}"
                                     alt="{{ img.legende }}" loading="lazy">
                            {% endif %}
                        {% endif %}
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}
    </div>
</section>
```

- [ ] **Step 5 — Retoucher `bloc_galerie.html`** — rendre l'image cliquable si `lien_url`
(remplacer le bloc `<img …>` lignes 16-19 par) :

```django
                            <figure class="tb-galerie__item">
                                {% if img.lien_url %}
                                    <a href="{{ img.lien_url }}" target="_blank" rel="noopener">
                                        <img class="tb-galerie__image"
                                             src="{{ img.image.med.url }}"
                                             alt="{{ img.legende }}" loading="lazy">
                                    </a>
                                {% else %}
                                    <img class="tb-galerie__image"
                                         src="{{ img.image.med.url }}"
                                         alt="{{ img.legende }}" loading="lazy">
                                {% endif %}
```

- [ ] **Step 6 — `tb-blocs.css`** — ajouter à la fin du fichier :

```css
/* ---------------------------------------------------------------------------
 * IFRAME — contenu intégré libre (newsletter, formulaire). Hauteur fixée par le
 * bloc (height inline sur l'iframe), largeur 100 %.
 * / IFRAME — free embedded content. Height set by the block, full width.
 * ------------------------------------------------------------------------- */
.tb-iframe { width: 100%; margin-top: 1.5rem; }
.tb-iframe iframe {
    width: 100%;
    border: 0;
    border-radius: var(--tb-rayon-sm);
    box-shadow: var(--tb-ombre);
    display: block;
    max-width: 100%;
}

/* ---------------------------------------------------------------------------
 * PARTENAIRES — bande de logos. Grille responsive ; logos en niveaux de gris au
 * repos, couleur au survol/focus (transition sur filter/opacity uniquement).
 * / PARTENAIRES — logo strip. Grayscale at rest, color on hover/focus.
 * ------------------------------------------------------------------------- */
.tb-partenaires {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 8rem), 1fr));
    gap: clamp(1rem, 3vw, 2rem);
    align-items: center;
    margin-top: 1.75rem;
}
.tb-partenaires__logo {
    width: 100%;
    max-height: 4.5rem;
    object-fit: contain;
    filter: grayscale(1);
    opacity: 0.75;
    transition: filter 0.2s ease, opacity 0.2s ease;
}
.tb-partenaires__lien:hover .tb-partenaires__logo,
.tb-partenaires__lien:focus-visible .tb-partenaires__logo,
.tb-partenaires__logo:hover {
    filter: grayscale(0);
    opacity: 1;
}
@media (prefers-reduced-motion: reduce) {
    .tb-partenaires__logo { transition: none; }
}
```

- [ ] **Step 7 — Lancer les tests, vérifier PASS**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages.py -k "rendu_bloc_iframe or rendu_bloc_partenaires" -q`
Attendu : PASS.

- [ ] **Step 8 — Suite complète pages (non-régression)**

Run : `docker exec lespass_django poetry run pytest tests/pytest/test_pages.py -q`
Attendu : tout PASS.

- [ ] **Step 9 — Commit (suggéré)** : `feat(pages): templates + CSS blocs IFRAME et PARTENAIRES (galerie cliquable)`

---

## Task 5 : Validation Chrome (GOAL) + doc

> **Objectif mainteneur : tout est testé dans Chrome.** Serveur déjà servi par Traefik.
> Utiliser le MCP `claude-in-chrome` (nouvel onglet, `tabs_context_mcp` d'abord). Tenant de
> test : `lespass` (skin classic) → `https://lespass.tibillet.localhost/`. Se connecter à
> l'admin avec l'admin de test (`admin@admin.com`) — le superadmin est requis pour la
> whitelist.

- [ ] **Step 1 — Whitelist ROOT** : dans la sidebar, section « Site web », ouvrir
**« Domaines iframe (ROOT) »** (item ajouté Task 3 Step 8c, visible seulement en superadmin).
Renseigner `domaines_embed_autorises` avec un domaine réellement intégrable pour le test
(ex. un domaine de formulaire https qui autorise l'iframing). Enregistrer. Vérifier que
l'item **n'apparaît PAS** pour un admin tenant non-superadmin (test manuel : se
reconnecter en admin tenant simple si dispo). Fallback URL directe si besoin :
`/<prefixe-admin>/root_billet/rootconfiguration/`.

- [ ] **Step 2 — Créer un bloc IFRAME** : Admin → Blocs → Ajouter. Choisir type
« Contenu intégré libre » → vérifier que **seuls** `page`, `titre`, `embed_url`,
`hauteur_px` s'affichent (conditional_fields). Renseigner l'URL whitelistée + hauteur.
Rattacher à une page publiée de test. Enregistrer.

- [ ] **Step 3 — Vérifier le rendu IFRAME public** : ouvrir la page publique, confirmer que
l'`<iframe>` s'affiche à la bonne hauteur. Puis éditer le bloc avec une URL **hors**
whitelist → recharger → confirmer le **message « hôte non autorisé »** (pas d'iframe).
Screenshot des deux états.

- [ ] **Step 4 — Créer un bloc PARTENAIRES** : type « Partenaires », enregistrer une 1re
fois (l'inline Images apparaît après le save). Ajouter 2-3 logos (upload) ; sur au moins
un, renseigner `lien_url` (site du partenaire), en laisser un sans lien. Enregistrer.

- [ ] **Step 5 — Vérifier le rendu PARTENAIRES public** : la bande de logos s'affiche
(grisés, couleur au survol). Cliquer un logo **avec** lien → confirmer l'ouverture dans un
**nouvel onglet**. Un logo **sans** lien n'est pas cliquable. Inspecter le HTML : `<a
target="_blank" rel="noopener">` présent uniquement sur les logos à lien. Screenshot.

- [ ] **Step 6 — Enregistrer un GIF** (`gif_creator`) du parcours admin → rendu, nommé
`chantier06-iframe-partenaires.gif`, pour la fiche de test.

- [ ] **Step 7 — `CHANGELOG.md`** — ajouter en haut une entrée bilingue :

```markdown
## N. Blocs Pages : Contenu intégré libre (iframe) + Partenaires / Pages blocks: free iframe embed + Partners

**Quoi / What:** Deux nouveaux blocs pour l'app pages. IFRAME intègre un contenu externe
(newsletter, formulaire) borné par une whitelist de domaines gérée par le ROOT.
PARTENAIRES affiche une bande de logos cliquables (mécanisme lien réutilisé par la galerie).
**Pourquoi / Why:** permettre newsletters (Ghost) et encarts partenaires sans développeur.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/models.py` | +types IFRAME/PARTENAIRES, +hauteur_px, +lien_url, validator anti-schéma |
| `root_billet/models.py` | +domaines_embed_autorises (whitelist ROOT) |
| `pages/templatetags/pages_tags.py` | tag iframe_libre (whitelist + https) |
| `pages/admin.py` | conditional_fields, inline PARTENAIRES, lien_url |
| `Administration/admin_tenant.py` | RootConfigurationAdmin (superadmin strict) |
| `pages/templates/.../bloc_iframe.html`, `bloc_partenaires.html`, `bloc_galerie.html` | rendus |
| `pages/static/pages/css/tb-blocs.css` | styles .tb-iframe, .tb-partenaires |

### Migration
- **Migration nécessaire / Migration required:** Oui — `migrate_schemas --executor=multiprocessing`
```

- [ ] **Step 8 — Fiche `A TESTER et DOCUMENTER/blocs-iframe-partenaires.md`** : reprendre
les scénarios Steps 1-5 (whitelist ROOT, conditional_fields IFRAME, hôte autorisé/refusé,
logos cliquables), + commandes DB de vérif si utile, + lien vers le GIF.

- [ ] **Step 9 — i18n (mainteneur)** : signaler qu'il faut lancer `makemessages`/
`compilemessages` (nouveaux libellés FR ajoutés dans models, templates, admin).

- [ ] **Step 10 — Commit (suggéré)** : `docs(pages): CHANGELOG + fiche test blocs IFRAME/PARTENAIRES`

---

## Self-review (couverture spec)

- IFRAME modèle (embed_url réutilisé + hauteur_px) → Task 1 ✓
- Whitelist ROOT (`domaines_embed_autorises`) → Task 1 (champ) + Task 3 (admin superadmin) ✓
- Tag `iframe_libre` (https + whitelist + sandbox + normalisation) → Task 2 ✓
- PARTENAIRES (ImageGalerie + lien_url + validator XSS) → Task 1 + Task 4 ✓
- Mécanisme image cliquable réutilisé par GALERIE → Task 4 Step 5 ✓
- conditional_fields titre/embed_url/hauteur_px + get_inlines → Task 3 ✓
- Templates classic + fallback FF automatique (select_template) → Task 4 ✓
- CSS Hallmark (grayscale, prefers-reduced-motion) → Task 4 ✓
- Migrations indépendantes (pages dual-list / root_billet SHARED) → Task 1 ✓
- Cache django-solo (`cache.clear()` à la save) → Task 3 Step 8 ✓
- Tests pytest (modèles, tag, admin, rendu) → Tasks 1-4 ✓
- **Validation Chrome complète (goal)** → Task 5 ✓
- CHANGELOG + fiche A TESTER → Task 5 ✓
