import { AlertTriangle } from 'lucide-react'

export function UpgradeNotice({ message }: { message: string }) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100">
      <span className="inline-flex items-center gap-2"><AlertTriangle size={16} />{message}</span>
    </div>
  )
}
