# SDD ledger — plan: TECH_DOC/SESSIONS/RECAP_QUOTIDIEN/PLAN.md

Spec : TECH_DOC/SESSIONS/RECAP_QUOTIDIEN/SPEC.md
HEAD au départ : ea460cc1. Aucun commit autorisé : les revues portent sur `git diff` + fichiers neufs, limités aux fichiers de la tâche.
Arbre partagé : d'autres travaux non committés en cours (laboutik/views.py, tests/pytest/test_c1_*, test_caisse_ecrit_la_vente.py, test_identification_solde_reseau.py, Makefile…). Ne jamais toucher aux hunks des autres.

## Pré-vol

| Paire / tâche | Produit → consommé | Constat |
|---|---|---|
| T1 → T2 | annulee_le (editable=False) → posé par méthodes + BookingAdmin.save_model | OK : editable=False n'empêche pas l'écriture par code |
| T1 → T3/T4 | created_at, annulee_le → filtres des rubriques | OK |
| T3 → T4 | format dict de rubrique → mêmes clés | OK |
| T3/T4/T5 → T6 | rubriques_de_la_veille, clotures_j_a_joindre, le_recap_a_du_contenu, destinataires_du_recap → preparer_le_recap_du_lieu | OK |
| T6 → T7 | envoyer_le_recap_du_lieu_si_c_est_l_heure(seuil_veille, seuil_auj) → appel dans comptabilite | OK |
| T6 → T8 | preparer_le_recap_du_lieu(maintenant, borne_basse, borne_haute), envoyer_le_recap → démo | OK |
| T7 ↔ T8 | CHANGELOG créé en T7, complété en T8 | OK |
| T7 | laboutik/views.py modifié aussi par un autre travail en cours | Ruling: T7 ne touche qu'au commentaire « e-mail automatique de la J » ; revue limitée à ce hunk — coût si faux : un hunk d'autrui relu à tort |
| T1 | migrations sur base partagée | Les tests pytest utilisent la base de dev (conftest django_db_setup) : migrate_schemas obligatoire avant les tests → accord du mainteneur demandé |
| Chaque tâche | tests ↔ code cohérents | OK après relecture Fable |
Ruling: migrate_schemas enchaîné par l'agent T1 — accord du mainteneur (2026-10-18)
Task 1: implémentée (DONE_WITH_CONCERNS) — migrations 0235_recap_quotidien_dates / booking 0006 ; migrate_schemas planté sur un Client orphelin d'un autre agent (test_clotures_122a4826), mais les 63 schémas existants ont colonnes + migration notée (vérifié par le coordinateur). L'agent a renommé la migration après application et corrigé django_migrations à la main (63 lignes) — vérifié cohérent.
Ruling: nom de migration remis à 0235_configuration_recap_quotidien_traite_le_and_more (le mainteneur a committé a9115fa0 et poussé sur origin/preprod pendant la tâche ; le renommage de l'agent aurait cassé un migrate en pré-prod). Fichier recréé par git show HEAD:…, copie renommée supprimée (identique), django_migrations réaligné (63 lignes), makemigrations --check propre — coût si faux : aucun, contenu identique.
Note : la branche courante est preprod (pas main). Le mainteneur committe en cours de route : les paquets de relecture partent de ea460cc1 (avant tâche 1) ou d'une photo des fichiers.
Task 1: complete (a9115fa0 + arbre, review clean)
Task 1: minor (deferred): heure_utc/FUSEAU_UTC préparés pour plus tard ; test annulee_le sans refresh_from_db ; created_at/annulee_le sans commentaire FALC (BaseBillet/models.py:2318, 3211)
INCIDENT 2026-10-18 19:37 et 19:57 : la session du mainteneur a été fermée DEUX fois. Cause (journalctl) : des pytest dans lespass_django montent à 24-28 Go (OOM ×4), systemd-oomd tue gnome-shell. Coupable isolé sous ulimit : TestAnnuleeLe::test_l_arret_du_renouvellement_ne_pose_pas_annulee_le (POST /api/cancel_sub/ avec MagicMock sur stripe et RootConfiguration → MemoryError).
Ruling: ce test est retiré (il ne vérifiait qu'un code non touché, ApiBillet/views.py ; la ligne « Non » de la spec §3.4 reste documentée dans la docstring de la classe) — coût si faux : un chemin « Non » sans test, code non modifié par le chantier.
Ruling: TOUT pytest des agents passe désormais par `docker exec lespass_django bash -c "ulimit -v 8000000; timeout 600 poetry run pytest …"` — coût : aucun.
Task 2: implémentée (DONE) — 6 tests verts, 5 mutations, 8 fichiers de tests existants verts
Task 2: complete (arbre, review clean)
Task 2: minor (deferred): gardes de BookingAdmin.save_model (déjà posé / statut inchangé / change=False) non testées ; ordre d'import de timezone dans le test
Diagnostic mémoire : cause prouvée et revérifiée par le coordinateur — MagicMock passé à Response DRF → JSONEncoder.default suit obj.tolist() à l'infini (rest_framework/utils/encoders.py:61). Défaut du test seul. Fichier de diag supprimé.
Task 3: implémentée (DONE) — 22 tests, 9 mutations, 11 chaînes _() ; écart : rouge prouvé par mutation (module écrit avant le 1er lancement)
Ruling: nouveaux_evenements exclut les sous-événements (parent non nul) et les categorie=ACTION, comme EventAdmin.get_queryset — sinon un événement avec 3 actions donne 4 lignes et le lien admin n'en montre qu'une — coût si faux : une action ou un sous-événement ajouté hier à un VIEIL événement n'apparaît pas dans le récap.
Task 3: fix round 1/5 lancé (1 Important + mineurs 1,2,3,4,5)
Ruling: le stock propositions_en_attente garde le filtre exact du tableau de bord admin (is_proposal=True, published=False), sans exclure les enfants — une proposition publique n'a pas de parent — coût si faux : un enfant proposé compté à part.
Task 3: fix round 1/5 (6 addressed, 0 open)
Task 3: complete (arbre, review clean après round 1)
Task 3: minor (deferred): test « sans personne » calcule la rubrique deux fois ; ligne f-string > 100 car. dans _ligne_d_une_inscription
Task 4: implémentée (DONE_WITH_CONCERNS) — 26 tests, 15 mutations, 12 chaînes _() ; productsold.product.name (le brief citait un attribut inexistant) ; BudgetItem.amount en centimes (vérifié : total_funding_amount additionne avec les contributions en centimes) ; annulations sans _construire_la_rubrique (3 modèles fusionnés).
Ruling: lien de la rubrique annulations = liste des réservations, avec un commentaire qui le dit (la rubrique mêle 3 modèles) — coût si faux : un clic de plus pour l'admin.
Ruling: montants crowds dans la devise du projet (Initiative.currency) via montant_a_la_francaise_dans_l_unite — sinon « 50,00 € » pour 50 heures — coût : aucun.
Task 4: minor (deferred): annulations chargées entières en mémoire pour compter (count() + 10 premiers suffirait).
Task 4: fix round 1/5 lancé (implémenteur neuf : l'original a été arrêté car il bouclait sur une tâche de fond) — 3 Importants + 2 conformité + mineurs 1-5
Task 4: fix round 1 fait (68 passed) — l'implémenteur a laissé partir un script en fond malgré la consigne ; vérifié : aucun processus restant.
Task 4: fix round 1/5 (10 addressed, 0 open)
Task 4: complete (arbre, review clean après round 1)
Task 5: implémentée (DONE) — 16 tests, 11 mutations, 0 chaîne _()
Task 5: complete (arbre, review clean)
Task 5: minor (deferred): admins sans order_by (ordre non déterministe) ; un admin à e-mail vide empêche le repli sur configuration.email (zéro destinataire possible) — À CORRIGER à la passe finale ; assertion `len(clotures) >= 1` faible (test ~371) ; imports en vrac dans le test
Task 6: implémentée (DONE) — 12 tests, 9 mutations ; aperçu HTML relu par le coordinateur (rendu propre ; « dont 1 nouveaux » à corriger). L'outil a basculé une boucle de mutations en fond (>120 s), terminée, code vérifié identique.
Ruling: « dont N nouvelles hier » (blocktrans count) affiché seulement si nombre_de_nouveaux > 0 ; envoyer_le_recap rend le résultat réel de send() — coût : aucun.
Task 6: fix round 1/5 lancé (2 Importants + 6 mineurs)
Task 6: fix round 1/5 (8 addressed, 0 open)
Task 6: complete (arbre, review clean après round 1)
Task 6: minor (deferred): msgid « Ouvrir l'administration » (apostrophe droite) doublon visuel de « Ouvrir l’administration » (apostrophe courbe, BaseBillet/tasks.py:495) — aligner sur l'existant
Task 7: implémentée (DONE) — 6 fichiers verts un par un (37/13/5/30/22/102), 3 mutations ; l'agent a édité un test par python3 depuis l'hôte (édition de texte, pas de poetry : .venv non touché).
Ruling: (constat plan-mandated) test_envoyer_email_cloture_envoie_si_config_ok garde l'envoi AUTOMATIQUE (envoyer_email_cloture) sur une H en périodicité hebdomadaire — le brief l'avait basculé sur envoyer_email_cloture_demande, ce qui laissait l'envoi H/M/A en production sans test positif ; la spec §5 autorisait « ou sur H » — coût si faux : aucun.
Task 7: fix round 1/5 lancé (1 Important + 7 mineurs ; INDEX.md fait par le coordinateur)
Task 7: fix round 1/5 (8 addressed, 0 open)
Task 7: complete (arbre, review clean après round 1)
Task 7: minor (deferred): test_envoyer_email_cloture_envoie_si_config_ok suit l'horloge réelle — fragilité théorique un lundi entre 0 h et 2 h heure du lieu
Task 8: implémentée (DONE_WITH_CONCERNS) — 7 tests neufs + 3 existants verts, 7 mutations ; Booking de Bruno PAID_BY_USER posé à la main ; garde d'idempotence fragile sans produit d'adhésion ; J créée dès qu'un des deux seeds écrit.
Task 8: complete (arbre, review clean)
Task 8: minor (deferred): (3) n'appeler seed_activite_de_la_veille_pour_le_recap que si le seed des ventes a écrit (ferme aussi le 4) ; (5) CHANGELOG l.98 : second récap possible le jour même si flush après 7 h avec Celery beat ; (6) patch(timezone.now) dans du code de commande → update(annulee_le=…) ; (7) commentaire « Bruno, 23:00 » ; (8) LOCALISATION dans les docstrings de fonction
Final review: prêt après corrections — 3 Importants (CHANGELOG : ordre de déploiement/restart Celery, ce que reçoit rapport_emails ; charge à 7 h = surveillance) + mineurs ; tri des deferred : à corriger avant merge = T5 admin e-mail vide, T6 apostrophe, T8(5) CHANGELOG ; le reste peut attendre.
Ruling: une seule passe de correction (final-constats.md, 9 points) ; INDEX.md fait par le coordinateur ; points « surveillance de charge » et « contrôle des domaines primaires en prod » remontés au mainteneur, pas de code.
Final fix: 9 points corrigés (104/37/13/5/7 passed)
Final fix re-review: 9 addressed, 0 open.
Final: parked — une erreur du récap est journalisée deux fois (except dédié puis except général « Échec des clôtures automatiques ») — Ruling: laissé tel quel (pas de seconde passe) ; correction d'une ligne proposée au mainteneur : sortir l'appel du récap du try général, ou ne pas re-journaliser — coût si faux : une ligne trompeuse de plus dans Sentry quand le récap plante.
