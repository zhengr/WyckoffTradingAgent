import { Hono } from 'hono'

/**
 * 服务端 K 线代理：/api/kline?code=600519&start=20260101&end=20261118&adjust=qfq
 *
 * 前端单股分析原本只走浏览器直连的 TickFlow（经 /api/llm-proxy）和 Tushare，
 * TickFlow key 失效/额度不足时页面直接报错。本路由在 Worker 服务端拉取
 * 腾讯（主） / 新浪（备）日 K —— 服务端不受 CORS 限制，也不需要把行情域名
 * 加进 llm-proxy 白名单。
 *
 * 安全：只允许固定的两个上游域名，入参严格校验（6 位数字代码 + 日期 + 白名单复权模式），
 * 不接受任何用户传入的 URL，因此不能被当作开放代理。
 */

export type KlineRowOut = {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

const TENCENT_FQKLINE = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
const TENCENT_HK_KLINE = 'https://web.ifzq.gtimg.cn/appstock/app/kline/kline'
const SINA_KLINE = 'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'

const UPSTREAM_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
  Referer: 'https://finance.sina.com.cn',
}
const UPSTREAM_TIMEOUT_MS = 15_000
const SH_PREFIXES = ['600', '601', '603', '605', '688', '510', '511', '512', '513', '515', '516', '518', '560', '561', '562', '563']
const BJ_PREFIXES = ['43', '83', '87', '920']
const MAX_COUNT = 800

export const klineRoutes = new Hono()

klineRoutes.get('/', async (c) => {
  const code = String(c.req.query('code') || '').trim()
  const start = String(c.req.query('start') || '').trim()
  const end = String(c.req.query('end') || '').trim()
  const adjust = String(c.req.query('adjust') || 'qfq').trim().toLowerCase()

  if (!/^\d{6}$/.test(code)) return c.json({ error: 'code 必须是 6 位数字' }, 400)
  if (!/^\d{8}$/.test(start) || !/^\d{8}$/.test(end)) return c.json({ error: 'start/end 必须是 YYYYMMDD' }, 400)
  if (start > end) return c.json({ error: 'start 不能大于 end' }, 400)
  if (!['', 'qfq', 'hfq', 'none'].includes(adjust)) return c.json({ error: 'adjust 只允许 qfq/hfq/none' }, 400)

  const errors: string[] = []
  const fetchers: Array<[string, typeof fetchTencentKline]> = [
    ['tencent', fetchTencentKline],
    ['sina', fetchSinaKline],
  ]
  for (const [name, fetcher] of fetchers) {
    try {
      const rows = await fetcher(code, start, end, adjust)
      if (rows.length) {
        return c.json({ data: rows.slice(-320), source: name })
      }
      errors.push(`${name}: empty`)
    } catch (err) {
      errors.push(`${name}: ${err instanceof Error ? err.message : String(err)}`)
    }
  }
  return c.json({ error: `kline sources failed: ${errors.join('; ')}` }, 502)
})

function toDash(ymd: string): string {
  return `${ymd.slice(0, 4)}-${ymd.slice(4, 6)}-${ymd.slice(6, 8)}`
}

function tencentSymbol(code: string): string {
  if (code.startsWith('00') || code.startsWith('30')) return `hk${code.padStart(5, '0')}`
  if (BJ_PREFIXES.some((p) => code.startsWith(p))) return `bj${code}`
  if (SH_PREFIXES.some((p) => code.startsWith(p))) return `sh${code}`
  return `sz${code}`
}

function sinaSymbol(code: string): string {
  if (BJ_PREFIXES.some((p) => code.startsWith(p))) return `bj${code}`
  if (SH_PREFIXES.some((p) => code.startsWith(p))) return `sh${code}`
  return `sz${code}`
}

async function fetchTencentKline(code: string, start: string, end: string, adjust: string): Promise<KlineRowOut[]> {
  const symbol = tencentSymbol(code)
  const isHk = symbol.startsWith('hk')
  if (symbol.startsWith('bj')) throw new Error('tencent 无北交所 K 线')
  const startD = toDash(start)
  const endD = toDash(end)
  const spanDays = Math.ceil((new Date(endD).getTime() - new Date(startD).getTime()) / 86400000) + 2
  const count = Math.min(Math.max(Math.trunc(spanDays * 1.5), 30), MAX_COUNT)
  const mode = adjust === 'hfq' ? 'hfq' : adjust === 'qfq' ? 'qfq' : ''

  const url = isHk ? TENCENT_HK_KLINE : TENCENT_FQKLINE
  const param = isHk
    ? `${symbol},day,${startD},${endD},${count}`
    : mode
      ? `${symbol},day,${startD},${endD},${count},${mode}`
      : `${symbol},day,${startD},${endD},${count}`
  const resp = await fetch(`${url}?param=${encodeURIComponent(param)}`, {
    headers: UPSTREAM_HEADERS,
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
  })
  if (!resp.ok) throw new Error(`tencent http ${resp.status}`)
  const payload = (await resp.json()) as Record<string, unknown>
  if (payload.code !== 0) throw new Error(`tencent code=${payload.code}`)
  const node = ((payload.data as Record<string, unknown>) || {})[symbol] as Record<string, unknown> | undefined
  const rows = (node?.[`${mode}day`] || node?.day || node?.qfqday || node?.hfqday) as unknown[] | undefined
  if (!Array.isArray(rows) || !rows.length) return []
  const out: KlineRowOut[] = []
  for (const r of rows) {
    if (!Array.isArray(r) || r.length < 6) continue
    const date = String(r[0])
    if (date < startD || date > endD) continue
    const open = Number(r[1])
    const close = Number(r[2])
    const high = Number(r[3])
    const low = Number(r[4])
    const volume = Number(r[5]) * (isHk ? 1 : 100) // A 股腾讯 volume 单位是手
    if (!(close > 0)) continue
    out.push({ date, open, high, low, close, volume })
  }
  return out.sort((a, b) => a.date.localeCompare(b.date))
}

async function fetchSinaKline(code: string, start: string, end: string, _adjust: string): Promise<KlineRowOut[]> {
  const symbol = sinaSymbol(code)
  if (symbol.startsWith('bj')) throw new Error('sina 无北交所 K 线')
  const startD = toDash(start)
  const endD = toDash(end)
  const spanDays = Math.ceil((new Date(endD).getTime() - new Date(startD).getTime()) / 86400000) + 2
  const datalen = Math.min(Math.max(Math.trunc(spanDays * 1.5), 30), 1023)
  const url = `${SINA_KLINE}?symbol=${symbol}&scale=240&ma=no&datalen=${datalen}`
  const resp = await fetch(url, { headers: UPSTREAM_HEADERS, signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) })
  if (!resp.ok) throw new Error(`sina http ${resp.status}`)
  const rows = (await resp.json()) as Array<Record<string, string>>
  if (!Array.isArray(rows)) return []
  const out: KlineRowOut[] = []
  for (const r of rows) {
    const date = String(r.day || '')
    if (date < startD || date > endD) continue
    const close = Number(r.close)
    if (!(close > 0)) continue
    out.push({
      date,
      open: Number(r.open),
      high: Number(r.high),
      low: Number(r.low),
      close,
      volume: Number(r.volume),
    })
  }
  return out.sort((a, b) => a.date.localeCompare(b.date))
}
