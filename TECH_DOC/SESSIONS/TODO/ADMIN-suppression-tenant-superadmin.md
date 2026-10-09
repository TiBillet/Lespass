# Admin — supprimer un lieu depuis la liste superadmin

> **Statut** : idée, spec à écrire. Demande du mainteneur (2026-10-09), pendant la
> répétition R-4 du chantier 05.
> Pré-requis : chantier 05 en production.

## Le besoin, en une phrase
Pouvoir supprimer un lieu (tenant) **à la main, un par un**, depuis la liste des lieux de
l'admin superadmin (`/admin/Customers/client/`, ex. https://codecommun.tibillet.coop/admin/Customers/client/),
au lieu d'une suppression en masse des lieux inactifs la nuit de la bascule.

## Pourquoi
La suppression en masse des lieux inactifs (fiche R §18, commande
`supprimer_lieux_inactifs`) a été **abandonnée** le 2026-10-09 : beaucoup de lieux sans
activité attendent la V2 pour tester de nouveau. Les supprimer d'un coup ferait des
frictions. Le tri se fera au cas par cas, par un humain qui connaît le lieu.

## Ce qui existe déjà (commité, `97a2b40c` et avant)
- `Administration/nettoyage_des_lieux.py` : lecture des traces d'un lieu (activité,
  configuration personnalisée, citations par d'autres lieux, monnaies, Stripe Connect,
  place Fedow), suppression en **SQL brut**, une transaction par lieu.
  `Client.delete()` est inutilisable (piège 12.5 de `tests/PIEGES.md`).
- `Administration/management/commands/supprimer_lieux_inactifs.py` : la même chose en masse,
  avec rapport, passage à blanc, mail aux administrateurs.
- Commande Fedow `renommer_places_orphelines` (dépôt `../Fedow`) : renomme la place Fedow
  d'un lieu supprimé (sinon un lieu recréé sous le même nom échoue à l'onboarding,
  `BUGS-constats-chantier-05.md` n°34).

## Pistes (à trancher dans la spec)
- Une action d'admin Unfold sur `Client` (une ligne cochée → écran de confirmation qui
  affiche les traces du lieu, comme le rapport de `supprimer_lieux_inactifs`) qui
  réutilise `nettoyage_des_lieux.py`.
- Garde : refus si le lieu a de l'activité (ventes, adhésions…) sauf confirmation
  explicite ; superadmin seulement.
- Mail aux administrateurs du lieu (texte de la fiche R §18) : oui / non ?
- Place Fedow et compte Stripe Connect : renommer / lister pour plus tard.
- Les utilisateurs et leurs portefeuilles restent (décision R-N : « on ne touche surtout
  pas aux utilisateurs »).
