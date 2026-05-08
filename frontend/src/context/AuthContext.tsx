// Auth context — tokens are stored in httpOnly cookies managed by the server.
// This context tracks the authenticated user profile only (no token state in JS).

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { apiClient, loginUser, refreshSession } from '@/services/api'
import type { UserProfile } from '@/types'

interface AuthState {
  user: UserProfile | null
  isAuthenticated: boolean
  isLoading: boolean
}

interface AuthContextValue extends AuthState {
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    isAuthenticated: false,
    isLoading: true,
  })

  // Auto-refresh on 401: the aq_refresh httpOnly cookie is sent automatically.
  useEffect(() => {
    const id = apiClient.interceptors.response.use(
      (r) => r,
      async (error) => {
        const original = error.config
        if (error.response?.status === 401 && !original._retry) {
          original._retry = true
          try {
            await refreshSession()
            // Cookies are updated by the server; retry the original request.
            return apiClient(original)
          } catch {
            logout()
          }
        }
        return Promise.reject(error)
      }
    )
    return () => apiClient.interceptors.response.eject(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Restore session on mount: if the aq_access cookie is still valid the server
  // returns the user profile; if it's expired the 401 interceptor triggers a refresh.
  useEffect(() => {
    apiClient
      .get<UserProfile>('/v1/auth/me')
      .then((r) => {
        setState({ user: r.data, isAuthenticated: true, isLoading: false })
      })
      .catch(() => {
        setState({ user: null, isAuthenticated: false, isLoading: false })
      })
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    await loginUser(username, password)
    // Cookies are set by the server response; fetch the profile to populate state.
    const profile = await apiClient.get<UserProfile>('/v1/auth/me')
    setState({ user: profile.data, isAuthenticated: true, isLoading: false })
  }, [])

  const logout = useCallback(() => {
    // Ask the server to clear the httpOnly cookies.
    apiClient.post('/v1/auth/logout').catch(() => undefined)
    setState({ user: null, isAuthenticated: false, isLoading: false })
  }, [])

  const value = useMemo(
    () => ({ ...state, login, logout }),
    [state, login, logout]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
