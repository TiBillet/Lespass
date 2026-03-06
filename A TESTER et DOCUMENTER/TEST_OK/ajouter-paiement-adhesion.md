# Ajouter un paiement sur une adhesion en attente

## Ce qui a ete fait

Les admins peuvent enregistrer un paiement hors-ligne (especes, cheque, virement) sur une adhesion en attente directement depuis l'admin Django.

### Modifications

| Fichier | Changement |
|---|---|
| `Administration/admin_tenant.py` | Action `MembershipAdmin.ajouter_paiement()` — formulaire GET/POST |
| `Administration/templates/admin/membership/ajouter_paiement.html` | Template du formulaire (montant + moyen de paiement) |

### Comportement

- Bouton "Ajouter un paiement" sur la page detail d'une adhesion en status WAITING_PAYMENT ou ADMIN_WAITING
- Formulaire : montant (pre-rempli avec le prix du produit) + moyen de paiement (especes, cheque, virement, offert)
- Validation : montant positif, moyen de paiement valide, "Offert" interdit avec montant > 0
- Apres validation, declenche toute la chaine :
  1. Mise a jour de la membership (contribution_value, payment_method, dates, status ONCE)
  2. Creation d'une LigneArticle en CREATED puis passage en PAID
  3. Le signal pre_save declenche trigger_A : deadline, email confirmation, transaction Fedow, envoi LaBoutik, passage VALID

### Gardes

- Uniquement sur adhesions en attente de paiement (WP ou AW)
- Validation cote serveur du montant et du moyen de paiement

---

## Test Playwright a ecrire

**Fichier suggere :** `tests/playwright/tests/33-admin-ajouter-paiement.spec.ts`

### Scenario

```
1. Se connecter a l'admin
2. Creer une adhesion en attente de paiement (ou en trouver une existante)
3. Aller sur la page detail de cette adhesion
4. Cliquer sur "Ajouter un paiement"
5. Verifier que le formulaire s'affiche avec le montant pre-rempli
6. Remplir le montant et choisir "Especes"
7. Soumettre le formulaire
8. Verifier le message de succes
9. Verifier que l'adhesion est passee en status ONCE ou VALID
10. Verifier qu'une LigneArticle a ete creee avec le bon montant
11. Tester les gardes :
    - Montant negatif → erreur
    - Montant vide → erreur
    - "Offert" avec montant > 0 → erreur
    - Adhesion deja payee → erreur (bouton absent ou message)
```

### Prerequis

- Un produit adhesion avec un prix configure
- Un utilisateur avec une adhesion en attente de paiement
- `--workers=1`
