# Libellé de prix : ce qui n'est pas encore branché sur le système commun

**Relevé du 2026-10-22.** Les cartes et fiches des événements, adhésions et ressources
passent par `BaseBillet/services_libelle_prix.py`
(voir `CHANGELOG/2026-10-22-libelle-prix-commun.md`). Trois endroits calculent encore
le prix à leur façon. On les a laissés de côté volontairement.

## 1. Newsletter : `newsletter/collecte.py:calculer_tarif`

**Aujourd'hui :** ses règles sont à elle.
- « Gratuit » pour un événement gratuit, alors que le site affiche « Entrée libre ».
- « Prix libre, à partir de X € », alors que le site affiche « Prix libre dès X € ».
- « À partir de X € » quand il y a plusieurs tarifs, alors que le site affiche « De X à Y € ».

Elle garde aussi son propre `_formater_montant`, qui met toujours une virgule, quelle que soit la langue.
Elle ne filtre ni `Price.archived` ni les tarifs en points.

**Correctif proposé :**
1. Remplacer le corps par `libelle_prix(tarifs_publies_de_l_evenement(event), TYPE_EVENEMENT)`.
2. Garder le cas « pas de billetterie → `None` » : c'est la newsletter qui décide de n'afficher aucune ligne tarif.
3. Supprimer `_formater_montant`.
4. Adapter `tests/pytest/test_newsletter_ghost.py` (l.286-338) aux nouveaux libellés.

## 2. SEO : `pages/templatetags/pages_tags.py:jsonld_event`

- Le commentaire dit que `published_prices` est une `@property`. C'est faux, c'est une méthode.
- Le code marche seulement parce que `EventMVT.retrieve` remplace la méthode par un queryset (`event.published_prices = Price.objects.filter(...)`).
- Il ne filtre ni les tarifs archivés ni les tarifs en points.

**Correctif proposé :** lire `tarifs_publies_de_l_evenement(event)` et garder seulement les tarifs en euros (`tarif_est_en_euros`).

## 3. Skin faire_festival : `pages/templates/pages/faire_festival/vues/adhesions.html:130`

Ce gabarit affiche le prix de chaque tarif, pas un minimum.
Un prix libre à 0 € y apparaît comme « Free ». Il faudrait tester `price.free_price` avant `price.prix > 0`.
