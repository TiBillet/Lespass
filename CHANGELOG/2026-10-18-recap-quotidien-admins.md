# Récap du matin des admins, avec les tickets Z / Admins' morning recap, with the Z tickets

**Date :** 2026-10-18
**Migration :** Oui — `BaseBillet/0235_configuration_recap_quotidien_traite_le_and_more` et `booking/0006_booking_annulee_le` (TENANT_APPS : passent sur chaque lieu) — `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas`
**Ordre de déploiement :** 1) migrer (`migrate_schemas`, exécuteur standard) AVANT de recharger le code : les colonnes neuves (Reservation, Membership, Event, Booking, Configuration) font planter chaque `save()` / `create()` tant qu'elles n'existent pas ; 2) puis `supervisorctl restart gunicorn daphne celery`. Sans redémarrer Celery, l'ancien code tourne : ancien mail du Z, pas de récap.
**Avant déploiement :** vérifier qu'aucun lieu n'est sans domaine primaire (`Client` sans `Domain(is_primary=True)`, hors `public` et `WAITING_CONFIG`) : sinon le récap de ce lieu plante chaque heure.
**Attention, destinataires :** en périodicité « Journalier », `rapport_emails` reçoit désormais tout le récap (noms et e-mails des adhérents, réservations, annulations, bénévoles), et tous les destinataires sont en `To:` (décision du mainteneur). Prévenir les lieux concernés si utile.

## Resume / Summary
**Quoi / What :** chaque matin, un mail par lieu aux admins résume ce qui s'est passé la veille (minuit à minuit, heure du lieu) : nouvelles adhésions et adhésions en attente, réservations, réservations de ressources, inscriptions bénévoles, événements et propositions, financement participatif (projets, lignes de budget, contributions, votes, participations), remboursements et annulations, avec les tickets Z de la veille en pièce jointe (PDF). Au plus 10 lignes par rubrique, puis « et N autres », et un lien vers l'admin. Aucun mail sans contenu. Le récap part à la fin de la sous-tâche horaire des clôtures du lieu, après le filet J : à 7 h passées (heure du lieu) et une fois le seuil du Z d'aujourd'hui passé, une seule fois par jour. Le mail séparé du Z journalier disparaît : en périodicité « Journalier », les adresses de `rapport_emails` reçoivent le récap. Les mails des clôtures semaine, mois et année et le bouton « Envoyer par e-mail » de la caisse ne changent pas.
/ Every morning, one mail per venue tells the admins what happened yesterday (venue's local day), section by section, with yesterday's Z tickets attached. No mail without content. It runs at the end of the venue's hourly closure sub-task, after the J net, once a day after 7 am. The separate daily Z mail is gone: with the "Daily" periodicity, `rapport_emails` receive the recap. Week, month and year closure mails and the register's e-mail button are unchanged.

**Pourquoi / Why :** les admins d'un lieu n'avaient aucune vue d'ensemble de la veille sans ouvrir chaque menu de l'admin ; le Z journalier arrivait seul, dans un autre mail. Un seul mail, au même moment, quand il y a quelque chose à dire. Spec : `TECH_DOC/SESSIONS/RECAP_QUOTIDIEN/SPEC.md`.
/ Admins had no overview of yesterday without opening every admin menu, and the daily Z came alone in another mail. One mail, at the same time, only when there is something to say.

Points notables :
- « créé hier » et « annulé hier » se lisent sur des dates fiables : `created_at` (`auto_now_add`) sur `Event` et `Reservation`, `annulee_le` sur `Reservation`, `Membership` et `Booking` (posée par les méthodes d'annulation et par `BookingAdmin.save_model`) ;
- le marqueur `Configuration.recap_quotidien_traite_le` est posé par `update()` (jamais `configuration.save()`, qui appelle Stripe), avant l'envoi, même quand rien ne part ;
- destinataires : les admins du lieu, sinon `Configuration.email` ; plus `rapport_emails` en périodicité « Journalier » ; sans doublon. Aucun destinataire : un avertissement dans les logs, pas de mail ;
- le mail est rendu dans la langue du lieu ;
- une erreur remonte toujours (Sentry). Une erreur dans le CALCUL du récap (rubriques, Z à joindre, destinataires) arrive avant le marqueur : il n'est pas posé, le récap est retenté au passage suivant. Une erreur de PDF ou d'envoi arrive après le marqueur : pas de nouvel essai ce jour-là (un mail perdu vaut mieux qu'un doublon chaque heure).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Event.created_at`, `Reservation.created_at` et `annulee_le`, `Membership.annulee_le`, `Configuration.recap_quotidien_traite_le` ; libellé du choix « Journalier » et `help_text` de `rapport_emails` ; `annulee_le` posée à l'annulation d'une réservation et de son dernier billet |
| `BaseBillet/migrations/0235_configuration_recap_quotidien_traite_le_and_more.py` | Nouvelle migration |
| `booking/models.py` | `Booking.annulee_le`, posée par `cancel_and_refund_booking` |
| `booking/migrations/0006_booking_annulee_le.py` | Nouvelle migration |
| `BaseBillet/views.py` | `MembershipMVT.cancel` pose `annulee_le` |
| `Administration/admin/resources.py` | `BookingAdmin.save_model` pose `annulee_le` quand l'admin passe un booking à annulé |
| `Administration/recap_quotidien.py` | Nouveau : fenêtre de la veille, rubriques, Z à joindre, destinataires, envoi (`envoyer_le_recap_du_lieu_si_c_est_l_heure`) |
| `BaseBillet/templates/emails/recap_quotidien.html` | Nouveau : gabarit du mail |
| `comptabilite/tasks.py` | `generer_les_clotures_automatiques_du_lieu` appelle le récap après le filet J et les H / M / A ; `demander_l_email_automatique_si_configure` ne demande plus de mail pour une J ; en-tête et docstrings |
| `comptabilite/pdf.py` | En-tête : le PDF sert aussi au récap |
| `laboutik/views.py` | Commentaires de `CaisseViewSet.cloturer` : plus de mail pour le Z de la caisse |
| `tests/pytest/test_recap_quotidien.py` | Nouveau : dates, annulations, rubriques, Z et destinataires, envoi, branchement et fusion, vérifiés par mutation |
| `tests/pytest/test_cloture_caisse.py` | `test_bouton_lieu_en_periodicite_j_aucun_email_separe` (renommé, zéro demande de mail) ; broker en panne : une seule demande (l'impression) |
| `tests/pytest/test_reprise_clotures.py` | `test_j_reprise_n_envoie_aucun_mail` : périodicité hebdomadaire, preuve par la tâche horaire du lundi suivant |
| `tests/pytest/test_comptabilite_celery.py` | `test_envoyer_email_cloture_envoie_si_config_ok` : envoi automatique d'une clôture hebdomadaire en périodicité hebdomadaire |
| `tests/pytest/test_comptabilite_exports.py` | Les tests du mail d'une J passent par `envoyer_email_cloture_demande` (le gabarit reste celui du bouton de la caisse) |
| `Administration/management/commands/_demo_data_v2_recap.py` | Nouveau : l'activité d'hier de quatre personnes de démo (`recap-alice/bruno/chloe/david@example.com`) et l'envoi du récap de démo |
| `Administration/management/commands/demo_data_v2.py` | `_seed_ventes_de_la_veille` écrit cette activité avant la J ; `_envoyer_le_recap_de_demo`, en dernier dans `handle` (sauté avec `--no-sales`) |
| `tests/pytest/test_demo_recap_de_la_veille.py` | Nouveau : quatre personnes datées d'hier, J et export, rubriques, idempotence, planning absent, récap envoyé à l'admin |

i18n : nouvelles chaînes traduisibles (msgid en français) dans `BaseBillet/models.py`, `Administration/recap_quotidien.py` et le gabarit ; workflow i18n à lancer par le mainteneur.

---

## Comment tester (a la main) / Manual test

**Base de dev uniquement.** Le test avance l'horloge à demain 7 h 10 : la tâche horaire peut créer des clôtures (chaîne scellée). Faire le Z de la caisse AVANT, et ne plus vendre ensuite : le filet n'a alors rien à clôturer. Ne pas faire l'essai un dimanche, ni le dernier jour d'un mois ou d'une année : « demain » serait un lundi ou un 1ᵉʳ, et l'horloge avancée clôturerait la semaine, le mois ou l'année en cours.

### Test 1 — le récap part, avec le Z
1. Sur un lieu de dev (ex. `lespass`), connecté·e en `admin@admin.com` : prendre une adhésion, réserver un événement, créer un événement ; à la caisse, vendre un article puis « Clôturer » (le Z).
2. Lancer la sous-tâche horaire du lieu, horloge à demain 7 h 10 heure du lieu :
   ```python
   # docker exec -it lespass_django poetry run python /DjangoFiles/manage.py shell
   from datetime import datetime, time, timedelta
   from unittest.mock import patch
   from django.utils import timezone
   from django_tenants.utils import tenant_context
   from BaseBillet.models import Configuration
   from Customers.models import Client
   import comptabilite.tasks

   lieu = Client.objects.get(schema_name="lespass")
   with tenant_context(lieu):
       Configuration.objects.update(recap_quotidien_traite_le=None)
       Configuration.clear_cache()
       fuseau = Configuration.get_solo().get_tzinfo()
   demain = timezone.localtime(timezone.now(), fuseau).date() + timedelta(days=1)
   demain_7h10 = datetime.combine(demain, time(7, 10), tzinfo=fuseau)
   with patch("django.utils.timezone.now", return_value=demain_7h10):
       comptabilite.tasks.generer_les_clotures_automatiques_du_lieu("lespass")
   ```
3. Attendu : un mail « [nom du lieu] Le récap du JJ/MM/AAAA » dans la boîte de dev (https://mailpit.tibillet.localhost), adressé aux admins du lieu ; les rubriques remplies, chacune avec son lien vers l'admin ; le PDF du Z en pièce jointe.
4. Relancer seulement les deux dernières lignes du bloc (le `with patch(...)` et l'appel), SANS les lignes qui remettent le marqueur à vide : aucun nouveau mail.

### Test 2 — avant 7 h, rien
1. Remettre le marqueur à vide (étape 2 du test 1), remplacer `time(7, 10)` par `time(6, 10)`.
2. Attendu : aucun mail, `recap_quotidien_traite_le` reste vide.

### Test 3 — le comptable reçoit le récap, plus de mail séparé du Z
1. Admin → Configuration : « Emails destinataires pour les rapports de clôture » = une adresse, « Fréquence d'envoi du rapport de clôture » = « Chaque jour, dans le récap du matin ».
2. À la caisse : une vente, « Clôturer ». Attendu : aucun mail du Z dans mailpit.
3. Bouton « Envoyer par e-mail » sur l'écran du Z : le mail du Z part tout de suite (inchangé).
4. Test 1, étape 2 : le récap arrive aussi à l'adresse de `rapport_emails`.

### Test 4 — la démo du flush : l'activité d'hier et le récap envoyé à l'admin
**Efface la base de dev partagée** : seulement avec l'accord du mainteneur.
1. `docker exec lespass_django bash /DjangoFiles/flush.sh`. Le flush envoie un vrai mail à la fin : sans `EMAIL_HOST` / `EMAIL_PORT` dans le `.env` de dev, la FIN du flush plante (les données sont déjà écrites).
2. Attendu dans la sortie, au bloc « Ventes d'hier par le moteur de vente (lespass)... » : les 5 ventes de `demo-ventes@example.com`, puis l'activité des quatre personnes de démo (heures d'hier, heure du lieu) :
   - Chloé : 09:15 demande d'adhésion en attente, 09:30 inscription au planning « Festival » ;
   - Alice : 10:25 inscription au planning « Bar associatif », 22:30 adhésion payée en ligne ;
   - David : 17:50 réservation de concert annulée, 23:20 3 bières au Bar (CB) ;
   - Bruno : 22:45 un billet « What the Funk ? », 23:05 « Petite salle » payée sur place en espèces ;
   puis « + Clôture J : uuid=… ».
3. Dernière ligne du flush : « Récap envoyé à <ADMIN_EMAIL du .env> : N rubrique(s), 1 Z joint(s). »
4. Dans mailpit (https://mailpit.tibillet.localhost) : le mail « [nom du lieu] Le récap du JJ/MM/AAAA » (la date d'hier), avec les rubriques adhésions, demandes d'adhésion en attente, réservations, réservations de ressources, inscriptions de bénévoles et annulations, et le PDF du Z en pièce jointe.
5. Le vrai récap du lendemain matin part quand même : la démo ne pose pas `recap_quotidien_traite_le`. Un flush après 7 h avec Celery beat actif déclenche aussi, le jour même, un récap de la veille (sans le Z) : la démo ne pose pas le marqueur.

### Verifs automatiques
- `docker exec lespass_django bash -c "ulimit -v 8000000; timeout 900 poetry run pytest /DjangoFiles/tests/pytest/test_recap_quotidien.py -v"`
- Même commande pour `test_cloture_unique.py`, `test_reprise_clotures.py`, `test_comptabilite_celery.py`, `test_cloture_caisse.py`, `test_comptabilite_exports.py`, `test_demo_recap_de_la_veille.py`, `test_demo_ventes_de_la_veille.py`.
