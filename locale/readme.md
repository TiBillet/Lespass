https://docs.djangoproject.com/fr/5.0/topics/i18n/translation/#message-files

```bash
# Ajoute les nouvelles string a traduire
django-admin makemessages -l fr
django-admin makemessages -l en
# Fabrique le fichier de compilation
django-admin compilemessages
```