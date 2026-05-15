# App COMPTABILITE — Hub documentaire

> Ce dossier est le **hub permanent** de l'app Django `comptabilite/`
> (Lespass V1). Il regroupe tous les chantiers passés et futurs liés à
> cette feature : clôture caisse, plan comptable paramétrable, exports
> FEC, profils CSV comptables, et toute évolution ultérieure.
>
> Convention : 1 chantier = 1 fichier `.md` numéroté dans ce dossier.
> `INDEX.md` (ce fichier) sert de table des matières + suivi global.

## Chantiers

| # | Chantier | Statut | Spec |
|---|---|---|---|
| 01 | Port partiel V2 (clôture caisse + plan comptable + exports CSV/FEC/Excel/PDF) | 🟡 Spec rédigée, en attente de S1 | [`SPEC.md`](SPEC.md) |
| 02 | (à venir) | — | — |

---

## Chantier 01 — Clôture comptable V1 (port partiel V2)

> Démarrage : 2026-05-15
> Branche : `main-wizard` (sera basculée sur `main-to-v2` au commit)
> Référence V2 : `/home/jonas/TiBillet/dev/lespass-main/laboutik/` (cloture caisse complète)
> Statut : 🟡 SPEC RÉDIGÉE, en attente de validation maintainer

## 1. Objectif

Porter de V2 (lespass-main, app `laboutik`) la page admin
`/admin/laboutik/cloturecaisse/` vers V1, **adaptée au périmètre V1** :
uniquement les **réservations d'événements** et les **adhésions**.

URL cible V1 : `/admin/comptabilite/cloturecaisse/` — visible dans la
sidebar Unfold section *Sales & accounting*, **juste au-dessus** de
l'entrée *Entries* (qui pointe sur `LigneArticle`).

L'app Django s'appelle **`comptabilite`** (et non `cloture`) car elle
hébergera également les modèles `CompteComptable` et
`MappingMoyenDePaiement` à partir de S5 (paramétrage du plan comptable
par tenant pour les exports CSV / FEC).

## 2. Spec détaillée

→ Voir [`SPEC.md`](SPEC.md) (spec complète : modèle, services, exports,
admin, tâches Celery, plan de découpage en sessions).

## 3. Périmètre

### On garde

- Modèle `ClotureCaisse` (UUID, périodicité J/H/M/A, numéro séquentiel,
  hash chain, `rapport_json` JSONField, totaux centimes)
- Service `RapportComptableService` (subset adapté)
- Rapport temps réel `/admin/cloture/rapport-temps-reel/`
- Exports : **CSV, Excel, PDF (WeasyPrint), FEC, CSV comptable**
  (7 profils ciblés sur la durée du chantier :
  Sage 50, EBP, Paheko, Dolibarr, PennyLane, CIEL, ODOO, DOKO ;
  voir SPEC §6.5 pour la priorisation)
- 4 tâches Celery périodiques : quotidienne, hebdomadaire, mensuelle,
  annuelle
- Email automatique des rapports (Configuration.rapport_emails +
  rapport_periodicite — petits AddField sur Configuration existante)
- Admin Unfold read-only avec rapport visuel (`change_form_before`) et
  bandeau exports (`changelist_before`)

### On ne garde pas (vs V2)

| Section / module V2 | Raison de l'exclusion |
|---|---|
| Modèle `PointDeVente`, `SortieCaisse`, `HistoriqueFondDeCaisse` | POS only — V1 n'a pas de caisse physique |
| `LaboutikConfiguration` (HMAC LNE, fond de caisse) | POS only |
| Section rapport « Solde caisse » | POS only |
| Section rapport « Recharges cashless » | Fedow only |
| Section rapport « Habitus » (stats NFC) | Fedow only |
| Section rapport « Opérateurs » | POS only (caissiers POS) |
| Section rapport « Ventilation par PV » | POS only |
| Filtre `sale_origin=LABOUTIK` | inversé en V1 → exclut LABOUTIK |
| Imprimantes thermiques, formatters Sunmi | POS only |
| Champ `point_de_vente` sur ClotureCaisse | POS only — supprimé. `total_perpetuel` conservé (filet anti-altération). |
| Modèle `ImpressionLog` (conformité LNE imprimante) | POS only — non porté |

## 4. Décisions principales

1. **App séparée `comptabilite/`** (TENANT_APPS) plutôt que coller dans
   `BaseBillet` ou `Administration`. Permet un rollback par retrait de
   l'app sans toucher au coeur métier. Nom choisi pour englober les
   futurs modèles `CompteComptable` et `MappingMoyenDePaiement`.
2. **Pas de `point_de_vente` sur le modèle** — V1 ne connaît pas le POS.
3. **Granularité paiement** : on ne pré-agrège pas par espèces/CB/cashless
   comme V2. On stocke `totaux_par_moyen` dans `rapport_json` avec les
   12 valeurs de `PaymentMethod` réelles (STRIPE_FED, STRIPE_NOFED,
   STRIPE_SEPA_NOFED, STRIPE_RECURENT, CC, CASH, CHEQUE, TRANSFER,
   QRCODE_MA, LOCAL_EURO, LOCAL_GIFT, FREE).
4. **Numéro séquentiel continu global tenant** (et non par niveau) —
   conformité LNE V2 conservée. Un seul compteur incrémental pour
   toutes les clôtures (J + H + M + A) d'un tenant. `UniqueConstraint`
   sur `numero_sequentiel` seul.
5. **Hash SHA-256 des lignes** conservé (filet de sécurité contre
   modifications post-clôture sur LigneArticle).
6. **Periodicités J/H/M/A** comme V2 — la clôture journalière reste la
   référence ; H/M/A sont des agrégations.
7. **Comptes comptables paramétrables dès S5** — modèles
   `CompteComptable` et `MappingMoyenDePaiement` portés depuis V2.
   Seed initial avec un plan comptable français par défaut (706, 756,
   411, 512, 530, 511, 4457X), modifiable par tenant.
8. **Mode école** (sale_origin=LABOUTIK_TEST de V2) non porté — V1 n'a
   pas ce concept.
9. **Configuration tenant enrichie** : 2 champs ajoutés à
   `BaseBillet.Configuration` :
   - `rapport_emails` (TextField, emails séparés par virgule)
   - `rapport_periodicite` (CharField, NONE/J/H/M/A)
10. **Filtre statut comptable** : `status IN [VALID, PAID, FREERES,
    CREDIT_NOTE]` — exclut CREATED/UNPAID/CANCELED/FAILED.
11. **7 profils CSV comptables ciblés** sur la durée du chantier :
    - **Phase A (S5)** : Sage 50, EBP, Paheko (premiers livrés avec
      le framework profils)
    - **Phase B (S6)** : Dolibarr, PennyLane, CIEL, ODOO, DOKO
      (ajoutés au fur et à mesure des demandes utilisateur)

## 5. Plan de découpage en sessions

→ Détail complet dans [`SPEC.md`](SPEC.md) section 9.

| # | Session | Sortie attendue |
|---|---|---|
| S1 | Modèle ClotureCaisse + migration + admin liste + sidebar | `/admin/comptabilite/cloturecaisse/` visible, vide |
| S2 | Service rapport + management command + tests pytest | `manage.py generer_cloture --niveau=J` produit un `rapport_json` valide |
| S3 | Templates admin (rapport visuel) + vue temps réel | Détail clôture lisible + page `/rapport-temps-reel/` |
| S4 | Exports CSV/Excel/PDF + FEC | 4 boutons d'export téléchargeables depuis la fiche |
| S5 | Celery beat J/H/M/A + email + modèles `CompteComptable` + `MappingMoyenDePaiement` + 3 profils CSV (Sage50, EBP, Paheko) | Génération auto + email + plan comptable paramétrable + 3 exports CSV comptables |
| S6 | 5 profils CSV restants (Dolibarr, PennyLane, CIEL, ODOO, DOKO) + polish | 8 profils CSV total, dossier de tests pytest complet |

Chaque session = **1 PR / commit isolé** validé par le maintainer.

## 6. Vérifications à passer à chaque session

```bash
# Check Django
docker exec lespass_django poetry run python /DjangoFiles/manage.py check

# Migrations
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations cloture --check --dry-run

# Tests pytest ciblés (à créer en S3)
docker exec lespass_django poetry run pytest tests/pytest/test_cloture_comptable.py -v
```

## 7. Garde-fous

- **Non destructif** : aucune modification du modèle `LigneArticle`,
  `Paiement_stripe`, `Reservation`, `Membership` existants.
- **Surface API stable** : aucun import externe affecté
  (`urls_tenants.py`, `discovery/admin.py`).
- **Multi-tenant** : toutes les requêtes passent par
  `tenant_context(tenant)` dans les tâches Celery ; modèles dans
  TENANT_APPS (table par schéma).
- **Pas de migration de données depuis V2** : V1 démarre sans clôture
  existante. La feature génère ses propres données à partir de
  `LigneArticle` du tenant.

## 8. Rollback

1. Retirer `'comptabilite'` de `TENANT_APPS` dans `TiBillet/settings.py`
2. Retirer entrée sidebar dans `Administration/admin/dashboard.py`
3. Retirer 4 wrappers Celery dans `TiBillet/celery.py`
4. Retirer les 2 champs ajoutés sur `Configuration` (migration reverse)
5. (Optionnel) Drop tables `comptabilite_*` via migration reverse

L'app `comptabilite/` reste sur disque, peut être ré-activée plus tard.

## 9. Statut détaillé

- [x] 0.1 Exploration code V2 (modèle, service, admin, exports, tasks)
- [x] 0.2 Exploration code V1 (LigneArticle, sidebar, Celery beat, deps)
- [x] 0.3 Rédaction SPEC.md
- [x] 0.4 Validation maintainer (décisions clés tranchées 2026-05-15)
- [ ] S1 — Modèle + admin minimal
- [ ] S2 — Service rapport + management command + tests
- [ ] S3 — Templates admin + vue temps réel
- [ ] S4 — Exports CSV/Excel/PDF/FEC
- [ ] S5 — Celery + email + CompteComptable + MappingMoyenDePaiement + 3 profils CSV (Sage50/EBP/Paheko)
- [ ] S6 — 5 profils CSV restants (Dolibarr/PennyLane/CIEL/ODOO/DOKO)

## 10. Liens utiles

- Spec détaillée chantier 01 : [`SPEC.md`](SPEC.md)
- Modèle V2 référence : `/home/jonas/TiBillet/dev/lespass-main/laboutik/models.py`
- Service V2 référence : `/home/jonas/TiBillet/dev/lespass-main/laboutik/reports.py`
- Admin V2 référence : `/home/jonas/TiBillet/dev/lespass-main/Administration/admin/laboutik.py`
- Templates V2 référence : `/home/jonas/TiBillet/dev/lespass-main/laboutik/templates/laboutik/`
- Cadre méthodologique migration V1↔V2 : [`../M-To-V2/INDEX.md`](../M-To-V2/INDEX.md)

---

## Ajouter un chantier futur dans ce dossier

Convention pour les sessions ultérieures sur l'app `comptabilite/` :

1. Créer un nouveau fichier `CHANTIER-02-<slug>.md` (puis 03, 04, ...) dans
   ce dossier. Slug court, kebab-case (ex: `CHANTIER-02-imports-fec.md`).
2. Ajouter une ligne dans le tableau « Chantiers » en haut de ce
   `INDEX.md` avec le numéro, le titre, le statut, le lien.
3. Suivre la structure type d'un chantier : Objectif, Périmètre,
   Décisions, Plan en sessions, Vérifications, Rollback, CHANGELOG.
4. À l'achèvement, basculer le statut sur ✅ et garder le `.md` en place
   (trace historique pour les futurs agents).
