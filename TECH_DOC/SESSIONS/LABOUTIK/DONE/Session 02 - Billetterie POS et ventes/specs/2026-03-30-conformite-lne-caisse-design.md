# Design Spec — Conformite LNE systeme de caisse

> Date : 2026-03-30
> Statut : APPROUVE
> Referentiel : LNE/DEC/CITI/MN v1.7 (30/05/2024)
> Objectif : moyen terme (preparer le terrain technique, certification ulterieure)

---

## 1. Contexte

TiBillet/LaBoutik est un logiciel de caisse open-source utilise par des associations,
lieux culturels et petites structures en France. La certification LNE (ou NF525 via AFNOR)
est obligatoire pour les assujettis a la TVA utilisant un logiciel de caisse.

Depuis la loi de finances 2025 (art. 43), l'auto-attestation editeur est supprimee.
A partir du 01/09/2026, seul un certificat d'un organisme accredite (LNE ou AFNOR) est accepte.

Ce design couvre les exigences techniques du chapitre IV du referentiel LNE v1.7
(21 exigences). Le volet organisationnel (chapitre III : SMC) sera traite separement.

### Perimetre

- App `laboutik/` (TENANT_APPS) — caisse POS
- App `BaseBillet/` — modele `LigneArticle`
- App `laboutik/printing/` — formatters et impressions

### Hors perimetre (pour cette iteration)

- Chapitre III du referentiel (SMC — Systeme de Management de la Conformite)
- Documentation reglementaire formelle (7 dossiers requis par l'exigence 1)
- Audit organisationnel

---

## 2. Decisions architecturales

| Sujet | Decision | Raison |
|-------|----------|--------|
| Modele rapport | Pas de nouveau modele. Enrichir `ClotureCaisse` | Un seul chemin de calcul (Ticket X live / Ticket Z persiste) |
| Inalterabilite (Ex.8) | Chainage HMAC-SHA256 sur chaque `LigneArticle` | Standard industrie, accepte par le LNE, detecte modification ET suppression |
| Cle HMAC | Par tenant, chiffree Fernet dans `LaboutikConfiguration` | Isolation tenant, pattern existant (Sunmi credentials), cle inaccessible a l'utilisateur |
| Clotures (Ex.6) | 3 niveaux (J/M/A) dans un seul modele `ClotureCaisse`. **GLOBALE au tenant** (pas par PV). | Contexte festival : 40 PV, impossible de cloturer un par un. `ventilation_par_pv` dans le rapport JSON pour le detail. PV = informatif (nullable). |
| Clotures M/A | Automatiques via Celery Beat | Le caissier ne declenche que la cloture J |
| Cloture J declencheur | Seul un **gerant** peut cloturer. WARNING "cloture TOUS les PV". | Evite qu'un caissier lambda cloture la soiree par erreur |
| Total perpetuel (Ex.7) | Compteur dans `LaboutikConfiguration` + snapshot sur `ClotureCaisse` | Jamais remis a 0, incremente atomiquement |
| `datetime_ouverture` | Calcule auto = datetime de la 1ere `LigneArticle` apres derniere cloture | Pas de saisie manuelle, pas de trou, pas d'oubli |
| Garde periode cloturee (Ex.6) | Implicite par construction | `auto_now_add` + HMAC chain empechent toute retro-insertion |
| Corrections (Ex.4) | Operations de +/- uniquement (CREDIT_NOTE) | Jamais de modification directe. Garde stricte post-cloture. Exception : correction moyen paiement pre-cloture tracee via CorrectionPaiement (casse le HMAC volontairement, verify_integrity distingue correction/falsification) |
| Tracabilite impressions (Ex.9) | Table `ImpressionLog` dediee | Qui a imprime quoi quand. Mention "DUPLICATA" sur reimpressions |
| Mode ecole (Ex.5) | `sale_origin=LABOUTIK_TEST` + flag `mode_ecole` sur config | Donnees identifiees, bandeau visible, tickets "SIMULATION" |
| Archivage (Ex.10-12) | Export format ouvert (CSV/JSON) avec hash d'integrite | Periode max 1 an/exercice fiscal, conservation 6 ans |
| Acces fiscal (Ex.19) | Management command + vue admin dediee | Export donnees brutes + outil verification integrite |

---

## 3. Exigences LNE → correspondance technique

| Exigence | Description | Implementation TiBillet |
|----------|-------------|----------------------|
| **Ex.1** | Documentation reglementaire | *Reporte* — 7 dossiers a rediger pour la certification |
| **Ex.2** | Documentation complementaire | *Reporte* — doc technique en anglais/francais |
| **Ex.3** | Donnees a enregistrer | `LigneArticle` : ajouter `total_ht` (donnee elementaire, pas calculee) |
| **Ex.4** | Corrections par +/- | `CREDIT_NOTE` existant. Garde : refus si periode cloturee |
| **Ex.5** | Mode ecole/test | `sale_origin=LABOUTIK_TEST` + `mode_ecole` sur config + bandeau UI |
| **Ex.6** | Clotures J/M/A | Champ `niveau` sur `ClotureCaisse` (J/M/A). M/A auto Celery Beat |
| **Ex.7** | Donnees cumulatives et perpetuelles | `total_perpetuel` dans config + snapshot sur cloture |
| **Ex.8** | Inalterabilite des donnees | Chainage HMAC-SHA256 sur `LigneArticle` + cle Fernet par tenant |
| **Ex.9** | Securisation des justificatifs | `ImpressionLog`, mention DUPLICATA, distinction avant/apres paiement |
| **Ex.10** | Archivage des donnees | Export CSV/JSON horodate avec hash d'integrite |
| **Ex.11** | Periodicite d'archivage | Max 1 an ou 1 exercice fiscal par archive |
| **Ex.12** | Integrite des archives | Hash HMAC sur l'archive, verifiable independamment du systeme |
| **Ex.13** | Purge | Archivage obligatoire avant purge, cumulatifs jamais purges |
| **Ex.14** | Purge partielle | Cumulatifs et tracabilite conserves dans le systeme |
| **Ex.15** | Tracabilite des operations | Journal securise : archivage, purge, restauration |
| **Ex.16** | Conservation des donnees | 6 ans minimum (7 ans en pratique) |
| **Ex.17** | Conservation des archives | Integrite et disponibilite 6 ans |
| **Ex.18** | Systeme centralisateur | Non applicable (archi web, pas de stockage local TPV) |
| **Ex.19** | Acces administration fiscale | Management command + vue admin lecture seule |
| **Ex.20** | Perimetre fiscal | Tableau code source ↔ exigences (doc) |
| **Ex.21** | Versions majeures/mineures | Empreinte SHA-256 du code, visible dans l'interface |

---

## 4. Nouveaux modeles et champs

### 4.1 Modifications `LigneArticle` (BaseBillet/models.py)

```python
# Chainage HMAC (Ex.8)
hmac_hash = CharField(max_length=64, blank=True, default='')
previous_hmac = CharField(max_length=64, blank=True, default='')

# Donnee elementaire HT (Ex.3)
total_ht = IntegerField(default=0, help_text="Total HT en centimes (donnee elementaire)")
```

Le HMAC est calcule a la creation de chaque LigneArticle :
```python
import hmac, hashlib, json

def calculer_hmac(ligne, cle_secrete, previous_hmac):
    donnees = json.dumps([
        str(ligne.uuid),
        str(ligne.datetime.isoformat()),
        ligne.amount,            # TTC centimes
        ligne.total_ht,          # HT centimes
        float(ligne.qty),
        float(ligne.vat),
        ligne.payment_method,
        ligne.status,
        ligne.sale_origin,
        previous_hmac,           # chaine avec le precedent
    ])
    return hmac.new(
        cle_secrete.encode('utf-8'),
        donnees.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
```

### 4.2 Modifications `ClotureCaisse` (laboutik/models.py)

```python
# Niveau de cloture (Ex.6)
NIVEAU_CHOICES = [('J', 'Journaliere'), ('M', 'Mensuelle'), ('A', 'Annuelle')]
niveau = CharField(max_length=1, choices=NIVEAU_CHOICES, default='J')

# Numero sequentiel par niveau, global au tenant (Ex.6)
# La cloture est GLOBALE (pas par PV). point_de_vente est nullable/informatif.
numero_sequentiel = PositiveIntegerField()

# Total perpetuel snapshot (Ex.7)
total_perpetuel = IntegerField(default=0)

# Hash d'integrite des lignes couvertes (filet de securite)
hash_lignes = CharField(max_length=64, blank=True, default='')
```

### 4.3 Modifications `LaboutikConfiguration` (laboutik/models.py)

```python
# Cle HMAC chiffree Fernet (Ex.8)
hmac_key = CharField(max_length=200, blank=True, null=True)
# + get_hmac_key() / set_hmac_key() comme Sunmi

# Total perpetuel (Ex.7) — jamais remis a 0
total_perpetuel = IntegerField(default=0)

# Mode ecole (Ex.5)
mode_ecole = BooleanField(default=False)

# Config rapports
fond_de_caisse = IntegerField(default=0)
rapport_emails = JSONField(default=list)
rapport_periodicite = CharField(max_length=10, default='daily')
pied_ticket = TextField(blank=True, default='')
```

### 4.4 Nouveau modele `ImpressionLog` (laboutik/models.py)

```python
class ImpressionLog(models.Model):
    uuid = UUIDField(primary_key=True, default=uuid4)
    datetime = DateTimeField(auto_now_add=True)
    ligne_article = ForeignKey(LigneArticle, on_delete=PROTECT, null=True, blank=True)
    cloture = ForeignKey(ClotureCaisse, on_delete=PROTECT, null=True, blank=True)
    operateur = ForeignKey(TibilletUser, on_delete=SET_NULL, null=True)
    printer = ForeignKey(Printer, on_delete=SET_NULL, null=True)
    type_justificatif = CharField(choices=[
        ('VENTE', 'Ticket de vente'),
        ('CLOTURE', 'Ticket Z'),
        ('COMMANDE', 'Bon de commande'),
        ('BILLET', 'Billet'),
    ])
    is_duplicata = BooleanField(default=False)
    # Chaine HMAC comme les autres donnees (Ex.8)
    hmac_hash = CharField(max_length=64, blank=True, default='')
```

---

## 5. Service de calcul — `RapportComptableService`

Fichier : `laboutik/reports.py`

Un seul service, deux usages :
- **Ticket X** (recap en cours) : appel live, pas de sauvegarde
- **Ticket Z** (cloture) : meme appel, resultat persiste dans `ClotureCaisse.rapport_json`

12 methodes de calcul + `calculer_hash_lignes()` + `generer_rapport_complet()`.

Le `datetime_ouverture` est calcule automatiquement :
= datetime de la 1ere LigneArticle apres la derniere cloture J du PV.

---

## 6. Decoupage en sessions

### Session 12 — Fondation HMAC + service de calcul

**Scope** : la couche de base dont tout le reste depend.

1. Cle HMAC par tenant (chiffree Fernet dans LaboutikConfiguration)
2. Champs `hmac_hash` + `previous_hmac` + `total_ht` sur LigneArticle
3. Fonction `calculer_hmac()` dans `laboutik/integrity.py`
4. Integration dans `_creer_lignes_articles()` (chainage a chaque creation)
5. `RapportComptableService` avec 12 methodes de calcul
6. `verifier_integrite_chaine()` — management command de verification
7. Tests : HMAC ok, HMAC ko apres modif, chaine cassee si suppression, service 12 cles

### Session 13 — Clotures J/M/A + total perpetuel

**Scope** : enrichissement ClotureCaisse, 3 niveaux, total perpetuel.

1. Champs `niveau`, `numero_sequentiel`, `total_perpetuel`, `hash_lignes` sur ClotureCaisse
2. `datetime_ouverture` calcule auto (1ere vente apres derniere cloture)
3. Connecter `cloturer()` au `RapportComptableService`
4. Clotures M/A automatiques (Celery Beat)
5. Total perpetuel dans LaboutikConfiguration (incremente atomiquement)
6. Garde correction post-cloture (refus si LigneArticle couverte par cloture)
7. Admin Unfold ClotureCaisseAdmin enrichi (section "Ventes")
8. Tests : 3 niveaux, numero sequentiel, total perpetuel, garde correction

### Session 14 — Mentions legales tickets + tracabilite impressions

**Scope** : conformite des justificatifs (Ex.3, Ex.9).

1. Modele `ImpressionLog`
2. Enrichir `formatter_ticket_vente()` : raison sociale, SIRET, TVA, HT/TTC, n° sequentiel
3. Modifier `escpos_builder.py` : rendu des nouvelles sections
4. Mention "DUPLICATA" sur reimpressions
5. Tracabilite : `ImpressionLog.create()` a chaque impression
6. Champ `pied_ticket` sur LaboutikConfiguration
7. Distinction justificatif avant/apres paiement
8. Tests : mentions legales presentes, duplicata, log cree

### Session 15 — Mode ecole + exports admin

**Scope** : Ex.5 (mode test) + admin Unfold pour les rapports.

1. `sale_origin=LABOUTIK_TEST` dans SaleOrigin
2. Flag `mode_ecole` sur LaboutikConfiguration
3. Bandeau "MODE ECOLE" sur l'interface POS (conditionnel)
4. Tickets portent mention "SIMULATION" en mode ecole
5. Admin Unfold : vue detail HTML du rapport (12 sections, pas JSON brut)
6. Actions admin : telecharger PDF, CSV, Excel
7. Export PDF (WeasyPrint A4 formel), CSV (delimiteur ;), Excel (openpyxl)
8. Tests : mode ecole visible, donnees marquees, exports fonctionnels

### Session 16 — Menu Ventes (Ticket X + liste)

**Scope** : menu cote caisse tactile.

1. `recap_en_cours()` — Ticket X (3 sous-vues : toutes/par_pv/par_moyen)
2. `liste_ventes()` — historique scrollable avec filtres et pagination HTMX
3. `detail_vente()` — detail d'une LigneArticle avec actions
4. Templates HTMX dans `laboutik/templates/laboutik/partial/`
5. Integration burger menu du header POS
6. CSS dans fichier separe
7. Tests : 5+ pytest, navigation E2E

### Session 17 — Corrections + fond/sortie de caisse

**Scope** : corrections moyen paiement, fond de caisse, sortie especes.

1. Modeles `CorrectionPaiement` et `SortieCaisse`
2. `corriger_moyen_paiement()` : ESP<->CB<->CHQ uniquement, NFC interdit, post-cloture interdit
3. Tracabilite : CorrectionPaiement avec raison obligatoire
4. Reimprimer ticket (reconstruit + `imprimer_async.delay()`)
5. Fond de caisse GET/POST
6. Sortie de caisse avec ventilation par coupure (12 lignes)
7. Total sortie recalcule cote serveur
8. Tests : 7+ pytest, correction NFC refusee, post-cloture refusee

### Session 18 — Archivage fiscal + acces administration

**Scope** : Ex.10-12, Ex.15, Ex.19.

1. Management command `archiver_donnees` : export CSV/JSON horodate
2. Hash HMAC sur l'archive (verifiable independamment)
3. Periodicite : max 1 an par archive
4. Management command `verifier_archive` : recheck integrite
5. Tracabilite operations (archivage, purge) dans journal securise
6. Management command `acces_fiscal` : export complet pour l'administration
7. Vue admin "Acces administration fiscale" (lecture seule, export)
8. Tests : archive generee, integrite verifiable, acces fiscal fonctionnel

### Session 19 — Envoi automatique + version (Ex.21)

**Scope** : Celery Beat rapports + identification version.

1. `generer_et_envoyer_rapport_periodique()` (Celery Beat daily/weekly/monthly/yearly)
2. Config : `rapport_emails`, `rapport_periodicite` dans LaboutikConfiguration
3. Empreinte SHA-256 du code source (perimetre fiscal)
4. Version majeure/mineure visible dans l'interface POS
5. Tests : envoi email avec PJ, version affichee

---

## 7. Ce qui ne change PAS

- Le `RapportComptableService` reste le coeur du calcul
- `ClotureCaisse` reste le seul modele de cloture (pas de `RapportComptable` separe)
- Les corrections passent toujours par `CREDIT_NOTE` (operations de +/-)
- L'architecture SaaS (django-tenants) protege deja l'acces en ecriture (Ex.8 option 3)
- Les tests existants (261 pytest + 36 E2E) ne doivent pas regresser

---

## 8. Risques et mitigations

| Risque | Mitigation |
|--------|-----------|
| Migration HMAC sur LigneArticle existantes | Les lignes existantes auront `hmac_hash=''`. Le chainage demarre a la 1ere ligne apres migration. La commande `verify_integrity` ignore les lignes pre-migration |
| Performance HMAC a chaque vente | Un HMAC-SHA256 prend ~1µs. Double write DB (INSERT + UPDATE) par ligne — negligeable |
| Chaines HMAC separees test/prod | Les lignes `LABOUTIK_TEST` et `LABOUTIK` ont des chaines HMAC independantes (voulu — les donnees test ne polluent pas la chaine de production) |
| Perte de la cle HMAC | Cle chiffree Fernet en DB, sauvegardee avec les backups PostgreSQL. Si perdue, la chaine est cassee mais les donnees restent lisibles |
| openpyxl pas dans pyproject.toml | Verifier et signaler au mainteneur avant la session 15 |
| Mode ecole active en production | Le bandeau est tres visible. L'admin peut desactiver. Les donnees sont marquees `LABOUTIK_TEST` et exclues des rapports de prod |
