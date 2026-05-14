import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles/global.css'

// Apply saved dark mode before first render to prevent flash
try {
  const saved = localStorage.getItem('aq-theme')
  if (saved && JSON.parse(saved)?.state?.isDark) {
    document.documentElement.classList.add('dark')
  }
} catch {
  // ignore
}

// Enable mock data when VITE_USE_MOCK=true (set in .env.local for dev demos)
if (import.meta.env.VITE_USE_MOCK === 'true') {
  const { setupMocks } = await import('./mocks/setup')
  setupMocks()
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
