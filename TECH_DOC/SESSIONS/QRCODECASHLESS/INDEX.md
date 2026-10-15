# QRCODECASHLESS — Hub du chantier

App `QrcodeCashless` : cartes NFC cashless (`CarteCashless`, `Detail`).

**Fedow (`../Fedow`) est la source de vérité des cartes.** `CarteCashless` est
un miroir local, alimenté à la création via `fedow_connect`.

## Documents

| Doc | Contenu | Statut |
|---|---|---|
| [SPEC.md](./SPEC.md) | Formulaire d'ajout de carte à l'unité dans l'admin Unfold : `DetailAdmin`, `CarteCashlessAddForm`, dérivation des identifiants, flux Fedow, réconciliation | ✅ Validé 2026-07-09 |
| [CHANTIER-02-rapatriement-cartes-fedow.md](./CHANTIER-02-rapatriement-cartes-fedow.md) | Rapatriement au scan (façon V1) des cartes connues de Fedow mais absentes du miroir local ; branchement aux premiers scans hors `atomic` | ✅ Livré 2026-10-12 (non commité) — §4.1 étape 6 corrigée par le chantier 03 |
| [CHANTIER-03-fed-invisible-en-caisse.md](./CHANTIER-03-fed-invisible-en-caisse.md) | Bug de prod : FED invisible en caisse V2 (carte liée par QR avant le premier scan, carte anonyme avec FED legacy) ; diagnostic, tests rouges, correction proposée. Annexe : [audit des tests](./CHANTIER-03-annexe-audit-tests.md) | 🟡 Correction codée le 2026-10-14, non commitée ; E2E à relancer |

## Points d'attention

- `QrcodeCashless/views.py` (666 lignes) et `urls.py` sont **intégralement
  commentés** : l'app n'expose aucune vue.
- `fedow_core.CarteService` est écrit mais **branché nulle part** (tests seuls).
- Le `409 CONFLICT` de `POST /card/` côté Fedow est **mort** : `Card.uuid` est
  une PK, donc `read_only` en DRF, donc jamais en erreur `unique`. Un doublon
  produit un `400`.
- `CarteCashless` et `Detail` sont en `SHARED_APPS` (schéma `public`) : tout
  queryset admin **doit** filtrer par tenant, et l'unicité de `tag_id` /
  `number` / `uuid` est **globale à toutes les instances**.
