# API v2 des ventes : publier les règlements (après la production)

**Décision du mainteneur (2026-10-05, Q-H8 du chantier 05)** : chantier **après la mise
en production**, hors du chantier 05.

## Le problème
`/api/v2/sales/` publie une ligne vendue avec `quantity`, `vat` et une propriété
`payment_method` lue sur la ligne (`api_v2/serializers.py` ~l.858). Depuis la fiche H-1
du chantier 05 (une ligne par article), les lignes écrites par la caisse, la tireuse et
le QR / NFC ont un `payment_method` **vide** : le moyen est dans les règlements de la
vente (`Reglement`). La propriété n'est donc plus publiée pour ces ventes. Elle
disparaît pour toutes les lignes en H-2 (colonne retirée).

Exemple : vente n° 1016, « Verre × 3, 10,50 € », payée 5 € en monnaie locale + 5,50 €
en CB : l'API publie la ligne sans moyen.

## Piste
Publier sur chaque ligne le numéro de sa vente et les règlements de cette vente (moyen,
montant), et l'écrire dans `api_v2/openapi-schema.yaml`. Voir `api_v2/GUIDELINES.md`.
Q-G6 (chantier 05, fiche G) : contrat des « parts » revu ici aussi.
