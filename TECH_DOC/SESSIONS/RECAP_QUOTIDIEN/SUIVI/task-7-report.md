# Tâche 7 — rapport : brancher le récap sur le filet J, fusion avec le mail du Z

Statut : DONE (doutes mineurs en fin de rapport)

## Fait

### Code
- `comptabilite/tasks.py:1067-1090` — `generer_les_clotures_automatiques_du_lieu` : après la boucle H/M/A, dans le même `tenant_context` et dans le même `try` (le `except Exception: logger.exception(...); raise` existant journalise et relance : rien n'est avalé), import local de `envoyer_le_recap_du_lieu_si_c_est_l_heure`, calcul de `seuil_d_aujourd_hui` et `seuil_de_la_veille` par `_seuil_du_filet_d_un_jour(jour, fuseau_du_lieu, configuration.heure_de_fermeture)` (jour = `maintenant_local.date()`, et la veille), puis l'appel. Commentaire FALC FR + EN.
- `comptabilite/tasks.py:820-823` — `demander_l_email_automatique_si_configure` : `if cloture.niveau == ClotureCaisse.NIVEAU_JOURNALIER: return` en tête, commentaire au présent. H/M/A inchangés. `envoyer_email_cloture_demande` non touché.
- Textes corrigés (au présent, sans historique) :
  - en-tête de `comptabilite/tasks.py` : nouveau bloc « LES EMAILS DE CLÔTURE » (l.7-17), règle de la mise en service (H/M/A sans mail, J non jointes au récap), FLUX (le récap après filet + H/M/A) ;
  - docstring de `demander_l_email_automatique_si_configure` (l.800) : H, M ou A ; une J part dans le récap ; mise en service ;
  - docstring de `generer_les_clotures_automatiques_du_lieu` (l.986) : « puis le récap du matin » ;
  - docstring de `envoyer_email_cloture` (l.1134) : H, M ou A ; la J n'a plus d'email séparé ;
  - `comptabilite/pdf.py:13-19` (en-tête FLUX) : admin, `_envoyer_l_email_de_la_cloture` (H/M/A + bouton caisse), `envoyer_le_recap` ;
  - `laboutik/views.py:3695-3697` (docstring de `CaisseViewSet.cloturer`, étape 4) et `laboutik/views.py:3815-3817` (commentaire au-dessus de l'appel) : « aucun e-mail pour une J : son Z part dans le récap du matin ». Le code de la vue n'est pas touché (`git diff laboutik/views.py` : 8 lignes de commentaires).
- `BaseBillet/models.py` : rien (libellé « Chaque jour, dans le récap du matin » et `help_text` déjà faits en tâche 1).
- `CHANGELOG/2026-10-18-recap-quotidien-admins.md` (NEUF) : format djc, Migration Oui (0235 + booking 0006), résumé bilingue, tableau des fichiers des tâches 1 à 7, `---`, 3 tests manuels (récap avec Z via `manage.py shell` et `timezone.now` patché à demain 7 h 10, avant 7 h rien, comptable en périodicité J), vérifs automatiques. Avertissement en tête : base de dev seulement, faire le Z avant (l'horloge avancée peut créer des clôtures scellées).

### Tests neufs — `tests/pytest/test_recap_quotidien.py:1740` classe `TestBranchementEtFusion`
(réutilise `_vendre_des_jus_a`, `_cloturer_a`, `_lancer_la_tache_horaire_a` de `TestZContenuDestinataires` ; `taches_celery_enregistrees` ajouté à l'import de `fabriques_panier`)
- `test_la_tache_horaire_envoie_le_recap_avec_le_filet_de_ce_matin` (l.1782) : fermeture 5 h, vente lundi 23 h, aucun Z manuel, tâche horaire mardi 7 h 10 ; `Administration.recap_quotidien.CeleryMailerClass` et `generer_pdf_cloture` remplacés (aucun mock rendu ni sérialisé) → la J du filet finit à 7 h, le mailer est appelé une fois avec `z-<n° du filet>.pdf`, le marqueur vaut le 13/10.
- `test_une_j_ne_demande_plus_de_mail_separe` (l.1815) : J créée, puis périodicité J + `rapport_emails` → `demander_l_email_automatique_si_configure` : `taches_demandees == []`.
- `test_une_h_demande_toujours_son_mail` (l.1832) : vente mercredi 7/10, tâche horaire lundi 12/10 4 h 10 → H ; périodicité H + `rapport_emails` → `[("envoyer_email_cloture", (schéma, uuid de la H))]`.

## Preuves TDD
- Avant le code (`-k TestBranchementEtFusion`) : `2 failed, 1 passed` — `test_la_tache_horaire…` : `assert 0 == 1` (mailer jamais appelé) ; `test_une_j_ne…` : une tâche `envoyer_email_cloture` demandée. `test_une_h…` vert d'emblée (non-régression : prouvé par la mutation 3).
- Après le code : `3 passed, 99 deselected`.

## Mutations (une par une, au premier plan, code restauré : `diff` avec la copie d'avant → IDENTIQUE, aucun « MUTATION » restant)
1. Appel au récap remplacé par `pass` → `test_la_tache_horaire_envoie_le_recap_avec_le_filet_de_ce_matin` FAILED (`assert 0 == 1`), les 2 autres verts.
2. Sortie J neutralisée (`if False: return`) → `test_une_j_ne_demande_plus_de_mail_separe` FAILED, les 2 autres verts.
3. Sortie pour tous les niveaux (`if True: return`) → `test_une_h_demande_toujours_son_mail` FAILED, les 2 autres verts.

## Tests existants adaptés (avant = avec le nouveau code, test non adapté)
| Test | Avant | Après |
|---|---|---|
| `test_cloture_caisse.py::test_bouton_lieu_en_periodicite_j_un_seul_email_pour_cette_j` → renommé `test_bouton_lieu_en_periodicite_j_aucun_email_separe` (l.987), attend `demandes_d_email == []` | FAILED (`assert [] == [('envoyer_email_cloture', …)]`) | PASSED |
| `test_cloture_caisse.py::test_broker_en_panne_effets_faits_avant_et_ecran_du_z_affiche` : `etats_vus_a_chaque_appel` à un seul élément (l.979) | FAILED (`[('L','AN')] == [('L','AN'), ('L','AN')]`) | PASSED |
| `test_cloture_caisse.py::test_envoi_demande_du_z_broker_en_panne_message_clair_pas_d_erreur_500` | PASSED (inchangé) | PASSED |
| `test_reprise_clotures.py::test_j_reprise_n_envoie_aucun_mail` (l.518) : périodicité hebdomadaire ; preuve par la tâche horaire du lundi 16 mars 4 h 10, qui clôture la semaine du 9 mars (finie après la mise en service du 10 mars 3 h) et demande son seul mail (la semaine du 12 janvier, historique, est clôturée sans mail) ; docstring renvoie à `test_une_cloture_finie_a_la_mise_en_service_n_est_pas_jointe` | FAILED (`assert [] == [('envoyer_email_cloture', …)]`) | PASSED |
| `test_comptabilite_celery.py::test_envoyer_email_cloture_envoie_si_config_ok` → `envoyer_email_cloture_demande` (l.240), import ajouté, ligne de périodicité retirée | PASSED, chemin mort (envoi automatique d'une J, plus jamais demandé) | PASSED |
| `test_comptabilite_exports.py::test_email_de_cloture_montre_le_chiffre_d_affaires_ttc` (l.835) et `::test_email_de_cloture_en_heure_du_lieu` (l.1121) → `envoyer_email_cloture_demande`, ligne de périodicité retirée | PASSED, chemin mort | PASSED |

## Vérification finale (un fichier à la fois, au premier plan)
Commande : `docker exec lespass_django bash -c "ulimit -v 8000000; timeout 900 poetry run pytest /DjangoFiles/tests/pytest/<fichier>.py -v"`
- `test_cloture_unique.py` : `37 passed, 2 warnings in 16.56s`
- `test_reprise_clotures.py` : `13 passed, 2 warnings in 14.72s`
- `test_comptabilite_celery.py` : `5 passed, 2 warnings in 5.88s`
- `test_cloture_caisse.py` : `30 passed, 2 warnings in 12.44s`
- `test_comptabilite_exports.py` : `22 passed, 2 warnings in 16.54s`
- `test_recap_quotidien.py` : `102 passed, 2 warnings in 16.06s`
Aucun MemoryError, aucun délai dépassé. `manage.py check` : no issues.

Point de vigilance 5 vérifié : dans `test_cloture_unique.py`, les deux tests horaires après 7 h (`…attend_le_seuil_suivant`, `…une_j_par_jour…`) passent par le récap : `WARNING Récap quotidien : aucun destinataire pour , aucun mail envoyé.` (relevé avec `-rA`), aucun PDF, aucun envoi. Aucun remplacement de mailer n'a été nécessaire.
Autres appelants hors périmètre relevés (non lancés) : `test_api_v2_comptabilite.py` (passages à 5 h et 6 h 30) et `test_lecteurs_montants_entiers.py` (5 h) — avant 7 h, le récap sort tout de suite.

## i18n
Tâche 7 : 0 chaîne `_()` ajoutée. (Chantier : chaînes des tâches 1, 3, 4, 6 — workflow i18n au mainteneur.)

## Migrations à appliquer
Aucune nouvelle en tâche 7 (celles du chantier : `BaseBillet 0235_configuration_recap_quotidien_traite_le_and_more`, `booking 0006_booking_annulee_le`, déjà appliquées en dev).

## Message de commit suggéré
```
feat(recap): récap du matin branché sur le filet J, fin du mail Z séparé
```

## Doutes
1. `laboutik/views.py` : la consigne disait « UN commentaire ». Deux textes de `cloturer` étaient faux et disaient la même chose : le commentaire au-dessus de l'appel (l.3815) et l'étape 4 de la docstring (l.3695). J'ai corrigé les deux (commentaires seulement, aucun code).
2. `ruff check` (lecture seule) sur les 7 fichiers : un seul constat, `import re` inutilisé dans `test_cloture_caisse.py:90`, déjà là avant (pas de mon fait, non corrigé).
3. Pas de mutation « récap avant le filet » (il aurait fallu déplacer le bloc) ; l'ordre est quand même couvert : si le récap passait avant le filet, la J de 7 h n'existerait pas encore et `test_la_tache_horaire…` verrait 0 appel au mailer.
4. Les deux premières éditions de `test_recap_quotidien.py` (ajout de la classe, import) ont été faites par un petit script `python3` de l'hôte (édition de texte seulement, sans toucher au `.venv` ni au projet Python). Le reste par l'outil Edit.
5. INDEX.md et l'essai réel : non faits (au coordinateur).

---

## Fix round 1

Constats : `task-7-constats-round1.md` (8 points). Toutes les commandes ont tourné dans le conteneur (y compris les `grep` de relevé). Aucune commande depuis l'hôte, rien en arrière-plan.

### Changements
1. (Important) `tests/pytest/test_comptabilite_celery.py:223` `test_envoyer_email_cloture_envoie_si_config_ok` : il teste de nouveau l'envoi AUTOMATIQUE `envoyer_email_cloture` (respecter_la_periodicite=True), cette fois sur une clôture H. La semaine de la vente du setUp est clôturée par `generer_cloture_pour_tenant(niveau=H)`, avec `timezone.now` patché au lundi suivant 5 h 10, heure du lieu, et `heure_de_fermeture = 2 h` posée dans le test (l.235-251). Elle est créée AVANT de régler les destinataires, donc aucun `.delay`. Ensuite `rapport_emails` à deux adresses et `PERIODICITE_HEBDOMADAIRE`, puis `envoyer_email_cloture(schéma, uuid de la semaine)` (l.265) : il rend True, deux destinataires, un PDF `cloture-*.pdf`, `send()` appelé une fois. Docstring de la classe `TestEmailDeCloture` revue (l.159). Imports : `datetime, time, timedelta` et `django.utils.timezone` ajoutés, `envoyer_email_cloture_demande` retiré (il ne sert plus).
2. `tests/pytest/test_recap_quotidien.py` : nouvel outil `_lancer_la_tache_horaire_avec_le_mailer_remplace_a` (l.1782 ; mailer et PDF du récap remplacés, rend le mailer). `test_la_tache_horaire_envoie_le_recap_avec_le_filet_de_ce_matin` se déroule maintenant ainsi :
   - une vente dimanche 11/10 à 23 h ;
   - la tâche horaire du lundi 12/10 à 7 h 10 crée la J du filet de lundi, finie lundi à 7 h, pile au seuil de la veille de mardi (assertion l.1821-1822) ;
   - une vente lundi à 23 h, puis la tâche horaire du mardi à 7 h 10 ;
   - le mailer de mardi ne reçoit que `z-<filet de mardi>.pdf`. La J de lundi n'est donc PAS jointe.
3. `comptabilite/tasks.py:546-551`, docstring de `creer_la_cloture_journaliere_de_la_caisse` : « Aucun e-mail n'est demandé pour cette J : son ticket Z part dans le récap du matin des admins ».
4. `comptabilite/tasks.py:699-703`, « APPELÉE PAR » de `mise_en_service_du_lieu` : `Administration/recap_quotidien.py` `clotures_j_a_joindre` y est ajouté.
5. `comptabilite/tasks.py:1095-1098`, log de l'except : « Échec des clôtures automatiques ou du récap du matin du lieu. » Le `raise` est inchangé. Aucun test ne lit ce message (vérifié par `rg`).
6. `tests/pytest/test_cloture_caisse.py:938-948`, docstring de `test_broker_en_panne…` : le lieu a un destinataire en périodicité journalière ; seule l'impression passe par le broker, une J ne demande pas d'e-mail.
7. `CHANGELOG/2026-10-18-recap-quotidien-admins.md` :
   - l.18 : une erreur de CALCUL ne pose pas le marqueur et le récap est retenté. Une erreur de PDF ou d'envoi arrive après le marqueur : pas de nouvel essai ce jour-là ;
   - l.46 : ne pas faire l'essai un dimanche, ni le dernier jour d'un mois ou d'une année ;
   - l.72 : relancer seulement le `with patch(...)` et l'appel, SANS les lignes de remise à vide ;
   - l.79 : les libellés tels que l'admin FR les affiche, relevés dans `locale/fr/LC_MESSAGES/django.po` : « Emails destinataires pour les rapports de clôture », « Fréquence d'envoi du rapport de clôture » = « Chaque jour, dans le récap du matin » (ce msgid FR n'est pas encore dans le .po, il s'affiche tel quel) ;
   - tableau : une ligne à part pour `test_comptabilite_celery.py` (envoi automatique H).
8. `tests/pytest/test_reprise_clotures.py:555-561` : assertion que la clôture H de la semaine du 12/01 au 19/01 existe (`_la_cloture_d_une_periode`). Docstring l.524 au présent : « Les J ne demandent pas de mail séparé ».

### Mutations (une par une, au premier plan, code remis ; `grep MUTATION comptabilite/tasks.py` → rien)
- Point 1 : `if respecter_la_periodicite and niveau_hors_periodicite:` remplacé par `if respecter_la_periodicite:` → `test_envoyer_email_cloture_envoie_si_config_ok` FAILED (`assert False is True`), `…skip_si_pas_de_config` PASSED. Remis → vert.
- Point 2 : `aujourd_hui - timedelta(days=2)` pour `seuil_de_la_veille` → `test_la_tache_horaire_envoie_le_recap_avec_le_filet_de_ce_matin` FAILED (`assert ['z-1.pdf', 'z-3.pdf'] == ['z-3.pdf']` ; le n° 2 est la H de la semaine du 5/10, même chaîne), les 2 autres PASSED. Remis → vert.

### Tests relancés (un fichier à la fois)
Commande : `docker exec lespass_django bash -c "ulimit -v 8000000; timeout 900 poetry run pytest /DjangoFiles/tests/pytest/<fichier>.py -v"`
- `test_comptabilite_celery.py` : `5 passed, 2 warnings in 6.05s`
- `test_recap_quotidien.py` : `102 passed, 2 warnings in 16.68s`
- `test_reprise_clotures.py` : `13 passed, 2 warnings in 14.73s`
- `test_cloture_caisse.py` : `30 passed, 2 warnings in 12.84s`
- `test_cloture_unique.py` : `37 passed, 2 warnings in 16.74s` (`tasks.py` est touché)
- `test_comptabilite_exports.py` : `22 passed, 2 warnings in 16.22s`
`ruff check` en lecture seule sur `comptabilite/tasks.py`, `test_comptabilite_celery.py`, `test_recap_quotidien.py`, `test_reprise_clotures.py` : All checks passed. Aucun MemoryError, aucun délai dépassé.

### Doute
- Le test du point 1 se cale sur l'horloge réelle : la vente du setUp est encaissée maintenant, et la semaine est clôturée au « lundi suivant 5 h 10 ». Il marche quel que soit le jour où il tourne : le lundi suivant est toujours après aujourd'hui, et à 5 h 10 le filet de 4 h de ce lundi est passé, puisque la fermeture est fixée à 2 h dans le test.
