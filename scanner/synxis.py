"""SynXis booking-engine client for Bellows AFS (chain 35524, hotel 99189).

The gateway sits behind Imperva/Incapsula, which blocks plain HTTP clients and
headless browsers on the availability endpoint. What works reliably is a
*headful* Chromium (run under xvfb in CI): load the booking page once to clear
the JS challenge and establish trust, then issue same-origin fetch() calls from
the page context. See CLAUDE.md for the reverse-engineered API contract.
"""

from playwright.sync_api import sync_playwright

BASE = "https://be.synxis.com"
CHAIN = "35524"
HOTEL = "99189"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)

# In-page fetch: same-origin POST that rides the page's Incapsula-cleared session.
_AVAIL_JS = """
async ([start, end, adults, children]) => {
  const body = {ProductAvailabilityQuery:{ReturnFullContentDetails:false,
    Chain:{Id:"%s"},Hotel:{Id:"%s"},AccessCode:{},Currency:{currencyCode:"USD"},
    ChannelList:{PrimaryChannel:{Code:"WEB"},SecondaryChannel:{Code:"GC"}},NumRooms:1,
    RoomStay:{StartDate:start,EndDate:end,GuestCount:[
      {AgeQualifyingCode:"Adult",NumGuests:adults},
      {AgeQualifyingCode:"Child",NumGuests:children}]},
    Template:{Code:"initialConfig",Level:"hotel"}},
    UserDetails:{Preferences:{Language:{code:"en-US"},ResponseOptions:"IncludeMealPlan"}},Version:1};
  const r = await fetch('/gw/product/v1/getProductAvailability',
    {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if (!(r.headers.get('content-type')||'').includes('json')) return {__blocked: r.status};
  return (await r.json()).ProductAvailabilityDetail || {};
}
""" % (CHAIN, HOTEL)

_CATALOG_JS = """
async () => {
  const body = {version:1, Hotel:{id:"%s"}, Chain:{id:"%s"},
    PrimaryChannel:{code:"WEB"},
    UserDetails:{Preferences:{Language:{code:"en-US"}}}};
  const r = await fetch('/gw/partner/v1/GetHotelDetails',
    {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if (!(r.headers.get('content-type')||'').includes('json')) return {__blocked: r.status};
  return await r.json();
}
""" % (HOTEL, CHAIN)


def _warm_url():
    return (
        f"{BASE}/?adult=2&chain={CHAIN}&hotel={HOTEL}"
        "&level=hotel&locale=en-US&currency=USD&rooms=1"
    )


class Blocked(Exception):
    pass


class SynxisBrowser:
    """Headful-Chromium client. Use as a context manager."""

    def __init__(self, warm_wait_ms=8000, headless=False):
        self.warm_wait_ms = warm_wait_ms
        self.headless = headless
        self._pw = None
        self._browser = None
        self.page = None

    def __enter__(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = self._browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        self.page = ctx.new_page()
        self.warm()
        return self

    def __exit__(self, *exc):
        try:
            self._browser.close()
        finally:
            self._pw.stop()

    def warm(self):
        """Load the booking page to clear the Incapsula challenge and gain trust."""
        self.page.goto(_warm_url(), wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(self.warm_wait_ms)

    def get_room_catalog(self):
        data = self.page.evaluate(_CATALOG_JS)
        if "__blocked" in data:
            self.warm()
            data = self.page.evaluate(_CATALOG_JS)
        if "__blocked" in data:
            raise Blocked(f"catalog blocked: {data['__blocked']}")
        return data["Hotel"]["RoomList"]

    def get_availability(self, start, end, adults=2, children=0, _retried=False):
        detail = self.page.evaluate(_AVAIL_JS, [start, end, adults, children])
        if "__blocked" in detail:
            if _retried:
                raise Blocked(f"availability blocked: {detail['__blocked']}")
            self.warm()
            return self.get_availability(start, end, adults, children, _retried=True)
        return detail
