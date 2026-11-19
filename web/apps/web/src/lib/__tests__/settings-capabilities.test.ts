import { describe, expect, it } from 'vitest'
import {
  buildSettingsCapabilityRows,
  summarizeSettingsCapabilities,
  type SettingsCapabilityId,
  type SettingsCapabilityRow,
} from '../settings-capabilities'

function findRow(rows: SettingsCapabilityRow[], id: SettingsCapabilityId): SettingsCapabilityRow {
  const row = rows.find((item) => item.id === id)
  expect(row).toBeDefined()
  return row!
}

describe('settings capabilities', () => {
  it('marks key settings missing when credentials are empty', () => {
    const rows = buildSettingsCapabilityRows({
      tushare: '',
      savedTushare: '',
      modelProviderLabel: 'DeepSeek',
      modelConfig: { api_key: '', model: '' },
      savedModelConfig: { api_key: '', model: '' },
    })
    const summary = summarizeSettingsCapabilities(rows)

    expect(findRow(rows, 'market-data').status).toBe('missing_config')
    expect(findRow(rows, 'reading-model').status).toBe('missing_config')
    expect(summary).toMatchObject({
      readyCount: 0,
      unsavedCount: 0,
      missingCount: 2,
      totalCount: 2,
      hasMarketData: false,
      hasReadingModel: false,
      isFullyConfigured: false,
      hasUnsavedChanges: false,
    })
  })

  it('marks filled-but-unsaved credentials as amber unsaved, not ready', () => {
    const rows = buildSettingsCapabilityRows({
      tushare: ' tu-key ',
      savedTushare: '',
      modelProviderLabel: 'DeepSeek',
      modelConfig: { api_key: 'deepseek-key', model: 'deepseek-v4-flash' },
      savedModelConfig: { api_key: '', model: '' },
    })
    const marketData = findRow(rows, 'market-data')
    const model = findRow(rows, 'reading-model')
    const summary = summarizeSettingsCapabilities(rows)

    expect(marketData.status).toBe('unsaved')
    expect(marketData.isReady).toBe(false)
    expect(marketData.isUnsaved).toBe(true)
    expect(model.status).toBe('unsaved')
    expect(summary).toMatchObject({
      readyCount: 0,
      unsavedCount: 2,
      missingCount: 0,
      hasMarketData: false,
      hasReadingModel: false,
      isFullyConfigured: false,
      hasUnsavedChanges: true,
    })
  })

  it('treats Tushare as ready only after saved credentials match the draft', () => {
    const rows = buildSettingsCapabilityRows({
      tushare: ' tu-key ',
      savedTushare: 'tu-key',
      modelProviderLabel: 'DeepSeek',
      modelConfig: { api_key: '', model: '' },
      savedModelConfig: { api_key: '', model: '' },
    })
    const marketData = findRow(rows, 'market-data')
    const summary = summarizeSettingsCapabilities(rows)

    expect(marketData.status).toBe('ready')
    expect(marketData.isReady).toBe(true)
    expect(marketData.priority).toBe('primary')
    expect(summary.hasMarketData).toBe(true)
    expect(summary.readyCount).toBe(1)
  })

  it('requires both an API key and model name for the reading model', () => {
    const missingModelRows = buildSettingsCapabilityRows({
      tushare: '',
      savedTushare: '',
      modelProviderLabel: 'DeepSeek',
      modelConfig: { api_key: 'deepseek-key', model: '' },
      savedModelConfig: { api_key: '', model: '' },
    })
    const readyRows = buildSettingsCapabilityRows({
      tushare: '',
      savedTushare: '',
      modelProviderLabel: 'DeepSeek',
      modelConfig: { api_key: 'deepseek-key', model: 'deepseek-v4-flash' },
      savedModelConfig: { api_key: 'deepseek-key', model: 'deepseek-v4-flash' },
    })

    expect(findRow(missingModelRows, 'reading-model').status).toBe('missing_config')
    expect(findRow(readyRows, 'reading-model').status).toBe('ready')
    expect(findRow(readyRows, 'reading-model').badgeLabels).toEqual(['deepseek-v4-flash'])
  })

  it('marks model unsaved when provider switched before save', () => {
    const rows = buildSettingsCapabilityRows({
      tushare: 'tu-key',
      savedTushare: 'tu-key',
      modelProviderLabel: 'DeepSeek',
      modelConfig: { api_key: 'deepseek-key', model: 'deepseek-v4-flash' },
      savedModelConfig: { api_key: 'old-key', model: 'old-model' },
      providerMatchesSaved: false,
    })

    expect(findRow(rows, 'reading-model').status).toBe('unsaved')
    expect(summarizeSettingsCapabilities(rows).hasUnsavedChanges).toBe(true)
  })

  it('summarizes fully configured key settings', () => {
    const rows = buildSettingsCapabilityRows({
      tushare: 'tu-key',
      savedTushare: 'tu-key',
      modelProviderLabel: 'DeepSeek',
      modelConfig: { api_key: 'deepseek-key', model: 'deepseek-v4-flash' },
      savedModelConfig: { api_key: 'deepseek-key', model: 'deepseek-v4-flash' },
    })

    expect(summarizeSettingsCapabilities(rows)).toMatchObject({
      readyCount: 2,
      unsavedCount: 0,
      missingCount: 0,
      totalCount: 2,
      hasMarketData: true,
      hasReadingModel: true,
      isFullyConfigured: true,
      hasUnsavedChanges: false,
    })
  })
})
