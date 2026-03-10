import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  InboxIcon,
  EnvelopeOpenIcon,
  EnvelopeIcon,
  FaceSmileIcon,
  FaceFrownIcon,
  QuestionMarkCircleIcon,
  NoSymbolIcon,
  ClockIcon,
  AdjustmentsHorizontalIcon,
} from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { getReplies, getReply, markRead, markAllRead, overrideSentiment } from '../api/client'
import { Badge } from '../components/Badge'
import { Spinner, EmptyState } from '../components/Shared'

const SENTIMENT_ICONS = {
  interested: { icon: FaceSmileIcon, color: 'text-emerald-400' },
  not_interested: { icon: FaceFrownIcon, color: 'text-red-400' },
  out_of_office: { icon: ClockIcon, color: 'text-amber-400' },
  unsubscribe: { icon: NoSymbolIcon, color: 'text-gray-500' },
  neutral: { icon: QuestionMarkCircleIcon, color: 'text-blue-400' },
}

const SENTIMENTS = ['interested', 'not_interested', 'neutral', 'out_of_office', 'unsubscribe']

export default function Replies() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState(null)
  const [filter, setFilter] = useState('all') // all | unread | interested | not_interested
  const [overrideVal, setOverrideVal] = useState('')

  const { data: replies = [], isLoading } = useQuery({
    queryKey: ['replies', filter],
    queryFn: () =>
      getReplies({
        ...(filter === 'unread' ? { is_read: false } : {}),
        ...(SENTIMENTS.includes(filter) ? { sentiment: filter } : {}),
      }).then((r) => Array.isArray(r.data) ? r.data : r.data?.data || []),
    refetchInterval: 20000,
  })

  const { data: detail } = useQuery({
    queryKey: ['reply', selectedId],
    queryFn: () => getReply(selectedId).then((r) => r.data),
    enabled: !!selectedId,
  })

  const markReadMut = useMutation({
    mutationFn: (id) => markRead(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['replies'] }),
  })

  const markAllMut = useMutation({
    mutationFn: () => markAllRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['replies'] })
      toast.success('All marked as read')
    },
  })

  const overrideMut = useMutation({
    mutationFn: ({ id, sentiment }) => overrideSentiment(id, sentiment),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['replies'] })
      queryClient.invalidateQueries({ queryKey: ['reply', selectedId] })
      toast.success('Sentiment updated')
    },
  })

  const handleSelect = (reply) => {
    setSelectedId(reply.id)
    if (!reply.is_read) markReadMut.mutate(reply.id)
  }

  if (isLoading) return <Spinner />

  const selected = detail || replies.find((r) => r.id === selectedId)
  const SentIcon = selected ? (SENTIMENT_ICONS[selected.sentiment] || SENTIMENT_ICONS.neutral) : null

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Replies</h2>
        <div className="flex items-center gap-3">
          <button onClick={() => markAllMut.mutate()} className="btn-secondary text-xs">
            <EnvelopeOpenIcon className="h-4 w-4" /> Mark All Read
          </button>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-2">
        <AdjustmentsHorizontalIcon className="h-4 w-4 text-gray-500" />
        {['all', 'unread', ...SENTIMENTS].map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              filter === f
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:text-white'
            }`}
          >
            {f.replace(/_/g, ' ')}
          </button>
        ))}
      </div>

      {replies.length === 0 ? (
        <EmptyState
          icon={InboxIcon}
          title="No replies"
          description="Replies from your prospects will appear here when they respond to your campaigns."
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4" style={{ minHeight: '60vh' }}>
          {/* Inbox list */}
          <div className="lg:col-span-2 card p-0 overflow-y-auto max-h-[75vh] divide-y divide-gray-800">
            {replies.map((reply) => {
              const SI = SENTIMENT_ICONS[reply.sentiment] || SENTIMENT_ICONS.neutral
              return (
                <button
                  key={reply.id}
                  onClick={() => handleSelect(reply)}
                  className={`w-full text-left px-4 py-3 transition-colors ${
                    selectedId === reply.id ? 'bg-gray-800' : 'hover:bg-gray-800/50'
                  } ${!reply.is_read ? 'border-l-2 border-indigo-500' : ''}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <SI.icon className={`h-4 w-4 flex-shrink-0 ${SI.color}`} />
                      <span className={`text-sm truncate ${!reply.is_read ? 'font-semibold text-white' : 'text-gray-300'}`}>
                        {reply.from_email || reply.company_name || 'Unknown'}
                      </span>
                    </div>
                    {!reply.is_read && <span className="h-2 w-2 rounded-full bg-indigo-500 flex-shrink-0" />}
                  </div>
                  <p className="text-xs text-gray-500 mt-1 truncate">
                    {reply.subject || reply.body?.substring(0, 80) || '(no content)'}
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    <Badge variant={reply.sentiment}>{reply.sentiment?.replace(/_/g, ' ')}</Badge>
                    <span className="text-[10px] text-gray-600">
                      {reply.received_at ? new Date(reply.received_at).toLocaleDateString() : ''}
                    </span>
                  </div>
                </button>
              )
            })}
          </div>

          {/* Detail pane */}
          <div className="lg:col-span-3 card">
            {!selected ? (
              <div className="flex h-full items-center justify-center text-gray-500 text-sm">
                Select a reply to view details
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="text-lg font-semibold text-white">{selected.from_email || 'Unknown sender'}</h3>
                    <p className="text-sm text-gray-400 mt-0.5">{selected.subject || '(no subject)'}</p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {SentIcon && <SentIcon.icon className={`h-5 w-5 ${SentIcon.color}`} />}
                    <Badge variant={selected.sentiment}>{selected.sentiment?.replace(/_/g, ' ')}</Badge>
                  </div>
                </div>

                <div className="flex items-center gap-3 text-xs text-gray-500">
                  {selected.received_at && <span>Received: {new Date(selected.received_at).toLocaleString()}</span>}
                  {selected.campaign_name && <span>Campaign: {selected.campaign_name}</span>}
                  {selected.confidence_score != null && <span>Confidence: {Math.round(selected.confidence_score * 100)}%</span>}
                </div>

                <div className="rounded-lg border border-gray-700 bg-gray-800 p-4 text-sm text-gray-300 whitespace-pre-wrap max-h-64 overflow-y-auto">
                  {selected.body || '(empty body)'}
                </div>

                {/* Original email thread */}
                {selected.original_subject && (
                  <div className="rounded-lg border border-gray-800 bg-gray-900 p-4 text-xs text-gray-500">
                    <p className="font-medium text-gray-400 mb-1">Original: {selected.original_subject}</p>
                    <p className="truncate">{selected.original_body?.substring(0, 200)}</p>
                  </div>
                )}

                {/* Sentiment override */}
                <div className="flex items-center gap-3 pt-2 border-t border-gray-700">
                  <span className="text-xs text-gray-500">Override sentiment:</span>
                  <select
                    className="input w-auto text-xs py-1"
                    value={overrideVal || selected.sentiment || ''}
                    onChange={(e) => setOverrideVal(e.target.value)}
                  >
                    {SENTIMENTS.map((s) => (
                      <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
                    ))}
                  </select>
                  <button
                    onClick={() => {
                      if (overrideVal && overrideVal !== selected.sentiment) {
                        overrideMut.mutate({ id: selected.id, sentiment: overrideVal })
                      }
                    }}
                    className="btn-secondary text-xs py-1"
                    disabled={!overrideVal || overrideVal === selected.sentiment}
                  >
                    Apply
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
