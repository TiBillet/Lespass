# Chantier 01 — Réservation de ressource à validation manuelle

**Date :** 2026-10-20
**Statut :** spec écrite et relue (relecture Fable du 2026-10-20 intégrée), à valider avant de coder.
**Migration :** Oui — `booking/migrations/0009_booking_motif_du_refus.py` (un champ texte, sans
donnée à reprendre).

## 1. Le besoin

Certains lieux ne veulent pas qu'une ressource soit réservée automatiquement : une
personne de l'équipe doit d'abord accepter la demande. C'est déjà possible pour les
adhésions (exemple : caisse sociale alimentaire). On fait la même chose pour les
ressources.

Parcours voulu :

1. La personne clique sur un créneau, choisit un tarif « à validation manuelle » et
   envoie le formulaire.
2. Elle voit : « Votre demande a été envoyée. Vous recevrez une confirmation, ou une
   invitation à payer. » Aucun paiement à ce moment-là.
3. L'équipe reçoit un mail. Dans l'admin, elle **valide** ou **refuse** la demande.
4. Validée et payante : la personne reçoit un mail avec un lien « Payer ma réservation ».
   Validée et gratuite : elle reçoit un mail de confirmation.
   Refusée : elle reçoit un mail avec le motif écrit par l'admin, s'il y en a un.

## 2. Décisions (validées par le mainteneur le 2026-10-20)

| # | Question | Décision |
|---|---|---|
| D1 | Une demande en attente bloque-t-elle le créneau ? | **Oui.** La place est retenue jusqu'à ce que la demande soit validée ou refusée. Premier arrivé, premier servi. |
| D2 | Une réservation validée mais pas encore payée expire-t-elle ? | **Non.** Elle bloque le créneau jusqu'au paiement, ou jusqu'à une annulation faite par l'admin. Pas d'échéance automatique. |
| D3 | Tarif gratuit validé | Confirmé tout de suite (statut gratuit `FREERES` / `FREERES_USERACTIV`), avec un mail de confirmation. |
| D4 | Refus | Mail à la personne. L'admin peut écrire un motif au moment du refus. Le motif est enregistré sur la réservation et repris dans le mail. |
| D5 | Où se règle la validation manuelle ? | Sur le **tarif** : le champ existant `Price.manual_validation` (`BaseBillet/models.py:2233`), comme pour les adhésions. Pas de nouveau champ sur `Resource`. |
| D6 | Panier | Inchangé : un tarif de ressource à validation manuelle est déjà refusé par le panier (`BaseBillet/services_panier.py:905`). La demande passe uniquement par la réservation directe. |

## 3. Ce qui existe déjà (à réutiliser)

- `Price.manual_validation` : le drapeau. Deux formulaires d'admin le concernent :
  - `PriceChangeForm` (`Administration/admin/prices.py:232`), la fiche d'un tarif seul : le
    champ y est caché pour tout produit qui n'est pas une adhésion (`prices.py:174`) ;
  - `ResourcePriceInlineForm` (`Administration/admin/products.py:1205`), l'inline des tarifs
    d'une ressource : le champ est absent de son tuple `fields` (`products.py:1246`).
- Les statuts du `Booking` (`booking/models.py:506`) :
  - `ADMIN_WAITING = "WA"` (« Waiting for admin validation ») : existe, **jamais posé** ;
  - `ADMIN_VALID = "VA"` (« Confirmed by admin, waiting for payment ») : bloque déjà le créneau ;
  - `ADMIN_CANCELED = "CA"` : ne bloque pas le créneau.
  - **Attention** : ces codes ne sont pas ceux de `Membership` (`AW`/`AV`/`AC`). Ne pas les mélanger.
- `get_checkout_stripe(booking, vente)` (`booking/booking_engine.py:869`) : crée la session
  Stripe d'un booking, sans SEPA (`accept_sepa=False`, l.894).
- Le passage à « payé » : Stripe → `Paiement_stripe.update_checkout_status` → lignes
  `PAID` → `trigger_C` (`BaseBillet/triggers.py:318`) → `Booking.PAID_BY_USER`.
- Le modèle à copier, côté adhésions :
  - `MembershipValidator.validate` (`BaseBillet/validators.py:1192-1211`) : bascule en attente + mails ;
  - `MembershipMVT.admin_accept` (`BaseBillet/views.py:5088`) : validation par l'admin ;
  - `MembershipMVT.get_checkout_for_membership` (`BaseBillet/views.py:4941-5085`) : lien de
    paiement qui crée la session Stripe **au clic**, avec les pages « déjà payé »,
    « paiement en cours », « lien invalide » ;
  - les tâches `send_membership_pending_admin`, `send_membership_pending_user`,
    `send_membership_payment_link_user` (`BaseBillet/tasks.py:437`, `516`, `931`) ;
  - le panneau `Administration/templates/admin/membership/actions_panel.html`, branché par
    `change_form_before_template` (`Administration/admin_tenant.py:2185`) et
    `changeform_view` (`:2187`).

### Vérifié à la relecture (pas d'action)

- **Aucune purge des ventes en attente.** Aucune tâche périodique ne touche `Vente` ni
  `LigneArticle` (`TiBillet/celery.py:58-139`). La clôture de caisse ne touche que tables et
  commandes. `reprise_des_ventes.py` est un script ponctuel sur les lignes **sans** vente.
  Une vente ouverte pendant des semaines pour une demande ne casse donc rien (D1, D2).
- **Un paiement abandonné n'annule pas la vente.** Le statut Stripe `CANCELED` n'est posé que
  si `payment_status` n'est ni `unpaid` ni `paid` ; un abandon donne `PENDING` puis `EXPIRE`,
  et `expire_paiement_stripe` ne touche pas la vente (`BaseBillet/signals.py:111-115`).
  `async_payment_failed` → `annuler_vente` (`ApiBillet/views.py:1311-1334`) ne concerne que
  le SEPA, absent ici. La personne peut donc retenter le paiement.
- **Un 2ᵉ essai de paiement** : `to_pay()` compte les lignes `UNPAID` et `CREATED`
  (`booking/models.py:699`), le montant ne change pas. `CreationPaiementStripe` rattache les
  lignes au nouveau paiement ; l'ancien, `EXPIRE`, reste sans ligne.
- **`max_per_user` et stock** : le parcours direct ne les lit pas (`validate_new_booking`,
  `booking_engine.py:613-690`) et `Price.max_per_user_reached` ne traite pas les ressources
  (`BaseBillet/models.py:1436-1458`). La question « une demande compte-t-elle ? » est sans
  objet aujourd'hui.
- **API v2** : `ProductCreateSerializer.create` (`api_v2/serializers.py:1217`) accepte la
  catégorie « Ressource » et pose `manual_validation` (`:1306-1322`). Rien à faire.

## 4. Le cycle de vie d'une demande

```
            (usager envoie le formulaire, tarif manual_validation)
                                   │
                                   ▼
                       WA — demande en attente ─────────────┐
                    (bloque le créneau, vente ouverte,       │ admin refuse
                     ligne CREATED, pas de Stripe)           │ (motif facultatif)
                                   │                         ▼
                      admin valide │                  CA — refusée
                                   │                  (vente annulée, ligne CANCELED,
             ┌─────────────────────┴───────────┐       créneau libéré, mail)
             │ prix > 0                        │ prix = 0
             ▼                                 ▼
 VA — validée, à payer                 FR / FU — confirmée
 (bloque le créneau sans               (ligne VALID « offert »,
  échéance, mail « Payer »)             vente encaissée à 0, mail)
             │
             │ clic sur « Payer » → session Stripe
             │ (le statut RESTE VA tant que Stripe n'a pas confirmé)
             ▼
 PA — payée (trigger_C, inchangé)

 Avant PA : l'admin peut refuser/annuler (CA), la personne peut annuler (UC).
 Un paiement qui arrive APRÈS CA ou UC ne réactive pas la réservation (§5.9).
```

## 5. Le détail, fichier par fichier

### 5.1 La demande — `booking/booking_engine.py`, `validate_new_booking`

Aujourd'hui (l.754-865) : le booking naît en `WAITING_PAYMENT` ; la vente est ouverte si
`create_checkout` est vrai (l.775) ; la ligne est créée en `CREATED` ; puis le bloc
`if create_checkout:` crée la session Stripe (payant) ou encaisse à 0 (gratuit).

Changement :

- Le booking naît en `ADMIN_WAITING` quand `price.manual_validation` est vrai, et en
  `WAITING_PAYMENT` sinon.
- `_book_post` continue d'appeler avec `create_checkout=True` (la valeur par défaut, l.508).
  **Ne pas** utiliser `create_checkout=False` pour dire « demande » : sans lui, aucune vente
  n'est ouverte. La vente et la ligne sont créées comme aujourd'hui, dans la même
  transaction. La ligne porte le tarif vendu et le montant (prix libre compris) : c'est elle
  qui donnera le montant à payer après la validation.
- Pour une demande, le bloc `if create_checkout:` est **sauté** : pas de session Stripe, pas
  d'`encaisser_vente`. La fonction rend `(True, booking, None)`.
- Toutes les gardes actuelles s'appliquent aussi à une demande : créneau passé, tarif de la
  ressource, adhésions obligatoires, prix libre, montant Stripe entre 0,01 et 0,49 € refusé
  (l.685), capacité.
- **Garde-fou** : si `validate_new_booking` reçoit une `commande` (chemin panier) avec un
  tarif à validation manuelle, c'est un bug d'appel (le panier refuse ce tarif plus tôt). On
  lève une `ValueError` explicite plutôt que de créer une demande dans une commande.
- Le bloc gratuit actuel (l.854-865 : statut `FREERES`/`FREERES_USERACTIV`, ligne `VALID` en
  `PaymentMethod.FREE`, `encaisser_vente`) est extrait en une fonction
  `confirmer_booking_gratuit(booking, ligne_article, vente, member)` dans `booking_engine.py`.
  Elle est appelée ici et par `admin_accept` (§5.6) : c'est le même geste comptable, il ne
  doit pas diverger.

### 5.2 Le blocage du créneau — `get_existing_bookings_for_resource`

`booking/booking_engine.py:341-348` : ajouter `Booking.ADMIN_WAITING` aux statuts qui
occupent le créneau (D1). `ADMIN_VALID` y est déjà (D2 : pas d'échéance). Un seul endroit à
changer : `compute_slots`, `compute_remaining_capacity` et l'affichage admin des créneaux
(`booking/views.py:119`) lisent tous cette fonction.

Sur le calendrier, un créneau demandé apparaît occupé pour tout le monde. L'affichage admin
(`infos_creneau.html:58`) montre `get_status_display()` (`booking/views.py:168`) : il
affichera la traduction de « Waiting for admin validation ». Rien d'autre à faire.

### 5.3 Le formulaire du créneau — `booking/templates/booking/partials/book_form.html`

- Chaque tarif (bouton radio) porte un `data-manual-validation="true|false"`.
- Un seul bouton d'envoi : son libellé passe de « Payer maintenant » à « Envoyer la demande »
  selon le tarif coché, avec un court texte « Cette réservation doit être acceptée par
  l'équipe. Vous recevrez un mail. ». On réutilise le JS déjà présent pour le prix libre
  (`book_form.html:240-300`), qui réagit au changement de tarif. Pas de `hx-get`.
- Pour un tarif à validation manuelle, les boutons du panier (`resource-add-to-cart`, et
  `then=checkout`) sont masqués : le panier le refuserait de toute façon.
- Cas « le panier n'est pas vide » (l.433-483) : aujourd'hui seul le panier est proposé. Pour
  un tarif à validation manuelle, le bouton « Envoyer la demande » doit quand même
  s'afficher, sinon la demande est impossible tant que le panier n'est pas vidé.

### 5.4 La réponse à l'usager — `booking/views.py`, `_book_post`

l.1014-1030 : si le booking rendu est en `ADMIN_WAITING`, il n'y a pas de `checkout_url`. On
pose `messages.success(request, _("Votre demande de réservation a été envoyée. Vous recevrez une confirmation ou une invitation à payer par mail."))`
et on redirige vers « Mes réservations » avec `?new=<pk>`, comme une réservation gratuite.
Les deux mails « demande reçue » (§5.7) partent par `transaction.on_commit`.

### 5.5 « Mes réservations » et annulation par la personne

**Affichage** — `BaseBillet/views.py`, `MyAccount.my_bookings` :
- les filtres `:1664-1665` et `:1671-1672`, et celui de l'accueil du compte (`:1505-1506`),
  ajoutent `ADMIN_WAITING`. `ADMIN_VALID` y est déjà ;
- gabarits `pages/templates/pages/V2/vues/compte/bookings.html` et
  `pages/templates/pages/classic/vues/compte/bookings.html` :
  - `WA` : badge « Demande en attente de validation » ;
  - `VA` avec un reste à payer : badge « Validée — à payer » et un bouton « Payer » vers la
    vue `pay` (§5.8), `data-testid="booking-pay"`.

**Annulation** — `cancel_confirm` (`booking/views.py:1115`, filtre des statuts `:1139`) :
- accepte aussi `ADMIN_WAITING` ;
- **le délai d'annulation** (`deadline_passed()`, `:1156-1164`) ne s'applique pas à une
  demande `WA` ni à une `VA` sans rien de payé : aucun argent n'est en jeu, la personne peut
  retirer sa demande jusqu'au début du créneau ;
- pour une `WA` ou une `VA` non payée, dans `cancel_and_refund_booking`
  (`booking/models.py:757`), sans toucher au chemin des réservations payées :
  - expirer la session Stripe ouverte s'il y en a une (`expirer_la_session_stripe_ouverte`,
    §5.9) ;
  - `annuler_vente(vente)` — **elle ne touche pas les lignes** (`BaseBillet/services_vente.py:2015-2018`) :
    passer explicitement la ligne en `LigneArticle.CANCELED` et la sauvegarder ;
  - rendre un texte juste : « Votre demande est annulée. Rien n'a été débité. » au lieu de
    `cancel_text()`, qui parle de remboursement sur la carte (`booking/models.py:750-754`).
    Le mail `send_booking_cancellation_user` reprend ce texte (`booking/tasks.py:33, 50-61`).

### 5.6 L'admin

**Le drapeau** :
- `ResourcePriceInlineForm` (`Administration/admin/products.py:1205`) : ajouter
  `manual_validation` au tuple `fields` (`:1246`), et surcharger son `help_text` dans
  `__init__` comme c'est déjà fait pour `max_per_user` (`:1222-1227`). Le `help_text` du
  modèle parle d'adhésion ; le changer dans le modèle fabriquerait une migration `BaseBillet`.
- `PriceChangeForm` (`Administration/admin/prices.py:174`) : ne plus cacher le champ pour les
  produits de catégorie ressource (fiche d'un tarif édité hors inline).

**Le panneau d'actions** — `BookingAdmin` (`Administration/admin/resources.py:119`) :
`change_form_before_template = "admin/booking/actions_panel.html"`, contexte injecté par
`changeform_view`, sur le modèle de `MembershipAdmin` (`admin_tenant.py:2185-2187`).
- Statut `WA` :
  - bouton « Valider la demande » (`data-testid="booking-action-accept"`) ;
  - bouton « Refuser », qui ouvre un champ texte « Motif (facultatif, envoyé à la personne) »
    puis « Confirmer le refus » (`data-testid="booking-action-refuse"`) ;
  - si le tarif exige une adhésion (`adhesions_obligatoires`), une ligne qui dit si la
    personne a toujours une adhésion valide. Information seulement, pas de blocage.
- Statut `VA` et reste à payer : boutons « Renvoyer le lien de paiement » et « Copier le
  lien », et le bouton « Refuser / annuler » avec motif.
- Styles en ligne (règle Unfold : pas de classes Tailwind custom).

**Les vues** — deux actions POST sur `BookingViewSet` (`booking/views.py`). `BookingViewSet`
a `permission_classes = [IsAuthenticatedOrReadOnly]` (`:61`) : chaque action teste elle-même
`TenantAdminPermissionWithRequest(request)` (`ApiBillet/permissions.py:76`, une **fonction**
qui rend un booléen) et rend 403 sinon.
- `admin_accept` — `WA` →
  - reste à payer > 0 : `VA`, puis mail « Payer ma réservation » ;
  - gratuit : `confirmer_booking_gratuit(...)` (§5.1), puis mail de confirmation ;
  - déjà `VA` : renvoie seulement le mail (même comportement que `admin_accept` des adhésions).
- `admin_refuse` — `WA` ou `VA` non payée → `ADMIN_CANCELED`, `annulee_le`,
  `motif_du_refus`, session Stripe expirée (§5.9), vente annulée, ligne en `CANCELED`
  (explicitement), mail de refus. Le motif est validé par un `serializers.Serializer`
  (`CharField(required=False, allow_blank=True, max_length=...)`), pas par un Form.
- Les deux ouvrent une transaction, verrouillent le booking (`select_for_update`) et relisent
  son statut : un double clic ou deux admins en même temps n'envoient pas deux mails et
  n'encaissent pas deux fois.
- **Tous les mails partent par `transaction.on_commit`** : sinon Celery peut lire le booking
  avant le commit, encore en `WA`, et choisir le mauvais texte.
- Réponse : un partiel HTMX qui remplace le panneau, plus un toast.

**Le champ `motif_du_refus`** (`booking/models.py`, `TextField(blank=True, default="")`) :
en lecture seule sur la fiche. Migration `0009`.

**Le filtre** : `ChoicesDropdownFilter` sur `status` (`resources.py:146`) propose déjà
« Waiting for admin validation ». Rien à ajouter.

**Le changement de statut à la main** (liste déroulante du formulaire) reste possible, mais
il n'envoie aucun mail et ne touche pas la vente. Le texte d'aide du champ statut le dit et
renvoie vers les boutons du panneau.

### 5.7 Les mails — `booking/tasks.py`

Quatre tâches Celery, sur le modèle des tâches d'adhésion, avec `send_email_generique`
(`BaseBillet/tasks.py:1674`). Toutes sont lancées par `transaction.on_commit`.

| Tâche | Destinataire | Contenu |
|---|---|---|
| `send_booking_request_admin` | les admins du lieu (`TibilletUser.objects.filter(client_admin=tenant)`, à défaut `Configuration.email`) | « Nouvelle demande de réservation » : ressource, créneau, personne, bouton vers la fiche admin |
| `send_booking_request_user` | la personne | « Votre demande est enregistrée » : ressource, créneau, « vous recevrez une réponse par mail » |
| `send_booking_accepted_user` | la personne | payant : « Votre demande est acceptée » + bouton « Payer ma réservation » (vue `pay`) ; gratuit : « Votre réservation est confirmée » |
| `send_booking_refused_user` | la personne | « Votre demande n'a pas pu être acceptée » + le motif s'il existe |

Rappel : redémarrer `lespass_celery` après l'ajout de nouvelles tâches.

### 5.8 Le paiement après validation — nouvelle action `pay` sur `BookingViewSet`

`GET /booking/<pk>/pay/` : le lien du mail et du bouton « Payer » de « Mes réservations ».
Copie de `get_checkout_for_membership` (`BaseBillet/views.py:4941-5085`) adaptée au booking :

- `BookingViewSet` laisse les GET aux anonymes : la vue teste `request.user.is_authenticated`
  elle-même (redirection vers la connexion avec `next`, comme `cancel_confirm`), et le
  booking doit appartenir à la personne connectée (sinon 404) ;
- `PAID_BY_USER` → page « déjà payée » ;
- statut autre que `VA` (refusée, annulée…) → page « lien plus valable » (409) ;
- un `Paiement_stripe` du booking (`booking.paiements`) encore `PENDING`/`OPEN` : relire la
  session Stripe — `open` → rediriger vers la même session ; `complete` → page « paiement en
  cours » ; sinon → marquer `EXPIRE` et en créer une nouvelle ;
- sinon → `get_checkout_stripe(booking, vente=<la vente de la ligne du booking>)` puis
  redirection vers Stripe.

**Point critique (D2)** : `get_checkout_stripe` remet aujourd'hui le booking en
`WAITING_PAYMENT` (`booking_engine.py:905`). Ce statut ne bloque le créneau que 30 minutes
(`DUREE_D_UN_PAIEMENT_EN_COURS`) : une personne qui ouvre Stripe puis abandonne perdrait sa
place validée. `get_checkout_stripe` doit donc **laisser `ADMIN_VALID` tel quel** et ne
passer à `WAITING_PAYMENT` que les autres statuts.

Trois petits gabarits dans `booking/templates/booking/views/` (« déjà payée », « paiement en
cours », « lien plus valable »). Ceux des adhésions (`fonctionnel/adhesion/payment_*.html`)
lisent `membership` : on ne les rend pas génériques.

### 5.9 Un paiement après une annulation — `trigger_C` et la session Stripe

`trigger_C` (`BaseBillet/triggers.py:318-332`) pose `PAID_BY_USER` sans regarder le statut
d'avant. Cas : la réservation est refusée par l'admin (`CA`) ou annulée par la personne
(`UC`) pendant qu'un onglet Stripe est encore ouvert ; le paiement arrive ensuite.
`encaisser_vente_stripe` refuse la vente annulée (`ValueError`), mais l'exception est avalée
(`BaseBillet/signals.py:100-106`) : les lignes passent quand même à `PAID` puis `VALID`, et
`trigger_C` réactiverait la réservation, peut-être sur un créneau redonné à quelqu'un d'autre.

Deux parades :

1. **Fermer la session** : une fonction `expirer_la_session_stripe_ouverte(booking)` (dans
   `booking_engine.py`) appelle `stripe.checkout.Session.expire` sur chaque
   `Paiement_stripe` `PENDING`/`OPEN` du booking, et le marque `EXPIRE`. Elle est appelée par
   `admin_refuse` (§5.6) et par l'annulation d'une `VA` par la personne (§5.5).
2. **Garde dans `trigger_C`**, comme pour les adhésions
   (`update_membership_state_after_stripe_paiement` ne réactive jamais une adhésion
   `ADMIN_CANCELED`, `triggers.py:58`) : si le booking est `ADMIN_CANCELED` **ou**
   `USER_CANCELED`, `trigger_C` ne change pas son statut et écrit un `logger.error` (visible
   dans Sentry). L'argent est encaissé : le remboursement se fait à la main depuis l'admin.

### 5.10 Récap quotidien — `Administration/recap_quotidien.py`

- `_rubrique_nouvelles_reservations_de_ressources` (l.306, exclusion `:313-315`) : exclure
  aussi `ADMIN_WAITING` (une demande n'est pas une réservation).
- Ajouter une rubrique « Demandes de réservation en attente » (toutes les `WA`, pas seulement
  celles d'hier), sur le modèle de `_rubrique_adhesions_en_attente` (l.265-270).

## 6. Hors périmètre

- Une échéance de paiement après validation (D2 : non).
- La validation manuelle dans le panier (D6 : le panier refuse ce tarif).
- Un mail de confirmation pour les réservations **directes** (il n'en existe pas
  aujourd'hui ; seul le cas « demande validée » en reçoit un).
- Le gabarit `booking/views/book.html`, rendu hors HTMX mais inexistant
  (`booking/views.py:829`, `964`, `998`, `1080`, et `BaseBillet/views.py:7839` dans
  `PanierMVT.add_resource`) : bug à part.
- Le filtre « À vérifier » de la liste des ventes (`Administration/admin_tenant.py:2400`,
  `:2827-2838`) montre toute vente en attente depuis plus d'une heure sans paiement Stripe.
  Une demande `WA`, ou une `VA` jamais payée, y restera visible. C'est juste, pas destructif :
  on le documente dans le CHANGELOG, on ne filtre pas.
- Un événement qui chevauche des réservations existantes (`EventForm.clean`,
  `admin_tenant.py:4112-4114`) : préexistant.

## 7. Plan en fiches

Ordre : **A → B → C → D → E**. La vue `pay` vient avant les boutons et les mails qui y mènent :
aucune fiche ne livre un lien mort. Chaque fiche se termine par ses tests verts, vus rouges
sur une mutation volontaire.

| Fiche | Contenu | Tests |
|---|---|---|
| A | Drapeau visible dans l'admin ressource (§5.6) ; `validate_new_booking` crée la demande, extraction de `confirmer_booking_gratuit` (§5.1) ; blocage du créneau (§5.2) | pytest : demande créée en `WA` sans `Paiement_stripe` ; vente ouverte + ligne `CREATED` au bon montant (prix libre compris) ; créneau `WA` occupé ; `commande` + tarif manuel → `ValueError` ; réservation gratuite directe inchangée |
| B | Formulaire du créneau (§5.3) ; réponse `_book_post` (§5.4) ; mails « demande reçue » (§5.7) ; « Mes réservations » (badge `WA`) et annulation par la personne (§5.5, sauf la session Stripe) | pytest : POST → redirection « Mes réservations », message, 2 tâches lancées ; `WA` visible dans le compte ; annulation d'une `WA` après le délai acceptée → `UC`, vente annulée, ligne `CANCELED`, texte « rien n'a été débité » |
| C | Vue `pay` (§5.8) ; `get_checkout_stripe` garde `VA` ; `expirer_la_session_stripe_ouverte` + garde `trigger_C` pour `CA` et `UC` (§5.9) ; bouton « Payer » de « Mes réservations » | pytest (Stripe simulé, fixture qui pose `VA`) : session créée, statut reste `VA` ; session ouverte réutilisée **sans 2ᵉ `Paiement_stripe`** ; `PA` → page déjà payée ; `CA` → 409 ; anonyme → connexion ; booking d'un autre → 404 ; paiement reçu sur `CA`/`UC` → statut inchangé + log |
| D | Migration `motif_du_refus` ; panneau admin + `admin_accept` / `admin_refuse` (§5.6) ; mails acceptée / refusée (§5.7) | pytest : accept payant → `VA` + mail après commit ; accept gratuit → `FR`/`FU`, vente encaissée à 0 ; refus → `CA`, motif, session expirée, vente annulée, ligne `CANCELED`, créneau libéré ; non-admin → 403 ; double accept → un seul mail |
| E | Récap quotidien (§5.10) ; CHANGELOG ; doc `booking/doc/tibillet-booking-presentation_fr.md:59` (« pas de validation manuelle » devient faux) | pytest récap ; E2E Playwright : demande → validation admin → paiement Stripe réel → « Payée » dans le compte (modèle : `tests/e2e/test_membership_manual_validation_stripe.py`) |

## 8. Textes traduisibles

Tous les nouveaux textes en `_()` / `{% translate %}`, msgid en **français**. Le workflow
i18n (`makemessages` / `compilemessages`) est lancé par le mainteneur à la fin du chantier.
