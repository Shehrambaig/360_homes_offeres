# NY Surrogate's Court WebSurrogate Scraper

Automated scraper for the [NY Surrogate's Court WebSurrogate](https://websurrogates.nycourts.gov) site. Handles Cloudflare bypass, hCaptcha automation, search form submission, deep file history extraction, and bulk PDF download.

## Architecture

```
nodriver (undetected Chrome)     Drives all browser interactions
        |                        Bypasses Cloudflare + hCaptcha automatically
        v
  websurrogates.nycourts.gov     Search forms, results, file history pages
        |
        v
  lxml + cssselect               Parses HTML from page source (fast, no regex)
        |
        v
  iapps.courts.state.ny.us       Document viewer (raw PDF behind Cloudflare)
        |
        v
  output/                        CSV, JSON, downloaded PDFs
```

## Requirements

```
pip install nodriver lxml cssselect
```

Or: `pip install -r requirements.txt`

Python 3.12+

## Quick Start

```bash
# Basic search (shallow — just the results table)
python scraper.py --search-type file_info --courts Kings \
    --proceeding "PROBATE PETITION" --from-date 2025-01-01 --to-date 2025-01-31

# Deep scrape (clicks into each file, extracts full history)
python scraper.py --search-type file_info --courts Kings --deep \
    --proceeding "PROBATE PETITION" --from-date 2025-01-01 --to-date 2025-01-31

# Deep + download all PDFs
python scraper.py --search-type file_info --courts Kings --deep --download \
    --proceeding "PROBATE PETITION" --from-date 2025-01-01 --to-date 2025-01-30

# Test with just 1 file
python scraper.py --search-type file_info --courts Kings --deep --download --limit 1 \
    --proceeding "PROBATE PETITION" --from-date 2025-01-01 --to-date 2025-01-30
```

## CLI Reference

### Required Arguments

| Argument | Description |
|---|---|
| `--search-type` | One of: `file_info`, `file_number`, `name_person`, `name_org` |
| `--courts` | One or more court names (e.g., `Kings`, `"New York"`, `Bronx Queens`) |

### Search Parameters

| Argument | Used with | Description |
|---|---|---|
| `--proceeding` | `file_info` | Proceeding type (e.g., `"PROBATE PETITION"`) |
| `--from-date` | `file_info` | Start date (`YYYY-MM-DD`) |
| `--to-date` | `file_info` | End date (`YYYY-MM-DD`, defaults to `--from-date`) |
| `--file-number` | `file_number` | Specific file number (e.g., `2025-267`) |
| `--last-name` | `name_person` | Last name to search |
| `--first-name` | `name_person` | First name (optional) |
| `--organization` | `name_org` | Organization name |
| `--death-from-date` | `name_person` | DOD range start |
| `--death-to-date` | `name_person` | DOD range end |
| `--file-from-date` | `name_org` | File date range start |
| `--file-to-date` | `name_org` | File date range end |
| `--chunk-days` | `file_info` | Days per search chunk for bulk (default: 30) |

### Mode Flags

| Flag | Description |
|---|---|
| `--deep` | Click into each file to extract full File History (parties, documents, related files) |
| `--download` | Download all document PDFs (requires `--deep`) |
| `--limit N` | Only process first N files in deep scrape (0 = all, useful for testing) |
| `--headless` | Run Chrome in headless mode (needs Xvfb on servers, see below) |

### Other Options

| Option | Default | Description |
|---|---|---|
| `--delay` | `1.0` | Seconds between requests |
| `--profile` | `.browser_profile/` | Persistent Chrome profile directory (reuses cookies across runs) |
| `--output` | `results` | Output file basename |

## Output Structure

```
output/
  results_search.csv      Shallow search results (one row per file)
  results_deep.csv        Deep scrape results (one row per file, JSON columns)
  results.json            Full JSON with all data
  downloads/
    {file_name_here}/
      PROBATE PETITION_01-17-2025.pdf
      WAIVER AND CONSENT_01-17-2025.pdf
      WAIVER AND CONSENT_01-17-2025_1.pdf    (duplicate name gets _1 suffix)
      WILL OF TESTATOR_01-17-2025.pdf
      ...
    CINDY SUE RABINOWITZ/
      ...
```

### results_search.csv (Shallow)

One row per search result. Columns:

| Column | Example | Description |
|---|---|---|
| `file_num` | `2025-267` | Court file number |
| `file_date` | `01/17/2025` | Filing date |
| `file_name` | `Name` | Decedent / party name |
| `proceeding` | `PROBATE PETITION` | Proceeding type |
| `dod` | `09/18/2024` | Date of death |
| `court` | `Kings` | Court name |

### results_deep.csv (Deep)

One row per file with all extracted data. Columns:

| Column | Type | Description |
|---|---|---|
| `court` | string | Court name |
| `file_number` | string | File number |
| `file_history_url` | string | URL of the File History page |
| `file_date` | string | Filing date |
| `file_name` | string | Decedent name |
| `proceeding` | string | Proceeding type |
| `dod` | string | Date of death |
| `estate_closed` | string | Estate closed (Y/N) |
| `disposed` | string | Disposition date |
| `letters` | string | Letters type (e.g., LETTERS TESTAMENTARY) |
| `letters_issued` | string | Letters issued date |
| `estate_attorney` | string | Attorney name |
| `estate_attorney_firm` | string | Attorney firm |
| `judge` | string | Judge name |
| `parties` | JSON | Array of `{party, role, dod, appointed, active}` |
| `documents` | JSON | Array of document objects (see below) |
| `document_count` | int | Total documents for this file |
| `related_files` | JSON | Array of related file numbers |

### Document Object (inside `documents` JSON column)

Each document in the JSON array has:

| Field | Type | Description |
|---|---|---|
| `doc_name` | string | Document name (e.g., `"PROBATE PETITION"`) |
| `comments` | string | Comments field |
| `qty` | string | Quantity |
| `doc_filed` | string | Date filed |
| `signed_date` | string | Date signed (if applicable) |
| `uuid` | string | Document UUID (empty if no link) |
| `has_link` | bool | Whether document has a viewable PDF |
| `viewer_url` | string | URL to view the document |
| `downloaded` | bool | Whether PDF was downloaded |
| `local_path` | string | Local file path of downloaded PDF (only if downloaded) |

### results.json

Full JSON containing both `search_results` and `cases` arrays with all the same data.

## How It Works

### Page Flow

```
1. websurrogates.nycourts.gov        (Cloudflare challenge — auto-bypassed)
       |
2. /Home/Welcome                      Click "Start Search" button
       |
3. /Home/AuthenticatePage             hCaptcha checkbox + search type buttons
       |                              (hCaptcha auto-solved via CDP mouse events)
       |
4. /File/FileSearch                   Fill form: court, proceeding, dates
       |                              Submit via FileSearchSubmit button
       |
5. Search Results table               Parse results, click each file number
       |
6. /File/FileHistory                  Extract all info, parties, documents
       |                              For each document with UUID:
       |                              Submit form → opens viewer in new tab
       |
7. iapps.courts.state.ny.us/viewer   Raw PDF (Cloudflare on this domain too)
                                      fetch() the PDF, save to disk
```

---

## Technical Deep Dive: Challenges & Solutions

### 1. Passing Cloudflare Protections

**The problem:** Both `websurrogates.nycourts.gov` and the document viewer at `iapps.courts.state.ny.us` sit behind Cloudflare Turnstile. Standard HTTP libraries (requests, httpx, even curl_cffi with Chrome TLS impersonation) are blocked because Cloudflare ties its `cf_clearance` cookie to the browser's TLS fingerprint — no library can replicate Chrome's exact fingerprint.

**What we tried and failed:**
- **httpx with extracted cookies** — 403 Forbidden. Cloudflare detected the TLS fingerprint mismatch.
- **curl_cffi with Chrome impersonation** — Still 403. Even with `impersonate="chrome"`, the TLS handshake differs enough for Cloudflare to reject it.

**What works:**
- **nodriver** (the successor to undetected-chromedriver) launches a real Chrome instance with anti-detection patches:
  - Removes `navigator.webdriver` flag
  - Randomizes browser fingerprint attributes
  - Uses a real Chrome binary — identical TLS fingerprint to a normal user
- Cloudflare Turnstile solves automatically in ~2-4 seconds with zero human interaction
- The scraper waits in a polling loop checking `document.body.innerText` for known page landmarks (`"Start Search"`, `"I am human"`, `"File Search"`) to know when the challenge has passed

**Two Cloudflare domains:**
- The main site clears on first page load
- The document viewer (`iapps.courts.state.ny.us`) has its own Cloudflare. The scraper polls `fetch(window.location.href)` on the viewer tab, checking the response `Content-Type` header — when it flips from `text/html` (Cloudflare challenge page) to `application/pdf` (the actual document), Cloudflare has cleared. First document takes ~10s; all subsequent documents are instant because the `cf_clearance` cookie is cached in the browser session.

**Headless detection:** Cloudflare detects headless Chrome even with nodriver's patches. True headless mode fails. The solution for servers is Xvfb (virtual framebuffer) which runs a headed Chrome without a physical display — Cloudflare sees a normal browser.

### 2. Solving hCaptcha

**The problem:** After Cloudflare, the site presents an hCaptcha "I am human" checkbox on `/Home/AuthenticatePage`. The checkbox is inside a **cross-origin iframe** (`newassets.hcaptcha.com`), which means:
- `document.querySelector()` can't reach inside the iframe (same-origin policy)
- nodriver can't connect to the iframe's target directly (WebSocket 404 error)
- Standard `element.click()` doesn't work across iframe boundaries

**What we tried and failed:**
- **Finding the iframe target via CDP** — nodriver returned a WebSocket 404 when trying to connect to the hCaptcha iframe's target ID
- **Evaluating JS inside the iframe** — Blocked by cross-origin policy

**What works:**
- **CDP `Input.dispatchMouseEvent`** operates at the viewport level, not the DOM level — it sends raw mouse events to the browser at specific screen coordinates, reaching into any iframe regardless of origin
- The scraper uses `JSON.stringify()` + `getBoundingClientRect()` to find the hCaptcha iframe's position on the page (nodriver's `evaluate()` returns raw CDP objects, not plain dicts — we learned to always wrap in `JSON.stringify()` and `json.loads()` the result)
- Mouse event sequence simulates a real click: `mouseMoved` → `mousePressed` → `mouseReleased` at coordinates `(iframe.left + 28, iframe.top + height/2)` — the exact position of the checkbox within the hCaptcha widget
- After clicking, the green checkmark appears. The scraper waits 3 seconds and proceeds — it does **not** wait for page navigation (the hCaptcha solves in-place on the same page)
- Then it clicks the "File Search" button (id=`FileSearch`) on the same AuthenticatePage to proceed to the search form

**Fallback:** If the checkbox click triggers an image challenge (rare), the scraper falls back to a 3-minute manual solve window — the user can solve it in the visible browser, and the scraper detects when the page state changes.

### 3. Writing Clean, Stable Selectors

**The problem:** The site uses ASP.NET MVC with dynamically loaded form fields. Initial attempts used incorrect field IDs (`CourtId`, `FileProceedingId`, `FileNum`) that didn't match the actual DOM.

**How we discovered the correct selectors:**
- Ran debug scripts that dumped all form elements, select options, and button attributes from the live page
- Mapped every form field by `id`, `name`, and `value` attributes

**Actual form field mapping (discovered via debugging):**

| What | Wrong (initial guess) | Correct (actual DOM) |
|---|---|---|
| Court dropdown | `id="CourtId"` | `id="CourtSelect"`, `name="CourtIDasString"` |
| Proceeding dropdown | `id="FileProceedingId"` | `id="SelectedProceeding"`, `name="SelectedProceeding"` |
| File number input | `name="FileNum"` | `name="FileNumber"`, `id="FileNumber"` |
| Date from | `name="FromDate"` | `name="FromDateString"`, `id="txtFilingDateFrom"` |
| Date to | `name="ToDate"` | `name="ToDateString"`, `id="txtFilingDateTo"` |
| Submit button | generic submit | `id="FileSearchSubmit"` |
| Search option buttons | — | `id="FileSearch"`, `id="NameSearch"`, etc. |
| Welcome button | — | `id="StartSearchButton"` inside `form#WelcomePageForm` |

**Dynamic dropdown loading:** The Proceeding dropdown (`#SelectedProceeding`) loads its options dynamically via AJAX after a court is selected. The scraper waits in a polling loop, checking `extract_select_options("SelectedProceeding")` until more than 1 option appears. Proceeding values are the **full text names** themselves (e.g., `"PROBATE PETITION"`), not numeric IDs.

**Document UUID buttons:** Documents on the File History page use `<button name="UUIDValue" value="uuid-here">`. Clicking them submits the `#FHForm` form. Rather than finding and clicking the specific button (which failed due to timing/DOM issues), the scraper injects a hidden input and submits the form directly:

```javascript
var form = document.getElementById('FHForm');
var inp = document.createElement('input');
inp.type = 'hidden'; inp.name = 'UUIDValue'; inp.value = uuid;
form.appendChild(inp);
form.target = '_blank';  // Force new tab
form.submit();
form.removeChild(inp);   // Clean up
form.target = '';         // Restore
```

This is more reliable than `querySelector` button matching because it works regardless of DOM readiness or rendering state.

**Search results table:** Parsed via `#NameResultsTable tbody tr` with `button[name='button'], button.ButtonAsLink` for file number links.

### 4. Proper Session and Cookie Management

**The problem:** The site uses ASP.NET anti-forgery tokens (`__RequestVerificationToken`) and session cookies. Sessions expire, Cloudflare cookies expire, and stale cookies cause a "Request Could Not Be Processed" error page instead of a clean redirect.

**Persistent browser profile:**
- Chrome's user data directory is set to `.browser_profile/` (configurable via `--profile`)
- All cookies, local storage, and session state persist across scraper runs
- On startup, the scraper checks the page state to decide what to skip:
  - If landed on `/File/` or `/Names/` URL → session fully valid, skip everything
  - If on Search Options page → session valid but need to click search type
  - If "Start Search" or "I am human" → need to re-authenticate
  - If "Request Could Not Be Processed" → stale session detected

**Stale session auto-recovery:**
- Detected by checking `document.body.innerText` for `"Request Could Not Be Processed"` or `"support ID"`
- When detected, the scraper clears all cookies via CDP (`network.clear_browser_cookies()`), navigates back to the base URL, and re-runs the full authentication flow (Welcome → hCaptcha → File Search)
- This happens both at startup and mid-session (in the `_navigate()` method) so the scraper self-heals if a session expires during a long bulk run

**Anti-forgery tokens:**
- Extracted from the page HTML via `lxml.cssselect('input[name="__RequestVerificationToken"]')`
- Included in all form submissions automatically (the real browser handles this natively since we submit forms through the DOM, not via HTTP)

**Viewer domain cookies:**
- `iapps.courts.state.ny.us` has separate Cloudflare cookies
- The scraper tracks whether the viewer Cloudflare has cleared via the `_viewer_cf_cleared` flag
- First document: polls content-type for up to 60 seconds
- Subsequent documents: only waits 15 seconds (cookie already cached)

### 5. Correctly Downloading and Saving PDF Files

**The problem:** Clicking a document UUID button opens a viewer page at `iapps.courts.state.ny.us/vscms_public/viewer?token=...`. This page serves a **raw PDF** (`Content-Type: application/pdf`), and Chrome's built-in PDF viewer plugin renders the toolbar (download button, print button, page controls). However:
- The PDF viewer toolbar is rendered by a **native Chrome plugin process** — it is not part of the page DOM at all
- `document.querySelectorAll('button')` returns zero results on the viewer page
- No automation tool (Selenium, Playwright, nodriver) can find or click the download button
- `fetch()` from the main site fails with CORS error because the viewer is on a different domain

**What we tried and failed:**
- **Clicking the download button** — Button doesn't exist in the DOM (native plugin)
- **`fetch()` from the File History page** — Cross-origin request blocked (`websurrogates.nycourts.gov` → `iapps.courts.state.ny.us`)
- **Immediate `fetch()` on the viewer tab** — Got the Cloudflare challenge HTML (8527 bytes, `text/html`) instead of the PDF because Cloudflare hadn't cleared yet

**What works — the three-step solution:**

**Step 1: Open viewer tabs via form injection.** Instead of finding and clicking individual UUID buttons (which failed due to DOM timing issues), the scraper injects a hidden input into `#FHForm`, sets `form.target = "_blank"`, and submits — this reliably opens a new tab to the viewer URL every time. For batch download, all tabs for a file are opened at once (~0.3s per tab).

**Step 2: Wait for Cloudflare on the viewer domain.** The scraper polls the viewer tab with `fetch(window.location.href)` and checks the response's `Content-Type` header. The Cloudflare challenge page returns `text/html`; when it flips to `application/pdf`, the challenge has passed and the real PDF is available. First document: ~10s. All subsequent: instant.

**Step 3: Fetch the PDF via JavaScript.** Once Cloudflare clears, the scraper runs `fetch(window.location.href)` on the viewer tab (same-origin now since we're on the viewer tab itself). The response blob is converted to base64 via `FileReader.readAsDataURL()`, passed back to Python through `evaluate()`, decoded with `base64.b64decode()`, and written to disk.

**Batch download optimization:**
- Sequential download (old): Open tab → wait CF → fetch → close → repeat. ~12s per document.
- Batch download (current): Open ALL tabs at once → wait CF once → fetch all → close all. For a file with 15 linked documents: ~20s total instead of ~3 minutes.

**File naming:**
- PDFs saved to `output/downloads/{PERSON_NAME}/{DOC_NAME}_{DATE}.pdf`
- Person name comes from the search results `file_name` field (e.g., `file_name`)
- Unsafe filename characters (`/`, `:`, `*`, etc.) replaced with underscores
- Duplicate names on the same date get `_1`, `_2` suffixes (e.g., `WAIVER AND CONSENT_01-17-2025.pdf`, `WAIVER AND CONSENT_01-17-2025_1.pdf`)
- Local file paths recorded in the `documents` JSON column as `local_path` for cross-referencing with the CSV

---

## Persistent Browser Profile

The scraper saves Chrome cookies/session in `.browser_profile/` by default. This means:

- **Headed runs** reuse Cloudflare cookies — subsequent runs may skip the challenge entirely
- **Cross-run sessions** — if the session is still valid, the scraper skips Welcome page + hCaptcha

If you get "Request Could Not Be Processed" errors (stale session), the scraper auto-detects this and clears cookies. You can also manually reset:

```bash
rm -rf .browser_profile
```

## Server Deployment

Headless Chrome is detected by Cloudflare. For servers use **Xvfb** (virtual framebuffer):

```bash
# Install once
sudo apt install xvfb

# Run with virtual display — Chrome thinks it's headed
xvfb-run python scraper.py --search-type file_info --courts Kings --deep --download \
    --proceeding "PROBATE PETITION" --from-date 2025-01-01 --to-date 2025-01-30
```

## Available Courts (62)

Albany, Allegany, Bronx, Broome, Cattaraugus, Cayuga, Chautauqua, Chenango, Clinton, Columbia, Cortland, Delaware, Dutchess, Erie, Essex, Franklin, Fulton, Genesee, Greene, Herkimer, Jefferson, Kings, Lewis, Livingston, Madison, Monroe, Montgomery, Nassau, New York, Niagara, Oneida, Onondaga, Ontario, Orange, Orleans, Oswego, Otsego, Putnam, Queens, Rensselaer, Richmond, Rockland, Saratoga, Schenectady, Schoharie, Schuyler, Seneca, St Lawrence, Steuben, Suffolk, Sullivan, Tioga, Tompkins, Ulster, Warren, Washington, Wayne, Westchester, Wyoming, Yates

## Project Files

```
scraper.py              Main scraper (1500 lines)
requirements.txt        Python dependencies (nodriver, lxml, cssselect)
.browser_profile/       Persistent Chrome profile (gitignored)
output/                 All output files
  results_search.csv    Shallow search results
  results_deep.csv      Deep scrape with all data
  results.json          Full JSON output
  downloads/            Downloaded PDFs organized by person name
```
