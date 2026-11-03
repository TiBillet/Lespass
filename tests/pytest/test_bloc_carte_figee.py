"""
Tests du bloc « Carte figée » : import JSON, vérification, conversion, admin.
/ Tests of the "frozen map" block: JSON import, checks, conversion, admin.

LOCALISATION : tests/pytest/test_bloc_carte_figee.py

Couvre :
- pages/carte_figee.py : lecture et vérification du fichier (sans base),
  conversion vers le format de l'outil de carte (sans base) ;
- pages/models.py : Bloc.clean() re-vérifie les données (chemin API, script) ;
- pages/admin.py : import du fichier depuis la fiche du bloc ;
- pages/classic/partials/bloc_carte_figee.html : rendu, via l'aperçu.
Pattern : base dev live (pas de rollback). Les pages de test ont un slug
préfixé « pytest-carte-figee- » et sont supprimées après chaque test.
/ Pattern: live dev DB (no rollback). Test pages are deleted after each test.
"""

import json

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django_tenants.utils import tenant_context

from pages.carte_figee import (
    donnees_explorer_depuis_carte_figee,
    lire_fichier_carte_figee,
    nettoyer_carte_figee,
)

PREFIXE_SLUG = "pytest-carte-figee-"


def _un_lieu_valide(**cles_a_changer):
    """Un lieu minimal valide, avec deux événements. / A minimal valid venue."""
    lieu = {
        "nom": "La Cité du Faire",
        "latitude": 45.7578,
        "longitude": 4.8320,
        "adresse": "12 rue de l'Exemple, 69003 Lyon",
        "url": "https://lacitedufaire.example.org/",
        "evenements": [
            {"nom": "Atelier ouvert", "date": "2026-10-03"},
            {
                "nom": "Visite guidée",
                "date": "2026-10-02T14:00",
                "url": "https://lacitedufaire.example.org/visite/",
                "tags": ["JPTO", "Visite"],
            },
        ],
    }
    lieu.update(cles_a_changer)
    return lieu


def _fichier_json(contenu, nom="carte.json"):
    """Un fichier envoyé, comme le reçoit le formulaire. / An uploaded file."""
    return SimpleUploadedFile(
        nom, json.dumps(contenu).encode("utf-8"), content_type="application/json"
    )


# ---------------------------------------------------------------------------
# Vérification du fichier : sans base / File checks: no database
# ---------------------------------------------------------------------------
def test_un_fichier_valide_rend_les_lieux_sans_erreur():
    lieux, erreurs = nettoyer_carte_figee([_un_lieu_valide()])

    assert erreurs == []
    assert lieux[0]["nom"] == "La Cité du Faire"
    assert len(lieux[0]["evenements"]) == 2


def test_un_lieu_sans_evenement_est_accepte():
    lieux, erreurs = nettoyer_carte_figee(
        [{"nom": "Lieu seul", "latitude": 48.57, "longitude": 7.75}]
    )

    assert erreurs == []
    assert lieux == [
        {"nom": "Lieu seul", "latitude": 48.57, "longitude": 7.75, "evenements": []}
    ]


def test_la_racine_doit_etre_une_liste():
    _lieux, erreurs = nettoyer_carte_figee({"lieux": []})

    assert len(erreurs) == 1


def test_une_liste_vide_est_refusee():
    _lieux, erreurs = nettoyer_carte_figee([])

    assert len(erreurs) == 1


def test_le_nom_du_lieu_est_obligatoire():
    _lieux, erreurs = nettoyer_carte_figee([_un_lieu_valide(nom="  ")])

    assert len(erreurs) == 1
    assert "nom" in str(erreurs[0])


def test_une_latitude_hors_bornes_est_refusee():
    _lieux, erreurs = nettoyer_carte_figee([_un_lieu_valide(latitude=91)])

    assert len(erreurs) == 1
    assert "latitude" in str(erreurs[0])


def test_une_longitude_absente_est_refusee():
    lieu = _un_lieu_valide()
    del lieu["longitude"]
    _lieux, erreurs = nettoyer_carte_figee([lieu])

    assert len(erreurs) == 1
    assert "longitude" in str(erreurs[0])


def test_un_booleen_n_est_pas_une_coordonnee():
    """En Python, True vaut 1 : sans garde, il passerait pour une latitude."""
    _lieux, erreurs = nettoyer_carte_figee([_un_lieu_valide(latitude=True)])

    assert len(erreurs) == 1


def test_les_nombres_en_texte_sont_convertis():
    lieux, erreurs = nettoyer_carte_figee(
        [_un_lieu_valide(latitude="45,7578", longitude=" 4.832 ")]
    )

    assert erreurs == []
    assert lieux[0]["latitude"] == 45.7578
    assert lieux[0]["longitude"] == 4.832


def test_une_url_javascript_est_refusee_sur_le_lieu():
    """Une URL javascript: dans un href s'exécuterait au clic (XSS)."""
    _lieux, erreurs = nettoyer_carte_figee([_un_lieu_valide(url="javascript:alert(1)")])

    assert len(erreurs) == 1
    assert "http" in str(erreurs[0])


def test_une_url_javascript_est_refusee_sur_un_evenement():
    lieu = _un_lieu_valide(evenements=[{"nom": "Piège", "url": "JavaScript:alert(1)"}])
    _lieux, erreurs = nettoyer_carte_figee([lieu])

    assert len(erreurs) == 1


def test_une_date_mal_formee_est_refusee():
    lieu = _un_lieu_valide(evenements=[{"nom": "Atelier", "date": "02/10/2026"}])
    _lieux, erreurs = nettoyer_carte_figee([lieu])

    assert len(erreurs) == 1
    assert "date" in str(erreurs[0])


def test_le_nom_d_un_evenement_est_obligatoire():
    lieu = _un_lieu_valide(evenements=[{"date": "2026-10-02"}])
    _lieux, erreurs = nettoyer_carte_figee([lieu])

    assert len(erreurs) == 1


def test_des_tags_qui_ne_sont_pas_une_liste_sont_refuses():
    lieu = _un_lieu_valide(evenements=[{"nom": "Atelier", "tags": "JPTO"}])
    _lieux, erreurs = nettoyer_carte_figee([lieu])

    assert len(erreurs) == 1


def test_une_cle_inconnue_est_ignoree_sans_erreur():
    lieux, erreurs = nettoyer_carte_figee([_un_lieu_valide(couleur="rouge")])

    assert erreurs == []
    assert "couleur" not in lieux[0]


def test_toutes_les_erreurs_sont_rendues_d_un_coup():
    """L'admin corrige tout en une fois, sans réimporter erreur par erreur."""
    _lieux, erreurs = nettoyer_carte_figee(
        [
            _un_lieu_valide(latitude=200),
            _un_lieu_valide(url="ftp://exemple.org"),
        ]
    )

    assert len(erreurs) == 2
    assert "Lieu 1" in str(erreurs[0])
    assert "Lieu 2" in str(erreurs[1])


def test_un_json_illisible_donne_une_erreur_avec_la_position():
    fichier = SimpleUploadedFile(
        "carte.json", b'[{"nom": "A",}]', content_type="application/json"
    )
    _lieux, erreurs = lire_fichier_carte_figee(fichier)

    assert len(erreurs) == 1
    assert "ligne 1" in str(erreurs[0])


def test_un_fichier_trop_gros_est_refuse():
    fichier = SimpleUploadedFile(
        "carte.json", b" " * (2 * 1024 * 1024 + 1), content_type="application/json"
    )
    _lieux, erreurs = lire_fichier_carte_figee(fichier)

    assert len(erreurs) == 1
    assert "2 Mo" in str(erreurs[0])


def test_un_fichier_qui_n_est_pas_en_utf8_est_refuse():
    fichier = SimpleUploadedFile("carte.json", '[{"nom": "Rosée"}]'.encode("latin-1"))
    _lieux, erreurs = lire_fichier_carte_figee(fichier)

    assert len(erreurs) == 1
    assert "UTF-8" in str(erreurs[0])


# ---------------------------------------------------------------------------
# Sécurité des URL : sans base / URL security: no database
# ---------------------------------------------------------------------------
# Chaque URL finit dans un attribut href="..." construit par explorer.js.
# / Every URL ends up in an href="..." attribute built by explorer.js.
URLS_REFUSEES = [
    # Un guillemet refermerait l'attribut href : XSS par attribut ajouté.
    # / A quote would close the href attribute: XSS through an added attribute.
    'https://x.org/" autofocus onfocus="alert(1)',
    "https://x.org/' onmouseover='alert(1)",
    "https://x.org/<script>",
    "https://x.org/a b",
    "https://x.org/a\tb",
    "https://x.org/a\nb",
    "https://x.org/`",
    "https://",
    "https:///chemin",
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    " javascript:alert(1)",
    "java\tscript:alert(1)",
    "&#106;avascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "ftp://exemple.org/",
    "//exemple.org/",
    "https://exemple.org/" + "a" * 2001,
]


@pytest.mark.parametrize("url_refusee", URLS_REFUSEES)
def test_une_url_dangereuse_ou_incomplete_est_refusee(url_refusee):
    lieu = _un_lieu_valide(url=url_refusee)
    _lieux, erreurs = nettoyer_carte_figee([lieu])

    assert len(erreurs) == 1, url_refusee


@pytest.mark.parametrize("url_refusee", URLS_REFUSEES)
def test_une_url_dangereuse_est_aussi_refusee_sur_un_evenement(url_refusee):
    lieu = _un_lieu_valide(evenements=[{"nom": "Atelier", "url": url_refusee}])
    _lieux, erreurs = nettoyer_carte_figee([lieu])

    assert len(erreurs) == 1, url_refusee


@pytest.mark.parametrize(
    "url_acceptee",
    [
        "https://exemple.org",
        "HTTPS://EXEMPLE.ORG/Page",
        "http://exemple.org/chemin?a=1&b=2#ancre",
        "https://exemple.org/%22encode%22",
        "https://sous.domaine.exemple.org:8443/",
    ],
)
def test_une_url_http_complete_est_acceptee(url_acceptee):
    lieux, erreurs = nettoyer_carte_figee([_un_lieu_valide(url=url_acceptee)])

    assert erreurs == []
    assert lieux[0]["url"] == url_acceptee


# ---------------------------------------------------------------------------
# Valeurs limites : sans base / Edge values: no database
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("valeur", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_nan_et_infini_ne_sont_pas_des_coordonnees(valeur):
    """json.loads accepte NaN et Infinity : ils doivent être refusés."""
    contenu = f'[{{"nom": "A", "latitude": {valeur}, "longitude": 4.8}}]'.encode()
    fichier = SimpleUploadedFile("carte.json", contenu)
    _lieux, erreurs = lire_fichier_carte_figee(fichier)

    assert len(erreurs) == 1
    assert "latitude" in str(erreurs[0])


def test_un_json_imbrique_trop_profondement_donne_une_erreur_et_pas_un_plantage():
    """200 000 crochets ouvrants : RecursionError dans json.loads, pas une 500."""
    fichier = SimpleUploadedFile("carte.json", b"[" * 200_000)
    _lieux, erreurs = lire_fichier_carte_figee(fichier)

    assert len(erreurs) == 1
    assert "imbriqué" in str(erreurs[0])


@pytest.mark.parametrize(
    "date_refusee",
    [
        "20261002",
        "2026-W40-1",
        "2026-10-02T14",
        "2026-13-01",
        "02/10/2026",
        "2026-10-02 14:00",
    ],
)
def test_une_date_d_une_autre_forme_est_refusee(date_refusee):
    """fromisoformat accepte 20261002 ou 2026-W40-1 : le navigateur affiche « Invalid Date »."""
    lieu = _un_lieu_valide(evenements=[{"nom": "Atelier", "date": date_refusee}])
    _lieux, erreurs = nettoyer_carte_figee([lieu])

    assert len(erreurs) == 1, date_refusee


@pytest.mark.parametrize(
    "date_acceptee", ["2026-10-02", "2026-10-02T14:00", "2026-10-02T14:00:30"]
)
def test_les_trois_formes_de_date_sont_acceptees(date_acceptee):
    lieu = _un_lieu_valide(evenements=[{"nom": "Atelier", "date": date_acceptee}])
    _lieux, erreurs = nettoyer_carte_figee([lieu])

    assert erreurs == []


@pytest.mark.parametrize("cle", ["nom", "adresse"])
def test_un_texte_de_lieu_trop_long_est_refuse(cle):
    _lieux, erreurs = nettoyer_carte_figee([_un_lieu_valide(**{cle: "a" * 201})])

    assert len(erreurs) == 1
    assert cle in str(erreurs[0])
    # Le nom trop long n'est pas recopié dans le message.
    # / The too long name is not echoed in the message.
    assert "a" * 201 not in str(erreurs[0])


def test_un_nom_d_evenement_ou_un_tag_trop_long_est_refuse():
    lieu = _un_lieu_valide(
        evenements=[{"nom": "e" * 201}, {"nom": "Atelier", "tags": ["t" * 201]}]
    )
    _lieux, erreurs = nettoyer_carte_figee([lieu])

    assert len(erreurs) == 2


def test_un_texte_de_200_caracteres_passe():
    _lieux, erreurs = nettoyer_carte_figee([_un_lieu_valide(nom="a" * 200)])

    assert erreurs == []


# ---------------------------------------------------------------------------
# Conversion pour l'outil de carte : sans base / Conversion: no database
# ---------------------------------------------------------------------------
def test_un_lieu_devient_un_tenant_et_un_point():
    lieux, _erreurs = nettoyer_carte_figee([_un_lieu_valide()])
    donnees = donnees_explorer_depuis_carte_figee(lieux)

    assert len(donnees["tenants"]) == 1
    assert len(donnees["points"]) == 1
    tenant_du_lieu = donnees["tenants"][0]
    point_du_lieu = donnees["points"][0]
    assert tenant_du_lieu["tenant_id"] == point_du_lieu["tenant_id"] == "lieu-1"
    assert point_du_lieu["latitude"] == 45.7578
    assert point_du_lieu["url"] == "https://lacitedufaire.example.org/"
    assert tenant_du_lieu["url"] == "https://lacitedufaire.example.org/"
    # La carte de la liste affiche `locality` : elle porte l'adresse.
    # / The list card shows `locality`: it carries the address.
    assert tenant_du_lieu["locality"] == "12 rue de l'Exemple, 69003 Lyon"
    assert point_du_lieu["address_display"] == "12 rue de l'Exemple, 69003 Lyon"


def test_les_evenements_sont_tries_par_date_avec_leur_lien_et_leurs_tags():
    lieux, _erreurs = nettoyer_carte_figee([_un_lieu_valide()])
    evenements = donnees_explorer_depuis_carte_figee(lieux)["points"][0][
        "events_futurs"
    ]

    assert [evenement["name"] for evenement in evenements] == [
        "Visite guidée",
        "Atelier ouvert",
    ]
    assert evenements[0]["url"] == "https://lacitedufaire.example.org/visite/"
    assert evenements[0]["tags"] == [
        {"slug": "jpto", "name": "JPTO"},
        {"slug": "visite", "name": "Visite"},
    ]


def test_tous_les_evenements_sont_gardes_sans_limite_a_cinq():
    """Le cache de la page réseau coupe à 5 ; une carte figée garde tout."""
    vingt_evenements = [
        {"nom": f"Atelier {numero}", "date": "2026-10-02"} for numero in range(20)
    ]
    lieux, _erreurs = nettoyer_carte_figee(
        [_un_lieu_valide(evenements=vingt_evenements)]
    )
    point_du_lieu = donnees_explorer_depuis_carte_figee(lieux)["points"][0]

    assert len(point_du_lieu["events_futurs"]) == 20
    assert point_du_lieu["events_futurs_count_total"] == 20


def _slugs_des_tags(noms_des_tags):
    """Les slugs donnés aux tags d'un événement. / Slugs given to an event's tags."""
    lieu = _un_lieu_valide(evenements=[{"nom": "Atelier", "tags": noms_des_tags}])
    lieux, _erreurs = nettoyer_carte_figee([lieu])
    evenement = donnees_explorer_depuis_carte_figee(lieux)["points"][0][
        "events_futurs"
    ][0]
    return [tag["slug"] for tag in evenement["tags"]]


def test_un_tag_non_latin_garde_un_slug_non_vide():
    """slugify ASCII rend "" pour 日本 : le filtre par tag ne marcherait pas."""
    slugs = _slugs_des_tags(["日本", "Économie"])

    assert slugs == ["日本", "économie"]


def test_un_tag_emoji_recoit_un_slug_de_repli():
    slugs = _slugs_des_tags(["🎉"])

    assert slugs[0] != ""
    assert slugs[0].startswith("tag-")


def test_deux_noms_differents_n_ont_jamais_le_meme_slug():
    """« Café » et « café » donneraient le même slug : ils seraient fusionnés."""
    slugs = _slugs_des_tags(["Café", "café"])

    assert slugs[0] != slugs[1]


def test_un_meme_tag_a_le_meme_slug_sur_toute_la_carte():
    lieux, _erreurs = nettoyer_carte_figee(
        [
            _un_lieu_valide(evenements=[{"nom": "A", "tags": ["JPTO"]}]),
            _un_lieu_valide(
                nom="Autre lieu", evenements=[{"nom": "B", "tags": ["JPTO"]}]
            ),
        ]
    )
    points = donnees_explorer_depuis_carte_figee(lieux)["points"]

    assert points[0]["events_futurs"][0]["tags"][0]["slug"] == "jpto"
    assert points[1]["events_futurs"][0]["tags"][0]["slug"] == "jpto"


# ---------------------------------------------------------------------------
# Avec la base : modèle, admin, rendu / With the database
# ---------------------------------------------------------------------------
@pytest.fixture
def nettoyer_pages_carte_figee(tenant):
    """
    Supprime les pages de test (et leurs blocs) AVANT et APRES le test.
    Avant : un run interrompu laisse des pages ; leur slug ferait echouer le
    Page.objects.create du run suivant (IntegrityError).
    / Deletes test pages BEFORE and AFTER: an interrupted run leaves pages whose
    slug would break the next run.
    """
    from pages.models import Page

    with tenant_context(tenant):
        Page.objects.filter(slug__startswith=PREFIXE_SLUG).delete()
    yield
    with tenant_context(tenant):
        Page.objects.filter(slug__startswith=PREFIXE_SLUG).delete()


def _creer_page(tenant, suffixe):
    from pages.models import Page

    with tenant_context(tenant):
        return Page.objects.create(
            titre=f"Pytest carte figée {suffixe}", slug=f"{PREFIXE_SLUG}{suffixe}"
        )


def _formulaire_d_ajout(page, titre="Bilan JPTO"):
    """Données minimales du formulaire d'un bloc CARTE_FIGEE. / Minimal form data."""
    return {
        "modele": "CARTE_FIGEE:",
        "type_bloc": "",
        "affichage": "",
        "page": str(page.pk),
        "titre": titre,
        "hauteur_px": "600",
        "nombre_max": "6",
        "_save": "Enregistrer",
    }


@pytest.mark.django_db
def test_bloc_clean_refuse_une_url_javascript_venue_d_un_autre_chemin(
    tenant, nettoyer_pages_carte_figee
):
    """
    L'API v2 écrit `donnees_carte_figee` sans passer par l'admin : Bloc.clean()
    doit donc re-vérifier les URL.
    / The v2 API writes the field directly: Bloc.clean() must re-check URLs.
    """
    from pages.models import Bloc

    page = _creer_page(tenant, "clean-url")
    with tenant_context(tenant):
        bloc = Bloc(
            page=page,
            type_bloc=Bloc.CARTE_FIGEE,
            donnees_carte_figee=[_un_lieu_valide(url="javascript:alert(1)")],
        )
        with pytest.raises(ValidationError):
            bloc.full_clean(exclude=["uuid"])


@pytest.mark.django_db
def test_bloc_clean_range_la_version_nettoyee(tenant, nettoyer_pages_carte_figee):
    from pages.models import Bloc

    page = _creer_page(tenant, "clean-propre")
    with tenant_context(tenant):
        bloc = Bloc(
            page=page,
            type_bloc=Bloc.CARTE_FIGEE,
            donnees_carte_figee=[_un_lieu_valide(latitude="45.75", couleur="rouge")],
        )
        bloc.full_clean(exclude=["uuid"])

        assert bloc.donnees_carte_figee[0]["latitude"] == 45.75
        assert "couleur" not in bloc.donnees_carte_figee[0]


@pytest.mark.django_db
def test_bloc_clean_refuse_une_carte_vide(tenant, nettoyer_pages_carte_figee):
    from pages.models import Bloc

    page = _creer_page(tenant, "clean-vide")
    with tenant_context(tenant):
        bloc = Bloc(page=page, type_bloc=Bloc.CARTE_FIGEE, donnees_carte_figee=[])
        with pytest.raises(ValidationError):
            bloc.full_clean(exclude=["uuid"])


@pytest.mark.django_db
def test_admin_l_import_d_un_fichier_valide_enregistre_la_carte(
    tenant, admin_client, nettoyer_pages_carte_figee
):
    from pages.models import Bloc

    page = _creer_page(tenant, "import-ok")
    donnees = _formulaire_d_ajout(page)
    donnees["fichier_carte_figee"] = _fichier_json([_un_lieu_valide()])

    url_d_ajout = reverse("staff_admin:pages_bloc_add") + f"?page={page.pk}"
    reponse = admin_client.post(url_d_ajout, donnees)

    assert reponse.status_code == 302, reponse.content.decode()[:3000]
    with tenant_context(tenant):
        bloc = Bloc.objects.get(page=page)
        assert bloc.type_bloc == Bloc.CARTE_FIGEE
        assert bloc.donnees_carte_figee[0]["nom"] == "La Cité du Faire"
        assert len(bloc.donnees_carte_figee[0]["evenements"]) == 2


@pytest.mark.django_db
def test_admin_un_fichier_en_erreur_n_enregistre_rien(
    tenant, admin_client, nettoyer_pages_carte_figee
):
    from pages.models import Bloc

    page = _creer_page(tenant, "import-ko")
    donnees = _formulaire_d_ajout(page)
    donnees["fichier_carte_figee"] = _fichier_json([_un_lieu_valide(latitude=500)])

    url_d_ajout = reverse("staff_admin:pages_bloc_add") + f"?page={page.pk}"
    reponse = admin_client.post(url_d_ajout, donnees)

    assert reponse.status_code == 200
    assert "la latitude doit être un nombre entre -90 et 90" in reponse.content.decode()
    with tenant_context(tenant):
        assert not Bloc.objects.filter(page=page).exists()


@pytest.mark.django_db
def test_admin_modifier_sans_fichier_garde_la_carte(
    tenant, admin_client, nettoyer_pages_carte_figee
):
    """On change le titre sans réimporter : les lieux restent."""
    from pages.models import Bloc

    page = _creer_page(tenant, "modifier")
    with tenant_context(tenant):
        bloc = Bloc.objects.create(
            page=page,
            type_bloc=Bloc.CARTE_FIGEE,
            titre="Ancien titre",
            donnees_carte_figee=[_un_lieu_valide()],
        )

    donnees = _formulaire_d_ajout(page, titre="Nouveau titre")
    reponse = admin_client.post(
        reverse("staff_admin:pages_bloc_change", args=[bloc.pk]), donnees
    )

    assert reponse.status_code == 302, reponse.content.decode()[:3000]
    with tenant_context(tenant):
        bloc.refresh_from_db()
        assert bloc.titre == "Nouveau titre"
        assert bloc.donnees_carte_figee[0]["nom"] == "La Cité du Faire"


@pytest.mark.django_db
def test_admin_la_fiche_montre_le_resume_et_l_exemple(
    tenant, admin_client, nettoyer_pages_carte_figee
):
    from pages.models import Bloc

    page = _creer_page(tenant, "fiche")
    with tenant_context(tenant):
        bloc = Bloc.objects.create(
            page=page,
            type_bloc=Bloc.CARTE_FIGEE,
            donnees_carte_figee=[_un_lieu_valide()],
        )

    contenu = admin_client.get(
        reverse("staff_admin:pages_bloc_change", args=[bloc.pk])
    ).content.decode()

    assert "Carte actuelle : 1 lieu(x), 2 événement(s)." in contenu
    assert "<details" in contenu
    assert "Voir un exemple de fichier" in contenu


@pytest.mark.django_db
def test_admin_une_deuxieme_carte_figee_sur_la_page_est_refusee(
    tenant, admin_client, nettoyer_pages_carte_figee
):
    from pages.models import Bloc

    page = _creer_page(tenant, "deux-cartes")
    with tenant_context(tenant):
        Bloc.objects.create(
            page=page,
            type_bloc=Bloc.CARTE_FIGEE,
            donnees_carte_figee=[_un_lieu_valide()],
        )

    donnees = _formulaire_d_ajout(page)
    donnees["fichier_carte_figee"] = _fichier_json([_un_lieu_valide()])
    url_d_ajout = reverse("staff_admin:pages_bloc_add") + f"?page={page.pk}"
    reponse = admin_client.post(url_d_ajout, donnees)

    assert reponse.status_code == 200
    assert "Cette page a déjà une carte figée" in reponse.content.decode()
    with tenant_context(tenant):
        assert Bloc.objects.filter(page=page).count() == 1


@pytest.mark.django_db
def test_le_rendu_pose_les_lieux_dans_le_widget_de_carte(
    tenant, admin_client, nettoyer_pages_carte_figee
):
    """
    L'aperçu d'un bloc enregistré rend l'outil de carte, avec les lieux du
    fichier, sur le socle (skin reunion -> classic) ET sur le skin V2.

    Le skin V2 doit rendre le .map-panel de sa coquille : V2.css pose la carte
    en position absolute dans ce panneau. Sans lui, la carte recouvre la page.
    Le skin est SIMULE (mock) : le test ne touche pas au skin de la base de dev.
    / Rendered on the base and on V2. V2 must render its .map-panel. The skin
    is MOCKED.
    """
    import html
    from unittest import mock

    from pages.models import Bloc

    page = _creer_page(tenant, "rendu")
    with tenant_context(tenant):
        bloc = Bloc.objects.create(
            page=page,
            type_bloc=Bloc.CARTE_FIGEE,
            donnees_carte_figee=[_un_lieu_valide()],
        )

    for skin in ("reunion", "V2"):
        with mock.patch("BaseBillet.views.get_skin_courant", return_value=skin):
            reponse = admin_client.post(
                reverse("staff_admin:pages_bloc_apercu"),
                {
                    "modele": "CARTE_FIGEE:",
                    "page": str(page.pk),
                    "bloc_uuid": str(bloc.pk),
                },
            )
        contenu = html.unescape(reponse.content.decode())

        assert reponse.status_code == 200, skin
        assert 'data-testid="bloc-carte-figee"' in contenu, skin
        assert 'id="explorer-data"' in contenu, skin
        # json_script encode les accents (\u00e9) : on cherche donc l'URL du lieu.
        # / json_script escapes accents: look for the venue URL instead.
        assert "https://lacitedufaire.example.org/" in contenu, skin
        assert "seo/explorer.js" in contenu, skin
        assert 'data-i18n-next-events="Événements :"' in contenu, skin
        if skin == "V2":
            assert 'class="map-panel"' in contenu
            # Le bouton « Réseau TiBillet » appartient à la page réseau seule.
            # / The "TiBillet network" button belongs to the network page only.
            assert "reseau-lien-explorer-global" not in contenu


@pytest.mark.django_db
def test_admin_un_fichier_en_erreur_n_affiche_que_l_erreur_du_fichier(
    tenant, admin_client, nettoyer_pages_carte_figee
):
    """Pas de « Importez un fichier JSON » en plus : un fichier a bien été envoyé."""
    page = _creer_page(tenant, "un-seul-message")
    donnees = _formulaire_d_ajout(page)
    donnees["fichier_carte_figee"] = _fichier_json([_un_lieu_valide(latitude=500)])

    url_d_ajout = reverse("staff_admin:pages_bloc_add") + f"?page={page.pk}"
    contenu = admin_client.post(url_d_ajout, donnees).content.decode()

    assert "la latitude doit être un nombre entre -90 et 90" in contenu
    assert "la carte n&#x27;a encore aucun lieu" not in contenu
    assert "la carte n'a encore aucun lieu" not in contenu


@pytest.mark.django_db
def test_admin_un_bloc_neuf_sans_fichier_demande_un_fichier(
    tenant, admin_client, nettoyer_pages_carte_figee
):
    from pages.models import Bloc

    page = _creer_page(tenant, "sans-fichier")
    url_d_ajout = reverse("staff_admin:pages_bloc_add") + f"?page={page.pk}"
    reponse = admin_client.post(url_d_ajout, _formulaire_d_ajout(page))

    assert reponse.status_code == 200
    assert "Importez un fichier JSON" in reponse.content.decode()
    with tenant_context(tenant):
        assert not Bloc.objects.filter(page=page).exists()


@pytest.mark.django_db
def test_un_bloc_d_un_autre_type_ne_garde_pas_de_donnees_de_carte(
    tenant, nettoyer_pages_carte_figee
):
    """
    L'API v2 peut poser donnees_carte_figee sur n'importe quel bloc, sans
    vérification : Bloc.clean() vide ce champ hors CARTE_FIGEE.
    / The v2 API can set the field on any block: Bloc.clean() empties it.
    """
    from pages.models import Bloc

    page = _creer_page(tenant, "autre-type")
    with tenant_context(tenant):
        bloc = Bloc(
            page=page,
            type_bloc=Bloc.FAQ,
            titre="Question",
            texte="Réponse",
            donnees_carte_figee=[_un_lieu_valide(url="javascript:alert(1)")],
        )
        bloc.full_clean(exclude=["uuid"])

        assert bloc.donnees_carte_figee == []
