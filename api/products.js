const CC_URL = 'https://ads.tiktok.com/creative_radar_api/v1/top_products/list';

const HEADERS = {
  'User-Agent':
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
  Accept: 'application/json, text/plain, */*',
  'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8',
  Referer: 'https://ads.tiktok.com/business/creativecenter/top-products/pc/en',
  Origin: 'https://ads.tiktok.com',
};

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS');
  if (req.method === 'OPTIONS') return res.status(200).end();

  const { period = '7', page = '1', country = 'TR', category = '' } = req.query;

  const params = new URLSearchParams({
    period,
    page,
    limit: '20',
    country_code: country,
    ...(category && { category_id: category }),
  });

  try {
    const response = await fetch(`${CC_URL}?${params}`, { headers: HEADERS });

    if (!response.ok) {
      return res.status(response.status).json({
        ok: false,
        error: `TikTok API yanıt vermedi (${response.status})`,
      });
    }

    const data = await response.json();

    // Normalize product list regardless of API shape
    const raw = data?.data?.list ?? data?.list ?? [];
    const products = raw.map((p) => ({
      id: p.item_id ?? p.id ?? '',
      title: p.title ?? p.item_title ?? '',
      cover: p.cover ?? p.item_cover ?? '',
      category: p.first_category_name ?? p.category_name ?? '',
      revenue_growth: p.revenue_growth_rate ?? null,
      sold_count: p.sold_count ?? null,
      price: p.price ?? null,
      link: p.item_url ?? `https://www.tiktok.com/search?q=${encodeURIComponent(p.title ?? '')}`,
      tag_url: `https://www.tiktok.com/tag/${encodeURIComponent((p.title ?? '').replace(/\s+/g, ''))}`,
    }));

    res.setHeader('Cache-Control', 's-maxage=1800, stale-while-revalidate=3600');
    return res.json({ ok: true, products, total: raw.length });
  } catch (err) {
    return res.status(500).json({ ok: false, error: err.message });
  }
}
