# Chantier 05-R — Reprise des ventes existantes, avant la mise en production

> **Statut** : 📝 PROJET (2026-10-02) — à valider par le mainteneur (§9), puis relecture Fable
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D1, D13, D16, R5
> Effort estimé : 3 j (2 sessions : R-1 §3-§5, R-2 §6-§7) — Dépend de : **F** (la clôture
> du nouveau modèle) et **G** (les lecteurs lisent les ventes). **À faire avant H** : H
> rend `LigneArticle.vente` obligatoire et retire les anciennes colonnes.
> **Migrations : non** (la reprise est une commande ; elle n'ajoute aucun champ, voir §5).

## 1. Le besoin

Le tronc a été écrit pour la base de **dev** : « aucune donnée historique à rattraper »
(tronc, en-tête). En **production**, chaque lieu a des années de `LigneArticle` écrites
par l'ancien code : **sans `Vente`, sans `Reglement`, sans montants entiers** (colonnes
`total_catalogue`, `part_offerte`, `total_ttc`, `total_ht`, `total_tva` à 0).

Sans reprise, la mise en production casse à deux endroits :

- **H bloque** : sa migration de vérification (H §3, étape 2) refuse toute ligne sans
  vente, avant de rendre `vente` obligatoire ;
- **les rapports mentent** : depuis F et G, les rapports, exports et totaux ne lisent
  que les ventes ; l'historique d'un lieu y serait vide.

La reprise donne à **chaque ancienne ligne** sa vente, ses montants entiers et ses
règlements, **sans changer un centime** de ce qui a été vendu, et sans rien déclencher
(ni mail, ni Fedow, ni ancien LaBoutik, ni Stripe).

## 2. Le principe

1. **On ne crée aucun article.** Les anciennes lignes restent ; la reprise les
   **rattache** à une vente et **remplit** leurs colonnes de montants, par `.update()`
   (aucun `save()`, donc aucun signal, aucune transition de statut, aucune tâche).
2. Les montants sont calculés par **la seule formule** du projet,
   `calculer_montants_article` (fiche A) : arrondi demi-haut au centime, une fois par
   article.
3. Les règlements sont **déduits des lignes** (moyen, monnaie, montant) : l'ancien code
   ne gardait pas d'autre trace de l'argent reçu.
4. Chaque vente reprise est numérotée et chaînée **comme une vente d'aujourd'hui**, dans
   l'ordre **chronologique**, à sa **date d'origine**.
5. La reprise tourne **une fois par lieu, au déploiement**, fenêtre de maintenance
   ouverte, **avant** toute nouvelle vente du lieu.

## 3. Session R-1 — une vente par encaissement réel

### 3.1 Le regroupement (une vente = un encaissement d'origine)

Règles appliquées dans cet ordre ; une ligne n'entre que dans un groupe :

| Ancienne ligne | Vente reprise |
|---|---|
| est un avoir (`credit_note_for`), un remboursement (`REFUNDED`) ou toute ligne de **quantité négative** | **une vente AVOIR par ligne**, `vente_liee` = la vente de la ligne d'origine (`credit_note_for`, sinon `metadata.original_lignearticle_uuid`, sinon vide). **Cette règle passe en premier** : l'ancien code recopiait `paiement_stripe` (et parfois `uuid_transaction`) sur les lignes négatives ; sans cet ordre, un remboursement Stripe historique tomberait dans la vente d'origine |
| a un `uuid_transaction` (caisse, tireuse, QR / NFC) | **une vente par `uuid_transaction`** ; origine, point de vente, carte, client lus sur les lignes |
| a un `paiement_stripe` (en ligne, panier, abonnement) | **une vente par paiement** (R5) ; `Paiement_stripe.vente` posé |
| toute autre ligne (admin, API, gratuit, webhook Fedow) | **une vente par ligne** |

Les ventes d'un lieu sont traitées dans l'ordre de la **date la plus ancienne** de leurs
lignes. Une vente AVOIR passe toujours après sa vente liée.

### 3.2 Le statut de la vente reprise

| Lignes du groupe | Vente |
|---|---|
| toutes payées ou validées (`VALID`, `PAID`, `FREERES`, `CREDIT_NOTE`, `REFUNDED`) | `REGLEE`, numérotée, chaînée |
| jamais payées (`CANCELED`, `FAILED`, `UNPAID`) | `ANNULEE`, sans numéro |
| paiement jamais constaté (`CREATED`) | `EN_ATTENTE`, sans numéro (D16) |
| statuts mélangés dans un même groupe | **anomalie** (§7.3) |

## 4. Session R-1 — les montants et les règlements

### 4.1 Les montants de chaque article

Par `calculer_montants_article` : prix unitaire = `amount`, quantité = `qty`, taux = `vat`.
La part offerte suit **les règles d'aujourd'hui** :

- moyen historique `FREE` à montant non nul → entièrement offert, source `OFFRIR` (fiche A,
  règle « offert à montant non nul ») ;
- part payée en jetons (moyen `LG`) → **vente ordinaire**, part offerte 0, **TVA 0**
  (D8 bis, fiche E §3.5 : la dette des jetons est soldée, compte 707900) ;
- sinon part offerte 0.

Les **anciennes lignes fractionnées** (une part par moyen, `qty` non entière, chantier 04)
gardent leur découpage : chaque part est un article, arrondi une fois.

### 4.2 Les règlements de chaque vente

- **un règlement par couple (moyen, monnaie)** présent dans la vente ; montant = Σ des
  **nets** des articles payés par ce moyen (déjà arrondis : les égalités tiennent par
  construction) ;
- la part offerte : le règlement `FREE` qu'écrit déjà la règle du service ; une part
  payée en jetons a un vrai règlement `LG` (D8 bis), compté comme les autres moyens ;
- vente Stripe : moyen = `Paiement_stripe.moyen`, à défaut le moyen des lignes ; relié au
  paiement ; **pas d'écart d'encaissement** (le montant reçu par Stripe n'a pas été
  gardé : on écrit Σ des nets) ;
- vente AVOIR : règlement négatif au moyen de la ligne d'avoir. **Référence externe** :
  `"reprise"` pour un ancien remboursement Stripe (statut `REFUNDED`), vide sinon. Une
  référence vide sur un règlement Stripe négatif veut dire, depuis D27, « remboursement à
  faire à la main » (lu par la fiche F) : sans cette marque, tous les remboursements
  historiques seraient comptés comme « à faire » (Q7) ;
- vente à 0 (gratuite) : aucun règlement.

`verifier_egalites(vente)` est appelée sur **chaque** vente reprise avant l'encaissement.

## 5. Session R-1 — numéro, date, chaîne

- **Date** : `datetime_creation` et `datetime_encaissement` = la date d'origine (la plus
  récente des lignes du groupe). `encaisser_vente` pose « maintenant » : la reprise passe
  par une **variante** qui reçoit la date (même verrou, mêmes égalités, même empreinte),
  sans changer le comportement de `encaisser_vente` pour les ventes d'aujourd'hui.
- **Numéro** : 1, 2, 3… dans l'ordre chronologique du lieu. La reprise **refuse** de
  tourner dans un lieu qui a déjà une vente `REGLEE` (sinon les numéros ne suivraient
  plus l'ordre du temps).
- **Empreinte** : la chaîne `calculer_hmac_vente` est calculée dans cet ordre ;
  `verifier_chaine_ventes` passe à la fin.
- **Marque de reprise, sans migration** : `idempotency_key = "reprise-<clé du groupe>"`
  (uuid de transaction, uuid de paiement ou uuid de ligne). Elle distingue une vente
  reprise et rend la reprise **rejouable** : un groupe déjà repris est sauté.

## 6. Session R-2 — clôtures, rapports, exports, archive légale

1. *(Sans objet — mainteneur, 2026-10-04 : la caisse V2 `laboutik` n'a jamais été en production — absente de la branche `main` — ni l'ancienne archive LNE, ni des clôtures. Il n'y a donc aucune ancienne chaîne de lignes de caisse à archiver ni à vérifier. Ce qui compte : ne perdre aucune vente de l'ancien système, toutes converties dans le nouveau modèle. G-1d fait passer l'archive et `verify_integrity` sur les ventes.)* ~~**Avant** la reprise, pour chaque lieu (procédure documentée, pas de code nouveau) :~~
   - `manage.py verify_integrity` : l'ancienne chaîne des lignes de caisse est intacte ;
   - `manage.py archiver_donnees` : l'archive fiscale de l'ancien modèle est produite et
     rangée hors de la base. **H retire ensuite ces colonnes** (`hmac_hash`,
     `previous_hmac`) : l'archive est la seule trace qui reste.
2. **Clôture de reprise** (Q2) : à la fin de la reprise d'un lieu, une clôture du
   nouveau modèle couvre toute la période reprise, jusqu'à l'heure de bascule. Sans
   elle, la **première clôture** du nouveau modèle contiendrait des années de ventes.
3. **FEC et rapports d'avant la bascule** (Q3) : ils ont été produits par l'ancien code.
4. **Anciennes clôtures `laboutik.ClotureCaisse`** (Q4) : documents de caisse d'origine ;
   H retire le modèle.
5. **Rattrapage automatique des clôtures** (constat F-2e, 2026-10-03) : la tâche horaire
   crée toutes les semaines / mois / années finis et non vides qui manquent, depuis la
   première vente du lieu. Après la reprise de plusieurs années de ventes, le premier
   passage créerait des centaines de clôtures dans une seule sous-tâche (limite de temps
   Celery) et enverrait un mail par clôture. À décider avec Q2 (clôture de reprise) :
   une date de départ du rattrapage (la bascule) ou un plafond par passage.

## 7. Session R-2 — l'outil

### 7.1 La commande

`manage.py reprendre_les_ventes_existantes` :

- **par lieu** (`--schema`) ou tous les lieux ;
- **passage à blanc par défaut** : rien n'est écrit ; le rapport donne, par lieu, le
  nombre de lignes, de ventes par type, de règlements par moyen, les totaux (ancien
  calcul `amount × qty` et nouveau calcul, à comparer), les anomalies, et la durée
  estimée ;
- `--executer` pour écrire ; **une transaction par vente reprise** (une coupure en
  cours de route se reprend en relançant : les groupes repris sont sautés) ;
- **garde-fou** : refus si le lieu a déjà une vente `REGLEE` qui n'est pas une reprise ;
- aucune requête réseau (ni Stripe, ni Fedow, ni ancien LaBoutik).

### 7.2 L'ordre de déploiement

1. fenêtre de maintenance, caisses fermées ;
2. archive légale (§6.1) ;
3. migrations A à G — **avant**, vérifier dans chaque lieu (passage à blanc) : (a) les tables
   `comptabilite_comptecomptable` et `comptabilite_mappingmoyendepaiement` sont vides
   (la migration `comptabilite/0004` les supprime sans recopie) ; (b) aucun lieu n'a
   l'ancien plan de caisse (comptes à 7 chiffres, `41910000`…) : sinon, après le
   chargement du plan par défaut, les recharges iraient au 419100 et les moyens `LE` /
   `LG` resteraient sur l'ancien compte. D'après le mainteneur (2026-10-02), aucun
   compte comptable n'existe en production : les deux vérifications doivent rendre
   « rien » ; sinon, STOP et règle à décider (contre-relecture Fable de E, I-1, M-6) ;
4. passage à blanc, lecture du rapport, **zéro anomalie** ;
5. `--executer` ;
6. `verifier_chaine_ventes` et la migration de vérification de H (aucune ligne sans
   vente) ;
7. ouverture ; puis, plus tard, H.

### 7.3 Les anomalies

Exemples : statuts mélangés dans un groupe ; avoir dont la ligne d'origine est
introuvable ; ligne d'argent sans moyen ; total ancien ≠ total nouveau de plus d'un
centime par article. **La commande ne devine rien** : chaque type d'anomalie vu en
passage à blanc devient une règle décidée avec le mainteneur, ajoutée à la fiche, puis
testée.

## 8. Tests

Fichier `tests/pytest/test_reprise_des_ventes.py`, **schéma dédié** (`FastTenantTestCase`,
tronc §8.5) : les anciennes lignes sont fabriquées par `LigneArticle.objects.create`
**sans vente**, une par forme réelle (caisse à un moyen, cascade en parts, tireuse, QR,
Stripe simple, panier, abonnement, admin, gratuit, webhook Fedow, avoir admin,
remboursement Stripe, offert, jetons).

| # | Test |
|---|---|
| 1 | `test_reprise_toutes_les_lignes_ont_une_vente` |
| 2 | `test_reprise_une_vente_par_transaction_de_caisse` |
| 3 | `test_reprise_une_vente_par_paiement_stripe` |
| 4 | `test_reprise_avoir_lie_a_la_vente_d_origine` |
| 5 | `test_reprise_egalites_tenues_pour_chaque_vente` |
| 6 | `test_reprise_numeros_dans_l_ordre_chronologique_et_chaine_valide` |
| 7 | `test_reprise_date_d_origine_gardee` |
| 8 | `test_reprise_ne_declenche_ni_mail_ni_fedow_ni_laboutik` (aucune tâche Celery, aucun appel réseau) |
| 9 | `test_reprise_passage_a_blanc_n_ecrit_rien` |
| 10 | `test_reprise_rejouee_ne_double_rien` |
| 11 | `test_reprise_refusee_si_le_lieu_a_deja_des_ventes` |
| 12 | `test_reprise_anomalie_signalee_et_rien_ecrit_pour_le_groupe` |
| 13 | `test_reprise_lignes_jamais_payees_vente_annulee_sans_numero` |
| 14 | `test_reprise_totaux_identiques_a_l_ancien_calcul_au_centime_pres` |

Mutations attendues : une vente par ligne au lieu d'une par transaction ; date
« maintenant » au lieu de la date d'origine ; ordre non chronologique ; `save()` au lieu
de `.update()` (les signaux partent) ; garde « lieu déjà vendu » retirée ; clé de reprise
retirée (rejeu en double).

## 9. Questions au mainteneur (avant toute session)

- **Q1 — Volume et calendrier.** Combien de lieux en production, et combien de lignes
  pour les plus gros ? La reprise tourne-t-elle pendant **une** fenêtre de maintenance
  pour tous les lieux, ou lieu par lieu ? (Défaut : lieu par lieu, chaque lieu fermé le
  temps de sa reprise.)
- **Q2 — Clôture de reprise.** Écrire une clôture du nouveau modèle qui couvre tout
  l'historique repris, jusqu'à l'heure de bascule ? (Défaut : oui, une par lieu, marquée
  « reprise ».)
- **Q3 — FEC et rapports d'avant la bascule.** Le nouveau FEC peut-il être produit pour
  une période d'avant la bascule (il différerait de l'ancien, déséquilibré) ? (Défaut :
  non, refus clair pour une période d'avant la bascule ; les anciens exports font foi.)
- **Q4 — Anciennes clôtures `ClotureCaisse`.** Avant que H retire le modèle, les
  exporter dans l'archive légale (§6.1) ? (Défaut : oui.)
- **Q5 — Règlements Stripe sans montant reçu.** L'ancien code n'a pas gardé le montant
  reçu par Stripe. Écrire Σ des nets (défaut), ou relire chaque paiement chez Stripe (des
  milliers d'appels réseau) ?
- **Q7 — Anciens remboursements Stripe.** Leur identifiant de remboursement n'a pas été
  gardé. Marquer leur règlement « reprise » (défaut) pour que F ne les compte pas comme
  « remboursement à faire à la main », ou faire lire à F seulement l'après-bascule ?
- **Q6 — Une vente AVOIR par ligne d'avoir.** Un ancien remboursement de plusieurs
  billets donne plusieurs ventes AVOIR. Acceptable ? (Défaut : oui, exact et simple.)

## 10. Ce que la fiche ne change pas

Aucune ligne n'est supprimée ; aucun montant vendu ne change ; aucune nouvelle colonne ;
le comportement des ventes d'aujourd'hui (`encaisser_vente`) est inchangé ; `kiosk/`
intouché.
