#!/usr/bin/env python3
"""
TikTok + 1688.com Ürün AI Ajanı
──────────────────────────────────────────────────────────────────────
Claude (claude-opus-4-7) düşünür → TikTok + 1688.com tarar
→ sorun çözen ürünleri analiz eder → Telegram'dan telefonuna gönderir.

Telegram komutları:
  /tara      — TikTok + 1688 tam tarama
  /1688      — sadece 1688.com ürün analizi
  /tiktok    — sadece TikTok trend analizi
  /hafta     — bu haftanın trendleri
  /durum     — ajan durumu
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

# ── Sistem promptu ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Sen bir e-ticaret ve dropshipping uzmanısın.
Sana TikTok trend verileri ve 1688.com toptan fiyatları verilecek.

Görevin:
1. SORUN ÇÖZEN ürünleri tespit et (ağrı kesici, temizleyici, düzenleyici, zaman kazandıran vb.)
2. Her ürün için şunları analiz et:
   - Hangi sorunu çözüyor?
   - TikTok'ta ne kadar viral potansiyeli var?
   - 1688'deki toptan fiyatı → tahmini satış fiyatı → KAR MARJI
   - Reklam açısı: hangi duygusal tetikleyici işe yarar?
3. En karlı 5 ürünü sırala

Yanıtı Telegram mesajı olarak yaz. Her ürün için net, satış odaklı yaz."""

# ── TikTok veri çekme ──────────────────────────────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "application/json",
    "Referer": "https://ads.tiktok.com/business/creativecenter/top-products/pc/en",
}


async def fetch_tiktok_products(period: int = 7) -> list[dict]:
    try:
        url = "https://ads.tiktok.com/creative_radar_api/v1/top_products/list"
        params = {"period": period, "page": 1, "limit": 20, "country_code": "TR"}
        async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as http:
            r = await http.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            raw = data.get("data", {}).get("list", data.get("list", []))
            products = [
                {
                    "baslik": p.get("title") or p.get("item_title", ""),
                    "kategori": p.get("first_category_name", ""),
                    "satis": p.get("sold_count"),
                    "buyume": p.get("revenue_growth_rate"),
                    "fiyat": p.get("price"),
                }
                for p in raw
                if p.get("title") or p.get("item_title")
            ]
            if products:
                log.info("TikTok API: %d ürün", len(products))
                return products
    except Exception as e:
        log.warning("TikTok API hatası: %s", e)

    # Playwright fallback
    log.info("TikTok Playwright fallback...")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=_HEADERS["User-Agent"])
        try:
            await page.goto(
                "https://ads.tiktok.com/business/creativecenter/top-products/pc/en",
                wait_until="networkidle", timeout=30_000,
            )
            await page.wait_for_timeout(3000)
            products = await page.evaluate("""() => {
                const cards = document.querySelectorAll(
                    '[class*="product-card"],[class*="ProductCard"]');
                return Array.from(cards).slice(0,20).map(c=>({
                    baslik:(c.querySelector('h3,[class*="title"]')?.textContent?.trim()||''),
                    kategori:(c.querySelector('[class*="category"]')?.textContent?.trim()||''),
                    satis:null, buyume:null, fiyat:null,
                })).filter(p=>p.baslik.length>2);
            }""")
        except Exception as e:
            log.warning("TikTok Playwright hatası: %s", e)
            products = []
        finally:
            await browser.close()
    return products


# ── 1688.com veri çekme ────────────────────────────────────────────────────────
_1688_QUERIES = [
    "解决问题神器",      # sorun çözen alet
    "懒人神器",          # tembellik aleti (pratik ürün)
    "家居收纳",          # ev düzenleme
    "清洁工具",          # temizlik aleti
    "健康护理",          # sağlık bakım
]


async def fetch_1688_products() -> list[dict]:
    """1688.com'dan sorun çözen ürünleri scrape eder."""
    log.info("1688.com taranıyor...")
    all_products: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )
        page = await context.new_page()

        for query in _1688_QUERIES[:3]:  # ilk 3 sorgu
            try:
                url = f"https://s.1688.com/selloffer/offer_search.htm?keywords={query}&sortType=va_sales"
                await page.goto(url, wait_until="networkidle", timeout=25_000)
                await page.wait_for_timeout(2000)

                products = await page.evaluate("""() => {
                    const items = document.querySelectorAll(
                        '.offer-list-row .offer-item, [class*="offer-item"], .item-offer');
                    return Array.from(items).slice(0, 8).map(el => ({
                        baslik: (
                            el.querySelector('.offer-title, [class*="title"] a, h4 a')
                               ?.textContent?.trim() || ''
                        ).slice(0, 80),
                        fiyat: (
                            el.querySelector('.price, [class*="price"] em, .priceText')
                               ?.textContent?.trim() || ''
                        ),
                        min_siparis: (
                            el.querySelector('.minOrder, [class*="minOrder"]')
                               ?.textContent?.trim() || ''
                        ),
                        tedarikci: (
                            el.querySelector('.company-name, [class*="companyName"]')
                               ?.textContent?.trim() || ''
                        ),
                        kaynak: '1688.com',
                    })).filter(p => p.baslik.length > 3);
                }""")

                all_products.extend(products)
                log.info("1688 '%s': %d ürün", query, len(products))
                await asyncio.sleep(1.5)

            except Exception as e:
                log.warning("1688 '%s' hatası: %s", query, e)

        await browser.close()

    log.info("1688 toplam: %d ürün", len(all_products))
    return all_products[:20]


# ── Claude analizi ─────────────────────────────────────────────────────────────
def analyze(tiktok_products: list[dict], products_1688: list[dict], mod: str = "tam") -> str:
    tarih = datetime.now().strftime("%d.%m.%Y %H:%M")

    if mod == "1688":
        icerik = f"1688.com ürünleri:\n{json.dumps(products_1688, ensure_ascii=False, indent=2)}"
        soru = "Bu 1688 ürünlerinden sorun çözen ve reklam potansiyeli yüksek olanları analiz et."
    elif mod == "tiktok":
        icerik = f"TikTok trend ürünleri:\n{json.dumps(tiktok_products, ensure_ascii=False, indent=2)}"
        soru = "Bu TikTok ürünlerini sorun çözme ve reklam potansiyeli açısından analiz et."
    else:
        icerik = (
            f"TikTok trend ürünleri:\n{json.dumps(tiktok_products, ensure_ascii=False, indent=2)}\n\n"
            f"1688.com toptan ürünleri:\n{json.dumps(products_1688, ensure_ascii=False, indent=2)}"
        )
        soru = (
            "TikTok trendleri ile 1688 toptan fiyatlarını karşılaştır. "
            "Sorun çözen, reklam potansiyeli yüksek ve karlı ürünleri bul."
        )

    response = claude.messages.create(
        model="claude-opus-4-7",
        max_tokens=2500,
        thinking={"type": "adaptive"},
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": f"Tarih: {tarih}\n\n{icerik}\n\nGörev: {soru}"}],
    )

    for block in response.content:
        if block.type == "text":
            return block.text
    return "Analiz alınamadı."


# ── Telegram gönderim ──────────────────────────────────────────────────────────
async def send(text: str) -> None:
    bot = Bot(token=TELEGRAM_TOKEN)
    for i in range(0, len(text), 4000):
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text[i:i+4000])


# ── Tarama döngüleri ───────────────────────────────────────────────────────────
async def run_full_scan(period: int = 7) -> None:
    await send("🔍 TikTok + 1688.com taranıyor, Claude analiz ediyor…")
    tiktok, ali = await asyncio.gather(
        fetch_tiktok_products(period),
        fetch_1688_products(),
    )
    analysis = analyze(tiktok, ali, mod="tam")
    header = f"📦 TikTok × 1688 Ürün Analizi\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n{'─'*32}\n\n"
    await send(header + analysis)


async def run_1688_scan() -> None:
    await send("🔍 1688.com taranıyor…")
    products = await fetch_1688_products()
    analysis = analyze([], products, mod="1688")
    header = f"🇨🇳 1688.com Ürün Analizi\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n{'─'*32}\n\n"
    await send(header + analysis)


async def run_tiktok_scan(period: int = 7) -> None:
    await send("🔍 TikTok taranıyor…")
    products = await fetch_tiktok_products(period)
    analysis = analyze(products, [], mod="tiktok")
    header = f"📱 TikTok Trend Analizi\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n{'─'*32}\n\n"
    await send(header + analysis)


# ── Telegram komutları ─────────────────────────────────────────────────────────
async def cmd_tara(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🚀 TikTok + 1688 taraması başlatıldı…")
    await run_full_scan()

async def cmd_1688(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🇨🇳 1688.com taraması başlatıldı…")
    await run_1688_scan()

async def cmd_tiktok(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📱 TikTok taraması başlatıldı…")
    await run_tiktok_scan()

async def cmd_hafta(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📅 Bu haftanın trendleri taranıyor…")
    await run_full_scan(period=7)

async def cmd_durum(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"✅ Ajan aktif\n"
        f"⏰ Her {SCAN_HOURS} saatte otomatik tarar\n\n"
        f"Komutlar:\n"
        f"  /tara   — TikTok + 1688 tam analiz\n"
        f"  /1688   — sadece 1688 ürün analizi\n"
        f"  /tiktok — sadece TikTok trendleri\n"
        f"  /hafta  — bu haftanın trendleri\n"
        f"  /durum  — bu mesaj"
    )


# ── Başlangıç ──────────────────────────────────────────────────────────────────
async def main() -> None:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_full_scan, "interval", hours=SCAN_HOURS)
    scheduler.start()
    log.info("Zamanlayıcı aktif: her %d saatte bir tarar", SCAN_HOURS)

    async def delayed_start():
        await asyncio.sleep(5)
        await run_full_scan()

    asyncio.create_task(delayed_start())

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("tara",   cmd_tara))
    app.add_handler(CommandHandler("1688",   cmd_1688))
    app.add_handler(CommandHandler("tiktok", cmd_tiktok))
    app.add_handler(CommandHandler("hafta",  cmd_hafta))
    app.add_handler(CommandHandler("durum",  cmd_durum))

    log.info("Telegram botu başlatıldı")
    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
