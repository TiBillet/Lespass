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

import stripe
from django.conf import settings
from django.db import connection
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
# Levee par Celery quand le broker (Redis) est injoignable.
# / Raised by Celery when the broker (Redis) is unreachable.
from kombu.exceptions import OperationalError
from django.utils.translation import gettext_lazy as _
from django_htmx.http import HttpResponseClientRedirect
from rest_framework import permissions, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action

from AuthBillet.models import TibilletUser
from fedow_connect.fedow_api import FedowAPI
from kiosk.models import PaymentsIntent
from kiosk.tasks import poll_payment_intent_status
from kiosk.validators import RefillWisePoseValidator
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
        # Admin du tenant courant (acces navigateur pour demo / debug).
        # / Current tenant admin (browser access for demo / debug).
        return user.is_tenant_admin(connection.tenant)


class KioskViewSet(viewsets.ViewSet):
    """
    Parcours de recharge en libre-service (borne kiosque + TPE Stripe).
    / Self-service refill flow (kiosk terminal + Stripe card reader).
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsKioskTerminal]

    def list(self, request):
        """
        GET /kiosk/ — page d'accueil : choix du montant.
        / GET /kiosk/ — home page: amount selection.
        """
        # type_app arrive une seule fois via le bridge (/kiosk/?type_app=cordova).
        # Les retours accueil (success/cancel -> window.location = "/kiosk/") perdent
        # le query param : on le memorise en session pour reinjecter cordova.js.
        # / type_app arrives once via the bridge redirect. Home returns
        # (success/cancel -> window.location = "/kiosk/") lose the query param:
        # keep it in session so cordova.js is still injected.
        type_app = request.GET.get("type_app")
        if type_app:
            request.session["type_app"] = type_app
        else:
            type_app = request.session.get("type_app", "unknown")

        context = {
            "test": settings.TEST,
            "demo": settings.DEMO,
            # Toutes les cartes du simulateur NFC (base.html/nfc.js les attendent toutes).
            # / All the NFC simulator cards (base.html/nfc.js expect them all).
            "demoTagIdCm": settings.DEMO_TAGID_CM,
            "demoTagIdClient1": settings.DEMO_TAGID_CLIENT1,
            "demoTagIdClient2": settings.DEMO_TAGID_CLIENT2,
            "demoTagIdClient3": settings.DEMO_TAGID_CLIENT3,
            # base.html s'en sert pour injecter cordova.js (plugin NFC de la borne
            # Android). / base.html uses it to inject cordova.js (Android NFC plugin).
            "type_app": type_app,
        }
        return render(request, "kiosk/select_amount.html", context)

    @action(detail=False, methods=['POST'])
    def check_request_card(self, request, *args, **kwargs):
        """
        POST /kiosk/check_request_card/ — verifie qu'une carte NFC existe
        (cote Fedow puis en base locale) avant de proposer la recharge.
        Reponse HTML (partial) : HTMX ne swap pas les 4xx/5xx par defaut,
        donc les erreurs metier sont rendues en 200 avec un message.
        / POST /kiosk/check_request_card/ — checks an NFC card exists (on
        Fedow, then locally) before offering the refill. HTML (partial)
        response: HTMX does not swap 4xx/5xx by default, so business errors
        are rendered as 200 with a message.
        """
        # L'accessor inverse OneToOne leve RelatedObjectDoesNotExist (sous-classe
        # d'AttributeError) si aucun Terminal n'est appaire : getattr -> None.
        # / The reverse OneToOne accessor raises RelatedObjectDoesNotExist
        # (an AttributeError subclass) when no Terminal is paired: getattr -> None.
        terminal = getattr(request.user, "terminal", None)

        # str() : request.data peut venir d'un POST JSON (valeur non-string).
        # / str(): request.data can come from a JSON POST (non-string value).
        tag_id = str(request.data.get('tag_id') or '').strip().upper()
        logger.info(f"--> tag_id = {tag_id}")
        if not tag_id:
            context = {
                "terminal": terminal,
                "user": request.user,
                "error_message": _("Aucune carte reçue. Merci de scanner à nouveau."),
            }
            return render(request, "kiosk/select_amount_content.html", context)

        try:
            FedowAPI().NFCcard.retrieve(tag_id)
            carte = CarteCashless.objects.get(tag_id=tag_id)
        except CarteCashless.DoesNotExist:
            context = {
                "terminal": terminal,
                "user": request.user,
                "error_message": _("Carte inconnue : %(tag_id)s") % {"tag_id": tag_id},
            }
            return render(request, "kiosk/select_amount_content.html", context)
        except Exception as e:
            logger.error(f"check_request_card : erreur Fedow pour {tag_id} : {e}")
            context = {
                "terminal": terminal,
                "user": request.user,
                "error_message": f"{e}",
            }
            return render(request, "kiosk/select_amount_content.html", context)

        context = {
            "card": carte,
            "terminal": terminal,
            "user": request.user,
        }
        return render(request, "kiosk/select_amount_content.html", context)

    @action(detail=False, methods=['POST'])
    def refill_with_wisepos(self, request, *args, **kwargs):
        """
        POST /kiosk/refill_with_wisepos/ — lance la recharge sur le TPE Stripe
        et le suivi Celery/WebSocket du paiement.
        / POST /kiosk/refill_with_wisepos/ — starts the refill on the Stripe
        terminal and the Celery/WebSocket payment tracking.
        """
        user = request.user

        # Garde : un TermUser Kiosque sans Terminal appaire ne doit pas faire un 500.
        # L'accessor inverse OneToOne leve RelatedObjectDoesNotExist (sous-classe
        # d'AttributeError) : getattr -> None.
        # / Guard: a Kiosk TermUser without a paired Terminal must not 500.
        # The reverse OneToOne accessor raises RelatedObjectDoesNotExist
        # (an AttributeError subclass): getattr -> None.
        terminal = getattr(user, "terminal", None)
        if terminal is None:
            logger.error(f"refill_with_wisepos : aucun Terminal appaire au user {user}")
            context = {
                "user": user,
                "error_message": _("Aucun terminal de paiement n'est appairé à cette borne."),
            }
            return render(request, "kiosk/select_amount_content.html", context)

        logger.info(f"request.data = {request.data}")
        validator = RefillWisePoseValidator(data=request.data)
        if not validator.is_valid():
            logger.error(f"ERROR VALIDATION : {validator.errors}")
            # HTMX ne swap pas les 4xx par defaut : on rend l'erreur en HTML (200)
            # dans le partial, sinon la borne ne montre rien a l'utilisateur.
            # / HTMX does not swap 4xx by default: render the error as HTML (200)
            # in the partial, otherwise the kiosk shows nothing to the user.
            premiere_liste_erreurs = next(iter(validator.errors.values()))
            context = {
                "user": user,
                "terminal": terminal,
                "error_message": premiere_liste_erreurs[0],
            }
            return render(request, "kiosk/select_amount_content.html", context)

        validated_data = validator.validated_data
        amount = validated_data['totalAmount']
        carte = validator.card

        # Creation de l'intention de paiement / Create the payment intent
        payment_intent = PaymentsIntent.objects.create(
            terminal=terminal,
            amount=amount,
            card=carte,
        )

        # Envoi de l'intention de paiement au terminal / Send the payment intent to the terminal
        try:
            payment_intent = payment_intent.send_to_terminal(terminal)
        except Exception as e:
            logger.error(f"refill_with_wisepos : send_to_terminal a echoue : {e}")
            # Partial (pas la page complete) : la reponse est swappee par HTMX
            # dans #tb-kiosque (innerHTML). / Partial (not the full page): the
            # response is swapped by HTMX into #tb-kiosque (innerHTML).
            context = {
                "card": carte,
                "terminal": terminal,
                "user": user,
                "error_message": f"{e}",
            }
            return render(request, "kiosk/select_amount_content.html", context)

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
            # HTMX ne swap pas les 5xx : on affiche un message d'erreur (200) plutot
            # qu'un ecran silencieux. / HTMX does not swap 5xx: show an error
            # message (200) instead of a silent screen.
            context = {
                "user": user,
                "terminal": terminal,
                "error_message": _("Le suivi du paiement n'a pas pu démarrer. Merci de contacter le personnel."),
            }
            return render(request, "kiosk/select_amount_content.html", context)

        # Renvoie la partie websocket pour le suivi de l'intention de paiement
        # / Return the websocket part to track the payment intent
        return render(request, 'kiosk/waiting_credit_card_terminal.html', context={
            'user': user,
            'amount': (amount / 100),
            'terminal': terminal,
            'payment_intent': payment_intent,
        })

    @action(detail=True, methods=['GET'], url_path='status')
    def payment_status(self, request, pk):
        """
        GET /kiosk/{pk}/status/ — filet de secours du websocket.
        / GET /kiosk/{pk}/status/ — websocket safety net.

        Le template d'attente sonde cette route toutes les 10 secondes. Elle ne
        renvoie quelque chose QUE si le paiement est termine : l'ecran final
        (success/cancel) porte un hx-swap-oob qui remplace #tb-kiosque, ce qui
        emporte au passage le declencheur du sondage.

        Tant que le paiement est en cours : 204, et HTMX ne swappe rien.

        Pourquoi ce filet : le websocket ne couvre pas la mort du worker Celery
        apres son demarrage. Le rejeu d'etat du consumer ne joue qu'a la
        (re)connexion ; si la borne reste connectee et que plus personne ne pousse,
        l'ecran resterait sur le spinner.

        / The waiting template polls this route every 10s. It answers only when the
        payment is finished: the final screen carries an hx-swap-oob replacing
        #tb-kiosque, which removes the poll trigger. While in progress: 204.
        """
        payment_intent_db = get_object_or_404(PaymentsIntent, pk=pk)

        # Meme garde que le websocket : ce paiement appartient-il a cette borne ?
        # L'admin du tenant est tolere (acces navigateur pour demo/debug, cf.
        # IsKioskTerminal).
        # / Same guard as the websocket: does this payment belong to this device?
        # The tenant admin is tolerated (browser access for demo/debug).
        user = request.user
        est_la_borne_proprietaire = (payment_intent_db.terminal.term_user_id == user.id)
        est_admin_du_tenant = user.is_tenant_admin(connection.tenant)
        if not est_la_borne_proprietaire and not est_admin_du_tenant:
            logger.error(f"payment_status : {user} n'est pas proprietaire du paiement {pk}")
            raise Http404

        if payment_intent_db.status == PaymentsIntent.SUCCEEDED:
            return render(request, "kiosk/success.html")
        if payment_intent_db.status == PaymentsIntent.CANCELED:
            return render(request, "kiosk/cancel.html")

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
        """
        try:
            payment_intent_db = get_object_or_404(PaymentsIntent, pk=pk)

            from root_billet.models import RootConfiguration
            stripe.api_key = RootConfiguration.get_solo().get_stripe_api()

            terminal = payment_intent_db.terminal
            stripe.terminal.Reader.cancel_action(terminal.stripe_id)
            logger.info(f"Cancel action on terminal {terminal.stripe_id}")

            stripe.PaymentIntent.cancel(payment_intent_db.payment_intent_stripe_id)
            payment_intent_db.refresh_from_db()
            logger.info(f"Cancel payment intent {payment_intent_db.pk} -> status : {payment_intent_db.status}")

            # Le cancel a ete fait cote stripe, le OOB du websocket va afficher la page cancel
            # / Cancel done on Stripe's side, the websocket OOB will show the cancel page
            return HttpResponse(status=205)
        except stripe._error.InvalidRequestError:
            return HttpResponseClientRedirect('/kiosk/')
        except Exception as e:
            logger.error(e)
            return HttpResponseClientRedirect('/kiosk/')
