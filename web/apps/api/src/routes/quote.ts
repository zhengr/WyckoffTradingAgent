import { Hono } from 'hono'
import { fetchServerQuotes } from '@wyckoff/shared'

/** Server-side realtime quote proxy: /api/quote?symbols=600519,00700.HK,AAPL.US */
export const quoteRoutes = new Hono()

quoteRoutes.get('/', async (c) => {
  const symbols = String(c.req.query('symbols') || c.req.query('code') || '')
    .split(',')
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, 30)
  if (symbols.length === 0) return c.json({ data: [] })
  try {
    const quotes = await fetchServerQuotes(symbols)
    const data = Object.entries(quotes).map(([symbol, quote]) => ({ symbol, ...quote }))
    return c.json({ data })
  } catch (error) {
    return c.json({ error: error instanceof Error ? error.message : 'quote source failed' }, 502)
  }
})
