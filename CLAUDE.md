# Bellows AFS availability tool

Unofficial tool to search Bellows Air Force Station lodging by **place type** (the
official SynXis booking engine only lets you pick a date and see what's free). A
scanner walks the availability API into JSON; a static GitHub Pages site
(`docs/`) filters by type and deep-links back to the official site to book.

## Layout

- `scanner/synxis.py` — SynXis client (Playwright-based, see gotcha below).
- `scanner/scan.py` — walks a date range, writes `docs/data/{rooms,availability}.json`.
- `docs/index.html` — self-contained static site (no build step) that reads the JSON.
- `.github/workflows/scan.yml` — re-scans every 6h under xvfb, commits changed JSON.

## Run

```bash
python -m venv .venv && .venv/bin/pip install -r scanner/requirements.txt
.venv/bin/playwright install chromium
.venv/bin/python scanner/scan.py --months 12          # writes docs/data/
python -m http.server -d docs 8000                    # view at localhost:8000
```

## The SynXis API (reverse-engineered)

Property: **chain 35524, hotel 99189**. All calls POST to `https://be.synxis.com/gw/...`.

- **Catalog** — `POST /gw/partner/v1/GetHotelDetails` → `Hotel.RoomList` (all 13 types,
  regardless of availability). Body: `{"version":1,"Hotel":{"id":"99189"},"Chain":{"id":"35524"},"PrimaryChannel":{"code":"WEB"},"UserDetails":{"Preferences":{"Language":{"code":"en-US"}}}}`
- **Availability** — `POST /gw/product/v1/getProductAvailability` (see `_AVAIL_JS` in
  `synxis.py` for the exact body). Returns `ProductAvailabilityDetail.Prices[]`: one entry
  per available (room, rate) combo with `AvailableInventory` and per-night price.
  `LeastRestrictiveFailure` explains why a type is absent.
- **Booking deep link**: `https://be.synxis.com/?adult=2&arrive=<D1>&chain=35524&child=0&currency=USD&depart=<D2>&hotel=99189&level=hotel&locale=en-US&rooms=1`

### ⚠️ Gotcha: Imperva/Incapsula blocks plain clients

The availability endpoint sits behind Imperva. Plain `requests` and **headless**
Chromium get a `403` WAF page ("Pardon Our Interruption" / Incapsula interstitial),
and rapid requests flag your IP for a while. What works reliably:

- **Headful Chromium** (`headless=False`) with `--disable-blink-features=AutomationControlled`.
- Load the booking page once to clear the JS challenge (the `warm()` step), then issue
  **same-origin `fetch()` from the page context** — it rides the page's cleared session.
  A direct fetch/XHR *before* warm-up, or from Python, is blocked.
- On CI, run headful under **xvfb** (`xvfb-run`); the workflow already does this.
- Re-`warm()` on any `403`; the scanner does this automatically.

`GetHotelDetails` (catalog) is *not* Imperva-gated and works from plain `requests`,
but the scanner fetches it in-page too for simplicity.

## The 13 place types

| Code | Type | Category | Sleeps |
|------|------|----------|--------|
| CABDOG | 2-BR Backrow Cabin, dog friendly, A/C | Beach Cabin | 6 |
| CAB2RB | 2-BR Backrow Cabin, no A/C | Beach Cabin | 6 |
| CABBAC | 2-BR Backrow, A/C | Beach Cabin | 6 |
| CABC1F | 2-BR Condo 1st floor, A/C | Condo | 6 |
| CABC2F | 2-BR Condo 2nd floor, A/C | Condo | 6 |
| CAB2RO | 2-BR Oceanfront Cabin, no A/C | Beach Cabin | 6 |
| CABFAC | 2-BR Oceanfront, A/C | Beach Cabin | 6 |
| CC | Camper Cabin, dog friendly | Camper Cabin | 10 |
| CFISH | Fishing Cabin | Camper Cabin | 10 |
| GRP15 | Group Campsite | Campsite | 75 |
| INDL | Individual Lettered Campsite | Campsite | 10 |
| INDM | Individual Menehune Campsite, dog friendly | Campsite | 10 |
| INDO | Individual Oceanfront Campsite | Campsite | 10 |

**Cabins/condos have minimum-stay rules** — a 1-night probe misses them; they appear
only on 2-night queries. The scanner queries both 1 and 2 nights (`--nights 1,2`).

Rate codes vary by eligibility. Campsites: ADCAMP / CIVCMP / GRDCMP / RESCMP / RETCMP /
VETCMP. Cabins: ACTIVE / CIVIL / GUARD / RESERV / RETIRE / VETERN. The site shows the
lowest of these as the nightly price.

## Data files

`docs/data/rooms.json` — array of `{code,name,category,guest_limit,description,images[]}`.
`docs/data/availability.json` — `{scanned_at, start, end, nights[], rooms:{CODE:{"YYYY-MM-DD":{"1":{i,p,r},"2":{...}}}}}`
where `i`=inventory, `p`=min nightly price, `r`=`{rateCode: price}`.
