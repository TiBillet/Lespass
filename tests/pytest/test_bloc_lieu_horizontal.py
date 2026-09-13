"""
Regroupement des infos pratiques d'un bloc LIEU en cartes (affichage HORIZONTAL).
/ Grouping a LIEU block's practical info into cards (HORIZONTAL layout).

LOCALISATION : tests/pytest/test_bloc_lieu_horizontal.py

Le tag `cartes_infos_pratiques` est la SEULE logique Python de cet affichage :
tout le reste est du gabarit. Il decoupe une liste PLATE d'items types en cartes
etiquetees, un item `badge` ouvrant chaque carte. C'est la regle que ces tests
figent, parce qu'elle n'est evidente pour personne en lisant le gabarit.

`contenu` est un JSONField saisi librement (admin ou API v2) : les tests couvrent
donc aussi les formes malformees, qui doivent rendre une liste vide plutot que de
faire sortir la page publique en erreur.
/ The tag is the only Python logic of this layout. These tests pin the grouping
rule and the behaviour on malformed input (a freely-typed JSONField).

Aucune base de donnees : le tag est une fonction pure (`register.simple_tag`
retourne la fonction inchangee).
/ No database: the tag is a pure function.
"""

from pages.templatetags.pages_tags import cartes_infos_pratiques


def test_un_badge_ouvre_une_carte_et_les_items_suivants_la_remplissent():
    """La regle centrale : `badge` = intitule, les suivants = contenu."""
    cartes = cartes_infos_pratiques([
        {"type": "badge", "texte": "Adresse"},
        {"type": "adresse", "texte": "12 rue de la Coopérative"},
        {"type": "badge", "texte": "Horaires"},
        {"type": "horaire", "texte": "MER → SAM 14h → 23h"},
        {"type": "horaire", "texte": "ATELIERS MAR & JEU"},
    ])

    assert len(cartes) == 2
    assert cartes[0]["intitule"] == "Adresse"
    assert [item["texte"] for item in cartes[0]["items"]] == ["12 rue de la Coopérative"]
    assert cartes[1]["intitule"] == "Horaires"
    assert len(cartes[1]["items"]) == 2


def test_les_items_avant_le_premier_badge_ne_sont_pas_perdus():
    """
    Un contenu qui ne commence pas par un badge reste affiche.

    Les jeter serait une perte SILENCIEUSE : la personne qui a saisi le bloc
    verrait son texte disparaitre sans message.
    / Dropping them would be a SILENT loss.
    """
    cartes = cartes_infos_pratiques([
        {"type": "para", "texte": "Au coeur du quartier."},
        {"type": "badge", "texte": "Adresse"},
        {"type": "adresse", "texte": "12 rue de la Coopérative"},
    ])

    assert len(cartes) == 2
    assert cartes[0]["intitule"] == ""
    assert cartes[0]["items"][0]["texte"] == "Au coeur du quartier."


def test_un_badge_sans_rien_apres_ne_rend_pas_de_carte_vide():
    """Une carte ouverte mais jamais remplie n'a rien a montrer."""
    cartes = cartes_infos_pratiques([
        {"type": "badge", "texte": "Adresse"},
        {"type": "adresse", "texte": "12 rue de la Coopérative"},
        {"type": "badge", "texte": "Intitule orphelin"},
    ])

    assert len(cartes) == 1
    assert cartes[0]["intitule"] == "Adresse"


def test_un_contenu_malforme_rend_une_liste_vide_sans_lever():
    """
    Un JSONField mal saisi ne doit JAMAIS faire sortir la page en erreur.

    L'admin comme l'API v2 acceptent n'importe quel JSON dans `contenu` : une
    chaine, un dict, une liste d'entiers. Le gabarit n'affiche alors rien.
    / A badly typed JSONField must never 500 the public page.
    """
    assert cartes_infos_pratiques(None) == []
    assert cartes_infos_pratiques("") == []
    assert cartes_infos_pratiques("Adresse") == []
    assert cartes_infos_pratiques({"type": "badge"}) == []
    assert cartes_infos_pratiques([]) == []
    # Items non-dictionnaires ignores un par un, sans casser les voisins.
    # / Non-dict items skipped one by one, without breaking their neighbours.
    cartes = cartes_infos_pratiques([
        42,
        None,
        {"type": "badge", "texte": "Adresse"},
        "texte libre",
        {"type": "adresse", "texte": "12 rue de la Coopérative"},
    ])
    assert len(cartes) == 1
    assert cartes[0]["intitule"] == "Adresse"
    assert len(cartes[0]["items"]) == 1


def test_un_badge_sans_texte_donne_une_carte_sans_intitule():
    """`texte` absent ou nul : la carte existe, sans etiquette."""
    cartes = cartes_infos_pratiques([
        {"type": "badge"},
        {"type": "para", "texte": "Sans intitule."},
    ])

    assert len(cartes) == 1
    assert cartes[0]["intitule"] == ""
    assert cartes[0]["items"][0]["texte"] == "Sans intitule."


def test_le_catalogue_declare_les_deux_affichages_du_bloc_lieu():
    """
    LIEU a deux affichages, et VOLONTAIREMENT aucune entree dans
    CHAMPS_PAR_AFFICHAGE : les deux dispositions consomment les memes champs.

    Ce test garde la decision explicite. Ajouter une entree a
    CHAMPS_PAR_AFFICHAGE["LIEU"] resserrerait les champs proposes par l'admin et
    masquerait `image` / `image_secondaire`, que le skin faire_festival rend.
    / LIEU has two layouts and deliberately no CHAMPS_PAR_AFFICHAGE entry: both
    consume the same fields, and the two image fields must stay offered.
    """
    from pages.blocs_catalogue import (
        AFFICHAGE_PAR_DEFAUT,
        AFFICHAGES_PAR_TYPE,
        CHAMPS_PAR_AFFICHAGE,
        CHAMPS_PAR_TYPE,
    )

    assert AFFICHAGES_PAR_TYPE["LIEU"] == ("VERTICAL", "HORIZONTAL")
    assert AFFICHAGE_PAR_DEFAUT["LIEU"] == "VERTICAL"
    assert "affichage" in CHAMPS_PAR_TYPE["LIEU"]
    assert "LIEU" not in CHAMPS_PAR_AFFICHAGE


def test_le_vertical_retombe_sur_le_gabarit_historique():
    """
    VERTICAL n'a pas de gabarit a son nom : il retombe sur `bloc_lieu.html`.

    C'est ce repli qui rend toute migration de donnees inutile — les blocs deja
    enregistres ont un `affichage` vide et suivent le meme chemin. Si quelqu'un
    creait un jour `bloc_lieu_vertical.html`, ce test resterait vrai ; il
    documente l'etat actuel, pas une interdiction.
    / VERTICAL has no template of its own and falls back to `bloc_lieu.html`,
    which is why no data migration is needed.
    """
    from django.template.loader import select_template

    gabarit = select_template([
        "pages/classic/partials/bloc_lieu_vertical.html",
        "pages/classic/partials/bloc_lieu.html",
    ])
    # Le nom EXACT, et non un `endswith` sur les deux candidats : `select_template`
    # n'en renvoie qu'UN, donc accepter les deux rendait l'assertion vraie quel que
    # soit le gabarit choisi. Elle ne prouvait que l'absence de
    # TemplateDoesNotExist, pas le repli — qui est precisement ce qu'elle documente,
    # puisque c'est lui qui rend toute migration de donnees inutile.
    # / The EXACT name, not an `endswith` over both candidates: select_template
    # returns only ONE, so accepting both made the assertion true whichever was
    # picked. It proved no TemplateDoesNotExist, not the fallback it documents.
    assert gabarit.template.name == "pages/classic/partials/bloc_lieu.html"

    # L'horizontal, lui, a bien son gabarit propre en V2.
    # / The horizontal layout does have its own V2 template.
    horizontal = select_template([
        "pages/V2/partials/bloc_lieu_horizontal.html",
        "pages/classic/partials/bloc_lieu.html",
    ])
    assert horizontal.template.name.endswith("bloc_lieu_horizontal.html")
