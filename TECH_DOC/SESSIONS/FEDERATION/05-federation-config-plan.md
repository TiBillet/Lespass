# Plan d'implémentation — `FederationConfiguration` (Phase A, zéro JS)

> **For agentic workers:** ce plan se déroule **inline** dans la session (executing-plans).
> Étapes en checkbox (`- [ ]`).
> **Spec :** [04-federation-config-design.md](04-federation-config-design.md).
> **État final :** Phase A livrée + option 1 (« lieux sans adresse ») finalement traitée
> **côté serveur sans JS** (point sans coordonnées injecté ; cf. §6 du design), fixtures
> `demo_data_v2` enrichies (3 scénarios), et tests d'intégration vue ajoutés
> (`tests/pytest/test_federation_view_integration.py`). **Pas de Phase B JS.**
> **Contraintes projet :** AUCUNE opération git de l'assistant (le mainteneur committe —
> remplace toute étape « commit » par « → le mainteneur committe ») · pas de
> `makemessages`/`compilemessages` auto · règle des 3 fichiers avant `check` + tests ·
> serveur tenu par le mainteneur dans byobu · **Phase B (option 1 / explorer.js) HORS scope**.

**Goal :** rendre configurables par tenant les options d'affichage de `/federation/`
(filtre event, lieux entrants, texte d'intro, tri), via un singleton django-solo,
sans toucher au JS ni au cache SEO.

**Architecture :** modèle `SingletonModel` tenant `FederationConfiguration` (BaseBillet) ;
logique de filtre/tri en fonction pure `appliquer_options_federation()` (seo/services.py) ;
câblage dans `FederationViewset.list` ; admin Unfold (patron `CrowdConfigAdmin`) + item
sidebar ; texte d'intro WYSIWYG dans `explorer.html`.

**Tech Stack :** Django, django-tenants, django-solo, django-unfold, DRF ViewSet, pytest.

---

### Task 1 : Modèle `FederationConfiguration` + migration

**Files :**
- Modify : `BaseBillet/models.py` (insérer la classe juste avant `class FederatedPlace(models.Model):`)

Prérequis déjà présents dans le fichier : `from solo.models import SingletonModel` (l.35),
`models`, `gettext_lazy as _`.

- [ ] **1.1** Ajouter la classe :

```python
class FederationConfiguration(SingletonModel):
    """
    Options d'affichage de la page Réseau local (/federation/) pour ce tenant.
    Singleton tenant : 1 instance par schema. Lu par FederationViewset.list.
    / Display options for this tenant's Local network page (/federation/).
    Tenant singleton: 1 row per schema. Read by FederationViewset.list.

    LOCALISATION : BaseBillet/models.py

    Toutes les options s'appliquent à la CONSOMMATION (la vue), pas au cache
    SEO pré-calculé (refresh_seo_cache). Additif, zéro migration de cache.
    / All options apply at CONSUMPTION time (the view), not to the pre-computed
    SEO cache. Additive, no cache migration.
    """

    # Tri de la liste des lieux / Sort order of the venues list
    TRI_ALPHABETIQUE = "alpha"
    TRI_EVENTS_A_VENIR = "events"
    TRI_CHOICES = [
        (TRI_ALPHABETIQUE, _("Alphabétique")),
        (TRI_EVENTS_A_VENIR, _("Par prochain événement")),
    ]

    afficher_lieux_sans_adresse = models.BooleanField(
        default=True,
        verbose_name=_("Afficher les lieux sans adresse"),
        help_text=_(
            "Si activé, la liste inclut aussi les lieux du réseau sans adresse "
            "géolocalisée (ils n'apparaissent pas sur la carte). "
            "[Effectif après la Phase B — modification du JS.]"
        ),
    )
    afficher_seulement_lieux_avec_event = models.BooleanField(
        default=False,
        verbose_name=_("Afficher seulement les lieux avec un événement à venir"),
        help_text=_(
            "Si activé, seuls les lieux ayant au moins un événement publié à venir "
            "sont affichés."
        ),
    )
    afficher_lieux_entrants = models.BooleanField(
        default=True,
        verbose_name=_("Afficher les lieux qui me fédèrent"),
        help_text=_(
            "Si activé, affiche aussi les lieux qui m'ont ajouté à leur réseau, "
            "même si je ne les ai pas ajoutés au mien."
        ),
    )
    texte_introduction = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Texte d'introduction"),
        help_text=_("Texte affiché en haut de la page Réseau local."),
    )
    tri_des_lieux = models.CharField(
        max_length=10,
        choices=TRI_CHOICES,
        default=TRI_ALPHABETIQUE,
        verbose_name=_("Tri des lieux"),
        help_text=_("Ordre d'affichage de la liste des lieux."),
    )

    class Meta:
        verbose_name = _("Options de fédération")
        verbose_name_plural = _("Options de fédération")

    def __str__(self):
        return str(_("Options de fédération"))
```

> Note : `afficher_lieux_sans_adresse` est créé dès la Phase A (défaut `True`) mais reste
> sans effet visible tant que la Phase B (JS) n'est pas faite. Le help_text le signale.

- [ ] **1.2** Générer la migration :
`docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet`
- [ ] **1.3** Appliquer :
`docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`
- [ ] **1.4** `docker exec lespass_django poetry run python /DjangoFiles/manage.py check` → 0 issue.
- [ ] **1.5** → le mainteneur committe.

---

### Task 2 : Fonction pure `appliquer_options_federation` + tests (TDD)

**Files :**
- Test : `tests/pytest/test_federation_config.py` (créer)
- Modify : `seo/services.py` (ajouter la fonction en fin de fichier)

- [ ] **2.1** Écrire le test qui échoue :

```python
"""
Tests de la logique d'options de fédération
(seo.services.appliquer_options_federation).
/ Tests for the federation display-options logic.

LOCALISATION : tests/pytest/test_federation_config.py
Voir SESSIONS/FEDERATION/04-federation-config-design.md.
"""


def _explorer_data_exemple():
    """Jeu explorer minimal : 3 points (3 tenants), 3 tenants."""
    return {
        "points": [
            {"pa_id": 1, "tenant_id": "uuid-B", "tenant_organisation": "Beta",
             "events_futurs": [{"datetime_iso": "2026-07-01T20:00:00+00:00"}],
             "events_futurs_count_total": 1},
            {"pa_id": 2, "tenant_id": "uuid-A", "tenant_organisation": "Alpha",
             "events_futurs": [], "events_futurs_count_total": 0},
            {"pa_id": 3, "tenant_id": "uuid-C", "tenant_organisation": "Gamma",
             "events_futurs": [{"datetime_iso": "2026-06-15T20:00:00+00:00"}],
             "events_futurs_count_total": 3},
        ],
        "tenants": [
            {"tenant_id": "uuid-B", "name": "Beta", "event_count": 1},
            {"tenant_id": "uuid-A", "name": "Alpha", "event_count": 0},
            {"tenant_id": "uuid-C", "name": "Gamma", "event_count": 3},
        ],
    }


def test_filtre_event_only_retire_les_lieux_sans_event():
    from seo.services import appliquer_options_federation
    result = appliquer_options_federation(
        _explorer_data_exemple(),
        afficher_seulement_avec_event=True,
        tri_des_lieux="alpha",
    )
    assert {p["pa_id"] for p in result["points"]} == {1, 3}
    assert {t["tenant_id"] for t in result["tenants"]} == {"uuid-B", "uuid-C"}


def test_pas_de_filtre_event_garde_tout():
    from seo.services import appliquer_options_federation
    result = appliquer_options_federation(
        _explorer_data_exemple(),
        afficher_seulement_avec_event=False,
        tri_des_lieux="alpha",
    )
    assert len(result["points"]) == 3
    assert len(result["tenants"]) == 3


def test_tri_alphabetique_ordonne_par_organisation():
    from seo.services import appliquer_options_federation
    result = appliquer_options_federation(
        _explorer_data_exemple(),
        afficher_seulement_avec_event=False,
        tri_des_lieux="alpha",
    )
    assert [p["tenant_organisation"] for p in result["points"]] == ["Alpha", "Beta", "Gamma"]


def test_tri_par_prochain_event_les_sans_event_a_la_fin():
    from seo.services import appliquer_options_federation
    result = appliquer_options_federation(
        _explorer_data_exemple(),
        afficher_seulement_avec_event=False,
        tri_des_lieux="events",
    )
    # point 3 (15 juin) avant point 1 (1 juil) ; point 2 (sans event) en dernier
    assert [p["pa_id"] for p in result["points"]] == [3, 1, 2]
```

- [ ] **2.2** Lancer → FAIL (`ImportError: cannot import name 'appliquer_options_federation'`) :
`docker exec lespass_django poetry run pytest tests/pytest/test_federation_config.py -v`

- [ ] **2.3** Implémenter la fonction (fin de `seo/services.py`) :

```python
def appliquer_options_federation(explorer_data, afficher_seulement_avec_event, tri_des_lieux):
    """
    Filtre et trie explorer_data selon les options du tenant (FederationConfiguration).
    N'agit QUE sur la carte/liste : filtre les points (PA) et les tenants.
    / Filter and sort explorer_data according to tenant FederationConfiguration options.

    LOCALISATION : seo/services.py

    Parametres / Parameters:
        explorer_data: dict {"points": [...], "tenants": [...]}
        afficher_seulement_avec_event: bool — si True, ne garde que les lieux
            avec au moins 1 event futur.
        tri_des_lieux: str — "alpha" (nom d'organisation) ou "events" (prochain event).

    Retourne / Returns: nouveau dict {"points", "tenants"}, filtre et trie.
    """
    points = list(explorer_data.get("points", []))
    tenants = list(explorer_data.get("tenants", []))

    # Filtre "event a venir seulement" / "upcoming event only" filter
    if afficher_seulement_avec_event:
        points = [p for p in points if (p.get("events_futurs_count_total") or 0) > 0]
        tenants = [t for t in tenants if (t.get("event_count") or 0) > 0]

    # Tri des points : l'ordre des cartes lieu (cote JS) suit l'ordre des points.
    # / Sort points: the JS venue-card order follows the points order.
    if tri_des_lieux == "events":
        # Par date du prochain event ; les lieux sans event finissent a la fin.
        # / By next-event date; venues without events go last.
        def cle_prochain_event(point):
            events = point.get("events_futurs") or []
            if not events:
                return "9999"
            return events[0].get("datetime_iso") or "9999"
        points.sort(key=cle_prochain_event)
    else:
        # Alphabetique par nom d'organisation du tenant.
        # / Alphabetical by tenant organisation name.
        points.sort(key=lambda p: (p.get("tenant_organisation") or "").lower())

    return {"points": points, "tenants": tenants}
```

- [ ] **2.4** Lancer → PASS (4 tests) :
`docker exec lespass_django poetry run pytest tests/pytest/test_federation_config.py -v`
- [ ] **2.5** `ruff check seo/services.py tests/pytest/test_federation_config.py` (sans `--fix` ni `format` : fichiers existants/neufs, vérifier le diff avant tout `--fix`).
- [ ] **2.6** → le mainteneur committe.

---

### Task 3 : Admin Unfold + item sidebar

**Files :**
- Modify : `Administration/admin_tenant.py` (import l.110 + classe avant `@admin.register(FederatedPlace, …)` l.3299)
- Modify : `Administration/admin/dashboard.py` (section `module_federation`, en tête des `items`, l.220)

Prérequis présents : `SingletonModelAdmin` (l.73), `WysiwygWidget`, `sanitize_textfields` (l.13),
`TenantAdminPermissionWithRequest`, `models.TextField` (utilisé par CrowdConfigAdmin), `reverse_lazy`.

- [ ] **3.1** `admin_tenant.py` — ajouter `FederationConfiguration` à la liste d'import des
modèles `BaseBillet` (l.110, à côté de `FederatedPlace`).

- [ ] **3.2** `admin_tenant.py` — ajouter la classe (juste avant `FederatedPlaceAdmin`) :

```python
@admin.register(FederationConfiguration, site=staff_admin_site)
class FederationConfigurationAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    fieldsets = (
        (_("Affichage des lieux"), {"fields": (
            "afficher_lieux_sans_adresse",
            "afficher_seulement_lieux_avec_event",
            "afficher_lieux_entrants",
            "tri_des_lieux",
        )}),
        (_("Présentation"), {"fields": ("texte_introduction",)}),
    )

    formfield_overrides = {
        models.TextField: {
            "widget": WysiwygWidget,
        }
    }

    def save_model(self, request, obj, form, change):
        # Sanitize les TextField pour eviter le XSS via WYSIWYG
        # / Sanitize TextFields to avoid XSS via WYSIWYG
        sanitize_textfields(obj)
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False
```

- [ ] **3.3** `dashboard.py` — insérer en **première** position des `items` de la section
Fédération (avant l'item « Espaces ») :

```python
{
    "title": _("Options"),
    "icon": "tune",
    "link": reverse_lazy(
        "staff_admin:BaseBillet_federationconfiguration_changelist"
    ),
    "permission": admin_permission,
},
```

- [ ] **3.4** `docker exec lespass_django poetry run python /DjangoFiles/manage.py check` → 0 issue.
- [ ] **3.5** → le mainteneur committe.

---

### Task 4 : Câblage `FederationViewset.list` + texte d'intro dans le template

**Files :**
- Modify : `BaseBillet/views.py` (méthode `FederationViewset.list`, ~l.1638-1761)
- Modify : `BaseBillet/templates/reunion/views/federation/explorer.html` (après le `<h1>`, l.63)

- [ ] **4.1** `views.py` — dans l'import local en tête de `list()` (l.1638), ajouter
`appliquer_options_federation` :

```python
        from seo.services import build_explorer_data_for_tenants, appliquer_options_federation
```

- [ ] **4.2** `views.py` — après `current_uuid = str(connection.tenant.uuid)`, lire la config :

```python
        from BaseBillet.models import FederationConfiguration
        config_federation = FederationConfiguration.get_solo()
```

- [ ] **4.3** `views.py` — remplacer le bloc `incoming_data`/`incoming_uuids` (l.1665-1668) par
une version conditionnée par l'option :

```python
        # Arretes ENTRANTES : seulement si l'option est activee.
        # / INCOMING edges: only if the option is enabled.
        incoming_uuids = set()
        if config_federation.afficher_lieux_entrants:
            incoming_data = get_seo_cache(SEOCache.FEDERATION_INCOMING) or {}
            incoming_uuids = set(
                incoming_data.get("by_tenant", {}).get(current_uuid, [])
            )
```

- [ ] **4.4** `views.py` — juste après
`explorer_data = build_explorer_data_for_tenants(sorted_uuids)` (l.1679), appliquer les
options de filtre/tri :

```python
        # Filtre "event a venir" + tri des lieux selon la config du tenant.
        # / "Upcoming event" filter + venue sort according to tenant config.
        explorer_data = appliquer_options_federation(
            explorer_data,
            afficher_seulement_avec_event=config_federation.afficher_seulement_lieux_avec_event,
            tri_des_lieux=config_federation.tri_des_lieux,
        )
```

- [ ] **4.5** `views.py` — ajouter `texte_introduction` au `template_context.update({…})` (l.1754) :

```python
            'texte_introduction': config_federation.texte_introduction,
```

- [ ] **4.6** `explorer.html` — insérer après le `<h1 class="visually-hidden">…</h1>` (l.63) :

```django
    {# Chapô éditorial optionnel (FederationConfiguration.texte_introduction). #}
    {# / Optional editorial intro. #}
    {% if texte_introduction %}
    <div class="federation-intro mx-auto my-3" style="max-width: 800px;"
         data-testid="federation-intro">{{ texte_introduction|safe }}</div>
    {% endif %}
```

- [ ] **4.7** `docker exec lespass_django poetry run python /DjangoFiles/manage.py check` → 0 issue.
- [ ] **4.8** Re-lancer la suite ciblée :
`docker exec lespass_django poetry run pytest tests/pytest/test_federation_config.py tests/pytest/test_seo_aggregate_points.py -v` → PASS.
- [ ] **4.9** → le mainteneur committe.

---

### Task 5 : Documentation + CHANGELOG

**Files :**
- Create : `A TESTER et DOCUMENTER/federation-config-options.md`
- Modify : `CHANGELOG.md` (nouvelle section en haut)

- [ ] **5.1** Créer la fiche `A TESTER` avec : ce qui a été fait (5 champs, fonction pure,
admin, sidebar, câblage), et les scénarios de test manuel :
  1. Admin → section Fédération → « Options » visible au-dessus de « Espaces ».
  2. Cocher « event à venir seulement » → un lieu sans event futur disparaît de `/federation/`.
  3. Décocher « lieux qui me fédèrent » → un voisin entrant non-réciproque disparaît.
  4. Saisir un texte d'intro WYSIWYG → s'affiche en haut de `/federation/`.
  5. Tri « par prochain événement » → ordre de la liste change.
  6. Rappel : « lieux sans adresse » sans effet tant que Phase B (JS) non faite.
- [ ] **5.2** Ajouter l'entrée `CHANGELOG.md` (format bilingue, flag migration = Oui : migration BaseBillet auto).
- [ ] **5.3** → le mainteneur committe.

---

## Self-review (coverage spec → plan)

| Exigence spec (§) | Tâche |
|---|---|
| Modèle 5 champs (§3) | Task 1 |
| Admin WYSIWYG + permissions + sanitize (§4) | Task 3 |
| Item sidebar avant Espaces (§4) | Task 3 |
| Option 3 entrants conditionnel (§5.1) | Task 4.3 |
| Option 2 event-only + tri (§5.2-5.3) | Task 2 + Task 4.4 |
| texte_introduction contexte + template (§5.4, §8) | Task 4.5, 4.6 |
| Option 1 = Phase B / JS (§6) | HORS scope (note Task 1.1) |
| Migration tenant (§7) | Task 1.2-1.3 |
| Tests DB-only (§9) | Task 2 |
| Doc + CHANGELOG (§9) | Task 5 |

Pas de placeholder. Signatures cohérentes : `appliquer_options_federation(explorer_data,
afficher_seulement_avec_event, tri_des_lieux)` identique en Task 2 (def + tests) et Task 4 (appel).
