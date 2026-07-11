# Pages : blocs IFRAME (contenu intégré libre) + PARTENAIRES

## Ce qui a été fait

Deux nouveaux blocs pour l'app `pages`, validés en pytest **et** dans Chrome (tenant `lespass`).

### Modifications
| Fichier | Changement |
|---|---|
| `pages/models.py` | +types `IFRAME`/`PARTENAIRES`, +`hauteur_px` (Bloc), +`lien_url` (ImageGalerie), validator `valider_url_sans_schema_dangereux` |
| `root_billet/models.py` | +`domaines_embed_autorises` (whitelist ROOT, SHARED) |
| `pages/templatetags/pages_tags.py` | tag `iframe_libre` + helper `_domaines_embed_autorises` |
| `pages/admin.py` | conditional_fields (embed_url+hauteur_px), get_inlines +PARTENAIRES, inline +`lien_url` |
| `Administration/admin_tenant.py` | `RootConfigurationAdmin` (superadmin strict, 1 seul champ, `cache.clear()`) |
| `Administration/admin/dashboard.py` | item « Domaines iframe autorisés » dans « Configuration racine » |
| `pages/templates/pages/classic/partials/bloc_iframe.html`, `bloc_partenaires.html` | nouveaux |
| `pages/templates/pages/classic/partials/bloc_galerie.html` | image cliquable si `lien_url` |
| `pages/static/pages/css/tb-blocs.css` | `.tb-iframe`, `.tb-partenaires` (grayscale + hover) |

## Migration
- **Nécessaire :** Oui. `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`
- Migrations : `pages/0002_iframe_partenaires`, `root_billet/0007_iframe_partenaires`.

## Tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_pages.py -q   # 42 passed
```

## Tests manuels (Chrome) — déjà validés en session

### Test 1 — Whitelist ROOT (superadmin uniquement)
1. Sidebar → **Configuration racine → Domaines iframe autorisés** (visible seulement si superadmin).
2. La fiche n'expose **que** `domaines_embed_autorises` (jamais les clés Stripe/Fedow).
3. Saisir un domaine par ligne (ex. `newsletter.ghost.io`, `www.openstreetmap.org`), enregistrer.
   → `cache.clear()` : la whitelist est immédiatement effective sur tous les tenants.
4. Vérifier qu'un admin **tenant non-superadmin** ne voit PAS cet item.

### Test 2 — Bloc IFRAME
1. Blocs → Ajouter → type **« Contenu intégré libre »**.
   → seuls `Page`, `Titre`, `URL à intégrer`, `Hauteur de l'iframe (600)` s'affichent (conditional_fields).
2. URL d'un hôte **whitelisté** en https (ex. `https://www.openstreetmap.org/export/embed.html?bbox=...`).
   → rendu public : l'`<iframe>` s'affiche à la hauteur choisie.
3. Changer l'URL vers un hôte **non whitelisté** (`https://evil.example/x`).
   → rendu public : message « Ce contenu ne peut pas être intégré (hôte non autorisé). », **pas d'iframe**.
4. URL en **http://** (hôte pourtant whitelisté) → rien (https obligatoire).

### Test 3 — Bloc PARTENAIRES
1. Blocs → Ajouter → type **« Partenaires »**, enregistrer une 1re fois.
   → l'inline **« Images de galerie »** apparaît, avec la colonne **« Lien de l'image »**.
2. Ajouter 2-3 logos ; renseigner `lien_url` sur certains, laisser vide sur un autre.
3. Rendu public : bande de logos (grille responsive), **grisés au repos, couleur au survol**.
   - Logo **avec** lien → `<a target="_blank" rel="noopener">` (ouvre un nouvel onglet).
   - Logo **sans** lien → `<img>` non cliquable.

### Test 4 — Sécurité XSS `lien_url`
- Saisir `lien_url = javascript:alert(1)` sur une image → **refusé** au `full_clean()` (validator modèle).

## Vérifications en base (optionnel)
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import schema_context
with schema_context('lespass'):
    from pages.models import Bloc
    for b in Bloc.objects.filter(type_bloc__in=['IFRAME','PARTENAIRES']):
        print(b.type_bloc, b.titre, repr(b.embed_url), b.hauteur_px)
"
```

## Compatibilité / notes
- Skin **classic** seulement ; `faire_festival` retombe dessus via `select_template` (fallback auto).
- `embed_url` partagé EMBED/IFRAME : deux tags distincts (`embed_iframe` = vidéo whitelist codée ;
  `iframe_libre` = whitelist ROOT). Ne pas les confondre.
- **Ne jamais whitelister** un domaine de la plateforme/tenant (avec `allow-same-origin`, le sandbox
  tomberait).

## Bloc NEWSLETTER (Ghost) — ajout
Type **`NEWSLETTER`** : formulaire d'inscription Ghost.
- **Script vendorisé** : `pages/static/pages/vendor/ghost/signup-form.min.js` (zéro CDN, cf. `SOURCE.txt`).
  Le script lit ses `data-*` et injecte lui-même un `<iframe>` vers l'instance Ghost.
- **Pas de whitelist** (décision mainteneur) : le script est local, il ne fait que poster vers
  l'instance Ghost configurée (`embed_url` = `data-site`).
- Champs : `embed_url` (data-site, ex. `https://ghost.tibillet.coop/`), `titre` (data-title),
  `sous_titre` (data-description). Couleurs/locale = défauts TiBillet dans le template.
- **Test manuel** : sur l'accueil `lespass`, section « Les news de TiBillet » → fond noir, bouton rose
  « S'abonner », champ email. Validé dans Chrome (aucune erreur console).
- **Migration** : `pages/0003_bloc_newsletter` (AlterField choices). Penser à `collectstatic` pour servir
  le script vendorisé.

## Fixture de démo (FAIT)
`pages/management/commands/charger_site_lespass.py` intègre les blocs sur la landing `lespass` :
- **Bloc IFRAME** « Le plan d'accès » (carte OpenStreetMap, hauteur 420) dans la section infos pratiques.
- **Bloc PARTENAIRES** « Ils nous soutiennent » avec 6 logos `static/contributeurs/` (France Tiers-Lieux,
  CoopCircuits, JetBrains, France 2030 = cliquables ; Circa, Demeter = non cliquables).
- **Bloc NEWSLETTER** « Les news de TiBillet » (data-site `https://ghost.tibillet.coop/`).
- La commande **autorise l'hôte OSM** dans la whitelist ROOT (`_whitelister_domaine_embed`, idempotent) —
  au chargement des fixtures (`demo_data_v2`), la whitelist est donc peuplée avant le rendu.
- **SVG exclus** : `StdImageField`/Pillow ne redimensionne pas le SVG → seuls PNG/JPG.

Relancer la fixture :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py charger_site_lespass --schema=lespass
```

## Note session
Les blocs de démo temporaires créés à la main sur la page « À propos » pendant la validation ont été
**supprimés**. La démo propre vit désormais sur l'**accueil** de `lespass` via la fixture ci-dessus.
