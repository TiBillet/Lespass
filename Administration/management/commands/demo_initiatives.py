import os
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django_tenants.utils import tenant_context, schema_context
from django.utils.text import slugify

from BaseBillet.models import Tag
from fedow_public.models import AssetFedowPublic
from Customers.models import Client
from crowds.models import Initiative, Contribution, Participation
from AuthBillet.utils import get_or_create_user


logger = logging.getLogger(__name__)


def ensure_tag(name: str, color: str = "#0dcaf0") -> Tag:
    tag, _ = Tag.objects.get_or_create(name=name, defaults={"color": color})
    # Harmoniser la couleur si déjà existant mais différente
    if tag.color != color and color:
        tag.color = color
        tag.save(update_fields=["color"])
    return tag


def add_contribution(initiative: Initiative, amount_eur: float, name: str | None = None):
    # Idempotent: on déduplique par triplet (initiative, montant, contributor_name) sur la dernière semaine
    amount_cents = int(round(amount_eur * 100))
    exists = Contribution.objects.filter(
        initiative=initiative,
        amount=amount_cents,
        contributor_name=name or "",
        payment_status=Contribution.PaymentStatus.PAID_ADMIN,
    ).exists()
    if not exists:
        Contribution.objects.create(
            initiative=initiative,
            amount=amount_cents,
            contributor_name=name,
            payment_status=Contribution.PaymentStatus.PAID_ADMIN,
            paid_at=timezone.now(),
            description="Contribution de démonstration",
        )


def add_participation(
    initiative: Initiative,
    user_email: str,
    requested_eur: float,
    description: str,
    state: str = Participation.State.APPROVED_ADMIN,
    time_spent_minutes: int | None = None,
):
    """
    Crée (ou met à jour) une participation.
    - Idempotent par (initiative, participant, description, requested_amount_cents)
    - Met à jour le state si différent
    - Renseigne time_spent_minutes uniquement pour les états terminés/validés
    """
    user = get_or_create_user(user_email, send_mail=False)
    # Dédupliquons par (initiative, participant, description, amount)
    amount_cents = int(round(requested_eur * 100))
    p, created = Participation.objects.get_or_create(
        initiative=initiative,
        participant=user,
        description=description,
        requested_amount_cents=amount_cents,
        defaults={"state": state},
    )

    fields_to_update: list[str] = []
    if p.state != state:
        p.state = state
        fields_to_update.append("state")

    # Renseigner le temps passé seulement si la participation est marquée terminée/validée
    if state in (Participation.State.COMPLETED_USER, Participation.State.VALIDATED_ADMIN):
        if time_spent_minutes is not None and p.time_spent_minutes != time_spent_minutes:
            p.time_spent_minutes = time_spent_minutes
            fields_to_update.append("time_spent_minutes")

    if fields_to_update:
        p.save(update_fields=fields_to_update)


class Command(BaseCommand):
    help = "Crée des initiatives de démonstration (crowds.Initiative) avec contributions, participations et tags."

    def handle(self, *args, **options):
        with schema_context("lespass"):
            self._run()

    def _run(self):
        logger.info("Création des données de démonstration pour crowds.Initiative …")

        # Tags demandés (FALC: lisibles et modifiables)
        tag_facile = ensure_tag("Difficultée : Facile", "#57e389")
        tag_inter = ensure_tag("Difficultée : Intermédiaire", "#f8e45c")
        tag_conf = ensure_tag("Difficultée : Confirmé", "#e66100")

        # Tags utiles et rigolos supplémentaires
        tag_idee = ensure_tag("Idée : Votez et on le code !", "#e01b24")
        tag_commu = ensure_tag("Communauté", "#8ff0a4")
        tag_access = ensure_tag("Accessibilité", "#6f7dff")
        tag_fun = ensure_tag("Rigolo", "#ffa348")
        tag_python = ensure_tag("Python", "#f9f06b")
        tag_htmlcss = ensure_tag("HTML/CSS", "#c061cb")
        # Tags complémentaires pour la transparence budgétaire et la communauté
        tag_transparent = ensure_tag("Transparence", "#4dd0e1")
        tag_communaute = ensure_tag("Communauté", "#8ff0a4")

        # ---------------------------------------------------------------------
        # 1) Crowdfunding — projet simple, contributions en € (pas de budget contributif)
        # ---------------------------------------------------------------------
        cf, _ = Initiative.objects.get_or_create(
            name="Crowdfunding : Financer un projet concret",
            defaults=dict(
                short_description="Un projet classique financé par des dons en €.",
                description=(
                    "Exemple de financement participatif classique : pas de budget contributif, "
                    "ni d'objectif adaptatif. Les contributions en € font avancer la jauge."
                ),
                funding_goal=int(8000 * 100),  # objectif 8 000 €
                archived=False,
                budget_contributif=False,
                adaptative_funding_goal_on_participation=False,
                funding_mode="cascade",
                currency="€",
                direct_debit=False,
            ),
        )
        # Mise à jour au cas où l'initiative existait déjà
        cf.description = (
            "Exemple de financement participatif classique : pas de budget contributif, "
            "ni d'objectif adaptatif. Les contributions en € font avancer la jauge."
        )
        cf.short_description = "Un projet classique financé par des dons en €."
        cf.currency = "€"
        cf.budget_contributif = False
        cf.adaptative_funding_goal_on_participation = False
        cf.funding_mode = "cascade"
        cf.save()
        cf.tags.set([tag_facile])
        # Contributions (progression partielle ~40%)
        add_contribution(cf, 1200, name="Fondation A")
        add_contribution(cf, 800, name="Soutien individuel")
        add_contribution(cf, 1200, name="Entreprise locale")

        # ---------------------------------------------------------------------
        # 2) Budget contributif fixe — objectif 5 000 € financé à 100%, ~20 participations = 70% du budget
        # ---------------------------------------------------------------------
        bc_fixe, _ = Initiative.objects.get_or_create(
            name="Budget contributif : objectif 5 000 € (100% financé)",
            defaults=dict(
                short_description="Budget contributif avec objectif fixe et financement total.",
                description=(
                    "Objectif de financement à 5 000 €. Les contributions couvrent 100% de l'objectif. "
                    "En parallèle, une vingtaine de participations validées représentent environ 70% du budget, "
                    "avec des durées variées (de quelques heures à plusieurs jours)."
                ),
                funding_goal=int(5000 * 100),
                archived=False,
                budget_contributif=True,
                adaptative_funding_goal_on_participation=False,
                funding_mode="cascade",
                currency="€",
                direct_debit=False,
            ),
        )
        bc_fixe.description = (
            "Objectif de financement à 5 000 €. Les contributions couvrent 100% de l'objectif. "
            "En parallèle, une vingtaine de participations validées représentent environ 70% du budget, "
            "avec des durées variées (de quelques heures à plusieurs jours)."
        )
        bc_fixe.short_description = "Budget contributif avec objectif fixe et financement total."
        bc_fixe.currency = "€"
        bc_fixe.budget_contributif = True
        bc_fixe.adaptative_funding_goal_on_participation = False
        bc_fixe.save()
        bc_fixe.tags.set([tag_inter])
        # Financement à 100% = 5 000 €
        add_contribution(bc_fixe, 1000, name="Collecte en ligne")
        add_contribution(bc_fixe, 1500, name="Subvention locale")
        add_contribution(bc_fixe, 2500, name="Mécénat")
        # ~20 participations totalisant ~70% de 5 000 € => 3 500 €
        base_email = os.environ.get("ADMIN_EMAIL", "demo@example.org")
        for i in range(1, 11):  # 10 x 100 €
            add_participation(
                bc_fixe,
                f"particip{i}@example.org",
                100,
                f"Participation #{i} — tâche courte (quelques heures)",
                state=Participation.State.APPROVED_ADMIN,
            )
        for i in range(11, 16):  # 5 x 200 €
            add_participation(
                bc_fixe,
                f"particip{i}@example.org",
                200,
                f"Participation #{i} — tâche d'une demi‑journée",
                state=Participation.State.APPROVED_ADMIN,
            )
        for i in range(16, 19):  # 3 x 300 €
            add_participation(
                bc_fixe,
                f"particip{i}@example.org",
                300,
                f"Participation #{i} — tâche d'une journée",
                state=Participation.State.VALIDATED_ADMIN,
                time_spent_minutes=7 * 60,  # ~1 journée de travail
            )
        for i in range(19, 21):  # 2 x 300 € (pour atteindre 3 500 €)
            add_participation(
                bc_fixe,
                f"particip{i}@example.org",
                300,
                f"Participation #{i} — tâche d'une journée",
                state=Participation.State.VALIDATED_ADMIN,
                time_spent_minutes=7 * 60,
            )

        # ---------------------------------------------------------------------
        # 3) Budget contributif adaptatif — 5 demandes = objectif, 55% financés par 2 structures
        # ---------------------------------------------------------------------
        bc_adapt, _ = Initiative.objects.get_or_create(
            name="Budget contributif adaptatif : 5 demandes, 55% financés",
            defaults=dict(
                short_description="Objectif qui s'ajuste au total des demandes validées.",
                description=(
                    "Le but de financement s'ajuste aux demandes validées. 5 participants "
                    "remplissent la jauge de l'objectif. Deux structures contribuent mais "
                    "n'atteignent que 55% du besoin total."
                ),
                funding_goal=int(0),  # base 0 → objectif = somme des demandes validées
                archived=False,
                budget_contributif=True,
                adaptative_funding_goal_on_participation=True,
                funding_mode="adaptative",
                currency="€",
                direct_debit=False,
            ),
        )
        bc_adapt.description = (
            "Le but de financement s'ajuste aux demandes validées. 5 participants remplissent la jauge. "
            "Deux structures contribuent mais n'atteignent que 55% du besoin total."
        )
        bc_adapt.short_description = "Objectif qui s'ajuste au total des demandes validées."
        bc_adapt.currency = "€"
        bc_adapt.budget_contributif = True
        bc_adapt.adaptative_funding_goal_on_participation = True
        bc_adapt.save()
        bc_adapt.tags.set([tag_conf])
        # 5 participations totalisant 4 000 € (objectif), financement = 2 200 € (~55%)
        add_participation(bc_adapt, base_email, 600, "Analyse et cadrage (1 j)", state=Participation.State.APPROVED_ADMIN)
        add_participation(bc_adapt, base_email, 800, "Dév. fonctionnalité A (2 j)", state=Participation.State.APPROVED_ADMIN)
        add_participation(bc_adapt, base_email, 900, "Intégration & tests (2 j)", state=Participation.State.APPROVED_ADMIN)
        add_participation(
            bc_adapt,
            base_email,
            700,
            "Design/UX (1,5 j)",
            state=Participation.State.VALIDATED_ADMIN,
            time_spent_minutes=int(1.5 * 7 * 60),  # 1,5 jour ~ 630 min
        )
        add_participation(
            bc_adapt,
            base_email,
            1000,
            "Documentation & transmission (2,5 j)",
            state=Participation.State.VALIDATED_ADMIN,
            time_spent_minutes=int(2.5 * 7 * 60),  # 2,5 jours ~ 1050 min
        )
        add_contribution(bc_adapt, 1500, name="Structure A")
        add_contribution(bc_adapt, 700, name="Structure B")

        # ---------------------------------------------------------------------
        # 4) Valorisation en monnaie temps — 6 personnes, financement en heures par une structure
        # ---------------------------------------------------------------------
        time_valo, _ = Initiative.objects.get_or_create(
            name="Valorisation en monnaie temps : contributions en heures",
            defaults=dict(
                short_description="Budget contributif valorisé en heures (monnaie temps).",
                description=(
                    "Le travail de 6 personnes est valorisé en monnaie temps. Une structure finance "
                    "l'équivalent du temps passé, de 1 heure à plusieurs demi‑journées."
                ),
                funding_goal=int(20 * 100),  # 20 h au total
                archived=False,
                budget_contributif=True,
                adaptative_funding_goal_on_participation=False,
                funding_mode="cascade",
                currency="h",
                direct_debit=False,
            ),
        )
        time_valo.description = (
            "Le travail de 6 personnes est valorisé en monnaie temps. Une structure finance l'équivalent du "
            "temps passé, de 1 heure à plusieurs demi‑journées."
        )
        time_valo.short_description = "Budget contributif valorisé en heures (monnaie temps)."
        time_valo.currency = "MoTmp"
        time_valo.budget_contributif = True
        time_valo.adaptative_funding_goal_on_participation = False
        time_valo.save()
        time_valo.tags.set([tag_facile])
        # 6 participations (1h, 2h, 3h, 4h, 4h, 6h) → 20 h, financées par une structure
        hours = [1, 2, 3, 4, 4, 6]
        for idx, h in enumerate(hours, start=1):
            add_participation(
                time_valo,
                f"h{idx}@example.org",
                float(h),
                f"Tâche #{idx} — {h} h déclarées",
                state=Participation.State.VALIDATED_ADMIN,
                time_spent_minutes=int(h * 60),
            )
        add_contribution(time_valo, 20.0, name="Structure solidaire (heures)")  # 20 h financées

        # Renommer l'asset de monnaie temps en "MTemps" s'il existe et lier l'initiative temps dessus
        try:
            time_assets = AssetFedowPublic.objects.filter(category=AssetFedowPublic.TIME)
            if time_assets.exists():
                # Met à jour le nom
                time_assets.update(name="MTemps")
                # Lier le premier trouvé si pas déjà lié
                ta = time_assets.first()
                if time_valo.asset_id != ta.uuid:
                    time_valo.asset = ta
                    time_valo.save(update_fields=["asset"])
        except Exception as e:
            logger.warning(f"Impossible de renommer/lier l'asset TIME → MTemps: {e}")

        # ---------------------------------------------------------------------
        # 4bis) Financement participatif pour maintenir le lieu (budget adaptatif)
        # ---------------------------------------------------------------------
        # FALC:
        # - Objectif qui suit les demandes (budget contributif adaptatif)
        # - Plusieurs lignes de demandes (loyers, EDF, consommables) déclarées par l'admin principal
        # - Contributions financières couvrant 60% du besoin → il manque 40% à financer
        maintien, _ = Initiative.objects.get_or_create(
            name="Financement participatif pour maintenir le lieu",
            defaults=dict(
                short_description=(
                    "exemple de budget contributif ou le total demandé suis les demande participative. "
                    "Le but est de financer en toute transparence."
                ),
                description=(
                    "Aidez nous à payer les charges : Loyer, chauffages, consomables, le budget total évolue "
                    "mais nous avons toujours besoin de vous !"
                ),
                funding_goal=int(0),  # objectif suit les demandes validées
                archived=False,
                budget_contributif=True,
                adaptative_funding_goal_on_participation=True,
                funding_mode="adaptative",
                currency="€",
                direct_debit=False,
            ),
        )
        # Mise à jour (idempotence) si l'initiative existe déjà
        maintien.short_description = (
            "exemple de budget contributif ou le total demandé suis les demande participative. "
            "Le but est de financer en toute transparence."
        )
        maintien.description = (
            "Aidez nous à payer les charges : Loyer, chauffages, consomables, le budget total évolue "
            "mais nous avons toujours besoin de vous !"
        )
        maintien.currency = "€"
        maintien.budget_contributif = True
        maintien.adaptative_funding_goal_on_participation = True
        maintien.funding_mode = "adaptative"
        maintien.save()
        # Tags lisibles
        maintien.tags.set([tag_transparent, tag_communaute])

        # Participations (demandes) — total demandé = 2 340 €
        # - 4 lignes de loyer à 500€
        for i in range(1, 5):
            add_participation(
                maintien,
                base_email,
                500,
                f"Loyer #{i} — mensualité",
                state=Participation.State.APPROVED_ADMIN,
            )
        # - 3 lignes EDF à 100€
        for i in range(1, 4):
            add_participation(
                maintien,
                base_email,
                100,
                f"Facture EDF #{i}",
                state=Participation.State.APPROVED_ADMIN,
            )
        # - Consommables divers 40€
        add_participation(
            maintien,
            base_email,
            40,
            "Consommables divers (PQ, papier imprimante)",
            state=Participation.State.APPROVED_ADMIN,
        )

        # Contributions financières: 60% du total demandé (2340€) = 1404€
        # Plusieurs contributeurs pour illustrer
        add_contribution(maintien, 700, name="Collecte en ligne")
        add_contribution(maintien, 500, name="Donateur.rice anonyme")
        add_contribution(maintien, 204, name="Cagnotte locale")

        # ---------------------------------------------------------------------
        # 5) Nouvelle initiative "Idée à voter ! Votez et on le code"
        # ---------------------------------------------------------------------
        idea_vote, _ = Initiative.objects.get_or_create(
            name="Idée à voter ! Votez et on le code",
            defaults=dict(
                short_description="Proposez une idée, votez, et on la code si tout le monde suit !",
                description=(
                    "Cette initiative sert d'exemple pour la collecte d'idées. Les membres votent pour les plus "
                    "pertinentes. Quand ça prend, on spécifie, on planifie… et on code !"
                ),
                funding_goal=0,
                archived=False,
                budget_contributif=False,
                adaptative_funding_goal_on_participation=False,
                funding_mode="cascade",
                currency="€",
                direct_debit=False,
            ),
        )
        # Mise à jour si existant déjà
        idea_vote.short_description = "Proposez une idée, votez, et on la code si tout le monde suit !"
        idea_vote.description = (
            "Cette initiative sert d'exemple pour la collecte d'idées. Les membres votent pour les plus "
            "pertinentes. Quand ça prend, on spécifie, on planifie… et on code !"
        )
        idea_vote.currency = "€"
        idea_vote.budget_contributif = False
        idea_vote.adaptative_funding_goal_on_participation = False
        idea_vote.save()
        # Tags cohérents
        idea_vote.tags.set([tag_idee, tag_facile, tag_commu, tag_fun])

        # Résumé console
        all_inits = Initiative.objects.filter(name__in=[
            cf.name, bc_fixe.name, bc_adapt.name, time_valo.name, idea_vote.name,
            "Financement participatif pour maintenir le lieu",
        ])
        for it in all_inits:
            logger.info(
                "Initiative '%s' – objectif=%s, reçu=%s, demandes=%s, tags=%s",
                it.name,
                it.get_funding_goal,
                it.funded_amount,
                it.requested_total_cents,
                ", ".join(t.name for t in it.tags.all()),
            )

        self.stdout.write(self.style.SUCCESS("Données de démonstration des initiatives (5 scénarios) créées/mises à jour."))
