import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Header from '@/components/Layout/Header'
import Sidebar from '@/components/Layout/Sidebar'
import Dashboard from '@/components/Dashboard'
import ControlPanel from '@/components/Control/ControlPanel'

// TODO (Phase 2): Add Settings page component.
// TODO (Phase 3): Add authentication guard (PrivateRoute).

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen bg-slate-900 text-slate-100 overflow-hidden">
        <Sidebar />
        <div className="flex flex-col flex-1 overflow-hidden">
          <Header />
          <main className="flex-1 overflow-y-auto p-6">
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/control" element={<ControlPanel />} />
              <Route
                path="*"
                element={
                  <div className="flex items-center justify-center h-full">
                    <p className="text-slate-400 text-lg">Page not found</p>
                  </div>
                }
              />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  )
}
