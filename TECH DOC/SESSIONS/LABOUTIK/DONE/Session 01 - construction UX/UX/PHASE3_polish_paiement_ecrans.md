# UX Phase 3 — Polish paiement et ecrans modaux

## Prompt

```
On travaille sur l'UX de l'interface POS LaBoutik.
Lis le plan UX : laboutik/doc/UX/PLAN_UX_LABOUTIK.md (section "Session 3" et captures d'ecran).
Cette session refond les ecrans modaux du flux de paiement pour les rendre FALC.

FALC = Facile A Lire et Comprendre. Les caissiers peuvent etre benevoles, non-formes,
en contexte bruyant (festival). Chaque ecran doit etre compris en 1 seconde.

Contexte technique :
- Stack : Django + HTMX + CSS custom, JS vanilla
- Skill /stack-ccc : commentaires FALC bilingues FR/EN
- Templates concernes : laboutik/templates/laboutik/partial/hx_*.html
- Composant bouton : laboutik/templates/cotton/bt/paiement.html
- Variables CSS : palette.css (--vert03=success, --bleu03, --bleu09, --warning00, etc.)

Tache 1 — Differencier les boutons de paiement :

1. Lis `laboutik/templates/cotton/bt/paiement.html` — actuellement tous les boutons
   utilisent la classe `.bt-basic-bg-success` (vert).
2. Ajoute un attribut `bg` au composant cotton pour passer une couleur custom.
3. Si `bg` est fourni, utiliser `style="background-color: var({{ bg }})"`.
   Sinon, garder la classe `.bt-basic-bg-success` par defaut.
4. Lis `laboutik/templates/laboutik/partial/hx_display_type_payment.html`.
5. Applique les couleurs suivantes :
   - CASHLESS : bg="--bleu03" (bleu vif)
   - ESPECE : bg="--vert03" (vert, inchange)
   - CB : bg="--bleu09" (bleu marine)
   - CHEQUE : bg="--gris05" (gris)
   - OFFRIR : bg="--warning00" (dore)

Tache 2 — Refonte ecran confirmation especes (FALC) :

1. Lis `laboutik/templates/laboutik/partial/hx_confirm_payment.html`.
2. Corrections :
   a. Supprimer la ligne `<div>uuid_transaction = {{ uuid_transaction }}</div>` (debug visible)
   b. Ajouter au-dessus du champ : le total a encaisser en gros
      `<div class="payment-title1">A encaisser : {{ total }} €</div>`
      avec {% translate %} et `tabular-nums`
   c. Agrandir le champ "somme donnee" :
      - font-size: 2rem, height: 80px, width: 200px, text-align: center
      - inputmode="decimal" (clavier numerique tactile)
      - autofocus
   d. Ajouter "€" en suffixe visuel apres le champ
   e. Harmoniser : "VALIDER" en majuscule (comme "RETOUR")
   f. Le label "somme donnee" → "Somme donnee" avec majuscule + icone fa-coins

Tache 3 — Refonte ecran succes (FALC) :

1. Lis `laboutik/templates/laboutik/partial/hx_return_payment_success.html`.
2. Corrections :
   a. "Transaction ok" → {% translate "Paiement reussi" %} (FALC)
   b. "Total(espece) 6,50 €" → {% translate "Paye en" %} {{ moyen_paiement }} : {{ total }} €
   c. Ajouter icone fa-check-circle en gros (font-size 4rem) au-dessus du texte
   d. Animation entree : @keyframes scale-in (0→1) sur l'icone, 300ms ease
   e. Si monnaie a rendre : section distincte avec fond rouge (--rouge07),
      texte gros (2.5rem), icone fa-hand-holding-usd
   f. Ajouter `tabular-nums` sur tous les montants

Tache 4 — Refonte ecran retour carte (FALC) :

1. Lis `laboutik/templates/laboutik/partial/hx_card_feedback.html`.
2. Corrections :
   a. Ajouter icone fa-id-card (font-size 3rem) en haut de page
   b. "Carte federee" → {% translate "Carte avec nom" %} (plus FALC)
   c. Formatage "0,0" → floatformat:2 sur total_monnaie (afficher "0,00 €")
   d. Soldes par asset : ajouter des icones distinctes
      - TLF : fa-euro-sign
      - TNF : fa-gift
      - TIM : fa-clock
   e. `tabular-nums` sur tous les montants
   f. Section adhesions : icone fa-id-badge + "Valide jusqu'au {{ deadline|date }}"

Tache 5 — Titre mode recharge FALC :

1. Lis `laboutik/templates/laboutik/partial/hx_display_type_payment.html`.
2. Le titre "Recharge : scannez la carte client" est correct mais peut etre
   plus FALC : "Posez la carte du client sur le lecteur" (action concrete).
3. Ajouter le montant dans le titre si possible.

Regles :
- Tous les textes dans {% translate %} — lancer makemessages + compilemessages apres
- Commentaires FALC bilingues FR/EN
- data-testid sur chaque section
- aria-live="polite" sur les zones dynamiques
- `tabular-nums` sur tous les montants
- Animations CSS `transition` (interruptibles) sauf animation d'entree (keyframe)
```

## Verification Chrome

### Test 1 : Boutons de paiement colores
1. Ajouter un article, cliquer VALIDER
   - **Attendu** : CASHLESS = bleu, ESPECE = vert, CB = bleu marine
   - **Attendu** : chaque bouton est visuellement distinct en 1 seconde
2. Les icones doivent etre visibles et contrastees sur le fond de chaque bouton

### Test 2 : Ecran confirmation especes
1. Ajouter 1 Biere + 1 Eau (6,50€), VALIDER, cliquer ESPECE
   - **Attendu** : PAS de "uuid_transaction =" visible
   - **Attendu** : "A encaisser : 6,50 €" en gros au-dessus du champ
   - **Attendu** : champ de saisie large, avec "€" visible
   - **Attendu** : le curseur est deja dans le champ (autofocus)
2. Saisir "10" → cliquer VALIDER
   - **Attendu** : monnaie a rendre visible sur l'ecran succes

### Test 3 : Ecran succes FALC
1. Apres paiement especes :
   - **Attendu** : icone check verte animee (scale-in)
   - **Attendu** : "Paiement reussi" (pas "Transaction ok")
   - **Attendu** : "Paye en espece : 6,50 €" (pas "Total(espece)")
2. Si monnaie a rendre (somme donnee > total) :
   - **Attendu** : section rouge bien visible "Monnaie a rendre : 3,50 €"

### Test 4 : Ecran retour carte
1. CHECK CARTE → scanner carte client 1
   - **Attendu** : icone carte en haut
   - **Attendu** : "Carte anonyme" avec pictogramme
   - **Attendu** : soldes avec icones par type (euro, cadeau, temps)
   - **Attendu** : montants formates en "X,XX" (pas "X,X")

### Test 5 : Mode recharge
1. Ajouter "Recharge EUR Test", VALIDER
   - **Attendu** : titre FALC (pas d'anglicisme)
   - **Attendu** : pas de bouton CASHLESS

### Test i18n
1. Verifier les textes en FR (changer la locale si necessaire)
2. Les nouveaux textes {% translate %} doivent etre traduits

## Fichiers concernes

- `laboutik/templates/cotton/bt/paiement.html` — attribut bg
- `laboutik/templates/laboutik/partial/hx_display_type_payment.html` — couleurs boutons
- `laboutik/templates/laboutik/partial/hx_confirm_payment.html` — refonte confirmation
- `laboutik/templates/laboutik/partial/hx_return_payment_success.html` — refonte succes
- `laboutik/templates/laboutik/partial/hx_card_feedback.html` — refonte retour carte
- `locale/fr/LC_MESSAGES/django.po` + `locale/en/LC_MESSAGES/django.po` — traductions
