# Bénévolat, chantier 4 : « Répéter des besoins » dans l'admin / Volunteering, step 4: "Repeat needs" in the admin

**Date :** 2026-10-16
**Migration :** Non (le `help_text` du slug est corrigé dans `booking/0003_benevolat.py`, sans effet SQL)

## Resume / Summary
**Quoi / What :** sur la fiche d'un planning de bénévoles, un bouton « Répéter des besoins » (menu d'actions) ouvre une page : on choisit une période modèle (un jour, une semaine), un écart (N jours ou N semaines) et un nombre de fois. Le premier envoi montre un aperçu en trois listes (à créer, sautés car jour fermé, ignorés car déjà présents), sans rien écrire. « Confirmer » crée tout dans une seule transaction et revient à la fiche : « 14 besoins créés, 2 sautés (fermeture), 2 ignorés (déjà présents). »
/ A "Repeat needs" admin page: model period, gap, count; preview then confirm.

**Pourquoi / Why :** chantier 4 de `TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md` (§5.7) : ne plus ressaisir chaque semaine les mêmes créneaux.

Règles : les inscriptions ne sont jamais copiées ; une copie un jour fermé du calendrier du planning est sautée (pas décalée) ; une copie identique (tâche, jour, heures) à un besoin existant est ignorée, donc relancer ne double rien. Le calcul est une fonction pure (`calculer_repetitions`), réutilisée par l'API au chantier 6.

Correction au passage : l'aide du champ « Adresse de la page » affichait `/booking/benevolat//` (le `<adresse>` était lu comme une balise HTML par l'admin).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/benevolat.py` | `cle_d_un_besoin`, `calculer_repetitions` (sans base) |
| `booking/models.py` | `periode_fermee_qui_couvre`, `libelle_d_une_fermeture` (sans base), réutilisées par `PlanningBenevole` ; `help_text` du slug |
| `Administration/admin/benevolat.py` | `RepeterDesBesoinsForm`, `calculer_l_apercu`, vue `PlanningBenevoleAdmin.repeter` (`get_urls`), bouton `actions_detail` |
| `Administration/templates/admin/booking/planning_repeter.html` | Nouveau gabarit (formulaire, aperçu, confirmation) |
| `booking/tests/test_benevolat_repetition.py` | 15 tests (10 sur le calcul pur, 5 sur la page), vérifiés par mutation (13 mutations) |
| `TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md` | Statut, détails §5.7 |

i18n : nouvelles chaînes traduisibles (msgid en français), workflow i18n à lancer par le mainteneur.

---

## Comment tester (a la main) / Manual test

### Test 1 — répéter un week-end
1. Admin → Plannings bénévoles → un planning avec des besoins un vendredi et un samedi.
2. Menu d'actions de la fiche (« … ») → « Répéter des besoins ».
3. Modèle : du vendredi au samedi, tous les 1 semaine(s), 4 fois → « Voir l'aperçu ».
4. Attendu : 8 copies à créer (moins celles d'un jour fermé), rien encore en base.
5. « Confirmer » → retour à la fiche, message « N besoins créés… », les besoins sont dans la liste, sans inscription.

### Test 2 — relancer
1. Refaire exactement la même chose.
2. Attendu : tout est « ignoré (déjà présent) », le bouton « Confirmer : créer 0 besoins » est désactivé.

### Test 3 — jour fermé
1. Choisir un calendrier de fermetures sur le planning, avec une fermeture qui tombe sur une copie.
2. Attendu : la copie est listée « sauté : <libellé de la fermeture> ».

### Verifs automatiques
- `docker exec -w /DjangoFiles lespass_django poetry run pytest booking/tests/test_benevolat_repetition.py -q`
