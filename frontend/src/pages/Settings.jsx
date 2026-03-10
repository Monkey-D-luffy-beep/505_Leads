import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  PlusIcon,
  PencilSquareIcon,
  TrashIcon,
  EyeSlashIcon,
  EyeIcon,
  KeyIcon,
  CpuChipIcon,
  ServerStackIcon,
} from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import {
  getSignalDefinitions,
  createSignalDefinition,
  updateSignalDefinition,
  deleteSignalDefinition,
  checkDomainHealth,
} from '../api/client'
import { Badge } from '../components/Badge'
import { Modal } from '../components/Modal'
import { Spinner } from '../components/Shared'

export default function Settings() {
  const queryClient = useQueryClient()
  const [showAddSignal, setShowAddSignal] = useState(false)
  const [editSignal, setEditSignal] = useState(null)
  const [signalForm, setSignalForm] = useState({ signal_key: '', label: '', default_weight: 10, detection_type: 'scrape', tier: 'tier_1', is_active: true })
  const [visibleKeys, setVisibleKeys] = useState({})
  const [domainInput, setDomainInput] = useState('')
  const [domainHealth, setDomainHealth] = useState(null)
  const [domainLoading, setDomainLoading] = useState(false)

  const handleDomainCheck = async () => {
    setDomainLoading(true)
    try {
      const res = await checkDomainHealth(domainInput || undefined)
      setDomainHealth(res.data)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Domain check failed')
    } finally { setDomainLoading(false) }
  }

  const { data: definitions = [], isLoading } = useQuery({
    queryKey: ['signal-definitions'],
    queryFn: () =>
      getSignalDefinitions().then((r) => Array.isArray(r.data) ? r.data : r.data?.data || []),
  })

  const createMut = useMutation({
    mutationFn: (data) => createSignalDefinition(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['signal-definitions'] })
      setShowAddSignal(false)
      resetForm()
      toast.success('Signal created')
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed'),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }) => updateSignalDefinition(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['signal-definitions'] })
      setEditSignal(null)
      toast.success('Signal updated')
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id) => deleteSignalDefinition(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['signal-definitions'] })
      toast.success('Signal deleted')
    },
  })

  const resetForm = () => setSignalForm({ signal_key: '', label: '', default_weight: 10, detection_type: 'scrape', tier: 'tier_1', is_active: true })

  const toggleKey = (key) => setVisibleKeys((prev) => ({ ...prev, [key]: !prev[key] }))

  const apiKeys = [
    { key: 'SUPABASE_URL', label: 'Supabase URL', hint: 'Project URL from Supabase dashboard' },
    { key: 'SUPABASE_ANON_KEY', label: 'Supabase Anon Key', hint: 'Public anon key' },
    { key: 'HUNTER_API_KEY', label: 'Hunter.io API Key', hint: 'For email finding' },
    { key: 'BREVO_API_KEY', label: 'Brevo API Key', hint: 'SMTP or API key for email sending' },
    { key: 'BREVO_SENDER_EMAIL', label: 'Sender Email', hint: 'Verified sender address in Brevo' },
  ]

  if (isLoading) return <Spinner />

  return (
    <div className="space-y-8">
      <h2 className="text-2xl font-bold text-white">Settings</h2>

      {/* API Keys Section */}
      <section className="card">
        <div className="flex items-center gap-3 mb-4">
          <KeyIcon className="h-5 w-5 text-indigo-400" />
          <h3 className="text-lg font-semibold text-white">API Keys & Configuration</h3>
        </div>
        <p className="text-xs text-gray-500 mb-4">These keys are stored in your backend .env file. This view is read-only — edit them directly in the .env file on your server.</p>

        <div className="space-y-3">
          {apiKeys.map(({ key, label, hint }) => (
            <div key={key} className="flex items-center gap-4 rounded-lg border border-gray-700 bg-gray-800/50 px-4 py-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white">{label}</p>
                <p className="text-xs text-gray-500">{hint}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-gray-400 truncate max-w-[200px]">
                  {visibleKeys[key] ? `(stored in .env)` : '••••••••••••'}
                </span>
                <button onClick={() => toggleKey(key)} className="text-gray-500 hover:text-gray-300">
                  {visibleKeys[key] ? <EyeSlashIcon className="h-4 w-4" /> : <EyeIcon className="h-4 w-4" />}
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Domain Health Check */}
      <section className="card">
        <div className="flex items-center gap-3 mb-4">
          <ServerStackIcon className="h-5 w-5 text-cyan-400" />
          <h3 className="text-lg font-semibold text-white">Domain Health Check</h3>
        </div>
        <p className="text-xs text-gray-500 mb-4">Check your outreach domain's DNS records (SPF, DKIM, DMARC). Leave empty to auto-detect from BREVO_SENDER_EMAIL.</p>
        <div className="flex items-center gap-3 mb-4">
          <input className="input flex-1" placeholder="yourdomain.com (optional)" value={domainInput} onChange={(e) => setDomainInput(e.target.value)} />
          <button onClick={handleDomainCheck} disabled={domainLoading} className="btn-primary text-sm whitespace-nowrap">
            {domainLoading ? 'Checking...' : 'Check Domain'}
          </button>
        </div>
        {domainHealth && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-sm text-white font-medium">Domain: {domainHealth.domain}</span>
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                domainHealth.overall_health === 'good' ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-700/50' :
                domainHealth.overall_health === 'fair' ? 'bg-amber-900/40 text-amber-400 border border-amber-700/50' :
                'bg-red-900/40 text-red-400 border border-red-700/50'
              }`}>{domainHealth.overall_health}</span>
            </div>
            {['spf', 'dkim', 'dmarc'].map((rec) => {
              const d = domainHealth[rec]
              return (
                <div key={rec} className="rounded-lg border border-gray-700 bg-gray-800/50 px-4 py-3 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-white uppercase">{rec}</p>
                    {d.record && <p className="text-xs text-gray-500 mt-0.5 truncate max-w-lg">{d.record}</p>}
                    {rec === 'dmarc' && d.policy && <p className="text-xs text-gray-400 mt-0.5">Policy: {d.policy}</p>}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${d.found && d.valid ? 'bg-emerald-400' : d.found ? 'bg-amber-400' : 'bg-red-400'}`} />
                    <span className="text-xs text-gray-400">{d.found ? (d.valid ? 'Valid' : 'Found (needs review)') : 'Not found'}</span>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* Signal Library */}
      <section className="card">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <CpuChipIcon className="h-5 w-5 text-emerald-400" />
            <h3 className="text-lg font-semibold text-white">Signal Library</h3>
          </div>
          <button onClick={() => { resetForm(); setShowAddSignal(true) }} className="btn-primary text-xs">
            <PlusIcon className="h-4 w-4" /> Add Signal
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-700">
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Key</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Label</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Tier</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-400 uppercase">Weight</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Type</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-400 uppercase">Active</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-400 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {definitions.map((def) => (
                <tr key={def.id} className="hover:bg-gray-800/50">
                  <td className="px-4 py-3 text-sm font-mono text-indigo-400">{def.signal_key}</td>
                  <td className="px-4 py-3 text-sm text-white">{def.label}</td>
                  <td className="px-4 py-3 text-sm">
                    <Badge variant={def.tier || 'draft'}>{def.tier || '—'}</Badge>
                  </td>
                  <td className="px-4 py-3 text-center text-sm font-bold text-white">{def.default_weight}</td>
                  <td className="px-4 py-3 text-sm text-gray-400">{def.detection_type}</td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => updateMut.mutate({ id: def.id, data: { is_active: !def.is_active } })}
                      className={`rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors ${
                        def.is_active
                          ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-700/50 hover:bg-emerald-900/60'
                          : 'bg-gray-800 text-gray-500 border border-gray-700 hover:text-white'
                      }`}
                    >
                      {def.is_active ? 'Active' : 'Inactive'}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1.5">
                      <button
                        onClick={() => { setSignalForm({ ...def }); setEditSignal(def.id) }}
                        className="rounded-lg border border-gray-700 p-1.5 text-gray-400 hover:text-white hover:bg-gray-800"
                      >
                        <PencilSquareIcon className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => { if (confirm('Delete?')) deleteMut.mutate(def.id) }}
                        className="rounded-lg border border-gray-700 p-1.5 text-gray-400 hover:text-red-400 hover:bg-gray-800"
                      >
                        <TrashIcon className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {definitions.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">No signal definitions configured</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Domain & Sending */}
      <section className="card">
        <div className="flex items-center gap-3 mb-4">
          <ServerStackIcon className="h-5 w-5 text-amber-400" />
          <h3 className="text-lg font-semibold text-white">Sending Configuration</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[
            { label: 'IMAP Host', desc: 'e.g. imap.gmail.com', key: 'IMAP_HOST' },
            { label: 'IMAP Port', desc: 'Usually 993 for SSL', key: 'IMAP_PORT' },
            { label: 'IMAP User', desc: 'Email used for reply polling', key: 'IMAP_USER' },
            { label: 'IMAP Password', desc: 'App password for IMAP access', key: 'IMAP_PASSWORD' },
          ].map(({ label, desc }) => (
            <div key={label} className="rounded-lg border border-gray-700 bg-gray-800/50 px-4 py-3">
              <p className="text-sm font-medium text-white">{label}</p>
              <p className="text-xs text-gray-500">{desc}</p>
              <p className="mt-1 text-xs text-gray-600 italic">Set in backend .env</p>
            </div>
          ))}
        </div>
      </section>

      {/* Add/Edit Signal Modal */}
      {(showAddSignal || editSignal) && (
        <Modal
          open
          onClose={() => { setShowAddSignal(false); setEditSignal(null) }}
          title={editSignal ? 'Edit Signal' : 'Add Signal'}
        >
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Signal Key</label>
                <input className="input" placeholder="e.g. has_google_ads" value={signalForm.signal_key} onChange={(e) => setSignalForm({ ...signalForm, signal_key: e.target.value })} disabled={!!editSignal} />
              </div>
              <div>
                <label className="label">Label</label>
                <input className="input" placeholder="Human-readable label" value={signalForm.label} onChange={(e) => setSignalForm({ ...signalForm, label: e.target.value })} />
              </div>
              <div>
                <label className="label">Weight</label>
                <input type="number" className="input" value={signalForm.default_weight} min={0} max={100} onChange={(e) => setSignalForm({ ...signalForm, default_weight: parseInt(e.target.value) || 0 })} />
              </div>
              <div>
                <label className="label">Tier</label>
                <select className="input" value={signalForm.tier} onChange={(e) => setSignalForm({ ...signalForm, tier: e.target.value })}>
                  <option value="tier_1">Tier 1 (Intent)</option>
                  <option value="tier_2">Tier 2 (Fit)</option>
                  <option value="tier_3">Tier 3 (Boost)</option>
                </select>
              </div>
              <div>
                <label className="label">Detection Type</label>
                <select className="input" value={signalForm.detection_type} onChange={(e) => setSignalForm({ ...signalForm, detection_type: e.target.value })}>
                  <option value="scrape">Scrape</option>
                  <option value="enrichment">Enrichment</option>
                  <option value="manual">Manual</option>
                </select>
              </div>
              <div className="flex items-end">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={signalForm.is_active} onChange={(e) => setSignalForm({ ...signalForm, is_active: e.target.checked })}
                    className="rounded border-gray-600 bg-gray-800 text-indigo-600 focus:ring-indigo-500" />
                  <span className="text-sm text-gray-300">Active</span>
                </label>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => { setShowAddSignal(false); setEditSignal(null) }} className="btn-secondary text-sm">Cancel</button>
              <button
                onClick={() => {
                  if (editSignal) {
                    updateMut.mutate({ id: editSignal, data: signalForm })
                  } else {
                    createMut.mutate(signalForm)
                  }
                }}
                className="btn-primary text-sm"
              >
                {editSignal ? 'Save Changes' : 'Create Signal'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
