"""
Test d'integration : carte NFC liee au wallet via le formulaire admin d'adhesion,
avec verification REELLE chez Fedow (pas de mock).
/ Integration test: NFC card linked to the wallet through the admin membership
form, with a REAL Fedow verification (no mock).

LOCALISATION : tests/pytest/test_membership_card_wallet_fedow.py

FLUX TESTE :
1. L'admin cree une adhesion via le formulaire admin (email + numero de carte).
2. `MembershipAddForm.clean_card_number()` verifie la carte chez Fedow
   (elle doit exister et avoir un wallet ephemere).
3. `MembershipAddForm.save()` appelle `fedowAPI.NFCcard.linkwallet_card_number()`
   qui lie la carte au wallet de l'utilisateur chez Fedow.
4. On verifie chez Fedow que le wallet de l'utilisateur a bien la carte
   (`has_user_card`) et que la carte n'est plus ephemere.
5. Nettoyage : `lost_my_card_by_signature()` detache la carte pour que le
   test soit rejouable avec le meme numero.

PREREQUIS :
- Le serveur Fedow de dev tourne (container fedow_django).
- Le tenant 'lespass' a une place Fedow signable (fedow_config) — cas par
  defaut en dev.

Le test est AUTONOME : la fixture carte_fedow_ephemere fabrique elle-meme une
carte fraiche chez Fedow (fedow_api.NFCcard.create_cards) si aucune carte
ephemere n'est disponible. Il ne skippe donc jamais et resiste a un reset
complet (down -v) qui vide la base Fedow.
FEDOW_TEST_CARD_NUMBER reste optionnel : si renseigne et que la carte est
encore ephemere, elle est reutilisee ; sinon une carte est fabriquee.
/ Self-contained: the fixture creates a fresh Fedow card (create_cards) if
needed, so it never skips and survives a full down -v. FEDOW_TEST_CARD_NUMBER
is optional (reused if still ephemeral, otherwise a card is created).
"""
import os
import uuid as uuid_module

import pytest
from django.test import override_settings
from django_tenants.utils import tenant_context


# override_settings(DEBUG=True) : pytest-django force DEBUG=False pendant
# les tests, ce qui active la verification SSL dans fedow_api
# (verify=bool(not settings.DEBUG)) — et le certificat Traefik de dev est
# auto-signe. On replique le runtime de dev (DEBUG=True → verify desactive).
# / pytest-django forces DEBUG=False in tests, which enables SSL verification
# in fedow_api — and the dev Traefik certificate is self-signed. We replicate
# the dev runtime (DEBUG=True → verify disabled).
pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture(scope="module")
def carte_fedow_ephemere(tenant):
    """Retourne le numero d'une carte Fedow ephemere (sans utilisateur).

    Le test est AUTONOME : si FEDOW_TEST_CARD_NUMBER pointe une carte ephemere
    existante, on la reutilise ; sinon on FABRIQUE une carte fraiche chez Fedow
    via create_cards. Ainsi le test ne skippe jamais et resiste a un reset
    complet (down -v) qui vide la base Fedow.
    / Self-contained: reuse FEDOW_TEST_CARD_NUMBER if it still points to an
    ephemeral card, otherwise create a fresh card on Fedow. Never skips.
    """
    import secrets

    with override_settings(DEBUG=True), tenant_context(tenant):
        from fedow_connect.fedow_api import FedowAPI
        fedow_api = FedowAPI()

        # 1) Numero fourni par l'environnement : on le reutilise s'il pointe
        # encore une carte ephemere (libre). / Reuse the env number if it
        # still points to a free (ephemeral) card.
        numero_env = os.environ.get("FEDOW_TEST_CARD_NUMBER", "").strip().upper()
        if numero_env:
            carte = fedow_api.NFCcard.card_number_retrieve(numero_env)
            if carte and carte.get("is_wallet_ephemere"):
                return numero_env

        # 2) Sinon, on fabrique une carte fraiche (numero + tag aleatoires de
        # 8 hexa) : garantie ephemere, et pas de conflit 409. / Otherwise,
        # create a fresh card (random 8-hex number + tag): guaranteed ephemeral.
        numero_carte = secrets.token_hex(4).upper()
        tag_rfid = secrets.token_hex(4).upper()
        fedow_api.NFCcard.create_cards([{
            "first_tag_id": tag_rfid,
            "complete_tag_id_uuid": str(uuid_module.uuid4()),
            "qrcode_uuid": str(uuid_module.uuid4()),
            "number_printed": numero_carte,
            "generation": 1,
            "is_primary": False,
        }])
        return numero_carte


@override_settings(DEBUG=True)
def test_carte_liee_au_wallet_via_formulaire_admin_avec_verif_fedow(
    admin_client, tenant, carte_fedow_ephemere, django_capture_on_commit_callbacks
):
    """L'adhesion creee en admin avec un numero de carte lie la carte au
    wallet de l'utilisateur — verifie chez Fedow (has_user_card + carte
    plus ephemere).
    / Membership created in admin with a card number links the card to the
    user's wallet — verified on Fedow (has_user_card + card no longer
    ephemeral).
    """
    suffixe = uuid_module.uuid4().hex[:8]
    email_adherent = f"jturbeaux+carte{suffixe}@pm.me"

    with tenant_context(tenant):
        from BaseBillet.models import Product, Price, PaymentMethod

        # --- Etape 1 : un tarif adhesion pour le formulaire ---
        # get_or_create : la DB dev est partagee, pas de rollback.
        # / get_or_create: shared dev DB, no rollback.
        produit_adhesion, _created = Product.objects.get_or_create(
            name=f"Adhesion CarteWallet {suffixe}",
            defaults={"categorie_article": Product.ADHESION},
        )
        tarif_adhesion, _created = Price.objects.get_or_create(
            product=produit_adhesion,
            name=f"Tarif CarteWallet {suffixe}",
            defaults={"prix": 10},
        )

    # --- Etape 2 : POST du formulaire admin d'ajout d'adhesion ---
    # payment_method=FREE + contribution vide : pas de paiement requis,
    # on teste uniquement le lien carte → wallet.
    # / FREE payment + empty contribution: no payment needed, we only
    # test the card → wallet link.
    # django_capture_on_commit_callbacks(execute=True) : le lien de la carte
    # est differe par transaction.on_commit (voir MembershipAddForm.save) et
    # le test tourne dans une transaction rollbackee — sans cette fixture,
    # le callback ne s'executerait jamais.
    # / The card link is deferred via transaction.on_commit and the test runs
    # in a rolled-back transaction — without this fixture the callback would
    # never run.
    with django_capture_on_commit_callbacks(execute=True):
        reponse = admin_client.post(
            "/admin/BaseBillet/membership/add/",
            data={
                "email": email_adherent,
                "first_name": "Carte",
                "last_name": "Wallet",
                "price": str(tarif_adhesion.pk),
                "contribution": "",
                "payment_method": PaymentMethod.FREE,
                "card_number": carte_fedow_ephemere,
                # ManagementForm de l'inline lignearticles (vide) — requis par
                # l'admin Django meme sans ligne saisie.
                # / Empty lignearticles inline ManagementForm — required by
                # the Django admin even with no row.
                "lignearticles-TOTAL_FORMS": "0",
                "lignearticles-INITIAL_FORMS": "0",
                "lignearticles-MIN_NUM_FORMS": "0",
                "lignearticles-MAX_NUM_FORMS": "1000",
            },
        )
    # Succes admin = redirection vers la changelist (302).
    # Un 200 signifie que le formulaire est re-affiche avec des erreurs.
    # / Admin success = redirect (302). A 200 means form errors.
    assert reponse.status_code == 302, (
        f"Le formulaire admin a echoue (HTTP {reponse.status_code}) : "
        f"{getattr(reponse, 'context_data', {}).get('errors', '')}"
    )

    with tenant_context(tenant):
        from AuthBillet.models import TibilletUser
        from BaseBillet.models import Membership
        from fedow_connect.fedow_api import FedowAPI

        # --- Etape 3 : l'adhesion et l'utilisateur existent ---
        utilisateur = TibilletUser.objects.get(email=email_adherent)
        adhesion = Membership.objects.get(user=utilisateur, price=tarif_adhesion)
        assert adhesion.status == Membership.ADMIN

        # --- Etape 4 : VERIFICATION CHEZ FEDOW (vrais appels HTTP) ---
        # Le try/finally garantit que la carte est detachee MEME si une
        # assertion echoue — sinon chaque echec consomme une carte de demo.
        # / try/finally guarantees the card is detached EVEN if an assertion
        # fails — otherwise each failure burns a demo card.
        fedow_api = FedowAPI()
        try:
            # 4a. Le wallet de l'utilisateur declare bien une carte liee.
            # retrieve_by_signature (NON cache) : le formulaire a mis le
            # wallet en cache AVANT le lien de la carte (clean_email,
            # cache 10 s) — la version cachee dirait has_user_card=False.
            # / 4a. The user's wallet does report a linked card.
            # retrieve_by_signature (NOT cached): the form cached the wallet
            # BEFORE the card link (10 s cache).
            wallet_serialise = fedow_api.wallet.retrieve_by_signature(
                utilisateur
            ).validated_data
            assert wallet_serialise.get("has_user_card") is True, (
                f"Fedow ne voit pas de carte liee au wallet de {email_adherent} : "
                f"{wallet_serialise}"
            )

            # 4b. La carte n'est plus ephemere : elle appartient a un utilisateur.
            # / 4b. The card is no longer ephemeral: it belongs to a user.
            carte_apres = fedow_api.NFCcard.card_number_retrieve(carte_fedow_ephemere)
            assert carte_apres, "La carte a disparu chez Fedow apres le lien"
            assert not carte_apres.get("is_wallet_ephemere"), (
                f"La carte {carte_fedow_ephemere} est toujours ephemere chez Fedow "
                "alors qu'elle devrait etre liee au wallet de l'utilisateur."
            )
        finally:
            # --- Etape 5 : nettoyage — on detache la carte pour rendre le
            # test rejouable avec le meme numero. Tolerant : si Fedow
            # refuse, le prochain run skipera proprement (fixture).
            # / Step 5: cleanup — detach the card so the test can be
            # replayed. Tolerant: if Fedow refuses, next run skips cleanly.
            try:
                fedow_api.NFCcard.lost_my_card_by_signature(
                    utilisateur, number_printed=carte_fedow_ephemere
                )
            except Exception as erreur_nettoyage:
                print(
                    f"Nettoyage carte impossible ({erreur_nettoyage}) — "
                    "le prochain run skipera tant que la carte reste liee."
                )


def test_create_cards_cree_une_carte_ephemere_chez_fedow(tenant):
    """create_cards() cree une carte NFC ephemere (sans utilisateur) chez Fedow,
    ensuite retrouvable par son numero imprime.
    / create_cards() creates an ephemeral NFC card on Fedow, then retrievable
    by its printed number.

    LOCALISATION : tests/pytest/test_membership_card_wallet_fedow.py

    C'est la brique qui rend le test d'integration ci-dessus autonome : la
    fixture carte_fedow_ephemere peut fabriquer sa carte si Fedow n'en a pas.
    """
    import secrets

    # Numero + tag aleatoires (8 hexa) pour ne pas entrer en conflit avec une
    # carte deja presente (l'endpoint renvoie 409 si le numero existe deja).
    # / Random number + tag (8 hex) to avoid a 409 conflict with an existing card.
    numero_imprime = secrets.token_hex(4).upper()
    tag_rfid = secrets.token_hex(4).upper()

    with override_settings(DEBUG=True), tenant_context(tenant):
        from fedow_connect.fedow_api import FedowAPI

        fedow_api = FedowAPI()
        fedow_api.NFCcard.create_cards([{
            "first_tag_id": tag_rfid,
            "complete_tag_id_uuid": str(uuid_module.uuid4()),
            "qrcode_uuid": str(uuid_module.uuid4()),
            "number_printed": numero_imprime,
            "generation": 1,
            "is_primary": False,
        }])

        carte = fedow_api.NFCcard.card_number_retrieve(numero_imprime)

    assert carte, f"La carte {numero_imprime} devrait exister chez Fedow apres create_cards"
    assert carte.get("is_wallet_ephemere") is True, (
        "Une carte fraichement creee doit etre ephemere (sans utilisateur)."
    )


# ---------------------------------------------------------------------------
# Liaison de la carte : saisie en minuscules, refus de Fedow, double envoi.
# Le formulaire d'adhesion admin est tres utilise en production. La liaison de
# la carte chez Fedow tourne APRES l'enregistrement de l'adhesion (on_commit) :
# elle ne doit jamais faire planter la page (l'admin renverrait le formulaire et
# creerait une adhesion en double), et un vrai refus doit rester une alerte.
# / Card link: lowercase input, Fedow refusal, double submit. The link runs
# AFTER the membership is saved: it must never crash the page, and a real
# refusal must stay an alert.
# ---------------------------------------------------------------------------


def _fabriquer_carte_ephemere_chez_fedow(tenant):
    """
    Cree une carte fraiche chez Fedow et renvoie son numero imprime (majuscules).
    Le numero commence par "AB" : il contient des lettres, donc sa version en
    minuscules est bien differente (utile pour tester la casse).
    / Creates a fresh Fedow card; the number always contains letters.
    """
    import secrets

    numero_carte = "AB" + secrets.token_hex(3).upper()
    with override_settings(DEBUG=True), tenant_context(tenant):
        from fedow_connect.fedow_api import FedowAPI

        FedowAPI().NFCcard.create_cards([{
            "first_tag_id": secrets.token_hex(4).upper(),
            "complete_tag_id_uuid": str(uuid_module.uuid4()),
            "qrcode_uuid": str(uuid_module.uuid4()),
            "number_printed": numero_carte,
            "generation": 1,
            "is_primary": False,
        }])
    return numero_carte


def _tarif_adhesion_de_test(tenant, suffixe):
    """Un produit adhesion + son tarif, pour le formulaire. / A membership price."""
    with tenant_context(tenant):
        from BaseBillet.models import Product, Price

        produit_adhesion, _created = Product.objects.get_or_create(
            name=f"Adhesion CarteWallet {suffixe}",
            defaults={"categorie_article": Product.ADHESION},
        )
        tarif_adhesion, _created = Price.objects.get_or_create(
            product=produit_adhesion,
            name=f"Tarif CarteWallet {suffixe}",
            defaults={"prix": 10},
        )
    return tarif_adhesion


def _poster_le_formulaire_d_adhesion(admin_client, email, tarif_adhesion, numero_saisi):
    """POST du formulaire admin d'ajout d'adhesion (gratuite). / Admin add form POST."""
    from BaseBillet.models import PaymentMethod

    return admin_client.post(
        "/admin/BaseBillet/membership/add/",
        data={
            "email": email,
            "first_name": "Carte",
            "last_name": "Wallet",
            "price": str(tarif_adhesion.pk),
            "contribution": "",
            "payment_method": PaymentMethod.FREE,
            "card_number": numero_saisi,
            "lignearticles-TOTAL_FORMS": "0",
            "lignearticles-INITIAL_FORMS": "0",
            "lignearticles-MIN_NUM_FORMS": "0",
            "lignearticles-MAX_NUM_FORMS": "1000",
        },
    )


def _membre_avec_wallet_fedow(tenant, email):
    """Un utilisateur avec son wallet Fedow, comme apres clean_email. / User + Fedow wallet."""
    with override_settings(DEBUG=True), tenant_context(tenant):
        from AuthBillet.utils import get_or_create_user
        from fedow_connect.fedow_api import FedowAPI

        utilisateur = get_or_create_user(email, send_mail=False)
        FedowAPI().wallet.get_or_create_wallet(utilisateur)
        utilisateur.refresh_from_db()
    return utilisateur


@override_settings(DEBUG=True)
def test_carte_saisie_en_minuscules_est_liee_au_wallet(
    admin_client, tenant, django_capture_on_commit_callbacks
):
    """
    Le numero de carte saisi en minuscules est lie quand meme. Fedow trouve la
    carte en majuscules a la verification ; la liaison doit envoyer le meme
    numero, sinon Fedow repond « l'objet n'existe pas ».
    / A lowercase card number is still linked (same number for check and link).
    """
    suffixe = uuid_module.uuid4().hex[:8]
    email_adherent = f"jturbeaux+cartemin{suffixe}@pm.me"
    tarif_adhesion = _tarif_adhesion_de_test(tenant, suffixe)
    numero_carte = _fabriquer_carte_ephemere_chez_fedow(tenant)
    numero_saisi_en_minuscules = numero_carte.lower()
    assert numero_saisi_en_minuscules != numero_carte

    with django_capture_on_commit_callbacks(execute=True):
        reponse = _poster_le_formulaire_d_adhesion(
            admin_client, email_adherent, tarif_adhesion, numero_saisi_en_minuscules,
        )
    assert reponse.status_code == 302, (
        f"Le formulaire admin a echoue (HTTP {reponse.status_code}) : "
        f"{getattr(reponse, 'context_data', {}).get('errors', '')}"
    )

    with tenant_context(tenant):
        from AuthBillet.models import TibilletUser
        from BaseBillet.models import Membership
        from fedow_connect.fedow_api import FedowAPI

        utilisateur = TibilletUser.objects.get(email=email_adherent)
        assert Membership.objects.filter(user=utilisateur, price=tarif_adhesion).count() == 1

        # La carte appartient maintenant au wallet de CE membre, chez Fedow.
        # / The card now belongs to THIS member's wallet, on Fedow.
        carte_chez_fedow = FedowAPI().NFCcard.card_number_retrieve(numero_carte)
        assert carte_chez_fedow, f"La carte {numero_carte} a disparu chez Fedow"
        assert not carte_chez_fedow.get("is_wallet_ephemere"), (
            f"La carte {numero_carte} saisie en minuscules n'a pas ete liee."
        )
        assert f"{carte_chez_fedow.get('wallet_uuid')}" == f"{utilisateur.wallet.uuid}"


@override_settings(DEBUG=True)
def test_refus_de_fedow_apres_enregistrement_ne_plante_pas_et_alerte(
    admin_client, tenant, django_capture_on_commit_callbacks, caplog
):
    """
    Fedow refuse la liaison APRES l'enregistrement de l'adhesion. La page ne
    plante pas (sinon l'admin renvoie le formulaire : adhesion en double),
    l'adhesion existe une seule fois, et une erreur est journalisee (alerte).
    / Fedow refuses the link after the membership is saved: no crash, one
    membership, and an error is logged.
    """
    import logging
    from unittest.mock import patch
    from fedow_connect.fedow_api import NFCcardFedow

    suffixe = uuid_module.uuid4().hex[:8]
    email_adherent = f"jturbeaux+carterefus{suffixe}@pm.me"
    tarif_adhesion = _tarif_adhesion_de_test(tenant, suffixe)
    numero_carte = _fabriquer_carte_ephemere_chez_fedow(tenant)

    refus_simule = Exception("linkwallet_card_number : 400 refus simule par le test")
    with caplog.at_level(logging.WARNING):
        with patch.object(NFCcardFedow, "linkwallet_card_number", side_effect=refus_simule):
            with django_capture_on_commit_callbacks(execute=True):
                reponse = _poster_le_formulaire_d_adhesion(
                    admin_client, email_adherent, tarif_adhesion, numero_carte,
                )

    assert reponse.status_code == 302

    with tenant_context(tenant):
        from AuthBillet.models import TibilletUser
        from BaseBillet.models import Membership
        from fedow_connect.fedow_api import FedowAPI

        utilisateur = TibilletUser.objects.get(email=email_adherent)
        assert Membership.objects.filter(user=utilisateur, price=tarif_adhesion).count() == 1

        # Le refus etait simule : la carte est toujours libre chez Fedow.
        # / The refusal was simulated: the card is still free on Fedow.
        carte_chez_fedow = FedowAPI().NFCcard.card_number_retrieve(numero_carte)
        assert carte_chez_fedow.get("is_wallet_ephemere") is True

    erreurs_journalisees = [
        record for record in caplog.records
        if record.levelno >= logging.ERROR and numero_carte in record.getMessage()
    ]
    assert erreurs_journalisees, (
        "Un vrai refus de Fedow doit rester une alerte (logger.error) : "
        "l'adhesion est enregistree sans sa carte."
    )


@override_settings(DEBUG=True)
def test_carte_deja_liee_a_ce_membre_double_envoi_simple_avertissement(tenant, caplog):
    """
    Double envoi du formulaire : la premiere requete a deja lie la carte a ce
    membre, Fedow refuse la seconde liaison. Ce n'est pas une anomalie : pas
    d'exception, pas d'erreur journalisee (pas d'alerte Sentry), un avertissement.
    / Double submit: the card is already on this member's wallet. No exception,
    no error log, only a warning.
    """
    import logging
    from Administration.admin_tenant import lier_la_carte_a_l_adherent_chez_fedow

    suffixe = uuid_module.uuid4().hex[:8]
    utilisateur = _membre_avec_wallet_fedow(tenant, f"jturbeaux+cartedouble{suffixe}@pm.me")
    numero_carte = _fabriquer_carte_ephemere_chez_fedow(tenant)

    with override_settings(DEBUG=True), tenant_context(tenant):
        from fedow_connect.fedow_api import FedowAPI

        # Premiere requete : la liaison reussit.
        # / First request: the link succeeds.
        FedowAPI().NFCcard.linkwallet_card_number(user=utilisateur, card_number=numero_carte)

        # Seconde requete : Fedow refuse, la carte n'est plus libre.
        # / Second request: Fedow refuses, the card is no longer free.
        with caplog.at_level(logging.WARNING):
            lier_la_carte_a_l_adherent_chez_fedow(FedowAPI(), utilisateur, numero_carte)

        carte_chez_fedow = FedowAPI().NFCcard.card_number_retrieve(numero_carte)
        assert f"{carte_chez_fedow.get('wallet_uuid')}" == f"{utilisateur.wallet.uuid}"

    erreurs_journalisees = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not erreurs_journalisees, (
        f"Un double envoi ne doit pas lever d'alerte : "
        f"{[r.getMessage() for r in erreurs_journalisees]}"
    )
    avertissements = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and numero_carte in r.getMessage()
    ]
    assert avertissements, "Le double envoi doit laisser une trace (warning)."


@override_settings(DEBUG=True)
def test_carte_liee_a_un_autre_membre_alerte_sans_planter(tenant, caplog):
    """
    La carte appartient deja a un AUTRE membre chez Fedow. La liaison est refusee :
    pas d'exception (l'adhesion est deja enregistree), mais une erreur journalisee,
    parce qu'une adhesion se retrouve sans sa carte.
    / The card belongs to ANOTHER member: no exception, but an error is logged.
    """
    import logging
    from Administration.admin_tenant import lier_la_carte_a_l_adherent_chez_fedow

    suffixe = uuid_module.uuid4().hex[:8]
    premier_membre = _membre_avec_wallet_fedow(tenant, f"jturbeaux+carteA{suffixe}@pm.me")
    second_membre = _membre_avec_wallet_fedow(tenant, f"jturbeaux+carteB{suffixe}@pm.me")
    numero_carte = _fabriquer_carte_ephemere_chez_fedow(tenant)

    with override_settings(DEBUG=True), tenant_context(tenant):
        from fedow_connect.fedow_api import FedowAPI

        FedowAPI().NFCcard.linkwallet_card_number(user=premier_membre, card_number=numero_carte)

        with caplog.at_level(logging.WARNING):
            lier_la_carte_a_l_adherent_chez_fedow(FedowAPI(), second_membre, numero_carte)

        # La carte reste au premier membre. / The card stays with the first member.
        carte_chez_fedow = FedowAPI().NFCcard.card_number_retrieve(numero_carte)
        assert f"{carte_chez_fedow.get('wallet_uuid')}" == f"{premier_membre.wallet.uuid}"

    erreurs_journalisees = [
        r for r in caplog.records
        if r.levelno >= logging.ERROR and numero_carte in r.getMessage()
    ]
    assert erreurs_journalisees, "Une carte liee a un autre membre doit rester une alerte."
