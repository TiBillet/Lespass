# QRCODECASHLESS — Hub du chantier

App `QrcodeCashless` : cartes NFC cashless (`CarteCashless`, `Detail`).

**Fedow (`../Fedow`) est la source de vérité des cartes.** `CarteCashless` est
un miroir local, alimenté à la création via `fedow_connect`.

## Documents

| Doc | Contenu | Statut |
|---|---|---|
| [SPEC.md](./SPEC.md) | Formulaire d'ajout de carte à l'unité dans l'admin Unfold : `DetailAdmin`, `CarteCashlessAddForm`, dérivation des identifiants, flux Fedow, réconciliation | ✅ Validé 2026-07-09 |

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
