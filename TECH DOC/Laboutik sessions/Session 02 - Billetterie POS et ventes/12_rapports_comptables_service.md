# Session 12 — Fondation HMAC + service de calcul

## CONTEXTE

Tu travailles sur `laboutik/` et `BaseBillet/` (POS Django).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune operation git.**

Cette session pose les **fondations de la conformite LNE** (referentiel v1.7, chapitre IV).
Tout le reste (clotures, tickets, archivage) depend de cette couche.

Le referentiel LNE exige l'**inalterabilite des donnees** (exigence 8) via un mecanisme
cryptographique a cle. La solution retenue : **chainage HMAC-SHA256** sur chaque `LigneArticle`.

Lis le design spec : `docs/superpowers/specs/2026-03-30-conformite-lne-caisse-design.md`

## TACHE 1 — Cle HMAC par tenant

Dans `laboutik/models.py`, ajouter sur `LaboutikConfiguration` :

```python
hmac_key = models.CharField(
    max_length=200, blank=True, null=True,
    verbose_name=_("HMAC key (encrypted)"),
    help_text=_("Cle HMAC pour le chainage d'integrite (stockee chiffree Fernet). "
                "/ HMAC key for integrity chaining (Fernet-encrypted)."),
)
```

+ methodes `get_hmac_key()` / `set_hmac_key()` (meme pattern que Sunmi).

+ methode `get_or_create_hmac_key()` qui genere la cle au premier appel :
```python
def get_or_create_hmac_key(self):
    key = self.get_hmac_key()
    if not key:
        import secrets
        key = secrets.token_hex(32)  # 256 bits
        self.set_hmac_key(key)
        self.save(update_fields=['hmac_key'])
    return key
```

Ajouter aussi les champs config :
- `fond_de_caisse` IntegerField(default=0) — montant initial tiroir (centimes)
- `rapport_emails` JSONField(default=list) — destinataires envoi auto
- `rapport_periodicite` CharField(choices, default='daily')
- `pied_ticket` TextField(blank=True, default='')
- `total_perpetuel` IntegerField(default=0) — jamais remis a 0

**NE PAS exposer `hmac_key` dans l'admin.** Le champ doit etre dans `exclude` de l'admin.

Migration.

## TACHE 2 — Champs HMAC sur LigneArticle

Dans `BaseBillet/models.py`, ajouter sur `LigneArticle` :

```python
# Chainage HMAC-SHA256 (conformite LNE exigence 8)
# / HMAC-SHA256 chaining (LNE compliance requirement 8)
hmac_hash = models.CharField(
    max_length=64, blank=True, default='',
    verbose_name=_("HMAC hash"),
    help_text=_("HMAC-SHA256 de cette ligne chainee avec la precedente."),
)
previous_hmac = models.CharField(
    max_length=64, blank=True, default='',
    verbose_name=_("Previous HMAC"),
    help_text=_("HMAC de la LigneArticle precedente dans la chaine."),
)

# Donnee elementaire HT — exigence LNE 3
# Le referentiel exige le total HT comme donnee elementaire (pas juste calcule)
# / LNE requirement 3: HT as elementary data (not just computed)
total_ht = models.IntegerField(
    default=0,
    verbose_name=_("Total HT (cents)"),
    help_text=_("Total hors taxes en centimes. Calcule : TTC / (1 + taux/100)."),
)
```

Migration.

## TACHE 3 — Module `laboutik/integrity.py`

Cree `laboutik/integrity.py`. Fonctions de calcul et verification HMAC.

```python
"""
Module d'integrite des donnees d'encaissement.
Chainage HMAC-SHA256 conforme a l'exigence 8 du referentiel LNE v1.7.
/ Data integrity module for POS transactions.
HMAC-SHA256 chaining per LNE certification standard v1.7, requirement 8.
"""
import hmac
import hashlib
import json


def calculer_hmac(ligne, cle_secrete, previous_hmac=''):
    """
    Calcule le HMAC-SHA256 d'une LigneArticle chainee avec la precedente.
    Les champs hashes sont ceux qui impactent le rapport comptable.
    / Computes HMAC-SHA256 of a LigneArticle chained with the previous one.
    """
    donnees = json.dumps([
        str(ligne.uuid),
        str(ligne.datetime.isoformat()) if ligne.datetime else '',
        ligne.amount,
        ligne.total_ht,
        float(ligne.qty),
        float(ligne.vat),
        ligne.payment_method or '',
        ligne.status or '',
        ligne.sale_origin or '',
        previous_hmac,
    ])
    return hmac.new(
        cle_secrete.encode('utf-8'),
        donnees.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def obtenir_previous_hmac(sale_origin='LABOUTIK'):
    """
    Retourne le hmac_hash de la derniere LigneArticle chainee.
    / Returns the hmac_hash of the last chained LigneArticle.
    """
    from BaseBillet.models import LigneArticle
    derniere = LigneArticle.objects.filter(
        sale_origin=sale_origin,
        hmac_hash__gt='',
    ).order_by('-datetime', '-pk').values_list('hmac_hash', flat=True).first()
    return derniere or ''


def verifier_chaine(lignes, cle_secrete):
    """
    Verifie l'integrite de la chaine HMAC sur un queryset de LigneArticle.
    Retourne (True, []) si tout est OK, (False, [erreurs]) sinon.
    / Verifies HMAC chain integrity on a LigneArticle queryset.
    Returns (True, []) if OK, (False, [errors]) otherwise.
    """
    erreurs = []
    corrections_tracees = []
    previous = ''
    for ligne in lignes.order_by('datetime', 'pk'):
        if not ligne.hmac_hash:
            # Ligne pre-migration, ignorer
            continue
        attendu = calculer_hmac(ligne, cle_secrete, previous)
        if ligne.hmac_hash != attendu:
            # Verifier si c'est une correction tracee (CorrectionPaiement)
            from laboutik.models import CorrectionPaiement
            correction = CorrectionPaiement.objects.filter(
                ligne_article=ligne
            ).first()
            if correction:
                corrections_tracees.append({
                    'uuid': str(ligne.uuid),
                    'correction': str(correction.uuid),
                    'ancien_moyen': correction.ancien_moyen,
                    'nouveau_moyen': correction.nouveau_moyen,
                })
            else:
                erreurs.append({
                    'uuid': str(ligne.uuid),
                    'datetime': str(ligne.datetime),
                    'attendu': attendu,
                    'trouve': ligne.hmac_hash,
                })
        previous = ligne.hmac_hash
    return (len(erreurs) == 0, erreurs, corrections_tracees)
```

## TACHE 4 — Integration dans `_creer_lignes_articles()`

Dans `laboutik/views.py`, modifier `_creer_lignes_articles()` pour :

1. Calculer `total_ht` a la creation : `int(round(amount / (1 + float(vat) / 100)))` si vat > 0, sinon `total_ht = amount`
2. Obtenir la cle HMAC : `LaboutikConfiguration.get_solo().get_or_create_hmac_key()`
3. Obtenir le `previous_hmac` de la derniere ligne chainee
4. Calculer le HMAC et le stocker sur la LigneArticle
5. Enchainer : chaque ligne suivante dans le meme panier utilise le HMAC de la precedente

```python
from laboutik.integrity import calculer_hmac, obtenir_previous_hmac

# Dans _creer_lignes_articles(), apres la creation de chaque ligne :
config = LaboutikConfiguration.get_solo()
cle = config.get_or_create_hmac_key()
previous = obtenir_previous_hmac()

for ligne in lignes_creees:
    # Calculer HT
    if ligne.vat and float(ligne.vat) > 0:
        ligne.total_ht = int(round(ligne.amount / (1 + float(ligne.vat) / 100)))
    else:
        ligne.total_ht = ligne.amount

    # Chainage HMAC
    ligne.previous_hmac = previous
    ligne.hmac_hash = calculer_hmac(ligne, cle, previous)
    ligne.save(update_fields=['total_ht', 'hmac_hash', 'previous_hmac'])
    previous = ligne.hmac_hash
```

## TACHE 5 — `RapportComptableService`

Cree `laboutik/reports.py`. Le service de calcul (12 methodes).

Voir le detail dans le design spec section 5.
Memes methodes que l'ancienne session 12 :
1. `calculer_totaux_par_moyen()`
2. `calculer_detail_ventes()`
3. `calculer_tva()`
4. `calculer_solde_caisse()`
5. `calculer_recharges()`
6. `calculer_adhesions()`
7. `calculer_remboursements()`
8. `calculer_habitus()` — SANS N+1 (annotate)
9. `calculer_billets()`
10. `calculer_synthese_operations()`
11. `calculer_operateurs()`
12. `_infos_legales()`
+ `generer_rapport_complet()` → dict avec 12 cles
+ `calculer_hash_lignes()` → SHA-256 des lignes couvertes (filet de securite cloture)

## TACHE 6 — Management command `verify_integrity`

Cree `laboutik/management/commands/verify_integrity.py`.

Parcourt toutes les `LigneArticle` chainées du tenant et verifie la chaine HMAC.
Signale les ruptures (ligne modifiee, ligne supprimee, ligne inseree).

```bash
docker exec lespass_django poetry run python manage.py verify_integrity --tenant=demo
```

## TACHE 7 — Tests

Cree `tests/pytest/test_integrity_hmac.py` et `tests/pytest/test_rapport_comptable.py`.

### test_integrity_hmac.py
- `test_hmac_calcule_a_la_creation` : creer une LigneArticle → hmac_hash non vide
- `test_hmac_chaine_correcte` : 3 lignes → chaine verifiable
- `test_hmac_detecte_modification` : modifier amount → verifier_chaine retourne False
- `test_hmac_detecte_suppression` : supprimer une ligne → chaine cassee
- `test_hmac_correction_tracee` : modifier payment_method avec CorrectionPaiement → verifier_chaine signale "correction tracee" (pas "falsification")
- `test_cle_generee_auto` : get_or_create_hmac_key() genere une cle au 1er appel
- `test_cle_stable` : 2 appels → meme cle
- `test_total_ht_calcule` : TVA 20% sur 1200c TTC → HT=1000, TVA=200

### test_rapport_comptable.py
- `test_totaux_par_moyen` : 3 lignes (especes, CB, NFC) → totaux corrects
- `test_tva_calcul` : TVA 20% sur 1200c TTC → HT=1000, TVA=200
- `test_tva_zero` : TVA 0% → HT=TTC
- `test_solde_caisse` : fond 15000 + ventes 5000 = 20000
- `test_habitus_sans_n_plus_1` : annotate (pas de boucle par carte)
- `test_detail_ventes_par_categorie` : 2 categories, sous-totaux
- `test_rapport_complet` : 12 cles presentes

## VERIFICATION

```bash
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run python manage.py check
docker exec lespass_django poetry run pytest tests/pytest/test_integrity_hmac.py -v
docker exec lespass_django poetry run pytest tests/pytest/test_rapport_comptable.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
```

### Critere de succes

- [ ] Cle HMAC par tenant (Fernet) dans LaboutikConfiguration
- [ ] `hmac_hash` + `previous_hmac` + `total_ht` sur LigneArticle (migration)
- [ ] `integrity.py` avec `calculer_hmac()` et `verifier_chaine()`
- [ ] Chainage HMAC integre dans `_creer_lignes_articles()`
- [ ] `RapportComptableService` avec 12 methodes + `generer_rapport_complet()`
- [ ] Management command `verify_integrity`
- [ ] 14+ tests pytest verts
- [ ] Tous les tests existants passent (261+)
