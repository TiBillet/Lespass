### Tâche 7 : brancher le récap sur le filet J, et fusionner avec le mail du Z

**Fichiers :**
- Modifier : `comptabilite/tasks.py` — `generer_les_clotures_automatiques_du_lieu`, `demander_l_email_automatique_si_configure`, en-tête du module, docstrings de `envoyer_email_cloture`
- Modifier : `comptabilite/pdf.py` (en-tête), `laboutik/views.py` (commentaire de `CaisseViewSet.cloturer` sur « l'e-mail automatique de la J »)
- Modifier les tests : `tests/pytest/test_cloture_caisse.py`, `tests/pytest/test_reprise_clotures.py`, `tests/pytest/test_comptabilite_celery.py`, `tests/pytest/test_comptabilite_exports.py`
- Créer : `CHANGELOG/2026-10-18-recap-quotidien-admins.md` (date du jour de la livraison)
- Test : classe `TestBranchementEtFusion`

**Interfaces — consomme :** `envoyer_le_recap_du_lieu_si_c_est_l_heure` (tâche 6).

Dans `generer_les_clotures_automatiques_du_lieu`, **après** la boucle H/M/A, toujours dans le
`tenant_context` : calculer `seuil_d_aujourd_hui = _seuil_du_filet_d_un_jour(maintenant_local.date(), fuseau_du_lieu, configuration.heure_de_fermeture)` et `seuil_de_la_veille` (même appel avec `maintenant_local.date() - timedelta(days=1)`), puis import local et appel de `envoyer_le_recap_du_lieu_si_c_est_l_heure(seuil_de_la_veille, seuil_d_aujourd_hui)`.

Dans `demander_l_email_automatique_si_configure` : sortie immédiate si `cloture.niveau == ClotureCaisse.NIVEAU_JOURNALIER` (le Z journalier part dans le récap). H/M/A inchangés.

- [ ] **Étape 1 : tests qui échouent**
  - `test_la_tache_horaire_envoie_le_recap_avec_le_filet_de_ce_matin` : `heure_de_fermeture=time(5, 0)` (seuil 7 h), vente lundi 23h, **aucun** Z manuel ; tâche horaire mardi 7h10 → le filet crée la J **et** le mock du mailer reçoit son PDF.
  - `test_une_j_ne_demande_plus_de_mail_separe` : périodicité J + `rapport_emails` → `demander_l_email_automatique_si_configure(schema, j)` ne lance aucune tâche (helper `taches_celery_enregistrees` de `fabriques_panier.py`).
  - `test_une_h_demande_toujours_son_mail` (périodicité H).
- [ ] **Étape 2 : échec vérifié.** — [ ] **Étape 3 : implémenter.** — [ ] **Étape 4 : PASS.**
- [ ] **Étape 5 : adapter les tests existants** (spec §5) :
  - `test_cloture_caisse.py::test_bouton_lieu_en_periodicite_j_un_seul_email_pour_cette_j` → renommer `test_bouton_lieu_en_periodicite_j_aucun_email_separe` et attendre **zéro** demande de mail ;
  - `test_cloture_caisse.py::test_broker_en_panne_effets_faits_avant_et_ecran_du_z_affiche` → `etats_vus_a_chaque_appel` n'a plus qu'**un** élément (l'impression). `test_envoi_demande_du_z_broker_en_panne_message_clair_pas_d_erreur_500` (bouton « Envoyer par e-mail ») : inchangé ;
  - `test_reprise_clotures.py::test_j_reprise_n_envoie_aucun_mail` → périodicité **hebdomadaire**, et la preuve passe par la tâche horaire du lundi suivant à 4h10 (motif de `test_aucun_mail_pour_une_cloture_finie_avant_la_mise_en_service`, même fichier). La règle de la mise en service pour les J est désormais portée par `test_une_cloture_finie_a_la_mise_en_service_n_est_pas_jointe` (tâche 5) ;
  - `test_comptabilite_celery.py::test_envoyer_email_cloture_envoie_si_config_ok`, `test_comptabilite_exports.py::test_email_de_cloture_montre_le_chiffre_d_affaires_ttc` et `::test_email_de_cloture_en_heure_du_lieu` → passer par `envoyer_email_cloture_demande` (le gabarit reste celui du bouton de la caisse).
- [ ] **Étape 6 : vérifier les tests horaires existants** (point de vigilance 5) : `make test ARGS="tests/pytest/test_cloture_unique.py tests/pytest/test_reprise_clotures.py tests/pytest/test_comptabilite_celery.py tests/pytest/test_cloture_caisse.py tests/pytest/test_comptabilite_exports.py tests/pytest/test_recap_quotidien.py"` → tout vert. Tests horaires existants qui tournent **après 7h** heure locale et joignent une J
  (relevé du 2026-10-18) : `test_cloture_unique.py::test_filet_apres_un_z_la_vente_du_lendemain_soir_attend_le_seuil_suivant`
  (19 h) et `test_cloture_unique.py::test_filet_ne_cree_qu_une_j_par_jour…` (16 h). Leur schéma n'a
  ni admin ni `Configuration.email` → `logger.warning`, aucun PDF, aucun envoi. Tous les autres
  appels de la tâche horaire sont avant 7h. Si l'un échoue, remplacer
  `Administration.recap_quotidien.CeleryMailerClass` dans ce test, jamais affaiblir le code.
- [ ] **Étape 7 : CHANGELOG** au format `djc` (résumé bilingue, « Migration : Oui » avec les deux migrations, `---`, scénarios de test manuel : un lieu de dev, des objets d'hier, `generer_les_clotures_automatiques_du_lieu` lancée à la main à 7h via `manage.py shell` avec `timezone.now` patché, mail vu dans la boîte de dev). Mettre à jour [INDEX.md](INDEX.md).
- [ ] **Étape 8 : rapport final** : mutations vues échouer, nombre de chaînes traduisibles ajoutées (workflow i18n au mainteneur), migrations à appliquer, demande d'accord pour lancer la suite complète.
- [ ] **Étape 9 : commit suggéré** : `feat(recap): récap du matin branché sur le filet J, fin du mail Z séparé`.

---

