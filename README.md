# Kleinanzeigen Description Finder

Search [kleinanzeigen.de](https://www.kleinanzeigen.de) for a product and keep only the listings whose **title or description contains your keywords**. Comes with a local web UI and a command-line version.

- Keyword search in title **and** description (any / all keywords)
- Optional price range (no limit unless you set one)
- Condition filter (_Zustand_): Neu, Sehr gut, Gut, In Ordnung, Defekt
- Seller filter (private / commercial), offers only or including wanted ads (_Gesuche_)
- Optional "only with _Versand möglich_" filter
- Size and color filters for shoes and clothes
- Location, radius and category: paste a search URL copied from kleinanzeigen.de
- Live progress, cancel button, sortable results (price, condition, size, color, location, date), CSV export (opens correctly in German Excel)

> **Disclaimer:** This is an unofficial tool, not affiliated with Kleinanzeigen. Kleinanzeigen's terms restrict automated access to the site, and its pages can change or block requests at any time. Use the tool for personal purposes only, at low volume, and at your own risk. Listings can contain personal data of private sellers: don't collect, store or publish it. The tool does not read seller names, phone numbers or addresses.

---

## Requirements

| What     | Details                                                                                                                                           |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python   | 3.9 or newer                                                                                                                                      |
| OS       | Windows, macOS or Linux                                                                                                                           |
| Packages | [`curl_cffi`](https://pypi.org/project/curl-cffi/) (recommended) and `requests` (automatic fallback) – see [`requirements.txt`](requirements.txt) |
| Browser  | Any modern browser, for the web UI                                                                                                                |

The web UI itself uses only the Python standard library.

## Installation

Use a virtual environment so nothing touches your system Python.

**Windows (PowerShell)**

```powershell
git clone https://github.com/<your-user>/kleinanzeigen-description-finder.git
cd kleinanzeigen-description-finder
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell refuses to run the activation script, run this once and activate again:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**macOS / Linux**

```bash
git clone https://github.com/<your-user>/kleinanzeigen-description-finder.git
cd kleinanzeigen-description-finder
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the web UI

```bash
python kleinanzeigen_ui.py
```

Your browser opens `http://127.0.0.1:8766`. Fill in the form and click **Search**. The server only listens on your own machine. Press `Ctrl+C` in the terminal to stop it.

## Run from the command line

```bash
python kleinanzeigen_crawler.py -q "JBL Charge 6" -k geschenk ovp
```

| Option                              | Meaning                                                                 |
| ----------------------------------- | ----------------------------------------------------------------------- |
| `-q`, `--query`                     | Search term (product name). Not needed if `--filter-url` is given       |
| `-k`, `--keywords`                  | One or more keywords that must appear in title/description              |
| `--match any\|all`                  | Match any keyword (default) or all keywords                             |
| `--min-price`, `--max-price`        | Price range in EUR. Not set = no limit                                  |
| `-c`, `--condition`                 | Zustand: `new` `very_good` `good` `ok` `defect`. Not set = all          |
| `--keep-unknown-condition`          | With `-c`: also keep listings that have no Zustand value                |
| `--seller any\|private\|commercial` | Seller type (default: any)                                              |
| `--include-wanted`                  | Also include wanted ads (_Gesuche_); by default only offers             |
| `--shipping-only`                   | Only listings that show _Versand möglich_                               |
| `--size`                            | Sizes to include, e.g. `42 42.5` or `M L`                               |
| `--color`                           | Colors to include, e.g. `Schwarz Weiß Blau`                             |
| `--filter-url`                      | Search URL copied from kleinanzeigen.de (location, radius, category, …) |
| `--pages`                           | Search result pages to scan, about 27 listings each (default 3)         |
| `--delay`                           | Seconds between requests (default 1.5, don't go much lower)             |
| `--csv FILE`                        | Save results as CSV                                                     |

Examples:

```bash
# Unopened gift items, new condition only, up to 120 EUR, private sellers
python kleinanzeigen_crawler.py -q "JBL Charge 6" -k geschenk ovp ungeöffnet versiegelt \
    -c new --max-price 120 --seller private

# Sneakers in size 42, black or white, like new, shipping possible
python kleinanzeigen_crawler.py -q "Nike Air Max 90" --size 42 --color Schwarz Weiß \
    -c new very_good --shipping-only --csv results.csv

# Broken phones near Berlin (location/radius copied from the site)
python kleinanzeigen_crawler.py -k defekt bastler \
    --filter-url "https://www.kleinanzeigen.de/s-berlin/iphone-13/k0l3331r20"
```

## How it works

1. Builds the search URL, for example `kleinanzeigen.de/s-preis:10:50/anzeige:angebote/jbl-charge-6/k0`, and walks through the result pages to collect listing links.
2. Opens every listing page and reads title, description, price, condition (_Zustand_), size, color, location and date.
3. Keeps the listings that match your keywords and filters. Results are sorted by price.

Because every listing has to be opened, a run takes a few minutes (about 1.5 s per listing). Fewer pages, a price range, a seller filter or a pasted URL with a narrow category make it faster.

## Filters in detail

- **Price, seller, offers vs. wanted ads** are sent to Kleinanzeigen as part of the search URL. Prices are checked again on each listing.
- **Condition (Zustand)** is read from each listing. Only some categories have this field (for example electronics, fashion, many household categories). Listings without a value are **skipped** when you filter by condition, and the tool tells you how many. Tick _Also keep listings that have no condition value_ (`--keep-unknown-condition`) to keep them.
- **Size** matches whole tokens: `42` matches `42` but not `42.5`; `S` matches `S` but not `XS`. **Color** matches by color family, also in English: `Blau` matches _Marineblau_ and _blue_. If a listing's size or color can't be read, the title and description text is used instead, and the tool reports how often that happened.
- **Versand möglich** is detected from the listing page text. Treat it as a good hint, not a guarantee.
- **Location, radius and category:** Kleinanzeigen uses internal IDs for these, so there is no plain-text field. On kleinanzeigen.de set _Ort + Umkreis_, category and other filters, copy the URL from the address bar and paste it into the **Advanced** box (or `--filter-url`). The search term field is then ignored; your price, seller, keyword and other settings are applied on top. Paste the URL of a search results page, not of a single listing.

---

# Keyword ideas

Matching is **case-insensitive and substring-based** on title + description. Paste any list below straight into the keywords field (comma-separated).

**Tips**

- Short stems are enough: `geschenk` also finds _Geburtstagsgeschenk_, _Weihnachtsgeschenk_ and _geschenkt_.
- Substring matching has no idea about negation: `kratzer` also matches _ohne Kratzer_, `etikett` also matches _ohne Etikett_. Check the hits.
- Avoid very short or generic words (`neu`, `vb`, `ok`): they match inside many other words. `neu` hits _neutral_, _neuwertig_, _Neukauf_.
- Use **any** matching to cast a wide net and **all** to narrow down.
- Sellers write umlauts both ways. Add variants when it matters: `ungeöffnet, ungeoeffnet`, `zubehör, zubehoer`.
- Kleinanzeigen is a local, mostly private marketplace. Typical phrases like _Privatverkauf_, _keine Garantie_ and _Abholung_ show up in almost every listing, so don't use them as positive signals. They are useful as exclusion hints when you read the results.

## 🇩🇪 German

### Gift, unused or unwanted purchase

```
geschenk, nie benutzt, ungenutzt, unbenutzt, originalverpackt, ovp, ungeöffnet, ungeoeffnet, versiegelt, ungetragen, fehlkauf, doppelt bekommen, passt nicht, falsche größe, falsche groesse
```

### Excellent condition / like new

```
neuwertig, wie neu, einwandfrei, makellos, top zustand, sehr guter zustand, kaum benutzt, kaum getragen, einmal getragen, ohne gebrauchsspuren, nichtraucher, rauchfrei, tierfrei, tierfreier haushalt
```

### Defects, repair and spare parts

```
defekt, kaputt, bastler, ersatzteile, reparatur, funktioniert nicht, geht nicht, akku schwach, riss, loch, löcher, fleck, kratzer, macken, gebrauchsspuren, bastlerware
```

### Motivated seller, negotiable, bundles

```
verhandlungsbasis, verhandelbar, muss weg, schnell weg, dringend, umzug, haushaltsauflösung, haushaltsaufloesung, wohnungsauflösung, wohnungsaufloesung, nachlass, preisnachlass, paketpreis, mehrere artikel
```

### Free and very cheap

```
zu verschenken, verschenke, gratis, kostenlos, gegen abholung, abzugeben, günstig abzugeben, symbolischer preis
```

### Complete set, accessories, proof of purchase

```
originalkarton, originalverpackung, zubehör, zubehoer, komplett, vollständig, ladekabel, netzteil, ladegerät, bedienungsanleitung, rechnung, kaufbeleg, kassenbon, seriennummer
```

### Electronics and tech

```
garantie, rechnung, seriennummer, akkukapazität, akkugesundheit, zyklen, entsperrt, ohne simlock, zurückgesetzt, neugerät, displayschutz
```

### Authentic, vintage, rare, collectible

```
original, authentisch, echtheitszertifikat, vintage, retro, selten, rar, limitiert, sammler, sammlerstück, nachlass, deadstock, vergriffen
```

### Clothes and shoes: fit and sizing

```
fällt klein aus, fällt groß aus, passt nicht, zu klein, zu groß, falsche größe, nur anprobiert, einmal getragen, ungetragen, mit etikett
```

### Shipping and handover

```
versand möglich, versand, nur abholung, abholung, selbstabholer, sicher bezahlen, paypal, übergabe, lieferung möglich
```

## 🇬🇧 English

Many sellers on Kleinanzeigen write in English, especially for electronics, books and expat items.

### Gift, unused or unwanted purchase

```
gift, never used, unused, unopened, sealed, brand new, still in box, unworn, never worn, wrong size, doesn't fit, received twice
```

### Excellent condition / like new

```
like new, mint condition, excellent condition, flawless, barely used, hardly worn, worn once, no signs of wear, smoke-free, pet-free, non-smoker, unused
```

### Defects, repair and spare parts

```
defective, broken, faulty, not working, for parts, spares or repair, needs repair, stain, hole, tear, scratch, damaged, as is
```

### Motivated seller, negotiable, bundles

```
negotiable, obo, must go, quick sale, urgent, moving, clearance, house clearance, bundle, discount
```

### Free and very cheap

```
free, giveaway, free to collect, for free, symbolic price
```

### Complete set, accessories, proof of purchase

```
complete, full set, original box, original packaging, accessories, charger, manual, receipt, invoice, serial number
```

### Electronics and tech

```
warranty, receipt, serial number, battery health, cycles, unlocked, sim-free, factory reset, brand new device
```

### Authentic, vintage, rare, collectible

```
authentic, genuine, vintage, retro, rare, limited edition, collector, deadstock, discontinued
```

### Clothes and shoes: fit and sizing

```
runs small, runs large, true to size, tried on, wrong size, doesn't fit, tags attached
```

### Shipping and handover

```
shipping possible, pickup only, collection only, can ship, paypal
```

> More languages: the Vinted version of this project has Dutch, French and Italian keyword lists that work the same way. Kleinanzeigen is a German-language site, so German and English cover almost everything.

---

## Troubleshooting

| Problem                                                | What to do                                                                                                                                                                                                                     |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `No listings found on the first search page`           | There may be no results, Kleinanzeigen may have blocked the request, or its layout changed. Open the saved `debug_search.html` to see what came back. Make sure `curl_cffi` is installed, raise `--delay`, and try again later |
| Errors 403 / 429 / 503 or very slow                    | You're being rate-limited. Increase the delay, scan fewer pages, don't run many searches in a row                                                                                                                              |
| Very few or no results with a condition filter         | The category may have no _Zustand_ field. Tick _Also keep listings that have no condition value_, or use a keyword filter instead                                                                                              |
| Search term with umlauts finds nothing                 | The tool falls back to Kleinanzeigen's own keyword redirect for the first page. For full control, run the search on the site and paste the URL into the Advanced box                                                           |
| The run seems stuck                                    | It is working through the listings (about 1.5 s each). The progress bar (UI) and the `checking n/total` line (CLI) show where it is                                                                                            |
| `pip install` fails with a permission error on Windows | Use a virtual environment (see Installation) or `pip install --user -r requirements.txt`                                                                                                                                       |
| `No module named kleinanzeigen_crawler`                | `kleinanzeigen_ui.py` and `kleinanzeigen_crawler.py` must be in the same folder; start the UI from that folder                                                                                                                 |
| Port 8766 already in use                               | An earlier instance is still running. Close it or change `PORT` at the top of `kleinanzeigen_ui.py`                                                                                                                            |

## Known limitations

- Kleinanzeigen has no public search API, so this tool reads the normal web pages. If the page layout or URL scheme changes, parts of it can stop working until the code is updated.
- Size, color, condition and shipping are read from the listing page on a best-effort basis; see _Filters in detail_.
- Kleinanzeigen limits how deep you can page through a search (the tool stops when a page has no new listings), so very broad searches can't be scanned completely. Narrow them with a price range, location or category.

## Project structure

```
kleinanzeigen-description-finder/
├── kleinanzeigen_crawler.py   # crawler + command-line interface
├── kleinanzeigen_ui.py        # local web UI (imports kleinanzeigen_crawler)
├── requirements.txt
└── README.md
```
