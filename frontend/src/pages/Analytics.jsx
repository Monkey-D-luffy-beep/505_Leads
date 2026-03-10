import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import {
  EnvelopeIcon,
  EnvelopeOpenIcon,
  ChatBubbleLeftRightIcon,
  UserGroupIcon,
  ArrowTrendingUpIcon,
} from '@heroicons/react/24/outline'
import {
  getOverviewStats,
  getEmailsOverTime,
  getSentimentBreakdown,
  getAbResults,
  getCampaigns,
} from '../api/client'
import { StatCard } from '../components/StatCard'
import { Spinner } from '../components/Shared'

const CHART_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4']
const PIE_COLORS = { interested: '#10b981', not_interested: '#ef4444', neutral: '#6366f1', out_of_office: '#f59e0b', unsubscribe: '#6b7280' }

export default function Analytics() {
  const [campaignId, setCampaignId] = useState('')

  const { data: stats, isLoading: loadingStats } = useQuery({
    queryKey: ['overview-stats'],
    queryFn: () => getOverviewStats().then((r) => r.data),
  })

  const { data: campaigns = [] } = useQuery({
    queryKey: ['campaigns-list'],
    queryFn: () => getCampaigns().then((r) => Array.isArray(r.data) ? r.data : r.data?.data || []),
  })

  const { data: emailsOverTime = [] } = useQuery({
    queryKey: ['emails-over-time', campaignId],
    queryFn: () =>
      getEmailsOverTime({ days: 30, campaign_id: campaignId || undefined }).then((r) =>
        Array.isArray(r.data) ? r.data : r.data?.data || []
      ),
  })

  const { data: sentimentBreakdown = [] } = useQuery({
    queryKey: ['sentiment-breakdown', campaignId],
    queryFn: () =>
      getSentimentBreakdown({ campaign_id: campaignId || undefined }).then((r) =>
        Array.isArray(r.data) ? r.data : r.data?.data || []
      ),
  })

  const { data: abResults = [] } = useQuery({
    queryKey: ['ab-results', campaignId],
    queryFn: () =>
      getAbResults({ campaign_id: campaignId || undefined }).then((r) =>
        Array.isArray(r.data) ? r.data : r.data?.data || []
      ),
  })

  if (loadingStats) return <Spinner />

  const openRate = stats?.emails_sent ? ((stats.emails_opened / stats.emails_sent) * 100).toFixed(1) : 0
  const replyRate = stats?.emails_sent ? ((stats.total_replies / stats.emails_sent) * 100).toFixed(1) : 0

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Analytics</h2>
        <select
          className="input w-56"
          value={campaignId}
          onChange={(e) => setCampaignId(e.target.value)}
        >
          <option value="">All Campaigns</option>
          {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard icon={EnvelopeIcon} label="Emails Sent" value={stats?.emails_sent ?? 0} color="indigo" />
        <StatCard icon={EnvelopeOpenIcon} label="Opens" value={stats?.emails_opened ?? 0} color="emerald" />
        <StatCard icon={ArrowTrendingUpIcon} label="Open Rate" value={`${openRate}%`} color="amber" />
        <StatCard icon={ChatBubbleLeftRightIcon} label="Replies" value={stats?.total_replies ?? 0} color="indigo" />
        <StatCard icon={UserGroupIcon} label="Reply Rate" value={`${replyRate}%`} color="emerald" />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Emails Over Time */}
        <div className="card">
          <h3 className="text-sm font-semibold text-white mb-4">Emails Sent (Last 30 Days)</h3>
          {emailsOverTime.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={emailsOverTime}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="date" tick={{ fill: '#9ca3af', fontSize: 11 }} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} />
                <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8, color: '#fff' }} />
                <Line type="monotone" dataKey="sent" stroke="#6366f1" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="opened" stroke="#10b981" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-gray-500 text-center py-12">No data yet</p>
          )}
        </div>

        {/* Sentiment Breakdown */}
        <div className="card">
          <h3 className="text-sm font-semibold text-white mb-4">Reply Sentiment</h3>
          {sentimentBreakdown.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={sentimentBreakdown}
                  dataKey="count"
                  nameKey="sentiment"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  innerRadius={50}
                  paddingAngle={3}
                  label={({ sentiment, count }) => `${sentiment}: ${count}`}
                >
                  {sentimentBreakdown.map((entry) => (
                    <Cell key={entry.sentiment} fill={PIE_COLORS[entry.sentiment] || '#6b7280'} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8, color: '#fff' }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-gray-500 text-center py-12">No replies yet</p>
          )}
        </div>
      </div>

      {/* A/B Results */}
      <div className="card">
        <h3 className="text-sm font-semibold text-white mb-4">A/B Test Results</h3>
        {abResults.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Campaign</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Step</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-400 uppercase">Variant</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-400 uppercase">Sent</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-400 uppercase">Opens</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-400 uppercase">Open Rate</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-400 uppercase">Replies</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-400 uppercase">Reply Rate</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {abResults.map((row, i) => {
                  const or = row.sent ? ((row.opens / row.sent) * 100).toFixed(1) : 0
                  const rr = row.sent ? ((row.replies / row.sent) * 100).toFixed(1) : 0
                  return (
                    <tr key={i} className="hover:bg-gray-800/50">
                      <td className="px-4 py-3 text-sm text-white">{row.campaign_name || row.campaign_id}</td>
                      <td className="px-4 py-3 text-sm text-gray-400">{row.step_order}</td>
                      <td className="px-4 py-3 text-center">
                        <span className={`rounded px-2 py-0.5 text-xs font-medium ${row.variant === 'a' ? 'bg-indigo-900/40 text-indigo-400' : 'bg-amber-900/40 text-amber-400'}`}>
                          {row.variant?.toUpperCase()}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center text-sm text-gray-300">{row.sent}</td>
                      <td className="px-4 py-3 text-center text-sm text-gray-300">{row.opens}</td>
                      <td className="px-4 py-3 text-center text-sm text-white font-medium">{or}%</td>
                      <td className="px-4 py-3 text-center text-sm text-gray-300">{row.replies}</td>
                      <td className="px-4 py-3 text-center text-sm text-white font-medium">{rr}%</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-gray-500 text-center py-8">No A/B test data available</p>
        )}
      </div>
    </div>
  )
}
