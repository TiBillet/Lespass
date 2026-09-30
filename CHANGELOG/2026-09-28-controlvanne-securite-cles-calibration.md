# controlvanne : clé API liée à sa tireuse, calibration réservée au lieu, limite sur authorize

**Date :** 2026-09-28
**Migration :** Non / No (`makemigrations --check` : « No changes detected »)

## Résumé / Summary

**Quoi / What :** trois points de sécurité de l'audit du 2026-09-26
(`CHANGELOG/a traiter/controlvanne-audit-securite-facturation.md`, points 1.4,
1.5 et 1.6). Ils sont traités ici et retirés de la fiche « à traiter ».

- **1.4 — Une clé API n'agit que sur SA tireuse.**
  - `HasTireuseAccess` refuse (403) toute clé sans compte de terminal : c'est
    le cas des anciennes clés créées avant l'appairage par code PIN.
  - `ping`, `authorize` et `event` vérifient ensuite que le compte de la clé
    est celui du terminal de la tireuse visée (`Terminal.term_user`). Sinon :
    403, et un avertissement dans les logs.
  - L'admin du lieu connecté (simulateur DEMO) garde l'accès.
- **1.5 — Calibration réservée aux admins du lieu.** `@staff_member_required`
  laissait passer le staff de n'importe quel lieu, car `is_staff` est un
  drapeau global. Les trois vues commencent maintenant par
  `_refuser_si_pas_admin_du_lieu` :
  - pas connecté → page de connexion ;
  - pas admin de ce lieu (`TenantAdminPermissionWithRequest`) → 403.
  La page prévient aussi quand le débitmètre est partagé avec d'autres
  tireuses, puisque le nouveau facteur s'applique à toutes.
- **1.6 — Limite sur `authorize`** : 30 appels par minute, **par clé API** (pas
  par IP : dans un bar, les Pi partagent souvent la même IP). L'admin connecté
  est compté par compte. Le lieu fait partie de la clé de cache. Au-delà :
  429.

/ 1.4 API keys only act on their own tap (keys without terminal account are
refused). 1.5 Calibration restricted to venue admins, shared flow meter
warning. 1.6 authorize limited to 30/min per API key.

**Pourquoi / Why :**
- Sans le 1.4, une clé volée ou la clé d'une tireuse pouvait badger, verser et
  facturer sur n'importe quelle tireuse du lieu.
- Sans le 1.5, un admin d'un autre lieu pouvait changer le facteur d'un
  débitmètre.
- Sans le 1.6, `authorize` (qui renvoie le solde) permettait de tester des UID
  de carte en masse.

## ⚠️ À faire au déploiement / Deployment

**Choix fait : les anciennes clés sans compte sont REFUSÉES.** Tout Raspberry Pi
appairé avec une clé créée avant le lien clé ↔ terminal cesse de fonctionner
(403) jusqu'à un **nouvel appairage** : Admin → Terminaux → nouveau code PIN.

Pour les repérer avant le déploiement, dans chaque lieu :
```bash
docker exec lespass_django poetry run python manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
from controlvanne.models import TireuseAPIKey
for t in Client.objects.exclude(schema_name='public'):
    with tenant_context(t):
        n = TireuseAPIKey.objects.filter(user__isnull=True, revoked=False).count()
        if n: print(t.schema_name, n, 'clé(s) sans compte')
"
```

## Fichiers / Files

| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/permissions.py` | Refus des clés sans compte de terminal |
| `controlvanne/viewsets.py` | `_la_cle_appartient_a_la_tireuse` + `_refus_cle_d_une_autre_tireuse` dans `ping`/`authorize`/`event` ; `AuthorizeTireuseThrottle` |
| `controlvanne/calibration_views.py` | `_refuser_si_pas_admin_du_lieu` au lieu de `@staff_member_required` ; liste des tireuses qui partagent le débitmètre |
| `controlvanne/templates/calibration/page.html` | Avertissement « débitmètre partagé » |
| `tests/pytest/fabriques_controlvanne.py` | Nouveau : `cle_api_de_la_tireuse` (appaire le terminal comme discovery) |
| `tests/pytest/test_controlvanne_api.py` | Clé liée à `test_tireuse` ; tests clé sans compte, clé d'une autre tireuse, limite 429 |
| `tests/pytest/test_controlvanne_billing.py`, `_models.py`, `_review_fixes.py` | Fixtures de clé liées à leur tireuse |
| `tests/pytest/test_controlvanne_ecran_calibration.py` | Tests d'accès à la calibration et du débitmètre partagé |
| `CHANGELOG/a traiter/controlvanne-audit-securite-facturation.md` | 1.4 à 1.6 retirés ; plan détaillé pour 1.1 à 1.3 |

## À tester / To test

1. **Clé d'une autre tireuse** : avec la clé du Pi de la tireuse A, appeler
   `POST /controlvanne/api/tireuse/authorize/` avec l'UUID de la tireuse B →
   403.
2. **Ancienne clé** : un Pi appairé avant le code PIN → 403 à chaque appel. Le
   ré-appairer → il refonctionne.
3. **Calibration** : se connecter avec un compte staff qui n'est pas admin du
   lieu → 403 sur `/controlvanne/calibration/<uuid>/`. Un admin du lieu → la
   page s'affiche. Deux tireuses sur le même débitmètre → l'avertissement
   liste l'autre tireuse.
4. **Limite** : plus de 30 `authorize` en une minute avec la même clé → 429.

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_*.py -q
```
