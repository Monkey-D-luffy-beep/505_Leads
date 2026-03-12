import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  UsersIcon,
  MegaphoneIcon,
  PaperAirplaneIcon,
  ChatBubbleLeftRightIcon,
  MagnifyingGlassIcon,
  PlusIcon,
} from '@heroicons/react/24/outline'
import { getOverviewStats, getEmails, getQueue } from '../api/client'
import { StatCard } from '../components/StatCard'
import { Badge } from '../components/Badge'
import { Spinner } from '../components/Shared'
import { formatDistanceToNow } from 'date-fns'

export default function Overview() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['overview-stats'],
    queryFn: () => getOverviewStats().then((r) => r.data),
  })

  const { data: recentEmails } = useQuery({
    queryKey: ['recent-emails'],
    queryFn: () => getEmails({ per_page: 10 }).then((r) => r.data),
  })

  const { data: queueData } = useQuery({
    queryKey: ['queue-count-overview'],
    queryFn: () => getQueue({ per_page: 1 }).then((r) => r.data),
  })

  const queueCount = queueData?.data?.length || 0
  const emails = recentEmails?.data || recentEmails || []

  if (isLoading) return <Spinner />

  const replyRate = stats?.emails_sent
    ? ((stats?.total_replies / stats.emails_sent) * 100).toFixed(1)
    : '0.0'

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Overview</h2>
          <p className="text-sm text-gray-400 mt-1">Your lead pipeline at a glance</p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Leads" value={stats?.total_leads ?? 0} icon={UsersIcon} color="indigo" />
        <StatCard label="Active Campaigns" value={stats?.active_campaigns ?? stats?.total_campaigns ?? 0} icon={MegaphoneIcon} color="emerald" />
        <StatCard label="Emails Sent" value={stats?.emails_sent_week ?? stats?.emails_sent ?? 0} icon={PaperAirplaneIcon} color="amber" />
        <StatCard label="Reply Rate" value={`${replyRate}%`} icon={ChatBubbleLeftRightIcon} color="indigo" />
      </div>

      {/* Queue Alert */}
      {queueCount > 0 && (
        <div className="rounded-lg border border-amber-700 bg-amber-900/20 p-4 flex items-center justify-between">
          <p className="text-sm text-amber-300">
            You have <span className="font-bold">{queueCount}</span> email{queueCount !== 1 ? 's' : ''} waiting for review
          </p>
          <Link to="/queue" className="btn-primary text-xs">
            Review Queue
          </Link>
        </div>
      )}

      {/* Quick Actions */}
      <div className="flex gap-3">
        <Link to="/leads" className="btn-primary">
          <MagnifyingGlassIcon className="h-4 w-4" /> 505 Leads
        </Link>
        <Link to="/campaigns/new" className="btn-secondary">
          <PlusIcon className="h-4 w-4" /> New Campaign
        </Link>
      </div>

      {/* Recent Activity */}
      <div className="card">
        <h3 className="text-lg font-semibold text-white mb-4">Recent Activity</h3>
        {Array.isArray(emails) && emails.length > 0 ? (
          <div className="space-y-3">
            {emails.slice(0, 10).map((log) => (
              <div key={log.id} className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-800/50 px-4 py-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white truncate">{log.subject || '(no subject)'}</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {log.campaign_leads?.leads?.company_name || 'Unknown'}
                  </p>
                </div>
                <div className="flex items-center gap-3 ml-4">
                  <Badge variant={log.status}>{log.status}</Badge>
                  {log.sent_at && (
                    <span className="text-xs text-gray-500 whitespace-nowrap">
                      {formatDistanceToNow(new Date(log.sent_at), { addSuffix: true })}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-500">No recent activity yet.</p>
        )}
      </div>
    </div>
  )
}
