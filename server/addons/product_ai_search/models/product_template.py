# -*- coding: utf-8 -*-
from odoo import models, api, _
import logging

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        try:
            # Auto index somente se parâmetro auto_index estiver ativo
            IrConfig = self.env['ir.config_parameter'].sudo()
            auto_index = IrConfig.get_param('product_ai_search.auto_index', 'False') == 'True'
            if not auto_index:
                return records

            # Coleta IDs recém criados
            product_ids = records.ids
            if not product_ids:
                return records

            service = self.env['product.ai.search.service']
            # Usa domínio restrito aos novos IDs
            domain = [('id', 'in', product_ids)]
            # Batch pequeno para minimizar latência em criação unitária
            result = service.index_products(domain=domain, limit=len(product_ids), batch_size=min(len(product_ids), 10))
            if not result.get('success'):
                _logger.warning("Auto index falhou para produtos %s: %s", product_ids, result.get('message'))
            else:
                _logger.info("Auto index concluído: %s produtos indexados", result.get('indexed_products'))
        except Exception as e:
            # Nunca bloquear criação de produto por erro de indexação
            _logger.error("Erro em auto index de produto: %s", e)
        return records

    def unlink(self):
        # Captura IDs antes da remoção
        product_ids = self.ids[:]
        result = super().unlink()
        if not product_ids:
            return result
        try:
            service = self.env['product.ai.search.service']
            resp = service.delete_product_embeddings(product_ids)
            if not resp.get('success'):
                _logger.warning("Falha ao remover embeddings para produtos %s: %s", product_ids, resp.get('message'))
            else:
                _logger.info("Embeddings removidos para %d produtos (total docs deletados: %s)", len(product_ids), resp.get('deleted'))
        except Exception as e:
            _logger.error("Erro ao tentar remover embeddings (não bloqueante): %s", e)
        return result

    def write(self, vals):
        """Override para reindexar quando campos relevantes mudarem.

        Campos monitorados: name, default_code, categ_id, list_price, type, active, sale_ok
        Estratégia simples: após escrever, apaga embeddings antigos e reindexa somente os produtos afetados.
        Sempre não bloqueante: falhas de indexação não impedem a atualização normal do produto.
        """
        monitored_fields = {'name', 'default_code', 'categ_id', 'list_price', 'type', 'active', 'sale_ok'}
        should_reindex = any(f in vals for f in monitored_fields)

        result = super().write(vals)

        if not should_reindex or not self:
            return result

        try:
            # Verifica parâmetro global de auto index (reutiliza mesmo flag de criação)
            IrConfig = self.env['ir.config_parameter'].sudo()
            auto_index = IrConfig.get_param('product_ai_search.auto_index', 'False') == 'True'
            if not auto_index:
                return result

            product_ids = self.ids
            if not product_ids:
                return result

            service = self.env['product.ai.search.service']

            # Remove embeddings antigos
            del_resp = service.delete_product_embeddings(product_ids)
            if not del_resp.get('success'):
                _logger.warning("Falha ao excluir embeddings antes de reindexar produtos %s: %s", product_ids, del_resp.get('message'))

            # Reindexa somente estes produtos
            domain = [('id', 'in', product_ids)]
            idx_resp = service.index_products(domain=domain, limit=len(product_ids), batch_size=min(len(product_ids), 10))
            if not idx_resp.get('success'):
                _logger.warning("Reindex (write) falhou para produtos %s: %s", product_ids, idx_resp.get('message'))
            else:
                _logger.info("Reindex (write) concluído: %s produtos indexados", idx_resp.get('indexed_products'))
        except Exception as e:
            _logger.error("Erro em reindex após write (não bloqueante): %s", e)

        return result
