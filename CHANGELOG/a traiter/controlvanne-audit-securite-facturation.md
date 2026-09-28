# controlvanne : facturation, suites de l'audit (sécurité traitée)

**Relevé du 2026-09-26.** Il vient de trois audits en lecture seule de
`controlvanne/` : djc côté Python, djc côté templates/JS, et hallmark sur
l'interface. Les lots 3 (écran kiosk) et 4 (calibration, i18n, a11y) ont été
corrigés : voir `CHANGELOG/2026-09-26-controlvanne-audit.md`. Le lot 1
(sécurité) a été traité le 2026-09-28. Le lot 2 ci-dessous est
**volontairement mis en attente**.

Chaque point **critique** a été vérifié dans le code. Les autres viennent des
audits et sont à confirmer au moment de les traiter.

**Traités depuis :** tout le lot 1 (sécurité).
- 1.4 (clé ↔ tireuse), 1.5 (calibration réservée au lieu), 1.6 (limite sur
  `authorize`) → `CHANGELOG/2026-09-28-controlvanne-securite-cles-calibration.md` ;
- 1.1 (accès au WebSocket), 1.2 (groupes par lieu), 1.3 (suppression de
  `KioskTokenView`) →
  `CHANGELOG/2026-09-28-controlvanne-websocket-acces-et-groupes-par-lieu.md`.

**Ordre de priorité proposé :** 2.1 (erreur de stock dans la facture) → 2.3
(montants calculés par le serveur) → le reste.

---

## Lot 2 — Facturation / argent

### 2.1 Une erreur de stock peut annuler toute la facture (vérifié)

- **Où :** `billing.py:350-363`.
- **Constat :** `except Exception: pass` autour de
  `StockService.decrementer_pour_vente`, **dans** le `transaction.atomic()` de
  `facturer_tirage` (`billing.py:223`), sans savepoint.
- **Scénario d'échec :** une erreur base de données dans `StockService`
  (contrainte, verrou…) met la transaction Postgres en état « aborted ». Le
  `pass` cache l'erreur. La requête suivante lève alors
  `TransactionManagementError`, qui fait remonter une 500 : transactions,
  `LigneArticle` et fermeture de session sont annulées, sans message clair.
- **Correctif :** tester l'absence de stock proprement
  (`hasattr(produit, "stock_inventaire")`), appeler `StockService` dans un
  `atomic()` imbriqué, et journaliser avec `logger.exception`.

### 2.2 Réservoir mis à jour avec une valeur périmée

- **Où :** `viewsets.py:229` (`_cloturer_session_et_facturer`).
- **Constat :** `tireuse.reservoir_ml = max(0, tireuse.reservoir_ml - v)` est
  calculé sur une tireuse lue sans verrou. Deux fermetures simultanées
  (session orpheline + `pour_end`) perdent une décrémentation.
- **Correctif :** `update(reservoir_ml=Greatest(F("reservoir_ml") - v, 0))`,
  puis `refresh_from_db`. Attention : `update()` ne déclenche pas `post_save`.
  Il faut extraire le push du snapshot (`signals.py`) dans une fonction et
  l'appeler via `on_commit`.

### 2.3 Montants calculés côté client

- **Où :** `controlvanne/static/controlvanne/js/ecran_tireuse.js:35,216`
  (nombre de verres, `prix_litre × 0.25`) et le calcul du prix servi.
- **Constat :** c'est de la logique d'argent dans le JS. L'arrondi JS n'est pas
  celui du serveur (`billing.py`), donc l'écran peut afficher un centime de
  différence avec le montant débité.
- **Correctif :** `_construire_payload_session` ajoute `prix_servi` et
  `nombre_verres`, déjà formatés, calculés par une fonction commune avec la
  facture. Le JS se contente d'écrire. `ws_payloads.py` doit être mis à jour.

### 2.4 Trop de requêtes à chaque `pour_update` (≈ 1/s/tireuse)

- **Constat :** `prix_litre` est lu 3 fois (une requête chaque fois),
  `liquid_label` charge le fût, `reservoir_max_ml` fait une requête sur Stock,
  plus le contexte cashless et une requête de solde par asset. Au total, plus
  de 10 requêtes par seconde et par tireuse.
- **Correctif :** `select_related("fut_actif")`, `prix_litre` lu une seule fois
  dans une variable, et le solde de l'`authorize` gardé en mémoire (à voir : un
  champ sur `RfidSession` demanderait une migration).

### 2.5 Restriction des cartes maintenance jamais appliquée

- **Où :** `models.py:158-164` (`CarteMaintenance.tireuses`, « Leave empty for
  all taps »), qui n'est jamais lu dans `authorize`.
- **Correctif :** refuser si `carte_maintenance.tireuses.exists()` et que la
  tireuse n'y figure pas (`_push_refus` avec un message traduit).

### 2.6 Refus sur tireuse désactivée non affiché

- **Où :** `viewsets.py:456`.
- **Constat :** le refus renvoie « Tap is disabled. » sans `_push_refus` : le
  kiosk n'affiche pas le refus.
- **Correctif :** ajouter `_push_refus(tireuse, _("Tireuse hors service."))`.

---

## Hors lots, relevés mais non instruits

- `ws_payloads.py` n'est importé nulle part, `force_close` n'est jamais émis,
  `RfidSession.last_message` n'est jamais écrit, `controlvanne/tests.py` est
  vide, et `ConfigurationTireuse` n'a aucun champ.
- `billing.py` importe des fonctions privées de `laboutik/views.py`
  (`_obtenir_ou_creer_wallet`, `_calculer_qty_partielles`) : il faudrait les
  déplacer dans un module `services`.
- `REMOTE_ADDR` derrière Traefik donne l'IP du proxy, pas celle du Pi.
- Docstring de `AuthKioskView` contradictoire : elle dit que le jeton ne passe
  pas en query string, alors que le Pi utilise `?kiosk_token=`.
