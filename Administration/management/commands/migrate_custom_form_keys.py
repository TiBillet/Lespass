import json
from collections import defaultdict, Counter
from typing import Dict, Iterable, List, Optional, Tuple

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Prefetch
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import tenant_context

from BaseBillet.models import Membership, Reservation, ProductFormField, Ticket, Product
from Customers.models import Client


def label_key_for_field(ff: ProductFormField) -> str:
    label = (ff.label or '').strip()
    return label or ff.name


def build_name_to_label_map_for_products(products: Iterable[Product]) -> Dict[str, List[str]]:
    """
    Build a map: field_name -> list of label_keys found across provided products.
    If the same name appears in multiple products, we keep all encountered label_keys
    so the caller can detect conflicts (different labels for the same name).
    """
    name_to_labels: Dict[str, List[str]] = defaultdict(list)
    if not products:
        return name_to_labels

    # Query once for all products
    q = ProductFormField.objects.filter(product__in=list(products))
    for ff in q:
        lk = label_key_for_field(ff)
        lst = name_to_labels[ff.name]
        if lk not in lst:
            lst.append(lk)
    return name_to_labels


class Command(BaseCommand):
    help = (
        "Migrate custom_form keys from ProductFormField.name to ProductFormField.label (fallback to name).\n"
        "- Scans Membership.custom_form and Reservation.custom_form.\n"
        "- For each key that matches a ProductFormField.name, replaces it by the field label (or name if label empty).\n"
        "- Skips changes when the target label would collide with an existing key holding a different value, and reports it.\n"
        "Run dry by default. Use --commit to apply changes."
    )

    def add_arguments(self, parser):
        parser.add_argument('--commit', action='store_true', help='Apply changes to the database. Without this flag, runs in dry-run mode.')
        parser.add_argument('--batch-size', type=int, default=500, help='Batch size for queryset iteration.')
        parser.add_argument('--only', choices=['membership', 'reservation'], help='Limit to one model.')

    def handle(self, *args, **options):
        for client in Client.objects.exclude(categorie=Client.ROOT):
            with tenant_context(client):
                commit: bool = options['commit']
                batch_size: int = options['batch_size']
                only: Optional[str] = options.get('only')

                totals = Counter()
                membership_stats = self.migrate_memberships(commit, batch_size) if (only in [None, 'membership']) else Counter()
                reservation_stats = self.migrate_reservations(commit, batch_size) if (only in [None, 'reservation']) else Counter()

                totals.update(membership_stats)
                totals.update(reservation_stats)

                self.stdout.write(self.style.MIGRATE_HEADING("Migration summary"))
                for k, v in totals.items():
                    self.stdout.write(f"- {k}: {v}")

                if not commit:
                    self.stdout.write(self.style.WARNING("Dry-run finished. Re-run with --commit to apply changes."))
                else:
                    self.stdout.write(self.style.SUCCESS("Migration applied."))

    # --- Memberships ---
    def migrate_memberships(self, commit: bool, batch_size: int) -> Counter:
        stats = Counter()
        qs = (
            Membership.objects
            .exclude(custom_form=None)
            .exclude(custom_form={})
            .select_related('price__product')
        )

        self.stdout.write(self.style.HTTP_INFO("Scanning Memberships..."))
        for m in qs.iterator(chunk_size=batch_size):
            product = getattr(getattr(m, 'price', None), 'product', None)
            products = [product] if product else []
            name_to_labels = build_name_to_label_map_for_products(products)

            changed, new_custom_form, change_detail = self._remap_keys(m.custom_form, name_to_labels)
            if not changed:
                stats['memberships_unchanged'] += 1
                continue

            stats['memberships_changed'] += 1
            stats['memberships_keys_renamed'] += change_detail['renamed']
            stats['memberships_collisions'] += change_detail['collisions']
            stats['memberships_missing_fields'] += change_detail['missing']

            if commit:
                with transaction.atomic():
                    m.custom_form = new_custom_form
                    m.save(update_fields=['custom_form'])
        return stats

    # --- Reservations ---
    def migrate_reservations(self, commit: bool, batch_size: int) -> Counter:
        stats = Counter()
        qs = (
            Reservation.objects
            .exclude(custom_form=None)
            .exclude(custom_form={})
            .prefetch_related(
                Prefetch('tickets', queryset=Ticket.objects.select_related('pricesold__price__product'))
            )
            .select_related('event')
        )

        self.stdout.write(self.style.HTTP_INFO("Scanning Reservations..."))
        for r in qs.iterator(chunk_size=batch_size):
            products = self._collect_products_for_reservation(r)
            name_to_labels = build_name_to_label_map_for_products(products)

            changed, new_custom_form, change_detail = self._remap_keys(r.custom_form, name_to_labels)
            if not changed:
                stats['reservations_unchanged'] += 1
                continue

            stats['reservations_changed'] += 1
            stats['reservations_keys_renamed'] += change_detail['renamed']
            stats['reservations_collisions'] += change_detail['collisions']
            stats['reservations_missing_fields'] += change_detail['missing']

            if commit:
                with transaction.atomic():
                    r.custom_form = new_custom_form
                    r.save(update_fields=['custom_form'])
        return stats

    # --- Helpers ---
    @staticmethod
    def _collect_products_for_reservation(reservation: Reservation) -> List[Product]:
        products: List[Product] = []
        try:
            # Prefer products from tickets
            tks = list(getattr(reservation, 'tickets').all())
            for t in tks:
                price = getattr(getattr(t, 'pricesold', None), 'price', None)
                prod = getattr(price, 'product', None)
                if prod is not None:
                    products.append(prod)
            if products:
                # Deduplicate while keeping order
                seen = set()
                uniq = []
                for p in products:
                    if p.pk not in seen:
                        uniq.append(p)
                        seen.add(p.pk)
                products = uniq
            # Fallback to event products if no tickets
            if not products and getattr(reservation, 'event', None) is not None:
                try:
                    products = list(reservation.event.products.all())
                except Exception:
                    products = []
        except Exception:
            products = []
        return products

    def _remap_keys(self, custom_form: dict, name_to_labels: Dict[str, List[str]]) -> Tuple[bool, dict, Dict[str, int]]:
        """
        Return (changed?, new_custom_form, details)
        - For each key that matches a field name in name_to_labels:
            * If a single label exists -> rename to that label (if different).
            * If multiple labels but identical -> rename to that label.
            * If multiple conflicting labels -> skip and count as 'missing' (ambiguous mapping).
        - Avoid overwriting an existing different value at target label; count as 'collisions'.
        """
        if not isinstance(custom_form, dict):
            return False, custom_form, {'renamed': 0, 'collisions': 0, 'missing': 0}

        new_cf = dict(custom_form)  # shallow copy fine (values unchanged)
        renamed = 0
        collisions = 0
        missing = 0
        changed = False

        for key, value in list(custom_form.items()):
            labels = name_to_labels.get(key)
            if not labels:
                # no mapping for this key (either already a label or obsolete field name)
                continue
            # Resolve target label
            target_label = labels[0]
            if len(labels) > 1:
                # conflict only if distinct labels
                distinct = list({lbl for lbl in labels})
                if len(distinct) > 1:
                    # ambiguous; skip
                    missing += 1
                    continue
                target_label = distinct[0]

            if target_label == key:
                # already correct
                continue

            # Check collision at target key
            if target_label in new_cf and new_cf[target_label] != value:
                collisions += 1
                continue

            # Move key
            new_cf[target_label] = new_cf.pop(key)
            renamed += 1
            changed = True

        return changed, new_cf, {'renamed': renamed, 'collisions': collisions, 'missing': missing}
