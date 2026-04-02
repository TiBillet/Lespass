# Avoir (credit note) sur les ventes

## Ce qui a ete fait

Les admins peuvent emettre un **avoir** (credit note) sur une ligne de vente depuis l'admin Django.
Un avoir est une annulation comptable : on cree une ligne miroir avec quantite negative, sans supprimer l'originale (conformite fiscale francaise).

### Modifications

| Fichier | Changement |
|---|---|
| `BaseBillet/models.py` | Nouveau status `CREDIT_NOTE = 'N'` + FK `credit_note_for` (self, nullable, PROTECT) |
| `BaseBillet/signals.py` | Handler `ligne_article_credit_note` + transition CREATED → CREDIT_NOTE |
| `Administration/admin_tenant.py` | Action row "Avoir" sur `LigneArticleAdmin`, `display_status` etendu |
| `Administration/importers/lignearticle_exporter.py` | Colonne "Credit note ref." dans l'export CSV |
| `BaseBillet/migrations/0199_credit_note_lignearticle.py` | Migration (1 FK nullable + 1 choice) |

### Comportement

- Bouton "Avoir" visible sur chaque ligne de vente dans la liste admin (Ventes)
- Gardes : uniquement sur lignes VALID ou PAID, et pas d'avoir si un avoir existe deja
- L'avoir cree une nouvelle LigneArticle avec `qty` negative, `sale_origin=ADMIN`, `status=CREDIT_NOTE`
- La ligne originale affiche un warning (⚠) si elle a un avoir
- L'avoir est envoye a LaBoutik via la meme task que les remboursements (`send_refund_to_laboutik`)
- L'export CSV inclut une colonne "Credit note ref." avec l'UUID de la ligne originale

### Difference avec le remboursement existant

| | Remboursement | Avoir |
|---|---|---|
| Retour d'argent | Oui (Stripe) | Non |
| Status | REFUNDED ('R') | CREDIT_NOTE ('N') |
| Declencheur | Annulation reservation | Action manuelle admin |

---

## Test Playwright a ecrire

**Fichier suggere :** `tests/playwright/tests/32-admin-credit-note.spec.ts`

### Scenario

```
1. Se connecter a l'admin
2. Aller sur la liste des ventes (LigneArticle changelist)
3. Trouver une ligne avec status "Confirmed" (VALID)
4. Cliquer sur le bouton "Avoir" (action row)
5. Verifier le message de succes "Credit note created."
6. Verifier qu'une nouvelle ligne apparait avec :
   - qty negative
   - status "Credit note"
   - meme produit que l'originale
7. Verifier que la ligne originale affiche le warning ⚠
8. Retourner sur la ligne originale et verifier que le bouton "Avoir" n'est plus cliquable
   (ou qu'un message d'erreur s'affiche si on retente)
9. Trouver une ligne avec status != VALID/PAID (ex: CREATED)
10. Verifier que le bouton "Avoir" renvoie une erreur
11. (Optionnel) Faire un export CSV et verifier la colonne "Credit note ref."
```

### Prerequis

- Au moins une LigneArticle en status VALID dans la base (creee par les tests precedents, ex: test 08 ou 09)
- `--workers=1` comme tous les tests Playwright du projet
