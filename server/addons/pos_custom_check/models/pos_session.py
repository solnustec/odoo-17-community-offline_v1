# -*- coding: utf-8 -*-

from odoo import  models



class PosSession(models.Model):
    _inherit = 'pos.session'

    def _loader_params_pos_payment_method(self):
        result = super()._loader_params_pos_payment_method()
        result['search_params']['fields'].append('allow_check_info')
        result['search_params']['fields'].append('code_payment_method')
        return result

    def _get_pos_ui_pos_res_banks(self, params):
        banks = self.env['res.bank'].search_read(**params['search_params'])
        return banks

    def load_pos_data(self):
        loaded_data = {}
        self = self.with_context(loaded_data=loaded_data)
        excluded_models = ['loyalty.program', 'loyalty.rule', 'loyalty.reward']

        for model in self._pos_ui_models_to_load():
            if model in excluded_models:
                continue
            loaded_data[model] = self._load_model(model)

        self._pos_data_process(loaded_data)
        bank_data = self._get_pos_ui_pos_res_banks(self._loader_params_pos_res_banks())
        loaded_data['banks'] = bank_data
        return loaded_data

    def _get_pos_ui_product_product(self, params):
        self = self.with_context(**params['context'])
        products = self.config_id.get_limited_products_loading(params['search_params']['fields'])

        self._process_pos_ui_product_product(products)
        return products

    def _loader_params_pos_res_banks(self):
        return {
            'search_params': {
                'domain': [],
                'fields': [],
            },
        }

    def _loader_params_res_partner(self):
        return {
            'search_params': {
                'domain': self._get_partners_domain(),
                'fields': [
                    'name', 'street', 'city', 'state_id', 'country_id', 'vat', 'lang', 'phone', 'zip', 'mobile', 'email',
                    'barcode', 'write_date', 'property_account_position_id', 'property_product_pricelist', 'parent_name'
                ],
            },
        }

    def _loader_params_res_partner(self):
        res = super()._loader_params_res_partner()
        res.get("search_params").get("fields").extend([
            'institution_ids',
            'id_database_old',
            'supplier_rank',
            'type',
            'has_discount_institution',
            'has_credit_institution'
        ])
        return res

    def _get_pos_ui_res_partner(self, params):
        params['search_params']['domain'] = [('id', '=', 0)]
        return self.env['res.partner'].search_read(**params['search_params'])


