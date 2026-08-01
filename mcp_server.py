import ipaddress
import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS
from mcp.server.fastmcp import FastMCP


ROOT = Path(__file__).resolve().parent
TRACKER = ROOT / "applications.json"
mcp = FastMCP("Scout")


@mcp.tool()
def web_search(query: str) -> str:
    """Search the live web for company facts and return five sources."""
    results = DDGS(timeout=10).text(query[:300], max_results=5)
    sources = [
        {
            "title": item.get("title", ""),
            "url": item.get("href", item.get("url", "")),
            "snippet": item.get("body", item.get("snippet", "")),
        }
        for item in results
    ]
    return json.dumps(sources, ensure_ascii=False)


def public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public http and https URLs are allowed.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    for address in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(address[4][0]).is_global:
            raise ValueError("Private and local URLs are blocked.")
    return url


@mcp.tool()
def fetch_url(url: str) -> str:
    """Extract readable text from a public job post or company page."""
    current = public_url(url)
    headers = {"User-Agent": "Scout/1.0 (job research assistant)"}

    with httpx.Client(timeout=12, follow_redirects=False, headers=headers) as client:
        for _ in range(4):
            response = client.get(current)
            if response.is_redirect:
                current = public_url(urljoin(current, response.headers["location"]))
                continue
            response.raise_for_status()
            break
        else:
            raise ValueError("Too many redirects.")

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "svg"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())
    return f"Source: {current}\n\n{text[:12_000]}"


@mcp.tool()
def get_resume() -> str:
    """Load the candidate's resume from resume.md."""
    return (ROOT / "resume.md").read_text(encoding="utf-8")


@mcp.tool()
def save_application(
    company: str,
    role: str,
    fit_score: int,
    notes: str,
) -> str:
    """Append a completed job assessment to applications.json."""
    if not 0 <= fit_score <= 100:
        raise ValueError("fit_score must be between 0 and 100.")

    applications = json.loads(TRACKER.read_text(encoding="utf-8"))
    applications.append(
        {
            "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "company": company.strip(),
            "role": role.strip(),
            "fit_score": fit_score,
            "notes": notes.strip(),
        }
    )
    TRACKER.write_text(
        json.dumps(applications, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return f"Saved {company} — {role} to applications.json."


if __name__ == "__main__":
    mcp.run(transport="stdio")
