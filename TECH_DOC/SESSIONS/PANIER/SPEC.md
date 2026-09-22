# Panier (Commande) — tests de toute la chaîne (chantier 01)

> **Status :** plan du 2026-09-21, relu par un agent Opus (exactitude) et un agent Fable
> (mainteneur, lisibilité), corrections intégrées. **Validé par le mainteneur** (§2.2).
> **Périmètre :** le panier (`BaseBillet/services_panier.py`, `BaseBillet/services_commande.py`,
> `PanierMVT` dans `BaseBillet/views.py`, `BaseBillet/context_processors.py`, modèle `Commande`),
> la chaîne de paiement qu'il déclenche (signaux, triggers), et **les parcours sans panier**
> pour vérifier que chaque achat donne le même résultat des deux façons.
> **Hors périmètre :** le panier en base (`TECH_DOC/SESSIONS/TODO/`), les remboursements
> (`TECH_DOC/SESSIONS/REMBOURSEMENT/`), le moteur de créneaux (`booking/tests/`).

## Lexique

| Terme | Sens |
|---|---|
| Ligne `O` / `U` / `P` / `V` | `LigneArticle` créée / non payée / payée / validée (`'C'` = annulée) |
| Billet `N` / `K` / `S` | `Ticket` pas encore actif / actif, prêt à scanner / scanné |
| Réservation `P` / `V` / `FA` | payée (mail pas encore parti) / validée (mail parti) / gratuite, utilisateur actif |
| Adhésion `ONCE` / `AW` / `WP` | payée une fois / en attente de validation manuelle / en attente de paiement |
| Parcours direct | achat sans panier (« Envoyer la demande », « Payer maintenant ») |
| Mutation | modification volontaire du code pour vérifier qu'un test la détecte (il doit rougir) |
| `make e2e-stripe` | E2E avec vrai paiement Stripe en mode test (`stripe listen` doit tourner) |

## 0. Objectif

Le panier est devenu le moteur d'achat principal, et il n'a aucun test dédié. À la fin :

1. chaque fonction du panier est testée (ajout, retrait, limites, revalidation, total) ;
2. chaque phase de `CommandeService.materialiser()` est testée, jusqu'au paiement d'une
   Commande mixte (adhésion + billets de 2 événements + ressource) ;
3. **chaque type d'achat donne le même résultat avec et sans panier** (§5) ;
4. chaque bug est prouvé par un test **rouge**, puis corrigé ou noté selon la décision du §2 ;
5. quelques E2E couvrent ce que seul un navigateur voit (§7, étape 7) ;
6. **la couverture de code monte** : mesure de départ par `make coverage` (ajouté pour ce
   chantier), mesure d'arrivée en clôture, les deux dans ce document (§6.4).

### Carte des parcours d'achat

| Qui | Bouton | Parcours | Retour de paiement |
|---|---|---|---|
| Anonyme | « Envoyer la demande » (billet, adhésion) | direct | billet : `/event/<paiement>/stripe_return/` ; adhésion : `/memberships/<paiement>/stripe_return/` |
| Connecté, panier vide | « Payer maintenant » | direct | idem ; ressource : `/event/<paiement>/stripe_return/` |
| Connecté, panier vide | « Ajouter au panier » | panier | — |
| Connecté, panier non vide | « Ajouter au panier » / « Ajouter et payer » | panier | `/event/<paiement>/stripe_return/`, même sans billet |

- La réservation de ressource (`booking-book`) exige d'être connecté.
- Un compte **non activé** ne peut pas utiliser le panier : `SessionAuthentication` le refuse
  (403) et le gabarit le traite en anonyme. Il n'a que le parcours direct.
- Le bouton « Ajouter au panier » s'affiche aussi pour les tarifs d'adhésion récurrents ou à
  validation manuelle, que le panier refuse : le refus doit être propre (toast d'erreur).
- Les parcours directs ne créent **pas** de `Commande`. Ce sont deux chaînes de code
  distinctes (`TicketCreator`/`MembershipValidator`/`validate_new_booking` d'un côté,
  `materialiser()` de l'autre), qui doivent donner le même résultat.

## 1. Constats

Chaque constat vient de la lecture du code, revérifiée par les deux relectures ; les plus
graves ont été revérifiés une troisième fois à la main. **Aucun n'est prouvé par un test** :
chacun le sera (rouge s'il s'agit d'un bug) avant toute correction. « Les deux parcours » veut
dire que le défaut existe aussi sans panier.

### 1.1 Argent

- **C5 — Un code promo remise TOUS les produits billet de l'événement** (les deux parcours).
  `TicketCreator.method_B` (`validators.py:312`) passe le code à `get_or_create_price_sold()`
  pour chaque tarif, sans vérifier `promo.product` (`ApiBillet/serializers.py:840`). Événement à
  2 produits, code sur A → B est aussi remisé.
- **C13 — Prix libre ajouté deux fois au même événement : facturé au dernier montant.**
  `services_commande.py:248-250` additionne les quantités mais **écrase** le montant libre.
  « 1 billet à 10 € » puis « 1 billet à 20 € » : le panier affiche 30 €, Stripe facture 40 €.
  Même endroit : les options et le formulaire du 2e ajout sont perdus (seul le 1er item est lu,
  l.256-258).
- **C15 — On peut réserver une ressource au tarif d'une autre** (les deux parcours).
  Ni `add_resource()`, ni `validate_new_booking()`, ni la vue directe `_book_post`
  (`booking/views.py:633`) ne vérifient `price.product == resource.product`. La vue directe
  n'exige même pas un tarif publié.
- **C19 — Les stocks ne tiennent pas** (les deux parcours).
  `Price.out_of_stock()` (`models.py:1849`) ne compte ni la quantité demandée ni les paniers ;
  le stock d'un tarif d'adhésion n'est vérifié dans **aucun** parcours ; la capacité d'une
  ressource ne compte pas les bookings en attente de paiement (`booking_engine.py:327`), donc
  deux paniers peuvent payer le dernier créneau. **Corrigé** (décisions 11 et 12) : un stock
  compte ce qui est vendu + ce qui est en train d'être payé (depuis moins de
  `DUREE_D_UN_PAIEMENT_EN_COURS`, 30 minutes) + ce qu'on demande. `Price.out_of_stock(event,
  quantite_demandee)` ; stock des adhésions vérifié en direct et au panier (actives, engagées
  `STATUTS_EN_COURS` dont validation manuelle `AW`, en attente de paiement récentes) ; créneau
  en attente de paiement retenu. La quantité demandée était déjà comptée pour la JAUGE de
  l'événement, jamais pour le STOCK du tarif.
  Cas d'usage remonté par un lieu (repas limité) : deux produits EXCLUSIFS, « réservation avec
  repas » (stock 25) et « réservation sans repas » (sans stock), jauge de l'événement 100 →
  au plus 100 personnes et 25 repas. Un produit « Repas » séparé compterait deux billets par
  personne dans la jauge. Test : `test_jauge_de_l_evenement_et_repas_limite_avec_deux_produits_exclusifs`.
- **C21 — Billet de catégorie `BILLET` à 0 € : Stripe en direct, gratuit au panier.**
  Le direct part dans `method_B` (checkout Stripe, piège 12.16) ; le panier voit un total nul et
  finalise en gratuit. L'un des deux est faux.
- **C22 — Prix libre entre 0,01 et 0,49 € : refusé en direct, accepté au panier**
  (`validators.py:503`), puis refusé par Stripe (minimum 0,50 €) → « Checkout failed ».

### 1.2 Actions qui ne partent pas, en silence

- **C10 — Panier gratuit : une adhésion ne passe jamais par `trigger_A`.**
  `_finaliser_gratuit()` passe les lignes de `O` à `V` ; la machine à états
  (`signals.py:317`) n'a pas de transition `O → V`. `trigger_A` (`triggers.py:251`) ne tourne
  donc pas : **ni mail de confirmation, ni récompense monnaie** (`fedow_reward_enabled`), ni
  rattachement de l'utilisateur au lieu (`client_achat` : il n'apparaît pas dans l'admin), ni
  newsletter, ni envoi à LaBoutik. Le direct crée la ligne en `P` et tout part
  (`validators.py:970-981`).
- **C14 — Panier gratuit avec un billet `FREERES` : le mail part deux fois.**
  `method_F` sauve la réservation en `FA`, puis `_finaliser_gratuit()` la re-sauve en `FA` ; la
  transition `FA → FA` relance `reservation_paid` (`signals.py:346`) → deux `ticket_celery_mailer`
  et deux webhooks, envoyés avant le commit.
- **C18 — Des informations du formulaire se perdent au panier.**
  La case newsletter n'est pas lue (adhésion créée avec `newsletter=False`) ; le formulaire
  personnalisé n'est pas validé (champs requis, choix), la multi-sélection garde sa dernière
  valeur, et les réponses sont rangées par nom de champ alors que l'admin lit par libellé (elles
  n'y apparaissent pas) ; un code promo inconnu est ignoré sans message, alors que le direct le
  refuse.

### 1.3 Erreurs 500

- **C12 — Un connecté qui dépasse `event.max_per_user` obtient une erreur 500.**
  `services_panier.py:182` : `%(event)` sans `s` → `ValueError: unsupported format character`
  (vérifié en Python ; même faute dans `locale/fr/LC_MESSAGES/django.po`). `add_tickets_batch`
  n'attrape que `InvalidItemError` → 500. Au checkout, `revalidate_all()` avale l'erreur et
  affiche le message technique.
- **C17 — Une quantité non numérique fait une 500.** `add_tickets_batch` attrape
  `(TypeError, ValueError)` mais `Decimal("abc")` lève `InvalidOperation`
  (`views.py:6001-6004`).

### 1.4 Contrôles manquants

- **C2 — Ressource : l'adhésion obligatoire n'est jamais vérifiée côté serveur** (les deux
  parcours). Seul le gabarit masque le tarif (`book_form.html:128`).
- **C20 — `add_ticket` accepte un événement passé, non publié ou archivé**
  (`services_panier.py:413-418`).
- **C23 — Le panier ne contrôle pas `max_per_user` d'une adhésion**, le direct le fait
  (`validators.py:894-902`).
- **C24 — Ressource à prix libre, montant 0 € : le panier échoue au checkout, le direct passe**
  (`booking_engine.py:611`).

### 1.5 Ordre, affichage, parcours

- **C1 — Le « bug connu » d'Antoine est rattrapé au paiement, pour les billets.**
  `CHANGELOG/panier.md` décrit l'affichage (le tarif adhérent reste visible dans le panier après
  le retrait de l'adhésion). Au checkout, `revalidate_all()` rejoue `add_ticket()`, la règle
  « adhésion obligatoire » ne trouve plus l'adhésion → refus, billet retiré, message, aucune
  Commande. À prouver par un test **vert**. Côté ressources, voir C2.
- **C3 — Retirer puis remettre l'adhésion fait refuser un panier valide.** L'adhésion remise
  passe en fin de liste ; `revalidate_all()` rejoue dans l'ordre et revalide le billet avant.
- **C16 — Le bouton « retirer » peut retirer le mauvais item.** Il envoie l'index de la liste
  affichée (`panier_item.html:111`), qui saute les items dont le tarif, l'événement ou la
  ressource a disparu (`context_processors.py:78-114`) : les index ne correspondent plus.
- **C11 — Retour de Stripe sans payer : panier perdu, message inquiétant, Commande à vie en
  attente.** `cancel_url` = `success_url`. Le panier a été vidé au checkout ; le message dit
  « paiement en attente de validation » ; la Commande reste `PENDING`, ses adhésions en attente
  de paiement. Aucun code ne pose `Commande.EXPIRED`, `CANCELED` ni `DRAFT`.
- **C25 — Skin `faire_festival` : le badge du panier ne se met jamais à jour.** Son `shell.html`
  n'a pas d'élément `#panier-badge-nav` (présent dans `classic` et `V2`), cible du swap HTMX.
- **C26 — Gabarit billet : un code promo tapé peut être perdu** (les deux parcours). Un champ
  `promotional_code` par produit, avec le même `name` et le même `id`
  (`reservation.html:527-535`) : la dernière valeur (souvent vide) l'emporte. Visible en E2E
  seulement. **Corrigé (2026-09-22)** : un seul champ « Code promo » par événement
  (`Event.a_des_codes_promo()`), le serveur lisant un seul code par envoi. Prouvé par sonde :
  code tapé dans le premier de deux champs → 10 € facturés au lieu de 5 €, dans les deux
  parcours. En complément, le panier affiche la remise (prix barré, prix remisé, code) et un
  total égal au montant facturé (`PanierSession.code_promo_du_billet`, `montant_apres_remise`,
  même calcul que `get_or_create_price_sold` ; billets seulement, comme le paiement).
- **C27 — Événement avec un produit `FREERES` et un produit `BILLET`** : `method_F` passe la
  réservation au statut gratuit (`FA`) même quand un produit payant l'accompagne. `CREATED → FA`
  appelle `reservation_paid` : webhook « réservation », billets activés, mail des billets, AVANT
  tout paiement. Mesuré avant le retour de Stripe (les deux ordres de produits) :
  - direct : billets remis `N` par `get_checkout_stripe`, mais mail et webhook déjà demandés
    (en réel, la tâche mail passe ensuite la réservation `V` sans paiement) ;
  - panier, produit payant traité en premier : réservation `FA`, **les deux billets actifs**
    et mail demandé, sans paiement ;
  - panier, produit gratuit traité en premier : après paiement, billets toujours `N`
    (`FA → PAID` n'existe pas).
  **Corrigé (accord du mainteneur, avis Fable, relectures Opus + Fable)** : `method_F` ne pose
  le statut gratuit que si le `TicketCreator` décide lui-même du paiement (`create_checkout`,
  parcours direct et API) ET que tous les produits de la réservation sont `FREERES`. Sinon le
  paiement décide : en direct, le bloc final de `TicketCreator.__init__` ; au panier, la
  Commande entière (`_finaliser_gratuit` si gratuite, le paiement sinon — le panier appelle
  un `TicketCreator` par prix libre, aucun ne voit tous les produits). Le signal de paiement
  (`set_ligne_article_paid`) valide aussi les réservations de la Commande sans ligne de vente
  (réservations 100 % gratuites d'une Commande payante). Les billets gratuits partent avec
  les billets payés, dans un seul envoi, et seulement après le paiement ; si le paiement ne
  passe pas, rien n'est actif ni envoyé (la réservation reste en attente, comme toute
  réservation payante abandonnée, C11). Caisse (`paid_externally`) : les billets gratuits
  d'une vente mixte sont activés à la fin de `TicketCreator.__init__`. Tests :
  `test_un_evenement_avec_un_produit_gratuit_et_un_*` (prix fixe, prix libre, prix libre à
  0 €, les deux parcours, les deux ordres), réservation gratuite réservée aux adhérents
  (`test_commande_service.py`), vente en caisse mixte (API v2).

### 1.5bis Découverts pendant l'écriture des tests

- **C28 — Parcours direct : la limite par personne ne compte pas la somme « déjà acheté +
  demandé ».** `ReservationValidator` compare la base au maximum, puis la demande seule au
  maximum (`validators.py:643-687`). Maximum 2, 1 billet déjà acheté, demande de 2 : accepté
  (3 billets). Le panier, lui, refuse. **Corrigé** (décision 8) : événement, produit et
  tarif comptent « déjà pris + demandé », comme le panier.
- **C29 — Gabarit `booking/views/book.html` absent.** Référencé 4 fois
  (`booking/views.py:567, 664, 755`, `BaseBillet/views.py` dans `PanierMVT.add_resource`), il
  n'existe pas : un formulaire de ressource refusé et envoyé sans HTMX (JavaScript désactivé)
  donne une erreur 500. Le front, qui poste en HTMX, prend l'autre branche (partial en 422).
  **Classé (décision du mainteneur, 2026-09-22)** : inatteignable par un parcours normal (le
  formulaire s'ouvre par `htmx.ajax`, son adresse n'est jamais affichée ; tous les envois sont
  en `hx-post`). Seuls une adresse tapée à la main, un robot ou un JavaScript en panne y
  mènent. Rien n'est modifié ; le test qui le prouvait est retiré. Le gabarit a été supprimé
  le 2026-07-13 (commit `c687c0ad`).
- **C30 — `booking/tests/` est cassé.** Sa fixture crée des `Resource` sans produit, alors que
  ce champ est devenu obligatoire : 31 échecs et 1 erreur, tous `NotNullViolation` sur
  `product_id`. Invisible parce que `make test` ne lance que `tests/pytest/`.
- **C31 — La récompense monnaie d'une adhésion part avant le commit.** `trigger_A` envoie
  `refill_from_lespass_to_user_wallet_from_price_solded` par `.delay()` (pas `on_commit`) ; la
  tâche attend 1 s puis relit la ligne, sans nouvel essai en cas d'échec. Si la transaction
  n'est pas validée à temps, la récompense est perdue. **Corrigé** (décision 9) : récompense
  et envoi à LaBoutik en `transaction.on_commit`.
- **Trouvés à la relecture Opus et corrigés** : API v2, billet « payant » à 0 € → deux lignes
  de vente (régression de C21) ; `validate_new_booking` acceptait un tarif dépublié ou un
  produit archivé (le panier refusait) ; au panier, un code promo lié à un produit non choisi
  était ignoré en silence (le direct refuse) ; événement « réservation gratuite » + billet à
  0 € : billets remis inactifs (régression de C21, test P2ter).
- **Trouvés à la relecture « prêt pour la prod » (Opus + Fable) et corrigés** :
  - quantité démesurée (`1e999999999`) : un worker bloqué plus de 20 s, sans compte en
    direct ; `Infinity` → erreur 500 au panier. Quantité bornée à `QUANTITE_MAXIMUM_PAR_TARIF`
    (9 999), contrôlée avant `int()`, au panier et en direct ;
  - panier : le premier code promo trouvé valait pour tout l'événement → un `TicketCreator`
    par code promo ;
  - panier : un montant saisi restait facturé sur un tarif repassé en prix fixe ;
  - API v2 : réservation gratuite + billet à 0 € → la ligne de la réservation gratuite
    manquait (correction de la double ligne trop large) ;
  - billets à 0 € : leurs lignes passent par « payée » (`trigger_B`), la vente part à
    LaBoutik (décision 10).
- **Trouvés à la relecture finale (Opus + Fable) et corrigés** :
  - quantité très négative (`-1e999999999`) : elle passait la borne et bloquait le serveur
    (direct ouvert sans compte) → borne dans les deux sens, par comparaisons (`abs()` sur un
    `Decimal` géant lève `decimal.Overflow`) ;
  - SEPA encore proposé pour une Commande avec une réservation gratuite (sans ligne de vente)
    et une adhésion payante → `contains_tickets` regarde aussi `commande.reservations` ;
  - `trigger_B` (envoi à LaBoutik d'un billet, désormais aussi à 0 € dans la transaction du
    panier) → `transaction.on_commit`, comme `trigger_A`.
- **C20 corrigé** (décision 7) : `Event.est_termine()` (fin dépassée ; sans date de fin :
  début + 24 h) et `Event.n_est_plus_en_vente()` (archivé ou terminé), appliqués au panier
  (ajout et paiement) et au parcours direct ; l'API v2 et la caisse n'appliquent que
  `est_termine()`. Un événement dépublié reste réservable. Le champ `event` de
  `ReservationValidator` filtrait `datetime >= now - 1 jour`, calculé UNE fois au chargement
  du module : la limite dérivait, et un festival commencé il y a plus d'un jour devenait
  impossible à réserver. Filtre retiré.
- **C25 corrigé** (décision 6) : lien et compteur du panier dans le menu Faire Festival.

### 1.6 Code mort ou latent (à signaler, pas à tester)

- **C4 — Code promo « global » du panier** : `set_promo_code()`, `clear_promo_code()`,
  `promo_code()`, les actions `/panier/promo_code/` : aucun gabarit ne les appelle et
  `materialiser()` les ignore.
- **C6 — `usage_limit` d'un code promo jamais appliqué** : `usage_count` n'est incrémenté nulle
  part (les deux parcours).
- **C7 — Code promo sur adhésion ou ressource** : noté sur la ligne, jamais déduit ; aucun
  formulaire ne le propose.
- Détails : docstring d'`add_resource` copiée d'`add_membership` ; `add_resource` stocke la
  chaîne `"None"` dans `custom_amount` ; commentaire faux `services_panier.py:229` (« toutes
  users confondues ») ; un panier de billets seuls d'un utilisateur sans prénom ni nom donne une
  Commande sans nom.

### 1.7 Pièges pour écrire les tests (découverts à la lecture)

| # | Piège | Parade |
|---|---|---|
| T1 | Créer un `Product` adhésion appelle **Fedow en HTTP**, hors transaction (`signals.py:427`) : le rollback n'annule pas l'asset créé chez Fedow | la fabrique patche `BaseBillet.signals.AssetFedow` |
| T2 | Le catalogue Stripe (`stripe.Product.retrieve/create`, `stripe.Price.create`) est appelé pour toute ligne non `FREERES`, **même à 0 €** ; `mock_stripe` ne le patche pas | patch du catalogue dans tous les nouveaux fichiers ; « aucun appel Stripe » s'asserte aussi sur `stripe.Price.create` |
| T3 | Sous `schema_context`, `trigger_A` plante en silence (`client_achat.add(FakeTenant)`) : ligne bloquée en `P` | toujours `tenant_context` ou le client de test |
| T4 | `revalidate_all()` **retourne** la liste des erreurs, retire les items invalides, et attrape `Exception` sans savepoint | les tests lisent la liste ; une erreur SQL y serait masquée |
| T5 | `on_commit` ne part pas sous rollback | fixture `django_capture_on_commit_callbacks` de pytest-django |
| T6 | Tâches Celery (`.delay()`) : le worker recevrait des lignes qui n'existent pas | `patch.object(Task, "apply_async", autospec=True)` dans les seuls nouveaux fichiers ; on vérifie les tâches demandées |
| T7 | `Configuration` est en cache (django-solo) : un `save()` ou `update()` de test fuit vers le serveur live ; modifier une instance ne sert à rien | `patch.object(Configuration, "get_solo", return_value=<instance jamais sauvée>)` |
| T8 | Les fixtures de session `admin_client`, `api_client` ne survivent pas au rollback (session de `force_login` annulée) | un client et un `force_login` par test |
| T9 | Le client de test rend les messages en **français** (`LANGUAGE_CODE='fr'`) | asserter le `level` du toast et l'état en base, ou `HTTP_ACCEPT_LANGUAGE="en"` |
| T10 | `materialiser()` ne pose `SERIALIZABLE` que hors transaction : jamais sous le wrapper | pas de test (même choix que `booking_engine.py`) |
| T11 | Une ligne de vente garde en mémoire l'objet adhésion de sa création : un trigger qui le sauve plus tard écrase les statuts posés entre-temps | recharger l'objet (`refresh_from_db()`) avant de relancer la machine à états |
| T12 | Un `xfail` passe dès que le test échoue, pour **n'importe quelle** raison | vérifier chaque cause avec `--runxfail` avant de livrer |
| T13 | Certaines vues prennent une branche non-HTMX que le front n'utilise jamais | poster les formulaires avec l'en-tête `HTTP_HX_REQUEST` |

## 2. Décisions à prendre

### 2.1 Corriger dans la session, ou seulement prouver et noter ?

Chaque ligne aura d'abord son test rouge. Tri par effet sur l'utilisateur.

| Constat | Effet | Coût de correction | Recommandation |
|---|---|---|---|
| C5 code promo sur tous les produits | argent (sous-facturation) | `TicketCreator` : ne remiser que le produit du code ; touche le direct | **corriger** |
| C13 prix libre ajouté deux fois | argent (sur-facturation) | montant par item dans `materialiser()` | **corriger** |
| C15 tarif d'une autre ressource | argent (tarif gratuit détourné) | une vérification dans `validate_new_booking()` | **corriger** |
| C10 panier gratuit sans `trigger_A` | mail, récompense monnaie, admin | lignes passées par `P` comme le direct | **corriger** |
| C14 double mail billet gratuit | mail en double | ne pas re-sauver une réservation déjà `FA` | **corriger** |
| C12 erreur 500 `%(event)` | 500 | un caractère (+ le `.po`) | **corriger** |
| C17 quantité non numérique | 500 | ajouter `InvalidOperation` | **corriger** |
| C16 mauvais item retiré | mauvais achat | index stable côté serveur | **corriger** |
| C2 adhésion obligatoire ressource | droit contourné | vérification serveur partagée | **corriger** |
| C3 adhésion retirée puis remise | refus à tort | rejouer les adhésions en premier | **corriger** |
| C18 newsletter, formulaire, code inconnu | données perdues | lire `newsletter`, valider comme le direct | corriger newsletter et code inconnu ; formulaire : noter |
| C21 `BILLET` à 0 € | incohérence | gratuit partout : le direct ne passe plus par Stripe à 0 € | **corriger** (décision 2) |
| C19 stocks, C20, C22, C23, C24, C25, C26, C27, C11 | divers | variable | **prouver et noter** (chantiers suivants) |
| C4, C6, C7 | code mort / latent | — | **noter seulement** |

### 2.2 Décisions du mainteneur (2026-09-21)

1. **Tableau 2.1** : recommandations suivies (« corriger » et « prouver et noter » tels
   qu'écrits).
2. **C21 — billet `BILLET` à 0 €** : **gratuit partout**. Un total à 0 € ne passe jamais par
   Stripe, avec ou sans panier. La correction touche le parcours direct (`TicketCreator`).
3. **E2E** : les fixtures manquantes sont ajoutées à `demo_data_v2._seed_e2e_fixtures` et à
   `tests/e2e/conftest.py::e2e_slugs` (seed idempotent à relancer).
4. **C11 — retour de Stripe sans payer** : comportement actuel figé par un test ; la décision
   produit attend le **panier en base** (`TECH_DOC/SESSIONS/TODO/`).

### 2.2bis Décisions du mainteneur après le chantier (2026-09-21)

5. C27 : corriger (fait) — billets gratuits et payants envoyés ensemble, après le paiement.
6. C25 : ajouter le lien et le badge du panier au menu du skin Faire Festival.
7. C20 : refuser un événement terminé ou archivé dans les DEUX parcours (panier : ajout et
   paiement ; direct). « Terminé » = fin de l'événement dépassée ; sans date de fin : début
   + 24 h. Un événement DÉPUBLIÉ reste réservable par lien direct. API v2 et caisse : même
   règle de date, sans contrôle archivé (réponses du mainteneur après la relecture finale).
8. C28 : le parcours direct additionne « déjà acheté + demandé » pour les limites par
   personne (événement, produit, tarif), comme le panier.
9. C31 : la récompense monnaie et l'envoi de la vente à LaBoutik partent après la validation
   en base (`transaction.on_commit`) dans `trigger_A`.
10. Billets à 0 € : envoyés à LaBoutik comme les autres ventes. Leurs lignes passent par
    « payée » (déclencheur `trigger_B` : envoi à LaBoutik, puis « validée »), comme les
    adhésions gratuites (C10).
11. C19 : un stock compte vendu + en cours de paiement + demandé ; une adhésion à validation
    manuelle en attente (`AW`) occupe une place.
12. Paiement en cours : **30 minutes partout, sans réglage par lieu** (constante
    `DUREE_D_UN_PAIEMENT_EN_COURS`, `BaseBillet/models.py`) : jauge et stock des billets, stock
    des adhésions, créneaux de ressource, blocage des réservations qui se chevauchent,
    confirmation d'une réservation gratuite par email, compteur de la caisse LaBoutik, et
    expiration de la session Stripe (30 min + 1 min de marge : Stripe refuse moins de 30 min).

### 2.3 Tranché sans vous (dites-le si vous n'êtes pas d'accord)

- **Anciens tests V2** : portés en les adaptant (§3).
- **Ressources** : dans le périmètre (vous les avez citées).
- **C4, code promo global** : pas testé, signalé comme code mort.
- **Isolation** : `@pytest.mark.django_db` (rollback vérifié dans le code de pytest-django 4.12,
  déjà utilisé par ~80 fichiers ; piège 12.3).
- **SERIALIZABLE** : pas de test (T10).
- **`booking/tests/` hors de `make test`** : signalé dans le rapport de fin, pas modifié ici.
- **Mutations** : appliquées par script, restaurées dans un `finally`, empreintes vérifiées
  (votre règle de session).

## 3. Anciens tests V2

Lus par `git show V2:<chemin>`. Classement **à la lecture**, confirmé en les exécutant.
Légende : **V** valide tel quel · **A** à adapter · **R** rouge attendu (bug) · **X** abandonné.

| Fichier V2 | Tests | V | A | R | X |
|---|---|---|---|---|---|
| `test_panier_session.py` | 35 | 18 | 12 | 1 | 4 |
| `test_panier_mvt.py` | 13 | 6 | 4 | 0 | 3 |
| `test_panier_batch.py` | 5 | 5 | 0 | 0 | 0 |
| `test_commande_service.py` | 5 | 2 | 3 | 0 | 0 |
| `test_panier_context_processor.py` | 4 | 3 | 1 | 0 | 0 |
| `test_commande_post_save_paid.py` | 4 | 4 | 0 | 0 | 0 |
| `test_commande_model.py` | 12 | 3 | 0 | 0 | 9 |
| **Total pytest** | **78** | **41** | **20** | **1** | **16** |
| `tests/e2e/test_panier_flow.py` | 5 | 0 | 5 | 0 | 0 |

Raisons :
- **A** : tout test qui crée un produit adhésion (T1, patch Fedow) ; `revalidate_all()` qui
  retourne une liste (T4) ; `materialiser()` qui retourne `(commande, succès)` ; le test de
  chevauchement qui fait `config.save()` (T7) ; trois assertions tautologiques dans
  `test_panier_mvt.py` (`GET /panier/`, checkout gratuit, profil incomplet).
- **R** : « DB + panier dépasse `event.max_per_user` » (C12).
- **X** : 4 + 2 tests du code promo global (C4) ; le test de l'endpoint `update_quantity`
  supprimé ; 9 tests du modèle `Commande` qui testent l'ORM de Django. On garde les 3 qui
  protègent un choix (utilisateur en `PROTECT`, un paiement = une Commande, code promo en
  `SET_NULL`).
- **E2E** : 4 des 5 passent en pytest (client de test : `HX-Redirect`, `then=checkout`, vider,
  tarif débloqué). Seul le parcours complet gratuit reste en E2E (E1).

## 4. Matrice de couverture (panier)

**V2** = porté · **N** = nouveau · **R** = nouveau, rouge attendu.

| Fonction | Scénarios | Source |
|---|---|---|
| `add_ticket` | stockage ; refus : qty, event, tarif, publication, archive, hors événement, **événement complet**, **tarif épuisé** | V2 + N |
| `add_ticket` | événement passé / non publié / archivé | R (C20) |
| `add_ticket` | prix libre : manquant, sous le minimum, trop haut | N |
| `add_ticket` | code promo : inconnu, inactif, épuisé, autre produit, valide | N |
| `add_ticket` | chevauchement : autre événement du panier, réservation en base (définitive / < 15 min) | V2 + N |
| `add_ticket` | adhésion obligatoire : absente, dans le panier, **active en base**, **expirée** | V2 + N |
| `validate_ticket_cart_limits` | 3 × `max_per_user` anonyme ; jauge ; `under_purchase` | V2 |
| `validate_ticket_cart_limits` | connecté : base + panier > `event.max_per_user` | R (C12) |
| `add_membership` | stockage, refus (récurrent, manuel, doublon, non-adhésion), prix libre, prénom/nom | V2 + N |
| `add_membership` | `max_per_user` de l'adhésion | R (C23) |
| `add_resource` | stockage, refus (catégorie, récurrent, manuel, créneau indisponible, créneau déjà au panier), estimation | N |
| `add_resource` | tarif d'une autre ressource ; tarif adhérent sans adhésion | R (C15, C2) |
| `revalidate_all` | tarif dépublié, jauge saturée, tarif épuisé entre l'ajout et le paiement → erreurs retournées, item retiré, items valides gardés | V2 adapté + N |
| `revalidate_all` | adhésion retirée → billet adhérent refusé ; retirée puis remise | N vert (C1) ; R (C3) |
| `calcul_total_centimes` | billets, adhésion, prix libre, ressource | V2 + N |
| `remove_item`, `clear`, `count`, `adhesions_product_ids` | | V2 |
| `PanierMVT` droits | `list`/`badge` anonymes ; écritures → 403 anonyme **et non activé** | V2 + N |
| `PanierMVT` HTMX | toast `HX-Trigger` (niveau), swap `#panier-content`, badge | V2 + N |
| `add_tickets_batch` | plusieurs tarifs, event inconnu, aucune quantité, rollback, uuid ou slug, code promo filtré, `then=checkout` | V2 + N |
| `add_tickets_batch` | quantité non numérique | R (C17) |
| `add_membership` (vue) | champ `price`, `custom_amount_<uuid>`, `then=checkout`, refus récurrent / manuel propre | V2 + N |
| `remove` (vue) | item disparu avant l'item retiré | R (C16) |
| `checkout` | panier vide ; gratuit → `HX-Redirect` + panier vidé ; payant → URL Stripe ; revalidation en échec → messages + retour `/panier/` ; **double checkout** → une seule Commande ; **Stripe indisponible** → aucune Commande, panier intact ; prénom/nom repris de l'item | V2 adapté + N |
| `panier_context` | vide, billet, adhésion, ressource, repli sur erreur | V2 + N |
| rendu | navbar des skins `classic`, `V2`, `faire_festival` contient `#panier-badge-nav` | R (C25) |
| `materialiser` phase 1 | adhésion `WP`, montant, prix libre, options, formulaire, prénom/nom | N |
| `materialiser` phase 2 | 1 réservation par événement, 2 tarifs groupés | V2 adapté + N |
| `materialiser` phase 2 | code promo limité à son produit ; prix libre ajouté deux fois | R (C5, C13) |
| `materialiser` phase 3 | booking créé, rattaché à la Commande, ligne comptable | N |
| `materialiser` paiement | un seul `Paiement_stripe` (`reservation=None`, `booking=None`), lignes `U`, Commande `PENDING` ; SEPA proposé si adhésions seules, refusé sinon | N |
| `materialiser` gratuit | Commande `PAID`, adhésion `ONCE` + deadline, réservation `FA`, booking `FA`, lignes `V` + `FREE`, aucun appel Stripe | V2 adapté + N |
| `materialiser` gratuit | mail et récompense demandés (C10) ; un seul mail billet (C14) | R |
| `materialiser` | panier vide ; rollback complet sur exception | V2 |
| Paiement | Commande mixte : retour → paiement `V`, lignes `V`, réservations `P`, billets `K`, adhésion `ONCE`, booking `PAID_BY_USER`, Commande `PAID` | N |
| Paiement | retour sans payer (session ouverte / expirée) : comportement actuel figé | N (C11) |
| Signal `PAID` | `V` → Commande `PAID`, sans Commande, autre statut, idempotence | V2 |

## 5. Parité avec et sans panier

### 5.1 Ce qui existe déjà pour les parcours directs

- La vue front **`EventMVT.reservation` n'est jamais appelée en pytest** (API v2 ou
  `ReservationValidator` seulement ; front en E2E).
- **`update_checkout_status()` n'est appelé que pour des adhésions** ; aucun billet n'est mené
  au retour de paiement en pytest. Le webhook Stripe n'est jamais appelé en pytest.
- **Aucun test de la vue `booking-book`**, payante ou gratuite.
- Les tests d'adhésion directs vérifient peu (statut, deadline, ligne, mail rarement contrôlés).
- Existant solide : validation manuelle (cycle complet en `make e2e-stripe`), prix libre
  d'adhésion, renouvellement récurrent (E2E), récompense monnaie (E2E, paiement en espèces).

### 5.2 Les cas de parité

Fichier `tests/pytest/test_parite_avec_sans_panier.py`, paramétré
`["sans_panier", "avec_panier"]` comme `test_stripe_refund.py`. Même utilisateur connecté,
même produit ; seul le bouton change (vrai formulaire front par le client de test, ou
`/panier/add/…` + `/panier/checkout/`), puis la vraie vue de retour du parcours, avec
`mock_stripe`. États attendus après un paiement simulé (lecture du code, confirmés par le
premier test) : paiement `V`, lignes `V`, réservation `P` (elle ne passe `V` que quand la tâche
de mail tourne), billets `K`, adhésion `ONCE` + deadline, booking `PAID_BY_USER`.

| # | Cas | Attendu |
|---|---|---|
| P1 | billet payant | vert |
| P2 | billet gratuit `FREERES` : réservation `FA`, billets `K`, **aucune** ligne (dans les deux parcours), aucun appel Stripe | panier **rouge** (C14 : mail demandé deux fois) |
| P3 | billet prix libre : montant, minimum | vert ; 0,01-0,49 € divergent (C22) |
| P4 | billet + code promo, événement à 2 produits | **rouge des deux côtés** (C5) ; code inconnu : panier rouge (C18) |
| P5 | tarif adhérent : sans adhésion refusé, adhésion active acceptée, expirée refusée | vert |
| P6 | limites `max_per_user` et jauge | panier connecté **rouge** (C12) ; « 1 en base, max 2, demande 2 » : le direct accepte, le panier refuse → à trancher avec C12 |
| P7 | tarif épuisé (`Price.stock`) ; quantité demandée > reste | vert ; reste **rouge des deux côtés** (C19) |
| P8 | adhésion payante : `ONCE`, deadline, contribution, ligne `V`, mail demandé, `client_achat` | vert |
| P9 | adhésion gratuite : idem, paiement `FREE` | panier **rouge** (C10) |
| P10 | adhésion prix libre : contribution = montant saisi | vert |
| P11 | adhésion avec récompense monnaie : la tâche est exécutée avec `FedowAPI` simulé, montant et monnaie vérifiés | payante vert ; gratuite panier **rouge** (C10) |
| P12 | adhésion à validation manuelle : direct `AW`, pas de checkout ; panier refus propre | vert |
| P13 | adhésion récurrente : direct checkout en mode abonnement ; panier refus propre | vert |
| P14 | SEPA : proposé pour une adhésion seule, refusé avec billet ou ressource | vert |
| P15 | ressource payante : `PAID_BY_USER`, ligne `V`, montant = heures × tarif | vert |
| P16 | ressource gratuite : panier ligne `V` `FREE` ; direct ligne reste `O` | divergent → à noter |
| P17 | ressource : tarif adhérent sans adhésion ; tarif d'une autre ressource | **rouge des deux côtés** (C2, C15) |
| P18 | double retour de paiement (retour puis rechargement) : rien en double, `paid_at` inchangé | vert |
| P19 | adhésion : `max_per_user` ; stock du tarif | panier **rouge** (C23) ; stock **rouge des deux côtés** (C19) |
| P20 | formulaire : newsletter, champs requis, multi-sélection | panier **rouge** (C18) |

La course « webhook et retour navigateur en même temps » n'est pas testable sous le wrapper :
elle reste un risque noté. Le vrai versement de jetons Fedow est vérifié une fois, en E2E.

## 6. Stratégie technique

### 6.1 Isolation

`@pytest.mark.django_db` : chaque test tourne dans une transaction annulée à la fin (pytest-django
4.12 enveloppe le test dans un `django.test.TestCase`). Les `atomic` de `materialiser()` et de
`validate_new_booking()` deviennent des savepoints. Parades : tableau T1-T10 (§1.7).

Les E2E tapent le serveur live, sans rollback : ils utilisent les fixtures seedées
`E2E Test — …`, ne suppriment rien (piège 12.4 : jamais de `.delete()` de queryset sur des
modèles riches en FK), et vident seulement le panier (session).

### 6.2 Fichiers

Nouveaux (autorisés à `ruff check --fix` et `ruff format`) :

| Fichier | Contenu |
|---|---|
| `tests/pytest/fabriques_panier.py` | fonctions explicites : `creer_evenement_avec_tarif()`, `creer_adhesion()` (patch Fedow), `creer_ressource_avec_tarif()`, `requete_avec_session(user)`, `client_connecte(user)` ; patchs du catalogue Stripe, de Celery et de `get_solo` |
| `tests/pytest/test_panier_session.py` | `PanierSession` et fonctions de validation |
| `tests/pytest/test_panier_mvt.py` | `PanierMVT` (dont l'ex-`test_panier_batch.py`) et rendu du badge |
| `tests/pytest/test_panier_context_processor.py` | `panier_context` |
| `tests/pytest/test_commande_service.py` | `materialiser()` et le paiement d'une Commande (dont l'ex-`test_commande_post_save_paid.py` et 3 tests du modèle) |
| `tests/pytest/test_parite_avec_sans_panier.py` | P1-P20 |
| `tests/e2e/test_panier_flow.py` | E2E |

Existants modifiés : le code de production pour les corrections décidées (§2.1) ;
`demo_data_v2.py` et `tests/e2e/conftest.py` si la question 3 est acceptée ; `tests/PIEGES.md`,
`CHANGELOG/panier.md` et un nouveau `CHANGELOG/2026-09-21-tests-panier.md` en clôture.
`tests/pytest/conftest.py` n'est pas modifié : la fixture `translation.deactivate()` (piège
10.5) est déclarée dans chaque fichier de test.

### 6.3 Règles `djc` et pièges

Skill `djc` + `GUIDELINES.md`. Pour ce chantier : tests atomiques aux noms verbeux en français,
commentaires bilingues qui expliquent le code tel qu'il est ; corrections en `ViewSet` /
`serializers.Serializer` / HTML + `HX-Trigger` ; texte source des `_()` en français, pas de
`makemessages` (nombre de chaînes signalé) ; `data-testid` ajouté à un gabarit si un E2E en a
besoin ; `ruff` complet sur les fichiers neufs seulement.

Pièges de `tests/PIEGES.md` qui changent une décision : 9.19 et 11.7 (retour de paiement, P18) ;
9.41 et 12.17 (jamais d'état final fabriqué par `create(status=…)` ou `.update()`) ; 10.1-10.9
(panier) ; 12.6 (`except Exception` qui avale : vérifier l'effet, pas l'absence d'erreur) ;
12.7 (HTMX n'échange pas le contenu sur 4xx) ; 12.10 (constantes, `'C'` = annulée) ; 12.16
(gratuit = `FREERES`) ; 12.13.quinquies (`stripe listen` qui meurt fausse une mutation) ;
12.14 (bouton « Pay » de Stripe) ; cache des singletons ; memcached (jamais pytest et Playwright
en parallèle) ; E2E rendus en anglais. Plus T1-T10 (§1.7), à ajouter à `PIEGES.md` en clôture,
avec deux mises au point : 9.45, 9.57 et 9.99 ne valent que **sans** la marque `django_db` ;
9.26 (`pytest.skip`) cède devant la règle « zéro skip silencieux ».

### 6.4 Couverture

`make coverage` (ajouté pour ce chantier : `pytest-cov` en dépendance de dev, configuration dans
`pyproject.toml`) lance la suite pytest sans Stripe réel, affiche le total, écrit `htmlcov/`, et
détaille des fichiers avec `FICHIERS="a.py,b.py"`. Seul le code exécuté dans le process pytest
compte (ni les tests qui appellent le serveur live en HTTP, ni les E2E).

Départ mesuré le 2026-09-21 sur la suite complète (1329 passed, 4 skipped, 6 min 47) :

| Fichier | Départ | Arrivée |
|---|---|---|
| **total du projet** | **52 %** | **55 %** |
| `BaseBillet/services_panier.py` | 28 % | 78 % |
| `BaseBillet/services_commande.py` | 53 % | 97 % |
| `BaseBillet/context_processors.py` | 44 % | 91 % |
| `BaseBillet/triggers.py` | 65 % | 78 % |
| `BaseBillet/signals.py` | 64 % | 78 % |
| `BaseBillet/validators.py` | 59 % | 66 % |
| `PaiementStripe/views.py` | 58 % | 59 % |
| `booking/booking_engine.py` | 21 % | 83 % |
| `booking/views.py` | 13 % | 31 % |

Arrivée mesurée le 2026-09-21 (1524 passed, 4 skipped, 19 xfailed, 9 min). Objectif de 90 %
atteint pour `services_commande.py`, pas pour `services_panier.py` (78 %) : le reste couvre
surtout des branches défensives et d'anciens formats de session.

`booking/booking_engine.py` est bas en partie parce que `booking/tests/` n'est pas lancé par
`make test`. `PanierMVT` vit dans `BaseBillet/views.py` (fichier de 6 000 lignes) : sa
couverture se lit dans `htmlcov/`, pas dans le pourcentage du fichier.

Objectif indicatif : au moins 90 % sur `services_panier.py` et `services_commande.py`, et une
hausse nette de `context_processors.py`, `booking/views.py` et `booking/booking_engine.py`.

Commande de mesure (à rejouer en clôture) :
`make coverage FICHIERS="BaseBillet/services_panier.py,BaseBillet/services_commande.py,BaseBillet/context_processors.py,BaseBillet/triggers.py,BaseBillet/signals.py,BaseBillet/validators.py,PaiementStripe/views.py,booking/booking_engine.py,booking/views.py"`

## 7. Plan par étapes

Chaque étape : tests écrits → vus passer → **vus échouer** (mutation ou bug) → `make test
ARGS="<fichiers>"`. Pour un bug à corriger (§2.1) : test rouge, correction, test vert, dans la
même étape. Suite complète (`make test`) à la fin des étapes 4, 6 et 7.

1. **Socle** : fabriques et patchs (T1, T2, T6, T7) ; 5 tests témoins (un par `add_*`,
   `revalidate_all`, `calcul_total_centimes`) ; vérification du rollback (un objet créé par un
   test n'existe plus après le run).
2. **`materialiser()` et paiement** (≈ 20 tests) : les phases, gratuit, rollback, Commande mixte
   jusqu'au retour de paiement, retour sans payer, double retour. C5, C10, C13, C14.
3. **Parité avec/sans panier** (P1-P20, ≈ 32 tests) : le cœur de la demande. C2, C15, C18,
   C19, C21, C22, C23.
4. **`PanierMVT` et `panier_context`** (≈ 30 tests) : droits, HTMX, double checkout, Stripe
   indisponible, non activé, badge des skins ; ex-E2E passés en pytest. C12, C16, C17, C25.
5. **`PanierSession` en détail** : port des tests V2 restants, cas fins de `add_*` et
   `revalidate_all`. C1, C3, C20.
6. **Corrections restantes** et suite complète.
7. **E2E** (après la question 3) — chaque parcours joué d'abord à la main dans Chrome
   (`https://lespass.tibillet.localhost/`) pour relever les vrais sélecteurs ; accord du
   mainteneur avant tout checkout dans Chrome :

   | # | Parcours | Lancement |
   |---|---|---|
   | E1 | billet gratuit : ajout → badge → toast → `/panier/` → checkout → `my_reservations` | `make e2e` |
   | E2 | anonyme clique « Ajouter au panier » → panneau de connexion | `make e2e` |
   | E3 | tarif récurrent → « Ajouter au panier » → toast d'erreur, panier inchangé | `make e2e` |
   | E4 | ressource : créneau ajouté → affiché « dans le panier » → checkout | `make e2e` |
   | E5 | panier mixte adhésion + billet payant → **vrai paiement** → Commande `PAID`, billets actifs | `make e2e-stripe` |
   | E6 | adhésion avec récompense monnaie **par le panier** → vrai paiement → solde Fedow crédité | `make e2e-stripe` |

8. **Clôture** : mutations (§8, mainteneur prévenu avant et après) ; `make test-stripe` et
   `make e2e-stripe` complets ; `make coverage` (arrivée, §6.4) ; relecture Opus du code ;
   `tests/PIEGES.md` ; CHANGELOG ; `CHANGELOG/panier.md` (bugs connus, « À tester »).

## 8. Vérification par mutation

Appliquée par script, restaurée dans un `finally`, empreinte `sha256` vérifiée après. Le
serveur live recharge le code muté : le mainteneur est prévenu avant et après chaque série.
Une mutation qui fait rougir une **autre** assertion que celle visée → vérifier l'environnement
(`stripe listen`, serveur) avant de conclure.

| # | Mutation | Test qui doit rougir |
|---|---|---|
| M1 | retirer la règle « adhésion obligatoire » de `add_ticket` | C1, refus sans adhésion |
| M2 | retirer le panier du calcul de jauge | jauge + panier |
| M3 | retirer le contrôle de doublon d'adhésion | doublon |
| M4 | `revalidate_all` n'ajoute plus les erreurs à la liste | tarif dépublié, jauge saturée |
| M5 | une réservation par item au lieu d'une par événement | groupage par événement |
| M6 | inverser `accept_sepa` | P14 |
| M7 | `_finaliser_gratuit` ne passe plus la Commande en `PAID` | gratuit |
| M8 | retirer `panier.clear()` du checkout | panier vidé |
| M9 | retirer le rollback de `add_tickets_batch` | rollback du lot |
| M10 | `list`/`badge` en `IsAuthenticated` | accès anonyme |
| M11 | supprimer le signal `commande_mark_paid_when_paiement_valid` | Commande mixte payée |
| M12 | retirer `out_of_stock` de `add_ticket` | tarif épuisé |
| M13 | faire lever `stripe.checkout.Session.create` | Stripe indisponible : aucune Commande |
| M14+ | une mutation par correction faite (la retirer → son test rougit) | tests des bugs corrigés |

## 9. Risques

- **Chaîne de paiement mockée** (étape 2) : `update_checkout_status()` sur un `MagicMock`
  (`expires_at`, `payment_method_types`) et les triggers Celery peuvent coûter du temps. Les
  états attendus du §5.2 sont confirmés par le premier test, pas supposés.
- **Classement V2 à la lecture** : d'autres « V » peuvent se révéler rouges (comme C12).
- **Nombre de bugs** : les corrections décidées font grossir la session ; les rouges « à
  noter » ne sont pas corrigés ici.
- **Skin V2** pour les E2E : préférer `data-testid` et rôles ARIA aux classes CSS.
- **Concurrence** : deux checkouts simultanés du même panier (deux onglets) ne sont pas
  testables en pytest ; seul `data-loading-disable` protège côté navigateur. Le panier en base
  est la vraie parade.
- **Effet de bord SEO** : créer un événement pose un verrou de reconstruction SEO dans
  memcached, même quand la tâche est interceptée ; la reconstruction du serveur live est
  retardée de quelques minutes (déjà le cas des tests qui créent des événements).

## 10. Avancement (2026-09-21)

### Fait

| Étape | Résultat |
|---|---|
| 0. Baseline | `make test` : 1329 passed, 4 skipped (Stripe réel), 0 échec. Couverture de départ : §6.4 |
| Outillage | `make coverage` (`pytest-cov` en dépendance de dev, `[tool.coverage.*]` dans `pyproject.toml`, suite `couverture` dans `scripts/lancer_tests.sh`) |
| 1. Socle | `tests/pytest/fabriques_panier.py` ; rollback `django_db` prouvé (0 objet de test restant) |
| 2. `materialiser` + paiement | `test_commande_service.py` ; C5, C10, C13, C14 corrigés |
| 3. Parité | `test_parite_avec_sans_panier.py` ; C2, C12, C15, C18 (code inconnu, newsletter), C21, C27 corrigés ; C19, C22, C23, C24, C28, C29, P16 en xfail |
| 4. Vues + context processor | `test_panier_mvt.py`, `test_panier_context_processor.py` ; C16, C17 corrigés ; C25 en xfail |
| 5. `PanierSession` détaillé | `test_panier_session.py` complété ; C3 corrigé ; C1 prouvé (vert) ; C20 en xfail |
| 7. E2E | `tests/e2e/test_panier_flow.py` E1 à E6 verts (E5, E6 en `make e2e-stripe`) ; fixtures ajoutées à `demo_data_v2._seed_e2e_fixtures_du_panier` et `e2e_slugs` (facultatives : les autres E2E ne dépendent pas d'elles) |
| 8. Relecture Opus + avis Fable | Intégrée : API v2 (double ligne), `validate_new_booking` (tarif dépublié / produit archivé), code promo d'un produit non choisi au panier, P2ter, `raises=` sur chaque xfail, commentaires périmés, `set -e` du script de couverture |
| 8. Mutations | pytest : 36/36 détectées après C27 (`mutations_panier.py`, restauration vérifiée par sha256) ; E2E : E3 et E6 détectées |
| 8. C27 | Corrigé dans `method_F` ; `make test` : 1533 passed, 4 skipped, 14 xfailed, 0 échec ; E2E du panier 6/6 |
| 9. Relecture « prêt pour la prod » | Opus + Fable ; corrigés : C27 au panier (prix libre, adhésion du panier), quantité démesurée, code promo par produit, prix libre redevenu fixe, ligne API v2, caisse mixte, billets à 0 € vers LaBoutik ; E1 renforcé |
| 10. Décisions C25, C20, C28, C31 | Corrigées (§2.2bis) ; `make test` : 1596 passed, 4 skipped, 9 xfailed, 0 échec ; `make test-stripe` : 1601 passed ; mutations pytest 56/56 ; mutation E2E de E1 détectée |
| 11. Relecture finale Opus + Fable | Corrigés : quantité très négative, SEPA avec réservation gratuite, `trigger_B` en `on_commit` ; C20 révisé selon les réponses du mainteneur (sans fin : + 24 h, dépublié réservable, API/caisse : règle de date seule) |
| 12. Clôture finale (2026-09-22) | `make test` : 1609 passed, 4 skipped, 9 xfailed, 0 échec ; E2E du panier 6/6 ; mutations pytest 62/62, empreintes vérifiées |
| 8. Clôture (avant C27) | `make test` : 1524 passed, 4 skipped, 19 xfailed, 0 échec ; `make test-stripe` : 1527 passed, 19 xfailed, 1 échec hors sujet (`test_events_list` : `ReadTimeout` du serveur live, passe seul en 9,7 s pour une limite de 10 s) ; `make e2e-stripe` sur `test_panier_flow.py` : 6/6 ; couverture d'arrivée : §6.4 |

Chaque `xfail` a été vérifié avec `--runxfail` : il échoue pour la raison écrite dans sa marque,
et `raises=` fixe l'exception attendue.

### Fichiers de production modifiés

`BaseBillet/services_panier.py` (C3, C12, C15/C2 dans `add_resource`, newsletter, méthode
`_adhesion_obligatoire_en_base_ou_dans_le_panier`, C20), `BaseBillet/services_commande.py`
(C10, C13, newsletter, code promo par produit, prix libre redevenu fixe, `_finaliser_gratuit`
seul juge du statut gratuit au panier, billets à 0 € via « payée »), `BaseBillet/validators.py`
(C5, C21 : paiement décidé une fois par réservation, `valider_une_reservation_a_zero_euro` ;
C27 dans `method_F` ; caisse mixte ; quantité bornée ; C20 ; C28), `BaseBillet/models.py`
(`Event.n_est_plus_en_vente`), `BaseBillet/signals.py` (réservations de la Commande validées
au paiement), `BaseBillet/triggers.py` (C31), `BaseBillet/views.py` (C17, C18 code inconnu,
code d'un produit non choisi, newsletter, quantité bornée), `BaseBillet/context_processors.py`
+ `panier_item.html` (C16), `pages/templates/pages/faire_festival/partials/navbar.html` (C25),
`booking/booking_engine.py` (C2, C15, tarif dépublié / produit archivé dans
`validate_new_booking`), `api_v2/serializers.py` (une ligne de vente par tarif),
`Administration/management/commands/demo_data_v2.py`, `tests/e2e/conftest.py`, `Makefile`,
`scripts/lancer_tests.sh`, `pyproject.toml`, `poetry.lock`.

### À signaler au mainteneur (hors correction)

- i18n : 8 chaînes neuves en français (dont, pour la remise au panier, « Prix avant remise :
  … € » et « code … (−… %) ») (`Ce tarif n'appartient pas à cette ressource.`,
  `Ce tarif est réservé aux adhérents.`, `Cet événement n'est plus en vente.`, et les trois
  messages qui citaient « 15 minutes », réécrits avec `%(minutes)s` : chevauchement avec un
  paiement en cours, confirmation trop tardive, réservation bloquée) ; msgid de C12
  changé (`%(event)` → `%(event)s`),
  les deux `.po` portent l'ancien, faux aussi dans le `msgstr` FR → workflow i18n à lancer.
  Les autres messages ajoutés réutilisent des msgids existants.
- 4 utilisateurs `test+panier…@mock.test` créés avant cette session (12 h 15-12 h 59 UTC),
  inactifs : non supprimés.
- `booking/tests/` cassé (C30) ; gabarit `booking/views/book.html` absent (C29).
- Panneau de réservation de ressource titré « Adhérer », bouton « Pay now » non traduit,
  tarif unique non présélectionné (vu en E2E).
- Récompense monnaie : un adhérent sans portefeuille Fedow la reçoit-il ? L'E2E existant et E6
  créent le portefeuille avant (question ouverte, parcours direct compris).
- Deux produits `FREERES` dans une même réservation directe : billets et webhook envoyés deux
  fois (`method_F` posait le statut gratuit à chaque produit). **Corrigé (2026-09-22)** : le
  statut gratuit est posé UNE fois, après tous les produits, dans `TicketCreator.__init__`.
- C20, à annoncer aux lieux : un événement archivé ou terminé n'est plus vendable (front et
  panier) ; sans date de fin, la vente ferme 24 h après le début ; la caisse et l'API vendent
  jusqu'à la fin de l'événement.
- C28 s'applique aussi à l'API v2 et à la caisse V1 (même validateur) : une caisse qui vend
  sous un email générique est bloquée après N ventes sur un événement limité par personne —
  c'était déjà le cas avant (contrôle « déjà atteint »).
- Non vérifiable ici : LaBoutik V1 accepte-t-elle une vente de billet à 0 € en « offert » ?
  `webhook_reservation` et `ticket_celery_mailer` (dans `reservation_paid`) partent avant la
  validation en base quand le panier gratuit est matérialisé (préexistant, même classe que
  C31).
- Menu : l'`aria-label` pluriel « Cart (n items) » n'a pas de traduction française (classic,
  V2 et Faire Festival).
- Relecture Fable n° 5 (ordre des produits non garanti) écartée : `post_save_Product` donne au
  nouveau produit un poids = nombre de produits + 1. Relecture Opus n° 7 (ordre du panier en
  session après une erreur) : sans conséquence, non traité.
- Chromium installé dans le conteneur (`playwright install-deps` + `install chromium`).
- Environnement (découvert le 2026-09-22, antérieur) : la tâche quotidienne `cron_morning`
  crée des lieux « en attente » (`waiting_…`) puis les migre un par un ; au premier échec
  (ici un interblocage avec une suite de tests lancée en même temps), elle s'arrête et laisse
  les schémas suivants VIDES (11 réparés à la main, avec l'accord du mainteneur).
  `test_pages_api.test_http_isolation_cross_tenant` choisit « le premier lieu par ordre
  alphabétique » : il peut tomber sur un de ces lieux vides.
- `test_events_list.py` frôle son délai de 10 s (réponse en 9,7 s) : il échoue au hasard
  quand le serveur live est chargé.
- Non relancée après la relecture : la suite E2E complète (`e2e_slugs` a changé : seules les
  clés du panier sont concernées, et les E2E du panier passent).
