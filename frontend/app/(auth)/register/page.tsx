'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Feather, Eye, EyeOff, Loader2, Check } from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { toast } from 'sonner'

export default function RegisterPage() {
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [loading, setLoading] = useState(false)
  const { register } = useAuth()
  const router = useRouter()

  const strength = password.length >= 8 && /[A-Z]/.test(password) && /[0-9]/.test(password)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email || !username || !password) return toast.error('Please fill in all fields')
    if (password.length < 6) return toast.error('Password must be at least 6 characters')
    setLoading(true)
    try {
      await register(email, username, password)
      toast.success('Welcome to NarratIQ AI!')
      router.push('/dashboard')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0d0f1a] flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <Link href="/" className="flex items-center justify-center gap-2 mb-10">
          <Feather className="w-6 h-6 text-amber-500" />
          <span className="text-lg font-semibold">NarratIQ AI</span>
        </Link>

        <div className="bg-[#13162a] border border-[#1f2440] rounded-2xl p-8">
          <h1 className="text-2xl font-bold mb-1">Start your manuscript</h1>
          <p className="text-[#9da3c8] text-sm mb-8">Create your free NarratIQ account</p>

          <form onSubmit={submit} className="space-y-5">
            <div>
              <label className="block text-sm text-[#9da3c8] mb-1.5">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-lg px-4 py-3 text-sm text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500 transition-colors"
              />
            </div>
            <div>
              <label className="block text-sm text-[#9da3c8] mb-1.5">Username</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value.replace(/\s/g, ''))}
                placeholder="your_pen_name"
                className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-lg px-4 py-3 text-sm text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500 transition-colors"
              />
            </div>
            <div>
              <label className="block text-sm text-[#9da3c8] mb-1.5">Password</label>
              <div className="relative">
                <input
                  type={show ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-lg px-4 py-3 pr-10 text-sm text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500 transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setShow(!show)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#5c6391] hover:text-[#9da3c8]"
                >
                  {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {password && (
                <div className="mt-2 flex items-center gap-2 text-xs">
                  <div className={`h-1 flex-1 rounded-full ${strength ? 'bg-green-500' : 'bg-amber-500'}`} />
                  <span className={strength ? 'text-green-400' : 'text-amber-400'}>
                    {strength ? 'Strong' : 'Moderate'}
                  </span>
                </div>
              )}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-black font-semibold py-3 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
              Create Account
            </button>
          </form>

          <ul className="mt-5 space-y-1">
            {['Free to start', 'No credit card required', 'Your data stays private'].map((b) => (
              <li key={b} className="flex items-center gap-2 text-xs text-[#5c6391]">
                <span className="text-amber-500">✓</span> {b}
              </li>
            ))}
          </ul>

          <p className="text-center text-sm text-[#5c6391] mt-6">
            Already have an account?{' '}
            <Link href="/login" className="text-amber-400 hover:text-amber-300">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
