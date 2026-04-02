# Phase 3 — Polish paiement et ecrans modaux (FALC)

## Ce qui a ete fait

Refonte FALC des 5 ecrans de paiement de la caisse POS.
Objectif : un benevole en festival comprend chaque ecran en 1 seconde.
Uniquement du HTML/CSS dans les templates Django — 0 changement Python, 0 changement JS.

### Modifications
| Fichier | Changement |
|---|---|
| `laboutik/templates/cotton/bt/paiement.html` | Variable Cotton `bg` pour couleur de fond personnalisable, `aria-hidden` sur icone decorative |
| `laboutik/templates/laboutik/partial/hx_display_type_payment.html` | Couleurs par moyen de paiement (CASHLESS bleu vif, CB bleu marine, CHEQUE gris, OFFRIR dore texte noir), titre recharge FALC + total affiche, `data-testid` sur tous les boutons |
| `laboutik/templates/laboutik/partial/hx_confirm_payment.html` | Total "A encaisser" en grand (2.5rem), champ saisie 80px avec devise, `inputmode="decimal"`, `autofocus`, `aria-label`, `role="alert"` sur erreur, media query mobile empile boutons, commentaires FALC bilingues |
| `laboutik/templates/laboutik/partial/hx_return_payment_success.html` | Icone check animee (scale-in 300ms), "Paiement reussi" remplace "Transaction ok", "Paye en" au lieu de "Total(moyen)", monnaie a rendre en box rouge/dore avec icone |
| `laboutik/templates/laboutik/partial/hx_card_feedback.html` | Icone carte fa-id-card, "Carte avec nom" remplace "Carte federee", icones par type d'asset (TLF=euro, TNF=gift, TIM=clock), `data-testid` par section |
| `locale/fr/LC_MESSAGES/django.po` | Traductions FR, correction fuzzy "Paiement reussi" (etait "Envoye a Stripe") |
| `locale/en/LC_MESSAGES/django.po` | Traductions EN completes |

## Tests a realiser

### Test 1 : Boutons de paiement colores (mode normal)
1. Ouvrir la caisse POS, ajouter des articles au panier
2. Cliquer VALIDER
3. Verifier les couleurs des boutons :
   - CASHLESS = bleu vif (`--bleu03` #0345ea)
   - ESPECE = vert (defaut `--success` #339448)
   - CB = bleu marine (`--bleu05` #012584)
   - CHEQUE = gris (`--gris02` #4d545a)
4. Passer en mode gerant (icone engrenage)
5. Verifier OFFRIR = dore (`--warning00` #f5972b) avec texte noir
6. Verifier que le texte blanc est bien lisible sur tous les autres boutons

### Test 2 : Ecran confirmation especes
1. Ajouter articles au panier, cliquer VALIDER, cliquer ESPECE
2. Verifier le titre "Confirmez le paiement par espece"
3. Verifier que le total est affiche en grand : "A encaisser : X.XX €"
4. Verifier l'icone fa-coins + label "Somme donnee"
5. Verifier que le champ de saisie est large (200px), centre, avec "€" a droite
6. Verifier que le curseur est dans le champ (autofocus)
7. Saisir une somme inferieure au total → message d'erreur rouge
8. Saisir une somme superieure ou egale → cliquer VALIDER → succes

### Test 3 : Ecran succes (paiement CB)
1. Ajouter articles, VALIDER, cliquer CB
2. Verifier l'icone check animee (scale-in)
3. Verifier "Paiement reussi" (pas "Transaction ok")
4. Verifier "Paye en carte bancaire : X.XX €"

### Test 4 : Ecran succes (paiement especes avec monnaie a rendre)
1. Ajouter un article a 5€, VALIDER, ESPECE
2. Saisir 10 dans "Somme donnee", VALIDER
3. Verifier "Somme donnee : 10.00 €" en discret (petite taille, opacite 0.85)
4. Verifier "Monnaie a rendre : 5.00 €" en grand, fond rouge (`--rouge07`), bordure doree (`--warning00`)
5. Verifier l'icone fa-hand-holding-usd

### Test 5 : Ecran retour carte
1. Cliquer CHECK CARTE, scanner une carte anonyme
2. Verifier : icone fa-id-card + "Carte anonyme" + icone fa-user-secret
3. Scanner une carte avec email
4. Verifier : icone fa-id-card + "Carte avec nom" + email affiche en dessous
5. Verifier les icones par type d'asset dans les soldes :
   - TLF → fa-euro-sign
   - TNF → fa-gift
   - TIM → fa-clock
   - Autre → fa-coins
6. Verifier la section adhesions avec icone fa-id-badge

### Test 6 : Titre recharge
1. Ajouter une recharge au panier, cliquer VALIDER
2. Verifier le titre "Posez la carte du client sur le lecteur"
3. Verifier que le montant total est affiche sous le titre en gros (2rem)

### Test 7 : Mobile (375x667)
1. Ouvrir Chrome DevTools, simuler 375x667 (iPhone SE)
2. Ecran confirmation especes : boutons RETOUR/VALIDER empiles verticalement
3. Tous les ecrans : pas de debordement horizontal
4. Champ de saisie especes : max-width 60% evite le debordement

### Test 8 : Traductions EN
1. Basculer en anglais
2. Verifier : "To collect", "Amount given", "CONFIRM", "Payment successful", "Paid by", "Change to give back"
3. Verifier : "Anonymous card", "Named card", "Active memberships", "No balance"
4. Verifier : "Place the customer card on the reader"

### Test 9 : Accessibilite
1. Verifier que toutes les icones decoratives ont `aria-hidden="true"`
2. Verifier que le champ de saisie a un `aria-label`
3. Verifier que les zones dynamiques ont `aria-live="polite"`
4. Verifier que le message d'erreur a `role="alert"`

## Verification en base
```bash
# Pas de verification en base necessaire — changements purement frontend (templates + CSS)
```

## Compatibilite
- Aucun changement Python ou JS — pas de risque de regression backend
- Les `data-testid` sont nouveaux — les tests E2E existants qui utilisent les anciens selecteurs CSS (.test-return-*) continuent de fonctionner
- Les traductions existantes sont preservees, seules les nouvelles chaines sont ajoutees
- La correction du fuzzy "Paiement reussi" (qui etait "Envoye a Stripe") est un bugfix i18n
