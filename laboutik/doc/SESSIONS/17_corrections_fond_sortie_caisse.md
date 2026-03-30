# Session 17 — Corrections + fond de caisse + sortie especes

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django + HTMX).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune operation git.**

Le menu Ventes affiche le Ticket X et la liste des ventes (session 16).
Il faut maintenant ajouter : correction de moyen de paiement, re-impression ticket,
fond de caisse, et sortie de caisse avec ventilation par coupure.

**Conformite LNE exigence 4** : les corrections se font par operations de +/- (CREDIT_NOTE),
jamais par modification directe. Les lignes couvertes par une cloture sont immuables.

Lis le design spec : `docs/superpowers/specs/2026-03-30-conformite-lne-caisse-design.md`

## TACHE 1 — Modeles

Dans `laboutik/models.py`, creer :

### `CorrectionPaiement` (trace d'audit)

- `uuid` PK
- `ligne_article` FK → LigneArticle (PROTECT)
- `ancien_moyen` CharField(10)
- `nouveau_moyen` CharField(10)
- `raison` TextField (obligatoire)
- `operateur` FK → TibilletUser (SET_NULL, nullable)
- `datetime` DateTimeField(auto_now_add)

### `SortieCaisse` (retrait especes)

- `uuid` PK
- `point_de_vente` FK → PointDeVente (PROTECT)
- `operateur` FK → TibilletUser (SET_NULL, nullable)
- `datetime` DateTimeField(auto_now_add)
- `montant_total` IntegerField (centimes)
- `ventilation` JSONField — cle = valeur coupure centimes, valeur = quantite
- `note` TextField(blank=True, default='')

Migration.

## TACHE 2 — Correction moyen de paiement

### Contraintes metier

- **UNIQUEMENT especes <-> CB <-> cheque.** Pas de NFC (lie a Transaction fedow_core).
- **Post-cloture interdit** : utiliser `ligne_couverte_par_cloture()` de `integrity.py`
- **Raison obligatoire**

### Action ViewSet

Dans `PaiementViewSet` :

```python
@action(detail=False, methods=['POST'], url_path='corriger_moyen_paiement')
def corriger_moyen_paiement(self, request):
    ligne_uuid = request.POST.get('ligne_uuid')
    nouveau_moyen = request.POST.get('nouveau_moyen')
    raison = request.POST.get('raison')

    ligne = LigneArticle.objects.get(uuid=ligne_uuid)

    # GARDE 1 : NFC interdit
    if ligne.payment_method in (PaymentMethod.LOCAL_EURO, PaymentMethod.LOCAL_GIFT):
        return erreur 400 "Les paiements cashless ne peuvent pas etre modifies"

    # GARDE 2 : post-cloture interdit
    from laboutik.integrity import ligne_couverte_par_cloture
    if ligne_couverte_par_cloture(ligne):
        return erreur 400 "Cette vente est couverte par une cloture. Modification interdite."

    # GARDE 3 : raison obligatoire
    if not raison or not raison.strip():
        return erreur 400 "La raison de la correction est obligatoire"

    # Creer la trace d'audit
    CorrectionPaiement.objects.create(...)

    # Modifier la LigneArticle
    ligne.payment_method = nouveau_moyen
    ligne.save(update_fields=['payment_method'])
    # Note : le HMAC chain est casse volontairement. La CorrectionPaiement
    # sert de trace. verify_integrity() (session 12) croise avec
    # CorrectionPaiement pour distinguer correction tracee de falsification.
```

## TACHE 3 — Re-impression ticket

Dans `CaisseViewSet` :

```python
@action(detail=False, methods=['POST'], url_path='reimprimer_ticket')
def reimprimer_ticket(self, request):
    # Reconstruire ticket_data
    # ImpressionLog avec is_duplicata=True
    # imprimer_async.delay()
```

## TACHE 4 — Fond de caisse

GET : affiche le montant actuel.
POST : met a jour le montant (`LaboutikConfiguration.fond_de_caisse`).

Template `hx_fond_de_caisse.html` : input `inputmode="decimal"`, bouton ENREGISTRER.

## TACHE 5 — Sortie de caisse

GET : formulaire ventilation (12 lignes de coupures).
POST : cree un `SortieCaisse` avec ventilation JSON.
Total recalcule cote serveur (ne pas faire confiance au JS).

## TACHE 6 — Tests

Dans `tests/pytest/test_corrections_fond_sortie.py` :

- `test_correction_espece_vers_cb` : OK + CorrectionPaiement creee
- `test_correction_nfc_refuse` : 400
- `test_correction_post_cloture_refuse` : 400
- `test_correction_raison_obligatoire` : 400
- `test_fond_de_caisse_get` : 200
- `test_fond_de_caisse_post` : montant mis a jour
- `test_sortie_de_caisse_creation` : SortieCaisse creee
- `test_sortie_de_caisse_total_recalcule` : total serveur, pas JS

## VERIFICATION

```bash
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run pytest tests/pytest/test_corrections_fond_sortie.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
```

### Critere de succes

- [ ] Modeles CorrectionPaiement et SortieCaisse (migration)
- [ ] Correction ESP<->CB<->CHQ avec audit trail
- [ ] Correction NFC refusee (400)
- [ ] Correction post-cloture refusee (400)
- [ ] Raison obligatoire
- [ ] Fond de caisse GET/POST
- [ ] Sortie de caisse avec ventilation
- [ ] Total recalcule cote serveur
- [ ] 8+ tests pytest verts
- [ ] Tous les tests existants passent
