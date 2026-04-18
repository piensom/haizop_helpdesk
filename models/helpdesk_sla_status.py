from odoo import api, fields, models


class HelpdeskSLAStatus(models.Model):
    _name = "helpdesk.sla.status"
    _description = "Helpdesk SLA Status (per ticket)"
    _order = "deadline asc, id"

    ticket_id = fields.Many2one("helpdesk.ticket", required=True, ondelete="cascade", index=True)
    sla_id = fields.Many2one("helpdesk.sla", required=True, ondelete="cascade")
    target_type = fields.Selection(related="sla_id.target_type", store=True)
    deadline = fields.Datetime(required=True)
    reached_date = fields.Datetime(help="When the SLA target was met.")
    status = fields.Selection(
        [("pending", "Pending"), ("at_risk", "At Risk"), ("reached", "Reached"), ("breached", "Breached")],
        default="pending",
        compute="_compute_status",
        store=True,
    )

    @api.depends("reached_date", "deadline", "sla_id.at_risk_ratio", "ticket_id.create_date")
    def _compute_status(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.reached_date:
                rec.status = "reached" if rec.reached_date <= rec.deadline else "breached"
                continue
            if not rec.deadline:
                rec.status = "pending"
                continue
            if now >= rec.deadline:
                rec.status = "breached"
                continue
            total = (rec.deadline - rec.ticket_id.create_date).total_seconds() or 1
            elapsed = (now - rec.ticket_id.create_date).total_seconds()
            if elapsed / total >= (rec.sla_id.at_risk_ratio or 0.7):
                rec.status = "at_risk"
            else:
                rec.status = "pending"
