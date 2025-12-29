from odoo import models, fields, api

class WhatsappQuickReply(models.Model):
    _name = "whatsapp.quick_reply"
    _description = "WhatsApp Quick Reply"
    _order = "sequence, shortcut"
    _rec_name = "shortcut"

    shortcut = fields.Char(required=True, index=True, help="Atajo sin espacios, p.ej. 'saludo'")
    message = fields.Text(required=True, help="Mensaje que se insertará en el input")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("shortcut_unique", "unique(shortcut)", "El atajo ya existe.")
    ]

    @api.model
    def search_suggestions(self, query="", limit=10):
        """
        Devuelve sugerencias por shortcut o texto, ignorando mayúsculas.
        Soporta que 'query' venga con '/' al inicio.
        """
        q = (query or "").strip()
        if q.startswith("/"):
            q = q[1:]
        domain = [("active", "=", True)]
        if q:
            domain = ["|", ("shortcut", "ilike", q), ("message", "ilike", q)] + domain
        records = self.sudo().search(domain, limit=limit)
        return [
            {"id": r.id, "shortcut": r.shortcut, "message": r.message}
            for r in records
        ]