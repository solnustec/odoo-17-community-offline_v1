# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
{
    'name': "Stock Picking Double Approval | Delivery Double Approval | Receipt Double Approval",
    'version': "17.0.0.4",
    'category': "Warehouse",
    'summary': "Stock approvals stock double approvals stock Two step approval stock Dual approval stock double check delivery order approval double approval for delivery order approval receipt approval double approval for receipt double approval for transfer Double check",
    'description': """Stock Picking Double Approval Odoo App helps to enhance the control and security of stock movements. This app introduces a double approval workflow for deliveries, receipts, and internal transfers, ensuring that all critical stock transactions are authorized by multiple approvers before execution to prevent errors, and reduce the risk of fraud. Only allowed users can approve or reject stock transfer and can enter reason for rejection.""",
    'author': "BROWSEINFO",
    'website': "https://www.browseinfo.com/demo-request?app=bi_picking_double_approval&version=17&edition=Community",
    'price': 0,
    'currency': "EUR",
    'depends': ['base', 'stock'],
	'data': [
		'security/res_groups.xml',
		'security/ir.model.access.csv',
		'views/res_config_settings_view.xml',
		'views/stock_picking_view.xml',
		'wizard/picking_reject_view.xml',
	],
	"license": 'OPL-1',
    'auto_install': False,
    'installable': True,
}
