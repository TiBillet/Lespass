# Session 14 — Mentions legales tickets + tracabilite impressions

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune operation git.**

Le chainage HMAC (session 12) et les clotures enrichies (session 13) sont en place.
Cette session rend les justificatifs conformes aux exigences LNE 3 et 9.

Lis le design spec : `docs/superpowers/specs/2026-03-30-conformite-lne-caisse-design.md`

## TACHE 1 — Modele `ImpressionLog`

Dans `laboutik/models.py`, creer :

```python
class ImpressionLog(models.Model):
    """
    Tracabilite des impressions et envois de justificatifs.
    Conformite LNE exigence 9 : securisation des justificatifs.
    / Print/send tracking for receipts.
    LNE compliance requirement 9: receipt security.
    """
    uuid = models.UUIDField(primary_key=True, default=uuid_module.uuid4, editable=False)
    datetime = models.DateTimeField(auto_now_add=True)

    ligne_article = models.ForeignKey(
        'BaseBillet.LigneArticle', on_delete=models.PROTECT,
        null=True, blank=True, related_name='impressions',
    )
    # Pour les tickets multi-lignes (regroupement par uuid_transaction)
    uuid_transaction = models.UUIDField(
        null=True, blank=True,
        verbose_name=_("Transaction UUID"),
        help_text=_("Regroupe les lignes d'un meme paiement."),
    )
    cloture = models.ForeignKey(
        ClotureCaisse, on_delete=models.PROTECT,
        null=True, blank=True, related_name='impressions',
    )
    operateur = models.ForeignKey(
        TibilletUser, on_delete=models.SET_NULL, null=True, blank=True,
    )
    printer = models.ForeignKey(
        Printer, on_delete=models.SET_NULL, null=True, blank=True,
    )

    TYPE_CHOICES = [
        ('VENTE', _('Sale receipt')),
        ('CLOTURE', _('Closure report')),
        ('COMMANDE', _('Order ticket')),
        ('BILLET', _('Event ticket')),
    ]
    type_justificatif = models.CharField(max_length=10, choices=TYPE_CHOICES)
    is_duplicata = models.BooleanField(default=False)

    # Format : 'PAPIER' ou 'ELECTRONIQUE'
    FORMAT_CHOICES = [('P', _('Paper')), ('E', _('Electronic'))]
    format_emission = models.CharField(max_length=1, choices=FORMAT_CHOICES, default='P')

    class Meta:
        ordering = ('-datetime',)
        verbose_name = _('Print log')
        verbose_name_plural = _('Print logs')
```

Migration.

## TACHE 2 — Enrichir `formatter_ticket_vente()`

Dans `laboutik/printing/formatters.py`, modifier `formatter_ticket_vente()` :

Le dict `ticket_data` recoit les nouvelles sections :

```python
"legal": {
    "business_name": str,      # Configuration.organisation
    "address": str,            # adress + postal_code + city
    "siret": str,              # Configuration.siren
    "tva_number": str,         # Configuration.tva_number ou "TVA non applicable, art. 293 B du CGI"
    "receipt_number": str,     # Numero sequentiel
    "terminal_id": str,        # Nom du PV
},
"tva_breakdown": [
    {"rate": "20.00", "ht": 1000, "tva": 200, "ttc": 1200},
],
"total_ht": int,
"total_tva": int,
"is_duplicata": bool,
"pied_ticket": str,
```

Calcul TVA : reutiliser la logique du service (HT = TTC / (1 + taux/100)).

Pour le numero sequentiel : compteur par PV, incremente a chaque ticket de vente.
Ajouter `compteur_tickets` IntegerField(default=0) sur LaboutikConfiguration
ou utiliser un compteur par PV.

## TACHE 3 — Modifier `escpos_builder.py`

Ajouter le rendu des nouvelles sections :
- **En-tete** : raison sociale (gras centre), adresse, SIRET, n° TVA
- **Articles** : nom + qty + prix unitaire + total ligne + taux TVA
- **Pied** : ventilation TVA par taux (tableau), total HT / TVA / TTC
- **Numero de ticket** + `pied_ticket` custom
- **Mention "DUPLICATA"** si `is_duplicata=True` (gras, encadre)

## TACHE 4 — Tracabilite des impressions

Modifier `imprimer_async()` dans `laboutik/tasks.py` :

Avant chaque impression, creer un `ImpressionLog` :

```python
# Determiner si c'est un duplicata
nb_precedentes = ImpressionLog.objects.filter(
    ligne_article=ligne,
    type_justificatif='VENTE',
).count()
is_duplicata = nb_precedentes > 0

# Creer le log
ImpressionLog.objects.create(
    ligne_article=ligne,
    operateur=operateur,
    printer=printer,
    type_justificatif='VENTE',
    is_duplicata=is_duplicata,
    format_emission='P',
)

# Ajouter is_duplicata dans ticket_data
ticket_data['is_duplicata'] = is_duplicata
```

## TACHE 5 — Champ `pied_ticket`

Deja ajoute en session 12 sur `LaboutikConfiguration`.
L'ajouter dans `LaboutikConfigurationAdmin.fieldsets`.

## TACHE 6 — Tests

Dans `tests/pytest/test_mentions_legales.py` :

- `test_ticket_contient_raison_sociale` : Configuration.organisation present
- `test_ticket_contient_siret` : SIRET present
- `test_ticket_contient_ventilation_tva` : tva_breakdown non vide
- `test_ticket_total_ht_ttc` : total_ht + total_tva = total_ttc
- `test_duplicata_marque` : 2e impression → is_duplicata=True
- `test_impression_log_cree` : apres impression → ImpressionLog existe
- `test_tva_non_applicable` : si pas de tva_number → mention art. 293 B

## VERIFICATION

```bash
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run python manage.py check
docker exec lespass_django poetry run pytest tests/pytest/test_mentions_legales.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
```

### Critere de succes

- [ ] Modele ImpressionLog cree avec migration
- [ ] Ticket de vente avec mentions legales completes
- [ ] Ventilation TVA par taux sur le ticket
- [ ] Mention "DUPLICATA" sur reimpressions
- [ ] ImpressionLog cree a chaque impression
- [ ] Champ pied_ticket dans l'admin
- [ ] 7+ tests pytest verts
- [ ] Tous les tests existants passent
