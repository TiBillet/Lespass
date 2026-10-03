# Page événement V2 : talon de billet pour les tarifs et la jauge / V2 event page: ticket stub for prices and capacity

**Date :** 2026-10-03
**Migration :** Non

## Resume / Summary

**Quoi / What :** Au-dessus du bouton « Réserver » de la page événement (skin V2), les deux
paragraphes gris (fourchette de prix, « X réservations validées sur Y places disponibles »)
sont remplacés par un talon de billet : le prix à gauche, les places restantes à droite, de part
et d'autre d'une perforation en pointillé. Les deux chiffres sont en Unbounded. Une pastille
zanana apparaît devant « Places restantes » quand il reste 15 % de la jauge ou moins.
Le prix libre et la gratuité s'affichent désormais (« Prix libre », « Gratuit »).
/ The two grey notes above the V2 booking button become a ticket stub: price on the left,
seats left on the right. Open price and free entry are now shown.

**Pourquoi / Why :** L'ancienne phrase de jauge donnait deux chiffres sans dire combien il
restait de places, et ne retirait pas les billets en cours de paiement. Le prix libre n'était
pas affiché du tout. Le comparatif `price_min is not price_max` testait l'identité de deux
Decimal au lieu de leur égalité.
/ The old gauge sentence did not say how many seats were left; open price was hidden;
`is not` compared Decimal identity instead of equality.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Event.places_restantes()` (même calcul que `complet()`, jamais négatif) et `Event.jauge_presque_pleine()` (≤ 15 % restant) |
| `pages/templates/pages/V2/partials/reservation_declencheur.html` | Talon `<dl class="talon">` au-dessus du bouton ; chaque case n'apparaît que si sa donnée existe |
| `pages/static/V2/css/V2.css` | Styles `.talon*` ; `.reservation-declencheur` prend la largeur de son bouton (sans largeur fixe, pour que le libellé tienne sur une ligne en desktop) et le talon s'y aligne ; `.reservation-declencheur__note` supprimée |
| `tests/pytest/test_event_places_restantes.py` | Tests sans base des deux nouvelles méthodes |

### Traductions / Translations
Nouvelles chaînes : « Vous choisissez », « Prix libre », « Le billet », « Gratuit », « Par billet »,
« Places restantes », « sur %(jauge)s ». À passer par `makemessages` puis le skill i18n-translate.
Les chaînes « Prices ranging between… », « Priced at… », « reservations validées sur »,
« places disponibles » ne sont plus utilisées par le skin V2 (le skin classic garde les siennes).

---

## Comment tester (a la main) / Manual test

### Test 1 — fourchette de prix + jauge
1. Un événement avec plusieurs tarifs (ex. 8 € et 15 €) et « Afficher la jauge » coché.
2. Ouvrir sa page détail (skin V2).
3. Attendu : talon « Par billet 8–15 € » | « Places restantes 37 sur 120 », bouton pleine largeur dessous.

### Test 2 — presque plein
1. Même événement, jauge à 20, 18 billets validés.
2. Attendu : pastille jaune devant « Places restantes », chiffre 2.

### Test 3 — prix libre, gratuit, sans jauge
1. Un tarif en prix libre → case « Vous choisissez / Prix libre ».
2. Un seul tarif à 0 € → « Le billet / Gratuit ».
3. « Afficher la jauge » décoché → une seule case, sans perforation.

### Test 4 — mobile
1. Largeur ≥ 420 px (tablette) : les deux cases restent côte à côte.
2. Largeur 375 px et 320 px : les cases s'empilent, la perforation devient horizontale.
