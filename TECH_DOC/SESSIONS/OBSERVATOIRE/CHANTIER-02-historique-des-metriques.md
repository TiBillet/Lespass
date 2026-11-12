# CHANTIER 02 — Historique des métriques / Metrics history

**Statut :** À faire plus tard (idée du mainteneur, 2026-11-12)
**Migration :** Oui (nouvelle table)

## Le besoin

Voir l'évolution de l'usage de TiBillet dans le temps, à partir du lancement de
l'observatoire.

## Ce qui se reconstruit déjà tout seul

Les compteurs mois par mois (CA, recharges, billets, adhésions, événements,
scans, usagers) viennent des clôtures et des tables des lieux. Ils sont recalculés
chaque nuit sur toute la fenêtre (`--mois`). La courbe « instances utilisées,
mois par mois » existe donc déjà sur 24 mois, sans rien stocker.

## Ce qui ne se reconstruit pas

- Les valeurs « du jour » : nombre de lieux, comptes admin, points de vente.
- Les lieux supprimés : ils disparaissent du calcul.
- Le classement d'un lieu à une date donnée, avec les seuils de cette date.

## Piste

Une petite table, une ligne par nuit : la date, et les totaux du réseau
(lieux par activité, par nature, par taille ; CA, recharges, cartes, usagers du
mois). Écrite par `refresh_observatoire` à la fin du calcul. Lue par une courbe
dans la page.

À décider le moment venu : totaux du réseau seulement, ou une ligne par lieu ;
durée de conservation.
