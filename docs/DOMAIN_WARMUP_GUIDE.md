# Domain Setup, Warmup & Deliverability Guide

> **Read this BEFORE sending your first email.** Following this guide is the difference between landing in inboxes vs. spam.

---

## Step 1 — Register an Outreach Domain

**Never send cold outreach from your main business domain.**

Register a variation ($10-12/year via Namecheap, Cloudflare, or GoDaddy):

| Main Domain | Outreach Domain (examples) |
|---|---|
| yourbrand.com | teamyourbrand.com ✅ |
| yourbrand.com | getyourbrand.com ✅ |
| yourbrand.com | yourbrandco.com ✅ |

Set up a simple landing page on it — dead domains get flagged faster.

---

## Step 2 — DNS Records (Non-Negotiable)

Add all 3 records in your domain's DNS settings:

### SPF Record
| Field | Value |
|---|---|
| Type | TXT |
| Host | @ |
| Value | `v=spf1 include:sendinblue.com ~all` |

If also using Gmail: `v=spf1 include:sendinblue.com include:_spf.google.com ~all`

### DKIM Record
Get from **Brevo Dashboard** → Settings → Senders & IPs → Domains → Add your domain.

| Field | Value |
|---|---|
| Type | TXT |
| Host | `mail._domainkey` (Brevo specifies this) |
| Value | Long string starting with `v=DKIM1; k=rsa; p=...` |

### DMARC Record
| Field | Value |
|---|---|
| Type | TXT |
| Host | `_dmarc` |
| Value (start) | `v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com; pct=100` |

Progress over time:
1. **Week 1-2:** `p=none` (monitoring only)
2. **Week 3-4:** `p=quarantine` (suspected spam goes to junk)
3. **Week 5+:** `p=reject` (full protection)

### Verify Your Setup
- **MXToolbox:** https://mxtoolbox.com/spf.aspx
- **Mail Tester:** https://www.mail-tester.com (aim for 9/10+)
- **In-app:** Settings → Domain Health Check button

---

## Step 3 — Warmup Schedule (5 Weeks)

| Week | Emails/Day | Notes |
|---|---|---|
| 1 | 5 | Manual sends to real people (friends, colleagues, your other emails) |
| 2 | 10 | Mix of real contacts + early campaign leads |
| 3 | 20 | Start using tool's auto mode |
| 4 | 30 | Normal campaign volume |
| 5+ | 30-50 | Sustained pace — never exceed 50/day on a cold domain |

### Warmup Tips:
- **Reply** to warmup emails from other accounts — signals real conversation
- **Star/mark** as "not spam" if they hit Gmail spam
- Keep bounce rate **< 2%** at all times
- Keep spam complaint rate **< 0.1%** (1 per 1,000 emails)

---

## Step 4 — Email Content Best Practices

### Subject Lines
- 30-60 characters
- No ALL CAPS, no `!!!` or `???`
- No spam triggers: "FREE", "GUARANTEED", "ACT NOW", "LIMITED TIME"
- Personalize: "Quick question about {{company_name}}"

### Email Body
- **Plain text** outperforms heavy HTML for cold email
- Keep it SHORT: 3-5 sentences for initial outreach
- One clear ask (a question, not "BUY NOW")
- Max 1 link in first email
- No attachments on first email
- Always include your name, company name, and email

### Footer (Required by CAN-SPAM / GDPR)
```
{{sender_name}} | {{company_name}}
{{company_address}}
If you'd prefer not to receive emails like this, reply "unsubscribe".
```

---

## Step 5 — Ongoing Monitoring

### Weekly Metrics

| Metric | Good | Warning | Critical |
|---|---|---|---|
| Bounce rate | < 1% | 1-3% | > 3% → pause sending |
| Spam complaints | < 0.05% | 0.05-0.1% | > 0.1% → pause immediately |
| Open rate | > 30% | 20-30% | < 20% → rethink targeting |
| Reply rate | > 5% | 2-5% | < 2% → rethink messaging |

### If Bounce Rate Spikes
1. Stop sending immediately
2. Clean contact list — remove all bounced emails
3. Re-verify remaining contacts before resuming
4. Check Brevo dashboard for auto-suppressed contacts

### Monitoring Tools
- **Brevo Dashboard** — bounce and complaint tracking
- **Google Postmaster Tools** — https://postmaster.google.com
  - Add your outreach domain, verify via DNS
  - Monitor: spam rate, domain reputation, IP reputation
- **In-app Domain Health** — Settings page checks SPF/DKIM/DMARC

---

## Pre-Send Checklist

- [ ] Outreach domain registered (NOT your main domain)
- [ ] Domain has a landing page (not blank)
- [ ] SPF record added + verified
- [ ] DKIM record from Brevo added + verified
- [ ] DMARC record added (`p=none` initially)
- [ ] Mail-tester.com score ≥ 8/10
- [ ] Google Postmaster Tools account created
- [ ] Manual warmup started (at least 1 week)
- [ ] `BREVO_SENDER_EMAIL` set in your `.env`
- [ ] `OUTREACH_DOMAIN` set in your `.env`
