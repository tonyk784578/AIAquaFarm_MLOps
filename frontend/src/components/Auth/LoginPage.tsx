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
    <div
      className="min-h-screen flex items-center justify-center p-4"
      style={{ backgroundColor: 'var(--bg-base)' }}
    >
      <div className="w-full max-w-sm animate-fade-in">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8 gap-3">
          <div
            className="p-4 rounded-2xl"
            style={{
              background: 'linear-gradient(135deg, var(--teal-500), var(--blue-500))',
              boxShadow: 'var(--shadow-lg)',
            }}
          >
            <Fish className="w-8 h-8 text-white" />
          </div>
          <div className="text-center">
            <h1 className="text-2xl font-extrabold tracking-tight" style={{ color: 'var(--text-primary)' }}>
              AIAquafarm
            </h1>
            <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
              스마트 RAS 양식장 관리 플랫폼
            </p>
          </div>
        </div>

        {/* Form card */}
        <form onSubmit={handleSubmit} className="card space-y-5">
          <div className="space-y-1.5">
            <label
              className="text-xs font-semibold uppercase tracking-wider"
              style={{ color: 'var(--text-muted)' }}
            >
              사용자명
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              placeholder="admin"
              className="input-base"
            />
          </div>

          <div className="space-y-1.5">
            <label
              className="text-xs font-semibold uppercase tracking-wider"
              style={{ color: 'var(--text-muted)' }}
            >
              비밀번호
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              placeholder="••••••••"
              className="input-base"
            />
          </div>

          {error && (
            <p
              className="text-xs rounded-lg px-3 py-2"
              style={{ color: 'var(--danger)', backgroundColor: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.15)' }}
            >
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="btn-primary w-full py-2.5"
          >
            {loading ? '로그인 중...' : '로그인'}
          </button>
        </form>

        <p className="mt-4 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
          AIAquafarm v0.1.0
        </p>
      </div>
    </div>
  )
}
