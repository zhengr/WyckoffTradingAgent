import { Hono } from 'hono'
import { createAdminSupabase, createUserSupabase } from '../middleware/auth'
import type { Env } from '../app'
import { authMiddleware } from '../middleware/auth'

/**
 * 管理员 API：用户列表 + 会员管理。
 * 鉴权：登录用户 + 邮箱在 ADMIN_EMAILS 白名单（逗号分隔，wrangler secret/vars）。
 * 所有管理操作用 service_role 服务端执行，普通用户无法访问。
 */
type AdminBindings = { Bindings: Env; Variables: { auth: { userId: string; accessToken: string } } }

export const adminRoutes = new Hono<AdminBindings>()

adminRoutes.use('*', authMiddleware)

function isAdminEmail(env: Env, email: string | undefined): boolean {
  if (!email) return false
  const raw = (env.ADMIN_EMAILS || '').trim()
  if (!raw) return false
  const allow = raw.split(',').map((s) => s.trim().toLowerCase()).filter(Boolean)
  return allow.includes(email.trim().toLowerCase())
}

async function requireAdmin(c: { env: Env; get: (k: 'auth') => { userId: string; accessToken: string }; json: (d: unknown, s?: number) => Response }) {
  const auth = c.get('auth')
  const userSupabase = createUserSupabase(c.env, auth.accessToken)
  const { data: { user } } = await userSupabase.auth.getUser(auth.accessToken)
  if (!user || !isAdminEmail(c.env, user.email)) return null
  return user
}

adminRoutes.get('/users', async (c) => {
  const admin = await requireAdmin(c)
  if (!admin) return c.json({ error: 'Admin only' }, 403)
  try {
    const supabase = createAdminSupabase(c.env)
    const [usersResult, membersResult, settingsResult] = await Promise.all([
      supabase.auth.admin.listUsers({ page: 1, perPage: 500 }),
      supabase.from('planet_members').select('user_id,expires_on,created_at'),
      supabase.from('user_settings').select('user_id,chat_provider,tushare_token,tickflow_api_key'),
    ])
    if (usersResult.error) throw usersResult.error
    if (membersResult.error) throw membersResult.error
    const memberMap = new Map((membersResult.data || []).map((m: { user_id: string; expires_on: string | null; created_at: string }) => [m.user_id, m]))
    const settingsMap = new Map((settingsResult.data || []).map((s: { user_id: string }) => [s.user_id, s]))
    const users = (usersResult.data?.users || []).map((u) => {
      const m = memberMap.get(u.id) as { expires_on: string | null; created_at: string } | undefined
      const s = settingsMap.get(u.id) as { chat_provider?: string; tushare_token?: string; tickflow_api_key?: string } | undefined
      return {
        id: u.id,
        email: u.email,
        created_at: u.created_at,
        confirmed: Boolean(u.email_confirmed_at),
        last_sign_in: u.last_sign_in_at || null,
        membership: m ? { expires_on: m.expires_on, joined_at: m.created_at } : null,
        settings: s ? {
          chat_provider: s.chat_provider || null,
          has_tushare: Boolean(s.tushare_token?.trim()),
          has_tickflow: Boolean(s.tickflow_api_key?.trim()),
        } : null,
      }
    })
    return c.json({ users, isAdminEmail: admin.email })
  } catch (err) {
    return c.json({ error: err instanceof Error ? err.message : 'list users failed' }, 500)
  }
})

adminRoutes.post('/membership', async (c) => {
  const admin = await requireAdmin(c)
  if (!admin) return c.json({ error: 'Admin only' }, 403)
  const body = await c.req.json<{ user_id?: string; expires_on?: string | null }>().catch(() => null)
  const userId = body?.user_id?.trim()
  const expiresOn = body?.expires_on === undefined ? null : (body.expires_on === null ? null : String(body.expires_on).trim())
  if (!userId) return c.json({ error: 'user_id required' }, 400)
  if (expiresOn && !/^\d{4}-\d{2}-\d{2}$/.test(expiresOn)) return c.json({ error: 'expires_on must be YYYY-MM-DD or null' }, 400)
  // 不能通过此接口移除自己的管理员资格（白名单在 env，非数据驱动，天然安全）
  try {
    const supabase = createAdminSupabase(c.env)
    const { error } = await supabase.from('planet_members').upsert(
      { user_id: userId, expires_on: expiresOn },
      { onConflict: 'user_id' },
    )
    if (error) throw error
    return c.json({ ok: true, user_id: userId, expires_on: expiresOn })
  } catch (err) {
    return c.json({ error: err instanceof Error ? err.message : 'update membership failed' }, 500)
  }
})
