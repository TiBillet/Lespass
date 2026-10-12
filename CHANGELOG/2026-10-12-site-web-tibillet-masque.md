# Site web « tibillet.org » masqué / "tibillet.org" website hidden

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Beaucoup de lieux ont `tibillet.org` comme site web. **Origine :** à la création du lieu, `TenantCreateValidator.create_tenant` (`BaseBillet/validators.py`) recopie dans `Configuration.site_web` l'URL déclarée dans le compte Stripe Connect (`business_profile.url`). TiBillet ne pré-remplit rien (`stripe.Account.create` sans site web) : un lieu sans site saisit l'adresse de TiBillet dans le formulaire Stripe.
- Nouvelle règle `est_un_site_du_projet_tibillet()` et propriété `Configuration.site_web_du_lieu` (`BaseBillet/models.py`) : `None` si l'adresse est tibillet.org / .coop / .re (avec ou sans `www`, avec ou sans protocole). Les sous-domaines des lieux ne sont pas concernés.
- Utilisée par : l'en-tête V2 (`tenant_header.html`), le JSON-LD Organization (`sameAs`, `pages_tags.py`), l'organisateur des événements de l'API v1 (`EventSerializer.get_organizer`).
- À la création d'un lieu, une URL TiBillet venue de Stripe n'est plus recopiée.
- Les données existantes ne sont pas modifiées : elles sont seulement masquées.

/ Venues whose website is TiBillet's own site (typed in the Stripe form, copied at venue creation) no longer show it; new venues no longer copy it.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `DOMAINES_DU_PROJET_TIBILLET`, `est_un_site_du_projet_tibillet()`, `Configuration.site_web_du_lieu` |
| `BaseBillet/validators.py` (`create_tenant`) | URL Stripe recopiée seulement si ce n'est pas TiBillet |
| `pages/templates/pages/V2/tenant_header.html` | `config.site_web_du_lieu` |
| `pages/templatetags/pages_tags.py` (`jsonld_organisation`) | `sameAs` sans le site du projet |
| `ApiBillet/serializers.py` (`get_organizer`) | idem |
| `tests/pytest/test_site_web_du_lieu.py` | 14 tests (vérifiés par mutation) |

**Non testé automatiquement :** la garde dans `create_tenant` (appel Stripe réel).

## Comment tester (a la main) / Manual test
1. Un lieu dont le site web est `https://tibillet.org/` : plus de lien sous le nom du lieu dans l'en-tête V2.
2. Un lieu avec un vrai site : le lien est toujours là.

`docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_site_web_du_lieu.py -q`
