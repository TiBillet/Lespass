# Concepts métier TiBillet — base du glossaire

Liste de référence des termes métier. Elle sert à **générer un glossaire figé
par langue cible** (`<code>.txt`), injecté à l'identique dans tous les lots du
workflow pour garantir la cohérence des traductions entre agents indépendants.

**Avant de figer un glossaire**, enrichis cette base avec le vocabulaire réel du
projet (voir SKILL.md, étape « Glossaire ») :
- `mcp__atomic__semantic_search` : requêtes type `"glossaire vocabulaire TiBillet"`,
  `"définition cashless monnaie locale temps"`, `"terme métier billetterie adhésion"`.
- skill `/djc` : conventions et vocabulaire du projet (FALC, modules, termes UI).

## Concepts (FR ↔ EN) à traduire de façon cohérente vers la langue cible

| FR | EN | Note |
|---|---|---|
| billetterie | ticketing | module |
| événement | event | |
| réservation | booking | pas « reservation » dans l'UI EN |
| tarif | price | `Price` côté modèle |
| adhésion | membership | |
| adhérent·e | member | |
| caisse / caisse enregistreuse | cash register / POS | module LaBoutik |
| point de vente | point of sale | |
| cashless | cashless | garder tel quel |
| carte NFC | NFC card | |
| monnaie locale | local currency | |
| monnaie temps | time currency | |
| monnaie cadeau | gift currency | |
| portefeuille | wallet | |
| recharge | top-up | recharger = to top up |
| avoir | credit note | comptabilité |
| clôture (de caisse) | cash-up / closing | |
| lieu | venue | pas « place » |
| fédération | federation | |
| bénévole | volunteer | |
| budget contributif | contributory budget | module crowds |
| financement participatif | crowdfunding | |
| reçu | receipt | |
| scan / scanner | scan | entrée événement |

## Noms propres — NE JAMAIS traduire
TiBillet, LaBoutik, Fedow, Lespass, Code Commun, Cascade, Stripe, SEPA, NFC,
QR code, FEC, LNE.
