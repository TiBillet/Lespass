"""
Tests E2E : le planning des bénévoles dans un vrai navigateur.
/ E2E tests: the volunteer planning in a real browser.

LOCALISATION : tests/e2e/test_benevolat_flow.py

Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§5.2 à §5.4, §8)

Chaque test crée SON planning (slug unique) par django_shell, et le supprime à la fin
(besoins et inscriptions partent avec lui).
/ Each test creates ITS planning and deletes it at the end.

Ce qui est vérifié ici, et que les tests pytest ne voient pas :
- htmx remplace la zone du planning sans recharger la page ;
- la fenêtre <dialog> s'ouvre, met le curseur dans le champ, « Annuler » ne crée rien ;
- une réponse 422 est bien affichée (écouteur htmx:beforeOnLoad de planning.html) ;
- la vue mobile (375 px) : liste par jour, aucun défilement horizontal de la page.

Lancer / Run : make e2e-visible benevolat
"""

import json
import uuid

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.benevolat]


@pytest.fixture
def planning(django_shell):
    """
    Un planning publié, une tâche, un besoin dans 5 jours (18h–21h, 1 personne souhaitée).
    Rend un dict : slug, uuid du besoin, date du besoin (AAAA-MM-JJ).
    / A published planning with one need in 5 days.
    """
    identifiant = uuid.uuid4().hex[:8]
    sortie = django_shell(
        "import datetime, json\n"
        "from django.utils import timezone\n"
        "from BaseBillet.models import Configuration\n"
        "from booking.models import BesoinBenevole, PlanningBenevole, TacheBenevole\n"
        "fuseau = Configuration.get_solo().get_tzinfo()\n"
        "jour = timezone.now().astimezone(fuseau).date() + datetime.timedelta(days=5)\n"
        f"planning = PlanningBenevole.objects.create(name='E2E planning {identifiant}',\n"
        f"    slug='e2e-benevolat-{identifiant}', published=True)\n"
        f"tache = TacheBenevole.objects.create(name='E2E bar {identifiant}')\n"
        "besoin = BesoinBenevole.objects.create(planning=planning, tache=tache, date=jour,\n"
        "    heure_debut=datetime.time(18, 0), heure_fin=datetime.time(21, 0), nombre_souhaite=1)\n"
        "print(json.dumps({'slug': planning.slug, 'besoin': str(besoin.pk),\n"
        "    'jour': jour.isoformat(), 'tache': str(tache.pk)}))\n"
    )
    donnees = json.loads(sortie)
    yield donnees
    django_shell(
        "from booking.models import PlanningBenevole, TacheBenevole\n"
        f"PlanningBenevole.objects.filter(slug='{donnees['slug']}').delete()\n"
        f"TacheBenevole.objects.filter(pk='{donnees['tache']}').delete()\n"
    )


def creer_un_benevole(django_shell, prenom="Camille", nom="Martin"):
    """Crée un compte actif à l'email unique, avec ce prénom et ce nom. Rend l'email."""
    email = f"test+e2ebenevolat{uuid.uuid4().hex[:8]}@mock.test"
    django_shell(
        "from AuthBillet.utils import get_or_create_user\n"
        f"benevole = get_or_create_user('{email}', send_mail=False)\n"
        "benevole.is_active = True\n"
        f"benevole.first_name = '{prenom}'\n"
        f"benevole.last_name = '{nom}'\n"
        "benevole.save()\n"
    )
    return email


def nombre_d_inscriptions(django_shell, uuid_du_besoin):
    return int(django_shell(
        "from booking.models import InscriptionBenevole\n"
        f"print(InscriptionBenevole.objects.filter(besoin_id='{uuid_du_besoin}').count())\n"
    ))


def poser_un_temoin_de_rechargement(page):
    """Une variable JS qui disparaît si la page est rechargée. / A JS flag lost on reload."""
    page.evaluate("window.pas_de_rechargement = true")


def la_page_n_a_pas_ete_rechargee(page):
    return page.evaluate("window.pas_de_rechargement === true")


def test_je_viens_puis_me_retirer_sans_recharger(page, login_as, django_shell, planning):
    """
    « Je viens » : la case montre « Toi », l'en-tête du jour passe à « tout est couvert »,
    un toast s'affiche, sans recharger. « Me retirer » rend la case libre.
    """
    email = creer_un_benevole(django_shell)
    login_as(page, email)
    page.goto(f"/booking/benevolat/{planning['slug']}/")
    poser_un_temoin_de_rechargement(page)

    entete_du_jour = page.locator(f'[data-testid="benevolat-entete-jour-{planning["jour"]}"]')
    expect(entete_du_jour).to_contain_text("1 place libre")

    page.locator(f'[data-testid="benevolat-je-viens-{planning["besoin"]}"]').click()

    case = page.locator(f'[data-testid="benevolat-besoin-{planning["besoin"]}"]')
    expect(case).to_contain_text("Toi")
    expect(case).to_contain_text("Tu y es")
    # La zone est remplacée, mais le focus clavier reste sur le bouton d'action de la
    # case (même id) : il ne retombe pas en haut de la page.
    # / The zone is replaced, but keyboard focus stays on the cell's action button.
    expect(page.locator(f'#benevolat-action-{planning["besoin"]}')).to_be_focused()
    expect(entete_du_jour).to_contain_text("tout est couvert")
    expect(page.locator(".swal2-toast")).to_be_visible()
    assert la_page_n_a_pas_ete_rechargee(page)
    assert nombre_d_inscriptions(django_shell, planning["besoin"]) == 1

    page.locator(f'[data-testid="benevolat-retirer-{planning["besoin"]}"]').click()

    expect(page.locator(f'[data-testid="benevolat-je-viens-{planning["besoin"]}"]')).to_be_visible()
    expect(entete_du_jour).to_contain_text("1 place libre")
    assert la_page_n_a_pas_ete_rechargee(page)
    assert nombre_d_inscriptions(django_shell, planning["besoin"]) == 0


def test_la_fenetre_du_nom_s_ouvre_s_annule_puis_inscrit(page, login_as, django_shell, planning):
    """
    Compte sans prénom ni nom : la fenêtre s'ouvre, le curseur est dans « Prénom »,
    « Annuler » ne crée rien. Remplie et envoyée : elle se ferme et la case montre « Toi ».
    """
    email = creer_un_benevole(django_shell, prenom="", nom="")
    login_as(page, email)
    page.goto(f"/booking/benevolat/{planning['slug']}/")

    bouton_je_viens = page.locator(f'[data-testid="benevolat-je-viens-{planning["besoin"]}"]')
    fenetre = page.locator('[data-testid="benevolat-modale-prenom"]')

    bouton_je_viens.click()
    expect(fenetre).to_be_visible()
    expect(page.locator('[data-testid="benevolat-prenom"]')).to_be_focused()

    page.locator('[data-testid="benevolat-modale-annuler"]').click()
    expect(fenetre).to_be_hidden()
    assert nombre_d_inscriptions(django_shell, planning["besoin"]) == 0

    bouton_je_viens.click()
    expect(fenetre).to_be_visible()
    page.locator('[data-testid="benevolat-prenom"]').fill("Camille")
    page.locator('[data-testid="benevolat-nom"]').fill("Martin")
    page.locator('[data-testid="benevolat-modale-enregistrer"]').click()

    expect(fenetre).to_be_hidden()
    expect(page.locator(f'[data-testid="benevolat-besoin-{planning["besoin"]}"]')).to_contain_text("Toi")
    assert nombre_d_inscriptions(django_shell, planning["besoin"]) == 1


def test_un_refus_422_est_affiche(page, login_as, django_shell, planning):
    """
    La page est ouverte, puis le planning devient réservé aux adhérent·es. Le clic sur
    « Je viens » reçoit une 422 : la zone recalculée s'affiche (badge « Réservé »).
    / The planning becomes members-only after page load: the 422 zone is swapped in.
    """
    email = creer_un_benevole(django_shell)
    login_as(page, email)
    page.goto(f"/booking/benevolat/{planning['slug']}/")

    django_shell(
        "from BaseBillet.models import Product\n"
        "from booking.models import PlanningBenevole\n"
        "adhesion = Product.objects.filter(categorie_article=Product.ADHESION).first()\n"
        "assert adhesion is not None, 'il faut une adhésion sur le lieu lespass'\n"
        f"PlanningBenevole.objects.get(slug='{planning['slug']}').adhesions_requises.add(adhesion)\n"
    )

    with page.expect_response(lambda reponse: "/inscrire/" in reponse.url) as attente:
        page.locator(f'[data-testid="benevolat-je-viens-{planning["besoin"]}"]').click()
    assert attente.value.status == 422

    expect(page.locator(f'[data-testid="benevolat-besoin-{planning["besoin"]}"]')).to_contain_text(
        "Réservé aux adhérent·es"
    )
    assert nombre_d_inscriptions(django_shell, planning["besoin"]) == 0


def test_la_vue_mobile_est_une_liste_sans_defilement_horizontal(page, django_shell, planning):
    """375 px : la grille est cachée, la barre de jours et la liste sont là, la page ne
    défile pas à l'horizontale."""
    page.set_viewport_size({"width": 375, "height": 800})
    page.goto(f"/booking/benevolat/{planning['slug']}/")

    expect(page.locator('[data-testid="benevolat-grille"]')).to_be_hidden()
    expect(page.locator('[data-testid="benevolat-barre-jours"]')).to_be_visible()
    expect(page.locator(f'[data-testid="benevolat-jour-mobile-{planning["jour"]}"]')).to_be_visible()
    expect(page.locator(f'[data-testid="benevolat-besoin-mobile-{planning["besoin"]}"]')).to_be_visible()

    largeur_de_la_page = page.evaluate("document.documentElement.scrollWidth")
    largeur_de_l_ecran = page.evaluate("window.innerWidth")
    assert largeur_de_la_page <= largeur_de_l_ecran


def test_semaine_suivante_sans_recharger_puis_retour_arriere(page, django_shell, planning):
    """
    §11.1 : « Semaine suivante » remplace la zone sans recharger et met ?semaine= dans
    l'adresse. Le retour arrière du navigateur ramène la première semaine.
    / "Next week" swaps the zone without reload and pushes ?semaine=; Back restores it.
    """
    besoin_de_la_semaine_d_apres = django_shell(
        "import datetime\n"
        "from booking.models import BesoinBenevole\n"
        f"premier = BesoinBenevole.objects.get(pk='{planning['besoin']}')\n"
        "besoin = BesoinBenevole.objects.create(planning=premier.planning, tache=premier.tache,\n"
        "    date=premier.date + datetime.timedelta(days=7), nombre_souhaite=1)\n"
        "print(besoin.pk)\n"
    )
    page.goto(f"/booking/benevolat/{planning['slug']}/")
    poser_un_temoin_de_rechargement(page)

    premier_besoin = page.locator(f'[data-testid="benevolat-besoin-{planning["besoin"]}"]')
    second_besoin = page.locator(f'[data-testid="benevolat-besoin-{besoin_de_la_semaine_d_apres}"]')
    expect(premier_besoin).to_be_visible()
    expect(second_besoin).to_have_count(0)

    page.locator('[data-testid="benevolat-semaine-suivante"]').click()

    expect(second_besoin).to_be_visible()
    expect(premier_besoin).to_have_count(0)
    expect(page.locator('[data-testid="benevolat-semaine-precedente"]')).to_be_visible()
    # Le focus va sur le titre de la nouvelle semaine (lecteur d'écran).
    # / Focus lands on the new week's title (screen reader).
    expect(page.locator('[data-testid="benevolat-semaine-titre"]')).to_be_focused()
    assert "?semaine=" in page.url
    assert la_page_n_a_pas_ete_rechargee(page)

    page.go_back()

    expect(premier_besoin).to_be_visible()
    expect(second_besoin).to_have_count(0)
    assert "?semaine=" not in page.url


def creer_une_personne_du_lieu(django_shell, prenom, nom="Equipe"):
    """Un compte rattaché au lieu (client_achat), avec ce prénom. Rend son pk."""
    return django_shell(
        "from AuthBillet.utils import get_or_create_user\n"
        f"personne = get_or_create_user('test+e2eequipe{uuid.uuid4().hex[:8]}@mock.test', send_mail=False)\n"
        f"personne.first_name = {prenom!r}\n"
        f"personne.last_name = {nom!r}\n"
        "personne.save()\n"
        "print(personne.pk)\n"
    )


def test_l_equipe_inscrit_quelqu_un_par_la_recherche(page, login_as_admin, django_shell, planning):
    """
    Admin du lieu : « Inscrire quelqu'un » → 2 lettres → la personne sort → « Inscrire » →
    confirmation acceptée → la case montre son nom, la fenêtre se ferme, sans recharger (§5.10).
    Le NOM de la personne contient du HTML piégé : le toast doit l'afficher en texte,
    sans l'exécuter (SweetAlert, titleText).
    / The person's last name carries trapped HTML: the toast must show it as text.
    """
    prenom_unique = f"Zelie{uuid.uuid4().hex[:5]}"
    nom_piege = '<img src=x onerror="window.xss_execute=1">'
    pk_de_la_personne = creer_une_personne_du_lieu(django_shell, prenom_unique, nom_piege)
    login_as_admin(page)
    page.goto(f"/booking/benevolat/{planning['slug']}/")
    poser_un_temoin_de_rechargement(page)

    page.locator(f'[data-testid="benevolat-inscrire-quelquun-{planning["besoin"]}"]').click()
    fenetre = page.locator('[data-testid="benevolat-modale-prenom"]')
    expect(fenetre).to_be_visible()

    page.locator('[data-testid="benevolat-recherche-personne"]').fill(prenom_unique[:6])
    bouton_inscrire = page.locator(f'[data-testid="benevolat-inscrire-personne-{pk_de_la_personne}"]')
    expect(bouton_inscrire).to_be_visible()
    page.once("dialog", lambda fenetre_de_confirmation: fenetre_de_confirmation.accept())
    bouton_inscrire.click()

    expect(fenetre).to_be_hidden()
    expect(page.locator(f'[data-testid="benevolat-besoin-{planning["besoin"]}"]')).to_contain_text(prenom_unique)
    toast = page.locator(".swal2-toast")
    expect(toast).to_contain_text("onerror")
    assert page.evaluate("window.xss_execute === undefined")
    assert la_page_n_a_pas_ete_rechargee(page)
    assert nombre_d_inscriptions(django_shell, planning["besoin"]) == 1


def test_annuler_la_confirmation_n_inscrit_personne(page, login_as_admin, django_shell, planning):
    """Le clic « Inscrire » demande confirmation : « Annuler » ne crée rien, n'envoie rien."""
    prenom_unique = f"Zoe{uuid.uuid4().hex[:5]}"
    pk_de_la_personne = creer_une_personne_du_lieu(django_shell, prenom_unique)
    login_as_admin(page)
    page.goto(f"/booking/benevolat/{planning['slug']}/")

    page.locator(f'[data-testid="benevolat-inscrire-quelquun-{planning["besoin"]}"]').click()
    page.locator('[data-testid="benevolat-recherche-personne"]').fill(prenom_unique[:6])
    bouton_inscrire = page.locator(f'[data-testid="benevolat-inscrire-personne-{pk_de_la_personne}"]')
    expect(bouton_inscrire).to_be_visible()
    page.once("dialog", lambda fenetre_de_confirmation: fenetre_de_confirmation.dismiss())
    bouton_inscrire.click()

    page.wait_for_timeout(800)
    assert nombre_d_inscriptions(django_shell, planning["besoin"]) == 0
