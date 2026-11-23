# Logs lisibles dans la supervision / Readable logs in the monitoring

**Date :** 2026-11-23
**Migration :** Non

## Resume / Summary

**Quoi / What :**
- Chaque ligne de log de la console dit maintenant de quel lieu elle vient et quel module l'écrit : `NIVEAU [schéma] module : message`.
- Les lignes de routine de la tâche des clôtures automatiques (« received », « succeeded », des dizaines de milliers par jour) ne sortent plus. Ses erreurs sortent toujours.
- Les avertissements CSS de weasyprint ne sortent plus. Ses erreurs sortent toujours.
- Les logs n'écrivent plus de tag NFC entier ni d'e-mail sur les parcours carte, caisse, kiosque et paiement : la carte devient `89EE…` (4 caractères), la personne ou le wallet devient l'UUID court (8 caractères). Le numéro imprimé et l'uuid de la carte (`qrcode_uuid`, dont les 8 premiers caractères SONT le numéro imprimé) passent aussi par `carte_courte()`.
- Une ligne d'événement par paiement NFC ou QR (accepté, refusé avec sa raison, en échec) et par carte scannée sans compte.
- / Console lines show the venue and the module. Routine Celery lines and weasyprint CSS warnings are dropped. No full NFC tag nor email on card and payment paths. One event line per NFC/QR payment and per card scanned without an account.

**Pourquoi / Why :**
Les logs de tous les serveurs arrivent dans OpenObserve. Sans le lieu, sans identifiant, et noyés dans le bruit, ils ne permettaient pas de comprendre un paiement refusé (cas d'une adhérente CLAF à la Biocoop, novembre 2026).
/ All logs reach OpenObserve. Without venue, identifiers, and with heavy noise, a refused payment could not be understood.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/settings.py` | Format `console` avec le schéma et le module ; filtre `sans_routine_celery` ; logger `weasyprint` en ERROR |
| `TiBillet/logging_filters.py` | Nouveau : filtre des lignes de routine Celery |
| `TiBillet/identifiants_pour_les_logs.py` | Nouveau : `carte_courte()` et `uuid_court()` |
| `BaseBillet/views.py` | Lignes `evenement=paiement_nfc`, `evenement=paiement_qr`, `evenement=carte_scannee_sans_compte` ; le POST complet de `valid_payment` n'est plus loggé ; e-mails remplacés par l'UUID court |
| `laboutik/views.py`, `laboutik/carte_primaire_ancien_fedow.py`, `QrcodeCashless/admin.py`, `QrcodeCashless/services.py`, `kiosk/views.py`, `kiosk/validators.py`, `kiosk/credit.py`, `fedow_connect/services.py`, `fedow_connect/fedow_api.py`, `AuthBillet/utils.py`, `BaseBillet/validators.py`, `Administration/admin_tenant.py` | Tags et e-mails raccourcis dans les appels `logger` |
| `tests/pytest/test_logging_filters.py`, `tests/pytest/test_identifiants_pour_les_logs.py` | Nouveaux tests |
| `tests/pytest/test_qrcode_ecrit_la_vente.py` | 2 tests : ligne d'événement NFC refusée et acceptée, sans tag ni e-mail |

Reste à faire (hors de ce chantier) : les e-mails des tâches d'envoi de mail (`BaseBillet/tasks.py`, `booking/tasks.py`, `crowds/tasks.py`) et les messages d'exception qui citent un tag (`CarteInconnueDeFedow`, `CarteDUnLieuNonMigre`).

---

## Comment tester (a la main) / Manual test

### Test 1 — format et lieu
1. Ouvrir une page d'un lieu, par exemple `https://lespass.tibillet.localhost/`.
2. Dans les logs du serveur, une ligne écrite par une vue commence par `INFO [lespass] BaseBillet.views : …`.
3. En dev (daphne), les lignes de `django.request` et `django.channels.server` disent `[public]` : elles sont écrites hors du fil de la requête. En prod (gunicorn), elles portent le lieu.

### Test 2 — paiement NFC refusé puis accepté
1. Générer un QR code de 12,50 € sur `/qrcodescanpay/get_generator/`, lire la carte de démo `52BE6543` (solde 12 €).
2. Le log montre `evenement=paiement_nfc resultat=refuse raison=solde_insuffisant carte=52BE… user=… wallet=… montant_centimes=1250 solde_centimes=1200`.
3. Générer un QR code de 1 €, relire la carte : `evenement=paiement_nfc resultat=accepte … debite_centimes=100`.
4. Côté Fedow, la même seconde : `evenement=transaction resultat=acceptee route=qrcodescanpay … expediteur=<même wallet>`.

### Test 3 — bruit retiré
1. Lancer `cron_clotures_automatiques.delay()` depuis un shell.
2. Les logs Celery montrent le cron, mais aucune ligne `generer_les_clotures_automatiques_du_lieu[…] received/succeeded`.

### Dans OpenObserve
- `SELECT * FROM conteneurs WHERE str_match(message, 'evenement=paiement_nfc') ORDER BY _timestamp DESC`
- Recouper une personne : l'UUID court de `user=` est le début de l'URL de sa fiche admin.

### Verifs automatiques
`pytest tests/pytest/test_logging_filters.py tests/pytest/test_identifiants_pour_les_logs.py tests/pytest/test_qrcode_ecrit_la_vente.py -k "ligne_d_evenement or filters or identifiants"`
