# PFF Data Scraper — Setup

## Prerequisites

- Active PFF Premium subscription
- Google Chrome (for cookie extraction)

## Cookie Setup

The scraper authenticates using your PFF session cookie. You need to extract it from Chrome and save it to a config file.

### Step 1: Log into PFF

1. Open Chrome and navigate to https://premium.pff.com
2. Log in with your PFF Premium credentials

### Step 2: Extract the Cookie

1. Open Chrome DevTools (Cmd+Option+I on macOS, F12 on Windows)
2. Go to the **Network** tab
3. Click on any page within premium.pff.com (e.g., a game report)
4. In the Network tab, click on any request to `premium.pff.com`
5. In the request headers, find the `Cookie` header
6. Copy the **entire value** of the Cookie header

### Step 3: Save the Cookie

Create the file `~/.fantasy-sim/pff/.env` and paste the cookie value:

```
PFF_COOKIE=paste_your_cookie_value_here
```

To create the directory and file:

```bash
mkdir -p ~/.fantasy-sim/pff
echo "PFF_COOKIE=your_cookie_here" > ~/.fantasy-sim/pff/.env
```

Then open `~/.fantasy-sim/pff/.env` in your editor and replace `your_cookie_here` with the actual cookie value.

### Cookie Expiration

PFF session cookies expire periodically. If the scraper reports a 401/403 error, repeat the extraction steps above to get a fresh cookie.

## Usage

```bash
# Scrape a full season
uv run python scripts/scrape_pff.py --season 2024

# Scrape specific weeks (mid-season)
uv run python scripts/scrape_pff.py --season 2026 --weeks 1-8

# Scrape a single week
uv run python scripts/scrape_pff.py --season 2026 --weeks 12

# Re-process existing raw data into parquet (no network)
uv run python scripts/scrape_pff.py --season 2024 --process-only

# Custom rate limit delay (default 0.3s)
uv run python scripts/scrape_pff.py --season 2024 --delay 0.5
```
