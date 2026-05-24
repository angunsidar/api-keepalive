"""
Fintables.com fon getiri sayfasından Türk yatırım fonu verilerini çeker.
GitHub Actions tarafından her iş günü 10:35 İstanbul saatinde çalışır.

Yöntem sırası:
  1. __NEXT_DATA__ JSON  (Next.js SSR embed)
  2. RSC endpoint        (RSC: 1 header)
  3. Accept: application/json
"""
import os
import sys
import json
import re
import requests
from datetime import date

API_URL = "https://finans-api-ztnv.onrender.com"
API_KEY = os.environ["API_KEY"]

HEDEF_FONLAR = {"YAS", "GAF", "TKF", "AKF", "MAC", "IPB", "TTE", "AFT"}

_BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

FINTABLES_URL = "https://fintables.com/fonlar/getiri"


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_BASE_HEADERS)
    try:
        s.get(
            "https://fintables.com/",
            timeout=15,
            headers={**_BASE_HEADERS, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
        )
        print("  Fintables session cookie alındı")
    except Exception as e:
        print(f"  Session cookie hatası (önemli değil): {e}")
    return s


def _try_next_data(html: str) -> list | None:
    """Next.js __NEXT_DATA__ script tag'inden fon listesini çıkar."""
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        print("  __NEXT_DATA__ bulunamadı")
        return None

    try:
        nd = json.loads(m.group(1))
    except Exception as e:
        print(f"  __NEXT_DATA__ JSON parse hatası: {e}")
        return None

    page_props = nd.get("props", {}).get("pageProps", {})
    print(f"  pageProps keys: {list(page_props.keys())}")

    for key in ("results", "data", "fonlar"):
        val = page_props.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict) and "code" in val[0]:
            print(f"  __NEXT_DATA__['{key}'] ✓ {len(val)} fon")
            return val

    # Daha derin arama
    def _deep(obj, depth=0):
        if depth > 6:
            return None
        if isinstance(obj, list) and len(obj) > 3 and isinstance(obj[0], dict) and "code" in obj[0]:
            return obj
        if isinstance(obj, dict):
            for v in obj.values():
                r = _deep(v, depth + 1)
                if r is not None:
                    return r
        return None

    deep = _deep(page_props)
    if deep:
        print(f"  __NEXT_DATA__ (derin) ✓ {len(deep)} fon")
        return deep

    print(f"  __NEXT_DATA__ var ama fon listesi yok. pageProps: {str(page_props)[:300]}")
    return None


def _try_rsc(session: requests.Session) -> list | None:
    """Next.js RSC endpoint'ini dene (RSC: 1 header)."""
    try:
        resp = session.get(
            FINTABLES_URL,
            headers={
                "Accept": "text/x-component",
                "RSC": "1",
                "Next-Router-State-Tree": "%5B%22%22%2C%7B%7D%2Cnull%2Cnull%2Ctrue%5D",
                "Next-Router-Prefetch": "1",
            },
            timeout=30,
        )
        print(f"  RSC status: {resp.status_code}, ilk 300: {resp.text[:300]!r}")
    except Exception as e:
        print(f"  RSC isteği başarısız: {e}")
        return None

    for line in resp.text.splitlines():
        line = line.strip()
        if not line or '"code"' not in line:
            continue
        try:
            idx = line.find("{")
            if idx < 0:
                continue
            data = json.loads(line[idx:])
            if isinstance(data, dict) and isinstance(data.get("results"), list):
                print(f"  RSC ✓ {len(data['results'])} fon")
                return data["results"]
        except Exception:
            continue
    return None


def _try_json(session: requests.Session) -> list | None:
    """Accept: application/json ile dene — dahili API varsa JSON döner."""
    try:
        resp = session.get(
            FINTABLES_URL,
            headers={"Accept": "application/json"},
            timeout=30,
        )
        print(f"  JSON status: {resp.status_code}, content-type: {resp.headers.get('content-type','?')}")
        data = resp.json()
        results = data.get("results") or data.get("data") or (data if isinstance(data, list) else None)
        if isinstance(results, list) and results and isinstance(results[0], dict) and "code" in results[0]:
            print(f"  Direct JSON ✓ {len(results)} fon")
            return results
    except Exception as e:
        print(f"  Direct JSON başarısız: {e}")
    return None


def fetch_fintables() -> list:
    session = _make_session()

    print("→ Yöntem 1: HTML + __NEXT_DATA__")
    try:
        resp = session.get(
            FINTABLES_URL,
            headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
            timeout=30,
        )
        print(f"  HTML status: {resp.status_code}, boyut: {len(resp.text)} karakter")
        results = _try_next_data(resp.text)
        if results:
            return results
    except Exception as e:
        print(f"  HTML isteği başarısız: {e}")

    print("→ Yöntem 2: RSC endpoint")
    results = _try_rsc(session)
    if results:
        return results

    print("→ Yöntem 3: Direct JSON")
    results = _try_json(session)
    if results:
        return results

    return []


# ── Ana akış ─────────────────────────────────────────────────────────────────

print("Fintables fon verisi çekiliyor...")
tum_fonlar = fetch_fintables()
print(f"Toplam {len(tum_fonlar)} fon alındı")

if not tum_fonlar:
    print("Fintables'tan hiç veri gelmedi — çıkılıyor")
    sys.exit(1)


def _f(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


veriler = []
for fon in tum_fonlar:
    kod = str(fon.get("code", "")).strip().upper()
    if kod not in HEDEF_FONLAR:
        continue

    veriler.append({
        "kod": kod,
        "ad": fon.get("title", kod),
        "fiyat": 0.0,
        "degisim_yuzde": _f(fon.get("yield_1m")) or 0.0,
        "yield_1m":  _f(fon.get("yield_1m")),
        "yield_3m":  _f(fon.get("yield_3m")),
        "yield_6m":  _f(fon.get("yield_6m")),
        "yield_ytd": _f(fon.get("yield_ytd")),
        "yield_1y":  _f(fon.get("yield_1y")),
        "yield_3y":  _f(fon.get("yield_3y")),
        "yield_5y":  _f(fon.get("yield_5y")),
        "para_birimi": "TRY",
        "tarih": str(date.today()),
        "kaynak": "fintables",
    })
    print(
        f"[{kod}] ✓ {fon.get('title', '?')[:50]}"
        f"  1A:{fon.get('yield_1m')}%  1Y:{fon.get('yield_1y')}%"
    )

print(f"\nToplam: {len(veriler)}/{len(HEDEF_FONLAR)} fon çekildi")

eksik = HEDEF_FONLAR - {v["kod"] for v in veriler}
if eksik:
    print(f"Eksik fonlar: {eksik}")

if not veriler:
    print("Hiçbir hedef fon bulunamadı — çıkılıyor")
    sys.exit(1)

# Finans API'ye gönder
try:
    r = requests.post(
        f"{API_URL}/fon/seed",
        json={"veriler": veriler},
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )
    print(f"\nAPI seed [{r.status_code}]: {r.text}")
    if r.status_code != 200:
        sys.exit(1)
except Exception as e:
    print(f"API POST hatası: {e}")
    sys.exit(1)
