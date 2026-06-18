# Admin clé API (asset cadeau) + nettoyage assets BDG + UUID asset

## Ce qui a été fait

Remontée utilisateur : sur **Admin → Outils externes → Clé API**, changer l'asset
cadeau (`gift_asset`) d'une clé semblait « ne rien faire » et provoquait une erreur
sur le nouvel asset.

### Diagnostic
- La **sauvegarde fonctionnait** déjà (la valeur `gift_asset` change bien en base —
  vérifié par reproduction directe du `save_model` de l'admin).
- L'erreur venait des **icônes crayon / œil / +** affichées à côté du menu déroulant
  (`RelatedFieldWidgetWrapper`). Elles ouvrent l'admin des assets, qui **masque
  volontairement les assets de type badgeuse (BDG)** (`AssetAdmin.get_queryset`
  exclut BDG et SUB). En cliquant dessus pour inspecter le nouvel asset → erreur
  « cet asset n'existe pas ».
- Les assets « [DEMO] Biere / Soft / Sandwich » (catégorie BDG) visibles dans le menu
  provenaient de la fixture `_demo_data_v2_ventes.py` qui créait ces **ventes de
  comptoir** en `Product.BADGE` (mauvaise catégorie). Un signal post_save transforme
  tout produit BADGE en asset BDG.

### Modifications
| Fichier | Changement |
|---|---|
| `Administration/admin_tenant.py` | `ExternalApiKeyAdmin.formfield_for_foreignkey` : queryset `gift_asset` restreint aux assets `origin = tenant courant` (étanchéité multi-tenant) |
| `Administration/admin_tenant.py` | `ExternalApiKeyAdmin.formfield_for_dbfield` : retire les icônes add/change/delete/view sur `gift_asset` |
| `Administration/admin_tenant.py` | `AssetAdmin` : `uuid` ajouté en `readonly_fields` + `fields` (affiché en lecture seule sur la fiche) |
| `Administration/management/commands/_demo_data_v2_ventes.py` | Biere/Soft/Sandwich : `Product.BADGE` → `Product.NONE` |
| Base dev (one-shot) | 3 assets BDG `[DEMO] *` supprimés + 3 produits démo repassés en `NONE` |

## Tests à réaliser

### Test 1 : changer l'asset cadeau d'une clé API (le bug d'origine)
1. Admin → Outils externes → Clé API → ouvrir une clé existante.
2. Champ **Wallet refill (asset)** : vérifier qu'**aucune icône** crayon / œil / + n'apparaît
   plus à droite du menu déroulant.
3. Choisir un asset (ex : MTemps), **Enregistrer**.
4. Rouvrir la clé : l'asset choisi est bien mémorisé, **aucune erreur**.

### Test 2 : le menu n'affiche plus les assets badgeuse démo
1. Sur la même page, dérouler **Wallet refill (asset)**.
2. Vérifier qu'il n'y a **plus** de « [DEMO] Biere / Soft / Sandwich ».
3. Seuls restent les assets rechargeables légitimes (cadeau TNF, temps TIM, fidélité FID,
   et d'éventuelles vraies badgeuses BDG si un lieu en utilise encore).

### Test 3 bis : étanchéité multi-tenant (le plus important)
1. Sur la page clé API d'un lieu A, dérouler **Wallet refill (asset)**.
2. Vérifier qu'**aucun asset d'un autre lieu** n'apparaît — seuls les assets cadeau/temps/
   fidélité/badge **créés par le lieu A** (origine = lieu courant) sont listés.
3. (Optionnel, technique) Tenter de forcer un POST avec l'UUID d'un asset d'un autre lieu →
   doit être **rejeté en validation** (« choix invalide »), pas enregistré.

### Test 3 : UUID lisible sur la fiche asset
1. Admin → section **Fedow** (visible si `module_monnaie_locale` actif) → Assets.
2. Ouvrir un asset (ex : MTemps).
3. Vérifier que le champ **Uuid** est affiché en **lecture seule** en haut de la fiche.

### Vérification en base (optionnel)
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from fedow_public.models import AssetFedowPublic
print('Assets BDG restants :', AssetFedowPublic.objects.filter(category='BDG').count())  # attendu : 0
"
```

## Compatibilité
- `BDG` reste une catégorie rechargeable valide côté API v2 (`REFILLABLE_CATEGORIES`) et
  reste autorisée dans `gift_asset.limit_choices_to` : on n'a pas retiré le support badgeuse,
  on a seulement supprimé les **données démo** trompeuses et corrigé leur catégorie.
- Au prochain `demo_data_v2`, `_produit_demo` repasse automatiquement les produits existants
  en `NONE` (logique de mise à jour de catégorie), donc les assets BDG ne se recréent pas.
- Le bloc « Badgeuse co-working » de `demo_data.py` a été **supprimé** (produit BADGE + tarif +
  phrase descriptive), à la demande du mainteneur (« on n'utilise plus les badges »). Aucune
  donnée en base à nettoyer : ce bloc n'avait jamais été exécuté sur la base dev.
