# Catalogue des cas de test — `booking` app

**Référence design :** `booking/doc/tibillet-booking-logic-design.md`
**Fichiers de test :** `booking/tests/`

--------------------------------------------------------------------------------

## Notation

Ce document utilise une syntaxe pseudo-Haskell pour décrire les cas de
test de façon concise et sans ambiguïté. Voici les règles nécessaires
pour lire le document.

**Type signatures**

```
f :: A → B → C
```

`f` prend un argument de type `A`, un de type `B`, et retourne `C`.
`[X]` signifie une liste de `X`. Ce n'est pas du code exécutable —
c'est une description de ce que la fonction accepte et retourne.

**Application de fonction**

```
y = f x          -- f appliquée à x, résultat dans y
z = f x (g w)    -- les parenthèses groupent les arguments
```

Pas de parenthèses ni de virgules autour des arguments — ils sont
séparés par des espaces. Les parenthèses ne servent qu'à grouper.

**Constructeurs de valeur**

```
cal = Calendar "nom" [ClosedPeriod "2026-06-01" "2026-06-03"]
wop = WeeklyOpening "nom" [OpeningEntry MONDAY "09:00" 60 2]
b1  = Booking user start="2026-06-01 09:00 +02:00" duration=60 count=1 status=confirmed
```

`Calendar`, `WeeklyOpening`, `Booking` sont des constructeurs — ils
créent un objet avec les champs donnés. Les arguments nommés
(`start=`, `duration=`) sont utilisés quand l'ordre serait ambigu.

**Listes**

```
[x, y, z]   -- liste de trois éléments
[]          -- liste vide
xs ++ ys    -- concaténation de deux listes
```

**Dérivation en chaîne**

Chaque test suit la chaîne :

```
cal → O → W → B → E → validate
```

où chaque étape est nommée et vérifiée avant d'être passée à la
suivante. Les `assert` intermédiaires sont des points de contrôle
lisibles — ils ne font pas partie du test exécutable mais montrent
pourquoi le résultat final est ce qu'il est.

**Dates relatives**

Les tests de `validate_new_booking` utilisent `next_weekday` car
la validation dépend de la date du jour (horizon de réservation).
Tous les autres tests utilisent des dates fixes (`"2026-06-01"`, etc.).

--------------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tests — open-day
# open-day :: Date → Date → Timezone → Calendar → [Interval]
# ---------------------------------------------------------------------------

# test_get_closed_intervals_returns_interval_covering_closed_period
# ClosedPeriod Jun 10–12 (3 days) → closed [Jun 10, Jun 13)
# complement within [Jun 01, Jul 01) → two open intervals

c  = Calendar "cal" [ClosedPeriod "2026-06-10" "2026-06-12"]
od = open-day "2026-06-01" "2026-06-30" "Europe/Paris" c

assert od == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-10 00:00 +02:00",
    Interval "2026-06-13 00:00 +02:00" "2026-07-01 00:00 +02:00",
]


# test_get_closed_intervals_handles_single_day_period
# ClosedPeriod Jun 15 only → closed [Jun 15, Jun 16)
# complement → two open intervals

c  = Calendar "cal" [ClosedPeriod "2026-06-15" "2026-06-15"]
od = open-day "2026-06-01" "2026-06-30" "Europe/Paris" c

assert od == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-15 00:00 +02:00",
    Interval "2026-06-16 00:00 +02:00" "2026-07-01 00:00 +02:00",
]


# test_get_closed_intervals_handles_null_end_date
# end_date=None → closed extends to date_to+1 = Jun 26
# complement → one open interval before the closure

c  = Calendar "cal" [ClosedPeriod "2026-06-20" None]
od = open-day "2026-06-18" "2026-06-25" "Europe/Paris" c

assert od == [
    Interval "2026-06-18 00:00 +02:00" "2026-06-20 00:00 +02:00",
]


# test_get_closed_intervals_handles_overlapping_closed_periods
# two overlapping ClosedPeriods → merged [Jun 10, Jun 19)
# complement within [Jun 01, Jul 01) → two open intervals

c  = Calendar "cal" [ClosedPeriod "2026-06-10" "2026-06-15",
                     ClosedPeriod "2026-06-13" "2026-06-18"]
od = open-day "2026-06-01" "2026-06-30" "Europe/Paris" c

assert od == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-10 00:00 +02:00",
    Interval "2026-06-19 00:00 +02:00" "2026-07-01 00:00 +02:00",
]


# ---------------------------------------------------------------------------
# Tests — theoretical-slots
# theoretical-slots :: WeeklyOpening → [Interval] → [Interval]
# ---------------------------------------------------------------------------

# test_generate_theoretical_slots_from_weekday_template
# 2026-06-01 is Monday; Europe/Paris in June = CEST = +02:00

start = "2026-06-01"
end   = "2026-06-01"
tz    = "Europe/Paris"
cal   = Calendar "cal" []
O    = open-day start end tz cal
wop   = WeeklyOpening "wop" [OpeningEntry MONDAY "09:00" 60 2]

W     = theoretical-slots wop O

assert W == [
    Interval "2026-06-01 09:00 +02:00" "2026-06-01 10:00 +02:00",
    Interval "2026-06-01 10:00 +02:00" "2026-06-01 11:00 +02:00",
]


# test_generate_theoretical_slots_excludes_closed_dates
# two Mondays in window (Jun 1, Jun 8); Jun 1 closed → O starts Jun 2
# Jun 1 slot [09:00, 10:00) ⊄ O → excluded; Jun 8 slot ⊆ O → kept

start = "2026-06-01"
end   = "2026-06-08"
tz    = "Europe/Paris"
cal   = Calendar "cal" [ClosedPeriod "2026-06-01" "2026-06-01"]
O     = open-day start end tz cal
wop   = WeeklyOpening "wop" [OpeningEntry MONDAY "09:00" 60 1]

W     = theoretical-slots wop O

assert W == [
    Interval "2026-06-08 09:00 +02:00" "2026-06-08 10:00 +02:00",
]


# test_generate_theoretical_slots_respects_date_to_boundary
# one Monday in window (Jun 1); next Monday Jun 8 is beyond end → excluded

start = "2026-06-01"
end   = "2026-06-07"
tz    = "Europe/Paris"
cal   = Calendar "cal" []
O     = open-day start end tz cal
wop   = WeeklyOpening "wop" [OpeningEntry MONDAY "09:00" 60 1]

W     = theoretical-slots wop O

assert W == [
    Interval "2026-06-01 09:00 +02:00" "2026-06-01 10:00 +02:00",
]


# test_generate_theoretical_slots_start_on_closed_day_bleed_into_open_day_is_excluded
# Mon 23:30–Tue 00:30; Mon closed → O = [Tue 00:00, Wed 00:00)
# slot.start = Mon 23:30 ∉ O → excluded

start = "2026-06-01"
end   = "2026-06-02"
tz    = "Europe/Paris"
cal   = Calendar "cal" [ClosedPeriod "2026-06-01" "2026-06-01"]
O     = open-day start end tz cal
wop   = WeeklyOpening "wop" [OpeningEntry MONDAY "23:30" 60 1]

W     = theoretical-slots wop O

assert W == []


# test_generate_theoretical_slots_last_slot_bleeds_onto_open_day_is_returned
# slot[0] Mon 22:00–00:00 → start=Mon(closed) ⊄ O → excluded
# slot[1] Tue 00:00–02:00 → start=Tue(open)   ⊆ O → kept

start = "2026-06-01"
end   = "2026-06-02"
tz    = "Europe/Paris"
cal   = Calendar "cal" [ClosedPeriod "2026-06-01" "2026-06-01"]
O     = open-day start end tz cal
wop   = WeeklyOpening "wop" [OpeningEntry MONDAY "22:00" 120 2]

W     = theoretical-slots wop O

assert W == [
    Interval "2026-06-02 00:00 +02:00" "2026-06-02 02:00 +02:00",
]


# test_generate_theoretical_slots_multi_day_spanning_entry
# slot[0] Mon 08:00–20:00  ⊆ O(Mon) → kept
# slot[1] Mon 20:00–Tue 08:00  ⊄ O (crosses Tue=closed) → excluded
# slot[2] Tue 08:00–20:00  ⊄ O (Tue closed) → excluded

start = "2026-06-01"
end   = "2026-06-02"
tz    = "Europe/Paris"
cal   = Calendar "cal" [ClosedPeriod "2026-06-02" "2026-06-02"]
O     = open-day start end tz cal
wop   = WeeklyOpening "wop" [OpeningEntry MONDAY "08:00" 720 3]

W     = theoretical-slots wop O

assert W == [
    Interval "2026-06-01 08:00 +02:00" "2026-06-01 20:00 +02:00",
]


# test_generate_theoretical_slots_bleed_into_closed_day_start_date_is_open
# Sun 23:30–Mon 00:30; Mon closed → O = [Sun 00:00, Mon 00:00)
# slot.end = Mon 00:30 > O.end = Mon 00:00 → slot ⊄ O → excluded

start = "2026-06-07"
end   = "2026-06-08"
tz    = "Europe/Paris"
cal   = Calendar "cal" [ClosedPeriod "2026-06-08" "2026-06-08"]
O     = open-day start end tz cal
wop   = WeeklyOpening "wop" [OpeningEntry SUNDAY "23:30" 60 1]

W     = theoretical-slots wop O

assert W == []


# test_generate_theoretical_slots_multi_day_slot_all_open_days_is_returned
# Thu 00:00–Sat 00:00 (2880 min); intersects Thu+Fri, both open → kept

start = "2026-06-04"
end   = "2026-06-06"
tz    = "Europe/Paris"
cal   = Calendar "cal" []
O     = open-day start end tz cal
wop   = WeeklyOpening "wop" [OpeningEntry THURSDAY "00:00" 2880 1]

W     = theoretical-slots wop O

assert W == [
    Interval "2026-06-04 00:00 +02:00" "2026-06-06 00:00 +02:00",
]


# test_generate_theoretical_slots_three_day_slot_with_closed_middle_day_is_excluded
# Thu 00:00–Sun 00:00 (4320 min); intersects Thu+Fri+Sat; Fri closed → excluded

start = "2026-06-04"
end   = "2026-06-07"
tz    = "Europe/Paris"
cal   = Calendar "cal" [ClosedPeriod "2026-06-05" "2026-06-05"]
O     = open-day start end tz cal
wop   = WeeklyOpening "wop" [OpeningEntry THURSDAY "00:00" 4320 1]

W     = theoretical-slots wop O

assert W == []


# ---------------------------------------------------------------------------
# Tests — bookable-intervals
# bookable-intervals :: [Interval] → Int → [Interval] → [BookableInterval]
# ---------------------------------------------------------------------------

# test_compute_remaining_capacity_with_no_bookings_equals_capacity

tz = "Europe/Paris"
cal = Calendar "cal" []
O   = open-day "2026-06-01" "2026-06-01" tz cal
assert O == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-02 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry MONDAY "09:00" 60 1]
W   = theoretical-slots wop O
assert W == [
    Interval "2026-06-01 09:00 +02:00" "2026-06-01 10:00 +02:00",
]

E = bookable-intervals W capacity=3 []

assert E == [
    BookableInterval (Interval "2026-06-01 09:00 +02:00" "2026-06-01 10:00 +02:00") max=3 remaining=3,
]


# test_compute_remaining_capacity_decreases_with_overlapping_booking

tz  = "Europe/Paris"
cal = Calendar "cal" []
O   = open-day "2026-06-01" "2026-06-01" tz cal
assert O == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-02 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry MONDAY "09:00" 60 1]
W   = theoretical-slots wop O
assert W == [
    Interval "2026-06-01 09:00 +02:00" "2026-06-01 10:00 +02:00",
]

b1 = Booking user start="2026-06-01 09:00 +02:00" duration=60 count=1 status=confirmed
B  = expand b1
assert B == [
    Interval "2026-06-01 09:00 +02:00" "2026-06-01 10:00 +02:00",
]

E = bookable-intervals W capacity=3 B

assert E == [
    BookableInterval (Interval "2026-06-01 09:00 +02:00" "2026-06-01 10:00 +02:00") max=3 remaining=2,
]


# test_compute_remaining_capacity_zero_when_all_units_taken

tz  = "Europe/Paris"
cal = Calendar "cal" []
O   = open-day "2026-06-01" "2026-06-01" tz cal
assert O == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-02 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry MONDAY "09:00" 60 1]
W   = theoretical-slots wop O
assert W == [
    Interval "2026-06-01 09:00 +02:00" "2026-06-01 10:00 +02:00",
]

b1 = Booking user start="2026-06-01 09:00 +02:00" duration=60 count=1 status=new
b2 = Booking user start="2026-06-01 09:00 +02:00" duration=60 count=1 status=confirmed
B  = expand b1 ++ expand b2
assert B == [
    Interval "2026-06-01 09:00 +02:00" "2026-06-01 10:00 +02:00",
    Interval "2026-06-01 09:00 +02:00" "2026-06-01 10:00 +02:00",
]

E = bookable-intervals W capacity=2 B

assert E == [
    BookableInterval (Interval "2026-06-01 09:00 +02:00" "2026-06-01 10:00 +02:00") max=2 remaining=0,
]


# ---------------------------------------------------------------------------
# Tests — compute_slots (end-to-end)
# open-day            :: Date → Date → Timezone → Calendar → [Interval]
# theoretical-slots   :: WeeklyOpening → [Interval] → [Interval]
# expand              :: Booking → [Interval]
# bookable-intervals  :: [Interval] → Int → [Interval] → [BookableInterval]
# ---------------------------------------------------------------------------

# test_compute_slots_booking_count_gt_1_overlaps_multiple_slots
# booking covers 09:00–11:00 (2×60 min); both slots consumed

tz  = "Europe/Paris"
cal = Calendar "cal" []
O   = open-day "2026-06-01" "2026-06-01" tz cal
assert O == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-02 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry MONDAY "09:00" 60 2]
W   = theoretical-slots wop O
assert W == [
    Interval "2026-06-01 09:00 +02:00" "2026-06-01 10:00 +02:00",
    Interval "2026-06-01 10:00 +02:00" "2026-06-01 11:00 +02:00",
]

b1  = Booking user start="2026-06-01 09:00 +02:00" duration=60 count=2 status=confirmed
B   = expand b1
assert B == [
    Interval "2026-06-01 09:00 +02:00" "2026-06-01 10:00 +02:00",
    Interval "2026-06-01 10:00 +02:00" "2026-06-01 11:00 +02:00",
]

E = bookable-intervals W capacity=1 B

assert E == [
    BookableInterval (Interval "2026-06-01 09:00 +02:00" "2026-06-01 10:00 +02:00") max=1 remaining=0,
    BookableInterval (Interval "2026-06-01 10:00 +02:00" "2026-06-01 11:00 +02:00") max=1 remaining=0,
]


# test_compute_slots_booking_partial_overlap_counts_as_full_overlap
# b1 covers 09:30–10:30 — partially overlaps slot 09:00–10:00 → remaining=0

tz  = "Europe/Paris"
cal = Calendar "cal" []
O   = open-day "2026-06-01" "2026-06-01" tz cal
assert O == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-02 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry MONDAY "09:00" 60 1]
W   = theoretical-slots wop O
assert W == [
    Interval "2026-06-01 09:00 +02:00" "2026-06-01 10:00 +02:00",
]

b1 = Booking user start="2026-06-01 09:30 +02:00" duration=60 count=1 status=confirmed
B  = expand b1
assert B == [
    Interval "2026-06-01 09:30 +02:00" "2026-06-01 10:30 +02:00",
]

E = bookable-intervals W capacity=1 B

assert E == [
    BookableInterval (Interval "2026-06-01 09:00 +02:00" "2026-06-01 10:00 +02:00") max=1 remaining=0,
]


# test_compute_slots_returns_empty_when_no_opening_entries

tz  = "Europe/Paris"
cal = Calendar "cal" []
O   = open-day "2026-06-01" "2026-06-07" tz cal

wop = WeeklyOpening "wop" []
W   = theoretical-slots wop O
assert W == []

E = bookable-intervals W capacity=1 []

assert E == []


# test_compute_slots_end_to_end_with_fixture_coworking_resource
# TODO §12 : dépend de la fixture "Coworking" en base — à réécrire avec données inline
# fixture: "Coworking" — Mon–Fri, 8×60min from 09:00, capacity=3
# next_monday = next weekday 0 from today

tz       = "Europe/Paris"
cal      = Calendar "Coworking"   # fixture calendar, no closures
O        = open-day next_monday next_monday tz cal
wop      = WeeklyOpening "Coworking"   # fixture: Mon–Fri "09:00" 60 8
W        = theoretical-slots wop O
assert W == [
    Interval (next_monday + "09:00 +02:00") (next_monday + "10:00 +02:00"),
    Interval (next_monday + "10:00 +02:00") (next_monday + "11:00 +02:00"),
    Interval (next_monday + "11:00 +02:00") (next_monday + "12:00 +02:00"),
    Interval (next_monday + "12:00 +02:00") (next_monday + "13:00 +02:00"),
    Interval (next_monday + "13:00 +02:00") (next_monday + "14:00 +02:00"),
    Interval (next_monday + "14:00 +02:00") (next_monday + "15:00 +02:00"),
    Interval (next_monday + "15:00 +02:00") (next_monday + "16:00 +02:00"),
    Interval (next_monday + "16:00 +02:00") (next_monday + "17:00 +02:00"),
]

B        = expand-all (bookings-for "Coworking" next_monday next_monday)
E        = bookable-intervals W capacity=3 B

assert len E == 8
assert all (bi.max == 3)       for bi in E
assert all (bi.remaining <= 3) for bi in E


# test_compute_slots_end_to_end_with_fixture_petite_salle
# TODO §12 : dépend de la fixture "Petite salle" en base — à réécrire avec données inline
# fixture: "Petite salle" — Sat+Sun, 3×180min from 10:00, capacity=1
# next_saturday = next weekday 5 from today

tz            = "Europe/Paris"
cal           = Calendar "Petite salle"   # fixture calendar, no closures
O             = open-day next_saturday next_saturday tz cal
wop           = WeeklyOpening "Petite salle"   # fixture: Sat+Sun "10:00" 180 3
W             = theoretical-slots wop O
assert W == [
    Interval (next_saturday + "10:00 +02:00") (next_saturday + "13:00 +02:00"),
    Interval (next_saturday + "13:00 +02:00") (next_saturday + "16:00 +02:00"),
    Interval (next_saturday + "16:00 +02:00") (next_saturday + "19:00 +02:00"),
]

B             = expand-all (bookings-for "Petite salle" next_saturday next_saturday)
E             = bookable-intervals W capacity=1 B

assert len E == 3
assert all (bi.max == 1) for bi in E


# ---------------------------------------------------------------------------
# Tests — theoretical-slots — full-week opening
# Shared setup:
#   tz  = "Europe/Paris"
#   cal = Calendar "cal" []
#   wop = WeeklyOpening "wop" [OpeningEntry d "00:00" 60 24 for d in MON..SUN]
#   O   = open-day "2026-06-01" "2026-06-07" tz cal
# ---------------------------------------------------------------------------

# test_full_week_opening_no_closed_day_returns_168_slots

tz  = "Europe/Paris"
cal = Calendar "cal" []
O   = open-day "2026-06-01" "2026-06-07" tz cal
assert O == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-08 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry d "00:00" 60 24 for d in MON..SUN]
W   = theoretical-slots wop O

assert len W == 168   # 7 days × 24 slots


# test_full_week_opening_wednesday_closed_returns_144_slots
# Tuesday's last slot 23:00–00:00 ends at Wed midnight (half-open) → not excluded
# O splits into [Mon 00:00, Wed 00:00) and [Thu 00:00, Sun+1 00:00)

tz  = "Europe/Paris"
cal = Calendar "cal" [ClosedPeriod "2026-06-03" "2026-06-03"]
O   = open-day "2026-06-01" "2026-06-07" tz cal
assert O == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-03 00:00 +02:00",
    Interval "2026-06-04 00:00 +02:00" "2026-06-08 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry d "00:00" 60 24 for d in MON..SUN]
W   = theoretical-slots wop O

assert len W == 144   # 6 days × 24 slots
assert all (s.start.date() != "2026-06-03") for s in W


# test_full_week_opening_monday_closed_returns_144_slots

tz  = "Europe/Paris"
cal = Calendar "cal" [ClosedPeriod "2026-06-01" "2026-06-01"]
O   = open-day "2026-06-01" "2026-06-07" tz cal
assert O == [
    Interval "2026-06-02 00:00 +02:00" "2026-06-08 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry d "00:00" 60 24 for d in MON..SUN]
W   = theoretical-slots wop O

assert len W == 144
assert all (s.start.date() != "2026-06-01") for s in W


# test_full_week_opening_sunday_closed_returns_144_slots
# Saturday's last slot 23:00–00:00 ends at Sun 00:00 = O[0].end → still ⊆ O

tz  = "Europe/Paris"
cal = Calendar "cal" [ClosedPeriod "2026-06-07" "2026-06-07"]
O   = open-day "2026-06-01" "2026-06-07" tz cal
assert O == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-07 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry d "00:00" 60 24 for d in MON..SUN]
W   = theoretical-slots wop O

assert len W == 144
assert all (s.start.date() != "2026-06-07") for s in W


# test_full_week_opening_two_non_adjacent_days_closed_returns_120_slots

tz  = "Europe/Paris"
cal = Calendar "cal" [ClosedPeriod "2026-06-02" "2026-06-02",
                      ClosedPeriod "2026-06-05" "2026-06-05"]
O   = open-day "2026-06-01" "2026-06-07" tz cal
assert O == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-02 00:00 +02:00",
    Interval "2026-06-03 00:00 +02:00" "2026-06-05 00:00 +02:00",
    Interval "2026-06-06 00:00 +02:00" "2026-06-08 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry d "00:00" 60 24 for d in MON..SUN]
W   = theoretical-slots wop O

assert len W == 120   # 5 days × 24 slots
assert all (s.start.date() != "2026-06-02") for s in W
assert all (s.start.date() != "2026-06-05") for s in W


# ---------------------------------------------------------------------------
# Tests — theoretical-slots — 1 entry × 7 one-day slots
# wop = WeeklyOpening [OpeningEntry MONDAY "00:00" 1440 7]
# Each slot is one full day; slot[k].start = Mon + k days
# ---------------------------------------------------------------------------

# test_one_day_slots_opening_no_closed_day_returns_7_slots

tz  = "Europe/Paris"
cal = Calendar "cal" []
O   = open-day "2026-06-01" "2026-06-07" tz cal
assert O == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-08 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry MONDAY "00:00" 1440 7]
W   = theoretical-slots wop O
assert W == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-02 00:00 +02:00",
    Interval "2026-06-02 00:00 +02:00" "2026-06-03 00:00 +02:00",
    Interval "2026-06-03 00:00 +02:00" "2026-06-04 00:00 +02:00",
    Interval "2026-06-04 00:00 +02:00" "2026-06-05 00:00 +02:00",
    Interval "2026-06-05 00:00 +02:00" "2026-06-06 00:00 +02:00",
    Interval "2026-06-06 00:00 +02:00" "2026-06-07 00:00 +02:00",
    Interval "2026-06-07 00:00 +02:00" "2026-06-08 00:00 +02:00",
]


# test_one_day_slots_opening_wednesday_closed_returns_6_slots

tz  = "Europe/Paris"
cal = Calendar "cal" [ClosedPeriod "2026-06-03" "2026-06-03"]
O   = open-day "2026-06-01" "2026-06-07" tz cal
assert O == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-03 00:00 +02:00",
    Interval "2026-06-04 00:00 +02:00" "2026-06-08 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry MONDAY "00:00" 1440 7]
W   = theoretical-slots wop O

assert len W == 6
assert all (s.start.date() != "2026-06-03") for s in W


# test_one_day_slots_opening_monday_closed_returns_6_slots
# slot[0] Jun 01–02 ⊄ O (O starts Jun 02) → excluded; slots[1..6] ⊆ O → kept

tz  = "Europe/Paris"
cal = Calendar "cal" [ClosedPeriod "2026-06-01" "2026-06-01"]
O   = open-day "2026-06-01" "2026-06-07" tz cal
assert O == [
    Interval "2026-06-02 00:00 +02:00" "2026-06-08 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry MONDAY "00:00" 1440 7]
W   = theoretical-slots wop O

assert len W == 6
assert W[0] == Interval "2026-06-02 00:00 +02:00" "2026-06-03 00:00 +02:00"


# test_one_day_slots_opening_sunday_closed_returns_6_slots
# slot[6] Jun 07–08 ⊄ O (O ends Jun 07) → excluded; slots[0..5] ⊆ O → kept

tz  = "Europe/Paris"
cal = Calendar "cal" [ClosedPeriod "2026-06-07" "2026-06-07"]
O   = open-day "2026-06-01" "2026-06-07" tz cal
assert O == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-07 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry MONDAY "00:00" 1440 7]
W   = theoretical-slots wop O

assert len W == 6
assert W[-1] == Interval "2026-06-06 00:00 +02:00" "2026-06-07 00:00 +02:00"


# test_one_day_slots_opening_two_non_adjacent_days_closed_returns_5_slots

tz  = "Europe/Paris"
cal = Calendar "cal" [ClosedPeriod "2026-06-02" "2026-06-02",
                      ClosedPeriod "2026-06-05" "2026-06-05"]
O   = open-day "2026-06-01" "2026-06-07" tz cal
assert O == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-02 00:00 +02:00",
    Interval "2026-06-03 00:00 +02:00" "2026-06-05 00:00 +02:00",
    Interval "2026-06-06 00:00 +02:00" "2026-06-08 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry MONDAY "00:00" 1440 7]
W   = theoretical-slots wop O

assert len W == 5
assert all (s.start.date() != "2026-06-02") for s in W
assert all (s.start.date() != "2026-06-05") for s in W


# ---------------------------------------------------------------------------
# Tests — theoretical-slots — 1 entry × 1 full-week slot
# wop = WeeklyOpening [OpeningEntry MONDAY "00:00" 10080 1]
# The single slot = Interval "2026-06-01 00:00 +02:00" "2026-06-08 00:00 +02:00"
# Any closed day splits O → slot ⊄ any single o ∈ O → W = []
# ---------------------------------------------------------------------------

# test_one_week_slot_opening_no_closed_day_returns_1_slot

tz  = "Europe/Paris"
cal = Calendar "cal" []
O   = open-day "2026-06-01" "2026-06-07" tz cal
assert O == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-08 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry MONDAY "00:00" 10080 1]
W   = theoretical-slots wop O
assert W == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-08 00:00 +02:00",
]


# test_one_week_slot_opening_wednesday_closed_returns_0_slots
# slot [Jun 01, Jun 08) ⊄ O[0]=[Jun 01, Jun 03) and ⊄ O[1]=[Jun 04, Jun 08)

tz  = "Europe/Paris"
cal = Calendar "cal" [ClosedPeriod "2026-06-03" "2026-06-03"]
O   = open-day "2026-06-01" "2026-06-07" tz cal
assert O == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-03 00:00 +02:00",
    Interval "2026-06-04 00:00 +02:00" "2026-06-08 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry MONDAY "00:00" 10080 1]
W   = theoretical-slots wop O
assert W == []


# test_one_week_slot_opening_monday_closed_returns_0_slots
# slot.start = Jun 01 < O.start = Jun 02 → slot ⊄ O

tz  = "Europe/Paris"
cal = Calendar "cal" [ClosedPeriod "2026-06-01" "2026-06-01"]
O   = open-day "2026-06-01" "2026-06-07" tz cal
assert O == [
    Interval "2026-06-02 00:00 +02:00" "2026-06-08 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry MONDAY "00:00" 10080 1]
W   = theoretical-slots wop O
assert W == []


# test_one_week_slot_opening_sunday_closed_returns_0_slots
# slot.end = Jun 08 > O.end = Jun 07 → slot ⊄ O

tz  = "Europe/Paris"
cal = Calendar "cal" [ClosedPeriod "2026-06-07" "2026-06-07"]
O   = open-day "2026-06-01" "2026-06-07" tz cal
assert O == [
    Interval "2026-06-01 00:00 +02:00" "2026-06-07 00:00 +02:00",
]

wop = WeeklyOpening "wop" [OpeningEntry MONDAY "00:00" 10080 1]
W   = theoretical-slots wop O
assert W == []


# ---------------------------------------------------------------------------
# Tests — validate_new_booking
# Signature: validate_new_booking resource start duration count member
#            → (is_valid: bool, error: str | None)
# Dates are relative: next_weekday k = next date with weekday k,
#                     at least min_days_ahead days from today.
# ---------------------------------------------------------------------------

# test_validate_booking_accepts_valid_slot
# open slot, within horizon, no existing booking → accepted

tz     = "Europe/Paris"
monday = next_weekday MONDAY min_days_ahead=2
cal    = Calendar "cal" []
O      = open-day monday monday tz cal
assert O == [
    Interval (monday + "00:00 +02:00") (monday+1 + "00:00 +02:00"),
]

wop    = WeeklyOpening "wop" [OpeningEntry MONDAY "10:00" 60 1]
W      = theoretical-slots wop O
assert W == [
    Interval (monday + "10:00 +02:00") (monday + "11:00 +02:00"),
]

res          = Resource cal wop capacity=1 horizon=28
start        = monday + "10:00 +02:00"
(valid, err) = validate_new_booking res start duration=60 count=1 member

assert valid == True
assert err   is None


# test_validate_booking_rejects_slot_beyond_horizon
# slot 14 days ahead; horizon=7 → W is empty for that date → rejected

tz     = "Europe/Paris"
monday = next_weekday MONDAY min_days_ahead=14
cal    = Calendar "cal" []
O      = open-day monday monday tz cal
assert O == [
    Interval (monday + "00:00 +02:00") (monday+1 + "00:00 +02:00"),
]

wop    = WeeklyOpening "wop" [OpeningEntry MONDAY "10:00" 60 1]
W      = theoretical-slots wop O
assert W == [
    Interval (monday + "10:00 +02:00") (monday + "11:00 +02:00"),
]

# W is non-empty but horizon=7 cuts it out inside validate_new_booking
res          = Resource cal wop capacity=1 horizon=7
start        = monday + "10:00 +02:00"
(valid, err) = validate_new_booking res start duration=60 count=1 member

assert valid == False
assert err   is not None


# test_validate_booking_rejects_slot_in_closed_period
# Monday declared closed → O excludes Monday → W = [] → rejected

tz     = "Europe/Paris"
monday = next_weekday MONDAY min_days_ahead=2
cal    = Calendar "cal" [ClosedPeriod monday monday]
O      = open-day monday monday tz cal
assert O == []

wop    = WeeklyOpening "wop" [OpeningEntry MONDAY "10:00" 60 1]
W      = theoretical-slots wop O
assert W == []

res          = Resource cal wop capacity=1 horizon=28
start        = monday + "10:00 +02:00"
(valid, err) = validate_new_booking res start duration=60 count=1 member

assert valid == False
assert err   is not None


# test_validate_booking_rejects_full_slot
# capacity=1, one existing booking on same slot → remaining=0 → rejected

tz     = "Europe/Paris"
monday = next_weekday MONDAY min_days_ahead=2
cal    = Calendar "cal" []
O      = open-day monday monday tz cal
assert O == [
    Interval (monday + "00:00 +02:00") (monday+1 + "00:00 +02:00"),
]

wop    = WeeklyOpening "wop" [OpeningEntry MONDAY "10:00" 60 1]
W      = theoretical-slots wop O
assert W == [
    Interval (monday + "10:00 +02:00") (monday + "11:00 +02:00"),
]

b1     = Booking member start=(monday + "10:00 +02:00") duration=60 count=1 status=confirmed
B      = expand b1
assert B == [
    Interval (monday + "10:00 +02:00") (monday + "11:00 +02:00"),
]

E      = bookable-intervals W capacity=1 B
assert E == [
    BookableInterval (Interval (monday + "10:00 +02:00") (monday + "11:00 +02:00")) max=1 remaining=0,
]

res          = Resource cal wop capacity=1 horizon=28
start        = monday + "10:00 +02:00"
(valid, err) = validate_new_booking res start duration=60 count=1 member

assert valid == False
assert err   is not None


# test_validate_booking_slot_count_gt_1_all_slots_must_be_available
# 3 consecutive slots, no existing bookings → all remaining=1 → accepted

tz     = "Europe/Paris"
monday = next_weekday MONDAY min_days_ahead=2
cal    = Calendar "cal" []
O      = open-day monday monday tz cal
assert O == [
    Interval (monday + "00:00 +02:00") (monday+1 + "00:00 +02:00"),
]

wop    = WeeklyOpening "wop" [OpeningEntry MONDAY "10:00" 60 3]
W      = theoretical-slots wop O
assert W == [
    Interval (monday + "10:00 +02:00") (monday + "11:00 +02:00"),
    Interval (monday + "11:00 +02:00") (monday + "12:00 +02:00"),
    Interval (monday + "12:00 +02:00") (monday + "13:00 +02:00"),
]

E      = bookable-intervals W capacity=1 []
assert all (bi.remaining == 1) for bi in E

res          = Resource cal wop capacity=1 horizon=28
start        = monday + "10:00 +02:00"
(valid, err) = validate_new_booking res start duration=60 count=3 member

assert valid == True
assert err   is None


# test_validate_booking_slot_count_gt_1_fails_if_one_slot_full
# count=3 from 10:00; middle slot 11:00 already booked → remaining=0 → rejected

tz     = "Europe/Paris"
monday = next_weekday MONDAY min_days_ahead=2
cal    = Calendar "cal" []
O      = open-day monday monday tz cal
wop    = WeeklyOpening "wop" [OpeningEntry MONDAY "10:00" 60 3]
W      = theoretical-slots wop O
assert W == [
    Interval (monday + "10:00 +02:00") (monday + "11:00 +02:00"),
    Interval (monday + "11:00 +02:00") (monday + "12:00 +02:00"),
    Interval (monday + "12:00 +02:00") (monday + "13:00 +02:00"),
]

b1     = Booking member start=(monday + "11:00 +02:00") duration=60 count=1 status=confirmed
B      = expand b1
E      = bookable-intervals W capacity=1 B
assert E == [
    BookableInterval (Interval (monday + "10:00 +02:00") (monday + "11:00 +02:00")) max=1 remaining=1,
    BookableInterval (Interval (monday + "11:00 +02:00") (monday + "12:00 +02:00")) max=1 remaining=0,
    BookableInterval (Interval (monday + "12:00 +02:00") (monday + "13:00 +02:00")) max=1 remaining=1,
]

res          = Resource cal wop capacity=1 horizon=28
start        = monday + "10:00 +02:00"
(valid, err) = validate_new_booking res start duration=60 count=3 member

assert valid == False
assert err   is not None


# test_validate_booking_slot_count_gt_1_fails_if_one_slot_in_closed_period
# count=3 daily slots Mon→Wed; Tuesday closed → W missing Tuesday → rejected

tz      = "Europe/Paris"
monday  = next_weekday MONDAY min_days_ahead=3
tuesday = monday + 1 day
cal     = Calendar "cal" [ClosedPeriod tuesday tuesday]
O       = open-day monday (monday + 2 days) tz cal
assert O == [
    Interval (monday   + "00:00 +02:00") (tuesday  + "00:00 +02:00"),
    Interval (tuesday+1 + "00:00 +02:00") (monday+3 + "00:00 +02:00"),
]

wop     = WeeklyOpening "wop" [OpeningEntry MONDAY "00:00" 1440 3]
W       = theoretical-slots wop O
assert W == [
    Interval (monday + "00:00 +02:00") (tuesday + "00:00 +02:00"),
    # Tuesday slot excluded — ⊄ O
    Interval (tuesday+1 + "00:00 +02:00") (monday+3 + "00:00 +02:00"),
]

res          = Resource cal wop capacity=1 horizon=28
start        = monday + "00:00 +02:00"
(valid, err) = validate_new_booking res start duration=1440 count=3 member

assert valid == False
assert err   is not None


# test_validate_booking_rejects_mismatched_slot_duration
# opening defines 60-min slots; W has no 30-min slot → rejected

tz     = "Europe/Paris"
monday = next_weekday MONDAY min_days_ahead=2
cal    = Calendar "cal" []
O      = open-day monday monday tz cal
wop    = WeeklyOpening "wop" [OpeningEntry MONDAY "10:00" 60 1]
W      = theoretical-slots wop O
assert W == [
    Interval (monday + "10:00 +02:00") (monday + "11:00 +02:00"),
]

res          = Resource cal wop capacity=1 horizon=28
start        = monday + "10:00 +02:00"
(valid, err) = validate_new_booking res start duration=30 count=1 member
# duration=30 → no slot in W has length 30 min → lookup fails

assert valid == False
assert err   is not None


# test_validate_booking_rejects_start_time_not_aligned_to_opening
# opening starts at 10:00; request at 10:15 → no slot in W starts at 10:15 → rejected

tz     = "Europe/Paris"
monday = next_weekday MONDAY min_days_ahead=2
cal    = Calendar "cal" []
O      = open-day monday monday tz cal
wop    = WeeklyOpening "wop" [OpeningEntry MONDAY "10:00" 60 1]
W      = theoretical-slots wop O
assert W == [
    Interval (monday + "10:00 +02:00") (monday + "11:00 +02:00"),
]

res          = Resource cal wop capacity=1 horizon=28
start        = monday + "10:15 +02:00"
(valid, err) = validate_new_booking res start duration=60 count=1 member

assert valid == False
assert err   is not None


# test_validate_booking_slot_count_gt_1_rejects_if_series_exceeds_opening
# opening defines count=2; request asks count=3 → 3rd slot absent from W → rejected

tz     = "Europe/Paris"
monday = next_weekday MONDAY min_days_ahead=2
cal    = Calendar "cal" []
O      = open-day monday monday tz cal
wop    = WeeklyOpening "wop" [OpeningEntry MONDAY "10:00" 60 2]
W      = theoretical-slots wop O
assert W == [
    Interval (monday + "10:00 +02:00") (monday + "11:00 +02:00"),
    Interval (monday + "11:00 +02:00") (monday + "12:00 +02:00"),
]

res          = Resource cal wop capacity=1 horizon=28
start        = monday + "10:00 +02:00"
(valid, err) = validate_new_booking res start duration=60 count=3 member
# 3rd slot [12:00, 13:00) absent from W → lookup fails

assert valid == False
assert err   is not None


# test_validate_booking_accepts_slot_bleeding_into_next_open_day
# slot Mon 23:00–Tue 01:00; O covers Mon+Tue → slot ⊆ O → accepted

tz      = "Europe/Paris"
monday  = next_weekday MONDAY min_days_ahead=2
tuesday = monday + 1 day
cal     = Calendar "cal" []
O       = open-day monday tuesday tz cal
assert O == [
    Interval (monday + "00:00 +02:00") (tuesday+1 + "00:00 +02:00"),
]

wop     = WeeklyOpening "wop" [OpeningEntry MONDAY "23:00" 120 1]
W       = theoretical-slots wop O
assert W == [
    Interval (monday + "23:00 +02:00") (tuesday + "01:00 +02:00"),
]

res          = Resource cal wop capacity=1 horizon=28
start        = monday + "23:00 +02:00"
(valid, err) = validate_new_booking res start duration=120 count=1 member

assert valid == True
assert err   is None


# test_validate_booking_rejects_slot_bleeding_into_closed_next_day
# slot Mon 23:00–Tue 01:00; Tuesday closed → O ends Mon midnight → slot ⊄ O → rejected

tz      = "Europe/Paris"
monday  = next_weekday MONDAY min_days_ahead=2
tuesday = monday + 1 day
cal     = Calendar "cal" [ClosedPeriod tuesday tuesday]
O       = open-day monday tuesday tz cal
assert O == [
    Interval (monday + "00:00 +02:00") (tuesday + "00:00 +02:00"),
]

wop     = WeeklyOpening "wop" [OpeningEntry MONDAY "23:00" 120 1]
W       = theoretical-slots wop O
assert W == []
# slot.end = Tue 01:00 > O.end = Tue 00:00 → slot ⊄ O

res          = Resource cal wop capacity=1 horizon=28
start        = monday + "23:00 +02:00"
(valid, err) = validate_new_booking res start duration=120 count=1 member

assert valid == False
assert err   is not None
