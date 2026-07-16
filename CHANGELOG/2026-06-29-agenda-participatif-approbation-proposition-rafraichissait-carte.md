# Agenda participatif : l'approbation d'une proposition ne rafraîchissait pas la carte / Proposal approval didn't refresh the map

**Date :** 2026-06-29
**Migration :** Non / No

**Quoi / What :** Approuver une proposition publique (agenda participatif) via
l'action admin « Approuver et publier les propositions sélectionnées » la publiait
bien, mais l'event **n'apparaissait sur la carte réseau qu'au beat 4 h**.

**Pourquoi / Why :** L'action utilisait `queryset.update(is_proposal=False,
published=True)`. Le `.update()` en masse **ne déclenche pas le signal
`post_save`** → `declencher_refresh_seo_cache` n'était jamais appelé → pas de
rebuild SEO. (Le toggle « Publier » de la liste et l'édition via le formulaire,
qui passent par `save()`, déclenchaient bien le signal — seule l'action bulk était
touchée.)

**Fix / Fix :** L'action publie désormais via `save(update_fields=["is_proposal",
"published"])` par instance (boucle), ce qui déclenche `post_save` → rebuild SEO
débouncé → l'event approuvé apparaît sur la carte en ~15-20 s. Vérifié par test +
en conditions réelles (Chrome) : toggle « Publier » → event présent dans
`AGGREGATE_EVENTS`, L1 cohérent cross-schema.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `approuver_propositions` : `save()` par instance au lieu de `queryset.update()` (déclenche le signal SEO) |
| `tests/pytest/test_seo_cache_fragments.py` | +1 test : l'approbation d'une proposition déclenche le rebuild SEO |

### Migration
- **Migration nécessaire / Migration required :** Non / No.
