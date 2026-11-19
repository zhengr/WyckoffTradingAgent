import { describe, expect, it, vi } from 'vitest'
import { refreshPortfolioTotalEquity } from '@wyckoff/shared'

function createSupabase() {
  const updates: Record<string, unknown>[] = []
  const rows: Record<string, unknown> = {
    portfolios: { data: { free_cash: 25_000 }, error: null },
    portfolio_positions: {
      data: [{ code: '600519', shares: 10 }, { code: '06881.HK', shares: 1000 }],
      error: null,
    },
    user_settings: { data: {}, error: null },
  }
  return {
    updates,
    client: {
      from(table: string) {
        let result = rows[table]
        const chain = {
          select: vi.fn(() => chain),
          update: vi.fn((payload: Record<string, unknown>) => {
            updates.push(payload)
            result = { data: [payload], error: null }
            return chain
          }),
          eq: vi.fn(() => chain),
          single: vi.fn(async () => result),
          then(resolve: (value: unknown) => void) { resolve(result) },
        }
        return chain
      },
    },
  }
}

function quoteText(entries: Array<[string, string, string]>) {
  return entries.map(([sym, price, pct]) => {
    const f = Array(34).fill('0')
    f[1] = 'NAME'
    f[2] = sym
    f[3] = price
    f[4] = '100'
    f[6] = '1000'
    f[30] = '20261118150000'
    f[32] = pct
    return `v_${sym}="${f.join('~')}"`
  }).join('\n')
}

describe('refreshPortfolioTotalEquity', () => {
  it('uses server quotes and converts HKD with the official CNY cross rate', async () => {
    const supabase = createSupabase()
    const fetcher = vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('qt.gtimg.cn')) {
        return new Response(quoteText([['sh600519', '1500', '0.67'], ['hk06881', '7.63', '1.2']]), { status: 200 })
      }
      return Response.json([{ base: 'CNY', quote: 'HKD', rate: 1.1627906977 }])
    })

    const result = await refreshPortfolioTotalEquity(
      { supabase: supabase.client as never, fetch: fetcher as never },
      'u1',
    )

    expect(result).toMatchObject({ ok: true, totalEquity: 46_561.8 })
    expect(supabase.updates[0]).toMatchObject({ total_equity: 46_561.8 })
  })

  it('does not overwrite total_equity when any quote is missing', async () => {
    const supabase = createSupabase()
    const fetcher = vi.fn(async (input: string | URL | Request) => {
      if (String(input).includes('qt.gtimg.cn')) return new Response('', { status: 200 })
      return Response.json([])
    })

    const result = await refreshPortfolioTotalEquity(
      { supabase: supabase.client as never, fetch: fetcher as never },
      'u1',
    )

    expect(result.ok).toBe(false)
    expect(supabase.updates).toEqual([])
  })
})
