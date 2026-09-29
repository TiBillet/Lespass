"""
kiosk/views.py — Viewset du parcours de recharge kiosque (CHANTIER-02, Task 02A).
kiosk/views.py — Kiosk refill flow viewset.

Copie rebranchee de LaBoutik htmxview/views.py (class Kiosk), SANS le parcours
"link" (identification email/nom depuis le kiosque : YAGNI, cf. plan).

Rebranchements :
- Auth session + garde sur le role terminal (TibilletUser.ROLE_KIOSQUE),
  via la permission IsKioskTerminal ci-dessous.
- Le TPE se recupere via request.user.terminal (OneToOne Terminal.term_user),
  pas via un PointDeVente.KIOSK (n'existe pas cote Lespass : PaymentsIntent
  n'a pas de champ `pos`).
- ConfigurationStripe (LaBoutik) -> RootConfiguration (Lespass).

/ Rebranched copy of LaBoutik htmxview/views.py (class Kiosk), WITHOUT the
"link" flow (email/name identification from the kiosk: YAGNI, see plan).

Rebranchings:
- Session auth + terminal-role guard (TibilletUser.ROLE_KIOSQUE), via the
  IsKioskTerminal permission below.
- The terminal is fetched via request.user.terminal (Terminal.term_user
  OneToOne), not a PointDeVente.KIOSK (does not exist here: PaymentsIntent
  has no `pos` field).
- ConfigurationStripe (LaBoutik) -> RootConfiguration (Lespass).
"""

import logging
import time

from django.conf import settings
from django.db import connection
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
# Levee par Celery quand le broker (Redis) est injoignable.
# / Raised by Celery when the broker (Redis) is unreachable.
from kombu.exceptions import OperationalError
from django.utils.translation import gettext_lazy as _
from django_htmx.http import HttpResponseClientRedirect
from rest_framework import permissions, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action

from AuthBillet.models import TibilletUser
from BaseBillet.models import Configuration
from fedow_connect.fedow_api import CarteInconnueDeFedow
from kiosk.carte import lire_la_carte_pour_la_borne
from kiosk.models import PaymentsIntent, obtenir_reglages_de_la_borne
from laboutik.models import Terminal
from kiosk.tasks import poll_payment_intent_status
from kiosk.validators import RecapitulatifSerializer, RefillWisePoseValidator
from QrcodeCashless.models import CarteCashless

logger = logging.getLogger(__name__)


class IsKioskTerminal(permissions.BasePermission):
    """
    Autorise les terminaux au role Kiosque, OU un admin du tenant connecte.
    / Allows Kiosk-role terminals, OR a logged-in tenant admin.

    L'admin tenant est autorise pour pouvoir ouvrir et tester la borne depuis un
    navigateur (mode demo / debug), sans avoir a appairer un vrai terminal.
    / The tenant admin is allowed so they can open and test the kiosk from a
    browser (demo / debug), without pairing a real terminal.
    """
    message = _("Ce terminal n'a pas le role Kiosque.")

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        # Terminal appaire en role Kiosque, ET rattache au tenant courant.
        # Le check du tenant d'origine (comme HasLaBoutikTerminalAccess) evite
        # qu'un cookie de terminal d'un autre tenant soit rejoue ici.
        # / Kiosk-role terminal AND belonging to the current tenant (origin check,
        # like HasLaBoutikTerminalAccess), to prevent cross-tenant cookie replay.
        if getattr(user, "terminal_role", None) == TibilletUser.ROLE_KIOSQUE:
            return user.client_source_id == connection.tenant.pk
        # Admin du tenant : acces navigateur UNIQUEMENT en demo/debug (presentation,
        # tests). En production, une borne kiosk est un appareil physique : aucun
        # admin n'a de raison legitime d'y acceder par navigateur.
        # / Tenant admin: browser access ONLY in demo/debug. In production a kiosk is
        # a physical device; no admin has a legitimate reason to reach it by browser.
        if not (settings.DEMO or settings.DEBUG):
            return False
        return user.is_tenant_admin(connection.tenant)


def utilisateur_peut_acceder_au_paiement(payment_intent_db, user):
    """
    Le paiement appartient-il a la borne appelante, ou l'appelant est-il admin ?
    / Does the payment belong to the calling device, or is the caller an admin?

    Garde partagee par les operations sur un paiement precis (cancel, status).
    Sans elle, une borne Kiosque pourrait agir sur le paiement d'une AUTRE borne
    du meme tenant en devinant son pk (IDOR intra-tenant).
    / Shared guard for per-payment operations (cancel, status). Without it, a
    Kiosk device could act on ANOTHER device's payment in the same tenant.

    Lien : PaymentsIntent -> Terminal -> term_user (la borne). L'admin du tenant
    est tolere (acces navigateur pour demo/debug), comme dans IsKioskTerminal.
    / Chain: PaymentsIntent -> Terminal -> term_user. Tenant admin is tolerated.

    Ordre paresseux : on ne fait la requete admin (is_tenant_admin touche la base)
    que si la borne n'est pas deja proprietaire — le cas courant ne paie pas la
    requete supplementaire. / Lazy order: the admin DB lookup runs only when the
    device is not already the owner.
    """
    est_la_borne_proprietaire = (payment_intent_db.terminal.term_user_id == user.id)
    if est_la_borne_proprietaire:
        return True
    # Admin tolere UNIQUEMENT en demo/debug (meme regle que IsKioskTerminal).
    # / Admin tolerated ONLY in demo/debug (same rule as IsKioskTerminal).
    if not (settings.DEMO or settings.DEBUG):
        return False
    return user.is_tenant_admin(connection.tenant)



# Cle de session posee quand une carte primaire a ouvert la configuration.
# On y range l'HEURE d'ouverture, pas un simple True : la configuration se
# referme seule apres DUREE_OUVERTURE_CONFIGURATION_SECONDES.
# / Session key set when a primary card unlocks the configuration. It stores
# the opening TIME, so the configuration closes by itself.
CLE_SESSION_ADMIN_BORNE = "kiosk_admin"
DUREE_OUVERTURE_CONFIGURATION_SECONDES = 10 * 60

# Sans geste pendant ce delai, une borne qui affiche une carte revient a
# l'accueil (main.js). Sinon la personne suivante rechargerait la carte de la
# precedente. / Idle delay before going back home while a card is shown.
DELAI_INACTIVITE_SECONDES = 60


def contexte_du_lieu(request):
    """
    Ce que toutes les pages completes de la borne affichent : l'identite du lieu,
    le simulateur NFC (DEMO) et le type d'appareil.
    / What every full kiosk page shows: place identity, NFC simulator (DEMO),
    device type.

    LOCALISATION : kiosk/views.py

    Le kiosque porte les couleurs du lieu, pas celles de Tibillet : son logo
    (Configuration.logo), sinon l'initiale de son nom.
    / The kiosk wears the place's identity: its logo, else its initial.
    """
    configuration_du_lieu = Configuration.get_solo()
    nom_du_lieu = configuration_du_lieu.organisation or ""

    adresse_du_logo = None
    if configuration_du_lieu.logo:
        try:
            adresse_du_logo = configuration_du_lieu.logo.med.url
        except Exception:
            # Variation absente (vieux fichier) : on prend l'original.
            # / Missing variation (old file): use the original.
            adresse_du_logo = configuration_du_lieu.logo.url

    initiale_du_lieu = nom_du_lieu.strip()[:1].upper() if nom_du_lieu.strip() else "T"

    # type_app arrive une seule fois via le bridge (/kiosk/?type_app=cordova).
    # Les retours accueil perdent le query param : on le memorise en session pour
    # reinjecter cordova.js. / type_app arrives once via the bridge redirect:
    # keep it in session so cordova.js is still injected.
    type_app = request.GET.get("type_app")
    if type_app:
        request.session["type_app"] = type_app
    else:
        type_app = request.session.get("type_app", "unknown")

    return {
        "nom_du_lieu": nom_du_lieu,
        "adresse_du_logo": adresse_du_logo,
        "initiale_du_lieu": initiale_du_lieu,
        "terminal": getattr(request.user, "terminal", None),
        "delai_inactivite_secondes": DELAI_INACTIVITE_SECONDES,
        "test": settings.TEST,
        "demo": settings.DEMO,
        # Les cartes du simulateur NFC (mode DEMO).
        # Ce sont les memes cartes que dans la caisse (laboutik/views.py)
        # et la tireuse (controlvanne/viewsets.py) : memes tag_id, memes noms.
        # base.html les donne a nfc.js, qui affiche un bouton par carte.
        # / NFC simulator cards (DEMO): same cards as the POS and the tap.
        "cartes_du_simulateur_nfc": [
            {"tag_id": settings.DEMO_TAGID_CM, "name": _("Carte primaire")},
            {"tag_id": settings.DEMO_TAGID_CLIENT1, "name": _("Carte client 1")},
            {"tag_id": settings.DEMO_TAGID_CLIENT2, "name": _("Carte client 2")},
            {"tag_id": settings.DEMO_TAGID_CLIENT3, "name": _("Carte client 3")},
            {"tag_id": settings.DEMO_TAGID_CLIENT4, "name": _("Carte inconnue")},
        ],
        # base.html s'en sert pour injecter cordova.js (plugin NFC de la borne
        # Android). / base.html uses it to inject cordova.js.
        "type_app": type_app,
    }


def premier_message_d_erreur(erreurs_du_serializer):
    """
    Renvoie le premier message d'erreur d'un serializer DRF, en texte.
    / Returns the first error message of a DRF serializer, as text.

    LOCALISATION : kiosk/views.py
    """
    premiere_liste_erreurs = next(iter(erreurs_du_serializer.values()))
    return premiere_liste_erreurs[0]


def la_recharge_est_active(request):
    """
    La borne propose-t-elle la recharge en ce moment ?
    / Does the kiosk currently offer the refill?

    LOCALISATION : kiosk/views.py

    Verifie cote SERVEUR, au debut de chaque etape du parcours : un ecran
    reste ouvert, ou un POST rejoue, ne doit pas permettre de payer sur une
    borne mise en pause.
    Sans borne appairee (admin en DEMO), la recharge est consideree active.
    / Checked SERVER-side at each step: a stale screen or replayed POST must
    not allow paying on a paused kiosk. No paired kiosk: refill counts as on.
    """
    terminal = getattr(request.user, "terminal", None)
    reglages = obtenir_reglages_de_la_borne(terminal)
    if reglages is None:
        return True
    return reglages.recharge_active


def la_configuration_est_ouverte(request):
    """
    Une carte primaire a-t-elle ouvert la configuration, il y a moins de
    DUREE_OUVERTURE_CONFIGURATION_SECONDES ?
    / Has a primary card unlocked the configuration recently enough?

    LOCALISATION : kiosk/views.py
    """
    heure_d_ouverture = request.session.get(CLE_SESSION_ADMIN_BORNE)

    # Seul un horodatage est accepte (les anciennes sessions portaient True).
    # / Only a timestamp is accepted (old sessions stored True).
    heure_d_ouverture_valide = isinstance(heure_d_ouverture, (int, float)) and not isinstance(
        heure_d_ouverture, bool
    )
    if not heure_d_ouverture_valide:
        return False

    secondes_ecoulees = time.time() - heure_d_ouverture
    if secondes_ecoulees > DUREE_OUVERTURE_CONFIGURATION_SECONDES:
        request.session.pop(CLE_SESSION_ADMIN_BORNE, None)
        return False
    return True


def contexte_des_modules(terminal):
    """
    L'etat des modules de la borne : une seule source de verite pour la page
    de configuration ET la grille rendue apres chaque interrupteur.
    / Module state: single source of truth for the page and the grid.

    LOCALISATION : kiosk/views.py

    Le nombre de services actifs et la phrase sous « Demarrer » sont calcules
    ICI, pas en JavaScript. / Active count computed HERE, not in JavaScript.
    """
    reglages = obtenir_reglages_de_la_borne(terminal)
    # Sans borne appairee (admin en DEMO), la recharge est consideree active,
    # comme sur l'ecran public (list). / No paired kiosk: refill counts as on.
    recharge_active = reglages.recharge_active if reglages else True

    nombre_de_services_actifs = 0
    if recharge_active:
        nombre_de_services_actifs += 1

    return {
        "terminal": terminal,
        "reglages": reglages,
        "recharge_active": recharge_active,
        "nombre_de_services_actifs": nombre_de_services_actifs,
    }


def rendre_les_modules(request, terminal, message_erreur=None):
    """
    Rend la grille des modules de l'ecran de configuration.
    / Renders the module grid of the configuration screen.

    LOCALISATION : kiosk/views.py
    """
    context = contexte_des_modules(terminal)
    context["error_message"] = message_erreur
    return render(request, "kiosk/partial/modules_borne.html", context)


class KioskViewSet(viewsets.ViewSet):
    """
    Parcours de recharge en libre-service (borne kiosque + TPE Stripe),
    et ecran de configuration de la borne (debloque par une carte primaire).
    / Self-service refill flow (kiosk terminal + Stripe card reader), and the
    kiosk configuration screen (unlocked by a primary card).

    ECRANS DU PARCOURS (tous swappes dans #tb-kiosque) :
    1. Posez votre carte          -> partial/etape_poser_carte.html (list)
    2. Solde + 3. choix du montant -> partial/etape_solde_et_montant.html (check_request_card)
    4. Recapitulatif              -> partial/etape_recapitulatif.html (recapitulatif)
    5. Paiement au TPE            -> waiting_credit_card_terminal.html (refill_with_wisepos)
    6/9. Succes puis merci, 7. refus -> success.html / cancel.html (websocket)
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsKioskTerminal]

    def list(self, request):
        """
        GET /kiosk/ — ecran 1 : posez votre carte. Si la recharge est coupee,
        la borne affiche « en pause ».
        / GET /kiosk/ — screen 1: tap your card. If refill is off, "paused".

        LOCALISATION : kiosk/views.py
        """
        context = contexte_du_lieu(request)
        context["recharge_active"] = la_recharge_est_active(request)

        return render(request, "kiosk/recharge.html", context)

    @action(detail=False, methods=['POST'])
    def check_request_card(self, request, *args, **kwargs):
        """
        POST /kiosk/check_request_card/ — lit la carte posee (Fedow distant) et
        affiche son solde, puis le choix du montant.
        Reponse HTML (partial) en 200 meme en erreur : HTMX ne swap pas les 4xx.
        / POST /kiosk/check_request_card/ — reads the tapped card (remote Fedow)
        and shows its balance, then the amount choice. Always 200 HTML.

        LOCALISATION : kiosk/views.py
        """
        # Borne en pause : on n'avance pas dans le parcours (garde serveur).
        # / Paused kiosk: the flow does not move on (server guard).
        if not la_recharge_est_active(request):
            return render(request, "kiosk/partial/borne_en_pause.html")

        # str() : request.data peut venir d'un POST JSON (valeur non-string).
        # / str(): request.data can come from a JSON POST (non-string value).
        tag_id = str(request.data.get('tag_id') or '').strip().upper()
        logger.info(f"--> tag_id = {tag_id}")

        if not tag_id:
            context = {"error_message": _("Aucune carte reçue. Merci de scanner à nouveau.")}
            return render(request, "kiosk/partial/etape_poser_carte.html", context)

        try:
            carte_lue = lire_la_carte_pour_la_borne(tag_id)
        except (CarteCashless.DoesNotExist, CarteInconnueDeFedow):
            context = {"error_message": _("Carte inconnue : %(tag_id)s") % {"tag_id": tag_id}}
            return render(request, "kiosk/partial/etape_poser_carte.html", context)
        except Exception as e:
            logger.error(f"check_request_card : erreur Fedow pour {tag_id} : {e}")
            context = {"error_message": _("La carte n'a pas pu être lue. Merci de réessayer.")}
            return render(request, "kiosk/partial/etape_poser_carte.html", context)

        context = {"carte": carte_lue}
        return render(request, "kiosk/partial/etape_solde_et_montant.html", context)

    @action(detail=False, methods=['POST'])
    def recapitulatif(self, request, *args, **kwargs):
        """
        POST /kiosk/recapitulatif/ — ecran 4 : ce que la personne ajoute, et son
        nouveau solde. Le calcul est fait ICI, pas dans le navigateur.
        / POST /kiosk/recapitulatif/ — screen 4: added amount and new balance,
        computed HERE, not in the browser.

        LOCALISATION : kiosk/views.py
        """
        if not la_recharge_est_active(request):
            return render(request, "kiosk/partial/borne_en_pause.html")

        validateur = RecapitulatifSerializer(data=request.data)
        if not validateur.is_valid():
            logger.error(f"recapitulatif : {validateur.errors}")
            context = {"error_message": premier_message_d_erreur(validateur.errors)}
            return render(request, "kiosk/partial/etape_erreur.html", context)

        carte_lue = validateur.carte_lue
        montant_en_centimes = validateur.validated_data["totalAmount"]

        context = {
            "carte": carte_lue,
            "montant_centimes": montant_en_centimes,
            # Renvoye tel quel au POST de paiement (valeur avec un point).
            # / Sent back as-is to the payment POST (dot decimal).
            "montant_pour_formulaire": f"{montant_en_centimes // 100}.{montant_en_centimes % 100:02d}",
            "nouveau_solde_centimes": carte_lue["solde_centimes"] + montant_en_centimes,
        }
        return render(request, "kiosk/partial/etape_recapitulatif.html", context)


    @action(detail=False, methods=['POST'])
    def refill_with_wisepos(self, request, *args, **kwargs):
        """
        POST /kiosk/refill_with_wisepos/ — lance la recharge sur le TPE Stripe
        et le suivi Celery/WebSocket du paiement.
        / POST /kiosk/refill_with_wisepos/ — starts the refill on the Stripe
        terminal and the Celery/WebSocket payment tracking.

        LOCALISATION : kiosk/views.py
        """
        # Garde serveur : aussi valable pour le bouton « Reessayer » de l'ecran
        # de refus, qui rejoue ce POST. / Server guard, also for the retry button.
        if not la_recharge_est_active(request):
            return render(request, "kiosk/partial/borne_en_pause.html")

        user = request.user

        # Garde : un TermUser Kiosque sans Terminal appaire ne doit pas faire un 500.
        # L'accessor inverse OneToOne leve RelatedObjectDoesNotExist (sous-classe
        # d'AttributeError) : getattr -> None.
        # / Guard: a Kiosk TermUser without a paired Terminal must not 500.
        # The reverse OneToOne accessor raises RelatedObjectDoesNotExist
        # (an AttributeError subclass): getattr -> None.
        terminal = getattr(user, "terminal", None)

        # En DEMO, l'admin (ou une borne sans TPE propre) utilise le TPE de
        # demonstration : le reader Stripe simule cree par la fixture demo_data_v2.
        # Hors DEMO, ce repli n'existe pas — seule la borne appairee a son TPE.
        # / In DEMO, the admin (or a device without its own reader) uses the demo
        # terminal (the simulated Stripe reader seeded by demo_data_v2). Outside
        # DEMO there is no fallback; only the paired device has its terminal.
        # Le repli DEMO ne prend qu'une borne QUI A UN LECTEUR : sans ce filtre, on
        # retomberait sur la premiere borne venue, sans TPE, et l'envoi echouerait plus loin
        # avec une erreur incomprehensible.
        # / The DEMO fallback only picks a device THAT HAS A READER.
        if terminal is None and settings.DEMO:
            terminal = (
                Terminal.objects.filter(
                    archived=False, tpe__isnull=False, tpe__active=True,
                )
                .order_by("name")
                .first()
            )

        if terminal is None:
            logger.error(f"refill_with_wisepos : aucun Terminal appaire au user {user}")
            context = {
                "user": user,
                "error_message": _("Aucun terminal de paiement n'est appairé à cette borne."),
            }
            return render(request, "kiosk/partial/etape_erreur.html", context)

        # La borne existe, mais aucun lecteur n'y est branche : on le dit clairement plutot
        # que de laisser l'envoi echouer avec une erreur Stripe cryptique.
        # / The kiosk exists but has no reader plugged in: say so clearly.
        lecteur_de_carte = getattr(terminal, "tpe", None)
        if lecteur_de_carte is None or not lecteur_de_carte.active:
            logger.error(f"refill_with_wisepos : aucun TPE actif sur la borne {terminal}")
            context = {
                "user": user,
                "error_message": _(
                    "Aucun lecteur de carte bancaire n'est branché sur cette borne."
                ),
            }
            return render(request, "kiosk/partial/etape_erreur.html", context)

        logger.info(f"request.data = {request.data}")
        validator = RefillWisePoseValidator(data=request.data)
        if not validator.is_valid():
            logger.error(f"ERROR VALIDATION : {validator.errors}")
            # HTMX ne swap pas les 4xx par defaut : on rend l'erreur en HTML (200)
            # dans le partial, sinon la borne ne montre rien a l'utilisateur.
            # / HTMX does not swap 4xx by default: render the error as HTML (200)
            # in the partial, otherwise the kiosk shows nothing to the user.
            context = {
                "user": user,
                "terminal": terminal,
                "error_message": premier_message_d_erreur(validator.errors),
            }
            return render(request, "kiosk/partial/etape_erreur.html", context)

        validated_data = validator.validated_data
        amount = validated_data['totalAmount']
        carte = validator.card

        # Creation de l'intention de paiement / Create the payment intent
        # Le solde avant recharge sert seulement a l'ecran de succes (rendu hors
        # requete, par le websocket). / Balance before refill: success screen only.
        payment_intent = PaymentsIntent.objects.create(
            terminal=terminal,
            amount=amount,
            card=carte,
            solde_avant_centimes=validator.carte_lue["solde_centimes"],
        )

        # Envoi de l'intention de paiement au terminal / Send the payment intent to the terminal
        try:
            payment_intent = payment_intent.send_to_terminal(terminal)
        except Exception as e:
            logger.error(f"refill_with_wisepos : send_to_terminal a echoue : {e}")
            # Le texte brut de l'erreur (Stripe, en anglais, avec des identifiants)
            # reste dans le journal. Le public lit un message simple et traduit.
            # / The raw error stays in the log; the public reads a plain message.
            context = {
                "card": carte,
                "terminal": terminal,
                "user": user,
                "error_message": _("Le terminal de paiement n'a pas répondu. Merci de réessayer ou de demander de l'aide au bar."),
            }
            return render(request, "kiosk/partial/etape_erreur.html", context)

        # Lancement de la tache Celery de suivi du statut.
        #
        # On n'attend PAS que la tache passe en STARTED : si tous les workers sont
        # occupes, elle reste PENDING quelques secondes, alors que le TPE demande
        # deja la carte. Attendre reviendrait a afficher « le suivi n'a pas pu
        # demarrer » pendant que le client paie.
        #
        # Le seul echec detectable ici est un broker injoignable : `.delay()` leve
        # alors immediatement. Tout le reste (worker mort, message perdu) est
        # rattrape par deux filets : le rejeu d'etat a la connexion du websocket
        # (TerminalConsumer.replay_payment_state_if_finished) et le sondage lent
        # `payment_status` du template d'attente.
        #
        # / We do NOT wait for the task to reach STARTED: with all workers busy it
        # stays PENDING while the reader already asks for the card. The only failure
        # detectable here is an unreachable broker: `.delay()` raises at once.
        # Everything else is caught by the websocket state replay and the slow
        # `payment_status` poll of the waiting template.
        logger.info(f"Started Celery task to poll payment intent status for ID: {payment_intent.pk}")
        try:
            poll_payment_intent_status.delay(payment_intent.pk)
        except OperationalError as erreur_broker:
            logger.error(f"refill_with_wisepos : broker Celery injoignable : {erreur_broker}")
            # CRITIQUE : send_to_terminal a DEJA arme le lecteur (l'invite de carte
            # est affichee). Sans suivi, on doit lacher le lecteur, sinon un client
            # qui tape sa carte serait debite en silence, ecran sur l'accueil.
            # / CRITICAL: send_to_terminal ALREADY armed the reader (card prompt is
            # up). With no tracking we must release it, else a customer tapping
            # their card would be charged silently while the screen shows home.
            payment_intent.annuler_sur_le_terminal()
            # HTMX ne swap pas les 5xx : on affiche un message d'erreur (200) plutot
            # qu'un ecran silencieux. / HTMX does not swap 5xx: show an error
            # message (200) instead of a silent screen.
            context = {
                "user": user,
                "terminal": terminal,
                "error_message": _("Le suivi du paiement n'a pas pu démarrer. Merci de contacter le personnel."),
            }
            return render(request, "kiosk/partial/etape_erreur.html", context)

        # Renvoie la partie websocket pour le suivi de l'intention de paiement
        # / Return the websocket part to track the payment intent
        return render(request, 'kiosk/waiting_credit_card_terminal.html', context={
            'user': user,
            'montant_centimes': amount,
            'terminal': terminal,
            'payment_intent': payment_intent,
        })

    @action(detail=True, methods=['GET'], url_path='status')
    def payment_status(self, request, pk):
        """
        GET /kiosk/{pk}/status/ — filet de secours du websocket.
        / GET /kiosk/{pk}/status/ — websocket safety net.

        LOCALISATION : kiosk/views.py

        Le template d'attente sonde cette route toutes les 10 secondes. Elle ne
        renvoie quelque chose QUE si le paiement est termine : l'ecran final
        (success/cancel) porte un hx-swap-oob qui remplace #tb-kiosque, ce qui
        emporte au passage le declencheur du sondage.

        Tant que le paiement est en cours : 204, et HTMX ne swappe rien.

        Pourquoi ce filet : c'est le SEUL recours si le worker Celery meurt apres
        son demarrage. La tache Celery est le seul code qui avance le statut en
        base ; si elle ne tourne plus, personne ne l'avance. Ce filet interroge
        donc Stripe LUI-MEME (get_from_stripe) tant que le statut local n'est pas
        termine — sinon il ne ferait que relire un statut fige et l'ecran
        resterait bloque sur le spinner, carte deja debitee.
        / This is the ONLY recourse if the Celery worker dies after starting. The
        task is the only code that advances the DB status; if it stops, nobody
        does. So this net queries Stripe ITSELF (get_from_stripe) while the local
        status is not final — otherwise it would just re-read a frozen status and
        the screen would stay stuck on the spinner with the card already charged.
        """
        payment_intent_db = get_object_or_404(PaymentsIntent, pk=pk)

        # Garde d'appartenance (voir utilisateur_peut_acceder_au_paiement).
        # / Ownership guard.
        if not utilisateur_peut_acceder_au_paiement(payment_intent_db, request.user):
            logger.error(f"payment_status : {request.user} n'est pas proprietaire du paiement {pk}")
            raise Http404

        # Statut local pas encore termine : on interroge Stripe directement.
        # C'est ce qui rend le filet independant du worker Celery. get_from_stripe
        # met a jour et sauve le statut en base.
        # / Local status not final yet: query Stripe directly. This makes the net
        # independent of the Celery worker. get_from_stripe updates and saves.
        statut_local_termine = payment_intent_db.status in (
            PaymentsIntent.SUCCEEDED,
            PaymentsIntent.CANCELED,
        )
        if not statut_local_termine:
            try:
                payment_intent_db.get_from_stripe()
            except Exception as erreur_stripe:
                # Stripe injoignable : on ne bloque pas, le prochain sondage reessaiera.
                # / Stripe unreachable: don't block, the next poll retries.
                logger.error(f"payment_status : get_from_stripe a echoue pour {pk} : {erreur_stripe}")

        # Meme contexte que l'evenement websocket (kiosk/tasks.py).
        # / Same context as the websocket event.
        context = {"event": payment_intent_db.contexte_ecran_final()}
        if payment_intent_db.status == PaymentsIntent.SUCCEEDED:
            return render(request, "kiosk/success.html", context)
        if payment_intent_db.status == PaymentsIntent.CANCELED:
            return render(request, "kiosk/cancel.html", context)

        # Paiement toujours en cours : 204, HTMX ne swappe rien.
        # / Still in progress: 204, HTMX swaps nothing.
        return HttpResponse(status=204)

    @action(detail=True, methods=['GET'])
    def cancel(self, request, pk):
        """
        GET /kiosk/{pk}/cancel/ — annule l'action en cours sur le TPE et le
        paiement Stripe correspondant.
        / GET /kiosk/{pk}/cancel/ — cancels the ongoing reader action and the
        matching Stripe payment.

        LOCALISATION : kiosk/views.py
        """
        payment_intent_db = get_object_or_404(PaymentsIntent, pk=pk)

        # Garde d'appartenance : cancel est destructif (il annule le paiement cote
        # Stripe). Sans cette garde, une borne pourrait annuler le paiement en cours
        # d'une AUTRE borne du meme tenant en devinant son pk (IDOR intra-tenant).
        # / Ownership guard: cancel is destructive. Without it a device could cancel
        # another device's in-flight payment in the same tenant (intra-tenant IDOR).
        if not utilisateur_peut_acceder_au_paiement(payment_intent_db, request.user):
            logger.error(f"cancel : {request.user} n'est pas proprietaire du paiement {pk}")
            raise Http404

        try:
            # Lache le lecteur et annule le PaymentIntent (best-effort, cf. modele).
            # / Release the reader and cancel the PaymentIntent (best-effort).
            statut_final = payment_intent_db.annuler_sur_le_terminal()
            logger.info(f"Cancel payment intent {payment_intent_db.pk} -> status : {statut_final}")

            # Le cancel est fait cote Stripe ; le OOB du websocket affichera la page
            # cancel. Le sondage payment_status prendra le relais si le WS est coupe.
            # / Cancel done on Stripe's side; the websocket OOB shows the cancel page.
            return HttpResponse(status=205)
        except Exception as e:
            logger.error(f"cancel : echec inattendu pour {pk} : {e}")
            return HttpResponseClientRedirect(reverse("kiosk-list"))

    # ------------------------------------------------------------------------
    # Configuration de la borne (equipe du lieu, carte primaire)
    # / Kiosk configuration (venue staff, primary card)
    # ------------------------------------------------------------------------

    @action(detail=False, methods=['POST'])
    def acces_admin(self, request, *args, **kwargs):
        """
        POST /kiosk/acces_admin/ — une carte a ete posee dans la modale admin.
        / POST /kiosk/acces_admin/ — a card was tapped in the admin modal.

        FLUX :
        1. main.js lit la carte (lecteur NFC) et poste son tag_id ici.
        2. Si c'est une carte primaire (laboutik.CartePrimaire), on ouvre la
           configuration pour cette session et on redirige (HX-Redirect).
        3. Sinon on renvoie l'etat « erreur » de la modale.

        LOCALISATION : kiosk/views.py
        """
        tag_id = str(request.data.get('tag_id') or '').strip().upper()

        # La carte primaire est celle des operateurs de caisse LaBoutik.
        # related_name 'carte_primaire' : cf. laboutik/models.py, CartePrimaire.
        # / Primary card = the LaBoutik operators' card.
        c_est_une_carte_primaire = False
        if tag_id:
            c_est_une_carte_primaire = CarteCashless.objects.filter(
                tag_id=tag_id,
                carte_primaire__isnull=False,
            ).exists()

        if not c_est_une_carte_primaire:
            logger.info(f"acces_admin : refus pour la carte {tag_id}")
            return render(request, "kiosk/partial/modale_admin_etat.html", {"etat": "erreur"})

        # On range l'heure d'ouverture : la configuration expire seule.
        # / Store the opening time: the configuration expires by itself.
        request.session[CLE_SESSION_ADMIN_BORNE] = time.time()
        return HttpResponseClientRedirect(reverse("kiosk-configuration"))

    @action(detail=False, methods=['GET'])
    def configuration(self, request, *args, **kwargs):
        """
        GET /kiosk/configuration/ — choix des services proposes par la borne.
        Refusee tant qu'une carte primaire n'a pas ete posee (acces_admin).
        / GET /kiosk/configuration/ — which services the kiosk offers.
        Refused until a primary card has been tapped.

        LOCALISATION : kiosk/views.py
        """
        if not la_configuration_est_ouverte(request):
            return HttpResponseRedirect(reverse("kiosk-list"))

        context = contexte_du_lieu(request)
        # Meme calcul que la grille rendue apres chaque interrupteur.
        # / Same computation as the grid rendered after each switch.
        context.update(contexte_des_modules(context["terminal"]))
        return render(request, "kiosk/configuration.html", context)

    @action(detail=False, methods=['POST'])
    def basculer_module(self, request, *args, **kwargs):
        """
        POST /kiosk/basculer_module/ — allume ou coupe la recharge.
        Renvoie la grille des modules, recalculee cote serveur.
        / POST /kiosk/basculer_module/ — turns the refill on or off.

        LOCALISATION : kiosk/views.py

        Le formulaire envoie l'etat VOULU (« activer » : true/false), pas un
        « inverse ». Un double clic ou un POST rejoue ne change donc pas le
        resultat. / The form sends the WANTED state, so a replay is harmless.
        """
        if not la_configuration_est_ouverte(request):
            return HttpResponseClientRedirect(reverse("kiosk-list"))

        terminal = getattr(request.user, "terminal", None)
        reglages = obtenir_reglages_de_la_borne(terminal)
        if reglages is None:
            return rendre_les_modules(
                request, terminal,
                message_erreur=_("Aucune borne n'est appairée : les réglages ne peuvent pas être enregistrés."),
            )

        # Seul module existant aujourd'hui : la recharge.
        # / Only module today: the refill.
        module_demande = request.data.get("module")
        etat_voulu = str(request.data.get("activer") or "").lower() == "true"
        if module_demande == "recharge":
            reglages.recharge_active = etat_voulu
            reglages.save(update_fields=["recharge_active"])

        return rendre_les_modules(request, terminal)

    @action(detail=False, methods=['POST'])
    def demarrer(self, request, *args, **kwargs):
        """
        POST /kiosk/demarrer/ — ferme la configuration et remet la borne au public.
        / POST /kiosk/demarrer/ — closes the configuration, back to the public.

        LOCALISATION : kiosk/views.py
        """
        if not la_configuration_est_ouverte(request):
            return HttpResponseClientRedirect(reverse("kiosk-list"))

        terminal = getattr(request.user, "terminal", None)
        reglages = obtenir_reglages_de_la_borne(terminal)
        aucun_service_actif = reglages is not None and not reglages.recharge_active
        if aucun_service_actif:
            return rendre_les_modules(
                request, terminal,
                message_erreur=_("Activez au moins un service avant de démarrer la borne."),
            )

        request.session.pop(CLE_SESSION_ADMIN_BORNE, None)
        return HttpResponseClientRedirect(reverse("kiosk-list"))
