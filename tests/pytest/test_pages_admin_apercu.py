"""
Tests de l'apercu des blocs dans l'admin et des editeurs de lignes.
/ Tests of the admin block preview and the line editors.

LOCALISATION : tests/pytest/test_pages_admin_apercu.py

Couvre :
- pages/editeur_items.py : lecture et nettoyage des lignes (sans base) ;
- pages/admin_apercu.py : apercu en direct, apercu enregistre, liste des blocs
  de la fiche Page, deplacement et suppression ;
- pages/admin.py : enregistrement des editeurs de lignes et insertion d'un
  bloc a une position donnee.
Pattern : base dev live (pas de rollback). Les pages de test ont un slug
prefixe « pytest-apercu- » et sont supprimees apres chaque test.
/ Pattern: live dev DB (no rollback). Test pages use a "pytest-apercu-" slug
prefix and are deleted after each test.
"""

import pytest
from django.http import QueryDict
from django.urls import reverse
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db

PREFIXE_SLUG = "pytest-apercu-"


@pytest.fixture
def nettoyer_pages_apercu(tenant):
    """
    Supprime les pages de test apres le test (leurs blocs partent avec elles).
    / Deletes test pages after the test (their blocks go with them).
    """
    yield
    from pages.models import Page

    with tenant_context(tenant):
        pages_de_test = Page.objects.filter(slug__startswith=PREFIXE_SLUG)
        pages_de_test.update(parent=None)
        pages_de_test.delete()


def skin_du_document(contenu):
    """
    Reconnait le skin d'un document d'apercu a sa feuille de style propre.
    Le contenu peut etre echappe (srcdoc) : on le decode d'abord.
    / Recognises a preview document's skin from its own stylesheet.
    """
    import html

    texte = html.unescape(contenu)
    if "V2/css/V2.css" in texte:
        return "V2"
    if "faire_festival/css/faire_festival.css" in texte:
        return "faire_festival"
    if "pages/css/tb-blocs.css" in texte:
        return "classic"
    return "inconnu"


def _creer_page(tenant, suffixe):
    from pages.models import Page

    with tenant_context(tenant):
        return Page.objects.create(titre=f"Pytest apercu {suffixe}", slug=f"{PREFIXE_SLUG}{suffixe}")


# ---------------------------------------------------------------------------
# editeur_items : sans base / no database
# ---------------------------------------------------------------------------
def test_lire_lignes_garde_l_ordre_du_formulaire():
    """Les valeurs repetees sont reassemblees ligne par ligne, dans l'ordre."""
    from pages.editeur_items import CLES_POINTS_GPS, lire_lignes_depuis_post

    donnees = QueryDict(mutable=True)
    donnees.setlist("gps__lat", ["1", "2"])
    donnees.setlist("gps__lng", ["3", "4"])
    donnees.setlist("gps__label", ["A", "B"])

    lignes = lire_lignes_depuis_post(donnees, "gps", CLES_POINTS_GPS)

    assert lignes == [
        {"lat": "1", "lng": "3", "label": "A"},
        {"lat": "2", "lng": "4", "label": "B"},
    ]


def test_nettoyer_contenu_lieu_retire_les_lignes_vides_et_decoupe_les_transports():
    """Une ligne vide disparait ; les lignes d'un transport deviennent une liste."""
    from pages.editeur_items import nettoyer_contenu_lieu

    items, erreurs = nettoyer_contenu_lieu(
        [
            {"type": "horaire", "texte": " Mardi 10h ", "titre": "", "lignes": ""},
            {"type": "para", "texte": "", "titre": "", "lignes": ""},
            {"type": "transport", "texte": "", "titre": "BUS", "lignes": "Ligne 37\n\n Ligne 12 "},
        ]
    )

    assert erreurs == []
    assert items == [
        {"type": "horaire", "texte": "Mardi 10h"},
        {"type": "transport", "titre": "BUS", "lignes": ["Ligne 37", "Ligne 12"]},
    ]


def test_nettoyer_contenu_lieu_refuse_un_type_inconnu():
    """Un type que le gabarit ne sait pas afficher est une erreur."""
    from pages.editeur_items import nettoyer_contenu_lieu

    items, erreurs = nettoyer_contenu_lieu([{"type": "pirate", "texte": "x"}])

    assert items == []
    assert len(erreurs) == 1


def test_nettoyer_contenu_cartes_vide_une_url_dangereuse():
    """Un lien javascript: est retire ; les cles vides ne sont pas stockees."""
    from pages.editeur_items import nettoyer_contenu_cartes

    items, erreurs = nettoyer_contenu_cartes(
        [{"titre": "Doc", "texte": "", "badge": "", "url": "javascript:alert(1)"}]
    )

    assert erreurs == []
    assert items == [{"titre": "Doc"}]


def test_nettoyer_points_gps_accepte_la_virgule_et_refuse_hors_bornes():
    """43,55 est accepte ; une latitude de 200 est une erreur."""
    from pages.editeur_items import nettoyer_points_gps

    items, erreurs = nettoyer_points_gps(
        [
            {"lat": "43,55", "lng": "1.48", "label": "La Cité"},
            {"lat": "200", "lng": "1", "label": ""},
            {"lat": "", "lng": "", "label": ""},
        ]
    )

    assert items == [{"lat": 43.55, "lng": 1.48, "label": "La Cité"}]
    assert len(erreurs) == 1


# ---------------------------------------------------------------------------
# Apercu en direct / Live preview
# ---------------------------------------------------------------------------
def _toutes_les_combinaisons():
    """Les couples (type, affichage) du catalogue ; "" pour un type a rendu unique."""
    from pages.blocs_catalogue import AFFICHAGES_PAR_TYPE

    combinaisons = []
    for type_bloc, affichages in AFFICHAGES_PAR_TYPE.items():
        if not affichages:
            combinaisons.append((type_bloc, ""))
        for affichage in affichages:
            combinaisons.append((type_bloc, affichage))
    return combinaisons


def test_apercu_en_direct_rend_chaque_combinaison_sur_chaque_skin(tenant, admin_client, nettoyer_pages_apercu):
    """
    Chaque couple (type, affichage) s'affiche en apercu sur les trois skins,
    DANS LE BON SKIN, et contient le titre saisi (quand le modele rend un
    titre : pas la citation, par exemple).

    Le skin est SIMULE (mock de get_skin_courant) : le test ne touche pas au
    skin de la base de dev, qu'un serveur ouvert en meme temps utiliserait.
    / The skin is MOCKED: the test never changes the dev DB skin.
    """
    from unittest import mock

    from pages.blocs_catalogue import CHAMPS_PAR_AFFICHAGE, CHAMPS_PAR_TYPE

    page = _creer_page(tenant, "combinaisons")
    url_apercu = reverse("staff_admin:pages_bloc_apercu")
    skin_attendu_par_skin = {"reunion": "classic", "V2": "V2", "faire_festival": "faire_festival"}

    for skin, skin_attendu in skin_attendu_par_skin.items():
        with mock.patch("BaseBillet.views.get_skin_courant", return_value=skin):
            for type_bloc, affichage in _toutes_les_combinaisons():
                reponse = admin_client.post(
                    url_apercu,
                    {
                        "modele": f"{type_bloc}:{affichage}",
                        "page": str(page.pk),
                        "titre": "Titre apercu pytest",
                        "texte": "Un texte",
                        "texte_markdown": "Un texte",
                        "hauteur_px": "600",
                        "nombre_max": "6",
                        # Images « choisies » : les modeles qui ne rendent rien
                        # sans image (ex. photo pleine largeur, ou le titre
                        # sert de texte alternatif) sont rendus avec leurs
                        # emplacements hachures.
                        # / "Chosen" images: models rendering nothing without
                        # an image are rendered with their placeholders.
                        "fichiers_choisis": "image,image_secondaire,auteur_photo",
                        # Une adresse a integrer : la newsletter ne rend rien sans.
                        # / An embed URL: the newsletter renders nothing without one.
                        "embed_url": "https://ghost.exemple.coop/",
                    },
                )
                contenu = reponse.content.decode()
                combinaison = (skin, type_bloc, affichage)
                assert reponse.status_code == 200, combinaison
                assert "bloc-apercu-iframe" in contenu, (combinaison, contenu[:400])
                assert skin_du_document(contenu) == skin_attendu, combinaison

                champs_rendus = CHAMPS_PAR_AFFICHAGE.get(type_bloc, {}).get(affichage, CHAMPS_PAR_TYPE[type_bloc])
                if "titre" in champs_rendus:
                    assert "Titre apercu pytest" in contenu, combinaison


def test_apercu_en_direct_affiche_le_titre_saisi(tenant, admin_client, nettoyer_pages_apercu):
    """Le titre tape (pas encore enregistre) apparait dans le document d'apercu."""
    page = _creer_page(tenant, "titre")

    reponse = admin_client.post(
        reverse("staff_admin:pages_bloc_apercu"),
        {
            "type_bloc": "SECTION",
            "affichage": "CARTE",
            "page": str(page.pk),
            "titre": "Mon atelier du jeudi",
        },
    )

    assert reponse.status_code == 200
    assert "Mon atelier du jeudi" in reponse.content.decode()


def test_apercu_en_direct_n_enregistre_rien(tenant, admin_client, nettoyer_pages_apercu):
    """L'apercu d'un bloc existant ne modifie pas le bloc en base."""
    from pages.models import Bloc

    page = _creer_page(tenant, "rien")
    with tenant_context(tenant):
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="Avant")

    admin_client.post(
        reverse("staff_admin:pages_bloc_apercu"),
        {"type_bloc": "FAQ", "page": str(page.pk), "titre": "Apres", "bloc_uuid": str(bloc.pk)},
    )

    with tenant_context(tenant):
        bloc.refresh_from_db()
        assert bloc.titre == "Avant"


def test_apercu_en_direct_retire_le_html_et_les_liens_dangereux(tenant, admin_client, nettoyer_pages_apercu):
    """Le script du texte et le lien javascript: ne passent pas dans l'apercu."""
    page = _creer_page(tenant, "xss")

    reponse = admin_client.post(
        reverse("staff_admin:pages_bloc_apercu"),
        {
            "type_bloc": "SECTION",
            "affichage": "CARTE",
            "page": str(page.pk),
            "titre": "Carte",
            "texte": "<p>ok</p><script>alert('pirate')</script>",
            "bouton_label": "Cliquer",
            "bouton_url": "javascript:alert(1)",
        },
    )

    contenu = reponse.content.decode()
    assert "alert(&#x27;pirate&#x27;)" not in contenu
    assert "alert(&amp;#x27;pirate" not in contenu
    assert "javascript:alert(1)" not in contenu


def test_apercu_en_direct_montre_les_lignes_de_l_editeur(tenant, admin_client, nettoyer_pages_apercu):
    """Les lignes d'une frise, pas encore enregistrees, sont dans l'apercu."""
    page = _creer_page(tenant, "frise")
    donnees = QueryDict(mutable=True)
    donnees.update({"type_bloc": "SECTION", "affichage": "FRISE", "page": str(page.pk)})
    donnees.setlist("contenu_cartes__titre", ["1987", "2024"])
    donnees.setlist("contenu_cartes__texte", ["Fondation", "Nouveau lieu"])
    donnees.setlist("contenu_cartes__badge", ["", ""])
    donnees.setlist("contenu_cartes__url", ["", ""])

    reponse = admin_client.post(reverse("staff_admin:pages_bloc_apercu"), donnees.urlencode(),
                                content_type="application/x-www-form-urlencoded")

    contenu = reponse.content.decode()
    assert "1987" in contenu
    assert "Nouveau lieu" in contenu


def test_apercu_en_direct_signale_un_point_gps_invalide(tenant, admin_client, nettoyer_pages_apercu):
    """Une latitude invalide donne un message, pas une erreur 500."""
    page = _creer_page(tenant, "gps")
    donnees = QueryDict(mutable=True)
    donnees.update({"type_bloc": "LIEU", "page": str(page.pk)})
    donnees.setlist("points_gps_editeur__lat", ["pas un nombre"])
    donnees.setlist("points_gps_editeur__lng", ["1"])
    donnees.setlist("points_gps_editeur__label", [""])

    reponse = admin_client.post(reverse("staff_admin:pages_bloc_apercu"), donnees.urlencode(),
                                content_type="application/x-www-form-urlencoded")

    assert reponse.status_code == 200
    assert "bloc-apercu-erreurs" in reponse.content.decode()


def test_les_vues_d_apercu_sont_refusees_sans_connexion(tenant, api_client, nettoyer_pages_apercu):
    """Une personne non connectee n'obtient ni apercu ni liste de blocs."""
    from pages.models import Bloc

    page = _creer_page(tenant, "anonyme")
    with tenant_context(tenant):
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="Secret")

    reponses = [
        api_client.post(reverse("staff_admin:pages_bloc_apercu"), {"type_bloc": "FAQ", "page": str(page.pk)}),
        api_client.get(reverse("staff_admin:pages_page_apercu", args=[page.pk])),
        api_client.post(reverse("staff_admin:pages_bloc_retirer", args=[bloc.pk])),
    ]

    for reponse in reponses:
        assert reponse.status_code in (302, 403)
    with tenant_context(tenant):
        assert Bloc.objects.filter(pk=bloc.pk).exists()


# ---------------------------------------------------------------------------
# Fiche Page : blocs rendus, deplacement, suppression
# / Page form: rendered blocks, move, delete
# ---------------------------------------------------------------------------
def test_fiche_page_contient_la_section_des_blocs(tenant, admin_client, nettoyer_pages_apercu):
    """La fiche d'une page existante charge la section « Contenu de la page »."""
    page = _creer_page(tenant, "fiche")

    reponse = admin_client.get(reverse("staff_admin:pages_page_change", args=[page.pk]))

    assert reponse.status_code == 200
    assert 'id="blocs-de-la-page"' in reponse.content.decode()


def test_fiche_page_a_une_seule_iframe(tenant, admin_client, nettoyer_pages_apercu):
    """Toute la page tient dans UNE iframe, quel que soit le nombre de blocs."""
    from pages.models import Bloc

    page = _creer_page(tenant, "une-iframe")
    with tenant_context(tenant):
        for rang in range(1, 4):
            Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre=f"Q{rang}", position=rang)

    contenu = admin_client.get(reverse("staff_admin:pages_page_change", args=[page.pk])).content.decode()

    assert contenu.count("data-apercu-iframe") == 1
    assert reverse("staff_admin:pages_page_apercu", args=[page.pk]) in contenu


def test_fiche_page_sans_bloc_invite_a_en_ajouter(tenant, admin_client, nettoyer_pages_apercu):
    """Une page vide n'affiche pas d'iframe, mais le menu « Ajouter un bloc en premier »."""
    page = _creer_page(tenant, "vide")

    contenu = admin_client.get(reverse("staff_admin:pages_page_change", args=[page.pk])).content.decode()

    assert "data-apercu-iframe" not in contenu
    assert 'data-testid="page-blocs-vide"' in contenu
    assert 'data-testid="page-ajouter-en-tete"' in contenu
    assert "inserer_apres=0" in contenu


def test_apercu_de_la_page_rend_tous_les_blocs_avec_leur_barre(tenant, admin_client, nettoyer_pages_apercu):
    """
    Le document de l'iframe contient chaque bloc, suivi d'un <template> qui
    porte sa barre d'actions (rang, modifier, menu d'ajout apres le bloc).
    """
    from pages.models import Bloc

    page = _creer_page(tenant, "document")
    with tenant_context(tenant):
        Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="Premiere question", position=1)
        Bloc.objects.create(page=page, type_bloc=Bloc.SECTION, affichage=Bloc.CARTE, titre="Une carte", position=2)

    reponse = admin_client.get(reverse("staff_admin:pages_page_apercu", args=[page.pk]))
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert reponse.get("X-Frame-Options") == "SAMEORIGIN"
    assert "Premiere question" in contenu and "Une carte" in contenu
    assert contenu.count("data-apercu-outils=") == 2
    assert 'data-testid="page-bloc-2-modifier"' in contenu
    # Le menu « + » n'est plus embarque : seule son URL de chargement l'est.
    # / The "+" menu is no longer embedded: only its loading URL is.
    assert "menu-ajout/?inserer_apres=2" in contenu
    assert reverse("staff_admin:pages_bloc_add") not in contenu
    assert "apercu_page_outils.js" in contenu


def test_deplacer_un_bloc_renumerote_meme_si_les_positions_sont_egales(tenant, admin_client, nettoyer_pages_apercu):
    """Trois blocs tous a 0 : descendre le premier le fait passer en deuxieme."""
    from pages.models import Bloc

    page = _creer_page(tenant, "deplacer")
    with tenant_context(tenant):
        bloc_a = Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="A", position=0)
        Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="B", position=0)
        Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="C", position=0)
        ordre_initial = list(page.blocs.order_by("position", "pk").values_list("titre", flat=True))

    premier_titre = ordre_initial[0]
    with tenant_context(tenant):
        premier_bloc = page.blocs.get(titre=premier_titre)

    reponse = admin_client.post(reverse("staff_admin:pages_bloc_deplacer", args=[premier_bloc.pk, "descendre"]))
    assert reponse.status_code == 200
    assert reponse["HX-Refresh"] == "true"

    with tenant_context(tenant):
        ordre = list(page.blocs.order_by("position").values_list("titre", flat=True))
        positions = list(page.blocs.order_by("position").values_list("position", flat=True))
    assert ordre == [ordre_initial[1], ordre_initial[0], ordre_initial[2]]
    assert positions == [1, 2, 3]
    assert bloc_a.pk  # le bloc existe toujours / block still exists


def test_retirer_un_bloc_depuis_la_page(tenant, admin_client, nettoyer_pages_apercu):
    """Le bouton 🗑 supprime le bloc et renumerote les autres."""
    from pages.models import Bloc

    page = _creer_page(tenant, "retirer")
    with tenant_context(tenant):
        Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="A", position=1)
        bloc_b = Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="B", position=2)
        Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="C", position=3)

    reponse = admin_client.post(reverse("staff_admin:pages_bloc_retirer", args=[bloc_b.pk]))

    assert reponse.status_code == 200
    assert reponse["HX-Refresh"] == "true"
    with tenant_context(tenant):
        assert list(page.blocs.order_by("position").values_list("titre", "position")) == [("A", 1), ("C", 2)]


# ---------------------------------------------------------------------------
# Fiche Bloc : enregistrement / Bloc form: saving
# ---------------------------------------------------------------------------
def _formulaire_d_ajout(page, type_bloc, affichage=""):
    """
    Donnees minimales valides du formulaire d'ajout d'un bloc. Le type et
    l'affichage passent par le select « Modele de bloc » ; les champs caches
    type_bloc / affichage restent vides, comme sans JavaScript.
    """
    donnees = QueryDict(mutable=True)
    donnees.update(
        {
            "modele": f"{type_bloc}:{affichage}",
            "type_bloc": "",
            "affichage": "",
            "page": str(page.pk),
            "titre": "Bloc pytest",
            "hauteur_px": "600",
            "nombre_max": "6",
            "_save": "Enregistrer",
        }
    )
    return donnees


def test_ajout_d_un_lieu_enregistre_les_lignes_en_json(tenant, admin_client, nettoyer_pages_apercu):
    """Les lignes des editeurs deviennent `contenu` et `points_gps`."""
    from pages.models import Bloc

    page = _creer_page(tenant, "lieu")
    donnees = _formulaire_d_ajout(page, "LIEU", "VERTICAL")
    donnees.setlist("contenu_lieu__type", ["badge", "transport"])
    donnees.setlist("contenu_lieu__texte", ["Nous trouver", ""])
    donnees.setlist("contenu_lieu__titre", ["", "BUS"])
    donnees.setlist("contenu_lieu__lignes", ["", "Ligne 37\nLigne 12"])
    donnees.setlist("points_gps_editeur__lat", ["43.5568"])
    donnees.setlist("points_gps_editeur__lng", ["1.4835"])
    donnees.setlist("points_gps_editeur__label", ["La Cité"])

    url_d_ajout = reverse("staff_admin:pages_bloc_add") + f"?page={page.pk}"
    reponse = admin_client.post(url_d_ajout, donnees.urlencode(),
                                content_type="application/x-www-form-urlencoded")

    assert reponse.status_code == 302, reponse.content.decode()[:2000]
    assert "#blocs-de-la-page" in reponse["Location"]
    with tenant_context(tenant):
        bloc = Bloc.objects.get(page=page)
        assert bloc.contenu == [
            {"type": "badge", "texte": "Nous trouver"},
            {"type": "transport", "titre": "BUS", "lignes": ["Ligne 37", "Ligne 12"]},
        ]
        assert bloc.points_gps == [{"lat": 43.5568, "lng": 1.4835, "label": "La Cité"}]


def test_modifier_une_carte_garde_son_contenu(tenant, admin_client, nettoyer_pages_apercu):
    """Une SECTION/CARTE ne lit pas `contenu` : l'enregistrer ne l'efface pas."""
    from pages.models import Bloc

    page = _creer_page(tenant, "carte")
    with tenant_context(tenant):
        bloc = Bloc.objects.create(
            page=page, type_bloc=Bloc.SECTION, affichage=Bloc.CARTE, contenu=[{"titre": "garde"}]
        )
    donnees = _formulaire_d_ajout(page, "SECTION", "CARTE")

    reponse = admin_client.post(reverse("staff_admin:pages_bloc_change", args=[bloc.pk]), donnees.urlencode(),
                                content_type="application/x-www-form-urlencoded")

    assert reponse.status_code == 302, reponse.content.decode()[:2000]
    with tenant_context(tenant):
        bloc.refresh_from_db()
        assert bloc.contenu == [{"titre": "garde"}]


def test_ajout_avec_inserer_apres_place_le_bloc_au_bon_endroit(tenant, admin_client, nettoyer_pages_apercu):
    """« + Ajouter un bloc ici » apres le bloc 1 : le nouveau bloc devient le 2e."""
    from pages.models import Bloc

    page = _creer_page(tenant, "inserer")
    with tenant_context(tenant):
        Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="A", position=1)
        Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="B", position=2)
    donnees = _formulaire_d_ajout(page, "FAQ")
    donnees["titre"] = "Nouveau"

    url_d_ajout = reverse("staff_admin:pages_bloc_add") + f"?page={page.pk}&inserer_apres=1"
    reponse = admin_client.post(url_d_ajout, donnees.urlencode(), content_type="application/x-www-form-urlencoded")

    assert reponse.status_code == 302, reponse.content.decode()[:2000]
    with tenant_context(tenant):
        ordre = list(page.blocs.order_by("position").values_list("titre", flat=True))
    assert ordre == ["A", "Nouveau", "B"]


def test_fiche_bloc_lieu_n_affiche_plus_de_json(tenant, admin_client, nettoyer_pages_apercu):
    """La fiche d'un LIEU montre les editeurs de lignes, remplis depuis la base."""
    from pages.models import Bloc

    page = _creer_page(tenant, "fiche-lieu")
    with tenant_context(tenant):
        bloc = Bloc.objects.create(
            page=page,
            type_bloc=Bloc.LIEU,
            contenu=[{"type": "horaire", "texte": "Mardi 10h"}],
            points_gps=[{"lat": 43.5, "lng": 1.4, "label": "Ici"}],
        )

    reponse = admin_client.get(reverse("staff_admin:pages_bloc_change", args=[bloc.pk]))
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert 'data-testid="editeur-lignes-contenu_lieu"' in contenu
    assert 'data-testid="editeur-lignes-points_gps_editeur"' in contenu
    assert "Mardi 10h" in contenu
    assert 'name="contenu"' not in contenu
    assert 'id="apercu-bloc"' in contenu
    # escapejs encode aussi les tirets (\u002D) : c'est du JS valide, qui donne
    # la meme chaine. / escapejs also encodes hyphens: same string in JS.
    from django.utils.html import escapejs

    assert f"bloc_uuid: '{escapejs(str(bloc.pk))}'" in contenu


# ---------------------------------------------------------------------------
# Champs caches : page du bloc, champs inutiles selon l'affichage ou le skin
# / Hidden fields: block page, fields useless for the affichage or skin
# ---------------------------------------------------------------------------
def test_ajout_sans_page_renvoie_vers_la_liste_des_pages(admin_client):
    """Sans ?page=, pas de formulaire d'ajout : on renvoie vers les pages."""
    for url in (
        reverse("staff_admin:pages_bloc_add"),
        reverse("staff_admin:pages_bloc_add") + "?page=pas-un-uuid",
    ):
        reponse = admin_client.get(url)
        assert reponse.status_code == 302
        assert reponse["Location"] == reverse("staff_admin:pages_page_changelist")


def test_fiche_bloc_n_a_plus_de_select_de_page(tenant, admin_client, nettoyer_pages_apercu):
    """La page du bloc est un champ cache, plus un select."""
    from pages.models import Bloc

    page = _creer_page(tenant, "sans-select")
    with tenant_context(tenant):
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="Q")

    contenu = admin_client.get(reverse("staff_admin:pages_bloc_change", args=[bloc.pk])).content.decode()

    assert '<select name="page"' not in contenu
    assert 'type="hidden" name="page"' in contenu


def test_modifier_un_bloc_ne_change_jamais_sa_page(tenant, admin_client, nettoyer_pages_apercu):
    """Une page postee a la main est ignoree : le champ est desactive."""
    from pages.models import Bloc

    page = _creer_page(tenant, "origine")
    autre_page = _creer_page(tenant, "autre")
    with tenant_context(tenant):
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="Q")
    donnees = _formulaire_d_ajout(autre_page, "FAQ")

    reponse = admin_client.post(reverse("staff_admin:pages_bloc_change", args=[bloc.pk]), donnees.urlencode(),
                                content_type="application/x-www-form-urlencoded")

    assert reponse.status_code == 302, reponse.content.decode()[:2000]
    with tenant_context(tenant):
        bloc.refresh_from_db()
        assert bloc.page_id == page.pk


def test_enregistrer_et_ajouter_un_nouveau_reste_dans_la_page(tenant, admin_client, nettoyer_pages_apercu):
    """« Enregistrer et ajouter un nouveau » garde la page et place le suivant apres."""
    page = _creer_page(tenant, "suivant")
    donnees = _formulaire_d_ajout(page, "FAQ")
    del donnees["_save"]
    donnees["_addanother"] = "1"

    reponse = admin_client.post(reverse("staff_admin:pages_bloc_add") + f"?page={page.pk}", donnees.urlencode(),
                                content_type="application/x-www-form-urlencoded")

    assert reponse.status_code == 302, reponse.content.decode()[:2000]
    assert f"page={page.pk}" in reponse["Location"]
    assert "inserer_apres=1" in reponse["Location"]


def test_images_du_lieu_visibles_seulement_pour_le_skin_qui_les_rend():
    """Le logo et le badge d'un LIEU ne s'affichent que pour faire_festival."""
    from pages.admin import _visibilite_des_champs

    visibilite = _visibilite_des_champs()

    assert "(type_bloc == 'LIEU' && ['faire_festival'].includes(skin_du_site))" in visibilite["image"]
    assert "includes(skin_du_site)" in visibilite["image_secondaire"]
    # Les autres types gardent leur image sans condition de skin.
    assert "(type_bloc == 'SECTION' &&" in visibilite["image"]


def test_page_a_lister_seulement_pour_une_liste_de_sous_pages():
    """« Page à lister » n'apparait que si la liste montre des sous-pages."""
    from pages.admin import _visibilite_des_champs

    assert _visibilite_des_champs()["page_source"] == "(type_bloc == 'LISTE' && source == 'SOUS_PAGES')"


def test_cles_des_sous_cartes_couvrent_les_affichages_qui_lisent_contenu():
    """
    Chaque affichage SECTION qui lit `contenu` declare ses cles d'element, et
    ces cles existent dans l'editeur. Sinon une ligne s'afficherait vide.
    """
    from pages.blocs_catalogue import CHAMPS_PAR_AFFICHAGE, CLES_ELEMENT_PAR_AFFICHAGE
    from pages.editeur_items import CLES_CONTENU_CARTES

    affichages_qui_lisent_contenu = set()
    for affichage, champs in CHAMPS_PAR_AFFICHAGE["SECTION"].items():
        if "contenu" in champs:
            affichages_qui_lisent_contenu.add(affichage)

    assert set(CLES_ELEMENT_PAR_AFFICHAGE) == affichages_qui_lisent_contenu
    for cles in CLES_ELEMENT_PAR_AFFICHAGE.values():
        assert set(cles) <= set(CLES_CONTENU_CARTES)


def test_la_frise_ne_propose_pas_de_badge():
    """L'expression du badge n'inclut pas FRISE ; celle du lien seulement RESSOURCES."""
    from pages.admin_widgets import EXPRESSIONS_DES_CLES_DE_CARTES

    assert "FRISE" not in EXPRESSIONS_DES_CLES_DE_CARTES["badge"]
    assert "['RESSOURCES']" in EXPRESSIONS_DES_CLES_DE_CARTES["url"]


# ---------------------------------------------------------------------------
# Modele de bloc : type + affichage en un seul choix
# / Block model: type + affichage as a single choice
# ---------------------------------------------------------------------------
def test_modeles_de_bloc_couvrent_tout_le_catalogue():
    """Chaque couple (type, affichage) du catalogue est un modele, une seule fois."""
    from pages.admin_apercu import modeles_de_bloc

    valeurs = []
    for groupe in modeles_de_bloc():
        for modele in groupe["modeles"]:
            valeurs.append(modele["valeur"])

    attendues = [f"{type_bloc}:{affichage}" for type_bloc, affichage in _toutes_les_combinaisons()]
    assert sorted(valeurs) == sorted(attendues)


def test_select_du_modele_groupe_les_affichages_par_type():
    """Un type a plusieurs affichages devient un groupe ; TEXTE reste une option simple."""
    from pages.admin import _choix_du_modele

    choix = dict(_choix_du_modele())

    assert "TEXTE:" in choix
    groupes = [options for options in choix.values() if isinstance(options, list)]
    valeurs_groupees = [valeur for options in groupes for valeur, libelle in options]
    assert "SECTION:CARTE" in valeurs_groupees
    assert "SECTION:" not in valeurs_groupees


def test_le_modele_fixe_type_et_affichage_meme_sans_javascript(tenant, admin_client, nettoyer_pages_apercu):
    """Champs caches vides (pas d'Alpine) : le modele suffit a enregistrer le bon type."""
    from pages.models import Bloc

    page = _creer_page(tenant, "modele")
    donnees = _formulaire_d_ajout(page, "SECTION", "CITATION")

    reponse = admin_client.post(reverse("staff_admin:pages_bloc_add") + f"?page={page.pk}", donnees.urlencode(),
                                content_type="application/x-www-form-urlencoded")

    assert reponse.status_code == 302, reponse.content.decode()[:2000]
    with tenant_context(tenant):
        bloc = Bloc.objects.get(page=page)
        assert (bloc.type_bloc, bloc.affichage) == ("SECTION", "CITATION")


def test_fiche_d_ajout_preselectionne_le_modele_de_l_url(tenant, admin_client, nettoyer_pages_apercu):
    """Les liens « + Ajouter » passent type et affichage : le select est pre-rempli."""
    page = _creer_page(tenant, "preselection")
    url = reverse("staff_admin:pages_bloc_add") + f"?page={page.pk}&type_bloc=IMAGES&affichage=GRILLE"

    contenu = admin_client.get(url).content.decode()

    assert '<option value="IMAGES:GRILLE" selected>' in contenu
    assert '<select name="type_bloc"' not in contenu
    assert '<select name="affichage"' not in contenu


def test_apercu_en_direct_lit_le_modele(tenant, admin_client, nettoyer_pages_apercu):
    """L'apercu suit le select « Modele », meme si les champs caches sont vides."""
    page = _creer_page(tenant, "apercu-modele")

    reponse = admin_client.post(
        reverse("staff_admin:pages_bloc_apercu"),
        {"modele": "SECTION:CITATION", "type_bloc": "", "affichage": "", "page": str(page.pk),
         "texte": "Une phrase marquante", "auteur_nom": "Camille"},
    )

    contenu = reponse.content.decode()
    assert "bloc-apercu-iframe" in contenu
    assert "Camille" in contenu


# ---------------------------------------------------------------------------
# Images de remplacement : image choisie mais pas encore envoyee
# / Placeholder images: image chosen but not uploaded yet
# ---------------------------------------------------------------------------
def test_image_choisie_affiche_un_emplacement_dans_l_apercu(tenant, admin_client, nettoyer_pages_apercu):
    """Un fichier choisi (pas envoye) devient une image de remplacement."""
    page = _creer_page(tenant, "image-choisie")

    reponse = admin_client.post(
        reverse("staff_admin:pages_bloc_apercu"),
        {"modele": "IMAGES:PLEINE_LARGEUR", "page": str(page.pk), "titre": "Photo",
         "fichiers_choisis": "image"},
    )

    assert "image_a_venir.svg" in reponse.content.decode()


def test_sans_fichier_choisi_pas_d_emplacement(tenant, admin_client, nettoyer_pages_apercu):
    """Sans fichier choisi, l'apercu n'invente pas d'image."""
    page = _creer_page(tenant, "sans-image")

    reponse = admin_client.post(
        reverse("staff_admin:pages_bloc_apercu"),
        {"modele": "IMAGES:PLEINE_LARGEUR", "page": str(page.pk), "titre": "Photo", "fichiers_choisis": ""},
    )

    assert "image_a_venir" not in reponse.content.decode()


def test_photo_d_auteur_choisie_a_un_emplacement_carre(tenant, admin_client, nettoyer_pages_apercu):
    """La photo d'une citation a son emplacement carre."""
    page = _creer_page(tenant, "citation-photo")

    reponse = admin_client.post(
        reverse("staff_admin:pages_bloc_apercu"),
        {"modele": "SECTION:CITATION", "page": str(page.pk), "texte": "Merci",
         "auteur_nom": "Camille", "fichiers_choisis": "auteur_photo"},
    )

    assert "image_a_venir_carree.svg" in reponse.content.decode()


def test_galerie_montre_les_nouvelles_lignes_de_l_encart(tenant, admin_client, nettoyer_pages_apercu):
    """
    Deux lignes neuves avec un fichier choisi dans « Images de galerie » :
    l'apercu de la grille montre deux emplacements. Une ligne neuve vide est
    ignoree.
    """
    from pages.models import Bloc

    page = _creer_page(tenant, "galerie")
    with tenant_context(tenant):
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.IMAGES, affichage=Bloc.GRILLE, titre="G")

    donnees = QueryDict(mutable=True)
    donnees.update({
        "modele": "IMAGES:GRILLE", "bloc_uuid": str(bloc.pk), "titre": "G",
        "images_galerie-TOTAL_FORMS": "3", "images_galerie-INITIAL_FORMS": "0",
        "images_galerie-0-id": "", "images_galerie-0-legende": "Premiere",
        "images_galerie-1-id": "", "images_galerie-1-legende": "Deuxieme",
        "images_galerie-2-id": "", "images_galerie-2-legende": "",
        "fichiers_choisis": "images_galerie-0-image,images_galerie-1-image",
    })

    reponse = admin_client.post(reverse("staff_admin:pages_bloc_apercu"), donnees.urlencode(),
                                content_type="application/x-www-form-urlencoded")

    contenu = reponse.content.decode()
    assert "bloc-apercu-iframe" in contenu
    assert contenu.count("image_a_venir.svg") >= 2
    with tenant_context(tenant):
        assert bloc.images_galerie.count() == 0  # rien n'est enregistre


def test_galerie_markdown_resout_une_image_choisie(tenant, admin_client, nettoyer_pages_apercu):
    """![x](galerie:1) dans un bloc TEXTE montre l'emplacement de l'image choisie."""
    from pages.models import Bloc

    page = _creer_page(tenant, "markdown-galerie")
    with tenant_context(tenant):
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.TEXTE, titre="Article")

    donnees = QueryDict(mutable=True)
    donnees.update({
        "modele": "TEXTE:", "bloc_uuid": str(bloc.pk), "texte_markdown": "Voici ![Photo](galerie:1)",
        "images_galerie-TOTAL_FORMS": "1", "images_galerie-0-id": "",
        "fichiers_choisis": "images_galerie-0-image",
    })

    reponse = admin_client.post(reverse("staff_admin:pages_bloc_apercu"), donnees.urlencode(),
                                content_type="application/x-www-form-urlencoded")

    contenu = reponse.content.decode()
    assert "image_a_venir.svg" in contenu
    assert "introuvable" not in contenu


def test_case_effacer_retire_l_image_de_l_apercu(tenant, admin_client, nettoyer_pages_apercu):
    """La case « Effacer » d'une image enregistree la retire de l'apercu."""
    from pages.admin_apercu import poser_les_images_de_remplacement
    from pages.models import Bloc

    bloc = Bloc(type_bloc=Bloc.IMAGES, affichage=Bloc.PLEINE_LARGEUR)
    bloc.image = "images/pages/existe.jpg"

    poser_les_images_de_remplacement(bloc, {"image-clear": "on", "fichiers_choisis": ""})

    assert not bloc.image


# ---------------------------------------------------------------------------
# Bouton « Retour a la page » / "Back to the page" button
# ---------------------------------------------------------------------------
def test_fiche_bloc_a_un_bouton_retour_a_la_page(tenant, admin_client, nettoyer_pages_apercu):
    """La fiche d'un bloc existant a un lien vers les blocs de sa page."""
    from pages.models import Bloc

    page = _creer_page(tenant, "retour")
    with tenant_context(tenant):
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="Q")

    contenu = admin_client.get(reverse("staff_admin:pages_bloc_change", args=[bloc.pk])).content.decode()

    url_attendue = reverse("staff_admin:pages_page_change", args=[page.pk]) + "#blocs-de-la-page"
    assert 'data-testid="bloc-retour-page"' in contenu
    assert f'href="{url_attendue}"' in contenu
    assert page.titre in contenu


def test_fiche_d_ajout_a_aussi_le_bouton_retour(tenant, admin_client, nettoyer_pages_apercu):
    """A l'ajout (depuis « + »), le bouton ramene a la page passee dans l'URL."""
    page = _creer_page(tenant, "retour-ajout")

    url = reverse("staff_admin:pages_bloc_add") + f"?page={page.pk}&type_bloc=FAQ"
    contenu = admin_client.get(url).content.decode()

    assert 'data-testid="bloc-retour-page"' in contenu
    assert reverse("staff_admin:pages_page_change", args=[page.pk]) in contenu


# ---------------------------------------------------------------------------
# Suite de l'audit : identifiants invalides, permissions, verrous, avertissements
# / Audit follow-up: invalid ids, permissions, locks, warnings
# ---------------------------------------------------------------------------
@pytest.fixture
def client_connecte_non_admin(tenant):
    """
    Un client connecte avec un compte ACTIF, is_staff, mais PAS admin du lieu.
    Le compte est supprime apres le test.
    / A client logged in as an active staff account that is NOT a venue admin.
    """
    from django.test import Client as ClientDjango

    from AuthBillet.models import TibilletUser

    email = "pytest-apercu-non-admin@example.org"
    utilisateur, _cree = TibilletUser.objects.get_or_create(email=email, defaults={"username": email})
    utilisateur.is_active = True
    utilisateur.is_staff = True
    utilisateur.save()
    utilisateur.client_admin.remove(tenant)

    client = ClientDjango(HTTP_HOST="lespass.tibillet.localhost")
    client.force_login(utilisateur)
    yield client
    TibilletUser.objects.filter(email=email).delete()


def test_un_non_admin_connecte_n_obtient_rien(tenant, client_connecte_non_admin, nettoyer_pages_apercu):
    """
    Connecte mais pas admin du lieu : aucune vue ne rend de contenu, et rien
    n'est deplace ni supprime.
    """
    from pages.models import Bloc

    page = _creer_page(tenant, "non-admin")
    with tenant_context(tenant):
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="Secret", position=1)
        Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="Autre", position=2)

    client = client_connecte_non_admin
    reponses = [
        client.get(reverse("staff_admin:pages_page_apercu", args=[page.pk])),
        client.post(reverse("staff_admin:pages_bloc_apercu"), {"modele": "FAQ:", "page": str(page.pk)}),
        client.get(reverse("staff_admin:pages_bloc_editeur_ligne") + "?editeur=gps&nom=points_gps_editeur"),
        client.get(reverse("staff_admin:pages_page_menu_ajout", args=[page.pk]) + "?inserer_apres=1"),
        client.post(reverse("staff_admin:pages_bloc_deplacer", args=[bloc.pk, "descendre"])),
        client.post(reverse("staff_admin:pages_bloc_retirer", args=[bloc.pk])),
    ]

    for reponse in reponses:
        assert reponse.status_code in (302, 403)
        assert "Secret" not in reponse.content.decode()
    with tenant_context(tenant):
        bloc.refresh_from_db()
        assert bloc.position == 1


def test_un_sens_de_deplacement_inconnu_est_refuse(tenant, admin_client, nettoyer_pages_apercu):
    """Seuls « monter » et « descendre » sont acceptes."""
    from pages.models import Bloc

    page = _creer_page(tenant, "sens")
    with tenant_context(tenant):
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="Q")

    reponse = admin_client.post(reverse("staff_admin:pages_bloc_deplacer", args=[bloc.pk, "sauter"]))

    assert reponse.status_code == 403


def test_ligne_vide_refuse_un_editeur_ou_un_nom_inconnus(admin_client):
    """Le nom du champ est recopie dans le HTML : seuls les 3 noms connus passent."""
    url = reverse("staff_admin:pages_bloc_editeur_ligne")

    assert admin_client.get(url + "?editeur=pirate&nom=contenu_lieu").status_code == 403
    assert admin_client.get(url + '?editeur=gps&nom="><script>').status_code == 403
    reponse_valide = admin_client.get(url + "?editeur=gps&nom=points_gps_editeur")
    assert reponse_valide.status_code == 200
    assert 'name="points_gps_editeur__lat"' in reponse_valide.content.decode()


def test_un_identifiant_invalide_ne_provoque_jamais_de_500(admin_client):
    """« abc » n'est pas un UUID : 404 ou redirection de l'admin, jamais 500."""
    reponses = [
        admin_client.get("/admin/pages/page/abc/change/"),
        admin_client.get("/admin/pages/bloc/abc/change/"),
        admin_client.get("/admin/pages/page/abc/apercu/"),
        admin_client.post("/admin/pages/bloc/abc/deplacer/monter/"),
        admin_client.post("/admin/pages/bloc/abc/retirer/"),
        admin_client.post(reverse("staff_admin:pages_bloc_apercu"), {"modele": "FAQ:", "bloc_uuid": "abc"}),
    ]

    for reponse in reponses:
        assert reponse.status_code in (200, 302, 404), reponse.status_code


def test_deplacer_un_bloc_verrouille_les_blocs_de_la_page(tenant, nettoyer_pages_apercu):
    """
    Le deplacement se fait dans une transaction, blocs verrouilles
    (SELECT ... FOR UPDATE) : deux clics simultanes ne se melangent pas.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from pages.models import Bloc
    from pages.services import deplacer_bloc

    page = _creer_page(tenant, "verrou")
    with tenant_context(tenant):
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="A", position=1)
        Bloc.objects.create(page=page, type_bloc=Bloc.FAQ, titre="B", position=2)
        with CaptureQueriesContext(connection) as requetes:
            deplacer_bloc(bloc, "descendre")

    sql_execute = " ".join(requete["sql"] for requete in requetes.captured_queries)
    assert "FOR UPDATE" in sql_execute


def test_type_inconnu_signale_et_garde_tel_quel():
    """
    Un item LIEU au type inconnu (venu de l'API) n'est pas change en silence :
    la ligne le garde, et un avertissement le signale.
    """
    from pages.editeur_items import lignes_pour_affichage

    lignes, avertissements = lignes_pour_affichage(
        [{"type": "wifi", "texte": "Code : 1234"}, {"type": "para", "texte": "ok", "couleur": "rouge"}],
        "lieu",
    )

    assert lignes[0]["type"] == "wifi"
    assert lignes[0]["type_inconnu"] is True
    assert "type_inconnu" not in lignes[1]
    texte_des_avertissements = " ".join(str(a) for a in avertissements)
    assert "wifi" in texte_des_avertissements
    assert "couleur" in texte_des_avertissements


def test_la_fiche_lieu_affiche_le_type_inconnu_dans_le_select(tenant, admin_client, nettoyer_pages_apercu):
    """Le select garde l'option du type inconnu, selectionnee : rien ne bascule sur « Intitule »."""
    from pages.models import Bloc

    page = _creer_page(tenant, "type-inconnu")
    with tenant_context(tenant):
        bloc = Bloc.objects.create(page=page, type_bloc=Bloc.LIEU, contenu=[{"type": "wifi", "texte": "Code"}])

    contenu = admin_client.get(reverse("staff_admin:pages_bloc_change", args=[bloc.pk])).content.decode()

    assert '<option value="wifi" selected>' in contenu
    assert 'data-testid="editeur-lignes-avertissement-contenu_lieu"' in contenu


def test_galerie_de_l_apercu_plafonne_le_nombre_de_lignes(tenant, admin_client, nettoyer_pages_apercu):
    """Un TOTAL_FORMS gigantesque (POST forge) est plafonne : reponse rapide."""
    import time

    page = _creer_page(tenant, "plafond")
    debut = time.monotonic()
    reponse = admin_client.post(
        reverse("staff_admin:pages_bloc_apercu"),
        {"modele": "IMAGES:GRILLE", "page": str(page.pk), "images_galerie-TOTAL_FORMS": "100000000"},
    )

    assert reponse.status_code == 200
    assert time.monotonic() - debut < 10


def test_le_cache_ne_ferme_pas_ses_connexions_en_fin_de_requete():
    """
    PyMemcacheCacheSansFermeture.close() ne deconnecte rien : sous ASGI, la fin
    d'une requete fermait les sockets des requetes voisines.
    """
    from unittest import mock

    from django.core.cache import caches

    from TiBillet.cache_memcached import PyMemcacheCacheSansFermeture

    # `caches["default"]` et non `cache` : ce dernier est un proxy.
    # / `caches["default"]`, not `cache`, which is a proxy.
    cache = caches["default"]
    assert isinstance(cache, PyMemcacheCacheSansFermeture)
    with mock.patch.object(type(cache._cache), "close") as fermeture, \
            mock.patch.object(type(cache._cache), "disconnect_all", create=True) as deconnexion:
        cache.close()
    fermeture.assert_not_called()
    deconnexion.assert_not_called()


def test_le_cache_a_des_delais_d_attente_et_tolere_les_pannes():
    """Delais d'attente poses et ignore_exc actif (voir TiBillet/settings.py)."""
    from django.core.cache import caches

    client_memcached = caches["default"]._cache
    assert client_memcached.use_pooling is True
    assert client_memcached.ignore_exc is True
    assert client_memcached.default_kwargs["timeout"] == 2
    assert client_memcached.default_kwargs["connect_timeout"] == 1


# ---------------------------------------------------------------------------
# Suites de l'audit (point 2 de « a traiter ») : menu a la demande, bornes,
# scripts tiers / Audit follow-ups: on-demand menu, bounds, third-party scripts
# ---------------------------------------------------------------------------
def test_menu_ajout_rend_les_modeles_pour_une_position(tenant, admin_client, nettoyer_pages_apercu):
    """Le menu « + » d'un bloc, charge a la demande, pre-remplit la bonne place."""
    page = _creer_page(tenant, "menu-demande")
    url = reverse("staff_admin:pages_page_menu_ajout", args=[page.pk]) + "?inserer_apres=3"

    reponse = admin_client.get(url)
    contenu = reponse.content.decode()

    assert reponse.status_code == 200
    assert "inserer_apres=3" in contenu
    assert 'target="_top"' in contenu
    assert 'data-testid="page-bloc-3-ajouter-sectioncarte"' in contenu


def test_menu_ajout_refuse_une_position_ou_une_page_invalide(tenant, admin_client, nettoyer_pages_apercu):
    """Position absente ou non numerique, page inconnue : 404, jamais 500."""
    page = _creer_page(tenant, "menu-invalide")
    url = reverse("staff_admin:pages_page_menu_ajout", args=[page.pk])

    assert admin_client.get(url).status_code == 404
    assert admin_client.get(url + "?inserer_apres=abc").status_code == 404
    assert admin_client.get("/admin/pages/page/abc/menu-ajout/?inserer_apres=1").status_code == 404


def test_bornes_de_l_apercu_identiques_a_celles_du_modele():
    """
    Le serializer de l'apercu lit ses limites sur le modele : l'apercu et
    l'enregistrement refusent exactement les memes valeurs.
    """
    from django.core.validators import MaxValueValidator, MinValueValidator

    from pages.admin_apercu import ApercuBlocSerializer
    from pages.models import Bloc

    champs = ApercuBlocSerializer().fields
    for nom in ("titre", "sous_titre", "badge", "bouton_label", "bouton_url",
                "bouton2_label", "bouton2_url", "auteur_nom", "auteur_role", "embed_url"):
        assert champs[nom].max_length == Bloc._meta.get_field(nom).max_length, nom

    for nom in ("hauteur_px", "nombre_max"):
        validateurs = Bloc._meta.get_field(nom).validators
        minimum = [v.limit_value for v in validateurs if isinstance(v, MinValueValidator)][0]
        maximum = [v.limit_value for v in validateurs if isinstance(v, MaxValueValidator)][0]
        assert (champs[nom].min_value, champs[nom].max_value) == (minimum, maximum), nom


def test_l_apercu_ne_charge_pas_formbricks(tenant, admin_client, nettoyer_pages_apercu):
    """Meme configure pour le lieu, formbricks n'est pas charge dans l'apercu."""
    from types import SimpleNamespace
    from unittest import mock

    page = _creer_page(tenant, "formbricks")
    faux_reglage = SimpleNamespace(api_host="https://formbricks.exemple.org")

    with mock.patch("BaseBillet.views.FormbricksConfig.get_solo", return_value=faux_reglage):
        reponse = admin_client.post(
            reverse("staff_admin:pages_bloc_apercu"),
            {"modele": "FAQ:", "page": str(page.pk), "titre": "Q"},
        )

    contenu = reponse.content.decode()
    assert "bloc-apercu-iframe" in contenu
    assert "formbricks.umd.cjs" not in contenu
