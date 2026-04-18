from odoo import api, fields, models


class HelpdeskTeam(models.Model):
    _name = "helpdesk.team"
    _description = "Helpdesk Team"
    _inherit = ["mail.thread", "mail.alias.mixin"]
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Html(translate=True)
    color = fields.Integer()
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, required=True,
    )

    # People
    member_ids = fields.Many2many("res.users", string="Members", domain=[("share", "=", False)])
    assignment_method = fields.Selection(
        [
            ("manual", "Manual"),
            ("random", "Random"),
            ("balanced", "Balanced (fewest open tickets)"),
        ],
        default="manual",
        required=True,
    )

    # Working hours
    resource_calendar_id = fields.Many2one(
        "resource.calendar",
        string="Working Hours",
        default=lambda self: self.env.company.resource_calendar_id,
        help="Used to compute SLA deadlines during business hours only.",
    )

    # Stages
    stage_ids = fields.Many2many(
        "helpdesk.stage",
        "helpdesk_stage_team_rel",
        "team_id",
        "stage_id",
        string="Stages",
    )

    # Channels
    use_alias = fields.Boolean(default=True, string="Email")
    use_website_form = fields.Boolean(default=True, string="Website Form")
    use_portal = fields.Boolean(default=True, string="Customer Portal")
    use_sla = fields.Boolean(default=True, string="SLA Policies")
    use_rating = fields.Boolean(default=True, string="Customer Ratings")
    use_similar_detection = fields.Boolean(default=True, string="Similar-Ticket Detection")
    use_ai_triage = fields.Boolean(default=False, string="AI Triage (Beta)")
    ai_provider = fields.Selection(
        [("anthropic", "Anthropic"), ("openai", "OpenAI"), ("ollama", "Local Ollama")],
        default="anthropic",
    )
    ai_endpoint = fields.Char(help="HTTP endpoint for the AI provider. Leave blank for default.")
    ai_api_key = fields.Char()

    # SLAs
    sla_ids = fields.One2many("helpdesk.sla", "team_id", string="SLA Policies")

    # Metrics (computed)
    open_ticket_count = fields.Integer(compute="_compute_ticket_counts")
    breach_count = fields.Integer(compute="_compute_ticket_counts")
    at_risk_count = fields.Integer(compute="_compute_ticket_counts")

    @api.depends()
    def _compute_ticket_counts(self):
        Ticket = self.env["helpdesk.ticket"]
        for team in self:
            team.open_ticket_count = Ticket.search_count([("team_id", "=", team.id), ("is_closed", "=", False)])
            team.breach_count = Ticket.search_count([
                ("team_id", "=", team.id),
                ("is_closed", "=", False),
                ("sla_status", "=", "breached"),
            ])
            team.at_risk_count = Ticket.search_count([
                ("team_id", "=", team.id),
                ("is_closed", "=", False),
                ("sla_status", "=", "at_risk"),
            ])

    # mail.alias.mixin
    def _alias_get_creation_values(self):
        values = super()._alias_get_creation_values()
        values["alias_model_id"] = self.env["ir.model"]._get("helpdesk.ticket").id
        if self.id:
            values["alias_defaults"] = {"team_id": self.id}
        return values

    @api.model_create_multi
    def create(self, vals_list):
        teams = super().create(vals_list)
        default_stages = self.env["helpdesk.stage"].search([("team_ids", "=", False)], limit=4)
        if not default_stages:
            default_stages = self.env["helpdesk.stage"].browse()
        for team in teams:
            if not team.stage_ids and default_stages:
                team.stage_ids = [(6, 0, default_stages.ids)]
        return teams

    def action_view_tickets(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name + " — Tickets",
            "res_model": "helpdesk.ticket",
            "view_mode": "kanban,list,form,pivot,graph",
            "domain": [("team_id", "=", self.id)],
            "context": {"default_team_id": self.id},
        }

    def _pick_assignee(self):
        self.ensure_one()
        members = self.member_ids
        if not members:
            return False
        if self.assignment_method == "random":
            import random
            return random.choice(members.ids)
        if self.assignment_method == "balanced":
            Ticket = self.env["helpdesk.ticket"]
            counts = {m.id: Ticket.search_count([
                ("team_id", "=", self.id),
                ("user_id", "=", m.id),
                ("is_closed", "=", False),
            ]) for m in members}
            return min(counts, key=counts.get)
        return False
