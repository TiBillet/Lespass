# Remboursements billetterie — corrections et tests (chantier 01)

> **Status :** plan rédigé le 2026-09-21, relu par un agent Fable (corrections intégrées),
> décisions du mainteneur prises (§2). **Implémenté le 2026-09-21** : 20 tests mockés + 4 tests
> Stripe réel verts, 20 + 4 mutations détectées (§4.6, §8). Relecture Opus : §7.
> **Périmètre :** `Reservation.cancel_and_refund_resa()`, `Reservation.cancel_and_refund_ticket()`,
> `Reservation._lignes_hors_stripe()`, `PaiementStripe/utils.py::partial_refund_payment()`,
> machine à états `BaseBillet/signals.py`, et `tests/pytest/test_stripe_refund.py`.
> **Hors périmètre (décision mainteneur) :** `booking/models.py` (Booking), paiements d'avant
> le refactor du 7 juillet, E2E Playwright.

## 0. Ce qu'on veut à la fin

Deux façons de vendre : **avec panier** (`reservation.commande` renseigné, paiement porté par
la `Commande`) et **sans panier** (`paiement.reservation` renseigné : parcours direct du front,
API v2).

Pour chacune, trois scénarios doivent fonctionner et être testés :

1. **Billet par billet** : une réservation de 3 billets, on rembourse les 3 un par un.
2. **Réservation complète** : une réservation de 3 billets, remboursée d'un coup.
3. **Mixte** : un billet, puis la réservation complète (les 2 restants).

À chaque étape, on vérifie : l'appel Stripe (montant), les lignes de vente, le statut du
paiement, le statut des billets, le statut de la réservation, et `total_paid()`.

## 1. Constats

Chaque constat indique sa preuve (test, essai front, journal serveur) ou, à défaut, la lecture
qui le fonde. Tous ont été revérifiés par la relecture Fable.

### B1 — Sans panier, le 2e remboursement ne part jamais (ARGENT) — ✅ corrigé dans le working tree

Après un 1er remboursement, le paiement passe `PARTIALLY_REFUNDED` (`H`). Le filtre du chemin
sans panier ne connaît pas `H` : la boucle ne trouve rien, aucun appel Stripe, aucune erreur,
mais le billet est annulé.

```python
for paiement in self.paiements.filter(status__in=[VALID, PAID, NOTSYNC]):   # H oublié
```

- **Preuve front** (essai du mainteneur, réservation `0b4a5b41`) : 2 billets `R`, une seule ligne
  −10 €. Dans le journal serveur, le 2e `POST …/cancel_ticket/` répond en 0,09 s sans aucun appel
  à `api.stripe.com/v1/refunds`.
- **Correction appliquée** : `Paiement_stripe.PARTIALLY_REFUNDED` ajouté aux deux filtres
  (`cancel_and_refund_resa` et `cancel_and_refund_ticket`).
- **Preuve de la correction** : 2 tests rouges avant, verts après ; retirer `H` de chaque filtre
  fait rougir le test correspondant (mutations M1, M2).
- **Chemin panier** : pas concerné (aucun filtre de statut). Prouvé par un test (billet, billet,
  réservation), qui rougit si l'on introduit le même filtre (mutations MP1, MP2).

### B2 — Annuler une vente Stripe crée un avoir sur la vente espèces d'un AUTRE client (COMPTA)

`_lignes_hors_stripe()` (`BaseBillet/models.py:2861`) cherche d'abord les lignes hors Stripe
**de la réservation**. Si elle n'en trouve pas, elle se replie (`:2887`) sur **tout le tenant** :

```python
return LigneArticle.objects.filter(
    paiement_stripe__isnull=True, status__in=[VALID, PAID],
    pricesold_id__in=pricesold_ids,          # même tarif du même événement…
    sale_origin=SaleOrigin.ADMIN,            # …vendu par l'admin
)                                            # ← aucun filtre sur la réservation !
```

Or cette recherche tourne dans des cas où la réservation n'a **aucune** ligne hors Stripe :
- **après un remboursement Stripe** : `cancel_and_refund_resa` l'appelle toujours (`:2977`),
  `cancel_and_refund_ticket` l'appelle parce que `refund` reste `False` (B3) ;
- **à l'annulation d'une réservation gratuite en ligne** : `method_F` (`validators.py:258`) crée
  les billets mais **aucune** `LigneArticle` → `total_paid() == 0` → pas de Stripe → requête
  directe vide → repli.

Dans ces cas, le repli trouve les ventes espèces/chèque des autres clients du même tarif. Le `PriceSold` est partagé : l'admin
fait `PriceSold.objects.get_or_create(productsold, price, prix)`, la vente en ligne
`get_or_create_price_sold()` avec la même clé.

- **Preuve** : test temporaire (réservation admin espèces A + réservation Stripe B, même tarif).
  Annuler B → **1 avoir −10 € créé sur la ligne de A**, alors que A reste `V` avec son billet `K`.
  Idem en annulant un seul billet de B. (Code de la preuve : annexe A.)
- **Conséquence** : la compta affiche un remboursement espèces qui n'a jamais eu lieu (écart de
  caisse), et l'avoir est envoyé à LaBoutik. Quand A sera vraiment annulée, elle n'aura plus
  d'avoir (le sien a déjà été « consommé »).

**Pourquoi le repli existe** : la FK `LigneArticle.reservation` date du 2026-03-06 (migration
`0200`). Le backfill `0201` ne l'a remplie que pour les lignes **Stripe**. Les ventes admin
d'avant mars 2026 n'ont donc pas de réservation liée : le repli est leur seul moyen d'être
retrouvées. Le supprimer les prive d'avoir à l'annulation : conséquence acceptée (Q3).

`Booking._lignes_hors_stripe()` (`booking/models.py:592`) n'a **pas** de repli : c'est le bon modèle.

**Même restreint aux lignes sans réservation, le repli reste imprécis** : pour une vente admin
d'avant mars 2026, il prend toutes les lignes anciennes du tarif, y compris celles d'autres
clients (`:2977` en crée un avoir pour chacune, `:3059` prend la première). Impossible de
les rattacher après coup : `Reservation.datetime` est en `auto_now=True`. Voir Q3.

### B3 — `cancel_and_refund_ticket` ne sait pas qu'il a remboursé par Stripe

```python
refund = False
...partial_refund_payment(...)       # remboursement Stripe fait
                                     # ← refund n'est jamais passé à True
if not refund:                       # → la recherche hors Stripe tourne quand même (B2)
    ...
return self.cancel_text() if refund else _("Ticket cancelled.")
```

- Sans B2 : message « Ticket cancelled. » au lieu du texte de remboursement.
- Avec B2 : message `cancel_text()`… déclenché par l'avoir parasite.
- **Preuve** : dans le test temporaire, le message renvoyé après un remboursement Stripe réussi
  est « La date limite pour obtenir un remboursement est dépassée. » (voir Q2).

### B4 — Les lignes de remboursement ne sont pas rattachées à la réservation (AFFICHAGE)

`partial_refund_payment()` (`PaiementStripe/utils.py:78`) crée la ligne négative **sans**
`reservation=` (ni `booking=`, ni `membership=`). Or `articles_paid()` / `total_paid()` lisent
d'abord `self.lignearticles` (FK directe) : les remboursements sont invisibles.

- **Preuve** : essai front, ligne −10 € avec `reservation_id = None` ; les lignes d'origine l'ont.
- **Conséquence** : `total_paid()` affiche toujours le montant d'avant remboursement dans le
  compte client (`reservations.html`, `event_card.html`), la colonne admin, l'export et les mails.
  Et `if self.total_paid() > 0` reste vrai même après un remboursement total.

### B5 — Chaque remboursement partiel écrit une fausse ERREUR dans les logs

`PRE_SAVE_TRANSITIONS` (`BaseBillet/signals.py:308`) ne déclare pas `VALID → PARTIALLY_REFUNDED` :
la transition tombe sur `'_else_': error_regression`.

- **Preuve** : `ERROR models_signal erreur_regression V to H` dans le journal serveur, une fois par
  remboursement partiel (deux lignes pour les deux essais front du 21/09).
- `P → H` et `P → R` tombent aussi sur `_else_` (`signals.py:306`). `H` et `S` n'ont pas d'entrée :
  `H → H`, `H → R`, `S → H` sont silencieux. Déclarer `V → H`, `P → H`, `P → R` suffit.
- Aucun blocage (`error_regression` ne fait que logger), mais c'est du bruit, et une fausse alerte
  si les `logger.error` remontent dans Sentry.

### B6 — Condition toujours vraie (robustesse, faible)

```python
if self.commande and self.lignearticles:   # un manager Django est toujours « vrai »
    paiement = self.lignearticles.first().paiement_stripe   # None.paiement_stripe si aucune ligne
```

Pas atteignable aujourd'hui (`materialiser()` crée toujours des lignes). **Noté, non corrigé.**

### B7 — Annuler UN billet d'une vente admin crée un avoir de TOUTE la ligne (COMPTA)

```python
# cancel_and_refund_ticket → _creer_avoir(ligne)
avoir = LigneArticle.objects.create(qty=-ligne.qty, ...)   # ← toute la quantité
```

Réservation admin espèces de 3 billets, on annule 1 billet → avoir de **−3 × prix**. La ligne
est alors marquée « avec avoir » (`exclude(credit_notes__isnull=False)`) : au 2e billet, la
requête directe est vide → repli (B2).
- **Preuve** : lecture (`models.py:2911`, `:3055-3059`). Vérifié par la relecture Fable.
  À prouver par un test avant correction.

### B8 — Les avoirs hors Stripe sont invisibles dans `total_paid()` (AFFICHAGE)

`_creer_avoir()` ne recopie pas `reservation`, et `articles_paid()` ne lit que
`PAID / VALID / REFUNDED` (pas `CREDIT_NOTE`). Une réservation admin annulée affiche toujours
son montant payé. Même logique dans `Booking.total_paid()` (`booking/models.py:587`).

## 2. Décisions du mainteneur (2026-09-21)

- **Q1 — Dernier billet remboursé → réservation `CANCELED` : OUI.**
  Revérifié, ce n'est pas le cas aujourd'hui. Seuls `cancel_and_refund_resa()` (`models.py:2981`)
  et le délai de confirmation d'une réservation gratuite (`signals.py:256`) posent `CANCELED`.
  La machine à états du `Ticket` ne connaît que `K → S`, et le `post_save` sur `Ticket` est commenté
  (`signals.py:535`). Le compte client cache les billets annulés (l'accordéon n'affiche que `K`/`S`),
  mais `my_reservations` liste toujours la réservation `VALID` avec « 3 places » et le bouton
  d'annulation. Conséquences : annuler ensuite la réservation lève « déjà annulée » (`:2931`), et
  c'est ce que vérifie T4. `VALID → CANCELED` est `no_change` (`signals.py:357`). Seul le mail
  « billet annulé » part.

- **Q2 — Délai de remboursement non appliqué : hors chantier** (décision métier, noté §6).

- **Q3 — Repli de `_lignes_hors_stripe()` : le SUPPRIMER**, comme dans Booking. Ne reste que la FK
  directe. Conséquence acceptée : annuler une vente admin d'avant mars 2026 (ligne sans réservation)
  ne crée plus d'avoir. Le drapeau « remboursé par Stripe » devient inutile : une réservation Stripe
  n'a pas de ligne hors Stripe, et aucun chemin de code ne mélange les deux.

- **Q4 — Avoirs hors Stripe billet par billet (B7, B8) : OUI, dans ce chantier.**

- **Q5 — Recopier `reservation`, `booking`, `membership` sur la ligne de remboursement : OUI**,
  même si `Booking.total_paid()` en profite indirectement.

## 3. Corrections prévues

| # | Fichier | Changement |
|---|---|---|
| B1 | `BaseBillet/models.py` | ✅ fait : `PARTIALLY_REFUNDED` dans les deux filtres sans panier |
| B2 | `BaseBillet/models.py` `_lignes_hors_stripe()` | Supprimer le repli : FK directe uniquement, comme `Booking._lignes_hors_stripe()` (Q3) |
| B3 | `BaseBillet/models.py` `cancel_and_refund_ticket()` | `refund = True` après `partial_refund_payment()` (les deux chemins) |
| B4 | `PaiementStripe/utils.py` | Ligne de remboursement : recopier `reservation`, `booking`, `membership` de la ligne d'origine |
| B5 | `BaseBillet/signals.py` | Déclarer `VALID → PARTIALLY_REFUNDED`, `PAID → PARTIALLY_REFUNDED` et `PAID → REFUNDED` en `no_change` |
| B7 | `BaseBillet/models.py` `_creer_avoir()`, `_lignes_hors_stripe()`, `cancel_and_refund_*` | `_creer_avoir(ligne, quantite)` : avoir de la quantité annulée (1 billet = `−1`). Une ligne reste sélectionnable tant que `qty + somme(avoirs.qty) > 0` (remplace `exclude(credit_notes__isnull=False)`). Calcul en boucle simple (FALC). Annulation complète : avoir de la quantité restante (`quantite_restante`) |
| B8 | `BaseBillet/models.py` `_creer_avoir()`, `articles_paid()` ; `Administration/admin_tenant.py` `LIGNE_PAYEE_STATUTS` (`:1033`) | Recopier `reservation` sur l'avoir ; compter `CREDIT_NOTE` dans `articles_paid()` et dans sa réplique admin |
| Q1 | `BaseBillet/models.py` `cancel_and_refund_ticket()` | Si plus aucun billet non annulé : réservation `CANCELED` |

**Effets de bord vérifiés pour B4 :**
- `_lignes_hors_stripe()` filtre `paiement_stripe__isnull=True` : une ligne de remboursement (qui a un
  paiement) n'y entre jamais.
- Chemin panier : `self.lignearticles.first()` peut devenir une ligne de remboursement, mais elle
  pointe vers le même paiement. `lignes = …filter(status__in=[VALID, PAID])` l'exclut (statut `REFUNDED`).
- `comptabilite/services.py` compte les `REFUNDED` par une requête dédiée, sans passer par la réservation.
- `Booking.cancel_and_refund_booking()` passe aussi par `partial_refund_payment()` : le booking
  remboursé verra lui aussi son `total_paid()` devenir juste. Ça touche Booking indirectement :
  **à valider** avec la décision « ne pas toucher Booking ».

## 4. Tests

### 4.1 Organisation de `tests/pytest/test_stripe_refund.py`

Deux fabriques de réservation payée, qui renvoient `(reservation, paiement, prix_un_billet)` :

```python
def _reservation_payee_sans_panier(api_client, auth_headers, tenant, mock_stripe, qty):
    # API v2 → paiement.reservation renseigné, reservation.commande vide

def _reservation_payee_avec_panier(api_client, auth_headers, tenant, mock_stripe, qty):
    # PanierSession + CommandeService.materialiser() → reservation.commande renseignée
```

Les deux appellent `_simuler_paiement_valide()` (paiement `VALID`, lignes `VALID`, billets activés
en `K` comme le fait le signal `reservation_paid`).

Les scénarios sont paramétrés sur le parcours :

```python
@pytest.mark.parametrize("parcours", ["sans_panier", "avec_panier"])
```

### 4.2 Matrice (× 2 parcours = 8 tests)

| Test | Scénario | Attendu |
|---|---|---|
| T1 `test_trois_billets_rembourses_un_par_un` | 3 × `cancel_and_refund_ticket` | 3 appels Stripe de `1000` ; paiement `H`, `H`, puis `R` ; 3 lignes `qty=-1` **rattachées à la réservation** ; `total_paid()` après chaque billet : `Decimal("20.00")`, `Decimal("10.00")`, `Decimal("0.00")` (euros, pas centimes) ; billets `R` ; réservation selon Q1 |
| T2 `test_reservation_complete_remboursee_d_un_coup` | `cancel_and_refund_resa` | 1 appel de 3 billets ; paiement `R` ; 1 ligne `qty=-3` rattachée ; réservation `CANCELED` ; billets `R` ; `total_paid()` = 0 |
| T3 `test_un_billet_puis_reservation_complete` | 1 billet, puis la réservation | appels `[1 billet, 2 billets]` ; paiement `R` ; réservation `CANCELED` |
| T4 `test_annuler_apres_trois_billets_rembourses_ne_rembourse_rien_de_plus` | T1 puis `cancel_and_refund_resa` | exception « déjà annulée », aucun nouvel appel Stripe, aucune nouvelle ligne |

Les deux parcours remboursent les mêmes montants : la matrice prouve que panier et sans panier
se comportent pareil.

### 4.3 Tests hors Stripe (non paramétrés)

| Test | Attendu |
|---|---|
| T5 `test_annuler_une_reservation_stripe_ne_touche_pas_la_vente_especes_d_un_autre_client` | A (admin, espèces) et B (Stripe) sur le même tarif ; annuler B → **0 avoir** sur la ligne de A |
| T6 `test_annuler_un_billet_stripe_ne_touche_pas_la_vente_especes_d_un_autre_client` | Idem avec un seul billet de B ; et le message renvoyé est `cancel_text()` |
| T7 `test_annuler_une_reservation_admin_especes_cree_son_avoir` | Non-régression : l'avoir de la réservation admin (FK directe) est toujours créé, `total_paid()` passe à 0 (B8) |
| T9 `test_annuler_une_reservation_gratuite_ne_touche_pas_la_vente_admin_du_meme_tarif` | Réservation gratuite en ligne (0 ligne) + vente admin sur le même tarif → 0 avoir |
| T10 `test_trois_billets_admin_annules_un_par_un_creent_trois_avoirs_d_un_billet` | Vente admin espèces de 3 billets, annulés un par un → 3 avoirs de `−1`, `total_paid()` 20 → 10 → 0 (selon Q4) |
| T11 `test_lignes_hors_stripe_ne_renvoie_que_les_lignes_de_la_reservation` | Test direct de `_lignes_hors_stripe()` : jamais une ligne d'une autre réservation, ni une ancienne ligne sans réservation |
| T12 `test_remboursement_partiel_n_ecrit_pas_d_erreur_dans_les_logs` | B5 : aucune ligne `erreur_regression` après un remboursement partiel |

T7 vérifie aussi la réplique admin `_lignes_payees_prefetch()` (B8).

### 4.4 Tests existants

- `test_cancel_and_refund_paid_reservation_calls_stripe_refund` → remplacé par T2 sans panier.
- `test_partial_refund_one_ticket_out_of_four` → remplacé par T1.
- Les 3 tests écrits pendant cette session (deux billets successifs, annulation après un billet,
  panier) → remplacés par T1, T3 et T1 avec panier.
- `test_free_reservation_cancel_does_not_call_stripe_refund` → gardé. Son commentaire « crée un
  avoir CREDIT_NOTE » est faux (une réservation gratuite n'a aucune ligne) et son nettoyage ne
  supprime rien : à corriger.

### 4.5 Règles

- Nettoyage dans un `finally`, après la garde `assert paiement is not None` (sinon
  `filter(paiement_stripe=None).delete()` viderait la compta du tenant). Avoirs supprimés avant
  leur ligne d'origine (`credit_note_for` est en `PROTECT`).
- Emails de test **en minuscules** (les adresses sont stockées en minuscules).
- **Chaque test est vu rouge** avant sa correction, ou sous une mutation du code qu'il protège.
- **Mutations et serveur live** : le serveur byobu recharge les fichiers modifiés. Prévenir le
  mainteneur avant chaque série de mutations (il ne doit pas tester le front à ce moment-là).

### 4.6 Mutations (toutes vues rouges, script de pilotage avec restauration systématique)

| # | Mutation | Test qui rougit |
|---|---|---|
| M1 | Retirer `H` du filtre de `cancel_and_refund_ticket` | billet par billet, sans panier |
| M2 | Retirer `H` du filtre de `cancel_and_refund_resa` | un billet puis complète, sans panier |
| M3 | Filtre de statut dans la branche panier de `cancel_and_refund_ticket` | billet par billet, avec panier |
| M4 | Filtre de statut dans la branche panier de `cancel_and_refund_resa` | un billet puis complète, avec panier |
| M5 | Remettre le repli sur tout le tenant | T5, T9, T11 |
| M6 | Retirer `refund = True` | T6 (garde-fou + message) |
| M7 | Avoir de toute la ligne pour un billet | T10 |
| M8 | Ne plus compter `CREDIT_NOTE` dans `articles_paid()` | T7, T10 |
| M9 | Retirer `CREDIT_NOTE` de `LIGNE_PAYEE_STATUTS` (admin) | T7 |
| M10 | Ne plus annuler la réservation au dernier billet | T1, T4, T10 |
| M11 | Ne plus rattacher la ligne de remboursement à la réservation | T1, T2, T3 |
| M12 | `specified_quantity=2` | T1 sans panier |
| M13 | Retirer `VALID → PARTIALLY_REFUNDED` de la machine à états | test des logs |
| MG1 | Retirer le garde-fou de `cancel_and_refund_ticket` | garde-fou [billet] |
| MG2 | Retirer le garde-fou de `cancel_and_refund_resa` | garde-fou [réservation] |
| MQ | Avoir de `ligne.qty` au lieu de `quantite_restante` (annulation complète) | T13 |
| MF | Proposer une ligne déjà entièrement créditée | T10 |
| MP | Retirer `PAID → CANCELED` de la machine à états | test des logs |
| MU | `save()` complet au lieu de `update_fields=["status"]` | T1 (date de réservation) |
| MB | Mail Booking revenu à `total_paid()` | test du mail Booking |

Les deux couches de B2 se masquaient l'une l'autre sur T5/T6 : c'est pourquoi T9 et T11 existent.

## 5. Ordre de travail

1. Écrire les tests (§4) : rouges sur B2 (T5, T6, T9, T11), B3, B4, B7, B8 et Q1 ; verts sur B1
   (déjà corrigé).
2. Corriger B2 + B3, puis B4, puis B7 + B8, puis B5, puis Q1 (selon réponses).
3. Mutations (§4.6), en prévenant le mainteneur.
4. Suite complète `tests/pytest/` (sans `-p no:cacheprovider` : les tests API v2 s'en servent).
5. Relecture par un agent Fable.
6. CHANGELOG au format du dossier `CHANGELOG/`.

## 6. Noté, hors périmètre

- **R1 — Double remboursement possible.** `Refund.create` tourne dans un `@atomic`. Si une
  exception survient après (ex. broker Celery indisponible sur `send_refund_to_laboutik.delay()`),
  la base revient en arrière mais l'argent est parti. Le client peut recliquer → 2e remboursement.
- **R2 — `.delay()` dans la transaction.** Les tâches Celery peuvent partir avant le commit.
  `transaction.on_commit()` serait plus sûr.
- **R3 — Webhooks `refund.*` ignorés.** Un remboursement fait depuis le tableau de bord Stripe
  n'est pas reflété dans Lespass.
- **R4 — Commentaire faux** dans `partial_refund_payment()` : « inférieur à 1 € » alors que le
  seuil `>= 1` est en centimes (1 centime).
- **R5 — Booking** : même filtre sans `H` (`booking/models.py:686`). Pas atteignable aujourd'hui
  (un Booking se rembourse en une fois). Même condition toujours vraie que B6.
- **Q2** (délai de remboursement non appliqué) : décision métier.
- **R6 — `set_ligne_article_paid`** (`signals.py:41-48`) repasserait en `PAID` des lignes
  `REFUNDED` si un paiement rejouait `PENDING → PAID`. Préexistant.
- **Admin, action « Cancel and refund »** (`admin_tenant.py:3471-3474`) : `tickets.count()` compte
  aussi les billets déjà annulés pour décider « toute la réservation ». Préexistant.
- **Données de dev** : billet `edd9942f` (réservation `0b4a5b41`) annulé sans remboursement
  pendant l'essai front. Laissé tel quel.

## 7. Relecture Opus de l'implémentation (2026-09-21) — corrections apportées

| Constat de la relecture | Correction |
|---|---|
| **Mail Booking à 0 €** (`booking/tasks.py`) : il lisait `total_paid()` après l'annulation, qui compte désormais le remboursement | Le mail lit la vente d'origine (lignes `PAID`/`VALID`). Test `test_mail_annulation_booking.py` |
| Tests « gratuits » passaient par `method_B` (catégorie « Ticket booking ») et appelaient le vrai Stripe | Catégorie « Free booking », garde `not mock_stripe.mock_create.called` (PIEGES 12.16) |
| `quantite_restante` et le filtre « entièrement créditée » sans test | T13 (un billet admin puis la réservation : −1 puis −2) ; T10 vérifie `_lignes_hors_stripe() == []` |
| Billet annulé sans remboursement si aucun paiement ne correspond (même famille que B1) | **Garde-fou** (décision mainteneur) : erreur « Aucun paiement remboursable… », rien n'est annulé. Test paramétré billet / réservation |
| `PAID → CANCELED` écrivait `erreur_regression` ; les tests partaient d'une réservation `U` | Transition déclarée ; `simuler_paiement_valide()` pose `VALID` ; test des logs en `PAID` (PIEGES 12.17) |
| `self.save()` complet au dernier billet (écrase `datetime` en `auto_now` et `mail_send`) | `save(update_fields=["status"])` ; T1 vérifie la date |
| FALC : `annotate(F + Coalesce(Sum))`, nom `qty_restante` | Boucle simple, `quantite_restante` |
| Docstrings et commentaires | `cancel_and_refund_resa` : LOCALISATION + FLUX ; commentaires anglais traduits ; « actif » → « non annulé » |

Écarts relevés mais laissés en l'état :
- données déjà en base (lignes de remboursement et avoirs sans réservation) : **rien en prod** (décision) ;
- `refund = True` même pour un billet à 0 € (message de remboursement annoncé) ;
- `_creer_avoir(quantite=1)` non borné par `quantite_restante` (quantités décimales : non atteignables aujourd'hui) ;
- double clic → double remboursement (pas de `select_for_update`), voir R1 ;
- fixture `booking/tests/conftest.py::test_resource` cassée depuis `3ca3ce5c` (30/06 : `Resource.product` obligatoire) ;
- chaque exécution laisse des événements, produits, réservations et utilisateurs de test (motif commun à la suite).

## 8. Stripe réel en mode test + lancement unifié (2026-09-21)

Demande du mainteneur : des tests qui passent vraiment par Stripe, réutilisables pour tester
de vrais paiements, et une procédure unique « Python ou E2E, avec ou sans Stripe ».

| Fichier | Rôle |
|---|---|
| `Makefile` | Table des matières : `make test`, `make test-stripe`, `make e2e`, `make e2e-stripe` |
| `scripts/lancer_tests.sh` | Serveur live vérifié, clé API de test, `STRIPE_REEL=1`, `stripe listen` vérifié pour `e2e-stripe` |
| `tests/stripe_reel.py` | Outils Stripe réel (clé `sk_test_` obligatoire, paiement par carte de test, lecture des remboursements) + mécanisme « ignoré, en rouge » partagé par les deux conftests |
| `tests/pytest/fabriques_reservation.py` | Fabriques de ventes (avec/sans panier, admin) ; `compte_stripe_reel=` pour un vrai paiement |
| `tests/pytest/test_stripe_reel_remboursement.py` | Marqueur `stripe_reel` : billet par billet et réservation complète, avec et sans panier, vérifiés chez Stripe |
| `tests/e2e/test_renouvellement_adhesion_recurrente.py` | Factorisé : `preparer_stripe_mode_test()` (garde anti-clé live) |

Une seule variable, `STRIPE_REEL=1`, pour les deux suites (`E2E_STRIPE_LISTEN` disparaît).

Vérifications côté Stripe dans les tests réels : `montants_rembourses_chez_stripe()` (Refund.list :
montants et statut `succeeded`) et `etat_du_paiement_chez_stripe()` (Charge.list : encaissé,
remboursé, en totalité). Recoupées une fois à la main par la CLI Stripe (`stripe payment_intents list`,
`stripe refunds list --payment-intent …`, `--stripe-account` du lieu) : 8 paiements de 3000,
remboursés 3 × 1000 ou 1 × 3000, tous `succeeded`.
Mutations propres aux tests réels : filtre sans `H`, `specified_quantity=2`, un billet de trop
(branche panier), paiement de 5 € de trop — toutes rougissent.
Marqueurs : `stripe_reel` (pytest, API Stripe de test) et `stripe_listen` (E2E, webhook).

## Annexe A — Preuve de B2

Scénario, avec Stripe mocké :
1. Événement + tarif 10 € (API v2).
2. Réservation B payée en ligne (API v2), paiement simulé `VALID`, billets `K`.
3. Réservation A créée comme `ReservationAddAdmin.save()` : même `get_or_create` du `PriceSold`,
   ticket `K` en espèces, ligne `VALID`, `sale_origin=ADMIN`, `reservation=A`, sans paiement Stripe.
4. `B.cancel_and_refund_resa()` (ou `B.cancel_and_refund_ticket(b1)`).

Résultat observé :

```
PriceSold partagé A/B : True
Réservation A (jamais annulée) : status=V, tickets=['K']
Avoirs créés sur la ligne espèces de A : 1 [('N', -1.0, 1000)]
Refund Stripe appelé : 1 fois — message renvoyé : 'La date limite pour obtenir un remboursement est dépassée.'
```
