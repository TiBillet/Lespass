# Bouton « Contribuez » conditionné au module Crowds / "Contribute" button gated by the Crowds module

**Date :** 2026-10-24
**Migration :** Oui — `BaseBillet/migrations/0239_module_crowdfunding_eteint_par_defaut.py` (AlterField, no-op SQL : `manage.py migrate_schemas`)

## Resume / Summary
**Quoi / What :** le bouton « Contribuez » de l'en-tête du lieu (skin V2) ne s'affiche plus que si le module financement participatif est actif, que la config Crowds est activée (champ « Activer ») et qu'il existe au moins une initiative non archivée. / The venue header "Contribute" button now shows only when the crowdfunding module is on, the Crowds config is active and at least one non-archived initiative exists.
Le module est aussi **éteint par défaut sur les nouveaux lieux** (`default=False`) ; les lieux existants gardent leur valeur. / The module is also **off by default for new venues**; existing venues keep their value.
**Pourquoi / Why :** le bouton ne dépendait que de `module_crowdfunding` (vrai par défaut sur tous les lieux) : il était visible partout, même sans aucune initiative, et le champ « Activer » de la config Crowds n'avait plus d'effet. / It only depended on `module_crowdfunding` (true by default), so it showed everywhere, even with no initiative.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `get_context()` calcule `afficher_bouton_contribuer` (module + `CrowdConfig.active` + initiative non archivée) |
| `BaseBillet/models.py` | `Configuration.module_crowdfunding` : `default=False` |
| `BaseBillet/migrations/0239_module_crowdfunding_eteint_par_defaut.py` | AlterField (aucun changement SQL) |
| `pages/templates/pages/V2/tenant_header.html` | Le bouton lit `afficher_bouton_contribuer` ; ajout `data-testid="tenant-header-contribuer"` |

---

## Comment tester (a la main) / Manual test
### Test 1 — scénario nominal
1. Sur `https://lespass.tibillet.localhost/` (skin V2, module Crowds actif, initiatives présentes).
2. Le bouton « Contribuez » est visible en haut à droite de l'en-tête du lieu.

### Test 2 — chaque condition masque le bouton
1. Admin → config Crowds → décocher « Activer » → recharger l'accueil : bouton absent. Recocher.
2. Tableau de bord admin → désactiver le module « Financement participatif » → bouton absent. Réactiver.
3. Archiver toutes les initiatives → bouton absent.

### Test 3 — nouveau lieu
1. Créer un lieu via l'onboarding.
2. Tableau de bord admin du nouveau lieu : le module « Financement participatif » est éteint, pas de bouton « Contribuez ».
3. Un lieu existant (ex : lespass) garde son module allumé.

### Vérifs DB / Playwright
- Pas de test automatique dédié pour l'instant (`data-testid="tenant-header-contribuer"` posé pour en écrire un).
- Attention en shell : `get_solo()` passe par le cache. Un `save()` dans une transaction annulée laisse le cache faux → `Configuration.objects.get().clear_cache()`.
