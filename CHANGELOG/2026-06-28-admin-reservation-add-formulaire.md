# Admin — Formulaire d'ajout de réservation (refonte)

**Date :** 2026-06-28
**Migration :** Non

Regroupe les corrections de la session sur `/admin/BaseBillet/reservation/add/`
(`ReservationAddAdmin`).

## Ce qui a été fait

### 1. Champ email → input texte (fix crash Sentry 7574740199)
Le champ `email` était devenu un `ModelChoiceField` (Select2 d'utilisateurs)
sans adapter `save()` → `AttributeError: 'TibilletUser' object has no attribute
'lower'`. Retour à un `forms.EmailField`. `save()` →
`get_or_create_user(email, send_mail=False)` (pas de mail de validation, user
rattaché au tenant).

### 2. Choix du tarif : une option par couple (évènement, tarif)
Le champ listait les `PriceSold` (qui n'existent qu'après une 1re vente) → un
seul tarif visible. Puis les `Price` → mais un tarif gratuit (« Réservation
gratuite ») est un **Product partagé entre plusieurs évènements**, donc une seule
option pour N évènements et réservation sur le mauvais.

Désormais : `forms.ChoiceField` dont les choix sont **une option par couple
(évènement, tarif)**, valeur `event_uuid:price_uuid`, libellé cherchable
« date — évènement — tarif — prix ». L'évènement est explicite. `save()`
matérialise `ProductSold`/`PriceSold` au besoin.

### 3. Email visible dans la liste des ventes
`LigneArticle.user_email()` ne gérait que `membership`/`paiement_stripe` → colonne
email vide pour les ventes admin. Ajout du cas `reservation.user_commande`.

### 4. Champ « Prix par billet » + auto-remplissage
Nouveau champ `amount` (montant unitaire **par billet**) :
- se **pré-remplit** à la sélection du tarif (JS), avec le prix du tarif ;
- **obligatoire** pour un tarif à **prix libre** (`free_price`) ;
- un libellé « prix € × quantité = total € » rappelle que c'est par billet.

`save()` stocke `LigneArticle.amount = prix_unitaire × 100` (montant **UNITAIRE**
en centimes ; le total est `amount × qty`, cf. `comptabilite/services.py`).
**⚠️ Bug pré-existant corrigé** : l'ancien `save()` mettait `prix × quantité × 100`,
soit un total compté `× qty` en trop (ex. 8 € × 3 → 72 € au lieu de 24 €). Les
`LigneArticle` ADMIN payantes `qty > 1` créées avant ce correctif sont à vérifier.

### Modifications
| Fichier | Changement |
|---|---|
| `Administration/admin_tenant.py` | `_build_event_price_options()` ; champ `email` (EmailField) ; champ `price` (ChoiceField couple event:price) ; champ `amount` (prix par billet) ; `payment_method` requis + option vide ; `__init__` (choix + data JS) ; `clean()` (requis si prix libre) ; `_extraire_evenement_et_tarif` ; `save()` + `clean_payment_method` adaptés ; `class Media` ; `get_or_create_user(send_mail=False)` |
| `Administration/static/admin/js/reservation_price_autofill.js` | Nouveau — auto-remplissage + requis prix libre + libellé total |
| `BaseBillet/models.py` | `LigneArticle.user_email()` gère `reservation.user_commande` |
| `tests/pytest/test_admin_reservation_add.py` | Nouveau fichier, 7 tests |

## Tests automatisés

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_admin_reservation_add.py -v
```
- gratuit (FREERES + Offert, qty 2) : VALID, user créé+rattaché, 2 billets, ligne 0, `user_email()` OK ;
- payant (BILLET 12€, qty 3) : `amount=1200` (unitaire), `total()=3600` ;
- **tarif partagé entre 2 events** → 2 options distinctes + réservation sur le bon event ;
- **prix par billet override** (tarif 12€, saisi 8€, qty 2) : `amount=800`, `total()=1600` ;
- **prix libre** : montant requis (invalide sans), puis 15€ qty 2 : `amount=1500`, `total()=3000` ;
- **moyen de paiement requis** : sans choix → form invalide ; 1re option du select = vide ;
- garde-fous : `email` = EmailField, `price` = ChoiceField (pas ModelChoiceField).

> Note : l'**auto-remplissage JS** (Partie B) n'est pas couvert par pytest
> (comportement navigateur). Voir le test manuel 4 ci-dessous.

## Tests manuels

### Test 1 : tous les events/tarifs futurs sont proposés
1. Avoir plusieurs events à venir, dont des **gratuits** partageant « Réservation gratuite ».
2. Admin → **Billetterie → Réservations → Ajouter**.
3. Champ **Tarif** : chaque évènement (même gratuit, même jamais vendu) a son
   entrée « date — évènement — tarif — prix ». La recherche dans le select fonctionne.

### Test 2 : réservation sur le bon évènement (tarif partagé)
1. Choisir le tarif gratuit d'un évènement **précis** (pas le premier de la liste).
2. Enregistrer.
3. Vérifier que la réservation est bien rattachée à **cet** évènement.

### Test 3 : création + email visible
1. Saisir un email, choisir un tarif, quantité 3, enregistrer.
2. Réservation VALID, 3 billets, pas de crash, aucun mail de validation envoyé.
3. `/admin/BaseBillet/lignearticle/` : la colonne email affiche l'acheteur.

### Test 4 : auto-remplissage du « Prix par billet » (JS, navigateur)
Vérification manuelle — non couverte par pytest.
1. Ouvrir `/admin/BaseBillet/reservation/add/`.
2. Sélectionner un **tarif payant** (ex. 12€) → le champ **Prix par billet** se
   pré-remplit avec `12.00` ; le champ n'est pas obligatoire.
3. Changer la **quantité** à 3 → le libellé affiche « 12.00 € × 3 = 36.00 € au total ».
4. Sélectionner un **tarif à prix libre** → le champ se **vide** et devient
   **obligatoire** (astérisque / validation HTML5 au submit si vide).
5. Saisir un montant, enregistrer → `LigneArticle.amount = montant × quantité × 100`.

> Si l'auto-remplissage ne se déclenche pas : vérifier que le statique
> `admin/js/reservation_price_autofill.js` est bien servi (en dev, `staticfiles`
> le sert automatiquement avec `DEBUG=True` ; sinon `collectstatic`).

## Points d'attention
- Recherche **client-side** (Select2) : toutes les options sont dans le DOM.
  Suffisant pour l'admin ; si un tenant a des milliers de tarifs futurs, envisager
  un autocomplete serveur.
- Les choix sont reconstruits à chaque affichage du formulaire (une requête
  `Event.objects...prefetch_related('products__prices')`).
