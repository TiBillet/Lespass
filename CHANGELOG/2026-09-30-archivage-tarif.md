# Archivage des tarifs : « supprimer » un tarif l'archive / Price archiving: "deleting" a price archives it

**Date :** 2026-09-30
**Migration :** Oui — `BaseBillet/migrations/0231_price_archived.py` (`migrate_schemas`)

**FR :** Un tarif (`Price`) ne pouvait pas être supprimé : les ventes passées (`PriceSold`),
les adhésions et les commandes de caisse pointent vers lui en `PROTECT`. Un tarif créé par
erreur restait donc affiché pour toujours. Maintenant, `Price.delete()` archive le tarif
(`archived=True`, `publish=False`) au lieu de l'effacer. La ligne reste en base : l'historique
des ventes est intact. Un tarif archivé n'est plus affiché ni accepté nulle part (site,
panier, caisse, API, admin). La suppression est réactivée dans l'admin (case « Supprimer »
de la fiche produit, bouton « Supprimer » de la fiche tarif) et elle archive.
`Price.hard_delete()` efface vraiment (tests, nettoyages).

**EN :** A `Price` could not be deleted: past sales (`PriceSold`), memberships and saved POS
orders point to it with `PROTECT`. `Price.delete()` now archives the price (`archived=True`,
`publish=False`) instead of removing it. The row stays, sales history is untouched. An
archived price is never shown nor accepted anywhere (site, cart, POS, API, admin). Deletion
is re-enabled in the admin and archives. `Price.hard_delete()` really deletes (tests, cleanups).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Price.archived`, `Price.delete()` archive, `Price.hard_delete()`, `save()` dépublie un tarif archivé, `Product.tarifs_non_archives()`, tarif gratuit FREERES recréé si l'ancien est archivé |
| `BaseBillet/migrations/0231_price_archived.py` | Ajout du champ / Adds the field |
| `Administration/admin/products.py` | Inline des tarifs : suppression autorisée (archive), archivés cachés, duplication sans les archivés |
| `Administration/admin/prices.py` | `PriceAdmin` : suppression autorisée (archive), page de confirmation sans objets protégés, archivés cachés |
| `Administration/admin_tenant.py`, `Administration/importers/membership_importers.py` | Sélecteurs de tarif sans les archivés |
| `BaseBillet/views.py`, `BaseBillet/validators.py`, `BaseBillet/services_panier.py` | Affichage et saisie : tarifs archivés exclus / refusés |
| `api_v2/serializers.py`, `ApiBillet/views.py`, `ApiBillet/serializers.py` | API : tarifs archivés exclus |
| `laboutik/views.py`, `kiosk/credit.py`, `controlvanne/models.py`, `controlvanne/billing.py` | Caisse, borne, tireuse : tarifs archivés exclus |
| `booking/`, `crowds/views.py`, `fedow_connect/views.py` | Tarifs archivés exclus / non réutilisés |
| `pages/templates/pages/faire_festival/vues/adhesions.html` | Boucle sur `product.tarifs_non_archives` |
| `tests/pytest/test_price_archivage.py` | Nouveaux tests / New tests |
| `tests/pytest/*.py` (7 fichiers) | Nettoyages : `price.delete()` → `price.hard_delete()` |
