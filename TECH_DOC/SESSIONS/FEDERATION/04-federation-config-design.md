# Design — `FederationConfiguration` (singleton tenant des options d'affichage du réseau)

> **Hub :** [INDEX.md](INDEX.md) si présent, sinon docs `01-…`, `02-…`, `03-…` de ce dossier.
> **Date :** 2026-06-01
> **Contraintes projet :** aucune opération git de l'assistant (le mainteneur committe) ·
> pas de `makemessages`/`compilemessages` auto · règle des 3 fichiers avant
> `manage.py check` + tests · serveur tenu par le mainteneur dans byobu ·
> **s'arrêter et demander avant de toucher au JS**.

---

## 1. Contexte et objectif

L'app d'exploration de réseau (`seo/` + consommation côté tenant dans `BaseBillet`)
affiche, sur la page **`/federation/`** d'un tenant, une carte + une liste des lieux
de son réseau coopératif local. Les données viennent du cache SEO pré-calculé
(`refresh_seo_cache`, toutes les 4 h) et sont assemblées à la consommation par
`FederationViewset.list` (`BaseBillet/views.py`).

Aujourd'hui, le comportement d'affichage est **figé dans le code** :

- la fédération est **bidirectionnelle en dur** : `outgoing | incoming`
  (`views.py:1672`, `incoming` = cache `FEDERATION_INCOMING`) ;
- la liste n'affiche que les lieux **ayant au moins une adresse géocodée**
  (le JS `explorer.js` construit les cartes lieu à partir des `points`) ;
- aucun filtre « event à venir », aucun texte d'introduction, aucun tri configurable.

**Objectif :** rendre ces comportements configurables **par tenant**, via une nouvelle
config singleton visible dans l'admin section **Fédération**, au-dessus de
« Espaces » (`FederatedPlace`) et « Assets » (`AssetFedowPublic`).

## 2. Décisions de cadrage (validées)

| Décision | Choix |
|---|---|
| Portée | **Par tenant** — modèle dans le schema tenant (comme `Configuration`). |
| Périmètre fonctionnel | **Carte + liste `/federation/`** uniquement. Le `/explorer/` public ROOT n'est pas affecté. |
| Impact cache | **Additif** — aucune modification de `refresh_seo_cache`. Tout s'applique à la consommation. |
| Réciprocité (option 3) | **Booléen simple** (pas de mode 3-valeurs en v1). |
| Texte d'introduction | Widget **WYSIWYG Unfold** (`unfold.contrib.forms.widgets.WysiwygWidget`). |

## 3. Le modèle — `BaseBillet/models.py`

`class FederationConfiguration(SingletonModel)` (django-solo), tenant-scoped.

| Champ | Type | Défaut | Effet sur `/federation/` |
|---|---|---|---|
| `afficher_lieux_sans_adresse` | `BooleanField` | `True` | Si `True` : la liste inclut aussi les lieux du réseau **sans** adresse géocodée (absents de la carte). **Nécessite une modif `explorer.js`** (cf. §6). |
| `afficher_seulement_lieux_avec_event` | `BooleanField` | `False` | Si `True` : ne garde que les lieux ayant ≥ 1 event futur publié (`events_futurs_count_total > 0`). |
| `afficher_lieux_entrants` | `BooleanField` | `True` | Toggle de `incoming_uuids` (`FEDERATION_INCOMING`). Si `False` : carte/liste **sortantes uniquement**. |
| `texte_introduction` | `TextField(blank=True, null=True)` rendu WYSIWYG | vide | Chapô éditorial en haut de la page. Rendu `\|safe` (contenu admin, **sanitizé** via `sanitize_textfields`). |
| `tri_des_lieux` | `CharField(choices=…)` | `alpha` | Ordre de la liste : `alpha` (alphabétique) ou `events` (par prochain event). |

Constantes de choix dans le modèle (FALC, verbeux) :

```python
TRI_ALPHABETIQUE = "alpha"
TRI_EVENTS_A_VENIR = "events"
TRI_CHOICES = [
    (TRI_ALPHABETIQUE, _("Alphabétique")),
    (TRI_EVENTS_A_VENIR, _("Par prochain événement")),
]
```

`Meta.verbose_name = _("Options de fédération")`. Tous les `help_text` en `_()`,
commentaires bilingues FR/EN.

## 4. L'admin — `Administration/admin_tenant.py`

Patron de référence : **`CrowdConfigAdmin`** (`admin_tenant.py:4019`).

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

    formfield_overrides = {models.TextField: {"widget": WysiwygWidget}}

    def save_model(self, request, obj, form, change):
        sanitize_textfields(obj)  # anti-XSS sur le WYSIWYG
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
    def has_delete_permission(self, request, obj=None):
        return False
```

**Sidebar** (`Administration/admin/dashboard.py`, section `module_federation`, l.214-239) :
ajouter en **tête** des `items` (avant « Espaces ») :

```python
{
    "title": _("Options"),
    "icon": "tune",
    "link": reverse_lazy("staff_admin:BaseBillet_federationconfiguration_changelist"),
    "permission": admin_permission,
},
```

## 5. Câblage de la vue — `BaseBillet/views.py`, `FederationViewset.list`

Lecture `config_federation = FederationConfiguration.get_solo()` puis :

1. **Option 3** (`afficher_lieux_entrants`) : appliqué **avant** `build_explorer_data_for_tenants` —
   si `False`, ne pas unir `incoming_uuids` (`all_uuids = outgoing | {current}` seulement).
2. **Option 2** (`afficher_seulement_lieux_avec_event`) : appliqué **après** —
   filtrer `explorer_data["points"]` sur `events_futurs_count_total > 0` et
   `explorer_data["tenants"]` sur `event_count > 0`.
3. **`tri_des_lieux`** : trier `explorer_data["points"]` en Python
   (`alpha` → `tenant_organisation` ; `events` → date du prochain event).
   L'ordre `for…in` de `buildLieuCardsFromPAs` (clés UUID = strings) **préserve**
   l'ordre d'insertion, donc l'ordre des cartes lieu suit l'ordre des `points`.
4. **`texte_introduction`** : passé au contexte template.
5. **Option 1** (`afficher_lieux_sans_adresse`) : cf. §6 — partie JS.

Le ROOT `/explorer/` (`seo/views.py`, via `build_explorer_data()`) **n'est pas touché**.

## 6. Option 1 (lieux sans adresse) — finalement 100 % serveur, zéro JS

À l'analyse de `explorer.js`, deux faits changent la donne :

- `addMarkers` (l.905) fait déjà `if (isNaN(lat) || isNaN(lng)) continue;` → un point sans
  coordonnées **n'a pas de marqueur** carte, sans aucune modif.
- `filterPAsByTextAndTag` (l.269) ne filtre **pas** sur les coordonnées → un point sans
  coords **apparaît dans la liste** (`buildLieuCardsFromPAs` itère sur les points visibles).

➡️ L'option 1 se fait donc **côté serveur** (principe djc « logique serveur > JS ») :
quand `afficher_lieux_sans_adresse=True`, `appliquer_options_federation` **injecte un
« point sans coordonnées »** (`latitude/longitude = None`, `is_addressless = True`) pour
chaque tenant présent dans `tenants` mais absent de `points`. Le JS l'affiche en liste et
ignore son marqueur — **aucune modification JS nécessaire**.

**Conséquence : pas de Phase B JS.** Tout (options 1 à 5) est livré côté serveur,
intégralement testable en pytch.

## 7. Migration & création

Migration tenant `BaseBillet`, appliquée via
`migrate_schemas --executor=multiprocessing`. `get_solo()` auto-crée la ligne au premier
accès — **pas de data migration**.

## 8. Template — `BaseBillet/templates/reunion/views/federation/explorer.html`

Insertion du `texte_introduction` après le `<h1 class="visually-hidden">` (l.63) et avant
le message d'état vide :

```django
{% if texte_introduction %}
<div class="federation-intro mx-auto my-3" style="max-width: 800px;"
     data-testid="federation-intro">{{ texte_introduction|safe }}</div>
{% endif %}
```

## 9. Conventions & vérifications

- **i18n** : libellés/help_text en FR (`_()`), source française. Pas de `makemessages` auto.
- **FALC** : commentaires bilingues FR/EN, noms verbeux.
- **a11y / tests** : `data-testid` sur les éléments touchés.
- **Tests** : test pytest DB-only — vérifier que chaque flag réduit/réordonne bien
  `explorer_data` (appel `FederationViewset.list` en `tenant_context`). E2E non requis
  pour la Phase A (pas de JS) ; un E2E ciblera la Phase B.
- **Doc** : fiche dans `A TESTER et DOCUMENTER/`, entrée `CHANGELOG.md`.

## 10. Décisions tranchées

- **Option 1** : finalement **côté serveur, zéro JS** (cf. §6) — pas de Phase B.
- **Niveau de test** : **pytch** (unitaire fonction pure + intégration vue), pas d'E2E.
- **Données de scénario** : enrichissement **additif** de `demo_data_v2` (cf. §11).

## 11. Scénarios dans les fixtures (`demo_data_v2`)

Pour que chaque option soit exerçable depuis `Lespass` `/federation/`, le réseau de démo
est enrichi additivement :

| Scénario | Fixture |
|---|---|
| Lieu **sans adresse** (option 1) + **sans event** (option 2) | `Lespass` fédère `Le Réseau des lieux en réseau` ; l'adresse du Réseau perd ses `latitude/longitude` (et `events: []`). |
| Voisin **entrant non-réciproque** (option 3) | `Le Cœur en or` fédère `Lespass` (sans réciprocité). |

⚠️ **Application des fixtures** : `PostalAddress.get_or_create(defaults=…)` ne met pas à
jour une adresse existante. Pour que la suppression des coords du Réseau prenne effet, le
mainteneur doit **reseed avec `--flush`**. Relancer ensuite les E2E
(`test_explorer_ux_pills_tags`) pour confirmer que `/explorer/` ROOT n'est pas régressé
(le Réseau perd son marqueur carte).
