# Design Spec — Session 18 : Archivage fiscal + acces administration

> **Date** : 2026-04-02
> **Exigences LNE** : Ex.10 (archivage), Ex.11 (periodicite), Ex.12 (integrite archives), Ex.15 (tracabilite operations), Ex.19 (acces administration fiscale)
> **Depend de** : Session 13 (clotures 3 niveaux), Session 17 (corrections + fond de caisse)
> **Scope** : 3 management commands, 2 nouveaux modeles, 1 bouton admin, 1 branchement sur vue existante, 10+ tests pytest

---

## 1. Nouveaux modeles

### 1.1 `JournalOperation` — tracabilite operations techniques (Ex.15)

Dans `laboutik/models.py`. Trace immutable des operations d'archivage, verification, export fiscal.

| Champ | Type | Contraintes | Role |
|-------|------|-------------|------|
| `uuid` | UUIDField PK | default=uuid4 | Identifiant unique |
| `type_operation` | CharField(20) | choices: ARCHIVAGE, VERIFICATION, EXPORT_FISCAL | Type d'operation |
| `datetime` | DateTimeField | auto_now_add=True | Horodatage immutable |
| `operateur` | FK TibilletUser | SET_NULL, null=True, blank=True | Qui a lance (null si Celery Beat) |
| `details` | JSONField | default=dict | Metadonnees libres (periode, hash, nb fichiers, resultat...) |
| `hmac_hash` | CharField(64) | blank=True, default='' | HMAC-SHA256 chaine avec l'entree precedente |

**Chainages HMAC** : meme logique que `LigneArticle`. Le contenu hashe est :
`type_operation|datetime_iso|json_sorted(details)|previous_hmac`.

**Admin** : read-only dans "Caisse LaBoutik", liste chronologique, pas d'edition.

**Meta** : `ordering = ['datetime']`, `verbose_name = "Journal des operations"`.

### 1.2 `HistoriqueFondDeCaisse` — trace des changements de fond de caisse

Dans `laboutik/models.py`. Trace immutable de chaque modification du fond de caisse.

| Champ | Type | Contraintes | Role |
|-------|------|-------------|------|
| `uuid` | UUIDField PK | default=uuid4 | Identifiant unique |
| `point_de_vente` | FK PointDeVente | SET_NULL, null=True, blank=True | PV actif au moment du changement |
| `operateur` | FK TibilletUser | SET_NULL, null=True, blank=True | Qui a change |
| `datetime` | DateTimeField | auto_now_add=True | Quand |
| `ancien_montant` | IntegerField | centimes | Montant avant modification |
| `nouveau_montant` | IntegerField | centimes | Montant apres modification |
| `raison` | TextField | blank=True, default='' | Contexte optionnel |

**Admin** : read-only dans "Caisse LaBoutik", colonnes: datetime, operateur, ancien_montant, nouveau_montant.

**Meta** : `ordering = ['-datetime']`, `verbose_name = "Historique fond de caisse"`.

### 1.3 Migration

Migration unique `0016_journaloperation_historiquefondecaisse.py`.

---

## 2. Management command `archiver_donnees` (Ex.10, Ex.11, Ex.12)

Fichier : `laboutik/management/commands/archiver_donnees.py`

### 2.1 Arguments

| Argument | Type | Requis | Defaut | Description |
|----------|------|--------|--------|-------------|
| `--schema` | str | oui | — | Schema tenant (ex: `demo`) |
| `--debut` | date | oui | — | Date debut periode (YYYY-MM-DD) |
| `--fin` | date | oui | — | Date fin periode (YYYY-MM-DD) |
| `--output` | path | oui | — | Repertoire de sortie |

### 2.2 Gardes

- **Periode max 1 an** (Ex.11) : erreur si `fin - debut > 365 jours`
- **Schema obligatoire** : erreur si tenant introuvable
- **Repertoire output** : cree si inexistant

### 2.3 Contenu du ZIP

Nom : `{schema}_{debut}_{fin}_{timestamp_iso}.zip`

| Fichier | Contenu |
|---------|---------|
| `lignes_article.csv` | LigneArticle de la periode (sale_origin=LABOUTIK + LABOUTIK_TEST) |
| `clotures.csv` | ClotureCaisse de la periode |
| `corrections.csv` | CorrectionPaiement de la periode |
| `impressions.csv` | ImpressionLog de la periode |
| `sorties_caisse.csv` | SortieCaisse de la periode |
| `historique_fond_de_caisse.csv` | HistoriqueFondDeCaisse de la periode |
| `donnees.json` | Export structure complet (memes donnees, format machine-readable) |
| `meta.json` | Raison sociale, SIRET, TVA, periode, version logiciel, date generation |
| `hash.json` | HMAC-SHA256 de chaque fichier + hash global |

### 2.4 Format CSV

Delimiteur `;` (coherent avec l'export Excel existant session 15).
Encodage UTF-8 avec BOM (pour Excel FR).
Premiere ligne = en-tetes.

**Colonnes `lignes_article.csv`** :
`uuid`, `datetime`, `article`, `categorie`, `prix_ttc_centimes`, `quantite`, `payment_method`, `sale_origin`, `taux_tva`, `total_ht_centimes`, `total_tva_centimes`, `point_de_vente`, `operateur_email`, `user_email`, `uuid_transaction`, `hmac_hash`

**Colonnes `clotures.csv`** :
`uuid`, `datetime_cloture`, `datetime_ouverture`, `niveau`, `numero_sequentiel`, `total_especes`, `total_carte_bancaire`, `total_cashless`, `total_cheque`, `total_general`, `nombre_transactions`, `total_perpetuel`, `hash_lignes`, `responsable_email`, `point_de_vente`

**Colonnes `corrections.csv`** :
`uuid`, `datetime`, `ligne_article_uuid`, `ancien_moyen`, `nouveau_moyen`, `raison`, `operateur_email`

**Colonnes `impressions.csv`** :
`uuid`, `datetime`, `type_justificatif`, `is_duplicata`, `format_emission`, `ligne_article_uuid`, `cloture_uuid`, `uuid_transaction`, `operateur_email`, `printer_name`

**Colonnes `sorties_caisse.csv`** :
`uuid`, `datetime`, `point_de_vente`, `montant_total_centimes`, `ventilation_json`, `note`, `operateur_email`

**Colonnes `historique_fond_de_caisse.csv`** :
`uuid`, `datetime`, `point_de_vente`, `ancien_montant_centimes`, `nouveau_montant_centimes`, `raison`, `operateur_email`

### 2.5 Format `meta.json`

```json
{
    "logiciel": "TiBillet/Lespass",
    "version": "2.0.0",
    "organisation": "Nom du lieu",
    "adresse": "...",
    "code_postal": "...",
    "ville": "...",
    "siren": "...",
    "tva_number": "...",
    "periode_debut": "2026-01-01",
    "periode_fin": "2026-12-31",
    "date_generation": "2026-04-02T14:30:00+02:00",
    "schema_tenant": "demo",
    "nombre_lignes_article": 1234,
    "nombre_clotures": 12,
    "nombre_corrections": 3,
    "nombre_impressions": 456,
    "nombre_sorties_caisse": 5,
    "nombre_historique_fond": 8,
    "total_perpetuel_a_date": 12345678
}
```

### 2.6 Format `hash.json`

```json
{
    "algorithme": "HMAC-SHA256",
    "date_generation": "2026-04-02T14:30:00+02:00",
    "fichiers": {
        "lignes_article.csv": "abc123...",
        "clotures.csv": "def456...",
        "corrections.csv": "ghi789...",
        "impressions.csv": "jkl012...",
        "sorties_caisse.csv": "mno345...",
        "historique_fond_de_caisse.csv": "pqr678...",
        "donnees.json": "stu901...",
        "meta.json": "vwx234..."
    },
    "hash_global": "xyz..."
}
```

Le `hash_global` est le HMAC-SHA256 de la concatenation ordonnee des hash fichiers.

### 2.7 Apres generation

Cree `JournalOperation(type_operation='ARCHIVAGE', details={hash_global, periode, chemin_zip, nb_fichiers})`.

---

## 3. Management command `verifier_archive` (Ex.12)

Fichier : `laboutik/management/commands/verifier_archive.py`

### 3.1 Arguments

| Argument | Type | Requis | Defaut | Description |
|----------|------|--------|--------|-------------|
| `--archive` | path | oui | — | Chemin vers le fichier ZIP |
| `--schema` | str | oui | — | Schema tenant (pour recuperer la cle HMAC) |

### 3.2 Logique

1. Ouvrir le ZIP
2. Lire `hash.json`
3. Pour chaque fichier dans `hash.json.fichiers` : lire le contenu du ZIP, recalculer HMAC avec la cle du tenant, comparer
4. Recalculer `hash_global`, comparer
5. Afficher OK/KO par fichier + resultat global
6. Creer `JournalOperation(type_operation='VERIFICATION', details={resultat, fichier_archive, nb_ok, nb_ko})`

### 3.3 Code retour

- `0` si tout OK
- `1` si au moins un fichier KO

---

## 4. Management command `acces_fiscal` (Ex.19)

Fichier : `laboutik/management/commands/acces_fiscal.py`

### 4.1 Arguments

| Argument | Type | Requis | Defaut | Description |
|----------|------|--------|--------|-------------|
| `--schema` | str | oui | — | Schema tenant |
| `--output` | path | oui | — | Repertoire de sortie |

### 4.2 Difference avec `archiver_donnees`

- **Pas de limite de periode** : exporte TOUT l'historique
- **Genere un dossier** (pas un ZIP) pour faciliter la lecture par le controleur
- **Inclut un `README.txt`** en francais

### 4.3 Contenu du dossier

```
export_fiscal_demo_2026-04-02/
  lignes_article.csv
  clotures.csv
  corrections.csv
  impressions.csv
  sorties_caisse.csv
  historique_fond_de_caisse.csv
  donnees.json
  meta.json
  hash.json
  README.txt
```

### 4.4 `README.txt`

```
EXPORT DES DONNEES D'ENCAISSEMENT
==================================

Logiciel : TiBillet/Lespass
Organisation : {nom}
SIRET : {siret}
Date d'export : {date}

CONTENU DE CE DOSSIER
---------------------

- lignes_article.csv : Toutes les ventes enregistrees
- clotures.csv : Clotures de caisse (journalieres, mensuelles, annuelles)
- corrections.csv : Corrections de moyen de paiement (avec motif)
- impressions.csv : Journal des impressions de tickets
- sorties_caisse.csv : Retraits d'especes
- historique_fond_de_caisse.csv : Modifications du fond de caisse
- donnees.json : Export structure complet (format machine)
- meta.json : Informations sur l'organisation et la periode
- hash.json : Empreintes numeriques pour verification d'integrite

VERIFICATION D'INTEGRITE
-------------------------

Pour verifier que les fichiers n'ont pas ete modifies :

    python manage.py verifier_archive --archive=<chemin_zip> --schema={schema}

Les empreintes HMAC-SHA256 dans hash.json permettent de detecter
toute modification des fichiers apres l'export.

FORMAT DES MONTANTS
-------------------

Tous les montants sont en centimes d'euros (ex: 1250 = 12,50 EUR).
Le delimiteur CSV est le point-virgule (;).
L'encodage est UTF-8.
```

### 4.5 Apres generation

Cree `JournalOperation(type_operation='EXPORT_FISCAL', details={chemin, nb_lignes, date})`.

---

## 5. Bouton admin "Export fiscal"

### 5.1 Emplacement

Dans `ClotureCaisseAdmin` (`Administration/admin/laboutik.py`), meme pattern que les exports CSV/PDF/Excel existants.

### 5.2 Implementation

- `get_urls()` : ajouter `export_fiscal/` (GET → formulaire dates, POST → generation ZIP + download)
- Template inline simple : 2 champs date (debut/fin, optionnels — defaut = tout), bouton "Exporter"
- La generation reutilise la meme logique que `archiver_donnees` (fonction partagee)
- Response : `StreamingHttpResponse` avec `Content-Disposition: attachment; filename=...`

### 5.3 Bouton dans la liste

Ajouter un lien "Export fiscal" dans le `change_list_template` ou via `changelist_view` override,
a cote des boutons d'export existants.

---

## 6. Branchement `HistoriqueFondDeCaisse`

Dans `PaiementViewSet.fond_de_caisse()` (methode POST existante, session 17) :

```python
# Avant de sauver le nouveau montant
# / Before saving the new amount
HistoriqueFondDeCaisse.objects.create(
    ancien_montant=config.fond_de_caisse,
    nouveau_montant=nouveau_montant_centimes,
    operateur=request.user,
    point_de_vente=point_de_vente,
)
config.fond_de_caisse = nouveau_montant_centimes
config.save(update_fields=['fond_de_caisse'])
```

---

## 7. Factorisation : fonction partagee d'export

Pour eviter la duplication entre `archiver_donnees`, `acces_fiscal`, et le bouton admin,
extraire la logique d'export dans un module `laboutik/archivage.py` :

```python
def generer_archive(schema, debut, fin, cle_hmac):
    """
    Genere les donnees d'archive (CSV bytes + JSON bytes + hash).
    / Generates archive data (CSV bytes + JSON bytes + hash).

    :param schema: str, schema tenant
    :param debut: date ou None (None = tout l'historique)
    :param fin: date ou None
    :param cle_hmac: bytes, cle HMAC du tenant
    :return: dict {nom_fichier: bytes_contenu}
    """
```

Les 3 consumers (2 commands + 1 vue admin) appellent cette fonction
puis empaquettent le resultat en ZIP ou dossier selon le besoin.

---

## 8. Tests

Fichier : `tests/pytest/test_archivage_fiscal.py`

| Test | Ce qu'il verifie |
|------|-----------------|
| `test_archiver_genere_zip` | `archiver_donnees` produit un ZIP non vide |
| `test_archive_contient_fichiers_attendus` | 6 CSV + 3 JSON dans le ZIP |
| `test_archive_csv_contenu_correct` | Les CSV contiennent les bonnes colonnes et donnees |
| `test_archive_hash_integrite` | Hash HMAC de chaque fichier correspond |
| `test_archive_hash_global` | Hash global = HMAC(concat hash fichiers) |
| `test_archive_periode_max_1_an` | Erreur CommandError si periode > 365 jours |
| `test_verifier_archive_ok` | Archive non modifiee → code retour 0 |
| `test_verifier_archive_ko` | Fichier modifie dans le ZIP → code retour 1, details erreur |
| `test_acces_fiscal_genere_dossier` | Dossier complet avec README.txt |
| `test_journal_operation_archivage` | Entree JournalOperation creee apres archivage |
| `test_journal_operation_verification` | Entree JournalOperation creee apres verification |
| `test_journal_operation_hmac_chaine` | Chaine HMAC coherente entre 2+ entrees |
| `test_historique_fond_de_caisse_creation` | Trace creee au changement de fond via POST |
| `test_historique_fond_de_caisse_montants` | ancien_montant et nouveau_montant corrects |

---

## 9. Hors scope

- **Purge de donnees** (Ex.13-14) — pas dans les taches session 18
- **Celery Beat archivage automatique** — session 19
- **Envoi email rapports** — session 19
- **Version visible dans l'interface POS** — session 19
