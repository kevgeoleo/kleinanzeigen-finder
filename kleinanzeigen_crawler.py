#!/usr/bin/env python3
"""
Kleinanzeigen.de crawler: search by keywords in title/description, with optional
price range, condition (Zustand), seller type, size, color and shipping filters.

How it works (no official API is used):
  1. /s-<filters>/<keyword>/k0       -> search result pages -> listing URLs
  2. /s-anzeige/<slug>/<id>-<c>-<l>  -> each listing page: title, description, price, attributes

Install:   pip install -r requirements.txt     (curl_cffi recommended)

Examples:
  python kleinanzeigen_crawler.py -q "JBL Charge 6" -k geschenk ovp
  python kleinanzeigen_crawler.py -q "Nike Air Max" --size 42 --color Schwarz -c new very_good --max-price 80
  python kleinanzeigen_crawler.py -k defekt bastler --filter-url "https://www.kleinanzeigen.de/s-berlin/iphone-13/k0l3331r20"
"""
import argparse
import csv
import html
import json
import math
import re
import sys
import time
from urllib.parse import quote, quote_plus, urlparse, urlunparse

try:
    from curl_cffi import requests as http
    IMPERSONATE = {"impersonate": "chrome"}
except ImportError:  # fallback
    import requests as http
    IMPERSONATE = {}

BASE = "https://www.kleinanzeigen.de"

# Kleinanzeigen "Zustand" values (only available in categories that have the attribute)
CONDITIONS = {
    "new": "Neu",
    "very_good": "Sehr gut",
    "good": "Gut",
    "ok": "In Ordnung",
    "defect": "Defekt",
}

# color name -> words that count as a match in the listing's color text
COLORS = {
    "Schwarz": ["schwarz", "black"],
    "Weiß": ["weiß", "weiss", "white"],
    "Grau": ["grau", "grey", "gray"],
    "Beige/Creme": ["beige", "creme", "cream"],
    "Braun": ["braun", "brown"],
    "Rot": ["rot", "red", "bordeaux"],
    "Rosa": ["rosa", "pink"],
    "Orange": ["orange"],
    "Gelb": ["gelb", "yellow", "senf"],
    "Grün": ["grün", "gruen", "green", "khaki", "oliv"],
    "Türkis": ["türkis", "turkis", "turquoise"],
    "Blau": ["blau", "blue", "marine", "navy"],
    "Lila": ["lila", "violett", "purple"],
    "Mehrfarbig": ["mehrfarbig", "multi", "bunt"],
    "Silber": ["silber", "silver"],
    "Gold": ["gold"],
}

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}
if not IMPERSONATE:
    HEADERS["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )

# /s-anzeige/<slug>/<id>-<category>-<location>, also inside JSON-escaped strings
ITEM_RE = re.compile(r'\\?/s-anzeige\\?/([^"\'\\\s?#<>/]+)\\?/(\d{6,})-(\d+)-(\d+)')
LDJSON_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
DETAIL_LI_RE = re.compile(
    r'<li[^>]*class="[^"]*addetailslist--detail[^"]*"[^>]*>(.*?)</li>', re.S | re.I)
DETAIL_VALUE_RE = re.compile(
    r'<span[^>]*class="[^"]*addetailslist--detail--value[^"]*"[^>]*>(.*?)</span>', re.S | re.I)


# --------------------------------------------------------------------------- HTTP

class Client:
    def __init__(self, delay=1.5):
        self.delay = delay
        self.s = http.Session(**IMPERSONATE) if IMPERSONATE else http.Session()
        self.s.headers.update(HEADERS)
        self._warm_up()

    def _warm_up(self):
        r = self.s.get(BASE + "/", timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"Homepage returned HTTP {r.status_code} (blocked?)")

    def get(self, url, retries=3):
        """Return page HTML, or None if the page does not exist (404/410)."""
        last = None
        for attempt in range(retries):
            time.sleep(self.delay)
            r = self.s.get(url, timeout=30)
            last = r.status_code
            if r.status_code == 200:
                return r.text
            if r.status_code in (404, 410):
                return None
            if r.status_code in (403, 429, 503):
                time.sleep(8 * (attempt + 1))
                try:
                    self._warm_up()
                except Exception:
                    pass
                continue
            r.raise_for_status()
        raise RuntimeError(f"HTTP {last} for {url} after {retries} tries")


# --------------------------------------------------------------------------- search URLs

def slugify(query):
    return quote(re.sub(r"\s+", "-", query.strip().lower()), safe="-")


def price_segment(min_price, max_price):
    if min_price is None and max_price is None:
        return ""
    lo = "" if min_price is None else str(int(math.floor(min_price)))
    hi = "" if max_price is None else str(int(math.ceil(max_price)))
    return f"preis:{lo}:{hi}"


def build_search_url(query, page=1, min_price=None, max_price=None, offers_only=True,
                     seller="any", base_url=""):
    """Kleinanzeigen search URL. Filters are path segments:
         /s-seite:2/preis:10:50/anzeige:angebote/<keyword>/k0
    If base_url (a URL copied from the site, with location/category/etc.) is given,
    it is used as the base and only page / price / offer type / seller are rewritten."""
    filters = []
    if page and page > 1:
        filters.append(f"seite:{page}")
    ps = price_segment(min_price, max_price)
    if ps:
        filters.append(ps)
    if offers_only:
        filters.append("anzeige:angebote")
    if seller == "private":
        filters.append("anbieter:privat")
    elif seller == "commercial":
        filters.append("anbieter:gewerblich")

    if not base_url:
        return f"{BASE}/s-" + "/".join(filters + [slugify(query), "k0"])

    u = urlparse(base_url.strip())
    path = u.path
    if not path.startswith("/s-") or path.startswith("/s-anzeige/"):
        raise ValueError("That does not look like a Kleinanzeigen search URL (expected /s-.../k0...). "
                         "Copy the address of a search results page, not of a single listing.")
    kinds = ["seite"]
    if ps:
        kinds.append("preis")
    if offers_only:
        kinds.append("anzeige")
    if seller in ("private", "commercial"):
        kinds.append("anbieter")
    for k in kinds:
        path = re.sub(rf"(?<=/s-){k}:[^/]*/", "", path)   # marker right after "/s-"
        path = re.sub(rf"/{k}:[^/]*(?=/)", "", path)      # marker in the middle
    if filters:
        path = "/s-" + "/".join(filters + [path[3:]])
    return urlunparse(("https", "www.kleinanzeigen.de", path, "", u.query, ""))


def extract_item_links(page_html):
    """Ordered {item_id: url} for all listing links found in a search page."""
    found = {}
    for m in ITEM_RE.finditer(page_html or ""):
        slug, iid, cat, loc = m.groups()
        found.setdefault(iid, f"{BASE}/s-anzeige/{slug}/{iid}-{cat}-{loc}")
    return found


def collect_links(client, query, pages, min_price=None, max_price=None, offers_only=True,
                  seller="any", base_url="", log=None, cancel=None):
    """Walk the search result pages. Returns (links, notes, error)."""
    log = log or (lambda m: None)
    links, notes, error = {}, [], ""
    for page in range(1, pages + 1):
        if cancel and cancel():
            break
        log(f"Scanning search page {page}/{pages}…")
        url = build_search_url(query, page, min_price, max_price, offers_only, seller, base_url)
        page_html = client.get(url)
        new = {k: u for k, u in extract_item_links(page_html).items() if k not in links}
        if not new:
            if page == 1:
                if not base_url and query:   # fallback: let Kleinanzeigen resolve the keyword itself
                    fb_html = client.get(f"{BASE}/s-suchanfrage.html?keywords={quote_plus(query)}")
                    fb = extract_item_links(fb_html)
                    if fb:
                        links.update(fb)
                        notes.append("The normal search URL returned nothing, so Kleinanzeigen's keyword "
                                     "redirect was used (first page only; price/seller filters are "
                                     "checked on each listing instead).")
                        break
                with open("debug_search.html", "w", encoding="utf-8") as f:
                    f.write(page_html or "")
                error = ("No listings found on the first search page. There may be no results, "
                         "Kleinanzeigen may have blocked the request, or its layout changed. "
                         "The raw page was saved to debug_search.html.")
            break
        links.update(new)
    return links, notes, error


# --------------------------------------------------------------------------- listing pages

def _text(fragment):
    fragment = re.sub(r"<br\s*/?>", "\n", fragment or "", flags=re.I)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    t = html.unescape(fragment)
    t = re.sub(r"[ \t\r\f\v\xa0]+", " ", t)
    t = re.sub(r" ?\n ?", "\n", t)
    return t.strip()


def _by_id(page_html, element_id):
    m = re.search(r'<(\w+)[^>]*\bid=["\']' + re.escape(element_id) + r'["\'][^>]*>(.*?)</\1>',
                  page_html, re.S | re.I)
    return _text(m.group(2)) if m else ""


def _meta(page_html, prop):
    m = re.search(r'<meta[^>]+(?:property|name)=["\']' + re.escape(prop) + r'["\'][^>]+content=["\'](.*?)["\']',
                  page_html, re.S | re.I)
    return html.unescape(m.group(1)).strip() if m else ""


def parse_price(text):
    """'1.299 € VB' -> (1299.0, True);  'Zu verschenken' -> (0.0, False);  'VB' -> (None, True)"""
    t = (text or "").lower()
    vb = bool(re.search(r"\bvb\b", t))
    if "verschenken" in t:
        return 0.0, vb
    m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?", t)
    if not m:
        return None, vb
    return float(f"{m.group(1).replace('.', '')}.{m.group(2) or 0}"), vb


def parse_attrs(page_html):
    """Attribute list of a listing, e.g. {'Zustand': 'Sehr Gut', 'Farbe': 'Schwarz', 'Größe': '42'}."""
    attrs = {}
    for m in DETAIL_LI_RE.finditer(page_html):
        inner = m.group(1)
        v = DETAIL_VALUE_RE.search(inner)
        if v:
            value, label = _text(v.group(1)), _text(DETAIL_VALUE_RE.sub("", inner, count=1))
        else:
            t = _text(inner)
            if ":" not in t:
                continue
            label, value = t.split(":", 1)
        label, value = label.strip().rstrip(":"), value.strip()
        if label and value:
            attrs[label] = value
    return attrs


def _label_value(page_html, label):
    """Loose fallback: '>Zustand</..><..>Sehr Gut<'."""
    m = re.search(r">\s*" + re.escape(label) + r"\s*<[^>]*>\s*(?:<[^>]*>\s*)*([^<>{}]{1,60}?)\s*<", page_html)
    return html.unescape(m.group(1)).strip() if m else ""


def condition_key(value):
    v = (value or "").lower()
    if not v:
        return ""
    if "defekt" in v:
        return "defect"
    if "in ordnung" in v:
        return "ok"
    if "sehr gut" in v:
        return "very_good"
    if "neu" in v:
        return "new"
    if "gut" in v:
        return "good"
    return ""


def parse_item_page(page_html):
    info = {"title": "", "description": "", "price": None, "vb": False, "condition": "",
            "cond_key": "", "size": "", "color": "", "location": "", "posted": "", "shipping": False}

    info["title"] = _by_id(page_html, "viewad-title")
    info["description"] = _by_id(page_html, "viewad-description-text")
    price_text = _by_id(page_html, "viewad-price")

    # structured data / meta tags as fallbacks
    for m in LDJSON_RE.finditer(page_html):
        try:
            data = json.loads(html.unescape(m.group(1)).strip())
        except Exception:
            continue
        for d in (data if isinstance(data, list) else [data]):
            if isinstance(d, dict) and d.get("@type") in ("Product", "Offer"):
                info["title"] = info["title"] or str(d.get("name") or "")
                info["description"] = info["description"] or str(d.get("description") or "")
                offers = d.get("offers") if isinstance(d.get("offers"), dict) else d
                if not price_text and offers.get("price") is not None:
                    price_text = f"{offers.get('price')} €"
    info["title"] = info["title"] or _meta(page_html, "og:title")
    info["description"] = info["description"] or _meta(page_html, "og:description")
    info["title"] = re.sub(r"^(Reserviert|Gelöscht)\s*[•·\-]\s*", "", info["title"]).strip()
    info["price"], info["vb"] = parse_price(price_text)

    attrs = parse_attrs(page_html)
    info["condition"] = attrs.get("Zustand") or _label_value(page_html, "Zustand")
    info["cond_key"] = condition_key(info["condition"])
    info["color"] = attrs.get("Farbe") or _label_value(page_html, "Farbe")
    for k, v in attrs.items():
        if "größe" in k.lower() or "groesse" in k.lower():
            info["size"] = v
            break
    if not info["size"]:
        info["size"] = _label_value(page_html, "Größe")

    info["location"] = _by_id(page_html, "viewad-locality").replace("\n", " ")
    extra = re.search(r'id=["\']viewad-extra-info["\'][^>]*>(.*?)</div>', page_html, re.S | re.I)
    if extra:
        first = re.search(r"<span[^>]*>(.*?)</span>", extra.group(1), re.S)
        info["posted"] = _text(first.group(1)) if first else ""
    info["shipping"] = "versand möglich" in html.unescape(page_html).lower()
    return info


# --------------------------------------------------------------------------- filtering

def matches(text, keywords, mode):
    text = text.lower()
    hits = [k.lower() in text for k in keywords]
    return all(hits) if mode == "all" else any(hits)


def size_matches(attr, wanted, fallback=""):
    """Whole-token match: '42' matches '42' but not '42.5'; 'S' does not match 'XS'."""
    text = (attr or fallback or "").lower()
    for w in wanted:
        w = w.strip().lower()
        if w and re.search(r"(?<!\w)(?<!\d[.,])" + re.escape(w) + r"(?!\w)(?![.,]\d)", text):
            return True
    return False


def color_matches(attr, wanted, fallback=""):
    for key in wanted:
        words = COLORS.get(key, [key.lower()])
        if attr:
            if any(w in attr.lower() for w in words):
                return True
        elif any(re.search(r"(?<!\w)" + re.escape(w), fallback.lower()) for w in words):
            return True
    return False


def new_stats():
    return {"cond_unknown": 0, "size_unread": 0, "color_unread": 0}


def passes_filters(info, f, stats):
    """f keys: keywords, match, min_price, max_price, conditions, keep_unknown_condition,
    sizes, colors, shipping_only"""
    text = f"{info['title']}\n{info['description']}"
    if f["keywords"] and not matches(text, f["keywords"], f["match"]):
        return False
    if f["conditions"]:
        if not info["cond_key"]:
            stats["cond_unknown"] += 1
            if not f["keep_unknown_condition"]:
                return False
        elif info["cond_key"] not in f["conditions"]:
            return False
    if f["sizes"]:
        stats["size_unread"] += not info["size"]
        if not size_matches(info["size"], f["sizes"], text):
            return False
    if f["colors"]:
        stats["color_unread"] += not info["color"]
        if not color_matches(info["color"], f["colors"], text):
            return False
    if f["shipping_only"] and not info["shipping"]:
        return False
    p = info["price"]
    if p is not None:
        if f["min_price"] is not None and p < f["min_price"]:
            return False
        if f["max_price"] is not None and p > f["max_price"]:
            return False
    return True


def stats_notes(stats, f):
    notes = []
    if f["conditions"] and stats["cond_unknown"]:
        verb = "kept" if f["keep_unknown_condition"] else "skipped"
        notes.append(f"{stats['cond_unknown']} listing(s) have no condition (Zustand) and were {verb}.")
    if stats["size_unread"]:
        notes.append(f"Size could not be read on {stats['size_unread']} listing(s) – title/description text was used.")
    if stats["color_unread"]:
        notes.append(f"Color could not be read on {stats['color_unread']} listing(s) – title/description text was used.")
    return " ".join(notes)


# --------------------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description="Kleinanzeigen.de keyword crawler")
    ap.add_argument("-q", "--query", default="", help="Search term (product name). Not needed with --filter-url")
    ap.add_argument("-k", "--keywords", nargs="*", default=[],
                    help="Keywords that must appear in title/description (case-insensitive)")
    ap.add_argument("--match", choices=["any", "all"], default="any")
    ap.add_argument("--min-price", type=float, default=None, help="Min price EUR (default: none)")
    ap.add_argument("--max-price", type=float, default=None, help="Max price EUR (default: none)")
    ap.add_argument("-c", "--condition", nargs="*", choices=list(CONDITIONS), default=[],
                    help="Zustand: new very_good good ok defect (default: all)")
    ap.add_argument("--keep-unknown-condition", action="store_true",
                    help="With -c: also keep listings that have no Zustand value")
    ap.add_argument("--seller", choices=["any", "private", "commercial"], default="any")
    ap.add_argument("--include-wanted", action="store_true", help="Also include wanted ads (Gesuche)")
    ap.add_argument("--shipping-only", action="store_true", help="Only listings with 'Versand möglich'")
    ap.add_argument("--size", nargs="*", default=[], help="Sizes to include, e.g. 42 42.5 M")
    ap.add_argument("--color", nargs="*", choices=list(COLORS), default=[], help="Colors to include")
    ap.add_argument("--filter-url", default="",
                    help="Search URL copied from kleinanzeigen.de (keeps location, radius, category, ...)")
    ap.add_argument("--pages", type=int, default=3, help="Search result pages to scan, ~27 listings each")
    ap.add_argument("--delay", type=float, default=1.5, help="Seconds between requests")
    ap.add_argument("--csv", help="Optional CSV output path")
    args = ap.parse_args()

    if not args.query and not args.filter_url:
        ap.error("Provide -q/--query or --filter-url")
    if not IMPERSONATE:
        print("Tip: `pip install curl_cffi` makes blocking much less likely.", file=sys.stderr)

    f = {"keywords": args.keywords, "match": args.match, "min_price": args.min_price,
         "max_price": args.max_price, "conditions": args.condition,
         "keep_unknown_condition": args.keep_unknown_condition, "sizes": args.size,
         "colors": args.color, "shipping_only": args.shipping_only}

    client = Client(delay=args.delay)
    links, notes, error = collect_links(
        client, args.query, args.pages, args.min_price, args.max_price,
        not args.include_wanted, args.seller, args.filter_url,
        log=lambda m: print(m, file=sys.stderr))
    for n in notes:
        print("Note:", n, file=sys.stderr)
    if error:
        print(error, file=sys.stderr)
    print(f"{len(links)} listings found", file=sys.stderr)

    stats, results = new_stats(), []
    for n, (iid, url) in enumerate(links.items(), 1):
        print(f"  checking {n}/{len(links)} ... ({len(results)} matches so far)", file=sys.stderr, flush=True)
        try:
            page_html = client.get(url)
        except Exception as e:
            print(f"  skip {iid}: {e}", file=sys.stderr)
            continue
        if page_html is None:
            continue
        info = parse_item_page(page_html)
        if not passes_filters(info, f, stats):
            continue
        results.append({"id": iid, "title": info["title"], "price_eur": "" if info["price"] is None else info["price"],
                        "vb": "VB" if info["vb"] else "", "condition": info["condition"], "size": info["size"],
                        "color": info["color"], "location": info["location"], "posted": info["posted"],
                        "shipping": "ja" if info["shipping"] else "", "url": url})
        print(f"  match: {info['title'][:60]}", file=sys.stderr)

    note = stats_notes(stats, f)
    if note:
        print("Note:", note, file=sys.stderr)

    results.sort(key=lambda r: (r["price_eur"] == "", r["price_eur"] or 0))
    print(f"\n{len(results)} matching listings:\n")
    for r in results:
        price = f"{r['price_eur']:.2f}" if r["price_eur"] != "" else "  ?  "
        meta = " | ".join(x for x in (r["condition"], r["size"], r["color"], r["location"]) if x)
        print(f"{price:>8} EUR {r['vb']:<2} | {r['title'][:55]}  [{meta}]\n              {r['url']}")

    if args.csv and results:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=results[0].keys(), delimiter=";")
            w.writeheader()
            w.writerows(results)
        print(f"\nSaved to {args.csv}")


if __name__ == "__main__":
    main()
