# Passe de correction finale — récap quotidien

Points 1-5 : CHANGELOG/2026-10-18-recap-quotidien-admins.md (en-tête : ordre de déploiement, vérification domaine primaire, destinataires `rapport_emails` ; test 4 : mail réel du flush, flush après 7 h avec beat actif).
Point 6 : comptabilite/tasks.py (~l.1091-1103) : try/except dédié autour de l'appel du récap, logger.exception("[schema] Échec du récap du matin.") puis raise ; message général = clôtures seules.
Point 7 : Administration/recap_quotidien.py (envoyer_le_recap_du_lieu_si_c_est_l_heure, pose du marqueur) : filter().exclude().update(), return False si 0 ligne. Test : test_un_marqueur_pose_entre_la_lecture_et_la_pose_n_envoie_rien.
Point 8 : destinataires_du_recap : admins nettoyés d'abord, repli sur configuration.email si la liste nettoyée est vide. Test : test_un_seul_admin_a_email_vide_laisse_le_mail_du_lieu.
Point 9 : gabarit l.51 et l.94 : apostrophe courbe. Aucune assertion de test ne le cherchait.

Mutations (code remis, vérifié par diff) :
- 7 : retrait de la ligne .exclude(...) -> 1 failed (le nouveau test), 103 passed.
- 8 : `if len(destinataires) == 0:` remplacé par `if False:` (supprime le repli) -> 4 failed dont le nouveau test.

ruff check --fix + format sur Administration/recap_quotidien.py : propre, rien changé.

Tests (docker exec lespass_django bash -c "ulimit -v 8000000; timeout 900 poetry run pytest /DjangoFiles/tests/pytest/<f>.py -q"):
- test_recap_quotidien : 104 passed
- test_cloture_unique : 37 passed
- test_reprise_clotures : 13 passed
- test_comptabilite_celery : 5 passed
- test_demo_recap_de_la_veille : 7 passed
Chaînes i18n : msgid « Ouvrir l’administration » désormais identique à l'existant (-1 chaîne nouvelle).
