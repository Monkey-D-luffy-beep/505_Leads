import { useState } from 'react'
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
import toast from 'react-hot-toast'
import { getOverviewStats, getEmails, getQueue, startScrapeJob } from '../api/client'
import { StatCard } from '../components/StatCard'
import { Badge } from '../components/Badge'
import { Modal } from '../components/Modal'
import { Spinner } from '../components/Shared'
import { formatDistanceToNow } from 'date-fns'

export default function Overview() {
  const [scrapeOpen, setScrapeOpen] = useState(false)
  const [scrapeForm, setScrapeForm] = useState({ keyword: '', location: '', max_results: 50 })
  const [scraping, setScraping] = useState(false)

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

  const handleScrape = async () => {
    if (!scrapeForm.keyword) return toast.error('Enter a keyword')
    setScraping(true)
    try {
      await startScrapeJob(scrapeForm)
      toast.success('Scrape job started!')
      setScrapeOpen(false)
      setScrapeForm({ keyword: '', location: '', max_results: 50 })
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Scrape failed')
    } finally {
      setScraping(false)
    }
  }

  if (isLoading) return <Spinner />

  const replyRate = stats?.emails_sent
    ? ((stats?.total_replies / stats.emails_sent) * 100).toFixed(1)
    : '0.0'

  const queueCount = queueData?.data?.length || 0
  const emails = recentEmails?.data || recentEmails || []

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
        <button onClick={() => setScrapeOpen(true)} className="btn-primary">
          <MagnifyingGlassIcon className="h-4 w-4" /> New Scrape Job
        </button>
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

      {/* Scrape Modal */}
      <Modal open={scrapeOpen} onClose={() => setScrapeOpen(false)} title="New Scrape Job">
        <div className="space-y-4">
          <div>
            <label className="label">Keyword *</label>
            <input
              className="input"
              placeholder="e.g. Web development agency"
              value={scrapeForm.keyword}
              onChange={(e) => setScrapeForm({ ...scrapeForm, keyword: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Location</label>
            <input
              className="input"
              placeholder="e.g. New York, USA"
              value={scrapeForm.location}
              onChange={(e) => setScrapeForm({ ...scrapeForm, location: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Max Results</label>
            <input
              type="number"
              className="input"
              value={scrapeForm.max_results}
              onChange={(e) => setScrapeForm({ ...scrapeForm, max_results: parseInt(e.target.value) || 50 })}
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button onClick={() => setScrapeOpen(false)} className="btn-secondary">Cancel</button>
            <button onClick={handleScrape} disabled={scraping} className="btn-primary">
              {scraping ? 'Starting...' : 'Start Scraping'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
