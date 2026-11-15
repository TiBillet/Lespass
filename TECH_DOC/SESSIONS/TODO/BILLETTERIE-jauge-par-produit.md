# BILLETTERIE — Jauge par produit (issue #496)

> **Status :** spec du 2026-11-13, **décisions prises avec le mainteneur le 2026-11-13**.
> Relue par un agent Fable (exactitude face au code) : ses corrections sont intégrées.
> **Pré-requis : merger la branche `OTP` d'abord.** Elle supprime notamment la
> confirmation tardive des réservations gratuites (`activator_free_reservation`,
> `BaseBillet/signals.py`) : ce chantier n'y touche donc pas.
> **Quand le chantier démarre :** déplacer ce fichier dans un hub
> `TECH_DOC/SESSIONS/BILLETTERIE/` (`INDEX.md` + `SPEC.md`), et relire les numéros de ligne :
> ils datent du code lu le 2026-11-13, avant le merge d'`OTP`.
> **Issue :** https://github.com/TiBillet/Lespass/issues/496
> **Consigne :** faire simple, conformité `djc` (FALC bilingue, pas de sucre, msgid en
> français, `data-testid`, `aria-*`, fichier `CHANGELOG/`).

---

## 1. Pourquoi ce chantier

Un lieu vend, pour un même événement, deux produits de billetterie déclinés en trois tarifs :

- « Billet sans repas » : plein, réduit, mini ;
- « Billet avec repas » : plein, réduit, mini.

Il veut limiter le nombre de **repas**, quel que soit le tarif. Une jauge existe sur
l'événement (`Event.jauge_max`) et sur chaque tarif (`Price.stock`), mais **pas sur le
produit**. Le lieu ferme aujourd'hui les trois tarifs à la main quand il approche du seuil.

Quand la jauge du produit est pleine, le message doit parler du produit (« Plus de places
pour « Billet avec repas » »), pas du tarif.

**Limite à dire au lieu :** la jauge produit ne sert que si les repas sont dans **un produit
à part**. Un produit unique décliné en 6 tarifs (avec/sans repas × plein/réduit/mini) ne
peut pas être limité de cette façon.

---

## 2. Décisions (mainteneur, 2026-11-13)

| # | Décision | Raison |
|---|---|---|
| D1 | Nouveau champ `Product.jauge_par_evenement`. Vide = illimité. **Minimum 1** (`MinValueValidator(1)`). | Aucun champ existant ne convient (D2). Le nom dit que la jauge vaut pour **un** événement : un produit est souvent partagé entre plusieurs événements (`Event.products`, M2M). Pour fermer un produit, on le dépublie. |
| D2 | `inventaire.Stock` n'est **pas** réutilisé. | C'est un compteur physique **unique par produit** (OneToOne `stock_inventaire`), décrémenté par des `MouvementStock`. Une jauge est **par événement** et se recalcule depuis les billets. `inventaire.Stock` reste l'outil d'une future boutique en ligne (merch). |
| D3 | Trois plafonds indépendants : événement, produit, tarif. Une vente doit respecter **les trois**. | Pas d'algorithme en cascade : le plus petit plafond l'emporte tout seul. |
| D4 | La caisse applique la jauge produit. | Sinon la caisse vend des repas au-delà de la jauge. |
| D5 | La caisse compte aussi les **billets en cours de paiement** (comme le site), avec un message explicite. | Sans ça, la caisse peut vendre au-delà de la jauge pendant une vente en ligne. Effet assumé : un panier Stripe abandonné retient sa place 30 minutes (`DUREE_D_UN_PAIEMENT_EN_COURS`), au guichet aussi. Le message le dit. |
| D6 | Une tuile de la caisse affiche la jauge **la plus contraignante** (le moins de places restantes) entre événement, produit et tarif. | C'est l'information utile pour vendre. |
| D7 | La diffusion WebSocket des jauges (`broadcast_jauge_event`) est **remise en service**, sans retirer de code, avec la jauge la plus contraignante. | Aujourd'hui, elle n'est appelée nulle part : les tuiles ne se mettent à jour qu'au chargement de la caisse. |
| D8 | L'API v2 expose le champ (création et lecture de produit). | Demande du mainteneur. |
| D9 | **`Price.stock` : seul `None` veut dire illimité.** `0` veut dire épuisé. Les valeurs négatives sont refusées. | Aujourd'hui, `0` ou négatif veut dire illimité, alors que l'admin dit « laisser vide si illimité ». Un admin qui met 0 pour fermer un tarif obtient l'inverse. Une migration de données garde le comportement des tarifs existants (§4.2). |
| D10 | **`Event.jauge_max = 0` veut dire complet partout**, caisse comprise. | Le site et le panier le traitent déjà comme complet ; la caisse et ses tuiles comme illimité. |
| D11 | Le formulaire de réservation n'affiche que les questions des produits **choisis** (défaut A, §4.8). | Une question obligatoire d'un produit non choisi bloque aujourd'hui le navigateur. |
| D12 | Les réponses restent **une par réservation**. Pas de réponse par billet, pas de question de quantité. | Simplicité. |
| D13 | Le plafond du compteur `[-] 0 [+]` tient compte du stock restant du tarif et de la jauge du produit (défaut C2, §4.7). | Le compteur laisse aujourd'hui monter au-delà, et le serveur refuse ensuite. |

**Hors périmètre :**

- Verrou en réservation directe (survente possible en rush) : fiche
  `TODO/CHARGE-forte-affluence-festivals.md`, « mesurer d'abord ».
- Questions posées au niveau de l'événement : fiche
  `TODO/BILLETTERIE-formulaire-au-niveau-evenement.md`.
- « Copier le formulaire vers un autre produit » : écarté. Les réponses sont rangées par
  libellé : deux produits avec la même question, choisis ensemble, lèvent « Duplicate field
  label ».
- Confirmation tardive d'une réservation gratuite : supprimée par la branche `OTP`.
- Billet créé dans l'admin (`ReservationAddAdmin`, `Administration/admin_tenant.py`) : aucun
  contrôle de jauge, **comme aujourd'hui**. L'admin peut dépasser.
- L'admin générique des produits (`ProductAdmin` enregistré sur `Product`) n'affiche pas le
  champ. Seul `TicketProductAdmin` l'affiche.
- Adhésions : la jauge produit ne concerne que `BILLET` et `FREERES`. Elles sont touchées
  seulement par D9 (sens de `Price.stock`).

---

## 3. État actuel (code lu le 2026-11-13)

### 3.1 Les comptages existants

- `Event.valid_tickets_count()`, `under_purchase()`, `complet()`, `places_restantes()`
  (`BaseBillet/models.py`, ~l. 2674-2718). Billets valides : `NOT_SCANNED`, `SCANNED`. Billets
  en cours de paiement : `CREATED`, `NOT_ACTIV`, réservation de moins de
  `DUREE_D_UN_PAIEMENT_EN_COURS` (30 min, l. 60). Les billets `CANCELED` ne comptent jamais.
- `Price.out_of_stock(event, quantite_demandee=1)` (~l. 2063) : même comptage, filtré sur le
  tarif et l'événement. Ligne 2076 : `if self.stock is None or self.stock < 1: return False`
  (0 et négatif = illimité, voir D9).
- Le panier calcule déjà les quantités **par produit** : `panier_avant_product` et
  `demandes_product` dans `validate_ticket_cart_limits` (`services_panier.py`, ~l. 179-190).

### 3.2 Les parcours qui vendent un billet

| # | Parcours | Fichier | Ce qui est contrôlé aujourd'hui |
|---|---|---|---|
| P1 | Réservation directe, API v2 (`api_v2/serializers.py:1618`), bénévoles | `BaseBillet/validators.py`, `ReservationValidator.validate` (~l. 793-1031) | `event.complet()` (l. 734), `price.out_of_stock(event, qty)` (l. 887), jauge événement avec la quantité totale (l. 955) |
| P2 | Panier (ajout, puis rejeu au paiement par `revalidate_all`) | `BaseBillet/services_panier.py`, `add_ticket` (~l. 510-580) et `validate_ticket_cart_limits` (~l. 121-290) | `event.complet()`, jauge événement (étape 4, l. 271-287), stock du tarif (« Validation 6 », l. 566-580) |
| P3 | Caisse | `laboutik/views.py`, ~l. 8755-8790, sous `select_for_update` de l'événement, dans un `atomic` | jauge événement et `Price.stock`, recomptés à la main, **sans** les billets en cours de paiement, avec `jauge_max > 0` (0 = illimité) |

Les trois skins incluent le même formulaire (`commun/offcanvas/reservation.html`). `booking`
et le kiosque ne créent pas de billet.

### 3.3 Les affichages

| # | Affichage | Fichier |
|---|---|---|
| A1 | Formulaire de réservation : messages par tarif, plafond `max` du compteur | `BaseBillet/views.py`, `EventMVT.retrieve` (~l. 3860-4015) ; `BaseBillet/templates/commun/formulaires/reservation.html` (l. 99-110) ; filtre `price_out_of_stock` (`BaseBillet/templatetags/tibitags.py:74`) |
| A2 | Tuiles billet de la caisse, au chargement | `laboutik/views.py`, ~l. 520-551 (comptage groupé par tarif) et ~l. 985-1110 (construction des tuiles) ; gabarit `laboutik/templates/cotton/billet_tuile.html` (l. 71-80) |
| A3 | Mise à jour des tuiles en direct | `wsocket/broadcast.py`, `broadcast_jauge_event` (l. 51) ; partial `laboutik/partial/hx_jauge_billet.html` ; consumer `wsocket/consumers.py` (rejoint `laboutik-jauges-{schema}` l. 74, méthode `jauge_update` l. 126). **Jamais appelée** : son déclencheur est commenté dans `BaseBillet/signals.py` (~l. 657-720, « FROM V2 : to implement later »). |

Logique actuelle d'une tuile (A2 et A3, recopiée deux fois) : si `Price.stock > 0`, jauge du
tarif (billets valides seulement) ; sinon jauge de l'événement (`complet` compte les billets
en cours). La mini-jauge de la barre latérale montre toujours l'événement.

### 3.4 Défaut A — questions de tous les produits affichées

`reservation.html` (~l. 233-360) affiche les questions de **tous** les produits de
l'événement. Le serveur ne valide que celles des produits choisis
(`build_custom_form_from_request`, appelé `validators.py:989` ; panier :
`add_tickets_batch`, `views.py` ~l. 7743-7757). Une question obligatoire (`required`) d'un
produit non choisi bloque la soumission par le bouton « réserver ».

Le bouton « ajouter au panier » (`type="button"`, `hx-post`, `hx-include="closest form"`,
~l. 617-620) n'a pas de contrôle `required` du navigateur : seuls `validateMsRequired`,
`validateBlRequired` (via `htmx:configRequest`) et le serveur le contrôlent.

---

## 4. Ce qu'on construit

### 4.1 Modèle — `Product.jauge_par_evenement` (`BaseBillet/models.py`)

À côté de `max_per_user` :

```python
jauge_par_evenement = models.PositiveSmallIntegerField(
    blank=True,
    null=True,
    validators=[MinValueValidator(1)],
    verbose_name=_("Jauge par événement"),
    help_text=_(
        "Nombre maximum de billets de ce produit pour un même événement, "
        "tous tarifs confondus. Laisser vide si illimité."
    ),
)
```

**Une seule méthode** sur `Product`, calquée sur `Price.out_of_stock` (mêmes statuts, même
fenêtre) :

```
places_restantes_pour_l_evenement(event) -> int | None
  None si jauge_par_evenement est vide.
  Sinon : jauge − billets valides − billets en cours de paiement, jamais négatif.
  Filtre : reservation__event__pk=event.pk, pricesold__price__product__pk=self.pk.
```

Chaque parcours compare en clair `quantité demandée > places restantes`. Pas de méthode
`jauge_atteinte` : elle referait les mêmes requêtes.

### 4.2 `Price.stock` : seul `None` veut dire illimité (D9)

1. **Migration de données**, sur chaque schéma de lieu (garde `schema_name == "public"` →
   `return`, voir le skill `djc`) : `Price.objects.filter(stock__lte=0).update(stock=None)`.
   Les tarifs existants gardent ainsi leur comportement (illimité). Afficher le nombre de
   tarifs modifiés par lieu. Billets **et** adhésions.
2. **Champ** : ajouter `MinValueValidator(0)` à `Price.stock`. Mettre à jour le `help_text` :
   « 0 = plus de places. Laisser vide si illimité. » (migration `AlterField`, sans SQL).
3. **`Price.out_of_stock`** : `if self.stock is None: return False`. Avec `stock = 0`, le tarif
   est épuisé.
4. **Tous les tests `price.stock > 0`** deviennent `price.stock is not None` :
   `laboutik/views.py` (~l. 531, 1046, 8779), `wsocket/broadcast.py` (~l. 112). À vérifier
   par `rg -n "stock > 0|stock < 1|stock is not None" --type py` au moment du codage.
5. **API v2** : `inventoryLevel.value = 0` veut maintenant dire épuisé. Le dire dans
   `openapi-schema.yaml`.

### 4.3 `Event.jauge_max = 0` : complet partout (D10)

La caisse (P3) et les tuiles (A2, A3) remplacent `jauge_max > 0 and …` par le même calcul
que `Event.complet()`. **Avant le déploiement**, le mainteneur compte en production les
événements à venir qui ont `jauge_max = 0` : ils deviendront complets en caisse.

### 4.4 P1 — `ReservationValidator.validate`

Dans la boucle `for product, price_dict in products_dict.items()` :

- sortir le calcul de `quantite_demandee_pour_ce_produit` du `if product.max_per_user:`
  (~l. 853-856), pour qu'il serve aux deux contrôles ;
- après le contrôle `product.max_per_user` :

```python
places_restantes_du_produit = product.places_restantes_pour_l_evenement(event)
if places_restantes_du_produit is not None:
    if quantite_demandee_pour_ce_produit > places_restantes_du_produit:
        # 0 → « Plus de places pour « %(produit)s ». »
        # sinon → « Il ne reste que %(n)s place(s) pour « %(produit)s ». »
```

Messages (msgid FR) :
- `"Plus de places pour « %(produit)s »."`
- `ngettext("Il ne reste que %(n)s place pour « %(produit)s ».", "Il ne reste que %(n)s places pour « %(produit)s ».", n)`

### 4.5 P2 — Panier

Dans `validate_ticket_cart_limits`, nouvelle **étape 5**, après la jauge de l'événement,
avec les variables déjà calculées :

```
places_restantes_du_produit = product.places_restantes_pour_l_evenement(event)
si places_restantes_du_produit is not None
   et panier_avant_product + demandes_product > places_restantes_du_produit :
   refus, mêmes messages que P1 ; le reste affiché = places_restantes − panier_avant_product
```

Le panier compte ainsi **tous les tarifs du produit** (au panier et dans l'envoi groupé), pas
seulement le même tarif. `revalidate_all` rejoue ce contrôle au paiement sans rien ajouter.
Docstring de `validate_ticket_cart_limits` : ajouter l'étape 5.

### 4.6 P3 — Caisse (`laboutik/views.py`, ~l. 8755-8790)

Toujours sous le `select_for_update` de l'événement :

1. **Jauge événement** : `valid_tickets_count() + under_purchase()` + quantité totale
   demandée, comparé à `jauge_max` sans exception pour 0 (D5, D10).
2. **Jauge produit** : additionner les quantités demandées **par produit**
   (`article["product"]`), puis comparer à `product.places_restantes_pour_l_evenement(...)`.
3. **Stock du tarif** : remplacer le recomptage à la main par
   `price.out_of_stock(event=event_locked, quantite_demandee=quantite)`. Il compte les billets
   en cours de paiement.

**Messages explicites** (D5), qui disent quand des paiements en cours retiennent des places :

- `_("Plus de places pour « %(produit)s ».")` ;
- quand les places manquantes sont retenues par des paiements en cours :
  `_("Plus de places disponibles pour « %(nom)s » : %(n)s place(s) retenue(s) par des paiements en ligne en cours, libérée(s) au plus tard dans 30 minutes.")`
  (à mettre en `ngettext` au codage). Le même principe vaut pour l'événement et le tarif.

La caisse lève toujours `ValueError` : le mécanisme d'erreur existant ne change pas.

### 4.7 A1 — Formulaire de réservation

**Vue `EventMVT.retrieve`** (`BaseBillet/views.py`, boucle sur `event.published_prices`) :

- calculer les places restantes **une fois par produit** : un dictionnaire
  `product_id → places restantes`, rempli seulement pour les produits qui ont une jauge.
  Indexer par `p.product_id` (`published_prices` n'a pas de `select_related`) ;
- pour chaque tarif `p` :
  - `p.produit_complet = (places restantes du produit == 0)` ;
  - ajouter à `plafonds` les places restantes du produit, si la jauge existe ;
  - ajouter à `plafonds` les places restantes du tarif, si `p.stock is not None` (D13). Le
    comptage est celui de `Price.out_of_stock` : le factoriser dans une méthode
    `Price.places_restantes_pour_l_evenement(event)`, que `out_of_stock` appelle.

Pour un événement fédéré, `published_prices` est vide dans le schéma courant : rien à faire.

**Gabarit `reservation.html`** (~l. 99-110), nouvelle branche **avant** `price_out_of_stock` :

```django
{% elif price.produit_complet %}
    <div class="alert alert-danger" role="alert" data-testid="booking-product-full-{{ price.uuid }}">
        {% blocktrans with produit=price.product.name %}Plus de places pour « {{ produit }} ».{% endblocktrans %}
    </div>
```

Ordre des branches : max par personne du produit, max par personne du tarif, **produit
complet**, tarif épuisé, adhésion obligatoire, compteur.

### 4.8 Défaut A — n'afficher que les questions des produits choisis (D11)

Dans `reservation.html` (~l. 233-360) :

- chaque bloc de questions d'un produit passe dans
  `<fieldset disabled hidden data-product-uuid="{{ product.uuid }}" data-testid="booking-product-questions-{{ product.uuid }}">`.
  Un `fieldset` désactivé n'est ni envoyé ni contrôlé par le navigateur. htmx 1.9.12 exclut
  aussi ses champs (`fieldset[disabled]`), y compris par `hx-include`. Le titre de chaque bloc
  reste le nom du produit ;
- `data-product-uuid="{{ price.product.uuid }}"` sur le `div.js-order` de chaque tarif
  (~l. 90 : un seul endroit, au lieu des trois `bs-counter`) ;
- un petit script calcule l'état **au chargement**, puis à chaque `bs-counter:update` et
  `change`. Il lit `counter.value` de **tous** les compteurs de chaque produit, sans se fier à
  `event.detail`. Somme au-dessus de 0 : il active et affiche le `fieldset` du produit.
  Sinon : il le désactive et le cache ;
- `validateMsRequired()` et `validateBlRequired()` (~l. 366-415) ignorent les groupes placés
  dans un `fieldset[disabled]` (`group.closest('fieldset[disabled]')`) ;
- la zone des questions porte `aria-live="polite"`.

Le serveur ne change pas.

### 4.9 A2 et A3 — Tuiles de caisse et diffusion WebSocket (D6, D7)

**La jauge la plus contraignante.** Une fonction pure, utilisée par la construction des
tuiles (A2) **et** par `broadcast_jauge_event` (A3) :

```
choisir_la_jauge_la_plus_contraignante(jauges) -> dict | None
  jauges : liste de {"jauge_max", "places_vendues", "places_en_cours"}, une par niveau
           qui a une jauge (événement, produit, tarif).
  Renvoie celle qui a le moins de places restantes (jauge − vendues − en cours),
  avec "pourcentage" et "complet" (restantes <= 0). None si aucune jauge.
```

Emplacement : `wsocket/broadcast.py` (déjà importé par `laboutik/views.py`), à côté de
`broadcast_jauge_event`. Pas de nouveau fichier.

La tuile affiche `jauge_max`, `places_vendues`, `pourcentage` et `complet` de cette jauge. La
mini-jauge de la barre latérale reste celle de l'événement.

**A2, chargement de la caisse** (`laboutik/views.py`) : les trois niveaux comptent les billets
valides **et** les billets en cours de paiement, pour que `complet` soit juste. Comptages
**groupés**, jamais dans la boucle des tuiles :

- tarif : étendre la requête groupée existante (~l. 535-551) avec un second compteur
  `Count(..., filter=Q(en cours de paiement))` ;
- produit : une requête groupée par (événement, produit), même forme ;
- événement : annotations existantes `nb_tickets_valides` et `nb_en_cours_achat`.

**A3, diffusion en direct** — remise en service, **sans retirer de code** :

1. `broadcast_jauge_event(event)` calcule chaque tuile avec
   `choisir_la_jauge_la_plus_contraignante` (tarif, produit, événement).
2. Décommenter le déclencheur de `BaseBillet/signals.py` (~l. 657-720) :
   `post_save` sur `Ticket` → `transaction.on_commit(..., robust=True)`. `robust=True`
   (Django ≥ 4.2) journalise une erreur de Redis sans la faire remonter : la vente est déjà
   enregistrée, la caisse ne doit pas afficher d'erreur. Garder la relecture de l'événement
   en base après le commit (`_safe_broadcast_jauge`), et y retirer le `try/except`
   générique, remplacé par `robust=True`.
3. Ajouter `post_delete` sur `Ticket` (suppression d'un billet dans l'admin) avec le même
   déclencheur.
4. Retirer le commentaire « FROM V2 : to implement later ».

Le signal couvre toutes les sources : caisse, vente en ligne (webhook Stripe), réservation
gratuite, annulation, remboursement, admin.

**Coût connu, accepté :** une réservation de N billets déclenche N diffusions (une par
sauvegarde de billet), chacune avec quelques `COUNT`. Si une mesure le montre gênant : une
seule diffusion par événement et par transaction. À noter dans la fiche
`TODO/CHARGE-forte-affluence-festivals.md` s'il faut y revenir.

### 4.10 Admin — `Administration/admin/products.py`

- `TicketProductAdmin` (~l. 1801) redéfinit ses `fieldsets` : `jauge_par_evenement` juste
  après `max_per_user`. `ProductAdmin.fieldsets` (~l. 1350) est partagé par tous les
  produits, on n'y touche pas.
- `TicketPriceInlineForm` (~l. 748) : mettre à jour le `help_text` de `stock`
  (« 0 = plus de places, vide = illimité »).
- La duplication de produit (`_duplicate_product`, `pk = None`) copie le champ seule.

### 4.11 API v2 — `api_v2/serializers.py`, `openapi-schema.yaml`, `GUIDELINES.md`

- **Création de produit** : lire une `additionalProperty` nommée `capacityPerEvent`, sur le
  modèle de `maxPerUser` (~l. 1273). Valeur entière ≥ 1, sinon erreur 400.
- **Lecture** (`ProductSchemaSerializer.to_representation`) : aujourd'hui, le produit ne porte
  d'`additionalProperty` qu'en mode comptable, posée par **affectation**
  (~l. 1033-1034). Construire la liste, y ajouter `capacityPerEvent` quand le champ est
  renseigné, puis y **ajouter** les propriétés comptables. Ne rien écraser.
- `openapi-schema.yaml` : ajouter `capacityPerEvent` au niveau **produit** (le `maxPerUser`
  de la l. 2842 est celui de l'Offer, le tarif). Préciser `inventoryLevel` (D9).
- `api_v2/GUIDELINES.md` : ajouter la correspondance `capacityPerEvent ↔
  Product.jauge_par_evenement`.
- Skill `tibillet-api` (`TECH_DOC/SKILLS/`) : vérifier s'il décrit la création de produit, et
  le compléter.

---

## 5. Tests

Lire `tests/PIEGES.md` avant d'écrire. Lancer par le skill `tibillet-test`, sous `ulimit`,
fichiers ciblés (d'autres agents utilisent la même base). Chaque test est vu **échouer** sur
une mutation volontaire avant d'être livré.

Pièges applicables : 9.23 (`TicketProduct.objects` rend n'importe quel produit), 9.47
(identifiants de tuile avec `__`), 13.19 (`Reservation.datetime` en `auto_now` : dater par
`update()`), 13.21 (`django_db`), et la mise à jour des schémas `test_*` après une migration
de TENANT_APP (`tests/PIEGES.md`, ~l. 2570).

### 5.1 Étape 0 — combler les trous des tests existants, AVANT tout code

Inventaire du 2026-11-13. Déjà couverts : jauge événement dépassée (`test_parite…:1955`, les
deux parcours), panier complet / quantité / en cours / rejeu (`test_panier_session.py:371,
715, 766, 1128`), stock du tarif épuisé et quantité (`test_parite…:818, 838`), stock et panier
(`test_panier_session.py:751`), paiement en cours retenu 30 min (`test_parite…:2093`), caisse
jauge et stock (`test_billetterie_pos.py:437, 541`), `places_restantes`
(`test_event_places_restantes.py`), plafond et affichage (`test_booking_counter_max.py`,
`test_event_retrieve_plafond_billets.py`).

Tests à écrire sur le code **actuel** (ils doivent passer) :

1. Billets d'un **autre événement** sur le même tarif : ignorés par le stock du tarif.
2. Billets **annulés** (`CANCELED`) : ne comptent ni dans la jauge, ni dans le stock du tarif.
3. Réservation **directe** : les billets en cours de paiement comptent dans la jauge de
   l'événement (aujourd'hui testé pour le panier seulement).
4. Billet en cours de paiement depuis **plus de 30 minutes** : ne compte plus.
5. API v2 : réservation refusée quand l'événement est complet, et quand le tarif est épuisé.
6. Tuiles de caisse (A2) : jauge du tarif quand `Price.stock` existe, sinon de l'événement.

### 5.2 Tests du chantier

7. `Product.places_restantes_pour_l_evenement` : vide = `None` ; valides et en cours comptés ;
   autre événement ignoré ; annulés ignorés.
8. P1 : produit à 3 places, 2 « plein » vendus, demande 2 « réduit » → refus avec le nom du
   produit ; 1 « réduit » → accepté.
9. P1 : deux tarifs du même produit **dans un seul envoi** dépassent la jauge → refus.
10. P2 : 2 « plein » au panier, ajout de 2 « réduit » sur un produit à 3 → refus.
11. P2 : envoi groupé (`add_tickets_batch`) de deux tarifs du même produit → refus.
12. P2 : la jauge se remplit entre l'ajout et le paiement → l'item sort au rejeu.
13. P3 : jauge produit refusée ; deux tarifs du même produit dans le même panier de caisse.
14. P3 : billets en cours de paiement comptés (D5), avec le message explicite. **Écrit en
    rouge d'abord** (comportement actuel), puis vert.
15. P3 : `jauge_max = 0` → complet (D10).
16. D9 : migration de données (`stock` 0 et négatif → `None`) ; `stock = 0` → tarif épuisé,
    en ligne et en caisse ; `stock = None` → illimité.
17. D1 : `jauge_par_evenement = 0` refusé par l'admin.
18. A1 : `max_billets` tient compte du stock restant du tarif et de la jauge produit ;
    `produit_complet` vrai quand le produit est plein ; message affiché.
19. A2 : tuile qui montre la jauge la plus contraignante, sur la construction **réelle** des
    articles de caisse.
20. A3 : `choisir_la_jauge_la_plus_contraignante` (bon niveau ; liste vide → `None`) ; une
    vente déclenche bien `broadcast_jauge_event` après le commit
    (`django_capture_on_commit_callbacks`), avec la bonne tuile ; une erreur du channel layer
    ne fait pas échouer la vente.
21. Admin : champ présent dans `TicketProductAdmin`, absent de l'admin adhésion.
22. API v2 : création avec `capacityPerEvent`, relecture normale et avec `?accounting=true`
    (propriétés comptables toujours présentes).

**E2E Playwright :**

23. Défaut A, bouton « réserver » : deux produits, question obligatoire sur « avec repas ».
    Seulement « sans repas » → la réservation part, la question est cachée. « Avec repas » →
    la question apparaît et bloque tant qu'elle est vide.
24. Même scénario avec le bouton « ajouter au panier » (`booking-add-to-cart`).
25. **Test existant à adapter** : `tests/e2e/test_reservation_validations.py` (l. 143-144 et
    191-192) coche le champ oui/non **avant** de monter le compteur. Monter le compteur
    d'abord.
26. Caisse, mise à jour en direct : une vente sur une caisse met à jour la tuile d'une
    seconde caisse ouverte.

---

## 6. Fichiers touchés (estimation)

| Fichier | Changement |
|---|---|
| `BaseBillet/models.py` | champ `Product.jauge_par_evenement` + méthode ; `Price.stock` (validateur, aide) ; `Price.places_restantes_pour_l_evenement` ; `out_of_stock` |
| `BaseBillet/migrations/00xx_…` | `AddField` produit, `AlterField` `Price.stock`, migration de données `stock <= 0 → None` |
| `BaseBillet/validators.py` | P1 |
| `BaseBillet/services_panier.py` | étape 5 |
| `BaseBillet/views.py` | `produit_complet`, plafonds |
| `BaseBillet/templates/commun/formulaires/reservation.html` | message produit, `fieldset` des questions, script |
| `BaseBillet/signals.py` | déclencheur de la diffusion décommenté, `post_delete` |
| `laboutik/views.py` | P3, tuiles (comptages groupés, jauge la plus contraignante), `stock is not None` |
| `wsocket/broadcast.py` | `choisir_la_jauge_la_plus_contraignante`, `broadcast_jauge_event` |
| `Administration/admin/products.py` | `TicketProductAdmin.fieldsets`, aide de `stock` |
| `api_v2/serializers.py`, `api_v2/openapi-schema.yaml`, `api_v2/GUIDELINES.md` | `capacityPerEvent`, `inventoryLevel` |
| `CHANGELOG/2026-xx-xx-jauge-par-produit.md` | fiche du chantier (migration : **Oui**) |
| `tests/pytest/…`, `tests/e2e/…` | §5 |

Chaînes traduisibles nouvelles : environ 8. Le workflow i18n est à lancer par le mainteneur.

**Déploiement :** migration sur tous les schémas de lieux (TENANT_APP), puis
`supervisorctl restart gunicorn daphne celery`. Avant : compter les événements à venir à
`jauge_max = 0` (§4.3).
