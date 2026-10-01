"""
Colonnes des réponses au formulaire personnalisé, pour les exports.
/ Custom form answer columns, for exports.

LOCALISATION : Administration/importers/reponses_formulaire_export.py

Utilisé par deux exports :
- les billets : Administration/importers/ticket_exporter.py (TicketExportResource) ;
- les adhésions : Administration/importers/membership_importers.py (MembershipExportResource).

Les deux exports lisent les réponses dans un champ JSON `custom_form`
(Reservation.custom_form pour un billet, Membership.custom_form pour une adhésion).
Chaque réponse y est rangée sous le LIBELLÉ de sa question
(build_custom_form_from_request, BaseBillet/validators.py).

Ce module décide dans QUEL ORDRE sortent les colonnes de réponses. Issue GitHub #290.
/ Decides the order of the answer columns.
"""

from BaseBillet.models import ProductFormField


def cle_de_la_reponse(question):
    """
    La clé sous laquelle la réponse à une question est rangée dans custom_form.
    / The key an answer is stored under in custom_form.

    Même règle que build_custom_form_from_request (BaseBillet/validators.py) et que
    l'éditeur de réponses de l'admin des adhésions : le libellé sans espaces autour,
    ou la clé technique si le libellé est vide.
    / Same rule as build_custom_form_from_request: stripped label, else the field key.

    :param question: un ProductFormField
    :return: la clé (str)
    """
    return (question.label or "").strip() or question.name


def cles_des_reponses_a_exporter(cles_trouvees, uuids_des_produits):
    """
    Les clés de réponses à exporter, dans l'ordre d'affichage des questions.
    / The answer keys to export, in the questions' display order.

    1. ON PART DES RÉPONSES. Seules les clés présentes dans les réponses des objets
       exportés deviennent des colonnes. Une question d'un autre événement ou d'une
       autre adhésion ne donne donc jamais de colonne vide.

    2. ON TRIE PAR ORDRE D'AFFICHAGE. Les produits dans leur ordre d'affichage
       (poids, puis nom), puis les questions de chaque produit dans leur ordre
       d'affichage (order).

    3. LES RÉPONSES ORPHELINES À LA FIN. Une clé qui ne correspond plus à aucune
       question (question renommée ou supprimée) est quand même exportée, en fin de
       tableau, par ordre alphabétique : on ne perd jamais une réponse.

    / Start from the keys found in the answers, sort by display order, and keep
      orphan keys at the end.

    :param cles_trouvees: ensemble des clés lues dans les custom_form exportés
    :param uuids_des_produits: les produits des objets exportés
    :return: liste ordonnée de clés
    """
    questions_des_produits = ProductFormField.objects.filter(
        product__uuid__in=list(uuids_des_produits),
    ).select_related("product").order_by(
        "product__poids",
        "product__name",
        "order",
        "uuid",
    )

    # Pour chaque clé : sa première position dans l'ordre d'affichage.
    # / For each key: its first display position.
    position_de_la_cle = {}
    position = 0
    for question in questions_des_produits:
        cle = cle_de_la_reponse(question)
        if cle not in position_de_la_cle:
            position_de_la_cle[cle] = position
            position += 1

    cles_rattachees_a_une_question = []
    cles_orphelines = []
    for cle in cles_trouvees:
        if cle in position_de_la_cle:
            cles_rattachees_a_une_question.append(cle)
        else:
            cles_orphelines.append(cle)

    cles_rattachees_a_une_question.sort(key=lambda cle: position_de_la_cle[cle])
    cles_orphelines.sort()
    return cles_rattachees_a_une_question + cles_orphelines
