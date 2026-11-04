# booking

App Lespass pour les lieux qui partagent des ressources (salles,
matériel) et fonctionnent avec des bénévoles. Les membres réservent des
créneaux sur le calendrier des ressources ; les gestionnaires planifient
les créneaux bénévoles, et les bénévoles s'y inscrivent.

Spécification : `spec/` (processus Dev43, voir `DEV43.md`).

Lancer ses tests (dans le conteneur Docker) :

    docker exec lespass_django poetry run pytest booking/tests/
