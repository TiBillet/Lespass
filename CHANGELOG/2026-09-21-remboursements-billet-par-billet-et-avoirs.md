# Remboursements billet par billet, avoirs hors Stripe, tests Stripe réel / Ticket-by-ticket refunds, non-Stripe credit notes, real Stripe tests

**Date :** 2026-09-21
**Migration :** Non (données déjà en base non reprises : rien de ce code n'est en production)
**Plan :** `TECH_DOC/SESSIONS/REMBOURSEMENT/SPEC.md`

## Resume / Summary

**Quoi / What :** on peut rembourser une réservation billet par billet, puis en entier, avec
ou sans panier. Chaque remboursement Stripe part vraiment ; chaque annulation d'une vente
admin (espèces, chèque…) crée un avoir du bon montant, sur la bonne vente. Si une réservation
payée n'a rien de remboursable, l'annulation est refusée au lieu d'être faite en silence.
Les tests se lancent par `make`, Python ou E2E, avec ou sans Stripe réel.
/ A reservation can be refunded ticket by ticket, then in full, with or without cart. Every
Stripe refund is really sent; every admin sale cancellation creates a credit note of the right
amount, on the right sale. A paid reservation with nothing refundable is refused instead of
silently cancelled. Tests run through `make`, Python or E2E, with or without real Stripe.

**Pourquoi / Why :** défauts prouvés (essai front, journal serveur ou test) :
/ Proven defects (front test, server log or test):

1. **Argent non remboursé** — sans panier, après un 1er billet remboursé (paiement
   `PARTIALLY_REFUNDED`), les billets suivants étaient annulés sans remboursement Stripe.
   / **Money not refunded** — without cart, after a first refunded ticket, the next ones were
   cancelled with no Stripe refund.
2. **Avoir sur la vente d'un autre client** — une réservation sans ligne hors Stripe (vente Stripe,
   réservation gratuite) créait un avoir sur les ventes admin du même tarif.
   / **Credit note on another customer's sale** (tenant-wide fallback).
3. **Montant payé faux** — lignes de remboursement et avoirs non rattachés à la réservation :
   `total_paid()` (compte client, admin, export, mails) montrait le montant d'avant.
   / **Wrong paid amount** — refund lines and credit notes were not linked to the reservation.
4. **Avoir de toute la ligne pour un seul billet admin** (3 billets → −3 au 1er billet annulé).
   / **Credit note for the whole line when cancelling one admin ticket.**
5. **Mauvais message** après un remboursement Stripe, et **fausses erreurs** dans les logs
   (`erreur_regression V to H`, `P to C`).
   / **Wrong message** after a Stripe refund, and **false errors** in the logs.
6. La réservation restait « Valide » quand ses billets étaient tous annulés un par un.
   / The reservation stayed "Valid" once all its tickets were cancelled one by one.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `cancel_and_refund_resa` / `cancel_and_refund_ticket` : `PARTIALLY_REFUNDED` dans le filtre sans panier ; `refund = True` après Stripe ; **garde-fou** « Aucun paiement remboursable » ; réservation `CANCELED` au dernier billet (`save(update_fields=["status"])`) ; docstrings LOCALISATION/FLUX |
| `BaseBillet/models.py` | `_lignes_hors_stripe()` : repli sur tout le lieu **supprimé** (FK directe seulement, comme Booking) ; `quantite_restante` calculée en boucle ; `_creer_avoir(ligne, quantite)` rattaché à la réservation ; `articles_paid()` compte les `CREDIT_NOTE` |
| `PaiementStripe/utils.py` | La ligne de remboursement recopie `reservation`, `booking`, `membership` |
| `BaseBillet/signals.py` | Machine à états : `PAID`/`VALID` → `PARTIALLY_REFUNDED`, `PAID` → `REFUNDED`, réservation `PAID` → `CANCELED` déclarés |
| `booking/tasks.py` | Mail d'annulation Booking : montant = vente d'origine (plus `total_paid()`, qui vaut 0 après remboursement) |
| `Administration/admin_tenant.py` | `LIGNE_PAYEE_STATUTS` compte les `CREDIT_NOTE` |
| `tests/pytest/test_stripe_refund.py` | Réécrit : matrice avec/sans panier, avoirs hors Stripe, garde-fou, logs, gratuit |
| `tests/pytest/test_stripe_reel_remboursement.py` | **Nouveau** — vrais paiements et remboursements Stripe (mode test), vérifiés chez Stripe : remboursements (`Refund.list`) et paiement encaissé / remboursé en totalité (`Charge.list`) |
| `tests/pytest/test_mail_annulation_booking.py` | **Nouveau** — montant du mail d'annulation Booking |
| `tests/pytest/fabriques_reservation.py` | **Nouveau** — fabriques de ventes réutilisables (avec/sans panier, admin, `compte_stripe_reel=`) |
| `tests/stripe_reel.py` | **Nouveau** — outils Stripe réel (clé `sk_test_` obligatoire) + tests « sur demande » partagés pytest/E2E |
| `tests/pytest/conftest.py`, `tests/e2e/conftest.py`, `pytest.ini` | Variable unique `STRIPE_REEL=1` (fin de `E2E_STRIPE_LISTEN`), marqueur `stripe_reel` |
| `tests/e2e/test_renouvellement_adhesion_recurrente.py` | Factorisé sur `preparer_stripe_mode_test()` (garde anti-clé live) |
| `Makefile`, `scripts/lancer_tests.sh` | **Nouveaux** — `make test`, `test-stripe`, `e2e`, `e2e-stripe` |
| `README.md`, `README.en.md`, `tests/README.md`, `tests/PIEGES.md` | Procédure `make` ; pièges 12.16 à 12.18 |
| `TECH_DOC/SESSIONS/REMBOURSEMENT/`, `TECH_DOC/SESSIONS/TODO/PANIER-en-base-commande-draft.md` | Hub du chantier ; idée « panier en base » mise de côté |

### Effets à connaître / Side effects

- **Ventes admin d'avant mars 2026** (lignes sans réservation liée) : les annuler ne crée plus
  d'avoir (décision : le repli était ambigu et touchait d'autres clients).
- **Garde-fou** : une réservation payée dont aucun paiement n'est remboursable n'est plus annulée ;
  le front et l'admin affichent l'erreur. Nouvelle chaîne traduisible (source FR) :
  « Aucun paiement remboursable n'a été trouvé. Rien n'a été annulé. » → **workflow i18n à lancer**.
- **Booking** : `Booking.total_paid()` devient juste après remboursement ; le mail d'annulation
  lit la vente d'origine.
- **Données déjà en base** : les remboursements et avoirs créés avant ce correctif restent sans
  lien vers leur réservation (bases de dev seulement).

### Non traité / Not addressed

Voir `SPEC.md` §6 et §7 : double remboursement possible si une exception suit `Refund.create`
ou sur double clic (R1), `.delay()` dans la transaction (R2), webhooks `refund.*` ignorés (R3),
délai de remboursement non appliqué (Q2), filtre Booking sans `PARTIALLY_REFUNDED` (R5), fixture
`booking/tests::test_resource` cassée depuis le 30/06 (`Resource.product` obligatoire).

---

## Comment tester (a la main) / Manual test

### Test 1 — billet par billet, sans panier
1. Réserver 3 billets payants depuis la page d'un événement (parcours direct), payer avec
   la carte de test `4242 4242 4242 4242`.
2. Mon compte → Mes réservations : annuler les billets un par un.
3. À chaque billet : un remboursement dans le tableau de bord Stripe, une ligne −1 dans
   l'admin « Ventes », et le montant affiché sur la carte de réservation baisse.
4. Au 3e billet : la réservation disparaît de « Mes réservations » (statut `CANCELED`).

### Test 2 — même chose avec le panier
Même scénario en passant par le panier (ajouter les billets au panier, puis payer).

### Test 3 — vente admin en espèces
1. Admin → Réservations → Ajouter : 3 billets, paiement Espèces.
2. Annuler un billet (action « Cancel and refund » sur un seul billet) : un avoir de −1 dans
   « Ventes », pas −3. Puis annuler la réservation : un avoir de −2.
3. Sur un autre client du même tarif, annuler une réservation Stripe : la vente espèces du
   premier client ne reçoit **aucun** avoir.

### Tests automatiques / Automated tests
```bash
make test ARGS="tests/pytest/test_stripe_refund.py tests/pytest/test_mail_annulation_booking.py -q"
make test-stripe ARGS="tests/pytest/test_stripe_reel_remboursement.py -q"   # vrai Stripe, mode test
make e2e-stripe ARGS="tests/e2e/test_renouvellement_adhesion_recurrente.py -v"
```

### Vérifs DB / DB checks
```bash
docker exec -i lespass_django poetry run python /DjangoFiles/manage.py shell <<'EOF'
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import LigneArticle, Reservation
with tenant_context(Client.objects.get(schema_name="lespass")):
    resa = Reservation.objects.get(uuid__startswith="<8 premiers caractères>")
    for l in resa.lignearticles.order_by("datetime"):
        print(l.datetime, l.status, l.qty, l.amount, l.credit_note_for_id)
    print("total payé :", resa.total_paid())
EOF
```
Attendu : une ligne `REFUNDED` (Stripe) ou `CREDIT_NOTE` (hors Stripe) par billet annulé,
toutes rattachées à la réservation, et `total_paid()` qui baisse d'autant.

### Playwright
Pas de nouveau scénario E2E (hors périmètre). `test_renouvellement_adhesion_recurrente.py`
est rejoué après sa factorisation.
