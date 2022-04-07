sleep 2400h

#cd /DjangoFiles
daphne -b 0.0.0.0 -p 7999 --access-log /DjangoFiles/logs/daphne.logs TiBillet.asgi:application

