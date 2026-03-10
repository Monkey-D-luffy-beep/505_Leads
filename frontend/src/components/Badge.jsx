const variants = {
  // Status badges
  active: 'bg-emerald-900/50 text-emerald-300 border border-emerald-700',
  draft: 'bg-gray-800 text-gray-300 border border-gray-600',
  paused: 'bg-amber-900/50 text-amber-300 border border-amber-700',
  complete: 'bg-blue-900/50 text-blue-300 border border-blue-700',
  new: 'bg-gray-800 text-gray-300 border border-gray-600',
  scored: 'bg-indigo-900/50 text-indigo-300 border border-indigo-700',
  in_campaign: 'bg-blue-900/50 text-blue-300 border border-blue-700',
  replied: 'bg-emerald-900/50 text-emerald-300 border border-emerald-700',
  converted: 'bg-emerald-900/50 text-emerald-300 border border-emerald-700',
  dead: 'bg-red-900/50 text-red-300 border border-red-700',

  // Email status
  queued: 'bg-gray-800 text-gray-300 border border-gray-600',
  approved: 'bg-blue-900/50 text-blue-300 border border-blue-700',
  sent: 'bg-indigo-900/50 text-indigo-300 border border-indigo-700',
  opened: 'bg-emerald-900/50 text-emerald-300 border border-emerald-700',
  clicked: 'bg-emerald-900/50 text-emerald-300 border border-emerald-700',
  bounced: 'bg-red-900/50 text-red-300 border border-red-700',
  failed: 'bg-red-900/50 text-red-300 border border-red-700',
  skipped: 'bg-gray-800 text-gray-400 border border-gray-600',

  // Sentiment
  positive: 'bg-emerald-900/50 text-emerald-300 border border-emerald-700',
  negative: 'bg-red-900/50 text-red-300 border border-red-700',
  neutral: 'bg-gray-800 text-gray-300 border border-gray-600',
  'out-of-office': 'bg-amber-900/50 text-amber-300 border border-amber-700',
  unsubscribe: 'bg-red-900/50 text-red-300 border border-red-700',

  // Send mode
  auto: 'bg-emerald-900/50 text-emerald-300 border border-emerald-700',
  review: 'bg-amber-900/50 text-amber-300 border border-amber-700',
}

export function Badge({ children, variant = 'draft' }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${variants[variant] || variants.draft}`}>
      {children}
    </span>
  )
}

export function ScoreBadge({ score }) {
  let cls = 'bg-red-900 text-red-300'
  if (score >= 60) cls = 'bg-emerald-900 text-emerald-300'
  else if (score >= 30) cls = 'bg-amber-900 text-amber-300'

  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold ${cls}`}>
      {score}
    </span>
  )
}
