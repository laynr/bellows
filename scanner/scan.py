"""Scan Bellows availability across a date range and write JSON for the site.

Usage: python scanner/scan.py [--months 12] [--nights 1,2] [--out docs/data]
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from synxis import SynxisBrowser, CHAIN, HOTEL


IMG_BASE = "https://be.synxis.com/shs-ngbe-image-resizer/images/hotel/99189/images/xlarge/room/"


def slim_room(room):
    details = room.get("Details", {})
    images = []
    for img in details.get("ImageList") or []:
        path = img.get("Path", "")
        if path:
            images.append(IMG_BASE + path.replace("\\", "/").rsplit("/", 1)[-1].lower())
    limit = details.get("GuestLimit", {}) or {}
    return {
        "code": room["Code"],
        "name": room.get("Name", room["Code"]),
        "category": room.get("CategoryCode", ""),
        "guest_limit": limit.get("Value"),
        "description": details.get("Description", "") or "",
        "images": images[:3],
    }


def parse_prices(detail):
    """-> {room_code: {"i": inventory, "p": min_nightly_price, "r": {rate: nightly_price}}}"""
    out = {}
    for entry in detail.get("Prices", []):
        product = entry.get("Product", {})
        room = (product.get("Room") or {}).get("Code")
        rate = (product.get("Rate") or {}).get("Code")
        if not room or not entry.get("Available"):
            continue
        per_night = (
            ((product.get("Prices") or {}).get("PerNight") or {}).get("Price") or {}
        ).get("Total", {})
        nightly = per_night.get("AmountWithTaxesFees") or per_night.get("Amount")
        slot = out.setdefault(room, {"i": entry.get("AvailableInventory", 0), "r": {}})
        slot["i"] = max(slot["i"], entry.get("AvailableInventory", 0))
        if rate and nightly is not None:
            slot["r"][rate] = nightly
    for slot in out.values():
        slot["p"] = min(slot["r"].values()) if slot["r"] else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--nights", default="1,2", help="comma-separated lengths of stay")
    ap.add_argument("--out", default="docs/data")
    ap.add_argument("--throttle", type=float, default=0.4)
    ap.add_argument("--adults", type=int, default=2)
    ap.add_argument("--headless", action="store_true", help="usually blocked; debugging only")
    args = ap.parse_args()

    nights_list = [int(n) for n in args.nights.split(",")]
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=args.months * 30)

    total_calls = len(nights_list) * (end - start).days
    done = 0
    errors = 0

    with SynxisBrowser(headless=args.headless) as client:
        rooms = [slim_room(r) for r in client.get_room_catalog()]
        # availability[room][iso_date][str(nights)] = {"i": inv, "p": price, "r": {...}}
        availability = {r["code"]: {} for r in rooms}
        print(f"catalog: {len(rooms)} room types")

        for nights in nights_list:
            day = start
            while day < end:
                arrive = day.isoformat()
                depart = (day + timedelta(days=nights)).isoformat()
                try:
                    detail = client.get_availability(arrive, depart, adults=args.adults)
                    for room_code, slot in parse_prices(detail).items():
                        availability.setdefault(room_code, {}).setdefault(arrive, {})[
                            str(nights)
                        ] = slot
                except Exception as e:
                    errors += 1
                    print(f"  ! {arrive} x{nights}: {e}", file=sys.stderr)
                    if errors > 20:
                        raise
                done += 1
                if done % 50 == 0:
                    print(f"  {done}/{total_calls} queries")
                client.page.wait_for_timeout(int(args.throttle * 1000))
                day += timedelta(days=1)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "rooms.json"), "w") as f:
        json.dump(rooms, f, separators=(",", ":"))
    with open(os.path.join(args.out, "availability.json"), "w") as f:
        json.dump(
            {
                "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "chain": CHAIN,
                "hotel": HOTEL,
                "adults": args.adults,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "nights": nights_list,
                "rooms": availability,
            },
            f,
            separators=(",", ":"),
        )
    n_avail = sum(len(v) for v in availability.values())
    print(f"wrote {args.out}: {n_avail} room-date availabilities, {errors} errors")


if __name__ == "__main__":
    main()
