import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Check, Crown, Clock } from 'lucide-react'
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

export function AdminPanel() {
  const { t } = usePreferences()
  const currentUser = useAuthStore((s) => s.user)
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
      setError(err instanceof Error ? err.message : 'Load failed')
    } finally {
      setLoading(false)
    }
  }, [])

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
      setError(err instanceof Error ? err.message : 'Update failed')
    } finally {
      setBusyId('')
    }
  }

  return (
    <section className="glass-panel rounded-2xl p-5">
      <div className="mb-4 flex items-center justify-between border-b border-border/60 pb-2">
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <Crown size={16} className="text-primary" />
          {t('settings.adminUsers')} ({users.length})
        </h2>
        <button type="button" onClick={() => void load()} disabled={loading} className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted-foreground transition hover:bg-muted disabled:opacity-50">
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> {t('settings.adminRefresh')}
        </button>
      </div>
      {error && <p className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-200">{error}</p>}
      {loading ? (
        <div className="flex justify-center py-10"><div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" /></div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="py-2.5 pr-3">{t('settings.adminEmail')}</th>
                <th className="px-3 py-2.5">{t('settings.adminRegistered')}</th>
                <th className="px-3 py-2.5">{t('settings.adminMember')}</th>
                <th className="px-3 py-2.5">{t('settings.adminConfig')}</th>
                <th className="py-2.5 pl-3 text-right">{t('settings.adminActions')}</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const isPermanent = Boolean(u.membership && !u.membership.expires_on)
                const isExpired = Boolean(u.membership?.expires_on && u.membership.expires_on < new Date().toISOString().slice(0, 10))
                const isSelf = u.id === currentUser?.id
                return (
                  <tr key={u.id} className="border-b border-border/60 last:border-0">
                    <td className="py-3 pr-3">
                      <div className="font-medium">{u.email || '—'}</div>
                      <div className="text-[11px] text-muted-foreground">{u.id.slice(0, 8)}…</div>
                    </td>
                    <td className="px-3 py-3 text-xs text-muted-foreground">
                      {u.created_at.slice(0, 10)}
                      <div className="mt-0.5 flex items-center gap-1">
                        {u.confirmed ? <><Check size={11} className="text-emerald-500" />{t('settings.adminConfirmed')}</> : <><Clock size={11} className="text-warning" />{t('settings.adminUnconfirmed')}</>}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      {isPermanent ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-1 text-xs font-medium text-primary"><Crown size={12} /> {t('settings.adminPermanent')}</span>
                      ) : u.membership && !isExpired ? (
                        <span className="rounded-full bg-emerald-500/10 px-2 py-1 text-xs text-emerald-600">{t('settings.adminUntil')} {u.membership.expires_on}</span>
                      ) : (
                        <span className="rounded-full bg-muted px-2 py-1 text-xs text-muted-foreground">{t('settings.adminRegular')}</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-xs text-muted-foreground">
                      {u.settings ? (
                        <div className="flex flex-wrap gap-1">
                          {u.settings.chat_provider && <span className="rounded bg-muted px-1.5 py-0.5">{u.settings.chat_provider}</span>}
                          {u.settings.has_tushare && <span className="rounded bg-muted px-1.5 py-0.5">Tushare</span>}
                        </div>
                      ) : '—'}
                    </td>
                    <td className="py-3 pl-3 text-right">
                      <button
                        type="button"
                        disabled={busyId === u.id || isSelf}
                        onClick={() => void setMembership(u.id, !isPermanent)}
                        className={`rounded-lg px-3 py-1.5 text-xs font-medium transition disabled:opacity-40 ${isPermanent ? 'border border-border text-muted-foreground hover:bg-muted' : 'bg-primary text-primary-foreground hover:opacity-90'}`}
                      >
                        {busyId === u.id ? '…' : isPermanent ? t('settings.adminRevoke') : t('settings.adminGrant')}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
