# Triggers Fedow dans les inlines de tarif (adhésion + billet)

## Ce qui a été fait

Les deux déclencheurs Fedow sont à nouveau réglables depuis l'admin produit, mais
cette fois **dans l'inline de tarif du bon proxy** (plus dans une vue séparée).

- **Adhésion** (`MembershipPriceInline`) : `fedow_reward_enabled` recharge le wallet
  du membre à l'achat de l'adhésion.
- **Billet** (`TicketPriceInline`) : `reward_on_ticket_scanned` récompense le wallet
  de l'acheteur au scan du billet.

`fedow_reward_asset` (le jeton) et `fedow_reward_amount` (le montant) ne s'affichent
que si le toggle correspondant est coché (JS `inline_conditional_fields.js`).

### Modifications

| Fichier | Changement |
|---|---|
| `Administration/admin/products.py` | Filtrage du queryset `fedow_reward_asset` sur `BasePriceInline` ; champs + règles conditionnelles sur `MembershipPriceInline` et `TicketPriceInline` ; câblage conditionnel remonté dans la base `ProductAdmin` |

Aucune migration (les champs `Price` existaient déjà).

## Tests à réaliser

Se connecter à l'admin d'un tenant en tant qu'admin (`admin@admin.com` ou
`jturbeaux@pm.me` selon le tenant), avec un Fedow configuré (`FedowConfig.can_fedow()`).

### Test 1 : Adhésion — recharge à l'achat
1. Admin → Adhésions → Membership products → ouvrir (ou créer) un produit adhésion.
2. Dans un tarif inline : **`fedow_reward_enabled` décoché** → vérifier que
   « Fedow Asset » et « Token amount to send » sont **masqués**.
3. Cocher `fedow_reward_enabled` → les deux champs **apparaissent** (animation douce,
   bordure gauche colorée).
4. Le dropdown « Fedow Asset » ne propose que les assets **locaux / temps / fidélité
   du lieu courant** (pas d'asset d'un autre tenant, pas d'asset archivé).
   Vérifier qu'il **n'y a pas** de boutons « + » (ajouter), crayon (modifier) ni
   corbeille (supprimer) à côté du dropdown : on ne gère pas les assets depuis ici.
5. Choisir un asset, saisir un montant, enregistrer → pas d'erreur, retour sur le
   produit. Rouvrir → valeurs persistées, champs toujours visibles.
6. Décocher `fedow_reward_enabled`, enregistrer → champs re-masqués.

### Test 2 : Billet — récompense au scan
1. Admin → Billetterie → Ticket products → ouvrir (ou créer) un produit billet.
2. Tarif inline : `reward_on_ticket_scanned` **décoché** → asset + montant masqués.
3. Cocher → asset + montant apparaissent. Même filtrage du dropdown asset.
4. Vérifier que le champ **« recharge à l'achat » (`fedow_reward_enabled`) n'apparaît
   PAS** sur un billet (et inversement, le « scan » n'apparaît pas sur une adhésion).

### Test 3 : Cohérence multi-lignes
1. Sur un produit adhésion avec **plusieurs tarifs**, activer le trigger sur un seul
   tarif → seul ce tarif affiche asset + montant ; les autres restent masqués.
2. Ajouter un nouveau tarif (bouton « + ») → le JS s'applique aussi à la ligne neuve
   (MutationObserver).

### Vérification en base (optionnel)
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import Price
with tenant_context(Client.objects.get(schema_name='lespass')):
    for p in Price.objects.filter(fedow_reward_enabled=True):
        print(p, p.fedow_reward_asset, p.fedow_reward_amount)
"
```

## Compatibilité

- L'ancienne vue `PriceAdmin` (onglet « Triggers ») reste enregistrée et fonctionnelle
  (autocomplete + cible de redirection), mais n'est plus le chemin nominal.
- Le comportement runtime des triggers est inchangé (mêmes champs consommés par
  `tasks.py` / `signals.py`). Seule l'interface de saisie a bougé.
