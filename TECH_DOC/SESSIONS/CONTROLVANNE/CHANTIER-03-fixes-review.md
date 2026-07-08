# CHANTIER-03 — Fixes de la review critique (C1-C3, I1-I4)

**Date** : 2026-07-06 — **FAIT** (TDD, 5 tests de garde + refactor JS)
**Réf.** : [REVIEW-2026-07-06-tour-critique.md](./REVIEW-2026-07-06-tour-critique.md)

## Ce qui a été corrigé

### C1 + I1 — Double facturation concurrente + compteurs incohérents
`controlvanne/viewsets.py` (branche `pour_end`/`card_removed` de `event()`)

Le test TDD a **prouvé le bug en réel** avant le fix : 2 threads `pour_end`
simultanés (barrier) → « 2 facturations pour UN tirage » sur la dev DB.

Fix : `transaction.atomic()` englobant + `RfidSession.objects.select_for_update()
.filter(pk=…, ended_at__isnull=True)` avec re-check — l'événement concurrent
reçoit un 200 « Session already closed by a concurrent event » sans re-facturer.
La fermeture de session, le décrément réservoir et la facturation partagent
désormais **une seule transaction** (I1) : plus de compteurs committés à moitié
si le serveur tombe au milieu. Sur `SoldeInsuffisant`, le savepoint interne de
`facturer_tirage` annule la facturation seule — fermeture + réservoir conservés
(réalité physique : la bière est servie), comportement S6 documenté inchangé.

**Effet de bord maîtrisé** : le `save()` du réservoir se fait désormais dans
l'atomic → le push WS du signal `post_save` de TireuseBec passe par
`transaction.on_commit` (`controlvanne/signals.py`) — piège projet
« broadcast dans atomic » évité ; hors transaction, `on_commit` s'exécute
immédiatement (comportement inchangé partout ailleurs).

### C2 — Reconnexion WebSocket du kiosk
`controlvanne/static/controlvanne/js/panel_kiosk.js` + `controlvanne/templates/base.html`

Le kiosk 24/7 gelait en silence à la première coupure (restart daphne,
micro-coupure Wi-Fi). Fix : connexion enveloppée dans `connecterWebSocket()`
avec `onclose`/`onerror` → retry avec backoff (1 s doublé jusqu'à 30 s max,
remis à zéro à la reconnexion), handler `onmessage` extrait tel quel en
`traiterMessageWs()`. Bandeau `#ws-status-banner` (alert Bootstrap,
`aria-live="assertive"`, `data-testid="kiosk-ws-banner"`) affiché pendant la
coupure, masqué au retour.

### C3 — Refus propre au lieu d'un 500 (carte sans wallet résoluble)
`controlvanne/billing.py` (`obtenir_contexte_cashless`)

`_obtenir_ou_creer_wallet` (laboutik, divergé du proto V2) LÈVE si la carte
n'a ni `user.wallet` ni `wallet_ephemere` et n'est pas résoluble via le Fedow
legacy. Décision : **pas de création de wallet éphémère à l'authorize tireuse**
(une carte sans wallet n'a aucun token → refus de toute façon ; l'éphémère se
crée au POS/recharge). Le try/except transforme l'exception en `None` → les
deux appelants (authorize → `{authorized: false}`, pour_end → pas de
facturation, loggé) refusent proprement.

### I2 — Réservoir remis à 0 au swap de fût sans Stock
`controlvanne/signals.py` (pre_save) : fût changé sans `Stock > 0` →
`reservoir_ml = 0` (pas d'info = pas de réserve connue) au lieu de conserver
la valeur de l'ancien fût (jauge fausse, « fût vide » prématuré).

### I3 — `volume_ml` négatif rejeté
`controlvanne/serializers.py` : `min_value=Decimal("0")` sur `EventSerializer`.

### I4 — Volume affiché correct sur tirage court
`controlvanne/models.py` (`close_with_volume`) : met aussi à jour
`dernier_volume_ml` — un tirage sans aucun `pour_update` n'affiche plus
« 0 cl » au kiosk.

## Tests

`tests/pytest/test_controlvanne_review_fixes.py` — 5 tests de garde (TDD,
tous rouges avant fix, tous verts après) dont le **test de concurrence à
2 threads** (barrier, connexions DB séparées) pour C1.

Non-régression : 52 tests controlvanne + discovery verts ; suite complète
relancée (cf. A TESTER).

## Restes (Minor de la review, dette assumée)

Cascade incluant FED sans garde-fou explicite, décrément réservoir en
read-modify-write (1 bec = 1 flux), `except: pass` stock dans l'atomic,
arrondi cl des micro-tirages, i18n calibration, N+1 admins historiques,
`quantite_avant` d'audit. → liste complète dans la REVIEW, à traiter à
l'occasion.
