"""
NY Surrogate's Court WebSurrogate Scraper

Architecture:
  1. nodriver (undetected Chrome) bypasses Cloudflare and drives all navigation
  2. lxml parses HTML from page source (fast, no regex needed)
  3. All form submissions happen through the real browser (no TLS fingerprint issues)

Supports all 5 search types with deep scraping.
Outputs: cases.csv, documents.csv, results.json
"""

import asyncio
import base64
import csv
import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path

import nodriver as uc
from lxml import html as lxml_html

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
BASE = "https://websurrogates.nycourts.gov"
URLS = {
    "name":       f"{BASE}/Names/NameSearch",
    "name_results": f"{BASE}/Names/NameSearchResults",
    "file":       f"{BASE}/File/FileSearch",
    "file_results": f"{BASE}/File/FileSearchResults",
    "file_history": f"{BASE}/File/FileHistory",
    "old_index":  f"{BASE}/OldIndex/OldIndexSearch",
    "index_book": f"{BASE}/IndexBook/IndexBookSearch",
    "will":       f"{BASE}/Wills/WillsSearch",
}

OUTPUT_DIR = Path(__file__).parent / "output"

# ---------------------------------------------------------------------------
# Courts
# ---------------------------------------------------------------------------
COURTS = {
    "Albany": "1", "Allegany": "2", "Bronx": "3", "Broome": "4",
    "Cattaraugus": "5", "Cayuga": "6", "Chautauqua": "7", "Chenango": "9",
    "Clinton": "10", "Columbia": "11", "Cortland": "12", "Delaware": "13",
    "Dutchess": "14", "Erie": "15", "Essex": "16", "Franklin": "17",
    "Fulton": "18", "Genesee": "19", "Greene": "20", "Herkimer": "22",
    "Jefferson": "23", "Kings": "24", "Lewis": "25", "Livingston": "26",
    "Madison": "27", "Monroe": "28", "Montgomery": "29", "Nassau": "30",
    "New York": "31", "Niagara": "32", "Oneida": "33", "Onondaga": "34",
    "Ontario": "35", "Orange": "36", "Orleans": "37", "Oswego": "38",
    "Otsego": "39", "Putnam": "40", "Queens": "41", "Rensselaer": "42",
    "Richmond": "43", "Rockland": "44", "Saratoga": "45", "Schenectady": "46",
    "Schoharie": "47", "Schuyler": "48", "Seneca": "49", "St Lawrence": "50",
    "Steuben": "51", "Suffolk": "52", "Sullivan": "53", "Tioga": "54",
    "Tompkins": "55", "Ulster": "56", "Warren": "57", "Washington": "58",
    "Wayne": "59", "Westchester": "60", "Wyoming": "61", "Yates": "62",
}

# ---------------------------------------------------------------------------
# Proceeding types
# ---------------------------------------------------------------------------
PROCEEDINGS = [
    "1211 PUBLIC ADMINISTRATION PETITION",
    "1219 CHIEF FISCAL OFFICER PETITION",
    "6TH AMENDMENT",
    "ADMINISTRATION (ANCILLARY) DBN PETITION",
    "ADMINISTRATION (ANCILLARY) PETITION",
    "ADMINISTRATION (CTA) AFTER PROBATE",
    "ADMINISTRATION (DE BONIS NON) PETITION",
    "ADMINISTRATION AND TEMPORARY ADMINISTRATION PETITION",
    "ADMINISTRATION AND TEMPORARY PETITION",
    "ADMINISTRATION DBN AND TEMPORARY DBN PETITION",
    "ADMINISTRATION PETITION",
    "ADMINISTRATOR (CTA) & TEMPORARY ADMINISTRATOR CTA AFTER PROBATE",
    "ADMINISTRATOR CTA/DBN-APPOINTMENT OF",
    "ADMINISTRATOR CTA-APPOINTMENT OF",
    "ADMINISTRATOR CTA-APPOINTMENT OF TEMPORARY",
    "ADVICE AND DIRECTIONS",
    "AGREEMENTS SETTLING ESTATES",
    "ANNUAL REPORT PERSONAL NEEDS GUARDIAN",
    "ANNUAL REPORT PROPERTY GUARDIAN",
    "APPLICATION FOR REFUND",
    "APPLICATION TO EXAMINE SEALED PRIVATE RESIDENCE",
    "APPOINTMENT OF SUCCESSOR TRUSTEE- INTER VIVOS",
    "APPOINTMENT OF TRUSTEE-INTER VIVOS",
    "APPORTION TAXES",
    "CHARITABLE REMAINDER TRUST PETITION",
    "COMMON TRUST FUND - FINAL ACCOUNTING",
    "COMMON TRUST FUND - INTERMEDIATE ACCOUNTING",
    "COMPEL DELIVERY OF PROPERTY BY FIDUCIARY",
    "COMPEL FIDUCIARY TO ACCOUNT PETITION",
    "COMPEL PRODUCTION OF WILL",
    "COMPEL TRUSTEE TO ACCOUNT PETITION",
    "COMPENSATION OF PERSONS UNDER POWERS OF ATTY",
    "COMPROMISE CAUSE OF ACTION-NOT WRONGFUL DEATH",
    "COMPROMISE OF A CAUSE OF ACTION (NOT WRONGFUL DEATH)",
    "COMPROMISE OF ACTION NOT W/D",
    "COMPROMISE OF CONTROVERSY",
    "COMPROMISE OF DISPUTED OR UNSETTLED DEBT",
    "COMPULSORY ACCOUNT PROCEEDING",
    "CONSERVATOR'S SETTLEMENT OF FINAL ACCOUNT",
    "CONSTRUCTION OF WILL",
    "CONTINUE BUSINESS",
    "COPIES",
    "CROSS PETITION (ACCOUNTING)",
    "CROSS PETITION (ADMINISTRATION)",
    "CROSS PETITION (MISCELLANEOUS)",
    "CROSS PETITION (PROBATE)",
    "CY PRES APPLICATION",
    "DENIAL OF PROBATE & GRANTING OF ADMINISTRATION",
    "DETERMINE PREFERENCE OF LIABILITY",
    "DETERMINE THE VALIDITY OF A RIGHT OF ELECTION",
    "DETERMINE VALIDITY OF CLAIM",
    "DISCHARGE TRUSTEE PETITION-INTER VIVOS",
    "DISCOVERY",
    "DISPENSE WITH TESTIMONY OF ATTESTING WITNESS APPLICATION",
    "DISPOSITION OF REAL PROPERTY",
    "ESTATE TAX RETURN (ET706,ET90,TT385)",
    "ESTATE TAX-FIX OR EXEMPT ESTATE FROM TAX",
    "ESTATE TAX-PROCEEDINGS UNDER 998 TAX LAW",
    "EX PARTE ADVANCE PAYMENT OF FEES OR COMMISSIONS",
    "EXECUTOR-APPOINTMENT OF SUCCESSOR EXECUTOR",
    "FAMILY COURT",
    "FEE APLICATION 11-07-1-08",
    "FEE APPLICATION 08/07-10-07 (SEE 1997LT 00023F",
    "FEE APPLICATION 1/08 - 5/08",
    "FEE APPLICATION TO 11/07",
    "FIX COMPENSATION OF ATTORNEY/OTHERS",
    "FIX COMPENSATION OF ATTORNEYS OR OTHERS",
    "INCREASE/DECREASE THE AMOUNT OF FIDUCIARY BOND",
    "INTERMEDIATE ACCOUNTING-INTER VIVOS",
    "INVADE TRUST PRINCIPAL",
    "INVADE TRUST PRINCIPLE",
    "JUDICIAL SETTLEMENT OF FINAL ACCOUNT",
    "JUDICIAL SETTLEMENT OF INTERMEDIATE ACCOUNT",
    "JUDICIAL SETTLEMENT-INTER VIVOS",
    "LIMITED ADMINISTRATION",
    "LIMITED ADMINISTRATION PETITION",
    "LIVING TRUST F/B/O LYNN TARBOX",
    "MISC GIFTING",
    "OPEN SAFE DEPOSIT BOX",
    "OTHER ACCOUNTING PETITION",
    "OTHER ACCOUNTING W/FEE PETITION",
    "OTHER ADMINISTRATION PETITION",
    "OTHER ADMINISTRATION W/FEE PETITION",
    "OTHER ESTATE TAX PETITION",
    "OTHER ESTATE TAX W/FEE PETITION",
    "OTHER PETITION",
    "OTHER PETITION-INTER VIVOS",
    "OTHER PROBATE PETITION",
    "OTHER PROBATE W/FEE PETITION",
    "OTHER W/FEE PETITION-INTER VIVOS",
    "PAYMENT ON ACCOUNT OF COMMISSIONS SCPA 2310 (ON NOTICE)",
    "PERMISSION TO PAY DEBT OWED TO FIDUCIARY",
    "PERMISSION TO RESIGN",
    "PERMISSION TO TURNOVER FUNDS PAID INTO COURT",
    "PETITION FOR DISCHARGE",
    "PETITION TO ESTABLISH SUPPLEMENTAL NEEDS TRUST",
    "PETITION TO OBTAIN PROOF OF DIVORCE",
    "PETITION TO SUSPEND, MODIFY, REVOKE OR REMOVE A FIDUCIARY",
    "PETITION TO VACATE DECREE",
    "PRELIMINARY PROBATE PETITION",
    "PRELIMINARY PROBATE PETITION- ANCILLARY",
    "PROBATE & PRELIMINARY PETITIONS",
    "PROBATE & PRELIMINARY PETITIONS WITH TRUSTEE APPOINTMENT",
    "PROBATE AND PRELIMINARY PETITION",
    "PROBATE OF HEIRSHIP",
    "PROBATE PETITION",
    "PROBATE PETITION & APPOINTMENT OF ADMINISTRATOR CTA",
    "PROBATE-ANCILLARY (CTA) PETITION",
    "PROBATE-ANCILLARY PETITION",
    "REFORMATION OF TRUST",
    "REINSTATE SUSPENDED TRUSTEE",
    "RELEASE AGAINST STATE",
    "RELIEF AGAINST A FIDUCIARY",
    "RELIEF-OTHER",
    "RENUNCIATION EXTENSION OF PROPERTY INTEREST PETITION",
    "RENUNCIATION OF PROPERTY INTEREST PETITION",
    "REPORT AND ACCOUNT IN SETTLEMENT OF SMALL ESTATE",
    "REPROBATE PETITION",
    "REV. TRUST",
    "REVERSE DISCOVERY",
    "REVIEW CORPORATE TRUSTEE COMPENSATION",
    "REVOKE OR MODIFY LETTER",
    "SEALED APPOINTMENT OF GUARDIAN",
    "SEVENTH AMENDMENT TO FOUNDATION",
    "STIPULATIONS SETTLING ESTATE",
    "SUPPLEMENTAL PROBATE PETITION",
    "SUPREME COURT",
    "SUSPEND POWERS OF A TRUSTEE",
    "SUSPEND POWERS-FIDUCIARY IN WAR",
    "SUSPEND, MODIFY, REVOKE OR REMOVE A FIDUCIARY",
    "TEMPORARY ADMINISTRATION",
    "TEMPORARY ADMINISTRATION FOR ABSENTEE",
    "TEMPORARY ADMINISTRATION FOR INTERNEE",
    "TEMPORARY ADMINISTRATION PETITION",
    "TERMINATION OF UNECONOMICAL TRUST",
    "TO PUNISH RESPONDENT FOR CONTEMPT",
    "TRUSTEE-APPOINTMENT OF SUCCESSOR TESTAMENTARY",
    "TRUSTEE-APPOINTMENT OF SUCCESSOR TRUSTEE OF SNT",
    "TRUSTEE-APPOINTMENT OF TESTAMENTARY",
    "TRUSTEE-APPOINTMENT OF TESTAMENTARY FILED WITH PROBATE",
    "UNSEALING&4TH AMENDMENT",
    "VOLUNTARY ADMIN (ARTICLE 13) WITHOUT WILL",
    "VOLUNTARY ADMIN AFFIDAVIT (ARTICLE 13) W/O WILL",
    "VOLUNTARY ADMIN AFFIDAVIT (ARTICLE 13) WITH WILL",
    "VOLUNTARY ADMIN AFFIDAVIT (ARTICLE 13) WITHOUT WILL",
    "VOLUNTARY ADMIN SUCCESSOR APPOINTED",
    "VOLUNTARY ADMINISTRATION WITHOUT WILL",
    "WILL FILED NOT FOR PROBATE",
    "WILL FILED PENDING PROBATE",
    "WILL FILED PENDING VOLUNTARY ADMINISTRATION",
    "WILL FOR SAFE KEEPING",
    "WRONGFUL DEATH PETITION",
]

INDEX_BOOK_LETTERS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


# ---------------------------------------------------------------------------
# HTML parsers (work on raw HTML strings via lxml)
# ---------------------------------------------------------------------------
def extract_antiforgery_token(html_str: str) -> str | None:
    tree = lxml_html.fromstring(html_str)
    tokens = tree.cssselect('input[name="__RequestVerificationToken"]')
    if tokens:
        return tokens[0].get("value")
    return None


def extract_select_options(html_str: str, select_id: str) -> dict:
    tree = lxml_html.fromstring(html_str)
    options = {}
    for opt in tree.cssselect(f"select#{select_id} option"):
        val = opt.get("value", "")
        if val:
            options[val] = opt.text_content().strip()
    return options


def parse_search_results(html_str: str) -> list[dict]:
    tree = lxml_html.fromstring(html_str)
    table = tree.cssselect("#NameResultsTable")
    if not table:
        return []

    rows = table[0].cssselect("tbody tr")
    results = []
    for tr in rows:
        cells = tr.cssselect("td")
        if not cells:
            continue
        vals = [c.text_content().strip() for c in cells]
        btn = tr.cssselect("button[name='button'], button.ButtonAsLink")
        btn_value = btn[0].get("value", "") if btn else ""

        results.append({
            "btn_value": btn_value,
            "file_num": vals[0] if vals else "",
            "file_date": vals[1] if len(vals) > 1 else "",
            "file_name": vals[2] if len(vals) > 2 else "",
            "proceeding": vals[3] if len(vals) > 3 else "",
            "dod": vals[4] if len(vals) > 4 else "",
        })
    return results


def parse_file_history(html_str: str) -> dict:
    tree = lxml_html.fromstring(html_str)
    text = tree.text_content()

    info = {}
    # Use non-greedy patterns that stop at the next label or end of line.
    # The page text has labels like "Proceeding:  PROBATE PETITION  Letters:  ..."
    # all on one line sometimes, so we stop at known label boundaries.
    label_boundary = (
        r"(?=\s*(?:Proceeding:|Letters:|Estate Attorney Firm:|Estate Attorney:|"
        r"Estate Closed:|File Date:|Disposed:|Letters Issued:|Judge:|"
        r"Related Files|Parties|Documents|\Z))"
    )
    patterns = {
        "proceeding":           r"Proceeding:\s*(.+?)" + label_boundary,
        "letters":              r"Letters:\s*(.+?)" + label_boundary,
        "estate_attorney_firm": r"Estate Attorney Firm:\s*(.+?)" + label_boundary,
        "estate_attorney":      r"Estate Attorney:\s*(.+?)" + label_boundary,
        "estate_closed":        r"Estate Closed:\s*(\S+)",
        "file_date":            r"File Date:\s*(\S+)",
        "disposed":             r"Disposed:\s*(\S+)",
        "letters_issued":       r"Letters Issued:\s*(\S+)",
        "judge":                r"Judge:\s*(.+?)" + label_boundary,
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, text, re.DOTALL)
        if m:
            val = m.group(1).strip()
            # Clean up: remove trailing whitespace/newlines
            val = re.sub(r'\s+', ' ', val).strip()
            if val:
                info[key] = val

    # Parties table — look for "Parties" section by text, then find the next table
    parties = []
    # Strategy 1: Find table with Party/Role headers (th or first-row td)
    for tbl in tree.cssselect("table"):
        headers = [th.text_content().strip().lower()
                    for th in tbl.cssselect("thead th, tr:first-child th")]
        # Also check first row <td> in case headers are in td not th
        if not any(h in headers for h in ("party", "role", "name")):
            first_row = tbl.cssselect("tr:first-child td")
            headers = [td.text_content().strip().lower() for td in first_row]
        if any(h in headers for h in ("party", "role", "name")):
            data_rows = tbl.cssselect("tbody tr")
            if not data_rows:
                # No tbody — skip first row (headers) and use remaining tr
                all_rows = tbl.cssselect("tr")
                data_rows = all_rows[1:] if len(all_rows) > 1 else []
            for tr in data_rows:
                cells = [td.text_content().strip() for td in tr.cssselect("td")]
                if len(cells) >= 2:
                    parties.append({
                        "party": cells[0],
                        "role": cells[1],
                        "dod": cells[2] if len(cells) > 2 else "",
                        "appointed": cells[3] if len(cells) > 3 else "",
                        "active": cells[4] if len(cells) > 4 else "",
                    })
            break

    # Strategy 2: Find by "Parties" text in page, then next table
    if not parties:
        parties_section = re.search(r"Parties.*?(?=Documents|Related Files|$)", text, re.DOTALL)
        if parties_section:
            section_text = parties_section.group()
            # Extract lines that look like party entries (Name  Role  Date patterns)
            for line in section_text.split("\n"):
                parts = [p.strip() for p in line.split("  ") if p.strip()]
                if len(parts) >= 2 and parts[0] not in ("Party", "Parties", "Name", "Role"):
                    parties.append({
                        "party": parts[0],
                        "role": parts[1],
                        "dod": parts[2] if len(parts) > 2 else "",
                        "appointed": parts[3] if len(parts) > 3 else "",
                        "active": parts[4] if len(parts) > 4 else "",
                    })

    # Documents table
    documents = []
    fh_form = tree.cssselect("#FHForm")
    if fh_form:
        for tr in fh_form[0].cssselect("table tr"):
            cells = tr.cssselect("td")
            if len(cells) < 3:
                continue
            vals = [c.text_content().strip() for c in cells]
            btn = tr.cssselect("button[name='UUIDValue']")
            documents.append({
                "doc_name": vals[0],
                "comments": vals[1] if len(vals) > 1 else "",
                "qty": vals[2] if len(vals) > 2 else "",
                "doc_filed": vals[3] if len(vals) > 3 else "",
                "signed_date": vals[4] if len(vals) > 4 else "",
                "uuid": btn[0].get("value", "") if btn else "",
                "has_link": bool(btn),
            })

    # Related files
    related_files = []
    for el in tree.cssselect("button.ButtonAsLink, a"):
        parent_text = ""
        p = el.getparent()
        while p is not None:
            pt = (p.text or "").strip()
            if "Related Files" in pt or "Related" in pt:
                parent_text = "related"
                break
            p = p.getparent()
        if parent_text:
            continue
    # Simpler approach: look for "Related Files" section text
    related_section = re.search(r"Related Files.*?(?=Documents|$)", text, re.DOTALL)
    if related_section:
        related_text = related_section.group()
        if "No Related Files" not in related_text:
            # Extract file numbers from related section
            for m in re.finditer(r"(\d{4}-\d+(?:/[A-Z])?)", related_text):
                related_files.append(m.group(1))

    return {
        "info": info,
        "parties": parties,
        "documents": documents,
        "related_files": related_files,
    }


# ---------------------------------------------------------------------------
# Browser helper: JavaScript for form manipulation
# ---------------------------------------------------------------------------
JS_GET_HTML = "document.documentElement.outerHTML"

JS_SET_SELECT = """
(function(selectId, value) {
    var el = document.getElementById(selectId);
    if (!el) return false;
    el.value = value;
    el.dispatchEvent(new Event('change', {bubbles: true}));
    return true;
})('%s', '%s')
"""

JS_SET_INPUT = """
(function(name, value) {
    var el = document.querySelector('input[name="' + name + '"]');
    if (!el) el = document.getElementById(name);
    if (!el) return false;
    el.value = value;
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    return true;
})('%s', '%s')
"""

JS_CLICK_SUBMIT = """
(function() {
    var btn = document.querySelector('input[type="submit"], button[type="submit"]');
    if (!btn) btn = document.querySelector('button.btn-primary, .btn-search');
    if (btn) { btn.click(); return true; }
    return false;
})()
"""

JS_CLICK_BUTTON_BY_VALUE = """
(function(val) {
    var btns = document.querySelectorAll('button[name="button"], button.ButtonAsLink');
    for (var i = 0; i < btns.length; i++) {
        if (btns[i].value === val) { btns[i].click(); return true; }
    }
    return false;
})('%s')
"""


# ---------------------------------------------------------------------------
# Scraper class — uses nodriver for all browser interactions
# ---------------------------------------------------------------------------
class WebSurrogateScraper:
    def __init__(
        self,
        request_delay: float = 1.0,
        headless: bool = False,
        download: bool = False,
    ):
        self.request_delay = request_delay
        self.headless = headless
        self.download = download
        self.limit = 0  # 0 = no limit
        self._browser = None
        self._page = None
        self.search_results: list[dict] = []  # shallow results
        self.cases: list[dict] = []  # deep: case details
        self.documents: list[dict] = []  # deep: document details
        self.download_dir = OUTPUT_DIR / "downloads"

    async def __aenter__(self):
        await self._init_browser()
        return self

    async def __aexit__(self, *exc):
        if self._browser:
            self._browser.stop()

    async def _init_browser(self):
        log.info("Launching undetected Chrome…")
        self._browser = await uc.start(headless=self.headless)
        self._page = await self._browser.get(BASE)

        # Phase 1: Wait for Cloudflare to clear
        for attempt in range(30):
            await asyncio.sleep(2)
            try:
                text = str(await self._page.evaluate("document.body.innerText"))
                if any(k in text for k in ("Start Search", "Welcome to WebSurrogate",
                                            "I am human", "Search Options", "File Search")):
                    log.info("Cloudflare cleared after %ds", (attempt + 1) * 2)
                    break
                if "Verifying" in text or "moment" in text.lower():
                    log.info("  still verifying… (%ds)", (attempt + 1) * 2)
            except Exception:
                pass
        else:
            log.warning("Cloudflare may not have cleared after 60s")

        # Phase 2: Click "Start Search" on Welcome page
        await self._handle_welcome_page()

        # Phase 3: Solve hCaptcha on Authenticate page
        await self._solve_hcaptcha()

        # Phase 4: Click "File Search" on Search Options page (default entry point)
        await self._click_search_option("file")

    async def _handle_welcome_page(self):
        """Click 'Start Search' button on the Welcome page if present."""
        try:
            text = str(await self._page.evaluate("document.body.innerText"))
            if "Start Search" not in text:
                return
        except Exception:
            return

        log.info("Welcome page detected — clicking 'Start Search'…")
        try:
            btn = await self._page.find("Start Search", timeout=5)
            if btn:
                await btn.click()
                log.info("  Clicked Start Search")
        except Exception:
            try:
                await self._page.evaluate("""
                    var btn = document.getElementById('StartSearchButton');
                    if (btn) btn.click();
                """)
                log.info("  Clicked Start Search via JS")
            except Exception:
                pass

        # Wait for navigation to Authenticate page and update page reference
        await asyncio.sleep(3)
        # Get the current active tab after navigation
        try:
            self._page = self._browser.main_tab
        except Exception:
            pass

    async def _solve_hcaptcha(self):
        """Solve hCaptcha on the Authenticate page."""
        try:
            text = str(await self._page.evaluate("document.body.innerText"))
            url = str(await self._page.evaluate("window.location.href"))
        except Exception:
            return

        if "I am human" not in text and "CAPTCHA" not in text and "Authenticate" not in url:
            log.info("No hCaptcha page detected — skipping")
            return

        log.info("hCaptcha page detected — waiting for iframe to load…")

        # Wait for hCaptcha iframe to fully load
        for _ in range(15):
            await asyncio.sleep(1)
            try:
                has_iframe = await self._page.evaluate(
                    "!!document.querySelector('iframe[src*=\"hcaptcha\"]')"
                )
                # nodriver may return the value directly or wrapped
                if has_iframe and str(has_iframe) != "False":
                    log.info("  hCaptcha iframe loaded")
                    break
            except Exception as e:
                log.info("  iframe check error: %s", e)
        else:
            log.warning("  hCaptcha iframe did not load")

        await asyncio.sleep(2)

        # Click #checkbox inside hCaptcha iframe using CDP mouse events.
        # CDP Input.dispatchMouseEvent works at viewport level — reaches into iframes.
        for attempt in range(8):
            try:
                # JSON.stringify ensures we get a plain parseable string back
                coords_raw = await self._page.evaluate("""
                    JSON.stringify((function() {
                        var iframe = document.querySelector('iframe[src*="hcaptcha"]');
                        if (!iframe) return null;
                        var rect = iframe.getBoundingClientRect();
                        if (rect.width === 0) return null;
                        return {x: Math.round(rect.left + 28),
                                y: Math.round(rect.top + rect.height / 2)};
                    })())
                """)
                coords = json.loads(str(coords_raw)) if coords_raw else None
                log.info("  Iframe coords: %s (attempt %d)", coords, attempt + 1)
                if not coords:
                    await asyncio.sleep(2)
                    continue

                x, y = float(coords["x"]), float(coords["y"])
                log.info("  Clicking hCaptcha at (%.0f, %.0f) (attempt %d)", x, y, attempt + 1)

                # Move → press → release (simulates real mouse behavior)
                await self._page.send(uc.cdp.input_.dispatch_mouse_event(
                    type_="mouseMoved", x=x, y=y))
                await asyncio.sleep(0.15)
                await self._page.send(uc.cdp.input_.dispatch_mouse_event(
                    type_="mousePressed", x=x, y=y,
                    button=uc.cdp.input_.MouseButton("left"), click_count=1))
                await asyncio.sleep(0.05)
                await self._page.send(uc.cdp.input_.dispatch_mouse_event(
                    type_="mouseReleased", x=x, y=y,
                    button=uc.cdp.input_.MouseButton("left"), click_count=1))

                # hCaptcha checkbox clicked — it stays on the same page
                # with a green checkmark. Just wait briefly and return so
                # _click_search_option can proceed.
                await asyncio.sleep(3)
                log.info("  hCaptcha checkbox clicked — proceeding")
                return

            except Exception as e:
                log.info("  Attempt %d error: %s", attempt + 1, e)
            await asyncio.sleep(2)

        # Fallback — wait for user to solve (challenge or manual click)
        log.info("Waiting for hCaptcha to be solved (solve it in the browser if needed)…")
        for _ in range(90):
            await asyncio.sleep(2)
            try:
                url = str(await self._page.evaluate("window.location.href"))
                text = str(await self._page.evaluate("document.body.innerText"))
                if "Authenticate" not in url and "CAPTCHA" not in text:
                    log.info("hCaptcha solved!")
                    return
                if "/File/" in url or "/Names/" in url:
                    log.info("Already on search page")
                    return
                # Check if search options page appeared
                if "File Search" in text and "CAPTCHA is required" not in text:
                    log.info("hCaptcha solved — on search options page!")
                    return
            except Exception:
                pass
        log.warning("hCaptcha timeout — continuing anyway")

    async def _click_search_option(self, search_type: str):
        """Click a search option button on the AuthenticatePage / Search Options page."""
        # Button IDs on /Home/AuthenticatePage
        id_map = {
            "file": "FileSearch",
            "name": "NameSearch",
            "old_index": "OldIndexSearch",
            "index_book": "IndexBookPages",
            "will": "WillSearch",
        }
        btn_id = id_map.get(search_type, "FileSearch")
        log.info("Clicking search option '%s' (id=%s)…", search_type, btn_id)

        # Click by element ID
        clicked = await self._page.evaluate(
            f"JSON.stringify((function(){{ var b=document.getElementById('{btn_id}'); if(b){{b.click();return true;}} return false; }})())"
        )
        if str(clicked) == "true":
            log.info("  Clicked %s button", btn_id)
            await asyncio.sleep(3)
            # Update page ref after navigation
            try:
                self._page = self._browser.main_tab
            except Exception:
                pass
            return

        # Fallback: find by text
        label_map = {
            "file": "File Search",
            "name": "Name Search",
            "old_index": "Old Index Search",
            "index_book": "Index Book Pages",
            "will": "Will Search",
        }
        label = label_map.get(search_type, "File Search")
        try:
            btn = await self._page.find(label, timeout=5)
            if btn:
                await btn.click()
                log.info("  Clicked '%s' by text", label)
                await asyncio.sleep(3)
                return
        except Exception:
            pass

        # Last resort: navigate directly
        log.info("  Fallback: navigating directly to %s", URLS.get(search_type, URLS["file"]))
        self._page = await self._browser.get(URLS.get(search_type, URLS["file"]))
        await asyncio.sleep(self.request_delay + 1)

    async def _get_html(self) -> str:
        return await self._page.evaluate(JS_GET_HTML)

    async def _navigate(self, url: str) -> str:
        self._page = await self._browser.get(url)
        await asyncio.sleep(self.request_delay)
        html = await self._get_html()

        # If redirected to Welcome page
        if "Start Search" in html and "Welcome to WebSurrogate" in html:
            log.info("Redirected to Welcome page — handling…")
            await self._handle_welcome_page()
            await self._solve_hcaptcha()
            for key, u in URLS.items():
                if u == url:
                    await self._click_search_option(key)
                    break
            html = await self._get_html()
        # If redirected to captcha page
        elif "CAPTCHA is required" in html or "I am human" in html:
            log.info("Redirected to captcha page — solving…")
            await self._solve_hcaptcha()
            for key, u in URLS.items():
                if u == url:
                    await self._click_search_option(key)
                    break
            html = await self._get_html()
        # If on Search Options page (no captcha, just buttons)
        elif "Select one of the following search options" in html:
            log.info("On Search Options page — clicking through…")
            for key, u in URLS.items():
                if u == url:
                    await self._click_search_option(key)
                    break
            html = await self._get_html()

        return html

    async def _wait_for_navigation(self, timeout: float = 10.0) -> str:
        """Wait for page to load after a click/submit."""
        await asyncio.sleep(self.request_delay + 1.0)
        # Wait for body to be available
        for _ in range(int(timeout)):
            try:
                ready = await self._page.evaluate("document.readyState")
                if ready == "complete":
                    break
            except Exception:
                pass
            await asyncio.sleep(1)
        return await self._get_html()

    async def _set_select(self, select_id: str, value: str):
        await self._page.evaluate(JS_SET_SELECT % (select_id, value))

    async def _set_input(self, name: str, value: str):
        await self._page.evaluate(JS_SET_INPUT % (name, value))

    async def _click_submit(self):
        await self._page.evaluate(JS_CLICK_SUBMIT)

    async def _click_button_by_value(self, value: str):
        await self._page.evaluate(JS_CLICK_BUTTON_BY_VALUE % value)

    # -- search form submission via browser ------------------------------------
    async def _submit_file_search(
        self, court: str, proceeding: str | None = None,
        from_date: str | None = None, to_date: str | None = None,
        file_number: str | None = None,
    ) -> str:
        court_id = COURTS.get(court)
        if not court_id:
            raise ValueError(f"Unknown court: {court!r}")

        # Navigate to File Search page
        await self._navigate(URLS["file"])

        # Set court (id=CourtSelect) — triggers dynamic loading of proceedings
        await self._set_select("CourtSelect", court_id)

        if file_number:
            await asyncio.sleep(0.5)
            await self._set_input("FileNumber", file_number)
        else:
            # Wait for proceeding dropdown (id=SelectedProceeding) to populate
            # Values are the proceeding names themselves
            for _ in range(10):
                await asyncio.sleep(1)
                page_html = await self._get_html()
                options = extract_select_options(page_html, "SelectedProceeding")
                if len(options) > 1:
                    break

            if proceeding:
                await self._set_select("SelectedProceeding", proceeding)
            if from_date:
                await self._set_input("FromDateString", from_date)
            if to_date:
                await self._set_input("ToDateString", to_date)

        await asyncio.sleep(0.3)
        # Click the specific submit button by ID
        await self._page.evaluate("""
            var btn = document.getElementById('FileSearchSubmit');
            if (btn) btn.click();
            else {
                btn = document.getElementById('FileSearchSubmit2');
                if (btn) btn.click();
            }
        """)
        return await self._wait_for_navigation()

    async def _submit_name_search(
        self, court: str, last_name: str | None = None,
        first_name: str | None = None,
        organization: str | None = None,
        death_from_date: str | None = None,
        death_to_date: str | None = None,
        file_from_date: str | None = None,
        file_to_date: str | None = None,
    ) -> str:
        court_id = COURTS.get(court, court)

        await self._navigate(URLS["name"])
        await self._set_select("CourtId", court_id)
        await asyncio.sleep(0.5)

        if last_name:
            await self._set_input("LastName", last_name)
        if first_name:
            await self._set_input("FirstName", first_name)
        if organization:
            await self._set_input("Organization", organization)
        if death_from_date:
            await self._set_input("DeathFromDate", death_from_date)
        if death_to_date:
            await self._set_input("DeathToDate", death_to_date)
        if file_from_date:
            await self._set_input("FileFromDate", file_from_date)
        if file_to_date:
            await self._set_input("FileToDate", file_to_date)

        await asyncio.sleep(0.3)
        await self._click_submit()
        return await self._wait_for_navigation()

    async def _click_file_number(self, btn_value: str) -> str:
        await self._click_button_by_value(btn_value)
        return await self._wait_for_navigation()

    # -- high-level search methods -----------------------------------------
    async def file_search_by_info(
        self, court: str, proceeding: str,
        from_date: str, to_date: str | None = None,
        deep: bool = False,
    ) -> list[dict]:
        log.info("File search: %s / %s / %s–%s", court, proceeding, from_date, to_date or "")
        results_html = await self._submit_file_search(
            court, proceeding=proceeding, from_date=from_date, to_date=to_date,
        )
        rows = parse_search_results(results_html)
        log.info("  Found %d results", len(rows))
        for r in rows:
            self.search_results.append({**r, "court": court})

        if deep and rows:
            await self._deep_scrape(rows, court)
        return rows

    async def file_search_by_number(
        self, court: str, file_number: str, deep: bool = False,
    ) -> list[dict]:
        log.info("File search by number: %s / %s", court, file_number)
        results_html = await self._submit_file_search(court, file_number=file_number)
        rows = parse_search_results(results_html)
        log.info("  Found %d results", len(rows))
        for r in rows:
            self.search_results.append({**r, "court": court})

        if deep and rows:
            await self._deep_scrape(rows, court)
        return rows

    async def name_search_person(
        self, court: str, last_name: str,
        first_name: str | None = None,
        death_from_date: str | None = None,
        death_to_date: str | None = None,
        deep: bool = False,
    ) -> list[dict]:
        log.info("Name search: %s / %s %s", court, last_name, first_name or "")
        results_html = await self._submit_name_search(
            court, last_name=last_name, first_name=first_name,
            death_from_date=death_from_date, death_to_date=death_to_date,
        )
        rows = parse_search_results(results_html)
        log.info("  Found %d results", len(rows))
        for r in rows:
            self.search_results.append({**r, "court": court})

        if deep and rows:
            await self._deep_scrape(rows, court)
        return rows

    async def name_search_organization(
        self, court: str, organization: str,
        file_from_date: str | None = None,
        file_to_date: str | None = None,
        deep: bool = False,
    ) -> list[dict]:
        log.info("Org search: %s / %s", court, organization)
        results_html = await self._submit_name_search(
            court, organization=organization,
            file_from_date=file_from_date, file_to_date=file_to_date,
        )
        rows = parse_search_results(results_html)
        log.info("  Found %d results", len(rows))
        for r in rows:
            self.search_results.append({**r, "court": court})

        if deep and rows:
            await self._deep_scrape(rows, court)
        return rows

    # -- document download via viewer tab ----------------------------------
    _viewer_cf_cleared = False  # Cloudflare on iapps.courts.state.ny.us

    async def _download_document(self, uuid: str, save_path: Path) -> bool:
        """Download a document PDF by clicking its UUID button (opens a viewer
        tab at iapps.courts.state.ny.us), waiting for Cloudflare to clear,
        then fetching the raw PDF via JavaScript fetch().
        """
        tabs_before = set(id(t) for t in self._browser.tabs)
        try:
            # Submit the FHForm with the UUID value in a new tab.
            # Instead of finding and clicking the UUID button (which can fail
            # if the DOM isn't ready), we inject a hidden input and submit
            # the form directly with target="_blank".
            await self._page.evaluate(
                f"""(function(){{
                    var form = document.getElementById('FHForm');
                    if (!form) return;
                    var inp = document.createElement('input');
                    inp.type = 'hidden'; inp.name = 'UUIDValue'; inp.value = '{uuid}';
                    form.appendChild(inp);
                    var origTarget = form.target;
                    form.target = '_blank';
                    form.submit();
                    form.removeChild(inp);
                    form.target = origTarget;
                }})()"""
            )

            # Wait for new viewer tab to appear
            viewer_tab = None
            for _ in range(15):
                await asyncio.sleep(1)
                for tab in self._browser.tabs:
                    if id(tab) not in tabs_before:
                        viewer_tab = tab
                        break
                if viewer_tab:
                    break

            if not viewer_tab:
                log.warning("      No viewer tab opened for %s", uuid[:8])
                return False

            # Wait for Cloudflare to clear on the viewer domain.
            # First doc takes ~10s; subsequent docs are instant (cookie cached).
            max_wait = 60 if not self._viewer_cf_cleared else 15
            for i in range(max_wait):
                await asyncio.sleep(1)
                try:
                    ct = await viewer_tab.evaluate(
                        "fetch(window.location.href)"
                        ".then(r => r.headers.get('content-type'))"
                        ".catch(() => 'error')",
                        await_promise=True,
                    )
                    ct = str(ct)
                    if "pdf" in ct.lower():
                        if not self._viewer_cf_cleared:
                            log.info("      Viewer Cloudflare cleared after %ds", i + 1)
                            self._viewer_cf_cleared = True
                        break
                except Exception:
                    pass
            else:
                log.warning("      Viewer Cloudflare timeout for %s", uuid[:8])
                await viewer_tab.close()
                return False

            # Fetch the PDF as base64
            raw = await viewer_tab.evaluate("""
                (async function() {
                    try {
                        var resp = await fetch(window.location.href);
                        var blob = await resp.blob();
                        return new Promise(function(resolve) {
                            var reader = new FileReader();
                            reader.onload = function() {
                                resolve(JSON.stringify({ok:true, size:blob.size, data:reader.result}));
                            };
                            reader.readAsDataURL(blob);
                        });
                    } catch(e) { return JSON.stringify({error: e.toString()}); }
                })()
            """, await_promise=True)

            result = json.loads(str(raw))
            if not result.get("ok") or not result.get("data"):
                log.warning("      Fetch failed for %s: %s", uuid[:8], result.get("error"))
                await viewer_tab.close()
                return False

            b64_data = result["data"].split(",", 1)[1]
            pdf_bytes = base64.b64decode(b64_data)

            if len(pdf_bytes) < 100:
                log.warning("      PDF too small (%d bytes) for %s", len(pdf_bytes), uuid[:8])
                await viewer_tab.close()
                return False

            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(pdf_bytes)
            log.info("      Saved %s (%d bytes)", save_path.name, len(pdf_bytes))

            await viewer_tab.close()
            return True

        except Exception as e:
            log.warning("      Download exception for %s: %s", uuid[:8], e)
            # Close any extra tabs
            for tab in self._browser.tabs:
                if id(tab) not in tabs_before:
                    try:
                        await tab.close()
                    except Exception:
                        pass
            return False

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Remove/replace characters that aren't safe for filenames."""
        # Replace slashes, colons, etc. with underscores
        name = re.sub(r'[\\/:*?"<>|]', '_', name)
        # Collapse multiple spaces/underscores
        name = re.sub(r'[\s_]+', ' ', name).strip()
        # Limit length
        if len(name) > 200:
            name = name[:200]
        return name

    # -- deep scrape -------------------------------------------------------
    async def _deep_scrape(self, rows: list[dict], court: str):
        """Click into each file -> extract File History -> collect all data."""
        if self.limit:
            rows = rows[:self.limit]
            log.info("    Limited to %d file(s)", self.limit)
        total = len(rows)
        for i, row in enumerate(rows):
            file_num = row["file_num"]
            btn_val = row["btn_value"]
            log.info("  [%d/%d] Deep scraping file %s", i + 1, total, file_num)

            if not btn_val:
                log.warning("    No button value, skipping")
                continue

            # Click file number to go to File History page
            fh_html = await self._click_file_number(btn_val)

            # Capture the File History page URL
            file_history_url = str(await self._page.evaluate("window.location.href"))

            fh = parse_file_history(fh_html)
            info = fh["info"]
            parties_list = fh["parties"]
            docs = fh["documents"]
            related = fh["related_files"]

            # Person folder name for downloads
            person_name = self._sanitize_filename(row.get("file_name", file_num))

            # Process documents: get viewer URLs and optionally download PDFs
            docs_with_urls = []
            name_counter: dict[str, int] = {}  # track duplicates for naming
            for doc in docs:
                doc_entry = {**doc, "viewer_url": "", "downloaded": False}

                if doc.get("has_link") and doc.get("uuid"):
                    uuid_val = doc["uuid"]

                    # Build a deterministic viewer URL from the form action + UUID
                    doc_entry["viewer_url"] = f"{BASE}/File/FileHistory?UUIDValue={uuid_val}"

                    # Download if requested
                    if self.download:
                        doc_name = self._sanitize_filename(doc.get("doc_name", "document"))
                        doc_date = doc.get("doc_filed", "").replace("/", "-")
                        base_name = f"{doc_name}_{doc_date}" if doc_date else doc_name

                        # Handle duplicates: append _1, _2, etc.
                        if base_name in name_counter:
                            name_counter[base_name] += 1
                            file_name = f"{base_name}_{name_counter[base_name]}.pdf"
                        else:
                            name_counter[base_name] = 0
                            file_name = f"{base_name}.pdf"

                        save_path = self.download_dir / person_name / file_name
                        success = await self._download_document(uuid_val, save_path)
                        doc_entry["downloaded"] = success
                        if success:
                            doc_entry["local_path"] = str(save_path)
                        await asyncio.sleep(0.5)  # brief pause between downloads

                docs_with_urls.append(doc_entry)

            # Build single flat row with all data
            self.cases.append({
                "court": court,
                "file_number": file_num,
                "file_history_url": file_history_url,
                "file_date": row.get("file_date", ""),
                "file_name": row.get("file_name", ""),
                "proceeding": row.get("proceeding", info.get("proceeding", "")),
                "dod": row.get("dod", ""),
                "estate_closed": info.get("estate_closed", ""),
                "disposed": info.get("disposed", ""),
                "letters": info.get("letters", ""),
                "letters_issued": info.get("letters_issued", ""),
                "estate_attorney": info.get("estate_attorney", ""),
                "estate_attorney_firm": info.get("estate_attorney_firm", ""),
                "judge": info.get("judge", ""),
                "parties": json.dumps(parties_list) if parties_list else "",
                "documents": json.dumps(docs_with_urls) if docs_with_urls else "",
                "document_count": len(docs_with_urls),
                "related_files": json.dumps(related) if related else "",
            })

            downloaded_count = sum(1 for d in docs_with_urls if d.get("downloaded"))
            log.info("    -> %d parties, %d docs, %d related, %d downloaded",
                     len(parties_list), len(docs_with_urls), len(related), downloaded_count)

            # Navigate back to results for next click
            if i < total - 1:
                await self._page.evaluate("window.history.back()")
                await self._wait_for_navigation()

    # -- bulk helpers ------------------------------------------------------
    async def bulk_file_search_by_info(
        self, courts: list[str], proceeding: str,
        from_date: str, to_date: str,
        chunk_days: int = 30, deep: bool = False,
    ):
        start = date.fromisoformat(from_date)
        end = date.fromisoformat(to_date)
        for court in courts:
            log.info("=== Bulk: %s ===", court)
            current = start
            while current <= end:
                chunk_end = min(current + timedelta(days=chunk_days - 1), end)
                f = current.strftime("%m/%d/%Y")
                t = chunk_end.strftime("%m/%d/%Y")
                log.info("  %s — %s", f, t)
                try:
                    await self.file_search_by_info(court, proceeding, f, t, deep=deep)
                except Exception as e:
                    log.error("  ERROR: %s", e)
                current = chunk_end + timedelta(days=1)

    # -- output ------------------------------------------------------------
    def save(self, basename: str = "results"):
        OUTPUT_DIR.mkdir(exist_ok=True)

        # Shallow search results (always saved)
        if self.search_results:
            path = OUTPUT_DIR / f"{basename}_search.csv"
            keys = [k for k in self.search_results[0].keys() if k != "btn_value"]
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
                w.writeheader()
                w.writerows(self.search_results)
            log.info("Saved %d search results -> %s", len(self.search_results), path)

        # Deep scrape: single flat CSV with all data per file
        if self.cases:
            path = OUTPUT_DIR / f"{basename}_deep.csv"
            keys = list(self.cases[0].keys())
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                w.writerows(self.cases)
            log.info("Saved %d files (deep) -> %s", len(self.cases), path)

        # Full JSON with everything
        path = OUTPUT_DIR / f"{basename}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "search_results": self.search_results,
                    "cases": self.cases,
                },
                f, indent=2, ensure_ascii=False,
            )
        log.info("Saved -> %s", path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="NY Surrogate's Court Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Shallow
  python scraper.py --search-type file_info --courts Kings \\
      --proceeding "PROBATE PETITION" --from-date 2025-01-01 --to-date 2025-01-31

  # Deep (full file history + documents)
  python scraper.py --search-type file_info --courts Kings --deep \\
      --proceeding "PROBATE PETITION" --from-date 2025-01-01 --to-date 2025-01-31

  # Deep + Download PDFs (saves to output/downloads/{person_name}/)
  python scraper.py --search-type file_info --courts Kings --deep --download \\
      --proceeding "PROBATE PETITION" --from-date 2025-01-01 --to-date 2025-01-31

  # Headless for servers (use Xvfb on Linux)
  python scraper.py --headless --search-type name_person --courts "New York" \\
      --last-name Smith --deep
""",
    )

    parser.add_argument("--search-type", required=True, choices=[
        "name_person", "name_org", "file_number", "file_info",
    ])
    parser.add_argument("--courts", nargs="+", required=True)
    parser.add_argument("--deep", action="store_true")

    parser.add_argument("--last-name", type=str)
    parser.add_argument("--first-name", type=str)
    parser.add_argument("--organization", type=str)
    parser.add_argument("--from-date", type=str, help="YYYY-MM-DD")
    parser.add_argument("--to-date", type=str)
    parser.add_argument("--death-from-date", type=str)
    parser.add_argument("--death-to-date", type=str)
    parser.add_argument("--file-from-date", type=str)
    parser.add_argument("--file-to-date", type=str)
    parser.add_argument("--file-number", type=str)
    parser.add_argument("--proceeding", type=str)
    parser.add_argument("--chunk-days", type=int, default=30)

    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--download", action="store_true",
                        help="Download document PDFs (requires --deep)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit to N files for deep scrape (0=all)")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--output", type=str, default="results")

    args = parser.parse_args()

    if args.download and not args.deep:
        parser.error("--download requires --deep")

    async with WebSurrogateScraper(
        headless=args.headless,
        request_delay=args.delay,
        download=args.download,
    ) as s:
        s.limit = args.limit

        st = args.search_type
        deep = args.deep
        courts = args.courts

        if st == "name_person":
            if not args.last_name:
                parser.error("--last-name required")
            for c in courts:
                await s.name_search_person(
                    c, args.last_name, args.first_name,
                    args.death_from_date, args.death_to_date, deep=deep,
                )

        elif st == "name_org":
            if not args.organization:
                parser.error("--organization required")
            for c in courts:
                await s.name_search_organization(
                    c, args.organization, args.file_from_date,
                    args.file_to_date, deep=deep,
                )

        elif st == "file_number":
            if not args.file_number:
                parser.error("--file-number required")
            for c in courts:
                await s.file_search_by_number(c, args.file_number, deep=deep)

        elif st == "file_info":
            if not args.proceeding or not args.from_date:
                parser.error("--proceeding and --from-date required")
            to = args.to_date or args.from_date
            await s.bulk_file_search_by_info(
                courts, args.proceeding, args.from_date, to,
                args.chunk_days, deep=deep,
            )

        s.save(args.output)
        log.info("Done. %d search results, %d cases, %d documents",
                 len(s.search_results), len(s.cases), len(s.documents))


if __name__ == "__main__":
    asyncio.run(main())
