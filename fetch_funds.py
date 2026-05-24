"""
TEFAS fon verisi çekici — GitHub Actions tarafından her iş günü 10:35'te çalışır.
Playwright (headless Chromium) ile TEFAS sayfasını açar, JS yüklenmesini bekler,
fon birim pay değerlerini çeker, Finans API /fon/seed endpoint'ine POST eder.
"""
import os
import re
import sys
import time
from datetime import date

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

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

veriler = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        locale="tr-TR",
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    page = context.new_page()

    for kod, ad in FONLAR.items():
        try:
            page.goto(
                f"https://www.tefas.gov.tr/FonAnaliz.aspx?FonKod={kod}",
                wait_until="networkidle",
                timeout=30000,
            )
            time.sleep(2)  # JS render için ekstra bekle

            # Önce tam HTML'i dene
            html = page.content()
            fiyat_match = re.search(r"\b(\d{1,6}[,\.]\d{6})\b", html)

            # Yoksa sayfanın görünür metnini dene
            if not fiyat_match:
                text = page.inner_text("body")
                fiyat_match = re.search(r"\b(\d{1,6}[,\.]\d{6})\b", text)

            if not fiyat_match:
                print(f"[{kod}] ✗ Fiyat bulunamadı")
                # Debug: sayfanın ortasından 300 karakter al
                print(f"       HTML[500:800]: {html[500:800]!r}")
                continue

            fiyat = round(float(fiyat_match.group(1).replace(",", ".")), 6)
            if fiyat == 0:
                print(f"[{kod}] ✗ Sıfır fiyat")
                continue

            # Günlük getiri
            gunluk = 0.0
            text_all = page.inner_text("body")
            getiri_match = re.search(r"([+-]?\d{1,3}[,\.]\d{4})\s*%", text_all)
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

        except PWTimeout:
            print(f"[{kod}] ✗ Timeout")
        except Exception as e:
            print(f"[{kod}] ✗ Hata: {e}")

    browser.close()

print(f"\nToplam: {len(veriler)}/{len(FONLAR)} fon çekildi")

if not veriler:
    print("Hiçbir veri alınamadı — çıkılıyor")
    sys.exit(1)

# Finans API'ye gönder
try:
    r = requests.post(
        f"{API_URL}/fon/seed",
        json={"veriler": veriler},
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )
    print(f"API seed [{r.status_code}]: {r.text}")
    if r.status_code != 200:
        sys.exit(1)
except Exception as e:
    print(f"API POST hatası: {e}")
    sys.exit(1)
