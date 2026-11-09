# Onboard : un seul suffixe de domaine proposé / Onboard: single domain suffix offered

**Date :** 2026-10-22
**Migration :** Non

## Resume / Summary
**Quoi / What :** L'étape « Votre lieu » de l'onboarding (`/onboard/venue/`) ne propose plus
que le 1er suffixe dérivé de l'environnement (`tibillet.coop` en prod). Le serializer refuse
tout autre suffixe. / The onboarding venue step now offers only the 1st env-derived suffix
(`tibillet.coop` in prod); the serializer rejects any other.

**Pourquoi / Why :** En prod, `ADDITIONAL_DOMAINS` contient tous les domaines servis : ils
apparaissaient tous comme choix pour un nouveau lieu. / In prod every served domain showed up
as a choice for a new venue.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `onboard/serializers.py` | `DNS_CHOICES` réduit au seul `DNS_DEFAUT` |
| `onboard/views.py` | `venue()` lit `DNS_CHOICES` du serializer ; un ancien suffixe en brouillon retombe sur le défaut |

`dns_suffixes_disponibles()` est inchangé (toujours utilisé par `create_empty_tenant`,
`batch_new_tenant`, `TenantCreateValidator`). Pour rouvrir le choix :
`DNS_CHOICES = tuple(dns_suffixes_disponibles())` dans `onboard/serializers.py`.

---

## Comment tester (a la main) / Manual test
### Test 1 — un seul choix
1. Aller sur `/onboard/venue/` (dev : `https://tibillet.localhost/onboard/venue/`).
2. Attendu : un seul bouton de suffixe (`tibillet.localhost` en dev, `tibillet.coop` en prod), coché.
3. L'aperçu « adresse finale » montre `<slug>.<ce suffixe>`.

### Test 2 — suffixe forcé refusé
- POST avec `dns_choice=domainbis.localhost` → 422, « n'est pas un choix valide ».

### Verifs
- `docker exec lespass_django poetry run pytest onboard/tests/test_step_venue.py onboard/tests/test_services_dns.py -q`
