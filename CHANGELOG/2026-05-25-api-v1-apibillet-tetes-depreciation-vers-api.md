# API v1 (ApiBillet) — en-têtes de dépréciation vers /api/v2/ / API v1 deprecation headers

**Date :** 2026-05-25
**Migration :** Non

**Quoi / What :**
- Les réponses des endpoints **consommateur** de l'API v1 (`ApiBillet`) portent
  désormais des en-têtes HTTP **non bloquants** orientant vers v2 :
  `Deprecation: true`, `Link: </api/v2/>; rel="successor-version"`,
  `Warning: 299 - "TiBillet API v1 is deprecated, migrate to /api/v2/"`.
- Mécanisme : mixin **`DeprecatedV1Mixin`** (override `finalize_response`) placé en
  **première base** des viewsets/APIViews consommateur. Marche pour `ViewSet` **et**
  `APIView` (les deux héritent `finalize_response` de DRF — vérifié).
- 12 classes concernées : `ApiReservationViewset`, `EventsViewSet`, `EventsSlugViewSet`,
  `ProductViewSet`, `TarifBilletViewSet`, `TicketViewset`, `Wallet`, `OptionTicket`,
  `HereViewSet`, `Gauge`, `TicketPdf`, `CancelSubscription`.
- **Exclus** (plomberie, pas de successeur v2) : `Webhook_stripe`, `Onboard_laboutik`,
  `Onboard_stripe_return`, `Get_user_pub_pem`.
- **Pas de `Sunset`** (aucune date de retrait décidée — à ajouter dans
  `API_V1_DEPRECATION_HEADERS` le jour venu).

**Pourquoi / Why :** orienter les intégrateurs (ex. client « codex-api » repéré sur le
tenant `raffinerie`) vers l'API v2 sémantique, sans casser les clients v1 existants.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `ApiBillet/views.py` | + `API_V1_DEPRECATION_HEADERS` + `DeprecatedV1Mixin` ; mixin ajouté en 1ʳᵉ base de 12 classes consommateur |

### Migration
- **Migration nécessaire / Migration required :** Non
