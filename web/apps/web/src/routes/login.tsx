import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { Languages, Moon, Sun, Mail, Lock, Eye, EyeOff, Check, ArrowRight, BarChart3, Sparkles, ShieldCheck } from 'lucide-react'
import { supabase } from '@/lib/supabase'
import { useAuthStore } from '@/stores/auth'
import { usePreferences } from '@/lib/preferences'

const REMEMBERED_EMAIL_KEY = 'wyckoff.login.email'

function readRememberedEmail() {
  try {
    return window.localStorage.getItem(REMEMBERED_EMAIL_KEY) ?? ''
  } catch {
    return ''
  }
}

function saveRememberedEmail(remember: boolean, email: string) {
  try {
    if (remember) {
      window.localStorage.setItem(REMEMBERED_EMAIL_KEY, email.trim())
      return
    }
    window.localStorage.removeItem(REMEMBERED_EMAIL_KEY)
  } catch {
    // localStorage can be disabled by privacy settings; login should still work.
  }
}

function useSessionRedirect() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [checkingSession, setCheckingSession] = useState(true)

  useEffect(() => {
    let active = true
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!active) return
      if (session) {
        setAuth(session.user, session)
        navigate('/', { replace: true })
        return
      }
      setCheckingSession(false)
    }).catch(() => active && setCheckingSession(false))

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!active || !session) return
      setAuth(session.user, session)
      navigate('/', { replace: true })
    })
    return () => {
      active = false
      subscription.unsubscribe()
    }
  }, [navigate, setAuth])

  return { checkingSession, navigate, setAuth }
}

function LoginToolbar() {
  const { locale, setLocale, theme, toggleTheme, t } = usePreferences()
  const ThemeIcon = theme === 'dark' ? Sun : Moon

  return (
    <div className="absolute right-4 top-4 z-30 flex gap-2">
      <button type="button" onClick={toggleTheme} className="flex h-9 w-9 items-center justify-center rounded-full border border-border/70 bg-card/60 backdrop-blur text-muted-foreground transition hover:bg-muted hover:text-foreground" aria-label={t('prefs.theme')}>
        <ThemeIcon size={16} />
      </button>
      <button type="button" onClick={() => setLocale(locale === 'zh-CN' ? 'en-US' : 'zh-CN')} className="flex h-9 items-center gap-1.5 rounded-full border border-border/70 bg-card/60 backdrop-blur px-3 text-xs text-muted-foreground transition hover:bg-muted hover:text-foreground" aria-label={t('prefs.language')}>
        <Languages size={15} />
        {locale === 'zh-CN' ? 'EN' : '中文'}
      </button>
    </div>
  )
}

/** 装饰性 K 线图：纯 SVG，营造投研氛围，不依赖外部素材。 */
function BrandChart() {
  return (
    <svg viewBox="0 0 520 220" className="w-full max-w-lg opacity-90" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="brandArea" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.28" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d="M0 190 L60 172 L120 180 L180 140 L240 152 L300 96 L360 118 L420 62 L480 78 L520 30 L520 220 L0 220 Z" fill="url(#brandArea)" />
      <path d="M0 190 L60 172 L120 180 L180 140 L240 152 L300 96 L360 118 L420 62 L480 78 L520 30" stroke="currentColor" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
      {[[60,172],[120,180],[180,140],[240,152],[300,96],[360,118],[420,62],[480,78]].map((point, i) => {
        const x = point[0] ?? 0
        const y = point[1] ?? 0
        return (
          <g key={i}>
            <line x1={x} y1={y - 12} x2={x} y2={y + 12} stroke="currentColor" strokeWidth="1.5" opacity="0.6" />
            <rect x={x - 5} y={y - 6} width="10" height="12" rx="2" fill="currentColor" opacity="0.5" />
          </g>
        )
      })}
      <line x1="0" y1="210" x2="520" y2="210" stroke="currentColor" strokeWidth="1" opacity="0.15" />
      <line x1="0" y1="160" x2="520" y2="160" stroke="currentColor" strokeWidth="1" strokeDasharray="4 6" opacity="0.12" />
      <line x1="0" y1="110" x2="520" y2="110" stroke="currentColor" strokeWidth="1" strokeDasharray="4 6" opacity="0.12" />
    </svg>
  )
}

function BrandPanel() {
  const { t } = usePreferences()
  return (
    <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-gradient-to-br from-indigo-600 via-violet-600 to-cyan-600 p-12 text-white lg:flex">
      <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-white/10 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-32 -left-20 h-96 w-96 rounded-full bg-cyan-300/20 blur-3xl" />
      <div className="relative z-10 flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/15 text-xl font-bold backdrop-blur ring-1 ring-white/30">W</div>
        <div>
          <div className="text-xl font-bold tracking-tight">Wyckoff</div>
          <div className="text-xs text-white/70">Intelligent Research Terminal</div>
        </div>
      </div>

      <div className="relative z-10 my-auto py-10">
        <h2 className="max-w-md text-4xl font-bold leading-tight tracking-tight">{t('login.brandTagline')}</h2>
        <p className="mt-5 max-w-md text-sm leading-relaxed text-white/80">{t('login.brandDesc')}</p>
        <div className="mt-8 space-y-3">
          {[
            { icon: BarChart3, text: t('login.feature1') },
            { icon: Sparkles, text: t('login.feature2') },
            { icon: ShieldCheck, text: t('login.feature3') },
          ].map(({ icon: Icon, text }) => (
            <div key={text} className="flex items-center gap-3 text-sm text-white/90">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/15 backdrop-blur ring-1 ring-white/20">
                <Icon size={16} />
              </span>
              <span>{text}</span>
            </div>
          ))}
        </div>
        <div className="mt-10 text-cyan-100">
          <BrandChart />
        </div>
      </div>

      <div className="relative z-10 flex items-center gap-2 text-xs text-white/60">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-300" />
        <span>© {new Date().getFullYear()} WyckoffAgent · Open Source</span>
      </div>
    </div>
  )
}

function LoginPageHeader() {
  const { t } = usePreferences()
  return (
    <div className="mb-7 text-center lg:hidden">
      <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-cyan-500 text-2xl font-bold text-white shadow-lg shadow-primary/30">W</div>
      <h1 className="bg-gradient-to-r from-primary to-cyan-500 bg-clip-text text-3xl font-bold text-transparent">Wyckoff</h1>
      <p className="mt-1 text-sm text-muted-foreground">{t('app.subtitle')}</p>
    </div>
  )
}

interface LoginFieldsProps {
  email: string
  password: string
  rememberEmail: boolean
  onEmail: (value: string) => void
  onPassword: (value: string) => void
  onRememberEmail: (value: boolean) => void
}

function LoginFields(props: LoginFieldsProps) {
  return (
    <>
      <LoginEmailField value={props.email} onInput={props.onEmail} />
      <LoginPasswordField value={props.password} onInput={props.onPassword} />
      <RememberEmailCheckbox checked={props.rememberEmail} onChange={props.onRememberEmail} />
    </>
  )
}

function LoginEmailField({ value, onInput }: { value: string; onInput: (value: string) => void }) {
  const { t } = usePreferences()
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold text-muted-foreground">{t('login.email')}</span>
      <span className="relative block">
        <Mail size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground/70" />
        <input
          type="email"
          value={value}
          onChange={(e) => onInput(e.target.value)}
          className="w-full rounded-xl border border-border bg-background/60 py-2.5 pl-10 pr-4 text-sm outline-none transition-all duration-200 focus:border-primary focus:bg-background focus:ring-4 focus:ring-primary/10 placeholder:text-muted-foreground/50"
          placeholder={t('login.emailPlaceholder')}
          autoComplete="email"
          required
        />
      </span>
    </label>
  )
}

function LoginPasswordField({ value, onInput }: { value: string; onInput: (value: string) => void }) {
  const { t } = usePreferences()
  const [show, setShow] = useState(false)
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold text-muted-foreground">{t('login.password')}</span>
      <span className="relative block">
        <Lock size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground/70" />
        <input
          type={show ? 'text' : 'password'}
          value={value}
          onChange={(e) => onInput(e.target.value)}
          className="w-full rounded-xl border border-border bg-background/60 py-2.5 pl-10 pr-11 text-sm outline-none transition-all duration-200 focus:border-primary focus:bg-background focus:ring-4 focus:ring-primary/10 placeholder:text-muted-foreground/50"
          placeholder="••••••••"
          autoComplete="current-password"
          required
          minLength={6}
        />
        <button type="button" onClick={() => setShow((v) => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground/70 transition hover:text-foreground" aria-label={show ? t('login.hidePassword') : t('login.showPassword')}>
          {show ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </span>
    </label>
  )
}

function RememberEmailCheckbox({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  const { t } = usePreferences()
  return (
    <button type="button" onClick={() => onChange(!checked)} className="flex w-full items-start gap-3 rounded-xl border border-border bg-muted/20 px-3.5 py-3 text-left text-xs text-muted-foreground transition hover:bg-muted/40">
      <span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border transition ${checked ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-background'}`}>
        {checked && <Check size={11} strokeWidth={3} />}
      </span>
      <span>
        <span className="block font-semibold text-foreground">{t('login.rememberAccount')}</span>
        <span className="mt-0.5 block text-[11px] text-muted-foreground/80">{t('login.passwordManagerHint')}</span>
      </span>
    </button>
  )
}

function LoginSubmit(props: { loading: boolean; error: string }) {
  const { t } = usePreferences()
  return (
    <>
      {props.error && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-200">{props.error}</p>}
      <button type="submit" disabled={props.loading} className="group flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-primary to-cyan-500 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-primary/25 transition-all hover:shadow-xl hover:shadow-primary/30 disabled:cursor-not-allowed disabled:opacity-60">
        {props.loading ? t('login.processing') : t('login.submit')}
        {!props.loading && <ArrowRight size={16} className="transition-transform group-hover:translate-x-0.5" />}
      </button>
    </>
  )
}

export function LoginPage() {
  const { checkingSession, navigate, setAuth } = useSessionRedirect()
  const { t } = usePreferences()
  const [email, setEmail] = useState(readRememberedEmail)
  const [password, setPassword] = useState('')
  const [rememberEmail, setRememberEmail] = useState(() => Boolean(readRememberedEmail()))
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) throw error
      if (data.session) setAuth(data.user, data.session)
      saveRememberedEmail(rememberEmail, email)
      navigate('/', { replace: true })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('login.operationFailed'))
    } finally {
      setLoading(false)
    }
  }

  if (checkingSession) return <LoadingSession />
  return (
    <div className="relative flex min-h-screen bg-background">
      <LoginToolbar />
      <BrandPanel />
      <div className="relative flex flex-1 items-center justify-center px-4 py-12 overflow-hidden">
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,#80808008_1px,transparent_1px),linear-gradient(to_bottom,#80808008_1px,transparent_1px)] bg-[size:24px_24px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_50%,#000_70%,transparent_100%)]" />
        <div className="relative z-10 w-full max-w-sm rounded-3xl border border-border/70 bg-card/80 p-8 shadow-2xl shadow-primary/5 backdrop-blur-xl transition-all duration-300 animate-fade-in-up">
          <LoginPageHeader />
          <form onSubmit={handleSubmit} className="space-y-4">
            <LoginFields email={email} password={password} rememberEmail={rememberEmail} onEmail={setEmail} onPassword={setPassword} onRememberEmail={setRememberEmail} />
            <LoginSubmit loading={loading} error={error} />
          </form>
        </div>
      </div>
    </div>
  )
}

function LoadingSession() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
    </div>
  )
}
