from odoo import api, fields, models


class HelpdeskSLA(models.Model):
    _name = "helpdesk.sla"
    _description = "Helpdesk SLA Policy"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    team_id = fields.Many2one("helpdesk.team", required=True, ondelete="cascade")
    target_type = fields.Selection(
        [("first_response", "First Response"), ("resolution", "Resolution")],
        default="resolution",
        required=True,
        help="First Response = time to first human reply. Resolution = time to reach closing stage.",
    )
    priority = fields.Selection(
        [("0", "Any"), ("1", "Low"), ("2", "Normal"), ("3", "High"), ("4", "Urgent")],
        default="0",
        required=True,
    )
    ticket_type_id = fields.Many2one("helpdesk.ticket.type")
    tag_ids = fields.Many2many("helpdesk.tag")
    partner_ids = fields.Many2many(
        "res.partner",
        help="Optional: limit this SLA to specific customers (e.g. VIP).",
    )
    stage_id = fields.Many2one(
        "helpdesk.stage",
        string="Reach Stage",
        help="For resolution SLA, the stage the ticket must reach. Defaults to first closing stage of the team.",
    )
    time_hours = fields.Float(
        string="Time (working hours)",
        default=8.0,
        required=True,
        help="Deadline expressed in working hours, based on the team's working calendar.",
    )
    at_risk_ratio = fields.Float(
        string="At-Risk Threshold",
        default=0.7,
        help="Show an 'at risk' banner when this fraction of the SLA window is consumed.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs._recompute_applicable_tickets()
        return recs

    def write(self, vals):
        res = super().write(vals)
        self._recompute_applicable_tickets()
        return res

    def _recompute_applicable_tickets(self):
        Ticket = self.env["helpdesk.ticket"]
        tickets = Ticket.search([
            ("team_id", "in", self.mapped("team_id").ids),
            ("is_closed", "=", False),
        ])
        tickets._apply_slas()
