import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  PlusIcon,
  PencilSquareIcon,
  PlayIcon,
  PauseIcon,
  UsersIcon,
  EnvelopeIcon,
  ChatBubbleLeftRightIcon,
  TrashIcon,
} from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { getCampaigns, pauseCampaign, resumeCampaign, deleteCampaign, getCampaignAnalytics } from '../api/client'
import { Badge } from '../components/Badge'
import { Spinner, EmptyState } from '../components/Shared'

export default function Campaigns() {
  const queryClient = useQueryClient()

  const { data: campaigns = [], isLoading } = useQuery({
    queryKey: ['campaigns'],
    queryFn: () => getCampaigns().then((r) => (Array.isArray(r.data) ? r.data : r.data?.data || [])),
  })

  const toggleMut = useMutation({
    mutationFn: ({ id, status }) =>
      status === 'active' ? pauseCampaign(id) : resumeCampaign(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaigns'] })
      toast.success('Campaign updated')
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Action failed'),
  })

  const deleteMut = useMutation({
    mutationFn: (id) => deleteCampaign(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaigns'] })
      toast.success('Campaign deleted')
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Delete failed'),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Campaigns</h2>
        <Link to="/campaigns/new" className="btn-primary">
          <PlusIcon className="h-4 w-4" /> New Campaign
        </Link>
      </div>

      {campaigns.length === 0 ? (
        <EmptyState
          title="No campaigns yet"
          description="Create your first campaign to start reaching prospects."
          action={<Link to="/campaigns/new" className="btn-primary text-sm"><PlusIcon className="h-4 w-4" /> Create Campaign</Link>}
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {campaigns.map((c) => (
            <CampaignCard key={c.id} campaign={c} onToggle={toggleMut.mutate} onDelete={deleteMut.mutate} />
          ))}
        </div>
      )}
    </div>
  )
}

function CampaignCard({ campaign: c, onToggle, onDelete }) {
  const enrolled = c.enrolled_count ?? c.leads_enrolled ?? 0
  const sent = c.sent_count ?? c.emails_sent ?? 0
  const replies = c.reply_count ?? c.replies ?? 0

  return (
    <div className="card hover:border-gray-600 transition-colors">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <Link to={`/campaigns/${c.id}/edit`} className="text-lg font-semibold text-white hover:text-indigo-400 transition-colors">
            {c.name}
          </Link>
          {c.description && <p className="text-sm text-gray-400 mt-0.5 truncate">{c.description}</p>}
        </div>
        <Badge variant={c.status}>{c.status}</Badge>
      </div>

      <div className="grid grid-cols-3 gap-4 mt-5 pt-4 border-t border-gray-700">
        <Metric icon={UsersIcon} label="Enrolled" value={enrolled} />
        <Metric icon={EnvelopeIcon} label="Sent" value={sent} />
        <Metric icon={ChatBubbleLeftRightIcon} label="Replies" value={replies} />
      </div>

      <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-800">
        <span className="text-xs text-gray-500">
          <Badge variant={c.send_mode}>{c.send_mode}</Badge>
          <span className="ml-2">{c.daily_limit}/day</span>
        </span>
        <div className="flex gap-1.5">
          <button
            onClick={() => onToggle({ id: c.id, status: c.status })}
            className="rounded-lg border border-gray-700 p-1.5 text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
            title={c.status === 'active' ? 'Pause' : 'Resume'}
          >
            {c.status === 'active' ? <PauseIcon className="h-4 w-4" /> : <PlayIcon className="h-4 w-4" />}
          </button>
          <Link
            to={`/campaigns/${c.id}/edit`}
            className="rounded-lg border border-gray-700 p-1.5 text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
            title="Edit"
          >
            <PencilSquareIcon className="h-4 w-4" />
          </Link>
          <button
            onClick={() => { if (confirm('Delete this campaign?')) onDelete(c.id) }}
            className="rounded-lg border border-gray-700 p-1.5 text-gray-400 hover:text-red-400 hover:bg-gray-800 transition-colors"
            title="Delete"
          >
            <TrashIcon className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

function Metric({ icon: Icon, label, value }) {
  return (
    <div className="text-center">
      <Icon className="h-4 w-4 text-gray-500 mx-auto mb-1" />
      <p className="text-lg font-bold text-white">{value}</p>
      <p className="text-xs text-gray-500">{label}</p>
    </div>
  )
}
