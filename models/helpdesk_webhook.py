from odoo import fields, models


class HelpdeskWebhookEvent(models.Model):
    _name = "helpdesk.webhook.event"
    _description = "Helpdesk Webhook Event"

    code = fields.Char(required=True)
    name = fields.Char(required=True, translate=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Event codes must be unique."),
    ]


class HelpdeskWebhook(models.Model):
    _name = "helpdesk.webhook"
    _description = "Helpdesk Outbound Webhook"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    url = fields.Char(required=True)
    secret = fields.Char(help="Sent as X-Haizop-Secret header if set.")
    team_id = fields.Many2one("helpdesk.team", help="Leave blank to apply to all teams.")
    event_ids = fields.Many2many(
        "helpdesk.webhook.event", string="Events", required=True,
    )
