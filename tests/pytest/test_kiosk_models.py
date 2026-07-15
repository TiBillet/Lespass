"""
tests/pytest/test_kiosk_models.py — Le lecteur de carte bancaire et les paiements TPE.
tests/pytest/test_kiosk_models.py — The card reader and card payments.

CE QUE CES TESTS PROTEGENT :

Le lecteur de carte (TPEBancaire) est un OBJET, pas un reglage du terminal. Il se DEPLACE
d'un appareil a l'autre — et c'est ce qui rend deux choses delicates :

1. Un paiement appartient a la BORNE, jamais au lecteur. Sinon, debrancher un lecteur en
   pleine transaction ferait perdre a la borne la propriete de son propre paiement.
2. Annuler un paiement doit viser le lecteur sur lequel il est REELLEMENT parti — pas celui
   actuellement branche, qui peut etre en train de servir un autre client.

Lancement / Run:
    docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_kiosk_models.py -v
"""

import pytest
from django_tenants.utils import tenant_context
from unittest.mock import patch

from Customers.models import Client
from kiosk.models import PaymentsIntent
from laboutik.models import StripeLocation, Terminal, TPEBancaire


@pytest.fixture
def tenant():
    return Client.objects.get(schema_name="lespass")


@pytest.fixture
def clean_kiosk(tenant):
    """Nettoie les objets de test avant ET apres (base de dev partagee).
    Ordre : PaymentsIntent -> TPEBancaire -> Terminal -> StripeLocation (FK PROTECT)."""
    def _clean():
        with tenant_context(tenant):
            PaymentsIntent.objects.filter(terminal__name__startswith="TEST_").delete()
            TPEBancaire.objects.filter(name__startswith="TEST_").delete()
            Terminal.objects.filter(name__startswith="TEST_").delete()
            StripeLocation.objects.filter(name__startswith="TEST_").delete()
    _clean()
    yield
    _clean()


def _creer_une_borne_avec_son_lecteur(nom_de_la_borne, stripe_id="tmr_fake123"):
    """
    Une borne et son lecteur branche dessus. A appeler DANS un tenant_context.
    / A kiosk and its plugged-in reader. Call INSIDE a tenant_context.
    """
    borne = Terminal.objects.create(name=nom_de_la_borne, terminal_role="KI")
    lecteur = TPEBancaire.objects.create(
        name=f"{nom_de_la_borne} — lecteur",
        terminal=borne,
        stripe_id=stripe_id,
        registration_code="simulated-wpe",
    )
    return borne, lecteur


# --- Le modele ---


@pytest.mark.django_db
def test_stripe_location_creation(tenant, clean_kiosk):
    """Une StripeLocation se cree. / A StripeLocation is created."""
    with tenant_context(tenant):
        loc = StripeLocation.objects.create(
            name="TEST_loc", stripe_id="tml_fake123", is_primary_location=False,
        )
        assert loc.stripe_id == "tml_fake123"
        assert str(loc) == "TEST_loc"


@pytest.mark.django_db
def test_un_terminal_n_a_pas_de_lecteur_par_defaut(tenant, clean_kiosk):
    """
    Un appareil n'a PAS de lecteur de carte par defaut : le cas courant est une caisse qui
    imprime. Le lecteur est un objet qu'on lui branche.
    / A device has NO card reader by default.
    """
    with tenant_context(tenant):
        caisse = Terminal.objects.create(name="TEST_Caisse1")
        assert caisse.a_un_tpe() is False
        assert caisse.printer is None
        assert caisse.term_user is None  # le compte est pose a l'appairage


@pytest.mark.django_db
def test_brancher_un_lecteur_sur_un_terminal(tenant, clean_kiosk):
    """
    On branche un lecteur sur un appareil. C'est LE LECTEUR qui designe l'appareil — parce
    que c'est le lecteur qu'on deplace physiquement.
    / The READER points at the device, because the reader is what moves.
    """
    with tenant_context(tenant):
        borne, lecteur = _creer_une_borne_avec_son_lecteur("TEST_Borne1")

        assert lecteur.terminal == borne
        assert lecteur.tpe_type == TPEBancaire.STRIPE_WISEPOS

        # Depuis l'appareil, on retrouve son lecteur par la relation inverse.
        # / From the device, the reader is found via the reverse relation.
        borne.refresh_from_db()
        assert borne.a_un_tpe() is True
        assert borne.tpe == lecteur


@pytest.mark.django_db
def test_deplacer_un_lecteur_d_un_appareil_a_l_autre(tenant, clean_kiosk):
    """
    C'EST LA RAISON D'ETRE DU MODELE : un lecteur se debranche d'une caisse et se rebranche
    sur une borne. Une seule edition, sur l'objet qu'on a en main.
    / THE reason this model exists: a reader unplugs from one device and plugs into another.
    """
    with tenant_context(tenant):
        caisse, lecteur = _creer_une_borne_avec_son_lecteur("TEST_Caisse")
        borne = Terminal.objects.create(name="TEST_Borne", terminal_role="KI")

        # On deplace le lecteur.
        # / Move the reader.
        lecteur.terminal = borne
        lecteur.save(update_fields=["terminal"])

        caisse.refresh_from_db()
        borne.refresh_from_db()

        assert caisse.a_un_tpe() is False   # la caisse n'a plus de lecteur
        assert borne.a_un_tpe() is True     # la borne en a un
        assert borne.tpe == lecteur


@pytest.mark.django_db
def test_un_lecteur_ne_se_branche_que_sur_un_seul_appareil(tenant, clean_kiosk):
    """
    Un appareil ne peut pas avoir deux lecteurs.
    Sinon un client verrait s'afficher, sur le lecteur devant lui, le montant de la vente
    d'a cote — et pourrait la payer.
    / A device cannot have two readers.

    La contrainte est portee par la BASE (OneToOneField). On la verifie ici a travers la
    validation du modele, plutot qu'en provoquant l'IntegrityError : une erreur d'integrite
    avorte la transaction du test et empeche le nettoyage.
    / The constraint is enforced by the DB. We check it through model validation rather than
    triggering an IntegrityError, which would abort the test transaction.
    """
    from django.core.exceptions import ValidationError

    with tenant_context(tenant):
        borne, _premier_lecteur = _creer_une_borne_avec_son_lecteur("TEST_Borne")

        second_lecteur = TPEBancaire(
            name="TEST_SecondLecteur",
            terminal=borne,          # deja pris
            stripe_id="tmr_autre",
        )

        with pytest.raises(ValidationError):
            second_lecteur.full_clean()


@pytest.mark.django_db
def test_enregistrement_du_lecteur_chez_stripe(tenant, clean_kiosk):
    """
    appairer_chez_stripe() enregistre le lecteur et retient son identifiant.
    / appairer_chez_stripe() registers the reader and keeps its id.
    """
    with tenant_context(tenant):
        lecteur = TPEBancaire.objects.create(
            name="TEST_LecteurNeuf",
            registration_code="simulated-wpe",
        )
        assert lecteur.est_appaire_chez_stripe() is False

        with patch("laboutik.models.StripeLocation.get_primary_location") as mock_loc, \
             patch("stripe.terminal.Reader.create") as mock_create, \
             patch("root_billet.models.RootConfiguration.get_solo") as mock_root:
            mock_loc.return_value = type("L", (), {"stripe_id": "tml_fake"})()
            mock_root.return_value.get_stripe_api.return_value = "sk_test_x"
            mock_create.return_value = type("R", (), {"id": "tmr_ok789"})()

            stripe_id = lecteur.appairer_chez_stripe()

        assert stripe_id == "tmr_ok789"
        assert lecteur.stripe_id == "tmr_ok789"
        assert lecteur.est_appaire_chez_stripe() is True


# --- Les paiements ---


@pytest.mark.django_db
def test_payments_intent_send_to_terminal(tenant, clean_kiosk):
    """
    send_to_terminal cree le PaymentIntent chez Stripe, l'envoie au lecteur branche sur la
    borne, et passe IN_PROGRESS. Stripe est mocke (aucun appel reseau).
    / send_to_terminal creates the Stripe PaymentIntent and pushes it to the plugged reader.
    """
    with tenant_context(tenant):
        borne, lecteur = _creer_une_borne_avec_son_lecteur("TEST_BorneTPE")
        paiement = PaymentsIntent.objects.create(amount=500, terminal=borne)
        assert paiement.status == PaymentsIntent.REQUIRES_PAYMENT_METHOD

        with patch("root_billet.models.RootConfiguration.get_solo") as mock_root, \
             patch("stripe.terminal.Reader.retrieve") as mock_retrieve, \
             patch("stripe.PaymentIntent.create") as mock_pi_create, \
             patch("stripe.terminal.Reader.process_payment_intent") as mock_process:
            mock_root.return_value.get_stripe_api.return_value = "sk_test_x"
            mock_retrieve.return_value = type("R", (), {"status": "online"})()
            mock_pi_create.return_value = type("PI", (), {"id": "pi_fake123"})()

            paiement.send_to_terminal(borne)

        paiement.refresh_from_db()
        assert paiement.status == PaymentsIntent.IN_PROGRESS
        assert paiement.payment_intent_stripe_id == "pi_fake123"

        # Le paiement est parti sur le lecteur branche sur CETTE borne.
        # / The payment went to the reader plugged into THIS kiosk.
        mock_process.assert_called_once()
        assert mock_process.call_args[0][0] == lecteur.stripe_id


@pytest.mark.django_db
def test_le_paiement_retient_sur_quel_lecteur_il_est_parti(tenant, clean_kiosk):
    """
    LE PIEGE QUE CE CHAMP EVITE :
    un lecteur se deplace. Si on annulait un paiement en relisant le lecteur ACTUELLEMENT
    branche sur la borne, on couperait le paiement d'un AUTRE client — celui qui est en
    train de payer sur ce lecteur, ailleurs.
    / Readers move. Cancelling by re-reading the kiosk's current reader would kill another
    customer's payment.
    """
    with tenant_context(tenant):
        borne, lecteur = _creer_une_borne_avec_son_lecteur(
            "TEST_BorneDeplacement", stripe_id="tmr_origine",
        )
        paiement = PaymentsIntent.objects.create(amount=500, terminal=borne)

        with patch("root_billet.models.RootConfiguration.get_solo") as mock_root, \
             patch("stripe.terminal.Reader.retrieve"), \
             patch("stripe.PaymentIntent.create") as mock_pi_create, \
             patch("stripe.terminal.Reader.process_payment_intent"):
            mock_root.return_value.get_stripe_api.return_value = "sk_test_x"
            mock_pi_create.return_value = type("PI", (), {"id": "pi_fake123"})()

            paiement.send_to_terminal(borne)

        paiement.refresh_from_db()
        assert paiement.reader_stripe_id == "tmr_origine"

        # On debranche le lecteur et on le met ailleurs, pendant que le paiement court.
        # / The reader is unplugged and moved, while the payment is still running.
        autre_borne = Terminal.objects.create(name="TEST_AutreBorne", terminal_role="KI")
        lecteur.terminal = autre_borne
        lecteur.save(update_fields=["terminal"])

        # L'annulation vise le lecteur d'ORIGINE, pas celui branche aujourd'hui.
        # / The cancel targets the ORIGINAL reader.
        with patch("root_billet.models.RootConfiguration.get_solo") as mock_root, \
             patch("stripe.terminal.Reader.cancel_action") as mock_cancel, \
             patch("stripe.PaymentIntent.cancel"), \
             patch("stripe.PaymentIntent.retrieve") as mock_retrieve_pi:
            mock_root.return_value.get_stripe_api.return_value = "sk_test_x"
            mock_retrieve_pi.return_value = type("PI", (), {"status": "canceled"})()

            paiement.annuler_sur_le_terminal()

        mock_cancel.assert_called_once_with("tmr_origine")

        # Et le paiement appartient TOUJOURS a sa borne d'origine : debrancher un cable ne
        # change pas le proprietaire d'une transaction.
        # / And the payment STILL belongs to its original kiosk.
        paiement.refresh_from_db()
        assert paiement.terminal == borne


@pytest.mark.django_db
def test_envoyer_un_paiement_sans_lecteur_est_refuse(tenant, clean_kiosk):
    """
    Une borne sans lecteur ne peut rien encaisser. On le dit clairement, plutot que de
    laisser Stripe renvoyer une erreur incomprehensible.
    / A kiosk with no reader cannot take payments. Say it clearly.
    """
    with tenant_context(tenant):
        borne_sans_lecteur = Terminal.objects.create(
            name="TEST_BorneSansLecteur", terminal_role="KI",
        )
        paiement = PaymentsIntent.objects.create(amount=500, terminal=borne_sans_lecteur)

        with pytest.raises(ValueError):
            paiement.send_to_terminal(borne_sans_lecteur)


# --- Le formulaire d'admin ---


@pytest.mark.django_db
def test_le_formulaire_refuse_un_code_que_stripe_rejette(tenant, clean_kiosk):
    """
    Un code d'enregistrement refuse par Stripe invalide le formulaire : l'erreur s'affiche
    sous le champ, et AUCUN lecteur n'est cree. Sans ca, on garderait en base un lecteur
    orphelin, sans identifiant Stripe, incapable d'encaisser.
    / A code rejected by Stripe invalidates the form; NO reader is created.
    """
    from Administration.admin.laboutik import TPEBancaireForm

    with tenant_context(tenant):
        with patch("laboutik.models.StripeLocation.get_primary_location") as mock_loc, \
             patch("root_billet.models.RootConfiguration.get_solo") as mock_root, \
             patch("stripe.terminal.Reader.create") as mock_create:
            mock_loc.return_value = type("L", (), {"stripe_id": "tml_fake"})()
            mock_root.return_value.get_stripe_api.return_value = "sk_test_x"
            mock_create.side_effect = Exception("No such registration code")

            form = TPEBancaireForm(data={
                "name": "TEST_LecteurRefuse",
                "tpe_type": TPEBancaire.STRIPE_WISEPOS,
                "registration_code": "code-bidon",
                "active": True,
            })
            assert form.is_valid() is False

        assert "registration_code" in form.errors
        assert TPEBancaire.objects.filter(name="TEST_LecteurRefuse").exists() is False


@pytest.mark.django_db
def test_le_formulaire_enregistre_le_lecteur_chez_stripe(tenant, clean_kiosk):
    """
    Un code accepte par Stripe rend le formulaire valide, et l'identifiant du lecteur est
    conserve.
    / A code accepted by Stripe makes the form valid, and the reader's id is persisted.
    """
    from Administration.admin.laboutik import TPEBancaireForm

    with tenant_context(tenant):
        with patch("laboutik.models.StripeLocation.get_primary_location") as mock_loc, \
             patch("root_billet.models.RootConfiguration.get_solo") as mock_root, \
             patch("stripe.terminal.Reader.create") as mock_create:
            mock_loc.return_value = type("L", (), {"stripe_id": "tml_fake"})()
            mock_root.return_value.get_stripe_api.return_value = "sk_test_x"
            mock_create.return_value = type("R", (), {"id": "tmr_ok456"})()

            form = TPEBancaireForm(data={
                "name": "TEST_LecteurAccepte",
                "tpe_type": TPEBancaire.STRIPE_WISEPOS,
                "registration_code": "simulated-wpe",
                "active": True,
            })
            assert form.is_valid() is True, form.errors
            lecteur = form.save()

        assert lecteur.stripe_id == "tmr_ok456"
        assert TPEBancaire.objects.get(name="TEST_LecteurAccepte").stripe_id == "tmr_ok456"


@pytest.mark.django_db
def test_le_meme_lecteur_physique_ne_s_enregistre_pas_deux_fois(tenant, clean_kiosk):
    """
    Deux fiches ne peuvent pas porter le meme code d'enregistrement : ce serait le meme
    lecteur physique, decrit deux fois — et deux caisses croiraient le piloter.
    / Two records cannot share a registration code: it would be the same physical reader.
    """
    from Administration.admin.laboutik import TPEBancaireForm

    with tenant_context(tenant):
        TPEBancaire.objects.create(
            name="TEST_LecteurPremier",
            registration_code="lecteur-deja-pris",
            stripe_id="tmr_deja_pris",
        )

        form = TPEBancaireForm(data={
            "name": "TEST_LecteurSecond",
            "tpe_type": TPEBancaire.STRIPE_WISEPOS,
            "registration_code": "lecteur-deja-pris",
            "active": True,
        })

        assert form.is_valid() is False
        assert "registration_code" in form.errors
        assert TPEBancaire.objects.filter(name="TEST_LecteurSecond").exists() is False
