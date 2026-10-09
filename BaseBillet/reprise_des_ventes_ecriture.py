"""
La reprise des ventes existantes : l'ÉCRITURE du plan, sans le recalculer.
/ Takeover of existing sales: WRITING the plan, without recomputing it.

LOCALISATION : BaseBillet/reprise_des_ventes_ecriture.py

LE BESOIN
Le calcul (`BaseBillet/reprise_des_ventes.py`, `calculer_le_plan_de_reprise`) construit
en mémoire la liste des ventes à créer pour un lieu. Ce module l'écrit en base : chaque
vente du plan devient une vraie `Vente`, avec ses règlements, numérotée et chaînée à sa
date d'origine ; chaque ancienne ligne reçoit sa vente et ses montants entiers. Les
montants viennent du plan : ils ne sont jamais recalculés ici.
/ Each plan sale becomes a real Vente, numbered and chained at its original date; each
old line receives its sale and its integer amounts, taken from the plan.

QUI L'APPELLE
`comptabilite/management/commands/reprendre_les_ventes_existantes.py --executer`, une
fois par lieu, dans le `tenant_context` du lieu, juste après le calcul du plan.
/ Called by the command with --executer, once per venue, inside its tenant_context.

FLUX DE `ecrire_le_plan_de_reprise`
1. Garde du lieu : refus (`RepriseRefusee`) si le lieu a déjà une vente réglée hors
   reprise. Rien n'est écrit.
2. Pour chaque vente du plan, dans l'ordre du plan (l'ordre du temps ; à date égale,
   l'avoir après sa vente) : sautée si sa clé "reprise-<clé>" existe déjà, sinon écrite
   dans SA transaction (`_ecrire_une_vente`).
3. Vérification de la chaîne des ventes du lieu (`verifier_chaine_ventes`).
/ 1. venue guard; 2. each sale in plan order, one transaction each, skipped if already
written; 3. chain check.

CE QUE L'ÉCRITURE NE FAIT PAS
Aucun `save()` sur une ancienne ligne ni sur un paiement Stripe : tout passe par
`.update()`. Un `save()` relancerait la machine à statuts (BaseBillet/signals.py) :
envoi à l'ancien LaBoutik, Fedow, mails. Aucune requête réseau, aucune tâche Celery.
/ No save() on an old line or a Stripe payment: .update() only, so no signal fires.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md (§2, §4
à §10, §13 R-2, §17) ; brief CHANTIER-05-briefs/05-R-2.md ; décisions du SUIVI §4.
"""

from dataclasses import dataclass, field

from django.db import transaction

from AuthBillet.models import Wallet
from BaseBillet.models import LigneArticle, Paiement_stripe, Product, SaleOrigin
from BaseBillet.models_vente import Reglement, Vente
from BaseBillet.services_refund import (
    get_or_create_pricesold_refund,
    get_or_create_product_virement_recu,
)
from BaseBillet.services_vente import (
    ajouter_article,
    ajouter_reglement,
    annuler_vente,
    encaisser_vente,
    ouvrir_vente,
)
from laboutik.integrity import verifier_chaine_ventes
from laboutik.models import LaboutikConfiguration
from QrcodeCashless.models import CarteCashless

# Le début de la clé d'idempotence d'une vente reprise : "reprise-<clé du groupe>".
# Elle marque la vente comme reprise et rend la reprise rejouable.
# / The idempotency key prefix of a sale taken over: marks it and makes it replayable.
PREFIXE_DE_LA_CLE_DE_REPRISE = "reprise-"

# L'origine d'une vente « virement reçu » : le webhook Stripe `transfer.created` l'a
# produite (décision C1 du SUIVI §4).
# / The origin of a "transfer received" sale: the Stripe transfer.created webhook.
ORIGINE_D_UN_VIREMENT_RECU = SaleOrigin.WEBHOOK


class RepriseRefusee(Exception):
    """
    Le lieu ne peut pas être repris : il a déjà une vente réglée hors reprise. Ses
    ventes reprises prendraient des numéros après elle, hors de l'ordre du temps.
    / The venue cannot be taken over: it already has a settled non-takeover sale.
    """


@dataclass
class ResultatDeLEcriture:
    """
    Ce que l'écriture d'un plan a fait, pour le rapport de la commande.
    / What writing a plan did, for the command report.
    """

    nombre_de_ventes_ecrites: int = 0
    # Ventes dont la clé "reprise-<clé>" existait déjà : rien n'est réécrit.
    # / Sales whose key already existed: nothing is written again.
    nombre_de_ventes_sautees: int = 0
    # Ventes dont les lignes n'ont pas toutes la même origine : la vente prend celle
    # de la première ligne du plan. La production n'en a pas.
    # / Sales whose lines have different origins: the first line's origin is taken.
    nombre_de_ventes_a_origines_melangees: int = 0
    chaine_valide: bool = True
    anomalies_de_la_chaine: list = field(default_factory=list)


def ecrire_le_plan_de_reprise(plan):
    """
    Écrit le plan de reprise du lieu courant, vente par vente, dans l'ordre du plan.
    / Writes the takeover plan of the current venue, sale by sale, in plan order.

    LOCALISATION : BaseBillet/reprise_des_ventes_ecriture.py

    Une transaction PAR VENTE : une coupure laisse les ventes déjà écrites, et la
    relance saute leurs clés. Le plan est écrit tel quel, jamais trié de nouveau : son
    ordre est celui des numéros (le calcul l'a trié dans l'ordre du temps).
    / One transaction PER SALE. The plan is written as is: its order is the numbers'.

    :param plan: le `PlanDeReprise` du lieu courant (`calculer_le_plan_de_reprise`)
    :return: un `ResultatDeLEcriture`
    :raises RepriseRefusee: le lieu a déjà une vente réglée hors reprise (rien écrit)
    """
    _refuser_si_le_lieu_a_deja_vendu()

    resultat = ResultatDeLEcriture()
    for vente_a_reprendre in plan.ventes:
        cle_de_la_vente = (
            f"{PREFIXE_DE_LA_CLE_DE_REPRISE}{vente_a_reprendre.cle_du_groupe}"
        )
        vente_deja_reprise = Vente.objects.filter(
            idempotency_key=cle_de_la_vente
        ).exists()
        if vente_deja_reprise:
            resultat.nombre_de_ventes_sautees += 1
            continue

        with transaction.atomic():
            origines_melangees = _ecrire_une_vente(vente_a_reprendre, cle_de_la_vente)
        resultat.nombre_de_ventes_ecrites += 1
        if origines_melangees:
            resultat.nombre_de_ventes_a_origines_melangees += 1

    # La chaîne du lieu, vérifiée à la fin. Invalide : le lieu reste écrit (une
    # transaction par vente), l'erreur est affichée par la commande.
    # / The venue chain, checked at the end. Invalid: the venue stays written.
    cle_de_l_empreinte = LaboutikConfiguration.get_solo().get_or_create_hmac_key()
    resultat.anomalies_de_la_chaine = verifier_chaine_ventes(cle_de_l_empreinte)
    resultat.chaine_valide = resultat.anomalies_de_la_chaine == []
    return resultat


def _refuser_si_le_lieu_a_deja_vendu():
    """
    Garde du lieu (fiche R §10) : refus si une vente réglée du lieu n'est pas une vente
    reprise (clé vide ou qui ne commence pas par "reprise-"). Sinon les numéros des
    ventes reprises suivraient cette vente, hors de l'ordre du temps.
    / Venue guard: refused if a settled sale is not a takeover sale.
    """
    # `exclude` garde aussi les ventes à clé vide (NULL) : Django ajoute la condition.
    # / exclude also keeps sales with an empty (NULL) key.
    ventes_reglees_hors_reprise = Vente.objects.filter(
        statut=Vente.Statut.REGLEE
    ).exclude(idempotency_key__startswith=PREFIXE_DE_LA_CLE_DE_REPRISE)
    nombre_de_ventes_hors_reprise = ventes_reglees_hors_reprise.count()
    if nombre_de_ventes_hors_reprise > 0:
        raise RepriseRefusee(
            f"Reprise refusée : le lieu a déjà une vente réglée hors reprise "
            f"({nombre_de_ventes_hors_reprise} au total). Rien n'est écrit."
        )


def _ecrire_une_vente(vente_a_reprendre, cle_de_la_vente):
    """
    Écrit UNE vente du plan. Appelée dans une transaction.
    / Writes ONE plan sale. Called inside a transaction.

    L'ORDRE COMPTE :
    1. ouvrir la vente (en attente, sans numéro), avec sa clé de reprise ;
    2. rattacher les anciennes lignes et poser leurs montants, en UN `.update()` par
       ligne : les contraintes de base de `LigneArticle` vérifient la ligne entière ;
    3. créer l'article d'un virement reçu (le seul article créé par la reprise) ;
    4. ajouter les règlements ;
    5. encaisser (vente réglée) EN DERNIER : l'empreinte relit articles et règlements
       en base, ils doivent être déjà écrits ; ou annuler ; en attente : rien, le
       webhook Stripe l'encaissera ;
    6. poser les dates d'origine hors empreinte et les champs du paiement Stripe.
    / Order matters: open, update old lines, create the transfer item, payments, settle
    LAST (the fingerprint reads items and payments back), then dates and payment.

    :return: vrai si les lignes de la vente n'ont pas toutes la même origine
    """
    date_de_la_vente = vente_a_reprendre.datetime_de_la_vente
    origine_de_la_vente, origines_melangees = _origine_de_la_vente(vente_a_reprendre)

    # 1. La vente. / 1. The sale.
    vente = ouvrir_vente(
        origine=origine_de_la_vente,
        nature=vente_a_reprendre.nature,
        unite=vente_a_reprendre.unite,
        client=vente_a_reprendre.client,
        vente_liee=_vente_de_la_ligne_d_origine(vente_a_reprendre),
        idempotency_key=cle_de_la_vente,
    )

    # 2. Les anciennes lignes, par `.update()` : jamais `save()` (signaux, garde
    # d'immutabilité).
    # / 2. Old lines, by .update(): never save().
    for article in vente_a_reprendre.articles:
        if article.ligne is None:
            continue
        champs_de_la_ligne = {
            "vente": vente,
            "total_catalogue": article.total_catalogue,
            "part_offerte": article.part_offerte,
            "source_offert": article.source_offert,
            "part_en_jetons": article.part_en_jetons,
            "total_ttc": article.total_ttc,
            "total_ht": article.total_ht,
            "total_tva": article.total_tva,
            "hors_chiffre_affaires": article.hors_chiffre_affaires,
        }
        # Le remboursement dont l'origine n'était que dans `metadata` reçoit
        # `credit_note_for` : un avoir fait après la bascule lit ce lien pour ne pas
        # rembourser deux fois.
        # / A refund whose origin was only in metadata gets credit_note_for.
        if vente_a_reprendre.credit_note_for_a_poser:
            champs_de_la_ligne["credit_note_for_id"] = (
                vente_a_reprendre.uuid_de_la_ligne_d_origine
            )
        LigneArticle.objects.filter(pk=article.ligne.pk).update(**champs_de_la_ligne)

    # 3. L'article à créer : seulement celui d'un virement reçu (QO-9).
    # / 3. The item to create: only a received transfer's.
    for article in vente_a_reprendre.articles:
        if article.ligne is not None:
            continue
        _creer_l_article_d_un_virement_recu(vente, article, date_de_la_vente)

    # 4. Les règlements, montants du plan. / 4. Payments, plan amounts.
    for reglement in vente_a_reprendre.reglements:
        carte_du_reglement = None
        if reglement.carte_id is not None:
            carte_du_reglement = CarteCashless.objects.get(pk=reglement.carte_id)
        portefeuille_du_reglement = None
        if reglement.wallet_id is not None:
            portefeuille_du_reglement = Wallet.objects.get(pk=reglement.wallet_id)
        ajouter_reglement(
            vente,
            moyen=reglement.moyen,
            montant=reglement.montant,
            asset=reglement.asset,
            carte=carte_du_reglement,
            wallet=portefeuille_du_reglement,
            paiement_stripe=reglement.paiement_stripe,
            reference_externe=reglement.reference_externe,
        )

    # 5. Le statut, en dernier. / 5. The status, last.
    if vente_a_reprendre.statut == Vente.Statut.REGLEE:
        encaisser_vente(vente, datetime_encaissement=date_de_la_vente)
    elif vente_a_reprendre.statut == Vente.Statut.ANNULEE:
        annuler_vente(vente)

    # 6. Les dates d'origine : `datetime_creation` et `Reglement.datetime` sont en
    # `auto_now_add` et hors de l'empreinte. Puis le paiement Stripe d'origine.
    # / 6. Original dates (outside the fingerprint), then the original Stripe payment.
    Vente.objects.filter(pk=vente.pk).update(datetime_creation=date_de_la_vente)
    Reglement.objects.filter(vente=vente).update(datetime=date_de_la_vente)

    if vente_a_reprendre.paiement_stripe is not None:
        champs_du_paiement = {"vente": vente}
        if vente_a_reprendre.moyen_du_paiement_stripe is not None:
            champs_du_paiement["moyen"] = vente_a_reprendre.moyen_du_paiement_stripe
        if vente_a_reprendre.montant_encaisse_du_paiement_stripe is not None:
            champs_du_paiement["montant_encaisse"] = (
                vente_a_reprendre.montant_encaisse_du_paiement_stripe
            )
        Paiement_stripe.objects.filter(pk=vente_a_reprendre.paiement_stripe.pk).update(
            **champs_du_paiement
        )

    return origines_melangees


def _origine_de_la_vente(vente_a_reprendre):
    """
    L'origine d'une vente reprise (décision C1) : celle de ses anciennes lignes ; si
    elles en ont plusieurs, celle de la première ligne du plan. Une vente sans ancienne
    ligne est un virement reçu : origine webhook Stripe.
    / The sale origin: its old lines' (the first one's if mixed); a received transfer:
    the Stripe webhook.

    :return: (origine, vrai si les lignes ont des origines différentes)
    """
    origines_des_lignes = []
    for article in vente_a_reprendre.articles:
        if article.ligne is None:
            continue
        if article.ligne.sale_origin not in origines_des_lignes:
            origines_des_lignes.append(article.ligne.sale_origin)

    if not origines_des_lignes:
        return ORIGINE_D_UN_VIREMENT_RECU, False
    origines_melangees = len(origines_des_lignes) > 1
    return origines_des_lignes[0], origines_melangees


def _vente_de_la_ligne_d_origine(vente_a_reprendre):
    """
    La vente liée d'un avoir : la vente de sa ligne d'origine, écrite plus tôt dans
    l'ordre du plan. Aucune si l'origine est introuvable, ou si sa ligne n'a pas de
    vente (groupe d'origine en anomalie).
    / A credit note's linked sale: its origin line's sale, written earlier; else None.
    """
    uuid_de_la_ligne_d_origine = vente_a_reprendre.uuid_de_la_ligne_d_origine
    if uuid_de_la_ligne_d_origine is None:
        return None
    vente_id_de_l_origine = (
        LigneArticle.objects.filter(pk=uuid_de_la_ligne_d_origine)
        .values_list("vente_id", flat=True)
        .first()
    )
    if vente_id_de_l_origine is None:
        return None
    return Vente.objects.get(pk=vente_id_de_l_origine)


def _creer_l_article_d_un_virement_recu(vente, article, date_de_la_vente):
    """
    Crée l'article « virement reçu » par le service de vente (`ajouter_article`) :
    produit système `VR`, prix, TVA et monnaie FED du plan, ligne validée, sans moyen
    (le règlement `SN` le porte). Puis sa date devient celle du transfert.
    / Creates the "transfer received" item through the sale service, then dates it.
    """
    if article.methode_caisse_du_produit_a_creer != Product.VIREMENT_RECU:
        raise ValueError(
            f"Article à créer inconnu : {article.methode_caisse_du_produit_a_creer!r}. "
            f"La reprise ne crée que l'article « virement reçu »."
        )
    produit_du_virement = get_or_create_product_virement_recu()
    tarif_vendu_du_virement = get_or_create_pricesold_refund(produit_du_virement)
    ligne_du_virement = ajouter_article(
        vente,
        pricesold=tarif_vendu_du_virement,
        quantite=article.quantite,
        prix_unitaire=article.prix_unitaire,
        taux_tva=article.taux_tva,
        hors_chiffre_affaires=article.hors_chiffre_affaires,
        asset=article.asset,
        status=LigneArticle.VALID,
    )
    # `datetime` est en `auto_now_add` et hors de l'empreinte de la vente.
    # / datetime is auto_now_add and outside the sale fingerprint.
    LigneArticle.objects.filter(pk=ligne_du_virement.pk).update(
        datetime=date_de_la_vente
    )
