# Admin — filtres par date à améliorer / Admin — date filters to improve

**Date :** 2026-09-30
**Origine :** passage des filtres « Produit » et « Événement » de l'admin en listes
déroulantes (`DropdownFilter` d'Unfold), et `list_filter_submit = True` posé sur le
`ModelAdmin` de base (`Administration/admin/base.py`).

Ce fichier liste ce qui reste à faire sur les filtres **par date**. Rien n'a été modifié
sur ces filtres.
/ What is left to do on the admin date filters. Nothing was changed on them.

---

## 1. Le problème

La plupart des listes de l'admin utilisent le filtre de date par défaut de Django.
Il propose cinq liens : « Toutes les dates », « Aujourd'hui », « Les 7 derniers jours »,
« Ce mois-ci », « Cette année ».

On ne peut pas choisir une période précise : impossible de demander « les adhésions
payées entre le 1er et le 15 mars », ou « les réservations de l'an dernier ».

## 2. Ce qui existe déjà

Unfold fournit deux filtres « du… au… » avec un sélecteur de date
(`unfold.contrib.filters.admin`) :

- `RangeDateFilter` : deux dates.
- `RangeDateTimeFilter` : deux dates avec l'heure.

Le projet a sa propre variante, `RangeDateTimeFilterWithTimeZone`
(`Administration/admin_tenant.py`). Elle lit le fuseau horaire du lieu dans
`Configuration`, pour que « le 1er mars à 0 h » soit l'heure du lieu et pas l'heure UTC.
Elle est déjà utilisée sur deux listes :

| Liste | Page | Champ |
|---|---|---|
| Événements | `/admin/BaseBillet/event/` | `datetime` |
| Ventes (lignes article) | `/admin/BaseBillet/lignearticle/` | `datetime` |

Ces filtres sont des champs de formulaire : ils sont envoyés par le bouton « Filtrer »
du panneau. Ce bouton est maintenant présent sur toutes les listes.

## 3. Les listes à convertir

Elles ont encore le filtre par défaut de Django.

| Liste | Page | Champ(s) |
|---|---|---|
| Adhésions | `/admin/BaseBillet/membership/` | `last_contribution`, `deadline` |
| Réservations | `/admin/BaseBillet/reservation/` | `datetime` |
| Billets | `/admin/BaseBillet/ticket/` | `reservation__datetime` |
| Paiements Stripe | `/admin/BaseBillet/paiement_stripe/` | `order_date` |
| Réservations de ressources | `/admin/booking/booking/` | `start_datetime` |
| Mouvements de stock | `/admin/inventaire/mouvementstock/` | `cree_le` |
| Initiatives | `/admin/crowds/initiative/` | `created_at` |
| Invitations d'accès | `/admin/onboard/onboardinvitation/` | `expires_at`, `used_at` |
| Configurations en attente | `/admin/MetaBillet/waitingconfiguration/` | `datetime` |

**Le changement, pour chaque liste.** Dans `list_filter`, remplacer le nom du champ par
un couple (champ, filtre) :

```python
# Avant / Before
list_filter = ['last_contribution', 'deadline']

# Après / After
list_filter = [
    ('last_contribution', RangeDateTimeFilterWithTimeZone),
    ('deadline', RangeDateTimeFilterWithTimeZone),
]
```

## 4. Points à trancher avant de convertir

- **On perd les raccourcis.** « Aujourd'hui » et « Les 7 derniers jours » disparaissent :
  il faut saisir deux dates. Pour les listes consultées tous les jours (ventes,
  réservations), c'est plus lent pour le cas courant. À voir liste par liste, ou garder
  les deux filtres côte à côte sur le même champ.
- **Date seule ou date et heure.** Pour une adhésion ou une échéance, l'heure n'a pas
  d'intérêt : `RangeDateFilter` suffit et demande deux saisies au lieu de quatre. Mais
  `RangeDateFilter` n'a pas de variante « fuseau du lieu » dans le projet : il faudrait
  l'écrire, sinon une vente faite à 0 h 30 heure locale peut tomber sur la veille.
- **`RangeDateTimeFilterWithTimeZone` ignore une borne incomplète.** Dans sa méthode
  `queryset`, une borne n'est prise en compte que si la date ET l'heure sont remplies.
  Si l'admin saisit seulement la date, le filtre ne fait rien, sans message. À corriger
  avant de l'étendre : prendre 00:00 pour le début et 23:59 pour la fin quand l'heure
  est vide.
- **Champ traversant une relation.** Pour les billets, le champ est
  `reservation__datetime`. À vérifier : `RangeDateTimeFilter` accepte-t-il un chemin
  avec `__`, et le nom des champs du formulaire reste-t-il correct.

## 5. Le filtre de période fait maison des tireuses

`controlvanne/admin.py` a son propre filtre `DateRangeFilter`, avec son gabarit
`controlvanne/templates/admin/date_range_filter.html` (deux champs `date_from` et
`date_to`). Il est utilisé sur quatre listes :

| Liste | Page |
|---|---|
| Historique des cartes | `/admin/controlvanne/historiquecarte/` |
| Historique des tireuses | `/admin/controlvanne/historiquetireuse/` |
| Historique de maintenance | `/admin/controlvanne/historiquemaintenance/` |
| Sessions d'étalonnage | `/admin/controlvanne/sessioncalibration/` |

Il fait le même travail que `RangeDateFilter` d'Unfold. Le remplacer supprimerait une
classe et un gabarit à maintenir, et donnerait le même sélecteur de date partout.
À vérifier avant : sur quel champ de date chaque liste filtre, et si des liens ou des
exports réutilisent les paramètres `date_from` / `date_to` dans l'URL.

## 6. Vérifications à prévoir

- Un test par liste convertie : la page s'affiche, et une période saisie filtre bien.
  Modèle à suivre : `tests/pytest/test_admin_filtre_produit_liste_deroulante.py`.
- Un test sur le fuseau horaire : une vente à 0 h 30 heure du lieu doit sortir dans la
  journée locale, pas dans la veille.
- Un passage à l'écran : le sélecteur de date d'Unfold dans le panneau de filtres, sur
  mobile et en thème sombre.
