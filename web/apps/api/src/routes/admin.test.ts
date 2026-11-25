import { describe, expect, it, vi, beforeEach } from 'vitest'
import { adminRoutes } from './admin'

const ENV = {
  SUPABASE_URL: 'https://example.supabase.co',
  SUPABASE_ANON_KEY: 'anon',
  SUPABASE_SERVICE_ROLE_KEY: 'service',
  ADMIN_EMAILS: 'admin@example.com, boss@example.com',
} as never

function req(path: string, token?: string) {
  return new Request(`http://localhost${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
}

describe('admin routes', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('requires auth (401 without token)', async () => {
    const res = await adminRoutes.fetch(req('/users'), ENV)
    expect(res.status).toBe(401)
  })

  it('rejects non-admin email (403)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ id: 'u1', email: 'normal@example.com' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    ))
    const res = await adminRoutes.fetch(req('/users', 'token'), ENV)
    expect(res.status).toBe(403)
  })

  it('validates membership payload', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ id: 'admin', email: 'admin@example.com' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    ))
    const res = await adminRoutes.fetch(new Request('http://localhost/membership', {
      method: 'POST',
      headers: { Authorization: 'Bearer token', 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: 'u1', expires_on: 'bad-date' }),
    }), ENV)
    expect(res.status).toBe(400)
  })
})
