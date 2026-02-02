import argparse
import json
import os
from datetime import timedelta
from types import SimpleNamespace

import django
from django.http import QueryDict
from django.utils import timezone


# This script helps create data for E2E tests.
# Ce script aide a creer des donnees pour les tests E2E.


def _get_tenant_context(schema_name: str):
    from django_tenants.utils import get_tenant_model, tenant_context

    tenant_model = get_tenant_model()
    tenant_obj = tenant_model.objects.get(schema_name=schema_name)
    return tenant_context(tenant_obj)


def create_reservation(payload: dict, tenant: str):
    from django.contrib.auth.models import AnonymousUser
    from BaseBillet.models import Event, Product, Price
    from BaseBillet.validators import ReservationValidator

    event_name = payload["event"]
    product_name = payload["product"]
    price_name = payload.get("price")
    email = payload["email"]
    qty = int(payload.get("qty") or 1)
    custom_amount = payload.get("custom_amount")

    with _get_tenant_context(tenant):
        event = Event.objects.filter(name__icontains=event_name).order_by("-datetime").first()
        if not event:
            return {"status": "error", "message": f"Event not found: {event_name}"}

        product = Product.objects.filter(name__icontains=product_name).order_by("-pk").first()
        if not product:
            return {"status": "error", "message": f"Product not found: {product_name}"}

        if price_name:
            price = product.prices.filter(name__icontains=price_name).order_by("order").first()
        else:
            price = product.prices.order_by("order").first()

        if not price:
            return {"status": "error", "message": f"Price not found for product: {product_name}"}

        data = QueryDict(mutable=True)
        data.update({
            "email": email,
            "event": str(event.pk),
            str(price.uuid): str(qty),
        })

        if custom_amount is not None:
            data.update({f"custom_amount_{price.uuid}": str(custom_amount)})

        fake_request = SimpleNamespace(user=AnonymousUser(), data=data)

        validator = ReservationValidator(data=data, context={"request": fake_request})
        if not validator.is_valid():
            return {"status": "error", "message": validator.errors}

        reservation = getattr(validator, "reservation", None)
        tickets = getattr(validator, "tickets", None)

        return {
            "status": "success",
            "reservation_uuid": str(reservation.uuid) if reservation else None,
            "tickets_count": len(tickets.tickets) if tickets and hasattr(tickets, "tickets") else None,
        }


def create_membership(payload: dict, tenant: str):
    from BaseBillet.models import Membership, Price, Product
    from AuthBillet.utils import get_or_create_user

    product_name = payload["product"]
    price_name = payload.get("price")
    email = payload["email"]
    deadline_days = int(payload.get("deadline_days") or 30)
    status = payload.get("status") or Membership.ONCE
    stripe_subscription_id = payload.get("stripe_subscription_id")

    with _get_tenant_context(tenant):
        product = Product.objects.filter(name__icontains=product_name).order_by("-pk").first()
        if not product:
            return {"status": "error", "message": f"Product not found: {product_name}"}

        if price_name:
            price = product.prices.filter(name__icontains=price_name).order_by("order").first()
        else:
            price = product.prices.order_by("order").first()

        if not price:
            return {"status": "error", "message": f"Price not found for product: {product_name}"}

        user = get_or_create_user(email)

        deadline = timezone.now() + timedelta(days=deadline_days)

        membership = Membership.objects.create(
            user=user,
            price=price,
            status=status,
            contribution_value=price.prix,
            last_contribution=timezone.now(),
            deadline=deadline,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        if stripe_subscription_id:
            membership.stripe_id_subscription = stripe_subscription_id
            membership.save(update_fields=["stripe_id_subscription"])

        return {
            "status": "success",
            "membership_uuid": str(membership.uuid),
            "deadline": membership.deadline.isoformat() if membership.deadline else None,
        }


def create_promotional_code(payload: dict, tenant: str):
    from BaseBillet.models import Product, PromotionalCode

    product_name = payload["product"]
    code_name = payload["code_name"]
    discount_rate = payload.get("discount_rate") or 10

    with _get_tenant_context(tenant):
        product = Product.objects.filter(name__icontains=product_name).order_by("-pk").first()
        if not product:
            return {"status": "error", "message": f"Product not found: {product_name}"}

        promo, created = PromotionalCode.objects.get_or_create(
            name=code_name,
            defaults={
                "discount_rate": discount_rate,
                "product": product,
                "is_active": True,
            },
        )

        if not created:
            promo.product = product
            promo.discount_rate = discount_rate
            promo.is_active = True
            promo.save()

        return {"status": "success", "code_uuid": str(promo.uuid)}


def create_ticket(payload: dict, tenant: str):
    from BaseBillet.models import Event, Product, Ticket, Reservation, Price
    from AuthBillet.utils import get_or_create_user
    from ApiBillet.serializers import get_or_create_price_sold

    event_name = payload["event"]
    product_name = payload["product"]
    price_name = payload.get("price")
    email = payload["email"]
    qty = int(payload.get("qty") or 1)

    with _get_tenant_context(tenant):
        event = Event.objects.filter(name__icontains=event_name).order_by("-datetime").first()
        if not event:
            return {"status": "error", "message": f"Event not found: {event_name}"}

        product = Product.objects.filter(name__icontains=product_name).order_by("-pk").first()
        if not product:
            return {"status": "error", "message": f"Product not found: {product_name}"}

        if price_name:
            price = product.prices.filter(name__icontains=price_name).order_by("order").first()
        else:
            price = product.prices.order_by("order").first()

        if not price:
            return {"status": "error", "message": f"Price not found for product: {product_name}"}

        user = get_or_create_user(email)

        reservation = Reservation.objects.create(
            user_commande=user,
            event=event,
            status=Reservation.VALID,
        )

        pricesold = get_or_create_price_sold(price=price, event=event)

        tickets = []
        for _ in range(qty):
            ticket = Ticket.objects.create(
                reservation=reservation,
                pricesold=pricesold,
                status=Ticket.NOT_SCANNED,
            )
            tickets.append(ticket)

        return {
            "status": "success",
            "reservation_uuid": str(reservation.uuid),
            "tickets_count": len(tickets),
        }


def link_price_to_membership(payload: dict, tenant: str):
    from BaseBillet.models import Product, Price

    price_product_name = payload["product"]
    membership_product_name = payload["membership_product"]
    price_name = payload.get("price")

    with _get_tenant_context(tenant):
        product = Product.objects.filter(name__icontains=price_product_name).order_by("-pk").first()
        if not product:
            return {"status": "error", "message": f"Product not found: {price_product_name}"}

        membership_product = Product.objects.filter(name__icontains=membership_product_name).order_by("-pk").first()
        if not membership_product:
            return {"status": "error", "message": f"Membership product not found: {membership_product_name}"}

        if price_name:
            price = product.prices.filter(name__icontains=price_name).order_by("order").first()
        else:
            price = product.prices.order_by("order").first()

        if not price:
            return {"status": "error", "message": f"Price not found for product: {price_product_name}"}

        price.adhesion_obligatoire = membership_product
        price.save(update_fields=["adhesion_obligatoire"])

        return {"status": "success", "price_uuid": str(price.uuid)}


def set_product_max_per_user(payload: dict, tenant: str):
    from BaseBillet.models import Product

    product_name = payload["product"]
    max_per_user = int(payload.get("max_per_user") or 1)

    with _get_tenant_context(tenant):
        product = Product.objects.filter(name__icontains=product_name).order_by("-pk").first()
        if not product:
            return {"status": "error", "message": f"Product not found: {product_name}"}

        product.max_per_user = max_per_user
        product.save(update_fields=["max_per_user"])

        return {"status": "success", "product_uuid": str(product.uuid)}


def set_price_recurring(payload: dict, tenant: str):
    from BaseBillet.models import Product

    product_name = payload["product"]
    price_name = payload.get("price")
    subscription_type = payload.get("subscription_type") or "M"
    recurring_payment = payload.get("recurring_payment") or "1"
    recurring_payment = str(recurring_payment) == "1"

    with _get_tenant_context(tenant):
        product = Product.objects.filter(name__icontains=product_name).order_by("-pk").first()
        if not product:
            return {"status": "error", "message": f"Product not found: {product_name}"}

        if price_name:
            price = product.prices.filter(name__icontains=price_name).order_by("order").first()
        else:
            price = product.prices.order_by("order").first()

        if not price:
            return {"status": "error", "message": f"Price not found for product: {product_name}"}

        price.recurring_payment = recurring_payment
        price.subscription_type = subscription_type
        price.save(update_fields=["recurring_payment", "subscription_type"])

        return {"status": "success", "price_uuid": str(price.uuid)}


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Setup test data for E2E tests",
    )
    parser.add_argument("--action", type=str, required=True, choices=[
        "create_reservation",
        "create_ticket",
        "create_membership",
        "create_promotional_code",
        "link_price_to_membership",
        "set_product_max_per_user",
        "set_price_recurring",
    ])
    parser.add_argument("--event", type=str, required=False, help="Event name")
    parser.add_argument("--product", type=str, required=False, help="Product name")
    parser.add_argument("--price", type=str, required=False, help="Price name")
    parser.add_argument("--email", type=str, required=False, help="User email")
    parser.add_argument("--qty", type=str, required=False, help="Quantity")
    parser.add_argument("--custom-amount", type=str, required=False, help="Custom amount for free price")
    parser.add_argument("--deadline-days", type=str, required=False, help="Membership deadline days (can be negative)")
    parser.add_argument("--status", type=str, required=False, help="Membership status code")
    parser.add_argument("--stripe-subscription-id", type=str, required=False, help="Stripe subscription id")
    parser.add_argument("--code-name", type=str, required=False, help="Promotional code name")
    parser.add_argument("--discount-rate", type=str, required=False, help="Promotional code discount rate")
    parser.add_argument("--membership-product", type=str, required=False, help="Membership product name")
    parser.add_argument("--max-per-user", type=str, required=False, help="Product max per user")
    parser.add_argument("--subscription-type", type=str, required=False, help="Price subscription type")
    parser.add_argument("--recurring-payment", type=str, required=False, help="Price recurring payment (1 or 0)")
    parser.add_argument("--tenant", type=str, default="lespass", help="Tenant schema")
    return parser.parse_args()


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "TiBillet.settings")
    django.setup()

    args = _parse_args()
    payload = {
        "event": args.event,
        "product": args.product,
        "price": args.price,
        "email": args.email,
        "qty": args.qty,
        "custom_amount": args.custom_amount,
        "deadline_days": args.deadline_days,
        "status": args.status,
        "stripe_subscription_id": args.stripe_subscription_id,
        "code_name": args.code_name,
        "discount_rate": args.discount_rate,
        "membership_product": args.membership_product,
        "max_per_user": args.max_per_user,
        "subscription_type": args.subscription_type,
        "recurring_payment": args.recurring_payment,
    }

    if args.action == "create_reservation":
        result = create_reservation(payload, args.tenant)
    elif args.action == "create_ticket":
        result = create_ticket(payload, args.tenant)
    elif args.action == "create_membership":
        result = create_membership(payload, args.tenant)
    elif args.action == "create_promotional_code":
        result = create_promotional_code(payload, args.tenant)
    elif args.action == "link_price_to_membership":
        result = link_price_to_membership(payload, args.tenant)
    elif args.action == "set_product_max_per_user":
        result = set_product_max_per_user(payload, args.tenant)
    elif args.action == "set_price_recurring":
        result = set_price_recurring(payload, args.tenant)
    else:
        result = {"status": "error", "message": "Unknown action"}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
