# Issue #290 : exports — questions du formulaire dans l'ordre d'affichage

## Ce qui a été fait

Dans l'export des billets et dans l'export des adhésions, les colonnes des réponses au
formulaire personnalisé sortent maintenant dans l'ordre d'affichage du formulaire, et non
plus par ordre alphabétique.

- Ordre : produits dans leur ordre d'affichage, puis questions de chaque produit dans
  leur ordre d'affichage (réglé par glisser-déposer dans l'admin du produit).
- Seules les questions qui ont des réponses dans les objets exportés deviennent des
  colonnes (inchangé).
- Une réponse dont la question a été renommée ou supprimée sort toujours, en fin de
  tableau (inchangé).

Non traité : choisir les questions à exporter (second point de l'issue).

Détails : `CHANGELOG/2026-10-01-issue-290-export-ordre-questions.md`.

### Modifications

| Fichier | Changement |
|---|---|
| `Administration/importers/reponses_formulaire_export.py` | Nouveau module : tri des colonnes |
| `Administration/importers/ticket_exporter.py` | `before_export` des billets |
| `Administration/importers/membership_importers.py` | `before_export` des adhésions |
| `tests/pytest/test_export_reponses_formulaire.py` | 4 tests |

## Pourquoi on ne voit rien sur les données de démo

Sur les données de dev, l'ordre d'affichage des questions est partout le même que l'ordre
alphabétique de leurs libellés (« 22, TEST », « Nom, Telephone »…). L'export est donc
identique avant et après. Il faut mettre les questions dans un ordre non alphabétique
pour voir la différence (voir la préparation).

## Préparation

1. Admin > un produit billet utilisé par un événement à venir > onglet des champs de
   formulaire. Créer, dans cet ordre :
   « Prénom », « Nom », « Téléphone », « Atelier choisi », « Régime alimentaire ».
2. Faire 2 réservations sur cet événement en répondant aux questions.
3. Sur un produit adhésion, créer les mêmes questions dans le même ordre, et prendre
   2 adhésions en y répondant.

## Tests à réaliser

### Test 1 : export des billets
1. Admin > Billets, filtrer sur l'événement, exporter en Excel (ou CSV).
2. **Attendu :** les colonnes des réponses sont dans l'ordre
   Prénom, Nom, Téléphone, Atelier choisi, Régime alimentaire.
   (Avant : Atelier choisi, Nom, Prénom, Régime alimentaire, Téléphone.)

### Test 2 : l'ordre suit le glisser-déposer
1. Dans l'admin du produit billet, glisser « Régime alimentaire » en premier, enregistrer.
2. Refaire l'export du test 1.
3. **Attendu :** « Régime alimentaire » est la première colonne de réponses.

### Test 3 : export des adhésions
1. Admin > Adhésions, filtrer sur le produit adhésion de la préparation, exporter.
2. **Attendu :** même ordre que dans le formulaire d'adhésion.

### Test 4 : question supprimée
1. Supprimer la question « Atelier choisi » du produit billet.
2. Refaire l'export du test 1.
3. **Attendu :** la colonne « Atelier choisi » est toujours là, avec les anciennes
   réponses, mais en **dernière** position.

### Test 5 : pas de colonnes d'un autre événement
1. Exporter les billets d'un autre événement, qui n'utilise pas ce produit.
2. **Attendu :** aucune des colonnes Prénom, Nom… de la préparation.

## Tests automatiques

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_export_reponses_formulaire.py -v
```

## Compatibilité

- Aucune migration, aucun changement de données.
- Mêmes colonnes qu'avant, seul leur ordre change.
- Si plusieurs produits d'un même export ont une question au libellé identique, il n'y a
  qu'une colonne (leurs réponses sont rangées sous la même clé), placée à la position de
  la première de ces questions.
