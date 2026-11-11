# Connexion demandée avant le formulaire, et réparation du merge OTP / Login asked before the form, and OTP merge repair

**Date :** 2026-11-09
**Migration :** Non

## Resume / Summary
**Quoi / What :**
1. Une personne non connectée qui clique sur le bouton de réservation d'un événement, ou sur « Adhérer » d'une carte d'adhésion, part **directement au guichet de connexion**. Le formulaire ne s'ouvre pas avant : elle n'a encore rien saisi, donc rien n'est perdu. Au retour, le formulaire s'ouvre tout seul : `?openbookingPanel=true` pour un événement, `/memberships/?open=<uuid>` pour une adhésion. C'est fait dans les 3 skins (V2, reunion/classic, faire_festival). Le panneau intermédiaire `#loginPanel` n'est plus utilisé dans ce parcours.
2. Le script qui ouvre l'adhésion demandée (`?open=<uuid>`) devient un partiel commun. Il existait seulement en V2 : il est ajouté aux skins classic et faire_festival. Il ne plante plus quand le bouton de la carte est absent.
3. Les boutons anonymes en bas des formulaires (« Réserver », « Adhérer ») restent, comme filet de sécurité. Ce sont maintenant des liens directs vers le guichet.
4. **Tous les autres boutons de connexion mènent aussi directement au guichet**, sans passer par le panneau `#loginPanel` :
   - le lien « Connexion » de la navbar (3 skins) et du footer (classic, faire_festival) ;
   - « Me connecter pour venir » du planning des bénévoles, avec le retour sur le planning, à la semaine de la case ;
   - « Postuler » des bénévoles d'un événement (classic, V2) ;
   - les ressources : un anonyme qui clique sur un créneau est envoyé au guichet, avec le retour sur la page de la ressource (il était renvoyé à l'accueil) ;
   - crowds (voter, contribuer, proposer) : plus de fenêtre « Connexion requise », direction le guichet ;
   - le lien « Log in » du panier.
   Le retour (`next`) des liens de la navbar, du footer et du panneau est le chemin de la page SANS ses paramètres (`request.path`) : un lien de suivi (`?utm_source=…`) ne doit pas se retrouver recopié dans la page (test `test_seo_canonical_doublons.py`).
   `#loginPanel` ne s'ouvre plus que tout seul : `?login=1`, réponse 403 à une requête htmx, session expirée sur le planning.
5. Le toast « Connexion réussie. Bienvenue ! » est retiré : la personne revient sur la page voulue, formulaire ouvert. Le toast d'avertissement du guichet (ancienne réservation non validable) reste.
6. Réparation du commit de merge `c2db0ad8` (main → OTP). Trois fichiers n'avaient pas la résolution prévue :
   - `reservation.html` ne compilait plus (deux `{% else %}`), et les pages d'événement tombaient en erreur 500 ;
   - `adhesion/form.html` montrait à un anonyme un bouton d'envoi direct, refusé ensuite par une 403 ;
   - `views.py` rendait `reservation_ok.html`, qui est supprimé.
   La numérotation de `TODO/INDEX.md` est aussi corrigée.

/ 1. Anonymous visitors go straight to the login desk when clicking an event's booking button or a membership card's "Join", before any form opens; the form reopens on return. All 3 skins. 2. The `?open=<uuid>` script is shared and added to classic and faire_festival. 3. In-form anonymous buttons are now direct links. 4. Repair of merge commit `c2db0ad8` (broken booking template, pre-OTP membership buttons, dead view branch).

**Pourquoi / Why :** demander la connexion en bas du formulaire faisait perdre toute la saisie, puisque la page se recharge au retour du guichet.
/ Asking to log in at the bottom of the form lost everything typed, since the page reloads on return from the desk.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/{classic,V2}/partials/reservation_declencheur.html`, `pages/templates/pages/faire_festival/vues/evenement.html` | Anonyme : lien vers `/connexion/?next=<événement>?openbookingPanel=true` (`data-testid="booking-open-login"`) ; connecté : bouton inchangé |
| `pages/templates/cotton/V2/membership_card.html`, `pages/templates/pages/{classic,faire_festival}/vues/adhesions.html` | Anonyme : lien vers `/connexion/?next=/memberships/?open=<uuid>` (`data-testid="membership-open-login-<uuid>"`) |
| `BaseBillet/templates/commun/partials/ouvrir_adhesion_demandee.html` | Nouveau : script `?open=<uuid>`, protégé, inclus par les 3 pages adhésions |
| `BaseBillet/templates/commun/formulaires/reservation.html` | Résolution du merge remise ; lien anonyme direct vers le guichet |
| `BaseBillet/templates/commun/adhesion/form.html` | Résolution du merge remise ; lien anonyme direct vers le guichet |
| `BaseBillet/views.py` | `EventMVT.reservation` : fin de la version OTP (connecté → « Mes réservations ») |
| `TECH_DOC/SESSIONS/TODO/INDEX.md` | Numérotation |
| `tests/pytest/test_achat_reserve_aux_connectes.py` | Liens vers le guichet ; 9 tests par skin (déclencheur d'événement, carte d'adhésion, script `?open`) |
| `pages/templates/pages/{V2,classic,faire_festival}/partials/navbar.html`, `pages/templates/pages/{classic,faire_festival}/partials/footer.html` | Lien « Connexion » direct vers le guichet (`?next=` = page courante) |
| `booking/templates/booking/benevolat/partials/besoin.html`, `pages/templates/pages/{classic,V2}/partials/evenement_benevoles.html` | Liens directs vers le guichet |
| `booking/views.py` | `book` : anonyme → `HX-Redirect` vers `/connexion/?next=/booking/<pk>/resource/` |
| `crowds/templates/crowds/views/{list,detail}.html` | `crowdsVoteRequireLogin` → guichet, sans fenêtre de confirmation |
| `BaseBillet/templates/htmx/components/panier_content.html` | Lien « Log in » → guichet |
| `BaseBillet/templates/commun/offcanvas/connexion.html` | Commentaire : le panneau ne s'ouvre plus que tout seul |
| `BaseBillet/views.py` (`connexion_retour`) | Toast « Connexion réussie » retiré |
| `tests/pytest/test_benevolat_inscription.py` | Lien du planning vers le guichet |
| `tests/e2e/test_login.py`, `test_skin_faire_festival_navigation.py` | Le lien « Connexion » mène au guichet |
| `tests/e2e/test_panier_flow.py`, `test_connexion_par_code.py`, `test_reservation_limits.py`, `test_numeric_overflow_validation.py` | Un anonyme part au guichet. Les tests qui veulent voir le formulaire anonyme l'ouvrent par `?openbookingPanel=true` |

Aucune nouvelle chaîne traduisible. Chaînes devenues inutilisées (retirées par le prochain makemessages) : « Connexion réussie. Bienvenue ! », « Connexion requise », « Veuillez vous connecter pour voter. », « Veuillez vous connecter pour continuer. ».

---

## Comment tester (a la main) / Manual test
### Test 1 — événement, anonyme
1. Se déconnecter. Ouvrir un événement avec des tarifs.
2. Cliquer sur le bouton de réservation. Attendu : le guichet de connexion s'ouvre tout de suite (pas de formulaire, pas de panneau intermédiaire).
3. Taper l'email puis le code. Attendu : retour sur l'événement, avec le formulaire de réservation ouvert et « Payer / Réserver maintenant ».

### Test 2 — adhésion, anonyme (3 skins)
1. Déconnecté, page « Adhésions ». Cliquer sur « Adhérer » d'une carte. Attendu : le guichet.
2. Après le code : retour sur `/memberships/?open=<uuid>`, avec le formulaire de cette adhésion ouvert.
3. Refaire en skin faire_festival puis en skin Réunion (Admin → Configuration du site → Thème).

### Test 3 — connecté
1. Connecté, les boutons ouvrent directement les formulaires, comme avant.

### Verifs DB / Playwright
- `make test ARGS="tests/pytest/test_achat_reserve_aux_connectes.py"`.
- `make e2e ARGS="tests/e2e/test_panier_flow.py tests/e2e/test_connexion_par_code.py tests/e2e/test_reservation_limits.py tests/e2e/test_numeric_overflow_validation.py"`.
