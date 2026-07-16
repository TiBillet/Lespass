# Kiosk — borne de recharge cashless (TPE Stripe)

**Date :** 2026-07-08
**Migration :** Oui

Nouvelle app `kiosk` : borne libre-service de recharge cashless sur terminal Android (Cordova),
avec TPE Stripe WisePOS. Crédit de la carte **côté Fedow distant** (coexistence V1, webhook Stripe).

## Ce qui a été fait

| Fichier / Zone | Changement |
|---|---|
| `kiosk/models.py` | `StripeLocation`, `Terminal` (`term_user` OneToOne), `PaymentsIntent` (`send_to_terminal` **sans signature**) |
| `kiosk/admin.py` | Admin Unfold des 3 modèles (appairage TPE) |
| `kiosk/views.py` | `KioskViewSet` (list/check_request_card/refill_with_wisepos/cancel), garde `terminal_role==KI` |
| `kiosk/validators.py` | `RefillWisePoseValidator` (carte via Fedow) |
| `kiosk/tasks.py` | `poll_payment_intent_status` (Celery, WebSocket) |
| `kiosk/templates/kiosk/`, `static/kiosk/` | Front HTMX + Bootstrap + SweetAlert |
| `fedow_connect/fedow_api.py` | `NFCcardFedow.retrieve(tag_id)` (+ fix bug `self.config`) |
| `wsocket/consumers.py` + `routing.py` | `TerminalConsumer` + route `ws/terminal/<pi_id>/` |
| `laboutik/views.py` | Bridge : `KI` → `/kiosk/`, autres → `/laboutik/caisse` |
| `BaseBillet/models.py` (+ migr. 0227) | `Configuration.module_kiosk` |
| `Administration/admin/dashboard.py` | Module + section sidebar « Kiosk » |
| **Fedow** `fedow_core/views.py`, `models.py` (+ migr. 0025) | Extension route TPE (place Lespass sans signature, miroir S6) + idempotence `unique`/`IntegrityError` |

## Tests automatiques (déjà verts)

```bash
# Lespass (16 tests)
docker exec lespass_django poetry run pytest \
  tests/pytest/test_kiosk_models.py tests/pytest/test_kiosk_flow.py \
  tests/pytest/test_kiosk_branchements.py tests/pytest/test_hardware_auth_bridge.py \
  -v --api-key dummy

# Fedow (14 tests de régression stripe/signature/idempotence)
docker exec fedow_django python manage.py test fedow_core.tests.test_stripe_refill_regression
```

## Recette manuelle

### Test 1 — Activer le module + appairer un TPE (admin)
1. Admin `https://lespass.tibillet.localhost/` (user `admin@admin.com`).
2. Dashboard → activer le module **Kiosk**. La section sidebar « Kiosk » apparaît.
3. Kiosk → **Terminaux** → ajouter : `name`, `registration_code` (reader Stripe test : `simulated-wpe`).
   En `DEMO=1` l'appairage réseau est sauté ; en `DEMO=0` le reader Stripe est créé (clés Stripe test requises).

### Test 2 — Appairer une borne en rôle Kiosque
1. Créer un `PairingDevice` en rôle **KI** (admin discovery) → PIN 6 chiffres.
2. Sur l'app Android (même APK que LaBoutik), saisir le PIN.
3. Vérifier la redirection vers **`/kiosk/`** (pas `/laboutik/caisse`).

### Test 3 — Parcours de recharge (DEMO)
1. Écran `/kiosk/` : sélectionner un montant (boutons additifs).
2. Cliquer Valider → scan NFC (simulateur en DEMO).
3. Écran d'attente (spinner, WebSocket `ws/terminal/`).
4. En DEMO le statut est tiré au sort → écran succès **ou** annulation, retour accueil (compte à rebours 15 s).
   **Rappel** : en DEMO aucun webhook Stripe → **rien n'est réellement crédité côté Fedow** (écran succès cosmétique).

### Test 3bis — DEMO simulateur : clic sur une carte simulée (CHANTIER-05)
1. `/kiosk/` en DEMO : sélectionner un montant, cliquer **Valider**.
2. La popup SweetAlert « Merci de scanner votre carte » s'ouvre → un **overlay plein écran** (fond
   noir, boutons `primary` / `client1` / `client2` / `client3` / `unknown`) apparaît par-dessus, posé
   par `rfid.startLecture()` (qui, en DEMO, appelle directement `simule()` sans passer par le hardware).
3. Cliquer sur une des cartes (ex. `client1`) : l'overlay disparaît, l'événement `nfcResult` est
   déclenché avec le `tagId` correspondant.
4. Le paiement `POST /kiosk/refill_with_wisepos/` part avec ce `tag_id` → écran d'attente TPE (spinner).
5. Vérifier qu'aucun double-POST n'a lieu (fix `{ once: true }` conservé) : un seul `PaymentsIntent`
   créé pour ce clic.
6. Variante annulation : l'overlay couvre la popup (z-index 2000 > 1060 SweetAlert). Cliquer sur le
   **fond noir** (hors cartes) → l'overlay se ferme et rend la main à la popup ; cliquer alors
   **Annuler** → la popup se ferme, le montant est remis à zéro (`clearAmount()`), pas de POST envoyé.
   Sans action, le timer (30 s) ferme la popup et retire l'overlay (`stopLecture()`).

### Test 4 — Non-régression bridge (rôles LB/TI)
- Un terminal appairé en **LB** doit toujours atterrir sur `/laboutik/caisse` (test auto `test_hardware_auth_bridge.py`).

### Vérifs en base (optionnel)
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c \
 "from kiosk.models import Terminal, PaymentsIntent; print(Terminal.objects.count(), PaymentsIntent.objects.count())"
```

## Compatibilité / déploiement
- **2 repos** à committer : Lespass + Fedow.
- **Fedow : rebuild d'image** obligatoire (code baké) + `migrate` (0025). Un simple restart ne prend PAS les changements.
- **makemessages/compilemessages** FR/EN pour les `{% translate %}` du front kiosk.
- Décision sécurité (place Lespass sans signature) repose sur : **compte Stripe Root exclusif au serveur de la fédération** (cf. `TECH_DOC/SESSIONS/KIOSK/SPEC.md` §8bis).
