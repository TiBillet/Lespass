# Newsletter Ghost : bloc bénévolat et bouton « En savoir plus » / Ghost newsletter: volunteer block and "En savoir plus" button

**Date :** 2026-10-18
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Le brouillon Ghost commence par un bloc « On a besoin de vous » : une carte product par planning de bénévoles du lieu qui a encore des créneaux à remplir. Phrase « Ces prochains jours, on a besoin de remplir X créneaux » (chaque semaine, 10 prochains jours) ou « du … au … · X créneaux libres » (ponctuel) — un créneau = un besoin qui a encore une place —, les prochains jours avec leurs places libres, et un bouton « Je m'inscris » vers la page du planning. Seulement si le module bénévolat est actif ; un planning entièrement couvert n'apparaît pas ; seulement le lieu courant (le bénévolat n'est pas fédéré).
- Des besoins en bénévoles suffisent à créer le brouillon, même sans évènement. Pas de brouillon seulement s'il n'y a ni évènement ni besoin.
- Le bouton des cartes d'évènement dit toujours « En savoir plus » (il mène à la page de l'évènement) ; le nom de bouton de réservation personnalisé de l'évènement n'est plus repris.
- Cartes « Coups de main » (site et newsletter) : pour un planning chaque semaine, les 5 jours colorés viennent maintenant des mêmes 10 jours que le compteur (un jour hors horizon montrait des places absentes du total).

/ The Ghost draft now starts with a "We need you" block (one product card per volunteer planning with open slots, "Je m'inscris" button). Volunteer needs alone are enough for a draft. Event buttons always read "En savoir plus". Weekly planning cards take their 5 days from the same 10-day horizon as the counter.

**Pourquoi / Why :** rappeler à tous les abonnés de s'inscrire comme bénévoles ; le bouton d'une newsletter mène à la page de l'évènement, pas à une réservation.
/ Remind every subscriber to sign up as a volunteer; a newsletter button opens the event page, not a booking.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `newsletter/collecte.py` | `collecter_besoins_benevoles()` (nouvelle) ; `libelle_bouton` = « En savoir plus » |
| `newsletter/rendu.py` | `rendre_newsletter_html(..., fiches_benevolat=())` |
| `newsletter/templates/newsletter/email_evenements.html` | Bloc « On a besoin de vous » en tête ; intro + sommaire seulement s'il y a des évènements |
| `newsletter/services.py` | Collecte des besoins ; `AucunEvenement` seulement sans évènement ET sans besoin ; `nombre_plannings_benevoles` dans le résultat et le journal |
| `newsletter/views.py` | Messages du panneau (succès avec le nombre de plannings, « aucun brouillon ») |
| `Administration/templates/admin/ghost/panneau_newsletter.html` | Texte d'aide : bloc bénévolat + « En savoir plus » |
| `booking/benevolat.py` | `resumes_des_plannings_a_venir` : 5 jours pris dans les besoins comptés |
| `tests/pytest/test_newsletter_ghost.py` | 12 tests ajoutés (rendu, collecte, service ; cas positif vérifié avant chaque cas négatif), 3 adaptés ; vérifiés par mutation |

Nouvelles chaînes traduisibles (msgid FR) : « On a besoin de vous », la phrase d'invitation, « Ces prochains jours, on a besoin de remplir … créneau(x). », « Je m'inscris », « En savoir plus », les messages du service et du panneau → workflow i18n à lancer.

---

## Comment tester (a la main) / Manual test
### Test 1 — brouillon avec bénévolat et évènements
1. Lieu avec module Newsletter + module bénévolat actifs, Ghost configuré, au moins un planning avec des créneaux libres et un évènement à venir.
2. Admin → Newsletter → Serveur Ghost → « Brouillon des 7 prochains jours ».
3. Message : « Brouillon créé avec N évènement(s) et M planning(s) de bénévoles. »
4. Ouvrir le brouillon dans Ghost : en tête « On a besoin de vous », une carte par planning (phrase, jours, bouton « Je m'inscris » vers `/booking/benevolat/<slug>/`), un séparateur, puis l'intro, le sommaire et les cartes d'évènement avec le bouton « En savoir plus ».

### Test 2 — bénévolat seul
1. Aucun évènement sur 7 jours, mais des besoins en bénévoles : le brouillon est créé, sans intro ni sommaire d'évènements.
2. Ni évènement ni besoin : message « aucun brouillon n'a été créé », rien dans Ghost.

### Test 3 — module éteint / planning couvert
1. Module bénévolat éteint : pas de bloc bénévolat.
2. Planning dont tous les créneaux sont pris : absent du bloc.

### Verifs automatiques
`docker exec lespass_django poetry run pytest tests/pytest/test_newsletter_ghost.py tests/pytest/test_benevolat_chantier3.py -q`
