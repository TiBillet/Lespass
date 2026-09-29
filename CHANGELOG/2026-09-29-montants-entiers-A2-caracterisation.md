# Tests de caractérisation avant le chantier « montants entiers » / Characterization tests before the "whole amounts" work

**Date :** 2026-09-29
**Migration :** Non

## Resume / Summary

**Refactoring interne / tests seulement — Internal refactoring / tests only.** Aucun code
de production modifié. / No production code changed.

**Quoi / What :** des tests de caractérisation figent le comportement ACTUEL de la
logique métier des ventes : statuts des paiements, lignes de vente, réservations,
billets, adhésions, bookings, commandes ; tâches Celery demandées (noms et arguments) ;
charge utile envoyée à l'ancien LaBoutik. Ils sont verts sur le code actuel et doivent
le rester, sans modification, de la fiche B à la fiche H (sauf la liste fermée de la
fiche A′ §4). Livrés en 4 sessions (A′-1 à A′-4). /
Characterization tests freeze the CURRENT sales business logic (statuses, requested
Celery tasks, legacy LaBoutik payload). Green on the current code, they must stay green,
unchanged, through sheets B to H.

**Pourquoi / Why :** le chantier 05 touche tous les chemins où l'argent entre ou sort,
sans devoir changer la logique métier. Un test de caractérisation qui tombe pendant une
fiche = une logique métier changée sans le vouloir. /
Chantier 05 touches every money path without changing business logic: a failing
characterization test means an accidental change.

Chantier : `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-A2-caracterisation.md` ;
détail : `CHANTIER-05-machine-a-etats.md` §6.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/pytest/test_caracterisation_en_ligne.py` | nouveau (A′-1) : 7 tests, parcours en ligne P1, P2, P3, P15 et T13 ; assistant commun `etat_metier()` (importé par les fichiers suivants) |
| `tests/pytest/test_caracterisation_annulations.py` | nouveau (A′-2) : 5 tests, annulations et avoirs P5, P6, P7, P8 ; importe `etat_metier()` et les gestes d'achat en ligne de A′-1 |
| `tests/pytest/test_caracterisation_admin_api.py` | nouveau (A′-3) : 4 tests, ventes de l'admin et de l'API v2 (P13, P16) et décision « Stripe ou gratuit » (T21) ; importe `etat_metier()` et les gestes d'achat en ligne de A′-1 |
| `tests/pytest/test_caracterisation_caisse.py` | nouveau (A′-4) : 4 tests, caisse P9, P12, double envoi (E23), clôture (T11, D29) ; importe `etat_metier()` et `arguments_des_taches()` de A′-1 |
| `tests/pytest/test_caracterisation_qr.py` | nouveau (A′-4) : 2 tests, paiement par QR code P10 (deux monnaies, échec Fedow, T2) ; importe `etat_metier()` et `arguments_des_taches()` de A′-1 |

### Session A′-1 — ventes en ligne (Stripe simulé)

| Test | Ce qu'il fige |
|---|---|
| `test_billets_directs_payes_statuts_et_taches` | P1 : deux tarifs sans panier ; au retour de Stripe, paiement `V`, 2 lignes `V`, réservation `P`, 3 billets `K` ; tâches `webhook_reservation`, `ticket_celery_mailer`, puis `send_sale_to_laboutik` une fois par ligne (arguments vérifiés) |
| `test_panier_mixte_paye_une_seule_fois` | P2 : panier adhésion + 2 billets + 1 billet + ressource + réservation gratuite ; un seul checkout ; tout payé, Commande `PAID` ; 12 tâches (triées) ; charges utiles `LigneArticleSerializer` des 3 ventes envoyées (moyen `SN`, montant, quantité, statut) |
| `test_paiement_reste_paye_puis_rejeu_repasse_les_avoirs_en_paye` | T13 : rejeu `P → P` → l'avoir de l'admin repasse `P` (bug connu, D33) |
| `test_adhesion_en_ligne_payee` | P2 adhésion seule : `ONCE`, échéance, `contribution_value` = prix vendu ; facture tout de suite, puis webhook, récompense, LaBoutik en `on_commit` (arguments vérifiés) |
| `test_sepa_soumis_statuts_et_mail_en_attente` | P3 : paiement `W`, ligne `U`, adhésion `PP`, tâche `send_membership_sepa_pending_user` (T1) |
| `test_sepa_refuse_lignes_en_echec_adhesion_rearmee` | P3 : paiement `F`, ligne `D`, adhésion `AV`, tâche `send_payment_refused_user` (T5) |
| `test_renouvellement_abonnement_iteration_et_statut_auto` | P15 : nouveau paiement et ligne `V`, adhésion `AUTO`, itération 1 → 2, `last_stripe_invoice` mise à jour |

Choix d'écriture à connaître pour la suite :
- `etat_metier(paiement, reservations, adhesion, booking, commande, taches_demandees)` :
  `reservations` est une **liste** (le panier mixte en a trois) ; seules les clés des
  objets passés apparaissent.
- Chaque test oublie les tâches de sa préparation (`lieu.taches_demandees.clear()`) et
  ne fige que celles de l'action testée (retour de Stripe, rejeu, webhook).
- Le panier mixte contient une **réservation gratuite** en plus du panier de
  `test_commande_service.py` : c'est la seule réservation que `set_ligne_article_paid`
  ne retrouve que par la Commande. Sans elle, la mutation « ne plus ajouter les
  réservations de la Commande » ne serait vue par aucun test.

### Session A′-2 — annulations et avoirs (Stripe simulé, remboursement compris)

| Test | Ce qu'il fige |
|---|---|
| `test_annuler_un_billet_stripe_rembourse_un_billet` | P5 : 3 billets payés par Stripe, le client en annule un depuis « Mon compte » : `Refund.create` appelé **une** fois avec 1000 centimes, paiement `H`, ligne `R` de quantité −1, billet `R`, réservation `P` ; tâches `send_refund_to_laboutik` (charge utile `SN`) puis `send_ticket_cancellation_user` |
| `test_annulation_utilisateur_reservation_admin_especes_cree_un_avoir` | P6, par le client : vente admin espèces de 2 billets annulée depuis « Mon compte » : avoir `N` de quantité −2, charge utile moyen `CA`, réservation et billets annulés, aucun appel Stripe. **Change en D (D31)** |
| `test_annuler_un_billet_caisse_offert_cree_un_avoir` | P6, par l'admin : billet vendu à la caisse et offert (ligne `NA` à 1500 centimes), annulé par l'action « Cancel and refund » des billets : avoir `N` de 1500 centimes, moyen `NA`. **Change en G** (`total_paid()` sur `total_ttc`) |
| `test_annulation_adhesion_avoirs_de_tous_les_renouvellements` | P7 : adhésion payée 3 fois (achat `SN` + 2 renouvellements `SR`), annulée par l'admin avec avoirs : `AC`, **3** avoirs, aucun appel Stripe ; 3 `send_refund_to_laboutik` puis `webhook_membership`. **Change en D (D30)** |
| `test_avoirs_admin_et_annulation_adhesion_n_appellent_pas_stripe` | P7/P8 (T8, D27) : avoir admin sur un billet payé par Stripe + annulation d'une adhésion payée par Stripe : `Refund.create` jamais appelé, paiements restés `V`, un avoir `N` par ligne |

**Retiré de la spec (décision du mainteneur, 2026-09-29) :
`test_annuler_reservation_caisse_payee_en_cascade_avoir_sur_la_part_rattachee`**. Le parcours n'existe pas dans le code : aucun chemin de caisse ne crée de
réservation à partir de lignes coupées en parts. `_creer_billets_depuis_panier` n'est
appelée qu'après `_creer_lignes_articles` (un seul moyen, pas de parts :
`laboutik/views.py` l.7417-7457 et l.7642-7682) ; les chemins en cascade
(`_payer_par_nfc` l.8457, `_executer_paiement_complementaire` l.9562 et l.10147) ne
rattachent que les adhésions. A′ compte donc 22 tests. /
Removed from the spec: no register path creates a reservation from cascade lines.

Choix d'écriture à connaître pour la suite :
- Le lieu de ce fichier simule aussi `stripe.Refund.create` (`lieu.remboursement_stripe`) :
  aucun test ne peut rembourser pour de vrai.
- « Mon compte » exige un compte actif et un portefeuille (sinon appel HTTP à Fedow) :
  `client_de_mon_compte()` les pose par `update()` (état de départ, aucun signal).
- La vente caisse offerte passe par la vraie route de paiement de la caisse
  (`POST /laboutik/paiement/payer/`, `gift`, carte primaire en mode gérant) : voir
  session A′-5.
- L'adhésion payée trois fois est un état de départ fabriqué par `create(status=…)`.

### Session A′-3 — admin et API v2 (Stripe, Fedow et Celery simulés)

| Test | Ce qu'il fige |
|---|---|
| `test_adhesion_creee_dans_l_admin_passe_par_trigger_a` | P16 : formulaire admin « Ajouter une adhésion », 20 € en espèces : adhésion `D` avec échéance, une ligne `V` (passée par `trigger_A`) ; tâches `send_membership_invoice_to_email`, puis en `on_commit` `connexion_celery_mailer`, `webhook_membership`, récompense, `send_sale_to_laboutik`, `webhook_membership` (arguments vérifiés) ; charge utile `CA`, 2000 centimes |
| `test_billets_vendus_dans_l_admin_offert_montant_zero` | P16 / T12 : formulaire admin « Ajouter une réservation », 2 billets d'un tarif à 15 €, « Offert » : réservation `V`, 2 billets `K`, une ligne `V` ; tâches `send_sale_to_laboutik` puis `ticket_celery_mailer` (tout de suite) ; charge utile `NA`, **0 centime**, quantité 2. **Change en D (D32)** |
| `test_recharge_api_v2_echec_puis_nouvel_essai_meme_ligne` | P13 : même recharge cadeau (300 jetons) envoyée 3 fois avec la même clé d'idempotence : Fedow en panne → 502, ligne `D` ; nouvel essai → la même ligne est `O` pendant l'appel à Fedow, puis `V`, 201 ; rejeu → 208, corps identique au 201, Fedow pas rappelé. Une seule ligne ; Fedow reçoit deux fois la même ligne |
| `test_decision_stripe_ou_gratuit_billets_et_booking` | T21 : sans panier, 2 billets à 10 € → une session Stripe, réservation `U`, billets `N`, ligne `U` ; 1 billet à 0 € → aucune session, réservation `FA`, billet `K`, ligne `V` ; 1 h de ressource à 12 € → une session, booking `WP`, ligne `U` ; 1 h à 0 € → aucune session, booking `FU`, ligne `V` |

Choix d'écriture à connaître pour la suite :
- Les deux ventes de l'admin passent par le **vrai formulaire** (`client.post` sur
  `/admin/BaseBillet/membership/add/` et `/admin/BaseBillet/reservation/add/`) : le
  formulaire d'adhésion ne remplit le tarif et le moyen de paiement que par l'admin
  (champs du `ModelForm` construit par `get_form`). `FedowAPI` du formulaire
  d'adhésion est simulé (`clean_email` demande le portefeuille en HTTP).
  `vente_admin_especes` (fabriques_reservation.py) n'est pas réutilisée : elle simule
  `send_sale_to_laboutik.delay` et `ticket_celery_mailer.delay`, que ce test doit voir.
- La recharge cadeau retrouve sa ligne par le produit « Recharge <monnaie> », et
  prouve « même ligne » par l'identifiant de ligne que Fedow reçoit dans ses
  métadonnées : jamais par la colonne `idempotency_key`, que la fiche H retire.
- La décision « Stripe ou gratuit » se lit au nombre de sessions Stripe créées
  (`mock_stripe.mock_create.call_count`) et aux statuts.

### Session A′-4 — caisse et QR code (Fedow et Celery simulés)

| Test | Ce qu'il fige |
|---|---|
| `test_vente_caisse_adhesion_sans_facture_ni_envoi_laboutik` | P9 : adhésion à 20 € vendue en espèces (`POST /laboutik/paiement/payer/`, adhérente identifiée par e-mail) : une ligne `V`, adhésion `L` (`LABOUTIK`) avec échéance ; **une seule** tâche, `webhook_membership` (argument vérifié) : ni facture, ni récompense, ni envoi à l'ancien LaBoutik. **Change en B-0** (facture et récompense ; renommé `…_facture_et_recompense_sans_envoi_laboutik`) |
| `test_rejeu_meme_cle_caisse_rien_en_double` | E23 : 2 bières à 5 € en espèces, envoyées deux fois avec la même clé d'idempotence : deux réponses 200, **une seule** ligne `V`, aucune tâche |
| `test_paiement_table_nfc_libere_la_table` | P12, chemin NFC : commande ouverte (`OP`) d'une table occupée, payée par une carte NFC chargée de 20 € (`POST /laboutik/commande/payer/<uuid>/`) : commande `PA`, article `SV`, table `L`, une ligne `V`, aucune tâche |
| `test_cloture_annule_les_commandes_ouvertes_et_libere_les_tables` | T11 (D29) : bouton de clôture ; commande ouverte `OP → AN`, commande servie `SV` intacte, les deux tables (`OCCUPEE`, `SERVIE`) → `L`, aucune tâche. Reste vert en G |
| `test_qr_deux_monnaies_deux_envois_laboutik_et_deux_mails` | P10 : QR code de 12,50 € payé 5 € en monnaie locale + 7,50 € en monnaie fédérée : deux lignes `V` ; tâches `send_sale_to_laboutik` ×2 puis `send_payment_success_admin`, `send_payment_success_user` (montant et e-mail vérifiés) ; charges utiles `LE` / `SF`, **`asset`** de chaque part, `amount` 1250 sur les deux, `qty` 0,4 / 0,6 ; un seul débit Fedow |
| `test_qr_echec_fedow_ligne_en_echec_rejeu_refuse` | P10, T2 : demande `O` ; Fedow en erreur au débit → ligne `D` ; seconde confirmation refusée, Fedow **pas** rappelé (un seul débit demandé), ligne toujours `D`, aucune tâche |

Choix d'écriture à connaître pour la suite :
- Les quatre tests de caisse passent par les **vraies routes** de la caisse, avec un
  administrateur du lieu connecté (la caisse accepte sa session sans carte primaire).
  Le module caisse est activé par `configuration_modifiee()` (jamais enregistré).
- Les lignes d'une vente de caisse sont retrouvées par leur **tarif**, créé pour le
  test (`pricesold__price`) : jamais par `uuid_transaction`, `carte` ou
  `point_de_vente`, que la fiche H retire. Les lignes QR sont retrouvées par les
  arguments des tâches `send_sale_to_laboutik`.
- P9 : la déclaration de l'adhérente à Fedow est simulée
  (`fedow_connect.services.declarer_wallet_user_a_fedow`, `FedowConfig.can_fedow`).
  L'adhérente n'a pas d'adhésion : le test passe par la **création**
  (`_creer_ou_renouveler_adhesion`, l.5935-5947), pas par le renouvellement.
- P12 : la carte est créditée dans la **première monnaie locale du lieu par ordre de
  nom**, lue par la même requête que la caisse (`AssetService.obtenir_assets_accessibles`,
  tests/PIEGES.md 9.97). Le test suppose que le lieu `lespass` en a une (c'est le cas
  en base de dev) ; sinon il tombe en erreur, jamais en faux vert.
- La clôture est globale au lieu et tourne sous `django_db` : la clôture créée, le
  total perpétuel et les tables / commandes des autres tests sont remis en l'état par
  le rollback. Une vente en espèces est faite avant (la clôture refuse une caisse sans
  vente, PIEGES 9.61).
- QR : la charge utile garde cinq champs, dont **`asset`** ; c'est ce qui fait tomber
  le test si `LigneArticleSerializer` perd ce champ.

### Session A′-5 — corrections de la relecture Fable

Aucun test ne fige autre chose qu'avant ; toujours 22 tests. / No test freezes anything
new; still 22 tests.

- `test_caracterisation_annulations.py` : la vente caisse offerte passe par la **vraie
  route** `POST /laboutik/paiement/payer/` (`moyen_paiement = "gift"`) et non plus par
  les fonctions privées `_creer_lignes_articles` / `_creer_billets_depuis_panier`, que
  la fiche B réécrit (remplace le choix d'écriture A′-2 ci-dessus). État de départ :
  caisse activée en mémoire (`configuration_modifiee()`), point de vente
  « billetterie » caché, administrateur du lieu connecté, carte primaire en **mode
  gérant** (`edit_mode=True`) envoyée dans `tag_id_cm` — OFFRIR un panier payant
  l'exige (`_panier_peut_etre_offert`). Mutation `edit_mode=False` : la caisse répond
  400, le test tombe. Docstring de `test_annuler_un_billet_caisse_offert_cree_un_avoir`
  sans date.
- `test_caracterisation_qr.py` : la docstring de
  `test_qr_deux_monnaies_deux_envois_laboutik_et_deux_mails` annonce qu'il **change en
  C** (envoi à l'ancien LaBoutik débranché pour le QR, renommé
  `…_aucun_envoi_laboutik_et_deux_mails`), et non plus « reste vert en G ». Nom et
  assertions inchangés.

### Comportements actuels surprenants figés / Surprising current behaviours frozen

Complété par les sessions A′-1 à A′-4. / Completed by sessions A′-1 to A′-4.

| Session | Comportement | Test | Où |
|---|---|---|---|
| A′-1 | **T13** : un paiement resté « payé » (`P`) puis rejoué (F5, webhook) repasse « payée » **toute** ligne non validée, avoir de l'admin compris (`N → P`) ; la réservation repasse `P → P` : webhook et mail des billets redemandés. Bug connu, à corriger dans un autre chantier (D33) | `test_paiement_reste_paye_puis_rejeu_repasse_les_avoirs_en_paye` | `BaseBillet/signals.py` l.42 |
| A′-1 | Le renouvellement d'abonnement demande **deux** `webhook_membership` : l'adhésion a déjà une échéance et elle est enregistrée deux fois (mise à jour après paiement, puis `set_deadline()`) | `test_renouvellement_abonnement_iteration_et_statut_auto` | `BaseBillet/triggers.py` l.137 et l.267 ; `BaseBillet/signals.py` l.518-529 |
| A′-1 | Le mail « SEPA en attente » ne part que si la **première** ligne du paiement porte le moyen `SP` (T1) | `test_sepa_soumis_statuts_et_mail_en_attente` | `ApiBillet/views.py` l.1229-1230 |
| A′-1 | SEPA refusé : `W → F` ne déclenche aucune transition, les lignes passent `D` par `update()` (T5) | `test_sepa_refuse_lignes_en_echec_adhesion_rearmee` | `ApiBillet/views.py` l.1312-1313 |
| A′-2 | Annuler une adhésion avec avoirs crée un avoir pour **chaque** paiement : l'achat et tous les renouvellements (T7) | `test_annulation_adhesion_avoirs_de_tous_les_renouvellements` | `BaseBillet/views.py` l.4670-4687 |
| A′-2 | Un billet **offert** à la caisse garde son prix (`amount` = 1500, moyen `NA`) : `total_paid()` le compte comme payé, et son annulation crée un avoir « offert » du prix entier | `test_annuler_un_billet_caisse_offert_cree_un_avoir` | `BaseBillet/models.py` l.2921-2926, l.3068-3072 |
| A′-2 | L'admin qui annule une adhésion ou émet un avoir sur une vente Stripe n'appelle jamais Stripe : l'avoir est seulement comptable (T8, D27) | `test_avoirs_admin_et_annulation_adhesion_n_appellent_pas_stripe` | `Administration/admin_tenant.py` l.2059-2105 ; `BaseBillet/views.py` l.4666-4688 |
| A′-2 | **Constaté, non figé** : annuler UN billet vendu à la caisse (bouton du billet dans « Mon compte », ou action admin sur une partie des billets) échoue toujours : « Aucun paiement remboursable n'a été trouvé ». La ligne de caisse et le billet n'ont pas le même tarif vendu (`ProductSold` sans événement pour la ligne, avec événement pour le billet), donc `_lignes_hors_stripe(pricesold_ids=…)` ne trouve rien. Seule l'annulation de la réservation entière marche | — (signalé au mainteneur) | `laboutik/views.py` l.5384-5388 et l.6554-6558 ; `BaseBillet/models.py` l.3168-3181 |
| A′-3 | L'ajout d'une adhésion dans l'admin envoie un **mail de connexion** à l'adhérente dont l'adresse n'est pas confirmée : `MembershipAddForm.save()` appelle `get_or_create_user(email)` avec `send_mail=True` par défaut (`clean_email` l'appelle, lui, avec `send_mail=False`) | `test_adhesion_creee_dans_l_admin_passe_par_trigger_a` | `Administration/admin_tenant.py` l.1381 et l.1438 ; `AuthBillet/utils.py` l.149-154 |
| A′-3 | L'adhésion créée dans l'admin demande **deux** `webhook_membership` : `trigger_A` pose l'échéance et enregistre l'adhésion (`set_deadline()`), puis le `post_save` de la création voit l'échéance à son tour. Même cause que le renouvellement (A′-1) | `test_adhesion_creee_dans_l_admin_passe_par_trigger_a` | `BaseBillet/signals.py` l.496-529 ; `BaseBillet/models.py` l.4169 |
| A′-3 | Billet **offert** vendu dans l'admin : ligne à `amount = 0` (le prix du tarif ne reste que sur le tarif vendu), charge utile `NA` à 0 centime (T12, change en D : D32). Ses deux tâches partent tout de suite, pas en `on_commit` | `test_billets_vendus_dans_l_admin_offert_montant_zero` | `Administration/admin_tenant.py` l.3092-3110 |
| A′-3 | Recharge API v2 : le rejeu 208 est **reconstruit depuis la ligne** (`metadata`, `amount`, `asset`), pas stocké ; il lit `ligne.asset` (T18, à adapter en H) | `test_recharge_api_v2_echec_puis_nouvel_essai_meme_ligne` | `api_v2/views.py` l.807-813, l.916-933 |
| A′-4 | Adhésion vendue à la caisse : statut `LABOUTIK`, **ni facture, ni récompense, ni envoi à l'ancien LaBoutik** ; seul `webhook_membership` part. Décidé : la facture et la récompense sont un bug, corrigé en B-0 (SUIVI §5) | `test_vente_caisse_adhesion_sans_facture_ni_envoi_laboutik` | `laboutik/views.py` l.5869-5950 |
| A′-4 | Clôture : la table **servie** est libérée alors que sa commande servie (`SV`) n'est **pas payée** ; cette commande n'est pas annulée et garde sa table (libre). Seules les commandes `OP` sont annulées | `test_cloture_annule_les_commandes_ouvertes_et_libere_les_tables` | `laboutik/views.py` l.2727-2737 |
| A′-4 | **Constaté, non figé** : la clôture est globale au lieu (numéro, tables, commandes de tous les points de vente), mais le début de la période est cherché depuis la dernière clôture **du point de vente qui clôture**. Depuis un point de vente qui n'a jamais clôturé, la période commence à la toute première vente de caisse du lieu | — (signalé) | `laboutik/views.py` l.2601-2632 |
| A′-4 | QR code payé sur deux monnaies : chaque ligne recréée porte le montant **entier** (1250) et sa part dans la quantité (0,4 / 0,6) ; une tâche `send_sale_to_laboutik` **par ligne**, et les deux mails, partent **tout de suite** (`.delay`, pas en `on_commit`), alors que la caisse n'envoie jamais rien à l'ancien LaBoutik | `test_qr_deux_monnaies_deux_envois_laboutik_et_deux_mails` | `BaseBillet/views.py` l.2294-2340 |

### Mutations

Jouées par l'orchestrateur. / Played by the orchestrator.

| Session | Mutation du code de production | Tests qui tombent |
|---|---|---|
| A′-1 | `BaseBillet/triggers.py` `trigger_B` : `self.ligne_article.status = LigneArticle.VALID` retiré | `test_billets_directs_payes_statuts_et_taches` (+ `panier_mixte`, `rejeu`) |
| A′-1 | `BaseBillet/signals.py` `set_ligne_article_paid` : `if commande_de_ce_paiement:` → `if False:` | `test_panier_mixte_paye_une_seule_fois` |
| A′-1 | `BaseBillet/triggers.py` `trigger_A` : `send_membership_invoice_to_email.delay(...)` → `None` | `test_adhesion_en_ligne_payee` (+ `panier_mixte`, `renouvellement`) |
| A′-1 | `ApiBillet/views.py` webhook SEPA : `== PaymentMethod.STRIPE_SEPA_NOFED` → `!=` | `test_sepa_soumis_statuts_et_mail_en_attente` (+ `sepa_refuse`) |
| A′-1 | `ApiBillet/views.py` `async_payment_failed` : `.filter(status=PAYMENT_PENDING)` → `.none()` | `test_sepa_refuse_lignes_en_echec_adhesion_rearmee` |
| A′-2 | `PaiementStripe/utils.py` `partial_refund_payment` : `if specified_quantity:` → `if False:` | `test_annuler_un_billet_stripe_rembourse_un_billet` |
| A′-2 | `BaseBillet/views.py` annulation d'adhésion : `break` après le premier avoir | `test_annulation_adhesion_avoirs_de_tous_les_renouvellements` |
| A′-3 | `BaseBillet/triggers.py` `trigger_A` : facture retirée (`email_sended = None`) | `test_adhesion_creee_dans_l_admin_passe_par_trigger_a` |
| A′-3 | `api_v2/views.py` recharge : nouvelle ligne au lieu de réutiliser la `FAILED` | `test_recharge_api_v2_echec_puis_nouvel_essai_meme_ligne` |
| A′-4 | `laboutik/views.py` `_creer_ou_renouveler_adhesion` (création) : `status=Membership.LABOUTIK` → `ONCE` | `test_vente_caisse_adhesion_sans_facture_ni_envoi_laboutik` |
| A′-4 | `laboutik/views.py` clôture : annulation des commandes `OPEN` retirée | `test_cloture_annule_les_commandes_ouvertes_et_libere_les_tables` |
| A′-4 | `ApiBillet/serializers.py` `LigneArticleSerializer` : champ `asset` retiré | `test_qr_deux_monnaies_deux_envois_laboutik_et_deux_mails` |

11 mutations de l'annexe §6.4, 12 jeux : la mutation `trigger_A` est jouée deux fois (A′-1 et A′-3).
Empreintes `sha256` des fichiers mutés identiques avant et après.

---

## Comment tester (a la main) / Manual test

Rien à tester à la main : aucun code de production ne change.
/ Nothing to test by hand: no production code changes.

### Lancer les tests / Run the tests

```bash
make test ARGS="tests/pytest/test_caracterisation_en_ligne.py"
make test ARGS="tests/pytest/test_caracterisation_annulations.py"
make test ARGS="tests/pytest/test_caracterisation_admin_api.py"
make test ARGS="tests/pytest/test_caracterisation_caisse.py tests/pytest/test_caracterisation_qr.py"
```

Attendu : `7 passed`, `5 passed`, `4 passed`, puis `6 passed` (`22 passed` pour
`make test ARGS="tests/pytest/test_caracterisation_*.py"`). Les lancer deux fois de suite : ils restent verts (transaction
annulée à la fin de chaque test, `django_db`).

### Traductions / Translations

Aucune nouvelle chaîne traduisible. / No new translatable string.
