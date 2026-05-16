# canvas-session-generator

Extracts your Canvas LMS session cookie and CSRF token by opening a real browser window, letting you log in (including SSO and MFA), and then capturing the tokens automatically.

## Setup

**1. Install Python dependencies**

```bash
pip install -r requirements.txt
```

**2. Install the Playwright browser binaries** (one-time, ~100 MB)

```bash
playwright install chromium
```

## Usage

```bash
python canvas_tokens.py <your-canvas-url>
```

**Examples:**

```bash
# Basic — opens Chromium, gives you 5 minutes to log in
python canvas_tokens.py canvas.myschool.edu

# More time to log in
python canvas_tokens.py canvas.myschool.edu --timeout 10

# Output as JSON (useful for scripting)
python canvas_tokens.py canvas.myschool.edu --format json

# Use Firefox instead
python canvas_tokens.py canvas.myschool.edu --browser firefox

# Save tokens to .env in the current directory
python canvas_tokens.py canvas.myschool.edu --save

# Save tokens to a specific file
python canvas_tokens.py canvas.myschool.edu --save path/to/my.env

# Verify tokens immediately with a test API call
python canvas_tokens.py canvas.myschool.edu --verify

# Dump all cookies (if your instance uses a non-standard session cookie name)
python canvas_tokens.py canvas.myschool.edu --all-cookies
```

## What it outputs

After login the script prints your `canvas_session` cookie and `csrf_token`, plus ready-to-paste **curl** and **Python requests** examples:

```
============================================================
Canvas Tokens
============================================================

  canvas_session:
    <your session token>

  csrf_token:
    <your csrf token>

--- curl example ---
curl -H "Cookie: canvas_session=..." \
     -H "X-CSRF-Token: ..." \
     "https://canvas.myschool.edu/api/v1/courses"

--- Python requests example ---
import requests

session = requests.Session()
session.cookies.set("canvas_session", "...")
session.headers["X-CSRF-Token"] = "..."

r = session.get("https://canvas.myschool.edu/api/v1/courses")
print(r.json())
============================================================
```

## Using saved tokens in your scripts

After running with `--save`, your `.env` will contain:

```
CANVAS_URL=https://canvas.myschool.edu
CANVAS_SESSION=...
CANVAS_CSRF_TOKEN=...
```

Load them in any Python script:

```python
from dotenv import load_dotenv
import os

load_dotenv()

canvas_url   = os.environ["CANVAS_URL"]
session      = os.environ["CANVAS_SESSION"]
csrf_token   = os.environ["CANVAS_CSRF_TOKEN"]
```

Install `python-dotenv` if you don't have it:

```bash
pip install python-dotenv
```

> **Tip:** Add `.env` to your `.gitignore` so tokens are never committed to source control.

## Notes

- **Token lifetime:** Session tokens expire when the server-side session ends (typically after a period of inactivity or on logout). Re-run the script when they stop working.
- **CSRF token:** Captured from the page `<meta name="csrf-token">` tag. Required for any mutating API requests (POST/PUT/DELETE). Read-only GET requests may not need it.
- **`--save` merges, not overwrites:** If a `.env` file already exists, only the three Canvas keys are updated — any other variables in the file are preserved.
- **`--verify`:** Makes a `GET /api/v1/users/self` call after extraction and prints your name and user ID if the tokens are valid. Useful for confirming everything worked, especially on first run.
- **`--all-cookies`:** If your Canvas instance uses a different session cookie name, this flag dumps every cookie so you can find the right one.
