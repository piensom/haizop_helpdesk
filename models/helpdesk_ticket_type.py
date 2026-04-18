from odoo import fields, models


class HelpdeskTicketType(models.Model):
    _name = "helpdesk.ticket.type"
    _description = "Helpdesk Ticket Type"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
