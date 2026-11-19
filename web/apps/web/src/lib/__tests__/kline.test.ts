import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchKlineWithQuality } from '../kline'

vi.mock('@/lib/supabase', () => ({
  supabase: { from: () => ({ select: () => ({ eq: () => ({ single: async () => ({ data: null }) }) }) }) },
}))

describe('fetchKlineWithQuality', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('falls back to the server /api/kline proxy when no tushare token', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        data: [
          { date: '2024-01-01', open: 10, high: 11, low: 9, close: 10.5, volume: 1000 },
          { date: '2024-01-02', open: 11, high: 12, low: 10, close: 11.5, volume: 1200 },
        ],
        source: 'tencent',
      }),
    }))

    const { data, quality } = await fetchKlineWithQuality('603039', { tushare: null }, 'user1')

    expect(quality.source).toBe('tencent')
    expect(data.map((row) => row.date)).toEqual(['2024-01-01', '2024-01-02'])
    expect(data[0]).toMatchObject({ open: 10, close: 10.5, volume: 1000 })
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/kline?'))
  })


  it('returns unadjusted rows for BSE stocks when tushare adj_factor is empty', async () => {
    // 北交所（92xxxx）tushare daily 有数据，但 adj_factor 常为空/限频——不应因此整体返回空
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/api/llm-proxy/')) {
        const body = String(init?.body ?? '')
        const isAdj = body.includes('adj_factor')
        return Promise.resolve({ ok: true, json: async () => (isAdj
          ? { code: 0, data: { fields: ['trade_date', 'adj_factor'], items: [] } }
          : { code: 0, data: { fields: ['trade_date', 'open', 'high', 'low', 'close', 'vol'], items: [['20261118', 30.0, 30.0, 27.98, 28.16, 8201.7]] } }) })
      }
      return Promise.resolve({ ok: false, json: async () => ({}) })
    }))

    const { data, quality } = await fetchKlineWithQuality('920029', { tushare: 'tok' }, 'user1')
    expect(quality.source).toBe('tushare')
    expect(data).toHaveLength(1)
    expect(data[0]?.close).toBeCloseTo(28.16) // 不复权原价
  })

  it('throws a neutral error when all sources fail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: () => Promise.resolve({}) }))

    await expect(fetchKlineWithQuality('603039', { tushare: null }, 'user1')).rejects.toThrow('无法获取K线数据')
  })
})
