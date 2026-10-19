### Tâche 1 : les six champs de date et leur migration

**Fichiers :**
- Modifier : `BaseBillet/models.py` (`Reservation`, `Event`, `Membership`, `Configuration`)
- Modifier : `booking/models.py` (`Booking`)
- Créer : `BaseBillet/migrations/0235_recap_quotidien_dates.py`, `booking/migrations/0006_booking_annulee_le.py` (générées)
- Test : `tests/pytest/test_recap_quotidien.py` (classe `TestLesDatesDeCreation`)

**Interfaces — produit :**
- `Reservation.created_at = DateTimeField(auto_now_add=True, null=True, verbose_name=_("Créée le"))`
- `Event.created_at = DateTimeField(auto_now_add=True, null=True, verbose_name=_("Créé le"))` — `Event.created` (auto_now) reste tel quel.
- `Reservation.annulee_le`, `Membership.annulee_le`, `Booking.annulee_le` =
  `DateTimeField(null=True, blank=True, editable=False, verbose_name=_("Annulée le"))`
- `Configuration.recap_quotidien_traite_le = DateField(null=True, blank=True, editable=False, verbose_name=_("Récap du matin traité le"))`
- Dans le même changement de modèle (une seule migration `BaseBillet`) : le `help_text` de
  `Configuration.rapport_emails` devient `_("Adresses séparées par des virgules. Elles reçoivent le récap du matin (périodicité « Journalier ») ou le rapport de chaque clôture (hebdomadaire, mensuelle, annuelle). Vide : aucun envoi.")` ;
  le libellé du choix `PERIODICITE_JOURNALIER` devient `_("Chaque jour, dans le récap du matin")`.

- [ ] **Étape 1 : écrire les tests qui échouent**

```python
def test_une_reservation_garde_sa_date_de_creation_quand_on_la_modifie(self):
    # created_at est posé à la création, puis ne bouge plus.
    reservation = ...  # fabrique
    date_de_creation = reservation.created_at
    with patch("django.utils.timezone.now", return_value=heure_de_paris(2026, 10, 14, 9)):
        reservation.save()
    reservation.refresh_from_db()
    assert reservation.created_at == date_de_creation
    assert reservation.created_at is not None

def test_un_evenement_garde_sa_date_de_creation_quand_on_le_modifie(self): ...  # même forme

def test_annulee_le_est_vide_a_la_creation(self):
    # Réservation, booking, adhésion : annulee_le vaut None tant que rien n'est annulé.
    assert reservation.annulee_le is None
    assert booking.annulee_le is None
    assert adhesion.annulee_le is None
```

- [ ] **Étape 2 : lancer, vérifier l'échec** — `make test ARGS="tests/pytest/test_recap_quotidien.py"` → `AttributeError … created_at`.
- [ ] **Étape 3 : ajouter les champs**, puis générer : `docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet booking`. Vérifier que `makemigrations` **ne pose aucune question** (colonnes nullables) et que les fichiers ne contiennent que les `AddField` / `AlterField` attendus. Les renommer comme ci-dessus.
- [ ] **Étape 4 : relancer** — PASS. Puis `docker exec lespass_django poetry run python /DjangoFiles/manage.py check` → `System check identified no issues`.
- [ ] **Étape 5 : message de commit suggéré** (ne pas committer) : `feat(recap): dates de création et d'annulation pour le récap du matin`.

---

