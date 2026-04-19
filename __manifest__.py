{
    "name": "HAIZOP Helpdesk",
    "version": "19.0.1.0.0",
    "summary": "Modern helpdesk with SLA, portal, AI triage scaffolding and webhooks — improved over Odoo Enterprise Helpdesk",
    "description": """
HAIZOP Helpdesk — Community-licensed replacement and improvement for Odoo Enterprise Helpdesk.

Highlights vs. Enterprise:
- First-response AND resolution SLA as separate policies
- Business-hours-aware SLA with per-team working calendar
- Breach prediction (at-risk banner before breach)
- Similar-ticket detection on create
- Outbound webhooks per event
- AI triage scaffolding (pluggable provider)
- Customer health score on res.partner
- Full portal, website form, email alias
""",
    "author": "HAIZOP",
    "website": "https://haizop.de",
    "category": "Services/Helpdesk",
    "license": "LGPL-3",
    "depends": [
        "base", "mail", "portal", "website", "rating", "utm", "resource",
    ],
    "data": [
        "security/helpdesk_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "data/helpdesk_data.xml",
        "data/mail_templates.xml",
        "data/ir_cron.xml",
        "views/helpdesk_tag_views.xml",
        "views/helpdesk_ticket_type_views.xml",
        "views/helpdesk_stage_views.xml",
        "views/helpdesk_team_views.xml",
        "views/helpdesk_dashboard_views.xml",
        "views/helpdesk_sla_views.xml",
        "views/helpdesk_webhook_views.xml",
        "views/helpdesk_ticket_views.xml",
        "views/helpdesk_menus.xml",
        "views/portal_templates.xml",
        "views/website_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "haizop_helpdesk/static/src/scss/helpdesk_portal.scss",
        ],
        "web.assets_backend": [
            "haizop_helpdesk/static/src/scss/helpdesk_backend.scss",
        ],
    },
    "application": True,
    "installable": True,
}
