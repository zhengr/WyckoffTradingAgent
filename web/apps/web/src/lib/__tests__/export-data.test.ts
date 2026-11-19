import { describe, expect, it } from 'vitest'
import { arrayToCSV, buildEnhancedRows, exportSymbolFromStock, parseExportSymbols, parseKlineToRows } from '../export-data'

describe('export-data', () => {
  it('maps search hits to export symbols', () => {
    expect(exportSymbolFromStock({ symbol: '603296.SH', analysisCode: '603296' })).toBe('603296.SH')
    expect(exportSymbolFromStock({ analysisCode: '000001' })).toBe('000001.SZ')
    expect(exportSymbolFromStock({ symbol: 'AAPL.US', analysisCode: 'AAPL.US' })).toBe('AAPL.US')
    expect(exportSymbolFromStock(null)).toBe('')
  })

  it('normalizes mixed batch symbols', () => {
    expect(parseExportSymbols('601318; 510300 000001.SH AAPL.US 00700.HK 601318')).toEqual([
      '601318.SH',
      '510300.SH',
      '000001.SH',
      'AAPL.US',
      '00700.HK',
    ])
  })

  it('maps /api/kline rows into export rows', () => {
    const rows = parseKlineToRows({
      data: [
        { date: '2026-05-18', open: 10, high: 11, low: 9, close: 10.5, volume: 1000 },
      ],
    })

    expect(rows).toEqual([
      { date: '2026-05-18', open: 10, high: 11, low: 9, close: 10.5, volume: 1000 },
    ])
  })

  it('normalizes compact trade dates from /api/kline rows', () => {
    const rows = parseKlineToRows({
      data: [
        { date: '20240101', open: 10, high: 11, low: 9, close: 10.5, volume: 1000 },
        { date: '20240621', open: 11, high: 12, low: 10, close: 11.5, volume: 1200 },
      ],
    })

    expect(rows.map((row) => row.date)).toEqual(['2024-01-01', '2024-06-21'])
  })

  it('builds enhanced OHLCV rows and escaped CSV', () => {
    const enhanced = buildEnhancedRows([{ date: '2026-05-18', open: 10, high: 11, low: 9, close: 10.5, volume: 1000, amount: 10500, sector: '银行,金融' }])

    expect(enhanced[0]).toMatchObject({
      Date: '2026-05-18',
      Open: 10,
      AvgPrice: 10.5,
      Sector: '银行,金融',
    })
    expect(arrayToCSV(enhanced)).toContain('"银行,金融"')
  })
})
