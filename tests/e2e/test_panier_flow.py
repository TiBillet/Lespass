"""
E2E du panier : ce que seul un navigateur peut voir.
/ Cart E2E: what only a browser can see.

LOCALISATION : tests/e2e/test_panier_flow.py

Les règles métier du panier sont testées en pytest (tests/pytest/test_panier_*.py,
test_commande_service.py, test_parite_avec_sans_panier.py). Ici, on ne vérifie que ce qui
passe par le navigateur : panneaux Bootstrap, swaps HTMX, badge, toasts SweetAlert2,
redirections, calendrier des ressources, et le vrai paiement Stripe.
/ Business rules are tested in pytest. Here: offcanvas, HTMX swaps, badge, toasts,
redirects, the resource calendar, and the real Stripe payment.

FIXTURES SEEDÉES (demo_data_v2 --e2e-only, lues par `e2e_slugs`) :
« E2E Test — Event gratuit / payant », « E2E Test — Adhesion payante / recurrente /
recompense », « E2E Test — Salle ».

ACHETEURS : chaque test crée son propre acheteur (email unique). Ses réservations et bookings
sont annulés en fin de test, par email exact, pour libérer la jauge et les créneaux
(tests/PIEGES.md, 12.4 : jamais de suppression large). L'utilisateur reste en base de dev.
/ Each test creates its own buyer; their bookings are cancelled at the end by exact email.

SKIN V2 : le badge du panier est dans `header[data-testid="user-bar"]`, pas dans une `.navbar`.
/ V2 skin: the cart badge lives in the user bar header, not in a `.navbar`.

Lancer / Run :
    make e2e ARGS="tests/e2e/test_panier_flow.py"          (E1 à E4)
    make e2e-stripe ARGS="tests/e2e/test_panier_flow.py"   (E1 à E6, vrai paiement Stripe)
"""

import re
import time
import uuid

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

SELECTEUR_DU_BADGE = '[data-testid="user-bar"] #panier-badge-nav'


# --------------------------------------------------------------------------
# Outils communs
# / Shared helpers
# --------------------------------------------------------------------------


def fixture_du_panier(e2e_slugs, cle):
    """
    Une valeur des fixtures E2E du panier (`e2e_slugs`). Si elle manque, le test échoue en
    disant quoi faire : jamais de skip silencieux.
    / A cart E2E fixture value; the test fails explicitly when it is missing.
    """
    valeur = e2e_slugs[cle]
    if valeur is None:
        pytest.fail(
            f"Fixture E2E du panier '{cle}' absente. Relancer : docker exec lespass_django "
            "poetry run python manage.py demo_data_v2 --e2e-only (la récompense exige aussi "
            "une monnaie locale du lieu)."
        )
    return valeur


def creer_un_acheteur(django_shell, avec_portefeuille_fedow=False):
    """
    Crée un acheteur actif à l'email unique, et rend cet email.
    / Creates an active buyer with a unique email, and returns that email.

    `avec_portefeuille_fedow` : crée aussi son portefeuille sur le Fedow. Une récompense
    monnaie ne peut être versée que sur un portefeuille qui existe déjà (même choix que
    tests/e2e/test_adhesion_recompense_puis_qrcode.py).
    / Also creates the buyer's Fedow wallet: a reward can only go to an existing wallet.
    """
    email = f"test+e2epanier{uuid.uuid4().hex[:8]}@mock.test"
    code_python = (
        "from AuthBillet.utils import get_or_create_user\n"
        f"acheteur = get_or_create_user('{email}', send_mail=False)\n"
        "acheteur.is_active = True\n"
        "acheteur.first_name = 'Ada'\n"
        "acheteur.last_name = 'Lovelace'\n"
        "acheteur.save()\n"
    )
    if avec_portefeuille_fedow:
        code_python += (
            "from fedow_connect.fedow_api import FedowAPI\n"
            "FedowAPI().wallet.get_or_create_wallet(acheteur)\n"
        )
    django_shell(code_python)
    return email


def liberer_ce_que_l_acheteur_a_pris(django_shell, email):
    """
    Annule les réservations, billets et bookings de CET acheteur (email exact) pour rendre
    les places et les créneaux des fixtures partagées. Rien n'est supprimé.
    / Cancels THIS buyer's reservations, tickets and bookings (exact email). Nothing deleted.
    """
    django_shell(
        "from BaseBillet.models import Reservation, Ticket\n"
        "from booking.models import Booking\n"
        f"Ticket.objects.filter(reservation__user_commande__email='{email}')"
        ".update(status=Ticket.CANCELED)\n"
        f"Reservation.objects.filter(user_commande__email='{email}')"
        ".update(status=Reservation.CANCELED)\n"
        f"Booking.objects.filter(user__email='{email}')"
        ".update(status=Booking.USER_CANCELED)"
    )


def ouvrir_le_panneau_de_reservation(page, slug_de_l_evenement):
    """Ouvre la page de l'événement et son panneau de réservation.
    / Opens the event page and its booking panel."""
    page.goto(f"/event/{slug_de_l_evenement}/")
    page.wait_for_load_state("networkidle")
    page.locator('[data-testid="booking-open-panel"]').click()
    expect(page.locator("#reservation_form")).to_be_visible(timeout=5_000)


def choisir_un_billet(page, uuid_du_tarif):
    """Monte le compteur du tarif à 1.
    / Sets the price counter to 1."""
    compteur = page.locator(f"bs-counter[name='{uuid_du_tarif}']")
    compteur.locator(".bi-plus, button:has(.bi-plus)").first.click()


def attendre_le_badge(page, nombre_attendu):
    """Le badge du panier affiche le nombre d'items attendu.
    / The cart badge shows the expected number of items."""
    expect(page.locator(SELECTEUR_DU_BADGE)).to_contain_text(
        str(nombre_attendu), timeout=5_000
    )


def lire_en_base(django_shell, code_python, marqueur):
    """Exécute du Python dans le shell Django et rend ce qui suit `marqueur` à l'écran.
    / Runs Python in the Django shell and returns what follows `marqueur`."""
    sortie = django_shell(code_python)
    trouve = re.search(rf"{marqueur}(\S+)", sortie)
    if not trouve:
        pytest.fail(
            f"Le shell Django n'a rien imprimé derrière '{marqueur}'. Sortie : {sortie[-500:]}"
        )
    return trouve.group(1)


# --------------------------------------------------------------------------
# E1 à E4 : sans paiement réel (make e2e)
# / E1 to E4: no real payment (make e2e)
# --------------------------------------------------------------------------


def test_e1_billet_gratuit_ajoute_au_panier_puis_confirme(
    page, login_as, django_shell, e2e_slugs
):
    """
    Billet gratuit : ajout → toast et badge à 1 → page `/panier/` → paiement → redirection
    vers « mes réservations », et la Commande est payée en base.
    / Free ticket: add → toast and badge 1 → `/panier/` → checkout → redirect, Order paid.
    """
    email = creer_un_acheteur(django_shell)
    try:
        login_as(page, email)
        ouvrir_le_panneau_de_reservation(page, e2e_slugs["event_gratuit_slug"])
        choisir_un_billet(page, e2e_slugs["event_gratuit_price_uuid"])

        page.locator('[data-testid="booking-add-to-cart"]').click()

        expect(page.locator(".swal2-toast")).to_be_visible(timeout=5_000)
        attendre_le_badge(page, 1)

        page.goto("/panier/")
        page.wait_for_load_state("networkidle")
        expect(page.locator("#panier-content")).to_contain_text(
            "E2E Test — Event gratuit"
        )
        page.locator('[data-testid="panier-checkout"]').click()
        page.wait_for_url(re.compile(r"/my_account/"), timeout=10_000)

        statut_de_la_commande = lire_en_base(
            django_shell,
            "from BaseBillet.models import Commande\n"
            f"commande = Commande.objects.filter(user__email='{email}').first()\n"
            "print('STATUT=' + (commande.status if commande else 'AUCUNE'))",
            "STATUT=",
        )
        assert statut_de_la_commande == "PAID"

        # Le billet est actif (prêt à être scanné), pas seulement la Commande payée.
        # / The ticket is active (ready to scan), not only the Order paid.
        statuts_des_billets = lire_en_base(
            django_shell,
            "from BaseBillet.models import Ticket\n"
            f"billets = Ticket.objects.filter(reservation__commande__user__email='{email}')\n"
            "print('BILLETS=' + ','.join(sorted(b.status for b in billets)))",
            "BILLETS=",
        )
        assert statuts_des_billets == "K"
    finally:
        liberer_ce_que_l_acheteur_a_pris(django_shell, email)


def test_e2_un_anonyme_qui_veut_ajouter_au_panier_voit_le_panneau_de_connexion(
    page, e2e_slugs
):
    """
    Visiteur anonyme : le bouton « Connectez-vous pour ajouter au panier » ouvre le panneau
    de connexion (le panier exige d'être connecté).
    / Anonymous visitor: "Log in to add to cart" opens the login panel.
    """
    ouvrir_le_panneau_de_reservation(page, e2e_slugs["event_payant_slug"])

    page.locator('[data-testid="booking-add-to-cart-login"]').click()

    expect(page.locator("#loginPanel")).to_have_class(
        re.compile(r"\bshow\b"), timeout=5_000
    )


def test_e3_une_adhesion_recurrente_est_refusee_par_le_panier(
    page, login_as, django_shell, e2e_slugs
):
    """
    Adhésion récurrente (paiement direct seulement) : « Ajouter au panier » affiche un toast
    d'erreur, et le panier reste vide.
    / Recurring membership: "Add to cart" shows an error toast, the cart stays empty.
    """
    uuid_de_l_adhesion = fixture_du_panier(e2e_slugs, "adhesion_recurrente_uuid")
    uuid_du_tarif = fixture_du_panier(e2e_slugs, "adhesion_recurrente_price_uuid")
    email = creer_un_acheteur(django_shell)
    login_as(page, email)
    page.goto("/memberships/")
    page.wait_for_load_state("networkidle")
    page.locator(f'[data-testid="membership-open-{uuid_de_l_adhesion}"]').click()
    expect(page.locator("#membership-form")).to_be_visible(timeout=10_000)

    page.locator(f'input[type="radio"][value="{uuid_du_tarif}"]').check()
    page.fill('[data-testid="membership-firstname"]', "Ada")
    page.fill('[data-testid="membership-lastname"]', "Lovelace")
    page.locator('[data-testid="membership-add-to-cart"]').click()

    # SweetAlert2 v11 pose la classe de niveau sur le toast lui-même.
    # / SweetAlert2 v11 puts the level class on the toast element itself.
    expect(page.locator(".swal2-toast.swal2-icon-error")).to_be_visible(timeout=5_000)

    # Le panier de ce nouvel acheteur est resté vide : aucun article à retirer.
    # / This new buyer's cart stayed empty: no item to remove.
    page.goto("/panier/")
    page.wait_for_load_state("networkidle")
    expect(page.locator('[data-testid="panier-item-remove"]')).to_have_count(0)


def test_e4_un_creneau_de_ressource_ajoute_au_panier_puis_envoye_au_paiement(
    page, login_as, django_shell, e2e_slugs
):
    """
    Ressource : clic sur un créneau libre du calendrier → formulaire → « Ajouter au panier »
    → badge à 1 → le créneau s'affiche « dans le panier » → paiement → page Stripe.
    / Resource: free slot → form → add to cart → badge 1 → slot shown "in cart" → Stripe.
    """
    pk_de_la_salle = fixture_du_panier(e2e_slugs, "salle_resource_pk")
    uuid_du_tarif_de_la_salle = fixture_du_panier(e2e_slugs, "salle_price_uuid")
    email = creer_un_acheteur(django_shell)
    try:
        login_as(page, email)
        adresse_de_la_salle = f"/booking/{pk_de_la_salle}/resource/"
        page.goto(adresse_de_la_salle)
        page.wait_for_load_state("networkidle")

        premier_creneau_libre = page.locator(
            '[data-testid="booking-calendar-slot-free"]'
        ).first
        debut_du_creneau = premier_creneau_libre.get_attribute("data-start-datetime")
        premier_creneau_libre.click()
        formulaire = page.locator('[data-testid="booking-confirm-form"]')
        expect(formulaire).to_be_visible(timeout=10_000)
        # Le tarif, même unique, n'est pas présélectionné : le visiteur doit le cocher.
        # / The price, even when unique, is not preselected: the visitor must tick it.
        formulaire.locator(
            f'input[name="price"][value="{uuid_du_tarif_de_la_salle}"]'
        ).check()
        formulaire.locator('input[name="firstname"]').fill("Ada")
        formulaire.locator('input[name="lastname"]').fill("Lovelace")
        page.locator('[data-testid="resource-add-to-cart"]').click()
        attendre_le_badge(page, 1)

        page.goto(adresse_de_la_salle)
        page.wait_for_load_state("networkidle")
        creneau_dans_le_panier = page.locator(
            f'[data-testid="booking-calendar-slot-cart"][data-start-datetime="{debut_du_creneau}"]'
        )
        expect(creneau_dans_le_panier).to_have_count(1)

        page.goto("/panier/")
        page.wait_for_load_state("networkidle")
        page.locator('[data-testid="panier-checkout"]').click()
        page.wait_for_url(
            lambda url: "checkout.stripe.com" in url,
            timeout=15_000,
            wait_until="domcontentloaded",
        )
    finally:
        liberer_ce_que_l_acheteur_a_pris(django_shell, email)


# --------------------------------------------------------------------------
# E5 et E6 : vrai paiement Stripe (make e2e-stripe, `stripe listen` dans byobu)
# / E5 and E6: real Stripe payment (make e2e-stripe)
# --------------------------------------------------------------------------


def ajouter_l_adhesion_au_panier(page, uuid_du_produit, uuid_du_tarif):
    """Ajoute une adhésion au panier depuis la page des adhésions.
    / Adds a membership to the cart from the memberships page."""
    page.goto("/memberships/")
    page.wait_for_load_state("networkidle")
    page.locator(f'[data-testid="membership-open-{uuid_du_produit}"]').click()
    expect(page.locator("#membership-form")).to_be_visible(timeout=10_000)
    page.locator(f'input[type="radio"][value="{uuid_du_tarif}"]').check()
    page.fill('[data-testid="membership-firstname"]', "Ada")
    page.fill('[data-testid="membership-lastname"]', "Lovelace")
    page.locator('[data-testid="membership-add-to-cart"]').click()


def payer_le_panier_chez_stripe(
    page, email, fill_stripe_card, soumettre_paiement_stripe
):
    """De `/panier/` au retour de Stripe, avec la carte de test.
    / From `/panier/` to the return from Stripe, with the test card."""
    page.goto("/panier/")
    page.wait_for_load_state("networkidle")
    page.locator('[data-testid="panier-checkout"]').click()
    page.wait_for_url(
        lambda url: "checkout.stripe.com" in url,
        timeout=15_000,
        wait_until="domcontentloaded",
    )
    fill_stripe_card(page, email)
    paiement_parti = soumettre_paiement_stripe(page)
    assert paiement_parti, (
        "Le formulaire Stripe n'a pas été soumis (tests/PIEGES.md, 12.14)."
    )
    page.wait_for_url(
        lambda url: "tibillet.localhost" in url,
        timeout=60_000,
        wait_until="domcontentloaded",
    )


def attendre_la_commande_payee(django_shell, email, secondes=60):
    """
    Attend que la Commande de l'acheteur soit payée (retour navigateur ou webhook).
    / Waits until the buyer's Order is paid (browser return or webhook).
    """
    statut = "AUCUNE"
    for _tentative in range(secondes // 2):
        statut = lire_en_base(
            django_shell,
            "from BaseBillet.models import Commande\n"
            f"commande = Commande.objects.filter(user__email='{email}').first()\n"
            "print('STATUT=' + (commande.status if commande else 'AUCUNE'))",
            "STATUT=",
        )
        if statut == "PAID":
            return statut
        time.sleep(2)
    return statut


@pytest.mark.stripe_listen
def test_e5_vrai_paiement_d_un_panier_adhesion_plus_billet(
    page, login_as, django_shell, e2e_slugs, fill_stripe_card, soumettre_paiement_stripe
):
    """
    Panier « adhésion payante + billet payant », payé pour de vrai chez Stripe : la Commande
    est payée, les billets sont actifs, l'adhésion est active.
    / Real Stripe payment of a membership + ticket cart: Order paid, tickets and membership active.
    """
    uuid_de_l_adhesion = fixture_du_panier(e2e_slugs, "adhesion_payante_uuid")
    uuid_du_tarif = fixture_du_panier(e2e_slugs, "adhesion_payante_price_uuid")
    email = creer_un_acheteur(django_shell)
    try:
        login_as(page, email)
        ajouter_l_adhesion_au_panier(page, uuid_de_l_adhesion, uuid_du_tarif)
        attendre_le_badge(page, 1)
        ouvrir_le_panneau_de_reservation(page, e2e_slugs["event_payant_slug"])
        choisir_un_billet(page, e2e_slugs["event_payant_price_uuid"])
        page.locator('[data-testid="booking-add-to-cart"]').click()
        attendre_le_badge(page, 2)

        payer_le_panier_chez_stripe(
            page, email, fill_stripe_card, soumettre_paiement_stripe
        )

        statut_de_la_commande = attendre_la_commande_payee(django_shell, email)
        assert statut_de_la_commande == "PAID", (
            f"Commande restée {statut_de_la_commande}. Vérifier que `stripe listen` tourne "
            "(pgrep -af 'stripe listen') avant de soupçonner le code (PIEGES 12.13.quinquies)."
        )
        etat_final = lire_en_base(
            django_shell,
            "from BaseBillet.models import Membership, Ticket\n"
            f"billets = Ticket.objects.filter(reservation__user_commande__email='{email}')\n"
            f"adhesion = Membership.objects.filter(user__email='{email}').first()\n"
            "print('ETAT=' + ','.join(sorted(set(b.status for b in billets))) + '|' + adhesion.status)",
            "ETAT=",
        )
        assert etat_final == "K|A", (
            f"Attendu : billets actifs (K), adhésion active (A). Lu : {etat_final}"
        )
    finally:
        liberer_ce_que_l_acheteur_a_pris(django_shell, email)


def solde_fedow_de(django_shell, email):
    """Le solde dépensable de l'acheteur, relu SUR LE FEDOW, sans cache.
    / The buyer's spendable balance, read ON THE FEDOW, no cache."""
    return int(
        lire_en_base(
            django_shell,
            "from AuthBillet.models import TibilletUser\n"
            "from fedow_connect.fedow_api import FedowAPI\n"
            f"acheteur = TibilletUser.objects.get(email='{email}')\n"
            "print('SOLDE=' + str(FedowAPI().wallet.get_total_fiducial_and_all_federated_token("
            "acheteur, use_cache=False)))",
            "SOLDE=",
        )
    )


@pytest.mark.stripe_listen
def test_e6_une_adhesion_payee_par_le_panier_verse_sa_recompense_monnaie(
    page, login_as, django_shell, e2e_slugs, fill_stripe_card, soumettre_paiement_stripe
):
    """
    Adhésion qui verse 5 unités de monnaie locale, payée par le panier : le solde de
    l'acheteur, relu sur le vrai Fedow, augmente de 500 centimes.
    / Membership paying 5 local-currency units, paid through the cart: the buyer's balance,
    read on the real Fedow, grows by 500 cents.
    """
    uuid_de_l_adhesion = fixture_du_panier(e2e_slugs, "adhesion_recompense_uuid")
    uuid_du_tarif = fixture_du_panier(e2e_slugs, "adhesion_recompense_price_uuid")
    email = creer_un_acheteur(django_shell, avec_portefeuille_fedow=True)
    login_as(page, email)
    solde_de_depart = solde_fedow_de(django_shell, email)

    ajouter_l_adhesion_au_panier(page, uuid_de_l_adhesion, uuid_du_tarif)
    attendre_le_badge(page, 1)
    payer_le_panier_chez_stripe(
        page, email, fill_stripe_card, soumettre_paiement_stripe
    )
    assert attendre_la_commande_payee(django_shell, email) == "PAID"

    solde_final = solde_de_depart
    for _tentative in range(30):
        solde_final = solde_fedow_de(django_shell, email)
        if solde_final != solde_de_depart:
            break
        time.sleep(2)

    assert solde_final - solde_de_depart == 500, (
        f"Solde Fedow : {solde_de_depart} → {solde_final}. Le versement passe par Celery "
        "(lespass_celery doit tourner) puis par le Fedow (joignable ?)."
    )
