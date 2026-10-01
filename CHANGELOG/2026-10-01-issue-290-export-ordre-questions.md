# Issue #290 : exports — questions du formulaire dans l'ordre d'affichage / Exports: form questions in display order

**Date :** 2026-10-01
**Migration :** Non

**FR :** Dans l'export des billets et dans l'export des adhésions, les colonnes des réponses
au formulaire personnalisé étaient triées par ordre alphabétique de leur libellé. Sur un
vrai formulaire (« Prénom, Nom, Téléphone, Atelier choisi… »), les colonnes sortaient
mélangées (« Atelier choisi, Nom, Prénom, Téléphone… ») et il fallait les réordonner à la
main à chaque export. Le tri alphabétique de Python plaçait aussi les libellés en
majuscules avant ceux en minuscules.

Les colonnes sortent maintenant dans l'ordre d'affichage : les produits dans leur ordre
d'affichage, puis les questions de chaque produit dans leur ordre d'affichage (celui réglé
par glisser-déposer dans l'admin du produit).

Ce qui ne change pas :
- seules les questions qui ont des réponses dans les billets ou adhésions exportés
  deviennent des colonnes ;
- le titre de colonne est le libellé de la question ;
- une réponse dont la question a été renommée ou supprimée sort toujours, en fin de
  tableau, par ordre alphabétique.

Le second point de l'issue (choisir les questions à exporter) n'est pas traité.

**EN :** In the ticket and membership exports, custom form answer columns were sorted
alphabetically. They now follow the display order: products in display order, then each
product's questions in display order. Only questions with answers in the exported objects
become columns; answers whose question was renamed or deleted are still exported, at the
end. Choosing which questions to export (second point of the issue) is not done.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `Administration/importers/reponses_formulaire_export.py` | Nouveau : `cle_de_la_reponse` et `cles_des_reponses_a_exporter` (tri dans l'ordre d'affichage, réponses orphelines à la fin) |
| `Administration/importers/ticket_exporter.py` | `TicketExportResource.before_export` : lit les produits des billets (une requête) et trie via le nouveau module |
| `Administration/importers/membership_importers.py` | `MembershipExportResource.before_export` : idem pour les adhésions |
| `tests/pytest/test_export_reponses_formulaire.py` | Nouveaux tests : ordre des billets, réponse orpheline, export complet, ordre des adhésions |
