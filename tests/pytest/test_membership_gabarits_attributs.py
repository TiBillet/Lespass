"""
Les cartes d'adhesion lisent des ATTRIBUTS, jamais des methodes.

LOCALISATION : tests/pytest/test_membership_gabarits_attributs.py

Les pages /my_account/ empilent des Membership lus dans plusieurs lieux
(`with tenant_context(...)`), puis rendent le gabarit APRES la sortie du with.
Un `{{ membership.methode }}` s'execute donc sur le schema du lieu AFFICHE, pas
sur celui qui a delivre l'adhesion. Consequences constatees :

- `is_valid()` -> `get_deadline()` -> `set_deadline()` finit par `self.save()` :
  un UPDATE sur le mauvais schema, avec une PK entiere, donc l'adhesion d'un
  autre membre ecrasee en silence (cf. tests/PIEGES.md 9.114).
- `get_iteration_end_date()` lit `Configuration.get_solo().get_tzinfo()` : le
  fuseau du mauvais lieu, donc une fin d'engagement qui peut basculer d'un jour.

La parade est la meme partout : la vue calcule dans le `with` et pose un
attribut (`est_valide`, `date_fin_engagement`), le gabarit se contente de lire.

/ Account pages stack Memberships read from several venues, then render after
leaving the tenant_context. A `{{ membership.method }}` therefore runs on the
DISPLAYED venue's schema. Views compute inside the with and set attributes;
templates only read them.
"""

import re
import uuid as uuid_module
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import Configuration, Membership, Price, Product

pytestmark = pytest.mark.django_db

RACINE_PROJET = Path(__file__).resolve().parents[2]

GABARITS_CARTE = [
    "pages/templates/pages/V2/vues/compte/membership/membership_card.html",
    "pages/templates/pages/classic/vues/compte/membership/membership_card.html",
    "pages/templates/pages/V2/vues/compte/index.html",
]

# Methodes de Membership qui requetent ou ecrivent : interdites au rendu.
# / Membership methods that query or write: forbidden at render time.
METHODES_INTERDITES = ["is_valid", "get_deadline", "get_iteration_end_date"]


@pytest.fixture
def adhesion_avec_engagement(tenant):
    """Une adhesion mensuelle calendaire avec engagement sur 12 iterations.

    CAL_MONTH est l'un des trois types dont le calcul de fin d'engagement
    utilise le fuseau du lieu — c'est le cas qui revele le bug.
    / CAL_MONTH is one of the three types whose end-of-commitment date uses the
    venue timezone — the case that exposes the bug.
    """
    suffixe = str(uuid_module.uuid4())[:8]

    with tenant_context(tenant):
        produit = Product.objects.create(
            name=f"TEST engagement {suffixe}",
            categorie_article=Product.ADHESION,
        )
        tarif = Price.objects.create(
            product=produit,
            name="Mensuel calendaire",
            prix=Decimal("10.00"),
            subscription_type=Price.CAL_MONTH,
            recurring_payment=True,
            iteration=12,
            commitment=True,
        )
        adherent = TibilletUser.objects.create(
            email=f"test-engagement-{suffixe}@tibillet.test",
            username=f"test-engagement-{suffixe}@tibillet.test",
        )

        yield tenant, tarif, adherent

        Membership.objects.filter(user=adherent).delete()
        adherent.delete()
        tarif.delete()
        try:
            produit.delete()
        except Exception:
            # django-stdimage plante dans son post_delete sans image
            # (cf. tests/PIEGES.md 10.1) : sans consequence, nom unique.
            # / django-stdimage crashes on image-less products; harmless.
            pass


def _creer_adhesion(tarif, adherent):
    return Membership.objects.create(
        user=adherent,
        price=tarif,
        status=Membership.AUTO,
        first_contribution=timezone.localtime() - timedelta(days=30),
        last_contribution=timezone.localtime(),
        deadline=timezone.localtime() + timedelta(days=30),
    )


def test_aucun_gabarit_de_carte_n_appelle_une_methode_de_membership():
    """Garde statique : un `{{ membership.is_valid }}` reintroduit fait rougir ce test.

    C'est le filet le plus large : il protege les trois gabarits d'un coup,
    sans monter de donnees.
    / Static guard: reintroducing a method call in a card template fails here.
    """
    fautes = []
    for chemin_relatif in GABARITS_CARTE:
        chemin = RACINE_PROJET / chemin_relatif
        assert chemin.exists(), f"Gabarit introuvable : {chemin_relatif}"
        contenu = chemin.read_text(encoding="utf-8")

        for methode in METHODES_INTERDITES:
            motif = r"membership\.%s\b" % methode
            for numero, ligne in enumerate(contenu.splitlines(), start=1):
                if re.search(motif, ligne):
                    fautes.append(f"{chemin_relatif}:{numero} -> membership.{methode}")

    assert not fautes, (
        "Un gabarit de carte appelle une methode de Membership au rendu, donc "
        "hors tenant_context (cf. tests/PIEGES.md 9.114). Utiliser un attribut "
        "pose par la vue (est_valide, date_fin_engagement) :\n  "
        + "\n  ".join(fautes)
    )


def test_la_fin_d_engagement_utilise_le_fuseau_du_lieu_courant(adhesion_avec_engagement):
    """Le calcul doit porter le fuseau du lieu dans lequel il est execute.

    C'est ce qui rend l'appel depuis le gabarit fautif : hors tenant_context,
    ce fuseau serait celui du lieu affiche.
    / The computation must carry the timezone of the venue it runs in.
    """
    tenant, tarif, adherent = adhesion_avec_engagement

    with tenant_context(tenant):
        adhesion = _creer_adhesion(tarif, adherent)

        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        date_fin = adhesion.get_iteration_end_date()

        assert date_fin is not None, (
            "Une adhesion CAL_MONTH recurrente avec iteration et "
            "first_contribution doit avoir une fin d'engagement."
        )
        assert date_fin.tzinfo == fuseau_du_lieu, (
            f"La fin d'engagement porte le fuseau {date_fin.tzinfo!r} au lieu "
            f"de celui du lieu ({fuseau_du_lieu!r})."
        )


def test_la_boucle_des_adhesions_ne_fabrique_pas_de_n_plus_un(adhesion_avec_engagement):
    """Le nombre de requetes ne doit pas croitre avec le nombre d'adhesions.

    `select_related('price')` couvre les acces de get_iteration_end_date au
    tarif, et `Configuration.get_solo()` est servi par le cache (cle par schema
    via django_tenants.cache.make_key). Sans cela, poser les attributs dans la
    boucle coutait une requete par adhesion.
    / Query count must not grow with the number of memberships.
    """
    tenant, tarif, adherent = adhesion_avec_engagement

    def compter_requetes_pour(nombre_d_adhesions):
        with tenant_context(tenant):
            for _ in range(nombre_d_adhesions):
                _creer_adhesion(tarif, adherent)

            # Reproduit exactement ce que font les boucles de BaseBillet.views.
            # / Mirrors what the views' loops do.
            with CaptureQueriesContext(connection) as requetes:
                adhesions = (
                    Membership.objects.filter(user=adherent)
                    .select_related("price", "price__product")
                    .prefetch_related("option_generale")
                )
                nom_du_lieu = Configuration.get_solo().organisation
                for adhesion in adhesions:
                    adhesion.origin = nom_du_lieu
                    adhesion.est_valide = adhesion.is_valid()
                    adhesion.date_fin_engagement = adhesion.get_iteration_end_date()

            return len(requetes.captured_queries)

    requetes_pour_une = compter_requetes_pour(1)
    requetes_pour_dix = compter_requetes_pour(9)  # 1 + 9 = 10 au total

    assert requetes_pour_dix <= requetes_pour_une, (
        f"Le nombre de requetes croit avec les adhesions : {requetes_pour_une} "
        f"pour 1, {requetes_pour_dix} pour 10. Un acces non precharge a ete "
        f"introduit dans la boucle (N+1)."
    )
