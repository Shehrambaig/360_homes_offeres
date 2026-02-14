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
    ABE J RIEDER/
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
| `file_name` | `ABE J RIEDER` | Decedent / party name |
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

### Cloudflare Bypass

- **nodriver** launches Chrome with anti-detection flags (no `navigator.webdriver`, randomized fingerprint)
- Cloudflare Turnstile challenge solves automatically (~2-4s)
- The viewer domain (`iapps.courts.state.ny.us`) has its own Cloudflare — first document takes ~10s, subsequent ones are instant (cookie cached)

### hCaptcha Automation

- The hCaptcha checkbox is inside a cross-origin iframe — standard DOM access doesn't work
- Uses **CDP `Input.dispatchMouseEvent`** to click at the iframe's viewport coordinates
- Finds iframe position via `getBoundingClientRect()`, clicks at (left + 28, top + height/2)

### PDF Download

- Document UUID buttons submit a form that opens a viewer at `iapps.courts.state.ny.us`
- The viewer serves a raw PDF (Chrome's native PDF viewer renders it)
- Chrome's PDF viewer toolbar is **not in the DOM** — can't click the download button
- Solution: `fetch(window.location.href)` from the viewer tab, get PDF as base64 blob, save to Python
- **Batch mode**: All document tabs for a file are opened at once, Cloudflare clears once, then all PDFs are fetched — much faster than sequential

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
