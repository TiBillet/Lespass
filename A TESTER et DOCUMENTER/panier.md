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

Si un prix adhérent pris grâce à une adhésion dans le panier, manque le fait de reverifier au moment du paiement si l'utilisateur 
possède l'adhésion ou l'as dans son panier. Actuellement, il est possible d'ajouter une adhésion, 
ajouter un prix uniquement accessible avec cette adhésion, puis supprimer l'adhésion du panier tout en gardant le prix donné grâce à l'adhésion.

### Remarque

Le terme "resource" est employé alors que le terme adapté devrait peut-être être "booking". Comme pour `Membership` par exemple où on utilise le nom de
l'objet final qui sera créé. À voir.

Les codes promo n'ont PAS DU TOUT été téstés. Je ne sais pas si ils sont bien appliqué et fonctionnent correctement.

Quand on crée le paiement stripe avec le panier, ses champs `booking` et `reservation` sont nulles, tout passe par son champ `commande`.

### À tester

1. Tester si des paiements créés avant le panier peuvent bien être remboursé. (voir "refund_refactor.md" également)
2. Tester la logique du panier au global
3. Vérifier si les codes promo fonctionnent
4. Tester le paiement hors panier pour chaque item
5. Tester les méthodes d'ajout au panier
   - `PanierSession`.`add_membership`
   - `PanierSession`.`add_ticket`
   - `PanierSession`.`add_booking`
