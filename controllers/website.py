from odoo import _, http
from odoo.http import request


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
        return request.redirect(f"/helpdesk/{team.id}?submitted={ticket.number}")
