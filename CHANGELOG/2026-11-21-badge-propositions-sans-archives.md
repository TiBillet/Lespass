# Badge des propositions : seulement les propositions futures et non archivées / Proposals badge: only future, non-archived proposals

**Date :** 2026-11-21
**Migration :** Non

## Resume / Summary
**Quoi / What :** le badge rouge « + N » du menu « Événements » de l'admin ne compte plus les propositions archivées, ni celles dont la date est passée. / The red "+ N" badge on the admin "Events" menu no longer counts archived or past proposals.
**Pourquoi / Why :** il n'existe pas d'action « refuser ». Une proposition écartée, archivée ou passée restait comptée pour toujours, et le badge restait bloqué. / There is no "refuse" action: a dismissed, archived or past proposal stayed counted forever and the badge was stuck.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/dashboard.py` | `event_proposals_badge_callback` filtre aussi `archived=False` et `datetime__gte=timezone.now()` |
| `tests/pytest/test_event_proposal_admin.py` | Nouveaux tests `test_callback_ignore_propositions_archivees` et `test_callback_ignore_propositions_passees` |

---

## Comment tester (a la main) / Manual test
### Test 1 — une proposition archivée sort du badge
1. Sur un lieu avec l'agenda participatif actif, noter la valeur du badge « + N » sur « Événements ».
2. Ouvrir une proposition en attente (filtre « Proposal status » → « Proposals pending »), cocher « Archive », enregistrer.
3. Recharger l'admin : le badge vaut N − 1. À 0 proposition, il disparaît.

### Test 2 — une proposition passée sort du badge
1. Créer une proposition, puis mettre sa date de début dans le passé depuis l'admin.
2. Recharger l'admin : elle n'est plus comptée dans le badge.

### Verifs DB / Playwright
- `docker exec lespass_django poetry run pytest tests/pytest/test_event_proposal_admin.py -k Badge`
