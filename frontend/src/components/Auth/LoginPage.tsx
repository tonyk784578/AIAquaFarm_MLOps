// Login page — full-screen centered form.

import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Fish } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(username, password)
      navigate('/dashboard', { replace: true })
    } catch {
      setError('아이디 또는 비밀번호가 올바르지 않습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8 gap-2">
          <div className="bg-sky-500/20 p-3 rounded-2xl ring-1 ring-sky-500/30">
            <Fish className="w-8 h-8 text-sky-400" />
          </div>
          <h1 className="text-2xl font-bold text-slate-100">AIAquafarm</h1>
          <p className="text-sm text-slate-400">스마트 RAS 양식장 관리 플랫폼</p>
        </div>

        {/* Form card */}
        <form
          onSubmit={handleSubmit}
          className="bg-slate-800 rounded-2xl p-6 space-y-5 ring-1 ring-slate-700"
        >
          <div className="space-y-1">
            <label className="text-xs text-slate-400 uppercase tracking-wider">사용자명</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              placeholder="admin"
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2
                         text-slate-100 text-sm placeholder-slate-600
                         focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500
                         transition-colors"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs text-slate-400 uppercase tracking-wider">비밀번호</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              placeholder="••••••••"
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2
                         text-slate-100 text-sm placeholder-slate-600
                         focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500
                         transition-colors"
            />
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-400/10 rounded-lg px-3 py-2">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700
                       text-white text-sm font-medium rounded-lg px-4 py-2.5
                       transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500"
          >
            {loading ? '로그인 중...' : '로그인'}
          </button>
        </form>

        <p className="mt-4 text-center text-xs text-slate-500">
          AIAquafarm v0.1.0 — Phase 6
        </p>
      </div>
    </div>
  )
}
