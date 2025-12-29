# -*- coding: utf-8 -*-
# Copyright 2009-2019 Noviat
# Copyright 2019 Tecnativa - Pedro M. Baeza
# Copyright 2021 Tecnativa - João Marques
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Assets Management",
    "version": "17.0.1.0.0",
    "license": "AGPL-3",
    "depends": [
        "account",
        "product",
    ],
    "development_status": "Mature",
    "external_dependencies": {
        "python": ["python-dateutil"]
    },
    "author": "Noviat, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/account-financial-tools",
    "category": "Accounting & Finance",
    "data": [
        # --- Seguridad y accesos ---
        "security/account_asset_security.xml",
        "security/ir.model.access.csv",

        # --- Data ---
        "data/asset_class_data.xml",
        "data/asset_subclass_data.xml",
        "data/asset_brand_data.xml",
        "data/cron.xml",

        # reportes primero
        "pdf_reports/report.xml",
        "pdf_reports/report_asset_transfer.xml",
        "pdf_reports/report_asset_mass_transfer.xml",
        "pdf_reports/report_asset_mass_transfer_template.xml",
        'pdf_reports/asset_custodian_report.xml',
        'pdf_reports/report_asset_custodian.xml',
        "pdf_reports/paperformat.xml",
        "pdf_reports/ir.actions.report.xml",

        # --- Vistas ---
        "views/account_account.xml",
        "views/account_asset.xml",
        "views/account_asset_group.xml",
        "views/account_asset_profile.xml",
        "views/account_move.xml",
        "views/account_move_line.xml",
        "views/employee_account.xml",
        "views/product_template_inherit.xml",
        "views/account_asset_views.xml",
        'views/asset_mass_assignment_views.xml',
        "views/account_asset_mass_transfer_view.xml",
        "views/hr_employee_views.xml",
        "views/report_asset_assign.xml",
        "views/report_transfers_assets.xml",
        # 'views/account_asset_zpl_views.xml',

        # --- Wizards ---
        "wizard/account_asset_compute.xml",
        "wizard/account_asset_remove.xml",
        "wizard/wiz_account_asset_report.xml",
        "wizard/wiz_asset_move_reverse.xml",
        "views/menuitem.xml",
        "views/reports_stickers_qr.xml",

    ],
    "installable": True,
    "application": False,
}
