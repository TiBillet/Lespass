# Panier : réponses au formulaire personnalisé

## Ce qui a été fait

Quand on ajoute une adhésion ou des billets au panier, les réponses au formulaire
personnalisé passent maintenant par la même fonction que le parcours sans panier :
`build_custom_form_from_request` (`BaseBillet/validators.py`).

Résultat : les réponses sont rangées de la même façon, quel que soit le parcours.
- Sous le **libellé** de la question (avant : sous la clé technique du champ).
- Case à cocher en **oui / non** (avant : le texte « on »).
- Choix multiple : **toutes** les valeurs cochées (avant : la dernière seulement).
- Question obligatoire **vérifiée** à l'ajout au panier (avant : pas vérifiée).
- Choix hors liste **refusé**.

Pour les billets, seules les questions des produits dont au moins un billet est demandé
sont lues. Une question obligatoire d'un autre produit du même événement ne bloque pas.

Détails : `CHANGELOG/2026-10-01-panier-reponses-formulaire-personnalise.md`.

### Modifications

| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` | Helper `reponses_du_formulaire_personnalise_pour_le_panier`, utilisé par `PanierMVT.add_membership` et `PanierMVT.add_tickets_batch` |
| `BaseBillet/views.py` | Helper `quantite_de_billets_demandee` (lecture de la quantité, sortie de la boucle d'ajout des billets) |
| `tests/pytest/test_panier_formulaire_personnalise.py` | 7 tests |

## Préparation

Dans l'admin, sur un produit billet utilisé par un événement à venir, ajouter trois
questions au formulaire personnalisé :
1. « Votre téléphone ? » — texte court, **obligatoire**.
2. « Ateliers ? » — choix multiple, options « Soudure », « Couture », « Bois ».
3. « Bénévole ? » — interrupteur oui / non.

Sur un produit adhésion, ajouter une question « Pseudo ? » — texte court, obligatoire.

## Tests à réaliser

### Test 1 : question obligatoire vide (billets)
1. Ouvrir la page de l'événement, choisir 1 billet.
2. Laisser « Votre téléphone ? » vide, cliquer « Ajouter au panier ».
3. **Attendu :** message d'erreur qui nomme la question (« Votre téléphone ? : … »).
   Le badge du panier ne change pas.

### Test 2 : ajout complet puis paiement (billets)
1. Remplir « Votre téléphone ? », cocher « Soudure » et « Bois », activer « Bénévole ? ».
2. Ajouter au panier, aller au panier, payer (carte de test Stripe
   `4242 4242 4242 4242`, `12/42`, `424`).
3. Admin > Réservations > ouvrir la réservation.
4. **Attendu :** dans « Réponses au formulaire » :
   - « Votre téléphone ? » avec le numéro saisi ;
   - « Ateliers ? » avec **Soudure et Bois** (les deux) ;
   - « Bénévole ? » à **Oui**.

### Test 3 : produit non choisi
1. Sur un événement qui propose deux produits billet, mettre une question obligatoire
   sur le produit B seulement.
2. Choisir uniquement un billet du produit A, ajouter au panier.
3. **Attendu :** le billet est ajouté, aucune erreur sur la question du produit B.

### Test 4 : adhésion
1. Page des adhésions, ouvrir le produit avec « Pseudo ? ».
2. Cliquer « Ajouter au panier » sans remplir le pseudo.
3. **Attendu :** message d'erreur nommant « Pseudo ? », rien n'est ajouté.
4. Remplir le pseudo, ajouter au panier, payer.
5. Admin > Adhésions > ouvrir l'adhésion.
6. **Attendu :** « Pseudo ? » avec la valeur saisie, et le bouton « Modifier les réponses »
   affiche bien cette valeur dans le champ.

### Test 5 : export des billets
1. Admin > Billets, filtrer sur l'événement du test 2, exporter en CSV ou Excel.
2. **Attendu :** une colonne par question (« Votre téléphone ? », « Ateliers ? »,
   « Bénévole ? »), remplie pour le billet du test 2. « Ateliers ? » contient les deux choix.

### Test 6 : parcours sans panier inchangé
1. Refaire le test 2 avec le parcours de réservation directe (sans panier), si le lieu
   l'utilise encore.
2. **Attendu :** même affichage dans l'admin et même export qu'au test 2.

## Vérification en base

```bash
docker exec lespass_django poetry run python manage.py tenant_command shell --schema=lespass -c \
  "from BaseBillet.models import Reservation; r = Reservation.objects.exclude(custom_form__isnull=True).order_by('-datetime').first(); print(r.custom_form)"
```

**Attendu :** les clés sont les libellés des questions (`'Votre téléphone ?'`), pas des
clés techniques (`'votre-telephone'`). « Ateliers ? » est une liste, « Bénévole ? » vaut
`True`.

## Tests automatiques

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_panier_formulaire_personnalise.py -v
```

## Compatibilité

- Le panier n'est pas encore en production : aucune réponse n'a été enregistrée avec
  l'ancien format, pas de reprise de données.
- Le parcours sans panier n'est pas modifié.
- Si l'on renomme une question après que des réponses ont été enregistrées, les anciennes
  réponses restent rangées sous l'ancien libellé (comportement déjà présent avant, dans
  les deux parcours).
