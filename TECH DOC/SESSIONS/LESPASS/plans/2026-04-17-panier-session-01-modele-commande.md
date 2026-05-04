# Panier multi-events — Plan Session 01 : Modèle Commande + migration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poser le socle DB du panier — nouveau modèle `Commande` pivot + FK nullable sur `Reservation` et `Membership`, avec tests de modèles isolés.

**Architecture:** Ajout d'un modèle `Commande` dans `BaseBillet/models.py` qui regroupera N `Reservation` + M `Membership` en une commande unique, liée optionnellement à un `Paiement_stripe` via OneToOne nullable. Les FK `commande` sur `Reservation`/`Membership` sont nullable pour préserver les flows directs existants (aucune régression).

**Tech Stack:** Django 5.x, django-tenants (migration multi-schemas), pytest, FALC (verbose/explicite/commentaires bilingues FR/EN).

**Spec:** `TECH DOC/SESSIONS/LESPASS/specs/2026-04-17-panier-multi-events-design.md`

**Scope de cette session :**
- ✅ Modèle `Commande` avec tous ses champs et statuts
- ✅ FK `commande` (nullable) sur `Reservation`
- ✅ FK `commande` (nullable) sur `Membership`
- ✅ Migration unique couvrant les 3 changements
- ✅ Tests pytest couvrant les modèles isolément (pas de service, pas de vue)

**Hors scope (sessions suivantes) :**
- ❌ `PanierSession` / `CommandeService` → Session 02
- ❌ Adaptation signals.py → Session 03
- ❌ Vues HTMX / templates → Sessions 04-05
- ❌ Tests E2E Playwright → Session 06

**Point de contrôle à la fin :** `manage.py check` OK + `migrate_schemas` OK + `pytest tests/pytest/test_commande_model.py` OK.

**Règle du projet :** Les opérations git (add/commit/push) sont toujours réalisées par le mainteneur. L'agent ne touche pas à git.

---

## Tâche 1.1 : Créer le modèle `Commande` dans `BaseBillet/models.py`

**Fichiers :**
- Modifier : `BaseBillet/models.py` (ajouter la classe `Commande` juste avant `class PriceSold` ligne 2615)

**Contexte :** Le modèle `Commande` est le nouveau pivot du panier. Il agrège N `Reservation` + M `Membership` et référence au plus UN `Paiement_stripe` (OneToOne nullable pour les commandes gratuites). Le modèle doit vivre **avant** `Reservation` et `Membership` dans le fichier pour que les FK réverses soient déclarables via `"Commande"` string references.

**Position dans le fichier** : insérer entre `class PromotionalCode` (fin ligne ~1533) et la section `@receiver(post_save, sender=Product)` ligne ~1536. Justification : `Commande` dépend de `PromotionalCode` (FK), donc doit venir après. `Reservation`, `Membership`, `Paiement_stripe` (lignes 2710, 3930, 3349) viennent après et référenceront `"Commande"` via string.

- [ ] **Étape 1 : Lire le contexte pour situer l'insertion**

```bash
docker exec lespass_django poetry run python -c "
from BaseBillet import models
print('Commande déjà existant ?', hasattr(models, 'Commande'))
"
```

Attendu : `Commande déjà existant ? False` — sinon stop et revérifier l'état du repo.

- [ ] **Étape 2 : Ajouter le modèle `Commande`**

Dans `BaseBillet/models.py`, insérer **juste après** la classe `PromotionalCode` (après sa `class Meta` et avant le premier `@receiver(post_save, sender=Product)`) :

```python
class Commande(models.Model):
    """
    Commande unifiée : regroupe plusieurs reservations et adhésions dans un achat
    unique (panier multi-events). Sert de pivot sémantique, découplé du moyen de
    paiement (Stripe aujourd'hui, autres moyens plus tard).

    / Unified order: groups several reservations and memberships into a single
    purchase (multi-event cart). Semantic pivot, decoupled from the payment mean
    (Stripe today, other means later).

    Liens (FK inverses) :
      - commande.reservations    → Reservation M2M/FK
      - commande.memberships_commande → Membership M2M/FK
      - commande.paiement_stripe → Paiement_stripe OneToOne nullable
    """

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="commandes",
        verbose_name=_("Buyer"),
        help_text=_(
            "Utilisateur acheteur (résolu par email au checkout). "
            "/ Buyer user (resolved by email at checkout)."
        ),
    )

    # Informations acheteur, capturées au moment du checkout
    # / Buyer information, captured at checkout time
    email_acheteur = models.EmailField(
        verbose_name=_("Buyer email"),
    )
    first_name = models.CharField(
        max_length=200,
        verbose_name=_("First name"),
    )
    last_name = models.CharField(
        max_length=200,
        verbose_name=_("Last name"),
    )

    # Statuts du cycle de vie d'une commande
    # / Order lifecycle statuses
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    PAID = "PAID"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"
    STATUS_CHOICES = [
        (DRAFT, _("Draft")),
        (PENDING, _("Pending payment")),
        (PAID, _("Paid")),
        (CANCELED, _("Canceled")),
        (EXPIRED, _("Expired")),
    ]
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=DRAFT,
        verbose_name=_("Order status"),
    )

    # Lien optionnel vers le paiement Stripe.
    # Nullable car :
    #   - une commande gratuite (total 0€) n'a pas de paiement
    #   - une commande DRAFT pré-checkout n'a pas encore de paiement
    # / Optional link to the Stripe payment. Nullable because:
    #   - a free order (total 0€) has no payment
    #   - a DRAFT pre-checkout order has no payment yet
    paiement_stripe = models.OneToOneField(
        "Paiement_stripe",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commande_obj",
        verbose_name=_("Stripe payment"),
    )

    # Code promo appliqué au panier (au plus un par commande en v1).
    # / Promotional code applied to the cart (at most one per order in v1).
    promo_code = models.ForeignKey(
        PromotionalCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commandes",
        verbose_name=_("Promotional code"),
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Paid at"),
    )

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")

    def __str__(self):
        return f"Commande {str(self.uuid)[:8]} ({self.status})"

    def uuid_8(self):
        """Raccourci d'affichage. / Display shortcut."""
        return f"{self.uuid}".partition("-")[0]

    def total_lignes(self):
        """
        Somme des montants TTC des LigneArticle de cette commande.
        Parcours : reservations → lignearticles + memberships → lignearticles.
        / Sum of TTC amounts for this order's LigneArticle.
        Walk: reservations → lignearticles + memberships → lignearticles.

        Retourne des centimes (int) pour cohérence avec LigneArticle.amount.
        / Returns cents (int) matching LigneArticle.amount.
        """
        total = 0
        # Lignes rattachées via les reservations du panier
        # / Lines attached via the order's reservations
        for reservation in self.reservations.all():
            for ligne in reservation.lignearticles.all():
                total += int(ligne.amount * ligne.qty)
        # Lignes rattachées via les memberships du panier
        # / Lines attached via the order's memberships
        for membership in self.memberships_commande.all():
            for ligne in membership.lignearticles.all():
                total += int(ligne.amount * ligne.qty)
        return total
```

- [ ] **Étape 3 : Vérifier que l'import de `uuid` et `settings` sont présents en tête de fichier**

Le fichier `BaseBillet/models.py` utilise déjà `uuid` et `settings` partout — aucune nouvelle ligne d'import n'est nécessaire. Vérification rapide :

```bash
docker exec lespass_django poetry run python -c "
with open('/DjangoFiles/BaseBillet/models.py') as f:
    content = f.read()
print('import uuid' in content, 'from django.conf import settings' in content or 'settings.AUTH_USER_MODEL' in content)
"
```

Attendu : `True True` — les imports sont déjà là. Sinon, les ajouter en tête.

- [ ] **Étape 4 : `python manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues (0 silenced).`

Si erreur **E304** (`Reverse accessor for 'Commande.paiement_stripe' clashes`) : c'est normal, ça signifie qu'on a bien ajouté un OneToOne. Relire le message en détail. S'il se plaint d'un `related_name` qui clashe avec un existant, vérifier qu'il n'y a pas déjà un `related_name="commande_obj"` sur `Paiement_stripe` — si oui, choisir un autre nom (proposition alternative : `commande_reverse`).

**Point de contrôle commit** — à ce stade, le modèle existe mais sans migration. Le mainteneur peut commit "wip: add Commande model" s'il le souhaite, mais attendre la migration est plus propre.

---

## Tâche 1.2 : Ajouter FK `commande` nullable sur `Reservation`

**Fichiers :**
- Modifier : `BaseBillet/models.py` (classe `Reservation`, ligne ~2710)

**Contexte :** La FK doit être **nullable** pour que les flows directs existants (achat mono-event sans passer par le panier) continuent de créer des `Reservation` avec `commande=None`. **Aucune régression** sur l'API existante.

- [ ] **Étape 1 : Repérer la position dans la classe `Reservation`**

Dans `BaseBillet/models.py`, la classe `Reservation` commence ligne ~2710. Le champ `event` (FK vers `Event`) est ligne ~2720. On va ajouter `commande` **juste après `event`**, avant le bloc `TYPE_CHOICES`.

- [ ] **Étape 2 : Ajouter la FK `commande`**

Dans la classe `Reservation`, après le champ `event` et avant le tuple `(CANCELED, CREATED, UNPAID, ...)` :

```python
    # FK optionnelle vers la commande qui regroupe cette reservation avec d'autres
    # (billets d'autres events + adhésions). Nullable pour que les flows directs
    # existants (mono-event sans panier) continuent de fonctionner sans régression.
    # / Optional FK to the order that groups this reservation with others
    # (tickets from other events + memberships). Nullable so that existing
    # direct flows (mono-event without cart) continue to work without regression.
    commande = models.ForeignKey(
        "Commande",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations",
        verbose_name=_("Order"),
        help_text=_(
            "Renseignée uniquement si la reservation a été créée via un panier multi-items. "
            "/ Only set if the reservation was created via a multi-item cart."
        ),
    )
```

- [ ] **Étape 3 : `python manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues (0 silenced).`

---

## Tâche 1.3 : Ajouter FK `commande` nullable sur `Membership`

**Fichiers :**
- Modifier : `BaseBillet/models.py` (classe `Membership`, ligne ~3930)

**Contexte :** Même logique que `Reservation`. La FK est nullable. Le `related_name` est `memberships_commande` (et non `memberships` qui est déjà pris pour le FK `user → Membership`).

- [ ] **Étape 1 : Repérer la position dans la classe `Membership`**

Dans `BaseBillet/models.py`, la classe `Membership` commence ligne ~3930. Le champ `price` est ligne ~3939. On va ajouter `commande` juste après `price`, avant les champs `asset_fedow` et `card_number`.

- [ ] **Étape 2 : Ajouter la FK `commande`**

Dans la classe `Membership`, après le champ `price` :

```python
    # FK optionnelle vers la commande qui regroupe cette adhésion avec d'autres
    # items (billets, autres adhésions). Nullable pour que les flows directs
    # existants (adhésion isolée via MembershipValidator) continuent de fonctionner.
    # / Optional FK to the order that groups this membership with other items
    # (tickets, other memberships). Nullable so that existing direct flows
    # (standalone membership via MembershipValidator) continue to work.
    commande = models.ForeignKey(
        "Commande",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memberships_commande",
        verbose_name=_("Order"),
        help_text=_(
            "Renseignée uniquement si l'adhésion a été créée via un panier multi-items. "
            "/ Only set if the membership was created via a multi-item cart."
        ),
    )
```

- [ ] **Étape 3 : `python manage.py check` doit passer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues (0 silenced).`

---

## Tâche 1.4 : Générer la migration

**Fichiers :**
- Créer : `BaseBillet/migrations/0213_commande_and_fks.py` (auto-généré par Django)

**Contexte :** Une seule migration couvrira les 3 changements (création `Commande` + FK sur `Reservation` + FK sur `Membership`) car ils sont dans la même app `BaseBillet`. Django lit les dépendances et ordonne correctement : `Commande` créé **d'abord** (elle est référencée par les FK), puis les `AddField` sur les deux modèles existants.

- [ ] **Étape 1 : Générer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet --name commande_and_fks
```

Attendu : sortie du style :
```
Migrations for 'BaseBillet':
  BaseBillet/migrations/0213_commande_and_fks.py
    + Create model Commande
    + Add field commande to reservation
    + Add field commande to membership
```

Si Django génère plusieurs migrations séparées, c'est OK — vérifier leur ordre de dépendance. Si le numéro de migration diffère (0214, 0215...), c'est OK aussi (dépend du dernier numéro en place).

- [ ] **Étape 2 : Inspecter la migration générée**

```bash
docker exec lespass_django cat /DjangoFiles/BaseBillet/migrations/0213_commande_and_fks.py
```

Vérifier que :
- L'opération `CreateModel('Commande', ...)` est présente avec tous les champs
- L'opération `AddField('reservation', 'commande', ...)` est présente
- L'opération `AddField('membership', 'commande', ...)` est présente
- Les `on_delete=django.db.models.deletion.SET_NULL` sont corrects
- `dependencies` référence la migration précédente (`0212_laboutikapikey_user` ou équivalent) + éventuellement une migration `AuthBillet` pour `settings.AUTH_USER_MODEL`

- [ ] **Étape 3 : Dry-run de la migration sur un seul schema (tenant `lespass`)**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate BaseBillet --schema=lespass --plan
```

Attendu : liste des migrations à appliquer, dont la nouvelle. Pas d'erreur SQL.

- [ ] **Étape 4 : Appliquer la migration sur tous les schemas**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```

Attendu : migration appliquée sur tous les tenants sans erreur. Sortie :
```
=== Running migrate for schema public
  Applying BaseBillet.0213_commande_and_fks... OK
=== Running migrate for schema lespass
  Applying BaseBillet.0213_commande_and_fks... OK
...
```

- [ ] **Étape 5 : Vérifier l'intégrité post-migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run python /DjangoFiles/manage.py showmigrations BaseBillet | tail -5
```

Attendu :
- `System check identified no issues (0 silenced).`
- La nouvelle migration marquée `[X]` (appliquée).

**Point de contrôle commit** — à ce stade : le modèle + les FK + la migration appliquée forment un livrable atomique. Le mainteneur peut commit "feat(panier): add Commande model with FKs on Reservation and Membership" avant de passer aux tests.

---

## Tâche 1.5 : Tests pytest des modèles

**Fichiers :**
- Créer : `tests/pytest/test_commande_model.py`

**Contexte :** Tests isolés qui valident :
1. Création d'une `Commande` minimale (statut DRAFT par défaut)
2. Relations FK inverses fonctionnent (`commande.reservations`, `commande.memberships_commande`)
3. Paiement_stripe OneToOne nullable fonctionne dans les deux sens
4. `Reservation` et `Membership` peuvent toujours être créés **sans** commande (rétrocompat)
5. `Commande.total_lignes()` somme correctement
6. Unicité du OneToOne `paiement_stripe` (un `Paiement_stripe` ne peut être associé qu'à une seule `Commande`)

Les tests tournent dans le schema tenant `lespass` via les fixtures existantes. On utilise `tenant_context` pour garantir l'isolation.

- [ ] **Étape 1 : Créer le fichier de tests**

Créer `tests/pytest/test_commande_model.py` avec le contenu suivant :

```python
"""
Tests unitaires du modèle Commande et de ses relations.
/ Unit tests for the Commande model and its relations.

Scope Session 01 : modèles uniquement, pas de service ni de vue.
/ Session 01 scope: models only, no service or view.

Run:
    poetry run pytest -q tests/pytest/test_commande_model.py
"""
import uuid as uuid_lib
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone
from django_tenants.utils import tenant_context


@pytest.fixture
def tenant_context_lespass():
    """Context manager qui fournit le tenant lespass activé.
    / Context manager that provides the activated lespass tenant."""
    from Customers.models import Client as TenantClient
    tenant = TenantClient.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        yield tenant


@pytest.fixture
def user_acheteur(tenant_context_lespass):
    """Utilisateur de test pour les commandes.
    / Test user for orders."""
    from AuthBillet.models import TibilletUser
    email = f"acheteur-{uuid_lib.uuid4()}@example.org"
    user = TibilletUser.objects.create(
        email=email,
        username=email,
    )
    yield user
    # Nettoyage après le test / Cleanup after test
    user.delete()


@pytest.mark.django_db(transaction=True)
def test_commande_creation_minimale(tenant_context_lespass, user_acheteur):
    """
    Une Commande peut être créée avec les champs obligatoires.
    Par défaut, status=DRAFT, pas de paiement, pas de promo_code.
    / A Commande can be created with mandatory fields.
    Default: status=DRAFT, no payment, no promo_code.
    """
    from BaseBillet.models import Commande

    commande = Commande.objects.create(
        user=user_acheteur,
        email_acheteur=user_acheteur.email,
        first_name="Alice",
        last_name="Dupont",
    )

    assert commande.uuid is not None
    assert commande.status == Commande.DRAFT
    assert commande.paiement_stripe is None
    assert commande.promo_code is None
    assert commande.paid_at is None
    assert commande.created_at is not None
    # Vérification __str__ / __str__ check
    assert "DRAFT" in str(commande)
    assert str(commande.uuid)[:8] in str(commande)


@pytest.mark.django_db(transaction=True)
def test_commande_uuid_8_raccourci(tenant_context_lespass, user_acheteur):
    """
    La méthode uuid_8() retourne les 8 premiers caractères de l'UUID.
    / uuid_8() method returns the first 8 characters of the UUID.
    """
    from BaseBillet.models import Commande

    commande = Commande.objects.create(
        user=user_acheteur,
        email_acheteur="test@example.org",
        first_name="Bob",
        last_name="Martin",
    )
    assert commande.uuid_8() == str(commande.uuid)[:8]


@pytest.mark.django_db(transaction=True)
def test_commande_tous_les_statuts_acceptes(tenant_context_lespass, user_acheteur):
    """
    Les 5 statuts DRAFT/PENDING/PAID/CANCELED/EXPIRED sont valides.
    / All 5 statuses DRAFT/PENDING/PAID/CANCELED/EXPIRED are valid.
    """
    from BaseBillet.models import Commande

    for status in [Commande.DRAFT, Commande.PENDING, Commande.PAID,
                   Commande.CANCELED, Commande.EXPIRED]:
        commande = Commande.objects.create(
            user=user_acheteur,
            email_acheteur=user_acheteur.email,
            first_name="Charlie",
            last_name="Durand",
            status=status,
        )
        assert commande.status == status


@pytest.mark.django_db(transaction=True)
def test_reservation_peut_etre_creee_sans_commande(tenant_context_lespass, user_acheteur):
    """
    Rétrocompatibilité : une Reservation peut toujours être créée sans FK commande.
    Garantit qu'on ne casse pas le flow mono-event existant.
    / Backward compat: a Reservation can still be created without the commande FK.
    Ensures we don't break the existing mono-event flow.
    """
    from BaseBillet.models import Event, Reservation

    event = Event.objects.create(
        name=f"Test Event {uuid_lib.uuid4()}",
        datetime=timezone.now() + timedelta(days=7),
    )
    reservation = Reservation.objects.create(
        user_commande=user_acheteur,
        event=event,
    )
    assert reservation.commande is None
    assert reservation.event == event


@pytest.mark.django_db(transaction=True)
def test_membership_peut_etre_cree_sans_commande(tenant_context_lespass, user_acheteur):
    """
    Rétrocompatibilité : un Membership peut toujours être créé sans FK commande.
    Garantit qu'on ne casse pas le flow adhésion directe existant.
    / Backward compat: a Membership can still be created without the commande FK.
    Ensures we don't break the existing direct membership flow.
    """
    from BaseBillet.models import Membership

    membership = Membership.objects.create(
        user=user_acheteur,
        first_name="Daisy",
        last_name="Ellis",
    )
    assert membership.commande is None


@pytest.mark.django_db(transaction=True)
def test_commande_agrege_reservations_et_memberships(tenant_context_lespass, user_acheteur):
    """
    Les relations FK inverses commande.reservations et
    commande.memberships_commande exposent bien les items liés.
    / Reverse FK relations commande.reservations and
    commande.memberships_commande correctly expose linked items.
    """
    from BaseBillet.models import Commande, Event, Membership, Reservation

    commande = Commande.objects.create(
        user=user_acheteur,
        email_acheteur=user_acheteur.email,
        first_name="Eve",
        last_name="Faure",
        status=Commande.PENDING,
    )

    event_a = Event.objects.create(
        name=f"Event A {uuid_lib.uuid4()}",
        datetime=timezone.now() + timedelta(days=3),
    )
    event_b = Event.objects.create(
        name=f"Event B {uuid_lib.uuid4()}",
        datetime=timezone.now() + timedelta(days=5),
    )
    resa_a = Reservation.objects.create(
        user_commande=user_acheteur, event=event_a, commande=commande,
    )
    resa_b = Reservation.objects.create(
        user_commande=user_acheteur, event=event_b, commande=commande,
    )
    membership = Membership.objects.create(
        user=user_acheteur,
        first_name="Eve",
        last_name="Faure",
        commande=commande,
    )

    # Agrégation via les FK inverses / Aggregation via reverse FKs
    assert commande.reservations.count() == 2
    assert set(commande.reservations.all()) == {resa_a, resa_b}
    assert commande.memberships_commande.count() == 1
    assert commande.memberships_commande.first() == membership


@pytest.mark.django_db(transaction=True)
def test_commande_paiement_stripe_one_to_one(tenant_context_lespass, user_acheteur):
    """
    Le OneToOne commande.paiement_stripe fonctionne dans les deux sens :
    - commande.paiement_stripe (forward)
    - paiement_stripe.commande_obj (reverse)
    / The OneToOne commande.paiement_stripe works both ways:
    - commande.paiement_stripe (forward)
    - paiement_stripe.commande_obj (reverse)
    """
    from BaseBillet.models import Commande, Paiement_stripe

    paiement = Paiement_stripe.objects.create(
        user=user_acheteur,
        source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PENDING,
    )
    commande = Commande.objects.create(
        user=user_acheteur,
        email_acheteur=user_acheteur.email,
        first_name="Fred",
        last_name="Gomez",
        paiement_stripe=paiement,
    )
    # Forward
    assert commande.paiement_stripe == paiement
    # Reverse
    paiement.refresh_from_db()
    assert paiement.commande_obj == commande


@pytest.mark.django_db(transaction=True)
def test_commande_paiement_stripe_unique(tenant_context_lespass, user_acheteur):
    """
    Un Paiement_stripe ne peut être associé qu'à UNE SEULE Commande.
    Contrainte OneToOne → IntegrityError si on tente d'en créer 2.
    / A Paiement_stripe can only be linked to ONE Commande.
    OneToOne constraint → IntegrityError if we try to create 2.
    """
    from BaseBillet.models import Commande, Paiement_stripe

    paiement = Paiement_stripe.objects.create(
        user=user_acheteur,
        source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PENDING,
    )
    Commande.objects.create(
        user=user_acheteur,
        email_acheteur=user_acheteur.email,
        first_name="Greg",
        last_name="Hubert",
        paiement_stripe=paiement,
    )
    # Tentative de création d'une 2e Commande avec le même paiement
    # / Attempt to create a 2nd Commande with the same payment
    with pytest.raises(IntegrityError):
        Commande.objects.create(
            user=user_acheteur,
            email_acheteur=user_acheteur.email,
            first_name="Héloïse",
            last_name="Ibanez",
            paiement_stripe=paiement,
        )


@pytest.mark.django_db(transaction=True)
def test_commande_paiement_stripe_nullable(tenant_context_lespass, user_acheteur):
    """
    Une Commande sans paiement_stripe est valide (cas gratuit 0€).
    Plusieurs commandes peuvent avoir paiement_stripe=None simultanément.
    / A Commande without paiement_stripe is valid (free case 0€).
    Multiple commandes can have paiement_stripe=None at the same time.
    """
    from BaseBillet.models import Commande

    c1 = Commande.objects.create(
        user=user_acheteur,
        email_acheteur=user_acheteur.email,
        first_name="Ismaël",
        last_name="Jouve",
    )
    c2 = Commande.objects.create(
        user=user_acheteur,
        email_acheteur=user_acheteur.email,
        first_name="Ismaël",
        last_name="Jouve",
    )
    # Pas d'IntegrityError car OneToOne nullable accepte plusieurs NULL
    # / No IntegrityError because nullable OneToOne allows multiple NULLs
    assert c1.paiement_stripe is None
    assert c2.paiement_stripe is None


@pytest.mark.django_db(transaction=True)
def test_commande_ordering_par_created_at_desc(tenant_context_lespass, user_acheteur):
    """
    L'ordering par défaut est -created_at (plus récentes en premier).
    / Default ordering is -created_at (most recent first).
    """
    from BaseBillet.models import Commande

    c1 = Commande.objects.create(
        user=user_acheteur, email_acheteur="a@a.fr",
        first_name="A", last_name="A",
    )
    c2 = Commande.objects.create(
        user=user_acheteur, email_acheteur="b@b.fr",
        first_name="B", last_name="B",
    )
    # On récupère les commandes de ce user dans l'ordre par défaut
    # / Retrieve this user's orders in default order
    commandes = list(Commande.objects.filter(user=user_acheteur))
    # Tri -created_at : c2 d'abord (plus récent), puis c1
    # Sorted by -created_at: c2 first (most recent), then c1
    assert commandes[0] == c2
    assert commandes[1] == c1


@pytest.mark.django_db(transaction=True)
def test_commande_total_lignes_agrege_reservations_et_memberships(
    tenant_context_lespass, user_acheteur
):
    """
    total_lignes() somme les amounts (centimes) de toutes les LigneArticle
    rattachées via reservations OU memberships.
    / total_lignes() sums amounts (cents) of all LigneArticle linked via
    reservations OR memberships.
    """
    from BaseBillet.models import (
        Commande, Event, LigneArticle, Membership,
        PaymentMethod, Price, PriceSold, Product, ProductSold, Reservation,
    )
    from ApiBillet.serializers import get_or_create_price_sold

    # Setup commande / Commande setup
    commande = Commande.objects.create(
        user=user_acheteur, email_acheteur="k@k.fr",
        first_name="K", last_name="K", status=Commande.PENDING,
    )

    # Event + Product + Price + Reservation + LigneArticle (billet)
    event = Event.objects.create(
        name=f"Total Event {uuid_lib.uuid4()}",
        datetime=timezone.now() + timedelta(days=2),
    )
    product_billet = Product.objects.create(
        name=f"Billet {uuid_lib.uuid4()}",
        categorie_article=Product.BILLET,
    )
    event.products.add(product_billet)
    price_billet = Price.objects.create(
        product=product_billet, name="Plein", prix=Decimal("10.00"), publish=True,
    )
    resa = Reservation.objects.create(
        user_commande=user_acheteur, event=event, commande=commande,
    )
    pricesold_billet = get_or_create_price_sold(price_billet, event=event)
    LigneArticle.objects.create(
        pricesold=pricesold_billet, amount=1000, qty=2,  # 2 × 10€ = 20€
        payment_method=PaymentMethod.STRIPE_NOFED,
        reservation=resa,
    )

    # Membership + LigneArticle (adhésion)
    product_adhesion = Product.objects.create(
        name=f"Adhésion {uuid_lib.uuid4()}",
        categorie_article=Product.ADHESION,
    )
    price_adhesion = Price.objects.create(
        product=product_adhesion, name="Standard", prix=Decimal("15.00"), publish=True,
    )
    membership = Membership.objects.create(
        user=user_acheteur,
        price=price_adhesion,
        first_name="K", last_name="K",
        contribution_value=Decimal("15.00"),
        commande=commande,
    )
    pricesold_adh = get_or_create_price_sold(price_adhesion)
    LigneArticle.objects.create(
        pricesold=pricesold_adh, amount=1500, qty=1,  # 1 × 15€ = 15€
        payment_method=PaymentMethod.STRIPE_NOFED,
        membership=membership,
    )

    # Total attendu : 2×1000 + 1×1500 = 3500 centimes (35€)
    # / Expected total: 2×1000 + 1×1500 = 3500 cents (35€)
    assert commande.total_lignes() == 3500


@pytest.mark.django_db(transaction=True)
def test_commande_promo_code_on_delete_set_null(tenant_context_lespass, user_acheteur):
    """
    Si le PromotionalCode est supprimé, la Commande reste mais son
    promo_code passe à NULL (on_delete=SET_NULL).
    / If the PromotionalCode is deleted, the Commande remains but its
    promo_code becomes NULL (on_delete=SET_NULL).
    """
    from BaseBillet.models import Commande, Product, PromotionalCode

    product = Product.objects.create(
        name=f"ProdPromo {uuid_lib.uuid4()}",
        categorie_article=Product.BILLET,
    )
    promo = PromotionalCode.objects.create(
        name=f"TEST-{uuid_lib.uuid4().hex[:8]}",
        discount_rate=Decimal("10.00"),
        product=product,
    )
    commande = Commande.objects.create(
        user=user_acheteur, email_acheteur="l@l.fr",
        first_name="L", last_name="L",
        promo_code=promo,
    )
    assert commande.promo_code == promo

    promo.delete()
    commande.refresh_from_db()
    assert commande.promo_code is None


@pytest.mark.django_db(transaction=True)
def test_commande_on_delete_protect_sur_user(tenant_context_lespass, user_acheteur):
    """
    Un utilisateur ne peut pas être supprimé s'il a des commandes
    (on_delete=PROTECT). Garantie d'intégrité historique.
    / A user cannot be deleted if they have orders (on_delete=PROTECT).
    Historical integrity guarantee.
    """
    from django.db.models.deletion import ProtectedError
    from BaseBillet.models import Commande

    Commande.objects.create(
        user=user_acheteur, email_acheteur="m@m.fr",
        first_name="M", last_name="M",
    )
    with pytest.raises(ProtectedError):
        user_acheteur.delete()
```

- [ ] **Étape 2 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_commande_model.py -v
```

Attendu : les 12 tests passent tous (`12 passed in X.XXs`).

Si un test échoue :
- Lire le traceback complet — il indique si c'est un problème de modèle, de migration, ou de setup fixture.
- Revérifier que la migration est bien appliquée : `docker exec lespass_django poetry run python /DjangoFiles/manage.py showmigrations BaseBillet | tail -3`
- Pour le test `total_lignes()` : vérifier que `ApiBillet.serializers.get_or_create_price_sold` existe et a la signature attendue.

- [ ] **Étape 3 : Lancer la suite complète de tests pytest pour vérifier la non-régression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q --ignore=tests/pytest/test_commande_model.py -x
```

On **exclut** le fichier fraîchement créé (déjà validé ci-dessus) et on lance le reste de la suite avec `-x` (arrêt au premier échec). L'objectif : s'assurer qu'aucun test existant n'est cassé par l'ajout des FK nullable.

Attendu : tous les tests existants passent. Aucune régression sur les flows `Reservation` et `Membership` existants.

En cas d'échec sur un test pré-existant : vérifier que c'est bien dû à un changement qu'on a introduit (et non un test flaky). Si c'est notre faute → investiguer le champ qui manque ou la FK qui casse quelque chose d'implicite. Si c'est flaky → consigner dans `tests/PIEGES.md` et relancer.

**Point de contrôle commit** — le livrable de la Session 01 est complet. Le mainteneur peut commit :
```
feat(panier): Session 01 — modèle Commande + FK nullable sur Reservation/Membership

- Nouveau modèle Commande dans BaseBillet/models.py
  - FK user (PROTECT), email/first_name/last_name acheteur
  - 5 statuts : DRAFT, PENDING, PAID, CANCELED, EXPIRED
  - OneToOne paiement_stripe nullable (cas gratuit + commande DRAFT)
  - FK promo_code nullable (SET_NULL)
  - Méthode total_lignes() qui agrège reservations + memberships
- FK `commande` nullable sur Reservation (SET_NULL)
- FK `commande` nullable sur Membership (SET_NULL, related_name='memberships_commande')
- Migration BaseBillet/migrations/0213_commande_and_fks.py appliquée
- 12 tests pytest dans tests/pytest/test_commande_model.py
- Zéro régression : les flows directs existants continuent avec commande=None
```

---

## Tâche 1.6 : Vérifications finales (non-régression globale)

**Fichiers :** aucun — vérifications uniquement.

**Contexte :** Dernière passe pour valider l'état du dépôt avant de passer à la Session 02.

- [ ] **Étape 1 : `manage.py check` global**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues (0 silenced).`

- [ ] **Étape 2 : Vérifier que les migrations sont à jour**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --dry-run
```

Attendu : `No changes detected` — sinon c'est qu'on a oublié de générer une migration pour un champ. Corriger avant de clore.

- [ ] **Étape 3 : Lancer toute la suite pytest**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

Attendu : 100% des tests passent (ou consigner les flaky connus dans `tests/PIEGES.md` et documenter).

- [ ] **Étape 4 : Smoke test manuel — shell Django**

```bash
docker exec -it lespass_django poetry run python /DjangoFiles/manage.py tenant_command shell --schema=lespass
```

Dans le shell :
```python
from BaseBillet.models import Commande, Reservation, Membership
# Introspection
print(Commande._meta.get_fields())
# Vérifier les relations
print([f.name for f in Reservation._meta.get_fields() if f.name == 'commande'])
print([f.name for f in Membership._meta.get_fields() if f.name == 'commande'])
# Compte actuel
print('Commandes en DB:', Commande.objects.count())
```

Attendu : les champs sont listés, aucune erreur, `0` commandes en DB (aucune créée en dehors des tests qui nettoient derrière eux).

- [ ] **Étape 5 : Mettre à jour `PLAN_LESPASS.md` pour marquer Session 01 ✅**

Éditer `TECH DOC/SESSIONS/LESPASS/PLAN_LESPASS.md` : ajouter une section ou un statut pour le chantier panier si pertinent. Le mainteneur décide du format exact ; si rien n'est prévu, laisser tel quel.

**Session 01 — terminée.** Prêt à enchaîner sur la Session 02 (`PanierSession` + `CommandeService.materialiser`).

---

## Récap des fichiers touchés

| Action | Fichier |
|---|---|
| Modifier | `BaseBillet/models.py` (ajout classe `Commande` + 2 FK) |
| Créer | `BaseBillet/migrations/0213_commande_and_fks.py` (auto-généré) |
| Créer | `tests/pytest/test_commande_model.py` |

## Récap des tests ajoutés

1. `test_commande_creation_minimale`
2. `test_commande_uuid_8_raccourci`
3. `test_commande_tous_les_statuts_acceptes`
4. `test_reservation_peut_etre_creee_sans_commande` (non-régression)
5. `test_membership_peut_etre_cree_sans_commande` (non-régression)
6. `test_commande_agrege_reservations_et_memberships`
7. `test_commande_paiement_stripe_one_to_one`
8. `test_commande_paiement_stripe_unique` (contrainte unicité)
9. `test_commande_paiement_stripe_nullable`
10. `test_commande_ordering_par_created_at_desc`
11. `test_commande_total_lignes_agrege_reservations_et_memberships`
12. `test_commande_promo_code_on_delete_set_null`
13. `test_commande_on_delete_protect_sur_user`

## Critères de Done Session 01

- [x] Modèle `Commande` en DB (migration appliquée sur tous les tenants)
- [x] FK `commande` nullable sur `Reservation`
- [x] FK `commande` nullable sur `Membership`
- [x] `manage.py check` : 0 erreur
- [x] `makemigrations --dry-run` : `No changes detected`
- [x] 13 tests pytest passent (12 nouveaux + non-régression globale)
- [x] Aucun test existant cassé
- [x] Spec de référence à jour : `2026-04-17-panier-multi-events-design.md`
