"""
Tests de rendu — le compteur de billets ne propose jamais plus que les places
reellement disponibles, et n'ecrit JAMAIS max="None".
/ Render tests — the ticket counter never offers more than the seats actually
available, and NEVER writes max="None".

LOCALISATION : tests/pytest/test_booking_counter_max.py

Contexte / Background
---------------------
Le gabarit booking_form.html bornait l'attribut `max` du composant bs-counter par
le seul `max_per_user` (le quota par personne), jamais par les places restantes.
Sur un evenement ou il reste 1 place, le compteur laissait donc demander jusqu'a
10 billets, et le serveur refusait (issue Sentry BILLETTERIE-COOP-4G, 781 refus).

Pire : `Event.max_per_user` et `Price.max_per_user` sont tous deux facultatifs en
base. Quand les deux etaient vides, le gabarit rendait la chaine litterale
max="None". Or bs-counter.mjs fait `if (this.max)` (la chaine "None" est truthy)
puis `Number(this.max)` (qui vaut NaN) : le bouton + n'etait alors JAMAIS
desactive, et le champ affichait le placeholder « 0 / NaN ».

Le plafond est desormais calcule en Python dans BaseBillet.views.EventMVT.retrieve
et depose sur chaque tarif sous le nom `max_billets`. Ces tests verrouillent le
rendu : ils echouent si le plafond repasse a "None", s'il disparait, ou si la
valeur 0 est avalee par une comparaison de veracite.

/ booking_form.html capped the counter with `max_per_user` only, never with the
remaining seats, and rendered the literal string max="None" when both optional
per-user caps were empty — which bs-counter reads as unlimited. The cap is now
computed in the view and attached to each price as `max_billets`. These tests
lock the rendering down.

Tests de contenu (pas de base de donnees, pas de reseau, non-flaky).
/ Content tests (no database, no network, non-flaky).
"""

import re
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.utils import translation

GABARIT = "reunion/views/event/partial/booking_form.html"


def _faux_tarif(uuid, nom="Plein tarif", prix=10, max_billets=None):
    """
    Tarif minimal permettant d'atteindre le compteur dans le gabarit.
    Les quatre gardes du gabarit (quota produit, quota tarif, rupture de stock,
    adhesion obligatoire) doivent toutes etre fausses, sinon le compteur est
    remplace par un message d'alerte.
    / Minimal price object that reaches the counter: the template's four guards
    must all be false, otherwise an alert replaces the counter.
    """
    return SimpleNamespace(
        uuid=uuid,
        name=nom,
        prix=prix,
        free_price=False,
        max_billets=max_billets,
        product=SimpleNamespace(name="Billet"),
        # Appele par le filtre price_out_of_stock. / Called by the filter.
        out_of_stock=lambda event=None: False,
        # `exists` non appelable : le gabarit le lit comme un booleen.
        # / Non-callable `exists`: the template reads it as a boolean.
        adhesions_obligatoires=SimpleNamespace(exists=False),
    )


def _rendu(tarifs, places_restantes=None, show_gauge=False, max_per_user=None):
    """Rend le formulaire de reservation. / Render the booking form."""
    event = SimpleNamespace(
        uuid="11111111-2222-3333-4444-555555555555",
        published_prices=tarifs,
        max_per_user=max_per_user,
        show_gauge=show_gauge,
        products=SimpleNamespace(all=[]),
    )
    return render_to_string(
        GABARIT,
        {
            "event": event,
            "places_restantes": places_restantes,
            "product_max_per_user_reached": [],
            "price_max_per_user_reached": [],
            "user": SimpleNamespace(is_anonymous=True, is_authenticated=False),
        },
    )


def _attribut_max(html, uuid):
    """
    Renvoie la valeur de l'attribut `max` du compteur d'un tarif, ou None si
    l'attribut est absent. Leve une AssertionError si le compteur lui-meme
    manque : cela signifierait qu'une garde du gabarit a bloque l'affichage et
    que le test ne mesure plus ce qu'il croit mesurer.
    / Return the counter's `max` attribute for a price, or None when absent.
    Raises if the counter itself is missing, which would mean the test no longer
    measures what it thinks it measures.
    """
    balise = re.search(
        r"<bs-counter\b[^>]*booking-amount-" + re.escape(uuid) + r"[^>]*>",
        html,
        re.S,
    )
    assert balise, f"compteur introuvable pour le tarif {uuid}"
    attribut = re.search(r'\bmax="([^"]*)"', balise.group(0))
    return attribut.group(1) if attribut else None


def _bloc_places_restantes(html):
    """Renvoie le paragraphe des places restantes, ou None. / Remaining-seats paragraph."""
    bloc = re.search(
        r'<p[^>]*data-testid="booking-remaining-seats"[^>]*>(.*?)</p>', html, re.S
    )
    return bloc.group(1).strip() if bloc else None


# ---------------------------------------------------------------------------
# Le plafond du compteur / The counter ceiling
# ---------------------------------------------------------------------------


def test_chaque_tarif_porte_son_propre_plafond():
    """
    Avec plusieurs tarifs, chaque compteur porte SON plafond, pas celui du voisin.
    / With several prices, each counter carries its own cap.
    """
    html = _rendu(
        [
            _faux_tarif("aaaa1111", nom="Plein tarif", max_billets=3),
            _faux_tarif("bbbb2222", nom="Tarif reduit", max_billets=1),
            _faux_tarif("cccc3333", nom="Tarif solidaire", max_billets=7),
        ],
        places_restantes=7,
    )

    assert _attribut_max(html, "aaaa1111") == "3"
    assert _attribut_max(html, "bbbb2222") == "1"
    assert _attribut_max(html, "cccc3333") == "7"


def test_jamais_de_plafond_none_ni_nan():
    """
    Le coeur du correctif : quand aucun plafond ne s'applique, le gabarit n'ecrit
    AUCUN attribut max — surtout pas la chaine "None", que bs-counter lit comme
    un plafond illimite et qui produit le placeholder « 0 / NaN ».
    / The heart of the fix: with no applicable cap, no `max` attribute at all —
    certainly not the string "None", which bs-counter reads as unlimited.
    """
    html = _rendu([_faux_tarif("dddd4444", max_billets=None)], places_restantes=None)

    assert _attribut_max(html, "dddd4444") is None
    assert 'max="None"' not in html
    assert "None" not in html
    assert "NaN" not in html


def test_plafond_zero_est_bien_ecrit():
    """
    Piege de veracite : 0 est falsy. Un `{% if price.max_billets %}` retirerait
    l'attribut precisement quand il doit bloquer le compteur. On verifie que le
    zero survit au rendu.
    / Truthiness trap: 0 is falsy. A plain `{% if %}` would drop the attribute
    exactly when it must block the counter.
    """
    html = _rendu([_faux_tarif("eeee5555", max_billets=0)], places_restantes=0)

    assert _attribut_max(html, "eeee5555") == "0"


def test_plafond_present_dans_la_branche_adhesion_obligatoire():
    """
    Le gabarit contient DEUX compteurs : la branche normale et celle des tarifs a
    adhesion obligatoire, pour un adherent a jour. Les deux doivent etre bornees.
    / The template has TWO counters: the normal branch and the membership-required
    one. Both must be capped.
    """
    tarif = _faux_tarif("ffff6666", max_billets=2)
    # `all` doit etre APPELABLE : le filtre is_membership fait
    # `membership_product.all()`, et le gabarit boucle sur `.all`.
    # / `all` must be CALLABLE: the is_membership filter calls it.
    tarif.adhesions_obligatoires = SimpleNamespace(exists=True, all=lambda: [])

    event = SimpleNamespace(
        uuid="11111111-2222-3333-4444-555555555555",
        published_prices=[tarif],
        max_per_user=None,
        show_gauge=False,
        products=SimpleNamespace(all=[]),
    )
    # Utilisateur authentifie ET adherent : le filtre is_membership doit renvoyer
    # vrai pour atteindre le compteur de cette branche.
    # / Authenticated member: is_membership must be true to reach that counter.
    utilisateur = SimpleNamespace(
        is_anonymous=False,
        is_authenticated=True,
        memberships=SimpleNamespace(
            filter=lambda **kwargs: SimpleNamespace(exists=lambda: True)
        ),
    )
    html = render_to_string(
        GABARIT,
        {
            "event": event,
            "places_restantes": 2,
            "product_max_per_user_reached": [],
            "price_max_per_user_reached": [],
            "user": utilisateur,
        },
    )

    assert _attribut_max(html, "ffff6666") == "2"
    assert 'max="None"' not in html


# ---------------------------------------------------------------------------
# L'affichage des places restantes / The remaining-seats notice
# ---------------------------------------------------------------------------


def test_places_restantes_affichees_sous_le_seuil():
    """Sans jauge visible, le message apparait quand il reste peu de places."""
    html = _rendu([_faux_tarif("aaaa1111", max_billets=3)], places_restantes=3)

    assert _bloc_places_restantes(html) is not None


def test_places_restantes_masquees_au_dessus_du_seuil():
    """
    Sans jauge visible et avec beaucoup de places, on n'affiche rien : annoncer
    « 3 reservations sur 200 » desservirait l'evenement.
    / No gauge and plenty of seats: stay silent.
    """
    html = _rendu([_faux_tarif("aaaa1111", max_billets=11)], places_restantes=11)

    assert _bloc_places_restantes(html) is None


def test_places_restantes_au_seuil_exact():
    """Le seuil est inclusif : 10 places restantes declenchent l'affichage."""
    html = _rendu([_faux_tarif("aaaa1111", max_billets=10)], places_restantes=10)

    assert _bloc_places_restantes(html) is not None


def test_places_restantes_toujours_affichees_si_jauge_visible():
    """
    Quand le lieu a active « Afficher la jauge », le message est permanent, quel
    que soit le nombre de places.
    / When the venue enabled the gauge, the notice is always shown.
    """
    html = _rendu(
        [_faux_tarif("aaaa1111", max_billets=150)],
        places_restantes=150,
        show_gauge=True,
    )

    assert _bloc_places_restantes(html) is not None


def test_pas_de_places_restantes_pour_un_evenement_federe():
    """
    Un evenement venu de la federation n'existe pas dans ce schema : sa jauge
    n'est pas calculable, `places_restantes` vaut None. On n'affiche rien, et
    surtout on ne rend pas « Il reste None places ».
    / A federated event has no computable capacity here: show nothing.
    """
    html = _rendu(
        [_faux_tarif("aaaa1111", max_billets=None)],
        places_restantes=None,
        show_gauge=True,
    )

    assert _bloc_places_restantes(html) is None
    assert "None" not in html


def test_accord_singulier_pluriel():
    """
    Le message s'accorde. Texte source en francais, donc on force la locale pour
    ne pas dependre de la langue active du lanceur de tests.
    / The notice agrees in number. Source text is French, so pin the locale.
    """
    with translation.override("fr"):
        une = _rendu([_faux_tarif("aaaa1111", max_billets=1)], places_restantes=1)
        plusieurs = _rendu([_faux_tarif("aaaa1111", max_billets=4)], places_restantes=4)

    texte_une = _bloc_places_restantes(une)
    texte_plusieurs = _bloc_places_restantes(plusieurs)

    assert texte_une is not None and texte_plusieurs is not None
    assert "1 place disponible" in texte_une
    assert "4 places disponibles" in texte_plusieurs
