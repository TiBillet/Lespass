# Page compte lente : cache des lieux partagé / Slow account page: shared venues cache

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- La table des jetons de `/my_account/` affiche le nom et le logo du lieu d'origine de chaque jeton. Ces infos venaient de `MyAccount.get_place_cached_info`, qui **parcourt tous les lieux** de l'instance quand son cache manque : **6,4 s en prod** (497 lieux, mesuré le 2026-10-12).
- Ce cache était **séparé par lieu** (clés préfixées par le schéma, `django_tenants.cache.make_key`) et expirait toutes les heures : le premier visiteur de chaque lieu, chaque heure, attendait le parcours complet.
- Maintenant :
  - le cache est **unique pour toute l'instance** (posé dans le schéma public) ;
  - il est **rempli par le beat** `refresh_seo_cache` (toutes les 4 h), avec une durée de 5 h : aucun visiteur ne paie le parcours ;
  - il ne contient que des textes (nom, adresse de la miniature du logo) au lieu de l'objet fichier `config.logo` ;
  - un cache vide (`{}`) est valide et n'est plus reconstruit à chaque appel.
- Les gabarits `token_table.html` (V2 et classic) lisent `token.asset.logo_url`.

/ The account tokens table no longer scans every venue on a per-venue hourly cache miss (6.4 s in production): one instance-wide cache, filled by the 4 h beat.

**Reste / Remaining :** deux appels Fedow à chaque visite (carte NFC 0,63 s, portefeuille 0,67 s, mesurés en prod), faits l'un après l'autre.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `CLE_CACHE_DES_LIEUX_FEDOW`, `lire_le_cache_des_lieux_fedow()`, `construire_le_cache_des_lieux_fedow()`, `MyAccount.get_place_cached_info` réécrit, `logo_url` sur les jetons |
| `seo/tasks.py` (`refresh_seo_cache`) | étape 2bis : remplit le cache des lieux |
| `pages/templates/pages/{V2,classic}/vues/compte/partials/token_table.html` | `token.asset.logo_url` |
| `tests/pytest/test_compte_cache_des_lieux.py` | 8 tests (vérifiés par mutation) |

---

## Deploiement / Deployment
Après le déploiement, remplir le cache tout de suite (sinon le premier visiteur paie une fois les 6 s, ou on attend le beat) :
```python
from BaseBillet.views import construire_le_cache_des_lieux_fedow
construire_le_cache_des_lieux_fedow()
```

## Comment tester (a la main) / Manual test
1. Ouvrir `https://la-filature.tibillet.coop/my_account/` avec un compte qui a des jetons : la table affiche les logos et les noms des lieux, la page répond sans attendre.
2. Ouvrir le compte sur un autre lieu : même rapidité (le cache est partagé).

`docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_compte_cache_des_lieux.py -q`
