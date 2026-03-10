import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeftIcon,
  GlobeAltIcon,
  PhoneIcon,
  MapPinIcon,
  StarIcon,
  EnvelopeIcon,
  PlusIcon,
} from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import {
  getLead, updateLead, getLeadSignals, rescoreLead,
  getContacts, findEmails, addContact, getEmails, getReplies,
} from '../api/client'
import { Badge, ScoreBadge } from '../components/Badge'
import { Spinner } from '../components/Shared'
// Modal not needed here but kept import pattern consistent

const TABS = ['Signals', 'Contacts', 'Email History', 'Replies']

export default function LeadProfile() {
  const { id } = useParams()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState('Signals')
  const [notes, setNotes] = useState('')
  const [notesLoaded, setNotesLoaded] = useState(false)
  const [showAddContact, setShowAddContact] = useState(false)
  const [contactForm, setContactForm] = useState({ first_name: '', last_name: '', email: '', designation: '' })

  const { data: lead, isLoading } = useQuery({
    queryKey: ['lead', id],
    queryFn: () => getLead(id).then((r) => {
      if (!notesLoaded) { setNotes(r.data.notes || ''); setNotesLoaded(true) }
      return r.data
    }),
  })

  const { data: signals } = useQuery({
    queryKey: ['signals', id],
    queryFn: () => getLeadSignals(id).then((r) => r.data),
    enabled: tab === 'Signals',
  })

  const { data: contacts } = useQuery({
    queryKey: ['contacts', id],
    queryFn: () => getContacts({ lead_id: id }).then((r) => Array.isArray(r.data) ? r.data : r.data?.data || []),
    enabled: tab === 'Contacts',
  })

  const { data: emails } = useQuery({
    queryKey: ['emails-lead', id],
    queryFn: () => getEmails({ lead_id: id }).then((r) => r.data),
    enabled: tab === 'Email History',
  })

  const { data: replies } = useQuery({
    queryKey: ['replies-lead', id],
    queryFn: () => getReplies({ lead_id: id }).then((r) => r.data),
    enabled: tab === 'Replies',
  })

  const saveNotes = async () => {
    try {
      await updateLead(id, { notes })
      toast.success('Notes saved')
    } catch { toast.error('Failed to save notes') }
  }

  const handleRescore = async () => {
    try {
      await rescoreLead(id)
      queryClient.invalidateQueries({ queryKey: ['lead', id] })
      queryClient.invalidateQueries({ queryKey: ['signals', id] })
      toast.success('Lead re-scored')
    } catch { toast.error('Failed to re-score') }
  }

  const handleFindEmails = async () => {
    try {
      await findEmails(id)
      toast.success('Email finding triggered')
      queryClient.invalidateQueries({ queryKey: ['contacts', id] })
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed') }
  }

  const handleAddContact = async () => {
    try {
      await addContact({ ...contactForm, lead_id: id })
      toast.success('Contact added')
      setShowAddContact(false)
      setContactForm({ first_name: '', last_name: '', email: '', designation: '' })
      queryClient.invalidateQueries({ queryKey: ['contacts', id] })
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed') }
  }

  if (isLoading) return <Spinner />
  if (!lead) return <p className="text-red-400">Lead not found.</p>

  const signalList = signals?.data || (Array.isArray(signals) ? signals : [])
  const contactList = contacts?.data || (Array.isArray(contacts) ? contacts : [])
  const emailList = emails?.data || (Array.isArray(emails) ? emails : [])
  const replyList = replies?.data || (Array.isArray(replies) ? replies : [])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link to="/leads" className="rounded-lg border border-gray-700 p-2 hover:bg-gray-800">
          <ArrowLeftIcon className="h-4 w-4 text-gray-400" />
        </Link>
        <div className="flex-1">
          <h2 className="text-2xl font-bold text-white">{lead.company_name}</h2>
          <div className="flex items-center gap-3 mt-1">
            <Badge variant={lead.status}>{lead.status}</Badge>
            <ScoreBadge score={lead.lead_score || 0} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Company Info */}
        <div className="space-y-4">
          <div className="card space-y-4">
            <h3 className="text-lg font-semibold text-white">Company Info</h3>
            {lead.website && (
              <a href={lead.website.startsWith('http') ? lead.website : `https://${lead.website}`} target="_blank" rel="noreferrer"
                className="flex items-center gap-2 text-sm text-indigo-400 hover:text-indigo-300">
                <GlobeAltIcon className="h-4 w-4" /> {lead.website}
              </a>
            )}
            <div className="space-y-2 text-sm">
              {[
                [MapPinIcon, lead.location || lead.city],
                [null, `Industry: ${lead.industry || '—'}`],
                [PhoneIcon, lead.phone],
                [null, `Employees: ${lead.employee_estimate || '—'}`],
              ].map(([Icon, val], i) => val && (
                <div key={i} className="flex items-center gap-2 text-gray-400">
                  {Icon && <Icon className="h-4 w-4 text-gray-500" />}
                  {!Icon && <span className="w-4" />}
                  {val}
                </div>
              ))}
            </div>
            {(lead.google_rating != null) && (
              <div className="flex items-center gap-2">
                <StarIcon className="h-4 w-4 text-amber-400" />
                <span className="text-sm text-gray-300">{lead.google_rating} ({lead.google_review_count || 0} reviews)</span>
              </div>
            )}
          </div>

          {/* Notes */}
          <div className="card">
            <h3 className="text-sm font-semibold text-white mb-2">Notes</h3>
            <textarea
              className="input h-24 resize-none"
              placeholder="Add notes..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              onBlur={saveNotes}
            />
          </div>

          {/* Tags */}
          <div className="card">
            <h3 className="text-sm font-semibold text-white mb-2">Tags</h3>
            <div className="flex flex-wrap gap-1.5">
              {(lead.tags || []).map((tag) => (
                <span key={tag} className="rounded-full bg-gray-800 px-2.5 py-0.5 text-xs text-gray-300 border border-gray-700">
                  {tag}
                </span>
              ))}
              {(!lead.tags || lead.tags.length === 0) && <span className="text-xs text-gray-500">No tags</span>}
            </div>
          </div>
        </div>

        {/* Right: Tabs */}
        <div className="lg:col-span-2">
          <div className="flex border-b border-gray-700 mb-4">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-2.5 text-sm font-medium transition-colors ${
                  tab === t
                    ? 'text-indigo-400 border-b-2 border-indigo-400'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Signals Tab */}
          {tab === 'Signals' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-sm text-gray-400">Total Score: <span className="font-bold text-white">{lead.lead_score || 0}</span></p>
                <button onClick={handleRescore} className="btn-secondary text-xs">Re-score Lead</button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {signalList.map((sig) => (
                  <div key={sig.id} className="rounded-lg border border-gray-700 bg-gray-800/50 p-4">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium text-white">{sig.signal_key}</p>
                      <span className="text-xs font-bold text-emerald-400">+{sig.signal_score || 0}</span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">{sig.signal_value || 'Detected'}</p>
                  </div>
                ))}
                {signalList.length === 0 && <p className="text-sm text-gray-500 col-span-2">No signals detected yet.</p>}
              </div>
            </div>
          )}

          {/* Contacts Tab */}
          {tab === 'Contacts' && (
            <div className="space-y-4">
              <div className="flex gap-3">
                <button onClick={handleFindEmails} className="btn-primary text-xs">
                  <EnvelopeIcon className="h-3.5 w-3.5" /> Find Emails
                </button>
                <button onClick={() => setShowAddContact(!showAddContact)} className="btn-secondary text-xs">
                  <PlusIcon className="h-3.5 w-3.5" /> Add Contact
                </button>
              </div>
              {showAddContact && (
                <div className="card space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <input className="input" placeholder="First name" value={contactForm.first_name} onChange={(e) => setContactForm({ ...contactForm, first_name: e.target.value })} />
                    <input className="input" placeholder="Last name" value={contactForm.last_name} onChange={(e) => setContactForm({ ...contactForm, last_name: e.target.value })} />
                    <input className="input" placeholder="Email" value={contactForm.email} onChange={(e) => setContactForm({ ...contactForm, email: e.target.value })} />
                    <input className="input" placeholder="Designation" value={contactForm.designation} onChange={(e) => setContactForm({ ...contactForm, designation: e.target.value })} />
                  </div>
                  <button onClick={handleAddContact} className="btn-primary text-xs">Save Contact</button>
                </div>
              )}
              <div className="card p-0 overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-700 bg-gray-800/50">
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Name</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Email</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Designation</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Confidence</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {contactList.map((c) => (
                      <tr key={c.id} className="hover:bg-gray-800/50">
                        <td className="px-4 py-3 text-sm text-white">{c.full_name || `${c.first_name || ''} ${c.last_name || ''}`.trim() || '—'}</td>
                        <td className="px-4 py-3 text-sm text-gray-300">{c.email || '—'}</td>
                        <td className="px-4 py-3 text-sm text-gray-400">{c.designation || '—'}</td>
                        <td className="px-4 py-3 text-sm text-gray-400">{c.email_confidence != null ? `${c.email_confidence}%` : '—'}</td>
                        <td className="px-4 py-3"><Badge variant={c.email_status || 'draft'}>{c.email_status || 'unknown'}</Badge></td>
                      </tr>
                    ))}
                    {contactList.length === 0 && (
                      <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500">No contacts found</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Email History Tab */}
          {tab === 'Email History' && (
            <div className="space-y-3">
              {emailList.map((log) => (
                <div key={log.id} className="rounded-lg border border-gray-700 bg-gray-800/50 p-4">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-white">{log.subject || '(no subject)'}</p>
                    <Badge variant={log.status}>{log.status}</Badge>
                  </div>
                  <div className="flex gap-4 mt-2 text-xs text-gray-500">
                    {log.variant_sent && <span>Variant {log.variant_sent.toUpperCase()}</span>}
                    {log.sent_at && <span>Sent: {new Date(log.sent_at).toLocaleDateString()}</span>}
                    {log.opened_at && <span>Opened: {new Date(log.opened_at).toLocaleDateString()}</span>}
                  </div>
                </div>
              ))}
              {emailList.length === 0 && <p className="text-sm text-gray-500">No emails sent to this lead yet.</p>}
            </div>
          )}

          {/* Replies Tab */}
          {tab === 'Replies' && (
            <div className="space-y-3">
              {replyList.map((reply) => (
                <div key={reply.id} className="rounded-lg border border-gray-700 bg-gray-800/50 p-4">
                  <div className="flex items-center justify-between mb-2">
                    <Badge variant={reply.sentiment}>{reply.sentiment}</Badge>
                    <span className="text-xs text-gray-500">{new Date(reply.received_at).toLocaleString()}</span>
                  </div>
                  <p className="text-sm text-gray-300 whitespace-pre-wrap">{reply.body}</p>
                </div>
              ))}
              {replyList.length === 0 && <p className="text-sm text-gray-500">No replies received yet.</p>}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
