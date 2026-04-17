#!/usr/bin/env python3
"""
TikTok Ürün AI Ajanı
──────────────────────────────────────────────────────────────────────
Claude (claude-opus-4-7) düşünür → Playwright/HTTP ile TikTok tarar
→ analiz eder → Telegram'dan telefonuna gönderir.

Telegram komutları:
  /tara    — anında tarama başlat
  /hafta   — bu haftanın trendleri
  /ay      — bu ayın trendleri
  /durum   — ajan durumu
"""

import asyncio
import json
import logging
import os
from datetime import datetime

import anthropic
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_TOKEN    = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID  = os.environ["TELEGRAM_CHAT_ID"]
SCAN_HOURS        = int(os.getenv("SCAN_INTERVAL_HOURS", "6"))

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Sistem promptu (cache'lenir) ───────────────────────────────────────────────
SYSTEM_PROMPT = """Sen bir TikTok ürün analizi uzmanısın. Verilen trend ürün verilerini \
analiz edip Türkçe rapor hazırlarsın.

Raporunu şu yapıda sun:
1. 🔥 En çok trend olan 5 ürün — her biri için başlık ve neden viral olduğu
2. 💰 Satın alma / dropshipping potansiyeli (düşük / orta / yüksek)
3. 🇹🇷 Türkiye pazarı için genel değerlendirme
4. ⚡ Hızlı aksiyon tavsiyesi (bu hafta kaçırma)

Telegram mesajı olarak düz metin yaz. Çok uzun olmasın, özet tut."""

# ── TikTok veri çekme ──────────────────────────────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "application/json",
    "Referer": "https://ads.tiktok.com/business/creativecenter/top-products/pc/en",
    "Origin": "https://ads.tiktok.com",
}


async def _fetch_via_api(period: int, country: str) -> list[dict]:
    url = "https://ads.tiktok.com/creative_radar_api/v1/top_products/list"
    params = {"period": period, "page": 1, "limit": 20, "country_code": country}
    async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as http:
        r = await http.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        raw = data.get("data", {}).get("list", data.get("list", []))
        return [
            {
                "baslik": p.get("title") or p.get("item_title", ""),
                "kategori": p.get("first_category_name") or p.get("category_name", ""),
                "satis_adedi": p.get("sold_count"),
                "gelir_artisi": p.get("revenue_growth_rate"),
                "fiyat": p.get("price"),
                "link": (
                    p.get("item_url")
                    or f"https://www.tiktok.com/search?q={p.get('title', '')}"
                ),
            }
            for p in raw
            if p.get("title") or p.get("item_title")
        ]


async def _fetch_via_playwright() -> list[dict]:
    log.info("Playwright fallback devreye giriyor...")
    products: list[dict] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=_HEADERS["User-Agent"])
        try:
            await page.goto(
                "https://ads.tiktok.com/business/creativecenter/top-products/pc/en",
                wait_until="networkidle",
                timeout=30_000,
            )
            await page.wait_for_timeout(4000)
            products = await page.evaluate("""() => {
                const sel = '[class*="product-card"],[class*="ProductCard"],[class*="productCard"]';
                const cards = document.querySelectorAll(sel);
                return Array.from(cards).slice(0, 20).map(c => ({
                    baslik: (c.querySelector('h3,[class*="title"],[class*="Title"]')
                             ?.textContent?.trim()) || '',
                    kategori: (c.querySelector('[class*="category"],[class*="Category"]')
                               ?.textContent?.trim()) || '',
                    satis_adedi: null,
                    gelir_artisi: null,
                    fiyat: (c.querySelector('[class*="price"],[class*="Price"]')
                            ?.textContent?.trim()) || null,
                    link: c.querySelector('a')?.href || 'https://www.tiktok.com',
                })).filter(p => p.baslik.length > 2);
            }""")
        except Exception as exc:
            log.warning("Playwright hatası: %s", exc)
        finally:
            await browser.close()
    return products


async def get_products(period: int = 7, country: str = "TR") -> list[dict]:
    try:
        products = await _fetch_via_api(period, country)
        if products:
            log.info("API'den %d ürün alındı", len(products))
            return products
    except Exception as exc:
        log.warning("API hatası (%s), Playwright deneniyor...", exc)
    return await _fetch_via_playwright()


# ── Claude analizi ─────────────────────────────────────────────────────────────
def analyze(products: list[dict]) -> str:
    if not products:
        return "⚠️ TikTok'tan ürün verisi alınamadı. Daha sonra tekrar deneyin."

    product_json = json.dumps(products, ensure_ascii=False, indent=2)
    tarih = datetime.now().strftime("%d.%m.%Y %H:%M")

    response = claude.messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    f"Tarih: {tarih}\n\n"
                    f"TikTok Creative Center'dan alınan trend ürünler:\n\n"
                    f"{product_json}"
                ),
            }
        ],
    )

    for block in response.content:
        if block.type == "text":
            return block.text
    return "Claude'dan yanıt alınamadı."


# ── Telegram gönderim ──────────────────────────────────────────────────────────
async def send(text: str) -> None:
    bot = Bot(token=TELEGRAM_TOKEN)
    for i in range(0, len(text), 4000):
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text[i : i + 4000])
    log.info("Telegram mesajı gönderildi")


# ── Ana tarama döngüsü ─────────────────────────────────────────────────────────
async def run_scan(period: int = 7) -> None:
    log.info("Tarama başlıyor (period=%d gün)...", period)
    await send("🔍 TikTok taranıyor, Claude analiz ediyor…")

    products = await get_products(period=period)
    analysis = analyze(products)

    header = (
        f"📱 TikTok Made Me Buy It\n"
        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"{'─' * 30}\n\n"
    )
    await send(header + analysis)
    log.info("Tarama tamamlandı")


# ── Telegram bot komutları ─────────────────────────────────────────────────────
async def cmd_tara(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🚀 Tarama başlatıldı, birazdan gelecek...")
    await run_scan(period=7)


async def cmd_hafta(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📅 Bu haftanın trendleri taranıyor...")
    await run_scan(period=7)


async def cmd_ay(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📆 Bu ayın trendleri taranıyor...")
    await run_scan(period=30)


async def cmd_durum(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"✅ Ajan aktif\n"
        f"⏰ Her {SCAN_HOURS} saatte otomatik tarar\n\n"
        f"Komutlar:\n"
        f"  /tara  — hemen tara\n"
        f"  /hafta — bu haftanın trendleri\n"
        f"  /ay    — bu ayın trendleri\n"
        f"  /durum — bu mesaj"
    )


# ── Başlangıç ──────────────────────────────────────────────────────────────────
async def main() -> None:
    # Zamanlayıcı
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_scan, "interval", hours=SCAN_HOURS)
    scheduler.start()
    log.info("Zamanlayıcı aktif: her %d saatte bir tarar", SCAN_HOURS)

    # İlk taramayı 5 saniye sonra başlat (bot hazır olsun)
    async def delayed_first_scan():
        await asyncio.sleep(5)
        await run_scan()

    asyncio.create_task(delayed_first_scan())

    # Telegram bot polling
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("tara", cmd_tara))
    app.add_handler(CommandHandler("hafta", cmd_hafta))
    app.add_handler(CommandHandler("ay", cmd_ay))
    app.add_handler(CommandHandler("durum", cmd_durum))

    log.info("Telegram botu başlatıldı — telefona komut gönderebilirsin")
    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
