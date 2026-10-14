# Chantier 06-B — Le module Dolibarr « TiBillet »

> **Statut** : 🛠️ **CODÉ le 2026-10-13** dans `/home/jonas/TiBillet/dev/tibillet-dolibarr/` (dépôt à part,
> non commité), installé dans la pile de dev. Spec relue par Fable le 2026-10-13 : corrections
> au §10, qui **prime sur le reste de la fiche** en cas d'écart.
> Contexte : [`README.md`](README.md) (décisions §7, essai d'import §9) ;
> l'API qu'il lit : [`CHANTIER-06-A-api-comptable.md`](CHANTIER-06-A-api-comptable.md)
> (codée le 2026-10-13).
> Code Dolibarr lu le 2026-10-13 : `/home/jonas/Gits/dolibarr`, branche `develop`,
> commit `11e66e00fc1` (≈ v24). Instance de test : `/home/jonas/Gits/dolibarr_stack`
> (Dolibarr 24.0.1). Abréviation : `H` = `htdocs/`.
> Effort estimé : 2,5 à 3 j.

---

## 1. Le but, en une phrase

Chaque nuit, Dolibarr va chercher chez TiBillet les clôtures du lieu qu'il n'a pas
encore, et range leurs écritures dans son grand livre, **non validées**. Le comptable
relit, puis valide.

## 2. Expliqué simplement (FALC)

1. **Une fois** : l'admin Dolibarr installe le module, colle l'adresse du lieu TiBillet
   et la clé d'API (droit « Comptabilité (lecture) »), puis clique « Tester ».
2. **Chaque nuit**, une tâche planifiée :
   - lit le plan comptable de TiBillet et **crée dans Dolibarr les comptes qui
     manquent** (sans jamais toucher un compte existant) ;
   - demande les clôtures **après la dernière importée** ;
   - pour chaque clôture : crée les **journaux** qui manquent (BAR, WEB…), écrit les
     écritures, et note la clôture comme importée.
3. Si TiBillet refuse une clôture (un compte manque dans le plan du lieu), la tâche
   **s'arrête** et le dit. La nuit suivante, elle reprend à la même clôture.
4. Une clôture mal rangée (le lieu a corrigé son plan après coup) peut être **retirée
   puis réimportée**, tant que le comptable ne l'a pas validée.

## 3. Ce qu'on sait déjà (vu ou lu, avec preuves)

| Sujet | Fait | Preuve |
|---|---|---|
| Écrire au grand livre | `BookKeeping::createStd($user)` : insère `piece_num` tel quel, contrôle seulement la date (exercice ouvert), arrondit les montants, rend l'id. **Pas** `create()` : il écrase `piece_num` et voit de faux doublons quand `fk_doc = 0` | `H/accountancy/class/bookkeeping.class.php` l.671 (createStd), l.227-409 (create) |
| Numéro de pièce | `getNextNumMvt()` = `MAX(piece_num)+1` de l'entité, **sans verrou** | même fichier l.2026 |
| Exercice | Par défaut, la date doit être dans un **exercice ouvert** ; **aucun exercice = refus** (`ErrorBookkeepingDocDateNotOnActiveFiscalPeriod`) | l.2710-2745 |
| Comptes | `AccountingAccount::fetch(0, $numero, 1)` (plan actif seulement) ; `create($user)` : rien n'est contrôlé, `active` vaut 0 et `pcg_type` vaut `XXXXXX` si on ne les remplit pas ; unicité `(account_number, entity, fk_pcg_version)` | `H/accountancy/class/accountingaccount.class.php` l.185, l.255-309 |
| Plan actif | `fk_pcg_version` = `SELECT pcg_version FROM llx_accounting_system WHERE rowid = CHARTOFACCOUNTS` | `H/accountancy/admin/card.php` l.89, l.104 |
| Zéros de droite | `clean_account()` = `rtrim($numero, "0")`, appliqué par l'écran et l'import, **pas** par `create()` ni `createStd()` ; désactivé si `ACCOUNTING_MANAGE_ZERO` | `H/core/lib/accounting.lib.php` l.139 ; README §9 E4 (vu) |
| Journaux | `AccountingJournal::create($user)` existe (natures 1, 2, 3, 4, 5, 8, 9) ; remplir `entity` et `active = 1` | `H/accountancy/class/accountingjournal.class.php` l.116-132 |
| Tâche planifiée | `$this->cronjobs` du descripteur ; `new Classe($db)` ; **retour 0 = OK** ; message dans `$this->output` (à déclarer) et `$this->error` ; utilisateur = `global $user` (premier admin en ligne de commande) ; langue en ligne de commande = **en_US** si `MAIN_LANG_DEFAULT = auto` | `H/cron/class/cronjob.class.php` l.1299-1530 ; `scripts/cron/cron_run_jobs.php` |
| Réglages | `dolibarr_set_const` **chiffre tout seul** une constante dont le nom finit par `_KEY` (`TIBILLET_API_KEY`) ; `getDolGlobalString` la rend en clair | `H/core/lib/admin.lib.php` l.751 ; `H/core/class/conf.class.php` l.581 |
| Appel HTTP | `getURLContent($url, 'GET', '', 1, $entetes, ['https', 'http'], $localurl, …)` ; `$localurl` 0 = Internet seulement, 2 = Internet et réseau local ; succès = `empty(curl_error_no) && http_code == 200` ; les en-têtes de la requête **sont journalisés** (risque : la clé dans `dolibarr.log`) | `H/core/lib/geturl.lib.php` l.51, l.405, l.553 |
| Annuler | `deleteMvtNum($piece_num)` filtre `date_validated IS NULL` et l'entité ; **pas** `deleteByImportkey()` (ni entité, ni lignes validées) | `bookkeeping.class.php` l.1826, l.1730 |
| Doublons | Dolibarr n'en détecte aucun | README §9 E8 (vu) |
| Import manuel | Possible avec le FEC inchangé (recette du README §9) ; les profils d'import ne se réappliquent pas (bug Dolibarr) | README §9 (vu) |

Résumé de l'exploration du code Dolibarr (11 questions, pièges) :
[`ANNEXE-exploration-dolibarr.md`](ANNEXE-exploration-dolibarr.md).

## 4. Décisions de conception (proposées, à valider)

| # | Sujet | Proposition | Pourquoi |
|---|---|---|---|
| B1 | Où vit le code | **Dépôt git à part** (`tibillet-dolibarr`), monté dans `dolibarr_stack/custom/tibillet/` en dev, installé par zip en prod (« Déployer un module externe ») | Dolibarr est GPL v3, TiBillet AGPL : un module externe vit à part. Le dépôt Lespass ne contient pas de PHP. **Question au mainteneur (Q1)** |
| B2 | Source des écritures | La route **JSON** `…/entries/` (pas le fichier FEC) | Centimes entiers : pas de virgule à lire (`price2num`, langue en_US du cron) ; pas de `ValidDate` |
| B3 | Écriture | `createStd()` ligne par ligne, avec **un `piece_num` par écriture** (un par journal) pris par `getNextNumMvt()` | Dolibarr choisit le numéro : pas de mélange avec ses autres pièces (README §9 E2) |
| B4 | Une clôture = un tout | Toutes les écritures d'une clôture **et** la ligne « clôture importée » dans **une seule transaction** : tout ou rien | Une moitié de soirée dans le grand livre serait pire que rien |
| B5 | Curseur | `after_number` = **le plus grand numéro** de la table des clôtures importées. Aucune constante à tenir à jour | Une seule source de vérité |
| B6 | Doublons | Table `llx_tibillet_cloture_importee`, **unique** `(cloture_uuid, entity)` ; une clôture déjà présente est sautée | Dolibarr ne détecte rien (E8) |
| B7 | `doc_ref` | `EcritureNum` de TiBillet (`12-BAR`) ; `doc_type` = `tibillet` ; `fk_doc` = 0 ; `import_key` = `TB` + date `AAAAMMJJhhmm` (14 caractères) | Trace vers la J ; `import_key` non numérique (`updateByMvt` caste un nombre en flottant) |
| B8 | Comptes | Avant chaque passage : `GET /api/v2/accounts/` ; chaque numéro est **normalisé comme Dolibarr** (`rtrim 0` sauf `ACCOUNTING_MANAGE_ZERO`) ; s'il manque dans le **plan actif**, il est créé : libellé TiBillet, `active = 1`, `pcg_type` d'après la classe (1 CAPIT, 2 IMMO, 3 STOCK, 4 THIRDPARTY, 5 FINAN, 6 EXPENSE, 7 INCOME), `account_parent` = 0. Un compte existant n'est **jamais** modifié | Décision du README §7 ; E4 ; piège `active` / `pcg_type` |
| B9 | Journaux | Un `JournalCode` inconnu est créé avec son `JournalLib`, **nature 1 (OD)**, `active = 1` | E6 : sinon la colonne Journal est vide. La nature « ventes » ouvrirait un écran de transfert de factures sans objet. **Question au mainteneur (Q2)** |
| B10 | Refus de l'API | `409` → la tâche s'arrête, rend une erreur (`$this->error` = la phrase de TiBillet), rien n'est écrit pour cette clôture ; `404` sur une clôture listée → erreur aussi (anormal) ; erreur réseau → erreur | La tâche apparaît « en échec » dans « Travaux planifiés » : l'admin le voit |
| B11 | Exercice absent ou clos | Testé **avant** d'écrire (même règle que `validBookkeepingDate`) ; sinon arrêt avec une phrase claire : « Aucun exercice comptable ouvert pour le 12/10/2026 » | Sinon chaque ligne échoue avec un code Dolibarr peu lisible |
| B12 | Retirer une clôture | Sur la page du module : liste des clôtures importées ; bouton « Retirer » (POST + jeton) → `deleteMvtNum` de chacune de ses pièces, **seulement si aucune ligne n'est validée**, puis suppression de la ligne de la table. Le prochain passage la réimporte | Le but de R3 (non verrouillé) : corriger une erreur de plan |
| B13 | Tâche planifiée | Créée **active** à l'installation, une fois par jour à 02:30 ; elle ne fait rien (retour 0, « Module non configuré ») tant que l'adresse et la clé manquent | L'admin n'a pas à aller l'activer ailleurs. **Question au mainteneur (Q3)** |
| B14 | Réglages | `TIBILLET_URL` (adresse du lieu), `TIBILLET_API_KEY` (chiffrée par Dolibarr), `TIBILLET_RESEAU_LOCAL` (oui/non → `$localurl` 2 ou 0 ; oui seulement en dev) | Trois réglages, rien d'autre |
| B15 | Clé dans les journaux | `getURLContent` journalise les en-têtes : en prod, garder le niveau de log de Dolibarr au-dessus d'INFO, et le dire dans la doc. À vérifier au codage (si la clé apparaît vraiment) ; sinon appel cURL direct | Piège 13 de l'exploration ; non vérifié à l'exécution |
| B16 | Droits | Page du module réservée aux **admins** Dolibarr ; aucun droit propre | Simple ; la tâche tourne avec le premier admin |

## 5. Le module

```
tibillet/
├── core/modules/modTiBillet.class.php   descripteur : numero 5xxxxx, depends modAccounting,
│                                        constantes, tâche planifiée, page de réglages
├── class/importtibillet.class.php       ImportTiBillet : importerLesClotures() (la tâche),
│                                        les étapes du §6, une méthode par étape
├── admin/setup.php                      réglages, « Tester la connexion », « Importer
│                                        maintenant », liste des clôtures importées, « Retirer »
├── sql/llx_tibillet_cloture_importee.sql      table (rowid, entity, cloture_uuid,
├── sql/llx_tibillet_cloture_importee.key.sql  numero, date_import, pieces, import_key)
└── langs/fr_FR/tibillet.lang, langs/en_US/tibillet.lang
```

Table `llx_tibillet_cloture_importee` :

| Colonne | Sens |
|---|---|
| `rowid` | clé |
| `entity` | `$conf->entity` (toujours `$conf->entity`, jamais `getEntity()`, règle de la comptabilité Dolibarr) |
| `cloture_uuid` | `uuid` TiBillet de la clôture (unique avec `entity`) |
| `numero` | `number` TiBillet (curseur, B5) |
| `date_import` | quand |
| `pieces` | les `piece_num` écrits, séparés par des virgules (pour « Retirer ») |
| `import_key` | B7 |

## 6. Un passage de la tâche, pas à pas

1. Lire les réglages. Adresse ou clé absente → retour 0, `output` = « Module non configuré ».
2. `GET {url}/api/v2/accounts/` → créer les comptes manquants (B8). Erreur HTTP → arrêt.
3. `curseur` = `MAX(numero)` de la table (0 si vide). `GET {url}/api/v2/closures/?after_number={curseur}`.
4. Pour chaque clôture, dans l'ordre :
   1. déjà dans la table (uuid) → sauter ;
   2. `GET {entries}` ; `409` / `404` / erreur → arrêt (B10) ;
   3. vérifier l'exercice pour `accountingDate` (B11) ;
   4. `begin` ; pour chaque écriture : créer le journal s'il manque (B9) ; `piece_num =
      getNextNumMvt()` ; pour chaque ligne, `createStd` avec : `doc_date` =
      `EcritureDate`, `doc_type` = `tibillet`, `doc_ref` = `EcritureNum`, `fk_doc` = 0,
      `fk_docdet` = 0, `code_journal` / `journal_label`, `numero_compte` (normalisé),
      `label_compte` = `CompteLib`, `label_operation` = `EcritureLib`, `debit` =
      `Debit / 100`, `credit` = `Credit / 100`, `montant` = le non nul, `sens` = `D` ou
      `C`, `piece_num` ; vérifier Σ débits = Σ crédits (ceinture : TiBillet le garantit) ;
   5. poser `import_key` (UPDATE) ; insérer la ligne de la table ; `commit`. Toute
      erreur → `rollback` de la clôture entière, arrêt.
5. `output` = « n clôtures importées (n° a à b), m comptes créés, k journaux créés ».

## 7. Tests

Pas de suite PHPUnit pour un module externe dans ce dépôt (Dolibarr en a une, lourde à
monter) : **essais à la main, écrits pas à pas**, sur la pile de dev. **Question au
mainteneur (Q4)** : faut-il quand même un test automatique, par exemple un script PHP en
ligne de commande lancé contre une API TiBillet de dev ?

Préparer la pile de dev : `extra_hosts` (ou alias réseau) pour que les conteneurs
Dolibarr joignent `lespass.tibillet.localhost` par Traefik ; `TIBILLET_RESEAU_LOCAL` à oui ;
une clé « Comptabilité (lecture) » dans le lieu de dev ; un exercice 2026 ouvert ; des
J de dev **sans** produit sans compte (README §9 : les J actuelles de la base de dev sont
refusées).

| # | Essai | Attendu |
|---|---|---|
| 1 | Module non configuré, lancer la tâche | OK, « Module non configuré », rien d'écrit |
| 2 | « Tester la connexion » avec une mauvaise clé | message « clé refusée (403) » |
| 3 | Premier passage | comptes manquants créés (7079, 445711…, 5171 sous la forme Dolibarr), journaux créés (nature OD), une pièce par journal et par J, non validées, `doc_ref` = `12-BAR` |
| 4 | Second passage sans nouvelle J | rien d'écrit, « 0 clôture importée » |
| 5 | Une J refusée par TiBillet (produit sans compte) | tâche en échec, phrase de TiBillet, rien d'écrit pour cette J ni pour les suivantes ; après correction du plan, le passage suivant l'importe |
| 6 | Aucun exercice ouvert | arrêt, phrase claire, rien d'écrit |
| 7 | « Retirer » une J non validée, puis tâche | pièces supprimées, J réimportée |
| 8 | « Retirer » une J dont une ligne est validée | refusé, message |
| 9 | Coupure au milieu (simuler une erreur à la 2ᵉ écriture d'une J) | rien de cette J dans le grand livre |
| 10 | La clé apparaît-elle dans `dolibarr.log` ? | noter le résultat (B15) |
| 11 | Somme des écritures importées = FEC de TiBillet pour la même J | égalité, compte par compte |

## 8. Hors de cette fiche

- L'**étape 2** (adhérents, cotisations, ventes détaillées) : après la revue de `/sales/` (Q-H8).
- Le **PDF** de la clôture (décision : pas pour l'instant).
- **Multicompany** (plusieurs lieux dans un Dolibarr) : décision R5, un logiciel par lieu ;
  la colonne `entity` est là, sans plus.
- **Dokos, Paheko, Pennylane** : leurs propres fiches.
- Signaler à Dolibarr le bug du profil d'import (README §9) : décision du mainteneur.

## 9. Questions au mainteneur

- **Q1** — Où vit le code du module : **réponse du mainteneur (2026-10-13) : dépôt à part
  `tibillet-dolibarr`**, dossier `/home/jonas/TiBillet/dev/tibillet-dolibarr/` (créé vide ;
  le mainteneur crée le dépôt git et commite).
- **Q2** — Nature des journaux créés : OD (1) ou ventes (2) ?
- **Q3** — Tâche planifiée active dès l'installation (à 02:30), ou à activer à la main ?
  **Réponse du mainteneur (2026-10-13) : active dès l'installation** (B13 confirmée).
- **Q4** — Essais à la main seulement, ou aussi un script de test automatique ?
  **Réponse du mainteneur (2026-10-13) : un script de test** (option b), en version légère :
  il lance l'import dans le conteneur Dolibarr, vérifie le grand livre, puis nettoie. Il
  couvre au moins les essais 3, 4, 5 et 9 du §7 (premier passage, second passage sans
  doublon, arrêt sur un compte manquant, tout ou rien d'une clôture), vus rouges avant
  d'être livrés. Les essais visuels (page de réglages) restent à la main.

## 10. Relecture Fable (2026-10-13) et décisions — ce qui a été appliqué dans le code

Le §10 prime sur les sections précédentes.

| Constat / question | Décision appliquée |
|---|---|
| **B-1** « Retirer » + curseur `MAX(numero)` : une J retirée n'était jamais réimportée | **« Réimporter »** en UNE transaction : refus si une ligne est validée, `deleteMvtNum` de chaque pièce (nombre de lignes retirées vérifié, sinon tout est annulé), relecture des écritures chez TiBillet, réécriture, mise à jour de la ligne. Le curseur ne bouge pas (Q6) |
| **B-2** la pile de dev ne lançait aucune tâche planifiée (`cron_run_jobs.php` sans utilisateur) | `DOLI_CRON_USER: firstadmin` dans `docker-compose.override.yml` (dev) ; **à reporter dans le `docker-compose.yml` de production** |
| **B-3 / I-4** Dolibarr ne joignait pas TiBillet en dev (DNS `*.localhost`, IP privée, certificat) ; la clé partait dans les journaux par `getURLContent` | **Appel cURL direct** (Q7) : aucune journalisation, pas de redirection suivie, https obligatoire hors mode dev. Mode dev (`TIBILLET_RESEAU_LOCAL`) : nom lu dans `/etc/hosts` (`CURLOPT_RESOLVE`), certificat non vérifié. `extra_hosts: lespass.tibillet.localhost:host-gateway` sur les deux services |
| **I-1** `doc_date` doit être un timestamp | date de l'écriture à **midi**, `dol_mktime(12, 0, 0, …, 'tzserver')` |
| **I-2** garde anti-doublon dans le grand livre lui-même | avant chaque écriture : `doc_type = tibillet` et `doc_ref = EcritureNum` déjà présents → refus, rien d'écrit |
| **I-3** `deleteMvtNum` amputerait une pièce à moitié validée | contrôle des lignes validées avant ; comparaison du nombre de lignes retirées |
| **I-5** heure de la tâche | `datenextrun` = demain 02:30 ; tâche active à l'installation (Q3) |
| **I-6** `account_parent` | parent cherché par préfixe dans le plan actif (`7079` → `707`) ; `pcg_type` d'après la classe (confirmé) |
| **I-7 / Q5** exercice clos | arrêt avec une phrase qui dit de rouvrir l'exercice ; les J suivantes attendent (option a) |
| **M-2** `import_key` inutile | retiré (la table garde `pieces`) |
| **M-8** équilibre | vérifié sur les centimes entiers du JSON |
| **Q2** nature des journaux | **OD (1)** (mainteneur, confirmé par Fable : la nature « ventes » ouvrirait le transfert des factures clients dans BAR) |
| **Q4** tests | `scripts/essai.php` : import, égalité grand livre = TiBillet compte par compte, aucune ligne validée, pas de doublon, réimport, tout ou rien |
| Relecture sécurité Opus (côté Dolibarr) | clé jamais réaffichée (champ vide = inchangée), adresses des écritures **reconstruites depuis l'uuid** (la clé ne part que vers `TIBILLET_URL`), tous les boutons en POST avec jeton |

À savoir (M-4) : le FEC **exporté par Dolibarr** n'est pas celui de TiBillet (`EcritureNum` = `piece_num` de Dolibarr, `PieceRef` = `12-BAR`, `EcritureDate` = jour de l'import). L'égalité se vérifie compte par compte.
