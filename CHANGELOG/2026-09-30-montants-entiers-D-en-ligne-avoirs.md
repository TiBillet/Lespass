# Ventes en ligne, admin, API et avoirs écrivent leur vente (chantier 05, fiche D) / Online, admin, API sales and credit notes write their sale (worksite 05, sheet D)

**Date :** 2026-09-30
**Migration :** Non

## Resume / Summary
**Quoi / What :** les ventes payées en ligne par Stripe, les ventes sans Stripe (admin, API) et les avoirs passent par le service de vente (`BaseBillet/services_vente.py`). /
Online Stripe sales, sales without Stripe (admin, API) and credit notes go through the sale service.

**Pourquoi / Why :** chantier 05 « montants entiers » : toute vente écrit son argent en centimes entiers, une seule fois, dans une `Vente` chaînée. /
Worksite 05 "whole amounts": every sale writes its money once, in whole cents, in a chained `Vente`.

Sections ci-dessous : D-1a (les producteurs Stripe directs ouvrent la vente), D-1b (panier et renouvellement d'abonnement), D-1c-0 (tests Stripe sans ménage), D-1c-1 (montant encaissé), D-1c-2 (encaissement de la vente, écart d'encaissement). / Sections below: D-1a, D-1b, D-1c-0, D-1c-1, D-1c-2.

## D-1a — Les producteurs Stripe directs ouvrent leur vente / Direct Stripe producers open their sale

**Migration :** Non — **Chaînes i18n :** aucune nouvelle.

### Resume / Summary
**Quoi / What :** quand un producteur Stripe direct crée ses lignes et son paiement Stripe, il ouvre d'abord une `Vente` (nature `VENTE`, origine = celle de ses lignes, client = l'acheteur). Ses lignes sont écrites par `ajouter_article` dans cette vente, sous la même forme qu'avant (prix unitaire, quantité, moyen, statut, origine, réservation / adhésion / booking, code promo) ; la TVA passée est celle de `_taux_tva_de_la_ligne_de_caisse` (produit, sinon lieu). La vente est rangée dans `Paiement_stripe.vente`, dans l'INSERT du paiement (`CreationPaiementStripe(vente=...)`). Elle reste `EN_ATTENTE`, sans numéro ni règlement : son encaissement viendra au point d'encaissement unique (D-1c). Un paiement abandonné ou expiré laisse sa vente `EN_ATTENTE`. /
A direct Stripe producer opens a `Vente` before its lines; lines are written by `ajouter_article` in the same shape; the sale is stored in `Paiement_stripe.vente` in the payment INSERT; it stays PENDING, without number or payment.

Producteurs : billets hors panier (`TicketCreator`, front et API v2), adhésion en ligne et lien de paiement d'une adhésion validée (même fonction `MembershipValidator.get_checkout_stripe` : chaque lien ouvre une nouvelle vente), réservation de ressource hors panier (`validate_new_booking`), contribution crowds à une initiative. /
Producers: tickets without cart, online membership and membership payment link, resource booking without cart, crowds contribution.

Voie gratuite (total 0, pas de Stripe) : la vente est quand même ouverte avant la ligne et reste `EN_ATTENTE` ; l'encaissement à 0 viendra avec les ventes sans Stripe (D-2). /
Free path: the sale is opened too and stays PENDING until D-2.

Hors de cette section : panier et abonnement (D-1b), point d'encaissement (D-1c), réservation par l'API v1 et financement global des crowds (sortis du chantier, sessions dédiées). /
Out of this section: cart and subscription (D-1b), settlement point (D-1c), API v1 reservation and crowds global funding (dedicated sessions).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `PaiementStripe/views.py` | `CreationPaiementStripe` reçoit `vente=None` et la pose dans l'INSERT du paiement |
| `BaseBillet/validators.py` | `TicketCreator(vente=None)` : ouvre sa vente avant la première ligne Stripe (`create_checkout=True`), ou reçoit celle de l'appelant ; panier sans vente, inchangé. `MembershipValidator.get_checkout_stripe` : une vente par appel |
| `booking/booking_engine.py` | `validate_new_booking(vente=None)` : vente ouverte avant la ligne, dans la transaction ; `get_checkout_stripe(booking, vente=None)` |
| `crowds/views.py` | `InitiativeViewSet.contribute` : vente ouverte avant la ligne de contribution |
| `tests/pytest/test_en_ligne_ecrit_la_vente.py` | Nouveau : 7 tests (6 producteurs + réservation gratuite) et le témoin « panier non touché » |

## D-1b — Le panier : une seule vente ; le renouvellement d'abonnement au prix unitaire / Cart: one single sale; subscription renewal at the unit price

**Migration :** Non — **Chaînes i18n :** aucune nouvelle.

### Resume / Summary
**Quoi / What :**
- **Panier** : `CommandeService.materialiser` ouvre UNE vente pour toute la commande (nature `VENTE`, origine en ligne `LP`, client = l'acheteur), dans sa transaction, et la pose dans l'INSERT de la `Commande` (`Commande.vente`). Il la passe à chaque producteur : les adhésions sont écrites par `ajouter_article`, `TicketCreator` (un appel par code promo, un par article à prix libre) et `validate_new_booking` reçoivent `vente=`. Le paiement Stripe de la commande porte la même vente (`CreationPaiementStripe(vente=...)`). Le total de la commande (choix Stripe ou gratuit, garde des 0,50 €) est la somme des `total_catalogue` des articles. Une commande à 0 € ouvre aussi sa vente, qui reste `EN_ATTENTE` (encaissement à 0 en D-2). /
  The cart opens ONE sale for the whole order, sets it on the `Commande`, passes it to every producer and to the Stripe payment. The order total is the sum of the items' `total_catalogue`. A 0 € order keeps its sale PENDING.
- **Renouvellement d'abonnement** (`new_entry_from_stripe_subscription_invoice`) : la ligne de l'échéance est écrite dans une vente ouverte avec elle (origine `WK`, client = l'abonné), par `ajouter_article`. Prix unitaire = `line.pricing.unit_amount_decimal` (texte en centimes, version d'API Stripe « basil »), arrondi au centime demi-haut ; quantité = `line.quantity`. Avant, `amount` recevait le TOTAL de la ligne de facture et `qty` la quantité : une échéance de quantité 2 comptait double. Sans prix unitaire (`pricing` absent), l'article vaut la ligne entière (total, quantité 1) et un avertissement est journalisé. Le `PriceSold` de l'échéance est au prix unitaire. Le paiement de l'échéance porte la vente ; elle reste `EN_ATTENTE` (encaissement par la branche `INVOICE` en D-1c). /
  The instalment line is written in its own sale, at Stripe's unit price (`pricing.unit_amount_decimal`, rounded half-up) and the invoice quantity: no more double count when quantity > 1. Without a unit price, the item is the whole line, quantity 1, with a warning.

**Pourquoi / Why :** un paiement Stripe = une vente (R5) ; règle d'or : le montant d'une vente est écrit une fois, en centimes entiers, et relu tel quel. / One Stripe payment = one sale; the amount is written once and read back as is.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/services_commande.py` | Vente ouverte avec la `Commande` et posée dessus ; adhésions par `ajouter_article` ; vente passée à `TicketCreator`, `validate_new_booking` et `CreationPaiementStripe` ; `total_centimes` = Σ `total_catalogue` |
| `PaiementStripe/views.py` | `new_entry_from_stripe_subscription_invoice` : vente de l'échéance, prix unitaire Stripe (`pricing.unit_amount_decimal`), repli « ligne entière » ; docstring de `CreationPaiementStripe(vente=)` |
| `BaseBillet/models.py` | Commentaire de `Commande.vente` : ouverte avec la commande, encaissée au paiement |
| `BaseBillet/validators.py`, `booking/booking_engine.py` | Commentaires seulement (aucun changement de comportement) : la branche « vente absente » de `TicketCreator` et de `validate_new_booking` ne sert plus à aucun chemin de production (le producteur direct ouvre sa vente, le panier passe la sienne) ; gardée pour les appels sans vente (tests), retirée en fiche H |
| `tests/pytest/test_en_ligne_ecrit_la_vente.py` | 6 tests ajoutés (panier : 3 ; abonnement : 3) ; le témoin « panier non touché » est retiré (son assertion est inversée par `test_panier_billets_booking_adhesion_une_seule_vente`) |

## D-1c-0 — Tests Stripe : plus de ménage, les événements sont archivés (tests seulement) / Stripe tests: no cleanup, events are archived (tests only)

### Resume / Summary
**Quoi / What :** les tests Stripe ne suppriment plus leurs données (lignes, paiements, réservations, commandes, avoirs, produits, tarifs, événements). Elles restent en base de dev, qui peut grossir. Seuls les événements créés sont archivés (`Event.archived = True`) après chaque test, par la fixture automatique `_archiver_les_evenements_crees` (`tests/pytest/conftest.py`), pour ne pas remplir l'agenda du lieu lespass. /
Stripe tests no longer delete their data; it stays in the dev DB. Only the events they create are archived after each test, to keep the lespass agenda clean.

**Pourquoi / Why :** un paiement encaissé scelle sa vente, et `Reglement.paiement_stripe` est en `PROTECT` : les suppressions de fin de test lèveraient `ProtectedError`. Chaque test crée ses propres données (noms et emails uniques), compte par écart et ne lit aucun rapport du lieu entier : il ne dépend d'aucun état propre. /
A captured payment seals its sale and `Reglement.paiement_stripe` is `PROTECT`: end-of-test deletions would raise `ProtectedError`. Each test creates its own data and depends on no clean state.

Refactoring interne, tests seulement, aucun code de production. / Internal refactoring, tests only, no production code.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/pytest/fabriques_reservation.py` | `nettoyer_evenements_crees` et `nettoyer_vente_admin` retirées ; `archiver_evenements_crees()` archive les événements de `EVENEMENTS_A_ARCHIVER` ; garde « vitale » retirée |
| `tests/pytest/conftest.py` | fixture automatique de suppression remplacée par `_archiver_les_evenements_crees` |
| `tests/pytest/test_stripe_refund.py` | tous les `try/finally` de ménage retirés |
| `tests/pytest/test_stripe_reservation.py` | les événements créés par l'aide du fichier sont archivés en fin de test |
| `tests/pytest/test_stripe_crowds.py` | la ligne comptable lue est celle de la contribution du test (`contrib.ligne_article`), plus la dernière ligne de 15 € du lieu |
| `test_stripe_membership_*.py`, `test_membership_sepa_payment_link.py` | aucun ménage, noms et emails déjà uniques : inchangés |

## D-1c-1 — Le montant encaissé par Stripe est rangé sur le paiement / The amount collected by Stripe is stored on the payment

**Migration :** Non (`Paiement_stripe.montant_encaisse` existe depuis la fiche A) — **Chaînes i18n :** aucune nouvelle.

### Resume / Summary
**Quoi / What :** quand Stripe confirme un paiement, le montant qu'il annonce, en centimes, est rangé dans `Paiement_stripe.montant_encaisse`, **avant** le `save()` qui passe le paiement à `PAID`, par les deux seuls chemins vivants qui constatent le paiement :
- `Paiement_stripe.update_checkout_status` (retour navigateur et webhook de checkout) : `checkout_session.amount_total` ;
- branche `INVOICE` de `paiment_stripe_validator` (webhook `invoice.paid`, échéance d'abonnement) : `invoice.amount_paid`. Une facture payée par le solde du client vaut 0 (un montant, pas « vide »).
Rien d'autre ne change : aucun encaissement de la vente ici (point d'encaissement : D-1c-2). /
When Stripe confirms a payment, the amount it announces (cents) is stored in `Paiement_stripe.montant_encaisse` before the save() that moves it to PAID, by both live paths: checkout (`amount_total`) and the `INVOICE` branch (`amount_paid`, 0 when paid by the customer balance). Nothing else changes.

**Pourquoi / Why :** le règlement Stripe de la vente sera écrit au montant **renvoyé par Stripe**, jamais recalculé depuis le catalogue ; un écart entre les deux devient un écart d'encaissement (D26). / The Stripe payment of the sale is written at the amount returned by Stripe, never recomputed from the catalogue.

**Tests : la fixture `mock_stripe`** (`tests/pytest/conftest.py`). `session.amount_total` n'est plus un `MagicMock` (`int(MagicMock())` vaut 1, sans erreur) : il est calculé au moment où on le lit, somme des `total_catalogue` des articles de la vente du `Paiement_stripe` le plus récent qui porte l'id de la session simulée (0 sans paiement ou sans vente). `stripe.Invoice.retrieve` est simulé aussi (`mock_stripe.facture`, payée, `amount_paid` calculé de la même façon pour le paiement qui porte l'id de facture). Un test d'écart impose sa valeur par affectation : `mock_stripe.session.amount_total = 2400`, `mock_stripe.facture.amount_paid = 0`. /
The `mock_stripe` fixture computes Stripe amounts from the payment's sale when read, simulates `stripe.Invoice.retrieve`, and lets a test impose a value by plain assignment.

**Deux fausses factures complétées** (décision du mainteneur) : celles du renouvellement d'abonnement dans `test_caracterisation_en_ligne.py` (P15) et `test_vente_modeles.py` reçoivent `amount_paid=1500`, le montant qu'elles simulent déjà. Une vraie facture Stripe porte toujours `amount_paid`, maintenant lu par la branche `INVOICE` ; aucune assertion n'est modifiée. /
Two fake invoices get `amount_paid=1500` (the amount they already simulate): a real Stripe invoice always carries it, and the `INVOICE` branch now reads it. No assertion changed.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `update_checkout_status` : `montant_encaisse = checkout_session.amount_total` dans la branche « payé », avant le `save()` final |
| `ApiBillet/views.py` | `paiment_stripe_validator`, branche `INVOICE` : `montant_encaisse = invoice.amount_paid` avant le `save()` |
| `tests/pytest/conftest.py` | fixture `mock_stripe` : montants calculés à la lecture, `Invoice.retrieve` simulé, valeur imposable par affectation |
| `tests/pytest/test_en_ligne_ecrit_la_vente.py` | 5 tests : la fixture (session, facture), montant du checkout, montant de la facture, facture à 0 |
| `tests/pytest/test_caracterisation_en_ligne.py`, `tests/pytest/test_vente_modeles.py` | fausse facture complétée avec `amount_paid=1500` (donnée de simulation seulement) |

## D-1c-2 — Le paiement Stripe encaisse sa vente ; écart d'encaissement / The Stripe payment settles its sale; collection gap

**Migration :** Non (les produits et catégories « Écart d'encaissement » sont des lignes créées à la demande) — **Chaînes i18n :** aucune nouvelle (les noms des produits d'écart sont des données en base, pas des `_()` ; les messages du journal ne sont pas traduits).

### Resume / Summary
**Quoi / What :**
- **Point d'encaissement unique** : à la fin de `set_ligne_article_paid` (transitions `PENDING → PAID`, `EXPIRE → PAID`, `PAID → PAID` du `pre_save` de `Paiement_stripe`), après le passage des lignes et des réservations en payé, `encaisser_vente_stripe(paiement)` encaisse la vente d'origine : verrou du lieu, vente relue sous verrou ; déjà `REGLEE` → rien n'est écrit (rejeu) ; `ANNULEE`, montant encaissé vide, moyen vide → `ValueError` ; UN règlement au moyen du paiement (`Paiement_stripe.moyen`) et au montant encaissé (`montant_encaisse`, lu sur l'objet reçu), aucun si le montant vaut 0 ; `encaisser_vente` en dernier. Un paiement sans vente (antérieur au chantier) n'encaisse rien (journal INFO). /
  At the end of the PAID transition, `encaisser_vente_stripe` settles the original sale: one payment at the collected amount and the payment's method (none at 0), idempotent, explicit errors for a cancelled sale or an empty amount / method.
- **Écart d'encaissement** (D26) : si le montant encaissé diffère de la somme des articles, un article « Écart d'encaissement — reçu en plus » (quantité +1) ou « — reçu en moins » (quantité −1) est ajouté : prix unitaire = |écart|, TVA 0, hors chiffre d'affaires, ligne `VALID` sans paiement Stripe (elle ne bloque pas le passage du paiement à `VALID`, n'est jamais envoyée à l'ancien LaBoutik). Les deux produits système (non publiés, tarif 0) et leurs catégories du même nom sont créés à la demande. Alerte au journal (ERROR). /
  A gap between Stripe's amount and the catalogue becomes a "collection gap" item (±1 × |gap|, VAT 0, off revenue, VALID, no Stripe payment), with an ERROR log.
- **T4** : l'appel est dans un `try / except` : aucune exception ne sort du `pre_save`. Le client est payé, ses billets partent ; la vente reste `EN_ATTENTE` et l'erreur est journalisée (ERROR). Rejeu : rappeler `encaisser_vente_stripe(paiement)` (le paiement est déjà `VALID`, un `save()` ne rejouerait rien). /
  No exception leaves the pre_save; replay by calling the function again.
- **Stripe dit non** : `PENDING → CANCELED` (aucun paiement requis) appelle `annuler_la_vente_du_paiement_stripe` → vente `ANNULEE` (si `EN_ATTENTE`) ; prélèvement SEPA refusé (`checkout.session.async_payment_failed`) : `annuler_vente` explicite après le passage à `FAILED` (T5). Une session expirée ne change rien : la vente reste `EN_ATTENTE`, sans numéro, et un paiement tardif l'encaisse (T6). /
  CANCELED and a refused SEPA debit cancel the pending sale; an expired session changes nothing.

**Pourquoi / Why :** un paiement Stripe = une vente, encaissée à l'argent réellement reçu (R5, D26) ; le client payé ne doit jamais être bloqué par la comptabilité. / One Stripe payment = one sale, settled at the money really received; a paid customer is never blocked by accounting.

**Test à vrai Stripe** (`tests/pytest/test_stripe_reel_remboursement.py`, accord du mainteneur) : plus de ménage en fin de test (`nettoyer_paiement` retirée, avec sa fonction dans `fabriques_reservation.py`) : un paiement encaissé scelle sa vente, supprimer ses lignes lèverait `ProtectedError`. Ses données restent en base de dev ; seuls les événements créés sont archivés (fixture de `conftest.py`). / Real-Stripe test: no more end-of-test cleanup (a settled payment seals its sale); data stays in the dev DB, created events are archived.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/services_vente.py` | `logger` ; constantes `NOM_ECART_RECU_EN_PLUS` / `NOM_ECART_RECU_EN_MOINS` ; `tarif_vendu_d_ecart_d_encaissement` ; `encaisser_vente_stripe` |
| `BaseBillet/signals.py` | fin de `set_ligne_article_paid` : `encaisser_vente_stripe` dans un `try` ; `PENDING → CANCELED` → `annuler_la_vente_du_paiement_stripe` ; commentaire d'`expire_paiement_stripe` |
| `ApiBillet/views.py` | branche `async_payment_failed` : `annuler_vente` de la vente en attente |
| `tests/pytest/test_stripe_reel_remboursement.py`, `tests/pytest/fabriques_reservation.py` | `try / finally` + `nettoyer_paiement` retirés (aucune assertion changée) ; fonction `nettoyer_paiement` supprimée |
| `tests/pytest/test_en_ligne_ecrit_la_vente.py` | 18 tests : fiche 2, 3, 4, 4b, 4c, 6, 7, 8, 9, 10 (encaissement) ; T4 ×2 ; T5 ; T6 ; paiement sans vente ; montant vide ; montant posé avant le `save()` ; vente annulée puis payée ; moyen vide |

---

## Comment tester (a la main) / Manual test

### Test 1 — billets hors panier
1. Sur `https://lespass.tibillet.localhost/`, réserver deux billets payants d'un événement sans passer par le panier (« Payer maintenant »), ne PAS payer chez Stripe.
2. Dans `manage.py shell` (tenant lespass) :
   ```python
   from BaseBillet.models import Paiement_stripe
   p = Paiement_stripe.objects.order_by("-order_date").first()
   v = p.vente
   print(v.statut, v.numero, v.origine, v.client, v.reglements.count())
   print([(a.amount, a.qty, a.total_catalogue, a.vat) for a in v.articles.all()])
   ```
3. Attendu : `EN_ATTENTE None LP <acheteur> 0`, et les articles = les lignes du paiement, `total_catalogue` = prix × quantité en centimes.

### Test 2 — lien de paiement d'une adhésion
1. Valider une adhésion à validation manuelle dans l'admin, ouvrir le lien reçu, ne pas payer.
2. Attendre l'expiration de la session Stripe, rouvrir le lien.
3. Attendu : deux paiements, deux ventes distinctes ; la première reste `EN_ATTENTE`, sans numéro.

### Test 3 — réservation gratuite
1. Réserver un billet d'un tarif à 0 € (catégorie billet payant), sans panier.
2. Attendu : aucun paiement Stripe ; une vente `EN_ATTENTE` dont l'article est la ligne du billet (0 centime).

### Test 4 (D-1b) — panier mixte, une seule vente
1. Mettre dans le panier une adhésion, deux billets de deux événements et un créneau de ressource ; payer le panier, ne PAS payer chez Stripe.
2. Dans `manage.py shell` (tenant lespass) :
   ```python
   from BaseBillet.models import Commande
   c = Commande.objects.order_by("-created_at").first()
   v = c.vente
   print(v.statut, v.numero, v.origine, v.client, v.reglements.count(), c.paiement_stripe.vente_id == v.pk)
   print([(a.amount, a.qty, a.total_catalogue) for a in v.articles.all()])
   ```
3. Attendu : `EN_ATTENTE None LP <acheteur> 0 True` ; les articles sont TOUTES les lignes de la commande (adhésion, billets, booking).

### Test 5 (D-1b) — panier gratuit
1. Panier avec un billet à 0 € et une adhésion à 0 €, valider.
2. Attendu : aucun paiement Stripe ; `Commande.vente` posée, `EN_ATTENTE`, sans numéro, deux articles à 0.

### Test 6 (D-1b) — renouvellement d'abonnement
Pas de test manuel simple (il faut une échéance Stripe réelle). Couvert par les tests automatiques `test_abonnement_*` : quantité 2 au prix unitaire, prix unitaire décimal arrondi demi-haut, ligne sans `pricing` écrite au total, quantité 1.

### Verifs automatiques
`make test ARGS="tests/pytest/test_en_ligne_ecrit_la_vente.py"`

### Test 7 (D-1c-0) — l'agenda ne grossit pas
1. Compter les événements visibles de l'agenda de `lespass`, lancer `make test ARGS="tests/pytest/test_stripe_refund.py"`, recompter.
2. Attendu : le nombre d'événements visibles ne change pas ; le nombre total d'événements augmente (ils sont archivés).

### Test 8 (D-1c-1) — le montant encaissé
1. Sur `https://lespass.tibillet.localhost/`, réserver un billet payant sans panier et le payer avec la carte de test Stripe.
2. Dans `manage.py shell` (tenant lespass) :
   ```python
   from BaseBillet.models import Paiement_stripe
   p = Paiement_stripe.objects.order_by("-order_date").first()
   print(p.status, p.montant_encaisse, sum(a.total_catalogue for a in p.vente.articles.all()))
   ```
3. Attendu : statut `V` (ou `P`), `montant_encaisse` = le montant payé chez Stripe, en centimes (égal au total catalogue sans remise Stripe).
4. Renouvellement d'abonnement : pas de test manuel simple ; couvert par `test_facture_payee_*` (montant de la facture, facture à 0).

### Test 9 (D-1c-2) — la vente est encaissée au paiement
1. Sur `https://lespass.tibillet.localhost/`, réserver un billet payant sans panier et le payer avec la carte de test Stripe.
2. Dans `manage.py shell` (tenant lespass) :
   ```python
   from BaseBillet.models import Paiement_stripe
   p = Paiement_stripe.objects.order_by("-order_date").first()
   v = p.vente
   print(p.status, v.statut, v.numero, [(r.moyen, r.montant) for r in v.reglements.all()])
   ```
3. Attendu : `V REGLEE <numéro>` et un seul règlement `('SN', <montant payé en centimes>)`.
4. Abandonner un autre checkout (ne pas payer) : sa vente reste `EN_ATTENTE`, sans numéro.
5. Écart d'encaissement : pas de test manuel simple (Stripe encaisse le montant demandé) ; couvert par `test_montant_stripe_*` et `test_facture_payee_par_le_solde_client_montant_zero`.
