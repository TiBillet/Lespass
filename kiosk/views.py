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
from kiosk.models import PaymentsIntent, Terminal
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

        # En DEMO, l'admin (ou une borne sans TPE propre) utilise le TPE de
        # demonstration : le reader Stripe simule cree par la fixture demo_data_v2.
        # Hors DEMO, ce repli n'existe pas — seule la borne appairee a son TPE.
        # / In DEMO, the admin (or a device without its own reader) uses the demo
        # terminal (the simulated Stripe reader seeded by demo_data_v2). Outside
        # DEMO there is no fallback; only the paired device has its terminal.
        if terminal is None and settings.DEMO:
            terminal = Terminal.objects.filter(archived=False).order_by("name").first()

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
            return HttpResponseClientRedirect('/kiosk/')
