import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { ArrowLeft, ShieldCheck, Users, RefreshCw, Check, Clock, Crown, UserCog } from 'lucide-react'
import { supabase } from '@/lib/supabase'
import { apiUrl } from '@/lib/api-url'
import { useAuthStore } from '@/stores/auth'
import { usePreferences } from '@/lib/preferences'

interface AdminUser {
  id: string
  email: string | null
  created_at: string
  confirmed: boolean
  last_sign_in: string | null
  membership: { expires_on: string | null; joined_at: string } | null
  settings: { chat_provider: string | null; has_tushare: boolean; has_tickflow: boolean } | null
}

async function getToken(): Promise<string> {
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token || ''
}

export function AdminPage() {
  const { t } = usePreferences()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const token = await getToken()
      const res = await fetch(apiUrl('/api/admin/users'), { headers: { Authorization: `Bearer ${token}` } })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`)
      setUsers(body.users || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : t('admin.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => { void load() }, [load])

  async function setMembership(userId: string, permanent: boolean) {
    setBusyId(userId)
    setError('')
    try {
      const token = await getToken()
      const res = await fetch(apiUrl('/api/admin/membership'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ user_id: userId, expires_on: permanent ? null : '1970-01-01' }),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('admin.updateFailed'))
    } finally {
      setBusyId('')
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-primary">
            <ShieldCheck size={14} /> {t('admin.badge')}
          </div>
          <h1 className="mt-1 flex items-center gap-2 text-2xl font-bold">
            <UserCog size={24} /> {t('admin.title')}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('admin.subtitle')}</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => navigate('/chat')} className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground transition hover:bg-muted">
            <ArrowLeft size={15} /> {t('admin.back')}
          </button>
          <button type="button" onClick={() => void load()} disabled={loading} className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground transition hover:bg-muted disabled:opacity-50">
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> {t('admin.refresh')}
          </button>
        </div>
      </div>

      {error && <p className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-200">{error}</p>}

      <div className="rounded-2xl border border-border bg-card">
        <div className="flex items-center gap-2 border-b border-border px-5 py-3 text-sm font-semibold">
          <Users size={16} /> {t('admin.users')} ({users.length})
        </div>
        {loading ? (
          <div className="flex justify-center py-12"><div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" /></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="px-5 py-3">{t('admin.email')}</th>
                  <th className="px-3 py-3">{t('admin.registered')}</th>
                  <th className="px-3 py-3">{t('admin.member')}</th>
                  <th className="px-3 py-3">{t('admin.config')}</th>
                  <th className="px-5 py-3 text-right">{t('admin.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const isPermanent = Boolean(u.membership && !u.membership.expires_on)
                  const isExpired = Boolean(u.membership?.expires_on && u.membership.expires_on < new Date().toISOString().slice(0, 10))
                  const isSelf = u.id === user?.id
                  return (
                    <tr key={u.id} className="border-b border-border/60 last:border-0">
                      <td className="px-5 py-3">
                        <div className="font-medium">{u.email || '—'}</div>
                        <div className="text-[11px] text-muted-foreground">{u.id.slice(0, 8)}…</div>
                      </td>
                      <td className="px-3 py-3 text-xs text-muted-foreground">
                        {u.created_at.slice(0, 10)}
                        <div className="mt-0.5 flex items-center gap-1">
                          {u.confirmed ? <><Check size={11} className="text-emerald-500" />{t('admin.confirmed')}</> : <><Clock size={11} className="text-warning" />{t('admin.unconfirmed')}</>}
                        </div>
                      </td>
                      <td className="px-3 py-3">
                        {isPermanent ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-1 text-xs font-medium text-primary"><Crown size={12} /> {t('admin.permanent')}</span>
                        ) : u.membership && !isExpired ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-1 text-xs text-emerald-600">{t('admin.until')} {u.membership.expires_on}</span>
                        ) : (
                          <span className="rounded-full bg-muted px-2 py-1 text-xs text-muted-foreground">{t('admin.regular')}</span>
                        )}
                      </td>
                      <td className="px-3 py-3 text-xs text-muted-foreground">
                        {u.settings ? (
                          <div className="flex flex-wrap gap-1">
                            {u.settings.chat_provider && <span className="rounded bg-muted px-1.5 py-0.5">{u.settings.chat_provider}</span>}
                            {u.settings.has_tushare && <span className="rounded bg-muted px-1.5 py-0.5">Tushare</span>}
                          </div>
                        ) : <span>—</span>}
                      </td>
                      <td className="px-5 py-3 text-right">
                        <button
                          type="button"
                          disabled={busyId === u.id || isSelf}
                          onClick={() => void setMembership(u.id, !isPermanent)}
                          className={`rounded-lg px-3 py-1.5 text-xs font-medium transition disabled:opacity-40 ${isPermanent ? 'border border-border text-muted-foreground hover:bg-muted' : 'bg-primary text-primary-foreground hover:opacity-90'}`}
                        >
                          {busyId === u.id ? '…' : isPermanent ? t('admin.revoke') : t('admin.grant')}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
