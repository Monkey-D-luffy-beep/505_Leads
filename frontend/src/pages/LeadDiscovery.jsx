import { useState, useEffect, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  MagnifyingGlassIcon,
  FunnelIcon,
  EnvelopeIcon,
  MegaphoneIcon,
} from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { getLeads, startScrapeJob, getScrapeStatus, findEmails } from '../api/client'
import { Badge, ScoreBadge } from '../components/Badge'
import { Spinner, EmptyState } from '../components/Shared'

const API_BASE = import.meta.env.VITE_API_URL || '/api/v1'

// SSE stream reader helper
async function readSSE(response, onEvent) {
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try { onEvent(JSON.parse(line.slice(6))) } catch {}
      }
    }
  }
}

export default function LeadDiscovery() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({ status: '', min_score: 0, search: '' })
  const [selected, setSelected] = useState([])

  // Scrape state
  const [scrapeForm, setScrapeForm] = useState({ keyword: '', location: '', max_results: 50 })
  const [scraping, setScraping] = useState(false)
  const [jobStatus, setJobStatus] = useState(null)
  const [scrapeMode, setScrapeMode] = useState(null) // 'single' or 'batch'

  const { data, isLoading } = useQuery({
    queryKey: ['leads', page, filters],
    queryFn: () => getLeads({ page, per_page: 50, ...filters }).then((r) => r.data),
  })

  const handleScrape = async () => {
    if (!scrapeForm.keyword) return toast.error('Enter a keyword')
    if (!scrapeForm.location) return toast.error('Enter a location')
    setScraping(true)
    setJobStatus(null)
    setScrapeMode('single')

    try {
      const response = await fetch(`${API_BASE}/leads/scrape-sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(scrapeForm),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      await readSSE(response, (parsed) => {
        setJobStatus(parsed)
        if (parsed.status === 'completed') {
          toast.success(`Done! ${parsed.inserted || 0} leads added`)
          queryClient.invalidateQueries({ queryKey: ['leads'] })
          setScraping(false)
        } else if (parsed.status === 'failed' || parsed.status === 'captcha_blocked') {
          toast.error(parsed.status === 'captcha_blocked' ? 'CAPTCHA detected — try later' : 'Scrape failed')
          setScraping(false)
        }
      })
      setScraping(false)
    } catch (e) {
      toast.error('Scrape failed: ' + e.message)
      setScraping(false)
    }
  }

  const handleBatchScrape = async () => {
    const queries = [
      { keyword: 'web design agency', location: 'London', max_results: 60 },
      { keyword: 'digital marketing agency', location: 'London', max_results: 60 },
      { keyword: 'software development company', location: 'London', max_results: 60 },
      { keyword: 'SEO agency', location: 'Manchester', max_results: 50 },
      { keyword: 'web design agency', location: 'Birmingham', max_results: 50 },
      { keyword: 'marketing agency', location: 'Leeds', max_results: 50 },
      { keyword: 'web development company', location: 'Bristol', max_results: 50 },
      { keyword: 'digital agency', location: 'Edinburgh', max_results: 50 },
      { keyword: 'creative agency', location: 'Glasgow', max_results: 50 },
      { keyword: 'IT services company', location: 'London', max_results: 50 },
    ]

    setScraping(true)
    setJobStatus(null)
    setScrapeMode('batch')

    try {
      const response = await fetch(`${API_BASE}/leads/scrape-batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ queries }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      await readSSE(response, (parsed) => {
        setJobStatus(parsed)
        if (parsed.status === 'completed') {
          toast.success(`Batch complete! ${parsed.total_inserted || 0} leads added`)
          queryClient.invalidateQueries({ queryKey: ['leads'] })
          setScraping(false)
        } else if (parsed.status === 'captcha_blocked') {
          toast.error('CAPTCHA detected — Google is rate-limiting. Try again later.')
          setScraping(false)
        }
      })
      setScraping(false)
    } catch (e) {
      toast.error('Batch scrape failed: ' + e.message)
      setScraping(false)
    }
  }

  const handleBulkFindEmails = async () => {
    for (const id of selected) {
      try { await findEmails(id) } catch {}
    }
    toast.success(`Email finding triggered for ${selected.length} leads`)
    setSelected([])
  }

  const toggleSelect = (id) => {
    setSelected((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
  }

  const toggleAll = () => {
    const leads = data?.data || data || []
    if (selected.length === leads.length) setSelected([])
    else setSelected(leads.map((l) => l.id))
  }

  const leads = data?.data || (Array.isArray(data) ? data : [])

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-white">Lead Discovery</h2>

      {/* Scrape Panel */}
      <div className="card">
        <h3 className="text-lg font-semibold text-white mb-4">Scrape Google Maps</h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <input
            className="input"
            placeholder="Keyword (e.g. Web agency)"
            value={scrapeForm.keyword}
            onChange={(e) => setScrapeForm({ ...scrapeForm, keyword: e.target.value })}
          />
          <input
            className="input"
            placeholder="Location (e.g. London)"
            value={scrapeForm.location}
            onChange={(e) => setScrapeForm({ ...scrapeForm, location: e.target.value })}
          />
          <input
            type="number"
            className="input"
            placeholder="Max results"
            value={scrapeForm.max_results}
            onChange={(e) => setScrapeForm({ ...scrapeForm, max_results: parseInt(e.target.value) || 50 })}
          />
          <div className="flex gap-2">
            <button onClick={handleScrape} disabled={scraping} className="btn-primary justify-center flex-1">
              <MagnifyingGlassIcon className="h-4 w-4" />
              {scraping && scrapeMode === 'single' ? 'Scraping...' : 'Scrape'}
            </button>
            <button onClick={handleBatchScrape} disabled={scraping} className="btn-secondary justify-center flex-1 text-xs" title="Scrape 505+ leads across multiple UK cities & niches">
              <MegaphoneIcon className="h-4 w-4" />
              {scraping && scrapeMode === 'batch' ? 'Running...' : '505 Leads'}
            </button>
          </div>
        </div>

        {/* Single scrape progress */}
        {jobStatus && scraping && scrapeMode === 'single' && (
          <div className="mt-4">
            <div className="flex items-center justify-between text-sm text-gray-400 mb-1">
              <span>Status: {jobStatus.status} — {jobStatus.inserted || 0} inserted, {jobStatus.skipped_duplicates || 0} skipped</span>
              <span>{jobStatus.processed || 0} / {jobStatus.total_found || '?'}</span>
            </div>
            <div className="h-2 rounded-full bg-gray-800">
              <div
                className="h-2 rounded-full bg-indigo-500 transition-all"
                style={{ width: `${jobStatus.total_found ? (jobStatus.processed / jobStatus.total_found) * 100 : 10}%` }}
              />
            </div>
          </div>
        )}

        {/* Batch scrape progress */}
        {jobStatus && scraping && scrapeMode === 'batch' && (
          <div className="mt-4 space-y-2">
            <div className="flex items-center justify-between text-sm text-gray-400">
              <span>
                Query {jobStatus.current_query || 0}/{jobStatus.total_queries || 0}:
                <span className="text-indigo-400 ml-1">{jobStatus.current_keyword}</span>
                <span className="text-gray-500 ml-1">in {jobStatus.current_location}</span>
              </span>
              <span className="text-emerald-400 font-medium">{jobStatus.total_inserted || 0} leads collected</span>
            </div>
            <div className="h-2 rounded-full bg-gray-800">
              <div
                className="h-2 rounded-full bg-indigo-500 transition-all"
                style={{ width: `${jobStatus.total_queries ? (jobStatus.current_query / jobStatus.total_queries) * 100 : 5}%` }}
              />
            </div>
            <div className="text-xs text-gray-500">
              Found: {jobStatus.total_found || 0} | Inserted: {jobStatus.total_inserted || 0} | Skipped: {jobStatus.total_skipped || 0} | Errors: {jobStatus.total_errors || 0}
            </div>
          </div>
        )}

        {/* Completed summary */}
        {jobStatus && !scraping && jobStatus.status === 'completed' && (
          <div className="mt-4 rounded-lg border border-emerald-700 bg-emerald-900/20 px-4 py-3">
            <p className="text-sm text-emerald-400">
              Done! {scrapeMode === 'batch'
                ? `${jobStatus.total_queries || 0} queries completed — ${jobStatus.total_inserted || 0} new leads, ${jobStatus.total_skipped || 0} duplicates skipped.`
                : `Found ${jobStatus.total_found || 0} businesses — inserted ${jobStatus.inserted || 0} new leads, skipped ${jobStatus.skipped_duplicates || 0} duplicates.`
              }
            </p>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <FunnelIcon className="h-4 w-4 text-gray-500" />
          <span className="text-sm text-gray-400">Filters:</span>
        </div>
        <select
          className="input w-auto"
          value={filters.status}
          onChange={(e) => { setFilters({ ...filters, status: e.target.value }); setPage(1) }}
        >
          <option value="">All Status</option>
          <option value="new">New</option>
          <option value="scored">Scored</option>
          <option value="in_campaign">In Campaign</option>
          <option value="replied">Replied</option>
          <option value="converted">Converted</option>
          <option value="dead">Dead</option>
        </select>
        <input
          type="number"
          className="input w-24"
          placeholder="Min score"
          value={filters.min_score || ''}
          onChange={(e) => { setFilters({ ...filters, min_score: parseInt(e.target.value) || 0 }); setPage(1) }}
        />
        <input
          className="input w-48"
          placeholder="Search company..."
          value={filters.search}
          onChange={(e) => { setFilters({ ...filters, search: e.target.value }); setPage(1) }}
        />
      </div>

      {/* Bulk Actions */}
      {selected.length > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-indigo-700 bg-indigo-900/20 px-4 py-3">
          <span className="text-sm text-indigo-300">{selected.length} selected</span>
          <button onClick={handleBulkFindEmails} className="btn-primary text-xs">
            <EnvelopeIcon className="h-3.5 w-3.5" /> Find Emails
          </button>
        </div>
      )}

      {/* Table */}
      {isLoading ? (
        <Spinner />
      ) : (
        <div className="card p-0 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-700 bg-gray-800/50">
                <th className="px-4 py-3 text-left">
                  <input type="checkbox" className="rounded" checked={selected.length === leads.length && leads.length > 0} onChange={toggleAll} />
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Company</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Location</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Industry</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Score</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {leads.map((lead) => (
                <tr key={lead.id} className="hover:bg-gray-800/50 transition-colors">
                  <td className="px-4 py-3">
                    <input type="checkbox" className="rounded" checked={selected.includes(lead.id)} onChange={() => toggleSelect(lead.id)} />
                  </td>
                  <td className="px-4 py-3">
                    <Link to={`/leads/${lead.id}`} className="text-sm font-medium text-indigo-400 hover:text-indigo-300">
                      {lead.company_name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-400">{lead.city || lead.location || '—'}</td>
                  <td className="px-4 py-3 text-sm text-gray-400">{lead.industry || '—'}</td>
                  <td className="px-4 py-3"><ScoreBadge score={lead.lead_score || 0} /></td>
                  <td className="px-4 py-3"><Badge variant={lead.status}>{lead.status}</Badge></td>
                </tr>
              ))}
              {leads.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-12">
                    <EmptyState
                      icon={MagnifyingGlassIcon}
                      title="No leads found"
                      description="Start by scraping Google Maps or adjusting your filters."
                    />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="btn-secondary text-xs">
          Previous
        </button>
        <span className="text-sm text-gray-400">Page {page}</span>
        <button onClick={() => setPage((p) => p + 1)} disabled={leads.length < 50} className="btn-secondary text-xs">
          Next
        </button>
      </div>
    </div>
  )
}
