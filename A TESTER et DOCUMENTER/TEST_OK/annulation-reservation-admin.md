# Correction annulation reservation admin (hors-Stripe)

## Bug corrige

Quand un admin annulait une reservation creee manuellement (cheque, especes, virement),
aucune ligne comptable de remboursement/avoir n'etait creee.
La reservation passait en "annulee" sans trace comptable.

**Cause** : `cancel_and_refund_resa` ne cherchait les LigneArticle que via `Paiement_stripe` (FK).
Les reservations admin n'ont pas de `Paiement_stripe` → leurs LigneArticle etaient invisibles.

## Ce qui a ete fait

### Nouvelles methodes sur Reservation (`BaseBillet/models.py`)

- `_lignes_hors_stripe(pricesold_ids=None)` : retrouve les LigneArticle VALID/PAID sans `paiement_stripe`,
  liees a la reservation par les `pricesold` des tickets, avec `sale_origin=ADMIN`.
  Exclut les lignes qui ont deja un avoir.
- `_creer_avoir(ligne)` : cree un avoir (CREDIT_NOTE) pour une LigneArticle.

### Modifications des methodes existantes

- `cancel_and_refund_resa()` : apres le bloc Stripe (inchange), appelle `_lignes_hors_stripe()`
  et cree un avoir pour chaque ligne trouvee.
- `cancel_and_refund_ticket(ticket)` : idem, filtre sur le `pricesold` du ticket annule.

### Ce qui n'a PAS change

- Le flow Stripe (remboursement via API Stripe + ligne REFUNDED) est **strictement inchange**.
- Les appels front (mon compte → annuler reservation/ticket) continuent de fonctionner.
- La structure des LigneArticle Stripe (liees via `paiement_stripe` FK) n'est pas modifiee.

---

## Tests a realiser

### Test 1 : Annulation reservation admin complete

```
1. Admin → Evenements → choisir un evenement
2. Creer une reservation via le bouton admin (moyen de paiement : Especes ou Cheque)
3. Verifier dans Ventes : une LigneArticle VALID, sale_origin=ADMIN, paiement_stripe=null
4. Admin → Reservations → selectionner la reservation → action "Annuler"
5. Verifier :
   - Reservation en status CANCELED
   - Tous les tickets en CANCELED
   - Une nouvelle LigneArticle CREDIT_NOTE avec qty negative, credit_note_for = ligne originale
   - La ligne originale reste en VALID (inchangee)
```

### Test 2 : Annulation ticket individuel admin

```
1. Creer une reservation admin avec 2+ billets
2. Admin → Billets → selectionner UN seul ticket → action annuler
3. Verifier :
   - Le ticket est CANCELED
   - Un avoir CREDIT_NOTE est cree pour la ligne correspondante
   - Les autres tickets restent NOT_SCANNED
```

### Test 3 : Non-regression Stripe

```
1. Creer une reservation via le front (paiement Stripe avec carte test 4242...)
2. Annuler la reservation (admin ou front "mon compte")
3. Verifier :
   - Le remboursement Stripe est effectue (ligne REFUNDED, pas CREDIT_NOTE)
   - Le Paiement_stripe passe en REFUNDED
   - Pas d'avoir supplementaire cree
```

### Test 4 : Annulation reservation gratuite

```
1. Creer une reservation admin gratuite (moyen de paiement : Offert, amount=0)
2. Annuler la reservation
3. Verifier : pas d'avoir cree (amount=0, pas de ligne VALID avec montant)
```

### Test 5 : Double annulation

```
1. Creer et annuler une reservation admin
2. Verifier qu'on ne peut pas re-annuler (deja CANCELED)
```
