import base64
import logging
from html import escape as _h

from markupsafe import Markup

from odoo import _, http
from odoo.http import request

_logger = logging.getLogger(__name__)


def _save_attachments(files, ticket):
    """Attach uploaded files to a ticket as ir.attachment."""
    if not files:
        return
    if not isinstance(files, list):
        files = [files]
    Attachment = request.env["ir.attachment"].sudo()
    max_size = 25 * 1024 * 1024  # 25 MB
    allowed = {
        "image/png", "image/jpeg", "image/gif", "image/webp",
        "application/pdf", "application/zip",
        "text/plain", "text/csv",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    }
    for f in files:
        if not f or not getattr(f, "filename", None):
            continue
        data = f.read(max_size + 1)
        if len(data) > max_size:
            continue  # silently drop oversize files; ticket still created
        mime = (f.mimetype or "application/octet-stream").split(";", 1)[0]
        if mime not in allowed:
            continue
        Attachment.create({
            "name": f.filename[:128],
            "datas": base64.b64encode(data),
            "res_model": "helpdesk.ticket",
            "res_id": ticket.id,
            "mimetype": mime,
        })


class HelpdeskWebsite(http.Controller):

    @http.route(["/helpdesk", "/helpdesk/<int:team_id>"],
                type="http", auth="public", website=True, sitemap=True)
    def website_helpdesk_index(self, team_id=None, **kw):
        teams = request.env["helpdesk.team"].sudo().search([("use_website_form", "=", True)])
        team = request.env["helpdesk.team"].sudo().browse(team_id).exists() if team_id else False
        if not team and teams:
            team = teams[0]
        similar = []
        q = (kw.get("q") or "").strip()
        if q and team:
            similar = request.env["helpdesk.ticket"].sudo().search([
                ("team_id", "=", team.id),
                ("name", "ilike", q),
            ], limit=5)
        return request.render("haizop_helpdesk.website_helpdesk_team", {
            "team": team, "teams": teams, "q": q, "similar": similar,
            "submitted": kw.get("submitted"),
        })

    @http.route(["/helpdesk/<int:team_id>/submit"],
                type="http", auth="public", website=True, methods=["POST"], csrf=True)
    def website_helpdesk_submit(self, team_id, **post):
        team = request.env["helpdesk.team"].sudo().browse(team_id).exists()
        if not team:
            return request.redirect("/helpdesk")
        name = (post.get("name") or "").strip()
        email = (post.get("email") or "").strip()
        subject = (post.get("subject") or "").strip()
        description = (post.get("description") or "").strip()
        priority = post.get("priority") or "2"
        if not (name and email and subject and description):
            return request.redirect(f"/helpdesk/{team.id}?error=missing")

        ticket = request.env["helpdesk.ticket"].sudo().create({
            "name": subject,
            "description": description,
            "partner_name": name,
            "email_from": email,
            "team_id": team.id,
            "priority": priority,
            "channel": "web",
        })

        # attachments
        files = request.httprequest.files.getlist("attachments") if hasattr(request, "httprequest") else []
        _save_attachments(files, ticket)

        # auto-acknowledgement email
        template = request.env.ref("haizop_helpdesk.mail_template_ticket_ack", raise_if_not_found=False)
        if template:
            try:
                template.sudo().send_mail(ticket.id, force_send=True,
                                          email_values={"email_to": email})
                _logger.info("Helpdesk ack queued for ticket %s to %s", ticket.number, email)
            except Exception:  # noqa: BLE001
                _logger.exception("Helpdesk ack email FAILED for ticket %s -> %s",
                                  ticket.number, email)

        # Notify all helpdesk team members by email
        try:
            members = team.member_ids
            partner_ids = members.mapped("partner_id").ids
            if partner_ids:
                priority_labels = dict(ticket._fields["priority"].selection)
                body = Markup(
                    '<p><strong>Neues Support-Ticket</strong> — <code>{number}</code></p>'
                    '<ul>'
                    '<li>Betreff: {subject}</li>'
                    '<li>Priorität: {priority}</li>'
                    '<li>Name: {name}</li>'
                    '<li>E-Mail: {email}</li>'
                    '</ul>'
                    '<p>Beschreibung:</p>'
                    '<blockquote style="border-left:3px solid #0284c7;padding-left:10px;color:#475569;">'
                    '{description}'
                    '</blockquote>'
                ).format(
                    number=_h(ticket.number),
                    subject=_h(subject),
                    priority=_h(priority_labels.get(priority, priority)),
                    name=_h(name),
                    email=_h(email),
                    description=_h(description),
                )
                ticket.sudo().message_subscribe(partner_ids=partner_ids)
                # Post as OdooBot so every team member (not just the "author")
                # receives the notification email.
                bot = request.env.ref("base.partner_root",
                                      raise_if_not_found=False)
                ticket.sudo().message_post(
                    body=body,
                    subject=f"[{ticket.number}] {subject}",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                    partner_ids=partner_ids,
                    author_id=bot.id if bot else False,
                )
                _logger.info("Ticket %s notified %s team members", ticket.number, len(partner_ids))
        except Exception:  # noqa: BLE001
            _logger.exception("Team notification FAILED for ticket %s", ticket.number)

        return request.redirect(f"/helpdesk/{team.id}?submitted={ticket.number}")

    # ---------- Public tracking ----------
    @http.route(["/helpdesk/track"], type="http", auth="public", website=True, sitemap=False)
    def track_form(self, number=None, email=None, **kw):
        if not (number and email):
            return request.render("haizop_helpdesk.public_track_form", {
                "number": number, "email": email, "error": None,
            })
        Ticket = request.env["helpdesk.ticket"].sudo()
        ticket = Ticket.search([
            ("number", "=", number.strip()),
            ("email_from", "=ilike", email.strip()),
        ], limit=1)
        if not ticket:
            return request.render("haizop_helpdesk.public_track_form", {
                "number": number, "email": email,
                "error": _("No ticket matches that number + e-mail combination."),
            })
        return request.render("haizop_helpdesk.public_track_result", {"ticket": ticket})
