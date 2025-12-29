from odoo import http
from odoo.http import request


class ServerMonitorController(http.Controller):

    @http.route('/server_monitor/get_stats', type='json', auth='user')
    def get_stats(self):
        monitor = request.env['server.monitor']
        return monitor.get_server_stats()
