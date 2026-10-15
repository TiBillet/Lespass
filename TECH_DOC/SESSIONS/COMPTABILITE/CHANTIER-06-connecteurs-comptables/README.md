# Chantier 06 — Connecteurs vers les logiciels comptables

> Statut : 🔎 **ÉTUDE** — rien n'est codé. Décisions du mainteneur du 2026-10-13 au §7.
> Origine : session du 2026-10-09 au 2026-10-13, menée depuis le dépôt Dolibarr
> (`/home/jonas/Gits/dolibarr`).
> Cibles : **Dolibarr** (étudié), puis **Dokos**, **Paheko**, **Pennylane** (pas encore regardés).
>
> Les constats sur Lespass datent de l'exploration du **2026-10-10**. Le chantier 05
> était alors en transition (fiche H-2 pas faite). **Revérifier les chemins et les
> numéros de ligne avant de s'en servir.**

---

## 1. L'idée en une phrase

Chaque nuit, le logiciel comptable d'un lieu vient chercher chez TiBillet les
clôtures de caisse qu'il n'a pas encore, et il range leurs écritures dans sa
comptabilité.

D'abord la comptabilité (le FEC). Plus tard, la gestion (adhésions, ventes détaillées).

---

## 2. Expliqué simplement (FALC)

### Les mots

| Mot | Ce que ça veut dire |
|---|---|
| **Compte** | Une case numérotée où l'on range l'argent selon sa nature. 707000 = ventes. 530000 = argent en caisse. 512100 = argent reçu par carte. |
| **Plan comptable** | La liste de toutes ces cases. |
| **Écriture** | Une ligne : « tant d'euros, dans telle case, à telle date ». |
| **Débit / Crédit** | Les deux côtés d'une écriture. Le total des deux côtés est toujours égal. |
| **Journal** | Un carnet qui regroupe les écritures d'une même origine : BAR, WEB, TIREUSE… |
| **Grand livre** | Le registre de toutes les écritures. C'est la comptabilité du lieu. |
| **Clôture J (ou Z)** | Le ticket de fin de service. Il fait le total de la soirée. Il ne bouge plus. |
| **FEC** | Un fichier au format défini par la loi. Il contient des écritures. Tous les logiciels comptables français le connaissent. |
| **Pièce justificative** | Le document qui prouve une écriture. Ici : le rapport de clôture TiBillet. |

### Ce qui se passerait chaque jour

1. Le bar ferme. TiBillet fait la clôture J.
2. TiBillet transforme cette clôture en écritures : c'est le FEC. **Ça existe déjà.**
3. La nuit, le logiciel comptable va chercher les clôtures qu'il n'a pas encore.
4. Il vérifie : les comptes existent, la date est dans une année ouverte, la clôture n'est pas déjà importée.
5. Il écrit les lignes dans son grand livre, **sans les verrouiller**.
6. Le comptable relit, puis valide. Après, plus rien ne bouge.

### Un exemple

Une soirée : 300 € par carte, 200 € en espèces, tout en bière (TVA 20 %).
Le logiciel reçoit **une seule écriture**, pas 80 tickets :

| Compte | Débit | Crédit | En clair |
|---|---|---|---|
| 512100 Carte bancaire | 300,00 | | L'argent arrivé par carte |
| 530000 Caisse espèces | 200,00 | | L'argent arrivé en espèces |
| 707000 Ventes | | 416,67 | Ce qui a été vendu, sans la TVA |
| 445711 TVA 20 % | | 83,33 | La TVA, à reverser à l'État |
| **Total** | **500,00** | **500,00** | Les deux côtés sont égaux |

### Ce dont chaque logiciel a besoin

Les quatre logiciels ont besoin des **mêmes quatre choses** :

1. la **liste des comptes** ;
2. les **écritures** de chaque clôture ;
3. un moyen de **ne pas importer deux fois** la même clôture ;
4. la **pièce justificative** (le rapport de clôture en PDF).

Donc le travail se coupe en deux :

- **Côté TiBillet — un seul travail, pour tous** : une API qui donne la liste des
  clôtures, leur FEC et leur PDF.
- **Côté chaque logiciel — un connecteur** : pour Dolibarr, un module ; pour les
  autres, à voir.

---

## 3. Ce qu'on a constaté côté TiBillet (exploration du 2026-10-10)

- **Le FEC existe** : `comptabilite/fec.py` → `generer_fec_cloture(cloture)`.
  Les écritures viennent de `comptabilite/ventilation.py` (`ventiler_cloture`,
  `ecritures_de_l_export`).
- **On ne peut l'obtenir que par un bouton de l'admin** :
  `/admin/comptabilite/cloturecaisse/<uuid>/exporter-fec/` (`comptabilite/admin.py`).
  Pas de route API, pas de commande `manage.py`, pas de tâche Celery qui le produit.
  L'email automatique de clôture ne joint que le PDF (`comptabilite/tasks.py`).
- **Les clôtures sont créées par Celery** (`cron_clotures_automatiques`, toutes les
  heures ; filet de sécurité J = heure de fermeture + 2 h) ou à la main
  (`manage.py generer_cloture --niveau J --tenant …`).
- **Format** : texte tabulé, 18 colonnes, UTF-8 sans BOM, fins de ligne CRLF,
  montants avec une virgule (`12,34`), dates `AAAAMMJJ`.
  Nom : `FEC-{AAAAMMJJ}-{numero_sequentiel}.txt`.
- **Grain** : une écriture par journal et par J. Pas de client, pas de lettrage,
  pas de détail des ventes. Colonnes vides : `CompAuxNum/Lib`, `EcritureLet/DateLet`,
  `Montantdevise/Idevise`.
- **Numéros** : `EcritureNum` = `{n° de la J}-{code journal}` (ex. `12-BAR`).
  `PieceRef` = n° de la J. `ValidDate` est **rempli**.
- **Rejeu** : les ventes sont scellées, donc mêmes montants et mêmes numéros. Mais les
  comptes sont recalculés avec le plan comptable **du moment** : si le lieu change son
  plan, un FEC rejoué peut changer de comptes. → Un connecteur doit importer **une
  seule fois** chaque clôture.
- **Refus d'export** : `CompteComptableManquant`, `EcritureDesequilibree`, et FEC refusé
  avant la mise en service (Q-R3).
- **Décisions déjà prises qui comptent ici** :
  - **Q-F2** : « TiBillet n'est pas un logiciel de comptabilité, c'est le logiciel
    comptable du lieu qui fige les écritures importées. »
  - **Q-F22** : le CSV comptable est retiré, **le FEC est le seul export comptable**.
  - **Q-F21** : jeu comptabilité gardé « sans les colonnes de l'ancien Dolibarr ».
  - **D22** : un journal FEC par point de vente (plus WEB, TIREUSE…).
  - **D23** : un seul FEC, équilibré par construction.
- **Ventes détaillées** : `Vente` / `Reglement` (`BaseBillet/models_vente.py`) et
  `LigneArticle` (`BaseBillet/models.py`). **Aucune API ne les expose.**
  `GET /api/v2/sales/` lit encore les anciennes `LigneArticle` ; la revue de son
  contrat est prévue après la prod (**Q-H8**, fiche H).
- **Multi-lieux** : un lieu = un schéma. Plan comptable, numérotation, chaîne HMAC :
  tout est par lieu. Les utilisateurs sont **globaux** (schéma public).

---

## 4. Ce qu'on a constaté côté Dolibarr (vérifié dans le code, branche develop ≈ v24)

- **Un module externe** vit dans `custom/<module>/`, sur le modèle de
  `htdocs/modulebuilder/template/`. Son descripteur peut déclarer une **tâche
  planifiée** (`$this->cronjobs`) : Dolibarr appelle une méthode PHP ; retour 0 = succès.
  Il peut aussi ajouter ses **propres routes API** (`class/api_*.class.php`).
- **Import FEC** : un profil existe (`core/modules/modAccounting.class.php:336`), mais
  **seulement dans l'assistant web**. Il ne fait qu'ajouter des lignes : pas de garde
  contre le double import, pas de contrôle de l'exercice, pas de contrôle des comptes.
- **L'API REST comptable ne sait pas importer** (`api_accountancy` = export seulement).
- **Trois pièges** :
  1. `piece_num` est un **entier**. `12-BAR` deviendrait `12`, et les journaux d'une
     même J fusionneraient. → Laisser Dolibarr numéroter, garder `12-BAR` dans la
     colonne `ref` (texte, 30 caractères).
  2. Si `ValidDate` est rempli, l'écriture est **verrouillée dès l'import** : plus
     modifiable, plus supprimable.
  3. Un compte inconnu de Dolibarr est **importé quand même**, sans erreur
     (pas de clé étrangère). Les rapports l'afficheront mal.
- **Justifier une écriture** : chaque ligne garde le journal, la date, le n° de la J
  et le libellé. **Mais Dolibarr ne sait pas joindre un fichier à une écriture.**
  Le PDF de clôture reste dans TiBillet (sauf si le module le télécharge et le range).
- **Pas de transfert automatique en comptabilité** : une facture Dolibarr ne devient
  une écriture que si quelqu'un clique « Enregistrer dans le grand livre ».
- **Identifiants externes** (pour l'étape 2) : `ref_ext` sur facture, tiers, produit,
  adhérent, cotisation, paiement (sans index unique : vérifier avant d'insérer).
  `llx_societe_account` (site, clé) a un vrai index unique : bon endroit pour l'UUID
  d'un utilisateur TiBillet.

### Une instance Dolibarr de test existe

- Dossier : `/home/jonas/Gits/dolibarr_stack/` (compose prod : Dolibarr 24 + cron +
  MariaDB 11.4, derrière TraefikV3, `make env/up/init/backup/check/restore/update`,
  sauvegarde borgwarehouse). URL locale : `https://dolibarr.localhost`.
- Mesures : ~320 Mo de RAM au repos pour les trois conteneurs.
- Défaut de l'image officielle corrigé dans le compose : l'installation automatique
  stockait les accents de travers (fichier `mariadb-client.cnf`).

---

## 5. Ce qu'on recommande (à valider)

| # | Sujet | Recommandation | Pourquoi |
|---|---|---|---|
| R1 | Source comptable | **Le FEC**, et lui seul | Respecte Q-F2 et Q-F22. Ne refait pas dans chaque logiciel les règles du chantier 05 (D6, D8 bis, D10, D26…). |
| R2 | Sens | **Le logiciel comptable vient chercher** chez TiBillet | TiBillet ne dépend d'aucun logiciel. Une nuit ratée se rattrape toute seule. |
| R3 | Verrouillage | **Importer sans verrouiller**, le comptable valide | Une erreur de plan comptable reste corrigeable. |
| R4 | Doublons | Repérer chaque clôture par son **UUID** côté connecteur | Le FEC rejoué peut changer de comptes (plan du moment). |
| R5 | Un lieu = ? | **Une instance de logiciel comptable par lieu** | Colle au plan comptable par lieu. Plus simple que le multi-société. |
| R6 | Étape 2 (gestion) | Plus tard. **Commencer par les adhésions** (adhérent + cotisation). Les ventes détaillées après H-2 et Q-H8. | Faible volume, forte valeur. Les modèles de vente bougent encore. |
| R7 | Double écriture | Règle : les factures TiBillet importées dans un logiciel **ne vont jamais en comptabilité** | Sinon la même soirée est comptée deux fois (FEC + factures). |

On a écarté l'idée de « passer directement à l'étape 2 » pour faire la comptabilité
avec des factures : il faudrait refaire chaque règle comptable du chantier 05 dans
chaque logiciel, risquer des écarts de centimes avec le Z, et créer des centaines de
factures par soirée. Et l'API des ventes n'existe pas encore.

---

## 6. À creuser dans la prochaine session

### Côté TiBillet (la pièce commune)

> **Points 1 à 6 répondus** par la spec [`CHANTIER-06-A-api-comptable.md`](CHANTIER-06-A-api-comptable.md)
> (2026-10-13, relue par Fable). Les routes finales diffèrent de l'exemple ci-dessous :
> `/api/v2/closures/?after_number=<n>`, `…/entries/`, `…/fec/`, `/api/v2/accounts/`.

1. **Dessiner l'API** des clôtures, par exemple :
   - `GET /api/v2/clotures/?niveau=J&depuis=<date>` → liste (uuid, numéro, dates, statut) ;
   - `GET /api/v2/clotures/<uuid>/fec/` → le fichier FEC ;
   - `GET /api/v2/clotures/<uuid>/pdf/` → la pièce justificative.
2. **Le droit** sur `ExternalApiKey` (un nouveau booléen « comptabilité » ?), et la
   question de l'utilisateur admin exigé aujourd'hui par `/sales/`.
3. **Les refus** : que renvoie l'API quand `generer_fec_cloture` lève
   `CompteComptableManquant` ou `EcritureDesequilibree`, ou avant la mise en service ?
4. **Le format** : garder le FEC légal tel quel (virgule, tabulation, CRLF) et laisser
   chaque connecteur s'adapter, ou proposer aussi une version JSON des mêmes écritures ?
5. **Le moment** : faire l'API maintenant, ou après la nuit de bascule et H-2 ?
6. **Le plan comptable** : faut-il une route qui donne la liste des comptes du lieu
   (numéro + libellé), pour que le connecteur les crée avant le premier import ?

### Côté logiciels

7. **Dokos, Paheko, Pennylane** : pour chacun, vérifier s'il sait importer un FEC tout
   seul, ou s'il faut passer par son API d'écritures ; comment il évite les doublons ;
   s'il peut joindre une pièce justificative.
8. **Dolibarr** : plan du module `tibillet` (config, tâche quotidienne, vérification des
   comptes, import non validé avec `ref` = `EcritureNum`, journal d'import, PDF ?).
   Choisir : **créer tout seul les comptes manquants** ou **refuser et les lister**.
9. **Comptes à 6 chiffres** : vérifier que les comptes du plan par défaut TiBillet
   (512100, 517100, 419100, 707900…) existent dans le plan de chaque logiciel, ou qu'ils
   s'y créent sans casser les regroupements.

### Questions pour le mainteneur

Toutes tranchées le 2026-10-13 : voir §7.

---

## 7. Décisions du mainteneur (2026-10-13)

| # | Question | Décision |
|---|---|---|
| R1 | Qui remplit le grand livre du lieu ? | **Le FEC de TiBillet.** Pour la comptabilité, c'est le FEC **ou** les factures, jamais les deux (sinon tout est compté deux fois). Les factures viendront plus tard, pour la gestion seulement (R7). |
| R3 | Verrouillage à l'import | **Non verrouillé.** Le comptable relit puis valide lui-même. |
| R5 | Un lieu = ? | **Un logiciel comptable par lieu.** |
| — | Premier logiciel | **Dolibarr.** |
| §6.4 | Forme des écritures dans l'API | **Les deux** : une route JSON (montants en centimes entiers) **et** une route qui rend le fichier FEC. Même contenu (`ecritures_de_l_export`). |
| §6.8 | Comptes manquants dans Dolibarr | **Le module les crée tout seul**, à partir de la liste des comptes du lieu donnée par TiBillet (numéro + libellé). Il ne modifie jamais un compte existant. → la route « plan comptable » (§6.6) est nécessaire. |
| — | Pièce justificative (PDF) | **Pas pour l'instant.** Chaque écriture garde le n° de la clôture ; le PDF reste dans l'admin TiBillet. |
| §6.5 | Moment de l'API | **Maintenant**, sans attendre H-2 / H-3 : l'API ne lit que les clôtures et le FEC, déjà en production. |

Ce que le mainteneur a dit pendant la session Dolibarr (2026-10-09 → 13) :
« je ne suis pas comptable, j'ai besoin de comprendre » (→ explications FALC) ;
« import automatique des comptes comptables de TiBillet depuis Dolibarr, puis écriture
des sommes dans Dolibarr tous les jours ».

---

## 8. Compléments de la session Dolibarr (2026-10-13)

**État de l'instance de test** (`/home/jonas/Gits/dolibarr_stack/`) : relancée par
`make up` / `up -d`. Module Comptabilité **jamais activé**, aucun plan chargé, aucun
import FEC tenté. Identifiants : `.env` (`DOLI_ADMIN_LOGIN`, `DOLI_ADMIN_PASSWORD`).
Certificat auto-signé régénéré à chaque recréation du conteneur (à réaccepter dans
Chrome). Pour monter de version : supprimer `documents/install.lock`. `DOLI_CRON=1` fait
du conteneur un cron **seul** ; le cron tourne toutes les 5 min (`cron_run_jobs.php`),
une tâche quotidienne se déclare avec `unitfrequency=86400`.

**Pièges à vérifier** (lus dans le code, **non testés**) :

- **Appel HTTP sortant** : `getURLContent()` (`htdocs/core/lib/geturl.lib.php:51`)
  refuse les IP privées par défaut (`localurl=0`, `isIPAllowed()` l.553). En dev, il
  faut `localurl=1` ou `2`. Dans le conteneur, `*.localhost` pointe sur lui-même : il
  faut un `extra_hosts` vers Traefik (ou un alias réseau). `dolibarr-cron` n'est que sur
  le réseau backend. En prod, une URL publique passe avec `localurl=0` (non vérifié).
- **Virgule décimale** : l'import FEC passe les montants dans `price2num()`, qui dépend
  de la langue de l'utilisateur. → La route JSON en centimes évite ce piège.
- **Doublons** : `BookKeeping::create()` (`htdocs/accountancy/class/bookkeeping.class.php:227`)
  a un contrôle de doublon pensé pour les documents Dolibarr ; avec `fk_doc=0`, il
  pourrait rejeter des lignes légitimes. `createStd()` (l.671) semble mieux adapté et
  contrôle la date d'exercice.
- **`import_key`** : 14 caractères au plus, trop court pour un UUID. Repérer les clôtures
  importées par une table propre au module (ou la colonne `ref`).
- **`deleteByImportkey()`** (l.1730) ne marche que sur une période encore modifiable.

**Pistes écartées** : l'envoi par TiBillet (les webhooks actuels se désactivent au
premier échec, `BaseBillet/tasks.py`) ; l'import par l'API REST de Dolibarr
(`api_accountancy` ne fait qu'exporter) ; le module Event Organization pour les billets
(pas de vraie notion de billet).

---

## 9. Essai d'import dans Dolibarr 24.0.1 (2026-10-13)

**Montage** :
- Instance de test `dolibarr_stack`.
- Modules activés : « Comptabilité (partie double) » (qui active aussi Tiers, Facturation, Banques) et « Imports de données ».
- Plan chargé : **FR PCG18-ASSOC** (783 comptes).
- Le fichier : un FEC fabriqué avec le **vrai formateur** `comptabilite/fec.py`. Il a deux journaux (BAR 530 €, WEB 120 €) dans la J n° 12, et les comptes à 6 chiffres de TiBillet.
- Pourquoi un fichier fabriqué : les deux J de la base de dev sont refusées par
  `CompteComptableManquant` (produit de test sans compte, monnaie d'un autre lieu sans
  compte), ce qui est exactement le `409 missing_account` de la spec 06-A.
- Chemin : assistant web, profil « Écritures comptables - format FEC ».

**Constats (vus, pas seulement lus dans le code)** :

| # | Constat | Conséquence |
|---|---|---|
| E1 | L'assistant n'accepte que **CSV ou Excel**. Il lit la virgule comme séparateur par défaut : il faut taper `\t`. **Aucune colonne n'est associée automatiquement**, même avec les noms du FEC : les 18 sont à choisir à la main | L'import manuel d'un FEC TiBillet dans Dolibarr est pénible : un module reste nécessaire |
| E2 | `EcritureNum` = `12-BAR` → **les 9 lignes sont refusées** (« Data truncated for column 'piece_num' », MariaDB en mode strict). Ce n'est pas une troncature silencieuse en `12`, contrairement à ce que disait le §4. Colonne non associée → refus aussi (« piece_num doesn't have a default value ») | Seule voie : associer au numéro de pièce une colonne **vide**. Dolibarr numérote alors lui-même, un numéro par changement de journal ou de date (BAR → 1, WEB → 2). Imposer un numéro, même entier, est dangereux : `piece_num` est le compteur de **toute** la comptabilité Dolibarr, un numéro déjà pris mélangerait deux opérations. → **recette ci-dessous**, avec le FEC inchangé |
| E3 | `ValidDate` remplie → écriture **verrouillée** : cadenas sur « Date validation », Modifier et Supprimer grisés | Confirme A7 de la spec 06-A : pas de `ValidDate` dans le JSON |
| E4 | Les **zéros de droite des comptes sont retirés** à l'import (`ACCOUNTING_MANAGE_ZERO` éteint par défaut) : 512100 → `5121`, 530000 → `53`, 419100 → `4191`, 707000 → `707`, 707900 → `7079`, 517100 → `5171`. 445711 reste `445711` | Le module doit comparer et créer les comptes **sous la forme Dolibarr** (sans zéros de droite, sauf si `ACCOUNTING_MANAGE_ZERO`). Sinon il crée `707900` alors que l'écriture arrive sur `7079` |
| E5 | Compte inconnu (`445711`, `7079`) **accepté sans erreur**, affiché « Compte comptable qui n'existe pas dans le plan comptable actuel » | Confirme le piège 3 du §4 : les comptes doivent être créés **avant** l'import |
| E6 | Journaux `BAR` et `WEB` inconnus de Dolibarr : la colonne Journal de l'écriture s'affiche **vide** | Le module doit aussi **créer les journaux** (`llx_accounting_journal`) à partir de `JournalCode` / `JournalLib` (déjà dans le JSON de 06-A) |
| E7 | Montants « 300,00 » lus juste (utilisateur en français) | Le piège `price2num()` reste à vérifier dans une tâche cron (langue du cron) ; le JSON en centimes l'évite |
| E8 | **Réimporter le même fichier : la simulation accepte à nouveau les 9 lignes**, sans rien signaler | Confirme : aucune garde contre le doublon. Le module garde les uuid des clôtures importées |
| E9 | `doc_ref` = `12` (le `PieceRef`, n° de la J), `label_operation` = « Clôture J n° 12 — Bar ». Le libellé du compte affiché est celui du **plan Dolibarr** (« Comptes en monnaie nationale » pour 5121), pas celui de TiBillet | La trace vers la J est gardée par `doc_ref` + journal |
| E10 | Colonne `montant` à **0** pour les 9 lignes (colonne ancienne de Dolibarr ; `debit` / `credit` / `sens` justes) | Mineur ; le module, qui écrit par le code PHP, la remplit lui-même |

**La recette qui marche avec le FEC TiBillet INCHANGÉ** (vue le 2026-10-13, décision du
mainteneur : un seul export, pas de variante) — à l'étape 3 de l'assistant, associer :

| Colonne du FEC | Champ Dolibarr | Pourquoi |
|---|---|---|
| C `EcritureNum` (`12-BAR`) | **`b.doc_ref`** (Pièce) | Garde la trace « J n° 12, journal BAR » |
| G `CompAuxNum` (**toujours vide** chez TiBillet) | **`b.piece_num`** | Associée et vide : **Dolibarr numérote lui-même** (prochain numéro libre, un par journal) |
| I `PieceRef` | rien | Déjà contenu dans `EcritureNum` |
| P `ValidDate` | **rien** | Écriture **non verrouillée** (décision R3) |
| toutes les autres | leur champ FEC | — |

Résultat : 9 lignes importées, `piece_num` 3 (BAR) et 4 (WEB) choisis par Dolibarr,
`doc_ref` = `12-BAR` / `12-WEB`, `date_validated` vide (pas de cadenas). Zéro changement de
code dans TiBillet. Ces associations se font **une seule fois** : l'assistant peut les
enregistrer comme **profil d'import**.

**Profil d'import (essayé le 2026-10-13)** :
- Enregistrement : OK. Il est rangé dans `llx_import_model` (« FEC TiBillet », visibilité
  « Privé » par défaut, ou « Tout le monde »). Il garde **les associations seulement**,
  pas le séparateur : `\t` est à retaper à chaque import.
- Réutilisation : **ne marche pas, à cause d'un bug de Dolibarr**. Le bouton « Appliquer »
  de l'étape 3 envoie `step=3`, mais le code qui charge le profil
  (`htdocs/imports/import.php` l.294) exige `$step == 4`. Le profil n'est jamais
  appliqué, sans message d'erreur. Le bug est vu dans l'instance 24.0.1 et lu dans le
  code de `develop` (2026-10-09).
- Preuve : le même formulaire envoyé avec `step=4` applique les 18 associations, astuce
  comprise.
- Conséquence : tant que Dolibarr n'est pas corrigé, l'import manuel demande de
  **réassocier les 18 colonnes à chaque fois**. Correctif amont probable : une ligne
  (`step` 4 dans le formulaire, ou `step == 3` dans la condition).

**Les comptes TiBillet dans les plans français de Dolibarr** (fichier
`htdocs/install/mysql/data/llx_accounting_account_fr.sql`, forme sans zéros) :

| TiBillet | Forme Dolibarr | PCG18-ASSOC | PCG25-DEV |
|---|---|---|---|
| 706000 | 706 | Ventes de prestations de services | Prestations de services |
| 707000 | 707 | Ventes de marchandises | Ventes de marchandises |
| 707900 | 7079 | **absent** | **absent** |
| 756000 | 756 | Cotisations | ⚠ **Gains de change** sur créances et dettes commerciales |
| 754000 | 754 | Ressources liées à la générosité du public | ⚠ **Ristournes** perçues des coopératives |
| 445711 à 445714 | 445711… | **absents** (44571 « TVA collectée » existe) | **absents** |
| 530000 | 53 | Caisse | Caisse |
| 511200 | 5112 | Chèques à encaisser | Chèques à encaisser |
| 512100 | 5121 | Comptes en monnaie nationale | Comptes en euros |
| 517100 | 5171 | **absent** | **absent** |
| 512000 | 512 | Banques | Banques |
| 467000 | 467 | Autres comptes débiteurs ou créditeurs | Divers comptes débiteurs… |
| 419100 | 4191 | Clients - avances et acomptes reçus | idem |
| 471000 | 471 | Comptes d'attente | idem |
| 623400 | 6234 | Cadeaux à la clientèle | idem |
| 758000 / 658000 | 758 / 658 | Produits / charges diverses de gestion courante | Indemnités et autres produits / Pénalités et autres charges |

→ À créer par le module dans les deux plans : **7079, 445711-445714, 5171**.
→ ⚠ **Plan 2025 des sociétés** : 756 et 754 ont **changé de sens** (gains de change,
ristournes). Les comptes par défaut 754 / 756 de TiBillet sont ceux du plan associatif,
ce que la fiche 05-E disait déjà. Un lieu en société sur PCG25 doit poser ses propres
comptes dans TiBillet. Le module ne peut pas le deviner : le compte existe, mais avec un
autre sens.

**Données laissées dans l'instance de test** : les 9 lignes importées
(`import_key = 20261013190859`, `piece_num` 1 et 2) et le plan PCG18-ASSOC.

---

**Correction d'un chemin du §3** : `CompteComptableManquant` est dans
`laboutik/plan_comptable.py:82` (pas dans `comptabilite/`). Les autres chemins du §3 sont
vérifiés au 2026-10-13.

---

## 10. Essai de bout en bout (2026-10-13) : ventes réelles → clôture → Dolibarr

**Ventes faites dans les vraies interfaces** (lieu `lespass` de dev) :

| # | Canal | Contenu | Moyen | Montant |
|---|---|---|---|---|
| 1 | Caisse, point de vente Bar | 2 Coca + 1 Chips | espèces | 8,00 € |
| 2 | Caisse, point de vente Bar | 1 Vin rouge + 1 Blonde Pression (pinte) | CB | 12,00 € |
| 3 | En ligne | Adhésion Tiers Lustre (Solidaire) | Stripe test | 10,00 € |
| 4 | En ligne | 2 billets « Concert essai Dolibarr » (TVA 5,5 %) | Stripe test | 24,00 € |

Paiements Stripe validés au retour du client (`stripe_return`), sans `stripe listen`.
Puis `manage.py generer_cloture --niveau J --tenant lespass` → J n° 2 (335,25 €, 94
ventes : les 4 ci-dessus + celles de la suite de tests du jour).

**Import par le vrai cron** (`cron_run_jobs.php … firstadmin 3 --force`) :
1. premier passage : J n° 1 importée, 6 comptes et 9 journaux créés, puis **arrêt sur la
   J n° 2** : TiBillet répond 409 (« Le produit « Chips » n'a pas de catégorie de caisse
   reliée à un compte ») ; tâche en échec, reprogrammée à 02:30. Comportement voulu ;
2. plan du lieu corrigé dans TiBillet (catégories Bar, Snacks, Vins & Spiritueux reliées
   au 707000) ; second passage : J n° 2 importée.

Dans le grand livre : `2-BAR` = 512100 (5121) 12,00 + 530000 (53) 8,00 au débit, 707
20,00 au crédit ; `2-WEB` = 5171 164,00 au débit, 706 72,75 + 445713 1,25 + 756 90,00 au
crédit. Pièces équilibrées, aucune ligne validée, journaux créés en nature OD.

**Script d'essai** (`tibillet-dolibarr/scripts/essai.php`) : TOUT EST OK (cohérence compte
par compte des deux J, aucune ligne validée, pas de doublon, réimport, tout ou rien).
Mutation jouée : `rollback` remplacé par `commit` dans la garde anti-doublon → le test du
tout ou rien échoue (2 échecs), empreinte identique après restauration.

**Pièges trouvés pendant l'essai** :
- **La clé du cron de la pile ne correspondait pas** à la constante `CRON_KEY` de
  Dolibarr (« securitykey … does not match ») : même avec `firstadmin`, aucune tâche ne
  tournait. Alignée en dev ; **à vérifier en production** (la clé de `DOLI_CRON_KEY`
  doit être celle de Configuration → Travaux planifiés) ;
- `validBookkeepingDate()` de Dolibarr appelle `dol_get_last_hour()` sans charger
  `date.lib.php` : plantage hors du cron. Le module charge la bibliothèque ;
- le lieu `lespass` de dev était encombré par les tests (≈ 120 produits sans compte,
  30 points de vente au même code journal) : rangés dans une catégorie « Ventes de test
  (dev) » reliée au 707000, codes journal `TAPAA`… posés ;
- les produits du Bar de la démo **n'ont pas de taux de TVA** : 707 sans ligne de TVA.
  Donnée de démo de TiBillet, pas un défaut du module.
