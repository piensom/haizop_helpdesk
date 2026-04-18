from odoo import fields, models


class HelpdeskStage(models.Model):
    _name = "helpdesk.stage"
    _description = "Helpdesk Stage"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(
        string="Folded in Kanban",
        help="Tickets in a folded stage are hidden in the kanban view by default.",
    )
    is_close = fields.Boolean(
        string="Closing Stage",
        help="Tickets reaching this stage are considered closed (SLA stops, rating request fires).",
    )
    team_ids = fields.Many2many(
        "helpdesk.team",
        "helpdesk_stage_team_rel",
        "stage_id",
        "team_id",
        string="Teams",
    )
    description = fields.Text()
    template_id = fields.Many2one(
        "mail.template",
        string="Email Template",
        domain="[('model', '=', 'helpdesk.ticket')]",
        help="If set, this email is sent to the customer when a ticket reaches this stage.",
    )
