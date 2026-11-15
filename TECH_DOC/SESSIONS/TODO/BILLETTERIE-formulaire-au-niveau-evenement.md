# BILLETTERIE — Formulaire dynamique au niveau de l'événement

> **Status :** idée du 2026-11-13, **spec à écrire**.
> **Origine :** discussion de l'issue GitHub #496 (« Paramétrer une jauge par produit de
> billetterie »). Le mainteneur a sorti cette idée du chantier de la jauge pour en faire un
> chantier à part.
> **Pré-requis :** le chantier de l'issue #496 terminé (`BILLETTERIE-jauge-par-produit.md`). Il corrige l'affichage du formulaire
> dynamique (défaut A, voir §2). Ce chantier-ci doit partir du code corrigé.

---

## 1. L'idée

Aujourd'hui, les questions du formulaire dynamique (`ProductFormField`) sont attachées au
**produit**. On veut pouvoir aussi poser des questions au niveau de l'**événement**.

Cela sépare deux sortes de questions :

| Niveau | Exemple de question | Posée quand |
|---|---|---|
| Événement | « Comment avez-vous connu l'événement ? », « Besoin d'un accès PMR ? » | à toute réservation de l'événement, quel que soit le billet |
| Produit | « Végé ou viande ? » sur le produit « Billet avec repas » | seulement si un tarif de ce produit est choisi |

**Pourquoi :**

- Aujourd'hui, une question commune à tous les billets doit être recopiée sur chaque produit de
  l'événement.
- Si la personne prend deux produits qui portent la même question, le serveur refuse la
  réservation avec « Duplicate field label » (`build_custom_form_from_request`,
  `BaseBillet/validators.py`). Les réponses sont rangées par **libellé de question**, et deux
  questions de même libellé entrent en collision.
- Un mécanisme « copier le formulaire vers un autre produit » a été **écarté** le 2026-11-13 :
  il garde la collision de libellés, et les copies finissent par diverger.

**Ne pas confondre** avec le nom et le prénom par billet : ils existent déjà, via
`Product.nominative`.

---

## 2. État actuel (code lu le 2026-11-13)

- **Modèle :** `ProductFormField` (`BaseBillet/models.py`), clé étrangère `product` →
  `Product.form_fields`. Le `name` (slug) est unique **par produit**, pas par événement.
- **Affichage :** `BaseBillet/templates/commun/formulaires/reservation.html` boucle sur
  `event.products.all` et affiche les questions de **chaque** produit de l'événement.
- **Validation :** `ReservationValidator` appelle `build_custom_form_from_request` avec les
  seuls produits choisis.
- **Stockage :** un JSON par réservation, `Reservation.custom_form`, rangé par libellé de
  question. L'API v2 le relit sous le nom `customForm`.
- **Adhésions :** le même modèle sert au formulaire d'adhésion (`Membership.custom_form`). Ce
  chantier ne doit pas casser ce parcours.

**Défaut corrigé par le chantier de l'issue #496** (à vérifier avant de démarrer) :

- **A.** Le formulaire affichait les questions de tous les produits, même ceux qui ne sont pas
  choisis. Une question obligatoire sur un produit non choisi bloquait le navigateur.

**Limite gardée volontairement** (décision du mainteneur, 2026-11-13) :

- **B.** Une seule réponse par réservation : avec 3 billets « avec repas », la personne ne
  répond qu'une fois à « végé ou viande ». Pas de réponse par billet, pas de question de
  quantité. Ne pas rouvrir ce point sans demande du mainteneur.

---

## 3. Pistes de design (à trancher en écrivant la spec)

1. **Où accrocher la question d'événement ?**
   - a) un nouveau modèle `EventFormField`, calqué sur `ProductFormField` ;
   - b) `ProductFormField` avec deux clés étrangères facultatives, `product` ou `event`, et une
     contrainte « exactement une des deux ».
   La piste b) réutilise le rendu et la validation existants. Elle complique la contrainte
   d'unicité du `name`.
2. **Une réponse par réservation**, comme les questions de produit (limite B gardée).
3. **Collision des libellés** entre une question d'événement et une question de produit : les
   ranger sous deux clés séparées dans le JSON, ou refuser le doublon dès l'admin.
4. **Événements récurrents et duplication d'événement :** les questions d'événement doivent
   suivre la duplication.
5. **Parcours à couvrir :** réservation directe, panier (`services_panier.py` transporte un
   `custom_form` par item), API v2 (création et lecture de `customForm`), admin (détail des
   réponses par événement, `BaseBillet/views.py`, vue admin de l'événement), export des
   réservations.

---

## 4. Questions ouvertes pour le mainteneur

- Les questions d'événement doivent-elles aussi exister pour les ressources (`booking`), qui
  lisent déjà les questions du produit de la ressource ?
- Faut-il un modèle de questions réutilisable d'un événement à l'autre (bibliothèque de
  questions), ou la duplication d'événement suffit-elle ?
