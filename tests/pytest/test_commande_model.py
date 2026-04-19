"""
Tests unitaires du modèle Commande et de ses relations.
/ Unit tests for the Commande model and its relations.

Scope Session 01 : modèles uniquement, pas de service ni de vue.
/ Session 01 scope: models only, no service or view.

Run:
    poetry run pytest -q tests/pytest/test_commande_model.py
"""
import time
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
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
    / Test user for orders.

    Teardown : on supprime d'abord les objets qui référencent le user
    (Commande avec on_delete=PROTECT), puis le user.
    / Teardown: we first delete objects referencing the user
    (Commande with on_delete=PROTECT), then the user.
    """
    from AuthBillet.models import TibilletUser
    email = f"acheteur-{uuid.uuid4()}@example.org"
    user = TibilletUser.objects.create(
        email=email,
        username=email,
    )
    yield user
    # Nettoyage après le test : ordre important à cause des FK PROTECT.
    # / Cleanup after test: order matters because of PROTECT FKs.
    from BaseBillet.models import (
        Commande, LigneArticle, Membership, Paiement_stripe, Reservation,
    )
    # LigneArticle.membership / LigneArticle.reservation : PROTECT → supprimer d'abord
    # / LigneArticle.membership / LigneArticle.reservation: PROTECT → delete first
    LigneArticle.objects.filter(
        membership__user=user,
    ).delete()
    LigneArticle.objects.filter(
        reservation__user_commande=user,
    ).delete()
    # Membership.user : SET_NULL, mais on supprime les Memberships pour ne pas
    # laisser de donnees orphelines liees a ce test.
    # / Membership.user is SET_NULL, but we delete Memberships to avoid leaving
    # test-specific orphan data.
    Membership.objects.filter(user=user).delete()
    # Reservation.user_commande : on libère
    # / Reservation.user_commande: release
    Reservation.objects.filter(user_commande=user).delete()
    # Commande.user : PROTECT → supprimer avant le user
    # / Commande.user: PROTECT → delete before the user
    Commande.objects.filter(user=user).delete()
    # Paiement_stripe.user : PROTECT → supprimer avant le user
    # / Paiement_stripe.user: PROTECT → delete before the user
    Paiement_stripe.objects.filter(user=user).delete()
    user.delete()


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_reservation_peut_etre_creee_sans_commande(tenant_context_lespass, user_acheteur):
    """
    Rétrocompatibilité : une Reservation peut toujours être créée sans FK commande.
    Garantit qu'on ne casse pas le flow mono-event existant.
    / Backward compat: a Reservation can still be created without the commande FK.
    Ensures we don't break the existing mono-event flow.
    """
    from BaseBillet.models import Event, Reservation

    event = Event.objects.create(
        name=f"Test Event {uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=7),
    )
    reservation = Reservation.objects.create(
        user_commande=user_acheteur,
        event=event,
    )
    assert reservation.commande is None
    assert reservation.event == event


@pytest.mark.django_db
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


@pytest.mark.django_db
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
        name=f"Event A {uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=3),
    )
    event_b = Event.objects.create(
        name=f"Event B {uuid.uuid4()}",
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


@pytest.mark.django_db
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


@pytest.mark.django_db
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
    # Tentative de création d'une 2e Commande avec le même paiement.
    # On wrappe dans atomic() pour isoler l'IntegrityError attendue et ne pas
    # casser la transaction externe (teardown fixture).
    # / Attempt to create a 2nd Commande with the same payment.
    # We wrap in atomic() to isolate the expected IntegrityError and avoid
    # breaking the outer transaction (fixture teardown).
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Commande.objects.create(
                user=user_acheteur,
                email_acheteur=user_acheteur.email,
                first_name="Héloïse",
                last_name="Ibanez",
                paiement_stripe=paiement,
            )


@pytest.mark.django_db
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
    # Preuve que les deux commandes sont bien persistees, distinctes, et avec
    # paiement_stripe NULL simultanement (le OneToOne nullable l'autorise).
    # / Proof that both orders are distinct persisted rows with simultaneous
    # NULL paiement_stripe (nullable OneToOne permits it).
    assert c1.paiement_stripe is None
    assert c2.paiement_stripe is None
    assert c1.uuid != c2.uuid
    assert Commande.objects.filter(
        user=user_acheteur, paiement_stripe__isnull=True
    ).count() >= 2


@pytest.mark.django_db
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
    # Garantir un delta >= 1 ms entre les deux created_at pour stabiliser l'ordre.
    # / Ensure >= 1 ms gap between the two created_at to stabilize ordering.
    time.sleep(0.001)
    c2 = Commande.objects.create(
        user=user_acheteur, email_acheteur="b@b.fr",
        first_name="B", last_name="B",
    )
    # Tri -created_at : c2 d'abord (plus recent), puis c1.
    # / Sorted by -created_at: c2 first (most recent), then c1.
    commandes_ordered = list(Commande.objects.filter(user=user_acheteur))
    assert commandes_ordered[0] == c2
    assert commandes_ordered[1] == c1


@pytest.mark.django_db
def test_commande_promo_code_on_delete_set_null(tenant_context_lespass, user_acheteur):
    """
    Si le PromotionalCode est supprimé, la Commande reste mais son
    promo_code passe à NULL (on_delete=SET_NULL).
    / If the PromotionalCode is deleted, the Commande remains but its
    promo_code becomes NULL (on_delete=SET_NULL).
    """
    from BaseBillet.models import Commande, Product, PromotionalCode

    product = Product.objects.create(
        name=f"ProdPromo {uuid.uuid4()}",
        categorie_article=Product.BILLET,
    )
    promo = PromotionalCode.objects.create(
        name=f"TEST-{uuid.uuid4().hex[:8]}",
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


@pytest.mark.django_db
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
