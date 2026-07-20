"""
Vues des pages legales du site ROOT public (schema public).
/ Legal pages views for the public ROOT site (public schema).

LOCALISATION : seo/views_legal.py

Ces trois pages sont servies uniquement sur le tenant public (tibillet.fr).
Elles sont volontairement ECRITES EN DUR dans des gabarits, et non stockees
en base via le CMS a blocs de l'app `pages`.

POURQUOI DES GABARITS ET PAS DES PAGES EN BASE :
Un texte legal doit pouvoir etre PROUVE a une date donnee. « Quelles CGU
etaient affichees le 14 mars ? » est une question a laquelle il faut savoir
repondre. Dans git, l'historique du fichier donne la reponse. En base, une
modification ecrase la version precedente sans laisser de trace.
/ Legal text must be provable at a given date. Git history answers that;
a database row does not.

FLUX :
1. Le navigateur demande /mentions-legales/, /cgu/ ou /confidentialite/
2. seo/urls.py route vers l'une des trois vues ci-dessous
3. La vue rend le gabarit correspondant dans seo/templates/seo/legal/
4. Le gabarit etend seo/legal/base_legal.html, qui etend seo/base.html

NOTE SUR L'i18n :
Le CORPS de ces documents n'est pas passe dans {% translate %}. Un texte
juridique ne se traduit pas chaine par chaine avec gettext : sa traduction
engage la responsabilite de la cooperative et demande une relecture juridique.
Seuls les elements d'interface (titres de navigation, liens du pied de page)
sont traduits. Si une version anglaise devient necessaire, elle fera l'objet
de gabarits distincts, pas d'un fichier .po.
/ The body of these documents is not run through gettext on purpose: legal
translation needs legal review, not string extraction.
"""

from django.template.response import TemplateResponse
from django.utils.translation import gettext as _

# Date de derniere mise a jour, affichee en tete de chaque document.
# A changer A LA MAIN a chaque modification du texte correspondant.
# / Last-updated date shown at the top of each document. Update BY HAND.
DATE_MISE_A_JOUR_MENTIONS_LEGALES = "20 juillet 2026"
DATE_MISE_A_JOUR_CGU = "20 juillet 2026"
DATE_MISE_A_JOUR_CONFIDENTIALITE = "20 juillet 2026"


def mentions_legales(request):
    """
    Page /mentions-legales/ — identification de l'editeur et de l'hebergeur.
    / /mentions-legales/ page — publisher and host identification.

    URL: GET /mentions-legales/

    LOCALISATION : seo/views_legal.py

    Contenu impose par la loi pour la confiance dans l'economie numerique
    (LCEN, article 6-III) : qui edite le site, qui l'heberge, comment les
    joindre.
    """
    # `request.path` et non l'URI complete : sans lui, la canonique embarque
    # la query string, et chaque lien tracke (?utm_source=...) se declare
    # canonique de lui-meme au lieu de pointer la page unique.
    # / `request.path`, not the full URI: otherwise each tracked link
    # canonicalises itself instead of pointing at the single page.
    url_de_la_page = request.build_absolute_uri(request.path)

    context = {
        "date_mise_a_jour": DATE_MISE_A_JOUR_MENTIONS_LEGALES,
        "page_title": _("Mentions légales — TiBillet"),
        "page_description": _(
            "Mentions légales de TiBillet : éditeur, hébergeur et coordonnées "
            "de la coopérative SCIC TiBillet COOP."
        ),
        "canonical_url": url_de_la_page,
    }

    return TemplateResponse(request, "seo/legal/mentions_legales.html", context)


def cgu(request):
    """
    Page /cgu/ — conditions generales d'utilisation de la plateforme.
    / /cgu/ page — platform terms of use.

    URL: GET /cgu/

    LOCALISATION : seo/views_legal.py

    ATTENTION AU PERIMETRE : ce document regit la relation entre la
    cooperative et les personnes qui utilisent la PLATEFORME. Il ne regit
    PAS la vente d'un billet : ce contrat-la lie l'acheteur au lieu
    organisateur. Les conditions de vente sont un document distinct, porte
    par chaque tenant.
    / Scope: this covers the coop <-> user relationship on the PLATFORM.
    Ticket sales bind the buyer to the venue, under separate terms.
    """
    url_de_la_page = request.build_absolute_uri(request.path)

    context = {
        "date_mise_a_jour": DATE_MISE_A_JOUR_CGU,
        "page_title": _("Conditions générales d'utilisation — TiBillet"),
        "page_description": _(
            "Conditions générales d'utilisation de la plateforme TiBillet : "
            "rôle de la coopérative, engagements, logiciel libre, litiges."
        ),
        "canonical_url": url_de_la_page,
    }

    return TemplateResponse(request, "seo/legal/cgu.html", context)


def confidentialite(request):
    """
    Page /confidentialite/ — politique de protection des donnees (RGPD).
    / /confidentialite/ page — data protection policy (GDPR).

    URL: GET /confidentialite/

    LOCALISATION : seo/views_legal.py

    Information obligatoire des personnes concernees (RGPD, articles 13 et
    14) : quelles donnees, pourquoi, sur quelle base legale, combien de
    temps, qui y a acces, et comment exercer ses droits.
    """
    url_de_la_page = request.build_absolute_uri(request.path)

    context = {
        "date_mise_a_jour": DATE_MISE_A_JOUR_CONFIDENTIALITE,
        "page_title": _("Politique de confidentialité — TiBillet"),
        "page_description": _(
            "Comment TiBillet protège vos données : aucune revente, aucun "
            "traceur publicitaire, hébergement en France, vos droits RGPD."
        ),
        "canonical_url": url_de_la_page,
    }

    return TemplateResponse(request, "seo/legal/confidentialite.html", context)
