"""
La bascule en un clic : ce qui retient un lieu sur l'ancien Fedow.
/ One-click switch: what keeps a venue on the old Fedow.

LOCALISATION : Customers/bascule_vers_v2.py

Un lieu legacy (ancien Fedow) passe au moteur V2 en allumant un module V2 (caisse,
monnaie locale, kiosk, tireuse), une seule fois et de lui-même, si rien ne le retient.
Ce fichier dit ce qui le retient. Il vit à part de `Customers/models.py`, qui n'importe
que Django : les modèles de `BaseBillet`, `fedow_public` et `QrcodeCashless` sont
importés dans la fonction, pour éviter un cycle d'import (l'admin importe ce fichier).
/ A legacy venue moves to V2 by switching on a V2 module, if nothing holds it. This file
lists what holds it. Models are imported inside the function (no import cycle).

Spec : TECH_DOC/SESSIONS/FEDOW_IMPORT/15-spec-verrou-moteur-legacy.md §2 décision 6, §5.8.
"""

from django.db import connection
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import get_public_schema_name

from Customers.models import MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY, Client


def raisons_qui_empechent_le_passage_en_v2(lieu):
    """
    Rend la liste des raisons qui retiennent un lieu sur l'ancien Fedow.
    Une liste vide veut dire : le lieu peut passer au moteur V2.
    / Returns the reasons that keep a venue on the old Fedow; empty = it can move to V2.

    LOCALISATION : Customers/bascule_vers_v2.py

    PRÉCONDITION : la fonction est appelée DANS LE CONTEXTE DU LIEU
    (`connection.tenant` est ce lieu, comme dans une requête HTTP de son admin). Elle lit
    la `Configuration` et les paiements Stripe dans le schéma courant. Elle ne change pas
    de schéma elle-même.
    / Precondition: called in the venue's own context; it never switches schema.

    Elle ne lit que la base : aucun appel réseau (ni Fedow, ni Stripe).
    / Database only, no network call.

    LES SEPT RAISONS, dans cet ordre (une phrase par raison présente) :
    1. le lieu est l'agenda partagé de TiBillet (`Client.META`) ;
    2. le lieu utilise LaBoutik V1 (`Configuration.server_cashless` renseigné, une adresse
       vide ne compte pas) ;
    3. le lieu accepte la monnaie legacy d'un autre lieu (`federated_with`) ;
    4. le lieu est invité sur une monnaie legacy (`pending_invitations`) ;
       Pour 3 et 4 : archivées comprises, catégories FED (la monnaie de toute la
       plateforme, acceptée par la caisse V2), SUB (adhésion) et BDG (badge) exclues.
    5. le lieu a créé une monnaie legacy, archivées comprises, hors SUB et BDG ;
    6. des cartes NFC ont le lieu pour origine (`Detail.origine`) ;
    7. un paiement Stripe du lieu est relié à au moins une `FedowTransaction`, et il a au
       moins une ligne d'un produit autre qu'une adhésion, ou aucune ligne (une recharge
       passée par l'ancien Fedow), quel que soit son statut.
    Ne retiennent pas : les adhésions et badges envoyés à l'ancien Fedow, une
    `FedowTransaction` sans paiement Stripe (cache local de l'historique « Mon compte »).
    / Seven reasons, in this order. Memberships and badges never hold a venue.

    APPELÉE PAR `raisons_qui_retiennent_le_lieu_courant()` (plus bas), elle-même
    appelée par `ConfigurationAdmin.module_toggle` (refus ou bascule),
    `ConfigurationAdmin.module_toggle_modal` (texte de la fenêtre) et
    `dashboard._build_modules_context` (cartes des modules V2 d'un lieu legacy).
    / Called through raisons_qui_retiennent_le_lieu_courant() by the admin.

    :param lieu: le `Client` du lieu (Customers.models.Client)
    :return: liste de phrases traduisibles (list), vide si rien ne retient le lieu
    """
    from BaseBillet.models import (
        Configuration,
        LigneArticle,
        Paiement_stripe,
        Product,
    )
    from fedow_public.models import AssetFedowPublic
    from QrcodeCashless.models import Detail

    raisons = []

    # 1 — L'agenda partagé de TiBillet reste sur l'ancien moteur.
    # / 1 — The shared agenda stays on the old engine.
    if lieu.categorie == Client.META:
        raisons.append(_("Ce lieu est l'agenda partagé de TiBillet."))

    # 2 — Un serveur LaBoutik V1 est branché sur le lieu.
    # / 2 — A LaBoutik V1 server is plugged on the venue.
    configuration_du_lieu = Configuration.get_solo()
    if configuration_du_lieu.server_cashless:
        raisons.append(_("Votre lieu utilise LaBoutik V1."))

    # Les catégories de monnaie qui ne retiennent jamais un lieu invité ou fédéré :
    # la monnaie fédérée de la plateforme (FED), les adhésions (SUB) et les badges (BDG).
    # / Currency categories that never hold an invited or federated venue.
    categories_exclues_des_monnaies_partagees = [
        AssetFedowPublic.STRIPE_FED_FIAT,
        AssetFedowPublic.SUBSCRIPTION,
        AssetFedowPublic.BADGE,
    ]

    # 3 — Le lieu accepte la monnaie d'un autre lieu (archivées comprises).
    # / 3 — The venue accepts another venue's currency (archived included).
    accepte_une_monnaie_d_un_autre_lieu = (
        AssetFedowPublic.objects.filter(federated_with=lieu)
        .exclude(origin=lieu)
        .exclude(category__in=categories_exclues_des_monnaies_partagees)
        .exists()
    )
    if accepte_une_monnaie_d_un_autre_lieu:
        raisons.append(
            _("Votre lieu accepte une monnaie partagée avec d'autres lieux.")
        )

    # 4 — Le lieu est invité sur une monnaie (archivées comprises).
    # / 4 — The venue is invited on a currency (archived included).
    est_invite_sur_une_monnaie = (
        AssetFedowPublic.objects.filter(pending_invitations=lieu)
        .exclude(category__in=categories_exclues_des_monnaies_partagees)
        .exists()
    )
    if est_invite_sur_une_monnaie:
        raisons.append(_("Votre lieu est invité à partager une monnaie."))

    # 5 — Le lieu a créé sa propre monnaie (archivées comprises), hors adhésion et badge.
    # / 5 — The venue created its own currency (archived included), except SUB and BDG.
    categories_qui_ne_sont_pas_des_monnaies = [
        AssetFedowPublic.SUBSCRIPTION,
        AssetFedowPublic.BADGE,
    ]
    a_sa_propre_monnaie = (
        AssetFedowPublic.objects.filter(origin=lieu)
        .exclude(category__in=categories_qui_ne_sont_pas_des_monnaies)
        .exists()
    )
    if a_sa_propre_monnaie:
        raisons.append(_("Votre lieu a sa propre monnaie sur Fedow."))

    # 6 — Des cartes NFC ont le lieu pour origine.
    # / 6 — NFC cards have the venue as origin.
    a_des_cartes_nfc = Detail.objects.filter(origine=lieu).exists()
    if a_des_cartes_nfc:
        raisons.append(_("Des cartes NFC sont rattachées à votre lieu."))

    # 7 — Une recharge Stripe passée par l'ancien Fedow : un paiement relié à une
    # transaction Fedow, avec une ligne qui n'est pas une adhésion, ou sans aucune ligne.
    # Un paiement qui mêle adhésion et recharge retient le lieu. Le statut ne compte pas.
    # / 7 — A Stripe top-up through the old Fedow: payment linked to a Fedow transaction,
    # with a non-membership line or no line at all; status does not matter.
    # On part des LIGNES : `exclude()` sur une ligne écarte cette ligne seulement. Parti
    # du paiement, il écarterait tout paiement qui a UNE ligne d'adhésion, même mêlée à
    # une recharge.
    # / Start from the LINES: exclude() then drops one line, not the whole payment.
    a_une_ligne_hors_adhesion_passee_par_fedow = (
        LigneArticle.objects.filter(paiement_stripe__fedow_transactions__isnull=False)
        .exclude(pricesold__productsold__product__categorie_article=Product.ADHESION)
        .exists()
    )
    a_un_paiement_sans_ligne_passe_par_fedow = Paiement_stripe.objects.filter(
        fedow_transactions__isnull=False,
        lignearticles__isnull=True,
    ).exists()
    if (
        a_une_ligne_hors_adhesion_passee_par_fedow
        or a_un_paiement_sans_ligne_passe_par_fedow
    ):
        raisons.append(_("Votre lieu a eu des échanges avec l'ancien moteur."))

    return raisons


def raisons_qui_retiennent_le_lieu_courant():
    """
    Les raisons qui retiennent le lieu courant (`connection.tenant`) sur l'ancien Fedow.
    / The reasons that keep the current venue on the old Fedow.

    LOCALISATION : Customers/bascule_vers_v2.py

    À appeler seulement pour un lieu legacy (`lieu_en_moteur_legacy()` vrai).
    - Un vrai lieu : les raisons de `raisons_qui_empechent_le_passage_en_v2()`, liste
      vide s'il peut passer en V2.
    - Pas un vrai lieu (`FakeTenant` sous `schema_context`, schéma public) : on ne sait
      pas lire le lieu, le verrou reste fermé. La seule « raison » est alors la phrase
      fixe du verrou : jamais de liste vide, donc jamais de bascule.
    / A real venue: its reasons. Not a real venue (FakeTenant, public schema): the fixed
    lock sentence, so the lock stays closed.

    APPELÉE PAR :
    - Administration/admin_tenant.py : `ConfigurationAdmin.module_toggle` et
      `ConfigurationAdmin.module_toggle_modal` ;
    - Administration/admin/dashboard.py : `_build_modules_context`.

    :return: liste de phrases traduisibles (list)
    """
    lieu_courant = getattr(connection, "tenant", None)

    lieu_courant_est_un_vrai_lieu = (
        isinstance(lieu_courant, Client)
        and lieu_courant.schema_name != get_public_schema_name()
    )
    if not lieu_courant_est_un_vrai_lieu:
        return [MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY]

    return raisons_qui_empechent_le_passage_en_v2(lieu_courant)
