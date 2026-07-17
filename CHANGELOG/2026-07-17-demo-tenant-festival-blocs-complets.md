# Fixture de démo : tenant « Festival » et couverture complète des blocs / Demo fixture: "Festival" tenant and full block coverage

**Date :** 2026-07-17
**Migration :** Non — mais un **flush complet est OBLIGATOIRE** (`demo_data_v2`), le schéma du tenant étant dérivé de son nom.

## Resume / Summary

**Quoi / What :**
Le tenant de démo `chantefrein` devient `festival` (schéma, domaine, nom, textes). Son site vitrine, jusqu'ici calqué sur un festival réel (le Faire Festival, Toulouse), devient un festival générique et fictif. Le seed du skin `faire_festival` couvre désormais **les 19 types de blocs** du catalogue, contre 10 auparavant.
/ The `chantefrein` demo tenant becomes `festival` (schema, domain, name, texts). Its showcase site, previously modelled on a real festival, becomes a generic fictional one. The `faire_festival` skin seed now covers **all 19 block types**, up from 10.

**Pourquoi / Why :**
Le nom du tenant devait refléter le skin qu'il démontre. La démo mettait en scène une organisation réelle, ce qui n'a pas lieu d'être dans une fixture. Enfin, chaque tenant de démonstration doit exposer tous les blocs pour permettre la revue visuelle d'un skin.
/ The tenant name had to reflect the skin it demonstrates. The demo depicted a real organisation, which does not belong in a fixture. Finally, each demo tenant must expose every block type to allow a skin's visual review.

Le schéma et le domaine sont dérivés automatiquement (`schema = slugify(name)`, `domain = f"{schema}.{domain_base}"`) : renommer le tenant suffit à obtenir `festival` / `festival.tibillet.coop`.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `Administration/management/commands/demo_data_v2.py` | Tenant renommé + textes génériques ; fédération de Lespass mise à jour ; **suppression d'un copier-collé de 53 lignes** |
| `Administration/management/commands/demo_data.py` · `demo_data_minimal.py` | `name = "Festival"` |
| `pages/management/commands/charger_demo_faire_festival.py` | Textes génériques ; **9 blocs ajoutés** ; helper `_whitelister_domaine_embed` |
| `pages/management/commands/charger_demo_blocs.py` | `--schema` par défaut |
| `Administration/fixtures/demo_logos/chantefrein.png` | Renommé `festival.png` (le logo est cherché par `schema_name`) |
| `docker-compose.yml` · `docker-compose-laboutik-V1.yml` · `docker-compose.pre-prod.yml` · `docker-compose.v1.pre-prod.yml` | `extra_hosts` et routes Traefik |
| `env_example` | `ADMIN_LABOUTIK` → `admin+fest@admin.com` |
| 7 fichiers de `tests/` | `chantefrein` → `festival` |

### Bug corrigé au passage / Bug fixed along the way

Un bloc de 53 lignes avait été copié-collé à la fin de `_aligner_wallets_clients_sur_fedow` : les deux appels de seed **et** les deux définitions de méthode. Conséquences : les sites vitrines étaient générés **deux fois** par flush (toutes les images réuploadées), et les `def` dupliquées masquaient silencieusement les originales — modifier ces dernières n'avait aucun effet.

### Couverture des blocs / Block coverage

| Tenant | Skin | Avant | Après |
|---|---|---|---|
| `lespass` | classic | 19 / 19 | 19 / 19 (inchangé) |
| `festival` | faire_festival | 10 / 19 | **19 / 19** |

Blocs ajoutés : `TEMOIGNAGE`, `GALERIE`, `LISTE_SOUS_PAGES` (page « Le Festival ») ; `MARKDOWN` (« Notre démarche ») ; `EMBED`, `IFRAME` (« Infos pratiques ») ; `EVENEMENTS`, `PARTENAIRES`, `NEWSLETTER` (accueil).

**Décision assumée :** le skin `faire_festival` ne fournit un gabarit que pour 11 des 19 types. Les 8 autres retombent sur le socle `classic` via `gabarit_skin()`. C'est **voulu** : la démo rend visible ce qui reste à habiller dans le skin.

---

## Comment tester (a la main) / Manual test

### Prérequis — le flush est obligatoire

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py demo_data_v2
```

Sans lui, le tenant `festival` n'existe pas : le site reste sur `chantefrein` et **7 fichiers de tests échouent** avec `Client.DoesNotExist: schema_name='festival'`.

### À faire dans le `.env` local (non versionné)

`ADMIN_LABOUTIK='jturbeaux+cf@pm.me'` → `jturbeaux+fest@pm.me`.
Le `+cf` désignait Chantefrein ; le tenant a maintenant `+fest`. Sans ce changement, la caisse LaBoutik V1 branchée sur ce tenant ne s'ouvrira plus.

### Test 1 — le tenant

1. `https://festival.tibillet.localhost/` répond, logo présent.
2. Dans l'admin, le lieu s'appelle « Festival », adresse « Le parc du festival », Villeurbanne.
3. Ses 4 events : Concert d'ouverture, Atelier sérigraphie, Point Coop' du festival, AG Ordinaire du festival.

### Test 2 — la fédération depuis Lespass

1. `https://lespass.tibillet.localhost/event/` : les events de Festival apparaissent.
2. Les 2 events tagués « Réunion » n'apparaissent **pas** (filtre `exclude_tags`).
3. Sur la carte, le point est à Villeurbanne.

### Test 3 — les 19 blocs (revue visuelle du skin)

Parcourir les 4 pages de `https://festival.tibillet.localhost/` :

| Page | Blocs à voir |
|---|---|
| `/` | HERO, VIDEO_TEXTE + 3 CARTE, CTA, IMAGE, 3 CARTE, **EVENEMENTS**, **PARTENAIRES**, **NEWSLETTER** |
| `/le-faire-festival/` | IMAGE, PARAGRAPHE, 3 IMAGE_TEXTE, **GALERIE**, **TEMOIGNAGE**, **LISTE_SOUS_PAGES** |
| `/notre-demarche/` | IMAGE, PARAGRAPHE, VIDEO_TEXTE, **MARKDOWN** |
| `/infos-pratiques/` | INFOS + CARTE_LEAFLET, IMAGE, 6 FAQ, **EMBED**, **IFRAME** |

Points de vigilance :
- **LISTE_SOUS_PAGES** doit lister « Notre démarche » (et non afficher l'état vide).
- **IFRAME** doit afficher le plan OpenStreetMap. S'il est vide, l'hôte n'est pas dans la whitelist ROOT (`Configuration racine → Domaines iframe autorisés`).
- Les 8 blocs en fallback classic détonneront visuellement dans le skin festival : **c'est attendu**, c'est la feuille de route de ce qu'il reste à habiller.

### Vérifs DB

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
from pages.models import Page, Bloc
t = Client.objects.get(schema_name='festival')
with tenant_context(t):
    vus = {b.type_bloc for p in Page.objects.all() for b in p.blocs.all()}
    print('Types couverts :', len(vus), '/', len(Bloc.TYPE_BLOC_CHOICES))
    print('Manquants :', sorted({c[0] for c in Bloc.TYPE_BLOC_CHOICES} - vus) or 'AUCUN')
"
```

### Tests automatisés

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_fedow_core.py \
  /DjangoFiles/tests/pytest/test_federation_tags_semantique.py \
  /DjangoFiles/tests/pytest/test_verify_transactions.py \
  /DjangoFiles/tests/pytest/test_impression_securite_websocket.py -q
```

Puis les E2E : `tests/e2e/test_skin_faire_festival_navigation.py` (cible `festival.{DOMAIN}`) et `tests/e2e/test_explorer_adresse_dupliquee.py`.
