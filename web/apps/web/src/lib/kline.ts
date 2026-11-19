import { buildKlineDataQuality, isCnSymbol, normalizeTushareCode } from '@wyckoff/shared'
import type { KlineDataQuality, KlineRow } from '@wyckoff/shared'

import { supabase } from './supabase'

type Fetcher = typeof globalThis.fetch

async function tusharePostWithFetch(fetcher: Fetcher, token: string, api_name: string, params: Record<string, string>, fields: string) {
  const resp = await fetcher('/api/llm-proxy/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Target-URL': 'https://api.tushare.pro' },
    body: JSON.stringify({ api_name, token, params, fields }),
  })
  if (!resp.ok) return null
  return (await resp.json()) as { data?: { fields?: string[]; items?: unknown[][] } }
}

async function tusharePost(token: string, api_name: string, params: Record<string, string>, fields: string) {
  return tusharePostWithFetch(globalThis.fetch, token, api_name, params, fields)
}

export async function fetchKlineViaTushare(code: string, token: string, startDate: string, endDate: string): Promise<KlineRow[]> {
  const tsCode = normalizeTushareCode(code)
  const [dailyJson, adjJson] = await Promise.all([
    tusharePost(token, 'daily', { ts_code: tsCode, start_date: startDate, end_date: endDate }, 'trade_date,open,high,low,close,vol'),
    tusharePost(token, 'adj_factor', { ts_code: tsCode, start_date: startDate, end_date: endDate }, 'trade_date,adj_factor'),
  ])
  const items = dailyJson?.data?.items
  if (!Array.isArray(items) || items.length === 0) return []

  const adjItems = adjJson?.data?.items
  // 北交所/新股等可能没有复权因子记录（或接口限频返回空）：按不复权处理（ratio=1），
  // 不能因此整体返回空，否则整条 Tushare 链对该标的失效。
  const adjMap = new Map<string, number>()
  let latestDate = ''
  if (Array.isArray(adjItems) && adjItems.length > 0) {
    for (const row of adjItems) {
      const dt = String(row[0])
      adjMap.set(dt, Number(row[1]))
      if (dt > latestDate) latestDate = dt
    }
  }
  const latestFactor = adjMap.get(latestDate) || 1

  return items.map(row => {
    const dt = String(row[0] || '')
    const factor = adjMap.get(dt) || latestFactor
    const ratio = factor / latestFactor
    return {
      date: dt.replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3'),
      open: Number(row[1] || 0) * ratio, high: Number(row[2] || 0) * ratio,
      low: Number(row[3] || 0) * ratio, close: Number(row[4] || 0) * ratio,
      volume: Number(row[5] || 0),
    }
  }).filter(d => d.date && d.close > 0)
}

export async function getUserDataKeys(userId: string): Promise<{ tushare: string | null }> {
  const { data } = await supabase
    .from('user_settings')
    .select('tushare_token')
    .eq('user_id', userId)
    .single()
  return {
    tushare: String(data?.tushare_token || '').trim() || null,
  }
}

export async function fetchKlineViaServerApi(
  code: string,
  startCompact: string,
  endCompact: string,
  adjust: 'qfq' | 'hfq' | '' = 'qfq',
): Promise<{ data: KlineRow[]; source: string } | null> {
  try {
    const params = new URLSearchParams({ code, start: startCompact, end: endCompact, adjust })
    const resp = await fetch(`/api/kline?${params}`)
    if (!resp.ok) return null
    const payload = (await resp.json()) as { data?: KlineRow[]; source?: string }
    if (!Array.isArray(payload.data) || !payload.data.length) return null
    return { data: payload.data, source: String(payload.source || 'server') }
  } catch {
    return null
  }
}

export async function fetchKlineWithQuality(
  code: string,
  keys: { tushare: string | null },
  _userId: string,
): Promise<{ data: KlineRow[]; quality: KlineDataQuality }> {
  const end = new Date(); end.setDate(end.getDate() - 1)
  const start = new Date(); start.setDate(start.getDate() - 500)
  const fmtCompact = (d: Date) => d.toISOString().slice(0, 10).replace(/-/g, '')
  const isCn = isCnSymbol(code)

  if (isCn && keys.tushare) {
    try {
      const r = await fetchKlineViaTushare(code, keys.tushare, fmtCompact(start), fmtCompact(end))
      if (r.length) {
        const data = r.sort((a, b) => a.date.localeCompare(b.date)).slice(-320)
        return { data, quality: buildKlineDataQuality('tushare', 320, data) }
      }
    } catch { /* fall through to server proxy */ }
  }
  const serverHit = await fetchKlineViaServerApi(code, fmtCompact(start), fmtCompact(end), 'qfq')
  if (serverHit && serverHit.data.length) {
    const data = serverHit.data.slice(-320)
    const src = serverHit.source === 'sina' ? 'sina' : 'tencent'
    return { data, quality: buildKlineDataQuality(src, 320, data, Boolean(keys.tushare)) }
  }
  throw new Error(`无法获取K线数据。请检查股票代码或稍后重试（支持 A股6位、00700.HK、AAPL.US）。`)
}

export async function fetchKline(
  code: string,
  keys: { tushare: string | null },
  userId: string,
): Promise<KlineRow[]> {
  return (await fetchKlineWithQuality(code, keys, userId)).data
}
