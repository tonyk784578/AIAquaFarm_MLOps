// Top navigation bar — shows service status and global actions.
// TODO (Phase 2): Add notification bell with active alert count badge.
// TODO (Phase 3): Add user avatar and logout button.

import { Activity } from 'lucide-react'

export default function Header() {
  return (
    <header className="h-14 bg-slate-800 border-b border-slate-700 flex items-center justify-between px-6 shrink-0">
      <div className="flex items-center gap-2">
        <Activity className="w-5 h-5 text-sky-400" />
        <span className="text-sm font-medium text-slate-300">AIAquafarm</span>
        <span className="text-slate-600">|</span>
        <span className="text-xs text-slate-400">스마트 RAS 양식장 AI 플랫폼</span>
      </div>

      <div className="flex items-center gap-3">
        {/* TODO (Phase 2): Real-time connection status from useWebSocket */}
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <span className="text-xs text-slate-400">연결됨</span>
        </div>
      </div>
    </header>
  )
}
