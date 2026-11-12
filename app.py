"""SiteScout backend: crawls a website and extracts pages, services, purpose and contact info."""
import ipaddress
import re
import socket
from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request

app = Flask(__name__, static_folder="static", static_url_path="")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SiteScout/1.0)"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<![\w/])\+?\(?\d[\d\s().-]{8,17}\d(?!\w)")
SOCIAL_HOSTS = ("facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com",
                "youtube.com", "tiktok.com", "github.com", "wa.me", "whatsapp.com", "t.me")
SKIP_EXT = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".pdf", ".zip", ".mp4",
            ".mp3", ".css", ".js", ".ico", ".xml", ".doc", ".docx", ".xls", ".xlsx")
SERVICE_WORDS = ("service", "solution", "product", "what-we-do", "offering", "feature",
                 "pricing", "program", "course", "treatment", "capabilit")
PRIORITY_WORDS = SERVICE_WORDS + ("contact", "about", "support")


def normalize(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url


def is_public_host(host: str) -> bool:
    """Basic protection so the tool can't be pointed at internal network addresses."""
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        return True
    except (socket.gaierror, ValueError):
        return False


def host_key(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def fetch(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
            return None
        r.encoding = r.apparent_encoding if r.encoding in (None, "ISO-8859-1") else r.encoding
        return r.url, BeautifulSoup(r.text, "html.parser")
    except requests.RequestException:
        return None


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def meta(soup, *names):
    for n in names:
        tag = soup.find("meta", attrs={"name": n}) or soup.find("meta", attrs={"property": n})
        if tag and tag.get("content"):
            return clean(tag["content"])
    return ""


def first_paragraph(soup, min_len=60):
    for p in soup.find_all("p"):
        t = clean(p.get_text())
        if len(t) >= min_len:
            return t[:400]
    return ""


def extract_page(url, soup):
    """Pull the useful parts out of one page (before removing scripts/styles)."""
    emails = set(EMAIL_RE.findall(soup.get_text(" ")))
    phones, socials, addresses = set(), set(), set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            emails.add(href[7:].split("?")[0].strip())
        elif href.lower().startswith("tel:"):
            phones.add(clean(href[4:]))
        else:
            full = urljoin(url, href)
            if any(h in urlparse(full).netloc.lower() for h in SOCIAL_HOSTS):
                socials.add(urldefrag(full)[0])
    for tag in soup.find_all("address"):
        addresses.add(clean(tag.get_text(" "))[:200])

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = clean(soup.get_text(" "))
    for m in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", m)
        if 9 <= len(digits) <= 15 and not re.match(r"^(19|20)\d{2}", digits):
            phones.add(clean(m))

    headings = [clean(h.get_text()) for h in soup.find_all(["h1", "h2", "h3"])]
    return {
        "url": url,
        "title": clean(soup.title.get_text()) if soup.title else "",
        "description": meta(soup, "description", "og:description"),
        "headings": [h for h in headings if 2 < len(h) < 120][:12],
        "words": len(text.split()),
        "summary": first_paragraph(soup),
        "emails": {e.lower() for e in emails},
        "phones": phones,
        "socials": socials,
        "addresses": addresses,
    }


def crawl(start_url: str, max_pages: int):
    start_url = normalize(start_url)
    base = host_key(start_url)
    queue, seen, pages = deque([start_url]), {start_url.rstrip("/")}, []
    while queue and len(pages) < max_pages:
        url = queue.popleft()
        got = fetch(url)
        if not got:
            continue
        final_url, soup = got
        links = []
        for a in soup.find_all("a", href=True):
            full = urldefrag(urljoin(final_url, a["href"]))[0]
            p = urlparse(full)
            if p.scheme not in ("http", "https") or host_key(full) != base:
                continue
            if p.path.lower().endswith(SKIP_EXT) or full.rstrip("/") in seen:
                continue
            seen.add(full.rstrip("/"))
            links.append((full, clean(a.get_text())))
        page = extract_page(final_url, soup)
        page["nav_links"] = links
        pages.append(page)
        for full, _ in links:  # important pages go to the front of the queue
            if any(w in full.lower() for w in PRIORITY_WORDS):
                queue.appendleft(full)
            else:
                queue.append(full)
    return pages


def build_report(start_url, pages):
    home = pages[0]
    purpose = home["description"] or home["summary"]
    about = next((p for p in pages if "about" in p["url"].lower() and p["summary"]), None)

    services, seen = [], set()
    for p in pages:
        if any(w in p["url"].lower() for w in SERVICE_WORDS):
            name = re.split(r"\s[|\-–—]\s", p["title"])[0] or p["url"]
            items = [h for h in p["headings"] if h.lower() != name.lower()][:8]
            if name.lower() not in seen:
                seen.add(name.lower())
                services.append({"name": name, "url": p["url"], "details": items,
                                 "description": p["description"] or p["summary"]})
    for text, url in {(t, u) for p in pages[:1] for u, t in p["nav_links"]}:
        if text and 2 < len(text) < 50 and any(w in (url + text).lower() for w in SERVICE_WORDS) \
                and text.lower() not in seen:
            seen.add(text.lower())
            services.append({"name": text, "url": url, "details": [], "description": ""})

    contact = {k: sorted(set().union(*(p[k] for p in pages))) for k in
               ("emails", "phones", "socials", "addresses")}
    contact["pages"] = [p["url"] for p in pages if "contact" in p["url"].lower()]

    return {
        "site": {"url": start_url, "domain": host_key(start_url), "title": home["title"],
                 "purpose": purpose, "about": about["summary"] if about else ""},
        "pages": [{k: p[k] for k in ("url", "title", "description", "headings", "words")}
                  for p in pages],
        "services": services,
        "contact": contact,
    }


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.post("/api/scrape")
def scrape():
    data = request.get_json(silent=True) or {}
    raw = (data.get("url") or "").strip()
    if not raw:
        return jsonify(error="Enter a website address."), 400
    url = normalize(raw)
    host = urlparse(url).hostname
    if not host or "." not in host:
        return jsonify(error="That doesn't look like a valid website address."), 400
    if not is_public_host(host):
        return jsonify(error="Could not resolve that address, or it points to a private network."), 400
    try:
        max_pages = max(1, min(int(data.get("max_pages", 10)), 30))
    except (TypeError, ValueError):
        max_pages = 10

    pages = crawl(url, max_pages)
    if not pages:
        return jsonify(error="The site could not be reached or blocked the request."), 502
    return jsonify(build_report(url, pages))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
