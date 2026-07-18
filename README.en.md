<h1 align="center">
  <!-- CAPTURE: TiBillet logo (the current one or a new one if you have it) -->
  <br>
  TiBillet
  <br>
</h1>

<h3 align="center">
  Ticketing, register, cashless, memberships, local currency — built in common.
</h3>

<p align="center">
  <a href="https://codecommun.coop">Code Commun Cooperative</a> ·
  <a href="https://tibillet.org">Documentation</a> ·
  <a href="https://codecommun.tibillet.coop/contrib">Contributory budget</a> ·
  <a href="https://discord.gg/ecb5jtP7vY">Discord</a> ·
  <a href="./README.md">🇫🇷 Français</a>
</p>

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/licence-AGPLv3-blue">
  <img alt="Django" src="https://img.shields.io/badge/Django-4.2-green">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11-blue">
  <img alt="Unit tests" src="https://img.shields.io/badge/pytest-618%20passed-brightgreen">
  <img alt="E2E tests" src="https://img.shields.io/badge/E2E%20Playwright-117%20passed-brightgreen">
</p>

<!-- CAPTURE: screenshot_hero.png — The most striking capture of the project. I suggest the public agenda of a venue with events, or a montage of 2-3 screens (agenda + register + NFC card). Wide format, 1200px minimum. -->

---
> **🇫🇷 Francophones :** TiBillet est une boîte à outils libre et fédérée pour la billetterie, la caisse, le paiement cashless NFC, les adhésions et les monnaies locales — construite comme un commun numérique par la [Coopérative Code Commun](https://codecommun.coop). [Lire la suite en français →](./README.md)

---


## What is TiBillet?

TiBillet is a set of free/open-source tools for cultural venues, festivals, associations and third places (tiers-lieux): online ticketing, point-of-sale register, NFC card cashless, membership management, local currency and time currency.

But TiBillet is not just software. It is a **digital commons**, built by and for the people who use it. Several hundred venues and organizations, more than twenty in active contribution, a cooperative conceived as a legal commons, and the simple idea that the tools that run our living spaces should belong to no one but those who use them.

**The principle:** A tool for building federations through shared agendas and ticketing, a register and a single NFC card, valid across the whole network. No activation fees, no expiry date, no dark pattern. You top up when you want, you spend where you want, you get refunded when you want. And the card also serves as a membership card, a local wallet and/or a time currency.

**An alternative to:** Weezevent, HelloAsso, Cyclos, L'Addition, Ulule, JVC registers and POS... 

But TiBillet goes even further because it is designed to create federations: a ticketing platform can federate with others to build shared agendas. Registers can read the same NFC cards to run local currencies. Collectives can federate producers to create a social food register.


---

## Features

|     | Module                      | Description                                                                                                 | Details                        |
| --- | --------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------ |
| 🎫  | **Ticketing & Agenda**      | Events, pricing, online bookings, QR codes, entrance scanning                                               | [→ BaseBillet/](./BaseBillet/) |
| 🏪  | **POS register**            | Touch point-of-sale, article grid, multiple payment methods, LNE-compliant                                  | [→ laboutik/](./laboutik/)     |
| 💳  | **NFC Cashless**            | Contactless card, top-up online or on site, federated multi-venue payment: festival cashless.               | [→ fedow_core/](./fedow_core/) |
| 🤝  | **Memberships**             | Online or on-site subscriptions, scan verification, preferential rates                                      | [→ BaseBillet/](./BaseBillet/) |
| 🪙  | **Local & time currency**   | Euros, gift currency, time currency — several currencies on a single card                                   | [→ fedow_core/](./fedow_core/) |
| 📊  | **Reports & accounting**    | Register closings, FEC export, ticketing reports, PDF and CSV                                               | [→ laboutik/](./laboutik/)     |
| 📦  | **Inventory**               | Stock per product, alerts, movement log, real-time updates                                                  | [→ inventaire/](./inventaire/) |
| 🗳️ | **Contributory budget**     | Initiatives, votes, crowdfunding, transparent co-remuneration, volunteer engagement tracking.               | [→ crowds/](./crowds/)         |
| 🖨️ | **Thermal printing**        | Tickets, receipts, closings — Sunmi Cloud, LAN, internal printer, kitchen order printing                    | [→ laboutik/](./laboutik/)     |
| 🌐  | **Semantic API**            | Schema.org / JSON-LD, API key, REST endpoints                                                               | [→ api_v2/](./api_v2/)         |

<!-- CAPTURES: For each module, a capture in the Presentation/ or docs/img/ folder. Suggested format: 800x500px, light theme. Here is the list:

1. screenshot_agenda.png — Public page of a venue with the list of upcoming events
2. screenshot_caisse.png — The POS article grid with tiles (ideally with a visible stock badge)
3. screenshot_cashless.png — The NFC payment screen or the card return with the balance
4. screenshot_adhesion.png — The public membership page or the admin with the member list
5. screenshot_admin_bilan.png — The ticketing report page in the Unfold admin (shows the pro side)
6. screenshot_contrib.png — The /contrib page with initiatives and budgets
7. screenshot_inventaire.png — The admin stock sheet with the actions form
8. photo_carte_nfc.jpg — A real TiBillet card front/back (the physical totem of the project)
9. screenshot_caisse_festival.png — The register in festival mode if the rendering is different

Optional but impactful:
10. photo_terrain_festival.jpg — Photo of a festival or venue with TiBillet in action
11. schema_architecture.png — Simple diagram of the federation (venues + shared card + Fedow)
-->

---

Documentation being written collaboratively and available in French at: https://tibillet.org/

The old EN/FR documentation is still available here: https://tibillet.github.io/documentation_v2/

---

## In production, for real

TiBillet is not a prototype. It is a tool in production since 2018, born at the [Manapany Festival](https://www.manapany-festival.re/) in Réunion, now deployed across several dozen venues — from community cafés to festivals of 15,000 people.

A few examples of what TiBillet makes possible today:

- **4 festivals in Montpellier** share the same NFC card for 15,000 festival-goers. One card, four venues, zero disposable wristbands.
- **A citizen collective in Normandy** distributes 100 cards for solidarity food aid (Social Security for Food). Each card is credited with €100, regardless of what the person paid. No checks, no "precarious" box to tick — just dignity.
- **La Raffinerie in Réunion**, a former sugar mill converted into a third place, uses a time currency: the hours spent on the Wednesday participatory worksites are recorded on the card, exchangeable for services or drinks at the community bar in the evening.
- **Community bars** automatically verify membership at the NFC scan — no more Excel file that nobody consulted.

---

## Quick start

TiBillet runs in Docker. A single command to launch the development environment:

```bash
git clone https://github.com/TiBillet/Lespass.git
cd Lespass
cp env_example .env        # Configure environment variables

# network
docker network create frontend

# Lespass only:
docker compose up -d
# Lespass + Laboutik
docker compose -f docker-compose-laboutik-V1.yml up -d

# for demo / dev data
docker exec -ti lespass_django bash
./flush.sh # the first time, it installs all the fixtures and starts the server
rsp # If the install has already been done, starts the dev server

# same for Laboutik:
docker exec -ti laboutik_django bash
./flush.sh # the first time, it installs all the fixtures and starts the server
rsp # If the install has already been done, starts the dev server
```

The application is accessible at 
- `https://lespass.tibillet.localhost`
- `https://laboutik.tibillet.localhost`

> **Prerequisites:** Docker, Docker Compose, and a Traefik reverse proxy (included in the compose).

For installation, configuration and production deployment details: [→ Full documentation](https://tibillet.org)

---

## Tests

**618 pytest tests + 117 E2E Playwright tests, 100% green.**

```bash
# Unit and integration tests (pytest DB-only, ~3 min)
docker exec lespass_django poetry run pytest tests/pytest/ -v

# End-to-End tests (Playwright Python, ~12 min)
# Prerequisites: Django ASGI server via Traefik (alias `rsp` in the byobu pane,
# runs `manage.py runserver` in daphne mode for WebSocket support).
docker exec \
  -e ADMIN_EMAIL=admin@admin.com \
  -e E2E_TEST_TOKEN='<see .env>' \
  lespass_django poetry run pytest tests/e2e/ -v
```

See `tests/TESTS_README.md` for the full documentation (architecture, pitfalls,
environment variables).

Test Stripe card: `4242 4242 4242 4242`, exp `12/42`, CVC `424`.

---

## Architecture

TiBillet is being unified into a **mono-repo**. The three historical services (Lespass, LaBoutik, Fedow) are becoming a single multi-tenant Django project:

```
TiBillet (mono-repo)
├── BaseBillet/      Ticketing, memberships, events
├── laboutik/        POS register
├── fedow_core/      Federated wallet, tokens, multi-currency
├── crowds/          Contributory budget, crowdfunding
├── inventaire/      POS stock management
├── api_v2/          Semantic schema.org API
├── Administration/  Django admin (Unfold)
├── AuthBillet/      Authentication, SSO
├── PaiementStripe/  Payments, Stripe webhooks
└── ...
```

**Stack:** Django 4.2, Python 3.11, PostgreSQL 13 (multi-tenant via django-tenants), Redis, Celery, HTMX + Bootstrap 5, Django Channels (WebSocket).

**No SPA, no heavy JavaScript framework.** Rendering is server-side. Dynamic interactions go through HTMX. JavaScript is minimal (toasts and small interactions). This is a deliberate choice: the code must be readable and modifiable by non-expert developers who join the cooperative.

---

## More than free software

TiBillet is licensed under AGPLv3. That guarantees the code will stay free — no one can lock it down, close it, or privatize it.

But we believe that free software, as great as it is, is not enough. A Git repository with a free license is an open resource. It is not yet a commons. Tanks run on Linux. The biggest companies in the world build their fortunes on free software. The license protects the code. It protects neither the uses, nor the people.

**We did not choose to "make a commons". We build in common, because TiBillet could never have been built any other way.**

La Raffinerie's time currency is an idea that emerged from the Wednesday morning worksites — not from a specification document. The SSA in Normandy is a citizen collective that said "we need this" and that we accompanied on site. The festival mode is the feedback from ten years of volunteers behind beer taps at 2 a.m. None of these uses would have been invented by a team of developers alone in an office, nor by an AI model trained on code — because these solutions come from the people who live the problems, not from those who imagine solving them.

We draw on the work of [Elinor Ostrom](https://en.wikipedia.org/wiki/Elinor_Ostrom) to think about what we do. A commons is three indissociable things:

- **A shared resource** — the software, yes, but above all everything it enables: the federated agenda, the shared card, the data that stays with you.
- **A living community** — the venues that use it, that report needs, that test, that document. That's the starting point, not a bonus.
- **An organized governance** — the [Code Commun cooperative](https://codecommun.coop), structured as a SCIC with three colleges (facilitators, contributors, users), where each voice counts equally.

> « A free software that sleeps at the bottom of a Git forge does not change the world. A living commons, shared, documented and supported, does. »
> — [Code Commun Charter](https://codecommun.coop/docs/Fabrique/commun_numerique)

To go further: [What is a digital commons?](https://codecommun.coop/docs/Fabrique/commun_numerique) · [Charter and values](https://codecommun.coop/docs/Fabrique/charte)

---

## Contributing

TiBillet does not work with "issues" and "pull requests" in a vacuum. We build together.

### The contributory budget

We put the money on the table — literally. On [codecommun.tibillet.coop/contrib](https://codecommun.tibillet.coop/contrib), you will find the ongoing worksites, the associated budgets and everyone's contributions. You choose a task, you decide how you want to be paid (or not — volunteering is welcome too), and it is validated collectively.

This is what we call the **contributory budget**: no manager who assigns tasks, no hierarchy that decides salaries. Everyone assesses their needs in transparency.

<!-- CAPTURE: screenshot_contrib.png — The /contrib page if not already placed above -->

### How we work

- **Peer-to-peer sessions** — Every Thursday and Friday, over video call, we code together. No need to be an expert.
- **On-site visits** — We don't build from an office. We go to the venues, we install, we train, we listen to feedback. That's how the real features emerge.
- **Open monthly meetings** — On the first Monday of each month, everyone is invited. We talk about what works, what's stuck, what we want to build next.
- **Discord & Matrix** — For the day-to-day, questions, lending a hand.

### Where to start

1. **Come and chat** on [Discord](https://discord.gg/ecb5jtP7vY) — we welcome you, we point you in the right direction.
2. **Browse the worksites** on the [contributory budget](https://codecommun.tibillet.coop/contrib) — there are tasks of all levels, from documentation to Django architecture.
3. **Read the [GUIDELINES.md](./GUIDELINES.md)** for code conventions (FALC, HTMX, ViewSets, etc.).
4. **Propose an idea** — if a need comes up in 3-4 venues, we get on it.

> The code follows the **FALC** principle (Facile À Lire et Comprendre — Easy to Read and Understand): explicit variable names, bilingual FR/EN comments, logic readable top to bottom, no magic. Because a digital commons implies that the code is accessible to those who want to take hold of it.

---

## Who makes TiBillet

TiBillet is driven by the [Code Commun Cooperative](https://codecommun.coop), a SCIC (Société Coopérative d'Intérêt Collectif — Cooperative Society of Collective Interest) based in Réunion.

### Support

- **France 2030** laureate — "Innovative ticketing" call for projects from the Ministry of Culture.
- [JetBrains](https://jb.gg/OpenSourceSupport) — Open source licenses.

---

## License

[AGPLv3](./LICENSE) — Free, and it will stay that way.

---

## Contact

- **Discord**: [discord.gg/ecb5jtP7vY](https://discord.gg/ecb5jtP7vY)
- **Matrix**: https://matrix.to/#/#tibillet:tiers-lieux.org
- **Email**: [contact@tibillet.re](mailto:contact@tibillet.re)
- **Site**: [tibillet.org](https://tibillet.org)
- **Cooperative**: [codecommun.coop](https://codecommun.coop)
