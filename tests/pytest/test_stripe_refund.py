"""
Tests pytest : remboursements d'une réservation (Stripe mocké) et avoirs hors Stripe.
/ Pytest tests: reservation refunds (mocked Stripe) and non-Stripe credit notes.

Deux façons de vendre, testées avec les mêmes scénarios :
- SANS panier : réservation directe (API v2), le paiement pointe vers la réservation ;
- AVEC panier : CommandeService.materialiser(), le paiement est porté par la Commande.
/ Two ways to sell, same scenarios: WITHOUT cart (API v2, payment points to the
reservation) and WITH cart (materialiser(), payment held by the Commande).

Scénarios Stripe : 3 billets remboursés un par un, réservation complète, un billet
puis le reste. Ventes admin en espèces : un avoir par billet annulé, et jamais
d'avoir sur la vente d'un autre client.
/ Stripe scenarios: 3 tickets one by one, full reservation, one ticket then the
rest. Admin cash sales: one credit note per cancelled ticket, never on another
customer's sale.

Stripe est mocké : Session.retrieve via la fixture mock_stripe, Refund.create patché.
/ Stripe is mocked: Session.retrieve via the mock_stripe fixture, Refund.create patched.

LOCALISATION : tests/pytest/test_stripe_refund.py
Code testé / Tested code : BaseBillet/models.py (Reservation.cancel_and_refund_resa,
cancel_and_refund_ticket, _lignes_hors_stripe), PaiementStripe/utils.py (partial_refund_payment).
Plan : TECH_DOC/SESSIONS/REMBOURSEMENT/SPEC.md
Fabriques de ventes / Sale factories : tests/pytest/fabriques_reservation.py

Lancer / Run :
  KEY=$(docker exec -e TEST=1 lespass_django poetry run python /DjangoFiles/manage.py test_api_key 2>/dev/null | tail -1)
  docker exec -e API_KEY="$KEY" lespass_django poetry run pytest tests/pytest/test_stripe_refund.py -q
"""

import re
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from fabriques_reservation import (
    creer_evenement_et_produit,
    creer_reservation_api,
    identifiant_aleatoire,
    nettoyer_paiement,
    nettoyer_vente_admin,
    reservation_payee,
    vente_admin_especes,
)


class TestRemboursementStripe:
    """Remboursements Stripe, avec et sans panier.
    / Stripe refunds, with and without cart.
    """

    @pytest.mark.parametrize("parcours", ["sans_panier", "avec_panier"])
    def test_trois_billets_rembourses_un_par_un(
        self, parcours, api_client, auth_headers, mock_stripe, tenant
    ):
        """3 billets remboursés un par un : 3 remboursements Stripe d'un billet.
        / 3 tickets refunded one by one: 3 one-ticket Stripe refunds.

        Après chaque billet : le paiement passe H, H puis R, et total_paid() baisse
        de 10 €. Au dernier billet, la réservation est annulée.
        / After each ticket: payment goes H, H then R, total_paid() drops by 10 €.
        At the last ticket, the reservation is cancelled.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Reservation, Paiement_stripe, LigneArticle, Ticket

        event_uuid, price_uuid = creer_evenement_et_produit(api_client, auth_headers, identifiant_aleatoire())
        reservation, paiement, prix_un_billet = reservation_payee(
            parcours, api_client, auth_headers, tenant, mock_stripe, event_uuid, price_uuid, qty=3,
        )

        try:
            with tenant_context(tenant):
                billets = list(reservation.tickets.order_by("pk"))
                statut_paiement_attendu = [
                    Paiement_stripe.PARTIALLY_REFUNDED,
                    Paiement_stripe.PARTIALLY_REFUNDED,
                    Paiement_stripe.REFUNDED,
                ]
                total_paye_attendu = [Decimal("20.00"), Decimal("10.00"), Decimal("0.00")]
                date_de_reservation = reservation.datetime

                with patch(
                    "stripe.Refund.create",
                    return_value=MagicMock(status="succeeded"),
                ) as mock_refund:
                    for numero, billet in enumerate(billets):
                        reservation.cancel_and_refund_ticket(billet)

                        paiement.refresh_from_db()
                        assert paiement.status == statut_paiement_attendu[numero], (
                            f"Billet {numero + 1} : paiement attendu {statut_paiement_attendu[numero]}, "
                            f"obtenu {paiement.status}"
                        )
                        assert reservation.total_paid() == total_paye_attendu[numero], (
                            f"Billet {numero + 1} : total payé attendu {total_paye_attendu[numero]}, "
                            f"obtenu {reservation.total_paid()}"
                        )

                montants = [appel.kwargs["amount"] for appel in mock_refund.call_args_list]
                assert montants == [prix_un_billet, prix_un_billet, prix_un_billet], (
                    f"3 remboursements d'un billet ({prix_un_billet}) attendus, obtenu {montants}"
                )

                # Chaque remboursement est une ligne négative rattachée à la réservation.
                # / Each refund is a negative line linked to the reservation.
                remboursements = LigneArticle.objects.filter(
                    paiement_stripe=paiement, status=LigneArticle.REFUNDED,
                )
                assert remboursements.count() == 3
                assert all(ligne.qty == -1 for ligne in remboursements)
                assert all(ligne.reservation_id == reservation.pk for ligne in remboursements), (
                    "Les lignes de remboursement doivent être rattachées à la réservation."
                )

                assert all(billet.status == Ticket.CANCELED for billet in reservation.tickets.all())
                reservation.refresh_from_db()
                assert reservation.status == Reservation.CANCELED, (
                    f"Plus aucun billet actif : réservation attendue CANCELED, obtenu {reservation.status}"
                )
                # Seul le statut est réécrit : la date de réservation ne bouge pas.
                # / Only the status is rewritten: the reservation date does not move.
                assert reservation.datetime == date_de_reservation
        finally:
            nettoyer_paiement(tenant, paiement)

    @pytest.mark.parametrize("parcours", ["sans_panier", "avec_panier"])
    def test_reservation_complete_remboursee_d_un_coup(
        self, parcours, api_client, auth_headers, mock_stripe, tenant
    ):
        """Réservation de 3 billets annulée d'un coup : un seul remboursement de 3 billets.
        / 3-ticket reservation cancelled at once: one refund of 3 tickets.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Reservation, Paiement_stripe, LigneArticle, Ticket

        event_uuid, price_uuid = creer_evenement_et_produit(api_client, auth_headers, identifiant_aleatoire())
        reservation, paiement, prix_un_billet = reservation_payee(
            parcours, api_client, auth_headers, tenant, mock_stripe, event_uuid, price_uuid, qty=3,
        )

        try:
            with tenant_context(tenant):
                with patch(
                    "stripe.Refund.create",
                    return_value=MagicMock(status="succeeded"),
                ) as mock_refund:
                    reservation.cancel_and_refund_resa()

                assert mock_refund.call_count == 1
                kwargs = mock_refund.call_args.kwargs
                assert kwargs["amount"] == prix_un_billet * 3, (
                    f"Remboursement de 3 billets attendu ({prix_un_billet * 3}), obtenu {kwargs['amount']}"
                )
                assert kwargs["payment_intent"] == mock_stripe.session.payment_intent

                paiement.refresh_from_db()
                assert paiement.status == Paiement_stripe.REFUNDED

                remboursement = LigneArticle.objects.get(
                    paiement_stripe=paiement, status=LigneArticle.REFUNDED,
                )
                assert remboursement.qty == -3
                assert remboursement.reservation_id == reservation.pk, (
                    "La ligne de remboursement doit être rattachée à la réservation."
                )

                reservation.refresh_from_db()
                assert reservation.status == Reservation.CANCELED
                assert all(billet.status == Ticket.CANCELED for billet in reservation.tickets.all())
                assert reservation.total_paid() == Decimal("0.00"), (
                    f"Tout est remboursé : total payé attendu 0, obtenu {reservation.total_paid()}"
                )
        finally:
            nettoyer_paiement(tenant, paiement)

    @pytest.mark.parametrize("parcours", ["sans_panier", "avec_panier"])
    def test_un_billet_puis_reservation_complete(
        self, parcours, api_client, auth_headers, mock_stripe, tenant
    ):
        """Un billet remboursé, puis la réservation annulée : les 2 restants sont remboursés.
        / One ticket refunded, then the reservation cancelled: the 2 others are refunded.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Reservation, Paiement_stripe

        event_uuid, price_uuid = creer_evenement_et_produit(api_client, auth_headers, identifiant_aleatoire())
        reservation, paiement, prix_un_billet = reservation_payee(
            parcours, api_client, auth_headers, tenant, mock_stripe, event_uuid, price_uuid, qty=3,
        )

        try:
            with tenant_context(tenant):
                with patch(
                    "stripe.Refund.create",
                    return_value=MagicMock(status="succeeded"),
                ) as mock_refund:
                    reservation.cancel_and_refund_ticket(reservation.tickets.order_by("pk").first())
                    reservation.cancel_and_refund_resa()

                montants = [appel.kwargs["amount"] for appel in mock_refund.call_args_list]
                assert montants == [prix_un_billet, prix_un_billet * 2], (
                    f"Remboursements attendus : 1 billet, puis les 2 restants. Obtenu {montants}"
                )

                paiement.refresh_from_db()
                assert paiement.status == Paiement_stripe.REFUNDED
                reservation.refresh_from_db()
                assert reservation.status == Reservation.CANCELED
                assert reservation.total_paid() == Decimal("0.00")
        finally:
            nettoyer_paiement(tenant, paiement)

    @pytest.mark.parametrize("parcours", ["sans_panier", "avec_panier"])
    def test_annuler_apres_trois_billets_rembourses_ne_rembourse_rien_de_plus(
        self, parcours, api_client, auth_headers, mock_stripe, tenant
    ):
        """Après les 3 billets remboursés, la réservation est annulée : la ré-annuler est refusé.
        / After the 3 tickets are refunded, the reservation is cancelled: cancelling again is refused.
        """
        from django.utils.translation import gettext
        from django_tenants.utils import tenant_context
        from BaseBillet.models import LigneArticle

        event_uuid, price_uuid = creer_evenement_et_produit(api_client, auth_headers, identifiant_aleatoire())
        reservation, paiement, _prix = reservation_payee(
            parcours, api_client, auth_headers, tenant, mock_stripe, event_uuid, price_uuid, qty=3,
        )

        try:
            with tenant_context(tenant):
                with patch(
                    "stripe.Refund.create",
                    return_value=MagicMock(status="succeeded"),
                ) as mock_refund:
                    for billet in reservation.tickets.order_by("pk"):
                        reservation.cancel_and_refund_ticket(billet)
                    lignes_avant = LigneArticle.objects.filter(paiement_stripe=paiement).count()

                    message_attendu = re.escape(gettext("This reservation has already been canceled."))
                    with pytest.raises(Exception, match=message_attendu):
                        reservation.cancel_and_refund_resa()

                assert mock_refund.call_count == 3, "Aucun remboursement Stripe de plus."
                assert LigneArticle.objects.filter(paiement_stripe=paiement).count() == lignes_avant
        finally:
            nettoyer_paiement(tenant, paiement)

    def test_annulation_billet_par_billet_n_ecrit_pas_d_erreur_dans_les_logs(
        self, api_client, auth_headers, mock_stripe, tenant, caplog
    ):
        """Rembourser tous les billets un par un n'écrit aucune fausse erreur dans les logs.
        / Refunding all tickets one by one writes no false error in the logs.

        Transitions couvertes : paiement VALID → PARTIALLY_REFUNDED → REFUNDED, et
        réservation PAID → CANCELED (payée, mail pas encore envoyé).
        / Covered transitions: payment VALID → H → R, reservation PAID → CANCELED.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Reservation

        event_uuid, price_uuid = creer_evenement_et_produit(api_client, auth_headers, identifiant_aleatoire())
        reservation, paiement, _prix = reservation_payee(
            "sans_panier", api_client, auth_headers, tenant, mock_stripe, event_uuid, price_uuid, qty=2,
        )

        try:
            with tenant_context(tenant):
                Reservation.objects.filter(pk=reservation.pk).update(status=Reservation.PAID)
                reservation.refresh_from_db()

                with patch("stripe.Refund.create", return_value=MagicMock(status="succeeded")):
                    for billet in reservation.tickets.order_by("pk"):
                        reservation.cancel_and_refund_ticket(billet)

                reservation.refresh_from_db()
                assert reservation.status == Reservation.CANCELED

            assert "erreur_regression" not in caplog.text, (
                "Une annulation a déclenché error_regression dans la machine à états."
            )
        finally:
            nettoyer_paiement(tenant, paiement)

    @pytest.mark.parametrize("annulation", ["billet", "reservation"])
    def test_annuler_sans_paiement_remboursable_leve_une_erreur_et_n_annule_rien(
        self, annulation, api_client, auth_headers, mock_stripe, tenant
    ):
        """Réservation payée dont le paiement n'est plus remboursable : erreur, rien n'est annulé.
        / Paid reservation whose payment is no longer refundable: error, nothing is cancelled.
        """
        from django.utils.translation import gettext
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Paiement_stripe, Reservation, Ticket

        event_uuid, price_uuid = creer_evenement_et_produit(api_client, auth_headers, identifiant_aleatoire())
        reservation, paiement, _prix = reservation_payee(
            "sans_panier", api_client, auth_headers, tenant, mock_stripe, event_uuid, price_uuid, qty=2,
        )

        try:
            with tenant_context(tenant):
                # Un statut que les filtres de remboursement ne retiennent pas.
                # / A status the refund filters do not keep.
                Paiement_stripe.objects.filter(pk=paiement.pk).update(status=Paiement_stripe.CANCELED)

                message_attendu = re.escape(gettext("Aucun paiement remboursable n'a été trouvé. Rien n'a été annulé."))
                with patch("stripe.Refund.create") as mock_refund:
                    with pytest.raises(Exception, match=message_attendu):
                        if annulation == "billet":
                            reservation.cancel_and_refund_ticket(reservation.tickets.order_by("pk").first())
                        else:
                            reservation.cancel_and_refund_resa()

                assert not mock_refund.called
                assert not reservation.tickets.filter(status=Ticket.CANCELED).exists(), (
                    "Aucun billet ne doit être annulé sans remboursement."
                )
                reservation.refresh_from_db()
                assert reservation.status == Reservation.VALID
        finally:
            nettoyer_paiement(tenant, paiement)

    def test_annuler_une_reservation_gratuite_n_appelle_pas_stripe(
        self, api_client, auth_headers, mock_stripe, tenant
    ):
        """Annuler une réservation gratuite n'appelle jamais Stripe.
        / Cancelling a free reservation never calls Stripe.

        Une réservation gratuite (« Free booking ») n'a aucune ligne payée : l'API v2 ne crée
        qu'une ligne FREERES à 0 €.
        / A free reservation ("Free booking") has no paid line: API v2 only creates a
        FREERES line at 0 €.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import LigneArticle, Reservation

        rid = identifiant_aleatoire()
        email = f"test+refundfree{rid}@mock.test"

        event_uuid, price_uuid = creer_evenement_et_produit(
            api_client, auth_headers, rid, price_amount="0.00", category="Free booking",
        )
        resp = creer_reservation_api(api_client, auth_headers, event_uuid, price_uuid, email)
        assert resp.status_code in (200, 201)

        with tenant_context(tenant):
            reservation = Reservation.objects.filter(
                user_commande__email=email,
            ).order_by("-datetime").first()
            assert reservation is not None

            try:
                assert not mock_stripe.mock_create.called, "Le parcours gratuit ne doit ouvrir aucun paiement Stripe."
                assert not LigneArticle.objects.filter(
                    reservation=reservation, status__in=[LigneArticle.VALID, LigneArticle.PAID],
                ).exists(), "Une réservation gratuite ne doit avoir aucune ligne payée."

                with patch("stripe.Refund.create") as mock_refund:
                    reservation.cancel_and_refund_resa()

                assert not mock_refund.called, "Aucun remboursement Stripe pour une réservation gratuite."
                reservation.refresh_from_db()
                assert reservation.status == Reservation.CANCELED
            finally:
                LigneArticle.objects.filter(reservation=reservation).delete()


class TestAvoirsHorsStripe:
    """Ventes admin (espèces, chèque…) : avoirs à l'annulation.
    / Admin sales (cash, check…): credit notes on cancellation.
    """

    def test_annuler_une_reservation_stripe_ne_touche_pas_la_vente_especes_d_un_autre_client(
        self, api_client, auth_headers, mock_stripe, tenant
    ):
        """Annuler une réservation Stripe ne crée aucun avoir sur la vente espèces d'un autre client.
        / Cancelling a Stripe reservation creates no credit note on another customer's cash sale.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import LigneArticle, Reservation

        event_uuid, price_uuid = creer_evenement_et_produit(api_client, auth_headers, identifiant_aleatoire())
        reservation_stripe, paiement, _prix = reservation_payee(
            "sans_panier", api_client, auth_headers, tenant, mock_stripe, event_uuid, price_uuid, qty=1,
        )
        reservation_admin, ligne_admin = vente_admin_especes(tenant, event_uuid, price_uuid, qty=1)

        try:
            with tenant_context(tenant):
                # Précondition : les deux ventes partagent le même tarif vendu.
                # / Precondition: both sales share the same sold price.
                assert reservation_stripe.tickets.get().pricesold_id == ligne_admin.pricesold_id

                with patch("stripe.Refund.create", return_value=MagicMock(status="succeeded")):
                    reservation_stripe.cancel_and_refund_resa()

                avoirs = LigneArticle.objects.filter(credit_note_for=ligne_admin)
                assert avoirs.count() == 0, (
                    "Annuler la réservation Stripe a créé un avoir sur la vente espèces d'un autre client."
                )
                reservation_admin.refresh_from_db()
                assert reservation_admin.status == Reservation.VALID
        finally:
            nettoyer_vente_admin(tenant, ligne_admin)
            nettoyer_paiement(tenant, paiement)

    def test_annuler_un_billet_stripe_ne_touche_pas_la_vente_especes_d_un_autre_client(
        self, api_client, auth_headers, mock_stripe, tenant
    ):
        """Annuler UN billet Stripe : aucun avoir chez un autre client, et le message de remboursement.
        / Cancelling ONE Stripe ticket: no credit note for another customer, and the refund message.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import LigneArticle

        event_uuid, price_uuid = creer_evenement_et_produit(api_client, auth_headers, identifiant_aleatoire())
        reservation_stripe, paiement, _prix = reservation_payee(
            "sans_panier", api_client, auth_headers, tenant, mock_stripe, event_uuid, price_uuid, qty=2,
        )
        _reservation_admin, ligne_admin = vente_admin_especes(tenant, event_uuid, price_uuid, qty=1)

        try:
            with tenant_context(tenant):
                with patch("stripe.Refund.create", return_value=MagicMock(status="succeeded")):
                    message = reservation_stripe.cancel_and_refund_ticket(
                        reservation_stripe.tickets.order_by("pk").first()
                    )

                avoirs = LigneArticle.objects.filter(credit_note_for=ligne_admin)
                assert avoirs.count() == 0, (
                    "Annuler un billet Stripe a créé un avoir sur la vente espèces d'un autre client."
                )
                # Remboursé par Stripe : le message est celui du remboursement.
                # / Refunded by Stripe: the message is the refund one.
                assert str(message) == str(reservation_stripe.cancel_text()), (
                    f"Message de remboursement attendu, obtenu {message!r}"
                )
        finally:
            nettoyer_vente_admin(tenant, ligne_admin)
            nettoyer_paiement(tenant, paiement)

    def test_annuler_une_reservation_admin_especes_cree_son_avoir(
        self, api_client, auth_headers, tenant
    ):
        """Réservation admin de 3 billets en espèces annulée : un avoir de 3 billets, total payé à 0.
        / 3-ticket admin cash reservation cancelled: one 3-ticket credit note, total paid at 0.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import LigneArticle, Reservation

        event_uuid, price_uuid = creer_evenement_et_produit(api_client, auth_headers, identifiant_aleatoire())
        reservation_admin, ligne_admin = vente_admin_especes(tenant, event_uuid, price_uuid, qty=3)

        try:
            with tenant_context(tenant):
                assert reservation_admin.total_paid() == Decimal("30.00")

                reservation_admin.cancel_and_refund_resa()

                avoir = LigneArticle.objects.get(credit_note_for=ligne_admin)
                assert avoir.status == LigneArticle.CREDIT_NOTE
                assert avoir.qty == -3
                assert avoir.reservation_id == reservation_admin.pk, (
                    "L'avoir doit être rattaché à la réservation."
                )
                reservation_admin.refresh_from_db()
                assert reservation_admin.status == Reservation.CANCELED
                assert reservation_admin.total_paid() == Decimal("0.00"), (
                    f"Avoir compté : total payé attendu 0, obtenu {reservation_admin.total_paid()}"
                )

                # La fiche utilisateur de l'admin recalcule le montant payé à sa façon.
                # / The admin user page computes the paid amount its own way.
                from Administration.admin_tenant import _lignes_payees_prefetch
                montant_admin = sum(
                    int(ligne.amount * ligne.qty) for ligne in _lignes_payees_prefetch(reservation_admin)
                )
                assert montant_admin == 0, f"Montant payé côté admin attendu 0, obtenu {montant_admin}"
        finally:
            nettoyer_vente_admin(tenant, ligne_admin)

    def test_trois_billets_admin_annules_un_par_un_creent_trois_avoirs_d_un_billet(
        self, api_client, auth_headers, tenant
    ):
        """3 billets admin en espèces annulés un par un : 3 avoirs d'un billet.
        / 3 admin cash tickets cancelled one by one: 3 one-ticket credit notes.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import LigneArticle, Reservation

        event_uuid, price_uuid = creer_evenement_et_produit(api_client, auth_headers, identifiant_aleatoire())
        reservation_admin, ligne_admin = vente_admin_especes(tenant, event_uuid, price_uuid, qty=3)

        try:
            with tenant_context(tenant):
                total_paye_attendu = [Decimal("20.00"), Decimal("10.00"), Decimal("0.00")]
                for numero, billet in enumerate(reservation_admin.tickets.order_by("pk")):
                    reservation_admin.cancel_and_refund_ticket(billet)

                    avoirs = LigneArticle.objects.filter(credit_note_for=ligne_admin)
                    assert [avoir.qty for avoir in avoirs] == [-1] * (numero + 1), (
                        f"Billet {numero + 1} : un avoir de -1 par billet attendu, "
                        f"obtenu {[avoir.qty for avoir in avoirs]}"
                    )
                    assert reservation_admin.total_paid() == total_paye_attendu[numero], (
                        f"Billet {numero + 1} : total payé attendu {total_paye_attendu[numero]}, "
                        f"obtenu {reservation_admin.total_paid()}"
                    )

                reservation_admin.refresh_from_db()
                assert reservation_admin.status == Reservation.CANCELED
                # Une ligne entièrement créditée n'est plus proposée.
                # / A fully credited line is no longer offered.
                assert reservation_admin._lignes_hors_stripe() == []
        finally:
            nettoyer_vente_admin(tenant, ligne_admin)

    def test_un_billet_admin_puis_reservation_complete_cree_un_avoir_pour_le_reste(
        self, api_client, auth_headers, tenant
    ):
        """3 billets admin en espèces : un billet annulé, puis la réservation. Avoirs de -1, puis -2.
        / 3 admin cash tickets: one cancelled, then the reservation. Credit notes of -1, then -2.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import LigneArticle

        event_uuid, price_uuid = creer_evenement_et_produit(api_client, auth_headers, identifiant_aleatoire())
        reservation_admin, ligne_admin = vente_admin_especes(tenant, event_uuid, price_uuid, qty=3)

        try:
            with tenant_context(tenant):
                reservation_admin.cancel_and_refund_ticket(reservation_admin.tickets.order_by("pk").first())
                reservation_admin.cancel_and_refund_resa()

                quantites_des_avoirs = sorted(
                    avoir.qty for avoir in LigneArticle.objects.filter(credit_note_for=ligne_admin)
                )
                assert quantites_des_avoirs == [-2, -1], (
                    f"Avoirs attendus : -1 (le billet), puis -2 (le reste). Obtenu {quantites_des_avoirs}"
                )
                assert reservation_admin.total_paid() == Decimal("0.00")
        finally:
            nettoyer_vente_admin(tenant, ligne_admin)

    def test_annuler_une_reservation_gratuite_ne_touche_pas_la_vente_admin_du_meme_tarif(
        self, api_client, auth_headers, mock_stripe, tenant
    ):
        """Une réservation gratuite n'a aucune ligne : l'annuler ne touche pas la vente admin du même tarif.
        / A free reservation has no line: cancelling it does not touch the admin sale of the same price.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import LigneArticle, Reservation

        rid = identifiant_aleatoire()
        email = f"test+gratuit{rid}@mock.test"
        event_uuid, price_uuid = creer_evenement_et_produit(
            api_client, auth_headers, rid, price_amount="0.00", category="Free booking",
        )
        resp = creer_reservation_api(api_client, auth_headers, event_uuid, price_uuid, email)
        assert resp.status_code in (200, 201)
        assert not mock_stripe.mock_create.called, "Le parcours gratuit ne doit ouvrir aucun paiement Stripe."
        # L'admin offre le même tarif gratuit à un autre client.
        # / The admin offers the same free price to another customer.
        _reservation_admin, ligne_admin = vente_admin_especes(
            tenant, event_uuid, price_uuid, qty=1, offert=True,
        )

        try:
            with tenant_context(tenant):
                reservation_gratuite = Reservation.objects.filter(
                    user_commande__email=email,
                ).order_by("-datetime").first()
                assert reservation_gratuite.tickets.get().pricesold_id == ligne_admin.pricesold_id

                reservation_gratuite.cancel_and_refund_resa()

                assert LigneArticle.objects.filter(credit_note_for=ligne_admin).count() == 0, (
                    "Annuler la réservation gratuite a créé un avoir sur la vente admin."
                )
        finally:
            nettoyer_vente_admin(tenant, ligne_admin)
            with tenant_context(tenant):
                LigneArticle.objects.filter(reservation__user_commande__email=email).delete()

    def test_lignes_hors_stripe_ne_renvoie_que_les_lignes_de_la_reservation(
        self, api_client, auth_headers, mock_stripe, tenant
    ):
        """_lignes_hors_stripe() ne renvoie que les lignes rattachées à la réservation.
        / _lignes_hors_stripe() only returns the lines linked to the reservation.

        Ni la vente d'un autre client, ni une ancienne ligne sans réservation.
        / Neither another customer's sale, nor an old line without reservation.
        """
        from django_tenants.utils import tenant_context
        from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin

        event_uuid, price_uuid = creer_evenement_et_produit(api_client, auth_headers, identifiant_aleatoire())
        reservation_admin, ligne_admin = vente_admin_especes(tenant, event_uuid, price_uuid, qty=2)
        _autre_reservation, ligne_autre_client = vente_admin_especes(tenant, event_uuid, price_uuid, qty=1)
        reservation_stripe, paiement, _prix = reservation_payee(
            "sans_panier", api_client, auth_headers, tenant, mock_stripe, event_uuid, price_uuid, qty=1,
        )

        with tenant_context(tenant):
            ancienne_ligne_sans_reservation = LigneArticle.objects.create(
                pricesold=ligne_admin.pricesold, qty=1, amount=1000,
                payment_method=PaymentMethod.CASH, status=LigneArticle.VALID,
                sale_origin=SaleOrigin.ADMIN,
            )

        try:
            with tenant_context(tenant):
                assert list(reservation_admin._lignes_hors_stripe()) == [ligne_admin]
                assert list(reservation_admin._lignes_hors_stripe(
                    pricesold_ids=[ligne_admin.pricesold_id],
                )) == [ligne_admin]
                assert list(reservation_stripe._lignes_hors_stripe()) == [], (
                    "Une réservation Stripe n'a aucune ligne hors Stripe à elle."
                )
        finally:
            nettoyer_vente_admin(tenant, ancienne_ligne_sans_reservation)
            nettoyer_vente_admin(tenant, ligne_autre_client)
            nettoyer_vente_admin(tenant, ligne_admin)
            nettoyer_paiement(tenant, paiement)
