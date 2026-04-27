# Gestion des cartes cashless — fedow_core

Documentation technique du flow carte cashless dans `fedow_core`. Remplace
progressivement `fedow_connect/` (HTTP vers Fedow distant).

## Modele `CarteCashless` (QrcodeCashless/models.py)

Une carte NFC physique, identifiee par :
- `tag_id` : identifiant NFC 8 hex (grave dans la puce)
- `uuid` : UUID public, utilise dans l'URL `/qr/<uuid>/` (QR code imprime)
- `number` : numero imprime visible (8 chars)
- `detail` : FK vers `Detail` (lot de cartes, porte l'origine via `detail.origine`)
- `user` : FK `TibilletUser` nullable — null si carte anonyme
- `wallet_ephemere` : OneToOne `Wallet` nullable — conteneur anonyme

## Les 4 etats d'une carte

| Etat | `user` | `wallet_ephemere` | Ou sont les tokens ? |
|---|---|---|---|
| Vierge | None | None | Nulle part |
| Anonyme | None | `Wallet_X` | Sur `Wallet_X` (sans reverse user) |
| Identifiee | `User_A` | None | Sur `User_A.wallet` |
| Perdue | None | None | Restent sur `User_A.wallet` (detache) |

## Transitions

### Scan d'une carte vierge (`CarteService.scanner_carte`)
- Vierge -> Anonyme : cree un `Wallet` avec `origin=detail.origine`, l'attache.

### Identification (`CarteService.lier_a_user`)
- Anonyme -> Identifiee : fusion des tokens `wallet_ephemere -> user.wallet` via
  `Transaction(action=FUSION)`, puis `carte.user = user ; carte.wallet_ephemere = None`.
- Anti-vol : refus si `user` a deja une autre carte (`user.cartecashless_set.exclude(pk=carte.pk).exists()`).
- Rattrapage : les `Membership(user=None, card_number=carte.number)` sont rattachees.

### Perte (`CarteService.declarer_perdue`)
- Identifiee -> Perdue : `carte.user = None ; carte.wallet_ephemere = None`.
- `user.wallet` et ses tokens restent intacts : le user peut lier une nouvelle carte.

## Pourquoi une fusion et pas "attacher l'user au wallet_ephemere" ?

1. **Unicite OneToOne user<->wallet** : `TibilletUser.wallet` est un OneToOne.
   Un user a un seul wallet. Un user peut avoir un wallet preexistant avec des
   tokens (adhesion, FED d'un autre festival, etc.) — on ne peut pas "l'ecraser".
2. **Preservation des tokens preexistants** : si `user.wallet` a deja 15 FED,
   attacher le wallet_ephemere (5 TLF) les perdrait.
3. **Auditabilite** : `Transaction(FUSION)` trace explicitement le transfert.

## Dispatch V1/V2

- Tenant avec `Configuration.server_cashless` renseigne -> V1 (`fedow_connect`).
- Tenant sans -> V2 (`fedow_core.CarteService`).
- Les 2 systemes de tokens sont disjoints : tokens V1 restent sur serveur Fedow
  distant, tokens V2 dans DB locale. Pas de pont entre les deux (hors scope).

## Coexistence avec le refactor wallet-only (en attente)

Le design `2026-04-14-refactor-carte-wallet-only-design.md` propose de supprimer
`CarteCashless.user` et `wallet_ephemere` au profit d'un champ `wallet` unique.
Si ce refactor passe, adapter `CarteService` (logique simplifiee, plus de dualite).
