# -*- coding: utf-8 -*-
##################################################################################
#
#    Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#
#################################################################################

def pre_init_check(env):
	from odoo.service import common
	from odoo.exceptions import UserError
	version_info = common.exp_version()
	server_serie = version_info.get('server_serie')
	if not 16 < float(server_serie) <= 17:
		raise UserError(f'Module support Odoo series 17.0 found {server_serie}.')
	return True
