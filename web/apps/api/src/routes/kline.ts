import { Hono } from 'hono'
import { fetchServerIntraday, fetchServerKline } from '@wyckoff/shared'

/**
 * 服务端行情代理：
 *   /api/kline?code=600519&start=20260101&end=20261118&adjust=qfq
 *   /api/kline?code=00700.HK&start=...&end=...&adjust=qfq
 *   /api/kline?code=600519&start=...&end=...&period=5m
 *
 * Worker 服务端直连腾讯（主）/ 新浪（备），不受 CORS 限制，也不需要用户配置密钥。
 * 只接受白名单上游域名和严格校验的入参，不能当作开放代理。
 */

export type KlineRowOut = {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export const klineRoutes = new Hono()

const CODE_PATTERN = /^(?:\d{6}(?:\.(?:SH|SZ|BJ|HK))?|\d{5}(?:\.HK)?|[A-Z][A-Z0-9.-]{0,15}\.US)$/
const PERIOD_PATTERN = /^(?:day|1m|5m|15m)$/

klineRoutes.get('/', async (c) => {
  const code = String(c.req.query('code') || '').trim().toUpperCase()
  const start = String(c.req.query('start') || '').trim()
  const end = String(c.req.query('end') || '').trim()
  const adjust = String(c.req.query('adjust') || 'qfq').trim().toLowerCase()
  const period = String(c.req.query('period') || 'day').trim().toLowerCase()

  if (!CODE_PATTERN.test(code)) return c.json({ error: 'code 必须是 6 位数字或 00700.HK / AAPL.US 格式' }, 400)
  if (!PERIOD_PATTERN.test(period)) return c.json({ error: 'period 只允许 day/1m/5m/15m' }, 400)
  if (!/^\d{8}$/.test(start) || !/^\d{8}$/.test(end)) return c.json({ error: 'start/end 必须是 YYYYMMDD' }, 400)
  if (start > end) return c.json({ error: 'start 不能大于 end' }, 400)
  if (!['', 'qfq', 'hfq', 'none'].includes(adjust)) return c.json({ error: 'adjust 只允许 qfq/hfq/none' }, 400)

  if (period !== 'day') {
    const rows = await fetchServerIntraday(code, period as '1m' | '5m' | '15m')
    if (!rows.length) return c.json({ error: 'minute kline unavailable' }, 502)
    return c.json({ data: rows.slice(-320), source: 'tencent', period })
  }

  const hit = await fetchServerKline(code, start, end, adjust)
  if (!hit) return c.json({ error: 'kline sources failed' }, 502)
  return c.json({ data: hit.data, source: hit.source })
})
