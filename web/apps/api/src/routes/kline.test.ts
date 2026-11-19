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
})
