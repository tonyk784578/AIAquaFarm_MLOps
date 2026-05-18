import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '@/context/AuthContext'
import LoginPage from '@/components/Auth/LoginPage'
import PrivateRoute from '@/components/Auth/PrivateRoute'
import ErrorBoundary from '@/components/ErrorBoundary'
import Header from '@/components/Layout/Header'
import Sidebar from '@/components/Layout/Sidebar'
import Dashboard from '@/components/Dashboard'
import ControlPanel from '@/components/Control/ControlPanel'
import GrowthPage from '@/components/Growth/GrowthPage'
import FeedingPage from '@/components/Feeding/FeedingPage'
import AlertsPage from '@/components/Alerts/AlertsPage'
import AgentsPage from '@/components/Agents/AgentsPage'
import MLOpsPage from '@/components/MLOps/MLOpsPage'
import SettingsPage from '@/components/Settings/SettingsPage'
import WaterQualityPage from '@/components/WaterQuality/WaterQualityPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 10_000, retry: 1 },
  },
})

function AppLayout() {
  return (
    <div className="flex h-screen overflow-hidden" style={{ backgroundColor: 'var(--bg-base)' }}>
      <Sidebar />
      <div className="flex flex-col flex-1 overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          {/* Per-route boundary — a crash in one page does NOT take down the shell. */}
          <ErrorBoundary>
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/water-quality" element={<WaterQualityPage />} />
              <Route path="/control" element={<ControlPanel />} />
              <Route path="/growth" element={<GrowthPage />} />
              <Route path="/feeding" element={<FeedingPage />} />
              <Route path="/alerts" element={<AlertsPage />} />
              <Route path="/agents" element={<AgentsPage />} />
              <Route path="/mlops" element={<MLOpsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route
                path="*"
                element={
                  <div className="flex items-center justify-center h-full">
                    <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                      페이지를 찾을 수 없습니다
                    </p>
                  </div>
                }
              />
            </Routes>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  )
}

export default function App() {
  return (
    // Outer boundary catches crashes anywhere — provider init, router setup,
    // login page — leaving the user with a usable fallback instead of a blank
    // screen. AppLayout has its own inner boundary so per-route crashes don't
    // unmount the shell.
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route
                path="/*"
                element={
                  <PrivateRoute>
                    <AppLayout />
                  </PrivateRoute>
                }
              />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
