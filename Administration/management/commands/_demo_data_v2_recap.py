"""
Helper du management command `demo_data_v2` : l'activité d'HIER de quatre personnes
de démo sur le lieu `lespass`, pour que le récap du matin ait de quoi parler.
/ Helper for `demo_data_v2`: YESTERDAY's activity of four demo people on `lespass`,
so the morning recap has something to tell.

LOCALISATION : Administration/management/commands/_demo_data_v2_recap.py

Les quatre personnes (`recap-<prénom>@example.com`) et leur journée d'hier :
- Alice : une adhésion payée en ligne ; une inscription au planning « Bar associatif » ;
- Bruno : la « Petite salle » réservée et payée sur place ; un billet de concert ;
- Chloé : une demande d'adhésion en attente ; une inscription au planning « Festival » ;
- David : 3 bières au Bar ; une réservation de concert annulée hier.

Les ventes passent par le vrai moteur (`_une_vente_reglee`, dans
`_demo_data_v2_ventes.py`). Les dates `auto_now_add` sont fixées par `.update()`.
L'annulation passe par `cancel_and_refund_resa`, à une heure d'hier.
/ Sales go through the real engine. auto_now_add dates are set by .update(). The
cancellation goes through cancel_and_refund_resa, at a time from yesterday.

Spécification : TECH_DOC/SESSIONS/RECAP_QUOTIDIEN/SPEC.md
"""

from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.db import transaction
from django.utils import timezone

from Administration.management.commands._demo_data_v2_ventes import (
    _membership_demo,
    _reservation_demo,
    _tarif_vendu_par_le_moteur,
    _une_vente_reglee,
)

EMAIL_D_ALICE = "recap-alice@example.com"

# Les quatre personnes de démo : (prénom pour l'e-mail, prénom, nom).
# / The four demo people: (first name for the e-mail, first name, last name).
PERSONNES_DE_DEMO = [
    ("alice", "Alice", "Martin"),
    ("bruno", "Bruno", "Petit"),
    ("chloe", "Chloé", "Durand"),
    ("david", "David", "Leroy"),
]


def _personne_de_demo(prenom_de_l_email, prenom, nom):
    """
    La personne `recap-<prénom>@example.com`, créée si besoin : active, sans mail.
    / The demo person, created if needed: active, no e-mail sent.
    """
    from AuthBillet.models import TibilletUser

    personne, _cree = TibilletUser.objects.get_or_create(
        email=f"recap-{prenom_de_l_email}@example.com",
        defaults={
            "username": f"recap-{prenom_de_l_email}",
            "is_active": True,
            "first_name": prenom,
            "last_name": nom,
        },
    )
    return personne


def _premier_besoin_a_venir(slug_du_planning):
    """
    Le premier besoin à venir du planning bénévole de ce slug, ou None.
    / The first upcoming need of the volunteer planning with this slug, or None.
    """
    from booking.benevolat import aujourd_hui_au_lieu
    from booking.models import BesoinBenevole

    return (
        BesoinBenevole.objects.filter(
            planning__slug=slug_du_planning, date__gte=aujourd_hui_au_lieu()
        )
        .order_by("date", "heure_debut")
        .first()
    )


def seed_activite_de_la_veille_pour_le_recap():
    """
    L'activité d'HIER des quatre personnes de démo (voir l'en-tête du fichier).
    / YESTERDAY's activity of the four demo people.

    Doit être appelé DANS tenant_context(lieu), APRÈS
    `seed_ventes_de_la_veille_par_le_moteur` et AVANT la clôture J : la J reprend
    ainsi les ventes d'Alice, de Bruno et de David.
    / Call INSIDE tenant_context, AFTER the yesterday sales seed and BEFORE the J.

    RIEN n'est écrit si Alice a déjà une adhésion, ou si le lieu a déjà une clôture
    J (une vente d'hier encaissée après une J n'entrerait dans aucune clôture).
    Jamais `status=Membership.ADMIN` : un signal écrirait une vente en plus.
    Un objet introuvable (mode --quick, planning absent) : une phrase dans
    "sautees", pas d'erreur.
    / Nothing is written if Alice already has a membership or the venue has a J.

    :return: dict {"ecrites": [phrases], "sautees": [phrases]}
    """
    from BaseBillet.models import (
        Configuration,
        Event,
        Membership,
        PaymentMethod,
        Price,
        Product,
        Reservation,
        SaleOrigin,
    )
    from booking.models import Booking, InscriptionBenevole, Resource
    from comptabilite.models import ClotureCaisse
    from laboutik.models import PointDeVente

    resultat = {"ecrites": [], "sautees": []}

    alice_a_deja_une_adhesion = Membership.objects.filter(
        user__email=EMAIL_D_ALICE
    ).exists()
    le_lieu_a_deja_une_j = ClotureCaisse.objects.filter(
        niveau=ClotureCaisse.NIVEAU_JOURNALIER,
    ).exists()
    if alice_a_deja_une_adhesion or le_lieu_a_deja_une_j:
        resultat["sautees"].append(
            "Activité du récap : Alice a déjà une adhésion ou le lieu a déjà une "
            "clôture J, rien d'ajouté."
        )
        return resultat

    # Hier, en heure du lieu. / Yesterday, in the venue's time zone.
    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
    maintenant_au_lieu = timezone.localtime(timezone.now(), fuseau_du_lieu)
    hier = maintenant_au_lieu - timedelta(days=1)

    def a_l_heure(heure, minute):
        return hier.replace(hour=heure, minute=minute, second=0, microsecond=0)

    personnes = {}
    for prenom_de_l_email, prenom, nom in PERSONNES_DE_DEMO:
        personnes[prenom_de_l_email] = _personne_de_demo(prenom_de_l_email, prenom, nom)
    alice = personnes["alice"]
    bruno = personnes["bruno"]
    chloe = personnes["chloe"]
    david = personnes["david"]

    # Les fixtures du mode complet (voir `seed_ventes_de_la_veille_par_le_moteur`).
    # / The full-mode fixtures.
    concert = Event.objects.filter(name="What the Funk ? — Spectacle payant").first()
    billet = Product.objects.filter(
        name="Billet", categorie_article=Product.BILLET
    ).first()
    tarif_du_billet = Price.objects.filter(product=billet, name="Plein tarif").first()
    adhesion = Product.objects.filter(
        name="Adhésion associative Tiers Lustre",
        categorie_article=Product.ADHESION,
    ).first()
    tarif_de_l_adhesion = Price.objects.filter(
        product=adhesion, name="Plein tarif"
    ).first()

    # Les ventes sont écrites dans l'ordre de leurs heures, après celles de
    # `seed_ventes_de_la_veille_par_le_moteur` (la dernière à 22:15) : les numéros
    # des ventes suivent l'heure d'encaissement.
    # / Sales are written in time order, after the yesterday sales seed (last 22:15).
    with transaction.atomic():
        # --- Chloé, 9:15 : une demande d'adhésion en attente, sans vente ---
        # / Chloé: a pending membership request, no sale.
        if tarif_de_l_adhesion is None:
            resultat["sautees"].append(
                "Chloé : « Adhésion associative Tiers Lustre » introuvable, pas de "
                "demande d'adhésion."
            )
        else:
            demande_de_chloe = Membership.objects.create(
                user=chloe,
                price=tarif_de_l_adhesion,
                contribution_value=tarif_de_l_adhesion.prix,
                first_name=chloe.first_name,
                last_name=chloe.last_name,
                status=Membership.ADMIN_WAITING,
            )
            Membership.objects.filter(pk=demande_de_chloe.pk).update(
                date_added=a_l_heure(9, 15)
            )
            resultat["ecrites"].append("09:15 Chloé : demande d'adhésion en attente")

        # --- Chloé, 9:30 : inscription au planning « Festival » ---
        # / Chloé: sign-up on the "Festival" planning.
        besoin_du_festival = _premier_besoin_a_venir("festival")
        if besoin_du_festival is None:
            resultat["sautees"].append(
                "Chloé : aucun besoin à venir sur le planning « Festival »."
            )
        else:
            inscription_de_chloe = InscriptionBenevole.objects.create(
                besoin=besoin_du_festival, user=chloe
            )
            InscriptionBenevole.objects.filter(pk=inscription_de_chloe.pk).update(
                created_at=a_l_heure(9, 30)
            )
            resultat["ecrites"].append(
                "09:30 Chloé : inscription bénévole au planning « Festival »"
            )

        # --- Alice, 10:25 : inscription au planning « Bar associatif » ---
        # / Alice: sign-up on the "Bar associatif" planning.
        besoin_du_bar = _premier_besoin_a_venir("bar-associatif")
        if besoin_du_bar is None:
            resultat["sautees"].append(
                "Alice : aucun besoin à venir sur le planning « Bar associatif »."
            )
        else:
            inscription_d_alice = InscriptionBenevole.objects.create(
                besoin=besoin_du_bar, user=alice
            )
            InscriptionBenevole.objects.filter(pk=inscription_d_alice.pk).update(
                created_at=a_l_heure(10, 25)
            )
            resultat["ecrites"].append(
                "10:25 Alice : inscription bénévole au planning « Bar associatif »"
            )

        # --- David, 12:30 : réservation de concert (gratuite), annulée à 17:50 ---
        # / David: free concert reservation, cancelled at 17:50.
        if concert is None:
            resultat["sautees"].append(
                "David : concert « What the Funk ? » introuvable, pas d'annulation."
            )
        else:
            reservation_de_david = _reservation_demo(david, concert)
            Reservation.objects.filter(pk=reservation_de_david.pk).update(
                created_at=a_l_heure(12, 30)
            )
            # La vraie annulation, à une heure d'hier : `annulee_le` vaut timezone.now().
            # / The real cancellation, at a time from yesterday.
            with patch("django.utils.timezone.now", return_value=a_l_heure(17, 50)):
                reservation_de_david.cancel_and_refund_resa()
            resultat["ecrites"].append("17:50 David : réservation de concert annulée")

        # --- Alice, 22:30 : adhésion payée en ligne (Stripe) ---
        # / Alice: membership paid online.
        if tarif_de_l_adhesion is None:
            resultat["sautees"].append(
                "Alice : « Adhésion associative Tiers Lustre » introuvable, pas "
                "d'adhésion."
            )
        else:
            adhesion_d_alice = _membership_demo(
                alice, tarif_de_l_adhesion, PaymentMethod.STRIPE_NOFED
            )
            Membership.objects.filter(pk=adhesion_d_alice.pk).update(
                first_name=alice.first_name,
                last_name=alice.last_name,
                date_added=a_l_heure(22, 28),
            )
            _une_vente_reglee(
                articles=[
                    {
                        "produit": adhesion,
                        "tarif_vendu": _tarif_vendu_par_le_moteur(
                            adhesion, tarif_de_l_adhesion
                        ),
                        "quantite": 1,
                        "champs": {
                            "membership": adhesion_d_alice,
                            "payment_method": PaymentMethod.STRIPE_NOFED,
                        },
                    }
                ],
                moyen=PaymentMethod.STRIPE_NOFED,
                origine=SaleOrigin.LESPASS,
                heure=a_l_heure(22, 30),
                client=alice,
            )
            resultat["ecrites"].append("22:30 Alice : adhésion payée en ligne, Stripe")

        # --- Bruno, 22:45 : 1 billet de concert en ligne (Stripe) ---
        # / Bruno: 1 concert ticket online.
        if concert is None or tarif_du_billet is None:
            resultat["sautees"].append(
                "Bruno : concert « What the Funk ? » introuvable, pas de billet."
            )
        else:
            reservation_de_bruno = _reservation_demo(bruno, concert)
            Reservation.objects.filter(pk=reservation_de_bruno.pk).update(
                created_at=a_l_heure(22, 43)
            )
            _une_vente_reglee(
                articles=[
                    {
                        "produit": billet,
                        "tarif_vendu": _tarif_vendu_par_le_moteur(
                            billet, tarif_du_billet, concert
                        ),
                        "quantite": 1,
                        "champs": {
                            "reservation": reservation_de_bruno,
                            "payment_method": PaymentMethod.STRIPE_NOFED,
                        },
                    }
                ],
                moyen=PaymentMethod.STRIPE_NOFED,
                origine=SaleOrigin.LESPASS,
                heure=a_l_heure(22, 45),
                client=bruno,
            )
            resultat["ecrites"].append(
                "22:45 Bruno : 1 billet « What the Funk ? », Stripe"
            )

        # --- Bruno, 23:00 : la « Petite salle », payée sur place en espèces ---
        # Le créneau : samedi de la semaine prochaine, 14 h, 1 h.
        # / Bruno: the small room, paid on site in cash. Slot: next week's Saturday 2 pm.
        petite_salle = Resource.objects.filter(product__name="Petite salle").first()
        tarif_de_la_salle = None
        if petite_salle is not None:
            tarif_de_la_salle = Price.objects.filter(
                product=petite_salle.product
            ).first()
        if tarif_de_la_salle is None:
            resultat["sautees"].append(
                "Bruno : ressource « Petite salle » ou son tarif introuvable."
            )
        else:
            aujourd_hui = maintenant_au_lieu.date()
            samedi = 5
            jours_jusqu_a_samedi_prochain = (samedi - aujourd_hui.weekday()) % 7 + 7
            debut_du_creneau = datetime.combine(
                aujourd_hui + timedelta(days=jours_jusqu_a_samedi_prochain),
                time(14, 0),
                tzinfo=fuseau_du_lieu,
            )
            booking_de_bruno = Booking.objects.create(
                resource=petite_salle,
                user=bruno,
                start_datetime=debut_du_creneau,
                slot_duration_minutes=60,
                slot_count=1,
                status=Booking.PAID_BY_USER,
                first_name=bruno.first_name,
                last_name=bruno.last_name,
            )
            Booking.objects.filter(pk=booking_de_bruno.pk).update(
                booked_at=a_l_heure(23, 0)
            )
            _une_vente_reglee(
                articles=[
                    {
                        "produit": petite_salle.product,
                        "tarif_vendu": _tarif_vendu_par_le_moteur(
                            petite_salle.product, tarif_de_la_salle
                        ),
                        "quantite": 1,
                        "champs": {
                            "booking": booking_de_bruno,
                            "payment_method": PaymentMethod.CASH,
                        },
                    }
                ],
                moyen=PaymentMethod.CASH,
                origine=SaleOrigin.ADMIN,
                heure=a_l_heure(23, 5),
                client=bruno,
            )
            resultat["ecrites"].append(
                "23:05 Bruno : « Petite salle » réservée, payée sur place en espèces"
            )

        # --- David, 23:20 : 3 bières au Bar, CB ---
        # / David: 3 beers at the Bar, card.
        bar = PointDeVente.objects.filter(name="Bar").first()
        biere = Product.objects.filter(
            name="Biere", methode_caisse=Product.VENTE
        ).first()
        tarif_de_la_biere = Price.objects.filter(
            product=biere, name="Tarif Biere"
        ).first()
        if bar is None or tarif_de_la_biere is None:
            resultat["sautees"].append(
                "David : point de vente « Bar » ou bière introuvable."
            )
        else:
            _une_vente_reglee(
                articles=[
                    {
                        "produit": biere,
                        "tarif_vendu": _tarif_vendu_par_le_moteur(
                            biere, tarif_de_la_biere
                        ),
                        "quantite": 3,
                    }
                ],
                moyen=PaymentMethod.CC,
                origine=SaleOrigin.LABOUTIK,
                heure=a_l_heure(23, 20),
                point_de_vente=bar,
                client=david,
            )
            resultat["ecrites"].append("23:20 David : 3 bières au Bar, CB")

    return resultat


def envoyer_le_recap_de_demo():
    """
    Le récap du lieu, calculé et envoyé tout de suite, comme le matin.
    Doit être appelé DANS tenant_context(lieu).
    / The venue's recap, computed and sent right away. Call INSIDE tenant_context.

    Borne basse des Z : la veille à 0 h (heure du lieu). Borne haute : MAINTENANT, pas
    le seuil d'aujourd'hui : le flush vient de créer la J, elle finit après ce seuil.
    Le marqueur `recap_quotidien_traite_le` n'est pas posé : le vrai récap du matin
    part quand même. Une erreur d'envoi remonte.
    / Lower Z bound: yesterday 0 am; upper bound: NOW. The daily marker is not set.

    :return: dict {"recap": le récap ou None, "mail_envoye": bool}
    """
    from Administration.recap_quotidien import (
        envoyer_le_recap,
        fenetre_de_la_veille,
        preparer_le_recap_du_lieu,
    )
    from BaseBillet.models import Configuration

    maintenant = timezone.now()
    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
    debut_de_la_veille, _fin_de_la_veille = fenetre_de_la_veille(
        maintenant, fuseau_du_lieu
    )

    recap = preparer_le_recap_du_lieu(maintenant, debut_de_la_veille, maintenant)
    if recap is None:
        return {"recap": None, "mail_envoye": False}

    mail_envoye = envoyer_le_recap(recap)
    return {"recap": recap, "mail_envoye": mail_envoye}
