import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircleIcon,
  XCircleIcon,
  PencilSquareIcon,
  EyeIcon,
  CheckIcon,
  FunnelIcon,
} from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import {
  getQueue,
  previewEmail,
  approveEmail,
  skipEmail,
  editQueuedEmail,
  bulkApprove,
} from '../api/client'
import { Badge } from '../components/Badge'
import { Modal } from '../components/Modal'
import { Spinner, EmptyState } from '../components/Shared'

export default function EmailQueue() {
  const queryClient = useQueryClient()
  const [campaignFilter, setCampaignFilter] = useState('')
  const [selected, setSelected] = useState([])
  const [previewId, setPreviewId] = useState(null)
  const [previewData, setPreviewData] = useState(null)
  const [editId, setEditId] = useState(null)
  const [editForm, setEditForm] = useState({ subject: '', body_html: '' })

  const { data: queue = [], isLoading } = useQuery({
    queryKey: ['queue', campaignFilter],
    queryFn: () =>
      getQueue({ campaign_id: campaignFilter || undefined, status: 'queued' }).then((r) =>
        Array.isArray(r.data) ? r.data : r.data?.data || []
      ),
    refetchInterval: 15000,
  })

  const approveMut = useMutation({
    mutationFn: (id) => approveEmail(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue'] })
      toast.success('Email approved')
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const skipMut = useMutation({
    mutationFn: (id) => skipEmail(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue'] })
      toast.success('Email skipped')
    },
  })

  const bulkMut = useMutation({
    mutationFn: (ids) => bulkApprove(ids),
    onSuccess: () => {
      setSelected([])
      queryClient.invalidateQueries({ queryKey: ['queue'] })
      toast.success(`${selected.length} emails approved`)
    },
  })

  const handlePreview = async (id) => {
    setPreviewId(id)
    try {
      const res = await previewEmail(id)
      setPreviewData(res.data)
    } catch {
      const item = queue.find((q) => q.id === id)
      setPreviewData(item || null)
    }
  }

  const handleEditOpen = (item) => {
    setEditId(item.id)
    setEditForm({ subject: item.subject || '', body_html: item.body_html || item.body || '' })
  }

  const handleEditSave = async () => {
    try {
      await editQueuedEmail(editId, editForm)
      setEditId(null)
      queryClient.invalidateQueries({ queryKey: ['queue'] })
      toast.success('Email updated')
    } catch (e) { toast.error(e.response?.data?.detail || 'Save failed') }
  }

  const toggleSelect = (id) => setSelected((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
  const toggleAll = () => setSelected(selected.length === queue.length ? [] : queue.map((q) => q.id))

  if (isLoading) return <Spinner />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Email Queue</h2>
        <div className="flex items-center gap-3">
          {selected.length > 0 && (
            <button onClick={() => bulkMut.mutate(selected)} className="btn-primary text-xs">
              <CheckCircleIcon className="h-4 w-4" /> Approve {selected.length} Selected
            </button>
          )}
          <div className="flex items-center gap-2">
            <FunnelIcon className="h-4 w-4 text-gray-400" />
            <input
              className="input w-48"
              placeholder="Filter by campaign ID"
              value={campaignFilter}
              onChange={(e) => setCampaignFilter(e.target.value)}
            />
          </div>
        </div>
      </div>

      {queue.length === 0 ? (
        <EmptyState
          title="Queue is empty"
          description="No emails waiting for review. Emails will appear here when campaigns generate them."
        />
      ) : (
        <div className="card p-0 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-700 bg-gray-800/50">
                <th className="w-10 px-4 py-3">
                  <input type="checkbox" checked={selected.length === queue.length && queue.length > 0} onChange={toggleAll}
                    className="rounded border-gray-600 bg-gray-800 text-indigo-600 focus:ring-indigo-500" />
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Subject</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Lead</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Campaign</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Variant</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Step</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-400 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {queue.map((item) => (
                <tr key={item.id} className="hover:bg-gray-800/50">
                  <td className="px-4 py-3">
                    <input type="checkbox" checked={selected.includes(item.id)} onChange={() => toggleSelect(item.id)}
                      className="rounded border-gray-600 bg-gray-800 text-indigo-600 focus:ring-indigo-500" />
                  </td>
                  <td className="px-4 py-3 text-sm text-white max-w-[250px] truncate">{item.subject || '(no subject)'}</td>
                  <td className="px-4 py-3 text-sm text-gray-300">{item.company_name || item.lead_id || '—'}</td>
                  <td className="px-4 py-3 text-sm text-gray-400">{item.campaign_name || item.campaign_id || '—'}</td>
                  <td className="px-4 py-3">
                    {item.variant_sent ? (
                      <span className="rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-300 uppercase">
                        {item.variant_sent}
                      </span>
                    ) : '—'}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-400">{item.step_order || '—'}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1.5">
                      <button onClick={() => handlePreview(item.id)} className="rounded-lg border border-gray-700 p-1.5 text-gray-400 hover:text-white hover:bg-gray-800" title="Preview">
                        <EyeIcon className="h-4 w-4" />
                      </button>
                      <button onClick={() => handleEditOpen(item)} className="rounded-lg border border-gray-700 p-1.5 text-gray-400 hover:text-white hover:bg-gray-800" title="Edit">
                        <PencilSquareIcon className="h-4 w-4" />
                      </button>
                      <button onClick={() => approveMut.mutate(item.id)} className="rounded-lg border border-gray-700 p-1.5 text-gray-400 hover:text-emerald-400 hover:bg-gray-800" title="Approve">
                        <CheckCircleIcon className="h-4 w-4" />
                      </button>
                      <button onClick={() => skipMut.mutate(item.id)} className="rounded-lg border border-gray-700 p-1.5 text-gray-400 hover:text-red-400 hover:bg-gray-800" title="Skip">
                        <XCircleIcon className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Preview Modal */}
      {previewId && previewData && (
        <Modal open onClose={() => { setPreviewId(null); setPreviewData(null) }} title="Email Preview" size="lg">
          <div className="space-y-4">
            <div>
              <p className="text-xs text-gray-500 uppercase mb-1">Subject</p>
              <p className="text-sm font-medium text-white">{previewData.subject}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase mb-1">Body</p>
              <div
                className="rounded-lg border border-gray-700 bg-gray-800 p-4 text-sm text-gray-300 prose prose-invert max-w-none"
                dangerouslySetInnerHTML={{ __html: previewData.body_html || previewData.body || '' }}
              />
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => { approveMut.mutate(previewId); setPreviewId(null); setPreviewData(null) }} className="btn-primary text-sm">
                <CheckIcon className="h-4 w-4" /> Approve & Send
              </button>
              <button onClick={() => { skipMut.mutate(previewId); setPreviewId(null); setPreviewData(null) }} className="btn-danger text-sm">
                Skip
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Edit Modal */}
      {editId && (
        <Modal open onClose={() => setEditId(null)} title="Edit Email" size="lg">
          <div className="space-y-4">
            <div>
              <label className="label">Subject</label>
              <input className="input" value={editForm.subject} onChange={(e) => setEditForm({ ...editForm, subject: e.target.value })} />
            </div>
            <div>
              <label className="label">Body HTML</label>
              <textarea
                className="input h-48 resize-none font-mono text-xs"
                value={editForm.body_html}
                onChange={(e) => setEditForm({ ...editForm, body_html: e.target.value })}
              />
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setEditId(null)} className="btn-secondary text-sm">Cancel</button>
              <button onClick={handleEditSave} className="btn-primary text-sm">Save Changes</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
