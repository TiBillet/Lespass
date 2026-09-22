## Panier

### État actuel

Le panier permet de faire une commande groupée de plusieurs types d'objet achetable différent, pour l'instant des `Membership`, `Reservation` 
et des `Booking`, respéctivement pour les adhésions, les réservations d'évènement (type billetterie) et les réservations de ressources (type salle ou machine).

#### Fichier principaux

Tout les fichiers sont dans Basebillet

1. views.py : Contient `PanierMVT` qui intéragit avec `PanierSession`. Possède les méthodes pour ajouter des items au panier : (`add_membership`, `add_tickets_batch` et `add_resource`)
2. services_panier.py : contient `PanierSession` qui stocke le panier en session sous forme de JSON, et contient toutes les fonctions pour intéragir avec.
3. service_commande.py : contient `CommandeService` qui crée l'object `Commande` en BDD et initialise le paiement si besoin.
4. context_processors.py : contient `panier_context` qui ajoute les informations du panier au contexte.
5. panier.html : affichage de `panier_content.html`
6. panier_content.html : affichage le panier, inclut `panier_item.html` pour l'affichage des items
7. panier_item.html : affiche les items selon leurs types
8. panier_toast.html et panier_badge.html : le premier contient juste un include vers le deuxième. Sert uniquement à mettre à jour l'affichage de l'icône du panier

#### Workflow du panier : 
1. Item ajouté au panier -> `PanierMVT`.`add_membership`, `add_tickets_batch` ou `add_resource` est appelé selon le type d'item à ajouter.
2. `add_membership`, `add_tickets_batch` ou `add_resource` appelle la fonction équivalente de `PanierSession` qui contient des vérifications adaptées au type de l'item.
3. L'utilisateur valide son panier : `PanierMVT`.`checkout` est appelé. Il revalide le contenu du panier avec `PanierSession`.`revalidate_all` qui vide le panier puis ajoute à nouveau tous les item un par un.
4. Si la `revalidate_all` retourne des erreurs, elles sont affichés sur la vue du panier. Sinon la logique continue 
5. Ensuite `PanierMVT`.`checkout` appelle `CommandeService`.`materialiser`. Cette méthode va créer tous les objets en python depuis le JSON, créer les `LigneArticle` associé, puis créer une `Commande` qui va contenir tous ces items.
6. Ici ça va dépendre de si les items dans le panier doivent être payé ou non : 
   - Si la commande nécessite un paiement, un `Paiement_Stripe` est créé, puis associé à la commande (via `CommandeService`.`_creer_paiement_stripe`).
   L'utilisateur est ensuite redirigé vers l'url stripe pour payer. Une fois le paiement éffectué, la rediction se fait sur `Event`.`stripe_return` dans TOUS les cas, même si il n'y a pas de réservation dans la commande.
   - Si la commande ne nécessite pas de paiement, elle est validé directement via `CommandeService`.`_finaliser_gratuit`, puis l'utilisateur est redirigé sur "my_account/my_reservations"

#### Fonctionnement particulier avec le panier
1. Quand un tarif pour un `Event` ou une `Resource` nécessite une adhésion obligatoire (`Price`.`adhesions_obligatoires`), 
   on vérifie les adhésions de l'utilisateur, mais également les adhésions contenues dans son panier (avec `in_cart` dans tibitags.py)
2. Il y a maintenant deux mécaniques de paiement pour les objets pouvant aller dans le panier : soit le paiement avec le panier bouton "Add to cart", soit le paiement direct sans passer par le panier.

### Manque

À terme le panier sera stocké en BDD au lieu d'être stocké en session. 
Cela simplifiera la "réservation" temporaires d'un ticket ou d'une ressource quand elle sera dans le panier de quelqu'un par exemple.
Cela permettra également de stocker les objets en tant que telle, au lieu de faire une conversion en JSON, ce qui n'est pas très pratique.


### Bugs connus

Mis à jour le 2026-09-21 (chantier de tests, voir `TECH_DOC/SESSIONS/PANIER/SPEC.md` et
`CHANGELOG/2026-09-21-tests-panier.md`).

- Adhésion ajoutée, tarif adhérent pris, puis adhésion retirée : pour un **billet**, le tarif est
  refusé au paiement (`revalidate_all()` rejoue les items, prouvé par un test). Le panier affiche
  encore le tarif adhérent tant qu'on n'a pas payé. Pour une **ressource**, la vérification
  manquait côté serveur : corrigé (C2).
- Événement qui porte un produit « réservation gratuite » ET un produit payant (C27) : corrigé
  le 2026-09-21. Les billets gratuits partent avec les billets payés, en un seul envoi, après
  le paiement ; si le paiement ne passe pas, rien n'est envoyé.
- Défauts connus, prouvés par des tests `xfail` et non corrigés : liste dans le SPEC (§1 et §10).

### Remarque

Le terme "resource" est employé alors que le terme adapté devrait peut-être être "booking". Comme pour `Membership` par exemple où on utilise le nom de
l'objet final qui sera créé. À voir.

Les codes promo sont testés depuis le 2026-09-21 (par item, avec et sans panier) ; un code ne remise plus que son produit (C5).

Quand on crée le paiement stripe avec le panier, ses champs `booking` et `reservation` sont nulles, tout passe par son champ `commande`.

### À tester

Fait le 2026-09-21 : logique du panier, codes promo, paiement avec et sans panier pour chaque
type d'article, méthodes d'ajout (`add_ticket`, `add_membership`, `add_resource`), paiement réel
en E2E. Remboursement avec et sans panier : chantier `TECH_DOC/SESSIONS/REMBOURSEMENT/`.
