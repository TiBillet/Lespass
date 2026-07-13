"""
Le controleur du panneau Newsletter de l'admin.
/ The controller behind the admin's Newsletter panel.

LOCALISATION : newsletter/views.py

POURQUOI CES VUES SONT ICI, ET PAS DANS L'ADMIN
-----------------------------------------------
Le panneau vit dans l'admin (Administration/templates/admin/ghost/panneau_newsletter.html),
mais sa LOGIQUE vit ici :

- `Administration/admin_tenant.py` fait deja plus de 4000 lignes. Chaque action qu'on y
  ajoute l'alourdit, et la rend invisible depuis l'app a laquelle elle appartient.
- Ici, la permission est declarative : `TenantAdminPermission` sur le ViewSet, une seule
  ligne, au lieu d'un `has_custom_actions_detail_permission` noye dans une classe d'admin.
- L'app `newsletter` devient AUTONOME : son client, sa collecte, son rendu, son
  orchestration ET ses vues. On peut la lire, la tester et la detacher d'un bloc.

L'admin ne garde donc que le GABARIT du panneau.
/ The panel lives in the admin, but its LOGIC lives here: the admin module is already
4000+ lines, the permission is declarative on a ViewSet, and the `newsletter` app stays
self-contained (client, collect, render, orchestrate AND views).

POURQUOI ON RENVOIE DU HTML, ET PAS DES django.messages
--------------------------------------------------------
Les messages Django ne sont PAS rendus sur la page de modification de l'admin. C'est un
piege documente (tests/PIEGES.md : « Unfold ne rend pas le bloc messages dans son base
template »), et VERIFIE en vrai sur cette page : le message part bien en session, mais rien
ne s'affiche — le gestionnaire clique, et il ne se passe RIEN a l'ecran.

On renvoie donc un PARTIAL HTML, que HTMX injecte dans le panneau, juste sous les boutons.
Le retour apparait la ou l'utilisateur vient de cliquer. C'est aussi ce que fait le panneau
des adhesions.
/ WHY WE RETURN HTML INSTEAD OF django.messages: Django messages are NOT rendered on the
admin change page (documented in tests/PIEGES.md, and verified here). We return an HTML
partial that HTMX injects into the panel, right under the buttons.
"""

import logging

from django.shortcuts import render
from django.utils.translation import gettext as _
from rest_framework import viewsets
from rest_framework.decorators import action

from ApiBillet.permissions import TenantAdminPermission
from newsletter.client_ghost import (
    ErreurGhost,
    GhostCleRefusee,
    GhostInjoignable,
    GhostReponseInattendue,
    tester_la_connexion,
)
from newsletter.services import (
    AucunEvenement,
    GhostNonConfigure,
    creer_brouillon_newsletter,
    journaliser,
    lire_la_configuration_ghost,
)

logger = logging.getLogger(__name__)

GABARIT_DE_LA_REPONSE = "newsletter/admin/reponse.html"

# Les fenetres proposees par le panneau. Le gabarit boucle dessus pour fabriquer les
# boutons, et la vue s'en sert de LISTE BLANCHE. Ajouter « 90 jours » ne demande donc que
# d'ajouter 90 ici : le bouton apparait, et la valeur est validee.
# / The windows offered by the panel. The template loops over it to build the buttons, and
# the view uses it as an ALLOW-LIST.
FENETRES_DE_BROUILLON_EN_JOURS = (7, 30)


def _reponse(request, niveau, message, lien=None, lien_libelle=None):
    """
    Rend la boite de reponse injectee dans le panneau. / Render the panel's response box.

    :param niveau: "succes" | "erreur" | "info"
    """
    return render(
        request,
        GABARIT_DE_LA_REPONSE,
        {
            "niveau": niveau,
            "message": message,
            "lien": lien,
            "lien_libelle": lien_libelle,
        },
    )


class NewsletterAdminViewSet(viewsets.ViewSet):
    """
    Les deux actions du panneau Newsletter : tester la connexion, generer un brouillon.
    / The Newsletter panel's two actions: test the connection, generate a draft.

    Reserve aux administrateurs du tenant. La permission est declarative : une ligne.
    / Restricted to tenant admins. The permission is declarative: one line.
    """

    permission_classes = [TenantAdminPermission]

    @action(detail=False, methods=["GET"], url_path="tester-connexion")
    def tester_connexion(self, request):
        """
        Bouton « Tester la connexion ». NE MODIFIE RIEN dans Ghost : il interroge.
        / "Test the connection" button. CHANGES NOTHING in Ghost: it only queries.
        """
        try:
            url_instance_ghost, cle_admin_ghost = lire_la_configuration_ghost()
            tester_la_connexion(url_instance_ghost, cle_admin_ghost)

        except GhostNonConfigure as erreur:
            return _reponse(request, "info", str(erreur))

        except GhostInjoignable:
            return _reponse(
                request,
                "erreur",
                _("Instance Ghost injoignable. Vérifiez l'adresse."),
            )

        except GhostCleRefusee:
            return _reponse(
                request,
                "erreur",
                _("La clé Admin API est refusée par Ghost. Vérifiez la clé."),
            )

        except GhostReponseInattendue as erreur:
            return _reponse(
                request,
                "erreur",
                _("Réponse inattendue de Ghost : %(erreur)s") % {"erreur": erreur},
            )

        # Filet de securite : une erreur imprevue ne doit pas faire une page 500 dans
        # l'admin. / Safety net: no 500 page in the admin.
        except Exception as erreur:
            logger.error(f"tester_connexion : {erreur}")
            return _reponse(
                request,
                "erreur",
                _("Le test a échoué : %(erreur)s")
                % {"erreur": f"{type(erreur).__name__} — {erreur}"},
            )

        journaliser("Test de connexion : OK")
        return _reponse(
            request,
            "succes",
            _("Connexion réussie. L'adresse et la clé Admin API sont bonnes."),
        )

    @action(
        detail=False,
        methods=["POST"],
        url_path=r"brouillon/(?P<nombre_de_jours>[0-9]+)",
    )
    def brouillon(self, request, nombre_de_jours=None):
        """
        Boutons « Brouillon ». Ca CREE un brouillon dans l'instance Ghost du tenant.
        / "Draft" buttons. This CREATES a draft inside the tenant's Ghost instance.

        LOCALISATION : newsletter/views.py

        Le post est cree en `status: draft`. Il n'est JAMAIS publie, JAMAIS envoye par
        email : l'envoi reste un geste humain, dans Ghost.
        / The post is a DRAFT. Never published, never emailed.

        La fenetre vient de l'URL. On la valide contre la LISTE BLANCHE
        FENETRES_DE_BROUILLON_EN_JOURS : sans ca, un `/brouillon/100000/` ferait balayer
        toute l'histoire des evenements du reseau.
        / The window comes from the URL and is validated against an ALLOW-LIST.
        """
        nombre_de_jours = int(nombre_de_jours)
        if nombre_de_jours not in FENETRES_DE_BROUILLON_EN_JOURS:
            return _reponse(
                request, "erreur", _("Période non autorisée.")
            )

        try:
            resultat = creer_brouillon_newsletter(nombre_de_jours=nombre_de_jours)

        except GhostNonConfigure as erreur:
            return _reponse(request, "info", str(erreur))

        except AucunEvenement:
            return _reponse(
                request,
                "info",
                _(
                    "Aucun évènement sur les %(jours)s prochains jours : "
                    "aucun brouillon n'a été créé."
                )
                % {"jours": nombre_de_jours},
            )

        except GhostInjoignable:
            return _reponse(request, "erreur", _("Instance Ghost injoignable."))

        except GhostCleRefusee:
            return _reponse(
                request, "erreur", _("La clé Admin API est refusée par Ghost.")
            )

        except GhostReponseInattendue as erreur:
            return _reponse(
                request,
                "erreur",
                _("Réponse inattendue de Ghost : %(erreur)s") % {"erreur": erreur},
            )

        # Une future sous-classe d'ErreurGhost passerait au travers des trois `except`
        # ci-dessus. `creer_brouillon_newsletter` documente `:raises ErreurGhost`.
        # / A future ErreurGhost subclass would slip through the excepts above.
        except ErreurGhost as erreur:
            return _reponse(
                request, "erreur", _("Erreur Ghost : %(erreur)s") % {"erreur": erreur}
            )

        # Dernier filet. La collecte traverse les SCHEMAS des tenants voisins : un voisin
        # aux migrations en retard leve une erreur de base. Le gestionnaire doit voir un
        # message, pas une page 500.
        # / Last net: the collect walks NEIGHBOUR SCHEMAS.
        except Exception as erreur:
            logger.error(f"brouillon ({nombre_de_jours} j) : {erreur}")
            return _reponse(
                request,
                "erreur",
                _("La génération du brouillon a échoué : %(erreur)s")
                % {"erreur": f"{type(erreur).__name__} — {erreur}"},
            )

        return _reponse(
            request,
            "succes",
            _("Brouillon créé avec %(nombre)s évènement(s).")
            % {"nombre": resultat["nombre_evenements"]},
            lien=resultat["url_edition"],
            lien_libelle=_("Ouvrir dans Ghost →"),
        )
