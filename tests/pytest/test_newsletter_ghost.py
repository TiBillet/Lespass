"""
Tests de la newsletter Ghost.
/ Ghost newsletter tests.

LOCALISATION : tests/pytest/test_newsletter_ghost.py
Voir TECH_DOC/SESSIONS/NEWSLETTER/SPEC.md et PLAN.md

Aucun test ne tape une vraie instance Ghost : requests.post est mocke avec
unittest.mock (le paquet `responses` n'est PAS dans le projet).
/ No test hits a real Ghost instance: requests.post is mocked with unittest.mock.
"""

import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jwt
import pytest
import requests
from django.utils import timezone
from django_tenants.utils import tenant_context

from BaseBillet.models import Event, FederatedPlace, Product
from Customers.models import Client
from newsletter.client_ghost import (
    ErreurGhost,
    GhostCleRefusee,
    GhostInjoignable,
    GhostReponseInattendue,
    creer_brouillon,
    forger_token_ghost,
)
from newsletter.collecte import calculer_tarif, collecter_evenements_du_reseau
from newsletter.rendu import rendre_newsletter_html, titre_de_la_newsletter
from newsletter.services import (
    AucunEvenement,
    GhostNonConfigure,
    creer_brouillon_newsletter,
)

# Une cle Ghost a la forme "<id hexa>:<secret hexa>".
# / A Ghost key looks like "<hex id>:<hex secret>".
CLE_GHOST_DE_TEST = "641f2b1a1c1d1e1f20212223:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def _fausse_reponse_ghost(status_code=201, id_du_post="abc123"):
    """Simule la reponse de Ghost a la creation d'un post."""
    reponse = MagicMock(spec=requests.Response)
    reponse.status_code = status_code
    reponse.ok = 200 <= status_code < 300
    reponse.text = json.dumps({"posts": [{"id": id_du_post}]})
    reponse.json.return_value = {"posts": [{"id": id_du_post}]}
    return reponse


class TestForgerTokenGhost:

    def test_le_token_porte_le_bon_header_et_la_bonne_audience(self):
        """
        Le JWT doit avoir alg=HS256, kid = l'id de la cle, et aud=/admin/.
        C'est le contrat de l'Admin API de Ghost.
        """
        token = forger_token_ghost(CLE_GHOST_DE_TEST)

        identifiant_attendu, secret_hexa = CLE_GHOST_DE_TEST.split(":")

        entete = jwt.get_unverified_header(token)
        assert entete["alg"] == "HS256"
        assert entete["kid"] == identifiant_attendu

        charge_utile = jwt.decode(
            token,
            bytes.fromhex(secret_hexa),
            algorithms=["HS256"],
            audience="/admin/",
        )
        assert charge_utile["aud"] == "/admin/"
        # Ghost refuse tout token dont la duree de vie depasse 5 minutes.
        assert charge_utile["exp"] - charge_utile["iat"] <= 5 * 60


class TestCreerBrouillon:

    def test_le_post_part_en_brouillon_sur_source_html(self):
        """
        Le POST doit viser ?source=html et porter status="draft".
        `status: draft` n'est PAS negociable : on ne publie jamais.
        """
        with patch("newsletter.client_ghost.requests.post",
                   return_value=_fausse_reponse_ghost()) as faux_post:
            creer_brouillon(
                url_instance_ghost="https://ghost.exemple.coop",
                cle_admin_ghost=CLE_GHOST_DE_TEST,
                titre="Agenda du 1 au 8 janvier",
                contenu_html="<h2>Un event</h2>",
            )

        url_appelee = faux_post.call_args[0][0]
        assert url_appelee == "https://ghost.exemple.coop/ghost/api/admin/posts/?source=html"

        corps_envoye = faux_post.call_args.kwargs["json"]
        post_envoye = corps_envoye["posts"][0]
        assert post_envoye["status"] == "draft"
        assert post_envoye["title"] == "Agenda du 1 au 8 janvier"
        assert post_envoye["html"] == "<h2>Un event</h2>"

        entetes = faux_post.call_args.kwargs["headers"]
        assert entetes["Authorization"].startswith("Ghost ")

        # On n'epingle AUCUNE version d'API : chaque tenant heberge son propre Ghost, a sa
        # propre version. Epingler "v6.0" ferait refuser la requete chez un tenant en
        # Ghost 5, et "v5.0" cassera quand Ghost retirera la compatibilite v5.
        # / We pin NO API version: each tenant self-hosts its own Ghost, at its own version.
        assert "Accept-Version" not in entetes

    def test_un_slash_final_dans_lurl_ne_produit_pas_de_double_slash(self):
        """URLField accepte un slash final : il ne doit pas donner //ghost/api/..."""
        with patch("newsletter.client_ghost.requests.post",
                   return_value=_fausse_reponse_ghost()) as faux_post:
            creer_brouillon(
                url_instance_ghost="https://ghost.exemple.coop/",
                cle_admin_ghost=CLE_GHOST_DE_TEST,
                titre="Titre",
                contenu_html="<p>x</p>",
            )

        url_appelee = faux_post.call_args[0][0]
        assert "//ghost/api" not in url_appelee
        assert url_appelee == "https://ghost.exemple.coop/ghost/api/admin/posts/?source=html"

    def test_renvoie_lurl_dedition_du_brouillon(self):
        """On rend au gestionnaire un lien cliquable vers l'editeur Ghost."""
        with patch("newsletter.client_ghost.requests.post",
                   return_value=_fausse_reponse_ghost(id_du_post="65f0a1")):
            url_edition = creer_brouillon(
                url_instance_ghost="https://ghost.exemple.coop",
                cle_admin_ghost=CLE_GHOST_DE_TEST,
                titre="Titre",
                contenu_html="<p>x</p>",
            )

        assert url_edition == "https://ghost.exemple.coop/ghost/#/editor/post/65f0a1"

    def test_une_cle_refusee_leve_GhostCleRefusee(self):
        with patch("newsletter.client_ghost.requests.post",
                   return_value=_fausse_reponse_ghost(status_code=401)):
            with pytest.raises(GhostCleRefusee):
                creer_brouillon(
                    url_instance_ghost="https://ghost.exemple.coop",
                    cle_admin_ghost=CLE_GHOST_DE_TEST,
                    titre="Titre",
                    contenu_html="<p>x</p>",
                )

    def test_un_timeout_leve_GhostInjoignable(self):
        with patch("newsletter.client_ghost.requests.post",
                   side_effect=requests.exceptions.Timeout()):
            with pytest.raises(GhostInjoignable):
                creer_brouillon(
                    url_instance_ghost="https://ghost.exemple.coop",
                    cle_admin_ghost=CLE_GHOST_DE_TEST,
                    titre="Titre",
                    contenu_html="<p>x</p>",
                )

    def test_une_reponse_500_leve_GhostReponseInattendue(self):
        with patch("newsletter.client_ghost.requests.post",
                   return_value=_fausse_reponse_ghost(status_code=500)):
            with pytest.raises(GhostReponseInattendue):
                creer_brouillon(
                    url_instance_ghost="https://ghost.exemple.coop",
                    cle_admin_ghost=CLE_GHOST_DE_TEST,
                    titre="Titre",
                    contenu_html="<p>x</p>",
                )

    def test_un_200_au_lieu_dun_201_leve_GhostReponseInattendue(self):
        """
        PANNE MUETTE. Si l'URL est en http:// et que le reverse-proxy force le https par
        une redirection 301, `requests` suit la redirection en TRANSFORMANT LE POST EN
        GET. Ghost repond alors 200 avec la LISTE de ses posts existants. Sans ce garde-fou
        on renverrait l'URL d'edition d'un article DEJA EXISTANT, sans avoir rien cree,
        et sans aucun signal d'erreur.
        La creation d'un post repond 201 : tout autre code est suspect.
        """
        with patch("newsletter.client_ghost.requests.post",
                   return_value=_fausse_reponse_ghost(status_code=200)):
            with pytest.raises(GhostReponseInattendue):
                creer_brouillon(
                    url_instance_ghost="https://ghost.exemple.coop",
                    cle_admin_ghost=CLE_GHOST_DE_TEST,
                    titre="Titre",
                    contenu_html="<p>x</p>",
                )

    def test_une_reponse_illisible_leve_GhostReponseInattendue(self):
        """Un 201 dont le corps n'a pas la forme attendue ne doit pas planter brutalement."""
        reponse_sans_posts = MagicMock(spec=requests.Response)
        reponse_sans_posts.status_code = 201
        reponse_sans_posts.ok = True
        reponse_sans_posts.text = "{}"
        reponse_sans_posts.json.return_value = {}

        with patch("newsletter.client_ghost.requests.post",
                   return_value=reponse_sans_posts):
            with pytest.raises(GhostReponseInattendue):
                creer_brouillon(
                    url_instance_ghost="https://ghost.exemple.coop",
                    cle_admin_ghost=CLE_GHOST_DE_TEST,
                    titre="Titre",
                    contenu_html="<p>x</p>",
                )

    def test_une_cle_malformee_leve_GhostCleRefusee_et_pas_une_ValueError(self):
        """
        Une cle sans ":" ou au secret non hexadecimal ne doit PAS faire fuiter une
        ValueError brute : l'admin ferait un 500 au lieu d'afficher un message.
        """
        for cle_pourrie in ("pas-de-deux-points", "id:pas-de-l-hexa-du-tout"):
            with pytest.raises(GhostCleRefusee):
                creer_brouillon(
                    url_instance_ghost="https://ghost.exemple.coop",
                    cle_admin_ghost=cle_pourrie,
                    titre="Titre",
                    contenu_html="<p>x</p>",
                )

    def test_toutes_les_erreurs_ghost_derivent_de_ErreurGhost(self):
        """L'appelant doit pouvoir attraper ErreurGhost et rien d'autre."""
        assert issubclass(GhostInjoignable, ErreurGhost)
        assert issubclass(GhostCleRefusee, ErreurGhost)
        assert issubclass(GhostReponseInattendue, ErreurGhost)


# ---------------------------------------------------------------------------
# Le calcul du tarif d'un evenement
# / An event's price calculation
# ---------------------------------------------------------------------------

def _faux_manager(objets):
    """
    Simule un manager Django prefetche : seul .all() est appele.
    / Fake a prefetched Django manager: only .all() is called.
    """
    return SimpleNamespace(all=lambda: objets)


def _faux_prix(montant, prix_libre=False, publie=True):
    """Simule un Price. `prix` est un Decimal en base. / Fake a Price."""
    return SimpleNamespace(
        prix=Decimal(str(montant)), free_price=prix_libre, publish=publie
    )


def _faux_produit(categorie, prix, publie=True, archive=False):
    """Simule un Product et ses Price. / Fake a Product with its Prices."""
    return SimpleNamespace(
        categorie_article=categorie,
        publish=publie,
        archive=archive,
        prices=_faux_manager(prix),
    )


def _faux_event(produits):
    """
    Simule un Event dont products.all() renvoie la liste donnee.
    calculer_tarif itere sur les RELATIONS (products -> prices), pas sur
    published_prices() : c'est ce qui lui permet de consommer le prefetch de la collecte
    au lieu de refaire une requete par evenement.
    / calculer_tarif walks the RELATIONS, so it consumes the caller's prefetch.
    """
    return SimpleNamespace(products=_faux_manager(produits))


class TestCalculerTarif:

    def test_pas_de_billetterie_renvoie_none(self):
        """Aucun produit -> pas de ligne tarif du tout."""
        assert calculer_tarif(_faux_event([])) is None

    def test_produit_hors_billetterie_est_ignore(self):
        """Un produit qui n'est ni BILLET ni FREERES ne fait pas un tarif d'event."""
        adhesion = _faux_produit(Product.ADHESION, [_faux_prix(10)])
        assert calculer_tarif(_faux_event([adhesion])) is None

    def test_produit_archive_est_ignore(self):
        billet_archive = _faux_produit(Product.BILLET, [_faux_prix(10)], archive=True)
        assert calculer_tarif(_faux_event([billet_archive])) is None

    def test_produit_non_publie_est_ignore(self):
        billet_cache = _faux_produit(Product.BILLET, [_faux_prix(10)], publie=False)
        assert calculer_tarif(_faux_event([billet_cache])) is None

    def test_prix_non_publie_est_ignore(self):
        """Un tarif en brouillon ne doit pas apparaitre dans la newsletter."""
        billet = _faux_produit(Product.BILLET, [_faux_prix(10, publie=False)])
        assert calculer_tarif(_faux_event([billet])) is None

    def test_seuls_les_prix_publies_comptent_dans_le_minimum(self):
        """Un tarif brouillon a 2 EUR ne doit pas faire annoncer "a partir de 2 EUR"."""
        billet = _faux_produit(
            Product.BILLET,
            [_faux_prix(2, publie=False), _faux_prix(12), _faux_prix(20)],
        )
        assert calculer_tarif(_faux_event([billet])) == "À partir de 12 €"

    def test_reservation_gratuite_donne_gratuit(self):
        gratuit = _faux_produit(Product.FREERES, [_faux_prix(0)])
        assert calculer_tarif(_faux_event([gratuit])) == "Gratuit"

    def test_billet_a_zero_euro_donne_gratuit(self):
        billet = _faux_produit(Product.BILLET, [_faux_prix(0)])
        assert calculer_tarif(_faux_event([billet])) == "Gratuit"

    def test_prix_unique_donne_le_montant(self):
        billet = _faux_produit(Product.BILLET, [_faux_prix(12)])
        assert calculer_tarif(_faux_event([billet])) == "12 €"

    def test_plusieurs_prix_donne_a_partir_de_au_minimum(self):
        billet = _faux_produit(
            Product.BILLET, [_faux_prix(20), _faux_prix(12), _faux_prix(15)]
        )
        assert calculer_tarif(_faux_event([billet])) == "À partir de 12 €"

    def test_le_minimum_se_calcule_sur_PLUSIEURS_produits(self):
        """Un event peut porter deux produits de billetterie : le minimum est global."""
        plein_tarif = _faux_produit(Product.BILLET, [_faux_prix(20)])
        tarif_reduit = _faux_produit(Product.BILLET, [_faux_prix(8)])
        assert calculer_tarif(_faux_event([plein_tarif, tarif_reduit])) == "À partir de 8 €"

    def test_le_prix_libre_gagne_sur_a_partir_de(self):
        """
        PIEGE : un event avec plusieurs prix dont un `free_price` matche AUSSI le cas
        "plusieurs prix". L'ordre d'evaluation doit faire gagner "prix libre".
        """
        billet = _faux_produit(
            Product.BILLET, [_faux_prix(5, prix_libre=True), _faux_prix(20)]
        )
        assert calculer_tarif(_faux_event([billet])) == "Prix libre, à partir de 5 €"

    def test_les_centimes_sont_affiches_seulement_si_utiles(self):
        """12.00 € s'ecrit "12 €", mais 12.50 € garde ses centimes."""
        entier = _faux_produit(Product.BILLET, [_faux_prix("12.00")])
        avec_centimes = _faux_produit(Product.BILLET, [_faux_prix("12.50")])
        assert calculer_tarif(_faux_event([entier])) == "12 €"
        assert calculer_tarif(_faux_event([avec_centimes])) == "12,50 €"


# ---------------------------------------------------------------------------
# La collecte des evenements du reseau federe
# / Gathering the federated network's events
#
# Ces tests tournent sur la base de DEV, en LECTURE SEULE, sur le seed demo_data_v2.
# Ils se mettent en `skip` (et non en echec) si le seed est absent. On ne cree RIEN en
# base : une ecriture cross-schema non annulee corromprait les donnees de demonstration.
# / Read-only tests on the DEV database. They skip if the seed is missing.
# ---------------------------------------------------------------------------

FENETRE_LARGE_EN_JOURS = 365


@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de test DB).
    # / Reuse the dev DB (no test DB creation).
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()


@pytest.fixture
def tenant_lespass():
    tenant = Client.objects.filter(schema_name="lespass").first()
    if not tenant:
        pytest.skip("Seed demo_data_v2 absent : pas de tenant 'lespass'.")
    return tenant


def _evenements_eligibles_chez(tenant, est_un_voisin, slugs_filter, slugs_exclude):
    """
    Calcule, DANS le contexte du tenant donne, les events qui DOIVENT etre collectes.
    / Compute, INSIDE the given tenant's context, the events that MUST be collected.

    C'est l'ORACLE des tests : on refait le calcul a la main, independamment du code
    teste, et on compare. Sans oracle, un `return []` ferait passer tous les tests.
    / This is the tests' ORACLE. Without it, a `return []` would pass everything.

    :return: l'ensemble des `full_url` des events attendus
    """
    debut = timezone.now() - timedelta(days=1)
    fin = timezone.now() + timedelta(days=FENETRE_LARGE_EN_JOURS)

    with tenant_context(tenant):
        evenements = Event.objects.filter(
            published=True,
            archived=False,
            datetime__gte=debut,
            datetime__lt=fin,
        ).exclude(categorie=Event.ACTION)

        if est_un_voisin:
            evenements = evenements.filter(private=False)

        eligibles = set()
        for event in evenements.distinct():
            slugs_de_levent = {tag.slug for tag in event.tag.all()}
            if slugs_filter and not (slugs_de_levent & set(slugs_filter)):
                continue
            if slugs_exclude and (slugs_de_levent & set(slugs_exclude)):
                continue
            eligibles.add(event.full_url)

    return eligibles


def _lieux_federes_du_tenant(tenant_courant):
    """Lit les FederatedPlace du tenant courant, avec leurs slugs de tags."""
    with tenant_context(tenant_courant):
        lieux = []
        for place in FederatedPlace.objects.select_related("tenant").prefetch_related(
            "tag_filter", "tag_exclude"
        ):
            lieux.append({
                "tenant": place.tenant,
                "slugs_filter": [tag.slug for tag in place.tag_filter.all()],
                "slugs_exclude": [tag.slug for tag in place.tag_exclude.all()],
            })
    return lieux


@pytest.mark.django_db
class TestCollecte:

    # --- Tests d'ORACLE : ils echouent si la collecte renvoie une liste vide ---

    def test_les_events_du_tenant_courant_remontent_tous(self, tenant_lespass):
        """
        ORACLE. Tout event publie, futur, non archive et non-ACTION du tenant courant
        DOIT figurer dans les fiches. Un `return []` fait echouer ce test.
        """
        attendus = _evenements_eligibles_chez(
            tenant_lespass, est_un_voisin=False, slugs_filter=[], slugs_exclude=[]
        )
        if not attendus:
            pytest.skip("Seed : le tenant courant n'a aucun event a venir.")

        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(FENETRE_LARGE_EN_JOURS)

        urls_collectees = {fiche["url_event"] for fiche in fiches}
        manquants = attendus - urls_collectees
        assert not manquants, f"Events du tenant courant NON collectes : {manquants}"

    def test_les_events_eligibles_dun_voisin_federe_remontent(self, tenant_lespass):
        """
        ORACLE — LE TEST QUI PROUVE LE CROSS-SCHEMA.
        Pour chaque FederatedPlace, on calcule dans le schema du VOISIN les events qui
        doivent remonter (en appliquant ses tag_filter / tag_exclude et le veto private),
        puis on verifie qu'ils sont bien dans les fiches.
        """
        lieux_federes = _lieux_federes_du_tenant(tenant_lespass)
        if not lieux_federes:
            pytest.skip("Seed : le tenant courant ne federe aucun voisin.")

        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(FENETRE_LARGE_EN_JOURS)
        urls_collectees = {fiche["url_event"] for fiche in fiches}

        au_moins_un_voisin_a_des_events = False
        for lieu in lieux_federes:
            if lieu["tenant"].schema_name == tenant_lespass.schema_name:
                continue

            attendus = _evenements_eligibles_chez(
                lieu["tenant"],
                est_un_voisin=True,
                slugs_filter=lieu["slugs_filter"],
                slugs_exclude=lieu["slugs_exclude"],
            )
            if attendus:
                au_moins_un_voisin_a_des_events = True

            manquants = attendus - urls_collectees
            assert not manquants, (
                f"Events du voisin '{lieu['tenant'].schema_name}' NON collectes : {manquants}"
            )

        if not au_moins_un_voisin_a_des_events:
            pytest.skip("Seed : aucun voisin n'a d'event eligible a venir.")

    def test_un_tag_exclu_dun_voisin_ne_remonte_pas(self, tenant_lespass):
        """
        ORACLE inverse. Un event d'un voisin portant un tag de son `tag_exclude` ne doit
        JAMAIS figurer dans les fiches. Matching par SLUG (les Tag sont par tenant).
        """
        lieux_avec_exclusion = [
            lieu for lieu in _lieux_federes_du_tenant(tenant_lespass)
            if lieu["slugs_exclude"]
            and lieu["tenant"].schema_name != tenant_lespass.schema_name
        ]
        if not lieux_avec_exclusion:
            pytest.skip("Seed : aucun voisin n'a de tag_exclude configure.")

        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(FENETRE_LARGE_EN_JOURS)
        urls_collectees = {fiche["url_event"] for fiche in fiches}

        for lieu in lieux_avec_exclusion:
            with tenant_context(lieu["tenant"]):
                urls_a_exclure = set()
                for event in Event.objects.filter(
                    tag__slug__in=lieu["slugs_exclude"], published=True
                ).distinct():
                    urls_a_exclure.add(event.full_url)

            fuites = urls_a_exclure & urls_collectees
            assert not fuites, (
                f"Events du voisin '{lieu['tenant'].schema_name}' portant un tag exclu "
                f"{lieu['slugs_exclude']} et pourtant collectes : {fuites}"
            )

    def test_aucun_event_prive_dun_voisin_ne_remonte(self, tenant_lespass):
        """
        Un event `private` ("non federable") d'un VOISIN ne doit jamais fuiter.
        Sur le tenant courant, en revanche, il reste dans SA propre newsletter :
        `private` veut dire "non federable", pas "secret". C'est ce que fait l'agenda.

        On compare par `full_url` et non par nom : deux tenants peuvent avoir des events
        homonymes, ce qui produirait un faux echec.
        """
        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(FENETRE_LARGE_EN_JOURS)
        urls_collectees = {fiche["url_event"] for fiche in fiches}

        for lieu in _lieux_federes_du_tenant(tenant_lespass):
            voisin = lieu["tenant"]
            if voisin.schema_name == tenant_lespass.schema_name:
                continue
            with tenant_context(voisin):
                urls_privees = set(
                    Event.objects.filter(private=True).values_list("full_url", flat=True)
                )
            fuites = urls_privees & urls_collectees
            assert not fuites, f"Events prives de '{voisin.schema_name}' ayant fuite : {fuites}"

    def test_aucun_intrus_ne_se_glisse_dans_les_fiches(self, tenant_lespass):
        """
        ORACLE SYMETRIQUE — le test le plus important de tous.

        Les autres oracles verifient `attendus - collectes` : ils attrapent ce qui MANQUE.
        Aucun n'attrape ce qui est EN TROP. Sans ce test, la collecte pourrait ignorer
        completement `tag_filter` (et remonter l'agenda entier d'un voisin), oublier
        `archived=False`, ou elargir la fenetre : toute la suite resterait verte.

        Ici on calcule l'UNION des events eligibles de TOUS les tenants du reseau, et on
        exige que la collecte ne produise RIEN d'autre.
        """
        union_des_attendus = _evenements_eligibles_chez(
            tenant_lespass, est_un_voisin=False, slugs_filter=[], slugs_exclude=[]
        )
        for lieu in _lieux_federes_du_tenant(tenant_lespass):
            if lieu["tenant"].schema_name == tenant_lespass.schema_name:
                continue
            union_des_attendus |= _evenements_eligibles_chez(
                lieu["tenant"],
                est_un_voisin=True,
                slugs_filter=lieu["slugs_filter"],
                slugs_exclude=lieu["slugs_exclude"],
            )

        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(FENETRE_LARGE_EN_JOURS)
        urls_collectees = {fiche["url_event"] for fiche in fiches}

        intrus = urls_collectees - union_des_attendus
        assert not intrus, (
            f"La collecte a remonte des events qu'elle ne devait PAS remonter : {intrus}. "
            f"Un filtre est ignore (tag_filter ? archived ? private ? la fenetre ?)."
        )

    # --- Tests de forme ---

    def test_la_fenetre_est_respectee(self, tenant_lespass):
        """Aucun event collecte ne doit tomber hors de la fenetre demandee."""
        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(nombre_de_jours=30)

        borne_basse = timezone.now() - timedelta(days=2)   # marge : la collecte part d'hier
        borne_haute = timezone.now() + timedelta(days=31)  # marge d'un jour
        for fiche in fiches:
            assert borne_basse <= fiche["date_debut"] <= borne_haute, (
                f"'{fiche['nom']}' est hors de la fenetre de 30 jours."
            )

    def test_les_fiches_sont_triees_par_date_croissante(self, tenant_lespass):
        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(FENETRE_LARGE_EN_JOURS)

        dates = [fiche["date_debut"] for fiche in fiches]
        assert dates == sorted(dates)

    def test_chaque_fiche_porte_toutes_les_cles_du_contrat(self, tenant_lespass):
        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(FENETRE_LARGE_EN_JOURS)

        if not fiches:
            pytest.skip("Seed : aucun event a venir, rien a verifier.")

        cles_attendues = {
            "nom", "date_debut", "date_fin", "organisateur", "description_courte",
            "description_longue", "lieu", "image_url", "tarif", "url_event",
            "libelle_bouton",
        }
        for fiche in fiches:
            assert cles_attendues == set(fiche.keys())

    def test_les_urls_sont_absolues(self, tenant_lespass):
        """Un email ne sait pas resoudre une URL relative."""
        with tenant_context(tenant_lespass):
            fiches = collecter_evenements_du_reseau(FENETRE_LARGE_EN_JOURS)

        if not fiches:
            pytest.skip("Seed : aucun event a venir.")

        for fiche in fiches:
            assert fiche["url_event"].startswith("http"), fiche["url_event"]
            if fiche["image_url"]:
                assert fiche["image_url"].startswith("http"), fiche["image_url"]


# ---------------------------------------------------------------------------
# Le rendu HTML
# / HTML rendering
# ---------------------------------------------------------------------------

def _fiche_de_test(**surcharges):
    fiche = {
        "nom": "Concert de soutien",
        "date_debut": timezone.now(),
        "date_fin": None,
        "organisateur": "La Maison des Communs",
        "description_courte": "Un concert pour la caisse de solidarité",
        "description_longue": "<p>Venez <strong>nombreux</strong> !</p>",
        "lieu": "L'atelier partagé, 12 rue des Lilas, 69100, Villeurbanne",
        "image_url": "https://demo-tibillet.ovh/media/images/concert.crop_hdr.jpg",
        "tarif": "Prix libre, à partir de 5 €",
        "url_event": "https://demo-tibillet.ovh/event/concert-de-soutien/",
        "libelle_bouton": "Réserver",
    }
    fiche.update(surcharges)
    return fiche


class TestRendu:

    def test_le_html_ne_contient_aucun_style_inline(self):
        """
        NON-REGRESSION sur la regle du chantier : l'apparence est le travail de Ghost.
        Un style inline court-circuiterait ses reglages de design newsletter et nous
        rendrait responsables de la compatibilite Outlook / Gmail / mode sombre.
        """
        html = rendre_newsletter_html([_fiche_de_test()], timezone.now(), timezone.now())
        assert "style=" not in html
        assert "<table" not in html  # pas de mise en page par tableau

    def test_levenement_est_une_carte_product_de_ghost(self):
        """
        Sans ces classes EXACTES, Ghost n'en fait PAS une carte product native : le
        brouillon s'ouvrirait en pave HTML opaque au lieu de blocs manipulables.
        """
        html = rendre_newsletter_html([_fiche_de_test()], timezone.now(), timezone.now())
        assert 'class="kg-card kg-product-card"' in html
        assert 'class="kg-product-card-container"' in html
        assert 'class="kg-product-card-title"' in html
        assert 'class="kg-product-card-description"' in html
        assert 'class="kg-product-card-image"' in html
        assert 'class="kg-product-card-button kg-product-card-btn-accent"' in html

    def test_le_bouton_porte_le_lien_et_le_libelle(self):
        html = rendre_newsletter_html([_fiche_de_test()], timezone.now(), timezone.now())
        assert 'href="https://demo-tibillet.ovh/event/concert-de-soutien/"' in html
        assert "Réserver" in html

    def test_limage_est_une_url_distante_jamais_un_upload(self):
        """On REFERENCE l'image TiBillet, on ne l'uploade pas dans Ghost."""
        html = rendre_newsletter_html([_fiche_de_test()], timezone.now(), timezone.now())
        assert 'src="https://demo-tibillet.ovh/media/images/concert.crop_hdr.jpg"' in html

    def test_aucun_br_dans_la_description_de_la_carte(self):
        """
        PIEGE VERIFIE EN REEL sur Ghost 6.52 : dans .kg-product-card-description, les <br>
        sont AVALES par le parseur. Le lieu se retrouverait colle a la date.
        UNE INFO = UN <p>.
        """
        html = rendre_newsletter_html([_fiche_de_test()], timezone.now(), timezone.now())
        debut = html.index('class="kg-product-card-description"')
        fin = html.index("</div>", debut)
        description = html[debut:fin]
        assert "<br" not in description
        assert description.count("<p>") >= 2  # au moins lieu + date

    def test_un_event_sans_image_ne_produit_pas_de_balise_img_vide(self):
        html = rendre_newsletter_html(
            [_fiche_de_test(image_url=None)], timezone.now(), timezone.now()
        )
        assert "kg-product-card-image" not in html

    def test_un_event_sans_tarif_naffiche_pas_de_ligne_tarif(self):
        html = rendre_newsletter_html(
            [_fiche_de_test(tarif=None)], timezone.now(), timezone.now()
        )
        assert "Prix libre" not in html

    def test_la_description_longue_est_hors_de_la_carte_et_en_html_brut(self):
        """
        long_description vient d'un widget Wysiwyg : c'est DEJA du HTML.
        L'echapper afficherait "&lt;strong&gt;" aux abonnes.
        Et elle doit rester DEHORS de la carte, sinon elle passe en petit gris illisible.
        """
        html = rendre_newsletter_html([_fiche_de_test()], timezone.now(), timezone.now())
        assert "<strong>nombreux</strong>" in html
        assert "&lt;strong&gt;" not in html

        # La description longue vient APRES la fermeture de la carte product.
        # / The long description comes AFTER the product card closes.
        fin_de_la_carte = html.index('class="kg-product-card-button')
        assert html.index("<strong>nombreux</strong>") > fin_de_la_carte

    def test_chaque_event_est_precede_dun_separateur(self):
        """
        <hr> -> carte divider dans Ghost. Le template en emet UN par fiche.
        On COMPTE : un simple `"<hr>" in html` passerait deja avec une seule fiche et ne
        prouverait donc pas la separation.
        """
        html = rendre_newsletter_html(
            [_fiche_de_test(nom="Premier"), _fiche_de_test(nom="Second")],
            timezone.now(),
            timezone.now(),
        )
        assert html.count("<hr>") == 2
        assert "Premier" in html
        assert "Second" in html

    def test_le_titre_porte_les_deux_dates(self):
        debut = timezone.now()
        fin = debut + timedelta(days=30)
        titre = titre_de_la_newsletter(debut, fin)
        assert str(debut.year) in titre
        assert len(titre) > 0


# ---------------------------------------------------------------------------
# L'orchestration : collecte -> rendu -> brouillon Ghost
# / Orchestration: collect -> render -> Ghost draft
# ---------------------------------------------------------------------------

def _fausse_ghost_config(url="https://ghost.exemple.coop", cle=CLE_GHOST_DE_TEST):
    config = MagicMock()
    config.ghost_url = url
    config.get_api_key.return_value = cle
    return config


@pytest.mark.django_db
class TestServices:

    def test_ghost_non_configure_leve_GhostNonConfigure(self, tenant_lespass):
        """Sans URL ni cle, on ne tente meme pas l'appel reseau."""
        config_vide = _fausse_ghost_config(url="", cle="")

        with tenant_context(tenant_lespass):
            with patch(
                "newsletter.services.GhostConfig.get_solo", return_value=config_vide
            ), patch("newsletter.services.creer_brouillon") as faux_creer:
                with pytest.raises(GhostNonConfigure):
                    creer_brouillon_newsletter(nombre_de_jours=7)

        faux_creer.assert_not_called()

    def test_une_cle_stockee_en_clair_ne_fait_pas_un_500(self, tenant_lespass):
        """
        SCENARIO REEL, ET IL FAISAIT UN 500.

        GhostConfigAdmin.save_model n'appelle set_api_key() (qui CHIFFRE la cle) QUE si le
        test de connexion a Ghost reussit. Si le gestionnaire saisit sa cle alors que Ghost
        est injoignable, elle est enregistree EN CLAIR. Au clic suivant, fernet_decrypt leve
        InvalidToken — qui n'est ni GhostNonConfigure ni ErreurGhost.

        On doit voir un message, pas une page 500.
        """
        from cryptography.fernet import InvalidToken

        config_avec_cle_pourrie = MagicMock()
        config_avec_cle_pourrie.ghost_url = "https://ghost.exemple.coop"
        config_avec_cle_pourrie.get_api_key.side_effect = InvalidToken()

        with tenant_context(tenant_lespass):
            with patch(
                "newsletter.services.GhostConfig.get_solo",
                return_value=config_avec_cle_pourrie,
            ), patch("newsletter.services.creer_brouillon") as faux_creer:
                with pytest.raises(GhostNonConfigure):
                    creer_brouillon_newsletter(nombre_de_jours=7)

        faux_creer.assert_not_called()

    def test_aucun_evenement_ne_cree_pas_de_brouillon_vide(self, tenant_lespass):
        """
        Zero event sur la periode -> on leve AucunEvenement et on NE POSTE RIEN.
        Un brouillon vide dans Ghost serait du bruit pour le gestionnaire.
        """
        config = _fausse_ghost_config()

        with tenant_context(tenant_lespass):
            with patch(
                "newsletter.services.GhostConfig.get_solo", return_value=config
            ), patch(
                "newsletter.services.collecter_evenements_du_reseau", return_value=[]
            ), patch("newsletter.services.creer_brouillon") as faux_creer:
                with pytest.raises(AucunEvenement):
                    creer_brouillon_newsletter(nombre_de_jours=7)

        faux_creer.assert_not_called()

    def test_succes_renvoie_lurl_et_le_nombre_devenements(self, tenant_lespass):
        config = _fausse_ghost_config()
        fiches = [_fiche_de_test(nom="A"), _fiche_de_test(nom="B")]

        with tenant_context(tenant_lespass):
            with patch(
                "newsletter.services.GhostConfig.get_solo", return_value=config
            ), patch(
                "newsletter.services.collecter_evenements_du_reseau", return_value=fiches
            ), patch(
                "newsletter.services.creer_brouillon",
                return_value="https://ghost.exemple.coop/ghost/#/editor/post/xyz",
            ):
                resultat = creer_brouillon_newsletter(nombre_de_jours=7)

        assert resultat["nombre_evenements"] == 2
        assert resultat["url_edition"] == "https://ghost.exemple.coop/ghost/#/editor/post/xyz"

    def test_le_brouillon_recoit_le_html_rendu_depuis_les_fiches(self, tenant_lespass):
        """
        Le HTML poste doit vraiment venir des fiches collectees : sans cette assertion,
        l'orchestration pourrait poster n'importe quoi et le test passerait.
        """
        config = _fausse_ghost_config()
        fiches = [_fiche_de_test(nom="Concert unique et reconnaissable")]

        with tenant_context(tenant_lespass):
            with patch(
                "newsletter.services.GhostConfig.get_solo", return_value=config
            ), patch(
                "newsletter.services.collecter_evenements_du_reseau", return_value=fiches
            ), patch(
                "newsletter.services.creer_brouillon", return_value="https://x/ghost/#/editor/post/1"
            ) as faux_creer:
                creer_brouillon_newsletter(nombre_de_jours=7)

        html_poste = faux_creer.call_args.kwargs["contenu_html"]
        assert "Concert unique et reconnaissable" in html_poste
        assert "kg-product-card" in html_poste

    def test_le_journal_est_ecrit_meme_en_cas_dechec(self, tenant_lespass):
        """ghost_last_log doit tracer l'echec : c'est le seul indice du gestionnaire."""
        config = _fausse_ghost_config()

        with tenant_context(tenant_lespass):
            with patch(
                "newsletter.services.GhostConfig.get_solo", return_value=config
            ), patch(
                "newsletter.services.collecter_evenements_du_reseau",
                return_value=[_fiche_de_test()],
            ), patch(
                "newsletter.services.creer_brouillon",
                side_effect=GhostInjoignable("timeout"),
            ):
                with pytest.raises(GhostInjoignable):
                    creer_brouillon_newsletter(nombre_de_jours=7)

        assert config.save.called
        assert "Erreur" in config.ghost_last_log

    def test_le_journal_est_ecrit_en_cas_de_succes(self, tenant_lespass):
        config = _fausse_ghost_config()

        with tenant_context(tenant_lespass):
            with patch(
                "newsletter.services.GhostConfig.get_solo", return_value=config
            ), patch(
                "newsletter.services.collecter_evenements_du_reseau",
                return_value=[_fiche_de_test()],
            ), patch(
                "newsletter.services.creer_brouillon",
                return_value="https://ghost.exemple.coop/ghost/#/editor/post/abc",
            ):
                creer_brouillon_newsletter(nombre_de_jours=7)

        assert config.save.called
        assert "abc" in config.ghost_last_log
