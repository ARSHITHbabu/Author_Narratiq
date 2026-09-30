'use client'

// Account settings (Stage 10): change password (10.7 / S10-F) and delete the
// account with all of its data (10.6 / S10-G). Every outcome is stated in plain
// language: what happened, what was kept, what the author can do next.

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Feather, KeyRound, Loader2, ShieldAlert, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { useAuth } from '@/lib/auth'
import { authApi } from '@/lib/api'

const MIN_PASSWORD = 8

function errorText(err: any, fallback: string): string {
  const d = err?.response?.data?.detail
  if (typeof d === 'string') return d
  if (!err?.response) return 'NarratIQ could not be reached. Check your connection and try again. Nothing was changed.'
  return fallback
}

const inputCls =
  'w-full bg-[#0d0f1a] border border-[#2e3454] rounded-xl px-4 py-3 text-sm text-[#e8eaf6] placeholder-[#3d4466] ' +
  'focus:outline-none focus:border-amber-500 focus-visible:ring-2 focus-visible:ring-amber-500/40 transition-colors'

function ChangePassword() {
  const { setSignedInUser } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const mismatch = repeat.length > 0 && next !== repeat
  const tooShort = next.length > 0 && next.length < MIN_PASSWORD
  const ready = current && next && repeat && !mismatch && !tooShort && !busy

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!ready) return
    setBusy(true)
    setError(null)
    try {
      const res = await authApi.changePassword(current, next)
      setSignedInUser(res.data.user)
      setCurrent(''); setNext(''); setRepeat('')
      toast.success('Password changed. You are still signed in here; every other device has been signed out.')
    } catch (err) {
      setError(errorText(err, 'Your password could not be changed. Nothing was changed.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby="pw-heading" className="bg-[#13162a] border border-[#1f2440] rounded-2xl p-6 sm:p-8">
      <div className="flex items-center gap-2 mb-1">
        <KeyRound className="w-4 h-4 text-amber-500" aria-hidden />
        <h2 id="pw-heading" className="text-lg font-semibold">Change password</h2>
      </div>
      <p className="text-sm text-[#9da3c8] mb-6">
        Changing your password signs you out on every other device. You stay signed in here.
      </p>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <div>
          <label htmlFor="pw-current" className="block text-sm text-[#9da3c8] mb-1.5">Current password</label>
          <input id="pw-current" type="password" autoComplete="current-password" value={current}
                 onChange={(e) => setCurrent(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label htmlFor="pw-new" className="block text-sm text-[#9da3c8] mb-1.5">New password</label>
          <input id="pw-new" type="password" autoComplete="new-password" value={next}
                 aria-describedby="pw-new-help" aria-invalid={tooShort}
                 onChange={(e) => setNext(e.target.value)} className={inputCls} />
          <p id="pw-new-help" className={`text-xs mt-1.5 ${tooShort ? 'text-amber-400' : 'text-[#8e94bd]'}`}>
            At least {MIN_PASSWORD} characters.
          </p>
        </div>
        <div>
          <label htmlFor="pw-repeat" className="block text-sm text-[#9da3c8] mb-1.5">Repeat new password</label>
          <input id="pw-repeat" type="password" autoComplete="new-password" value={repeat}
                 aria-invalid={mismatch} aria-describedby={mismatch ? 'pw-repeat-err' : undefined}
                 onChange={(e) => setRepeat(e.target.value)} className={inputCls} />
          {mismatch && <p id="pw-repeat-err" className="text-xs mt-1.5 text-amber-400">The two new passwords do not match.</p>}
        </div>
        {error && <p role="alert" className="text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>}
        <button type="submit" disabled={!ready}
                className="bg-amber-500 hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed text-black font-semibold px-5 py-2.5 rounded-xl text-sm transition-colors inline-flex items-center gap-2">
          {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden />}
          Change password
        </button>
      </form>
    </section>
  )
}

function DeleteAccount() {
  const { setSignedInUser } = useAuth()
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ready = password.length > 0 && confirm === 'DELETE' && !busy

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!ready) return
    setBusy(true)
    setError(null)
    try {
      await authApi.deleteAccount(password, confirm)
      setSignedInUser(null)
      router.replace('/account-deleted')
    } catch (err) {
      setError(errorText(err, 'Your account could not be deleted. Nothing was deleted.'))
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby="del-heading" className="bg-[#13162a] border border-red-500/20 rounded-2xl p-6 sm:p-8">
      <div className="flex items-center gap-2 mb-1">
        <ShieldAlert className="w-4 h-4 text-red-400" aria-hidden />
        <h2 id="del-heading" className="text-lg font-semibold">Delete account</h2>
      </div>
      <p className="text-sm text-[#9da3c8] mb-3">
        This permanently deletes your account and everything in it: every manuscript, chapter, character,
        note, Story Bible, saved AI version, voice recording and uploaded image. It cannot be undone.
      </p>
      <p className="text-sm text-[#9da3c8] mb-6">
        Export anything you want to keep first. Copies inside NarratIQ&apos;s encrypted backups are removed as those
        backups expire — see the <Link href="/data-policy" className="text-amber-400 underline underline-offset-2">data policy</Link>.
      </p>
      {!open ? (
        <button type="button" onClick={() => setOpen(true)}
                className="border border-red-500/40 text-red-300 hover:bg-red-500/10 px-5 py-2.5 rounded-xl text-sm transition-colors inline-flex items-center gap-2">
          <Trash2 className="w-4 h-4" aria-hidden /> Delete my account…
        </button>
      ) : (
        <form onSubmit={submit} className="space-y-4" noValidate>
          <div>
            <label htmlFor="del-password" className="block text-sm text-[#9da3c8] mb-1.5">Your password</label>
            <input id="del-password" type="password" autoComplete="current-password" value={password}
                   onChange={(e) => setPassword(e.target.value)} className={inputCls} autoFocus />
          </div>
          <div>
            <label htmlFor="del-confirm" className="block text-sm text-[#9da3c8] mb-1.5">
              Type <span className="font-mono text-red-300">DELETE</span> to confirm
            </label>
            <input id="del-confirm" value={confirm} autoComplete="off" spellCheck={false}
                   onChange={(e) => setConfirm(e.target.value)} className={inputCls} />
          </div>
          {error && <p role="alert" className="text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex flex-wrap gap-3">
            <button type="button" onClick={() => { setOpen(false); setPassword(''); setConfirm(''); setError(null) }}
                    className="border border-[#2e3454] text-[#9da3c8] px-5 py-2.5 rounded-xl text-sm hover:border-[#3d4466] transition-colors">
              Keep my account
            </button>
            <button type="submit" disabled={!ready}
                    className="bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold px-5 py-2.5 rounded-xl text-sm transition-colors inline-flex items-center gap-2">
              {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden />}
              Permanently delete everything
            </button>
          </div>
        </form>
      )}
    </section>
  )
}

export default function AccountPage() {
  const { user } = useAuth()
  return (
    <div className="min-h-screen bg-[#0d0f1a]">
      <nav className="border-b border-[#1f2440]">
        <div className="max-w-3xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/dashboard" className="inline-flex items-center gap-2 text-sm text-[#9da3c8] hover:text-[#e8eaf6] transition-colors">
            <ArrowLeft className="w-4 h-4" aria-hidden /> Back to manuscripts
          </Link>
          <span className="inline-flex items-center gap-2 text-sm">
            <Feather className="w-4 h-4 text-amber-500" aria-hidden /> NarratIQ AI
          </span>
        </div>
      </nav>
      <main className="max-w-3xl mx-auto px-6 py-10 space-y-8">
        <header>
          <h1 className="text-2xl font-bold">Account</h1>
          <p className="text-sm text-[#8e94bd] mt-1">Signed in as {user?.username} ({user?.email})</p>
        </header>
        <ChangePassword />
        <DeleteAccount />
      </main>
    </div>
  )
}
