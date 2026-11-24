import { describe, expect, it, vi, beforeEach } from 'vitest'
import { klineRoutes } from './kline'

function makeReq(query: Record<string, string>) {
  const qs = new URLSearchParams(query).toString()
  return new Request(`http://localhost/?${qs}`)
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('kline route', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  it('rejects invalid code', async () => {
    const res = await klineRoutes.fetch(makeReq({ code: 'abc', start: '20260101', end: '20261118' }))
    expect(res.status).toBe(400)
  })

  it('rejects bad date range', async () => {
    const res = await klineRoutes.fetch(makeReq({ code: '600519', start: '20261118', end: '20260101' }))
    expect(res.status).toBe(400)
  })

  it('rejects unknown adjust mode', async () => {
    const res = await klineRoutes.fetch(
      makeReq({ code: '600519', start: '20260101', end: '20261118', adjust: 'xyz' }),
    )
    expect(res.status).toBe(400)
  })

  it('returns tencent rows with volume converted from 手 to 股', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('ifzq.gtimg.cn')) {
        return jsonResponse({
          code: 0,
          data: {
            sh600519: {
              qfqday: [
                ['2026-11-17', '1450.000', '1456.660', '1457.000', '1445.000', '20000.000'],
                ['2026-11-18', '1450.000', '1442.660', '1456.000', '1431.700', '29847.000'],
              ],
            },
          },
        })
      }
      throw new Error('unexpected upstream ' + url)
    })
    vi.stubGlobal('fetch', fetchMock)

    const res = await klineRoutes.fetch(
      makeReq({ code: '600519', start: '20261101', end: '20261118', adjust: 'qfq' }),
    )
    expect(res.status).toBe(200)
    const body = (await res.json()) as { data: Array<Record<string, number | string>>; source: string }
    expect(body.source).toBe('tencent')
    expect(body.data).toHaveLength(2)
    expect(body.data[1].date).toBe('2026-11-18')
    expect(body.data[1].close).toBeCloseTo(1442.66)
    expect(body.data[1].volume).toBeCloseTo(29847 * 100)
  })

  it('falls back to sina when tencent returns empty', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('ifzq.gtimg.cn')) {
        return jsonResponse({ code: 0, data: { sh600519: { qfqday: [] } } })
      }
      if (url.includes('sina.com.cn')) {
        return jsonResponse([
          { day: '2026-11-17', open: '1450.000', high: '1457.000', low: '1445.000', close: '1456.660', volume: '2000000' },
          { day: '2026-11-18', open: '1450.000', high: '1456.000', low: '1431.700', close: '1442.660', volume: '2984695' },
        ])
      }
      throw new Error('unexpected upstream')
    })
    vi.stubGlobal('fetch', fetchMock)

    const res = await klineRoutes.fetch(
      makeReq({ code: '600519', start: '20261101', end: '20261118', adjust: 'qfq' }),
    )
    expect(res.status).toBe(200)
    const body = (await res.json()) as { data: unknown[]; source: string }
    expect(body.source).toBe('sina')
    expect(body.data).toHaveLength(2)
  })

  it('returns 502 when all sources fail', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({}, 500)))
    const res = await klineRoutes.fetch(
      makeReq({ code: '600519', start: '20261101', end: '20261118' }),
    )
    expect(res.status).toBe(502)
  })

  it('returns BSE rows from ths when tencent/sina have none', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('ifzq.gtimg.cn')) {
        return jsonResponse({ code: 0, data: { bj920029: { day: [] } } })
      }
      if (url.includes('sina.com.cn')) {
        throw new Error('sina no BSE')
      }
      if (url.includes('push2his.eastmoney.com') && url.includes('920029')) {
        return jsonResponse({
          data: { code: '920029', klines: ['2026-11-17,30.21,29.90,30.50,30.21,3265374', '2026-11-18,30.00,28.16,30.00,27.98,8201700'] },
        })
      }
      throw new Error('unexpected upstream ' + url)
    })
    vi.stubGlobal('fetch', fetchMock)

    const res = await klineRoutes.fetch(
      makeReq({ code: '920029', start: '20261110', end: '20261118' }),
    )
    expect(res.status).toBe(200)
    const body = (await res.json()) as { data: Array<Record<string, number | string>>; source: string }
    expect(body.source).toBe('ths')
    expect(body.data).toHaveLength(2)
    expect(body.data[1].close).toBeCloseTo(28.16)
    expect(body.data[1].date).toBe('2026-11-18')
  })

  it('returns US rows from tencent fqkline without date range', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('fqkline') && url.includes('usAAPL')) {
        // 带日期会空，这里模拟"最近N根"模式的数据
        return jsonResponse({
          code: 0,
          data: {
            usAAPL: {
              day: [
                ['2026-11-10', '350.00', '348.50', '352.00', '347.00', '50000000.000'],
                ['2026-11-18', '351.94', '352.45', '356.00', '350.00', '58588703.000'],
              ],
            },
          },
        })
      }
      throw new Error('unexpected upstream')
    })
    vi.stubGlobal('fetch', fetchMock)

    const res = await klineRoutes.fetch(
      makeReq({ code: 'AAPL.US', start: '20261110', end: '20261118', adjust: 'qfq' }),
    )
    expect(res.status).toBe(200)
    const body = (await res.json()) as { data: Array<Record<string, number | string>>; source: string }
    expect(body.source).toBe('tencent')
    expect(body.data).toHaveLength(2)
    expect(body.data[1].close).toBeCloseTo(352.45)
  })

})
