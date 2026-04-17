# TikTok Made Me Buy It – Ürün Arama

TikTok'taki **#TikTokMadeMeBuyIt** trendindeki ürünleri keşfetmek için Flask tabanlı web uygulaması.

## Kurulum

```bash
pip install -r requirements.txt
playwright install chromium
```

## Yapılandırma

```bash
cp .env.example .env
# .env dosyasını düzenleyip MS_TOKEN değerini girin
```

**MS_TOKEN nasıl alınır?**
1. Tarayıcıda `https://www.tiktok.com` adresini açın
2. `F12` → *Application* → *Cookies* → *tiktok.com*
3. `msToken` çerezini bulup değerini kopyalayın

## Çalıştırma

```bash
python app.py
```

Tarayıcıda `http://localhost:5000` adresini açın.

## API Uç Noktaları

| Uç Nokta | Parametre | Açıklama |
|---|---|---|
| `GET /api/hashtag` | `tag`, `count` | Hashtag videolarını getirir |
| `GET /api/search` | `q`, `count` | Anahtar kelimeyle arar |
