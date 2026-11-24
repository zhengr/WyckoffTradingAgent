/**
 * Server-side market data fetchers (Tencent / Sina).
 *
 * These run in the Cloudflare Worker (no CORS limits). Browser code must go
 * through the /api/kline and /api/quote routes instead of calling upstreams
 * directly. Shared chat tools call these helpers directly because the Worker's
 * tool fetch shim only rewrites /api/llm-proxy paths, not relative /api/* paths.
 */

export type ServerKlineRow = {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export type ServerQuote = {
  price: number | null
  previousClose: number | null
  changePct: number | null
  volume: number | null
  asOf: string | null
}

const TENCENT_FQKLINE = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
const TENCENT_KLINE = 'https://web.ifzq.gtimg.cn/appstock/app/kline/kline'
const TENCENT_MKLINE = 'https://ifzq.gtimg.cn/appstock/app/kline/mkline'
const TENCENT_MINUTE = 'https://web.ifzq.gtimg.cn/appstock/app/minute/query'
const TENCENT_QUOTE = 'https://qt.gtimg.cn/q='
const SINA_KLINE = 'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'
const THS_KLINE = 'https://d.10jqka.com.cn/v6/line/{symbol}/01/{tail}.js'

const UPSTREAM_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
  Referer: 'https://finance.sina.com.cn',
}
const UPSTREAM_TIMEOUT_MS = 15_000
const SH_PREFIXES = ['600', '601', '603', '605', '688', '510', '511', '512', '513', '515', '516', '518', '560', '561', '562', '563', '000', '001', '010', '011']
const BJ_PREFIXES = ['43', '83', '87', '920']
const MAX_COUNT = 800

type Fetcher = typeof globalThis.fetch

export type MarketKind = 'cn' | 'hk' | 'us'

/** Parse the code formats used across the app into a market kind + upstream symbol. */
export function resolveServerSymbol(raw: string): { kind: MarketKind; symbol: string; code: string } | null {
  const c = String(raw || '').trim().toUpperCase()
  if (!c) return null
  const hk = /^\d{5}$/.test(c) ? [c, c] : c.match(/^(\d{1,5})\.HK$/)
  if (hk) {
    const num = hk[1]!.padStart(5, '0')
    return { kind: 'hk', symbol: `hk${num}`, code: `${num}.HK` }
  }
  const us = c.match(/^([A-Z][A-Z0-9.-]{0,15})\.US$/)
  if (us) return { kind: 'us', symbol: `us${us[1]}`, code: c }
  const cnSuffix = c.match(/^(\d{6})\.(SH|SZ|BJ)$/)
  if (cnSuffix) return { kind: 'cn', symbol: `${cnSuffix[2]!.toLowerCase()}${cnSuffix[1]!}`, code: cnSuffix[1]! }
  if (/^\d{6}$/.test(c)) {
    let symbol: string
    if (BJ_PREFIXES.some((p) => c.startsWith(p))) symbol = `bj${c}`
    else if (SH_PREFIXES.some((p) => c.startsWith(p))) symbol = `sh${c}`
    else symbol = `sz${c}`
    return { kind: 'cn', symbol, code: c }
  }
  return null
}

function toDash(ymd: string): string {
  return `${ymd.slice(0, 4)}-${ymd.slice(4, 6)}-${ymd.slice(6, 8)}`
}

async function getJson(url: string, fetcher: Fetcher): Promise<unknown> {
  const resp = await fetcher(url, { headers: UPSTREAM_HEADERS, signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) })
  if (!resp.ok) throw new Error(`upstream http ${resp.status}`)
  return resp.json()
}

/** 同花顺返回 JSONP（quotebridge_v6_line_hs_xxx_01_yyy( {...} )），剥壳后解析。 */
async function getThsJson(url: string, fetcher: Fetcher): Promise<Record<string, unknown>> {
  const resp = await fetcher(url, { headers: UPSTREAM_HEADERS, signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) })
  if (!resp.ok) throw new Error(`upstream http ${resp.status}`)
  const text = await resp.text()
  const start = text.indexOf('(')
  const end = text.lastIndexOf(')')
  if (start === -1 || end <= start) throw new Error('ths jsonp format unexpected')
  return JSON.parse(text.slice(start + 1, end)) as Record<string, unknown>
}

export async function fetchTencentKline(
  code: string, start: string, end: string, adjust: string, fetcher: Fetcher = globalThis.fetch,
): Promise<ServerKlineRow[]> {
  const resolved = resolveServerSymbol(code)
  if (!resolved) return []
  const { symbol, kind } = resolved
  if (symbol.startsWith('bj')) throw new Error('tencent 无北交所 K 线')
  const isHk = kind === 'hk'
  const startD = toDash(start)
  const endD = toDash(end)
  const spanDays = Math.ceil((new Date(endD).getTime() - new Date(startD).getTime()) / 86400000) + 2
  const count = Math.min(Math.max(Math.trunc(spanDays * 1.5), 30), MAX_COUNT)
  const mode = adjust === 'hfq' ? 'hfq' : adjust === 'qfq' ? 'qfq' : ''

  // 美股：fqkline 带日期区间会返回空数组，只能不带日期取最近 N 根再本地过滤；
  // 港股走 kline/kline（不复权）；A股走 fqkline（支持 qfq/hfq + 日期区间）。
  const url = isHk ? TENCENT_KLINE : kind === 'us' ? TENCENT_FQKLINE : TENCENT_FQKLINE
  const param = isHk
    ? `${symbol},day,${startD},${endD},${count}`
    : kind === 'us'
      ? mode
        ? `${symbol},day,,,,${count},${mode}`
        : `${symbol},day,,,${count}`
      : mode
        ? `${symbol},day,${startD},${endD},${count},${mode}`
        : `${symbol},day,${startD},${endD},${count}`
  const payload = (await getJson(`${url}?param=${encodeURIComponent(param)}`, fetcher)) as Record<string, unknown>
  if (payload.code !== 0) throw new Error(`tencent code=${payload.code}`)
  const node = ((payload.data as Record<string, unknown>) || {})[symbol] as Record<string, unknown> | undefined
  const rows = (node?.[`${mode}day`] || node?.day || node?.qfqday || node?.hfqday) as unknown[] | undefined
  if (!Array.isArray(rows) || !rows.length) return []
  const out: ServerKlineRow[] = []
  for (const r of rows) {
    if (!Array.isArray(r) || r.length < 6) continue
    const date = String(r[0])
    if (date < startD || date > endD) continue
    const open = Number(r[1])
    const close = Number(r[2])
    const high = Number(r[3])
    const low = Number(r[4])
    const volume = Number(r[5]) * (kind === 'cn' ? 100 : 1)
    if (!(close > 0)) continue
    out.push({ date, open, high, low, close, volume })
  }
  return out.sort((a, b) => a.date.localeCompare(b.date))
}

export async function fetchSinaKline(code: string, start: string, end: string, _adjust: string, fetcher: Fetcher = globalThis.fetch): Promise<ServerKlineRow[]> {
  const resolved = resolveServerSymbol(code)
  if (!resolved || resolved.kind !== 'cn') return []
  const symbol = resolved.symbol
  if (symbol.startsWith('bj')) throw new Error('sina 无北交所 K 线')
  const startD = toDash(start)
  const endD = toDash(end)
  const spanDays = Math.ceil((new Date(endD).getTime() - new Date(startD).getTime()) / 86400000) + 2
  const datalen = Math.min(Math.max(Math.trunc(spanDays * 1.5), 30), 1023)
  const rows = (await getJson(`${SINA_KLINE}?symbol=${symbol}&scale=240&ma=no&datalen=${datalen}`, fetcher)) as Array<Record<string, string>>
  if (!Array.isArray(rows)) return []
  const out: ServerKlineRow[] = []
  for (const r of rows) {
    const date = String(r.day || '')
    if (date < startD || date > endD) continue
    const close = Number(r.close)
    if (!(close > 0)) continue
    out.push({ date, open: Number(r.open), high: Number(r.high), low: Number(r.low), close, volume: Number(r.volume) })
  }
  return out.sort((a, b) => a.date.localeCompare(b.date))
}

/** Tencent -> Sina fallback. Returns null when every upstream failed. */
export async function fetchServerKline(
  code: string, start: string, end: string, adjust = 'qfq', fetcher: Fetcher = globalThis.fetch,
): Promise<{ data: ServerKlineRow[]; source: 'tencent' | 'sina' | 'ths' } | null> {
  const resolved = resolveServerSymbol(code)
  // 北交所：腾讯/新浪都无数据，走同花顺（hs_ 前缀）
  if (resolved?.symbol.startsWith('bj')) {
    try {
      const rows = await fetchThsKline(code, start, end, fetcher)
      if (rows.length) return { data: rows.slice(-320), source: 'ths' }
    } catch (err) {
      if (typeof console !== 'undefined') console.warn('[market-data] ths kline failed:', err instanceof Error ? err.message : err)
    }
    return null
  }
  for (const [source, upstream] of [['tencent', fetchTencentKline], ['sina', fetchSinaKline]] as const) {
    try {
      const rows = await upstream(code, start, end, adjust, fetcher)
      if (rows.length) return { data: rows.slice(-320), source }
    } catch { /* try next */ }
  }
  return null
}

/** Tencent minute klines: period in 1m/5m/15m. Best effort. */
export async function fetchServerIntraday(code: string, period: '1m' | '5m' | '15m', fetcher: Fetcher = globalThis.fetch): Promise<ServerKlineRow[]> {
  const resolved = resolveServerSymbol(code)
  if (!resolved) return []
  const { symbol } = resolved
  try {
    if (period === '1m') {
      const payload = (await getJson(`${TENCENT_MINUTE}?code=${symbol}`, fetcher)) as Record<string, unknown>
      const data = ((payload.data as Record<string, unknown>) || {})[symbol] as Record<string, unknown> | undefined
      const inner = (data?.data as Record<string, unknown>) || {}
      const lines = Array.isArray(inner.data) ? inner.data : []
      const day = String(inner.date || '').replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3')
      const out: ServerKlineRow[] = []
      for (const line of lines) {
        const parts = String(line).trim().split(/\s+/)
        if (parts.length < 3) continue
        const close = Number(parts[1])
        if (!(close > 0)) continue
        const volume = Number(parts[2])
        out.push({ date: `${day} ${parts[0]}`.trim(), open: close, high: close, low: close, close, volume })
      }
      return out
    }
    const m = period === '5m' ? 'm5' : 'm15'
    const payload = (await getJson(`${TENCENT_MKLINE}?param=${encodeURIComponent(`${symbol},${m},,160`)}`, fetcher)) as Record<string, unknown>
    const data = ((payload.data as Record<string, unknown>) || {})[symbol] as Record<string, unknown> | undefined
    const rows = (data?.[m] as unknown[] | undefined) || []
    const out: ServerKlineRow[] = []
    for (const r of rows) {
      if (!Array.isArray(r) || r.length < 6) continue
      const close = Number(r[2])
      if (!(close > 0)) continue
      out.push({ date: String(r[0]), open: Number(r[1]), close, high: Number(r[3]), low: Number(r[4]), volume: Number(r[5]) })
    }
    return out
  } catch {
    return []
  }
}

/** Batch realtime quotes via Tencent qt.gtimg.cn. Keyed by requested codes and symbols. */
/** 同花顺日线（北交所 hs_ 前缀）：JSONP 包裹，按年文件取，data="date,open,high,low,close,volume,amount,amp,..." 分号分隔。 */
async function fetchThsKline(code: string, start: string, end: string, fetcher: Fetcher): Promise<ServerKlineRow[]> {
  const resolved = resolveServerSymbol(code)
  if (!resolved || resolved.kind !== 'cn') return []
  const symbol = `hs_${resolved.code}`
  const startNum = start
  const endNum = end
  const startYear = Number(start.slice(0, 4))
  const endYear = Number(end.slice(0, 4))
  const out: ServerKlineRow[] = []
  for (let y = startYear; y <= endYear; y++) {
    const raw = await getThsJson(
      THS_KLINE.replace('{symbol}', symbol).replace('{tail}', `${y}.js`),
      fetcher,
    ) as Record<string, unknown>
    const dataStr = String((raw as Record<string, unknown>).data || '')
    if (!dataStr) continue
    for (const row of dataStr.split(';')) {
      const f = row.split(',')
      if (f.length < 7) continue
      const dateNum = f[0]!.trim()
      if (dateNum < startNum || dateNum > endNum) continue
      const close = Number(f[4])
      if (!(close > 0)) continue
      out.push({
        date: `${dateNum.slice(0, 4)}-${dateNum.slice(4, 6)}-${dateNum.slice(6, 8)}`,
        open: Number(f[1]),
        high: Number(f[2]),
        low: Number(f[3]),
        close,
        volume: Number(f[5]),
      })
    }
  }
  return out.sort((a, b) => a.date.localeCompare(b.date))
}

export async function fetchServerQuotes(codes: string[], fetcher: Fetcher = globalThis.fetch): Promise<Record<string, ServerQuote>> {
  const resolved = codes.map((code) => resolveServerSymbol(code)).filter((r): r is NonNullable<typeof r> => Boolean(r))
  if (resolved.length === 0) return {}
  const symbols = Array.from(new Set(resolved.map((r) => r.symbol)))
  const resp = await fetcher(`${TENCENT_QUOTE}${symbols.join(',')}`, {
    headers: { 'User-Agent': UPSTREAM_HEADERS['User-Agent'] },
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
  })
  if (!resp.ok) throw new Error(`quote http ${resp.status}`)
  const text = await resp.text()
  const bySymbol = new Map<string, ServerQuote>()
  for (const match of text.matchAll(/v_([A-Za-z0-9]+)="([^"]*)"/g)) {
    const symbol = match[1]!
    const fields = match[2]!.split('~')
    if (fields.length < 6) continue
    const price = num(fields[3])
    const previousClose = num(fields[4])
    const changePct = num(fields[32])
    const volume = num(fields[6])
    const asOf = formatStamp(fields[30])
    if (price == null) continue
    bySymbol.set(symbol, { price, previousClose, changePct, volume, asOf })
  }
  const result: Record<string, ServerQuote> = {}
  for (const r of resolved) {
    const quote = bySymbol.get(r.symbol)
    if (!quote) continue
    result[r.symbol] = quote
    result[r.code] = quote
    result[r.code.split('.')[0]!] = quote
  }
  return result
}

function num(value: string | undefined): number | null {
  const n = Number(value)
  return Number.isFinite(n) && n > 0 ? n : null
}

function formatStamp(raw: string | undefined): string | null {
  const s = String(raw || '')
  const m = s.match(/^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$/)
  return m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}+08:00` : null
}
