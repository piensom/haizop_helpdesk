from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    helpdesk_ticket_count = fields.Integer(compute="_compute_helpdesk_metrics")
    helpdesk_open_ticket_count = fields.Integer(compute="_compute_helpdesk_metrics")
    helpdesk_breach_count = fields.Integer(compute="_compute_helpdesk_metrics")
    helpdesk_health_score = fields.Integer(
        compute="_compute_helpdesk_metrics",
        help="0–100. Starts at 100; subtract 5 per open ticket, 20 per breach, cap at 0.",
    )

    @api.depends()
    def _compute_helpdesk_metrics(self):
        Ticket = self.env["helpdesk.ticket"]
        for p in self:
            total = Ticket.search_count([("partner_id", "=", p.id)])
            opened = Ticket.search_count([("partner_id", "=", p.id), ("is_closed", "=", False)])
            breach = Ticket.search_count([("partner_id", "=", p.id), ("sla_status", "=", "breached")])
            p.helpdesk_ticket_count = total
            p.helpdesk_open_ticket_count = opened
            p.helpdesk_breach_count = breach
            p.helpdesk_health_score = max(0, 100 - 5 * opened - 20 * breach)

    def action_view_helpdesk_tickets(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Tickets",
            "res_model": "helpdesk.ticket",
            "view_mode": "list,form,kanban",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id},
        }
