import base64
from collections import OrderedDict

from odoo import _, http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


ALLOWED_CLOSE_REASONS = {"solved", "duplicate", "no_response", "cannot_reproduce", "other"}


def _save_portal_attachments(files, ticket):
    if not files:
        return
    if not isinstance(files, list):
        files = [files]
    Attachment = request.env["ir.attachment"].sudo()
    max_size = 25 * 1024 * 1024
    for f in files:
        if not f or not getattr(f, "filename", None):
            continue
        data = f.read(max_size + 1)
        if len(data) > max_size:
            continue
        Attachment.create({
            "name": f.filename[:128],
            "datas": base64.b64encode(data),
            "res_model": "helpdesk.ticket",
            "res_id": ticket.id,
            "mimetype": (f.mimetype or "application/octet-stream").split(";", 1)[0],
        })


class HelpdeskCustomerPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "ticket_count" in counters:
            partner = request.env.user.partner_id
            values["ticket_count"] = request.env["helpdesk.ticket"].search_count([
                ("partner_id", "=", partner.id),
            ])
        return values

    @http.route(["/my/tickets", "/my/tickets/page/<int:page>"],
                type="http", auth="user", website=True)
    def portal_my_tickets(self, page=1, sortby=None, filterby=None, **kw):
        partner = request.env.user.partner_id
        Ticket = request.env["helpdesk.ticket"]
        domain = [("partner_id", "=", partner.id)]

        searchbar_sortings = {
            "date": {"label": _("Newest"), "order": "create_date desc"},
            "name": {"label": _("Subject"), "order": "name"},
            "stage": {"label": _("Status"), "order": "stage_id"},
        }
        sortby = sortby or "date"
        order = searchbar_sortings[sortby]["order"]

        searchbar_filters = {
            "all": {"label": _("All"), "domain": []},
            "open": {"label": _("Open"), "domain": [("is_closed", "=", False)]},
            "closed": {"label": _("Closed"), "domain": [("is_closed", "=", True)]},
        }
        filterby = filterby or "all"
        domain += searchbar_filters[filterby]["domain"]

        total = Ticket.search_count(domain)
        pager = portal_pager(
            url="/my/tickets",
            url_args={"sortby": sortby, "filterby": filterby},
            total=total, page=page, step=self._items_per_page,
        )
        tickets = Ticket.search(domain, order=order, limit=self._items_per_page, offset=pager["offset"])
        values = {
            "tickets": tickets,
            "page_name": "ticket",
            "pager": pager,
            "default_url": "/my/tickets",
            "searchbar_sortings": searchbar_sortings,
            "sortby": sortby,
            "searchbar_filters": OrderedDict(sorted(searchbar_filters.items())),
            "filterby": filterby,
        }
        return request.render("haizop_helpdesk.portal_my_tickets", values)

    @http.route(["/my/ticket/<int:ticket_id>"], type="http", auth="public", website=True)
    def portal_ticket_page(self, ticket_id, access_token=None, **kw):
        try:
            ticket_sudo = self._document_check_access("helpdesk.ticket", ticket_id, access_token)
        except (AccessError, MissingError):
            return request.redirect("/my")
        return request.render("haizop_helpdesk.portal_ticket_page", {
            "ticket": ticket_sudo,
            "page_name": "ticket",
        })

    @http.route(["/my/ticket/<int:ticket_id>/reply"], type="http", auth="user",
                website=True, methods=["POST"], csrf=True)
    def portal_ticket_reply(self, ticket_id, **post):
        ticket = request.env["helpdesk.ticket"].browse(ticket_id)
        if ticket.partner_id != request.env.user.partner_id:
            return request.redirect("/my/tickets")
        body = (post.get("body") or "").strip()
        if body:
            files = request.httprequest.files.getlist("attachments")
            attachment_ids = []
            if files:
                pre_ticket = ticket.sudo()
                _save_portal_attachments(files, pre_ticket)
                # take the attachments we just created (most recent for this ticket)
                recent = request.env["ir.attachment"].sudo().search([
                    ("res_model", "=", "helpdesk.ticket"),
                    ("res_id", "=", ticket.id),
                ], limit=len(files), order="create_date desc")
                attachment_ids = recent.ids
            ticket.message_post(
                body=body, message_type="comment", subtype_xmlid="mail.mt_comment",
                attachment_ids=attachment_ids,
            )
        return request.redirect(f"/my/ticket/{ticket.id}")

    @http.route(["/my/ticket/<int:ticket_id>/close"], type="http", auth="user",
                website=True, methods=["POST"], csrf=True)
    def portal_ticket_close(self, ticket_id, **post):
        ticket = request.env["helpdesk.ticket"].browse(ticket_id)
        if ticket.partner_id == request.env.user.partner_id:
            reason = post.get("reason") or "solved"
            if reason not in ALLOWED_CLOSE_REASONS:
                reason = "solved"
            ticket.action_close(reason=reason)
        return request.redirect(f"/my/ticket/{ticket.id}")

    @http.route(["/my/ticket/<int:ticket_id>/reopen"], type="http", auth="user",
                website=True, methods=["POST"], csrf=True)
    def portal_ticket_reopen(self, ticket_id, **post):
        ticket = request.env["helpdesk.ticket"].browse(ticket_id)
        if ticket.partner_id == request.env.user.partner_id:
            ticket.action_reopen()
        return request.redirect(f"/my/ticket/{ticket.id}")
