import { createAnthropic } from '@ai-sdk/anthropic'
import { createOpenAI } from '@ai-sdk/openai'
import { generateText } from 'ai'
import { Hono } from 'hono'
import { z } from 'zod'
import {
  PROVIDER_BASE_URLS,
  PROVIDER_DEFAULT_MODELS,
  isAllowedModelBaseUrl,
  resolveOfficialDeepSeekModel,
  type Provider,
} from '@wyckoff/shared'
import { authMiddleware, type AuthContext } from '../middleware/auth'
import type { Env } from '../app'
import { patchDeepSeekApiBody } from '../services/chat-language-model'

type SettingsBindings = { Bindings: Env; Variables: { auth: AuthContext } }
type ModelTestConfig = z.infer<typeof MODEL_TEST_SCHEMA>

export const settingsRoutes = new Hono<SettingsBindings>()

settingsRoutes.use('*', authMiddleware)

settingsRoutes.get('/', async (c) => {
  return c.json({ message: 'Settings endpoint - Phase 2' })
})

settingsRoutes.put('/', async (c) => {
  return c.json({ message: 'Settings save endpoint - Phase 2' })
})

settingsRoutes.post('/test-model', async (c) => {
  const body = await c.req.json().catch(() => null)
  const parsed = MODEL_TEST_SCHEMA.safeParse(body)
  if (!parsed.success) return c.json({ ok: false, error: '模型配置不完整' }, 400)

  const config = normalizeModelConfig(parsed.data)
  const baseUrl = allowedProviderBaseUrl(config.provider, config.base_url)
  if (!baseUrl) return c.json({ ok: false, error: '模型 Base URL 不在允许列表内' }, 400)

  try {
    const result = await generateText({
      model: providerModel({ ...config, base_url: baseUrl }),
      prompt: '请仅回复 OK。这是一条 Wyckoff 设置页模型连通性测试请求。',
      temperature: 0,
      maxOutputTokens: 8,
      abortSignal: c.req.raw.signal,
    })
    return c.json({
      ok: true,
      provider: config.provider,
      model: config.model,
      message: '模型连通性正常',
      sample: result.text.slice(0, 40),
    })
  } catch (error) {
    return c.json({ ok: false, error: normalizeConnectivityError(error) }, 502)
  }
})

settingsRoutes.post('/test-data-source', async (c) => {
  const body = await c.req.json().catch(() => null)
  const parsed = DATA_SOURCE_TEST_SCHEMA.safeParse(body)
  if (!parsed.success) return c.json({ ok: false, error: 'Tushare Token 不能为空' }, 400)

  try {
    const response = await fetch('https://api.tushare.pro/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_name: 'stock_basic',
        token: parsed.data.tushare_token,
        params: { list_status: 'L' },
        fields: 'ts_code,name',
      }),
      signal: c.req.raw.signal,
    })
    const payload = await response.json().catch(() => null) as { code?: number; message?: string; data?: { items?: unknown[] } } | null
    if (!response.ok || payload?.code !== 0 || !Array.isArray(payload.data?.items) || payload.data.items.length === 0) {
      const detail = payload?.message || payload?.code != null ? String(payload?.message ?? payload?.code) : `HTTP ${response.status}`
      return c.json({ ok: false, error: `Tushare 连通性失败：${detail}` }, 502)
    }
    return c.json({ ok: true, source: 'tushare', rows: payload.data.items.length, message: 'Tushare 连通性正常' })
  } catch (error) {
    return c.json({ ok: false, error: normalizeConnectivityError(error) }, 502)
  }
})

const MODEL_TEST_SCHEMA = z.object({
  provider: z.enum(['1route', 'gemini', 'openai', 'deepseek', 'anthropic']),
  api_key: z.string().trim().min(1),
  model: z.string().trim().min(1),
  base_url: z.string().trim().optional().default(''),
})

const DATA_SOURCE_TEST_SCHEMA = z.object({
  tushare_token: z.string().trim().min(1),
})

function normalizeModelConfig(config: ModelTestConfig): Required<ModelTestConfig> {
  const provider = config.provider
  return {
    provider,
    api_key: config.api_key,
    model: config.model || PROVIDER_DEFAULT_MODELS[provider],
    base_url: config.base_url || providerDefaultBaseUrl(provider),
  }
}

function providerDefaultBaseUrl(provider: Provider): string {
  if (provider === 'gemini') return 'https://generativelanguage.googleapis.com/v1beta/openai'
  if (provider === 'anthropic') return 'https://api.anthropic.com'
  return PROVIDER_BASE_URLS[provider]
}

function allowedProviderBaseUrl(provider: Provider, raw: string): string {
  const baseUrl = raw || providerDefaultBaseUrl(provider)
  return isAllowedModelBaseUrl(baseUrl) ? baseUrl : ''
}

function providerModel(config: Required<ModelTestConfig>) {
  if (config.provider === 'anthropic') {
    return createAnthropic({ apiKey: config.api_key, baseURL: config.base_url }).chat(config.model)
  }
  const resolved = resolveOfficialDeepSeekModel(config.provider, config.model, config.base_url)
  const fetchImpl: typeof globalThis.fetch = async (input, init) => {
    const requestUrl = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const body = config.provider === 'deepseek' ? patchDeepSeekApiBody(requestUrl, init?.body, 'off') : init?.body
    return globalThis.fetch(input, { ...init, body })
  }
  return createOpenAI({ apiKey: config.api_key, baseURL: config.base_url, fetch: fetchImpl }).chat(resolved.model)
}

function normalizeConnectivityError(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  return String(error || '连通性测试失败')
}
