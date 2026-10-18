# Section « Coups de main » sur l'accueil V2 / "Coups de main" section on the V2 home

**Date :** 2026-10-18
**Migration :** Non

## Resume / Summary
**Quoi / What :** l'accueil codé en dur du skin V2 (servi quand le lieu n'a pas de page d'accueil CMS publiée) affiche, sous « Ce qui arrive », les 3 plannings de bénévoles qui ont des besoins à venir. Mêmes cartes que le bloc CMS LISTE source « COUPS_DE_MAIN », avec un lien « Tous les plannings ». Section visible seulement si le module bénévolat est actif et qu'un planning a des besoins à venir.
/ The hardcoded V2 home now shows, below "Ce qui arrive", the 3 volunteer plannings with upcoming needs (same cards as the CMS LISTE block, COUPS_DE_MAIN source). Only when the volunteering module is on and a planning has upcoming needs.

Cartes (accueil V2 et bloc CMS) : pour un planning « chaque semaine », les places libres ne comptent que les 10 prochains jours (aujourd'hui compris), et le planning n'a pas de carte s'il n'a aucun besoin dans ces 10 jours. Un planning ponctuel compte toujours toutes ses places à venir.
/ Cards: weekly plannings count free places over the next 10 days only (no card if none there); fixed-date plannings count all upcoming places.

Textes des cartes : planning « chaque semaine » → « Ces prochains jours, on a besoin de remplir X créneaux » (au lieu de « chaque semaine · X places libres ») ; planning ponctuel → « du … au … · X créneaux libres ».
/ Card wording: weekly → "Ces prochains jours, on a besoin de remplir X créneaux"; fixed dates → "X créneaux libres".

**Pourquoi / Why :** l'invitation au bénévolat n'existait que dans une page CMS ; un lieu sans page d'accueil CMS ne la montrait jamais. Un planning hebdomadaire additionnait des semaines de besoins (« 56 places libres »), sans rapport avec l'urgence.
/ The volunteering invitation only existed in CMS pages; weekly plannings summed weeks of needs.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/V2/vues/accueil.html` | Section `accueil-benevolat` (balise `plannings_benevoles_a_venir` + `booking/benevolat/partials/cartes_accueil.html`), `{% load pages_tags %}` |
| `booking/benevolat.py` | `resumes_des_plannings_a_venir` : horizon de 10 jours pour les plannings « chaque semaine » |
| `booking/templates/booking/benevolat/partials/cartes_accueil.html` | Nouveaux textes « Ces prochains jours… X créneaux » / « X créneaux libres » |
| `tests/pytest/test_benevolat_chantier3.py` | 6 tests : texte « ces prochains jours » ; section présente / absente module éteint ; hebdomadaire compté sur 10 jours, hebdomadaire sans besoin proche caché, ponctuel compté en entier (vérifiés par mutation) |

Nouvelles chaînes traduisibles (msgid FR) : « Coups de main », « Tous les plannings », « Ces prochains jours, on a besoin de remplir … créneau(x) », « … créneau(x) libre(s) » (« chaque semaine » et « … place(s) libre(s) » ne servent plus dans ce gabarit) → workflow i18n à lancer.

---

## Comment tester (a la main) / Manual test
### Test 1 — section visible
1. Lieu en skin V2, sans page d'accueil CMS publiée, module bénévolat actif, un planning publié avec un besoin à venir.
2. Ouvrir `/` : sous « Ce qui arrive », section « Coups de main » avec une carte par planning (3 max), jours colorés, bouton « Voir le planning ».
3. « Tous les plannings → » mène à `/booking/benevolat/`.

### Test 2 — section absente
1. Éteindre le module bénévolat (admin → Configuration) : la section disparaît.
2. Module actif mais aucun besoin à venir : la section n'apparaît pas (pas de message vide sur l'accueil).

### Test 3 — places libres
1. Planning « chaque semaine » : « Ces prochains jours, on a besoin de remplir X créneaux », X = les 10 prochains jours seulement (sur lespass en dev : « Bar associatif » 8 au lieu de 56).
2. Planning ponctuel (ex. « Festival ») : « du … au … · X créneaux libres », toutes ses places à venir (62).
3. Planning « chaque semaine » dont le premier besoin est dans plus de 10 jours : pas de carte.
