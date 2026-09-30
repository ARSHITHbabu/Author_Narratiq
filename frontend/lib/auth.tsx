'use client'

import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { User } from './types'
import { authApi } from './api'
import { bindStudioStoreToUser } from './studioStore'

// Stage 10 (10.7): the session is an HttpOnly cookie set by the backend. This
// context never sees a token — it only knows who is signed in, which it learns
// by asking the server (/api/auth/me), not by trusting browser storage.
interface AuthCtx {
  user: User | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  /** After a password change or account deletion, replace/clear the signed-in user. */
  setSignedInUser: (u: User | null) => void
  loading: boolean
}

const AuthContext = createContext<AuthCtx>({} as AuthCtx)

// Keys written by the pre-Stage-10 client. Removed on load so a token that was
// once readable by script does not linger in this browser.
const LEGACY_KEYS = ['narratiq_token', 'narratiq_user']

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    try { LEGACY_KEYS.forEach((k) => localStorage.removeItem(k)) } catch {}
    let alive = true
    authApi.me()
      .then((res) => { if (alive) setUser(res.data) })
      .catch(() => { if (alive) setUser(null) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])

  const login = async (email: string, password: string) => {
    const res = await authApi.login(email, password)
    setUser(res.data.user)
  }

  const register = async (email: string, username: string, password: string) => {
    const res = await authApi.register(email, username, password)
    setUser(res.data.user)
  }

  const logout = async () => {
    try {
      await authApi.logout()        // ends THIS session server-side and clears the cookie
    } catch {
      // Signing out locally must still happen if the server is unreachable.
    }
    // Detach the studio layout from this account; the next sign-in loads its own.
    void bindStudioStoreToUser(null)
    setUser(null)
  }

  const setSignedInUser = (u: User | null) => {
    if (!u) void bindStudioStoreToUser(null)
    setUser(u)
  }

  return (
    <AuthContext.Provider value={{ user, login, register, logout, setSignedInUser, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
