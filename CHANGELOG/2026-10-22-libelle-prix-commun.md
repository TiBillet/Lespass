# Libellé de prix commun : événements, adhésions, ressources / Shared price label: events, memberships, resources

**Date :** 2026-10-22
**Migration :** Non

## Resume / Summary
**Quoi / What :** un seul module, `BaseBillet/services_libelle_prix.py`, fabrique le texte de prix des cartes et fiches. Les cinq calculs dispersés ont été retirés. Règles :
- 1 seul montant → « 12 € »
- plusieurs montants → « De 10 à 25 € »
- au moins un prix libre → « Prix libre dès X € », ou « Prix libre » si X vaut 0
- aucun tarif, ou tous à 0 € → « Entrée libre » (événement) ou « Gratuit » (adhésion, ressource)
- uniquement des tarifs en points ou en temps → rien n'est affiché

Les montants n'ont plus de centimes inutiles, et le séparateur décimal suit la langue. L'attribut lu par les gabarits devient `libelle_prix`.
/ A single module builds the price text on cards and detail pages, with the rules above. Templates read `libelle_prix`.

**Pourquoi / Why :** il y avait cinq façons de calculer le prix minimum, avec des résultats incohérents :
- « À partir de 0.00 € » pour un prix libre ;
- une branche « Prix libre » qui ne s'exécutait jamais ;
- une comparaison `is` dans le gabarit classic ;
- un « A partir de » codé en dur.

/ Five inconsistent min-price computations, several visible bugs.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/services_libelle_prix.py` | Nouveau : `libelle_prix()`, `tarifs_publies_de_l_evenement()`, `formater_montant()` |
| `BaseBillet/views.py` | Suppression de `_libelle_prix_agenda` et `_calculer_prix_min_max_event`. L'agenda, la fiche, les événements fédérés et les adhésions posent `libelle_prix`. Préfixe de cache de l'agenda passé à `event_list_v2_`. Suppression du bloc commenté des ressources |
| `booking/views.py` | `BookingViewSet.list` pose `resource.libelle_prix` |
| `pages/templatetags/pages_tags.py` | Commentaires : `price_min` → `libelle_prix` |
| `pages/templates/cotton/V2/event_card.html`, `membership_card.html`, `ressource_card.html` | Affichent `libelle_prix`, ajout de `data-testid`, retrait de « A partir de » |
| `pages/templates/pages/classic/partials/reservation_declencheur.html` | Le bloc min/max est remplacé par `libelle_prix` (`data-testid="booking-libelle-prix"`) |
| `tests/pytest/test_libelle_prix.py` | Nouveau : 13 tests, un par règle |
| `tests/pytest/test_bloc_agenda_prix_federes.py` | Utilise l'attribut `libelle_prix` |
| `CHANGELOG/a traiter/libelle-prix-unification-restante.md` | Newsletter, JSON-LD et faire_festival restent à brancher |

**i18n :** nouvelles chaînes à traduire :
- « Prix libre dès %(montant)s € »
- « De %(minimum)s à %(maximum)s € »
- « %(montant)s € »
- « Gratuit »
- « Entrée libre »

Les chaînes « Prices ranging between… » et « Priced at… » ne sont plus utilisées.

---

## Comment tester (a la main) / Manual test

### Test 1 — Événement (agenda V2 et fiche classic)
Créer un événement de billetterie, puis vérifier sa carte dans l'agenda et sa fiche pour chaque cas :
1. un tarif à 15 € → « 15 € » ;
2. deux tarifs, 10 € et 25 € → « De 10 à 25 € » ;
3. un tarif à 12,50 € → « 12,50 € » (en anglais : « 12.50 € ») ;
4. ajouter un tarif à prix libre avec un minimum de 5 € → « Prix libre dès 5 € » ;
5. mettre ce minimum à 0 → « Prix libre » ;
6. réservation gratuite à 0 €, ou aucun tarif → « Entrée libre ».

L'agenda est en cache : enregistrer l'événement invalide la clé.

### Test 2 — Adhésions (/memberships/, skin V2)
1. Une adhésion à 20 € → « 20 € », sans « A partir de ».
2. Deux tarifs, 10 € et 30 € → « De 10 à 30 € ».
3. Une adhésion à 0 € → « Gratuit ».
4. Une adhésion vendue en points seulement → aucun prix sur la carte.

### Test 3 — Ressources (/booking/)
Mêmes cas que pour les adhésions. Une ressource à 0 € affiche « Gratuit ».

### Test 4 — Événement fédéré
Afficher l'agenda d'un lieu qui fédère un autre lieu. Le prix de l'événement fédéré correspond à ses propres tarifs, et non à « Entrée libre ».

### Verifs automatiques
- `poetry run pytest -q tests/pytest/test_libelle_prix.py tests/pytest/test_bloc_agenda_prix_federes.py`
