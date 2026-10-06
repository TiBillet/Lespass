"""
L'alignement des blocs de l'admin sur la colonne de contenu, et la fiche « Vente ».
/ Admin blocks aligned on the content column, and the "Sale" detail page.

LOCALISATION : tests/pytest/test_admin_alignements_et_fiche_vente.py

RÈGLES TESTÉES
- A. Les gabarits posés avant ou après un formulaire ou une liste ne se décalent pas
  de la colonne : leur bloc racine n'a pas de marge intérieure horizontale (`p-4`,
  `px-4`). Il n'a qu'un espacement vertical : `mb-6` avant un formulaire, `mt-6`
  après, `mb-4` au-dessus d'une liste.
- B. Les quatre écrans d'action (« Émettre un avoir » / « Avoir total », « Avoir sur
  un article », « Rejouer l'encaissement », « Annuler et rembourser ») prennent toute
  la colonne, comme un bloc de champs Unfold : un `fieldset class="module"` avec son
  titre, sans boîte étroite centrée (`max-width`, `margin: 40px auto`).
- C. Un bloc de champs ne déborde pas de la colonne : `min-width: 0` sur les
  `fieldset.module`, sélecteurs `filter_horizontal` souples. La fiche d'un
  utilisateur suit la même règle (`min-w-0`, titres sans marge négative, bouton qui
  passe à la ligne).
- D. Les lignes conditionnelles des tarifs sont marquées par une ombre intérieure,
  sans bordure, marge ni retrait.
- E. Fiche « Vente » : nature et statut en badge (jamais le tuple brut), titre
  « Vente n° X » (« Vente sans numéro » avant l'encaissement), quantité lisible sur
  l'écran « Avoir sur un article » d'une part d'historique, sans changer la quantité
  rendue.
/ A: no horizontal padding on before/after templates. B: full-width action screens.
C: no overflowing fieldsets. D: inset shadow on conditional rows. E: sale page badges,
title and readable quantity.

SIMULATIONS
Chaque test qui touche la base est marqué `django_db` : la transaction est annulée
à la fin (tests/PIEGES.md 13.1). Les ventes sont écrites par le service de vente.
Stripe et Celery sont simulés, la `Configuration` est modifiée en mémoire seulement
(13.5). Le client de l'admin est créé dans chaque test (13.10).
/ Rolled back per test; sales through the service; Stripe and Celery faked.

Lancer / Run : make test ARGS="tests/pytest/test_admin_alignements_et_fiche_vente.py"
"""

import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.utils import translation
from django_tenants.utils import tenant_context

from BaseBillet.models import PaymentMethod
from BaseBillet.models_vente import Vente
from fabriques_panier import (
    catalogue_stripe_simule,
    configuration_modifiee,
    creer_utilisateur,
    taches_celery_enregistrees,
)
from test_admin_ecrit_la_vente import vendre_et_relire
from test_admin_vente import (
    adresse_de_la_fiche,
    adresse_de_l_avoir_total,
    adresse_du_rejeu_de_l_encaissement,
    client_de_l_admin_du_lieu,
    ouvrir_une_vente_en_ligne_en_attente,
    ouvrir_une_vente_stripe_en_attente_paiement_valide,
    vendre_trois_jus_en_deux_parts,
    vendre_trois_jus_par_cb,
    ventes_d_avoir_de,
)
from test_avoirs_ecrivent_la_vente import (
    ACTION_ANNULER_LES_RESERVATIONS,
    URL_DE_LA_LISTE_DES_RESERVATIONS,
    lancer_l_action_d_annulation,
)

# Le dossier racine du projet (les gabarits et le CSS sont lus sur le disque).
# / The project root (templates and CSS are read from disk).
RACINE_DU_PROJET = Path(settings.BASE_DIR)
DOSSIER_DES_GABARITS_DE_L_ADMIN = (
    RACINE_DU_PROJET / "Administration" / "templates" / "admin"
)


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant, mock_stripe):
    """
    Le lieu `lespass`, caisse et monnaie locale activées en mémoire, avec Stripe
    (session, catalogue) et Celery simulés.
    / The `lespass` venue, register and local currency on in memory, Stripe and
    Celery faked.
    """
    with tenant_context(tenant):
        with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
            with catalogue_stripe_simule():
                with taches_celery_enregistrees() as taches_demandees:
                    yield SimpleNamespace(
                        tenant=tenant, taches_demandees=taches_demandees
                    )


# --------------------------------------------------------------------------
# Outils
# / Helpers
# --------------------------------------------------------------------------


def balise_ouvrante_de_l_element(html_de_la_page, testid):
    """
    La balise ouvrante de l'élément qui porte ce `data-testid` (par exemple
    `<fieldset class="module ..." data-testid="avoir-ecran">`), ou None.
    / The opening tag of the element carrying this data-testid, or None.
    """
    motif_de_la_balise = re.compile(
        r"<[a-z]+[^>]*data-testid=\"" + re.escape(testid) + r"\"[^>]*>"
    )
    resultat = motif_de_la_balise.search(html_de_la_page)
    if resultat is None:
        return None
    return resultat.group(0)


def verifier_l_ecran_en_pleine_largeur(reponse, testid):
    """
    Vérifie qu'un écran d'action prend la colonne de contenu comme un bloc de champs
    Unfold : l'élément `testid` est un `fieldset class="module"`, sans largeur maximale
    ni marge automatique ; la page ne garde aucune boîte centrée ; le titre a la
    classe du titre d'un bloc de champs Unfold (`bg-base-100`).
    / Checks an action screen is a full-width Unfold fieldset.
    """
    assert reponse.status_code == 200, reponse.status_code
    html_de_la_page = reponse.content.decode()

    balise_de_l_ecran = balise_ouvrante_de_l_element(html_de_la_page, testid)
    assert balise_de_l_ecran is not None, f"Aucun élément data-testid={testid}."
    assert balise_de_l_ecran.startswith("<fieldset"), balise_de_l_ecran
    assert 'class="module' in balise_de_l_ecran, balise_de_l_ecran
    assert "max-width" not in balise_de_l_ecran, balise_de_l_ecran
    assert "margin: 40px auto" not in html_de_la_page

    # Le contenu de l'écran est dans la colonne de la fiche (`#content-main`), et son
    # titre a la forme du titre d'un bloc de champs Unfold.
    # / The screen sits in `#content-main`, its title shaped like an Unfold fieldset title.
    assert 'id="content-main"' in html_de_la_page
    titre_de_l_ecran = balise_ouvrante_de_l_element(html_de_la_page, testid + "-titre")
    assert titre_de_l_ecran is not None, f"Aucun titre data-testid={testid}-titre."
    assert titre_de_l_ecran.startswith("<h2"), titre_de_l_ecran
    assert "bg-base-100" in titre_de_l_ecran, titre_de_l_ecran


def contenu_du_champ_de_la_fiche(html_de_la_page, libelle_du_champ):
    """
    Le HTML d'un champ en lecture seule de la fiche : de son libellé
    (`<label ...>Nature</label>`) jusqu'au libellé suivant. Unfold ne pose pas de
    classe `field-<nom>` sur un champ en lecture seule : on part du libellé.
    / The HTML of one read-only field, from its label to the next label.
    """
    fin_du_libelle = f">{libelle_du_champ}</label>"
    debut = html_de_la_page.find(fin_du_libelle)
    assert debut != -1, f"Champ « {libelle_du_champ} » absent de la fiche."
    fin = html_de_la_page.find("</label>", debut + len(fin_du_libelle))
    if fin == -1:
        fin = len(html_de_la_page)
    return html_de_la_page[debut:fin]


# --------------------------------------------------------------------------
# A — Gabarits avant / après : pas de retrait horizontal
# / A — Before / after templates: no horizontal inset
# --------------------------------------------------------------------------

# Chaque gabarit, et l'espacement vertical attendu sur son bloc racine :
# `mb-6` avant un formulaire (le formulaire espace ses blocs de 24 px, `gap-6`),
# `mt-6` après un formulaire, `mb-4` au-dessus d'une liste.
# / Each template and the vertical spacing expected on its root block.
GABARITS_ET_ESPACEMENT_ATTENDU = [
    ("membership/actions_panel.html", "mb-6"),
    ("membership/custom_form.html", "mt-6"),
    ("reservation/custom_form.html", "mt-6"),
    ("ghost/panneau_newsletter.html", "mb-6"),
    ("comptable/plan_complet.html", "mb-4"),
    ("comptable/changelist_before.html", "mb-4"),
    ("comptable/monnaies_changelist_before.html", "mb-4"),
    ("asset/asset_list_before.html", "mb-4"),
    ("asset/asset_change_form_before.html", "mb-6"),
    ("scanapp/list_before.html", "mb-4"),
    ("asset/asset_changelist_invitations.html", "mb-4"),
    ("federation/federation_list_before.html", "mb-4"),
    ("federation/federation_members.html", "mb-6"),
]

# Un bloc racine : une balise `div` en début de ligne, sans retrait.
# / A root block: a `div` tag at the start of a line, not indented.
MOTIF_DES_BLOCS_RACINES = re.compile(r"^<div\b[^>]*>", re.MULTILINE)


@pytest.mark.parametrize(
    "chemin_du_gabarit,espacement_attendu", GABARITS_ET_ESPACEMENT_ATTENDU
)
def test_gabarit_avant_apres_sans_retrait_horizontal(
    chemin_du_gabarit, espacement_attendu
):
    """
    Le bloc racine d'un gabarit avant / après n'a pas de marge intérieure horizontale
    (`p-4`, `px-4`) : ses cartes s'alignent sur les blocs de champs et la barre
    d'enregistrement. Il a l'espacement vertical attendu.
    / A before/after template root block has no horizontal padding, and the expected
    vertical spacing.
    """
    texte_du_gabarit = (DOSSIER_DES_GABARITS_DE_L_ADMIN / chemin_du_gabarit).read_text()
    blocs_racines = MOTIF_DES_BLOCS_RACINES.findall(texte_du_gabarit)
    assert blocs_racines, f"Aucun bloc racine dans {chemin_du_gabarit}."

    for bloc_racine in blocs_racines:
        classes_du_bloc = re.search(r'class="([^"]*)"', bloc_racine)
        assert classes_du_bloc is not None, bloc_racine
        liste_des_classes = classes_du_bloc.group(1).split()
        assert "p-4" not in liste_des_classes, bloc_racine
        assert "px-4" not in liste_des_classes, bloc_racine
        assert espacement_attendu in liste_des_classes, bloc_racine


# --------------------------------------------------------------------------
# B — Écrans d'action en pleine largeur, comme un bloc de champs Unfold
# / B — Full-width action screens, like an Unfold fieldset
# --------------------------------------------------------------------------


def test_ecran_avoir_total_en_pleine_largeur(lieu):
    """
    « Avoir total » d'une vente réglée (gabarit admin/vente/avoir_total.html) :
    un bloc de champs Unfold, pas une boîte centrée.
    / The "Full credit note" screen is a full-width Unfold fieldset.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_par_cb(creer_utilisateur())

    reponse = client_de_l_admin.get(adresse_de_l_avoir_total(vente))

    verifier_l_ecran_en_pleine_largeur(reponse, "avoir-ecran")


def test_ecrans_avoir_sur_un_article_en_pleine_largeur(lieu):
    """
    « Avoir sur un article » : l'écran de la liste des articles, puis celui de
    l'article choisi, en blocs de champs Unfold.
    / Both "Credit note on one item" screens are full-width Unfold fieldsets.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_par_cb(creer_utilisateur())
    ligne_des_jus = vente.articles.get()
    adresse_de_la_liste = f"/admin/BaseBillet/vente/{vente.uuid}/avoir_sur_un_article/"

    reponse_de_la_liste = client_de_l_admin.get(adresse_de_la_liste)
    reponse_de_l_article = client_de_l_admin.get(
        f"{adresse_de_la_liste}?ligne={ligne_des_jus.pk}"
    )

    verifier_l_ecran_en_pleine_largeur(reponse_de_la_liste, "avoir-article-ecran")
    verifier_l_ecran_en_pleine_largeur(reponse_de_l_article, "avoir-article-ecran")


def test_ecran_rejouer_l_encaissement_en_pleine_largeur(lieu):
    """
    « Rejouer l'encaissement » d'une vente en ligne restée en attente : un bloc de
    champs Unfold.
    / The "Replay settlement" screen is a full-width Unfold fieldset.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente, _paiement = ouvrir_une_vente_stripe_en_attente_paiement_valide()

    reponse = client_de_l_admin.get(adresse_du_rejeu_de_l_encaissement(vente))

    verifier_l_ecran_en_pleine_largeur(reponse, "rejeu-ecran")


def test_ecran_annuler_et_rembourser_en_pleine_largeur(lieu):
    """
    « Annuler et rembourser » (action de la liste des réservations) : l'écran de
    confirmation est un bloc de champs Unfold.
    / The "Cancel and refund" confirmation screen is a full-width Unfold fieldset.
    """
    vente_admin = vendre_et_relire(
        lieu, prix="10.00", quantite=2, moyen_de_paiement=PaymentMethod.CC
    )
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)

    reponse = lancer_l_action_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_RESERVATIONS,
        ACTION_ANNULER_LES_RESERVATIONS,
        [vente_admin.reservation],
    )

    verifier_l_ecran_en_pleine_largeur(reponse, "annulation-ecran")


# --------------------------------------------------------------------------
# C — Blocs de champs qui ne débordent pas
# / C — Fieldsets that do not overflow
# --------------------------------------------------------------------------


def test_css_des_blocs_de_champs_sans_debordement():
    """
    La feuille de l'admin (static/css/tibillet-admin.css) donne `min-width: 0` aux
    blocs de champs, et des sélecteurs `filter_horizontal` souples (`flex: 1 1 0`,
    `min-width: 0`, largeur automatique).
    / The admin stylesheet gives fieldsets `min-width: 0` and flexible
    filter_horizontal selectors.
    """
    texte_du_css = (
        RACINE_DU_PROJET / "static" / "css" / "tibillet-admin.css"
    ).read_text()

    regle_des_blocs_de_champs = re.search(
        r"#content-main fieldset\.module\s*\{([^}]*)\}", texte_du_css
    )
    assert regle_des_blocs_de_champs is not None
    assert re.search(r"min-width:\s*0\s*;", regle_des_blocs_de_champs.group(1))

    regle_des_selecteurs = re.search(
        r"\.selector-available,\s*html \.selector-chosen\s*\{([^}]*)\}", texte_du_css
    )
    assert regle_des_selecteurs is not None
    corps_de_la_regle = regle_des_selecteurs.group(1)
    assert re.search(r"width:\s*auto\s*;", corps_de_la_regle)
    assert re.search(r"flex:\s*1 1 0\s*;", corps_de_la_regle)
    assert re.search(r"min-width:\s*0\s*;", corps_de_la_regle)


def test_fiche_utilisateur_blocs_sans_debordement():
    """
    La fiche d'un utilisateur (admin/human_user/right_and_wallet_info.html) : ses
    blocs de champs ont `min-w-0`, leurs titres n'ont plus de marge négative, et le
    bouton des cartes peut passer à la ligne.
    / The user page: fieldsets with min-w-0, titles without negative margin, the cards
    button can wrap.
    """
    texte_du_gabarit = (
        DOSSIER_DES_GABARITS_DE_L_ADMIN / "human_user" / "right_and_wallet_info.html"
    ).read_text()

    balises_des_blocs = re.findall(r"<fieldset\b[^>]*>", texte_du_gabarit)
    assert len(balises_des_blocs) == 4
    for balise_du_bloc in balises_des_blocs:
        assert "min-w-0" in balise_du_bloc, balise_du_bloc

    assert "-mx-4" not in texte_du_gabarit

    bouton_des_cartes = re.search(
        r"<button[^>]*admin_my_cards[^>]*>", texte_du_gabarit, re.DOTALL
    )
    assert bouton_des_cartes is not None
    assert "whitespace-nowrap" not in bouton_des_cartes.group(0)


# --------------------------------------------------------------------------
# D — Lignes conditionnelles des tarifs sans décalage
# / D — Price conditional rows without offset
# --------------------------------------------------------------------------


def test_lignes_conditionnelles_marquees_par_une_ombre_sans_decalage():
    """
    Le script des champs conditionnels des inlines marque une ligne par une ombre
    intérieure : aucune bordure, marge ni retrait, la ligne reste alignée.
    / The inline conditional fields script marks a row with an inset shadow only.
    """
    texte_du_script = (
        RACINE_DU_PROJET
        / "Administration"
        / "static"
        / "admin"
        / "js"
        / "inline_conditional_fields.js"
    ).read_text()
    debut_de_la_fonction = texte_du_script.index("function appliquer_style_rangee")
    fin_de_la_fonction = texte_du_script.index("\n    }\n", debut_de_la_fonction)
    corps_de_la_fonction = texte_du_script[debut_de_la_fonction:fin_de_la_fonction]

    assert "boxShadow" in corps_de_la_fonction
    assert "inset 3px 0 0" in corps_de_la_fonction
    assert "borderLeft" not in corps_de_la_fonction
    assert "marginLeft" not in corps_de_la_fonction
    assert "paddingLeft" not in corps_de_la_fonction


# --------------------------------------------------------------------------
# E — Fiche « Vente »
# / E — "Sale" detail page
# --------------------------------------------------------------------------


def test_fiche_vente_nature_et_statut_en_badge(lieu):
    """
    La fiche d'une vente réglée affiche « Nature » et « Statut » en badge Unfold
    (vert pour une vente, vert pour réglée), jamais le tuple brut `('VENTE', ...)`.
    / The sale page shows nature and status as Unfold badges, never the raw tuple.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_en_deux_parts(creer_utilisateur())

    reponse = client_de_l_admin.get(adresse_de_la_fiche(vente))

    assert reponse.status_code == 200
    html_de_la_page = reponse.content.decode()
    assert "(&#x27;VENTE&#x27;" not in html_de_la_page
    assert "(&#x27;REGLEE&#x27;" not in html_de_la_page
    ligne_de_la_nature = contenu_du_champ_de_la_fiche(html_de_la_page, "Nature")
    ligne_du_statut = contenu_du_champ_de_la_fiche(html_de_la_page, "Statut")
    assert re.search(
        r'<span class="[^"]*bg-green-100[^"]*"[^>]*>\s*Vente\s*</span>',
        ligne_de_la_nature,
    )
    assert re.search(
        r'<span class="[^"]*bg-green-100[^"]*"[^>]*>\s*Réglée\s*</span>',
        ligne_du_statut,
    )


def test_liste_des_ventes_nature_et_statut_en_badge(lieu):
    """
    La liste des ventes garde ses badges de nature et de statut.
    / The sales list keeps its nature and status badges.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    acheteur = creer_utilisateur()
    vendre_trois_jus_en_deux_parts(acheteur)

    reponse = client_de_l_admin.get("/admin/BaseBillet/vente/", {"q": acheteur.email})

    assert reponse.status_code == 200
    html_de_la_page = reponse.content.decode()
    assert "(&#x27;VENTE&#x27;" not in html_de_la_page
    assert re.search(
        r'<span class="[^"]*bg-green-100[^"]*"[^>]*>\s*Vente\s*</span>', html_de_la_page
    )
    assert re.search(
        r'<span class="[^"]*bg-green-100[^"]*"[^>]*>\s*Réglée\s*</span>',
        html_de_la_page,
    )


def test_titre_de_la_fiche_vente_numerotee(lieu):
    """
    Le titre de la fiche d'une vente réglée est « Vente n° X », jamais
    « Vente object (uuid) ».
    / A settled sale page is titled "Vente n° X".
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_en_deux_parts(creer_utilisateur())

    reponse = client_de_l_admin.get(adresse_de_la_fiche(vente))

    html_de_la_page = reponse.content.decode()
    assert "Vente object" not in html_de_la_page
    assert f"Vente n° {vente.numero}" in html_de_la_page
    assert str(vente) == f"Vente n° {vente.numero}"


def test_titre_de_la_fiche_vente_sans_numero(lieu):
    """
    Une vente pas encore réglée n'a pas de numéro : son titre le dit (« Vente sans
    numéro », avec son statut).
    / A sale without a number is titled "Vente sans numéro".
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = ouvrir_une_vente_en_ligne_en_attente(creer_utilisateur(), depuis_minutes=5)

    reponse = client_de_l_admin.get(adresse_de_la_fiche(vente))

    html_de_la_page = reponse.content.decode()
    assert "Vente object" not in html_de_la_page
    assert "Vente sans numéro" in html_de_la_page
    assert str(vente) == "Vente sans numéro — En attente"


def test_avoir_sur_une_part_d_historique_quantite_lisible(lieu):
    """
    L'écran « Avoir sur un article » d'une part d'historique (1,571429 jus) propose
    une quantité lisible (1,571 : 3 décimales au plus), jamais 1,571429.
    / The screen offers a readable quantity (1.571), never 1.571429.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_en_deux_parts(creer_utilisateur())
    ligne_de_la_seconde_part = vente.articles.get(total_ttc=550)
    adresse_de_l_article = (
        f"/admin/BaseBillet/vente/{vente.uuid}/avoir_sur_un_article/"
        f"?ligne={ligne_de_la_seconde_part.pk}"
    )

    reponse = client_de_l_admin.get(adresse_de_l_article)

    assert reponse.status_code == 200
    quantite_proposee = Decimal(str(reponse.context["form"]["quantite"].value()))
    assert quantite_proposee == Decimal("1.571")
    html_de_la_page = reponse.content.decode()
    assert "571429" not in html_de_la_page


def test_avoir_sur_une_part_d_historique_rend_toute_la_quantite_exacte(lieu):
    """
    La quantité lisible proposée (1,571), renvoyée telle quelle, rend toute la part
    exacte (1,571429) : l'avoir vaut −550, comme la part.
    / Posting the offered readable quantity gives back the whole exact part (−550).
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_en_deux_parts(creer_utilisateur())
    ligne_de_la_seconde_part = vente.articles.get(total_ttc=550)
    adresse_de_l_article = (
        f"/admin/BaseBillet/vente/{vente.uuid}/avoir_sur_un_article/"
        f"?ligne={ligne_de_la_seconde_part.pk}"
    )
    reponse_de_l_ecran = client_de_l_admin.get(adresse_de_l_article)
    quantite_proposee = reponse_de_l_ecran.context["form"]["quantite"].value()

    reponse = client_de_l_admin.post(
        adresse_de_l_article,
        {"quantite": str(quantite_proposee), "moyen_rembourse": PaymentMethod.CASH},
    )

    assert reponse.status_code == 302
    avoirs = ventes_d_avoir_de(vente)
    assert len(avoirs) == 1
    article_d_avoir = avoirs[0].articles.get()
    assert article_d_avoir.qty == -Decimal("1.571429")
    assert article_d_avoir.total_ttc == -550
    assert avoirs[0].nature == Vente.Nature.AVOIR


def test_inlines_de_la_fiche_vente_sans_titre_de_ligne_et_quantites_a_la_francaise(lieu):
    """
    La fiche de la vente fil rouge (3 jus en deux parts, monnaie locale 5,00 € + CB
    5,50 €) :
    - les inlines « Articles » et « Règlements » n'ont plus de titre au-dessus de
      chaque ligne (option Unfold `hide_title`) : ni uuid court, ni
      « Reglement object (…) », ni titre qui répète les colonnes ;
    - les colonnes restent : produit et moyen de paiement, une cellule par ligne ;
    - les quantités s'écrivent à la française, 3 décimales au plus : 1,429 et 1,571,
      jamais 1.43 ni 1.57.
    / Sale page inlines: no row title any more, columns kept, French quantities.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_en_deux_parts(creer_utilisateur())
    nom_du_produit = vente.articles.first().pricesold.productsold.product.name

    reponse = client_de_l_admin.get(adresse_de_la_fiche(vente))

    assert reponse.status_code == 200
    html_de_la_page = reponse.content.decode()
    # Le titre d'une ligne d'inline tabulaire Unfold est un paragraphe de classe
    # « group/title » (unfold/helpers/edit_inline/tabular_title.html).
    # / The Unfold tabular inline row title is a "group/title" paragraph.
    assert "group/title" not in html_de_la_page
    assert "Reglement object" not in html_de_la_page
    cellules_du_produit = re.findall(
        r"<td[^>]*field-produit[^>]*>\s*(.*?)\s*</td>", html_de_la_page, re.DOTALL
    )
    cellules_du_moyen = re.findall(
        r"<td[^>]*field-moyen_affiche[^>]*>\s*(.*?)\s*</td>", html_de_la_page, re.DOTALL
    )
    textes_du_produit = []
    for cellule in cellules_du_produit:
        textes_du_produit.append(re.sub(r"<[^>]+>", "", cellule).strip())
    assert textes_du_produit == [nom_du_produit, nom_du_produit]
    assert len(cellules_du_moyen) == 2
    assert "1,429" in html_de_la_page
    assert "1,571" in html_de_la_page
    assert ">1.43<" not in html_de_la_page.replace(" ", "").replace("\n", "")
    assert ">1.57<" not in html_de_la_page.replace(" ", "").replace("\n", "")


# --------------------------------------------------------------------------
# F — Les lignes (`LigneArticle`) n'ont plus d'admin ; l'export passe par les ventes
# / F — Lines have no admin any more; the export goes through the sales
# --------------------------------------------------------------------------


def test_lignearticle_n_est_pas_enregistree_dans_l_admin_du_lieu():
    """
    `LigneArticle` n'a plus de ModelAdmin sur le site du lieu : ni liste, ni fiche,
    ni bouton « Avoir » de ligne. Les articles se lisent sur la fiche de leur vente.
    / LigneArticle is not registered on the venue admin site.
    """
    from Administration.admin.site import staff_admin_site
    from BaseBillet.models import LigneArticle

    assert not staff_admin_site.is_registered(LigneArticle)


def test_les_anciennes_adresses_des_lignes_repondent_404(lieu):
    """
    La liste des lignes et l'ancien bouton « Avoir » d'une ligne répondent 404.
    / The old lines list and line credit note addresses answer 404.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_par_cb(creer_utilisateur())
    ligne_des_jus = vente.articles.get()

    reponse_de_la_liste = client_de_l_admin.get("/admin/BaseBillet/lignearticle/")
    reponse_de_la_fiche = client_de_l_admin.get(
        f"/admin/BaseBillet/lignearticle/{ligne_des_jus.pk}/change/"
    )
    reponse_de_l_avoir = client_de_l_admin.get(
        f"/admin/BaseBillet/lignearticle/{ligne_des_jus.pk}/emettre_avoir/"
    )

    assert reponse_de_la_liste.status_code == 404
    assert reponse_de_la_fiche.status_code == 404
    assert reponse_de_l_avoir.status_code == 404


def liens_et_titres_du_menu(elements_du_menu):
    """
    Tous les (lien, titre) de la barre latérale, sous-menus compris.
    / Every (link, title) of the sidebar, sub-menus included.
    """
    liens_et_titres = []
    for element in elements_du_menu:
        liens_et_titres.append(
            (str(element.get("link") or ""), str(element.get("title") or ""))
        )
        liens_et_titres.extend(liens_et_titres_du_menu(element.get("items") or []))
    return liens_et_titres


def test_le_menu_ne_cite_plus_les_lignes(lieu):
    """
    La barre latérale n'a plus d'entrée vers les lignes (« Entries »).
    / The sidebar has no entry to the lines any more.
    """
    from Administration.admin.dashboard import get_sidebar_navigation

    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    requete = client_de_l_admin.get("/admin/").wsgi_request

    with translation.override("en"):
        liens_et_titres = liens_et_titres_du_menu(get_sidebar_navigation(requete))

    assert liens_et_titres, "Barre latérale vide : test sans objet."
    for lien, titre in liens_et_titres:
        assert "lignearticle" not in lien, (lien, titre)
        assert titre != "Entries", (lien, titre)


def test_export_des_ventes_contient_les_colonnes_de_l_ancien_export(lieu):
    """
    Le bouton « Exporter » de la liste des ventes (filtrée sur le client) rend un CSV
    des ARTICLES de ces ventes : BOM pour Excel, mêmes colonnes que l'ancien export
    des lignes (`LigneArticleExportResource`), une ligne par article.
    / The sales list export: a CSV of the sales' items, BOM, same columns as the old
    lines export, one row per item.
    """
    import csv
    import io

    from import_export.formats.base_formats import CSV

    from Administration.admin.site import staff_admin_site
    from Administration.importers.lignearticle_exporter import (
        LigneArticleExportResource,
    )

    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    acheteur = creer_utilisateur()
    vendre_trois_jus_en_deux_parts(acheteur)
    admin_des_ventes = staff_admin_site._registry[Vente]
    rang_du_format_csv = None
    for rang, format_d_export in enumerate(admin_des_ventes.get_export_formats()):
        if format_d_export is CSV:
            rang_du_format_csv = rang
    assert rang_du_format_csv is not None

    reponse = client_de_l_admin.post(
        f"/admin/BaseBillet/vente/export/?q={acheteur.email}",
        {"format": str(rang_du_format_csv), "resource": "0"},
    )

    assert reponse.status_code == 200, reponse.status_code
    contenu = reponse.content
    assert contenu.startswith("﻿".encode("utf-8"))
    lignes_du_csv = list(csv.reader(io.StringIO(contenu.decode("utf-8-sig"))))
    with translation.override("fr"):
        titres_de_l_ancien_export = []
        for titre in LigneArticleExportResource().get_export_headers():
            titres_de_l_ancien_export.append(str(titre))
    assert lignes_du_csv[0] == titres_de_l_ancien_export
    assert len(titres_de_l_ancien_export) == 15
    assert len(lignes_du_csv) == 1 + 2


def test_aucun_gabarit_ni_code_ne_renvoie_vers_l_admin_des_lignes():
    """
    Aucun gabarit, JavaScript ou code Python du projet (hors tests et fichiers
    collectés `www/`) ne renvoie vers l'ancienne liste ou fiche des lignes.
    / No template, JavaScript or Python code links to the old lines admin.
    """
    morceaux_interdits = [
        "lignearticle_changelist",
        "lignearticle_change",
        "/admin/BaseBillet/lignearticle/",
    ]
    dossiers_ignores = {"www", "tests", "node_modules", ".git", "TECH_DOC", "CHANGELOG"}
    fichiers_fautifs = []
    for chemin in RACINE_DU_PROJET.rglob("*"):
        if not chemin.is_file() or chemin.suffix not in {".py", ".html", ".js"}:
            continue
        parties_du_chemin = set(chemin.relative_to(RACINE_DU_PROJET).parts)
        if parties_du_chemin & dossiers_ignores:
            continue
        texte = chemin.read_text(errors="ignore")
        for morceau in morceaux_interdits:
            if morceau in texte:
                fichiers_fautifs.append(
                    (str(chemin.relative_to(RACINE_DU_PROJET)), morceau)
                )
    assert fichiers_fautifs == []


def test_inline_des_reglements_affiche_le_nom_de_la_monnaie_lu_une_fois(lieu):
    """
    Une vente de 3 jus (10,50 €) payée 2,50 € + 2,50 € en monnaie locale du lieu et
    5,50 € par CB. L'inline « Règlements » de la fiche :
    - colonne « Monnaie » : le NOM de la monnaie locale pour ses deux règlements
      (jamais son uuid), « — » pour la CB ;
    - les noms sont lus UNE fois pour tout l'inline (`noms_des_monnaies_des_ventes`
      appelé une seule fois), pas une fois par règlement.
    / Payments inline: the currency NAME (never its uuid), "—" for the card, names
    read once for the whole inline.
    """
    from unittest.mock import patch

    from Administration import admin_tenant
    from BaseBillet.models import LigneArticle, SaleOrigin
    from BaseBillet.services_vente import (
        ajouter_article,
        ajouter_reglement,
        encaisser_vente,
        ouvrir_vente,
    )
    from fabriques_vente import creer_tarif_vendu
    from test_caisse_ecrit_la_vente import monnaie_locale_du_lieu

    monnaie_locale = monnaie_locale_du_lieu(lieu)
    assert monnaie_locale is not None, "Le lieu n'a pas de monnaie locale."
    vente = ouvrir_vente(
        origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE, client=creer_utilisateur()
    )
    ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(nom="Jus", prix_en_euros="3.50"),
        quantite=Decimal("3"),
        prix_unitaire=350,
        taux_tva=Decimal("20"),
        status=LigneArticle.VALID,
    )
    ajouter_reglement(
        vente, moyen=PaymentMethod.LOCAL_EURO, montant=250, asset=monnaie_locale.uuid
    )
    ajouter_reglement(
        vente, moyen=PaymentMethod.LOCAL_EURO, montant=250, asset=monnaie_locale.uuid
    )
    ajouter_reglement(vente, moyen=PaymentMethod.CC, montant=550)
    vente = Vente.objects.get(pk=encaisser_vente(vente).pk)
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)

    with patch.object(
        admin_tenant,
        "noms_des_monnaies_des_ventes",
        wraps=admin_tenant.noms_des_monnaies_des_ventes,
    ) as lecture_des_noms:
        reponse = client_de_l_admin.get(adresse_de_la_fiche(vente))

    assert reponse.status_code == 200
    html_de_la_page = reponse.content.decode()
    assert str(monnaie_locale.uuid) not in html_de_la_page
    cellules_de_la_monnaie = re.findall(
        r'<td[^>]*field-monnaie[^>]*>\s*(.*?)\s*</td>', html_de_la_page, re.DOTALL
    )
    textes_des_cellules = []
    for cellule in cellules_de_la_monnaie:
        textes_des_cellules.append(re.sub(r"<[^>]+>", "", cellule).strip())
    assert sorted(textes_des_cellules) == sorted(
        [monnaie_locale.name, monnaie_locale.name, "—"]
    ), textes_des_cellules
    assert lecture_des_noms.call_count == 1
