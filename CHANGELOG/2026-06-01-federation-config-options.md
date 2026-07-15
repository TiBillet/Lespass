# Options de fédération — config singleton par tenant (Phase A)

**Date :** 2026-06-01
**Migration :** Oui

## Ce qui a été fait

Nouvelle config singleton **`FederationConfiguration`** (par tenant) pour piloter
l'affichage de la page **Réseau local** (`/federation/`), sans toucher au cache SEO
(`refresh_seo_cache`) : tout s'applique à la consommation, dans `FederationViewset.list`.

5 champs (tous effectifs, **100 % serveur — aucun JS modifié**) :
- `afficher_lieux_sans_adresse` (défaut **True**) — la vue injecte un « point sans
  coordonnées » pour chaque lieu fédéré sans adresse géocodée : il apparaît **dans la
  liste** mais **pas sur la carte** (le JS ignore déjà les marqueurs sans coords).
- `afficher_seulement_lieux_avec_event` (défaut **False**) — ne garde que les lieux avec
  ≥ 1 event futur publié.
- `afficher_lieux_entrants` (défaut **True**) — affiche aussi les lieux qui m'ont fédéré
  sans réciprocité (cache `FEDERATION_INCOMING`). Si décoché : sortants uniquement.
- `texte_introduction` (WYSIWYG Unfold) — chapô éditorial en haut de la page.
- `tri_des_lieux` (`alpha` / `events`, défaut `alpha`).

### Modifications

| Fichier | Changement |
|---|---|
| `BaseBillet/models.py` | Modèle `FederationConfiguration(SingletonModel)` |
| `BaseBillet/migrations/0215_federationconfiguration.py` | Migration (auto, tous schemas tenant) |
| `seo/services.py` | Fonction pure `appliquer_options_federation(explorer_data, …)` |
| `Administration/admin_tenant.py` | `FederationConfigurationAdmin` (WYSIWYG + sanitize + permissions) |
| `Administration/admin/dashboard.py` | Item sidebar « Options » en tête de la section Fédération |
| `BaseBillet/views.py` | `FederationViewset.list` : lit la config, applique filtre/tri/entrants/intro |
| `BaseBillet/templates/reunion/views/federation/explorer.html` | Affichage du `texte_introduction` |
| `Administration/management/commands/demo_data_v2.py` | Fixtures : 3 scénarios fédération additifs |
| `tests/pytest/test_federation_config.py` | 7 tests DB-only de la fonction pure (options 1/2/tri) |
| `tests/pytest/test_federation_view_integration.py` | 4 tests d'intégration de la vue (option entrants + rendu) |

## Tests à réaliser

> Prérequis admin : se connecter avec `admin@admin.com`. Le module Fédération doit être
> activé (`Configuration.module_federation = True`) pour voir la section dans la sidebar.

### Test 1 : l'admin apparaît au bon endroit
1. Admin → sidebar, section **Fédération**.
2. Vérifier l'item **« Options »** (icône `tune`) **au-dessus** de « Espaces » et « Assets ».
3. Cliquer : le formulaire singleton s'ouvre avec les 5 champs ; `texte_introduction` est un
   éditeur WYSIWYG.

### Test 2 : filtre « event à venir seulement »
1. Avoir au moins 2 lieux fédérés, dont 1 sans event futur.
2. Cocher **« Afficher seulement les lieux avec un événement à venir »**, enregistrer.
3. Aller sur `/federation/` → le lieu sans event futur **disparaît** de la liste et de la carte.

### Test 3 : lieux entrants
1. Avoir un voisin entrant non-réciproque (un autre tenant qui m'a ajouté, sans que je
   l'aie ajouté).
2. Décocher **« Afficher les lieux qui me fédèrent »**, enregistrer.
3. `/federation/` → ce voisin **disparaît**. Le recocher → il **réapparaît**.

### Test 4 : texte d'introduction
1. Saisir du texte (gras, lien) dans **« Texte d'introduction »**, enregistrer.
2. `/federation/` → le chapô s'affiche en haut (sous le titre), mise en forme respectée.
3. Vérifier qu'un essai d'injection `<script>` est neutralisé (sanitize au save).

### Test 5 : tri des lieux
1. Tri **« Par prochain événement »**, enregistrer → l'ordre de la liste suit la date du
   prochain event (lieux sans event à la fin).
2. Tri **« Alphabétique »** → ordre par nom d'organisation.

### Test 6 : lieux sans adresse (option 1)
1. `Lespass` fédère `Le Réseau des lieux en réseau`, dont l'adresse n'a pas de coordonnées
   (cf. fixtures ci-dessous).
2. Cocher **« Afficher les lieux sans adresse »** (défaut activé) → `Le Réseau` apparaît
   **dans la liste** de `/federation/` mais **sans marqueur** sur la carte.
3. Décocher → `Le Réseau` disparaît de la liste.

## Scénarios dans les fixtures (`demo_data_v2`)

Le réseau de démo a été enrichi (additif) pour exercer chaque option depuis `Lespass` :

| Scénario | Donnée |
|---|---|
| Lieu sans adresse (opt. 1) + sans event (opt. 2) | `Lespass` fédère `Le Réseau des lieux en réseau` (adresse sans lat/lng, `events: []`) |
| Voisin entrant non-réciproque (opt. 3) | `Le Cœur en or` fédère `Lespass` (Lespass ne le fédère pas) |

⚠️ **Pour appliquer ces fixtures** : `PostalAddress.get_or_create` ne met pas à jour une
adresse existante. Reseed avec **`--flush`** pour que la suppression des coords du Réseau
prenne effet :
```bash
docker exec lespass_django poetry run python manage.py demo_data_v2 --flush
```
Puis **relancer les E2E** `test_explorer_ux_pills_tags` pour vérifier que `/explorer/`
ROOT n'est pas régressé (le Réseau perd son marqueur carte).

## Vérifications en base / commandes

```bash
# Le singleton se crée au premier accès (get_solo). Vérifier les défauts :
docker exec lespass_django poetry run python manage.py shell -c \
"from django_tenants.utils import tenant_context; from Customers.models import Client; \
from BaseBillet.models import FederationConfiguration; \
t=Client.objects.exclude(schema_name='public').first(); \
[print(FederationConfiguration.get_solo().__dict__) for _ in [0] if tenant_context(t).__enter__() or True]"
```

## Tests automatisés

```bash
KEY=$(docker exec -e TEST=1 lespass_django poetry run python manage.py test_api_key | tail -1)
docker exec -e TEST=1 -e API_KEY="$KEY" lespass_django poetry run pytest \
  tests/pytest/test_federation_config.py \
  tests/pytest/test_federation_view_integration.py -v
```

> Note : pour lancer pytest **depuis le conteneur**, il faut injecter `API_KEY` (sinon la
> fixture `conftest.py:_inject_cli_env` tente un `docker exec` absent dans le conteneur).

## Compatibilité

- **Additif** : aucune modif de `refresh_seo_cache` ni du cache SEO. Le `/explorer/`
  public ROOT n'est pas affecté (la config est lue uniquement dans `FederationViewset.list`).
- Défauts choisis pour **reproduire le comportement actuel** (entrants affichés, pas de
  filtre event), sauf `afficher_lieux_sans_adresse=True` qui reste neutre jusqu'à la Phase B.
