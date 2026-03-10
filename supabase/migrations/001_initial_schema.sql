-- ============================================================
-- 001_initial_schema.sql
-- Full schema for outbound lead generation & campaign tool
-- ============================================================

-- leads table
create table leads (
  id uuid primary key default gen_random_uuid(),
  company_name text not null,
  website text,
  location text,
  city text,
  country text,
  industry text,
  phone text,
  address text,
  google_rating numeric,
  google_review_count integer,
  employee_estimate text,
  lead_score integer default 0,
  score_breakdown jsonb default '{}',
  status text default 'new' check (status in ('new','scored','in_campaign','replied','converted','dead')),
  notes text,
  tags text[],
  raw_data jsonb default '{}',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- contacts table
create table contacts (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid references leads(id) on delete cascade,
  first_name text,
  last_name text,
  full_name text,
  designation text,
  email text,
  email_confidence integer,
  email_status text default 'unverified' check (email_status in ('unverified','verified','bounced','invalid')),
  linkedin_url text,
  created_at timestamptz default now()
);

-- signals table
create table signals (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid references leads(id) on delete cascade,
  signal_key text not null,
  signal_value text,
  signal_score integer default 0,
  detected_at timestamptz default now()
);

-- signal_definitions table (configurable in UI)
create table signal_definitions (
  id uuid primary key default gen_random_uuid(),
  signal_key text unique not null,
  label text not null,
  description text,
  tier integer check (tier in (1,2,3)),
  default_weight integer default 10,
  detection_type text default 'auto' check (detection_type in ('auto','manual','custom')),
  detection_logic jsonb default '{}',
  is_active boolean default true,
  created_at timestamptz default now()
);

-- campaigns table
create table campaigns (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  description text,
  target_filters jsonb default '{}',
  min_score integer default 30,
  signal_weights jsonb default '{}',
  status text default 'draft' check (status in ('draft','active','paused','complete')),
  send_mode text default 'review' check (send_mode in ('auto','review')),
  daily_limit integer default 30,
  send_window_start time default '09:00',
  send_window_end time default '17:00',
  timezone text default 'UTC',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- sequences table
create table sequences (
  id uuid primary key default gen_random_uuid(),
  campaign_id uuid references campaigns(id) on delete cascade,
  step_number integer not null,
  step_name text,
  delay_days integer default 0,
  variant_a_subject text,
  variant_a_body text,
  variant_b_subject text,
  variant_b_body text,
  split_ratio numeric default 0.5,
  winner_variant text,
  created_at timestamptz default now()
);

-- campaign_leads table (junction)
create table campaign_leads (
  id uuid primary key default gen_random_uuid(),
  campaign_id uuid references campaigns(id) on delete cascade,
  lead_id uuid references leads(id) on delete cascade,
  contact_id uuid references contacts(id),
  current_step integer default 0,
  status text default 'enrolled' check (status in ('enrolled','active','paused','replied','completed','unsubscribed')),
  enrolled_at timestamptz default now(),
  next_send_at timestamptz,
  unique(campaign_id, lead_id)
);

-- email_logs table
create table email_logs (
  id uuid primary key default gen_random_uuid(),
  campaign_lead_id uuid references campaign_leads(id) on delete cascade,
  contact_id uuid references contacts(id),
  sequence_id uuid references sequences(id),
  variant_sent text check (variant_sent in ('a','b')),
  subject text,
  body text,
  status text default 'queued' check (status in ('queued','approved','skipped','sending','sent','opened','clicked','replied','bounced','failed')),
  tracking_id text unique,
  queued_at timestamptz default now(),
  sent_at timestamptz,
  opened_at timestamptz,
  clicked_at timestamptz,
  replied_at timestamptz
);

-- replies table
create table replies (
  id uuid primary key default gen_random_uuid(),
  email_log_id uuid references email_logs(id),
  contact_id uuid references contacts(id),
  received_at timestamptz default now(),
  subject text,
  body text,
  sentiment text check (sentiment in ('positive','negative','neutral','out-of-office','unsubscribe')),
  is_read boolean default false,
  raw_payload jsonb default '{}'
);
