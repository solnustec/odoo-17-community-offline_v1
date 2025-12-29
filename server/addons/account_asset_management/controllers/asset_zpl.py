# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class AssetZPLController(http.Controller):

    @http.route('/asset/print_zpl/<int:asset_id>', type='http', auth='user')
    def print_zpl(self, asset_id):
        """Genera un archivo .zpl descargable para el activo"""
        asset = request.env['account.asset'].browse(asset_id)
        if not asset.exists():
            return request.not_found()

        # ZPL de 60x30 mm con nombre, código y QR
        zpl_code = f"""
^XA
^PW472
^LL236
^FO20,20^A0N,25,25^FD{asset.name or ''}^FS
^FO250,20^A0N,20,20^FD{asset.asset_code or ''}^FS
^FO20,60^BQN,2,5
^FDMA,{asset.qr_info or 'SIN_DATOS'}^FS
^XZ
"""

        return request.make_response(
            zpl_code,
            headers=[
                ('Content-Type', 'text/plain'),
                ('Content-Disposition', f'attachment; filename=asset_{asset_id}.zpl')
            ]
        )
