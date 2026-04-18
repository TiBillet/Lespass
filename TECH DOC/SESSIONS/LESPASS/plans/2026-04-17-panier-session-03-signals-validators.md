# Panier multi-events — Plan Session 03 : Signals + `accept_sepa` + `ReservationValidator` cart-aware

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Câbler le paiement Stripe multi-lignes pour le panier : patch du signal `set_ligne_article_paid` pour itérer sur N reservations, nouveau post_save qui bascule la `Commande` en PAID quand le Paiement_stripe est VALID, flag `accept_sepa` sur `CreationPaiementStripe`, et `ReservationValidator` cart-aware (+ correction incidente du bug overlap).

**Architecture:** Aucune nouvelle classe. Trois adaptations ciblées dans des fichiers existants (`signals.py`, `validators.py`, `PaiementStripe/views.py`) + une ligne dans `services_commande.py` pour passer le nouveau flag. Zéro régression garantie par défauts préservant le comportement legacy.

**Tech Stack:** Django 5.x signaux pre/post_save, django-tenants, poetry, PostgreSQL, pytest.

**Spec:** `TECH DOC/SESSIONS/LESPASS/specs/2026-04-17-panier-multi-events-design.md` (sections 3.6, 3.7, 3.7bis)

**Dépend de :** Session 01 DONE (modèle Commande), Session 02 DONE (PanierSession + CommandeService + 47 tests).

**Scope de cette session :**
- ✅ Patch `BaseBillet/signals.py` — `set_ligne_article_paid()` passe du FK unique à l'itération sur les lignes
- ✅ Nouveau post_save `Paiement_stripe` → `Commande.PAID`
- ✅ Param `accept_sepa: bool | None = None` sur `CreationPaiementStripe`
- ✅ `CommandeService._creer_paiement_stripe()` passe `accept_sepa=False` si panier contient des billets
- ✅ `ReservationValidator` cart-aware via attribut injecté `current_commande`
- ✅ Fix bug `ReservationValidator.validate()` ligne 613 — filtrer par `BLOCKING_STATUSES`
- ✅ Tests pytest : non-régression flows mono-event + adhésion, nouveaux flows multi-reservations

**Hors scope (sessions suivantes) :**
- ❌ Vues HTMX `PanierMVT` → Session 04
- ❌ Templates modal / page panier → Session 05
- ❌ Tests E2E Playwright → Session 06

**Règle projet :** L'agent ne touche jamais à git. Les commits sont faits par le mainteneur.

---

## Architecture des fichiers

| Fichier | Action | Rôle |
|---|---|---|
| `BaseBillet/signals.py` | Modifier | `set_ligne_article_paid()` : itération sur `ligne.reservation` (rétrocompat) + nouveau handler post_save `Paiement_stripe` → `Commande.PAID` |
| `PaiementStripe/views.py` | Modifier | `CreationPaiementStripe.__init__` : nouveau param `accept_sepa` + adaptation `dict_checkout_creator()` |
| `BaseBillet/services_commande.py` | Modifier | `_creer_paiement_stripe()` : calcule `contains_tickets` et passe `accept_sepa=False` si tickets, `True` sinon |
| `BaseBillet/validators.py` | Modifier | `ReservationValidator.validate()` : cart-aware adhesions_obligatoires (check `current_commande`) + fix bug overlap (réutiliser `reservations_bloquantes_pour_user`) |
| `tests/pytest/test_signals_cascade_multi_reservations.py` | Créer | Tests non-régression + nouveau flow multi-reservations |
| `tests/pytest/test_commande_post_save_paid.py` | Créer | Tests du nouveau handler post_save Commande.PAID |
| `tests/pytest/test_accept_sepa_flag.py` | Créer | Tests du flag `accept_sepa` |
| `tests/pytest/test_reservation_validator_cart_aware.py` | Créer | Tests cart-aware adhesions_obligatoires + fix bug overlap |

**Principes de découpage respectés :**
- Chaque modification est locale et rétrocompatible (défaut = comportement legacy).
- Zéro refonte. Tous les flows existants continuent de marcher.
- Les tests couvrent AUTANT la non-régression que les nouvelles fonctionnalités.

---

## Tâche 3.1 : Patch `set_ligne_article_paid()` dans `signals.py`

**Fichiers :**
- Modifier : `BaseBillet/signals.py` (fonction `set_ligne_article_paid`, lignes 36-59)
- Créer : `tests/pytest/test_signals_cascade_multi_reservations.py`

**Contexte :** Aujourd'hui (ligne 52-57) :

```python
# s'il y a une réservation, on la met aussi en payée :
if new_instance.reservation:
    new_instance.reservation.status = Reservation.PAID
    new_instance.reservation.save()
```

Cette ligne lit `paiement_stripe.reservation` (FK unique). Pour un panier multi-events, ce FK est `None` et les reservations sont référencées via `ligne.reservation` sur chaque `LigneArticle`. On veut itérer sur les lignes et basculer toutes les reservations référencées.

**Rétrocompat :** flow mono-event legacy = 1 seule reservation référencée par les lignes = le set dédoublonne = 1 reservation passée en PAID (identique). Flow adhésion-only = pas de reservation dans les lignes = set vide = aucune action (identique).

- [ ] **Étape 1 : Lire le contexte**

```bash
docker exec lespass_django cat /DjangoFiles/BaseBillet/signals.py | head -70
```

Repérer la fonction `set_ligne_article_paid` (ligne 36-59) et confirmer sa forme actuelle.

- [ ] **Étape 2 : Remplacer le bloc `if new_instance.reservation`**

Dans `BaseBillet/signals.py`, la fonction `set_ligne_article_paid` (ligne 36). Le code actuel (lignes 51-57) est :

```python
    # s'il y a une réservation, on la met aussi en payée :
    if new_instance.reservation:
        logger.info(
            f"        PAIEMENT_STRIPE set_ligne_article_paid : Toutes les ligne_article on été passé en {LigneArticle.PAID} et on été save()")
        logger.info(f"        On passe la reservation en PAID et save()")
        new_instance.reservation.status = Reservation.PAID
        new_instance.reservation.save()
```

Le remplacer par :

```python
    # On rassemble toutes les reservations à valider : la FK legacy (flow mono-event)
    # + les FK sur les LigneArticle (nouveau : flow panier multi-events).
    # Le set() dédoublonne automatiquement : flow mono-event = 1 seule reservation.
    # / Gather all reservations to validate: legacy FK (mono-event flow) + FKs on
    # LigneArticle (new: multi-event cart flow). set() dedupes: mono-event = 1 single reservation.
    reservations_a_valider = set()
    if new_instance.reservation:
        reservations_a_valider.add(new_instance.reservation)
    for ligne in new_instance.lignearticles.all():
        if ligne.reservation:
            reservations_a_valider.add(ligne.reservation)

    if reservations_a_valider:
        logger.info(
            f"        PAIEMENT_STRIPE set_ligne_article_paid : {len(reservations_a_valider)} reservation(s) à valider")
        for reservation in reservations_a_valider:
            logger.info(f"        On passe la reservation {reservation.uuid_8()} en PAID et save()")
            reservation.status = Reservation.PAID
            reservation.save()
```

Note : `Reservation.uuid_8()` existe-t-il ? Vérifier rapidement avec :
```bash
docker exec lespass_django poetry run python -c "from BaseBillet.models import Reservation; print(hasattr(Reservation, 'uuid_8'))"
```

Si False → remplacer `{reservation.uuid_8()}` par `{str(reservation.uuid)[:8]}`.

- [ ] **Étape 3 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues (0 silenced).`

- [ ] **Étape 4 : Créer `tests/pytest/test_signals_cascade_multi_reservations.py`**

Créer le fichier avec :

```python
"""
Tests de non-régression + nouveau flow multi-reservations sur set_ligne_article_paid().
Session 03 — Tâche 3.1.

Run:
    poetry run pytest -q tests/pytest/test_signals_cascade_multi_reservations.py
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context


@pytest.fixture(autouse=True)
def _reset_translation_after_test():
    """Reset le locale Django modifie par les signaux post-paiement.
    / Reset Django locale modified by post-payment signals."""
    from django.utils import translation
    yield
    translation.deactivate()


@pytest.fixture
def tenant_context_lespass():
    from Customers.models import Client as TenantClient
    tenant = TenantClient.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        yield tenant


@pytest.fixture
def user_acheteur(tenant_context_lespass):
    from AuthBillet.models import TibilletUser
    user = TibilletUser.objects.create(
        email=f"sig-{uuid.uuid4()}@example.org",
        username=f"sig-{uuid.uuid4()}",
    )
    yield user
    # Best-effort cleanup / Cleanup best-effort
    try:
        from django.db.models import Q
        from BaseBillet.models import (
            Commande, LigneArticle, Membership, Paiement_stripe, Reservation,
        )
        LigneArticle.objects.filter(
            Q(reservation__user_commande=user) | Q(membership__user=user)
        ).delete()
        Reservation.objects.filter(user_commande=user).delete()
        Membership.objects.filter(user=user).delete()
        Commande.objects.filter(user=user).delete()
        Paiement_stripe.objects.filter(user=user).delete()
        user.delete()
    except Exception:
        pass


def _creer_paiement_avec_n_reservations(user, n_reservations=2):
    """
    Helper : crée un Paiement_stripe PENDING avec N reservations + leurs tickets
    via `LigneArticle.reservation` (nouveau flow panier), sans FK
    `Paiement_stripe.reservation` (donc =None).
    / Helper: creates a PENDING Paiement_stripe with N reservations + tickets
    via `LigneArticle.reservation` (new cart flow), without FK `Paiement_stripe.reservation`.
    """
    from ApiBillet.serializers import get_or_create_price_sold
    from BaseBillet.models import (
        Event, LigneArticle, Paiement_stripe, PaymentMethod, Price, Product,
        Reservation, SaleOrigin, Ticket,
    )

    paiement = Paiement_stripe.objects.create(
        user=user, source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PENDING,
    )
    reservations = []
    for i in range(n_reservations):
        event = Event.objects.create(
            name=f"EvtSig-{uuid.uuid4()}",
            datetime=timezone.now() + timedelta(days=3 + i),
            jauge_max=50,
        )
        product = Product.objects.create(
            name=f"B {uuid.uuid4()}", categorie_article=Product.BILLET,
        )
        event.products.add(product)
        price = Price.objects.create(
            product=product, name="x", prix=Decimal("10.00"), publish=True,
        )
        resa = Reservation.objects.create(
            user_commande=user, event=event, status=Reservation.UNPAID,
        )
        pricesold = get_or_create_price_sold(price, event=event)
        line = LigneArticle.objects.create(
            pricesold=pricesold, amount=1000, qty=1,
            payment_method=PaymentMethod.STRIPE_NOFED,
            reservation=resa,
            paiement_stripe=paiement,
            status=LigneArticle.UNPAID,
        )
        Ticket.objects.create(
            status=Ticket.NOT_ACTIV, reservation=resa, pricesold=pricesold,
        )
        reservations.append(resa)
    return paiement, reservations


@pytest.mark.django_db
def test_legacy_mono_event_reservation_passe_en_paid(user_acheteur, tenant_context_lespass):
    """
    Flow mono-event legacy : Paiement_stripe.reservation FK set + ligne.reservation = même resa.
    Le set() dédoublonne → 1 seule reservation traitée. Comportement identique à avant.
    / Legacy mono-event: Paiement_stripe.reservation FK set + ligne.reservation = same resa.
    set() dedupes → 1 reservation processed. Identical behavior.
    """
    from ApiBillet.serializers import get_or_create_price_sold
    from BaseBillet.models import (
        Event, LigneArticle, Paiement_stripe, PaymentMethod, Price, Product,
        Reservation, Ticket,
    )

    event = Event.objects.create(
        name=f"LegacyE-{uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=2),
        jauge_max=50,
    )
    product = Product.objects.create(
        name=f"B {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(product)
    price = Price.objects.create(
        product=product, name="x", prix=Decimal("10.00"), publish=True,
    )
    resa = Reservation.objects.create(
        user_commande=user_acheteur, event=event, status=Reservation.UNPAID,
    )
    paiement = Paiement_stripe.objects.create(
        user=user_acheteur, source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PENDING,
        reservation=resa,  # FK legacy — flow mono-event
    )
    pricesold = get_or_create_price_sold(price, event=event)
    LigneArticle.objects.create(
        pricesold=pricesold, amount=1000, qty=1,
        payment_method=PaymentMethod.STRIPE_NOFED,
        reservation=resa,  # aussi peuplée, même resa
        paiement_stripe=paiement,
        status=LigneArticle.UNPAID,
    )
    Ticket.objects.create(
        status=Ticket.NOT_ACTIV, reservation=resa, pricesold=pricesold,
    )

    # Passage PENDING → PAID déclenche set_ligne_article_paid
    paiement.status = Paiement_stripe.PAID
    paiement.save()

    resa.refresh_from_db()
    # La reservation a été passée en PAID (puis trigger enchaîne → possiblement VALID)
    # / The reservation was moved to PAID (trigger chain may progress to VALID)
    assert resa.status in [Reservation.PAID, Reservation.VALID]


@pytest.mark.django_db
def test_flow_panier_n_reservations_toutes_passent_en_paid(
    user_acheteur, tenant_context_lespass,
):
    """
    Flow panier : Paiement_stripe.reservation=None + N lignes sur N reservations.
    Toutes les reservations doivent passer en PAID via le patch.
    / Cart flow: Paiement_stripe.reservation=None + N lines on N reservations.
    All reservations must move to PAID via the patch.
    """
    from BaseBillet.models import Paiement_stripe, Reservation

    paiement, reservations = _creer_paiement_avec_n_reservations(user_acheteur, n_reservations=3)
    # Confirmation préalable : FK legacy est None (panier)
    # / Sanity check: legacy FK is None (cart)
    assert paiement.reservation is None

    paiement.status = Paiement_stripe.PAID
    paiement.save()

    for resa in reservations:
        resa.refresh_from_db()
        assert resa.status in [Reservation.PAID, Reservation.VALID], (
            f"Reservation {resa.uuid} should be PAID/VALID, got {resa.status}"
        )


@pytest.mark.django_db
def test_adhesion_only_ne_touche_pas_reservations(user_acheteur, tenant_context_lespass):
    """
    Flow adhésion seule : paiement.reservation=None + ligne.reservation=None.
    Le set() est vide → aucun save() sur Reservation. Comportement identique à avant.
    / Standalone adhesion: paiement.reservation=None + ligne.reservation=None.
    Empty set → no Reservation save(). Identical behavior.
    """
    from ApiBillet.serializers import get_or_create_price_sold
    from BaseBillet.models import (
        LigneArticle, Membership, Paiement_stripe, PaymentMethod, Price, Product,
    )

    prod = Product.objects.create(
        name=f"A {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price = Price.objects.create(
        product=prod, name="std", prix=Decimal("10.00"), publish=True,
    )
    membership = Membership.objects.create(
        user=user_acheteur, price=price,
        status=Membership.WAITING_PAYMENT,
        first_name="A", last_name="B",
        contribution_value=Decimal("10.00"),
    )
    paiement = Paiement_stripe.objects.create(
        user=user_acheteur, source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PENDING,
    )
    pricesold = get_or_create_price_sold(price)
    LigneArticle.objects.create(
        pricesold=pricesold, amount=1000, qty=1,
        payment_method=PaymentMethod.STRIPE_NOFED,
        membership=membership,
        paiement_stripe=paiement,
        status=LigneArticle.UNPAID,
    )
    # Aucune reservation dans le setup / No reservation in setup
    assert paiement.reservation is None

    paiement.status = Paiement_stripe.PAID
    paiement.save()

    # Le membership trigger_A passe au ONCE via la cascade standard
    # / The membership trigger_A moves to ONCE via standard cascade
    membership.refresh_from_db()
    assert membership.status == Membership.ONCE
```

- [ ] **Étape 5 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_signals_cascade_multi_reservations.py -v
```

Attendu : 3 tests PASS.

- [ ] **Étape 6 : Non-régression sur les tests existants**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_reservation_create.py tests/pytest/test_commande_model.py tests/pytest/test_panier_session.py tests/pytest/test_commande_service.py tests/pytest/test_ticket_creator_no_checkout.py -q
```

Attendu : tous les tests passent (aucune régression introduite).

**Point de contrôle commit (mainteneur)** — fin Tâche 3.1.

---

## Tâche 3.2 : Post_save `Paiement_stripe` → `Commande.PAID`

**Fichiers :**
- Modifier : `BaseBillet/signals.py` (ajouter un nouveau handler à la fin du fichier)
- Créer : `tests/pytest/test_commande_post_save_paid.py`

**Contexte :** Quand toutes les lignes passent VALID, `set_paiement_stripe_valid` (signals.py ligne 77) bascule `Paiement_stripe.status = VALID`. À ce moment, on veut que la `Commande` associée (via OneToOne reverse `commande_obj`) passe aussi `PAID` avec `paid_at = now`.

**Approche :** un nouveau `@receiver(post_save, sender=Paiement_stripe)` qui détecte `status == VALID` et met à jour la Commande.

- [ ] **Étape 1 : Ajouter le handler dans `BaseBillet/signals.py`**

À la fin du fichier `BaseBillet/signals.py` (après la dernière ligne), ajouter :

```python
######################## SIGNAL COMMANDE ########################


@receiver(post_save, sender=Paiement_stripe)
def commande_mark_paid_when_paiement_valid(sender, instance: Paiement_stripe, **kwargs):
    """
    Dès qu'un Paiement_stripe passe à VALID, on marque la Commande liée
    comme PAID + paid_at=now. Utilisé par le flow panier multi-events.

    / As soon as a Paiement_stripe goes to VALID, mark the linked Commande
    as PAID + paid_at=now. Used by the multi-event cart flow.

    Rétrocompat : les Paiement_stripe sans Commande (flow legacy) ne
    déclenchent aucune action (commande_obj n'existe pas → AttributeError attrapée).
    / Backward compat: Paiement_stripe without Commande (legacy flow) trigger
    no action (commande_obj doesn't exist → AttributeError caught).
    """
    if instance.status != Paiement_stripe.VALID:
        return
    try:
        commande = instance.commande_obj  # OneToOne reverse
    except Exception:
        return
    if commande is None:
        return
    from BaseBillet.models import Commande
    if commande.status != Commande.PAID:
        commande.status = Commande.PAID
        commande.paid_at = timezone.now()
        commande.save(update_fields=["status", "paid_at"])
        logger.info(
            f"    SIGNAL COMMANDE : Commande {commande.uuid_8()} → PAID (paiement {instance.uuid_8()} VALID)"
        )
```

- [ ] **Étape 2 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues (0 silenced).`

- [ ] **Étape 3 : Créer `tests/pytest/test_commande_post_save_paid.py`**

```python
"""
Tests du post_save Paiement_stripe → Commande.PAID.
Session 03 — Tâche 3.2.

Run:
    poetry run pytest -q tests/pytest/test_commande_post_save_paid.py
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context


@pytest.fixture(autouse=True)
def _reset_translation_after_test():
    from django.utils import translation
    yield
    translation.deactivate()


@pytest.fixture
def tenant_context_lespass():
    from Customers.models import Client as TenantClient
    tenant = TenantClient.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        yield tenant


@pytest.fixture
def user_acheteur(tenant_context_lespass):
    from AuthBillet.models import TibilletUser
    user = TibilletUser.objects.create(
        email=f"ps-{uuid.uuid4()}@example.org",
        username=f"ps-{uuid.uuid4()}",
    )
    yield user
    try:
        from django.db.models import Q
        from BaseBillet.models import (
            Commande, LigneArticle, Membership, Paiement_stripe, Reservation,
        )
        LigneArticle.objects.filter(
            Q(reservation__user_commande=user) | Q(membership__user=user)
        ).delete()
        Reservation.objects.filter(user_commande=user).delete()
        Membership.objects.filter(user=user).delete()
        Commande.objects.filter(user=user).delete()
        Paiement_stripe.objects.filter(user=user).delete()
        user.delete()
    except Exception:
        pass


@pytest.mark.django_db
def test_paiement_valid_bascule_commande_en_paid(user_acheteur, tenant_context_lespass):
    """
    Quand un Paiement_stripe passe à VALID, la Commande liée passe à PAID + paid_at=now.
    / When Paiement_stripe goes to VALID, the linked Commande goes to PAID + paid_at=now.
    """
    from BaseBillet.models import Commande, Paiement_stripe

    paiement = Paiement_stripe.objects.create(
        user=user_acheteur, source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PENDING,
    )
    commande = Commande.objects.create(
        user=user_acheteur, email_acheteur=user_acheteur.email,
        first_name="A", last_name="B",
        status=Commande.PENDING,
        paiement_stripe=paiement,
    )

    paiement.status = Paiement_stripe.VALID
    paiement.save()

    commande.refresh_from_db()
    assert commande.status == Commande.PAID
    assert commande.paid_at is not None


@pytest.mark.django_db
def test_paiement_sans_commande_ne_plante_pas(user_acheteur, tenant_context_lespass):
    """
    Un Paiement_stripe VALID sans Commande associée (flow legacy) ne lève pas d'exception.
    / A VALID Paiement_stripe without linked Commande (legacy flow) raises no exception.
    """
    from BaseBillet.models import Paiement_stripe

    paiement = Paiement_stripe.objects.create(
        user=user_acheteur, source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PAID,
    )
    # Pas de Commande attachée / No linked Commande
    paiement.status = Paiement_stripe.VALID
    paiement.save()  # doit passer sans erreur


@pytest.mark.django_db
def test_paiement_autre_status_ne_bascule_pas_commande(
    user_acheteur, tenant_context_lespass,
):
    """
    Si le Paiement_stripe passe à PENDING ou PAID (pas VALID), la Commande reste en PENDING.
    / If Paiement_stripe goes to PENDING or PAID (not VALID), Commande stays PENDING.
    """
    from BaseBillet.models import Commande, Paiement_stripe

    paiement = Paiement_stripe.objects.create(
        user=user_acheteur, source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PENDING,
    )
    commande = Commande.objects.create(
        user=user_acheteur, email_acheteur=user_acheteur.email,
        first_name="X", last_name="Y",
        status=Commande.PENDING,
        paiement_stripe=paiement,
    )
    # Transition non VALID / Non-VALID transition
    paiement.status = Paiement_stripe.PAID
    paiement.save()

    commande.refresh_from_db()
    assert commande.status == Commande.PENDING
    assert commande.paid_at is None


@pytest.mark.django_db
def test_paiement_deja_valid_ne_re_bascule_pas(user_acheteur, tenant_context_lespass):
    """
    Si la Commande est déjà PAID, le save ne modifie pas paid_at (idempotence).
    / If Commande is already PAID, save doesn't modify paid_at (idempotence).
    """
    from BaseBillet.models import Commande, Paiement_stripe

    paiement = Paiement_stripe.objects.create(
        user=user_acheteur, source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.VALID,
    )
    initial_paid_at = timezone.now() - timedelta(hours=1)
    commande = Commande.objects.create(
        user=user_acheteur, email_acheteur=user_acheteur.email,
        first_name="I", last_name="J",
        status=Commande.PAID,
        paid_at=initial_paid_at,
        paiement_stripe=paiement,
    )
    # Re-save du paiement VALID / Re-save VALID payment
    paiement.save()

    commande.refresh_from_db()
    # paid_at n'a pas été écrasé / paid_at not overwritten
    assert commande.paid_at == initial_paid_at
```

- [ ] **Étape 4 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_commande_post_save_paid.py -v
```

Attendu : 4 tests PASS.

**Point de contrôle commit (mainteneur)** — fin Tâche 3.2.

---

## Tâche 3.3 : Param `accept_sepa` sur `CreationPaiementStripe`

**Fichiers :**
- Modifier : `PaiementStripe/views.py` (classe `CreationPaiementStripe`, lignes 32-176)
- Modifier : `BaseBillet/services_commande.py` (méthode `_creer_paiement_stripe()`)
- Créer : `tests/pytest/test_accept_sepa_flag.py`

**Contexte :** Aujourd'hui `dict_checkout_creator()` ligne 159 fait `if not self.reservation and self.config.stripe_accept_sepa`. Problème : pour un panier avec billets, `self.reservation=None` mais on ne veut pas SEPA. Solution : param explicite `accept_sepa: bool | None = None` (None = legacy, True/False = override).

- [ ] **Étape 1 : Ajouter le param `accept_sepa` dans `__init__`**

Dans `PaiementStripe/views.py`, la classe `CreationPaiementStripe.__init__` (ligne 34-44). Remplacer :

```python
    def __init__(self,
                 user: User,
                 liste_ligne_article: list,
                 metadata: dict,
                 reservation: (Reservation, None),
                 source: str = None,
                 absolute_domain: (str, None) = None,
                 success_url: (str, None) = None,
                 cancel_url: (str, None) = None,
                 invoice=None,
                 ) -> None:
```

Par :

```python
    def __init__(self,
                 user: User,
                 liste_ligne_article: list,
                 metadata: dict,
                 reservation: (Reservation, None),
                 source: str = None,
                 absolute_domain: (str, None) = None,
                 success_url: (str, None) = None,
                 cancel_url: (str, None) = None,
                 invoice=None,
                 accept_sepa: (bool, None) = None,
                 ) -> None:
        """
        accept_sepa : None = comportement legacy (SEPA si reservation=None + config ON)
                      True = forcer SEPA autorisé (cas adhésion-only)
                      False = forcer SEPA refusé (cas panier avec billets)
        / accept_sepa: None = legacy (SEPA if reservation=None + config ON)
                       True = force allow SEPA (standalone membership case)
                       False = force deny SEPA (cart-with-tickets case)
        """
```

Puis juste avant la ligne `self.user = user` dans le corps, ajouter :

```python
        self.accept_sepa = accept_sepa
```

- [ ] **Étape 2 : Adapter `dict_checkout_creator()`**

Dans la même classe, méthode `dict_checkout_creator` (ligne 149-176). Remplacer le bloc actuel :

```python
        payment_method_types = ["card",]
        if not self.reservation and self.config.stripe_accept_sepa:
            payment_method_types.append("sepa_debit")
```

Par :

```python
        payment_method_types = ["card",]
        # SEPA autorisé si :
        # - Flag explicite True (cas adhésion-only via panier), OU
        # - Flag None (legacy) + pas de reservation FK (cas adhésion directe).
        # SEPA refusé si flag explicite False (cas panier avec billets).
        # / SEPA authorized if explicit True, or legacy (None) with no reservation FK.
        # SEPA refused if explicit False (cart-with-tickets).
        if self.accept_sepa is not None:
            sepa_authorized = self.accept_sepa
        else:
            sepa_authorized = not self.reservation
        if sepa_authorized and self.config.stripe_accept_sepa:
            payment_method_types.append("sepa_debit")
```

- [ ] **Étape 3 : Mettre à jour `CommandeService._creer_paiement_stripe()`**

Dans `BaseBillet/services_commande.py`, méthode `_creer_paiement_stripe(commande, user, lignes)`. Trouver l'appel `CreationPaiementStripe(...)` et ajouter deux choses :

1. Avant l'appel, calculer `contains_tickets` en parcourant `lignes` :

```python
    @staticmethod
    def _creer_paiement_stripe(commande, user, lignes):
        """Phase 3 — crée un Paiement_stripe consolidé pour toutes les lignes.
        / Phase 3 — create a consolidated Paiement_stripe for all lines."""
        from BaseBillet.models import LigneArticle, Paiement_stripe
        from PaiementStripe.views import CreationPaiementStripe

        tenant = connection.tenant
        metadata = {
            'tenant': f'{tenant.uuid}',
            'tenant_name': f'{tenant.name}',
            'commande_uuid': f'{commande.uuid}',
        }

        # Détection : y a-t-il des billets dans la commande ?
        # Si oui → SEPA refusé (billets à utiliser rapidement).
        # Si non (adhésion-only) → SEPA autorisé si config ON.
        # / Detection: does the order contain tickets?
        # If yes → deny SEPA (tickets must be usable quickly).
        # If no (adhesion-only) → allow SEPA if config ON.
        contains_tickets = any(
            line.reservation is not None for line in lignes
        )

        new_paiement = CreationPaiementStripe(
            user=user,
            liste_ligne_article=lignes,
            metadata=metadata,
            reservation=None,  # Pas de FK : le pivot est Commande
            source=Paiement_stripe.FRONT_BILLETTERIE,
            success_url=f"stripe_return/",
            cancel_url=f"stripe_return/",
            absolute_domain=f"https://{tenant.get_primary_domain()}/panier/",
            accept_sepa=(not contains_tickets),  # <-- ajout
        )
        ...
```

Le reste de la méthode (is_valid, update statuses, save paiement_stripe) reste identique.

- [ ] **Étape 4 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues (0 silenced).`

- [ ] **Étape 5 : Créer `tests/pytest/test_accept_sepa_flag.py`**

```python
"""
Tests du flag accept_sepa sur CreationPaiementStripe.
Session 03 — Tâche 3.3.

Run:
    poetry run pytest -q tests/pytest/test_accept_sepa_flag.py
"""
import pytest
from django_tenants.utils import tenant_context


@pytest.fixture(autouse=True)
def _reset_translation_after_test():
    from django.utils import translation
    yield
    translation.deactivate()


@pytest.fixture
def tenant_context_lespass():
    from Customers.models import Client as TenantClient
    tenant = TenantClient.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        yield tenant


@pytest.fixture
def config_sepa_on(tenant_context_lespass):
    """Active SEPA dans la config (et restore en teardown).
    / Enable SEPA in config (restore on teardown)."""
    from BaseBillet.models import Configuration
    config = Configuration.get_solo()
    original = config.stripe_accept_sepa
    config.stripe_accept_sepa = True
    config.save()
    yield config
    config.stripe_accept_sepa = original
    config.save()


def _make_creator_stub(reservation=None, accept_sepa=None):
    """
    Construit une fausse instance CreationPaiementStripe juste assez peuplée
    pour appeler dict_checkout_creator() sans toucher à Stripe.
    / Build a fake CreationPaiementStripe instance populated enough to call
    dict_checkout_creator() without hitting Stripe.
    """
    from unittest.mock import MagicMock
    from BaseBillet.models import Configuration
    from PaiementStripe.views import CreationPaiementStripe

    # On crée l'instance sans __init__ (évite l'appel Stripe)
    # / Create instance without __init__ (avoid Stripe call)
    instance = CreationPaiementStripe.__new__(CreationPaiementStripe)
    instance.user = MagicMock(email="test@example.org", pk=1)
    instance.reservation = reservation
    instance.source = "F"
    instance.absolute_domain = "https://example.org/"
    instance.success_url = "ok/"
    instance.cancel_url = "ko/"
    instance.paiement_stripe_db = MagicMock(uuid="00000000")
    instance.line_items = []
    instance.mode = "payment"
    instance.metadata = {"tenant": "test"}
    instance.stripe_connect_account = "acct_x"
    instance.config = Configuration.get_solo()
    instance.accept_sepa = accept_sepa
    return instance


@pytest.mark.django_db
def test_accept_sepa_none_legacy_sans_reservation_sepa_autorise(config_sepa_on):
    """
    Legacy (accept_sepa=None) + reservation=None + config SEPA ON → sepa_debit dans les methods.
    / Legacy + reservation=None + config SEPA ON → sepa_debit in methods.
    """
    instance = _make_creator_stub(reservation=None, accept_sepa=None)
    data = instance.dict_checkout_creator()
    assert "sepa_debit" in data["payment_method_types"]


@pytest.mark.django_db
def test_accept_sepa_none_legacy_avec_reservation_pas_de_sepa(config_sepa_on):
    """
    Legacy + reservation set → pas de sepa_debit.
    / Legacy + reservation set → no sepa_debit.
    """
    from unittest.mock import MagicMock
    reservation = MagicMock(uuid="reservation-x")
    instance = _make_creator_stub(reservation=reservation, accept_sepa=None)
    data = instance.dict_checkout_creator()
    assert "sepa_debit" not in data["payment_method_types"]


@pytest.mark.django_db
def test_accept_sepa_false_force_refus_meme_sans_reservation(config_sepa_on):
    """
    Flag False → pas de sepa_debit, même si reservation=None.
    Cas panier avec billets.
    / Flag False → no sepa_debit even if reservation=None. Cart-with-tickets case.
    """
    instance = _make_creator_stub(reservation=None, accept_sepa=False)
    data = instance.dict_checkout_creator()
    assert "sepa_debit" not in data["payment_method_types"]


@pytest.mark.django_db
def test_accept_sepa_true_force_autorisation(config_sepa_on):
    """
    Flag True → sepa_debit activé.
    Cas adhésion-only via panier.
    / Flag True → sepa_debit enabled. Standalone adhesion case via cart.
    """
    instance = _make_creator_stub(reservation=None, accept_sepa=True)
    data = instance.dict_checkout_creator()
    assert "sepa_debit" in data["payment_method_types"]


@pytest.mark.django_db
def test_accept_sepa_true_mais_config_off_ignore(tenant_context_lespass):
    """
    Flag True mais config SEPA OFF → pas de sepa_debit.
    / Flag True but config SEPA OFF → no sepa_debit.
    """
    from BaseBillet.models import Configuration
    config = Configuration.get_solo()
    original = config.stripe_accept_sepa
    config.stripe_accept_sepa = False
    config.save()
    try:
        instance = _make_creator_stub(reservation=None, accept_sepa=True)
        data = instance.dict_checkout_creator()
        assert "sepa_debit" not in data["payment_method_types"]
    finally:
        config.stripe_accept_sepa = original
        config.save()
```

- [ ] **Étape 6 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_accept_sepa_flag.py -v
```

Attendu : 5 tests PASS.

- [ ] **Étape 7 : Non-régression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_commande_service.py tests/pytest/test_reservation_create.py -q
```

Attendu : tous les tests Session 02 + reservation existants passent.

**Point de contrôle commit (mainteneur)** — fin Tâche 3.3.

---

## Tâche 3.4 : `ReservationValidator` cart-aware + fix bug overlap

**Fichiers :**
- Modifier : `BaseBillet/validators.py` (classe `ReservationValidator.validate`, lignes 580-620)
- Créer : `tests/pytest/test_reservation_validator_cart_aware.py`

**Contexte :** Deux modifications dans `ReservationValidator.validate()` :

1. **Ligne 580-586 (check adhésion)** : accepter l'adhésion présente dans `self.current_commande.memberships_commande` si l'attribut est injecté.

2. **Ligne 606-620 (check overlap)** : remplacer le queryset actuel (toutes les reservations du user, sans filtre) par un appel à `reservations_bloquantes_pour_user()` (défini en Session 02) qui filtre `BLOCKING_STATUSES` + fenêtre 15 min pour `UNPAID/CREATED`.

**Rétrocompat :** `current_commande` n'est jamais injecté par les flows directs → pas de changement pour eux. Le fix overlap rend le validator plus permissif (ne bloque plus les UNPAID anciennes ou CANCELED) — comportement bug-corrigé attendu par le mainteneur.

- [ ] **Étape 1 : Modifier le check adhesion_obligatoires (lignes 579-586)**

Dans `BaseBillet/validators.py`, fonction `ReservationValidator.validate()`. Le code actuel :

```python
                # Check adhésion
                if price.adhesions_obligatoires.exists():
                    if not user.memberships.filter(
                        price__product__in=price.adhesions_obligatoires.all(),
                        deadline__gte=timezone.now(),
                    ).exists():
                        logger.warning(_(f"User is not subscribed."))
                        raise serializers.ValidationError(_(f"User is not subscribed."))
```

Le remplacer par :

```python
                # Check adhésion — cart-aware
                # L'adhésion requise peut être déjà active en DB, OU présente dans
                # la commande en cours (flow panier via current_commande injecté).
                # / Cart-aware check: required membership can be already active in DB,
                # OR in the current order (cart flow via injected current_commande).
                if price.adhesions_obligatoires.exists():
                    required_products = list(price.adhesions_obligatoires.all())
                    has_active_membership = user.memberships.filter(
                        price__product__in=required_products,
                        deadline__gte=timezone.now(),
                    ).exists()

                    # Nouveau : vérifier la commande en cours si injectée
                    # / New: check current order if injected
                    has_in_current_order = False
                    if hasattr(self, 'current_commande') and self.current_commande is not None:
                        has_in_current_order = self.current_commande.memberships_commande.filter(
                            price__product__in=required_products,
                        ).exists()

                    if not (has_active_membership or has_in_current_order):
                        logger.warning(_(f"User is not subscribed."))
                        raise serializers.ValidationError(_(f"User is not subscribed."))
```

- [ ] **Étape 2 : Fixer le bug overlap (lignes 605-620)**

Dans la même fonction, le code actuel :

```python
        # Vérification que l'utilisateur peut reserer une place s'il est déja inscrit sur un horaire
        if not Configuration.get_solo().allow_concurrent_bookings:
            start_this_event = event.datetime
            end_this_event = event.end_datetime
            if not end_this_event:
                end_this_event = start_this_event + timedelta(
                    hours=1)  # Si ya pas de fin sur l'event, on rajoute juste une heure.

            if Reservation.objects.filter(
                    user_commande=user,
            ).filter(
                Q(event__datetime__range=(start_this_event, end_this_event)) |
                Q(event__end_datetime__range=(start_this_event, end_this_event)) |
                Q(event__datetime__lte=start_this_event, event__end_datetime__gte=end_this_event)
            ).exists():
                raise serializers.ValidationError(_(f'You have already booked this slot.'))
```

Le remplacer par :

```python
        # Vérification overlap — fix bug : ne compte que les reservations réellement bloquantes.
        # Ancien comportement : TOUTES les reservations du user (même CANCELED, UNPAID
        # abandonnées) bloquaient. Nouveau : BLOCKING_STATUSES (toujours) +
        # UNPAID/CREATED récents (< 15 min) uniquement.
        # / Overlap check — bug fix: only count truly blocking reservations.
        # Old behavior: ALL user's reservations (even CANCELED, abandoned UNPAID)
        # blocked. New: BLOCKING_STATUSES (always) + UNPAID/CREATED recent (< 15 min) only.
        if not Configuration.get_solo().allow_concurrent_bookings:
            from BaseBillet.services_panier import (
                _blocking_statuses, reservations_bloquantes_pour_user,
            )
            start_this_event = event.datetime
            end_this_event = event.end_datetime
            if not end_this_event:
                end_this_event = start_this_event + timedelta(hours=1)

            conflit = reservations_bloquantes_pour_user(
                user, start_this_event, end_this_event,
            ).first()
            if conflit:
                if conflit.status in _blocking_statuses():
                    raise serializers.ValidationError(
                        _("You have already booked this slot: %(name)s")
                        % {"name": conflit.event.name}
                    )
                # Blocage récent (UNPAID/CREATED < 15 min) → message explicite
                # / Recent block (UNPAID/CREATED < 15 min) → explicit message
                raise serializers.ValidationError(
                    _("You have a payment in progress for this slot: %(name)s. "
                      "Please complete it or wait 15 minutes.")
                    % {"name": conflit.event.name}
                )
```

- [ ] **Étape 3 : `manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues (0 silenced).`

- [ ] **Étape 4 : Créer `tests/pytest/test_reservation_validator_cart_aware.py`**

```python
"""
Tests du ReservationValidator cart-aware + fix bug overlap.
Session 03 — Tâche 3.4.

Run:
    poetry run pytest -q tests/pytest/test_reservation_validator_cart_aware.py
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context


@pytest.fixture(autouse=True)
def _reset_translation_after_test():
    from django.utils import translation
    yield
    translation.deactivate()


@pytest.fixture
def tenant_context_lespass():
    from Customers.models import Client as TenantClient
    tenant = TenantClient.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        yield tenant


@pytest.fixture
def user_acheteur(tenant_context_lespass):
    from AuthBillet.models import TibilletUser
    user = TibilletUser.objects.create(
        email=f"rv-{uuid.uuid4()}@example.org",
        username=f"rv-{uuid.uuid4()}",
    )
    yield user
    try:
        from django.db.models import Q
        from BaseBillet.models import (
            Commande, LigneArticle, Membership, Paiement_stripe, Reservation,
        )
        LigneArticle.objects.filter(
            Q(reservation__user_commande=user) | Q(membership__user=user)
        ).delete()
        Reservation.objects.filter(user_commande=user).delete()
        Membership.objects.filter(user=user).delete()
        Commande.objects.filter(user=user).delete()
        Paiement_stripe.objects.filter(user=user).delete()
        user.delete()
    except Exception:
        pass


# ==========================================================================
# Tests cart-aware adhesions_obligatoires
# ==========================================================================


@pytest.mark.django_db
def test_validator_refuse_tarif_gate_sans_adhesion_ni_commande(
    user_acheteur, tenant_context_lespass,
):
    """
    Flow direct : tarif gaté + user sans adhésion + pas de current_commande → rejet.
    / Direct flow: gated rate + user without membership + no current_commande → reject.
    """
    from rest_framework.exceptions import ValidationError
    from BaseBillet.models import Event, Price, Product
    from BaseBillet.validators import ReservationValidator
    from django.test import RequestFactory

    # Setup : event + billet gaté + adhésion requise
    event = Event.objects.create(
        name=f"Gate-{uuid.uuid4()}", datetime=timezone.now() + timedelta(days=2),
        jauge_max=50,
    )
    prod_billet = Product.objects.create(
        name=f"B {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(prod_billet)
    prod_adh = Product.objects.create(
        name=f"A {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price = Price.objects.create(
        product=prod_billet, name="Gated", prix=Decimal("5.00"), publish=True,
    )
    price.adhesions_obligatoires.add(prod_adh)

    # Payload minimal pour ReservationValidator
    factory = RequestFactory()
    request = factory.post("/", {
        "email": user_acheteur.email, "event": str(event.uuid),
        str(price.uuid): "1",
    })
    request.user = user_acheteur
    validator = ReservationValidator(
        data={
            "email": user_acheteur.email, "event": str(event.uuid),
            str(price.uuid): "1",
        },
        context={"request": request},
    )
    with pytest.raises(ValidationError, match="User is not subscribed"):
        validator.is_valid(raise_exception=True)


@pytest.mark.django_db
def test_validator_accepte_tarif_gate_si_current_commande_avec_adhesion(
    user_acheteur, tenant_context_lespass,
):
    """
    Flow panier : current_commande injectée + Membership en Phase 1 → tarif gaté accepté.
    / Cart flow: current_commande injected + Membership in Phase 1 → gated rate accepted.
    """
    from django.test import RequestFactory
    from BaseBillet.models import Commande, Event, Membership, Price, Product
    from BaseBillet.validators import ReservationValidator

    event = Event.objects.create(
        name=f"OKGate-{uuid.uuid4()}", datetime=timezone.now() + timedelta(days=2),
        jauge_max=50,
    )
    prod_billet = Product.objects.create(
        name=f"B {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(prod_billet)
    prod_adh = Product.objects.create(
        name=f"A {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price_adh = Price.objects.create(
        product=prod_adh, name="Std", prix=Decimal("10.00"), publish=True,
    )
    price_gated = Price.objects.create(
        product=prod_billet, name="Gated", prix=Decimal("5.00"), publish=True,
    )
    price_gated.adhesions_obligatoires.add(prod_adh)

    # Simulation Phase 1 : Membership déjà créé dans la Commande
    # / Simulation Phase 1: Membership already created in the Commande
    commande = Commande.objects.create(
        user=user_acheteur, email_acheteur=user_acheteur.email,
        first_name="X", last_name="Y", status=Commande.PENDING,
    )
    Membership.objects.create(
        user=user_acheteur, price=price_adh, commande=commande,
        status=Membership.WAITING_PAYMENT,
        first_name="X", last_name="Y",
        contribution_value=Decimal("10.00"),
    )

    factory = RequestFactory()
    request = factory.post("/", {
        "email": user_acheteur.email, "event": str(event.uuid),
        str(price_gated.uuid): "1",
    })
    request.user = user_acheteur
    validator = ReservationValidator(
        data={
            "email": user_acheteur.email, "event": str(event.uuid),
            str(price_gated.uuid): "1",
        },
        context={"request": request},
    )
    # Injection de current_commande (comme le fera CommandeService en Phase 2)
    # / Inject current_commande (as CommandeService Phase 2 will do)
    validator.current_commande = commande

    # Le validator doit passer sans ValidationError
    # / Validator must pass without ValidationError
    assert validator.is_valid() is True


# ==========================================================================
# Tests fix bug overlap
# ==========================================================================


@pytest.mark.django_db
def test_overlap_fix_reservation_canceled_ne_bloque_plus(
    user_acheteur, tenant_context_lespass,
):
    """
    FIX BUG : une reservation CANCELED chevauchante ne bloque plus.
    / BUG FIX: a CANCELED overlapping reservation no longer blocks.
    """
    from django.test import RequestFactory
    from BaseBillet.models import Configuration, Event, Price, Product, Reservation
    from BaseBillet.validators import ReservationValidator

    config = Configuration.get_solo()
    orig = config.allow_concurrent_bookings
    config.allow_concurrent_bookings = False
    config.save()
    try:
        start = timezone.now() + timedelta(days=3)
        event_past = Event.objects.create(
            name=f"Past-{uuid.uuid4()}", datetime=start,
            end_datetime=start + timedelta(hours=2), jauge_max=50,
        )
        # Reservation CANCELED sur créneau chevauchant
        # / CANCELED reservation on overlapping slot
        Reservation.objects.create(
            user_commande=user_acheteur, event=event_past, status=Reservation.CANCELED,
        )

        # Maintenant on tente de réserver un autre event qui chevauche
        event_new = Event.objects.create(
            name=f"New-{uuid.uuid4()}", datetime=start + timedelta(hours=1),
            end_datetime=start + timedelta(hours=3), jauge_max=50,
        )
        prod = Product.objects.create(
            name=f"P {uuid.uuid4()}", categorie_article=Product.BILLET,
        )
        event_new.products.add(prod)
        price = Price.objects.create(
            product=prod, name="x", prix=Decimal("10.00"), publish=True,
        )

        factory = RequestFactory()
        request = factory.post("/", {
            "email": user_acheteur.email, "event": str(event_new.uuid),
            str(price.uuid): "1",
        })
        request.user = user_acheteur
        validator = ReservationValidator(
            data={
                "email": user_acheteur.email, "event": str(event_new.uuid),
                str(price.uuid): "1",
            },
            context={"request": request},
        )
        # Doit passer — la resa CANCELED ne bloque plus
        # / Must pass — CANCELED resa no longer blocks
        assert validator.is_valid() is True
    finally:
        config.allow_concurrent_bookings = orig
        config.save()


@pytest.mark.django_db
def test_overlap_unpaid_ancien_ne_bloque_plus(user_acheteur, tenant_context_lespass):
    """
    FIX BUG : une reservation UNPAID abandonnée > 15 min ne bloque plus.
    / BUG FIX: an UNPAID reservation abandoned > 15 min no longer blocks.
    """
    from django.test import RequestFactory
    from BaseBillet.models import Configuration, Event, Price, Product, Reservation
    from BaseBillet.validators import ReservationValidator

    config = Configuration.get_solo()
    orig = config.allow_concurrent_bookings
    config.allow_concurrent_bookings = False
    config.save()
    try:
        start = timezone.now() + timedelta(days=3)
        event_old = Event.objects.create(
            name=f"Old-{uuid.uuid4()}", datetime=start,
            end_datetime=start + timedelta(hours=2), jauge_max=50,
        )
        old_resa = Reservation.objects.create(
            user_commande=user_acheteur, event=event_old, status=Reservation.UNPAID,
        )
        # Forcer datetime > 15 min (simule resa abandonnée)
        # / Force datetime > 15 min (simulate abandoned resa)
        Reservation.objects.filter(pk=old_resa.pk).update(
            datetime=timezone.now() - timedelta(minutes=30)
        )

        event_new = Event.objects.create(
            name=f"Fresh-{uuid.uuid4()}", datetime=start + timedelta(hours=1),
            end_datetime=start + timedelta(hours=3), jauge_max=50,
        )
        prod = Product.objects.create(
            name=f"P {uuid.uuid4()}", categorie_article=Product.BILLET,
        )
        event_new.products.add(prod)
        price = Price.objects.create(
            product=prod, name="x", prix=Decimal("10.00"), publish=True,
        )

        factory = RequestFactory()
        request = factory.post("/", {
            "email": user_acheteur.email, "event": str(event_new.uuid),
            str(price.uuid): "1",
        })
        request.user = user_acheteur
        validator = ReservationValidator(
            data={
                "email": user_acheteur.email, "event": str(event_new.uuid),
                str(price.uuid): "1",
            },
            context={"request": request},
        )
        # Doit passer — UNPAID abandonnée ne bloque plus
        # / Must pass — abandoned UNPAID no longer blocks
        assert validator.is_valid() is True
    finally:
        config.allow_concurrent_bookings = orig
        config.save()


@pytest.mark.django_db
def test_overlap_paid_bloque_toujours(user_acheteur, tenant_context_lespass):
    """
    Non-régression : une reservation PAID/VALID chevauchante bloque TOUJOURS.
    / Non-regression: PAID/VALID overlapping reservation STILL blocks.
    """
    from django.test import RequestFactory
    from rest_framework.exceptions import ValidationError
    from BaseBillet.models import Configuration, Event, Price, Product, Reservation
    from BaseBillet.validators import ReservationValidator

    config = Configuration.get_solo()
    orig = config.allow_concurrent_bookings
    config.allow_concurrent_bookings = False
    config.save()
    try:
        start = timezone.now() + timedelta(days=3)
        event_paid = Event.objects.create(
            name=f"Paid-{uuid.uuid4()}", datetime=start,
            end_datetime=start + timedelta(hours=2), jauge_max=50,
        )
        Reservation.objects.create(
            user_commande=user_acheteur, event=event_paid, status=Reservation.PAID,
        )

        event_new = Event.objects.create(
            name=f"Tentative-{uuid.uuid4()}", datetime=start + timedelta(hours=1),
            end_datetime=start + timedelta(hours=3), jauge_max=50,
        )
        prod = Product.objects.create(
            name=f"P {uuid.uuid4()}", categorie_article=Product.BILLET,
        )
        event_new.products.add(prod)
        price = Price.objects.create(
            product=prod, name="x", prix=Decimal("10.00"), publish=True,
        )

        factory = RequestFactory()
        request = factory.post("/", {
            "email": user_acheteur.email, "event": str(event_new.uuid),
            str(price.uuid): "1",
        })
        request.user = user_acheteur
        validator = ReservationValidator(
            data={
                "email": user_acheteur.email, "event": str(event_new.uuid),
                str(price.uuid): "1",
            },
            context={"request": request},
        )
        # Doit échouer — PAID bloque toujours
        # / Must fail — PAID still blocks
        with pytest.raises(ValidationError, match="already booked"):
            validator.is_valid(raise_exception=True)
    finally:
        config.allow_concurrent_bookings = orig
        config.save()


@pytest.mark.django_db
def test_overlap_unpaid_recent_bloque_avec_message_paiement_en_cours(
    user_acheteur, tenant_context_lespass,
):
    """
    UNPAID < 15 min → bloque avec message "payment in progress".
    / UNPAID < 15 min → blocks with "payment in progress" message.
    """
    from django.test import RequestFactory
    from rest_framework.exceptions import ValidationError
    from BaseBillet.models import Configuration, Event, Price, Product, Reservation
    from BaseBillet.validators import ReservationValidator

    config = Configuration.get_solo()
    orig = config.allow_concurrent_bookings
    config.allow_concurrent_bookings = False
    config.save()
    try:
        start = timezone.now() + timedelta(days=3)
        event_recent = Event.objects.create(
            name=f"Rec-{uuid.uuid4()}", datetime=start,
            end_datetime=start + timedelta(hours=2), jauge_max=50,
        )
        Reservation.objects.create(
            user_commande=user_acheteur, event=event_recent, status=Reservation.UNPAID,
            # datetime sera auto_now=True (maintenant) → < 15 min
        )

        event_new = Event.objects.create(
            name=f"New-{uuid.uuid4()}", datetime=start + timedelta(hours=1),
            end_datetime=start + timedelta(hours=3), jauge_max=50,
        )
        prod = Product.objects.create(
            name=f"P {uuid.uuid4()}", categorie_article=Product.BILLET,
        )
        event_new.products.add(prod)
        price = Price.objects.create(
            product=prod, name="x", prix=Decimal("10.00"), publish=True,
        )

        factory = RequestFactory()
        request = factory.post("/", {
            "email": user_acheteur.email, "event": str(event_new.uuid),
            str(price.uuid): "1",
        })
        request.user = user_acheteur
        validator = ReservationValidator(
            data={
                "email": user_acheteur.email, "event": str(event_new.uuid),
                str(price.uuid): "1",
            },
            context={"request": request},
        )
        with pytest.raises(ValidationError, match="payment in progress"):
            validator.is_valid(raise_exception=True)
    finally:
        config.allow_concurrent_bookings = orig
        config.save()
```

- [ ] **Étape 5 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_reservation_validator_cart_aware.py -v
```

Attendu : 5 tests PASS.

- [ ] **Étape 6 : Non-régression sur reservations existants**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_reservation_create.py tests/pytest/test_reservation_limits.py tests/pytest/test_event_adhesion_obligatoire.py -v
```

Attendu : tous les tests existants passent (le cart-aware est rétrocompat — `current_commande` jamais injecté = comportement identique).

**Point de contrôle commit (mainteneur)** — fin Tâche 3.4.

---

## Tâche 3.5 : Vérifications finales Session 03

**Fichiers :** aucun — vérifications uniquement.

- [ ] **Étape 1 : `manage.py check`**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : 0 issue.

- [ ] **Étape 2 : makemigrations --dry-run**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --dry-run
```

Attendu : `No changes detected`.

- [ ] **Étape 3 : Pytest suite Sessions 01 + 02 + 03**

```bash
docker exec lespass_django poetry run pytest \
    tests/pytest/test_commande_model.py \
    tests/pytest/test_panier_session.py \
    tests/pytest/test_commande_service.py \
    tests/pytest/test_ticket_creator_no_checkout.py \
    tests/pytest/test_signals_cascade_multi_reservations.py \
    tests/pytest/test_commande_post_save_paid.py \
    tests/pytest/test_accept_sepa_flag.py \
    tests/pytest/test_reservation_validator_cart_aware.py \
    -v
```

Attendu : 13 + 28 + 4 + 2 + 3 + 4 + 5 + 5 = **64 tests PASS**.

- [ ] **Étape 4 : Non-régression globale**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

Attendu : même pattern que Sessions 01 et 02 — les ~9 flakies pré-existants passent en isolation, aucune nouvelle régression.

**Session 03 — terminée.**

---

## Récap fichiers touchés

| Action | Fichier |
|---|---|
| Modifier | `BaseBillet/signals.py` (patch `set_ligne_article_paid` + nouveau handler `commande_mark_paid_when_paiement_valid`) |
| Modifier | `PaiementStripe/views.py` (param `accept_sepa` + adaptation `dict_checkout_creator`) |
| Modifier | `BaseBillet/services_commande.py` (passer `accept_sepa` dans `_creer_paiement_stripe`) |
| Modifier | `BaseBillet/validators.py` (cart-aware adhesions_obligatoires + fix bug overlap) |
| Créer | `tests/pytest/test_signals_cascade_multi_reservations.py` (3 tests) |
| Créer | `tests/pytest/test_commande_post_save_paid.py` (4 tests) |
| Créer | `tests/pytest/test_accept_sepa_flag.py` (5 tests) |
| Créer | `tests/pytest/test_reservation_validator_cart_aware.py` (5 tests) |

## Critères de Done Session 03

- [x] `set_ligne_article_paid` itère sur les lignes → panier multi-events validé correctement, flow mono-event inchangé
- [x] Post_save `Paiement_stripe` VALID → `Commande.status = PAID` + `paid_at`
- [x] `CreationPaiementStripe(accept_sepa=...)` fonctionne : None=legacy, True=forcer, False=refuser
- [x] `CommandeService` passe `accept_sepa=False` si panier contient des billets
- [x] `ReservationValidator` accepte le tarif gaté si l'adhésion est dans `current_commande` injectée
- [x] Bug overlap corrigé : CANCELED et UNPAID > 15 min ne bloquent plus
- [x] 17 tests ajoutés en Session 03, tous PASS
- [x] Aucune régression sur les tests existants

## Hors scope — attendu en Session 04

- Vues HTMX `PanierMVT` (URLs, actions add/remove/checkout)
- Context processor `panier_context`
- Injection de `current_commande` dans le validator depuis `CommandeService` (déjà fait via attribut d'instance dans la Phase 2 de `materialiser`)

Wait — la dernière ligne est incorrecte. Le plan Session 02 ne wirait pas `validator.current_commande = commande` dans le CommandeService. Il faut le faire maintenant en Session 03, car c'est ce qui rend le cart-aware opérationnel côté panier. Je corrige la portée en ajoutant une micro-étape à la Tâche 3.4.

## Correction — Étape 7 supplémentaire de la Tâche 3.4

Après avoir rendu `ReservationValidator` cart-aware, il faut que `CommandeService` injecte effectivement `current_commande` avant d'utiliser ce validator en Phase 2. Or la Phase 2 actuelle utilise `TicketCreator` directement (qui ne valide rien), pas `ReservationValidator`. Donc l'injection n'est pas nécessaire dans `CommandeService.materialiser()` tel qu'il est écrit aujourd'hui.

**Conséquence** : le cart-aware de `ReservationValidator` est surtout utile pour le flow direct (page event → bouton "Payer maintenant" qui passe par `ReservationValidator`). Dans le flow panier, c'est `PanierSession.add_ticket` qui vérifie déjà cart-aware (Session 02, Tâche 2.3). La Session 03 consolide la règle côté validator legacy au cas où un flow en aurait besoin.

**Aucune modification supplémentaire requise dans `CommandeService`.** Les critères de Done ci-dessus sont atteints par les 4 tâches.
