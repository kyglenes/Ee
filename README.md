# TikTok Made Me Buy It — AI Ürün Ajanı

**Tamamen otonom:** Claude düşünür → TikTok tarar → Telegram'dan telefonuna gönderir.

---

## Kurulum (5 dakika)

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

`.env` dosyasını düzenle (3 değişken):

| Değişken | Nasıl alınır |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |
| `TELEGRAM_BOT_TOKEN` | Telegram'da @BotFather → /newbot |
| `TELEGRAM_CHAT_ID` | Telegram'da @userinfobot'a mesaj at |

## Çalıştır

```bash
python agent.py
```

Ajan başlar, 5 saniye sonra ilk taramayı yapar ve sonuçları Telegram'a gönderir.

## Telefon Komutları

Telegram'dan bota yaz:

| Komut | Ne yapar |
|---|---|
| `/tara` | Hemen tarama başlat |
| `/hafta` | Bu haftanın trendleri |
| `/ay` | Bu ayın trendleri |
| `/durum` | Ajan durumu |

## Nasıl çalışır?

1. **Veri çekme** — TikTok Creative Center API'sinden trend ürünleri alır
2. **AI analizi** — Claude Opus 4.7 (adaptive thinking) ürünleri analiz eder, ranklar
3. **Telegram** — Sonuçları doğrudan telefonuna gönderir
4. **Otomatik** — Her `SCAN_INTERVAL_HOURS` saatte bir tekrarlar (varsayılan: 6 saat)

## Web Arayüzü (opsiyonel)

Vercel'e deploy edip tarayıcıdan da kullanabilirsin:

```bash
npm i -g vercel && vercel --prod
```
