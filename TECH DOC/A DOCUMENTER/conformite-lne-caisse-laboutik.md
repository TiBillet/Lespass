# Conformité LNE — Logiciel de caisse LaBoutik

> **Logiciel** : TiBillet/Lespass — module LaBoutik (caisse/POS)
> **Référentiel** : LNE v1.7 — Certification des logiciels de caisse
> **Sessions couvertes** : 12 à 18 (mars-avril 2026)
> **Dernière mise à jour** : 2026-04-02

---

## 1. Présentation du logiciel

### 1.1 Qu'est-ce que LaBoutik ?

LaBoutik est un **logiciel de caisse (POS)** intégré au groupware TiBillet/Lespass.
Il fonctionne sur terminaux SUNMI et en navigateur web.

Fonctionnalités principales :
- Encaissement multi-moyen (espèces, carte bancaire, chèque, cashless NFC)
- Gestion des points de vente (bar, restaurant, billetterie, adhésions)
- Clôtures de caisse journalières, mensuelles et annuelles
- Impression de tickets (Sunmi Cloud, LAN, Inner, mock)
- Mode école pour la formation du personnel
- Archivage fiscal et accès pour l'administration

### 1.2 Architecture technique

| Élément | Technologie |
|---------|------------|
| Backend | Django 4.2 (Python 3.11) |
| Multi-tenant | django-tenants (schéma PostgreSQL par lieu) |
| Interface | HTMX + Bootstrap 5, rendu serveur |
| Tâches | Celery + Redis (clôtures auto, impressions) |
| Impression | ESC/POS via Sunmi Cloud, LAN, WebSocket |

Chaque lieu (association, bar, festival) dispose de son propre schéma de base de données.
Les données d'un lieu sont **isolées** de celles des autres lieux.

---

## 2. Tableau de conformité — Référentiel LNE v1.7

### 2.1 Vue d'ensemble

| Exigence | Titre | Statut | Session |
|----------|-------|--------|---------|
| Ex.1 | Documentation réglementaire | À faire | — |
| Ex.2 | Documentation complémentaire | À faire | — |
| **Ex.3** | **Données à enregistrer** | **Fait** | S12, S14 |
| **Ex.4** | **Corrections par +/-** | **Fait** | S13, S17 |
| **Ex.5** | **Mode école/test** | **Fait** | S15 |
| **Ex.6** | **Clôtures J/M/A** | **Fait** | S13 |
| **Ex.7** | **Données cumulatives et perpétuelles** | **Fait** | S13 |
| **Ex.8** | **Inaltérabilité des données** | **Fait** | S12 |
| **Ex.9** | **Sécurisation des justificatifs** | **Fait** | S14 |
| **Ex.10** | **Archivage des données** | **Fait** | S18 |
| **Ex.11** | **Périodicité d'archivage** | **Fait** | S18 |
| **Ex.12** | **Intégrité des archives** | **Fait** | S18 |
| Ex.13 | Purge (archivage préalable) | À faire | — |
| Ex.14 | Purge partielle (cumulatifs conservés) | À faire | — |
| **Ex.15** | **Traçabilité des opérations** | **Fait** | S18 |
| **Ex.16** | **Conservation des données (6 ans)** | **Fait** | S18 |
| **Ex.17** | **Conservation des archives (6 ans)** | **Fait** | S18 |
| Ex.18 | Système centralisateur | Non applicable | — |
| **Ex.19** | **Accès administration fiscale** | **Fait** | S18 |
| Ex.20 | Périmètre fiscal (tableau code/exigences) | À faire | — |
| Ex.21 | Versions majeures/mineures | À faire | S19 |

**Bilan : 15 exigences couvertes sur 21** (hors Ex.18 non applicable).

---

### 2.2 Détail par exigence

#### Ex.3 — Données à enregistrer

Chaque vente enregistre une **LigneArticle** avec :

| Donnée | Champ | Type |
|--------|-------|------|
| Identifiant unique | `uuid` | UUID |
| Date et heure | `datetime` | DateTimeField |
| Désignation article | `article` | CharField |
| Catégorie | `categorie` | CharField |
| Montant TTC | `amount` | IntegerField (centimes) |
| Montant HT | `total_ht` | IntegerField (centimes) |
| Quantité | `qty` | DecimalField |
| Taux de TVA | `vat` | DecimalField (%) |
| Moyen de paiement | `payment_method` | CharField |
| Origine (production/test) | `sale_origin` | CharField |
| Point de vente | `point_de_vente` | FK PointDeVente |
| Empreinte HMAC | `hmac_hash` | CharField(64) |

Le **total HT** est calculé automatiquement :
`HT = round(TTC / (1 + taux_tva / 100))`

Les **mentions légales** figurent sur chaque ticket imprimé :
raison sociale, adresse, SIRET, numéro de TVA (ou mention art. 293 B du CGI),
numéro séquentiel du ticket, ventilation TVA par taux.

---

#### Ex.4 — Corrections par opérations de +/-

Les corrections de moyen de paiement se font **sans modification directe** des données.

**Principe** : une correction crée une trace d'audit (`CorrectionPaiement`) puis modifie
le moyen de paiement. La chaîne HMAC est volontairement cassée — la trace d'audit
permet à `verify_integrity` de distinguer une correction tracée d'une falsification.

**Contraintes métier** :
- Uniquement entre Espèces, Carte bancaire et Chèque
- Les paiements NFC/cashless ne peuvent pas être corrigés (liés à une Transaction fedow_core)
- Les lignes couvertes par une clôture journalière sont **immutables** (modification interdite)
- La raison de la correction est obligatoire

**Trace d'audit** (`CorrectionPaiement`) :

| Champ | Description |
|-------|------------|
| `ligne_article` | FK vers la LigneArticle corrigée |
| `ancien_moyen` | Moyen de paiement avant correction |
| `nouveau_moyen` | Moyen de paiement après correction |
| `raison` | Motif de la correction (obligatoire) |
| `operateur` | Utilisateur qui a effectué la correction |
| `datetime` | Date et heure de la correction |

---

#### Ex.5 — Mode école / test

Le mode école permet de **former le personnel** sans polluer les données de production.

**Activation** : champ `mode_ecole` dans la configuration du lieu (admin).

**Comportement** :
- Un bandeau orange "MODE ÉCOLE — SIMULATION" est affiché en permanence sur l'interface POS
- Toutes les ventes sont marquées `sale_origin = LABOUTIK_TEST`
- Les tickets imprimés portent la mention "*** SIMULATION ***"
- Les ventes de test sont **exclues des rapports comptables** de production
- Les chaînes HMAC de test sont **séparées** de celles de production

---

#### Ex.6 — Clôtures journalières, mensuelles et annuelles

LaBoutik génère trois niveaux de clôture :

| Niveau | Déclenchement | Contenu |
|--------|--------------|---------|
| **Journalière (J)** | Manuel par le caissier | Totaux par moyen, détail ventes, TVA, opérateurs |
| **Mensuelle (M)** | Automatique le 1er du mois (3h) | Agrégat des clôtures J du mois précédent |
| **Annuelle (A)** | Automatique le 1er janvier (4h) | Agrégat des clôtures M de l'année précédente |

**Décision architecturale** : la clôture est **globale au tenant** (pas par point de vente).
Dans un contexte festival avec 40 points de vente, il est impossible de clôturer chaque PV
individuellement. La ventilation par PV est incluse dans le rapport.

Chaque clôture porte un **numéro séquentiel** unique par niveau, sans trou.

La **date d'ouverture** est calculée automatiquement : c'est la date de la première vente
après la dernière clôture journalière. Elle n'est jamais saisie manuellement.

---

#### Ex.7 — Données cumulatives et perpétuelles

Le **total perpétuel** est un compteur global du chiffre d'affaires TTC depuis la mise
en service du logiciel. Il est :

- Incrémenté **atomiquement** à chaque clôture (expression `F()` PostgreSQL)
- **Jamais remis à zéro**
- Stocké dans la configuration du lieu (`LaboutikConfiguration.total_perpetuel`)
- **Photographié** sur chaque `ClotureCaisse.total_perpetuel`

Ce total permet de détecter toute suppression de clôture (le total courant doit être
égal à la somme de toutes les clôtures).

---

#### Ex.8 — Inaltérabilité des données (HMAC-SHA256)

Chaque `LigneArticle` est **chaînée** par un HMAC-SHA256.

**Algorithme** :
```
HMAC = HMAC-SHA256(
    clé_secrète,
    JSON([uuid, datetime, amount, total_ht, qty, vat, payment_method, status, sale_origin, previous_hmac])
)
```

**Propriétés** :
- La clé HMAC est **par tenant**, chiffrée Fernet en base de données
- L'utilisateur final n'a **jamais accès** à la clé
- Chaque ligne inclut le hash de la précédente (chaînage)
- Une modification, suppression ou insertion détectée = **rupture de chaîne**
- La commande `verify_integrity` vérifie la chaîne complète et distingue les corrections tracées des falsifications

**Commande de vérification** :
```bash
docker exec lespass_django poetry run python manage.py verify_integrity --schema=<nom_du_lieu>
```

---

#### Ex.9 — Sécurisation des justificatifs (tickets)

Chaque impression est tracée dans un **journal immutable** (`ImpressionLog`) :

| Champ | Description |
|-------|------------|
| `type_justificatif` | VENTE, CLÔTURE, COMMANDE ou BILLET |
| `is_duplicata` | Vrai si c'est une réimpression |
| `format_emission` | PAPIER ou ÉLECTRONIQUE |
| `operateur` | Qui a imprimé |
| `printer` | Sur quelle imprimante |
| `datetime` | Quand |

Les **réimpressions** portent la mention "*** DUPLICATA ***" en gras sur le ticket.

Le **compteur de tickets** (`LaboutikConfiguration.compteur_tickets`) est incrémenté
atomiquement. Chaque ticket porte un numéro séquentiel unique (T-000001, T-000002, ...).

---

#### Ex.10, Ex.11, Ex.12 — Archivage et intégrité des archives

##### Archivage des données (Ex.10)

La commande `archiver_donnees` génère une **archive ZIP** contenant :

| Fichier | Contenu |
|---------|---------|
| `lignes_article.csv` | Toutes les ventes de la période |
| `clotures.csv` | Clôtures de caisse |
| `corrections.csv` | Corrections de moyen de paiement |
| `impressions.csv` | Journal des impressions |
| `sorties_caisse.csv` | Retraits d'espèces |
| `historique_fond_de_caisse.csv` | Modifications du fond de caisse |
| `donnees.json` | Export structuré complet (mêmes données, format machine) |
| `meta.json` | Informations du lieu (raison sociale, SIRET, période, version) |
| `hash.json` | Empreintes HMAC-SHA256 de chaque fichier + empreinte globale |

**Format CSV** : délimiteur point-virgule (`;`), encodage UTF-8 avec BOM, en-têtes en première ligne. Montants en centimes d'euros.

```bash
docker exec lespass_django poetry run python manage.py archiver_donnees \
    --schema=<nom_du_lieu> --debut=2026-01-01 --fin=2026-12-31 --output=/archives/
```

##### Périodicité (Ex.11)

La période d'une archive ne peut pas dépasser **1 an** (365 jours).

##### Intégrité (Ex.12)

Le fichier `hash.json` contient l'empreinte HMAC-SHA256 de chaque fichier de l'archive,
plus une empreinte globale. La vérification est **indépendante du système** :

```bash
docker exec lespass_django poetry run python manage.py verifier_archive \
    --archive=/archives/demo_20260101_20261231.zip --schema=<nom_du_lieu>
```

Résultat : OK ou KO fichier par fichier, avec code de sortie 0 (valide) ou 1 (invalide).

---

#### Ex.15 — Traçabilité des opérations

Chaque opération d'archivage, de vérification ou d'export fiscal est tracée
dans un **journal sécurisé** (`JournalOperation`) :

| Champ | Description |
|-------|------------|
| `type_operation` | ARCHIVAGE, VÉRIFICATION ou EXPORT_FISCAL |
| `datetime` | Date et heure de l'opération |
| `operateur` | Utilisateur qui a lancé l'opération |
| `details` | Métadonnées (période, hash, nombre de fichiers, résultat) |
| `hmac_hash` | Empreinte HMAC-SHA256 chaînée avec l'entrée précédente |

Le chaînage HMAC utilise le **même principe** que celui des lignes de vente (Ex.8).
Toute modification ou suppression d'une entrée est détectable.

Les changements de **fond de caisse** sont également tracés (`HistoriqueFondDeCaisse`) :
ancien montant, nouveau montant, opérateur, date.

---

#### Ex.16, Ex.17 — Conservation des données et archives

Les données d'encaissement et les archives sont conservées **au minimum 6 ans**
(obligation fiscale de conservation des pièces justificatives).

Le format ouvert (CSV + JSON) garantit que les données restent **lisibles**
indépendamment du logiciel, même après plusieurs années.

---

#### Ex.19 — Accès pour l'administration fiscale

En cas de contrôle fiscal, le lieu peut générer un **export complet** de toutes
ses données d'encaissement :

```bash
docker exec lespass_django poetry run python manage.py acces_fiscal \
    --schema=<nom_du_lieu> --output=/export_fiscal/
```

L'export génère un dossier contenant :
- Les mêmes fichiers CSV et JSON que l'archivage
- Un fichier `hash.json` pour vérifier l'intégrité
- Un fichier `README.txt` en français à destination du contrôleur

Le **README** explique en langage clair :
- Le contenu de chaque fichier
- Comment vérifier l'intégrité des données
- Le format des montants (centimes d'euros)
- Le délimiteur CSV (point-virgule)

L'export est également accessible depuis l'**interface d'administration** (bouton
"Export fiscal" dans la section Clôtures) pour les utilisateurs non techniques.

---

## 3. Guide de l'utilisateur

### 3.1 Clôture de caisse

À la fin de chaque service, le caissier effectue une **clôture journalière** :

1. Ouvrir le menu "Ventes" dans l'interface POS
2. Consulter le **Ticket X** (récap en cours, non sauvegardé)
3. Cliquer "Clôturer la caisse"
4. Le **Ticket Z** est généré (sauvegarde définitive) et imprimé

Les clôtures mensuelles et annuelles sont **automatiques** (pas d'action requise).

### 3.2 Corrections

Si un moyen de paiement a été mal saisi (ex : espèces au lieu de carte bancaire) :

1. Ouvrir le menu "Ventes"
2. Trouver la vente dans la liste
3. Cliquer "Corriger le moyen de paiement"
4. Sélectionner le bon moyen
5. Indiquer la raison de la correction
6. Valider

**Limitations** :
- Impossible après une clôture journalière
- Impossible pour les paiements NFC/cashless

### 3.3 Fond de caisse

Pour définir ou modifier le fond de caisse :

1. Ouvrir le menu "Ventes"
2. Cliquer "Fond de caisse"
3. Saisir le montant (accepte la virgule : `50,00`)
4. Valider

Chaque modification est **tracée** (ancien montant, nouveau montant, opérateur).

### 3.4 Sortie de caisse

Pour retirer des espèces du tiroir :

1. Ouvrir le menu "Ventes"
2. Cliquer "Sortie de caisse"
3. Indiquer le nombre de chaque coupure (billets et pièces)
4. Le total est calculé automatiquement
5. Valider

Le total est **recalculé côté serveur** pour éviter toute manipulation.

### 3.5 Mode école

Pour former du personnel sans affecter les données de production :

1. Aller dans l'administration du lieu
2. Activer le "Mode école" dans la configuration LaBoutik
3. Un bandeau orange permanent apparaît sur l'interface POS
4. Toutes les ventes sont marquées comme simulations
5. Désactiver le mode école une fois la formation terminée

---

## 4. Guide pour l'administration fiscale

### 4.1 Obtenir les données d'encaissement

En cas de contrôle, demander au responsable du lieu de générer l'export fiscal :

**Option 1 — Interface d'administration** :
1. Se connecter à l'administration du lieu
2. Section "Clôtures" → bouton "Export fiscal"
3. Renseigner les dates (optionnel, défaut = tout)
4. Télécharger le fichier ZIP

**Option 2 — Ligne de commande** :
```bash
docker exec lespass_django poetry run python manage.py acces_fiscal \
    --schema=<nom_du_lieu> --output=/export_fiscal/
```

### 4.2 Contenu de l'export

| Fichier | Description |
|---------|------------|
| `lignes_article.csv` | Toutes les ventes : date, article, montant TTC/HT, TVA, moyen de paiement |
| `clotures.csv` | Clôtures de caisse : totaux par moyen, numéro séquentiel, total perpétuel |
| `corrections.csv` | Corrections de moyen de paiement : ancien/nouveau moyen, motif, opérateur |
| `impressions.csv` | Journal des impressions de tickets (original/duplicata) |
| `sorties_caisse.csv` | Retraits d'espèces avec ventilation par coupure |
| `historique_fond_de_caisse.csv` | Historique des modifications du fond de caisse |
| `donnees.json` | Mêmes données en format structuré (JSON) |
| `meta.json` | Informations de l'organisation (raison sociale, SIRET, période) |
| `hash.json` | Empreintes numériques pour vérification d'intégrité |
| `README.txt` | Guide en français |

### 4.3 Format des données

- **Montants** : en centimes d'euros (ex : `1250` = 12,50 EUR)
- **Délimiteur CSV** : point-virgule (`;`)
- **Encodage** : UTF-8
- **Dates** : format ISO 8601 (ex : `2026-03-31T14:30:00+02:00`)

### 4.4 Vérifier l'intégrité

Pour vérifier que les données n'ont pas été modifiées après l'export :

```bash
docker exec lespass_django poetry run python manage.py verifier_archive \
    --archive=<chemin_vers_le_zip> --schema=<nom_du_lieu>
```

Le résultat affiche OK ou KO pour chaque fichier. Le code de sortie est 0 si tout
est intègre, 1 si une anomalie est détectée.

Les empreintes sont calculées avec l'algorithme **HMAC-SHA256** et la clé propre au lieu.

### 4.5 Vérifier la chaîne d'intégrité des ventes

Pour vérifier que les données de vente n'ont pas été altérées en base de données :

```bash
docker exec lespass_django poetry run python manage.py verify_integrity \
    --schema=<nom_du_lieu>
```

Ce contrôle parcourt toutes les lignes de vente et vérifie le chaînage HMAC.
Il détecte et distingue :
- Les **corrections tracées** (moyen de paiement corrigé avec motif — normal)
- Les **anomalies** (modification ou suppression non tracée — alerte)

---

## 5. Modèles de données

### 5.1 Modèles principaux

```
LigneArticle (BaseBillet)
├── uuid, datetime, article, categorie
├── amount (TTC centimes), total_ht (HT centimes)
├── qty, vat (taux %), payment_method, status, sale_origin
├── point_de_vente → PointDeVente
├── hmac_hash, previous_hmac (chaînage HMAC-SHA256)
└── uuid_transaction (regroupement multi-articles)

ClotureCaisse (laboutik)
├── uuid, datetime_cloture, datetime_ouverture
├── niveau (J/M/A), numero_sequentiel
├── total_especes, total_carte_bancaire, total_cashless, total_general
├── nombre_transactions, total_perpetuel, hash_lignes
├── rapport_json (rapport complet 12 sections)
└── responsable → TibilletUser, point_de_vente → PointDeVente

CorrectionPaiement (laboutik)
├── uuid, datetime
├── ligne_article → LigneArticle
├── ancien_moyen, nouveau_moyen, raison
└── operateur → TibilletUser

ImpressionLog (laboutik)
├── uuid, datetime
├── type_justificatif, is_duplicata, format_emission
├── ligne_article → LigneArticle, cloture → ClotureCaisse
├── uuid_transaction
└── operateur → TibilletUser, printer → Printer

SortieCaisse (laboutik)
├── uuid, datetime
├── montant_total (centimes), ventilation (JSON coupures), note
└── operateur → TibilletUser, point_de_vente → PointDeVente

JournalOperation (laboutik)
├── uuid, datetime
├── type_operation (ARCHIVAGE/VERIFICATION/EXPORT_FISCAL)
├── details (JSON), hmac_hash (chaînage)
└── operateur → TibilletUser

HistoriqueFondDeCaisse (laboutik)
├── uuid, datetime
├── ancien_montant, nouveau_montant (centimes), raison
└── operateur → TibilletUser, point_de_vente → PointDeVente
```

### 5.2 Configuration par lieu

```
LaboutikConfiguration (singleton par tenant)
├── hmac_key (chiffrée Fernet — clé HMAC-SHA256)
├── total_perpetuel (jamais remis à zéro)
├── fond_de_caisse (centimes)
├── mode_ecole (booléen)
├── compteur_tickets (séquentiel atomique)
├── pied_ticket (texte libre)
├── rapport_emails, rapport_periodicite
└── sunmi_app_id, sunmi_app_key (impression cloud)
```

---

## 6. Commandes disponibles

| Commande | Description | Exigence |
|----------|------------|----------|
| `verify_integrity --schema=X` | Vérifie la chaîne HMAC des ventes | Ex.8 |
| `archiver_donnees --schema=X --debut=D --fin=F --output=O` | Génère une archive ZIP (max 1 an) | Ex.10-12 |
| `verifier_archive --archive=A --schema=X` | Vérifie l'intégrité d'un ZIP | Ex.12 |
| `acces_fiscal --schema=X --output=O` | Export complet pour l'administration | Ex.19 |
| `create_test_pos_data` | Crée des données de test (développement) | — |

---

## 7. Exigences restantes

| Exigence | Titre | Commentaire |
|----------|-------|------------|
| Ex.1-2 | Documentation réglementaire | 7 dossiers formels à rédiger pour la certification |
| Ex.13-14 | Purge sécurisée | Archivage obligatoire avant purge, cumulatifs conservés |
| Ex.20 | Périmètre fiscal | Tableau de correspondance code source / exigences |
| Ex.21 | Version logiciel | Empreinte SHA-256 du code, visible dans l'interface POS |

Ces exigences sont prévues dans les sessions 19 (version) et futures.

---

## 8. Tests de conformité

### 8.1 Tests automatisés

| Domaine | Fichier | Nb tests |
|---------|---------|----------|
| Intégrité HMAC | `test_cloture_enrichie.py` | 15 |
| Clôtures 3 niveaux | `test_cloture_caisse.py` | 7 |
| Exports admin | `test_cloture_export.py` | 8 |
| Corrections + fond/sortie | `test_corrections_fond_sortie.py` | 20 |
| Archivage fiscal | `test_archivage_fiscal.py` | 14 |

**Total session 18** : 14 tests nouveaux, 57 tests laboutik au total, 0 régression.

### 8.2 Lancer les tests

```bash
# Tests archivage fiscal uniquement
docker exec lespass_django poetry run pytest tests/pytest/test_archivage_fiscal.py -v

# Tous les tests laboutik
docker exec lespass_django poetry run pytest tests/pytest/test_archivage_fiscal.py \
    tests/pytest/test_corrections_fond_sortie.py \
    tests/pytest/test_cloture_caisse.py \
    tests/pytest/test_cloture_enrichie.py \
    tests/pytest/test_cloture_export.py -v
```
