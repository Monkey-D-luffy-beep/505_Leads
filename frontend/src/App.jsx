import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ChartBarIcon,
  MagnifyingGlassIcon,
  MegaphoneIcon,
  InboxStackIcon,
  ChatBubbleLeftRightIcon,
  ChartPieIcon,
  Cog6ToothIcon,
} from '@heroicons/react/24/outline'
import { getUnreadCount, getQueue } from './api/client'

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

function App() {
  const { data: unread } = useQuery({
    queryKey: ['unread-count'],
    queryFn: () => getUnreadCount().then((r) => r.data.count),
    refetchInterval: 30_000,
  })

  const { data: queueCount } = useQuery({
    queryKey: ['queue-count'],
    queryFn: () => getQueue({ per_page: 1 }).then((r) => r.data.data?.length || 0),
    refetchInterval: 30_000,
  })

  const badges = { replies: unread || 0, queue: queueCount || 0 }

  return (
    <Router>
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

          <div className="border-t border-gray-800 px-4 py-3">
            <p className="text-xs text-gray-600 text-center">v1.0 · Module 08</p>
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
    </Router>
  )
}

export default App
