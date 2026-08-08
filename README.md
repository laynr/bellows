# Bellows AFS — Find a Place by Type

The official [Bellows Air Force Station](https://bellowsafs.com/) booking engine only
lets you pick a date and see what's free. This unofficial tool flips that around: it
scans availability into JSON and serves a static site where you filter by **place type**
— beach cabins, condos, camper cabins, or campsites — see a per-type availability
calendar, and click straight through to the official site to book.

**Live site:** https://laynr.github.io/bellows/

- `scanner/` — Python + Playwright scanner that walks the SynXis availability API.
- `docs/` — the static GitHub Pages site (reads `docs/data/*.json`).
- A GitHub Action re-scans every 6 hours and commits fresh data.

See [CLAUDE.md](CLAUDE.md) for the API details and how to run it locally.

Not affiliated with Bellows AFS or the Department of Defense. Availability is a
periodic snapshot — always confirm on the official site before relying on it.
