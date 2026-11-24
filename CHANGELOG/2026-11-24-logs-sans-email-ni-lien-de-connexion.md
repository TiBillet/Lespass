# Logs sans e-mail, sans lien de connexion, sur une seule ligne / Logs without email, login link, on one line

**Date :** 2026-11-24
**Migration :** Non

Suite de `2026-11-23-logs-lisibles-dans-la-supervision.md`, après une nuit de logs de prod dans OpenObserve.
/ Follow-up of the 2026-11-23 entry, after one night of production logs.

## Resume / Summary

**Quoi / What :**
- **Sécurité :** la tâche `connexion_celery_mailer` écrivait le lien de connexion (`/emailconfirmation/<jeton>`, valable 72 h) dans les logs, même hors DEBUG. Il n'est plus loggé qu'en DEBUG. Le mail, lui, part comme avant.
- La machine à état (`pre_save_signal_status`) écrivait `str(instance)` : pour une réservation ou un utilisateur, c'est l'e-mail. Elle écrit maintenant l'UUID court, sur une seule ligne (elle entourait le message de `\n\n` … `\n`).
- Le `validate` du formulaire de réservation n'écrit plus le champ `email`.
- E-mails remplacés par l'UUID court (ou `@domaine` quand on n'a que l'adresse) dans les tâches mail (connexion, billets, Ghost, Brevo, rappels bénévoles, OTP de l'onboarding), le webhook Stripe, l'adhésion, le websocket, Fedow.
- Les métadonnées Stripe sortaient en JSON indenté sur 4 lignes : `json.dumps(dict(metadata))`, une ligne.
- Retirés : les `\n` en fin de message des signaux et des triggers, les lignes vides et les lignes `----` autour de la création d'un paiement Stripe et du webhook.
- / Login link no longer logged outside DEBUG. State machine, reservation validator, mail tasks, Stripe webhook: no email. One line per message: no `\n`, no blank or `----` lines, Stripe metadata without indent.

**Pourquoi / Why :**
Docker et OpenObserve coupent un message à chaque retour à la ligne : chaque morceau devient une entrée sans niveau, sans lieu, sans module. Et les logs restent un an dans la supervision : ni e-mail, ni jeton.
/ The monitoring splits a message at each newline, and keeps logs for a year.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/tasks.py` | Lien de connexion loggé seulement en DEBUG ; e-mails → UUID court ou `@domaine` (connexion, billets, Ghost, Brevo, `CeleryMailerClass`) ; debug du webhook adhésion sur une ligne |
| `BaseBillet/signals.py` | Machine à état : UUID court, une ligne ; plus d'e-mail dans l'envoi du mail de réservation ; `\n` retirés |
| `BaseBillet/triggers.py` | `\n` retirés |
| `BaseBillet/validators.py` | `validate` sans le champ `email` |
| `BaseBillet/models.py` | Métadonnées Stripe en JSON sur une ligne |
| `BaseBillet/views.py` | Adhésion : noms des champs seulement ; `admin_my_cards` : UUID court |
| `ApiBillet/views.py` | Webhook Stripe : type et id au lieu du payload entier ; adhésion en UUID court ; ligne vide retirée |
| `PaiementStripe/views.py` | Lignes vides et `----` retirées |
| `booking/tasks.py`, `onboard/tasks.py`, `wsocket/consumers.py`, `fedow_connect/fedow_api.py`, `Administration/admin_tenant.py` | E-mails → UUID court ou `@domaine` ; `\n` retirés |
| `tests/pytest/test_logs_sans_email.py` | Nouveau : machine à état sans e-mail ni `\n` ; mail de connexion sans lien ni e-mail hors DEBUG |

Reste à faire (hors de ce chantier) : les logs d'accès gunicorn et nginx écrivent l'URL demandée, donc `/emailconfirmation/<jeton>` quand quelqu'un clique sur son lien ; `crowds/tasks.py` écrit l'adresse en cas d'échec d'envoi ; les `{request.user}` de `kiosk/views.py` (comptes de borne, en erreur seulement).

---

## Comment tester (a la main) / Manual test

### Test 1 — lien de connexion
1. Demander un lien de connexion sur `https://lespass.tibillet.localhost/` (en dev, DEBUG=True : le lien apparaît, c'est voulu).
2. En prod (DEBUG=False), les logs Celery montrent `connexion_celery_mailer : adresse @domaine`, et aucune ligne `/emailconfirmation/`.

### Test 2 — réservation
1. Réserver un événement gratuit.
2. Les logs montrent `START MACHINE A ETAT pre_save_signal_status RESERVATION 1d8c9a68 : … to …` sur une seule ligne, sans e-mail, sans ligne vide autour.

### Dans OpenObserve
- `SELECT * FROM conteneurs WHERE str_match(message, '@') ORDER BY _timestamp DESC` : il ne doit rester que des `@domaine`.

### Verifs automatiques
`pytest tests/pytest/test_logs_sans_email.py tests/pytest/test_logging_filters.py tests/pytest/test_identifiants_pour_les_logs.py`
