"""
Tests E2E : popup de participation crowds (pro-bono + règles de contribution).
/ E2E tests: crowds participation popup (pro-bono + contribution covenant).

Conversion de tests/playwright/tests/23-crowds-participation.spec.ts

Flow testé / Tested flow:
1. Connexion admin, navigation vers la liste /crowd/
2. Ouverture du détail d'une initiative à budget contributif
3. Ouverture du popup SweetAlert2 de participation
4. Validation des éléments du popup (lien règles, toggle pro-bono, montant caché)
5. Toggle pro-bono → le champ montant apparaît
6. Soumission sans accepter les règles → message de validation
7. Acceptation des règles + montant → soumission OK
8. Vérification de la participation dans la liste
9. Marquage "terminé" avec durée (1 jour) → durée affichée

Adaptation vs le spec TS : le spec original cliquait sur le PREMIER lien
"Détails" de la liste (fragile : la première initiative n'a pas forcément
de budget contributif). Ici on crée une initiative dédiée avec un nom
unique via django_shell, puis on cible sa card via [data-initiative=uuid].
/ Adaptation vs the TS spec: the original clicked the FIRST "Détails" link
(fragile: first initiative may lack a contributive budget). Here we create
a dedicated initiative with a unique name via django_shell, then target
its card via [data-initiative=uuid].
"""

import random
import re
import string

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


def _random_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


class TestCrowdsParticipation:
    """Popup participation crowds / Crowds participation popup."""

    def test_pro_bono_toggle_and_covenant_requirement_then_mark_completed(
        self, page, login_as_admin, django_shell
    ):
        """Valide le toggle pro-bono, l'exigence des règles, la soumission
        et le marquage 'terminé' avec durée.
        / Validates pro-bono toggle, covenant requirement, submission and
        'mark as completed' with duration.
        """
        random_id = _random_id()
        initiative_name = f"E2E Crowd Participation {random_id}"
        participation_desc = f"Test participation E2E {random_id}"

        # --- Étape 0 : Créer une initiative à budget contributif ---
        # Le bouton "Participer" n'apparaît que si budget_contributif=True
        # et initiative non clôturée (crowds/templates/crowds/views/detail.html).
        # DB dev partagée : nom unique, pas de rollback.
        # / Step 0: create an initiative with contributive budget enabled.
        # The "Participer" button only shows when budget_contributif=True.
        result = django_shell(
            "from crowds.models import Initiative; "
            f"ini = Initiative.objects.create(name='{initiative_name}', "
            "budget_contributif=True); "
            "print('uuid=' + str(ini.uuid))"
        )
        uuid_match = re.search(r"uuid=([0-9a-f-]+)", result)
        assert uuid_match, f"Création initiative échouée : {result}"
        initiative_uuid = uuid_match.group(1)

        # --- Étape 1 : Connexion admin / Step 1: login as admin ---
        login_as_admin(page)

        # --- Étape 2 : Aller sur la liste crowds / Step 2: go to crowds list ---
        # networkidle OK sur les pages TiBillet (jamais sur Stripe — piège 9.28).
        # / networkidle is fine on TiBillet pages (never on Stripe — trap 9.28).
        page.goto("/crowd/")
        page.wait_for_load_state("networkidle")

        # --- Étape 3 : Ouvrir le détail de NOTRE initiative ---
        # La card porte data-initiative="<uuid>" (crowds/partial/card.html).
        # On clique son lien "Détails" (FR) ou "Details" (EN) — piège 9.34.
        # / Step 3: open OUR initiative details. The card carries
        # data-initiative="<uuid>"; click its "Détails"/"Details" link.
        card = page.locator(f'[data-initiative="{initiative_uuid}"]')
        expect(card).to_be_visible()
        details_link = card.locator(
            'a:has-text("Détails"), a:has-text("Details")'
        ).first
        expect(details_link).to_be_visible()
        details_link.click()

        # Le lien est un hx-get avec hx-push-url : on attend l'URL du détail.
        # wait_for_url : le callback reçoit une STRING (piège 9.29).
        # Le détail vit sous /contrib/<uuid>/ (crowds.urls inclus sous
        # 'contrib/' dans urls_tenants.py) — on tolère /crowd/ et /contrib/.
        # / The link is an hx-get with hx-push-url: wait for the detail URL.
        # wait_for_url: callback receives a STRING (trap 9.29).
        # Detail lives under /contrib/<uuid>/ (crowds.urls mounted on
        # 'contrib/' in urls_tenants.py) — accept both /crowd/ and /contrib/.
        page.wait_for_url(
            lambda url: f"/crowd/{initiative_uuid}" in url
            or f"/contrib/{initiative_uuid}" in url
        )
        page.wait_for_load_state("networkidle")
        assert initiative_uuid in page.url

        # --- Étape 4 : Ouvrir le popup de participation ---
        # / Step 4: open the participation popup
        participate_button = page.locator(
            'button:has-text("Participer"), button:has-text("Participate")'
        ).first
        expect(participate_button).to_be_visible()
        participate_button.click()

        popup = page.locator(".swal2-popup")
        expect(popup).to_be_visible()

        # --- Étape 5 : Valider les éléments du popup ---
        # Lien vers les règles de contribution : sélecteur souple
        # (movilab.org par défaut, ou texte FR/EN traduit).
        # / Step 5: validate popup elements. Covenant link: flexible
        # selector (movilab.org by default, or translated FR/EN text).
        covenant_link = popup.locator(
            'a[href*="movilab.org"], a:has-text("Règles"), a:has-text("Covenant")'
        )
        expect(covenant_link).to_be_visible()
        expect(covenant_link).to_have_attribute("target", "_blank")

        pro_bono_toggle = popup.locator("#part-pro-bono")
        amount_wrap = popup.locator("#part-amt-wrap")

        # Au départ : pro-bono coché, montant caché (display: none).
        # / Initially: pro-bono checked, amount hidden (display: none).
        expect(pro_bono_toggle).to_be_checked()
        expect(amount_wrap).to_be_hidden()

        # --- Étape 6 : Désactiver pro-bono → le montant apparaît ---
        # / Step 6: toggle pro-bono off → amount field appears
        pro_bono_toggle.click()
        expect(pro_bono_toggle).not_to_be_checked()
        expect(amount_wrap).to_be_visible()

        # --- Étape 7 : Envoyer SANS accepter les règles → validation ---
        # Le preConfirm SweetAlert2 affiche un message si #part-covenant
        # n'est pas coché.
        # / Step 7: submit WITHOUT accepting the covenant → validation.
        # SweetAlert2 preConfirm shows a message when #part-covenant
        # is unchecked.
        popup.locator("#part-desc").fill(participation_desc)
        popup.locator(".swal2-confirm").click()

        validation_message = popup.locator(".swal2-validation-message")
        expect(validation_message).to_be_visible()

        # --- Étape 8 : Accepter les règles + montant → envoi OK ---
        # Le preConfirm POSTe via htmx.ajax sur #participations_list
        # puis ferme le popup.
        # / Step 8: accept covenant + amount → submission OK.
        # preConfirm POSTs via htmx.ajax to #participations_list then closes.
        popup.locator("#part-covenant").check()
        popup.locator("#part-amt").fill("10")
        popup.locator(".swal2-confirm").click()

        expect(popup).to_be_hidden()

        # --- Étape 9 : Vérifier la participation dans la liste ---
        # La description unique (ou le libellé Pro-bono) doit apparaître.
        # Assertion tolérante FR/EN — piège 9.34.
        # / Step 9: verify the participation in the list. The unique
        # description (or the Pro-bono label) must appear. FR/EN tolerant.
        participations_list = page.locator("#participations_list")
        expect(participations_list).to_contain_text(
            re.compile(rf"Pro-bono|{re.escape(participation_desc)}", re.I)
        )

        # --- Étape 10 : Marquer la participation comme terminée ---
        # Bouton FR "Marquer terminé" / EN "Mark as completed".
        # / Step 10: mark the participation as completed.
        mark_button = page.locator(
            'button:has-text("Marquer terminé"), '
            'button:has-text("Mark as completed")'
        ).first
        expect(mark_button).to_be_visible()
        mark_button.click()

        completion_popup = page.locator(".swal2-popup")
        expect(completion_popup).to_be_visible()
        expect(completion_popup.locator("#part-time-unit")).to_be_visible()

        # 1 jour = 480 minutes (journée de 8h) côté JS.
        # / 1 day = 480 minutes (8h workday) on the JS side.
        completion_popup.locator("#part-time-value").fill("1")
        completion_popup.locator("#part-time-unit").select_option("days")
        completion_popup.locator(".swal2-confirm").click()

        expect(completion_popup).to_be_hidden()

        # --- Étape 11 : Vérifier la durée affichée ---
        # Le filtre minutes_to_human rend "1 j" (FR) ou "1 d" (EN) — piège 9.34.
        # / Step 11: verify displayed duration. minutes_to_human renders
        # "1 j" (FR) or "1 d" (EN) — trap 9.34.
        expect(participations_list).to_contain_text(
            re.compile(r"1 j|1 d", re.I)
        )
