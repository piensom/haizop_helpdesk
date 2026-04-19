from datetime import timedelta

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
    unassigned_count = fields.Integer(compute="_compute_ticket_counts")
    today_created = fields.Integer(compute="_compute_ticket_counts")
    today_closed = fields.Integer(compute="_compute_ticket_counts")
    avg_resolution_hours = fields.Float(compute="_compute_ticket_counts", digits=(5, 1))
    sla_success_rate = fields.Integer(compute="_compute_ticket_counts",
        help="Percent of resolved SLAs that were reached on time (last 30 days).")

    @api.depends()
    def _compute_ticket_counts(self):
        Ticket = self.env["helpdesk.ticket"]
        Status = self.env["helpdesk.sla.status"]
        today = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        month_ago = fields.Datetime.now() - timedelta(days=30)
        for team in self:
            base = [("team_id", "=", team.id)]
            team.open_ticket_count = Ticket.search_count(base + [("is_closed", "=", False)])
            team.breach_count = Ticket.search_count(
                base + [("is_closed", "=", False), ("sla_status", "=", "breached")])
            team.at_risk_count = Ticket.search_count(
                base + [("is_closed", "=", False), ("sla_status", "=", "at_risk")])
            team.unassigned_count = Ticket.search_count(
                base + [("is_closed", "=", False), ("user_id", "=", False)])
            team.today_created = Ticket.search_count(base + [("create_date", ">=", today)])
            team.today_closed = Ticket.search_count(
                base + [("closed_date", ">=", today)])
            # avg resolution
            closed = Ticket.search(base + [
                ("is_closed", "=", True), ("closed_date", ">=", month_ago),
            ])
            if closed:
                total_hours = sum(
                    ((t.closed_date - t.create_date).total_seconds() / 3600.0)
                    for t in closed if t.closed_date and t.create_date
                )
                team.avg_resolution_hours = total_hours / len(closed)
            else:
                team.avg_resolution_hours = 0.0
            # SLA success rate (30d)
            done_statuses = Status.search([
                ("ticket_id.team_id", "=", team.id),
                ("reached_date", ">=", month_ago),
            ])
            if done_statuses:
                reached = len(done_statuses.filtered(lambda s: s.status == "reached"))
                team.sla_success_rate = int(round(100 * reached / len(done_statuses)))
            else:
                team.sla_success_rate = 100

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
