# Reprise des ventes existantes : le calcul et le passage à blanc (chantier 05, fiche R, session R-1) / Takeover of existing sales: computation and dry run (worksite 05, sheet R, session R-1)

**Date :** 2026-10-07
**Migration :** Non

## Resume / Summary
**Quoi / What :** nouveau calcul `calculer_le_plan_de_reprise(moment_de_la_reprise)`
(`BaseBillet/reprise_des_ventes.py`). Pour un lieu, il lit les anciennes lignes d'article
(sans vente) et les paiements Stripe, et construit EN MÉMOIRE le plan des ventes à créer :
groupes, nature, statut, date, client, montants entiers de chaque article (formule unique
`calculer_montants_article`), règlements, ce qu'il faudra poser sur les paiements Stripe,
anomalies. Les paiements `T` (retours en banque FED) deviennent des ventes « virement
reçu » (article `VR` à créer). Nouvelle commande `manage.py reprendre_les_ventes_existantes
[--schema …]` : passage à blanc seulement ; rapport par lieu puis total, en nombres, sans
aucune donnée personnelle. Rien n'est écrit. /
New computation of the takeover plan, in memory, and a dry-run command that prints a
numbers-only report per venue. Nothing is written.

**Pourquoi / Why :** en production, 23 465 anciennes lignes (115 lieux) n'ont ni vente, ni
règlement, ni montants entiers. R-1 fait le calcul ; R-2 écrira ce plan sans le
recalculer. Fiche `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md` (§3 à
§10, §14, §17), brief `CHANTIER-05-briefs/05-R-1.md`, décisions du SUIVI §4 (2026-10-07). /
Old production lines have no sale; R-1 computes, R-2 will write.

Règles appliquées (formes de la production seulement ; toute autre forme est l'anomalie
« forme non prévue », groupe non écrit) :
- regroupement dans cet ordre : avoir (une vente par ligne), parts QR / NFC (même texte
  `metadata`), paiement Stripe (une vente par paiement), ligne seule ;
- statut : paiement `V` `P` `R` → réglée ; `W` commandé il y a moins de 30 jours (lu sur
  `order_date`) → en attente ; `W` plus vieux et `E` → annulée ; paiement non payé : lignes
  `U` / `O` seulement ; hors Stripe, le statut suit les lignes ;
- montants : TVA lue sur la ligne ; part QR (et lignes `LE` / `SF` à quantité non entière
  hors QR) : argent = `amount` ; offert `NA` à montant non nul : part offerte = total,
  règlement FREE ;
- règlements : un par couple (moyen, monnaie), seulement pour une vente réglée ; moyen vide
  sur Stripe → `SN` ; avoir sur Stripe : relié au paiement, référence « reprise » ;
- paiement Stripe réglé : moyen (B-3) et montant encaissé (total d'origine des articles,
  avoirs non déduits) à poser ;
- client : réservation, sinon adhésion, sinon paiement Stripe ;
- rapport : ancien calcul (Σ `amount × qty`) et Σ `total_catalogue` hors parts QR, plus
  Σ `total_ttc` et Σ `part_offerte`.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/reprise_des_ventes.py` | Nouveau : le calcul du plan (aucune écriture) |
| `comptabilite/management/commands/reprendre_les_ventes_existantes.py` | Nouveau : le passage à blanc et son rapport |
| `tests/pytest/test_reprise_des_ventes.py` | Nouveau : 15 tests (schéma dédié `FastTenantTestCase`) |

### Chaînes i18n ajoutées / Added i18n strings
Aucune (rapport de commande, sans `_()`).

### Tests
- Rouge (étape 1, code absent) : `15 failed` — 14 × `ModuleNotFoundError: No module named
  'BaseBillet.reprise_des_ventes'`, 1 × `CommandError: Unknown command:
  'reprendre_les_ventes_existantes'`.
- Vert (étape 2) : `15 passed`.

### Mutations à jouer (orchestrateur) / Mutations to play
| Mutation | Fichier:ligne | Test attendu en échec |
|---|---|---|
| Une vente par ligne au lieu d'une par paiement | `BaseBillet/reprise_des_ventes.py:458` (`str(ligne.paiement_stripe_id)` → `str(ligne.uuid)`) | `test_reprise_une_vente_par_paiement_stripe` |
| Règle « négatif » après la règle Stripe | `BaseBillet/reprise_des_ventes.py:443` et `:457` (tester `paiement_stripe_id` avant `_ligne_est_un_avoir`) | `test_reprise_ligne_negative_ou_remboursee_devient_un_avoir_meme_avec_un_paiement_stripe` |
| `amount × qty` pour une part QR | `BaseBillet/reprise_des_ventes.py:886` (`= ligne.amount` → `= None`) | `test_reprise_parts_qr_argent_egal_au_montant_de_la_part`, `test_reprise_totaux_identiques_a_l_ancien_calcul_hors_parts_qr` |
| Âge lu sur `last_action` | `BaseBillet/reprise_des_ventes.py:802` (`paiement.order_date` → `paiement.last_action`) | `test_reprise_statut_suit_le_paiement_stripe` |
| Seuil de 30 jours retiré | `BaseBillet/reprise_des_ventes.py:802` (retirer `and paiement.order_date > …`) | `test_reprise_statut_suit_le_paiement_stripe` |
| TVA relue sur le tarif | `BaseBillet/reprise_des_ventes.py:891` (`taux_tva=ligne.vat` → `Decimal(ligne.pricesold.productsold.product.tva.tva_rate)`) | `test_reprise_une_vente_par_paiement_stripe` |
| `metadata` texte non lu | `BaseBillet/reprise_des_ventes.py:516` (retirer la branche `isinstance(metadata, str)`) | `test_reprise_metadata_lue_en_dict_et_en_texte` |
| Montant du paiement `T` lu ailleurs | `BaseBillet/reprise_des_ventes.py:1187` (`objet_du_transfert["amount"]` → `paiement.montant_encaisse` passé par l'appelant, l.1106) | `test_reprise_paiement_t_devient_une_vente_virement_recu` |
| Date du paiement `T` lue sur `order_date` | `BaseBillet/reprise_des_ventes.py:1156` (`date_du_virement` → `paiement.order_date`) | `test_reprise_paiement_t_devient_une_vente_virement_recu` |
| Ordre du client inversé (paiement avant réservation) | `BaseBillet/reprise_des_ventes.py:1065-1073` (boucle du paiement en premier) | `test_reprise_client_reservation_puis_adhesion_puis_paiement` |

## Session R-2 — l'écriture du plan / Writing the plan (2026-10-08)

**Migration :** Non

**Quoi / What :** nouvelle fonction `ecrire_le_plan_de_reprise(plan)`
(`BaseBillet/reprise_des_ventes_ecriture.py`, module neuf) et option `--executer` de la
commande `reprendre_les_ventes_existantes`. Le plan de R-1 est écrit tel quel, sans être
recalculé : chaque vente reprise devient une vraie `Vente` (clé
`idempotency_key = "reprise-<clé du groupe>"`), avec ses règlements, numérotée et chaînée
à sa date d'origine ; chaque ancienne ligne reçoit sa vente et ses huit montants par UN
`.update()` (jamais `save()`). `encaisser_vente` reçoit un paramètre facultatif
`datetime_encaissement=None` : sans lui, « maintenant », comme avant. /
The R-1 plan is written as is: real sales, numbered and chained at their original date;
old lines updated by .update() only; `encaisser_vente` gets an optional date.

**Pourquoi / Why :** rapports, exports et H-2 lisent les ventes : l'historique des lieux
doit en avoir. Brief `CHANTIER-05-briefs/05-R-2.md`, fiche R §8, §10, §13 (R-2) ; décisions
C1 à C8 du SUIVI §4 (2026-10-08). / History must have sales for reports and H-2.

Règles appliquées :
- une transaction par vente, dans l'ordre du plan (ordre du temps ; à date égale, l'avoir
  après sa vente) ; ouvrir → `.update()` des lignes (et `credit_note_for` quand le plan le
  demande) → article « virement reçu » par `ajouter_article` → règlements par
  `ajouter_reglement` → `encaisser_vente(date d'origine)` EN DERNIER (ou `annuler_vente` ;
  en attente : rien) → `.update()` de `Vente.datetime_creation`, `Reglement.datetime` et
  du paiement Stripe (`vente`, et `moyen` / `montant_encaisse` quand le plan les donne) ;
- origine de la vente : celle de ses lignes (première ligne si mélangées, comptées au
  rapport) ; virement reçu : `WK` (C1) ; ligne « virement reçu » sans moyen (C6) ;
- avoir : `vente_liee` = la vente de sa ligne d'origine, déjà écrite ;
- rejouable : une vente dont la clé existe est sautée ;
- garde du lieu : une vente réglée hors reprise → `RepriseRefusee`, rien n'est écrit ; la
  commande affiche le message et passe au lieu suivant (C3) ;
- fin de lieu : `verifier_chaine_ventes` ; invalide → erreur affichée, le lieu reste écrit ;
- rapport d'exécution : ventes écrites, sautées, à origines mélangées, chaîne valide
  oui / non, durée ; puis le total.

### Fichiers modifiés (R-2) / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/reprise_des_ventes_ecriture.py` | Nouveau : l'écriture du plan, la garde du lieu |
| `BaseBillet/services_vente.py` | `encaisser_vente(vente, datetime_encaissement=None)` |
| `comptabilite/management/commands/reprendre_les_ventes_existantes.py` | Option `--executer` et rapport d'exécution |
| `tests/pytest/test_reprise_des_ventes.py` | 15 tests de R-2 ajoutés (ceux de R-1 inchangés) ; `setUp` crée `LaboutikConfiguration` |

### Chaînes i18n ajoutées (R-2)
Aucune (rapport de commande et message d'exception, sans `_()`).

### Tests (R-2)
- Rouge (étape 1, code absent) : `14 failed, 16 passed` — 13 × `CommandError: Error:
  unrecognized arguments: --executer`, 1 × `ModuleNotFoundError: No module named
  'BaseBillet.reprise_des_ventes_ecriture'` ; verts : les 15 de R-1 et
  `test_encaisser_vente_sans_date_garde_maintenant` (caractérisation de l'appel d'aujourd'hui).
- Vert (étape 2) : `30 passed` ; `tests/pytest/test_caracterisation_*.py` : `24 passed`
  sans modification ; `test_vente_service.py` + `test_integrity_hmac.py` : `36 passed`.

### Mutations à jouer (orchestrateur, R-2)
| Mutation | Fichier:ligne | Test attendu en échec |
|---|---|---|
| Date « maintenant » au lieu de la date d'origine | `BaseBillet/reprise_des_ventes_ecriture.py:254` (retirer `datetime_encaissement=date_de_la_vente`) | `test_reprise_date_d_origine_gardee_sur_vente_et_reglements`, `test_reprise_virement_recu_ecrit_vente_vr_reglement_sn_et_paiement_relie` |
| Dates hors empreinte non posées | `BaseBillet/reprise_des_ventes_ecriture.py:261-262` (retirer les deux `.update()`) | `test_reprise_date_d_origine_gardee_sur_vente_et_reglements` |
| Ordre non chronologique | `BaseBillet/reprise_des_ventes_ecriture.py:120` (`plan.ventes` → `sorted(plan.ventes, key=lambda v: v.cle_du_groupe)`) | `test_reprise_numeros_dans_l_ordre_chronologique_et_chaine_valide` |
| `save()` au lieu de `.update()` | `BaseBillet/reprise_des_ventes_ecriture.py:224` (`setattr` des champs sur `article.ligne`, puis `article.ligne.save()`) | `test_reprise_ne_declenche_ni_mail_ni_fedow_ni_laboutik`, `test_reprise_toutes_les_lignes_ont_une_vente` (ligne `P` passée `V`) |
| Garde « lieu déjà vendu » retirée | `BaseBillet/reprise_des_ventes_ecriture.py:117` (retirer l'appel) | `test_reprise_refusee_si_le_lieu_a_deja_une_vente_hors_reprise` |
| Clé de reprise retirée | `BaseBillet/reprise_des_ventes_ecriture.py:196` (`idempotency_key=None`) | `test_reprise_toutes_les_lignes_ont_une_vente` (et tout test qui retrouve une vente par sa clé) |
| Saut d'une vente déjà reprise retiré | `BaseBillet/reprise_des_ventes_ecriture.py:127` (`if vente_deja_reprise:` → `if False:`) | `test_reprise_rejouee_ne_double_rien` |
| Référence « reprise » vide | `BaseBillet/reprise_des_ventes_ecriture.py:249` (`reference_externe=""`) | `test_reprise_avoir_stripe_reference_reprise` |
| `credit_note_for` non posé | `BaseBillet/reprise_des_ventes_ecriture.py:220-223` (retirer le `if`) | `test_reprise_avoir_lie_a_la_vente_d_origine_et_credit_note_for_pose` |
| `.update()` des lignes après l'encaissement | `BaseBillet/reprise_des_ventes_ecriture.py:202-224` (déplacer la boucle après la l.256) | `test_reprise_toutes_les_lignes_ont_une_vente`, `test_reprise_numeros_dans_l_ordre_chronologique_et_chaine_valide` (vente sans article refusée) |
| Moyen du règlement `VR` : `SN` → `TR` | `BaseBillet/reprise_des_ventes.py:1140` (`PaymentMethod.STRIPE_NOFED` → `PaymentMethod.TRANSFER`) | `test_reprise_virement_recu_ecrit_vente_vr_reglement_sn_et_paiement_relie`, `test_reprise_paiement_t_devient_une_vente_virement_recu` |
| `Paiement_stripe.vente` non posé | `BaseBillet/reprise_des_ventes_ecriture.py:265` (`{"vente": vente}` → `{}`) | `test_reprise_paiement_stripe_moyen_et_montant_encaisse_poses`, `test_reprise_vente_en_attente_encaissee_par_le_webhook_sans_ecart` |
| Origine du virement reçu | `BaseBillet/reprise_des_ventes_ecriture.py:71` (`SaleOrigin.WEBHOOK` → `SaleOrigin.LESPASS`) | `test_reprise_virement_recu_ecrit_vente_vr_reglement_sn_et_paiement_relie` |
| `encaisser_vente` ignore la date reçue | `BaseBillet/services_vente.py:1943` (`= datetime_encaissement` → `= timezone.now()`) | `test_reprise_date_d_origine_gardee_sur_vente_et_reglements` |

---

## Comment tester (a la main) / Manual test

### Test 1 — passage à blanc d'un lieu
1. `docker exec lespass_django poetry run python /DjangoFiles/manage.py reprendre_les_ventes_existantes --schema lespass`
2. Lire le rapport : lignes lues, ventes par nature et statut, règlements par moyen,
   totaux, anomalies, informations, paiements Stripe sans ligne, durée.
3. Vérifier : aucun mail, aucun nom, aucun texte de `metadata` dans la sortie.

### Test 2 — rien n'est écrit
1. Compter avant : `Vente.objects.count()`, `Reglement.objects.count()`,
   `LigneArticle.objects.filter(vente__isnull=True).count()` (dans `tenant_context`).
2. Lancer la commande sans `--schema` (tous les lieux).
3. Recompter : les trois nombres sont identiques.

### Verifs DB / Playwright
- Tests automatiques : `make test ARGS="tests/pytest/test_reprise_des_ventes.py"`.
- Sur la copie de production : passage à blanc fait par l'orchestrateur (jamais par un
  ouvrier), lecture du rapport (nombres seulement).

### Test 3 (R-2) — écrire un lieu, puis relancer
1. Sur la base de dev seulement (jamais en production hors de la nuit de bascule) :
   `docker exec lespass_django poetry run python /DjangoFiles/manage.py reprendre_les_ventes_existantes --schema <lieu> --executer`
2. Lire « Écriture » : ventes écrites, sautées, chaîne des ventes valide : oui.
   Un lieu qui a déjà une vente réglée du nouveau code est refusé (« vente réglée hors
   reprise ») : rien n'est écrit.
3. Relancer la même commande : 0 vente écrite (les lignes reprises ont une vente).
4. `docker exec lespass_django poetry run python /DjangoFiles/manage.py verify_integrity --schema <lieu>` :
   chaîne valide.
