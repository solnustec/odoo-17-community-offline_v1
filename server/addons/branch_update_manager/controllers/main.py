# -*- coding: utf-8 -*-

import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class BranchUpdateController(http.Controller):
    """Controlador web para páginas y vistas del módulo."""

    @http.route('/branch_update/dashboard', type='http', auth='user', website=True)
    def dashboard(self, **kwargs):
        """Dashboard de actualizaciones."""
        branches = request.env['branch.registry'].search([])
        packages = request.env['branch.update.package'].search([
            ('state', 'in', ['ready', 'published'])
        ], limit=10, order='create_date desc')

        values = {
            'branches': branches,
            'packages': packages,
            'total_branches': len(branches),
            'active_branches': len(branches.filtered(lambda b: b.state == 'active')),
            'online_branches': len(branches.filtered(lambda b: b.is_online)),
        }

        return request.render('branch_update_manager.dashboard_template', values)
