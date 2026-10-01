# Admin : filtres en liste déroulante et navigation sans les pages d'application / Admin: dropdown filters and navigation without the app pages

**Date :** 2026-09-30 → 2026-10-01
**Migration :** Non

**FR :** Plusieurs changements sur l'admin pour la rendre plus lisible.

1. **Filtres en liste déroulante.** Les filtres qui affichaient une longue liste de liens
   (produits, événements, tireuses, assets…) sont des listes déroulantes avec recherche
   (filtres `DropdownFilter`, `RelatedDropdownFilter` et `ChoicesDropdownFilter` d'Unfold).
   Les produits sont triés par nom.
2. **Bouton « Filtrer » partout.** `list_filter_submit = True` est posé sur le `ModelAdmin`
   de base du projet : toutes les listes de l'admin en héritent. Ce bouton est obligatoire
   pour les filtres Unfold qui sont des champs de formulaire (liste déroulante, plage de
   dates). Les filtres classiques en liens s'appliquent toujours au clic.
3. **Liste des blocs désactivée.** `/admin/pages/bloc/` redirige vers la liste des pages,
   avec un message : un bloc se gère depuis la fiche de sa page.
4. **Pages d'accueil des applications désactivées.** `/admin/BaseBillet/`,
   `/admin/laboutik/`, etc. listaient à plat tous les modèles d'une application Django.
   Elles redirigent maintenant vers le tableau de bord. La route est gardée : Unfold et
   Django fabriquent des liens vers elle.
5. **Fil d'Ariane.** Sur une page qui n'appartient à aucun module, l'entrée de
   l'application Django (ex : « Billetterie », lien vers `/admin/BaseBillet/`) est retirée.
   Sur une page rangée dans un module, rien ne change : l'entrée est remplacée par le module.
6. **Admin des pages.** Le champ, la colonne et le filtre « page d'accueil » (`est_accueil`)
   ne sont plus affichés dans l'admin des pages (lignes commentées dans `pages/admin.py`).

**EN :** Long link-list filters became searchable dropdowns; a "Filter" submit button on
every changelist (set on the project base ModelAdmin); the flat block list, and the generic
Django app pages (`/admin/BaseBillet/`…), now redirect; the breadcrumb no longer shows the
Django app entry on module-less pages; the "home page" field is hidden in the Page admin.

### Filtres convertis / Converted filters

| Page | Filtre | Type |
|---|---|---|
| Adhésions `/admin/BaseBillet/membership/` | Produit | `DropdownFilter` |
| Ventes `/admin/BaseBillet/lignearticle/` | Produit | `DropdownFilter` |
| Ventes `/admin/BaseBillet/lignearticle/` | `status` | `ChoicesDropdownFilter` |
| Réservations `/admin/BaseBillet/reservation/` | Événement à venir, passé, archivé | `DropdownFilter` |
| Billets `/admin/BaseBillet/ticket/` | Événement à venir, passé, archivé | `DropdownFilter` |
| Codes promotionnels `/admin/BaseBillet/promotionalcode/` | `product` | `RelatedDropdownFilter` |
| Produits de caisse `/admin/BaseBillet/posproduct/` | `categorie_pos` | `RelatedDropdownFilter` |
| Produits de caisse `/admin/BaseBillet/posproduct/` | `methode_caisse` | `ChoicesDropdownFilter` |
| Réservations de ressources `/admin/booking/booking/` | `status` | `ChoicesDropdownFilter` |
| Historiques du fond de caisse `/admin/laboutik/historiquefonddecaisse/` | `point_de_vente` | `RelatedDropdownFilter` |
| Jetons `/admin/fedow_core/token/` | `asset` | `RelatedDropdownFilter` |
| Transactions `/admin/fedow_core/transaction/` | `asset` | `RelatedDropdownFilter` |
| Transactions `/admin/fedow_core/transaction/` | `action` | `ChoicesDropdownFilter` |
| Initiatives `/admin/crowds/initiative/` | `tags` | `RelatedDropdownFilter` |
| Historique des cartes, des tireuses, de maintenance, sessions d'étalonnage, sessions (`/admin/controlvanne/…`) | `tireuse_bec` | `RelatedDropdownFilter` |

Un filtre sur une relation n'est affiché que s'il a au moins deux choix (comportement de
Django). Avec une seule tireuse, par exemple, la liste déroulante n'apparaît pas.
/ A relation filter only shows with at least two choices.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/base.py` | `list_filter_submit = True` sur le `ModelAdmin` de base |
| `Administration/admin_tenant.py` | Filtres produit et événement en `DropdownFilter`, `status` des ventes et `tags` des initiatives en liste déroulante |
| `Administration/admin/prices.py` | Filtre `product` des codes promo |
| `Administration/admin/products.py` | Filtres `categorie_pos` et `methode_caisse` des produits de caisse |
| `Administration/admin/resources.py` | Filtre `status` des réservations de ressources |
| `Administration/admin/laboutik.py` | Filtre `point_de_vente` du fond de caisse |
| `controlvanne/admin.py` | Filtre `tireuse_bec` sur 5 listes |
| `fedow_core/admin.py` | Filtres `asset` et `action` |
| `pages/admin.py` | `BlocAdmin.changelist_view` redirige vers la liste des pages ; « page d'accueil » masqué dans l'admin des pages |
| `Administration/admin/site.py` | `StaffAdminSite.app_index` redirige vers le tableau de bord |
| `Administration/templatetags/tb_admin.py` | `fil_ariane_par_module` retire l'entrée de l'application quand la page n'a pas de module |
| `Administration/templates/unfold/helpers/header_title.html` | Commentaire mis à jour (aucun changement de rendu) |
| `tests/pytest/test_admin_filtre_produit_liste_deroulante.py` | Nouveaux tests : chaque filtre converti, redirection de la liste des blocs |
| `tests/pytest/test_admin_fil_ariane_et_rail.py` | Fil d'Ariane sans l'application, redirection des pages d'application |

### Reste à faire / Still to do

Les filtres par date : `CHANGELOG/a traiter/admin-filtres-par-date.md`.
