# HAIZOP Helpdesk

Community-licensed, improved alternative to Odoo Enterprise Helpdesk for Odoo 19 CE.

## Why
Enterprise Helpdesk costs a seat and still misses a few things (business-hours SLA, breach prediction, duplicate detection, outbound webhooks). This module covers the same surface area and adds those features — under LGPL-3.

## Features

### Parity with Enterprise
- Multi-team helpdesk with kanban/list/form/pivot/graph ticket views
- Per-team stages (configurable), priority, tags, types
- Manual / random / balanced assignment
- Email-to-ticket via `mail.alias`
- Customer portal (`/my/tickets`, `/my/ticket/<id>`) with reply + self-close
- Website form (`/helpdesk`)
- Customer rating request on close (`rating.mixin`)
- Merge tickets with message migration
- Activities, followers, full mail.thread

### Improvements over Enterprise
- **Separate first-response and resolution SLAs** — each tracks independently
- **Business-hours SLA deadlines** via `resource.calendar` (skips nights/weekends/holidays)
- **At-risk banner before breach** (configurable threshold, default 70% of window)
- **Similar-ticket detection** on create — shows the 5 most similar open tickets
- **Outbound webhooks** per event (`ticket.create` / `stage_change` / `assign` / `close`)
- **Customer health score** on `res.partner` (0–100, open + breach weighted)
- **AI triage scaffolding** — provider/endpoint/key fields per team (hook your own LLM)
- **Audit-friendly SLA status records** (one `helpdesk.sla.status` per ticket-policy pair)
- **SLA sweep cron** recomputes at-risk/breached status every 10 min

## Install
```bash
# Copy into your addons path, e.g.:
cp -r haizop_helpdesk /opt/odoo/addons/

# Install:
odoo -d <database> -i haizop_helpdesk --stop-after-init
# or via Apps UI
```

Dependencies: `base`, `mail`, `portal`, `website`, `rating`, `utm`, `resource` (all in Odoo CE).

## License
LGPL-3.

## Status
Tested on Odoo 19.0-20260409. Production deployment at https://haizop.de.
