# Les lecteurs de la caisse sur la clôture unique et les ventes (chantier 05, fiche G, session G-1) / Register readers on the single closure and the sales (worksite 05, sheet G, session G-1)

**Date :** 2026-10-03 → 2026-10-04
**Migration :** **Oui** (G-1b) : `laboutik/migrations/0014_vider_le_lien_de_cloture_des_impressions.py` (données : le lien des impressions vers l'ancienne clôture est vidé), puis `laboutik/migrations/0015_impression_vers_la_cloture_unique.py` (`ImpressionLog.cloture` pointe vers `comptabilite.ClotureCaisse` ; irréversible dès qu'un Z est tracé) — `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`

## Resume / Summary
**Quoi / What :** la caisse lit et écrit la clôture unique (`comptabilite.ClotureCaisse`) et le rapport des ventes (`RapportDesVentes`) : garde de correction, bouton « Clôturer », ticket Z et son journal d'impression, ticket X, récapitulatif, sortie de caisse. L'archive fiscale LNE exporte les ventes réglées (toutes origines) avec leurs montants stockés et les clôtures uniques ; `verify_integrity` vérifie les chaînes des ventes et des clôtures. Le code mort de l'ancienne clôture est retiré. /
The register reads and writes the single closure and the sales report; the LNE fiscal archive exports settled sales and single closures; verify_integrity checks the sales and closures chains; the old closure's dead code is removed.

**Pourquoi / Why :** fiche `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-G-lecteurs.md` §2, brief `CHANTIER-05-briefs/05-G-1.md`, décisions Q-G1 à Q-G12 et relectures Opus (SUIVI §4).

Sections : G-1a (la garde de correction), G-1b (le bouton « Clôturer » et le ticket Z), G-1c (ticket X, récapitulatif, sortie de caisse), G-1d (archive, intégrité, retraits), puis les corrections des relectures (G-1b-bis, G-1c-bis, G-1d-bis), et la liste des chaînes i18n. /
Sections: G-1a to G-1d, then the review fixes, then the i18n strings.

## G-1a — La garde « correction interdite après clôture »

### Resume / Summary
- `laboutik/integrity.py` `vente_couverte_par_cloture(vente)` remplace `ligne_couverte_par_cloture` : une vente est couverte si son `numero` est au plus le plus grand `numero_derniere_vente` des J uniques. /
  A sale is covered when its number is at most the largest last-sale number of the single J.
- `laboutik/views.py` `raison_du_refus_de_correction(ligne)` : la seule règle, partagée par `corriger_moyen_paiement` (refus 400) et `detail_vente` (bouton « Corriger » caché). Seule une vente réglée, faite à la caisse, payée en espèces, CB ou chèque, pas encore couverte par une J, se corrige (Q-G1). Montant nul : refus propre.

### Tests réécrits ou retirés
| Test | Raison |
|---|---|
| `test_lecteurs_montants_entiers.py` (nouveau) `TestGardeDeCorrectionSurLaClotureUnique` | La garde lit la J unique ; ligne sans vente, vente en attente, autre origine, autre moyen refusés, avec leur message. |
| `test_corrections_fond_sortie.py` | Les lignes passent par des ventes réglées, la J par la vraie tâche, messages de refus mis à jour. |
| `test_caisse_ecrit_la_vente.py` `test_correction_moyen_apres_cloture_refusee_aucune_vente`, `test_correction_d_une_ligne_sans_vente_comme_avant` | Retirés : couverts par `test_lecteurs_montants_entiers.py` (garde sur la J unique ; ligne sans vente refusée, Q-G1). |
| `test_cloture_enrichie.py` `test_garde_correction_post_cloture` | Retiré avec l'ancien fichier : couvert par `test_lecteurs_montants_entiers.py`. |

## G-1b — Le bouton « Clôturer » crée la J unique ; le ticket Z

### Resume / Summary
- `laboutik/views.py` `cloturer` : la J est créée par `comptabilite/tasks.py` `creer_la_cloture_journaliere_de_la_caisse(responsable, point_de_vente)`, hors de toute transaction de la vue. « Rien à clôturer » → 400, sans effet. Effets T11 (tables libérées, commandes OPEN → CANCEL), puis demandes au broker protégées (ticket Z tracé `ImpressionLog.CLOTURE`, e-mail automatique). Écran du Z (`hx_cloture_rapport.html`) : chiffre d'affaires, règlements, tiroir, phrase de réconciliation, lien vers la fiche admin.
- Routes `rapport_pdf`, `rapport_csv`, `envoyer_rapport` sur la clôture unique (`comptabilite/pdf.py`, `csv_export.py`, tâche `envoyer_email_cloture_demande` : un clic ignore la périodicité). Sans destinataire : 400 et message clair.
- `ImpressionLog.cloture` → `comptabilite.ClotureCaisse` (migrations 0014, 0015) ; la tâche d'impression cherche la clôture unique (le DUPLICATA d'un Z est détecté).
- Rapport : `chiffre_affaires.par_moyen` (CA par moyen, part hors CA imputée au moyen de sa vente ; invariant Σ = CA TTC, alerte en mots si cassé). Ticket Z : lignes = CA par moyen, TOTAL = CA TTC ; recharges, cartes vidées, écarts sous le total.
- Début du service : fin de la dernière J ; sans J, heure de la première ligne d'article réglée.

### Tests réécrits ou retirés
| Test | Raison |
|---|---|
| `test_cloture_caisse.py` (réécrit, schéma dédié `test_cloture_caisse`) ; `test_cloture_totaux_corrects`, `test_cloture_nombre_transactions`, `test_cloture_rapport_json_complet`, `test_cloture_datetime_ouverture_auto`, `test_double_cloture_meme_periode` retirés | L'ancienne clôture n'est plus écrite ; remplacés par les tests du bouton sur la J unique (totaux, n° de vente, début du service, rien à clôturer, broker en panne, ticket Z). |
| `test_cloture_enrichie.py` (réécrit, schéma dédié) ; `test_cloture_journal_numero_sequentiel`, `test_cloture_journal_total_perpetuel`, `test_cloture_mensuelle`, `test_datetime_ouverture_auto`, `test_pas_de_vente_pas_de_cloture`, `test_rapport_json_14_cles` retirés | Ancien modèle ; numérotation, perpétuel, M et rapport sont ceux de la clôture unique (`test_cloture_unique.py`, `test_rapport_unique.py`). |
| `test_caracterisation_caisse.py` `test_cloture_annule_les_commandes_ouvertes_et_libere_les_tables` → `TestClotureDeCaisseT11` | Même assertion T11, en schéma dédié (Q-G12). |
| `test_lecteurs_montants_entiers.py` `TestBoutonCloturerEtTicketZSurLaClotureUnique` (nouveau) | Le bouton crée la J unique ; FK des impressions et DUPLICATA. |
| `test_rapports_cheque.py`, `test_vente_en_points.py`, `test_hors_argent_offerts.py`, `test_ventes_remontent_au_ticket_z.py` | La clôture du comptoir est la J unique : assertions lues dans `rapport_json` et sur le ticket Z unique. |
| `test_caisse_ecrit_la_vente.py` (21b retiré, 21d refusé) | Correction d'une ligne sans vente refusée (Q-G1). |

## G-1c — Ticket X, récapitulatif en cours, sortie de caisse

### Resume / Summary
- Ticket X : `RapportDesVentes(début du service, maintenant).rapport_x()` → `formatter_ticket_x` (mêmes lignes que le Z, fuseau du rapport).
- Récapitulatif en cours : toutes les sections du rapport X, l'essentiel ouvert, le reste replié (`sections_pour_affichage`, gabarit `_section_du_rapport_caisse.html`). Les historiques de l'ancien moteur restent jusqu'à G-2a.
- Sortie de caisse : lignes du tiroir (fond, espèces reçues, rendues, corrections, sorties, solde) ; `data-especes` = solde − fond.

### Tests réécrits ou retirés
| Test | Raison |
|---|---|
| `test_rapport_temps_reel.py` `TestServiceEnCours` (nouveau, schéma dédié) | Ticket X, récap et sortie sur le rapport unique, valeurs à la main. |
| `test_menu_ventes.py` `test_recap_en_cours_toutes_caisses`, `test_recap_en_cours_par_pv` retirés | Totaux et point de vente du récap couverts par `test_rapport_temps_reel.py`. |
| `test_menu_ventes.py` récap par moyen, totaux de la liste, boutons du récap | Déplacés en schéma dédié (`TestEcransVentesSurDesVentesReglees`, ventes réglées) : le service en cours dépendait de la base de dev. |
| `test_rapport_unique.py` | Ajout du CA par moyen (décor mêlé, alerte). |

## G-1d — Archive fiscale, intégrité, retraits

### Resume / Summary
- `laboutik/archivage.py` : `ventes.csv` (en-tête, totaux, `point_de_vente_uuid`, empreinte chaînée), `articles.csv` (montants **stockés**, `pricesold_uuid`, `uuid_transaction`), `reglements.csv`, `clotures.csv` (clôtures uniques, `rapport_json` en JSON canonique), toutes origines, ventes RÉGLÉES seulement. Plus de `corrections.csv` (Q-G8 : la vente CORRECTION suffit). `donnees.json` porte le rapport entier de chaque clôture. Bornes dans le fuseau du lieu ; fin figée au début de la génération ; articles et règlements lus depuis les ventes extraites. README réécrit (fichiers, bornes, parts, corrections, message de l'empreinte d'une vente, README non signé).
- Bouton « Export fiscal » dans le bandeau de la liste des clôtures (`comptabilite/admin.py`), seulement avec le module caisse. La route web plafonne la période à 365 jours, comme `archiver_donnees`.
- `verify_integrity` : chaîne des ventes + chaîne des clôtures, tous les lieux (ou `--schema`), clé lue jamais créée, sortie ≠ 0 sur anomalie, sans lieu, ou sans clé avec ventes scellées. `verify_clotures` : sortie ≠ 0 sur anomalie et `--tenant` inconnu, clé lue jamais créée, erreur d'un lieu = anomalie (la boucle continue).
- Q-G7 : tâches de clôture mortes de `laboutik/tasks.py` retirées. Code mort retiré : `laboutik/pdf.py`, `csv_export.py`, `excel_export.py`, deux gabarits, `EnvoyerRapportSerializer`, `sections_de_detail_pour_export`, `verifier_chaine` (ancienne chaîne par ligne ; l'empreinte par ligne est encore écrite jusqu'à H).
- `create_test_pos_data.py` : plus d'ancienne clôture ; lignes de démo dans un `atomic()`, retrouvées par un uuid de transaction fixe.
- Q-G9 : « Plan complet ? » derrière le bouton « Vérifier le plan » (route `verifier-le-plan/`, indicateur de chargement) ; le filet `s_assurer_que_le_plan_existe` reste à l'ouverture des trois écrans et au début du FEC d'une clôture.

### Tests réécrits ou retirés
| Test | Raison |
|---|---|
| `test_archive_lne_ventes.py` (nouveau, schéma dédié) | Tests 4, 5, 6 de la fiche ; colonnes exactes ; rapport des clôtures ; `uuid_transaction` ; empreinte recalculée depuis l'archive ; bornes et fuseau ; signature ; bouton ; plafond ; `verify_integrity` (cas limites) ; tâches mortes ; garde-fous « ancienne clôture » (écriture et liste blanche). |
| `test_archivage_fiscal_lne.py` `test_l_origine_utilisee_par_l_archivage_existe_bien` | Retiré : l'archive ne filtre plus par origine (couvert par `test_archive_lne_contient_tireuse_et_en_ligne`). |
| `test_caisse_ecrit_la_vente.py` `test_archive_lne_ligne_offerte_garde_les_valeurs_d_avant` → `..._exporte_ses_montants_stockes` ; `test_archive_lne_part_au_centime_arrondi_comme_avant` → `..._tva_stockee` | L'archive lit les montants stockés (offert : HT 0 ; part : TVA 83, plus 82). |
| `test_caisse_ecrit_la_vente.py` `test_archive_lne_ligne_sans_vente_garde_son_ht_stocke` | Retiré : l'archive exporte les ventes ; rien de l'ancien modèle à archiver (aucune caisse V2 en production). |
| `test_total_ht_ligne.py` `test_l_archive_fiscale_deduit_la_bonne_tva_de_la_ligne` → `..._exporte_le_ht_et_la_tva_stockes_de_la_ligne` ; `test_la_chaine_hmac_reste_valide` | Archive lue dans `articles.csv` ; chaîne vérifiée par `verifier_chaine_ventes`. |
| `test_rapports_cheque.py` `test_la_cloture_agregee_additionne_les_cheques_des_journalieres` | Retiré : la M/A unique relit les ventes (`test_cloture_unique.py::test_mois_calendaire_egal_ventes_du_mois`). |
| `test_rapports_cheque.py` `test_lexport_csv_de_la_cloture_montre_la_ligne_cheque`, `test_le_pdf_de_la_cloture_porte_le_total_cheque` | Retirés avec les anciens exports : exports uniques sans liste de moyens en dur, totaux = rapport (`test_comptabilite_exports.py`). |
| `test_rapports_cheque.py` `test_larchive_lne_exporte_le_vrai_montant_des_cheques` | Lit `reglements.csv` (CH 1500) et `clotures.csv` (J 4500). |
| `test_hors_argent_offerts.py` `test_l_export_csv_de_la_cloture_liste_les_offerts` ; `test_vente_en_points.py` exports csv / excel / PDF des points et des offerts (4 tests) | Retirés avec les anciens exports : sections « Offerts » et « Points » des exports uniques (`test_comptabilite_exports.py`). |
| `test_vente_en_points.py` `test_l_archive_fiscale_garde_la_vente_en_points_sans_tva` | Lit `articles.csv` et `reglements.csv` (NM). |
| `test_cloture_export.py` (fichier retiré) | Anciens exports et `sections_de_detail_pour_export` retirés : exports uniques dans `test_comptabilite_exports.py` et `test_comptabilite_celery.py`. |
| `test_integrity_hmac.py` `test_hmac_chaine_3_lignes`, `test_hmac_detecte_modification` | Retirés avec `verifier_chaine` : la chaîne vérifiée est celle des ventes (`test_archive_lne_ventes.py`, `test_rapport_unique.py`). `test_hmac_calcule_non_vide` reste (empreinte par ligne encore écrite). |
| `test_pos_retour_consigne.py` deux tests de chaîne | Vérifient `verifier_chaine_ventes` ; le singleton de la caisse est créé dans `setUp` (PIEGES 9.86). |
| `test_comptabilite_verify.py`, `test_cloture_unique.py::test_verify_clotures_detecte_un_maillon_casse_et_une_vente_alteree` | Code de sortie asserté ; `--tenant` inconnu, clé absente, erreur d'un lieu. |
| `test_plan_comptable_unique.py` trois tests « Plan complet ? » | Le verdict passe par le bouton « Vérifier le plan » ; nouveaux : pas de calcul à l'ouverture, plan chargé à l'ouverture d'un lieu neuf, refus d'un non-admin. |
| `tests/e2e/test_admin_plan_comptable.py` | Clic sur « Vérifier le plan » avant de lire le verdict. |
| `test_timezone_middleware.py` | Docstring seule (la tâche citée est retirée). |

## Corrections des relectures (G-1b-bis, G-1c-bis, G-1d-bis)

- **Recharge corrigée** (mainteneur : permise, rapport corrigé) : `_parts_deplacees_par_les_corrections` déplace la part hors CA des lignes corrigées avec l'argent, dans le CA par moyen et dans les recharges par moyen (requêtes constantes, corrections successives suivies).
- **Recharges remboursées** : `reconciliation.recharges_remboursees_en_centimes`, ligne sous le total des tickets.
- **Tiroir** : une seule écriture signée (`presentation.lignes_du_tiroir`), mêmes libellés à l'écran et sur le ticket ; tiroir calculé depuis la fin de la J même sans vente.
- **Ordre des moyens** : une seule fonction (`codes_des_moyens_dans_l_ordre`), écran et tickets.
- **Tickets en 32 caractères** : « EUR » retiré si la ligne déborde, date courte dans le pied (`Début de période: 10/03/26 10:00`), « Offerts: N art., X.XX EUR », points sans « (hors argent) » si trop long.
- **Broker** : `.delay` protégés dans `imprimer_ticket_x` et `envoyer_rapport` (503 et message).
- **Accessibilité** : titre unique des sections repliées, `aria-live` limité au total du Z, « (nouvel onglet) » ; `blocktrans` dans le récap.
- **Récap** : l'historique de l'ancien moteur titré « Lignes de caisse (hors ventes en ligne, recharges comprises) ».
- Tests ajoutés ou réécrits : `test_rapport_unique.py` (un décor par cas de Σ = CA : offert, jetons, points, écart négatif, plusieurs moyens, recharge corrigée une et deux fois, recharge remboursée, requêtes constantes, ordre à l'écran, signe de l'alerte) ; `test_rapport_temps_reel.py` (cellules du tiroir lues une à une, sortie après la J sans vente, broker, titre lu une fois, 32 caractères) ; `test_cloture_caisse.py` (broker de l'e-mail, lien et `aria-live`, pied du Z en 32 caractères) ; `test_ventes_remontent_au_ticket_z.py` (`test_la_cloture_fige_les_montants_annonces_par_le_ticket_x` compare le vrai ticket X ; `test_une_vente_en_ligne_n_entre_pas_dans_le_rapport_de_caisse` retiré, remplacé par `test_une_vente_en_ligne_entre_dans_le_ticket_x_et_dans_la_j`) ; `test_menu_ventes.py` (récap « aucune vente » et liste des ventes en schéma dédié) ; utilitaires d'écran déplacés dans `tests/pytest/fabriques_ecran.py`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/integrity.py` | `vente_couverte_par_cloture` ; `verifier_chaine` retirée |
| `laboutik/views.py` | Garde de correction, bouton « Clôturer », écran du Z, routes pdf/csv/envoi, ticket X, récap, sortie de caisse, plafond de l'export fiscal |
| `laboutik/printing/formatters.py`, `laboutik/printing/tasks.py` | Tickets X et Z sur le rapport unique ; impression du Z liée à la J unique |
| `laboutik/models.py`, migrations 0014 / 0015 | `ImpressionLog.cloture` → clôture unique |
| `laboutik/archivage.py` | Archive des ventes et des clôtures uniques |
| `laboutik/management/commands/verify_integrity.py`, `comptabilite/management/commands/verify_clotures.py` | Chaînes, code de sortie, clé lue |
| `laboutik/tasks.py`, `laboutik/serializers.py`, `laboutik/reports.py` | Code mort retiré |
| `laboutik/pdf.py`, `csv_export.py`, `excel_export.py`, 2 gabarits | Retirés |
| `laboutik/management/commands/create_test_pos_data.py` | Plus d'ancienne clôture ; `atomic()` |
| `comptabilite/rapport.py`, `presentation.py`, `tasks.py`, `admin.py`, `fec.py` | CA par moyen, corrections, recharges remboursées, tiroir, ordre, bouton Export fiscal, filet du FEC |
| `Administration/admin/laboutik.py`, gabarits du plan | Bouton « Vérifier le plan », filet à l'ouverture |
| `laboutik/templates/laboutik/partial/*` | Écran du Z, récap, sortie de caisse, section du rapport |

---

## Comment tester (a la main) / Manual test

### Test 1 — Le bouton « Clôturer » (lieu de dev, caisse)
1. Vendre deux jus en espèces et une bière en CB, puis Ventes → « Clôturer toutes les caisses » → confirmer.
2. L'écran du Z montre le chiffre d'affaires TTC, « Opérations numérotées : 3 · Clôture n° N », les règlements, le tiroir (montants signés) et la phrase de réconciliation.
3. « Voir la fiche complète » ouvre la J dans l'admin (Ventes & comptabilité → Clôtures).

### Test 2 — La correction après clôture
1. Après le Z, ouvrir le détail d'une vente de la journée : pas de bouton « Corriger ».
2. Vendre de nouveau, corriger le moyen d'une vente en espèces : la correction passe.

### Test 3 — Ticket X et sortie de caisse
1. Imprimer un ticket X : lignes par moyen, TOTAL = chiffre d'affaires, pied du tiroir signé, aucune ligne de plus de 32 caractères.
2. Juste après un Z, faire une sortie de caisse : l'écran suivant montre la sortie et le solde diminué.

### Test 4 — Export fiscal
1. Admin → Clôtures : bandeau « Export fiscal » → formulaire → télécharger. Le ZIP contient `ventes.csv`, `articles.csv`, `reglements.csv`, `clotures.csv` (colonne `rapport_json`), pas de `corrections.csv`.
2. Demander une période de plus de 365 jours : refus.

### Test 5 — Plan comptable
1. Ouvrir Plan comptable : le composant « Plan complet ? » montre le bouton « Vérifier le plan », sans verdict.
2. Cliquer : « Vérification en cours… », puis les manques ou le message vert.

### Verifs commandes
- `docker exec lespass_django poetry run python /DjangoFiles/manage.py verify_integrity --schema=lespass ; echo $?` → 0 si sain.
- `docker exec lespass_django poetry run python /DjangoFiles/manage.py verify_clotures --tenant=inconnu ; echo $?` → 1.

## Chaînes i18n (workflow à lancer par le mainteneur)
Nouvelles chaînes (msgid en français) :
- Garde : « Seule une vente réglée peut être corrigée. », « Seule une vente faite à la caisse peut être corrigée. », « Seul un paiement en espèces, par carte bancaire ou par chèque peut être corrigé. », « Rien à corriger : le montant est nul. »
- Bouton et écran du Z : « Aucune vente à clôturer », « Aucun destinataire de rapport n'est configuré pour le lieu. », « Envoi du rapport demandé », « L'envoi du rapport n'a pas pu être demandé. Réessayez plus tard. », « Chiffre d'affaires TTC », « Opérations numérotées », « Clôture n° », « Exporter le rapport », « Télécharger le PDF », « Télécharger le CSV », « Envoyer par email », « Voir la fiche complète », « nouvel onglet », « La fiche complète s'ouvre dans l'administration du lieu : il faut y être connecté. », « Fermer la caisse »
- Tickets : « Début de période », « Fermeture », « Recharges », « Recharges remboursées », « Cartes vidées », « Écarts d'encaissement », « Opérations numérotées », « art. », « Le ticket X n'a pas pu être envoyé à l'imprimante. Réessayez plus tard. »
- Rapport et tiroir : « Plusieurs moyens », « Par moyen de paiement », « Moyen », « Les lignes par moyen ne recomposent pas le chiffre d'affaires TTC : écart de %(ecart)s. », « Espèces reçues », « Espèces rendues », « Corrections », « Sorties de caisse », « Solde théorique »
- Récap et sortie : « Opérations numérotées : %(nombre)s · depuis %(debut)s » (blocktrans), « Lignes de caisse », « Lignes de caisse (hors ventes en ligne, recharges comprises) », « dépasse les espèces du service dans le tiroir (solde moins fond) »
- Export fiscal : « Export fiscal », « Archive signée (ZIP) des ventes, de leurs articles et règlements, et des clôtures, pour l'administration fiscale. », « La date de fin est antérieure à la date de début. », « La période demandée dépasse 365 jours. Faites un export par année. »
- Plan : « Vérifier le plan », « Vérification en cours… », « Vérifie que chaque produit, moyen de paiement, monnaie et taux de TVA utilisés a son compte, pour que l'export comptable passe. »

Chaînes qui ne servent plus aux tickets : « Entrees especes », « Sorties especes », « Solde caisse », « articles », « valeur ». Les `.po` citent encore les gabarits retirés (`laboutik/pdf/cloture_rapport_pdf.html`, `laboutik/email/cloture_rapport_email.html`) : le prochain `makemessages` les nettoie.
