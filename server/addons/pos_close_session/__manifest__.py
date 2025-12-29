# -*- coding: utf-8 -*-
{
    "name": "Cierre de sesión POS",
    "summary": "Módulo para generar y descargar reportes de cierre de caja en POS",
    "description": """
Módulo para procesar sesiones de punto de venta y descargar reportes de cierre de caja automáticos. ff
    """,
    "author": "Solnus, Novacode",
    "website": "https://www.yourcompany.com",
    "category": "Point of Sale",
    "version": "0.1",
    "depends": ["base", "point_of_sale"],
    "data": [
        "security/ir.model.access.csv",
        "reports/report_cash_summary.xml",
        "views/view_ticket_close_session.xml",
        "views/menu_ticket_user.xml",
    ],
    "assets": {
        "point_of_sale.assets": [
            "/pos_close_session/static/src/js/money_details_filter.js"
        ],
        "point_of_sale._assets_pos": [
            "/pos_close_session/static/src/*/*.js",
            "/pos_close_session/static/src/*/*.xml",
        ],
        "web.assets_backend": [
            "/pos_close_session/static/src/js/user_menu_logout_clear.js",
        ],
    },
    "license": "GPL-3",
    "installable": True,
    "auto_install": False,
    "application": False,
}  # type: ignore
