import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeftIcon,
  PlusIcon,
  TrashIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  DocumentDuplicateIcon,
} from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import {
  getCampaign,
  createCampaign,
  updateCampaign,
  getSequences,
  createSequence,
  updateSequence,
  deleteSequence,
} from '../api/client'
import { Spinner } from '../components/Shared'

const DEFAULT_FORM = {
  name: '',
  description: '',
  status: 'draft',
  send_mode: 'review',
  daily_limit: 25,
  min_score: 50,
  target_locations: '',
  target_industries: '',
  signal_weights: {},
  sequences: [],
}

const TEMPLATE_VARS = ['{{first_name}}', '{{last_name}}', '{{company_name}}', '{{website}}', '{{industry}}', '{{city}}']

export default function CampaignForm() {
  const { id } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const isEditing = !!id

  const [form, setForm] = useState(DEFAULT_FORM)
  const [saving, setSaving] = useState(false)
  const [expandedSeq, setExpandedSeq] = useState(null)

  const { isLoading } = useQuery({
    queryKey: ['campaign', id],
    queryFn: () => getCampaign(id).then((r) => r.data),
    enabled: isEditing,
    onSuccess: (data) => {
      setForm({
        ...DEFAULT_FORM,
        ...data,
        target_locations: Array.isArray(data.target_locations) ? data.target_locations.join(', ') : data.target_locations || '',
        target_industries: Array.isArray(data.target_industries) ? data.target_industries.join(', ') : data.target_industries || '',
        signal_weights: data.signal_weights || {},
      })
    },
  })

  const { data: sequences = [] } = useQuery({
    queryKey: ['sequences', id],
    queryFn: () => getSequences(id).then((r) => Array.isArray(r.data) ? r.data : r.data?.data || []),
    enabled: isEditing,
  })

  const [localSeqs, setLocalSeqs] = useState([])
  useEffect(() => {
    if (sequences.length > 0) setLocalSeqs(sequences)
  }, [sequences])

  const set = (key, val) => setForm((prev) => ({ ...prev, [key]: val }))

  const handleSave = async (activate = false) => {
    if (!form.name.trim()) { toast.error('Campaign name is required'); return }
    setSaving(true)
    try {
      const payload = {
        name: form.name,
        description: form.description,
        status: activate ? 'active' : form.status,
        send_mode: form.send_mode,
        daily_limit: parseInt(form.daily_limit) || 25,
        min_score: parseInt(form.min_score) || 0,
        target_locations: form.target_locations ? form.target_locations.split(',').map(s => s.trim()).filter(Boolean) : [],
        target_industries: form.target_industries ? form.target_industries.split(',').map(s => s.trim()).filter(Boolean) : [],
        signal_weights: form.signal_weights,
      }

      let campaignId = id
      if (isEditing) {
        await updateCampaign(id, payload)
      } else {
        const res = await createCampaign(payload)
        campaignId = res.data.id
      }

      // Save sequences
      for (const seq of localSeqs) {
        const seqPayload = {
          step_number: seq.step_number,
          delay_days: seq.delay_days,
          variant_a_subject: seq.variant_a_subject,
          variant_a_body: seq.variant_a_body,
          variant_b_subject: seq.variant_b_subject || null,
          variant_b_body: seq.variant_b_body || null,
        }
        if (seq.id && !seq._isNew) {
          await updateSequence(seq.id, seqPayload)
        } else {
          await createSequence(campaignId, seqPayload)
        }
      }

      queryClient.invalidateQueries({ queryKey: ['campaigns'] })
      toast.success(activate ? 'Campaign activated!' : 'Campaign saved')
      navigate('/campaigns')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Save failed')
    } finally { setSaving(false) }
  }

  const addStep = () => {
    const nextOrder = localSeqs.length > 0 ? Math.max(...localSeqs.map(s => s.step_number || 0)) + 1 : 1
    setLocalSeqs([...localSeqs, {
      _isNew: true,
      _key: Date.now(),
      step_number: nextOrder,
      delay_days: nextOrder === 1 ? 0 : 3,
      variant_a_subject: '',
      variant_a_body: '',
      variant_b_subject: '',
      variant_b_body: '',
    }])
    setExpandedSeq(localSeqs.length)
  }

  const updateSeq = (idx, key, val) => {
    setLocalSeqs((prev) => prev.map((s, i) => i === idx ? { ...s, [key]: val } : s))
  }

  const removeSeq = async (idx) => {
    const seq = localSeqs[idx]
    if (seq.id && !seq._isNew) { 
      try { await deleteSequence(seq.id) } catch { /* ignore */ }
    }
    setLocalSeqs((prev) => prev.filter((_, i) => i !== idx))
  }

  const insertVar = (idx, field, v) => {
    updateSeq(idx, field, (localSeqs[idx][field] || '') + v)
  }

  if (isEditing && isLoading) return <Spinner />

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/campaigns" className="rounded-lg border border-gray-700 p-2 hover:bg-gray-800">
          <ArrowLeftIcon className="h-4 w-4 text-gray-400" />
        </Link>
        <h2 className="text-2xl font-bold text-white">{isEditing ? 'Edit Campaign' : 'New Campaign'}</h2>
      </div>

      {/* Section 1: Basic Info */}
      <Section title="Basic Info">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="md:col-span-2">
            <label className="label">Campaign Name *</label>
            <input className="input" value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="e.g. Q1 SaaS Outreach" />
          </div>
          <div className="md:col-span-2">
            <label className="label">Description</label>
            <textarea className="input h-20 resize-none" value={form.description} onChange={(e) => set('description', e.target.value)} placeholder="Campaign notes..." />
          </div>
        </div>
      </Section>

      {/* Section 2: Target Filters */}
      <Section title="Target Filters">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="label">Minimum Lead Score</label>
            <input type="number" className="input" value={form.min_score} onChange={(e) => set('min_score', e.target.value)} min={0} max={100} />
          </div>
          <div />
          <div>
            <label className="label">Target Locations (comma-sep)</label>
            <input className="input" value={form.target_locations} onChange={(e) => set('target_locations', e.target.value)} placeholder="e.g. California, Texas, New York" />
          </div>
          <div>
            <label className="label">Target Industries (comma-sep)</label>
            <input className="input" value={form.target_industries} onChange={(e) => set('target_industries', e.target.value)} placeholder="e.g. SaaS, FinTech" />
          </div>
        </div>
      </Section>

      {/* Section 3: Send Settings */}
      <Section title="Send Settings">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="label">Send Mode</label>
            <select className="input" value={form.send_mode} onChange={(e) => set('send_mode', e.target.value)}>
              <option value="review">Review (manual approval)</option>
              <option value="auto">Auto Send</option>
            </select>
          </div>
          <div>
            <label className="label">Daily Limit</label>
            <input type="number" className="input" value={form.daily_limit} onChange={(e) => set('daily_limit', e.target.value)} min={1} max={200} />
          </div>
        </div>
      </Section>

      {/* Section 4: Sequences */}
      <Section title={`Email Sequences (${localSeqs.length} steps)`}>
        <div className="space-y-3">
          {localSeqs.map((seq, idx) => (
            <div key={seq.id || seq._key} className="rounded-lg border border-gray-700 bg-gray-800/50">
              {/* Step header */}
              <button
                className="flex w-full items-center justify-between px-4 py-3"
                onClick={() => setExpandedSeq(expandedSeq === idx ? null : idx)}
              >
                <div className="flex items-center gap-3">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white">
                    {seq.step_number}
                  </span>
                  <span className="text-sm font-medium text-white">
                    {seq.variant_a_subject || `Step ${seq.step_number}`}
                  </span>
                  {seq.delay_days > 0 && <span className="text-xs text-gray-500">+{seq.delay_days}d delay</span>}
                  {seq.variant_b_subject && (
                    <span className="ml-1 rounded bg-amber-900/40 px-1.5 py-0.5 text-[10px] font-medium text-amber-400 border border-amber-700/50">
                      A/B
                    </span>
                  )}
                </div>
                {expandedSeq === idx ? <ChevronUpIcon className="h-4 w-4 text-gray-400" /> : <ChevronDownIcon className="h-4 w-4 text-gray-400" />}
              </button>

              {expandedSeq === idx && (
                <div className="border-t border-gray-700 px-4 py-4 space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="label">Delay (days)</label>
                      <input type="number" className="input" value={seq.delay_days} onChange={(e) => updateSeq(idx, 'delay_days', parseInt(e.target.value) || 0)} min={0} />
                    </div>
                    <div />
                  </div>

                  {/* Variant A */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-indigo-400 uppercase tracking-wider">Variant A</span>
                      <VarButtons onClick={(v) => insertVar(idx, 'variant_a_body', v)} />
                    </div>
                    <input className="input" placeholder="Subject line A" value={seq.variant_a_subject} onChange={(e) => updateSeq(idx, 'variant_a_subject', e.target.value)} />
                    <textarea className="input h-32 resize-none font-mono text-xs" placeholder="Email body A — use template variables..." value={seq.variant_a_body} onChange={(e) => updateSeq(idx, 'variant_a_body', e.target.value)} />
                  </div>

                  {/* Variant B */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-amber-400 uppercase tracking-wider">Variant B (optional A/B test)</span>
                      <VarButtons onClick={(v) => insertVar(idx, 'variant_b_body', v)} />
                    </div>
                    <input className="input" placeholder="Subject line B" value={seq.variant_b_subject || ''} onChange={(e) => updateSeq(idx, 'variant_b_subject', e.target.value)} />
                    <textarea className="input h-32 resize-none font-mono text-xs" placeholder="Email body B (leave empty to skip A/B)..." value={seq.variant_b_body || ''} onChange={(e) => updateSeq(idx, 'variant_b_body', e.target.value)} />
                  </div>

                  <div className="flex justify-end">
                    <button onClick={() => removeSeq(idx)} className="btn-danger text-xs">
                      <TrashIcon className="h-3.5 w-3.5" /> Remove Step
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}

          <button onClick={addStep} className="btn-secondary w-full">
            <PlusIcon className="h-4 w-4" /> Add Step
          </button>
        </div>
      </Section>

      {/* Action bar */}
      <div className="flex items-center justify-end gap-3 pt-2 pb-8">
        <Link to="/campaigns" className="btn-secondary">Cancel</Link>
        <button onClick={() => handleSave(false)} disabled={saving} className="btn-secondary">
          {saving ? 'Saving...' : 'Save Draft'}
        </button>
        <button onClick={() => handleSave(true)} disabled={saving} className="btn-primary">
          {saving ? 'Saving...' : 'Save & Activate'}
        </button>
      </div>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="card">
      <h3 className="text-lg font-semibold text-white mb-4">{title}</h3>
      {children}
    </div>
  )
}

function VarButtons({ onClick }) {
  return (
    <div className="flex flex-wrap gap-1">
      {TEMPLATE_VARS.map((v) => (
        <button
          key={v}
          type="button"
          onClick={() => onClick(v)}
          className="rounded bg-gray-700 px-1.5 py-0.5 text-[10px] text-gray-300 hover:bg-gray-600 hover:text-white transition-colors"
        >
          {v.replace(/\{\{|\}\}/g, '')}
        </button>
      ))}
    </div>
  )
}
