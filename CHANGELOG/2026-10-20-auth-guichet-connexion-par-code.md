# Connexion par code sur un guichet commun, achat réservé aux connectés / Login by code on a shared desk, purchase for logged-in users only

**Date :** 2026-10-20
**Migration :** Oui — `AuthBillet/migrations/0025_tibilletuser_jeton_de_session.py` (nouveau champ `TibilletUser.jeton_de_session`, vide par défaut). `AuthBillet` est dans les `SHARED_APPS` : schéma `public` seulement.

**Ordre de déploiement obligatoire / Mandatory deployment order :**
1. `git pull`
2. `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --shared`
3. `supervisorctl restart gunicorn daphne celery`

Le code lit `jeton_de_session` à **chaque** requête d'une personne connectée. Code redémarré avant la migration = erreur 500 pour toutes les personnes connectées.
/ The code reads `jeton_de_session` on every logged-in request: restarting before migrating = 500 for every logged-in user.

## Resume / Summary
**Quoi / What :**
- **Une seule façon de se connecter : un code à 6 chiffres reçu par mail.** Le code se tape sur un **guichet commun** à tous les lieux, sur le domaine du schéma `public` (`/sso/…`). Plus de lien de connexion par mail.
  / One way to log in: a 6-digit code sent by email, typed on a desk shared by all venues.
- **Une seule connexion pour tous les lieux (SSO).** Sur un 2ᵉ lieu, un clic sur « Se connecter » suffit, sans code. Le guichet renvoie au lieu un ticket signé (60 s, un seul lieu, une seule fois).
  / One login for all venues: on a second venue, one click, no code (signed one-time ticket).
- **Déconnexion de partout.** « Me déconnecter » (site ou admin) ferme toutes les sessions du compte : tous les lieux et le guichet.
  / Logout closes every session of the account.
- **Réserver et adhérer exigent d'être connecté.** Un anonyme voit « Se connecter pour réserver » ou « Se connecter pour adhérer ». La personne connectée réserve et adhère toujours pour elle-même : son email est en lecture seule.
  / Booking and membership require login; the email is the account's.
- **Réservation gratuite toujours validée tout de suite (`FA`)**, même par l'API v2 pour un compte non activé. Les billets partent aussitôt.
  / Free reservations are always `FA` at once, API v2 included.
- **Plafonds** sur les demandes de code : 60 s entre deux envois, 10 codes par heure et par email, 5 essais par code, 500 demandes par IP et par 10 minutes (réglable : `CONNEXION_CODE_PLAFOND_IP_10_MIN`).
- Empreinte du code en HMAC-SHA256 avec la clé secrète (`salted_hmac`), plus un SHA-256 simple.
- `OtpSession` supprimée (aucun utilisateur, et un code universel en DEBUG).

**Pourquoi / Why :** un anonyme pouvait réserver au nom d'un autre (billets envoyés chez lui, quota et jauge pris), viser un tarif réservé aux adhérents, inonder une boîte mail, ou créer des comptes avant toute preuve de l'email. Et il fallait se reconnecter sur chaque lieu. Spec : `TECH_DOC/SESSIONS/TODO/AUTH-connexion-par-code-achat-connecte.md`.
/ Anonymous users could book in someone else's name, reach member-only prices, flood mailboxes and create accounts before proving the email; and each venue needed its own login.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `AuthBillet/connexion_par_code.py` | Nouveau : envoi et vérification du code (cache, plafonds, code dans le journal en DEBUG) |
| `AuthBillet/sso.py` | Nouveau : domaine du guichet, lieu d'un domaine, fabrication et lecture du ticket |
| `AuthBillet/views_sso.py`, `AuthBillet/templates/sso/` | Nouveau : guichet (`/sso/`, `/sso/code/`, `/sso/code/verifier/`), finalisation du compte dans le contexte du lieu |
| `AuthBillet/models.py` + migration `0025` | `jeton_de_session`, `_get_session_auth_hash`, `deconnecter_de_partout()` |
| `AuthBillet/otp_service.py` | Empreinte en `salted_hmac` ; `envoyer_email_otp` renvoie `mail.sended` |
| `AuthBillet/otp_session.py`, `tests/pytest/test_otp_session.py` | **Supprimés** (D11) |
| `BaseBillet/tasks.py` | Nouvelle tâche `code_de_connexion_celery_mailer` (2 essais au plus) |
| `BaseBillet/views.py` | `connexion` (GET → guichet), `connexion_retour` (nouvelle), `deconnexion` de partout (POST + jeton CSRF, 405 en GET), `login_fullpage` redirige ; `EventMVT` / `MembershipMVT` : connexion exigée, email du compte injecté |
| `BaseBillet/urls.py`, `TiBillet/urls_public.py` | Routes `/connexion/retour/` et `/sso/…` |
| `BaseBillet/validators.py` | Réservation gratuite toujours `FA` (3 endroits) |
| `Administration/admin/site.py` | `StaffAdminSite.logout` : déconnexion de partout, POST seulement (405 en GET) |
| `Administration/admin_tenant.py` | Commentaires des boutons de la réservation remis à jour |
| `TiBillet/settings.py`, `env_example` | `CONNEXION_CODE_PLAFOND_IP_10_MIN` (500 par défaut) |
| `BaseBillet/templates/commun/offcanvas/connexion.html` | Panneau `#loginPanel` : texte + bouton vers le guichet (`data-next` copié) |
| `BaseBillet/templates/commun/formulaires/reservation.html`, `commun/adhesion/form.html` | Email en lecture seule ; un seul bouton de connexion pour un anonyme |
| `BaseBillet/static/commun/js/booking-calculator.mjs`, `membership-form.mjs` | Contrôle email / confirmation retiré |
| `BaseBillet/templates/htmx/components/panier_scripts.html` | Un 403 sur `/event/` et `/memberships/` ouvre aussi le panneau de connexion |
| `pages/templates/pages/faire_festival/vues/adhesions.html` | En iframe (embed) : lien vers `/memberships/` dans un nouvel onglet |
| `commun/formulaires/login.html`, `fonctionnel/connexion/*` (4 fichiers), `fonctionnel/event/reservation_ok.html` | **Supprimés** |
| `api_v2/GUIDELINES.md` | Une réservation gratuite par l'API n'est plus jamais `F` |
| `TECH_DOC/SESSIONS/OTP/INDEX.md`, `tests/PIEGES.md` (16.1-16.5, 9.98, 9.99), `onboard/views.py` (commentaire) | Docs à jour |
| `tests/pytest/` : `test_connexion_par_code.py` (17), `test_sso_guichet.py` (31), `test_deconnexion_de_partout.py` (5), `test_reservation_gratuite_validee_tout_de_suite.py` (2), `test_achat_reserve_aux_connectes.py` (11) | Nouveaux tests |
| `tests/e2e/test_connexion_par_code.py` (3) | Nouveau : code, SSO entre deux lieux, déconnexion de partout, panneau de réservation rouvert |
| Tests existants (`test_parite_avec_sans_panier`, `test_en_ligne_ecrit_la_vente`, `test_stripe_membership_*`, `test_otp_service`, 11 E2E) | Client connecté (`login_as`), statut `FA` |

---

## Comment tester (a la main) / Manual test

**Avant de commencer :** redémarrer `lespass_celery` (nouvelle tâche `code_de_connexion_celery_mailer`). Sinon le mail du code ne part pas.

### Test 1 — connexion par code
1. Sur `https://lespass.tibillet.localhost/`, en anonyme : « Connexion » → « Se connecter ».
2. On arrive sur le guichet `https://tibillet.localhost/sso/…`, titre « Connexion à <nom du lieu> ».
3. Taper son email → « Recevoir un code ».
4. Lire le code dans le journal du serveur : ligne « Connexion par code (DEBUG) ».
5. Taper le code → « Me connecter ».
6. Attendu : retour sur la page de départ, connecté, message « Connexion réussie. Bienvenue ! ».

### Test 2 — un 2ᵉ lieu sans code, puis déconnexion de partout
1. Toujours connecté sur lespass, ouvrir `https://festival.tibillet.localhost/`.
2. « Connexion » → « Se connecter ».
3. Attendu : connecté tout de suite, sans taper de code.
4. Cliquer « Me déconnecter » sur festival.
5. Recharger lespass. Attendu : déconnecté.

### Test 3 — réserver en anonyme
1. Page d'un événement, en anonyme → « Réserver ».
2. Attendu : un seul bouton « Se connecter pour réserver ».
3. Se connecter par le guichet.
4. Attendu : retour sur l'événement, panneau de réservation rouvert.

### Test 4 — adhérer
1. `/memberships/` en anonyme : bouton « Se connecter pour adhérer ».
2. Connecté : l'email du formulaire est en lecture seule.

### Test 5 — JavaScript
1. Ouvrir la console sur les pages d'adhésion et d'événement : aucune erreur.
2. Thème, langue et compteurs de quantité marchent (ils sont chargés dans le même module que `membership-form.mjs`).

### Test 6 — session expirée
1. Ouvrir un événement connecté, panneau de réservation ouvert.
2. Se déconnecter dans un autre onglet.
3. Revenir, cliquer « Payer maintenant ».
4. Attendu : le panneau de connexion s'ouvre, toast « Connectez-vous pour continuer. ».

### Test 7 — pages intégrées (iframe)
1. Intégrer `/event/embed/` et `/memberships/embed/` dans une iframe d'un autre site (surtout le skin faire_festival).
2. Attendu : le bouton ouvre la page du lieu dans un nouvel onglet.

### Test 8 — cas limites du guichet
1. `https://tibillet.localhost/sso/?lieu=inconnu.localhost&state=x` → « Lien de connexion invalide. ».
2. Code faux → « Code incorrect. Vérifiez le code reçu par mail. ».
3. « Recevoir un nouveau code » dans la minute → « Un code vient de partir. Patientez une minute avant d'en demander un autre. ».
4. « Changer d'adresse » → retour à l'étape de l'email.

### Points d'attention
- **Tests E2E non lancés** : ceux marqués `stripe_listen` n'ont pas tourné, faute de `stripe listen` : `test_panier_flow.py` (`test_e5_vrai_paiement_d_un_panier_adhesion_plus_billet`, `test_e6_une_adhesion_payee_par_le_panier_verse_sa_recompense_monnaie`) et le parcours en ligne de `test_adhesion_recompense_puis_qrcode.py`. À lancer avec `stripe listen`.
- **Gabarits de connexion supprimés** (`fonctionnel/connexion/*`) alors qu'ils avaient été retouchés le 2026-10-08 (commit 4a744db8, auteur NothRen). Le prévenir.
- **Décision en attente du mainteneur** (spec §12, E1) : `webhook_reservation` part sans `on_commit` dans `reservation_paid` : sous `transaction.atomic()` (API v2), il peut ne pas trouver la réservation.
- **Déconnexion en POST** (spec §12, E2, tranché) : `/deconnexion/`, `/logout/` et `/admin/logout/` refusent le GET (405). Les liens « Me déconnecter » des skins classic, V2 et faire_festival sont devenus des petits formulaires POST avec le jeton CSRF.
- **Chaînes à traduire** : nouvelles chaînes en français, `makemessages` à lancer par le mainteneur.

### Verifs DB / Playwright
- Champ posé après la déconnexion : `docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "from AuthBillet.models import TibilletUser; print(TibilletUser.objects.get(email='<email>').jeton_de_session)"` (64 caractères après « Me déconnecter », vide avant).
- Tests ciblés : `docker exec lespass_django bash -c "ulimit -v 8000000; timeout 600 poetry run pytest /DjangoFiles/tests/pytest/test_connexion_par_code.py -v"` (idem pour les autres fichiers ci-dessus).
- E2E : `tests/e2e/test_connexion_par_code.py`.
