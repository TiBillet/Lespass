# Récap du matin : liens des événements et du bénévolat / Morning recap: event and volunteering links

**Date :** 2026-11-26
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- FR : dans le mail « Le récap du JJ/MM/AAAA », chaque ligne de « Nouveaux événements » est un lien vers la fiche de l'événement dans l'admin. Pour les bénévoles, les liens mènent au site public, plus à l'admin : le titre « Nouvelles inscriptions de bénévoles » ouvre la liste des plannings (`/booking/benevolat/`), chaque ligne ouvre le planning de son inscription (`/booking/benevolat/<slug>/`).
- EN: in the morning recap mail, each "New events" line links to the event's admin page. Volunteer links go to the public site instead of the admin: the section title opens the plannings list, each line opens its sign-up's planning.

**Pourquoi / Why :**
- FR : ouvrir directement l'événement à vérifier ; voir les créneaux de bénévoles comme le public les voit.
- EN: open the event to check in one click; see volunteer slots as the public sees them.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/recap_quotidien.py` | Lignes d'événement et d'inscription = dict `{texte, lien}` ; titre de la rubrique bénévoles vers `/booking/benevolat/`, lignes vers le planning |
| `BaseBillet/templates/emails/recap_quotidien.html` | Une ligne qui porte un `lien` devient un `<a>` |
| `tests/pytest/test_recap_quotidien.py` | Tests adaptés + lien de la fiche événement + lien du planning d'une inscription + rendu du lien dans le gabarit |

---

## Comment tester (a la main) / Manual test
### Test 1 — nouveaux événements
1. Créer un événement, puis antidater sa création à hier (`Event.objects.filter(pk=...).update(created_at=...)`).
2. Déclencher le récap du lieu (voir `CHANGELOG/2026-10-18-recap-quotidien-admins.md`).
3. Dans mailpit (https://mailpit.tibillet.localhost) : le nom de l'événement est cliquable et ouvre `/admin/BaseBillet/event/<uuid>/change/`.

### Test 2 — inscriptions de bénévoles
1. Une inscription de bénévole datée d'hier.
2. Dans le mail, le titre « Nouvelles inscriptions de bénévoles (N) » ouvre `https://<domaine>/booking/benevolat/`.
3. Chaque ligne (bénévole — tâche — date) est cliquable et ouvre la page publique de son planning, `https://<domaine>/booking/benevolat/<slug>/`.

### Verifs automatiques
- `tests/pytest/test_recap_quotidien.py` : `test_chaque_evenement_mene_a_sa_fiche_admin`, `test_chaque_inscription_mene_a_la_page_publique_de_son_planning`, `test_le_gabarit_fait_un_lien_d_une_ligne_qui_porte_un_lien`, `test_nouvelles_inscriptions_benevoles_compte_hier_et_pas_avant_hier_ni_aujourd_hui`.
