# Panier — Stocker le panier en base (Commande DRAFT) plutôt qu'en session

> **Status :** idée, **non commencée**. Exercice de pensée validé sur le principe.
> **Pré-requis :** aucun.
> **Date :** 2026-09-21 (session remboursements Stripe).

## 1. Contexte

Aujourd'hui, le panier vit dans la session Django :

```python
request.session['panier'] = {
    'items': [{'type': 'ticket', 'event_uuid': '…', 'price_uuid': '…', 'qty': 2}],
    'promo_code_name': None,
    'created_at': '…',
}
```

Au clic sur « Payer », `CommandeService.materialiser()` crée en base une `Commande`
(directement en `PENDING`), les `Reservation`, `Membership`, `Booking`,
`LigneArticle` et le `Paiement_stripe`. Puis la session est vidée (`panier.clear()`).

## 2. L'idée

Le panier devient une `Commande` au statut `DRAFT`, en base, tout le temps.

```
DRAFT (panier) ──clic Payer──► PENDING (attente Stripe) ──► PAID
       └── abandonné ──► EXPIRED
```

## 3. Ce qui existe déjà

- `Commande.DRAFT` existe, et c'est **le statut par défaut** du champ `status`.
  Il n'est utilisé nulle part aujourd'hui (`materialiser()` crée en `PENDING`).
- Le commentaire du champ `paiement_stripe` le prévoit : « une commande DRAFT
  pré-checkout n'a pas encore de paiement ».
- `Commande.EXPIRED` existe aussi.
- **Le panier exige déjà d'être connecté** pour écrire (`PanierMVT.get_permissions()` :
  `add`, `remove`, `checkout`, `promo`, `clear` → `IsAuthenticated`). Un panier non vide
  a donc toujours un utilisateur. Pas besoin de session pour le retrouver :

```python
panier = Commande.objects.filter(user=request.user, status=Commande.DRAFT).first()
```

## 4. Design recommandé

**Option A — une liste d'articles dans la commande (retenue)**

```python
items = models.JSONField(default=list)   # même format que la session aujourd'hui
```

- `PanierSession` garde son API, mais lit et écrit `commande.items` au lieu de
  `request.session['panier']`.
- `materialiser()` reprend la commande `DRAFT` (et la passe en `PENDING`) au lieu
  d'en créer une nouvelle.

**Option B — créer les vraies réservations dès l'ajout (écartée)**

Les billets `CREATED` / `NOT_ACTIV` de moins de 15 min sont comptés dans la jauge
(`Event.under_purchase()`). Un panier oublié bloquerait des places. Il faudrait aussi
gérer `max_per_user`, les lignes de vente et les signaux. Trop d'effets de bord.

## 5. Ce qu'on gagne

- Le panier suit l'utilisateur d'un appareil à l'autre et survit à la déconnexion.
- Paniers abandonnés visibles en base (statistiques, relances possibles).
- Une seule source de vérité : tout en base, rien en session.
- Tests plus simples : plus besoin de fabriquer une requête avec session
  (`tests/PIEGES.md`, piège 10.2).

## 6. Points de vigilance

- **Une seule commande DRAFT par utilisateur**, garantie en base :

```python
UniqueConstraint(fields=["user"], condition=Q(status="DRAFT"), name="un_seul_panier")
```

- **Paniers abandonnés** : une session expire seule, une ligne en base non.
  Décider : garder (une ligne par utilisateur, c'est peu), ou passer en `EXPIRED`
  via une tâche planifiée.
- **Revalidation au paiement** (prix changé, stock épuisé) : déjà faite par
  `panier.revalidate_all()` dans `materialiser()`.
- **Multi-tenant** : rien ne change. `Commande` est dans le schéma du lieu, comme le
  cookie de session est lié au domaine du lieu.
- **Deux onglets ouverts** : même problème qu'avec la session, pas pire.
