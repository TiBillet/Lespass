"""
Fiche de détail d'un évènement dans l'admin : billets, réponses aux formulaires dynamiques, filtres.
/ Admin event detail page: tickets, dynamic form answers, filters.

LOCALISATION : tests/pytest/test_admin_fiche_detail_evenement.py

Code testé / Tested code :
- BaseBillet/views.py : EventMVT.admin_show_event_detail (et get_permissions),
  _event_detail_form_questions, _read_question_filters, _reservation_matches_filters
- Administration/templates/admin/reservation/event_detail.html
- Administration/templates/admin/reservation/partials/event_detail_results.html

Lancer / Run : make test ARGS="tests/pytest/test_admin_fiche_detail_evenement.py"
"""

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    creer_evenement_avec_tarif,
    creer_utilisateur,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


def creer_un_evenement_avec_formulaire(tenant, reponses_par_reservation):
    """
    Crée un évènement dont le produit a 3 questions (choix, choix multiple, texte),
    puis une réservation + un billet valide pour chaque dict de réponses.
    / Creates an event with 3 questions, then one reservation + one valid ticket per answers dict.

    Rend (evenement, liste des réservations).
    """
    from BaseBillet.models import ProductFormField, Reservation, Ticket

    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees():
                concert = creer_evenement_avec_tarif(prix="10.00")
                ProductFormField.objects.create(
                    product=concert.produit,
                    label="Régime",
                    field_type=ProductFormField.FieldType.SINGLE_SELECT,
                    options=["Omnivore", "Végan"],
                    order=0,
                )
                ProductFormField.objects.create(
                    product=concert.produit,
                    label="Ateliers",
                    field_type=ProductFormField.FieldType.MULTI_SELECT,
                    options=["Pain", "Épices"],
                    order=1,
                )
                ProductFormField.objects.create(
                    product=concert.produit,
                    label="Allergies",
                    field_type=ProductFormField.FieldType.SHORT_TEXT,
                    order=2,
                )

                reservations = []
                for reponses in reponses_par_reservation:
                    reservation = Reservation.objects.create(
                        user_commande=creer_utilisateur(),
                        event=concert.evenement,
                        custom_form=reponses,
                    )
                    Ticket.objects.create(
                        reservation=reservation,
                        first_name="Ada",
                        last_name="Lovelace",
                        status=Ticket.NOT_SCANNED,
                    )
                    reservations.append(reservation)
                return concert.evenement, reservations


def afficher_la_fiche_detail(client_http, tenant, evenement, filtres=None, **entetes):
    """GET de la fiche de détail, comme le bouton « Voir » ou un filtre.
    / GET of the detail page, like the "Voir" button or a filter."""
    with tenant_context(tenant):
        return client_http.get(
            f"/event/{evenement.pk}/admin_show_event_detail/",
            filtres or {},
            **entetes,
        )


def nombre_de_lignes_billets(contenu):
    return contenu.count('data-testid="admin-event-detail-ticket-row"')


def nombre_de_lignes_reponses(contenu):
    return contenu.count('data-testid="admin-event-detail-form-answer-row"')


def test_la_fiche_affiche_l_email_du_billet_sans_le_nom(admin_client, tenant):
    """Le billet apparaît avec l'email de l'acheteur. Le nom du billet n'est pas affiché.
    / The ticket shows with the buyer's email. The ticket name is not shown."""
    evenement, reservations = creer_un_evenement_avec_formulaire(
        tenant, [{"Régime": "Végan"}]
    )

    reponse = afficher_la_fiche_detail(admin_client, tenant, evenement)

    assert reponse.status_code == 200
    contenu = reponse.content.decode()
    assert nombre_de_lignes_billets(contenu) == 1
    assert reservations[0].user_commande.email in contenu
    assert "Lovelace" not in contenu


def test_la_fiche_affiche_les_reponses_au_formulaire_en_colonnes(admin_client, tenant):
    """Chaque question est une colonne, la réponse est dans la ligne de la réservation.
    / Each question is a column, the answer is in the reservation's row."""
    evenement, _reservations = creer_un_evenement_avec_formulaire(
        tenant, [{"Allergies": "Arachides"}]
    )

    reponse = afficher_la_fiche_detail(admin_client, tenant, evenement)

    contenu = reponse.content.decode()
    bloc_des_reponses = contenu.split('data-testid="admin-event-detail-form-answers"')[
        1
    ]
    assert "Allergies" in bloc_des_reponses
    assert "Arachides" in bloc_des_reponses


def test_le_filtre_email_ne_garde_que_la_reservation_correspondante(
    admin_client, tenant
):
    """Le filtre email (« contient ») ne garde qu'une réservation sur deux.
    / The email filter keeps only one of the two reservations."""
    evenement, reservations = creer_un_evenement_avec_formulaire(
        tenant, [{"Régime": "Végan"}, {"Régime": "Omnivore"}]
    )
    email_cherche = reservations[0].user_commande.email

    reponse = afficher_la_fiche_detail(
        admin_client, tenant, evenement, {"email": email_cherche[:20]}
    )

    contenu = reponse.content.decode()
    assert nombre_de_lignes_billets(contenu) == 1
    assert nombre_de_lignes_reponses(contenu) == 1
    assert email_cherche in contenu


def test_le_filtre_sur_une_question_a_choix(admin_client, tenant):
    """question_0 = « Végan » ne garde que les réservations qui ont répondu Végan.
    / question_0 = "Végan" keeps only reservations that answered Végan."""
    evenement, _reservations = creer_un_evenement_avec_formulaire(
        tenant, [{"Régime": "Végan"}, {"Régime": "Omnivore"}, {"Régime": "Végan"}]
    )

    reponse = afficher_la_fiche_detail(
        admin_client, tenant, evenement, {"question_0": "Végan"}
    )

    contenu = reponse.content.decode()
    assert nombre_de_lignes_reponses(contenu) == 2
    assert nombre_de_lignes_billets(contenu) == 2


def test_le_filtre_sur_une_question_a_choix_multiple(admin_client, tenant):
    """Choix multiple : la réservation passe si l'option fait partie de ses réponses.
    / Multiple choice: the reservation matches if the option is among its answers."""
    evenement, _reservations = creer_un_evenement_avec_formulaire(
        tenant, [{"Ateliers": ["Pain", "Épices"]}, {"Ateliers": ["Épices"]}]
    )

    reponse = afficher_la_fiche_detail(
        admin_client, tenant, evenement, {"question_1": "Pain"}
    )

    assert nombre_de_lignes_reponses(reponse.content.decode()) == 1


def test_le_filtre_texte_cherche_dans_la_reponse(admin_client, tenant):
    """Question texte : le filtre garde les réponses qui contiennent le texte (sans la casse).
    / Text question: the filter keeps answers containing the text (case-insensitive)."""
    evenement, _reservations = creer_un_evenement_avec_formulaire(
        tenant, [{"Allergies": "Gluten et noix"}, {"Allergies": "Arachides"}]
    )

    reponse = afficher_la_fiche_detail(
        admin_client, tenant, evenement, {"question_2": "GLU"}
    )

    assert nombre_de_lignes_reponses(reponse.content.decode()) == 1


def test_le_filtre_statut_ne_garde_que_les_billets_de_ce_statut(admin_client, tenant):
    """ticket_status = « S » (scanné) : aucun billet, ils sont tous « non scanné ».
    / ticket_status = "S": no ticket, they are all "not scanned"."""
    evenement, _reservations = creer_un_evenement_avec_formulaire(
        tenant, [{"Régime": "Végan"}]
    )

    reponse = afficher_la_fiche_detail(
        admin_client, tenant, evenement, {"ticket_status": "S"}
    )

    contenu = reponse.content.decode()
    assert nombre_de_lignes_billets(contenu) == 0
    assert 'data-testid="admin-event-detail-no-matching-tickets"' in contenu


def test_un_filtre_invalide_est_ignore(admin_client, tenant):
    """Une option inconnue, un statut inconnu ou une question inconnue n'empêchent pas l'affichage.
    / An unknown option, status or question does not break the page."""
    evenement, _reservations = creer_un_evenement_avec_formulaire(
        tenant, [{"Régime": "Végan"}, {"Régime": "Omnivore"}]
    )
    filtres_invalides = {
        "question_0": "Carnivore",
        "ticket_status": "ZZ",
        "question_99": "x",
    }

    reponse = afficher_la_fiche_detail(
        admin_client, tenant, evenement, filtres_invalides
    )

    assert reponse.status_code == 200
    assert nombre_de_lignes_reponses(reponse.content.decode()) == 2


def test_une_requete_de_filtre_htmx_ne_renvoie_que_les_resultats(admin_client, tenant):
    """Avec HX-Target = event-detail-results, la vue rend le partial, sans le formulaire de filtres.
    / With HX-Target = event-detail-results, the view renders the partial, without the filters form."""
    evenement, _reservations = creer_un_evenement_avec_formulaire(
        tenant, [{"Régime": "Végan"}]
    )

    reponse = afficher_la_fiche_detail(
        admin_client,
        tenant,
        evenement,
        {"question_0": "Végan"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="event-detail-results",
    )

    contenu = reponse.content.decode()
    assert 'id="event-detail-results"' in contenu
    assert 'data-testid="admin-event-detail-filters"' not in contenu


def test_une_reponse_avec_du_html_est_echappee(admin_client, tenant):
    """Une réponse contenant une balise <script> est affichée comme du texte.
    / An answer containing a <script> tag is shown as text."""
    evenement, _reservations = creer_un_evenement_avec_formulaire(
        tenant, [{"Allergies": "<script>alert(1)</script>"}]
    )

    reponse = afficher_la_fiche_detail(admin_client, tenant, evenement)

    contenu = reponse.content.decode()
    assert "<script>alert(1)</script>" not in contenu
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in contenu


def test_la_fiche_est_interdite_aux_visiteurs_non_admin(tenant):
    """Un visiteur anonyme ne voit pas les données des acheteurs.
    / An anonymous visitor cannot see buyers' data."""
    from django.test import Client as DjangoClient

    evenement, _reservations = creer_un_evenement_avec_formulaire(
        tenant, [{"Allergies": "Arachides"}]
    )
    client_anonyme = DjangoClient(HTTP_HOST="lespass.tibillet.localhost")

    reponse = afficher_la_fiche_detail(client_anonyme, tenant, evenement)

    assert reponse.status_code in [401, 403]
    assert "Arachides" not in reponse.content.decode()


def test_la_fiche_est_une_page_complete_de_l_admin(admin_client, tenant):
    """Sans HTMX, la fiche est une page complète (gabarit de l'admin) : retour et rafraîchissement marchent.
    / Without HTMX, the detail is a full admin page: back and refresh work."""
    evenement, _reservations = creer_un_evenement_avec_formulaire(
        tenant, [{"Régime": "Végan"}]
    )

    reponse = afficher_la_fiche_detail(admin_client, tenant, evenement)

    contenu = reponse.content.decode()
    assert "<html" in contenu
    assert 'data-testid="admin-event-detail"' in contenu
    assert 'hx-replace-url="true"' in contenu


def test_les_filtres_dans_l_adresse_sont_reappliques_a_l_ouverture(
    admin_client, tenant
):
    """Ouvrir l'adresse avec des filtres (après un « retour ») réapplique les filtres et les réaffiche.
    / Opening the URL with filters (after "back") re-applies and re-shows them."""
    evenement, _reservations = creer_un_evenement_avec_formulaire(
        tenant, [{"Régime": "Végan"}, {"Régime": "Omnivore"}]
    )

    reponse = afficher_la_fiche_detail(
        admin_client, tenant, evenement, {"question_0": "Végan"}
    )

    contenu = reponse.content.decode()
    assert nombre_de_lignes_reponses(contenu) == 1
    assert '<option value="Végan" selected>' in contenu


def test_la_fiche_d_un_evenement_a_un_bouton_vers_le_detail(admin_client, tenant):
    """En haut de la fiche d'un évènement, un lien mène à la fiche de détail.
    / At the top of an event change form, a link leads to the detail page."""
    from django.urls import reverse

    evenement, _reservations = creer_un_evenement_avec_formulaire(
        tenant, [{"Régime": "Végan"}]
    )

    with tenant_context(tenant):
        reponse = admin_client.get(
            reverse("staff_admin:BaseBillet_event_change", args=[evenement.pk])
        )

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert 'data-testid="event-change-form-detail-link"' in contenu
    assert f"/event/{evenement.pk}/admin_show_event_detail/" in contenu


def test_la_page_d_ajout_d_un_evenement_n_a_pas_de_bouton_vers_le_detail(
    admin_client, tenant
):
    """Sur la page d'ajout, l'évènement n'existe pas encore : pas de bouton.
    / On the add page, the event does not exist yet: no button."""
    from django.urls import reverse

    with tenant_context(tenant):
        reponse = admin_client.get(reverse("staff_admin:BaseBillet_event_add"))

    assert 'data-testid="event-change-form-detail-link"' not in reponse.content.decode()


def test_le_bouton_voir_de_la_liste_est_un_lien_classique(admin_client, tenant):
    """Le bouton « Voir » de la liste est un vrai lien (href), sans HTMX vers #content.
    / The list "Voir" button is a real link (href), without HTMX to #content."""
    from django.urls import reverse

    evenement, _reservations = creer_un_evenement_avec_formulaire(
        tenant, [{"Régime": "Végan"}]
    )

    with tenant_context(tenant):
        reponse = admin_client.get(
            reverse("staff_admin:BaseBillet_event_changelist"), {"q": evenement.name}
        )

    contenu = reponse.content.decode()
    assert f"href='/event/{evenement.pk}/admin_show_event_detail/'" in contenu
    assert "hx-get='/event/" not in contenu
