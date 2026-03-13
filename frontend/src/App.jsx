import { BrowserRouter as Router, Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ChartBarIcon,
  MagnifyingGlassIcon,
  MegaphoneIcon,
  InboxStackIcon,
  ChatBubbleLeftRightIcon,
  ChartPieIcon,
  Cog6ToothIcon,
  ArrowRightOnRectangleIcon,
} from '@heroicons/react/24/outline'
import { getUnreadCount, getQueue } from './api/client'
import { AuthProvider, useAuth } from './context/AuthContext'

import Login from './pages/Login'
import Overview from './pages/Overview'
import LeadDiscovery from './pages/LeadDiscovery'
import LeadProfile from './pages/LeadProfile'
import Campaigns from './pages/Campaigns'
import CampaignForm from './pages/CampaignForm'
import EmailQueue from './pages/EmailQueue'
import Replies from './pages/Replies'
import Analytics from './pages/Analytics'
import Settings from './pages/Settings'

const navItems = [
  { path: '/', label: 'Overview', icon: ChartBarIcon },
  { path: '/leads', label: 'Lead Discovery', icon: MagnifyingGlassIcon },
  { path: '/campaigns', label: 'Campaigns', icon: MegaphoneIcon },
  { path: '/queue', label: 'Email Queue', icon: InboxStackIcon, badgeKey: 'queue' },
  { path: '/replies', label: 'Replies', icon: ChatBubbleLeftRightIcon, badgeKey: 'replies' },
  { path: '/analytics', label: 'Analytics', icon: ChartPieIcon },
  { path: '/settings', label: 'Settings', icon: Cog6ToothIcon },
]

function AppShell() {
  const { user, loading, signOut } = useAuth()

  const { data: unread } = useQuery({
    queryKey: ['unread-count'],
    queryFn: () => getUnreadCount().then((r) => r.data.count),
    refetchInterval: 30_000,
    enabled: !!user,
  })

  const { data: queueCount } = useQuery({
    queryKey: ['queue-count'],
    queryFn: () => getQueue({ per_page: 1 }).then((r) => r.data.data?.length || 0),
    refetchInterval: 30_000,
    enabled: !!user,
  })

  const badges = { replies: unread || 0, queue: queueCount || 0 }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-950">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500" />
      </div>
    )
  }

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" /> : <Login />} />
      <Route path="*" element={user ? (
        <div className="flex min-h-screen bg-gray-950">
          {/* Sidebar */}
          <aside className="fixed inset-y-0 left-0 z-30 w-64 border-r border-gray-800 bg-gray-900 flex flex-col">
            <div className="px-6 py-5 border-b border-gray-800">
              <h1 className="text-xl font-bold text-white tracking-tight">⚡ 505 Leads</h1>
              <p className="text-xs text-gray-500 mt-0.5">AI-Powered Lead Engine</p>
            </div>

            <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
              {navItems.map(({ path, label, icon: Icon, badgeKey }) => (
                <NavLink
                  key={path}
                  to={path}
                  end={path === '/'}
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-600/30'
                        : 'text-gray-400 hover:bg-gray-800 hover:text-white border border-transparent'
                    }`
                  }
                >
                  <Icon className="h-5 w-5 shrink-0" />
                  <span className="flex-1">{label}</span>
                  {badgeKey && badges[badgeKey] > 0 && (
                    <span className="flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-indigo-600 px-1.5 text-xs font-bold text-white">
                      {badges[badgeKey]}
                    </span>
                  )}
                </NavLink>
              ))}
            </nav>

            <div className="border-t border-gray-800 px-4 py-3 space-y-2">
              <div className="flex items-center gap-2 px-2">
                <div className="h-6 w-6 rounded-full bg-indigo-600 flex items-center justify-center text-xs font-bold text-white">
                  {(user.user_metadata?.full_name || user.email || '?')[0].toUpperCase()}
                </div>
                <span className="text-xs text-gray-400 truncate flex-1">{user.email}</span>
              </div>
              <button
                onClick={signOut}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-gray-500 hover:text-red-400 hover:bg-gray-800 transition-colors"
              >
                <ArrowRightOnRectangleIcon className="h-4 w-4" />
                Sign out
              </button>
            </div>
          </aside>

          {/* Main Content */}
          <main className="ml-64 flex-1 p-8">
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/leads" element={<LeadDiscovery />} />
              <Route path="/leads/:id" element={<LeadProfile />} />
              <Route path="/campaigns" element={<Campaigns />} />
              <Route path="/campaigns/new" element={<CampaignForm />} />
              <Route path="/campaigns/:id/edit" element={<CampaignForm />} />
              <Route path="/queue" element={<EmailQueue />} />
              <Route path="/replies" element={<Replies />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </main>
        </div>
      ) : <Navigate to="/login" />} />
    </Routes>
  )
}

function App() {
  return (
    <Router>
      <AuthProvider>
        <AppShell />
      </AuthProvider>
    </Router>
  )
}

export default App
