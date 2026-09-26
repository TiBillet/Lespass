# LaBoutik : icônes Material Symbols locales, FontAwesome supprimé / LaBoutik: local Material Symbols icons, FontAwesome removed

**Date :** 2026-09-25
**Migration :** **Oui** — `laboutik/migrations/0006_icones_fontawesome_vers_material.py` (données)
**Commit :** non committé au moment de la rédaction / not committed yet

## Resume / Summary

**Quoi / What :**
- La caisse n'utilise plus FontAwesome. Toutes ses icônes sont des Material Symbols :
  `<span class="material-symbols-outlined" aria-hidden="true">sports_bar</span>`.
- La police Material est **locale** : celle que fournit django-unfold
  (`static/unfold/fonts/material-symbols/`). Plus d'appel à Google Fonts.
- Le sélecteur d'icônes de l'admin (`ICON_POS`) propose des noms Material
  (98 entrées, un nom distinct par entrée).
- Une migration de données convertit les noms FontAwesome déjà stockés.
/ The POS uses local Material Symbols only; the admin picker offers Material names;
  a data migration converts stored FontAwesome names.

**Pourquoi / Why :**
- La maquette n'utilise pas FontAwesome ; deux systèmes d'icônes cohabitaient.
- La police Material venait de Google Fonts (dépendance réseau au démarrage de la caisse),
  en version variable complète dont aucune variation n'était utilisée.
- FontAwesome pesait 2,7 Mo de polices.
/ One icon system, no network dependency, 2.7 MB less.

**Couverture de la police d'Unfold :** 4137 icônes sur les 4299 de la liste Google actuelle
(164 icônes récentes absentes). Toutes celles utilisées par la caisse, l'admin et la
migration sont présentes : c'est vérifié par `tests/pytest/test_laboutik_icones.py`.

**Piège évité / Pitfall :** des noms Material commencent par « fa » (`fastfood`, `favorite`).
La migration détecte FontAwesome sur le préfixe **`fa-`** (avec tiret), jamais sur « fa ».

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/migrations/0006_icones_fontawesome_vers_material.py` | **Nouveau** : convertit `CategorieProduct.icon`, `Product.icon_pos`, `PointDeVente.icon`, `CategorieTable.icon` (rien dans le schéma public) |
| `Administration/admin/products.py` | `ICON_POS` en noms Material |
| `Administration/templates/admin/widgets/icon_picker.html` | Icônes Material, plus de feuille FontAwesome ; radios masqués en style inline |
| `Administration/templates/admin/widgets/palette_picker.html` | Radios masqués en style inline (`.sr-only` venait de FontAwesome) |
| `Administration/templates/admin/cloture/rapport_before.html`, `export_csv_comptable_detail_form.html` | Icônes FA (invisibles) → Material |
| `laboutik/templates/laboutik/base.html` | Police locale d'Unfold ; FontAwesome et Google Fonts retirés |
| `laboutik/static/css/components.css` | Classe `.material-symbols-outlined`, taille par défaut, `.sr-only` |
| `laboutik/static/css/addition.css`, `header.css`, `modele00.css`, `ventes.css` | Sélecteurs `i` / `.fas` → `.material-symbols-outlined` |
| `laboutik/templates/cotton/*.html`, `laboutik/templates/laboutik/partial/*.html`, `laboutik/static/js/addition.js` | 57 icônes FA → Material ; branches `icone_type == "fa"` supprimées |
| `laboutik/views.py` | Icônes par défaut en Material (`category`, `apps`, `calendar_month`, `confirmation_number`) |
| `laboutik/management/commands/create_test_pos_data.py` | Données de démo en noms Material |
| `fedow_core/signals.py` | Produits de recharge créés avec des icônes Material |
| `laboutik/static/css/all_fontawesome-free-5-11-2.css`, `laboutik/static/css/webfonts/` | **Supprimés** |
| `tests/pytest/test_laboutik_icones.py` | **Nouveau** : 11 tests (police, `ICON_POS`, gabarits, migration) |
| `tests/pytest/test_pos_views_data.py` | Attentes en noms Material |

### Migration
- **Migration necessaire / Migration required:** **Oui**
- `laboutik.0006_icones_fontawesome_vers_material` (RunPython, sens inverse = rien)
```bash
docker exec lespass_django poetry run python manage.py migrate_schemas
docker exec lespass_django poetry run python manage.py collectstatic --noinput
```
Les copies FontAwesome de `www/static` (sortie de `collectstatic`) ont été supprimées en dev ;
en production, `collectstatic` ne les supprime pas : les retirer à la main ou lancer
`collectstatic --clear`.

## Tests a realiser / How to test

### Automatiques
```bash
poetry run pytest tests/pytest/test_laboutik_icones.py tests/pytest/test_pos_views_data.py -v
```

### Vérification en base après migration
```bash
docker exec lespass_django poetry run python manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import Product, CategorieProduct
from laboutik.models import PointDeVente, CategorieTable
for t in Client.objects.exclude(schema_name='public'):
    with tenant_context(t):
        for M, f in [(CategorieProduct,'icon'), (Product,'icon_pos'), (PointDeVente,'icon'), (CategorieTable,'icon')]:
            reste = list(M.objects.filter(**{f+'__contains': 'fa-'}).values_list(f, flat=True))
            if reste: print(t.schema_name, M.__name__, reste)
"
```
Attendu : rien ne s'affiche.

### Test 1 : Caisse
1. Ouvrir un point de vente : icônes de l'en-tête, des catégories, des tuiles, du ticket
   (corbeille, panier vide, « Check carte ») affichées en **pictogrammes**, jamais en texte
   (« sports_bar » écrit en toutes lettres = police non chargée).
2. Onglet Réseau du navigateur : aucune requête vers `fonts.googleapis.com` ni vers `fa-solid-900`.
3. Menu burger, liste des points de vente : icônes présentes, coche verte sur le PV courant.

### Test 2 : Admin
1. Admin → un produit POS → sélecteur d'icônes : grille d'icônes Material, **aucun bouton
   radio visible**, l'icône choisie entourée en bleu.
2. Même vérification pour le sélecteur de palette (pastilles « Aa »).
3. Choisir une icône, enregistrer, recharger la caisse : la tuile affiche cette icône.
4. Admin → Clôtures → un rapport : icônes CSV / PDF / Excel / FEC visibles.
