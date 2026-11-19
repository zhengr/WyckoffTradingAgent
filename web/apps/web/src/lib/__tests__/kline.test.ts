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

  it('throws a neutral error when all sources fail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: () => Promise.resolve({}) }))

    await expect(fetchKlineWithQuality('603039', { tushare: null }, 'user1')).rejects.toThrow('无法获取K线数据')
  })
})
