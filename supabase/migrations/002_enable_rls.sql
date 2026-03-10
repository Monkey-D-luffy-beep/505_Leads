-- ============================================================
-- 002_enable_rls.sql
-- Enable Row Level Security on all public tables
-- The backend uses service_role key which bypasses RLS.
-- This blocks direct anon/public access to the tables.
-- ============================================================

-- Enable RLS on every table
alter table public.leads enable row level security;
alter table public.contacts enable row level security;
alter table public.signals enable row level security;
alter table public.signal_definitions enable row level security;
alter table public.campaigns enable row level security;
alter table public.sequences enable row level security;
alter table public.campaign_leads enable row level security;
alter table public.email_logs enable row level security;
alter table public.replies enable row level security;

-- Allow authenticated users full access (for future auth integration)
create policy "Authenticated full access on leads"
  on public.leads for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "Authenticated full access on contacts"
  on public.contacts for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "Authenticated full access on signals"
  on public.signals for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "Authenticated full access on signal_definitions"
  on public.signal_definitions for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "Authenticated full access on campaigns"
  on public.campaigns for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "Authenticated full access on sequences"
  on public.sequences for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "Authenticated full access on campaign_leads"
  on public.campaign_leads for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "Authenticated full access on email_logs"
  on public.email_logs for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "Authenticated full access on replies"
  on public.replies for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');
