import json
import logging
from datetime import timedelta

from odoo import _, api, exceptions, fields, models
from odoo.tools import email_normalize

_logger = logging.getLogger(__name__)


class HelpdeskTicket(models.Model):
    _name = "helpdesk.ticket"
    _description = "Helpdesk Ticket"
    _inherit = ["mail.thread.cc", "mail.activity.mixin", "portal.mixin", "rating.mixin"]
    _order = "priority desc, create_date desc"
    _primary_email = "email_from"
    _mail_post_access = "read"

    # --- Identity ---
    name = fields.Char(string="Subject", required=True, tracking=True)
    number = fields.Char(
        string="Ticket #", copy=False, readonly=True, default=lambda s: _("New"), index=True,
    )
    active = fields.Boolean(default=True)
    color = fields.Integer()

    # --- Customer ---
    partner_id = fields.Many2one("res.partner", string="Customer", tracking=True, index=True)
    partner_name = fields.Char(string="Customer Name")
    email_from = fields.Char(string="Email", tracking=True, index=True)
    phone = fields.Char()

    # --- Team / routing ---
    team_id = fields.Many2one("helpdesk.team", required=True, tracking=True, index=True)
    user_id = fields.Many2one(
        "res.users", string="Assigned to", tracking=True, index=True,
        domain="[('share', '=', False)]",
    )
    stage_id = fields.Many2one(
        "helpdesk.stage", tracking=True, index=True, group_expand="_read_group_stage_ids",
        domain="[('team_ids', '=', team_id)]",
    )
    kanban_state = fields.Selection(
        [("normal", "In Progress"), ("done", "Ready"), ("blocked", "Blocked")],
        default="normal", tracking=True,
    )
    priority = fields.Selection(
        [("1", "Low"), ("2", "Normal"), ("3", "High"), ("4", "Urgent")],
        default="2", tracking=True,
    )
    ticket_type_id = fields.Many2one("helpdesk.ticket.type", string="Type")
    tag_ids = fields.Many2many("helpdesk.tag", string="Tags")
    channel = fields.Selection(
        [("web", "Website"), ("email", "Email"), ("portal", "Portal"),
         ("backend", "Backend"), ("api", "API")],
        default="backend", readonly=True,
    )

    # --- Content ---
    description = fields.Html(sanitize=True)

    # --- Lifecycle ---
    is_closed = fields.Boolean(related="stage_id.is_close", store=True, index=True)
    closed_date = fields.Datetime(tracking=True, readonly=True)
    close_reason = fields.Selection(
        [("solved", "Solved"), ("duplicate", "Duplicate"), ("no_response", "No Response"),
         ("cannot_reproduce", "Cannot Reproduce"), ("other", "Other")],
        tracking=True,
    )
    first_response_date = fields.Datetime(readonly=True)

    # --- SLA ---
    sla_status_ids = fields.One2many("helpdesk.sla.status", "ticket_id", string="SLA Status")
    sla_status = fields.Selection(
        [("pending", "On Track"), ("at_risk", "At Risk"), ("reached", "Reached"), ("breached", "Breached")],
        compute="_compute_sla_status", store=True, index=True,
    )
    sla_deadline = fields.Datetime(compute="_compute_sla_status", store=True, index=True)

    # --- Merge ---
    merged_into_id = fields.Many2one("helpdesk.ticket", string="Merged Into", readonly=True)

    # --- Rating ---
    rating_last_value = fields.Float(related="rating_ids.rating", store=False)

    # --- Dupes / similar ---
    similar_ticket_ids = fields.Many2many(
        "helpdesk.ticket", "helpdesk_ticket_similar_rel", "src", "dst",
        compute="_compute_similar", string="Similar Tickets",
    )

    # ---------- Defaults ----------
    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if "team_id" in fields_list and not vals.get("team_id"):
            team = self.env["helpdesk.team"].search([], limit=1)
            if team:
                vals["team_id"] = team.id
        return vals

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        team_id = self.env.context.get("default_team_id")
        if team_id:
            return stages.search([("team_ids", "in", team_id)], order="sequence")
        return stages.search([], order="sequence")

    # ---------- Create / Write ----------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("number") or vals["number"] == _("New"):
                vals["number"] = self.env["ir.sequence"].next_by_code("helpdesk.ticket") or "/"
            # auto-link partner by email
            if vals.get("email_from") and not vals.get("partner_id"):
                email = email_normalize(vals["email_from"])
                if email:
                    partner = self.env["res.partner"].search([("email_normalized", "=", email)], limit=1)
                    if partner:
                        vals["partner_id"] = partner.id
            # default stage
            if not vals.get("stage_id") and vals.get("team_id"):
                team = self.env["helpdesk.team"].browse(vals["team_id"])
                first = team.stage_ids.sorted("sequence")[:1]
                if first:
                    vals["stage_id"] = first.id
            # auto-assign
            if not vals.get("user_id") and vals.get("team_id"):
                team = self.env["helpdesk.team"].browse(vals["team_id"])
                pick = team._pick_assignee()
                if pick:
                    vals["user_id"] = pick
        tickets = super().create(vals_list)
        tickets._apply_slas()
        tickets._dispatch_webhook("ticket.create")
        return tickets

    def write(self, vals):
        track_first_response = "message_ids" in vals
        stage_change = "stage_id" in vals
        res = super().write(vals)
        if stage_change:
            for t in self:
                if t.is_closed and not t.closed_date:
                    t.closed_date = fields.Datetime.now()
                    # stop all open SLAs
                    open_sla = t.sla_status_ids.filtered(lambda s: not s.reached_date)
                    open_sla.write({"reached_date": fields.Datetime.now()})
                    if t.team_id.use_rating:
                        t._send_rating_request()
                if not t.is_closed and t.closed_date:
                    t.closed_date = False
                # mark resolution SLA reached if target stage
                for s in t.sla_status_ids.filtered(lambda s: s.target_type == "resolution" and not s.reached_date):
                    target = s.sla_id.stage_id or t.team_id.stage_ids.filtered("is_close")[:1]
                    if target and t.stage_id == target:
                        s.reached_date = fields.Datetime.now()
            self._dispatch_webhook("ticket.stage_change")
        if "user_id" in vals:
            self._dispatch_webhook("ticket.assign")
        if track_first_response:
            for t in self:
                if not t.first_response_date and t._has_human_reply():
                    t.first_response_date = fields.Datetime.now()
                    for s in t.sla_status_ids.filtered(
                        lambda s: s.target_type == "first_response" and not s.reached_date
                    ):
                        s.reached_date = t.first_response_date
        return res

    # ---------- SLA ----------
    @api.depends("sla_status_ids.status", "sla_status_ids.deadline")
    def _compute_sla_status(self):
        order = {"breached": 3, "at_risk": 2, "pending": 1, "reached": 0}
        for t in self:
            statuses = t.sla_status_ids.filtered(lambda s: not s.reached_date)
            if not statuses:
                t.sla_status = "reached" if t.sla_status_ids else False
                t.sla_deadline = False
            else:
                worst = max(statuses, key=lambda s: order.get(s.status, 0))
                t.sla_status = worst.status
                t.sla_deadline = min(statuses.mapped("deadline"))

    def _apply_slas(self):
        SLA = self.env["helpdesk.sla"]
        Status = self.env["helpdesk.sla.status"]
        for t in self:
            if not t.team_id.use_sla or t.is_closed:
                continue
            applicable = SLA.search([
                ("team_id", "=", t.team_id.id),
                ("active", "=", True),
                "|", ("priority", "=", "0"), ("priority", "=", t.priority),
                "|", ("ticket_type_id", "=", False), ("ticket_type_id", "=", t.ticket_type_id.id),
            ])
            applicable = applicable.filtered(
                lambda s: (not s.tag_ids or (s.tag_ids & t.tag_ids))
                and (not s.partner_ids or t.partner_id in s.partner_ids)
            )
            existing_ids = set(t.sla_status_ids.mapped("sla_id").ids)
            for sla in applicable:
                if sla.id in existing_ids:
                    continue
                deadline = self._compute_deadline(t.create_date or fields.Datetime.now(), sla)
                Status.create({"ticket_id": t.id, "sla_id": sla.id, "deadline": deadline})

    def _compute_deadline(self, start, sla):
        cal = self.team_id.resource_calendar_id
        if cal:
            try:
                return cal.plan_hours(sla.time_hours, start, compute_leaves=True)
            except Exception:
                pass
        return start + timedelta(hours=sla.time_hours)

    def _has_human_reply(self):
        self.ensure_one()
        for msg in self.message_ids:
            if msg.message_type == "comment" and msg.author_id and msg.author_id != self.partner_id:
                return True
        return False

    # ---------- Similar tickets ----------
    @api.depends("name", "description", "team_id")
    def _compute_similar(self):
        for t in self:
            if not t.name or not t.team_id.use_similar_detection:
                t.similar_ticket_ids = False
                continue
            terms = [w for w in t.name.split() if len(w) > 3][:5]
            if not terms:
                t.similar_ticket_ids = False
                continue
            domain = [("id", "!=", t.id or 0), ("team_id", "=", t.team_id.id)]
            domain += ["|"] * (len(terms) - 1)
            for w in terms:
                domain.append(("name", "ilike", w))
            t.similar_ticket_ids = self.search(domain, limit=5)

    # ---------- Rating ----------
    def _send_rating_request(self):
        template = self.env.ref("haizop_helpdesk.mail_template_rating_request", raise_if_not_found=False)
        for t in self:
            if not t.partner_id and not t.email_from:
                continue
            if template:
                template.send_mail(t.id, force_send=False)

    def _rating_get_parent_field_name(self):
        return "team_id"

    # ---------- Merge ----------
    def action_merge_into(self, target_id):
        target = self.browse(target_id)
        if not target.exists():
            raise exceptions.UserError(_("Target ticket not found."))
        others = self - target
        if not others:
            return
        body = _("Merged tickets: %s") % ", ".join(others.mapped("number"))
        target.message_post(body=body)
        # Fold tags, keep target's other fields
        tags = (target.tag_ids | others.mapped("tag_ids"))
        target.tag_ids = [(6, 0, tags.ids)]
        # Move messages
        self.env["mail.message"].search([("model", "=", self._name), ("res_id", "in", others.ids)]).write({
            "res_id": target.id,
        })
        others.write({
            "merged_into_id": target.id,
            "active": False,
            "stage_id": target.team_id.stage_ids.filtered("is_close")[:1].id or target.stage_id.id,
            "close_reason": "duplicate",
        })
        return target

    # ---------- Close ----------
    def action_close(self, reason="solved"):
        closing = self.team_id.stage_ids.filtered("is_close")[:1] or self.env.ref(
            "haizop_helpdesk.stage_solved", raise_if_not_found=False
        )
        for t in self:
            stage = t.team_id.stage_ids.filtered("is_close")[:1]
            if stage:
                t.stage_id = stage
            t.close_reason = reason

    def action_reopen(self):
        for t in self:
            open_stage = t.team_id.stage_ids.filtered(lambda s: not s.is_close).sorted("sequence")[:1]
            if open_stage:
                t.stage_id = open_stage
                t.close_reason = False
                t.closed_date = False

    # ---------- Webhooks ----------
    def _dispatch_webhook(self, event):
        hooks = self.env["helpdesk.webhook"].sudo().search([
            ("active", "=", True), ("event_ids.code", "=", event),
        ])
        if not hooks:
            return
        import urllib.request
        for hook in hooks:
            for t in self:
                if hook.team_id and hook.team_id != t.team_id:
                    continue
                payload = json.dumps({
                    "event": event,
                    "id": t.id,
                    "number": t.number,
                    "name": t.name,
                    "team": t.team_id.name,
                    "stage": t.stage_id.name,
                    "priority": t.priority,
                    "assignee": t.user_id.login if t.user_id else None,
                    "partner": t.partner_id.display_name if t.partner_id else t.email_from,
                    "sla_status": t.sla_status,
                }).encode()
                req = urllib.request.Request(hook.url, data=payload, method="POST")
                req.add_header("Content-Type", "application/json")
                if hook.secret:
                    req.add_header("X-Haizop-Secret", hook.secret)
                try:
                    urllib.request.urlopen(req, timeout=5).read()
                except Exception as e:  # noqa: BLE001
                    _logger.warning("Webhook %s failed: %s", hook.url, e)

    # ---------- Portal ----------
    def _compute_access_url(self):
        super()._compute_access_url()
        for t in self:
            t.access_url = f"/my/ticket/{t.id}"

    # ---------- Mail gateway ----------
    def message_post(self, **kwargs):
        # Always prefix subject with [HDxxxxx] so Outlook/Gmail thread correctly
        # and the recipient sees the ticket number instead of a raw subject.
        if self and not kwargs.get("subject"):
            self.ensure_one()
            number = self.number or _("New")
            kwargs["subject"] = f"[{number}] {self.name or _('Ticket')}"
        elif self and kwargs.get("subject") and self.number and f"[{self.number}]" not in (kwargs["subject"] or ""):
            kwargs["subject"] = f"[{self.number}] {kwargs['subject']}"
        msg = super().message_post(**kwargs)
        try:
            if kwargs.get("message_type") == "comment" and msg.author_id and msg.author_id != self.partner_id:
                for t in self:
                    if not t.first_response_date:
                        t.first_response_date = fields.Datetime.now()
                        for s in t.sla_status_ids.filtered(
                            lambda s: s.target_type == "first_response" and not s.reached_date
                        ):
                            s.reached_date = t.first_response_date
        except Exception:  # noqa: BLE001
            _logger.exception("First-response SLA hook failed")
        return msg

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        defaults = dict(custom_values or {})
        defaults.setdefault("channel", "email")
        defaults.setdefault("name", msg_dict.get("subject") or _("Email"))
        defaults.setdefault("email_from", msg_dict.get("email_from"))
        defaults.setdefault("description", msg_dict.get("body") or "")
        return super().message_new(msg_dict, defaults)

    # ---------- Cron: SLA sweep ----------
    @api.model
    def _cron_sla_sweep(self):
        # recompute status + breach-predict notifications
        open_tickets = self.search([("is_closed", "=", False)])
        open_tickets._apply_slas()
        for t in open_tickets:
            t.sla_status_ids._compute_status()
