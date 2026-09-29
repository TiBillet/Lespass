# Tables Vente et Règlement, montants entiers de l'article / Sale and Payment tables, integer item amounts

**Date :** 2026-09-29
**Migration :** Oui — `BaseBillet/migrations/0230_vente_reglement_montants_entiers.py`
puis `laboutik/migrations/0007_commandesauvegarde_vente.py` (qui dépend de la première).
Commande : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`

## Resume / Summary

**Quoi / What :** fiche A du chantier 05 « montants entiers ».
Session A-1 : les tables `Vente` et `Reglement` (`BaseBillet/models_vente.py`) ; sur
`LigneArticle`, les montants entiers de l'article (`total_catalogue`, `part_offerte`,
`source_offert`, `total_ttc`, `total_tva`, `cout_achat`, `hors_chiffre_affaires`) et
la FK `vente`, avec deux contraintes de base ; sur `Paiement_stripe`, `vente` (vente
d'origine), `montant_encaisse` et `moyen` (SN / SP / SR) ; `Commande.vente` et
`CommandeSauvegarde.vente` ; la formule unique `calculer_montants_article`
(`BaseBillet/services_vente.py`) ; le marqueur `_tva_explicite` de `LigneArticle.save()`.
Personne n'appelle encore la formule ni les tables : aucun comportement ne change, sauf
`Paiement_stripe.moyen`, posé en plus du moyen des lignes. /
Sale and Payment tables, integer amounts on the sold item with two database
constraints, new Stripe payment fields, the single money formula and the explicit-VAT
flag. Nothing calls them yet: no behaviour change, except `Paiement_stripe.moyen`, set in
addition to the line's method.

**Pourquoi / Why :** l'argent d'une vente doit être écrit une seule fois, en centimes
entiers, puis seulement additionné : plus aucun centime perdu ou inventé par un
recalcul `amount × qty`. /
Money must be written once in whole cents, then only summed: no cent lost or invented by
recomputing.

Chantier : `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-A-vente-reglement.md` (tronc :
`CHANTIER-05-montants-entiers.md` §2-§3 ; écarts : `CHANTIER-05-SUIVI.md` §4).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models_vente.py` | nouveau : `Vente` (`Nature`, `Statut` en `TextChoices`, numéro unique nullable, clé d'idempotence unique si posée), `Reglement` (contrainte `montant <> 0`) |
| `BaseBillet/services_vente.py` | nouveau : `calculer_montants_article` (formule unique, arrondi demi-haut, `ValueError` si l'offert sort de `[0, total catalogue]`), `MOYENS_OFFERTS = [LG, FREE]` |
| `BaseBillet/models.py` | `LigneArticle` : champs entiers, FK `vente`, contraintes `lignearticle_ttc_egal_catalogue_moins_offert` et `lignearticle_ht_plus_tva_egal_ttc_si_vente` (seulement si `vente` posée, SUIVI §4) ; `save()` saute la TVA par défaut si `_tva_explicite` ; `Paiement_stripe` : `vente`, `montant_encaisse`, `moyen` ; `update_checkout_status()` pose `SP` (deux branches SEPA) ou `SN` (constaté payé, pas SEPA) ; `Commande.vente` ; import de `models_vente` en fin de fichier |
| `PaiementStripe/views.py` | `CreationPaiementStripe._send_paiement_stripe_in_db` : `moyen = SR` pour le paiement d'une facture d'abonnement (appelé seulement par `new_entry_from_stripe_subscription_invoice`), dans l'INSERT |
| `laboutik/models.py` | `CommandeSauvegarde.vente` |
| `BaseBillet/migrations/0230_vente_reglement_montants_entiers.py` | nouveau ; les deux contraintes de `LigneArticle` déplacées en fin d'opérations (la 2ᵉ lit `vente_id`) |
| `laboutik/migrations/0007_commandesauvegarde_vente.py` | nouveau, dépend de `BaseBillet.0230` |
| `tests/pytest/test_montants_article.py` | nouveau : 11 tests de la formule (sans base) |
| `tests/pytest/test_vente_modeles.py` | nouveau : 6 tests (dont T1 en 3 cas, et T1 « échéance d'abonnement → SR » par le webhook `invoice.paid`) sur la base partagée |

### Tests vus échouer puis mutations / Tests seen failing, then mutations

**Session A-1.** Avant correctif (rouge prouvé par l'orchestrateur) :
```
tests/pytest/test_montants_article.py:43: in <module>
    from BaseBillet.services_vente import calculer_montants_article
E   ModuleNotFoundError: No module named 'BaseBillet.services_vente'
ERROR tests/pytest/test_montants_article.py
```
```
E       AssertionError: assert Decimal('20.00') == Decimal('0.00')
E       ModuleNotFoundError: No module named 'BaseBillet.models_vente'
E       ModuleNotFoundError: No module named 'BaseBillet.models_vente'
E       AttributeError: 'Paiement_stripe' object has no attribute 'moyen'
E       AttributeError: 'Paiement_stripe' object has no attribute 'moyen'
PASSED tests/pytest/test_vente_modeles.py::test_create_sans_vat_garde_la_tva_du_produit
FAILED tests/pytest/test_vente_modeles.py::test_tva_zero_explicite_respectee_par_save
FAILED tests/pytest/test_vente_modeles.py::test_contrainte_base_refuse_une_ligne_incoherente
FAILED tests/pytest/test_vente_modeles.py::test_paiement_stripe_vente_d_origine
FAILED tests/pytest/test_vente_modeles.py::test_paiement_stripe_moyen_sepa_pose_a_la_mise_a_jour[paiement_direct]
FAILED tests/pytest/test_vente_modeles.py::test_paiement_stripe_moyen_sepa_pose_a_la_mise_a_jour[abonnement]
=================== 5 failed, 1 passed, 2 warnings in 0.59s ====================
```
`test_create_sans_vat_garde_la_tva_du_produit` est vert avant et après : c'est une
non-régression (les producteurs qui ne passent pas `vat` gardent la TVA du produit).
Le cas « carte → SN » du test T1 a été ajouté avec le correctif (décision de
l'orchestrateur).
Le test `test_paiement_stripe_moyen_sr_pose_a_la_creation_d_une_echeance` a été ajouté
ensuite (condition du mainteneur pour garder la pose de `SR` dans
`PaiementStripe/views.py`) : il passe par le vrai webhook `invoice.paid`, comme la
caractérisation P15, et vérifie `moyen == SR` sur le paiement de l'échéance.

Après correctif : `19 passed` (11 + 8) ; caractérisation (`test_caracterisation_*.py`,
sans modification) : `22 passed` ; `manage.py check` : aucun problème ;
`makemigrations --check --dry-run` : « No changes detected ».

#### Mutations

Jouées par l'orchestrateur.

| Session | Mutation | Test qui tombe |
|---|---|---|
| A-1 | `services_vente.py` `arrondir_au_centime_demi_haut` : `ROUND_HALF_UP` → `ROUND_HALF_EVEN` | `test_net_111_a_20_pourcent_ht_93` |
| A-1 | `services_vente.py` : TVA calculée à part (`arrondi(net × taux / (100 + taux))`) | `test_net_105_a_20_pourcent_ht_88_tva_17` (+ net 111) |
| A-1 | `services_vente.py` : coût sur `quantite` au lieu de `quantite_pour_cout` | `test_cout_achat_sur_la_quantite_reelle` |
| A-1 | `models.py` `LigneArticle.save()` : marqueur `_tva_explicite` ignoré | `test_tva_zero_explicite_respectee_par_save` |
| A-1 | `models.py` `LigneArticle.save()` : défaut seulement si `vat is None` | `test_create_sans_vat_garde_la_tva_du_produit` |
| A-1 | `models.py` `update_checkout_status` : `SP` non posé (branche abonnement) | `…moyen_sepa…[sepa_abonnement-SP-W]` |
| A-1 | idem, branche paiement direct | `…moyen_sepa…[sepa_paiement_direct-SP-W]` |
| A-1 | idem, `SN` non posé (carte) | `…moyen_sepa…[carte-SN-P]` |
| A-1 | `PaiementStripe/views.py` `CreationPaiementStripe` : `dict_paiement['moyen'] = SR` retiré | `test_paiement_stripe_moyen_sr_pose_a_la_creation_d_une_echeance` |
| A-1 | **en base** (schéma `lespass`) : `DROP CONSTRAINT lignearticle_ttc_egal_catalogue_moins_offert` | `test_contrainte_base_refuse_une_ligne_incoherente` (« DID NOT RAISE ») |
| A-1 | en base : `DROP CONSTRAINT lignearticle_ht_plus_tva_egal_ttc_si_vente` | idem |
| A-1 | en base : `DROP CONSTRAINT reglement_montant_non_nul` | idem |
| A-2 | `services_vente.py` `encaisser_vente` : 2ᵉ égalité retirée | `test_encaisser_refuse_si_argent_different_du_net` |
| A-2 | idem, 1ʳᵉ égalité retirée (**a survécu** au premier jeu : test `test_encaisser_refuse_un_offert_sans_reglement_de_trace` ajouté, puis tuée) | `test_encaisser_refuse_un_offert_sans_reglement_de_trace` |
| A-2 | numéro = nombre de ventes au lieu de `max + 1` | 7 tests de numérotation (`…numeros_consecutifs…`, `…ne_prend_pas_de_numero`…) |
| A-2 | règle « offert à montant non nul » retirée | `test_offert_a_montant_non_nul_part_offerte_et_reglement_free` |
| A-2 | clé d'idempotence de `ouvrir_vente` ignorée | `test_ouvrir_vente_meme_cle_rend_la_meme_vente` |
| A-2 | refus « vente sans article » retiré | `test_vente_sans_article_refusee_sauf_vidage_et_correction` |
| A-2 | refus « encaisser une vente annulée » retiré | `test_encaisser_vente_annulee_refuse` |
| A-2 | refus « montant non entier » retiré | `test_reglement_decimal_ou_nul_refuse` |
| A-2 | refus « TVA sur une vente en points » retiré | `test_vente_en_points_refuse_une_tva` |
| A-2 | `VR` et `FD` retirés de la liste hors chiffre d'affaires | `test_hors_chiffre_affaires_calcule_depuis_le_produit_ou_force` |
| A-2 | `save()` en plus sur la ligne après sa création | `test_ajouter_article_ne_declenche_aucune_transition` |
| A-2 | refus « ajouter à une vente non en attente » retiré (article) | `test_ajouter_a_une_vente_reglee_refuse` |
| A-2 | origine de la vente non recopiée sur la ligne | `test_ajouter_article_recopie_l_origine_de_la_vente` |
| A-2 | refus « annuler une vente réglée » retiré | `test_annuler_vente_reglee_refusee_et_annulee_rendue_telle_quelle` (message « ne s'annule pas ») |
| A-2 | garde de `Vente.save()` retirée | `test_vente_reglee_refuse_toute_modification_par_save` |
| A-2 | garde de `Reglement.save()` retirée | idem |
| A-2 | garde de `LigneArticle.save()` retirée | idem |
| A-3 | `laboutik/integrity.py` : `"reglements"` retiré du message | `test_alterer_une_vente_reglee_casse_la_chaine`, `test_premiere_vente_chainee…` |
| A-3 | idem, `"vente_liee"` retiré | idem (cas « vente_liee » non signalé) |
| A-3 | idem, `"point_de_vente"` retiré | idem (cas « point_de_vente » non signalé) |
| A-3 | `services_vente.py` : `previous_hmac = ""` toujours | 4 tests (chaînage, maillon cassé, altérations, trou) |
| A-3 | numéro = nombre de ventes réglées + 1 | `test_supprimer_une_vente_laisse_un_trou_signale` |
| A-3 | statut `REGLEE` posé après le calcul de l'empreinte (ordre littéral de la fiche §4) | 5 tests de chaîne |
| A-3 | `atomic()` interne retiré (`if True:`) | script de concurrence : « RÉSULTAT : ÉCHEC » (`TransactionManagementError`) |
| A-3 | `select_for_update` retiré | **survit** (script OK) : redondant avec le verrou du lieu pour l'encaissement ; ne protège que contre une annulation simultanée, non jouée par le script simplifié. Gardé (fiche §4), documenté |
| A-4 | `services_vente.py` `calculer_montants_article` : refus du `float` retiré (`valeur_exacte = True`) | `test_quantite_en_float_refusee`, `…quantite_pour_cout_en_float…`, `test_taux_tva_en_float_refuse` |
| A-4 | idem, refus d'un centime non entier retiré | `test_centimes_non_entiers_refuses` |
| A-4 | `models.py` garde de `LigneArticle.save()` : normalisation décimale retirée | `test_statut_d_une_ligne_reglee_modifiable_sur_l_instance_du_service` |
| A-4 | `ajouter_reglement` : contrôle du moyen retiré | `test_valeurs_hors_choix_refusees` (« moyen de règlement « XX » ») |
| A-4 | `ouvrir_vente` : contrôle de l'origine retiré | idem (« origine de vente « ZZ » ») |
| A-4 | `ouvrir_vente` : contrôle de la nature retiré | idem (« nature de vente « INCONNUE » ») |

Non jouées : retour anticipé d'`annuler_vente` sur une vente déjà annulée (mutation équivalente) .
Empreintes `sha256` des fichiers mutés identiques avant / après ; pour les contraintes,
témoin `pg_get_constraintdef` relevé avant et après, identique. Retirer une
`CheckConstraint` de `Meta` sans migration ne change pas la base : la mutation se joue
donc en SQL (`ALTER TABLE … DROP / ADD CONSTRAINT`).

### Session A-2 — service de vente, fabrique, garde d'immutabilité / Sale service, factory, immutability guard

**Quoi / What :** le service de vente complet (sauf l'empreinte, en A-3) :
`ouvrir_vente` (clé d'idempotence), `ajouter_article` (un seul INSERT, règle « offert à
montant non nul », `hors_chiffre_affaires` figé depuis le produit ou forcé, TVA 0
obligatoire pour une vente en points), `ajouter_reglement` (entier non nul),
`encaisser_vente` (verrou du lieu, `select_for_update`, vente sans article refusée sauf
vidage / correction, deux égalités, numéro `max + 1`, totaux, `REGLEE`), `annuler_vente` ;
l'exception `EgaliteDeVenteRompue` ; `MOYENS_HORS_ENCAISSEMENT`. Garde d'immutabilité :
`Vente.save()`, `Reglement.save()` et `LigneArticle.save()` refusent une modification
une fois la vente `REGLEE` en base (`ValueError`). La fabrique de test
`fabriques_vente.py` et `verifier_egalites`. Ajouts (logique D14, SUIVI §4) :
`ajouter_article` et `ajouter_reglement` refusent une vente qui n'est plus `EN_ATTENTE`
(statut relu en base) ; la ligne recopie `vente.origine` dans `sale_origin` sauf si le
producteur en passe une ; `annuler_vente` refuse une vente `REGLEE` et rend telle quelle
une vente déjà `ANNULEE`. Aucun producteur n'appelle encore le service. /
The full sale service (fingerprint excepted, A-3), the settled-sale guard, and the test
factory. No producer calls the service yet.

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/services_vente.py` | `ouvrir_vente`, `ajouter_article`, `ajouter_reglement`, `encaisser_vente` (TODO A-3 à l'endroit de l'empreinte), `annuler_vente`, `EgaliteDeVenteRompue`, constantes `MOYENS_HORS_ENCAISSEMENT`, `METHODES_CAISSE_HORS_CHIFFRE_AFFAIRES`, `NATURES_SANS_ARTICLE_ACCEPTEES` |
| `BaseBillet/models_vente.py` | `Vente.save()`, `Reglement.save()` : garde (statut relu en base) |
| `BaseBillet/models.py` | `LigneArticle.save()` : garde sur `amount`, `qty`, `vat`, `total_*`, `part_offerte`, `pricesold`, `vente` ; statuts et champs des tâches restent libres |
| `tests/pytest/fabriques_vente.py` | nouveau : `creer_tarif_vendu`, `fabriquer_vente_encaissee` (par le service), `verifier_egalites` |
| `tests/pytest/test_vente_service.py` | nouveau : 22 tests, schéma dédié `test_vente_service` |
| `tests/pytest/test_vente_modeles.py` | `test_tva_zero_explicite_respectee_par_save` passe par `ajouter_article` (recharge euros, taux 0) |

Rouge (étape 1, prouvé par l'orchestrateur ; les deux tests ajoutés ensuite, rouges de
la même façon) :
```
tests/pytest/test_vente_service.py:50: in <module>
E   ImportError: cannot import name 'EgaliteDeVenteRompue' from 'BaseBillet.services_vente'
ERROR tests/pytest/test_vente_service.py
```
```
E       ImportError: cannot import name 'ajouter_article' from 'BaseBillet.services_vente'
FAILED tests/pytest/test_vente_modeles.py::test_tva_zero_explicite_respectee_par_save
=================== 1 failed, 7 passed, 2 warnings in 0.88s ====================
```
Ajouts (vente close, origine, annulation) — rouge avant le code :
```
E           Failed: DID NOT RAISE <class 'ValueError'>
E       AssertionError: assert 'LP' == SaleOrigin.LABOUTIK
FAILED tests/pytest/test_vente_service.py::TestServiceDeVente::test_ajouter_a_une_vente_reglee_refuse
FAILED tests/pytest/test_vente_service.py::TestServiceDeVente::test_ajouter_article_recopie_l_origine_de_la_vente
============ 2 failed, 1 passed, 18 deselected, 2 warnings in 0.51s ============
```
`test_annuler_vente_reglee_refusee_et_annulee_rendue_telle_quelle` est vert dès l'écriture :
`annuler_vente` faisait déjà ces deux cas.

Vert : A-2 + A-1 + caractérisation (sans modification) `63 passed` (22 + 11 + 8 + 22) ;
`manage.py check` : aucun problème ; `makemigrations --check --dry-run` :
« No changes detected ».

Mutations de A-2 : à jouer par l'orchestrateur (liste dans le rapport de session), à
reporter dans le tableau ci-dessus.

### Session A-3 — empreinte chaînée de la vente / Chained sale fingerprint

**Quoi / What :** `laboutik/integrity.py` : `calculer_hmac_vente(vente, cle, previous_hmac)`
(HMAC-SHA256 du message JSON canonique de la fiche §5, `"format": 1`, articles et
règlements relus en base et triés par uuid, date d'encaissement en UTC) et
`verifier_chaine_ventes(cle)` (ventes `REGLEE` par numéro croissant ; anomalies
`{numero, uuid, raison}` : trou de numéro, maillon cassé, empreinte fausse, égalité
rompue relue en base ; aucune exception tolérée). `calculer_hmac` et `verifier_chaine`
(par ligne) restent inchangés jusqu'à la fiche H. `encaisser_vente` pose, sous le verrou
du lieu, `previous_hmac` (empreinte de la vente numéro − 1, "" pour la première) et
`hmac_hash` ; le statut `REGLEE` est posé **avant** le calcul (il fait partie du
message). Clé : `LaboutikConfiguration.get_solo().get_or_create_hmac_key()`. /
One chained HMAC per settled sale, and a chain check that lists every anomaly.

**Pourquoi / Why :** une vente réglée modifiée par `.update()` ou par SQL contourne la
garde de `save()` : seule l'empreinte chaînée le révèle (D18). /
Only the chained fingerprint reveals a settled sale changed behind `save()`.

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/integrity.py` | ajout de `calculer_hmac_vente` et `verifier_chaine_ventes` (import `datetime`) |
| `BaseBillet/services_vente.py` | `encaisser_vente` : étape 6, empreinte chaînée (le TODO A-3 est remplacé) ; commentaire sur le `atomic()` interne ; imports `calculer_hmac_vente`, `LaboutikConfiguration` |
| `tests/pytest/test_vente_service.py` | 5 tests A-3, `calculer_l_empreinte_attendue` (message de la fiche recopié à la main), `anomalie_signalee` |

Tests A-3 : `test_premiere_vente_chainee_sur_vide_puis_suivante_sur_la_precedente`,
`test_alterer_une_vente_reglee_casse_la_chaine` (10 cas par `.update()`, chacun dans un
point de sauvegarde annulé : `total_ttc` d'un article — déguisé en offert cohérent, les
contraintes de base refusant `total_ttc` seul —, `montant` d'un règlement, `vente_liee`,
`point_de_vente`, `numero`, `datetime_encaissement`, `nature`, `origine`, `unite`,
totaux de la vente), `test_empreinte_precedente_modifiee_signale_un_maillon_casse`
(ajouté : sans lui, « maillon cassé » n'est vu par aucun test),
`test_supprimer_une_vente_laisse_un_trou_signale` (SQL brut ; la vente suivante prend le
n° 4), `test_supprimer_un_reglement_signale_egalite_rompue` (SQL brut).

Rouge (prouvé par l'orchestrateur) — sur le code d'avant :
```
tests/pytest/test_vente_service.py:79: in <module>
    from laboutik.integrity import calculer_hmac_vente, verifier_chaine_ventes
E   ImportError: cannot import name 'calculer_hmac_vente' from 'laboutik.integrity' (/DjangoFiles/laboutik/integrity.py)
ERROR tests/pytest/test_vente_service.py
```
Contre un service volontairement vide (`calculer_hmac_vente` → "", `verifier_chaine_ventes`
→ [], injectés par un plugin pytest jetable hors dépôt) :
```
FAILED ...::test_alterer_une_vente_reglee_casse_la_chaine
FAILED ...::test_empreinte_precedente_modifiee_signale_un_maillon_casse
FAILED ...::test_premiere_vente_chainee_sur_vide_puis_suivante_sur_la_precedente
FAILED ...::test_supprimer_un_reglement_signale_egalite_rompue
FAILED ...::test_supprimer_une_vente_laisse_un_trou_signale
5 failed, 22 passed, 2 warnings in 7.76s
```

Vert : A-3 + A-2 + A-1 + caractérisation (sans modification) `68 passed`
(27 + 11 + 8 + 22) ; autres fichiers qui importent `laboutik.integrity` ou le service
(`test_integrity_hmac`, `test_cloture_enrichie`, `test_poids_mesure`,
`test_pos_retour_consigne`, `test_total_ht_ligne`) : `49 passed` ; `manage.py check` :
aucun problème ; `makemigrations --check --dry-run` : « No changes detected ».

#### Concurrence (vérification manuelle) / Concurrency (manual check)

Pas de pytest `transaction=True` (interdit : sans base de test, le teardown viderait la
base de dev). Un script, lancé **uniquement** dans le schéma `test_vente_service` (créé
par `tests/pytest/test_vente_service.py`), avec deux fils qui démarrent ensemble, chacun
dans son `tenant_context`. Il écrit vraiment (les fils ne voient que ce qui est commité),
puis nettoie tout ce qu'il a créé dans un `finally` (ventes, articles, règlements,
produit, tarifs ; le singleton de la caisse s'il l'a créé). Il refuse de tourner dans un
autre schéma ou si des ventes existent déjà.

Commande (le script est copié ci-dessous ; l'enregistrer sous `concurrence_a3.py`) :
```bash
docker cp concurrence_a3.py lespass_django:/tmp/concurrence_a3.py
docker exec lespass_django poetry run python /DjangoFiles/manage.py \
    tenant_command shell --schema=test_vente_service \
    -c "exec(open('/tmp/concurrence_a3.py').read())"
```

Sortie obtenue (deux lancements, l'ordre des fils du scénario 1 varie) :
```
Scénario 1 — fil a : 2
Scénario 1 — fil b : 1
Scénario 2 — fil a : 3
Scénario 2 — fil b : 3
Numéros en base : [1, 2, 3]
verifier_chaine_ventes : []
Nettoyage : ventes restantes en base = 0
RÉSULTAT : OK — numéros distincts, un seul numéro par vente, chaîne saine.
```
Après le lancement : 0 produit, 0 tarif, 0 ligne, 0 vente, 0 règlement, 0 singleton
dans `test_vente_service`.

Sous mutation (non jouée) :
- `atomic()` interne d'`encaisser_vente` retiré → `select_for_update()` hors transaction
  lève `TransactionManagementError` dans chaque fil → « RÉSULTAT : ÉCHEC »
  (scénario 1 : numéros `{None}`).
- `select_for_update()` retiré → le script reste **OK** : le verrou du lieu
  (`pg_advisory_xact_lock`, tenu jusqu'au COMMIT grâce au `atomic()`) suffit à
  sérialiser deux encaissements ; le second relit la vente déjà `REGLEE`. Le
  `select_for_update` protège d'un `annuler_vente` simultané (qui ne prend pas le verrou
  du lieu), cas que ce script ne joue pas.

Le script :
```python
"""
Vérification manuelle de la concurrence d'`encaisser_vente` (chantier 05, fiche A-3).
/ Manual concurrency check of encaisser_vente (worksite 05, sheet A-3).

LOCALISATION : copie dans le CHANGELOG
CHANGELOG/2026-09-29-montants-entiers-A-vente-reglement.md (section A-3).

Pas de test pytest ici : il faudrait `transaction=True`, interdit (sans base de test, le
teardown viderait la base de dev). Ce script tourne UNIQUEMENT dans le schéma
`test_vente_service`, créé par tests/pytest/test_vente_service.py. Il refuse tout autre
schéma, et refuse de tourner si ce schéma contient déjà des ventes.
/ Runs ONLY in the test_vente_service schema, and refuses to run if sales already exist.

Les fils (threads) ont chacun leur connexion : ils ne voient que ce qui est COMMITÉ. Le
script écrit donc vraiment en base (autocommit), puis NETTOIE tout ce qu'il a créé à la
fin, même en cas d'erreur (bloc `finally`).
/ Threads only see committed rows: the script really writes, then cleans up everything.

DEUX SCÉNARIOS, chacun lancé par deux fils qui démarrent ensemble (barrière) :
1. deux ventes DIFFÉRENTES encaissées en même temps → deux numéros distincts ;
2. la MÊME vente encaissée deux fois en même temps → un seul numéro, le même rendu
   aux deux fils.
À la fin : numéros 1 à N sans trou, et `verifier_chaine_ventes` sans anomalie.

LANCEMENT (depuis la racine du dépôt, sur l'hôte) :
    docker cp <chemin>/concurrence_a3.py lespass_django:/tmp/concurrence_a3.py
    docker exec lespass_django poetry run python /DjangoFiles/manage.py \
        tenant_command shell --schema=test_vente_service \
        -c "exec(open('/tmp/concurrence_a3.py').read())"
"""

import threading
from decimal import Decimal

from django.db import connection
from django_tenants.utils import tenant_context

from BaseBillet.models import (
    LigneArticle,
    PaymentMethod,
    Price,
    PriceSold,
    Product,
    ProductSold,
    SaleOrigin,
)
from BaseBillet.models_vente import Reglement, Vente
from BaseBillet.services_vente import (
    ajouter_article,
    ajouter_reglement,
    encaisser_vente,
    ouvrir_vente,
)
from laboutik.integrity import verifier_chaine_ventes
from laboutik.models import LaboutikConfiguration

# Garde-fous : le bon schéma, et un schéma sans vente.
# / Safety: the right schema, and no existing sale.
if connection.schema_name != "test_vente_service":
    raise SystemExit(
        f"ARRÊT : ce script ne tourne que dans test_vente_service "
        f"(schéma courant : {connection.schema_name})."
    )
if Vente.objects.exists():
    raise SystemExit("ARRÊT : le schéma test_vente_service contient déjà des ventes.")

lieu_du_test = connection.tenant
anomalies_constatees = []
ventes_creees = []

# Le singleton de la caisse porte la clé de l'empreinte. S'il n'existe pas en base, le
# script le crée, et le supprime à la fin.
# / The register singleton holds the key; created (then deleted) if missing.
singleton_de_la_caisse_deja_en_base = LaboutikConfiguration.objects.exists()
LaboutikConfiguration.get_solo().save()

produit_du_jus = Product.objects.create(name="TEST_vente concurrence jus")
tarif_du_jus = Price.objects.create(
    product=produit_du_jus, name="Tarif unique", prix=Decimal("3.50"), publish=True
)
produit_vendu_du_jus = ProductSold.objects.create(product=produit_du_jus)
tarif_vendu_du_jus = PriceSold.objects.create(
    productsold=produit_vendu_du_jus, price=tarif_du_jus, prix=tarif_du_jus.prix
)


def preparer_une_vente_prete_a_encaisser():
    """
    Une vente d'un jus à 3,50 €, réglée 350 en espèces, encore en attente.
    / A pending sale of one juice, paid 350 in cash.
    """
    vente = ouvrir_vente(origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE)
    ventes_creees.append(vente)
    ajouter_article(
        vente,
        pricesold=tarif_vendu_du_jus,
        quantite=Decimal("1"),
        prix_unitaire=350,
        taux_tva=Decimal("20"),
    )
    ajouter_reglement(vente, moyen=PaymentMethod.CASH, montant=350)
    return vente


def agir_dans_un_fil(action, vente, barriere, resultats, nom_du_fil):
    """
    Corps d'un fil : se place dans le lieu, attend l'autre fil, puis agit sur la vente.
    Le résultat (la vente rendue, ou le texte de l'erreur) va dans `resultats`.
    / Thread body: enter the venue, wait for the other thread, then act on the sale.
    """
    try:
        with tenant_context(lieu_du_test):
            barriere.wait()
            try:
                resultats[nom_du_fil] = action(vente)
            except Exception as erreur:
                resultats[nom_du_fil] = f"ERREUR {type(erreur).__name__} : {erreur}"
    finally:
        # Chaque fil a sa propre connexion : on la ferme.
        # / Each thread has its own connection: close it.
        connection.close()


def lancer_deux_fils_ensemble(action_du_fil_a, vente_du_fil_a, action_du_fil_b, vente_du_fil_b):
    """
    Lance deux fils qui démarrent au même instant, attend leur fin, rend leurs résultats.
    / Starts two threads at the same instant, waits for them, returns their results.
    """
    barriere = threading.Barrier(2)
    resultats = {}
    fil_a = threading.Thread(
        target=agir_dans_un_fil,
        args=(action_du_fil_a, vente_du_fil_a, barriere, resultats, "a"),
    )
    fil_b = threading.Thread(
        target=agir_dans_un_fil,
        args=(action_du_fil_b, vente_du_fil_b, barriere, resultats, "b"),
    )
    fil_a.start()
    fil_b.start()
    fil_a.join()
    fil_b.join()
    return resultats["a"], resultats["b"]


try:
    # --- Scénario 1 : deux ventes différentes en même temps.
    # / Scenario 1: two different sales at the same time.
    premiere_vente = preparer_une_vente_prete_a_encaisser()
    seconde_vente = preparer_une_vente_prete_a_encaisser()
    resultat_a, resultat_b = lancer_deux_fils_ensemble(
        encaisser_vente, premiere_vente, encaisser_vente, seconde_vente
    )
    print(f"Scénario 1 — fil a : {getattr(resultat_a, 'numero', resultat_a)}")
    print(f"Scénario 1 — fil b : {getattr(resultat_b, 'numero', resultat_b)}")
    # Un ensemble : l'ordre d'arrivée des deux fils ne compte pas.
    # / A set: the arrival order of the two threads does not matter.
    numeros_du_scenario_1 = {
        Vente.objects.get(pk=premiere_vente.pk).numero,
        Vente.objects.get(pk=seconde_vente.pk).numero,
    }
    if numeros_du_scenario_1 != {1, 2}:
        anomalies_constatees.append(
            f"Scénario 1 : numéros {numeros_du_scenario_1}, attendu {{1, 2}}."
        )

    # --- Scénario 2 : la même vente, deux fois en même temps.
    # / Scenario 2: the same sale, twice at the same time.
    vente_encaissee_deux_fois = preparer_une_vente_prete_a_encaisser()
    resultat_a, resultat_b = lancer_deux_fils_ensemble(
        encaisser_vente, vente_encaissee_deux_fois, encaisser_vente, vente_encaissee_deux_fois
    )
    numero_rendu_au_fil_a = getattr(resultat_a, "numero", resultat_a)
    numero_rendu_au_fil_b = getattr(resultat_b, "numero", resultat_b)
    print(f"Scénario 2 — fil a : {numero_rendu_au_fil_a}")
    print(f"Scénario 2 — fil b : {numero_rendu_au_fil_b}")
    if not (numero_rendu_au_fil_a == numero_rendu_au_fil_b == 3):
        anomalies_constatees.append(
            f"Scénario 2 : fil a {numero_rendu_au_fil_a}, fil b {numero_rendu_au_fil_b}, "
            f"attendu 3 et 3."
        )

    # --- Fin : numéros sans trou, chaîne saine.
    # / End: gapless numbers, sound chain.
    numeros_en_base = list(
        Vente.objects.filter(statut=Vente.Statut.REGLEE)
        .order_by("numero")
        .values_list("numero", flat=True)
    )
    numeros_attendus = list(range(1, len(numeros_en_base) + 1))
    print(f"Numéros en base : {numeros_en_base}")
    if numeros_en_base != numeros_attendus:
        anomalies_constatees.append(f"Numéros {numeros_en_base}, attendu {numeros_attendus}.")

    cle = LaboutikConfiguration.get_solo().get_or_create_hmac_key()
    anomalies_de_la_chaine = verifier_chaine_ventes(cle)
    print(f"verifier_chaine_ventes : {anomalies_de_la_chaine}")
    if anomalies_de_la_chaine:
        anomalies_constatees.append(f"Chaîne : {anomalies_de_la_chaine}")

finally:
    # Nettoyage de tout ce que le script a créé, dans l'ordre des clés étrangères.
    # / Cleanup of everything the script created, in foreign-key order.
    uuids_des_ventes_creees = []
    for vente in ventes_creees:
        uuids_des_ventes_creees.append(vente.pk)
    Reglement.objects.filter(vente_id__in=uuids_des_ventes_creees).delete()
    LigneArticle.objects.filter(vente_id__in=uuids_des_ventes_creees).delete()
    Vente.objects.filter(pk__in=uuids_des_ventes_creees).delete()
    tarif_vendu_du_jus.delete()
    produit_vendu_du_jus.delete()
    tarif_du_jus.delete()
    # SQL brut pour le produit : `Product.delete()` plante dans le signal de
    # suppression de stdimage quand le produit n'a pas d'image.
    # / Raw SQL for the product: Product.delete() crashes in stdimage without image.
    with connection.cursor() as curseur:
        curseur.execute(
            'DELETE FROM "BaseBillet_product" WHERE uuid = %s', [produit_du_jus.pk]
        )
    if not singleton_de_la_caisse_deja_en_base:
        LaboutikConfiguration.objects.all().delete()
        LaboutikConfiguration.clear_cache()
    print(f"Nettoyage : ventes restantes en base = {Vente.objects.count()}")

if anomalies_constatees:
    print("RÉSULTAT : ÉCHEC")
    for anomalie in anomalies_constatees:
        print(f"  - {anomalie}")
else:
    print("RÉSULTAT : OK — numéros distincts, un seul numéro par vente, chaîne saine.")
```

### Session A-4 — types et choix vérifiés, garde normalisée / Types and choices checked, normalised guard

**Quoi / What :**
- `calculer_montants_article` refuse (`ValueError`, avant tout calcul) des centimes
  (`prix_unitaire`, `part_offerte`, `prix_achat`) qui ne sont pas des `int` (`Decimal`,
  `float` et `bool` refusés, comme `total_catalogue_impose` et `ajouter_reglement`), et
  une `quantite`, une `quantite_pour_cout` ou un `taux_tva` qui n'est ni un `Decimal` ni
  un `int` (le message demande un `Decimal`). Le `float` est refusé toujours, même
  quand la valeur ne sert pas (`quantite_pour_cout` sans prix d'achat).
- `LigneArticle.save()` : la garde d'une vente réglée compare un champ décimal tel que
  la base le stocke (`to_python()` puis `quantize` à `decimal_places`, `ROUND_HALF_UP`,
  comme l'arrondi de PostgreSQL). Une `qty` à 28 décimales (part de cascade
  `Decimal(500) / Decimal(350)`) n'est plus vue « modifiée » face à ses 6 décimales en
  base.
- `ouvrir_vente` refuse une `origine` hors de `SaleOrigin` et une `nature` hors de
  `Vente.Nature` ; `ajouter_reglement` refuse un `moyen` hors de `PaymentMethod`.
- Lisibilité : commentaire du `int()` d'`arrondir_au_centime_demi_haut` ; commentaires
  des imports locaux de `calculer_hmac_vente` et `verifier_chaine_ventes` ; en-tête des
  champs de `LigneArticle` sans référence de session ; imports de `models_vente` /
  `services_vente` en tête de `test_vente_modeles.py`.
/ The formula refuses non-int cents and float quantities or VAT rate; the settled-line
guard compares decimals as stored; unknown origin, nature and payment method are refused.

**Pourquoi / Why :** `Decimal(0.35)` vaut 0,34999… : 1290 × 0,35 en `float` donnait 451
au lieu de 452, en silence. La garde refusait à tort un `save()` du statut sur l'instance
rendue par `ajouter_article` (part de cascade). La base ne vérifie pas les choix d'un
champ texte : une valeur inconnue était écrite puis scellée dans l'empreinte. /
A float silently lost a cent; the guard refused a legitimate status save; unknown
choices were written and sealed in the fingerprint.

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/services_vente.py` | `calculer_montants_article` : étapes 0 et 0 bis (types reçus), docstring « LES TYPES REÇUS » ; `ouvrir_vente` : refus origine / nature hors choix ; `ajouter_reglement` : refus moyen hors choix ; import `SaleOrigin` ; commentaire du `int()` |
| `BaseBillet/models.py` | `LigneArticle.save()` : normalisation des champs décimaux avant comparaison ; en-tête « Montants de l'article, en centimes entiers, et sa vente » |
| `laboutik/integrity.py` | commentaires des imports locaux (cycle d'import avec `services_vente`) |
| `tests/pytest/test_montants_article.py` | 6 tests : `test_quantite_en_float_refusee`, `test_quantite_pour_cout_en_float_refusee` (avec et sans prix d'achat), `test_taux_tva_en_float_refuse`, `test_centimes_non_entiers_refuses` (9 cas), `test_quantite_et_taux_en_int_acceptes`, `test_montants_rendus_entiers_avec_part_offerte_et_cout` |
| `tests/pytest/test_vente_service.py` | 2 tests : `test_valeurs_hors_choix_refusees` (3 cas), `test_statut_d_une_ligne_reglee_modifiable_sur_l_instance_du_service` |
| `tests/pytest/test_vente_modeles.py` | imports locaux remontés en tête de fichier |

Rouge (prouvé par l'orchestrateur, `make test`) — sur le code d'avant :
```
test_montants_article.py:363: Failed: DID NOT RAISE <class 'ValueError'>   (quantité float)
test_montants_article.py:378: Failed: DID NOT RAISE <class 'ValueError'>   (quantité pour le coût float)
test_montants_article.py:395: Failed: DID NOT RAISE <class 'ValueError'>   (taux float)
test_montants_article.py:466: AssertionError: Centimes non entiers acceptés : [les 9 cas]
BaseBillet/models.py:4076: ValueError: La ligne … appartient à une vente réglée : ces champs ne peuvent plus changer : qty.
test_vente_service.py:436: AssertionError: Valeurs hors choix acceptées : ['moyen de règlement « XX »', 'origine de vente « ZZ »', 'nature de vente « INCONNUE »']
6 failed, 40 passed, 2 warnings
```
`test_quantite_et_taux_en_int_acceptes` et
`test_montants_rendus_entiers_avec_part_offerte_et_cout` sont verts dès le départ : ils
gardent le comportement voulu (un `int` reste accepté ; tout montant rendu est un `int`).

Vert : A-1 + A-2 + A-3 + A-4 `54 passed` (17 + 8 + 29) ; caractérisation (sans
modification) `22 passed` ; autres fichiers qui importent `laboutik.integrity`
(`test_integrity_hmac`, `test_cloture_enrichie`, `test_poids_mesure`,
`test_pos_retour_consigne`, `test_total_ht_ligne`) : `49 passed` ; `manage.py check` :
aucun problème ; `makemigrations --check --dry-run` : « No changes detected ».

Mutations de A-4 : à jouer par l'orchestrateur (liste dans le rapport de session), à
reporter dans le tableau ci-dessus.

### Traductions / Translations

Session A-2 : aucune nouvelle chaîne `_()` (les messages d'exception du service et de la
garde sont en français, non traduits : ils s'adressent aux développeurs et aux journaux).
Session A-3 : aucune nouvelle chaîne `_()` (les raisons des anomalies de la chaîne sont en
français, non traduites, comme les messages du service).
Session A-4 : aucune nouvelle chaîne `_()` (les nouveaux messages d'exception sont en
français, non traduits, comme ceux du service).

Nouvelles chaînes `_()` (source FR), à passer dans `makemessages` puis à traduire en EN :
- natures : « Vente », « Avoir », « Vidage de carte », « Correction de moyen de paiement » ;
- statuts : « En attente », « Réglée », « Annulée » ;
- sources d'offert : « Offert par le lieu », « Jetons cadeau » ;
- noms des modèles : « Vente », « Ventes », « Règlement », « Règlements » ;
- libellés de champs (`Vente`) : « Numéro », « Nature », « Statut », « Origine »,
  « Unité », « Point de vente », « Opérateur », « Client », « Carte », « Vente liée »,
  « Total catalogue », « Total offert », « Total net vendu (TTC) », « Total HT »,
  « Total TVA », « Date de création », « Date d'encaissement », « Empreinte »,
  « Empreinte précédente », « Clé d'idempotence » ;
- libellés de champs (`Reglement`) : « Moyen de paiement », « Montant (centimes) »,
  « Monnaie », « Portefeuille », « Transaction Fedow », « Paiement Stripe »,
  « Référence externe », « Date » ;
- libellés de champs (`LigneArticle`, `Paiement_stripe`, `Commande`,
  `CommandeSauvegarde`) : « Total catalogue (centimes) », « Part offerte (centimes) »,
  « Source de l'offert », « Net vendu TTC (centimes) », « Total TVA (centimes) »,
  « Coût d'achat (centimes) », « Hors chiffre d'affaires », « Vente d'origine »,
  « Montant encaissé (centimes) », « Moyen de paiement Stripe ».

---

## Comment tester (a la main) / Manual test

### Test 1 — la migration est passée partout
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --check --dry-run
```
Attendu : rien à appliquer, « No changes detected ».

### Test 2 — la formule, dans un shell
```python
# docker exec -it lespass_django poetry run python /DjangoFiles/manage.py shell
from decimal import Decimal
from BaseBillet.services_vente import calculer_montants_article
calculer_montants_article(prix_unitaire=350, quantite=Decimal("3"), taux_tva=Decimal("20"))
# {'total_catalogue': 1050, 'part_offerte': 0, 'total_ttc': 1050, 'total_ht': 875, 'total_tva': 175, 'cout_achat': None}
calculer_montants_article(prix_unitaire=111, quantite=Decimal("1"), taux_tva=Decimal("20"))["total_ht"]
# 93
```

### Test 3 — aucun comportement visible ne change
1. Acheter un billet en ligne (carte de test `4242 4242 4242 4242`) : parcours inchangé.
2. Dans un shell (`tenant_command shell --schema=lespass`) :
   `Paiement_stripe.objects.order_by("-order_date").first().moyen` vaut `"SN"`.
3. Une vente en caisse : inchangée (aucune `Vente` n'est encore écrite).

### Test 4 — le service de vente, dans un shell (A-2)
Dans un schéma de test, jamais dans `lespass` : une vente encaissée ne se supprime pas
(FK `PROTECT`) et prendrait un numéro. Le plus simple : les tests automatiques
ci-dessous. Pour voir un refus à la main, dans une transaction annulée :
```python
# docker exec -it lespass_django poetry run python /DjangoFiles/manage.py tenant_command shell --schema=lespass
from decimal import Decimal
from django.db import transaction
from BaseBillet.models import PriceSold, SaleOrigin, PaymentMethod
from BaseBillet.models_vente import Vente
from BaseBillet.services_vente import ouvrir_vente, ajouter_article, ajouter_reglement, encaisser_vente
with transaction.atomic():
    vente = ouvrir_vente(origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE)
    ajouter_article(vente, pricesold=PriceSold.objects.first(), quantite=Decimal("3"), prix_unitaire=350, taux_tva=Decimal("20"))
    ajouter_reglement(vente, moyen=PaymentMethod.CASH, montant=1049)
    encaisser_vente(vente)   # EgaliteDeVenteRompue : 1049 contre 1050
```

### Test 5 — l'empreinte chaînée (A-3)
1. Les tests : `make test ARGS="tests/pytest/test_vente_service.py"` (27 tests).
2. La concurrence : le script de la section A-3, dans `test_vente_service` uniquement
   (lancer d'abord les tests une fois, pour que ce schéma existe). Attendu :
   « RÉSULTAT : OK ».

### Verifs DB / Playwright
- Tests automatiques : `make test ARGS="tests/pytest/test_montants_article.py tests/pytest/test_vente_modeles.py tests/pytest/test_vente_service.py"`.
- Contraintes en base (schéma `lespass`) : `lignearticle_ttc_egal_catalogue_moins_offert`,
  `lignearticle_ht_plus_tva_egal_ttc_si_vente`, `reglement_montant_non_nul`.
