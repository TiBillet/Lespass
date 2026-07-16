# Kiosk : revue sécurité + robustesse du suivi de paiement / Kiosk: security review + payment-tracking hardening

**Date :** 2026-07-10
**Migration :** Non / No

**Quoi / What :** corrections issues d'une double revue (workflow adversarial + agent sécurité) du flux
de paiement TPE et du suivi WebSocket.

- **IDOR intra-tenant sur `cancel`** (`kiosk/views.py`) : `cancel` annulait le paiement Stripe sans
  vérifier l'appartenance — une borne pouvait annuler le paiement en cours d'une autre borne du même
  tenant en devinant son `pk`. Garde d'appartenance ajoutée (helper `utilisateur_peut_acceder_au_paiement`),
  partagée avec `payment_status`. **3 tests** (`test_kiosk_security.py`).
- **Broker Redis down → carte débitée en silence** (`kiosk/views.py`) : quand `.delay()` lève
  `OperationalError`, le lecteur était déjà armé et n'était jamais annulé. On appelle désormais
  `PaymentsIntent.annuler_sur_le_terminal()` avant d'afficher l'erreur.
- **Filet `payment_status` inopérant si le worker meurt** (`kiosk/views.py`) : il lisait le statut en
  base, que seule la tâche Celery avance. Il interroge maintenant Stripe lui-même (`get_from_stripe`)
  tant que le statut local n'est pas terminal — vrai filet indépendant du worker.
- **Garde WebSocket désactivée sous `DEBUG`** (`wsocket/consumers.py`) : `if not settings.DEBUG:`
  court-circuitait toute la garde. Remplacé par `connexion_autorisee()` calqué sur `IsKioskTerminal`
  (borne KI propriétaire OU admin tenant), actif en dev comme en prod. Catch élargi (`ProgrammingError`
  sur schéma public → refus propre au lieu d'un crash du consumer).
- **Timeout Celery affichait un « Annulé » mensonger** (`kiosk/tasks.py`) : sur timeout, annulation
  réelle côté Stripe puis affichage du statut réel (succès si capturé entre-temps, sinon annulé) —
  écran, base et Stripe cohérents.
- **Bug front** (`sweet_scan_button.html`) : `const chevronsDeScan` en portée globale d'un `<script>`
  de partial re-swappé par HTMX → `SyntaxError` au 2ᵉ swap, bouton scan cassé. Déplacé dans `readNfc()`.

**Nouveau modèle** : `PaymentsIntent.annuler_sur_le_terminal()` (best-effort : lâche le lecteur, annule
le PaymentIntent, reflète le statut Stripe réel). Utilisé par `cancel`, le broker down et le timeout.

**Vérifié** : Chrome (flux complet, mode nuit, panneau simulateur, non-régression), 20 tests kiosk verts.
**Audit externe consigné** : le webhook Fedow ne signe pas les places Lespass (SPEC §8bis) — sûr tant que
la clé Stripe Root reste exclusive au serveur ; `fedow_place_uuid` posé par le serveur, non falsifiable
par un tenant. Rien à corriger côté Lespass.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `kiosk/views.py` | Helper appartenance, garde `cancel`, filet Stripe, annulation broker-down |
| `kiosk/models.py` | `PaymentsIntent.annuler_sur_le_terminal()` + logger |
| `wsocket/consumers.py` | `connexion_autorisee` (fin du bypass DEBUG), catch élargi |
| `kiosk/tasks.py` | Timeout : annulation réelle + statut cohérent |
| `kiosk/templates/kiosk/sweet_scan_button.html` | `chevronsDeScan` déplacé (fin du re-swap cassé) |
| `tests/pytest/test_kiosk_security.py` | 3 tests IDOR (cancel/status refusés à une autre borne) |

---
