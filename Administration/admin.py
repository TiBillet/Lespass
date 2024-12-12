# admin.py
from django.contrib import admin
from unfold.admin import ModelAdmin
from BaseBillet.models import Webhook

@admin.register(Webhook)
class WebhookAdmin(ModelAdmin):
    readonly_fields = ['last_response', ]
    fields = [
        "url",
        "active",
        "event",
        "last_response",
    ]

    list_display = [
        "url",
        "active",
        "event",
        "last_response",
    ]
