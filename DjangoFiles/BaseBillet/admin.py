from django.contrib import admin

# Register your models here.

# créer un modèle d'administration pour le modèle Billet

# class BilletAdmin(admin.ModelAdmin):
#     list_display = ('titre', 'auteur', 'date')
#     list_filter = ('date',)
#     date_hierarchy = 'date'
#     ordering = ('-date',)
#     search_fields = ('titre', 'contenu')