# Mailpit en dev et délai maximal SMTP / Mailpit in dev and SMTP timeout

**Date :** 2026-09-28
**Migration :** Non

## Resume / Summary

**Quoi / What :** un service `mailpit` (conteneur `lespass_mailpit`) reçoit tous les
e-mails de dev et de test sans les envoyer sur Internet ; ils se lisent sur
https://mailpit.tibillet.localhost. Nouveau réglage `EMAIL_TIMEOUT` (30 s par défaut) :
attente maximale de chaque échange avec le serveur SMTP. `EMAIL_USE_SSL` /
`EMAIL_USE_TLS` sont lus comme de vrais booléens. /
A `mailpit` service catches every dev/test e-mail. New `EMAIL_TIMEOUT` (default 30 s).
`EMAIL_USE_SSL` / `EMAIL_USE_TLS` are parsed as real booleans.

**Pourquoi / Why :** en dev, les e-mails partaient par le vrai SMTP OVH. Pendant la
suite E2E, les adresses de test étaient refusées et le relais coupait la connexion ;
sans délai maximal, une tâche `send_membership_pending_admin` prenait ~100 s et
bloquait un worker Celery. Une récompense d'adhésion est ainsi arrivée 2 min 32 après
la cotisation et un test E2E (`test_adhesion_recompense_puis_qrcode.py`, attente 60 s) a
échoué. Côté réglages, la chaîne `"False"` était vraie pour Python. /
Test e-mails went through the real OVH SMTP; with no timeout a task blocked a Celery
worker ~100 s. The string "False" was truthy.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `docker-compose.yml` (dev seulement) | service `mailpit` (réseaux backend + frontend, Traefik `mailpit.$DOMAIN` priorité 100), procédure de bascule en commentaire |
| `TiBillet/settings.py` | `EMAIL_USE_SSL` / `EMAIL_USE_TLS` comparés à une liste explicite ; `EMAIL_TIMEOUT = int(os.environ.get('EMAIL_TIMEOUT') or 30)` |
| `env_example` | `EMAIL_USE_*`, `EMAIL_TIMEOUT`, `DEFAULT_FROM_EMAIL` documentés ; bloc Mailpit en commentaire |

Comportement sans variable dans le `.env` : identique à avant (SSL oui, TLS non), plus le
délai de 30 s. **Avant un déploiement**, vérifier sur chaque serveur :
`grep -E '^EMAIL_USE' .env`. Une valeur `False` ou `0`, jusqu'ici lue comme vraie, est
désormais lue comme fausse (voir la relecture).

### Vérifications faites
- Envoi Django vers Mailpit (variables surchargées pour un seul processus) : 29 ms ;
  envoi par `CeleryMailerClass` : 14 ms, expéditeur conservé ; messages relus par l'API.
- Sans surcharge : SSL True, TLS False, délai 30 s ; `EMAIL_TIMEOUT` vide → 30.
- Serveur SMTP qui accepte la connexion sans jamais répondre : `SMTPServerDisconnected`
  au bout du délai (3,0 s avec `EMAIL_TIMEOUT=3`).
- `make test` : 1970 passed.
- Relecture Opus : procédure corrigée (garder `EMAIL_HOST_USER` ou définir
  `DEFAULT_FROM_EMAIL` ; recréer les conteneurs, un restart ne relit pas le `.env`),
  délai porté à 30 s, commentaires au présent.

Pas de test automatisé : changement de configuration, vérifié à la main ci-dessus.

### Après la bascule du .env (2026-09-28)
- `make e2e` : **110 passed** (8 min 58 s, contre 9 min 55 s avant) ; 79 e-mails reçus par
  Mailpit, 0 erreur SMTP dans Celery.
- File Celery sur la durée de la suite : `send_membership_pending_admin` 7 tâches, 7,5 s
  au total (contre 6 tâches, 610 s avant) ; aucune tâche d'envoi au-delà de 1,1 s.
- Récompense d'adhésion (`test_adhesion_recompense_puis_qrcode.py`) : versée 1,6 s après
  la cotisation (contre 2 min 32 s avant).
- Tests pytest liés aux e-mails (`onboard/tests/test_tasks_mailers.py`,
  `test_cloture_export.py`, `test_comptabilite_celery.py`, `test_mail_annulation_booking.py`,
  `test_otp_service.py`) : 38 passed.
- Piège rencontré : recréer `lespass_django` efface le navigateur Playwright (installé dans
  le conteneur, pas dans l'image). Réinstaller avant `make e2e` :
  `docker exec -u root lespass_django /home/tibillet/.cache/pypoetry/virtualenvs/lespass-LcPHtxiF-py3.11/bin/playwright install-deps chromium`
  puis `docker exec lespass_django poetry run playwright install chromium`.

---

## Comment basculer (a la main) / Switching over

1. Attendre qu'aucune suite de tests ne tourne (`docker exec lespass_django pgrep -af pytest`).
2. Dans `.env`, commenter les lignes OVH (pour revenir en arrière) et mettre :
   ```
   EMAIL_HOST="mailpit"
   EMAIL_PORT="1025"
   EMAIL_USE_SSL="False"
   EMAIL_USE_TLS="False"
   ```
   **Garder `EMAIL_HOST_USER`** (ou ajouter `DEFAULT_FROM_EMAIL="noreply@tibillet.localhost"`) :
   c'est l'adresse d'expédition, vide = aucun e-mail ne part.
3. Recréer (pas redémarrer) :
   `docker compose up -d --no-deps --force-recreate lespass_django lespass_celery`
4. Relancer `runserver_plus 0.0.0.0:8002` dans byobu.
5. Vérifier :
   ```bash
   docker exec lespass_celery poetry run python /DjangoFiles/manage.py shell -c \
     "from django.conf import settings as s; print(s.EMAIL_HOST, s.EMAIL_PORT, s.EMAIL_USE_SSL, s.EMAIL_USE_TLS, s.EMAIL_TIMEOUT)"
   # attendu : mailpit 1025 False False 30
   ```
   Puis se connecter par e-mail sur https://lespass.tibillet.localhost/ : le message
   apparaît sur https://mailpit.tibillet.localhost en moins d'une seconde.
6. Retour en arrière : remettre les lignes OVH, refaire les étapes 3 et 4.
