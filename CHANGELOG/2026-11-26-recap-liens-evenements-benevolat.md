# Récap du matin : liens des événements et du bénévolat / Morning recap: event and volunteering links

**Date :** 2026-11-26
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- FR : dans le mail « Le récap du JJ/MM/AAAA », chaque ligne de « Nouveaux événements » est un lien vers la fiche de l'événement dans l'admin. Le titre « Nouvelles inscriptions de bénévoles » mène à la liste publique des plannings (`/booking/benevolat/`), plus à l'admin.
- EN: in the morning recap mail, each "New events" line links to the event's admin page. The "New volunteer sign-ups" title links to the public plannings list instead of the admin.

**Pourquoi / Why :**
- FR : ouvrir directement l'événement à vérifier ; voir les créneaux de bénévoles comme le public les voit.
- EN: open the event to check in one click; see volunteer slots as the public sees them.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/recap_quotidien.py` | Ligne d'événement = dict `{texte, lien}` ; lien de la rubrique bénévoles vers `/booking/benevolat/` |
| `BaseBillet/templates/emails/recap_quotidien.html` | Une ligne qui porte un `lien` devient un `<a>` |
| `tests/pytest/test_recap_quotidien.py` | Tests adaptés + lien de la fiche événement + rendu du lien dans le gabarit |

---

## Comment tester (a la main) / Manual test
### Test 1 — nouveaux événements
1. Créer un événement, puis antidater sa création à hier (`Event.objects.filter(pk=...).update(created_at=...)`).
2. Déclencher le récap du lieu (voir `CHANGELOG/2026-10-18-recap-quotidien-admins.md`).
3. Dans mailpit (https://mailpit.tibillet.localhost) : le nom de l'événement est cliquable et ouvre `/admin/BaseBillet/event/<uuid>/change/`.

### Test 2 — inscriptions de bénévoles
1. Une inscription de bénévole datée d'hier.
2. Dans le mail, le titre « Nouvelles inscriptions de bénévoles (N) » ouvre `https://<domaine>/booking/benevolat/`.

### Verifs automatiques
- `tests/pytest/test_recap_quotidien.py` : `test_chaque_evenement_mene_a_sa_fiche_admin`, `test_le_gabarit_fait_un_lien_d_une_ligne_qui_porte_un_lien`, `test_nouvelles_inscriptions_benevoles_compte_hier_et_pas_avant_hier_ni_aujourd_hui`.
