# Branche OTP : fusion de main, boutons « Réserver » / « Adhérer » et panneau de vérification / OTP branch: main merged, "Book" / "Join" buttons and verification panel

**Date :** 2026-11-09
**Migration :** Non pour ce chantier. La fusion apporte celles de main (`BaseBillet 0237-0238`, `booking 0009-0010`, `comptabilite 0006-0007`, `pages 0004-0005`), et OTP garde `AuthBillet 0025` (`manage.py migrate_schemas --shared`, puis `migrate_schemas`).

## Resume / Summary
**Quoi / What :**
1. `main` est fusionnée dans `OTP`. Pour les personnes connectées, les boutons de main sont gardés : « Payer maintenant » / « Réserver maintenant » en principal, « Ajouter au panier » en secondaire, avec les erreurs dans le formulaire et l'option `Event.panier_desactive`. La réservation et l'adhésion anonymes restent retirées (décisions D1 et D15 du chantier AUTH).
2. Une personne non connectée voit « Réserver » ou « Adhérer », et non plus « Se connecter pour réserver / adhérer ». Le bouton ouvre le panneau `#loginPanel`.
3. Le panneau `#loginPanel` dit maintenant « Pour continuer, nous avons besoin de vérifier que vous êtes un vrai humain. ». Son bouton devient « Continuer », et son titre « Vérification ».
4. Le cas « anonyme » passe avant `panier_desactive` : un anonyme ne voit jamais de bouton d'envoi direct, qui lui donnerait une 403.

/ 1. `main` merged into `OTP`: logged-in people get main's buttons; anonymous booking and joining stay removed. 2. Anonymous people see "Book" / "Join" instead of "Log in to book / join". 3. The login panel now asks to verify that you are a real human, with a "Continue" button. 4. The anonymous case comes before `panier_desactive`.

**Pourquoi / Why :** un bouton « Se connecter » au moment de réserver fait peur et casse l'élan. On garde le mot de l'action, et on présente la connexion comme une simple vérification.
/ A "log in" button at booking time is off-putting: keep the action word, and present login as a simple check.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | Conflit : version OTP gardée (connecté → « Mes réservations ») |
| `BaseBillet/templates/fonctionnel/event/reservation_ok.html` | Supprimé (version OTP) : plus de réservation anonyme à valider par email |
| `BaseBillet/templates/commun/formulaires/reservation.html` | Boutons : anonyme → « Réserver » (ouvre `#loginPanel`) ; sinon `panier_desactive` → envoi direct seul ; sinon envoi direct + panier (version main) |
| `BaseBillet/templates/commun/adhesion/form.html` | Boutons de main pour les connectés ; anonyme → « Adhérer » (ouvre `#loginPanel`) |
| `BaseBillet/templates/commun/offcanvas/connexion.html` | Nouveau texte, bouton « Continuer », titre « Vérification » |
| `TECH_DOC/SESSIONS/TODO/INDEX.md` | Conflit : lignes de main gardées, numérotation remise à la suite |
| `tests/e2e/test_panier_flow.py` | Conflit : test e2 d'OTP gardé (un anonyme voit le panneau de connexion) |
| `tests/pytest/test_reservation_gratuite_redirection.py` | Tests de réservation anonyme retirés ; nouveau test : anonyme + panier désactivé → seulement le bouton de connexion |
| `tests/pytest/test_adhesion_erreurs_dans_le_formulaire.py` | Le formulaire est envoyé par une personne connectée |
| `tests/pytest/test_achat_reserve_aux_connectes.py`, `tests/e2e/test_connexion_par_code.py`, `tests/e2e/test_reservation_limits.py` | Docstrings : nouveaux libellés |

Chaînes traduisibles ajoutées (msgid FR) : « Réserver », « Adhérer », « Vérification », « Continuer », « Pour continuer, nous avons besoin de vérifier que vous êtes un vrai humain. », « Un code vous sera envoyé par email. ». Le workflow i18n est à lancer.

---

## Comment tester (a la main) / Manual test
### Test 1 — réservation, personne non connectée
1. Se déconnecter. Ouvrir un événement, cliquer sur le bouton de réservation de la page.
2. Attendu : en bas du panneau, un seul bouton « Réserver », sans « Ajouter au panier ».
3. Cliquer sur « Réserver ». Attendu : le panneau « Vérification » s'ouvre, avec « Pour continuer, nous avons besoin de vérifier que vous êtes un vrai humain. » et un bouton « Continuer ».
4. « Continuer » → guichet (email, puis code). Attendu : retour sur l'événement, avec le panneau de réservation ouvert.

### Test 2 — réservation, personne connectée
1. Connecté, ouvrir un événement payant. Attendu : « Payer maintenant » (principal) puis « Ajouter au panier » (secondaire).
2. Événement gratuit : « Réserver maintenant » à la place de « Payer maintenant ».
3. Admin → événement → « Désactiver le panier » coché. Attendu : un seul bouton, « Payer / Réserver maintenant ».

### Test 3 — panier désactivé, personne non connectée
1. Même événement, déconnecté. Attendu : seulement « Réserver », qui ouvre le panneau de vérification.

### Test 4 — adhésion
1. Déconnecté, ouvrir une adhésion. Attendu : un seul bouton « Adhérer », qui ouvre le panneau de vérification.
2. Connecté : « Payer maintenant », puis « Ajouter au panier ».

### Verifs DB / Playwright
- `make test ARGS="tests/pytest/test_reservation_gratuite_redirection.py tests/pytest/test_achat_reserve_aux_connectes.py tests/pytest/test_adhesion_erreurs_dans_le_formulaire.py"`.
- E2E existants (`data-testid` inchangés) : `tests/e2e/test_panier_flow.py`, `tests/e2e/test_connexion_par_code.py`.
