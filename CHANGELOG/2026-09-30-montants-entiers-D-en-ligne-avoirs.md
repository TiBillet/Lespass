# Ventes en ligne, admin, API et avoirs écrivent leur vente (chantier 05, fiche D) / Online, admin, API sales and credit notes write their sale (worksite 05, sheet D)

**Date :** 2026-09-30
**Migration :** Non

## Resume / Summary
**Quoi / What :** les ventes payées en ligne par Stripe, les ventes sans Stripe (admin, API) et les avoirs passent par le service de vente (`BaseBillet/services_vente.py`). /
Online Stripe sales, sales without Stripe (admin, API) and credit notes go through the sale service.

**Pourquoi / Why :** chantier 05 « montants entiers » : toute vente écrit son argent en centimes entiers, une seule fois, dans une `Vente` chaînée. /
Worksite 05 "whole amounts": every sale writes its money once, in whole cents, in a chained `Vente`.

Sections ci-dessous : D-1a (les producteurs Stripe directs ouvrent la vente), D-1b (panier et renouvellement d'abonnement), D-1c-0 (tests Stripe sans ménage), D-1c-1 (montant encaissé), D-1c-2 (encaissement de la vente, écart d'encaissement), D-1c-3 (tests du rapport comptable), D-2a (voies gratuites encaissées à 0), D-2b (ventes faites dans l'admin), D-2c (API et ancienne caisse), D-3a (avoir admin et écran « Remboursé par »), D-1z (corrections de la relecture de D-1 et D-2), D-3b (le remboursement Stripe écrit sa vente AVOIR). / Sections below: D-1a, D-1b, D-1c-0, D-1c-1, D-1c-2, D-1c-3, D-2a, D-2b, D-2c, D-3a, D-1z, D-3b.

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

## D-1c-3 — Les tests du rapport comptable tournent dans un lieu dédié (tests seulement) / Accounting report tests run in a dedicated venue (tests only)

### Resume / Summary
**Quoi / What :** `tests/pytest/test_comptabilite_service.py` passe en schéma dédié (`FastTenantTestCase`, schéma `test_comptabilite_service`). Mêmes scénarios, mêmes assertions ; les totaux se vérifient à l'égalité au lieu d'un « avant / après ». Chaque test annule sa transaction : les `.delete()` de fin de test et le contournement des `post_delete` d'`Event` disparaissent, plus rien n'arrive dans la base de dev. / Same scenarios, same assertions; totals are now exact; each test rolls back.

**Pourquoi / Why :** le service lit le lieu entier sur 5 minutes. Les avoirs laissés en base de dev par `test_stripe_refund.py` faussaient `test_calculer_remboursements_status_negatifs` (`-18500 == -500`). / The service reads the whole venue over 5 minutes; credit notes left by the Stripe refund tests skewed a total.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `tests/pytest/test_comptabilite_service.py` | 17 tests en classe `FastTenantTestCase` ; assertions exactes (ensemble des lignes du queryset, totaux par moyen, total d'adhésion, total de billet, un seul article par catégorie) |

---

## D-2a — Les voies gratuites : la vente est encaissée à 0 / Free paths: the sale is settled at 0

**Migration :** Non — **Chaînes i18n :** deux nouvelles (msgid français, `api_v2/serializers.py`) : « La quantité de billets doit être un nombre entier. » et « Le prix d'un billet doit être un montant positif en euros. ». Le workflow i18n est à lancer par le mainteneur.

### Resume / Summary
**Quoi / What :**
- **Une vente gratuite est encaissée à 0** : `encaisser_vente(vente)` sans règlement (total 0). Elle est `REGLEE` et numérotée : c'est une opération enregistrée. Elle est encaissée par l'appelant qui écrit la DERNIÈRE ligne, jamais avant (une vente encaissée ne reçoit plus d'article). /
  A free sale is settled at 0 (REGLEE, numbered, no payment) by the caller that writes the LAST line.
- **Réservation à 0 € du front** : `TicketCreator.valider_une_reservation_a_zero_euro` encaisse après les lignes et le statut gratuit. Nouveau paramètre `TicketCreator(encaisser_la_vente_gratuite=True)` ; `ReservationValidator` le lit dans son contexte (`encaisser_la_vente_gratuite`, `True` par défaut). /
  Front 0 € reservation: settled by `TicketCreator`, unless the caller passes `encaisser_la_vente_gratuite=False`.
- **Réservation gratuite de l'API v2** : l'API passe `encaisser_la_vente_gratuite=False`. Ses lignes « réservation gratuite » (FREERES) sont écrites par `ajouter_article` dans la MÊME vente que `TicketCreator` (sinon une vente ouverte par l'API, origine API, juste avant la première ligne), TVA par `_taux_tva_de_la_ligne_de_caisse` (FREE → 0), puis l'API encaisse. Un `price` non nul sur une réservation gratuite suit la règle « offert à montant non nul » : part offerte totale (OFFRIR) et règlement FREE du même montant. /
  API v2: its free-booking lines go into the same sale, then the API settles it; a non-zero price is fully offered with a FREE payment.
- **API v2, contrôle des billets demandés** (avant `ReservationValidator`) : la quantité (`ticketQuantity`) est convertie en entier (`"2"` → 2), bornée par `QUANTITE_MAXIMUM_PAR_TARIF` avant `int()` ; une quantité non entière (`"2.5"`) est refusée avec une erreur claire, et rien n'est créé (avant, `ReservationValidator` en faisait 2 billets et la ligne gardait 2,5). Le `price` (texte en euros, `openapi-schema.yaml`) devient un `Decimal` ; un texte qui n'est pas un montant entre 0 et 999 999,99 est refusé (avant : erreur 500 `'str' object has no attribute 'quantize'` dans `dround`). /
  API v2: the quantity is cast to an int, a decimal quantity is refused; the price text becomes a Decimal, an invalid one is refused (it used to crash).
- **Booking gratuit** (`validate_new_booking`, branche gratuite) : encaissé après le passage de sa ligne en `VALID` / FREE. /
  Free booking: settled after its line.
- **Panier gratuit** (`CommandeService._finaliser_gratuit`) : encaissé après le passage de toutes les lignes ; une vente sans article (panier de réservations gratuites seules) est ANNULEE, sans numéro. /
  Free cart: settled after all lines; an empty sale (free bookings only) is cancelled.
- **Pas de vente sans ligne** : une réservation gratuite seule, hors panier, n'ouvre toujours aucune vente (test témoin). **T16** (accepté) : une réservation à 0 € annulée après coup (place perdue en attendant la confirmation du mail) garde sa vente `REGLEE` à 0. /
  No sale without a line; a 0 € reservation cancelled afterwards keeps its settled sale (accepted, T16).

**Pourquoi / Why :** fiche D §3 (« Gratuit : total 0, aucun règlement, vente numérotée »), décisions D-2 du SUIVI (a, b, g, h). Hors session : la branche « payé en caisse » de l'API v2 (`paid_externally`, D-2c). / Sheet D §3 and the D-2 decisions; the API "paid at the POS" branch stays for D-2c.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/validators.py` | `TicketCreator(encaisser_la_vente_gratuite=True)` ; `valider_une_reservation_a_zero_euro` encaisse la vente ; `ReservationValidator` passe le paramètre lu dans son contexte |
| `api_v2/serializers.py` | `ReservationCreateSerializer.create` : quantité entière et prix `Decimal` contrôlés avant le validateur ; contexte `encaisser_la_vente_gratuite=False` ; lignes FREERES par `ajouter_article` dans la vente de `TicketCreator` (ou une vente API) ; encaissement final |
| `booking/booking_engine.py` | branche gratuite de `validate_new_booking` : `encaisser_vente(vente)` après la ligne |
| `BaseBillet/services_commande.py` | `_finaliser_gratuit` : encaisse la vente de la commande, ou l'annule si elle n'a aucun article ; commentaires de `materialiser` |
| `tests/pytest/test_en_ligne_ecrit_la_vente.py` | les deux témoins D-1 changent de sens et de nom (`…_vente_encaissee_a_zero`) ; 9 tests : témoin FREERES seule (vert attendu), T16, booking gratuit, fiche 14 (deux ordres de produits), fiche 15 en deux (texte `"2"`, décimale `"2.5"`), FREERES API à prix non nul offerte, panier FREERES seules annulé |

## D-2b — Les ventes faites dans l'admin écrivent leur vente, encaissée / Admin sales write their sale, settled

**Migration :** Non — **Chaînes i18n :** une nouvelle (msgid français, `Administration/admin_tenant.py`, `MembershipAddForm.clean`) : « Choisissez un moyen de paiement pour la contribution. ». Le workflow i18n est à lancer par le mainteneur.

### Resume / Summary
**Quoi / What :**
- **Billets vendus dans l'admin** (`ReservationAddAdmin.save`) : une vente `ADMIN` (client = l'acheteur, opérateur vide), la ligne par `ajouter_article` (TVA par `_taux_tva_de_la_ligne_de_caisse`), UN règlement au moyen choisi (espèces, CB, chèque, virement) du montant total, puis `encaisser_vente`, avant le mail des billets, dans la transaction de l'admin. Une réservation gratuite (FREERES, 0 €) donne une vente encaissée à 0, sans règlement. /
  Tickets sold in the admin: one ADMIN sale, one payment at the chosen method, settled before the tickets mail.
- **Billet offert dans l'admin (D32, T12)** : écrit comme un offert de la caisse : au prix du tarif (avant : 0), part offerte = total, source OFFRIR, un règlement FREE du même montant (posé par le service). /
  Offered ticket: written at the rate's price, fully offered, with a FREE payment (it used to be 0).
- **Billets vendus dans l'admin : plus d'envoi à l'ancienne caisse LaBoutik V1** (décision du mainteneur, tous les billets admin) : `send_sale_to_laboutik.delay` est retiré ; le mail des billets reste. /
  Tickets sold in the admin are no longer sent to the legacy LaBoutik V1 register.
- **Paiement d'adhésion dans l'admin** (`MembershipMVT.ajouter_paiement`) : adhésion, vente `ADMIN` (client = l'adhérent), ligne, règlement au moyen choisi et encaissement dans UNE transaction. La ligne passe `PAID` (déclencheur `trigger_A`), PUIS la vente est encaissée, même si `trigger_A` échoue (la ligne reste alors `PAID` : l'argent est déclaré reçu). Limite acceptée : une erreur SQL dans `trigger_A` annule tout (rien n'est perdu, le paiement est à refaire). /
  Membership payment in the admin: one transaction; trigger first, then settle, even if the trigger fails.
- **Adhésion créée ou renouvelée dans l'admin** (signal `create_lignearticle_if_membership_created_on_admin`) : même forme (vente `ADMIN`, client = l'adhérent, ligne par le service, `PAID` puis encaissement) ; règlement au moyen de l'adhésion ; une adhésion offerte (0) donne une vente à 0, sans règlement. /
  Membership created or renewed in the admin: same shape; an offered membership is a sale at 0.
- **Formulaire d'ajout d'adhésion** (`MembershipAddForm.clean`) : une contribution > 0 sans moyen de paiement est refusée (avant : acceptée, la ligne gardait un moyen vide). /
  The add form refuses a contribution without payment method.

**Pourquoi / Why :** fiche D §3 (lignes admin), §5 test 11, trous T12 (D32) et T15 ; décisions D-2 du SUIVI (e, f, g, i, k). Tests existants changés : le test A′ `test_billets_vendus_dans_l_admin_offert_montant_zero` devient `…_offert_au_prix_part_offerte_totale` (D32, liste fermée A′ §4 ; tâches attendues : le mail des billets seulement) ; dans `tests/pytest/test_admin_reservation_add.py`, les deux `assert_called_once()` sur `send_sale_to_laboutik` deviennent `assert_not_called()`, pour la seule raison de l'arrêt de l'envoi à LaBoutik V1. /
  Sheet D §3, test 11, gaps T12 and T15. The A′ test is renamed (D32); two assertions of the admin reservation test follow the end of the LaBoutik V1 sending.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | `ReservationAddAdmin.save` : vente `ADMIN` par le service, billet offert au prix (D32), un règlement au moyen choisi, encaissement avant le mail ; plus de `send_sale_to_laboutik` (l'import reste : les tests le patchent). `MembershipAddForm.clean` : contribution sans moyen refusée |
| `BaseBillet/views.py` | `MembershipMVT.ajouter_paiement` : tout dans un `atomic` ; vente `ADMIN`, ligne par `ajouter_article`, `PAID` (`trigger_A`), règlement, encaissement en dernier |
| `BaseBillet/signals.py` | `create_lignearticle_if_membership_created_on_admin` : vente `ADMIN`, ligne par le service, `PAID`, règlement (sauf 0), encaissement |
| `tests/pytest/test_admin_ecrit_la_vente.py` | nouveau : 10 tests (billets espèces / offert D32 / virement ; `ajouter_paiement` : ordre, déclencheur en échec, tout ou rien ; adhésion admin payée et offerte ; formulaire sans moyen refusé) |
| `tests/pytest/test_caracterisation_admin_api.py` | test A′ renommé `…_offert_au_prix_part_offerte_totale` : prix 1500, part offerte 3000, net 0 ; tâches : `ticket_celery_mailer` seulement |
| `tests/pytest/test_admin_reservation_add.py` | `send_sale_to_laboutik` : `assert_called_once()` → `assert_not_called()` (2 lignes, rien d'autre) |

## D-2c — API et ancienne caisse : adhésion gratuite, recharge cadeau, « payé ailleurs », webhook Fedow / API and legacy register: free membership, gift refill, "paid elsewhere", Fedow webhook

**Migration :** Non — **Chaînes i18n :** aucune nouvelle.

### Resume / Summary
**Quoi / What :**
- **Adhésion gratuite** (`MembershipValidator`, branche gratuite ; API v2 en mode « FREE », origine API, et front à 0 €, origine en ligne) : la ligne est l'article d'une vente ouverte avec elle (client = l'adhérent), écrite « offerte en totalité ». Montant non nul : part offerte = total, règlement FREE du même montant. Montant 0 : vente à 0. La vente est encaissée APRÈS le passage « payée » de la ligne (le déclencheur garde son rôle : e-mails, échéance, ligne VALID). /
  Free membership: one sale opened with the line, fully offered (FREE payment when non-zero), settled after the line's trigger.
- **Recharge cadeau de l'API v2** (`WalletRefillViewSet`) : la ligne `CREATED` naît dans une vente `EN_ATTENTE` (origine en ligne, client = le destinataire). Fedow répond : ligne `VALID`, vente encaissée (article hors chiffre d'affaires, offert en totalité, règlement FREE). Fedow échoue : ligne `FAILED`, la vente reste `EN_ATTENTE`, sans numéro ; le nouvel essai (même ligne) encaisse la MÊME vente. `Vente.unite` = l'uuid de la monnaie pour du temps ou des points (TIM, FID) ; une monnaie cadeau (TNF) garde `EUR`. L'anti double crédit reste le verrou de `LigneArticle.idempotency_key` (409). /
  API v2 gift refill: PENDING sale with the CREATED line; settled on success; stays PENDING on failure and the retry settles the same sale; unit = the currency only for time or points; the 409 lock is unchanged.
- **Billets « payés ailleurs » de l'API v2** (`paymentMethod` cash / card) : les lignes payées (`VALID`, origine LaBoutik) sont les articles d'UNE vente (client = la personne réservée), avec UN règlement au moyen déclaré (cash → CA, card → CC) du total net, puis encaissée par l'API. Une « réservation gratuite » du même appel n'écrit toujours aucune ligne (comportement gardé) : elle n'entre pas dans la vente. /
  API v2 "paid elsewhere": one sale, one payment at the declared method, settled by the API; free bookings of the same call still write no line.
- **Webhook Fedow d'adhésion** (`fedow_connect/views.py`, adhésion vendue par l'ancienne caisse) : la ligne (`VALID`, moyen inconnu, origine LaBoutik) est l'article d'une vente (client = l'adhérent, vide s'il est inconnu de Lespass), avec UN règlement `UNKNOWN` du montant, encaissée. Ligne, vente et encaissement dans un `atomic` ; le `try / except` et la tolérance aux rejeux restent. Limite acceptée : l'adhésion est créée avant ce bloc ; s'il échoue, elle reste sans ligne ni vente, et un rejeu (208) ne réécrit rien. /
  Fedow membership webhook: one sale, one UNKNOWN payment, settled, all or nothing; the membership is created before (accepted limit).

**Pourquoi / Why :** fiche D §3 (adhésion gratuite, recharge cadeau, webhook Fedow), §5 tests 13 et 16 ; SUIVI §4 « D-2 » (c, d, g) et §5 du 2026-10-01 (argent encaissé par l'ancienne caisse : une vente, règlement au moyen déclaré ; webhook encore utilisé). Aucun test existant modifié. /
  Sheet D §3, tests 13 and 16; maintainer decision of 2026-10-01 on money collected by the legacy register.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/validators.py` | adhésion gratuite : vente ouverte avec la ligne (`ajouter_article`, `offert_en_totalite`), encaissement après le `save()` qui lance le déclencheur ; `TicketCreator.method_B`, branche `paid_externally` : vente ouverte avant la première ligne, lignes par `ajouter_article` (TVA `_taux_tva_de_la_ligne_de_caisse`) |
| `api_v2/serializers.py` | `ReservationCreateSerializer.create`, « payé ailleurs » : un règlement au moyen déclaré (total net), puis `encaisser_vente`, avant le retour anticipé |
| `api_v2/views.py` | `WalletRefillViewSet` : `_creer_ligne_article_recharge` ouvre la vente (unité, client) et écrit l'article offert ; encaissement après le passage `VALID` |
| `fedow_connect/views.py` | `Membership_fwh.retrieve` : vente LaBoutik, ligne par le service, règlement `UNKNOWN`, encaissement, dans un `atomic` ; variable locale `transaction` renommée `transaction_fedow` (elle masquait `django.db.transaction`) |
| `tests/pytest/test_api_ecrit_la_vente.py` | nouveau : 12 fonctions de test, 14 cas (adhésion gratuite API et front ; recharge : échec puis nouvel essai, temps, cadeau, 409 ; payé ailleurs espèces / carte, avec réservation gratuite dans les deux ordres ; webhook : vente, rejeu, adhérent inconnu, encaissement en échec) |

## D-3a — L'avoir émis dans l'admin écrit sa vente ; écran « Remboursé par » / The admin credit note writes its sale; "Refunded by" screen

**Migration :** Non — **Chaînes i18n nouvelles (msgid FR) :** « Remboursé par », « Le moyen par lequel l'argent est rendu au client. », « Émettre un avoir », « Émettre l'avoir », « Annuler », « Remboursez cette somme depuis votre tableau de bord Stripe. », « Cet article a été offert : aucun argent n'est à rendre. », « La vente d'origine n'est pas réglée : l'avoir est impossible. », « L'avoir n'a pas pu être émis : %(raison)s ». Workflow i18n à lancer par le mainteneur.

### Resume / Summary
**Quoi / What :**
- **Nouvelle fonction du service** `ajouter_l_article_d_avoir(vente_avoir, ligne_d_origine, quantite)` : l'article miroir d'une ligne vendue, dans une vente AVOIR. Même tarif vendu, même prix unitaire, même TVA, quantité négative. Toute la quantité d'une ligne écrite par le service : total catalogue et part offerte recopiés en négatif, exactement (une « part » de caisse en cascade rend son total d'origine au centime). Ligne d'avant le chantier (total 0) : prix × −quantité. Quantité partielle d'une ligne avec une part offerte : refusée (« rembourser l'article entier »). Champs recopiés : `credit_note_for`, moyen historique, monnaie, portefeuille, carte, paiement Stripe, adhésion, réservation, booking, `metadata` (+ `original_lignearticle_uuid`), hors chiffre d'affaires ; statut `CREATED`. Aucun règlement (sauf le FREE de la règle « offert » du service). Elle servira aux producteurs de D-3b et D-3c. /
  New service function: the negative mirror item of a sold line, exact totals for a full return, partial return of an offered item refused, no payment written.
- **Bouton « Avoir » de la liste des ventes** (`LigneArticleAdmin.emettre_avoir`) : un GET affiche désormais un **écran** (il ne crée plus l'avoir en un clic), le POST l'écrit. Trois écrans : ligne hors Stripe → champ « Remboursé par » (espèces, CB, chèque, virement), pré-rempli avec le moyen d'origine s'il est dans la liste, sinon vide et obligatoire ; ligne entièrement offerte (part offerte = total, ou moyen historique « offert ») → simple confirmation ; ligne payée par Stripe → simple confirmation et rappel « Remboursez cette somme depuis votre tableau de bord Stripe. » (aucun appel à Stripe). Nouvelle garde : vente d'origine pas réglée → refus. /
  The "Credit note" button now opens a screen (GET) and writes on POST; three screens; new guard on an unsettled original sale.
- **L'avoir écrit sa vente**, dans une seule transaction : vente AVOIR (origine admin, liée à la vente de la ligne, vide pour une ligne d'avant le chantier, client de la vente liée), l'article par la fonction ci-dessus, UN règlement d'argent du net rendu (moyen choisi, ou moyen Stripe d'origine relié au paiement, sans référence externe), un règlement FREE négatif pour la part offerte (jamais deux fois), encaissement, PUIS la transition `CREDIT_NOTE` (envoi à l'ancien LaBoutik, inchangé). Après l'action, retour à la liste des ventes. /
  The credit note writes an AVOIR sale in one transaction: one money payment, one FREE payment for the offered part, settled, then CREDIT_NOTE.

**Pourquoi / Why :** fiche D §4 (avoir admin hors Stripe et Stripe), §5 tests 18, 18b, 18c, 19 ; SUIVI §4 « D-3 » et §5 du 2026-10-01 (décision D27 : écran « Remboursé par ») ; décisions techniques de l'orchestrateur à l'étape 2 (total recopié exactement, règlement Stripe relié au paiement, carte recopiée, « entièrement offerte » = montants ou moyen FREE). Tests existants : seul le mécanisme d'appel change (GET puis POST), aucune assertion. /
  Sheet D §4 and §5; decision D27. Existing tests: only the call mechanism changes.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/services_vente.py` | nouvelle fonction `ajouter_l_article_d_avoir` |
| `Administration/admin_tenant.py` | `MOYENS_DU_CHAMP_REMBOURSE_PAR`, `EmettreAvoirAvecMoyenForm`, `EmettreAvoirSansMoyenForm` ; `LigneArticleAdmin.emettre_avoir` réécrite (écran + vente AVOIR) ; import `render` |
| `Administration/templates/admin/lignearticle/emettre_avoir.html` | nouveau : l'écran « Émettre un avoir » |
| `tests/pytest/test_avoirs_ecrivent_la_vente.py` | nouveau : 12 tests (espèces au lieu de CB, pré-remplissage, champ vide refusé, ligne Stripe, billet offert, ligne ancienne offerte, part en jetons, part arrondie, avoir partiel refusé, ligne sans vente, échec d'encaissement, vente d'origine pas réglée) |
| `tests/pytest/test_caracterisation_annulations.py` | aide `emettre_un_avoir_depuis_l_admin` : GET de l'écran puis POST (paramètre `moyen_rembourse` optionnel) ; aucune assertion changée |
| `tests/pytest/test_caracterisation_en_ligne.py` | T13 : GET de l'écran puis POST ; aucune assertion changée |
| `tests/e2e/test_admin_credit_note.py` | passe par l'écran (vérifie l'absence du champ pour une ligne offerte, clique « Émettre l'avoir ») |

## D-1z — Corrections de la relecture de D-1 et D-2 / Fixes from the D-1 and D-2 review

**Migration :** Non — **Chaînes i18n :** aucune nouvelle.

### Resume / Summary
**Quoi / What :**
- **API v2, réservation « payée ailleurs » et réservation gratuite : tout ou rien.** `ReservationViewSet.create` écrit la réservation, les billets, les lignes, la vente, le règlement et l'encaissement dans une seule transaction. Si l'encaissement échoue, rien n'est écrit et l'erreur remonte (500, Sentry) : un nouvel envoi de la caisse ne crée plus une seconde réservation. Limites acceptées : (1) les tâches lancées sans `on_commit` par `reservation_paid` (`webhook_reservation`, `ticket_celery_mailer`, réservation gratuite d'un compte déjà actif) partent tout de suite ; après un échec, elles ne trouvent pas la réservation retirée et leur erreur part dans Sentry ; (2) le produit et le prix du catalogue Stripe créés par `get_or_create_price_sold` restent chez Stripe, orphelins (sans effet sur l'argent). /
  API v2 reservation: one transaction; a failed settlement writes nothing and returns a 500. Accepted limits: tasks sent without `on_commit` by `reservation_paid` leave at once (their error goes to Sentry); Stripe catalogue objects stay orphaned.
- **Paiement Stripe refusé (`PENDING → CANCELED`) : aucune exception ne sort du `pre_save`.** Un échec de l'annulation de la vente (vente devenue réglée entre-temps, erreur de base) est journalisé (Sentry) ; la vente reste telle quelle, le paiement passe `CANCELED`. Même règle que l'encaissement (T4). /
  Stripe CANCELED: a failed sale cancellation is logged, the payment still turns CANCELED.
- **Billets vendus dans l'admin** : le prix unitaire en centimes passe par `dec_to_int` (même calcul, une seule fonction). /
  Admin tickets: unit price in cents through `dec_to_int`.
- **Imports** : dans `BaseBillet/signals.py` (adhésion créée dans l'admin) et `LigneArticleAdmin.emettre_avoir`, les imports locaux montent en tête de module : aucun cycle d'import ne les justifiait (vérifié au démarrage de Django). Leur commentaire, faux, disparaît. /
  Local imports moved to module top: no import cycle; the wrong comment is gone.
- **Test** : la docstring de `test_billets_vendus_dans_l_admin_offert_au_prix_part_offerte_totale` ne raconte plus la session ; aucune assertion changée. /
  Test docstring no longer tells the session story.

**Pourquoi / Why :** relecture Fable de D-1 et D-2 (SUIVI §4, constats 1, 3, 4, 7, 8) ; le constat 2 (webhook Fedow) est gardé tel quel (mainteneur, SUIVI §5). /
Fable review of D-1 and D-2 (findings 1, 3, 4, 7, 8); finding 2 kept as is.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `api_v2/views.py` | `ReservationViewSet.create` : `transaction.atomic()` autour de `input_serializer.save()` |
| `BaseBillet/signals.py` | `annuler_la_vente_du_paiement_stripe` : `try / except` + `logger.error` ; imports du service de vente et de `_taux_tva_de_la_ligne_de_caisse` en tête de module |
| `Administration/admin_tenant.py` | `dec_to_int(prix_unitaire)` ; imports de `emettre_avoir` en tête de module |
| `tests/pytest/test_api_ecrit_la_vente.py` | 2 tests : « payé ailleurs » et réservation gratuite, encaissement en échec → 500, rien n'est écrit (par la vraie route) |
| `tests/pytest/test_en_ligne_ecrit_la_vente.py` | 1 test : `CANCELED` avec annulation en échec → pas d'exception, paiement `CANCELED`, erreur journalisée |
| `tests/pytest/test_caracterisation_admin_api.py` | docstring seulement |

## D-3b — Le remboursement Stripe écrit sa vente AVOIR, au montant renvoyé par Stripe / The Stripe refund writes its AVOIR sale, at the amount Stripe returns

**Migration :** Non — **Chaînes i18n :** aucune nouvelle.

### Resume / Summary
**Quoi / What :**
- **`partial_refund_payment` écrit une vente AVOIR par remboursement** (annulation d'un billet, d'une réservation ou d'un booking payés par Stripe). Origine LESPASS, liée à la vente du paiement (vide pour un paiement antérieur aux ventes), client de cette vente. Un article par ligne remboursée, par `ajouter_l_article_d_avoir` (même règle de quantité qu'avant). Tout se fait dans une seule transaction. /
  `partial_refund_payment` writes one AVOIR sale per refund, one item per refunded line, in one transaction.
- **Les articles sont écrits AVANT l'appel à Stripe** : un refus du service (avoir partiel d'un article avec une part offerte, quantité hors bornes) arrête tout avant que Stripe ne rende de l'argent. Nouvelle garde, elle aussi avant Stripe : une vente d'origine qui existe mais n'est pas réglée est refusée (`ValueError`). Rien à rendre sur aucune ligne : aucune vente n'est ouverte. /
  Items are written BEFORE the Stripe call; unsettled original sale refused before Stripe; nothing to give back: no sale opened.
- **Le montant demandé à Stripe** = −Σ des nets des articles (centimes entiers), au lieu de prix × quantité. **UN règlement** Stripe négatif, montant = −`refund.amount` **lu sur l'objet renvoyé par Stripe**, au moyen du paiement (repli : moyen de la ligne), relié au paiement, `reference_externe` = `refund.id`. La part offerte (aucune aujourd'hui sur une ligne Stripe) serait tracée par un règlement FREE négatif, comme en D-3a. /
  One negative Stripe payment of the amount Stripe returns, with the refund id as external reference.
- **Écart d'encaissement** : si Stripe rend un autre montant que les articles (frais, arrondi), un article « Écart d'encaissement » (même produit système et mêmes règles qu'à l'encaissement en ligne) et une alerte ERROR. La création de cet article devient une fonction commune du service, `ajouter_l_article_d_ecart_d_encaissement`, appelée aussi par `encaisser_vente_stripe` (comportement inchangé). /
  Collection gap item when Stripe returns another amount; shared service function.
- **Ordre** : encaissement de la vente AVOIR, PUIS le paiement passe « remboursé en partie » (ou « remboursé »), PUIS les articles passent `REFUNDED` (envoi à l'ancien LaBoutik, inchangé). Une écriture qui échoue après le remboursement Stripe : rien n'est écrit, le paiement garde son statut, l'erreur est journalisée (ERROR, Sentry) avec l'id et le montant du remboursement pour un rapprochement à la main, puis remontée. /
  Settle, then payment status, then REFUNDED. A failure after the refund writes nothing and logs the refund id and amount.
- **Changement de comportement** : la ligne remboursée par Stripe porte désormais `credit_note_for` (la ligne d'origine). Après un remboursement Stripe **partiel**, le bouton « Avoir » de la liste des ventes refuse donc la ligne d'origine (« A credit note already exists for this entry. ») et la liste affiche ⚠ sur son statut : pas de double remboursement. Le rapport comptable lit les avoirs par statut, pas par ce lien : inchangé. /
  Behaviour change: Stripe-refunded lines carry `credit_note_for`; after a partial Stripe refund the "Credit note" button refuses the original line.
- **Tests** : la simulation de `stripe.Refund.create` rend un objet avec `id`, `amount` (le montant demandé) et `status` (plus de `MagicMock`, dont `int()` vaut 1). La fabrique `simuler_paiement_valide` encaisse la vente d'origine comme en production (`montant_encaisse`, moyen `SN`, `encaisser_vente_stripe`) : un remboursement refuse une vente pas réglée. Aucune assertion des tests existants ne change. /
  Tests: the faked refund returns id/amount/status; the paid-reservation factory settles the original sale as in production. No existing assertion changes.

**Pourquoi / Why :** fiche D §4 (« Remboursement Stripe », règle « Remboursement Stripe différent de la somme des articles »), §5 tests 17 et 21 ; SUIVI §4 « D-3 » (a)-(e) ; décisions techniques de l'orchestrateur (pas de vente vide, garde « vente pas réglée », FREE de la part offerte, `credit_note_for` accepté, erreur journalisée avec l'id du remboursement). /
Sheet D §4 and §5 tests 17, 21; SUIVI §4 D-3; orchestrator decisions.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `PaiementStripe/utils.py` | `partial_refund_payment` réécrite : vente AVOIR, articles avant Stripe, règlement au montant du refund, écart, transaction unique ; import `timezone` retiré |
| `BaseBillet/services_vente.py` | nouvelle fonction `ajouter_l_article_d_ecart_d_encaissement`, appelée par `encaisser_vente_stripe` et `partial_refund_payment` |
| `tests/pytest/test_avoirs_ecrivent_la_vente.py` | 8 tests : remboursement partiel, total (une vente, un règlement), écart, avoir partiel d'un offert refusé avant Stripe, échec d'encaissement (rien d'écrit, id du refund journalisé), vente d'origine pas réglée refusée avant Stripe, booking (FK `booking`), rien à rendre (aucune vente) ; aide `verifier_la_vente_d_avoir_encaissee` : paramètre `origine_attendue` (ADMIN par défaut) |
| `tests/pytest/test_caracterisation_annulations.py` | nouvelle aide `rembourser_comme_stripe` ; la fixture `lieu` l'utilise ; aucune assertion changée |
| `tests/pytest/test_stripe_refund.py` | simulations de `Refund.create` par `rembourser_comme_stripe` ; aucune assertion changée |
| `tests/pytest/fabriques_reservation.py` | `simuler_paiement_valide` encaisse la vente d'origine (montant encaissé, moyen `SN`, `encaisser_vente_stripe`) |

## D-3c-1 — Annulations : l'avoir de l'admin écrit sa vente, écran « Remboursé par » ; l'utilisateur hors Stripe n'a plus d'avoir (D31) / Cancellations: the admin credit note writes its sale, "Refunded by" screen; no credit note for a non-Stripe user (D31)

**Migration :** Non — **Chaînes i18n :** 7 nouvelles (msgid français) : « Annuler et rembourser », « Sélection », « Les achats payés en ligne sont remboursés par Stripe. », « Confirmer l'annulation », « Retour à la liste », « Réglé sur place : pour un éventuel remboursement, contactez l'organisateur. » (réservation, billet : la vue ajoute déjà « … has been cancelled. » devant), « Votre réservation est annulée. Elle a été réglée sur place : pour un éventuel remboursement, contactez l'organisateur. » (booking, dont la vue n'ajoute rien). Workflow i18n à lancer par le mainteneur.

### Resume / Summary
**Quoi / What :**
- **Fonction commune** `ecrire_la_vente_d_avoir_d_une_ligne(ligne, quantite, moyen_rembourse, origine)` (`BaseBillet/services_vente.py`), extraite du POST d'`emettre_avoir` : vente AVOIR liée, article miroir, un règlement d'argent (moyen Stripe d'origine, ou moyen choisi, obligatoire s'il y a de l'argent hors Stripe à rendre), FREE pour la part offerte (jamais deux fois), encaissement, PUIS `CREDIT_NOTE`. Refus si la vente d'origine n'est pas réglée. Une transaction (point de sauvegarde si l'appelant en a une). `emettre_avoir` l'appelle (comportement inchangé). Nouvelle petite fonction `ligne_entierement_offerte(ligne)`, lue par les deux écrans. /
  Shared service function for one line's credit note, called by the "Credit note" button and the admin cancellations.
- **Avoir partiel d'une ligne entièrement offerte : permis** (SUIVI D-3c (d)) : `ajouter_l_article_d_avoir` accepte une partie de la quantité quand part offerte = total catalogue (non nul) ; l'avoir est entièrement offert lui aussi. Une ligne **en partie** offerte reste refusée en partiel. /
  Partial credit note of a fully offered line is allowed.
- **`cancel_and_refund_resa(annulation_par_l_admin=False, moyen_rembourse=None)` et `cancel_and_refund_ticket(ticket, annulation_par_l_admin=False, moyen_rembourse=None)`** : partie Stripe inchangée (D-3b). Lignes hors Stripe : l'ADMIN écrit un avoir par ligne par la fonction commune, origine ADMIN : un billet = 1 ; toute la réservation = les billets ENCORE ACTIFS du tarif (comparé par `Price`, la caisse écrivant ligne et billets sur deux `PriceSold`), bornés par la quantité pas encore créditée (un billet annulé par l'utilisateur sans avoir n'est pas rendu, un billet déjà remboursé par l'admin ne l'est pas deux fois) ; l'UTILISATEUR (valeurs par défaut, vues inchangées) n'écrit **aucun avoir** (D31). Garde « payée mais rien de remboursable » : l'admin sur tout l'argent payé (inchangé) ; l'utilisateur sur l'argent payé par Stripe seulement. `Reservation._creer_avoir` supprimée. /
  Explicit admin flag; the admin writes one credit note per non-Stripe line; the user writes none (D31); the refusal guard only looks at Stripe money for the user.
- **Les deux actions admin** (« Cancel and refund selected reservations », « Cancel and refund » des billets) passent par un **écran intermédiaire** (convention Django : 1er POST = écran, 2e POST `post=yes` = annulation). Champ « Remboursé par » (espèces, CB, chèque, virement) seulement si une ligne hors Stripe de la sélection a de l'argent à rendre ; pré-rempli si toutes ces lignes ont le même moyen d'origine dans la liste ; obligatoire quand il est affiché (champ vide → l'écran revient, rien n'est annulé). Un seul moyen pour toute la sélection. Mails et messages de succès / d'erreur inchangés. Nouveau gabarit `admin/annulation/confirmer_annulation.html`. /
  Both admin cancel actions go through a confirmation screen with an optional, required-when-shown "Refunded by" field.
- **Booking** : plus d'avoir hors Stripe dans `cancel_and_refund_booking` (seule la personne annule un booking, D31) ; `Booking._creer_avoir` supprimée ; `_lignes_hors_stripe` ne sert plus qu'au message. /
  Bookings: no non-Stripe credit note any more.
- **Changements de comportement (D31, décision du mainteneur)** : un utilisateur qui annule depuis « Mon compte » une réservation, un billet ou un booking réglé hors Stripe n'obtient plus d'avoir ; l'argent reste acquis, l'admin fait un avoir si le lieu rembourse. Le message dit « Réglé sur place : pour un éventuel remboursement, contactez l'organisateur. » après « Your reservation / ticket has been cancelled. » (booking : « Votre réservation est annulée. Elle a été réglée sur place… »), au lieu de « You will be refunded to the credit card… ». Seulement s'il y a de l'argent hors Stripe : un achat entièrement offert garde le message d'avant. /
  Behaviour change (D31): no credit note for a user cancelling an on-site purchase; new message when money was paid on site.

**Pourquoi / Why :** fiche D §4 (avoir de réservation hors Stripe fait par l'admin, annulation par l'utilisateur), annexe T9 (D31), §6 ; SUIVI §4 « D-3c (décisions techniques, avant brief) » (a)-(f) ; décisions de l'orchestrateur (paramètre explicite `annulation_par_l_admin`, garde utilisateur sur la partie Stripe seulement, contrat d'écran `post=yes`) et du mainteneur (message « réglée sur place »). La ligne « Avoir de booking fait par l'admin » de la fiche §4 est périmée (SUIVI (e)). /
Sheet D §4, T9 (D31); SUIVI D-3c; orchestrator and maintainer decisions.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/services_vente.py` | `ecrire_la_vente_d_avoir_d_une_ligne` et `ligne_entierement_offerte` (nouvelles) ; `ajouter_l_article_d_avoir` accepte l'avoir partiel d'une ligne entièrement offerte |
| `BaseBillet/models.py` | `cancel_and_refund_resa` / `cancel_and_refund_ticket` : `annulation_par_l_admin`, `moyen_rembourse`, D31, garde utilisateur sur Stripe, message « réglée sur place » ; `_montant_paye_par_stripe` (nouvelle) ; `_creer_avoir` supprimée |
| `Administration/admin_tenant.py` | `emettre_avoir` appelle la fonction commune ; `preparer_le_champ_rembourse_par` et `afficher_ou_valider_l_ecran_d_annulation` (module) ; les deux actions d'annulation passent par l'écran ; imports du service mis à jour |
| `Administration/templates/admin/annulation/confirmer_annulation.html` | nouveau : écran « Annuler et rembourser » |
| `booking/models.py` | `cancel_and_refund_booking` sans avoir hors Stripe, message « réglée sur place » ; `_creer_avoir` supprimée ; `_lignes_hors_stripe` simplifiée ; import `SaleOrigin` retiré |
| `Administration/management/commands/_demo_data_v2_ventes.py` | un commentaire qui citait `Reservation._creer_avoir()` |
| `tests/pytest/test_avoirs_ecrivent_la_vente.py` | 13 tests (14 cas) : écran et avoir au moyen choisi, écran sans champ (Stripe), moyen vide refusé, un billet sur trois, un billet offert sur deux, deux réservations (pré-remplissage), échec d'encaissement, utilisateur hors Stripe (réservation, billet ; message), réservation, billet et booking offerts (message d'avant), billet annulé par l'utilisateur puis réservation par l'admin (billet actif seulement), booking hors Stripe (message) |
| `tests/pytest/test_caracterisation_annulations.py` | `test_annulation_utilisateur_reservation_admin_especes_cree_un_avoir` → `…_aucun_avoir` (D31 : aucun avoir, rien envoyé à LaBoutik, réservation et billets annulés) ; l'aide `annuler_des_billets_depuis_l_admin` passe par l'écran (mécanisme) ; docstring |
| `tests/pytest/test_stripe_refund.py` | les trois tests d'avoir admin hors Stripe passent `annulation_par_l_admin=True, moyen_rembourse=CASH` (mécanisme) ; aucune assertion changée |
| `tests/e2e/test_admin_reservation_cancel.py` | l'admin valide l'écran de confirmation (mécanisme) |

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
2. Attendu : aucun paiement Stripe ; une vente dont l'article est la ligne du billet (0 centime). Depuis D-2a, elle est `REGLEE`, numérotée, sans règlement (voir Test 11).

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
2. Attendu : aucun paiement Stripe ; `Commande.vente` posée, deux articles à 0. Depuis D-2a, elle est `REGLEE`, numérotée, sans règlement (voir Test 12).

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

### Test 10 (D-1c-3) — le rapport ne dépend plus de la base de dev
1. Lancer `make test ARGS="tests/pytest/test_stripe_refund.py"`, puis tout de suite `make test ARGS="tests/pytest/test_comptabilite_service.py"`.
2. Attendu : 17 passés (le second fichier ne voit aucune ligne du lieu `lespass`).

### Test 11 (D-2a) — réservation et booking gratuits encaissés à 0
1. Réserver un billet d'un tarif à 0 € sans panier, puis un créneau d'une ressource à 0 €/h.
2. Dans `manage.py shell` (tenant lespass) :
   ```python
   from BaseBillet.models_vente import Vente
   for v in Vente.objects.order_by("-datetime_creation")[:2]:
       print(v.statut, v.numero, v.origine, v.total_catalogue, v.reglements.count())
   ```
3. Attendu : deux ventes `REGLEE`, numérotées, origine `LP`, total 0, 0 règlement.

### Test 12 (D-2a) — panier gratuit, et panier de réservations gratuites seules
1. Panier avec un billet à 0 € et une adhésion à 0 €, valider : `Commande.vente` est `REGLEE`, numérotée, sans règlement.
2. Panier avec une seule « réservation gratuite » (FREERES), valider : `Commande.vente` est `ANNULEE`, sans numéro, sans article.

### Test 13 (D-2a) — API v2, réservation gratuite
1. `POST /api/v2/reservations/` (clé API, permission réservation) avec, pour le même événement, un tarif billet à 0 € et un tarif « réservation gratuite » (`ticketQuantity: "2"`).
2. Attendu : une seule vente `REGLEE`, origine `AP` (API), qui porte les deux lignes ; la ligne FREERES a la quantité 2.
3. Même appel avec `ticketQuantity: "2.5"` : réponse 400, « La quantité de billets doit être un nombre entier. », aucune réservation créée.
4. Une réservation gratuite seule avec `"price": "5.00"` : la ligne vaut 500 centimes, entièrement offerte, un règlement FREE de 500 ; vente `REGLEE`.

### Verifs automatiques (D-2a)
`make test ARGS="tests/pytest/test_en_ligne_ecrit_la_vente.py"`

### Test 14 (D-2b) — billets vendus dans l'admin
1. Admin > Réservations > Ajouter : un tarif à 10 €, quantité 2, « Espèces ». Enregistrer.
2. Dans `manage.py shell` (tenant lespass) :
   ```python
   from BaseBillet.models_vente import Vente
   v = Vente.objects.order_by("-datetime_creation").first()
   print(v.origine, v.statut, v.numero, v.client, v.operateur, list(v.reglements.values_list("moyen", "montant")))
   ```
3. Attendu : `AD`, `REGLEE`, numérotée, client = l'acheteur, opérateur `None`, `[('CA', 2000)]`.
4. Même chose en « Offert » sur un tarif à 15 €, quantité 2 : ligne `amount = 1500`, `part_offerte = 3000`, règlements `[('NA', 3000)]`.
5. Le worker Celery ne reçoit AUCUNE tâche `send_sale_to_laboutik` pour ces ventes ; le mail des billets part.

### Test 15 (D-2b) — paiement et création d'adhésion dans l'admin
1. Une adhésion « en attente de paiement » : panneau « Ajouter un paiement », 20 €, « Chèque ». Attendu : ligne `V`, vente `AD` `REGLEE`, `[('CH', 2000)]`.
2. Admin > Adhésions > Ajouter : 20 €, « Virement ». Attendu : vente `AD` `REGLEE`, `[('TR', 2000)]`.
3. Admin > Adhésions > Ajouter : contribution vide, « Offert ». Attendu : vente `AD` `REGLEE` à 0, aucun règlement.
4. Admin > Adhésions > Ajouter : 20 €, sans moyen de paiement. Attendu : le formulaire revient avec « Choisissez un moyen de paiement pour la contribution. » ; rien n'est créé.

### Verifs automatiques (D-2b)
`make test ARGS="tests/pytest/test_admin_ecrit_la_vente.py tests/pytest/test_caracterisation_admin_api.py tests/pytest/test_admin_reservation_add.py"`

### Test 16 (D-2c) — adhésion gratuite par l'API v2
1. `POST /api/v2/memberships/` (clé API « membership »), sur un tarif d'adhésion à 15 €, sans `paymentMode` (donc « FREE »).
2. Dans `manage.py shell` (tenant lespass) : la ligne de l'adhésion a `part_offerte = 1500`, sa vente est `AP`, `REGLEE`, numérotée, règlements `[('NA', 1500)]`.
3. Même chose par le formulaire du site sur un tarif à 0 € : vente `LP`, `REGLEE`, aucun règlement.

### Test 17 (D-2c) — recharge cadeau, Fedow en panne puis rétabli
1. `POST /api/v2/wallet-refills/` avec un `Idempotency-Key`, Fedow arrêté : réponse 502. La ligne est `F`, sa vente `EN_ATTENTE`, sans numéro.
2. Fedow relancé, même requête, même clé : 201. La MÊME vente est `REGLEE`, `unite = 'EUR'` (monnaie cadeau), règlements `[('NA', <montant>)]`.
3. Même requête une troisième fois : 208, rien de plus en base.

### Test 18 (D-2c) — billets « payés ailleurs » et webhook Fedow
1. `POST /api/v2/reservations/` avec `additionalProperty paymentMethod = "card"`, deux billets à 10 € : vente `LB`, `REGLEE`, `[('CC', 2000)]`.
2. Une adhésion vendue par l'ancienne caisse LaBoutik : la vente `LB` de la ligne est `REGLEE`, `[('UK', <montant>)]`.

### Verifs automatiques (D-2c)
`make test ARGS="tests/pytest/test_api_ecrit_la_vente.py tests/pytest/test_api_v2_reservation_laboutik.py tests/pytest/test_api_v2_wallet_refill.py tests/pytest/test_caracterisation_admin_api.py"`

### Test 19 (D-3a) — avoir d'une vente admin, remboursé en espèces
1. Admin > Réservations > Ajouter : deux billets à 10 €, payés par CB.
2. Admin > Ventes : sur la ligne, bouton « Avoir ». Attendu : l'écran « Émettre un avoir », champ « Remboursé par » pré-rempli « CB ».
3. Choisir « Espèces », cliquer « Émettre l'avoir ». Attendu : retour à la liste, « Credit note created. », une ligne `Avoir` (quantité −2).
4. Dans `manage.py shell` (tenant lespass) : la vente de la ligne d'avoir est `AVOIR`, `REGLEE`, `vente_liee` = la vente des billets, règlements `[('CA', -2000)]`.
5. Cliquer de nouveau « Avoir » sur la ligne d'origine : « A credit note already exists for this entry. ».

### Test 20 (D-3a) — les autres écrans
1. Ligne payée en ligne par Stripe : l'écran n'a pas de champ et affiche « Remboursez cette somme depuis votre tableau de bord Stripe. » ; aucun remboursement n'apparaît chez Stripe ; règlement `[('SN', -<montant>)]` relié au paiement, sans référence externe.
2. Billet « Offert » vendu dans l'admin : l'écran n'a pas de champ ; règlements de l'avoir `[('NA', -1500)]`.
3. Ligne de caisse payée en monnaie locale : le champ est vide ; valider sans choisir → l'écran revient avec une erreur, rien n'est écrit.

### Verifs automatiques (D-3a)
`make test ARGS="tests/pytest/test_avoirs_ecrivent_la_vente.py tests/pytest/test_caracterisation_annulations.py tests/pytest/test_caracterisation_en_ligne.py"` ; `make e2e ARGS="tests/e2e/test_admin_credit_note.py"`

### Test 21 (D-1z) — API v2 : rien n'est écrit si l'encaissement échoue
Pas de test à la main : l'échec d'encaissement ne se provoque pas sans simulation. Témoin à la main : `POST /api/v2/reservations/` « payé ailleurs » (`paymentMethod = "cash"`) répond toujours 201, avec sa vente `LB` `REGLEE`.

### Verifs automatiques (D-1z)
`make test ARGS="tests/pytest/test_api_ecrit_la_vente.py tests/pytest/test_en_ligne_ecrit_la_vente.py"`

### Test 22 (D-3b) — annulation d'un billet payé par Stripe (Stripe en mode test, `stripe listen` lancé)
1. Acheter trois billets à 10 € en ligne, payer avec la carte de test.
2. « Mon compte » : annuler UN billet.
3. Dans `manage.py shell` (tenant lespass) :
   ```python
   from BaseBillet.models_vente import Vente
   v = Vente.objects.filter(nature="AVOIR").order_by("-datetime_creation").first()
   print(v.origine, v.statut, v.numero, v.vente_liee_id, list(v.articles.values_list("qty", "total_ttc", "status")), list(v.reglements.values_list("moyen", "montant", "reference_externe")))
   ```
4. Attendu : `LP`, `REGLEE`, numérotée, liée à la vente des billets ; un article `(-1, -1000, 'R')` ; un règlement `('SN', -1000, 're_…')`. L'id `re_…` est celui du remboursement visible dans le tableau de bord Stripe.
5. Admin > Ventes : sur la ligne des trois billets, bouton « Avoir » → « A credit note already exists for this entry. ».

### Test 23 (D-3b) — annulation d'une réservation de ressource payée par Stripe
1. Réserver un créneau payant d'une ressource, payer, puis l'annuler depuis « Mon compte ».
2. Attendu : une vente AVOIR `REGLEE`, son article porte le booking, un règlement `SN` négatif avec la référence `re_…`.

### Verifs automatiques (D-3b)
`make test ARGS="tests/pytest/test_avoirs_ecrivent_la_vente.py tests/pytest/test_stripe_refund.py tests/pytest/test_caracterisation_annulations.py tests/pytest/test_en_ligne_ecrit_la_vente.py"` ; une fois, vrai Stripe en mode test : `make test ARGS="tests/pytest/test_stripe_reel_remboursement.py"`

### Test 24 (D-3c-1) — l'admin annule une réservation payée en espèces
1. Admin > Réservations > « Ajouter » : deux billets à 10 €, moyen « Espèces ».
2. Cocher la réservation, action « Cancel and refund selected reservations ».
3. Attendu : un écran « Annuler et rembourser » avec la sélection et le champ « Remboursé par » pré-rempli « Espèces ». Valider sans rien changer (ou choisir « Virement »).
4. Attendu : retour à la liste, message de succès ; la réservation et ses billets sont annulés ; dans `manage.py shell`, la dernière vente `AVOIR` est `REGLEE`, origine `AD`, un article `(-2, -2000, 'N')`, un règlement au moyen choisi de −2000.
5. Recommencer avec deux réservations, l'une en espèces, l'autre par CB : le champ est vide et obligatoire (« Confirmer » sans choix → l'écran revient avec l'erreur, rien n'est annulé).

### Test 25 (D-3c-1) — un billet sur deux, offert
1. Admin > Réservations > « Ajouter » : deux billets à 15 €, moyen « Offert ».
2. Admin > Billets : cocher UN des deux billets, action « Cancel and refund ».
3. Attendu : écran sans champ « Remboursé par » ; après validation, ce billet est annulé, l'autre reste actif ; la vente `AVOIR` a un article `(-1)` entièrement offert et un seul règlement `FREE` de −1500.

### Test 26 (D-3c-1) — l'utilisateur annule un achat réglé sur place (D31)
1. Vendre dans l'admin deux billets en espèces à un compte que vous pouvez ouvrir.
2. Se connecter avec ce compte, « Mon compte » > Réservations : annuler la réservation.
3. Attendu : message « … Réglé sur place : pour un éventuel remboursement, contactez l'organisateur. » ; réservation et billets annulés ; **aucune** vente `AVOIR` nouvelle, la ligne de vente reste « Confirmée ».
4. Variante : vendre deux billets en espèces, l'utilisateur en annule UN, puis l'admin annule la réservation (« Remboursé par : espèces ») : l'avoir ne porte que sur le billet encore actif (−1, −1000).

### Verifs automatiques (D-3c-1)
`make test ARGS="tests/pytest/test_avoirs_ecrivent_la_vente.py tests/pytest/test_caracterisation_annulations.py tests/pytest/test_stripe_refund.py"` ; E2E seul : `make e2e ARGS="tests/e2e/test_admin_reservation_cancel.py"`
