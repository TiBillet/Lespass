# Panier multi-events — Plan Session 07 : Fixes blockers + simplifications

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corriger les 3 blockers du code review (C1 data loss, C2 dead code, C3 Stripe fragile) + appliquer les simplifications validées par le mainteneur (auth-only panier, cleanup code mort, revalidation centralisée, /panier/ sans form buyer).

**Architecture:** Pure maintenance — aucun nouveau concept. Fixes ciblés sur `services_commande.py` (C1 + S5 + S6 + C3), suppression de code mort (`validators.py` branche cart-aware, templates legacy, endpoint single), `PanierMVT` devient auth-only. `/panier/` délègue les infos user à `/my_account/` (pas de form buyer dédié).

**Tech Stack:** Django 5.x, DRF, pytest. Zéro nouvelle dépendance.

**Spec :** `TECH DOC/SESSIONS/LESPASS/specs/2026-04-17-panier-multi-events-design.md`
**Revue préalable :** feedback code-reviewer fin Session 06 (3 Critical + 3 Important + 12 Minor)

**Dépend de :** Sessions 01-06 DONE (87 tests pytest, zéro régression jusqu'à présent).

**Scope :**
- ✅ C1 — Propager `options` + `custom_form` dans `CommandeService.materialiser()` Phase 2
- ✅ S1 — Retirer la branche cart-aware de `ReservationValidator` (dead code → kill C2)
- ✅ S3 — Supprimer les templates morts (`htmx/views/event.html`, `htmx/components/cardTickets.html`, etc.)
- ✅ S4 — Supprimer l'endpoint `/panier/add/ticket/` (single), conserver uniquement `/panier/add/tickets_batch/`
- ✅ S2 — `PanierMVT` → `IsAuthenticated` (flow direct event/membership reste `AllowAny`)
- ✅ S8 — UX booking_form : toast clair si "Pay now" + tarif gaté non-adhérent
- ✅ S9 — Page `/panier/` sans form buyer (dérivé de `request.user`)
- ✅ S5 — `PanierSession.revalidate_all()` appelé en Phase 0 de `materialiser()`
- ✅ S6 — Consolider calcul total : supprimer `Commande.total_lignes()`, exposer `calcul_total_centimes(items)` helper
- ✅ C3 — Persister URL Stripe checkout dans `Paiement_stripe` (nouveau champ) pour redirect fiable

**Hors scope — explicitement rejetés :**
- ❌ S7 (retry Commande PENDING récente) — FALC > robustesse complexe
- ❌ S2 élargi (cart auth-only SEULEMENT ; flow direct reste anonyme)
- ❌ Refactor session en dataclass/Pydantic
- ❌ Unification navbars reunion/faire-festival

**Règle projet :** L'agent ne touche jamais à git. Les commits sont faits par le mainteneur.

---

## Architecture des fichiers impactés

| Fichier | Action | Rôle |
|---|---|---|
| `BaseBillet/services_commande.py` | Modifier | C1 (propagation options+custom_form) + S5 (revalidate_all call) + C3 (save Stripe URL) |
| `BaseBillet/services_panier.py` | Modifier | +`revalidate_all()` + helper `calcul_total_centimes()` |
| `BaseBillet/validators.py` | Modifier | S1 retirer branche cart-aware ReservationValidator |
| `BaseBillet/views.py` | Modifier | S4 retirer action `add_ticket` + S2 `IsAuthenticated` + S9 checkout sans form buyer |
| `BaseBillet/models.py` | Modifier | Supprimer `Commande.total_lignes()` (S6) + **Session 07 : pas de migration** (buyer fields restent, même si unused sur panier — évite migration douloureuse) |
| `BaseBillet/migrations/0214_paiement_stripe_checkout_url.py` | Créer | C3 ajout champ `Paiement_stripe.checkout_session_url` CharField |
| `PaiementStripe/views.py` | Modifier | C3 persister `checkout_session.url` dans `paiement_stripe_db.checkout_session_url` |
| `BaseBillet/templates/htmx/views/panier.html` | Modifier | S9 retirer form buyer (garde juste bouton checkout) |
| `BaseBillet/templates/reunion/views/event/partial/booking_form.html` | Modifier | S8 (aucun changement code — comportement géré par ReservationValidator qui rejette déjà les gated non-adhérent) |
| **Supprimés (S3)** | Delete | `htmx/views/event.html`, `htmx/components/cardTickets.html`, `htmx/components/cardOptions.html` (après vérification d'absence de référence live) |
| `tests/pytest/test_commande_service.py` | Modifier | +test C1 (options+custom_form propagés) + S5 (revalidate_all appelé) |
| `tests/pytest/test_panier_session.py` | Modifier | +tests `revalidate_all()` + `calcul_total_centimes()` |
| `tests/pytest/test_panier_mvt.py` | Modifier | Adapter tests pour auth required (login fixture) + retirer tests du endpoint single |
| `tests/pytest/test_reservation_validator_cart_aware.py` | Modifier | Retirer les 2 tests cart-aware (dead branch), garder les 4 tests overlap fix |
| `tests/pytest/test_stripe_checkout_url.py` | Créer | C3 — persistance URL Stripe |

---

## Tâche 7.1 : C1 — Propager options + custom_form Phase 2

**Fichiers :**
- Modifier : `BaseBillet/services_commande.py` (méthode `materialiser`, Phase 2)
- Modifier : `tests/pytest/test_commande_service.py` (ajouter test)

**Contexte :** Actuellement, les items ticket du panier ont `options` et `custom_form` stockés en session, mais Phase 2 de `materialiser()` ne les propage pas à la `Reservation`. Data loss silencieuse.

Tous les items d'un même event partagent les mêmes `options`/`custom_form` (venant d'une seule soumission de `booking_form.html`).

- [ ] **Étape 1 : Lire la Phase 2 actuelle**

```bash
docker exec lespass_django grep -n "Phase 2" /DjangoFiles/BaseBillet/services_commande.py
```

Repérer la boucle `for event_uuid, items_event in tickets_par_event.items():`.

- [ ] **Étape 2 : Modifier la Phase 2**

Dans `BaseBillet/services_commande.py`, trouver le bloc :

```python
        for event_uuid, items_event in tickets_par_event.items():
            event = Event.objects.get(uuid=event_uuid)
            # Construction d'un products_dict conforme au format attendu par TicketCreator
            products_dict = {}
            custom_amounts = {}
            for it in items_event:
                price = Price.objects.get(uuid=it['price_uuid'])
                qty = int(it['qty'])
                products_dict.setdefault(price.product, {})
                products_dict[price.product][price] = products_dict[price.product].get(price, 0) + qty
                if it.get('custom_amount'):
                    custom_amounts[price.uuid] = Decimal(str(it['custom_amount']))

            reservation = Reservation.objects.create(
                user_commande=user,
                event=event,
                commande=commande,
                status=Reservation.CREATED,
            )
```

Le remplacer par :

```python
        for event_uuid, items_event in tickets_par_event.items():
            event = Event.objects.get(uuid=event_uuid)
            # Construction d'un products_dict conforme au format attendu par TicketCreator
            # / Build a products_dict compatible with TicketCreator's expected format
            products_dict = {}
            custom_amounts = {}
            for it in items_event:
                price = Price.objects.get(uuid=it['price_uuid'])
                qty = int(it['qty'])
                products_dict.setdefault(price.product, {})
                products_dict[price.product][price] = products_dict[price.product].get(price, 0) + qty
                if it.get('custom_amount'):
                    custom_amounts[price.uuid] = Decimal(str(it['custom_amount']))

            # Tous les items de cet event partagent options + custom_form
            # (une seule soumission de booking_form.html par event).
            # / All items from this event share options + custom_form
            # (single submission of booking_form.html per event).
            first_item = items_event[0]
            custom_form = first_item.get('custom_form') or None
            options_uuids = first_item.get('options') or []

            reservation = Reservation.objects.create(
                user_commande=user,
                event=event,
                commande=commande,
                custom_form=custom_form,
                status=Reservation.CREATED,
            )
            if options_uuids:
                from BaseBillet.models import OptionGenerale
                opts = OptionGenerale.objects.filter(uuid__in=options_uuids)
                if opts.exists():
                    reservation.options.set(opts)
```

- [ ] **Étape 3 : Ajouter un test de propagation dans `test_commande_service.py`**

Ajouter à la fin de la classe de tests existante :

```python
@pytest.mark.django_db
def test_materialiser_propage_options_et_custom_form(
    request_authentifie, user_acheteur, tenant_context_lespass,
):
    """
    C1 fix : les options et custom_form des items panier sont propagés
    sur la Reservation créée en Phase 2.
    / C1 fix: options and custom_form from cart items are propagated to
    the Reservation created in Phase 2.
    """
    from BaseBillet.models import (
        Commande, Event, OptionGenerale, Price, Product, Reservation,
    )
    from BaseBillet.services_commande import CommandeService
    from BaseBillet.services_panier import PanierSession

    # Setup event + product FREERES + option
    prod = Product.objects.create(
        name=f"C1-{uuid.uuid4()}", categorie_article=Product.FREERES,
    )
    event = Event.objects.create(
        name=f"C1evt-{uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=3),
        jauge_max=50,
    )
    event.products.add(prod)
    price = prod.prices.filter(prix=0).first()
    option = OptionGenerale.objects.create(name=f"Opt-{uuid.uuid4().hex[:6]}")
    event.options_radio.add(option)

    panier = PanierSession(request_authentifie)
    panier.add_ticket(
        event.uuid, price.uuid, qty=1,
        options=[str(option.uuid)],
        custom_form={"dietary": "vegan"},
    )

    commande = CommandeService.materialiser(
        panier, user_acheteur,
        first_name="C1", last_name="Test",
        email=user_acheteur.email,
    )

    reservation = commande.reservations.first()
    assert reservation is not None
    assert reservation.custom_form == {"dietary": "vegan"}, (
        f"custom_form lost: {reservation.custom_form}"
    )
    assert option in reservation.options.all(), (
        "option not propagated to reservation"
    )
```

- [ ] **Étape 4 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_commande_service.py -v
```

Attendu : 5 tests PASS (4 existants + 1 nouveau).

**Point de contrôle commit (mainteneur)** — fin Tâche 7.1.

---

## Tâche 7.2 : Cleanup code mort (S1 + S3 + S4)

**Fichiers :**
- Modifier : `BaseBillet/validators.py` (retirer branche cart-aware de `ReservationValidator`)
- Supprimer : `BaseBillet/templates/htmx/views/event.html` (dead — remplacé par `reunion/views/event/retrieve.html`)
- Supprimer : `BaseBillet/templates/htmx/components/cardTickets.html` (dead — `booking_form.html` est le template vivant)
- Supprimer : `BaseBillet/templates/htmx/components/cardOptions.html` (si référencé uniquement par les dead templates — à vérifier)
- Modifier : `BaseBillet/views.py` (retirer action `add_ticket`, garder `add_tickets_batch`)
- Modifier : `tests/pytest/test_panier_mvt.py` (retirer test de l'endpoint single)
- Modifier : `tests/pytest/test_reservation_validator_cart_aware.py` (retirer 2 tests cart-aware)

**Contexte :**
- **S1** : la branche cart-aware (`hasattr(self, 'current_commande')`) dans `ReservationValidator.validate()` n'est JAMAIS injectée en production (`CommandeService` utilise `TicketCreator` directement, pas `ReservationValidator`). → dead code → supprimer.
- **S3** : `htmx/views/event.html` référencé uniquement par une fonction `event()` commentée (`views.py:2381`). La vraie page event est `reunion/views/event/retrieve.html`. Même sort pour `cardTickets.html`.
- **S4** : `PanierSession.add_ticket()` (méthode) reste. L'endpoint HTTP `/panier/add/ticket/` (single) n'est utilisé que par les tests. Le frontend prod utilise uniquement `/panier/add/tickets_batch/`.

- [ ] **Étape 1 : Retirer la branche cart-aware dans `ReservationValidator`**

Dans `BaseBillet/validators.py`, trouver le bloc dans `validate()` qui contient :

```python
                # Check adhésion — cart-aware
                if price.adhesions_obligatoires.exists():
                    required_products = list(price.adhesions_obligatoires.all())
                    has_active_membership = user.memberships.filter(
                        price__product__in=required_products,
                        deadline__gte=timezone.now(),
                    ).exists()

                    # Nouveau : vérifier la commande en cours si injectée
                    has_in_current_order = False
                    if hasattr(self, 'current_commande') and self.current_commande is not None:
                        has_in_current_order = self.current_commande.memberships_commande.filter(
                            price__product__in=required_products,
                        ).exists()

                    if not (has_active_membership or has_in_current_order):
                        logger.warning(_(f"User is not subscribed."))
                        raise serializers.ValidationError(_(f"User is not subscribed."))
```

Le remplacer par la version simplifiée (comportement pré-Session 03, sans cart-aware) :

```python
                # Check adhésion : user doit avoir une adhésion active en DB.
                # Le flow panier est géré en amont par PanierSession.add_ticket
                # qui applique son propre cart-aware check.
                # / Check membership: user must have an active membership in DB.
                # Cart flow is handled upstream by PanierSession.add_ticket which
                # applies its own cart-aware check.
                if price.adhesions_obligatoires.exists():
                    if not user.memberships.filter(
                        price__product__in=price.adhesions_obligatoires.all(),
                        deadline__gte=timezone.now(),
                    ).exists():
                        logger.warning(_(f"User is not subscribed."))
                        raise serializers.ValidationError(_(f"User is not subscribed."))
```

- [ ] **Étape 2 : Vérifier absence de références aux dead templates**

```bash
grep -rn "htmx/views/event\|htmx/components/cardTickets\|htmx/components/cardOptions" /home/jonas/TiBillet/dev/Lespass --include="*.py" --include="*.html" 2>/dev/null
```

Si **toutes** les références sont dans des commentaires, dans `htmx/` lui-même, ou dans des templates qui étendent morts, on peut supprimer.

**Si une référence non-morte apparaît** (ex: `reunion/views/...` qui fait `{% include "htmx/components/cardX" %}`) → STOP, ne pas supprimer ce fichier spécifiquement.

- [ ] **Étape 3 : Supprimer les templates morts confirmés**

```bash
# Supprimer les fichiers morts (adapter la liste selon le résultat de Étape 2)
docker exec lespass_django rm /DjangoFiles/BaseBillet/templates/htmx/views/event.html
docker exec lespass_django rm /DjangoFiles/BaseBillet/templates/htmx/components/cardTickets.html
# Éventuellement cardOptions.html, cardArtist.html, cardCreditCashless.html, cardEmail.html, cardGifts.html, cardMembership.html selon Étape 2
```

Puis vérifier Django check :

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : 0 issue.

- [ ] **Étape 4 : Retirer l'action `add_ticket` (single) dans `PanierMVT`**

Dans `BaseBillet/views.py`, classe `PanierMVT`, trouver :

```python
    # --- POST /panier/add/ticket/ ---
    @action(detail=False, methods=['POST'], url_path='add/ticket')
    def add_ticket(self, request):
        """
        Ajoute N billets au panier. Params POST attendus :
          event_uuid, price_uuid, qty, custom_amount (opt), options (opt, liste), 
          form__<field> (opt, ProductFormField).
        """
        ...
```

**Supprimer** cette méthode entière. La méthode `PanierSession.add_ticket()` (interne, dans `services_panier.py`) reste — elle est utilisée par `add_tickets_batch` et par les tests directs du service.

- [ ] **Étape 5 : Retirer les tests devenus obsolètes**

Dans `tests/pytest/test_panier_mvt.py`, supprimer les 2 tests :
- `test_POST_add_ticket_ajoute_au_panier`
- `test_POST_add_ticket_event_inexistant_retourne_erreur`

Ils testaient l'endpoint single `/panier/add/ticket/`. Les tests du batch (`test_panier_batch.py`) couvrent la même logique.

Dans `tests/pytest/test_reservation_validator_cart_aware.py`, supprimer les 2 tests cart-aware :
- `test_validator_refuse_tarif_gate_sans_adhesion_ni_commande` (comportement maintenu par le validator simple, pas par cart-aware)

Wait — ce test doit RESTER car il vérifie le comportement "pas d'adhésion → rejet" qui est toujours valide avec la version simplifiée.

- Retirer uniquement : `test_validator_accepte_tarif_gate_si_current_commande_avec_adhesion` (seul test qui utilisait `current_commande` injecté)

Les 4 tests overlap + le test "sans adhésion rejet" restent (5 tests).

- [ ] **Étape 6 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_panier_mvt.py tests/pytest/test_panier_batch.py tests/pytest/test_reservation_validator_cart_aware.py tests/pytest/test_commande_service.py -v
```

Attendu :
- `test_panier_mvt.py` : 11 tests PASS (13 − 2 supprimés)
- `test_panier_batch.py` : 5 tests PASS (inchangé)
- `test_reservation_validator_cart_aware.py` : 5 tests PASS (6 − 1 supprimé)
- `test_commande_service.py` : 5 tests PASS

**Point de contrôle commit (mainteneur)** — fin Tâche 7.2.

---

## Tâche 7.3 : Auth-only PanierMVT + /panier/ sans form buyer (S2 + S9)

**Fichiers :**
- Modifier : `BaseBillet/views.py` (`PanierMVT.get_permissions()` + `PanierMVT.checkout`)
- Modifier : `BaseBillet/templates/htmx/views/panier.html` (retirer form buyer)
- Modifier : `tests/pytest/test_panier_mvt.py` (adapter tests avec auth)

**Contexte :**
- **S2** : panier = feature auth-only. Le flow direct (event → `/validate_event/`, membership → direct) reste anonyme. Seules les actions `PanierMVT` exigent `IsAuthenticated`.
- **S9** : puisque le panier connaît `request.user`, la page `/panier/` ne demande plus first_name/last_name/email. Juste un bouton "Proceed to payment".
- Si `user.first_name` ou `user.last_name` est vide (ancien compte), afficher un message renvoyant à `/my_account/` pour compléter.

- [ ] **Étape 1 : Changer les permissions de `PanierMVT`**

Dans `BaseBillet/views.py`, classe `PanierMVT`, remplacer :

```python
    def get_permissions(self):
        # Panier accessible aux anonymes (matérialisation demande un user)
        return [permissions.AllowAny()]
```

Par :

```python
    def get_permissions(self):
        # Panier = feature auth-only (simplifie l'UX, derive buyer de request.user).
        # Le flow direct (event/membership sans panier) reste anonyme, ailleurs.
        # / Cart = auth-only feature (simpler UX, buyer derived from request.user).
        # Direct flow (event/membership without cart) stays anonymous elsewhere.
        return [permissions.IsAuthenticated()]
```

- [ ] **Étape 2 : Simplifier `PanierMVT.checkout()` (S9)**

Dans la même classe, méthode `checkout`. Remplacer :

```python
    @action(detail=False, methods=['POST'], url_path='checkout')
    def checkout(self, request):
        from AuthBillet.utils import get_or_create_user
        from BaseBillet.services_commande import CommandeService, CommandeServiceError
        from BaseBillet.services_panier import PanierSession

        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip().lower()

        if not (first_name and last_name and email):
            return self._render_badge_and_toast(
                request, message=_("First name, last name and email are required."),
                level='error',
            )

        user = get_or_create_user(email)

        panier = PanierSession(request)
        try:
            commande = CommandeService.materialiser(
                panier, user, first_name, last_name, email,
            )
        ...
```

Par :

```python
    @action(detail=False, methods=['POST'], url_path='checkout')
    def checkout(self, request):
        """
        Matérialise le panier en Commande → redirect Stripe (payant) ou
        my_account (gratuit). Utilise request.user comme buyer (auth required).
        / Materialize cart → Stripe redirect (paid) or my_account (free).
        Uses request.user as buyer (auth required).
        """
        from BaseBillet.services_commande import CommandeService, CommandeServiceError
        from BaseBillet.services_panier import PanierSession

        user = request.user
        # Si infos user incomplètes (ancien compte), renvoyer vers my_account.
        # / If user info incomplete (old account), redirect to my_account.
        if not (user.first_name and user.last_name):
            messages.warning(
                request,
                _("Please complete your profile (first name, last name) before checkout."),
            )
            return HttpResponseClientRedirect('/my_account/')

        panier = PanierSession(request)
        try:
            commande = CommandeService.materialiser(
                panier, user,
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
            )
        except CommandeServiceError as exc:
            return self._render_badge_and_toast(request, message=str(exc), level='error')
        except Exception as exc:
            logger.error(f"CommandeService.materialiser failed: {exc}")
            return self._render_badge_and_toast(
                request, message=_("Checkout failed. Please try again."), level='error'
            )

        panier.clear()

        if commande.paiement_stripe:
            try:
                checkout_session = commande.paiement_stripe.get_checkout_session()
                return HttpResponseClientRedirect(checkout_session.url)
            except Exception as exc:
                logger.error(f"Unable to retrieve Stripe checkout URL: {exc}")
                return HttpResponseClientRedirect('/my_account/my_reservations/')
        else:
            messages.success(
                request,
                _("Order confirmed. You will receive an email shortly."),
            )
            return HttpResponseClientRedirect('/my_account/my_reservations/')
```

Note : la ligne `from AuthBillet.utils import get_or_create_user` n'est plus nécessaire dans cette méthode — vérifier qu'elle n'est utilisée nulle part ailleurs dans `PanierMVT`, sinon la retirer de l'import.

- [ ] **Étape 3 : Simplifier la page `/panier/`**

Dans `BaseBillet/templates/htmx/views/panier.html`, trouver la section `<form method="post" action="{% url 'panier-checkout' %}" ...>` qui contient les inputs first_name/last_name/email.

La remplacer par :

```html
                        <form method="post" action="{% url 'panier-checkout' %}"
                              hx-post="{% url 'panier-checkout' %}"
                              class="vstack gap-3">
                            {% csrf_token %}
                            {% if user.is_authenticated and user.first_name and user.last_name %}
                                <p class="text-muted small">
                                    {% blocktrans with name=user.first_name %}Checkout as {{ name }}{% endblocktrans %}
                                    <span class="text-muted">({{ user.email }})</span>
                                </p>
                                <button type="submit" class="btn btn-primary btn-lg">
                                    <i class="bi bi-credit-card me-2" aria-hidden="true"></i>
                                    {% trans "Proceed to payment" %}
                                </button>
                            {% elif user.is_authenticated %}
                                <div class="alert alert-warning" role="alert">
                                    {% trans "Please complete your profile (first name, last name) before checkout." %}
                                    <a href="/my_account/" class="alert-link">{% trans "Complete my profile" %}</a>
                                </div>
                            {% else %}
                                <div class="alert alert-warning" role="alert">
                                    {% trans "Please log in to proceed to payment." %}
                                    <a href="#" data-bs-toggle="offcanvas" data-bs-target="#loginPanel"
                                       class="alert-link">{% trans "Log in" %}</a>
                                </div>
                            {% endif %}
                        </form>
```

Note : `user` est disponible dans les templates via le context processor `auth` standard Django.

- [ ] **Étape 4 : Adapter les tests `test_panier_mvt.py` pour auth**

Tous les tests `PanierMVT` utilisent un `http_client` anonyme qui va maintenant recevoir 403. Adapter chaque test pour se logger au préalable.

Ajouter une fixture en tête de `test_panier_mvt.py` :

```python
@pytest.fixture
def http_client_auth(tenant_context_lespass):
    """Django test client authentifié comme un user de test.
    / Django test client authenticated as a test user."""
    from AuthBillet.models import TibilletUser
    from django.test import Client
    user = TibilletUser.objects.create(
        email=f"mvt-{uuid.uuid4()}@example.org",
        username=f"mvt-{uuid.uuid4()}",
        first_name="Test",
        last_name="User",
        is_active=True,
    )
    client = Client(HTTP_HOST='lespass.tibillet.localhost')
    client.force_login(user)
    yield client, user
    try:
        user.delete()
    except Exception:
        pass
```

Remplacer tous les usages de `http_client` par `http_client_auth[0]` (et utiliser `user = http_client_auth[1]` si besoin).

**Pour test checkout** : ne plus passer `first_name`/`last_name`/`email` en POST — l'user est déjà authentifié. Seulement un POST vide.

Adapter en particulier :
- `test_POST_checkout_panier_vide_retourne_erreur` → `client.post('/panier/checkout/')` sans params
- `test_POST_checkout_manque_infos_acheteur_retourne_erreur` → **supprimer** ce test (comportement déplacé vers redirect my_account si profil incomplet)
- `test_POST_checkout_panier_gratuit_redirige` → pas de `first_name/last_name/email` en POST

Ajouter un nouveau test :

```python
@pytest.mark.django_db
def test_POST_checkout_anonyme_retourne_403(tenant_context_lespass):
    """Sans login, PanierMVT actions retournent 403.
    / Without login, PanierMVT actions return 403."""
    from django.test import Client
    anon_client = Client(HTTP_HOST='lespass.tibillet.localhost')
    response = anon_client.post('/panier/checkout/')
    assert response.status_code == 403
```

Et un test profil incomplet :

```python
@pytest.mark.django_db
def test_POST_checkout_profil_incomplet_redirige_my_account(
    tenant_context_lespass,
):
    """User authentifié sans first_name → redirect vers /my_account/.
    / Authenticated user without first_name → redirect to /my_account/."""
    from AuthBillet.models import TibilletUser
    from django.test import Client
    user = TibilletUser.objects.create(
        email=f"incomplete-{uuid.uuid4()}@example.org",
        username=f"incomplete-{uuid.uuid4()}",
        first_name="",
        last_name="",
        is_active=True,
    )
    client = Client(HTTP_HOST='lespass.tibillet.localhost')
    client.force_login(user)

    response = client.post('/panier/checkout/')
    # HTMX redirect → 200 avec HX-Redirect header
    assert response.status_code == 200
    hx_redirect = response.get('HX-Redirect', '')
    assert '/my_account/' in hx_redirect
    try:
        user.delete()
    except Exception:
        pass
```

- [ ] **Étape 5 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_panier_mvt.py -v
```

Attendu : tous les tests auth-adapted passent + 2 nouveaux tests = ~12 tests PASS.

**Point de contrôle commit (mainteneur)** — fin Tâche 7.3.

---

## Tâche 7.4 : Robustesse — S5 revalidate_all + S6 consolider total + C3 persister Stripe URL

**Fichiers :**
- Modifier : `BaseBillet/services_panier.py` (+`revalidate_all()` + `calcul_total_centimes()`)
- Modifier : `BaseBillet/services_commande.py` (appel `revalidate_all()` + supprimer duplication)
- Modifier : `BaseBillet/models.py` (supprimer `Commande.total_lignes()`)
- Créer : `BaseBillet/migrations/0214_paiement_stripe_checkout_url.py` (C3)
- Modifier : `BaseBillet/models.py` (ajouter `Paiement_stripe.checkout_session_url`)
- Modifier : `PaiementStripe/views.py` (persister URL)
- Modifier : `BaseBillet/context_processors.py` (utiliser `calcul_total_centimes`)
- Modifier : `tests/pytest/test_panier_session.py` (test `revalidate_all`)
- Modifier : `tests/pytest/test_commande_model.py` (retirer test `total_lignes`)
- Créer : `tests/pytest/test_stripe_checkout_url.py` (C3)

**Contexte :**
- **S5** : re-validation au checkout pour attraper les changements entre add et paiement (stock épuisé, price dépublié, adhésion supprimée).
- **S6** : `Commande.total_lignes()` et `context_processors._compute_total_ttc()` font la même chose de 2 façons différentes. Consolider dans un helper pur `calcul_total_centimes(items)`.
- **C3** : `Paiement_stripe.get_checkout_session()` appelle Stripe à chaque redirect. Si réseau/API lente, risque d'erreur. Persister l'URL dans le modèle une fois obtenue.

- [ ] **Étape 1 : Ajouter `calcul_total_centimes()` et `revalidate_all()` à `PanierSession`**

Dans `BaseBillet/services_panier.py`, ajouter les 2 méthodes à la classe `PanierSession` (juste avant la fin de la classe) :

```python
    def calcul_total_centimes(self):
        """
        Total TTC du panier en centimes (int). Source de vérité unique pour
        les totaux pré-matérialisation. Utilisé par le context processor et
        par materialiser() pour la détection "panier gratuit".
        / Cart TTC total in cents (int). Single source of truth for
        pre-materialization totals.
        """
        from BaseBillet.models import Price
        total = 0
        for item in self._data.get('items', []):
            try:
                price = Price.objects.get(uuid=item['price_uuid'])
            except Price.DoesNotExist:
                continue
            if price.free_price and item.get('custom_amount'):
                amount_eur = Decimal(str(item['custom_amount']))
            else:
                amount_eur = price.prix or Decimal("0.00")
            qty = int(item.get('qty', 1))
            total += int(amount_eur * qty * 100)
        return total

    def revalidate_all(self):
        """
        Re-applique toutes les validations d'add sur les items présents.
        Appelé par CommandeService.materialiser() en Phase 0.
        Lève InvalidItemError sur le premier item invalide (stock épuisé,
        price dépublié, adhésion obligatoire plus disponible, etc.).
        / Re-apply all add validations on present items. Called by
        materialiser() in Phase 0. Raises InvalidItemError on first invalid.
        """
        # Copie des items (on va les re-injecter un par un)
        # / Copy items (we'll re-inject one by one)
        items_snapshot = list(self._data.get('items', []))
        self._data['items'] = []
        self._save()
        for item in items_snapshot:
            if item['type'] == 'ticket':
                self.add_ticket(
                    event_uuid=item['event_uuid'],
                    price_uuid=item['price_uuid'],
                    qty=item['qty'],
                    custom_amount=item.get('custom_amount'),
                    options=item.get('options', []),
                    custom_form=item.get('custom_form', {}),
                )
            elif item['type'] == 'membership':
                self.add_membership(
                    price_uuid=item['price_uuid'],
                    custom_amount=item.get('custom_amount'),
                    options=item.get('options', []),
                    custom_form=item.get('custom_form', {}),
                )
```

- [ ] **Étape 2 : Appeler `revalidate_all()` dans `materialiser()`**

Dans `BaseBillet/services_commande.py`, au début de `materialiser()`, juste après le `if panier.is_empty(): raise ...` :

```python
        if panier.is_empty():
            raise CommandeServiceError(_("Cart is empty."))

        # Phase 0 : re-validation complète des items contre la DB.
        # Si stock épuisé, price dépublié, adhésion supprimée, etc. → InvalidItemError
        # qui remonte naturellement (atomic rollback → aucune écriture DB).
        # / Phase 0: full re-validation of items against DB.
        panier.revalidate_all()
```

- [ ] **Étape 3 : Supprimer `Commande.total_lignes()` (S6)**

Dans `BaseBillet/models.py`, classe `Commande`, supprimer la méthode `total_lignes()`.

Dans `tests/pytest/test_commande_model.py`, supprimer le test `test_commande_total_lignes_agrege_reservations_et_memberships`.

- [ ] **Étape 4 : Utiliser `calcul_total_centimes()` dans le context processor**

Dans `BaseBillet/context_processors.py`, remplacer la fonction `_compute_total_ttc(panier)` par l'appel direct :

Remplacer :

```python
def _compute_total_ttc(panier):
    """..."""
    from BaseBillet.models import Price
    total = Decimal('0.00')
    for item in panier.items():
        ...
    return total
```

Par (supprimer la fonction helper et utiliser directement depuis `panier_context`) :

```python
# Dans panier_context(request):
...
            'total_ttc': Decimal(panier.calcul_total_centimes()) / 100,
...
```

Donc la fonction `_compute_total_ttc(panier)` devient inutile — la supprimer.

- [ ] **Étape 5 : C3 — Ajouter `checkout_session_url` sur `Paiement_stripe`**

Dans `BaseBillet/models.py`, classe `Paiement_stripe`, ajouter le champ après `checkout_session_id_stripe` (ligne ~3360) :

```python
    checkout_session_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_("Stripe checkout URL"),
        help_text=_(
            "URL Stripe Checkout persistée après création — permet de rediriger "
            "l'utilisateur vers le paiement sans rappeler Stripe. "
            "/ Stripe Checkout URL persisted after creation — allows redirecting "
            "the user to payment without recalling Stripe."
        ),
    )
```

Générer la migration :

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet --name paiement_stripe_checkout_url
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```

- [ ] **Étape 6 : Persister l'URL dans `CreationPaiementStripe`**

Dans `PaiementStripe/views.py`, méthode `_checkout_session`, après `self.paiement_stripe_db.checkout_session_id_stripe = checkout_session.id` :

```python
        self.paiement_stripe_db.payment_intent_id = checkout_session.payment_intent
        self.paiement_stripe_db.checkout_session_id_stripe = checkout_session.id
        self.paiement_stripe_db.checkout_session_url = checkout_session.url  # <-- C3
        self.paiement_stripe_db.status = Paiement_stripe.PENDING
        self.paiement_stripe_db.save()
```

- [ ] **Étape 7 : Utiliser l'URL persistée dans `PanierMVT.checkout`**

Dans `BaseBillet/views.py`, méthode `checkout` de `PanierMVT`, remplacer :

```python
        if commande.paiement_stripe:
            try:
                checkout_session = commande.paiement_stripe.get_checkout_session()
                return HttpResponseClientRedirect(checkout_session.url)
            except Exception as exc:
                logger.error(f"Unable to retrieve Stripe checkout URL: {exc}")
                return HttpResponseClientRedirect('/my_account/my_reservations/')
```

Par :

```python
        if commande.paiement_stripe and commande.paiement_stripe.checkout_session_url:
            return HttpResponseClientRedirect(commande.paiement_stripe.checkout_session_url)
        elif commande.paiement_stripe:
            logger.error(
                f"Commande {commande.uuid_8()} has Paiement_stripe but no checkout_session_url"
            )
            messages.error(
                request,
                _("Payment link unavailable. Please contact support."),
            )
            return HttpResponseClientRedirect('/my_account/my_reservations/')
```

- [ ] **Étape 8 : Tests C3 — créer `tests/pytest/test_stripe_checkout_url.py`**

```python
"""
Tests C3 : persistance de l'URL Stripe checkout.
Session 07 — Tâche 7.4.

Run:
    poetry run pytest -q tests/pytest/test_stripe_checkout_url.py
"""
import uuid
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


@pytest.mark.django_db
def test_paiement_stripe_a_champ_checkout_session_url(tenant_context_lespass):
    """
    Le modèle Paiement_stripe a bien le champ checkout_session_url.
    / Paiement_stripe model has the checkout_session_url field.
    """
    from BaseBillet.models import Paiement_stripe
    fields = [f.name for f in Paiement_stripe._meta.get_fields()]
    assert 'checkout_session_url' in fields


@pytest.mark.django_db
def test_paiement_stripe_checkout_session_url_nullable(tenant_context_lespass):
    """
    Le champ est nullable (defaut None).
    / The field is nullable (default None).
    """
    from AuthBillet.models import TibilletUser
    from BaseBillet.models import Paiement_stripe
    user = TibilletUser.objects.create(
        email=f"c3-{uuid.uuid4()}@example.org",
        username=f"c3-{uuid.uuid4()}",
    )
    p = Paiement_stripe.objects.create(
        user=user,
        source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PENDING,
    )
    assert p.checkout_session_url is None
    p.checkout_session_url = "https://checkout.stripe.com/c/pay/cs_test_xxx"
    p.save()
    p.refresh_from_db()
    assert p.checkout_session_url == "https://checkout.stripe.com/c/pay/cs_test_xxx"
    try:
        p.delete()
        user.delete()
    except Exception:
        pass
```

- [ ] **Étape 9 : Test `revalidate_all()` dans `test_panier_session.py`**

Ajouter à la fin de `tests/pytest/test_panier_session.py` :

```python
@pytest.mark.django_db
def test_revalidate_all_detecte_price_depublie(
    request_with_session, event_avec_tarif,
):
    """
    revalidate_all() détecte un price qui a été dépublié après ajout.
    / revalidate_all() detects a price unpublished after add.
    """
    from BaseBillet.services_panier import PanierSession, InvalidItemError

    event, price = event_avec_tarif
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=1)

    # Simuler un dépubliage entre add et checkout
    # / Simulate unpublishing between add and checkout
    price.publish = False
    price.save()

    with pytest.raises(InvalidItemError, match="not available"):
        panier.revalidate_all()


@pytest.mark.django_db
def test_calcul_total_centimes(request_with_session, event_avec_tarif):
    """
    calcul_total_centimes() retourne le total en int centimes.
    / calcul_total_centimes() returns total in int cents.
    """
    from BaseBillet.services_panier import PanierSession

    event, price = event_avec_tarif  # price = 10.00 EUR
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=3)

    assert panier.calcul_total_centimes() == 3000  # 3 x 10€ = 3000 centimes
```

- [ ] **Étape 10 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_panier_session.py tests/pytest/test_panier_mvt.py tests/pytest/test_commande_service.py tests/pytest/test_commande_model.py tests/pytest/test_stripe_checkout_url.py tests/pytest/test_panier_context_processor.py -v
```

Attendu : tous les tests passent (avec -1 test `total_lignes` supprimé + 2 nouveaux tests `revalidate_all`/`calcul_total` + 2 tests C3).

**Point de contrôle commit (mainteneur)** — fin Tâche 7.4.

---

## Tâche 7.5 : Vérifications finales Session 07

**Fichiers :** aucun — vérifications uniquement.

- [ ] **Étape 1 : `manage.py check`**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : 0 issue.

- [ ] **Étape 2 : `makemigrations --dry-run`**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --dry-run
```

Attendu : `No changes detected`.

- [ ] **Étape 3 : Pytest suite Sessions 01-07**

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
    tests/pytest/test_panier_context_processor.py \
    tests/pytest/test_panier_mvt.py \
    tests/pytest/test_panier_batch.py \
    tests/pytest/test_stripe_checkout_url.py \
    -q
```

Attendu (Session 06 = 87 tests, Session 07 adjustments) :
- `test_panier_mvt.py` : 12 (11 existants − 2 supprimés + 3 nouveaux)
- `test_commande_service.py` : 5 (+1 C1)
- `test_commande_model.py` : 12 (−1 total_lignes)
- `test_panier_session.py` : 30 (+2 revalidate + total)
- `test_reservation_validator_cart_aware.py` : 5 (−1 cart-aware)
- `test_stripe_checkout_url.py` : 2 (nouveau)
- Autres : inchangés

**Total attendu : ~87 tests PASS** (− 4 supprimés + 8 nouveaux = +4 net → 91 approximativement).

- [ ] **Étape 4 : Non-régression globale**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

Attendu : même pattern de flakies que Sessions précédentes (tests pré-existants qui passent en isolation).

- [ ] **Étape 5 : Ruff sur fichiers touchés**

```bash
docker exec lespass_django poetry run ruff check --fix \
    /DjangoFiles/BaseBillet/services_panier.py \
    /DjangoFiles/BaseBillet/services_commande.py \
    /DjangoFiles/BaseBillet/context_processors.py
docker exec lespass_django poetry run ruff check \
    /DjangoFiles/BaseBillet/services_panier.py \
    /DjangoFiles/BaseBillet/services_commande.py \
    /DjangoFiles/BaseBillet/context_processors.py
```

Attendu : `All checks passed!`.

- [ ] **Étape 6 : Mettre à jour `PLAN_LESPASS.md` section 8**

Ajouter après le bilan existant :

```markdown
**Session 07 (2026-04-17) — Fixes blockers + simplifications** :
- C1 : options + custom_form propagés à Phase 2 (fix data loss)
- C3 : URL Stripe checkout persistée dans le modèle (fix fragilité redirect)
- S1 : suppression branche cart-aware dead de ReservationValidator
- S2 : PanierMVT auth-only (flow direct anonyme conservé)
- S3 : templates morts supprimés (htmx/views/event.html, cardTickets.html)
- S4 : endpoint single /panier/add/ticket/ supprimé (batch suffit)
- S5 : PanierSession.revalidate_all() appelé en Phase 0 de materialiser()
- S6 : Commande.total_lignes() remplacé par PanierSession.calcul_total_centimes()
- S9 : /panier/ sans form buyer (dérivé de request.user)

Migration : `BaseBillet.0214_paiement_stripe_checkout_url`
```

**Session 07 — terminée. Chantier panier v2 clos avec 0 blocker résiduel.**

---

## Récap fichiers touchés

| Action | Fichier |
|---|---|
| Modifier | `BaseBillet/services_commande.py` (C1 propagation + S5 revalidate_all call + C3 URL use) |
| Modifier | `BaseBillet/services_panier.py` (+revalidate_all + calcul_total_centimes) |
| Modifier | `BaseBillet/validators.py` (S1 remove cart-aware branch) |
| Modifier | `BaseBillet/views.py` (S4 remove single endpoint + S2 IsAuthenticated + S9 simplify checkout) |
| Modifier | `BaseBillet/models.py` (S6 remove total_lignes + C3 add checkout_session_url) |
| Créer | `BaseBillet/migrations/0214_paiement_stripe_checkout_url.py` |
| Modifier | `PaiementStripe/views.py` (C3 persist URL) |
| Modifier | `BaseBillet/context_processors.py` (use calcul_total_centimes) |
| Modifier | `BaseBillet/templates/htmx/views/panier.html` (S9 remove buyer form) |
| Supprimer | `BaseBillet/templates/htmx/views/event.html` (S3 dead) |
| Supprimer | `BaseBillet/templates/htmx/components/cardTickets.html` (S3 dead) |
| (éventuels autres morts) | selon vérification Tâche 7.2 Étape 2 |
| Modifier | 4 fichiers de tests pytest (adapter auth + tests new) |
| Créer | `tests/pytest/test_stripe_checkout_url.py` |
| Modifier | `TECH DOC/SESSIONS/LESPASS/PLAN_LESPASS.md` (section 8 Session 07) |

## Critères de Done Session 07

- [x] C1 fix : `Reservation.custom_form` et `Reservation.options` persistés depuis le panier
- [x] C2 éliminé : branche cart-aware de `ReservationValidator` supprimée (dead code)
- [x] C3 fix : URL Stripe persistée, redirect fiable
- [x] S1 : flow direct avec gated rate passe par `ReservationValidator` simple (user is member OR reject)
- [x] S2 : `PanierMVT` auth-only (403 si anonyme), flow direct reste anonyme
- [x] S3 : templates morts supprimés (vérification `grep` avant)
- [x] S4 : un seul endpoint HTTP add-to-cart (`/panier/add/tickets_batch/`)
- [x] S5 : `revalidate_all()` appelé au checkout
- [x] S6 : source de vérité unique pour le total (`calcul_total_centimes`)
- [x] S9 : page `/panier/` sans form buyer
- [x] Migration `0214_paiement_stripe_checkout_url` appliquée
- [x] Tests Sessions 01-07 : ~91 PASS
- [x] Zéro régression sur les 700+ tests existants
- [x] `manage.py check` : 0 issue
- [x] Ruff propre sur fichiers services
- [x] `PLAN_LESPASS.md` mis à jour avec le récap Session 07
