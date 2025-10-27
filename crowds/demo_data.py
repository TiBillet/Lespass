from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.utils import timezone
import random

from fedow_public.models import AssetFedowPublic
from .models import Initiative, Contribution
from BaseBillet.models import Tag

User = get_user_model()


def _short_from_md(md: str, max_len: int = 180) -> str:
    """Create a short, FALC-friendly summary from Markdown.
    - Remove markdown syntax (#, *, ``, links/images)
    - Collapse whitespace
    - Cut at word boundary and append ellipsis if needed
    """
    if not md:
        return ""
    text = md
    # Remove code fences and inline code
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`[^`]*`", " ", text)
    # Replace images/links with their label
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    # Strip headings markers and list bullets
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    # Remove extra markdown chars
    text = re.sub(r"[*_>]+", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    # Cut at last space before limit
    cut = text[:max_len].rstrip()
    last_space = cut.rfind(" ")
    if last_space > max_len * 0.6:
        cut = cut[:last_space]
    return cut.rstrip(" .,") + "…"


@dataclass
class DemoInit:
    name: str
    goal_eur: float
    tags: List[str]
    description_md: str
    image: str | None = None


TAG_PALETTE = {
    "Écologie": "#2ecc71",
    "Solidarité": "#e67e22",
    "Culture": "#9b59b6",
    "Numérique": "#3498db",
    "Alimentation": "#c0392b",
    "Éducation": "#f1c40f",
    "Énergie": "#16a085",
    "Mobilité": "#8e44ad",
    "Santé": "#e84393",
    "Logement": "#34495e",
}


DEMO_PROJECTS: List[DemoInit] = [
    DemoInit(
        name="Atelier réparation vélos",
        goal_eur=1500,
        tags=["Mobilité", "Solidarité"],
        description_md=(
            "# Atelier réparation\n"
            "Nous organisons un atelier mensuel de réparation de vélos.\n\n"
            "- Achat d'outils\n- Pièces de rechange\n- Café partagé\n\n"
            "Objectif: permettre à toutes et tous de rouler en sécurité."
        ),
        image="https://images.unsplash.com/photo-1518459031867-a89b944bffe0?w=1200&q=80&auto=format&fit=crop",
    ),
    DemoInit(
        name="Cantine solidaire du mercredi",
        goal_eur=2200,
        tags=["Alimentation", "Solidarité"],
        description_md=(
            "Des repas à prix libre préparés collectivement.\n\n"
            "## Dépenses prévues\n- Ingrédients bio\n- Gaz/énergie\n- Ustensiles réutilisables"
        ),
        image="https://images.unsplash.com/photo-1555949963-aa79dcee981e?w=1200&q=80&auto=format&fit=crop",
    ),
    DemoInit(
        name="Festival micro-culture locale",
        goal_eur=6500,
        tags=["Culture"],
        description_md=(
            "Un petit festival participatif sur 2 jours.\n\n"
            "- Scène et sonorisation\n- Bénévolat reconnu\n- Accès prix libre"
        ),
        image="https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=1200&q=80&auto=format&fit=crop",
    ),
    DemoInit(
        name="Bibliothèque d'objets",
        goal_eur=4800,
        tags=["Écologie", "Économie du partage"],
        description_md=(
            "Prêter au lieu d'acheter.\n\n"
            "### Besoins\n- Étagères\n- Logiciel de prêt\n- Entretien"
        ),
        image="https://images.unsplash.com/photo-1519682577862-22b62b24e493?w=1200&q=80&auto=format&fit=crop",
    ),
    DemoInit(
        name="Ateliers code et éthique du numérique",
        goal_eur=3000,
        tags=["Numérique", "Éducation"],
        description_md=(
            "Des ateliers d'initiation au code libre, à la vie privée et à l'accessibilité."
        ),
        image="https://images.unsplash.com/photo-1518779578993-ec3579fee39f?w=1200&q=80&auto=format&fit=crop",
    ),
    DemoInit(
        name="Jardin partagé de quartier",
        goal_eur=2700,
        tags=["Écologie", "Alimentation"],
        description_md=(
            "Planter, arroser, récolter, ensemble.\n\n"
            "- Semences\n- Compost\n- Système d'arrosage"
        ),
        image="https://images.unsplash.com/photo-1501004318641-b39e6451bec6?w=1200&q=80&auto=format&fit=crop",
    ),
    DemoInit(
        name="Ateliers éco-rénovation participative",
        goal_eur=8200,
        tags=["Énergie", "Logement"],
        description_md=(
            "Former des équipes pour isoler et rénover des logements précaires."
        ),
        image="https://images.unsplash.com/photo-1503387762-592deb58ef4e?w=1200&q=80&auto=format&fit=crop",
    ),
    DemoInit(
        name="Clinique vélo mobile",
        goal_eur=3600,
        tags=["Mobilité", "Santé"],
        description_md=(
            "Une remorque équipée pour réparer les vélos dans différents quartiers."
        ),
        image="https://images.unsplash.com/photo-1493238792000-8113da705763?w=1200&q=80&auto=format&fit=crop",
    ),
    DemoInit(
        name="Ateliers cuisine bas carbone",
        goal_eur=1900,
        tags=["Alimentation", "Éducation"],
        description_md=(
            "Apprendre à cuisiner simple, bon, local et bas carbone."
        ),
        image="https://images.unsplash.com/photo-1466637574441-749b8f19452f?w=1200&q=80&auto=format&fit=crop",
    ),
    DemoInit(
        name="Fabrique numérique citoyenne",
        goal_eur=9100,
        tags=["Numérique", "Culture"],
        description_md=(
            "Impression 3D ouverte, ateliers de design libre, documentation en commun."
        ),
        image="https://images.unsplash.com/photo-1555421689-43cad7100751?w=1200&q=80&auto=format&fit=crop",
    ),
    DemoInit(
        name="Ateliers premiers secours et santé communautaire",
        goal_eur=4200,
        tags=["Santé", "Éducation"],
        description_md=(
            "Former des citoyen·nes aux gestes qui sauvent et à la prévention."
        ),
        image="https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?w=1200&q=80&auto=format&fit=crop",
    ),
    DemoInit(
        name="Caisse énergie partagée",
        goal_eur=12000,
        tags=["Énergie", "Solidarité"],
        description_md=(
            "Un fond d'entraide pour des factures énergie et des petits équipements sobres."
        ),
        image="https://images.unsplash.com/photo-1482192505345-5655af888cc4?w=1200&q=80&auto=format&fit=crop",
    ),
]


def _get_asset() -> AssetFedowPublic | None:
    asset = AssetFedowPublic.objects.filter(category=AssetFedowPublic.STRIPE_FED_FIAT).first()
    if asset:
        return asset
    return AssetFedowPublic.objects.first()


def _get_demo_user() -> User | None:
    # Try existing known user
    u = User.objects.filter(email="jturbeaux@pm.me").first()
    if u:
        return u
    # Fallback: first user, else create a simple demo user (only in DEBUG)
    u = User.objects.order_by("id").first()
    if u:
        return u
    try:
        return User.objects.create_user(email="demo@tibillet.local", password="demo1234", first_name="Demo")
    except Exception:
        return None


def _eur_to_cents(value: float) -> int:
    try:
        return int(round(value * 100))
    except Exception:
        return 0


def seed() -> None:
    """Seed a set of demo tags and initiatives with markdown descriptions.

    - DEBUG only: does nothing if not DEBUG
    - Idempotent: uses get_or_create by name/slug and does not duplicate
    - Assigns colored tags and a few contributions to each initiative to vary progress
    """
    if not settings.TEST:
        return

    asset = None

    # Ensure tags exist with colors
    tag_objs = {}
    for name, color in TAG_PALETTE.items():
        slug = slugify(name)
        tag, _ = Tag.objects.get_or_create(slug=slug, defaults={"name": name, "color": color})
        # If tag existed but no color yet, set it once
        if tag.color != color:
            tag.color = color
            tag.save(update_fields=["color"])
        tag_objs[name] = tag

    demo_user = _get_demo_user()

    for proj in DEMO_PROJECTS:
        # Create or get initiative
        initiative, created = Initiative.objects.get_or_create(
            name=proj.name,
            defaults={
                "description": proj.description_md,  # markdown accepted as plain text, templates may render with linebreaks/markdown later
                "short_description": _short_from_md(proj.description_md),
                "funding_goal": _eur_to_cents(proj.goal_eur),
                "asset": asset,
            },
        )
        # Ensure short_description exists for pre-existing initiatives
        if not created and not (initiative.short_description or "").strip():
            initiative.short_description = _short_from_md(proj.description_md)
            try:
                initiative.save(update_fields=["short_description"])
            except Exception:
                pass

        # Assign tags (keep existing ones)
        if proj.tags:
            to_add = []
            for tname in proj.tags:
                t = tag_objs.get(tname)
                if not t:
                    # create on the fly with a neutral color if not in palette
                    t, _ = Tag.objects.get_or_create(slug=slugify(tname), defaults={"name": tname, "color": "#6c757d"})
                    tag_objs[tname] = t
                to_add.append(t)
            initiative.tags.add(*to_add)

        # Create a few tiny contributions to vary progress, only once
        if created and demo_user:
            # 3 contributions: 5-20% of goal cumulatively
            goal = proj.goal_eur
            parts = [goal * 0.05, goal * 0.03, goal * 0.12]
            for amount_eur in parts:
                try:
                    contrib = Contribution.objects.create(
                        initiative=initiative,
                        contributor=demo_user,
                        contributor_name=(demo_user.first_name or demo_user.last_name or demo_user.email or "Anonyme"),
                        description=f"Contribution de démonstration pour ‘{initiative.name}’.",
                        amount=_eur_to_cents(amount_eur),
                    )
                    # Randomly mark some as paid in demo
                    if random.random() < 0.66:
                        contrib.payment_status = Contribution.PaymentStatus.PAID
                        contrib.paid_at = timezone.now()
                        contrib.save(update_fields=["payment_status", "paid_at"])
                except Exception:
                    # If contributor constraint or similar blocks, skip silently in demo
                    pass

    # Done
    return
