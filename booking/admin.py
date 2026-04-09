"""
Enregistrements de l'administration Django pour le module booking.
/ Django admin registrations for the booking module.

LOCALISATION : booking/admin.py
"""
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from Administration.admin.site import staff_admin_site
from booking.models import (
    Booking,
    Calendar,
    ClosedPeriod,
    OpeningEntry,
    Resource,
    ResourceGroup,
    WeeklyOpening,
)


class ClosedPeriodInline(TabularInline):
    model = ClosedPeriod
    extra = 0


class OpeningEntryInline(TabularInline):
    model = OpeningEntry
    extra = 0


@admin.register(Calendar, site=staff_admin_site)
class CalendarAdmin(ModelAdmin):
    inlines = [ClosedPeriodInline]


@admin.register(WeeklyOpening, site=staff_admin_site)
class WeeklyOpeningAdmin(ModelAdmin):
    inlines = [OpeningEntryInline]


@admin.register(Booking, site=staff_admin_site)
class BookingAdmin(ModelAdmin):
    list_filter = ['status', 'start_datetime']


class ResourceInline(TabularInline):
    model = Resource
    extra = 0
    fields = ['name', 'capacity', 'weekly_opening', 'calendar']


@admin.register(ResourceGroup, site=staff_admin_site)
class ResourceGroupAdmin(ModelAdmin):
    inlines = [ResourceInline]
    exclude = ['tags']  # provisoire — voir booking/doc/tibillet-booking-decisions.md §4


@admin.register(Resource, site=staff_admin_site)
class ResourceAdmin(ModelAdmin):
    list_display = ['name', 'group', 'capacity', 'weekly_opening', 'calendar']
    exclude = ['tags']  # provisoire — voir booking/doc/tibillet-booking-decisions.md §4
