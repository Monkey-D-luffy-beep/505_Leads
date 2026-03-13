import axios from 'axios'
import { supabase } from '../lib/supabase'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// Attach Supabase access token to every request
client.interceptors.request.use(async (config) => {
  const { data: { session } } = await supabase.auth.getSession()
  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`
  }
  return config
})

// 401 → redirect to login
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// ── Leads ──────────────────────────────────────────────────────────────
export const getLeads = (params) => client.get('/leads', { params })
export const getLead = (id) => client.get(`/leads/${id}`)
export const updateLead = (id, data) => client.patch(`/leads/${id}`, data)
export const deleteLead = (id) => client.delete(`/leads/${id}`)
export const startScrapeJob = (data) => client.post('/leads/scrape', data)
export const getScrapeStatus = (jobId) => client.get(`/leads/scrape/status/${jobId}`)

// ── Signals (per lead) ────────────────────────────────────────────────
export const getLeadSignals = (leadId) => client.get(`/leads/${leadId}/signals`)
export const rescoreLead = (leadId) => client.post(`/leads/${leadId}/rescore`)

// ── Contacts ──────────────────────────────────────────────────────────
export const getContacts = ({ lead_id, ...params }) => client.get(`/leads/${lead_id}/contacts`, { params })
export const findEmails = (leadId) => client.post(`/leads/${leadId}/find-emails`)
export const addContact = (data) => { const { lead_id, ...body } = data; return client.post(`/leads/${lead_id}/contacts`, body) }

// ── Campaigns ─────────────────────────────────────────────────────────
export const getCampaigns = (params) => client.get('/campaigns', { params })
export const getCampaign = (id) => client.get(`/campaigns/${id}`)
export const createCampaign = (data) => client.post('/campaigns', data)
export const updateCampaign = (id, data) => client.patch(`/campaigns/${id}`, data)
export const deleteCampaign = (id) => client.delete(`/campaigns/${id}`)
export const enrollLeads = (id, data) => client.post(`/campaigns/${id}/enroll`, data)
export const pauseCampaign = (id) => client.post(`/campaigns/${id}/pause`)
export const resumeCampaign = (id) => client.post(`/campaigns/${id}/resume`)
export const getCampaignLeads = (id, params) => client.get(`/campaigns/${id}/leads`, { params })

// ── Sequences ─────────────────────────────────────────────────────────
export const getSequences = (campaignId) => client.get(`/campaigns/${campaignId}/sequences`)
export const createSequence = (campaignId, data) => client.post(`/campaigns/${campaignId}/sequences`, data)
export const updateSequence = (id, data) => client.patch(`/sequences/${id}`, data)
export const deleteSequence = (id) => client.delete(`/sequences/${id}`)

// ── Queue ─────────────────────────────────────────────────────────────
export const getQueue = (params) => client.get('/queue', { params })
export const previewEmail = (id) => client.get(`/queue/${id}`)
export const approveEmail = (id) => client.post(`/queue/${id}/approve`)
export const skipEmail = (id) => client.post(`/queue/${id}/skip`)
export const editQueuedEmail = (id, data) => client.patch(`/queue/${id}/edit`, data)
export const bulkApprove = (ids) => client.post('/queue/bulk-approve', { email_log_ids: ids })

// ── Emails ────────────────────────────────────────────────────────────
export const getEmails = (params) => client.get('/emails', { params })

// ── Replies ───────────────────────────────────────────────────────────
export const getReplies = (params) => client.get('/replies', { params })
export const getReply = (id) => client.get(`/replies/${id}`)
export const markRead = (id) => client.post(`/replies/${id}/mark-read`)
export const markAllRead = () => client.post('/replies/mark-all-read')
export const overrideSentiment = (id, sentiment) => client.patch(`/replies/${id}/sentiment`, { sentiment })
export const getUnreadCount = () => client.get('/replies/unread-count')

// ── Analytics ─────────────────────────────────────────────────────────
export const getOverviewStats = () => client.get('/analytics/overview')
export const getEmailsOverTime = (params) => client.get('/analytics/emails-over-time', { params })
export const getAbResults = (params) => client.get('/analytics/ab-results', { params })
export const getSentimentBreakdown = (params) => client.get('/analytics/sentiment-breakdown', { params })
export const getCampaignAnalytics = (id) => client.get(`/analytics/campaign/${id}`)

// ── Settings / Signal Definitions ─────────────────────────────────────
export const getSignalDefinitions = () => client.get('/signals/definitions')
export const createSignalDefinition = (data) => client.post('/signals/definitions', data)
export const updateSignalDefinition = (id, data) => client.patch(`/signals/definitions/${id}`, data)
export const deleteSignalDefinition = (id) => client.delete(`/signals/definitions/${id}`)

// ── Domain Health (Module 09) ─────────────────────────────────────────
export const checkDomainHealth = (domain) => client.get('/settings/domain-health', { params: { domain } })

export default client
