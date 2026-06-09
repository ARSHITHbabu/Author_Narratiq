'use client'

import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { User } from './types'
import { authApi } from './api'

interface AuthCtx {
  user: User | null
  token: string | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, username: string, password: string) => Promise<void>
  logout: () => void
  loading: boolean
}

const AuthContext = createContext<AuthCtx>({} as AuthCtx)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    try {
      const t = localStorage.getItem('narratiq_token')
      const u = localStorage.getItem('narratiq_user')
      if (t && u) {
        setToken(t)
        setUser(JSON.parse(u))
      }
    } catch {
      localStorage.removeItem('narratiq_token')
      localStorage.removeItem('narratiq_user')
    } finally {
      setLoading(false)
    }
  }, [])

  const login = async (email: string, password: string) => {
    const res = await authApi.login(email, password)
    const { access_token, user: u } = res.data
    localStorage.setItem('narratiq_token', access_token)
    localStorage.setItem('narratiq_user', JSON.stringify(u))
    setToken(access_token)
    setUser(u)
  }

  const register = async (email: string, username: string, password: string) => {
    const res = await authApi.register(email, username, password)
    const { access_token, user: u } = res.data
    localStorage.setItem('narratiq_token', access_token)
    localStorage.setItem('narratiq_user', JSON.stringify(u))
    setToken(access_token)
    setUser(u)
  }

  const logout = () => {
    localStorage.removeItem('narratiq_token')
    localStorage.removeItem('narratiq_user')
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, token, login, register, logout, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
