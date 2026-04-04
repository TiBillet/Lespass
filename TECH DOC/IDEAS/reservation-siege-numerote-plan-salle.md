# Idée : Moteur de réservation par siège numéroté avec plan de salle interactif

**Priorité estimée :** Medium-High
**Complexité :** Élevée
**Statut :** Idée à explorer
**Date :** 2026-04-04

---

## Contexte et besoin

TiBillet/Lespass gère actuellement la billetterie en mode "jauge globale" — on vend N billets pour une jauge de N places. Il n'existe pas de fonctionnalité permettant d'attribuer un **siège numéroté précis** à chaque billet.

Or, certains événements nécessitent absolument cette fonctionnalité :
- Opéras, théâtres, salles de spectacle classiques
- Concerts assis (festivals premium, salles de musique)
- Cinémas en plein air avec placement numéroté
- Conférences avec plans de salle définis

C'est une fonctionnalité qui **manque dans tout l'écosystème open source de billetterie**, ce qui contraint les structures culturelles à passer par des SaaS fermés et coûteux (seats.io, Ticketmaster, FNAC...).

---

## Architecture proposée

### Approche : SVG 2D + zones + zoom par section

C'est le pattern universel utilisé par tous les grands acteurs parce que c'est ce que les utilisateurs comprennent intuitivement. Deux niveaux de navigation :

**Niveau 1 — Vue macro de la salle (plan SVG 2D vue de dessus)**
```
┌─────────────────────────────┐
│         [SCÈNE]             │
│  [Fosse]  [Parterre] [VIP]  │
│     [Balcon 1]              │
│     [Balcon 2]              │
│  [Loges gauche] [Loges dr.] │
└─────────────────────────────┘
```
Chaque zone est une zone cliquable colorée par disponibilité globale (vert = places dispo, orange = presque complet, rouge = complet).

**Niveau 2 — Vue micro d'une section (zoom sur la section choisie)**
```
Rangée A  ○ ○ ○ ● ● ● ○ ○ ○ ○
Rangée B  ○ ○ ● ● ● ● ● ○ ○ ○
Rangée C  ● ● ● ● ● ● ● ● ● ●
           (● = occupé, ○ = libre)
```
Chaque siège est un `<circle>` ou `<rect>` SVG cliquable avec son numéro.

Pour les salles complexes (opéra avec balcons), on gère avec des **onglets ou calques** (Parterre / Balcon 1 / Balcon 2 / Loges) plutôt qu'une vraie 3D.

---

## Modèle de données

### `Venue` — La salle physique (permanente, réutilisable)

```python
class Venue(models.Model):
    """
    Représente une salle physique avec son plan de siège.
    Un Venue peut être utilisé pour plusieurs événements différents.
    """
    nom_de_la_salle = models.CharField(max_length=200)
    capacite_totale = models.IntegerField()

    # Le plan SVG de la salle (niveau macro)
    # Généré une fois, stocké, réutilisé à chaque événement
    svg_plan_de_salle = models.TextField(blank=True)

    # Configuration JSON de la salle (sections, rangées, sièges)
    configuration_json = models.JSONField()

    federation = models.ForeignKey('BaseFederation', on_delete=models.CASCADE)
    date_creation = models.DateTimeField(auto_now_add=True)
```

### `Section` — Une zone de la salle (Parterre, Balcon, Loge...)

```python
class Section(models.Model):
    """
    Une section logique d'un Venue.
    Ex: "Parterre", "Balcon 1", "Loges côté jardin".
    """
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name='sections')
    nom_de_la_section = models.CharField(max_length=100)
    couleur_hex = models.CharField(max_length=7, default='#4CAF50')  # pour le plan SVG
    ordre_affichage = models.IntegerField(default=0)
```

### `Siege` — Un siège physique (permanent, lié au Venue)

```python
class Siege(models.Model):
    """
    Un siège physique dans une salle.
    Existe indépendamment des événements — c'est la réalité physique.
    Ex: "Parterre, Rangée C, Siège 12"
    """
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='sieges')

    # Identifiants lisibles par l'humain
    numero_de_rangee = models.CharField(max_length=10)   # "A", "B", "12"...
    numero_de_siege = models.IntegerField()               # 1, 2, 3...
    label_affiche = models.CharField(max_length=20)       # "C-12", "Loge 3 - Place 2"

    # Position dans le SVG de la section (coordonnées en %)
    position_x_pourcentage = models.FloatField()
    position_y_pourcentage = models.FloatField()

    # Accessibilité
    est_accessible_pmr = models.BooleanField(default=False)
    est_actif = models.BooleanField(default=True)
```

### `SiegeEvenement` — L'état d'un siège pour UN événement précis

```python
class SiegeEvenement(models.Model):
    """
    Lien entre un siège physique et un événement.
    C'est ici qu'on gère la disponibilité et les réservations.
    Un Siege + un Evenement = un SiegeEvenement unique.
    """
    STATUT_LIBRE = 'libre'
    STATUT_RESERVE_TEMPORAIREMENT = 'reserve_temp'  # panier, expire après X minutes
    STATUT_VENDU = 'vendu'
    STATUT_BLOQUE = 'bloque'  # bloqué manuellement par l'organisateur

    CHOIX_STATUT = [
        (STATUT_LIBRE, 'Libre'),
        (STATUT_RESERVE_TEMPORAIREMENT, 'Réservé temporairement'),
        (STATUT_VENDU, 'Vendu'),
        (STATUT_BLOQUE, 'Bloqué'),
    ]

    siege = models.ForeignKey(Siege, on_delete=models.CASCADE)
    evenement = models.ForeignKey('Evenement', on_delete=models.CASCADE)
    statut = models.CharField(max_length=20, choices=CHOIX_STATUT, default=STATUT_LIBRE)

    # Prix spécifique à cet événement (peut différer selon la section/tarif)
    prix_en_centimes = models.IntegerField(null=True, blank=True)

    # Si vendu : lien vers la réservation
    reservation = models.ForeignKey(
        'Reservation',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='sieges_reserves'
    )

    # Expiration de la réservation temporaire (panier)
    expire_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('siege', 'evenement')
```

---

## Problème clé : la concurrence (deux users qui cliquent en même temps)

C'est **le** problème central de tout système de réservation par siège. Deux utilisateurs voient le même siège libre, cliquent en même temps — qui l'obtient ?

### Solution recommandée : verrouillage optimiste + réservation temporaire

```python
# Dans la vue Django qui gère la sélection d'un siège
from django.db import transaction

def selectionner_siege(request, siege_evenement_id):
    """
    Tente de réserver temporairement un siège pour le mettre dans le panier.
    Utilise select_for_update() pour éviter les conflits de concurrence.
    """
    with transaction.atomic():
        # Le SELECT FOR UPDATE verrouille la ligne le temps de la transaction
        # Si un autre worker tente la même chose simultanément, il attend
        siege_evenement = SiegeEvenement.objects.select_for_update().get(
            id=siege_evenement_id
        )

        # On re-vérifie le statut APRÈS le verrou (il a pu changer)
        if siege_evenement.statut != SiegeEvenement.STATUT_LIBRE:
            # Quelqu'un d'autre vient de le prendre — on répond 409
            return HttpResponse(status=409)  # Conflict

        # On le réserve temporairement pour 10 minutes
        siege_evenement.statut = SiegeEvenement.STATUT_RESERVE_TEMPORAIREMENT
        siege_evenement.expire_le = timezone.now() + timedelta(minutes=10)
        siege_evenement.save()

    return HttpResponse(status=200)
```

Une tâche Celery périodique libère les réservations temporaires expirées.

---

## Mise à jour temps réel de la carte

Pour que la carte se mette à jour quand un siège est pris par quelqu'un d'autre :

**Option A (simple) : polling htmx**
```html
<!-- La vue macro de la salle se rafraîchit toutes les 30 secondes -->
<div hx-get="/salle/{{ evenement_id }}/plan/"
     hx-trigger="every 30s"
     hx-swap="outerHTML">
  <!-- Plan SVG ici -->
</div>
```

**Option B (avancée) : WebSockets Django Channels**
Le serveur pousse une mise à jour à tous les clients connectés dès qu'un siège change de statut. Plus réactif, plus complexe à déployer.

→ Commencer par Option A, migrer vers B si la salle fait >500 places avec forte concurrence.

---

## Génération du SVG

Deux approches pour créer le plan SVG :

**Option A — Éditeur visuel intégré (admin Django)**
Un outil type "dessin de salle" dans l'admin Unfold, où l'organisateur place les sièges en glissant-déposant sur un canvas. Chaque siège placé crée un objet `Siege` en base. Ambitieux.

**Option B — Import JSON/CSV + génération automatique (recommandé pour commencer)**
L'organisateur décrit la salle dans un CSV :
```csv
section,rangee,siege,x_pct,y_pct,pmr
Parterre,A,1,10,20,false
Parterre,A,2,15,20,false
...
```
Django génère le SVG à partir de ce CSV. Beaucoup plus rapide à implémenter.

**Option C — Templates de salles standards**
Des gabarits de salles pré-définis (salle rectangle 500 places, U 200 places, théâtre à l'italienne...) que l'organisateur adapte. Bon compromis entre flexibilité et simplicité.

---

## Intégration dans le flow TiBillet existant

```
Événement existant
      ↓
L'organisateur choisit : "Placement libre" OU "Placement numéroté"
      ↓ (si numéroté)
Sélection ou création d'un Venue
      ↓
Génération des SiegeEvenement pour cet événement
      ↓
Page publique de l'événement :
  → Vue macro du plan de salle (SVG interactif)
  → Clic sur une section → zoom sur les sièges
  → Clic sur un siège → ajout au panier (réservation temporaire 10 min)
  → Paiement → statut passe à VENDU
  → Billet généré avec numéro de siège imprimé
```

---

## Ce qui existe en open source (à auditer avant de coder)

- **[seatchart.js](https://github.com/omahili/seatchart)** — Librairie JS pure pour plans de salle, MIT, à évaluer
- **[theater.js](https://github.com/Benny-/jQuery-theater)** — Vieux plugin jQuery, pas maintenu
- **[vue-seat-chart](https://github.com/claudiouzelac/vue-seat-chart)** — Vue.js, peu maintenu

→ seatchart.js mérite une vraie évaluation avant de tout coder from scratch. Si elle couvre 80% du besoin, on l'intègre et on écrit juste le backend Django + le modèle de données.

---

## Prochaines étapes suggérées

1. **Évaluer seatchart.js** : est-ce qu'elle gère les salles complexes multi-niveaux ?
2. **Définir un cas d'usage concret** : y a-t-il une salle partenaire TiBillet qui en aurait besoin maintenant ?
3. **Prototyper le modèle de données** : Venue + Section + Siege + SiegeEvenement
4. **Valider la gestion de concurrence** avec `select_for_update()`
5. **Décider de l'interface d'administration** : import CSV ou éditeur visuel ?

---

## Estimation très grossière

| Phase | Complexité | Commentaire |
|-------|-----------|-------------|
| Modèle de données + migrations | Faible | 1-2 jours |
| Import CSV → génération SVG | Moyenne | 2-3 jours |
| Vue publique interactive (htmx + JS) | Élevée | 1-2 semaines |
| Gestion concurrence + panier temporaire | Moyenne | 2-3 jours |
| Admin organisateur (Unfold) | Moyenne | 3-5 jours |
| Tests, edge cases | Élevée | 1 semaine |

Total réaliste : **4-8 semaines** pour une V1 utilisable.
