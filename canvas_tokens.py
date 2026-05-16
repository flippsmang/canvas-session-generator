#!/usr/bin/env python3
"""
canvas_tokens.py

Opens a browser window so you can log in to your Canvas instance (including SSO
and MFA), then extracts the session cookie and CSRF token once login is detected.
Prints the tokens to stdout in a format ready to paste into curl, Python requests,
or any other HTTP client.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# Canvas sets the session in this cookie name
SESSION_COOKIE_NAME = "canvas_session"
CSRF_COOKIE_NAME = "_csrf_token"

def normalise_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def extract_csrf_from_meta(page) -> str | None:
    """Pull the CSRF token from the Canvas <meta name='csrf-token'> tag."""
    try:
        token = page.get_attribute('meta[name="csrf-token"]', "content", timeout=2000)
        return token
    except Exception:
        return None


def get_tokens(canvas_url: str, timeout_minutes: int, browser_type: str) -> dict:
    base_url = normalise_url(canvas_url)
    canvas_hostname = urlparse(base_url).netloc
    login_url = f"{base_url}/login"
    timeout_ms = timeout_minutes * 60 * 1000

    print(f"\nOpening browser → {login_url}")
    print(f"You have {timeout_minutes} minute(s) to log in. The browser will close automatically.\n")

    with sync_playwright() as p:
        launcher = getattr(p, browser_type)
        browser = launcher.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        page.goto(login_url)

        # Wait until we're genuinely logged in:
        #   1. Back on the Canvas hostname (not mid-redirect at the SSO provider)
        #   2. Not on any auth/login/saml path
        #   3. Either on a known post-login path OR the Canvas app header is in the DOM
        try:
            page.wait_for_function(
                f"""() => {{
                    const loc = new URL(window.location.href);
                    if (loc.hostname !== {json.dumps(canvas_hostname)}) return false;
                    const path = loc.pathname;
                    if (/\\/(login|auth|saml|sso|oauth|cas)/.test(path)) return false;
                    const postLoginPath = /\/(dashboard|courses|calendar|inbox|grades|profile|accounts)/.test(path);
                    const hasAppHeader = !!document.querySelector('.ic-app-header, #header, #identity');
                    return postLoginPath || hasAppHeader;
                }}""",
                timeout=timeout_ms,
            )
        except PlaywrightTimeoutError:
            browser.close()
            sys.exit(f"Timed out after {timeout_minutes} minute(s) waiting for login. Exiting.")

        # Give the page a moment to settle so cookies are fully written
        page.wait_for_timeout(1000)

        # --- Extract tokens ---
        cookies = context.cookies()
        cookie_map = {c["name"]: c["value"] for c in cookies}

        session_token = cookie_map.get(SESSION_COOKIE_NAME)
        csrf_from_cookie = cookie_map.get(CSRF_COOKIE_NAME)
        csrf_from_meta = extract_csrf_from_meta(page)

        browser.close()

    return {
        "base_url": base_url,
        "canvas_session": session_token,
        "csrf_token_cookie": csrf_from_cookie,
        "csrf_token_meta": csrf_from_meta,
        "all_cookies": cookie_map,
    }


def print_results(tokens: dict, output_format: str) -> None:
    base_url = tokens["base_url"]
    session = tokens["canvas_session"]
    csrf = tokens["csrf_token_meta"] or tokens["csrf_token_cookie"]

    if output_format == "json":
        out = {
            "base_url": base_url,
            "canvas_session": session,
            "csrf_token": csrf,
        }
        print(json.dumps(out, indent=2))
        return

    print("=" * 60)
    print("Canvas Tokens")
    print("=" * 60)

    if session:
        print(f"\n  canvas_session:\n    {session}")
    else:
        print("\n  canvas_session:  (not found — check the cookie name for your instance)")

    if csrf:
        print(f"\n  csrf_token:\n    {csrf}")
    else:
        print("\n  csrf_token:  (not found)")

    if session and csrf:
        print("\n--- curl example ---")
        print(
            f'curl -H "Cookie: canvas_session={session}" \\\n'
            f'     -H "X-CSRF-Token: {csrf}" \\\n'
            f'     "{base_url}/api/v1/courses"'
        )

        print("\n--- Python requests example ---")
        print(
            f'import requests\n\n'
            f'session = requests.Session()\n'
            f'session.cookies.set("canvas_session", "{session}")\n'
            f'session.headers["X-CSRF-Token"] = "{csrf}"\n\n'
            f'r = session.get("{base_url}/api/v1/courses")\n'
            f'print(r.json())'
        )

    print("=" * 60)


def save_env_file(tokens: dict, path: Path) -> None:
    base_url = tokens["base_url"]
    session = tokens["canvas_session"] or ""
    csrf = tokens["csrf_token_meta"] or tokens["csrf_token_cookie"] or ""

    existing: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()

    existing["CANVAS_URL"] = base_url
    existing["CANVAS_SESSION"] = session
    existing["CANVAS_CSRF_TOKEN"] = csrf

    lines = [f"{k}={v}" for k, v in existing.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nTokens saved to {path}")
    print("Load in Python with: from dotenv import load_dotenv; load_dotenv()")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract Canvas session and CSRF tokens by logging in via a browser.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "canvas_url",
        help="Your Canvas instance URL, e.g. canvas.myschool.edu",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        metavar="MINUTES",
        help="Minutes to wait for login before giving up",
    )
    parser.add_argument(
        "--browser",
        choices=["chromium", "firefox", "webkit"],
        default="chromium",
        help="Browser to open",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        dest="output_format",
        help="Output format",
    )
    parser.add_argument(
        "--all-cookies",
        action="store_true",
        help="Also dump all cookies in JSON (useful if your instance uses a different session cookie name)",
    )
    parser.add_argument(
        "--save",
        nargs="?",
        const=".env",
        metavar="FILE",
        help="Save tokens to a .env file (default: .env in current directory)",
    )

    args = parser.parse_args()

    tokens = get_tokens(args.canvas_url, args.timeout, args.browser)
    print_results(tokens, args.output_format)

    if args.all_cookies:
        print("\n--- All cookies (JSON) ---")
        print(json.dumps(tokens["all_cookies"], indent=2))

    if args.save:
        save_env_file(tokens, Path(args.save))


if __name__ == "__main__":
    main()
