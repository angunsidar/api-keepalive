"""
TEFAS fon verisi çekici — GitHub Actions tarafından her iş günü 10:35'te çalışır.
Fon fiyatlarını TEFAS'tan alır, Finans API'ye POST eder.
"""
import os
import re
import sys
import time
from datetime import date

import requests

API_URL = "https://finans-api-ztnv.onrender.com"
API_KEY = os.environ["API_KEY"]

FONLAR = {
    "YAS": "Yapı Kredi Portföy Altın Fonu",
    "GAF": "Garanti BBVA Portföy Altın Fonu",
    "TKF": "Türkiye Kurumsal Yönetim End. Fonu",
    "AKF": "Ak Portföy Birinci Fon",
    "MAC": "Marmara Cap. Türkiye Fonu",
    "IPB": "İş Portföy BIST Banka End. Fonu",
    "TTE": "TEB Portföy Tahvil Fonu",
    "AFT": "Ak Portföy Kısa Vad. Tahvil Fonu",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

session = requests.Session()
session.headers.update(HEADERS)

# TEFAS'ın session cookie'sini al
try:
    session.get("https://www.tefas.gov.tr/", timeout=15)
    print("TEFAS session açıldı")
except Exception as e:
    print(f"TEFAS session hatası: {e}")

veriler = []

for kod, ad in FONLAR.items():
    time.sleep(2)  # Rate limit önlemi
    try:
        resp = session.get(
            f"https://www.tefas.gov.tr/FonAnaliz.aspx?FonKod={kod}",
            timeout=20,
        )
        resp.raise_for_status()
        html = resp.text

        # Birim pay değeri: tam 6 ondalık basamak (örn: 13,784033)
        fiyat_match = re.search(r"\b(\d{1,6}[,\.]\d{6})\b", html)
        if not fiyat_match:
            print(f"[{kod}] Fiyat bulunamadı — HTML snippet: {html[:200]!r}")
            continue

        fiyat = round(float(fiyat_match.group(1).replace(",", ".")), 6)
        if fiyat == 0:
            print(f"[{kod}] Sıfır fiyat, atlanıyor")
            continue

        # Günlük getiri (opsiyonel)
        gunluk = 0.0
        getiri_match = re.search(r"([+-]?\d{1,3}[,\.]\d{4})\s*(?:%|&#37;)", html)
        if getiri_match:
            try:
                gunluk = round(float(getiri_match.group(1).replace(",", ".")), 4)
            except Exception:
                pass

        veriler.append({
            "kod": kod,
            "ad": ad,
            "fiyat": fiyat,
            "degisim_yuzde": gunluk,
            "para_birimi": "TRY",
            "tarih": str(date.today()),
            "kaynak": "tefas",
        })
        print(f"[{kod}] ✓ {fiyat} TRY  ({gunluk:+.4f}%)")

    except Exception as e:
        print(f"[{kod}] ✗ Hata: {e}")

if not veriler:
    print("Hiçbir fon verisi alınamadı — API'ye POST yapılmıyor")
    sys.exit(1)

# Finans API'ye gönder
try:
    r = requests.post(
        f"{API_URL}/fon/seed",
        json={"veriler": veriler},
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )
    print(f"\nAPI seed yanıtı [{r.status_code}]: {r.text}")
    if r.status_code != 200:
        sys.exit(1)
except Exception as e:
    print(f"API POST hatası: {e}")
    sys.exit(1)
