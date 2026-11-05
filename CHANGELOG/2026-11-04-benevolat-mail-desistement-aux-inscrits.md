# Mail de désistement : envoyé aussi aux inscrit·es, lien vers le planning public / Withdrawal email: also sent to volunteers, link to the public planning

**Date :** 2026-11-04
**Migration :** Non

## Resume / Summary
**Quoi / What :** Le mail « X ne pourra pas venir » part à l'équipe du lieu ET à chaque personne encore inscrite sur le créneau (un mail par adresse). Le bouton mène à la page publique du planning, plus à l'admin. Le mail reprend l'habillage des autres mails bénévolat (logo et nom du lieu) et explique pourquoi on le reçoit.
/ The "X can't come" email goes to the venue team AND every volunteer still signed up on the shift (one email per address). The button opens the public planning page instead of the admin. Same look as the other volunteering emails (venue logo and name), plus a line explaining why it was received.

**Nom visible / Visible name :** l'équipe reçoit le nom complet de la personne qui se retire ; les autres bénévoles ne reçoivent que son prénom, dans le sujet et le corps (comme sur le planning public).
/ The team gets the full name; the other volunteers only get the first name.

**Vouvoiement / Formal address :** le mail de confirmation bénévole (« L'équipe vous a inscrit·e », « Dites-le en un clic ») vouvoie désormais : plus aucun mail ne tutoie.
/ The volunteer confirmation email now uses the formal "vous": no email uses "tu" anymore.

**Pourquoi / Why :** Les bénévoles du même créneau doivent savoir qu'il manque quelqu'un ; un lien vers l'admin ne leur sert à rien.
/ Volunteers on the same shift need to know someone is missing; an admin link is useless to them.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/tasks.py` | `prevenir_l_equipe_d_un_desistement` : destinataires = `Configuration.email` + inscrit·es restant·es, sans doublon ; `url_du_planning` remplace `url_de_l_admin` ; un envoi en erreur est journalisé et n'empêche pas les suivants ; nom complet pour l'équipe, prénom pour les bénévoles |
| `booking/benevolat.py` | `retirer_une_inscription` passe aussi `prenom_public(user)` à la tâche |
| `booking/templates/booking/benevolat/emails/desistement_equipe.html` | En-tête logo + nom du lieu, bouton « Voir le planning », mention « Vous recevez ce mail car… » |
| `tests/pytest/test_benevolat_rappel.py` | 5 tests : prénom seul pour les bénévoles, un mail à l'équipe et un par personne restante (lien public), lieu sans email, adresse en double, envoi qui plante |
| `tests/pytest/test_benevolat_inscription.py` | Contexte du test de rendu mis à jour ; la tâche reçoit aussi le prénom |
| `booking/templates/booking/benevolat/emails/confirmation.html` | 4 phrases passées au vouvoiement |
| `tests/pytest/test_benevolat_equipe.py` | Texte attendu « Lespass vous a inscrit·e » |
| `api_v2/openapi-schema.yaml`, `api_v2/GUIDELINES.md`, `api_v2/views_benevolat.py`, `TECH_DOC/SKILLS/tibillet-api/SKILL.md` | Citation du mail mise à jour |

---

## Comment tester (a la main) / Manual test
### Test 1 — scénario nominal
1. Sur un planning publié, créer un besoin à J+1 avec un délai de retrait de 48 h.
2. Inscrire 3 personnes (A, B, C), puis vieillir l'inscription de A (créée avant le délai).
3. Connecté·e en A, cliquer « Je ne peux plus venir ».
4. Vérifier : l'adresse du lieu, B et C reçoivent chacun un mail séparé (A ne reçoit rien). Le lieu voit « Prénom Nom », B et C ne voient que le prénom.
5. Le mail montre le logo et le nom du lieu, le bouton « Voir le planning » ouvre `/booking/benevolat/<slug>/`.

### Test 2 — cas limites
- Lieu sans `Configuration.email` : seuls B et C reçoivent le mail.
- Une personne inscrite avec la même adresse que le lieu : un seul mail à cette adresse.
- Un envoi refusé par le serveur mail : l'erreur part dans Sentry, les autres destinataires reçoivent le mail.

### Verifs DB / Playwright
- `make test ARGS="tests/pytest/test_benevolat_rappel.py -k desistement"`
