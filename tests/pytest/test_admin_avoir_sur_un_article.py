"""
L'action « Avoir sur un article » de la fiche « Vente » de l'admin.
/ The "Credit note on one item" action of the admin "Sale" page.

LOCALISATION : tests/pytest/test_admin_avoir_sur_un_article.py

RÈGLE MÉTIER TESTÉE
Depuis la fiche d'une vente réglée, l'admin rend une partie d'un article : par exemple
1 jus sur 3. L'avoir est une vente AVOIR liée à la vente, avec le même prix unitaire et
une quantité négative, écrite par `ecrire_la_vente_d_avoir_d_une_ligne` (origine ADMIN).
- L'écran ne propose que les articles du chiffre d'affaires (ni recharge, ni article
  d'écart) qui ont encore une quantité à rendre (la quantité vendue, moins celle des
  avoirs déjà faits). Au moment d'écrire, cette
  quantité est relue sous verrou : deux envois identiques n'écrivent qu'un avoir.
- Le champ « Remboursé par » suit D27 : pas de champ pour un article payé par Stripe
  (règlement négatif au moyen Stripe d'origine, référence vide, message « remboursez
  depuis Stripe ») ; sinon il est pré-rempli par le moyen d'origine.
- Une ligne payée en partie en jetons cadeau et en partie en espèces : « Remboursé
  par » est demandé, l'avoir rend un règlement LG (monnaie et carte du règlement LG
  d'origine) et le reste au moyen choisi.
- REFUS (rien n'est écrit) : une quantité plus grande que le reste ; une partie d'un
  article qui a une part offerte ou une part payée en jetons (« rembourser l'article
  entier ») ; une partie d'un article au poids ou à la tireuse (Q-H5 : seulement
  l'article entier, la quantité proposée n'est pas modifiable).
- REFUS DU SERVICE (pour tous les appelants, testés sans l'écran) : une vente qui
  porte un écart d'encaissement (aucun avoir sur ses articles, Q-H13) ; une
  recharge cashless ; une partie non entière d'un article à la pièce ; une partie d'une
  pesée. Tout ce qui reste, même non entier (une « part » d'historique), passe.
- REFUS DE L'ÉCRAN sur l'état de la vente : vente pas réglée, vente en points,
  vente qui porte un écart d'encaissement (le bouton de la fiche est caché, l'écran
  renvoie à la fiche avec le message du service).
/ Partial credit note of one item from the sale page; refusals (service and screen);
D27 for Stripe.

CONTRAT DE L'ÉCRAN (ce que ces tests supposent de l'interface)
- adresse : `/admin/BaseBillet/vente/<uuid de la vente>/avoir_sur_un_article/` ;
- GET sans paramètre : l'écran de la liste des articles qui ont un reste à rendre (200) ;
  la clé (`pk`) de chaque article proposé est écrite dans la page, celle d'un article
  entièrement rendu ne l'est pas ;
- GET `?ligne=<pk de la ligne>` : l'écran de l'article choisi (200), avec un formulaire
  `form` dans le contexte. Il a le champ `quantite` ; pour un article au poids ou à la
  tireuse, sa valeur proposée est le reste et il n'est pas modifiable (`disabled`, ou
  attribut `readonly` du widget). Il a le champ `moyen_rembourse` seulement s'il y a de
  l'argent à rendre hors Stripe, pré-rempli par le moyen d'origine ;
- POST `?ligne=<pk de la ligne>` avec `quantite` (point décimal) et `moyen_rembourse` :
  l'avoir (302). Un refus laisse un message d'erreur (302), ou réaffiche l'écran avec
  une erreur du formulaire (200) ; dans les deux cas, rien n'est écrit.
/ Screen contract: address, list screen, item screen with its form, POST answers.

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin
(tests/PIEGES.md 13.1). Les ventes sont écrites par le service de vente. Stripe et
Celery sont simulés, la `Configuration` est modifiée en mémoire seulement
(tests/PIEGES.md 13.5). Le client de l'admin est créé dans chaque test (13.10).
/ Rolled back per test; sales through the service; Stripe and Celery faked.

D'OÙ VIENNENT LES VALEURS ATTENDUES
- 3 jus à 3,50 € : un jus rendu = −350 ;
- comté 0,350 kg à 12,90 €/kg : 0,350 × 1290 = 451,5 → 452 ;
- tirage 0,50 L à 6,00 €/L : 0,50 × 600 = 300 ;
- 2 billets à 10,00 € payés par Stripe : un billet rendu = −1000.
/ Expected values: juice −350, cheese 452, tap 300, Stripe ticket −1000.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-H-retrait.md (§2 « Avoir sur
un article », §5 test 5c) ; brief CHANTIER-05-briefs/05-H-1d.md (tests 1 à 6) ;
CHANTIER-05-montants-entiers.md D13, D27 ; SUIVI Q-H5, Q-H13 ; brief
CHANTIER-05-briefs/05-H-1-ter.md (tests 3, 4 et 8).

Lancer / Run : make test ARGS="tests/pytest/test_admin_avoir_sur_un_article.py"
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib import messages
from django.contrib.messages import get_messages
from django.utils import translation
from django_tenants.utils import tenant_context

from BaseBillet.models import (
    LigneArticle,
    Paiement_stripe,
    PaymentMethod,
    Product,
    SaleOrigin,
)
from BaseBillet.models_vente import Reglement, Vente
from BaseBillet.services_vente import (
    MESSAGE_AVOIR_LIGNE_VENTE_AVEC_UN_ECART,
    ajouter_article,
    ajouter_l_article_d_ecart_d_encaissement,
    ajouter_reglement,
    ecrire_la_vente_d_avoir_d_une_ligne,
    encaisser_vente,
    encaisser_vente_stripe,
    ouvrir_vente,
)
from fabriques_panier import (
    catalogue_stripe_simule,
    configuration_modifiee,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fabriques_vente import (
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from test_admin_vente import (
    adresse_de_la_fiche,
    client_de_l_admin_du_lieu,
    message_traduit,
    moyens_et_montants,
    ouvrir_une_vente_en_ligne_en_attente,
    textes_des_messages,
    vendre_en_ligne_avec_un_ecart_d_encaissement,
    vendre_trois_jus_en_deux_parts,
    vendre_une_planche_en_points,
    vendre_une_recharge_de_carte_par_cb,
    ventes_d_avoir_de,
)
from test_caisse_ecrit_la_vente import monnaie_cadeau_du_lieu
from test_part_en_jetons import (
    creer_une_carte_du_client,
    reglements_en_detail,
    vendre_des_bieres_a_la_forme_de_demain,
)

pytestmark = pytest.mark.django_db

# Le refus d'un avoir sur une partie d'un article qui a une part offerte ou une part
# en jetons (texte du service, `_montants_imposes_d_un_avoir`).
# / The refusal of a partial credit note on an item with an offered or token part.
REFUS_DE_L_AVOIR_PARTIEL = "rembourser l'article entier"


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


def adresse_de_l_avoir_sur_un_article(vente, ligne=None):
    """
    L'adresse de l'action « Avoir sur un article » d'une vente : l'écran de la liste,
    ou l'écran de l'article choisi (`?ligne=<pk>`).
    / The action address: the list screen, or the chosen item screen.
    """
    adresse = f"/admin/BaseBillet/vente/{vente.uuid}/avoir_sur_un_article/"
    if ligne is not None:
        adresse += f"?ligne={ligne.pk}"
    return adresse


def quantite_restante_de_la_ligne(ligne):
    """
    La quantité qui reste à rendre sur une ligne, relue en base : la quantité vendue,
    plus celle (négative) de ses avoirs.
    / The quantity left to give back on a line, read back.
    """
    ligne_relue = LigneArticle.objects.get(pk=ligne.pk)
    quantite_restante = ligne_relue.qty
    for ligne_qui_rend_une_partie in ligne_relue.credit_notes.all():
        quantite_restante += ligne_qui_rend_une_partie.qty
    return quantite_restante


def textes_des_refus(reponse):
    """
    Les textes qui disent le refus à l'admin : les messages d'erreur (refus par
    redirection) et les erreurs du formulaire (écran réaffiché). Le contrat accepte
    les deux formes.
    / The texts telling the refusal: error messages, or form errors.
    """
    textes = []
    for message in get_messages(reponse.wsgi_request):
        if message.level == messages.ERROR:
            textes.append(str(message))
    if reponse.status_code == 200 and reponse.context is not None:
        formulaire = reponse.context.get("form")
        if formulaire is not None:
            for erreurs_d_un_champ in formulaire.errors.values():
                for erreur in erreurs_d_un_champ:
                    textes.append(str(erreur))
    return textes


def l_avoir_est_refuse(reponse):
    """
    Dit si la réponse annonce un refus : un message d'erreur après une redirection,
    ou l'écran réaffiché avec une erreur du formulaire.
    / Tells whether the answer is a refusal (error message, or form error).
    """
    reponse_attendue = reponse.status_code in (200, 302)
    return reponse_attendue and len(textes_des_refus(reponse)) > 0


def la_quantite_n_est_pas_modifiable(champ_quantite):
    """Dit si le champ « quantité » est figé : désactivé, ou en lecture seule.
    / Tells whether the quantity field is frozen (disabled or read-only)."""
    if champ_quantite.disabled:
        return True
    return bool(champ_quantite.widget.attrs.get("readonly"))


def vendre_trois_jus_payes_en_especes():
    """
    Une vente de caisse réglée : 3 jus à 3,50 € (UNE ligne, quantité 3), payés 10,50 €
    en espèces. Rend la vente et sa ligne.
    / A settled register sale: 3 juices (one line) paid 10.50 in cash.
    """
    vente = ouvrir_vente(
        origine=SaleOrigin.LABOUTIK,
        nature=Vente.Nature.VENTE,
        client=creer_utilisateur(),
    )
    ligne_des_jus = ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(nom="Jus", prix_en_euros="3.50"),
        quantite=Decimal("3"),
        prix_unitaire=350,
        taux_tva=Decimal("20"),
        status=LigneArticle.VALID,
    )
    ajouter_reglement(vente, moyen=PaymentMethod.CASH, montant=1050)
    vente_reglee = encaisser_vente(vente)
    return SimpleNamespace(
        vente=Vente.objects.get(pk=vente_reglee.pk),
        ligne=LigneArticle.objects.get(pk=ligne_des_jus.pk),
    )


def vendre_trois_bieres_dont_une_offerte():
    """
    Une vente de caisse réglée : 3 bières à 5,00 € (UNE ligne, total catalogue 1500),
    dont une offerte par le gérant (part offerte 500). Règlements : offert 500 +
    espèces 1000. Rend la vente et sa ligne.
    / A settled sale: 3 beers, one offered (offered part 500); FREE 500 + cash 1000.
    """
    vente = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": creer_tarif_vendu(nom="Biere", prix_en_euros="5.00"),
                "quantite": Decimal("3"),
                "prix_unitaire": 500,
                "taux_tva": Decimal("20"),
                "part_offerte": 500,
                "source_offert": LigneArticle.SourceOffert.OFFRIR,
                "status": LigneArticle.VALID,
            }
        ],
        reglements=[
            {"moyen": PaymentMethod.FREE, "montant": 500},
            {"moyen": PaymentMethod.CASH, "montant": 1000},
        ],
    )
    vente_relue = Vente.objects.get(pk=vente.pk)
    return SimpleNamespace(vente=vente_relue, ligne=vente_relue.articles.get())


def vendre_un_comte_au_poids():
    """
    Une vente de caisse réglée au poids (D15) : 0,350 kg de comté à 12,90 €/kg (TVA
    5,5 %), poids saisi 350 g dans `weight_quantity`. Total 0,350 × 1290 = 451,5 →
    452, payé en espèces. Rend la vente, sa ligne, la quantité vendue et une quantité
    partielle à forger.
    / A settled weight sale: 0.350 kg of cheese at 12.90/kg = 452, paid in cash.
    """
    vente = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": creer_tarif_vendu(
                    nom="Comte au poids", prix_en_euros="12.90", taux_tva="5.50"
                ),
                "quantite": Decimal("0.350"),
                "prix_unitaire": 1290,
                "taux_tva": Decimal("5.5"),
                "weight_quantity": 350,
                "status": LigneArticle.VALID,
            }
        ],
        reglements=[{"moyen": PaymentMethod.CASH, "montant": 452}],
    )
    vente_relue = Vente.objects.get(pk=vente.pk)
    return SimpleNamespace(
        vente=vente_relue,
        ligne=vente_relue.articles.get(),
        quantite_vendue=Decimal("0.350"),
        quantite_partielle_forgee="0.100",
        total_de_l_article=452,
    )


def vendre_un_tirage_a_la_tireuse():
    """
    Une vente de la tireuse réglée (D15) : 0,50 L de bière à 6,00 €/L, volume servi
    50 cl dans `weight_quantity`, ligne d'origine « tireuse ». Total 0,50 × 600 = 300,
    payé en monnaie locale. Rend la vente, sa ligne, la quantité vendue et une quantité
    partielle à forger.
    / A settled tap sale: 0.50 L at 6.00/L = 300, paid in local currency.
    """
    vente = fabriquer_vente_encaissee(
        origine=SaleOrigin.TIREUSE,
        articles=[
            {
                "pricesold": creer_tarif_vendu(
                    nom="Biere pression", prix_en_euros="6.00"
                ),
                "quantite": Decimal("0.50"),
                "prix_unitaire": 600,
                "taux_tva": Decimal("20"),
                "weight_quantity": 50,
                "sale_origin": SaleOrigin.TIREUSE,
                "status": LigneArticle.VALID,
            }
        ],
        reglements=[{"moyen": PaymentMethod.LOCAL_EURO, "montant": 300}],
    )
    vente_relue = Vente.objects.get(pk=vente.pk)
    return SimpleNamespace(
        vente=vente_relue,
        ligne=vente_relue.articles.get(),
        quantite_vendue=Decimal("0.50"),
        quantite_partielle_forgee="0.20",
        total_de_l_article=300,
    )


def vendre_deux_billets_payes_par_stripe():
    """
    Une vente en ligne réglée par Stripe : 2 billets à 10,00 € (UNE ligne, quantité 2),
    reliée au paiement Stripe VALID de 20,00 € (moyen « SN »), encaissée par
    `encaisser_vente_stripe`. Rend la vente, sa ligne et le paiement.
    / A settled online sale paid by Stripe: 2 tickets at 10.00, one line.
    """
    acheteur = creer_utilisateur()
    vente = ouvrir_vente(
        origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE, client=acheteur
    )
    # Une création : aucune transition de la machine à états ne part.
    # / A creation: no state machine transition runs.
    paiement = Paiement_stripe.objects.create(
        user=acheteur,
        status=Paiement_stripe.VALID,
        moyen=PaymentMethod.STRIPE_NOFED,
        montant_encaisse=2000,
        payment_intent_id=f"pi_test_{identifiant_unique()}",
        vente=vente,
    )
    ligne_des_billets = ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(nom="Billet", prix_en_euros="10.00"),
        quantite=Decimal("2"),
        prix_unitaire=1000,
        taux_tva=Decimal("0"),
        payment_method=PaymentMethod.STRIPE_NOFED,
        paiement_stripe=paiement,
        status=LigneArticle.VALID,
    )
    encaisser_vente_stripe(paiement)
    return SimpleNamespace(
        vente=Vente.objects.get(pk=vente.pk),
        ligne=LigneArticle.objects.get(pk=ligne_des_billets.pk),
        paiement=paiement,
    )


# --------------------------------------------------------------------------
# 1 — Un jus sur trois, rendu en espèces
# / 1 — One juice of three, refunded in cash
# --------------------------------------------------------------------------


def test_admin_avoir_sur_un_article_quantite_partielle(lieu):
    """
    3 jus à 3,50 € payés en espèces. L'écran de l'article a le champ « Remboursé
    par », pré-rempli « Espèces » (le moyen d'origine). L'admin rend 1 jus en espèces :
    UNE vente AVOIR liée, origine admin, réglée, total −350 ; son article : quantité
    −1, prix unitaire 350 (le même), lié à la ligne d'origine ; un règlement espèces
    −350. Il reste 2 jus à rendre : la liste propose toujours l'article.
    / 3 juices paid in cash; 1 refunded in cash: AVOIR −350, item qty −1 price 350,
    cash −350; 2 left, still offered by the list.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente_des_jus = vendre_trois_jus_payes_en_especes()

    reponse_de_l_ecran = client_de_l_admin.get(
        adresse_de_l_avoir_sur_un_article(vente_des_jus.vente, vente_des_jus.ligne)
    )
    assert reponse_de_l_ecran.status_code == 200
    formulaire_de_l_ecran = reponse_de_l_ecran.context["form"]
    assert "quantite" in formulaire_de_l_ecran.fields
    assert "moyen_rembourse" in formulaire_de_l_ecran.fields
    assert formulaire_de_l_ecran["moyen_rembourse"].value() == PaymentMethod.CASH

    reponse = client_de_l_admin.post(
        adresse_de_l_avoir_sur_un_article(vente_des_jus.vente, vente_des_jus.ligne),
        {"quantite": "1", "moyen_rembourse": PaymentMethod.CASH},
    )

    assert reponse.status_code == 302
    avoirs = ventes_d_avoir_de(vente_des_jus.vente)
    assert len(avoirs) == 1
    vente_d_avoir = avoirs[0]
    assert vente_d_avoir.statut == Vente.Statut.REGLEE
    assert vente_d_avoir.origine == SaleOrigin.ADMIN
    assert vente_d_avoir.total_ttc == -350
    article_d_avoir = vente_d_avoir.articles.get()
    assert article_d_avoir.qty == Decimal("-1")
    assert article_d_avoir.amount == 350
    assert article_d_avoir.credit_note_for_id == vente_des_jus.ligne.pk
    assert moyens_et_montants(vente_d_avoir) == [(PaymentMethod.CASH, -350)]

    assert quantite_restante_de_la_ligne(vente_des_jus.ligne) == Decimal("2")
    reponse_de_la_liste = client_de_l_admin.get(
        adresse_de_l_avoir_sur_un_article(vente_des_jus.vente)
    )
    assert reponse_de_la_liste.status_code == 200
    assert str(vente_des_jus.ligne.pk) in reponse_de_la_liste.content.decode()
    # L'écran de l'article propose le RESTE (2), pas la quantité vendue (3).
    # / The item screen offers what is LEFT (2), not the sold quantity (3).
    reponse_du_second_ecran = client_de_l_admin.get(
        adresse_de_l_avoir_sur_un_article(vente_des_jus.vente, vente_des_jus.ligne)
    )
    quantite_proposee = reponse_du_second_ecran.context["form"]["quantite"].value()
    assert Decimal(str(quantite_proposee)) == Decimal("2")
    verifier_egalites(vente_d_avoir)


# --------------------------------------------------------------------------
# 2 — Pas d'avoir partiel sur une part offerte ou une part en jetons
# / 2 — No partial credit note on an offered part or a token part
# --------------------------------------------------------------------------


@pytest.mark.parametrize("part_sans_prorata", ["jetons", "offerte"])
def test_admin_avoir_partiel_refuse_sur_une_part_offerte_ou_en_jetons(
    lieu, part_sans_prorata
):
    """
    3 bières à 5,00 € sur UNE ligne :
    - « jetons » : payées 600 en jetons cadeau + 900 en monnaie locale (part en jetons
      600) ;
    - « offerte » : une bière offerte par le gérant (part offerte 500), le reste en
      espèces.
    L'admin veut rendre 1 bière sur 3 : refus « rembourser l'article entier », aucune
    vente AVOIR (le projet ne fait aucun prorata, fiche D §4).
    / 1 beer of 3 on a line with a token part or an offered part: refused, nothing
    written.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    if part_sans_prorata == "jetons":
        vente_des_bieres = vendre_des_bieres_a_la_forme_de_demain(
            lieu, nombre_de_bieres=3, part_en_jetons=600, montant_en_monnaie_locale=900
        )
    else:
        vente_des_bieres = vendre_trois_bieres_dont_une_offerte()

    reponse = client_de_l_admin.post(
        adresse_de_l_avoir_sur_un_article(
            vente_des_bieres.vente, vente_des_bieres.ligne
        ),
        {"quantite": "1", "moyen_rembourse": PaymentMethod.CASH},
    )

    assert l_avoir_est_refuse(reponse), reponse.status_code
    textes_du_refus = " ".join(textes_des_refus(reponse))
    assert REFUS_DE_L_AVOIR_PARTIEL in textes_du_refus
    assert ventes_d_avoir_de(vente_des_bieres.vente) == []
    assert quantite_restante_de_la_ligne(vente_des_bieres.ligne) == Decimal("3")
    verifier_egalites(vente_des_bieres.vente)


# --------------------------------------------------------------------------
# 2 bis — Une ligne mixte jetons et espèces : tout le reste, par l'écran
# / 2 bis — A mixed tokens and cash line: everything left, through the screen
# --------------------------------------------------------------------------


def vendre_une_biere_300_jetons_200_especes(lieu):
    """
    Une vente de caisse réglée : UNE bière à 5,00 € (TVA 20 %), part en jetons 300.
    Règlements : jetons cadeau (LG) 300, avec la monnaie cadeau du lieu et la carte du
    client ; espèces 200. Rend la vente relue, sa ligne, la carte et la monnaie cadeau.
    / A settled register sale: ONE beer, token part 300; payments LG 300 (gift
    currency, customer card) and cash 200.
    """
    jetons_cadeau = monnaie_cadeau_du_lieu(lieu)
    assert jetons_cadeau is not None, "Le lieu n'a pas de monnaie cadeau (TNF)."
    carte_du_client = creer_une_carte_du_client()
    vente = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": creer_tarif_vendu(nom="Biere", prix_en_euros="5.00"),
                "quantite": Decimal("1"),
                "prix_unitaire": 500,
                "taux_tva": Decimal("20"),
                "part_en_jetons": 300,
                "status": LigneArticle.VALID,
            }
        ],
        reglements=[
            {
                "moyen": PaymentMethod.LOCAL_GIFT,
                "montant": 300,
                "asset": jetons_cadeau.uuid,
                "carte": carte_du_client,
            },
            {"moyen": PaymentMethod.CASH, "montant": 200},
        ],
        carte=carte_du_client,
    )
    vente_relue = Vente.objects.get(pk=vente.pk)
    return SimpleNamespace(
        vente=vente_relue,
        ligne=vente_relue.articles.get(),
        carte=carte_du_client,
        jetons_cadeau=jetons_cadeau,
    )


def test_avoir_sur_un_article_d_une_ligne_mixte_jetons_et_especes(lieu):
    """
    Une bière payée 300 en jetons cadeau + 200 en espèces (UNE ligne). L'écran de
    l'article demande « Remboursé par » : il y a 200 d'argent à rendre. L'admin rend
    tout le reste (la bière) en espèces :
    - règlements de l'avoir : jetons (LG) −300, avec la monnaie et la carte du
      règlement LG de la vente d'origine ; espèces −200 ;
    - article d'avoir : part en jetons −300, total −500.
    / A beer paid 300 tokens + 200 cash: the screen asks "Refunded by"; the whole beer
    refunded in cash gives LG −300 (original currency and card) and cash −200.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    biere_mixte = vendre_une_biere_300_jetons_200_especes(lieu)

    reponse_de_l_ecran = client_de_l_admin.get(
        adresse_de_l_avoir_sur_un_article(biere_mixte.vente, biere_mixte.ligne)
    )
    assert reponse_de_l_ecran.status_code == 200
    assert "moyen_rembourse" in reponse_de_l_ecran.context["form"].fields

    reponse = client_de_l_admin.post(
        adresse_de_l_avoir_sur_un_article(biere_mixte.vente, biere_mixte.ligne),
        {"quantite": "1", "moyen_rembourse": PaymentMethod.CASH},
    )

    assert reponse.status_code == 302
    avoirs = ventes_d_avoir_de(biere_mixte.vente)
    assert len(avoirs) == 1
    vente_d_avoir = avoirs[0]
    assert vente_d_avoir.statut == Vente.Statut.REGLEE
    assert reglements_en_detail(vente_d_avoir) == sorted(
        [
            (PaymentMethod.CASH, -200, None, None),
            (
                PaymentMethod.LOCAL_GIFT,
                -300,
                biere_mixte.jetons_cadeau.uuid,
                biere_mixte.carte.pk,
            ),
        ],
        key=str,
    )
    article_d_avoir = vente_d_avoir.articles.get()
    assert article_d_avoir.part_en_jetons == -300
    assert article_d_avoir.total_ttc == -500
    assert quantite_restante_de_la_ligne(biere_mixte.ligne) == Decimal("0")
    verifier_egalites(vente_d_avoir)


# --------------------------------------------------------------------------
# 3 — Poids et tireuse : seulement l'article entier (Q-H5)
# / 3 — Weight and tap: the whole item only (Q-H5)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "vendre_l_article",
    [vendre_un_comte_au_poids, vendre_un_tirage_a_la_tireuse],
    ids=["poids", "tireuse"],
)
def test_admin_avoir_au_poids_seulement_l_article_entier(lieu, vendre_l_article):
    """
    Un article au poids (comté 0,350 kg) ou à la tireuse (0,50 L). L'écran ne propose
    que la quantité vendue, et elle n'est pas modifiable. Un POST forgé avec une
    partie de la quantité (0,100 kg ; 0,20 L) est refusé, rien n'est écrit. Le POST de
    la quantité entière écrit l'avoir de tout l'article (−452 ; −300).
    / Weight or tap item: the screen offers only the whole quantity, frozen; a forged
    partial POST is refused; the whole quantity is accepted.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    article_vendu = vendre_l_article()
    adresse_de_l_article = adresse_de_l_avoir_sur_un_article(
        article_vendu.vente, article_vendu.ligne
    )

    reponse_de_l_ecran = client_de_l_admin.get(adresse_de_l_article)
    assert reponse_de_l_ecran.status_code == 200
    formulaire_de_l_ecran = reponse_de_l_ecran.context["form"]
    quantite_proposee = Decimal(str(formulaire_de_l_ecran["quantite"].value()))
    assert quantite_proposee == article_vendu.quantite_vendue
    assert la_quantite_n_est_pas_modifiable(formulaire_de_l_ecran.fields["quantite"])

    reponse_forgee = client_de_l_admin.post(
        adresse_de_l_article,
        {
            "quantite": article_vendu.quantite_partielle_forgee,
            "moyen_rembourse": PaymentMethod.CASH,
        },
    )
    assert l_avoir_est_refuse(reponse_forgee), reponse_forgee.status_code
    assert ventes_d_avoir_de(article_vendu.vente) == []

    reponse_entiere = client_de_l_admin.post(
        adresse_de_l_article,
        {
            "quantite": str(article_vendu.quantite_vendue),
            "moyen_rembourse": PaymentMethod.CASH,
        },
    )
    assert reponse_entiere.status_code == 302
    avoirs = ventes_d_avoir_de(article_vendu.vente)
    assert len(avoirs) == 1
    article_d_avoir = avoirs[0].articles.get()
    assert article_d_avoir.qty == -article_vendu.quantite_vendue
    assert article_d_avoir.total_ttc == -article_vendu.total_de_l_article
    assert moyens_et_montants(avoirs[0]) == [
        (PaymentMethod.CASH, -article_vendu.total_de_l_article)
    ]
    verifier_egalites(avoirs[0])


# --------------------------------------------------------------------------
# 4 — Pas plus que le reste
# / 4 — No more than what is left
# --------------------------------------------------------------------------


def test_admin_avoir_quantite_superieure_au_reste_refusee(lieu):
    """
    3 jus payés en espèces, dont 2 déjà rendus (un premier avoir). L'admin veut en
    rendre 2 de plus : il n'en reste qu'1, refus ; toujours un seul avoir, il reste
    1 jus à rendre.
    / 2 juices of 3 already refunded: refunding 2 more is refused.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente_des_jus = vendre_trois_jus_payes_en_especes()
    ecrire_la_vente_d_avoir_d_une_ligne(
        vente_des_jus.ligne,
        quantite=Decimal("2"),
        moyen_rembourse=PaymentMethod.CASH,
        origine=SaleOrigin.ADMIN,
    )

    reponse = client_de_l_admin.post(
        adresse_de_l_avoir_sur_un_article(vente_des_jus.vente, vente_des_jus.ligne),
        {"quantite": "2", "moyen_rembourse": PaymentMethod.CASH},
    )

    assert l_avoir_est_refuse(reponse), reponse.status_code
    assert len(ventes_d_avoir_de(vente_des_jus.vente)) == 1
    assert quantite_restante_de_la_ligne(vente_des_jus.ligne) == Decimal("1")
    verifier_egalites(vente_des_jus.vente)


# --------------------------------------------------------------------------
# 5 — Article payé par Stripe : règle D27
# / 5 — Item paid by Stripe: rule D27
# --------------------------------------------------------------------------


def test_admin_avoir_sur_un_article_paye_par_stripe(lieu):
    """
    D27. 2 billets à 10,00 € payés par Stripe. L'écran de l'article n'a PAS de champ
    « Remboursé par ». L'admin rend 1 billet : un règlement négatif au moyen Stripe
    d'origine (« SN », −1000), relié au paiement, référence externe vide. Aucun appel
    à Stripe. Un message rappelle de rembourser depuis le tableau de bord Stripe.
    / D27: Stripe-paid item: no field; one negative payment at the original Stripe
    method, empty reference, no Stripe call, a reminder message.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente_des_billets = vendre_deux_billets_payes_par_stripe()
    adresse_de_l_article = adresse_de_l_avoir_sur_un_article(
        vente_des_billets.vente, vente_des_billets.ligne
    )

    with patch("stripe.Refund.create") as remboursement_stripe:
        reponse_de_l_ecran = client_de_l_admin.get(adresse_de_l_article)
        reponse = client_de_l_admin.post(adresse_de_l_article, {"quantite": "1"})

    assert reponse_de_l_ecran.status_code == 200
    assert "moyen_rembourse" not in reponse_de_l_ecran.context["form"].fields
    assert reponse.status_code == 302
    assert remboursement_stripe.call_count == 0
    avoirs = ventes_d_avoir_de(vente_des_billets.vente)
    assert len(avoirs) == 1
    assert moyens_et_montants(avoirs[0]) == [(PaymentMethod.STRIPE_NOFED, -1000)]
    reglement_de_l_avoir = Reglement.objects.get(vente=avoirs[0])
    assert reglement_de_l_avoir.reference_externe == ""
    assert reglement_de_l_avoir.paiement_stripe_id == vente_des_billets.paiement.pk
    rappel_attendu = message_traduit(
        reponse, "Remboursez cette somme depuis votre tableau de bord Stripe."
    )
    assert rappel_attendu in textes_des_messages(reponse)
    verifier_egalites(avoirs[0])


# --------------------------------------------------------------------------
# 6 — Double envoi : un seul avoir
# / 6 — Double submission: one credit note
# --------------------------------------------------------------------------


def test_admin_avoir_double_envoi_un_seul_avoir(lieu):
    """
    3 jus payés en espèces. Le même POST (rendre 2 jus) arrive deux fois (double
    clic) : un seul avoir est écrit, le second envoi est refusé (la quantité relue
    sous verrou n'est plus que 1). En séquentiel, ce test prouve la relecture du reste
    au moment d'écrire ; le verrou lui-même ne se voit qu'avec deux envois simultanés.
    / The same POST twice: one credit note; the second one is refused.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente_des_jus = vendre_trois_jus_payes_en_especes()
    adresse_de_l_article = adresse_de_l_avoir_sur_un_article(
        vente_des_jus.vente, vente_des_jus.ligne
    )
    donnees_du_formulaire = {"quantite": "2", "moyen_rembourse": PaymentMethod.CASH}

    premiere_reponse = client_de_l_admin.post(
        adresse_de_l_article, donnees_du_formulaire
    )
    seconde_reponse = client_de_l_admin.post(
        adresse_de_l_article, donnees_du_formulaire
    )

    assert premiere_reponse.status_code == 302
    assert l_avoir_est_refuse(seconde_reponse), seconde_reponse.status_code
    avoirs = ventes_d_avoir_de(vente_des_jus.vente)
    assert len(avoirs) == 1
    assert avoirs[0].total_ttc == -700
    assert quantite_restante_de_la_ligne(vente_des_jus.ligne) == Decimal("1")
    verifier_egalites(avoirs[0])


# --------------------------------------------------------------------------
# Refus portés par le SERVICE (`ecrire_la_vente_d_avoir_d_une_ligne`) : tous les
# appelants sont protégés, pas seulement l'écran.
# / Refusals carried by the SERVICE: every caller is protected, not only the screen.
# --------------------------------------------------------------------------

# Débuts des textes de refus du service (français, non traduits).
# / Starts of the service refusal texts (French, untranslated).
REFUS_POUR_UN_ECART = "Cette vente a un écart d'encaissement"
REFUS_POUR_UNE_RECHARGE = "Cet article est une recharge de carte"
REFUS_POUR_UNE_QUANTITE_NON_ENTIERE = "doit être un nombre entier d'articles"
REFUS_POUR_UNE_PARTIE_D_UNE_PESEE = "vendu au poids ou à la tireuse"


def ligne_du_billet_et_ligne_de_l_ecart(vente):
    """
    Les deux lignes d'une vente en ligne avec un écart d'encaissement : le billet
    (dans le chiffre d'affaires) et l'article « Écart d'encaissement » (hors chiffre
    d'affaires). Rend (ligne du billet, ligne de l'écart).
    / The ticket line and the gap line of an online sale with a collection gap.
    """
    ligne_du_billet = vente.articles.get(hors_chiffre_affaires=False)
    ligne_de_l_ecart = vente.articles.get(hors_chiffre_affaires=True)
    return ligne_du_billet, ligne_de_l_ecart


@pytest.mark.parametrize("article_rendu", ["billet", "ecart"])
def test_service_avoir_d_une_ligne_refuse_une_vente_avec_un_ecart_d_encaissement(
    lieu, article_rendu
):
    """
    Une vente en ligne où Stripe a encaissé 1,00 € de plus que le billet (article
    « Écart d'encaissement — reçu en plus »). AUCUN avoir n'est possible sur
    ses articles (Q-H13) : ni sur le billet, ni sur l'article d'écart. Le service
    refuse (ValueError), rien n'est écrit.
    / A sale with a collection gap: no credit note on any of its items (Q-H13).
    """
    vente = vendre_en_ligne_avec_un_ecart_d_encaissement(creer_utilisateur())
    ligne_du_billet, ligne_de_l_ecart = ligne_du_billet_et_ligne_de_l_ecart(vente)
    if article_rendu == "billet":
        ligne_rendue = ligne_du_billet
    else:
        ligne_rendue = ligne_de_l_ecart

    with pytest.raises(ValueError, match=REFUS_POUR_UN_ECART):
        ecrire_la_vente_d_avoir_d_une_ligne(
            ligne_rendue,
            quantite=ligne_rendue.qty,
            moyen_rembourse=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
        )

    assert ventes_d_avoir_de(vente) == []
    verifier_egalites(vente)


def test_admin_avoir_sur_un_article_affiche_le_refus_du_service_pour_un_ecart(lieu):
    """
    Même vente avec un écart d'encaissement, par l'écran : le POST sur le billet est
    refusé, le message d'erreur porte le texte du service, rien n'est écrit.
    / Same sale through the screen: the error message carries the service text.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_en_ligne_avec_un_ecart_d_encaissement(creer_utilisateur())
    ligne_du_billet, _ligne_de_l_ecart = ligne_du_billet_et_ligne_de_l_ecart(vente)

    reponse = client_de_l_admin.post(
        adresse_de_l_avoir_sur_un_article(vente, ligne_du_billet),
        {"quantite": "1", "moyen_rembourse": PaymentMethod.CASH},
    )

    assert l_avoir_est_refuse(reponse), reponse.status_code
    assert REFUS_POUR_UN_ECART in " ".join(textes_des_refus(reponse))
    assert ventes_d_avoir_de(vente) == []


def vendre_deux_billets_en_ligne_avec_un_ecart():
    """
    Une vente en ligne réglée : 2 billets à 10,00 € (UNE ligne, quantité 2), et
    l'article « Écart d'encaissement — reçu en plus » de 1,00 € (Stripe a encaissé
    21,00 €). Rend la vente relue.
    / A settled online sale: 2 tickets on one line, plus a 1.00 "received more" gap
    item (Stripe collected 21.00).
    """
    vente = ouvrir_vente(
        origine=SaleOrigin.LESPASS,
        nature=Vente.Nature.VENTE,
        client=creer_utilisateur(),
    )
    ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(nom="Billet", prix_en_euros="10.00"),
        quantite=Decimal("2"),
        prix_unitaire=1000,
        taux_tva=Decimal("0"),
        payment_method=PaymentMethod.STRIPE_NOFED,
    )
    ajouter_l_article_d_ecart_d_encaissement(vente, 100)
    ajouter_reglement(vente, moyen=PaymentMethod.STRIPE_NOFED, montant=2100)
    return Vente.objects.get(pk=encaisser_vente(vente).pk)


def test_bouton_cache_et_ecran_refuse_sur_une_vente_avec_ecart(lieu):
    """
    Une vente en ligne de 2 billets qui porte un écart d'encaissement (reçu en plus).
    Le service refuse tout avoir sur ses articles (Q-H13) : l'écran le dit AVANT.
    - la fiche de la vente ne montre pas le bouton « Avoir sur un article » ;
    - l'écran (GET) ne s'ouvre pas : retour à la fiche (302), avec le message du
      service ;
    - aucun avoir n'est écrit.
    Témoin : la fiche d'une vente sans écart (3 jus en espèces) montre le bouton. Sans
    ce témoin, une fiche qui n'afficherait jamais l'adresse du bouton ferait passer le
    test.
    / A sale with a collection gap: no button on the detail page, the screen redirects
    with the service message, nothing written. A gap-free sale shows the button.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente_avec_ecart = vendre_deux_billets_en_ligne_avec_un_ecart()
    vente_temoin = vendre_trois_jus_payes_en_especes()

    fiche_du_temoin = client_de_l_admin.get(adresse_de_la_fiche(vente_temoin.vente))
    fiche_de_la_vente_avec_ecart = client_de_l_admin.get(
        adresse_de_la_fiche(vente_avec_ecart)
    )
    reponse_de_l_ecran = client_de_l_admin.get(
        adresse_de_l_avoir_sur_un_article(vente_avec_ecart)
    )

    assert fiche_du_temoin.status_code == 200
    assert adresse_de_l_avoir_sur_un_article(vente_temoin.vente) in (
        fiche_du_temoin.content.decode()
    )
    assert fiche_de_la_vente_avec_ecart.status_code == 200
    assert adresse_de_l_avoir_sur_un_article(vente_avec_ecart) not in (
        fiche_de_la_vente_avec_ecart.content.decode()
    )
    assert reponse_de_l_ecran.status_code == 302
    message_du_service = message_traduit(
        reponse_de_l_ecran, MESSAGE_AVOIR_LIGNE_VENTE_AVEC_UN_ECART
    )
    assert message_du_service in textes_des_refus(reponse_de_l_ecran)
    assert ventes_d_avoir_de(vente_avec_ecart) == []


def vendre_un_billet_et_une_recharge_en_especes():
    """
    Une vente de caisse réglée : un billet à 10,00 € (dans le chiffre d'affaires) et une
    recharge de carte de 10,00 € (hors chiffre d'affaires), payés 20,00 € en espèces.
    Rend la vente, la ligne du billet et la ligne de la recharge.
    / A settled register sale: a ticket (revenue) and a card top-up (off revenue), paid
    in cash.
    """
    vente = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": creer_tarif_vendu(nom="Billet", prix_en_euros="10.00"),
                "quantite": Decimal("1"),
                "prix_unitaire": 1000,
                "taux_tva": Decimal("0"),
                "status": LigneArticle.VALID,
            },
            {
                "pricesold": creer_tarif_vendu(
                    nom="Recharge",
                    prix_en_euros="10.00",
                    taux_tva="0.00",
                    categorie_article=Product.RECHARGE_CASHLESS,
                ),
                "quantite": Decimal("1"),
                "prix_unitaire": 1000,
                "taux_tva": Decimal("0"),
                "status": LigneArticle.VALID,
            },
        ],
        reglements=[{"moyen": PaymentMethod.CASH, "montant": 2000}],
    )
    vente_relue = Vente.objects.get(pk=vente.pk)
    return SimpleNamespace(
        vente=vente_relue,
        ligne_du_billet=vente_relue.articles.get(hors_chiffre_affaires=False),
        ligne_de_la_recharge=vente_relue.articles.get(hors_chiffre_affaires=True),
    )


def test_liste_des_articles_sans_recharge_ni_ecart(lieu):
    """
    Une vente de caisse avec un billet et une recharge de carte. La liste des articles
    de l'écran « Avoir sur un article » ne propose que le billet : une ligne hors
    chiffre d'affaires (recharge, article d'écart) n'a pas d'avoir sur un article (le
    service la refuserait). La recharge tient lieu ici des deux : une vente qui porte un
    article d'écart n'ouvre pas l'écran du tout
    (`test_bouton_cache_et_ecran_refuse_sur_une_vente_avec_ecart`).
    / The item list offers only the ticket, never an off-revenue line (top-up, gap
    item); a sale with a gap item does not open the screen at all.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente_mixte = vendre_un_billet_et_une_recharge_en_especes()

    reponse_de_la_liste = client_de_l_admin.get(
        adresse_de_l_avoir_sur_un_article(vente_mixte.vente)
    )

    assert reponse_de_la_liste.status_code == 200
    page_de_la_liste = reponse_de_la_liste.content.decode()
    assert str(vente_mixte.ligne_du_billet.pk) in page_de_la_liste
    assert str(vente_mixte.ligne_de_la_recharge.pk) not in page_de_la_liste


def test_service_avoir_d_une_ligne_refuse_une_recharge_cashless(lieu):
    """
    Une recharge de carte de 10,00 € payée par CB (hors chiffre d'affaires) : son
    avoir est refusé par le service (il ne retirerait pas l'argent de la carte), rien
    n'est écrit. Même refus que l'« Avoir total ».
    / A card top-up line: refused by the service, nothing written.
    """
    vente = vendre_une_recharge_de_carte_par_cb(creer_utilisateur())
    ligne_de_la_recharge = vente.articles.get()

    with pytest.raises(ValueError, match=REFUS_POUR_UNE_RECHARGE):
        ecrire_la_vente_d_avoir_d_une_ligne(
            ligne_de_la_recharge,
            quantite=ligne_de_la_recharge.qty,
            moyen_rembourse=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
        )

    assert ventes_d_avoir_de(vente) == []
    verifier_egalites(vente)


def test_service_avoir_partiel_refuse_une_quantite_non_entiere_a_la_piece(lieu):
    """
    3 jus à la pièce : rendre 1,5 jus est refusé par le service (une partie de ce qui
    reste doit être un nombre entier d'articles), rien n'est écrit.
    / 1.5 juice of 3: refused by the service, nothing written.
    """
    vente_des_jus = vendre_trois_jus_payes_en_especes()

    with pytest.raises(ValueError, match=REFUS_POUR_UNE_QUANTITE_NON_ENTIERE):
        ecrire_la_vente_d_avoir_d_une_ligne(
            vente_des_jus.ligne,
            quantite=Decimal("1.5"),
            moyen_rembourse=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
        )

    assert ventes_d_avoir_de(vente_des_jus.vente) == []
    assert quantite_restante_de_la_ligne(vente_des_jus.ligne) == Decimal("3")


def test_service_avoir_de_tout_le_reste_non_entier_reste_accepte(lieu):
    """
    Une « part » d'historique (fil rouge : 3 jus coupés en deux parts, 1,428571 et
    1,571429) : rendre TOUTE la quantité d'une part, non entière, reste accepté. Seule
    une PARTIE de ce qui reste doit être entière. L'avoir rend exactement la part
    (−500, recopiée de la ligne).
    / The whole non-whole quantity of a historical part is still accepted (−500).
    """
    vente = vendre_trois_jus_en_deux_parts(creer_utilisateur())
    ligne_de_la_premiere_part = vente.articles.get(total_ttc=500)

    article_d_avoir = ecrire_la_vente_d_avoir_d_une_ligne(
        ligne_de_la_premiere_part,
        quantite=ligne_de_la_premiere_part.qty,
        moyen_rembourse=PaymentMethod.CASH,
        origine=SaleOrigin.ADMIN,
    )

    article_relu = LigneArticle.objects.get(pk=article_d_avoir.pk)
    assert article_relu.qty == -Decimal("1.428571")
    assert article_relu.total_ttc == -500
    verifier_egalites(Vente.objects.get(pk=article_relu.vente_id))


def test_service_avoir_refuse_une_partie_d_une_pesee(lieu):
    """
    Comté 0,350 kg : le service refuse une partie de la pesée (0,100 kg), quel que soit
    l'appelant (Q-H5). Rien n'est écrit.
    / A part of a weighing is refused by the service itself, nothing written.
    """
    comte_vendu = vendre_un_comte_au_poids()

    with pytest.raises(ValueError, match=REFUS_POUR_UNE_PARTIE_D_UNE_PESEE):
        ecrire_la_vente_d_avoir_d_une_ligne(
            comte_vendu.ligne,
            quantite=Decimal("0.100"),
            moyen_rembourse=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
        )

    assert ventes_d_avoir_de(comte_vendu.vente) == []


# --------------------------------------------------------------------------
# Refus de l'écran sur l'état de la vente
# / Screen refusals on the sale state
# --------------------------------------------------------------------------


def test_admin_avoir_sur_un_article_refuse_une_vente_pas_reglee(lieu):
    """
    Une vente en ligne restée en attente (pas réglée) : l'écran est refusé (GET : retour
    à la fiche, message d'erreur) et le POST aussi. Aucun avoir n'est écrit.
    / An unsettled sale: screen and POST refused, nothing written.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = ouvrir_une_vente_en_ligne_en_attente(creer_utilisateur(), depuis_minutes=10)
    ligne_du_billet = vente.articles.get()

    reponse_de_l_ecran = client_de_l_admin.get(adresse_de_l_avoir_sur_un_article(vente))
    reponse_de_la_validation = client_de_l_admin.post(
        adresse_de_l_avoir_sur_un_article(vente, ligne_du_billet),
        {"quantite": "1", "moyen_rembourse": PaymentMethod.CASH},
    )

    assert reponse_de_l_ecran.status_code == 302
    assert l_avoir_est_refuse(reponse_de_l_ecran)
    assert l_avoir_est_refuse(reponse_de_la_validation)
    assert ventes_d_avoir_de(vente) == []


def test_admin_avoir_sur_un_article_refuse_une_vente_en_points(lieu):
    """
    Une vente tenue en points : l'écran est refusé (GET : retour à la fiche, message
    d'erreur) et le POST aussi. Aucun avoir n'est écrit (un avoir en euros rendrait de
    l'argent pour des points).
    / A points sale: screen and POST refused, nothing written.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_une_planche_en_points(creer_utilisateur())
    ligne_de_la_planche = vente.articles.get()

    reponse_de_l_ecran = client_de_l_admin.get(adresse_de_l_avoir_sur_un_article(vente))
    reponse_de_la_validation = client_de_l_admin.post(
        adresse_de_l_avoir_sur_un_article(vente, ligne_de_la_planche), {"quantite": "1"}
    )

    assert reponse_de_l_ecran.status_code == 302
    assert l_avoir_est_refuse(reponse_de_l_ecran)
    assert l_avoir_est_refuse(reponse_de_la_validation)
    assert ventes_d_avoir_de(vente) == []
