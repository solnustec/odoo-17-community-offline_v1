# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ProductAISearchIndexer(models.TransientModel):
    """
    Wizard para indexação em massa de produtos
    """
    _name = 'product.ai.search.indexer'
    _description = 'Indexador em Massa para Busca IA de Produtos'

    # Configurações de indexação
    index_type = fields.Selection([
        ('all', 'Todos los Productos'),
        ('published', 'Solo Productos Publicados'),
        ('category', 'Por Categoría'),
        ('custom', 'Dominio Personalizado'),
    ], string='Tipo de Indexação', default='all', required=True)
    
    category_id = fields.Many2one(
        'product.category',
        string='Categoria',
        help='Categoria para filtrar productos (solo si tipo es "Por Categoría")'
    )
    
    custom_domain = fields.Text(
        string='Dominio Personalizado',
        placeholder="[('name', 'ilike', 'termo'), ('sale_ok', '=', True)]",
        help='Dominio de Odoo para filtrar productos'
    )
    
    max_products = fields.Integer(
        string='Máximo de Produtos',
        default=40000,
        help='Limitar número de produtos a indexar (0 = sem limite)'
    )
    
    batch_size = fields.Integer(
        string='Tamanho do Lote',
        default=50,
        help='Número de produtos processados por lote'
    )
    
    # Status da indexação
    indexation_started = fields.Boolean('Indexação Iniciada', default=False)
    indexation_completed = fields.Boolean('Indexação Completada', default=False)
    
    # Resultados
    total_found = fields.Integer('Produtos Encontrados', readonly=True)
    total_indexed = fields.Integer('Produtos Indexados', readonly=True) 
    total_failed = fields.Integer('Falhas', readonly=True)
    indexation_time = fields.Float('Tempo (segundos)', readonly=True)
    indexation_rate = fields.Float('Taxa (produtos/min)', readonly=True)
    
    # Log de progresso
    progress_log = fields.Text('Log de Progresso', readonly=True)
    error_details = fields.Text('Detalhes de Erros', readonly=True)

    @api.onchange('index_type')
    def _onchange_index_type(self):
        """Atualiza visibilidade de campos baseado no tipo"""
        if self.index_type != 'category':
            self.category_id = False
        if self.index_type != 'custom':
            self.custom_domain = ''

    def _get_domain_filter(self):
        """Retorna domínio baseado na configuração"""
        base_domain = [
            ('name', '!=', False),
        ]
        
        if self.index_type == 'all':
            return base_domain + [('sale_ok', '=', True)]
        
        elif self.index_type == 'published':
            # Tenta diferentes campos para produtos publicados
            ProductTemplate = self.env['product.template']
            if 'is_published' in ProductTemplate._fields:
                return base_domain + [('is_published', '=', True)]
            elif 'website_published' in ProductTemplate._fields:
                return base_domain + [('website_published', '=', True)]
            else:
                return base_domain + [('sale_ok', '=', True)]
        
        elif self.index_type == 'category':
            if not self.category_id:
                raise ValidationError(_("Selecione uma categoria"))
            return base_domain + [('categ_id', 'child_of', self.category_id.id)]
        
        elif self.index_type == 'custom':
            if not self.custom_domain:
                raise ValidationError(_("Insira um domínio personalizado"))
            try:
                import ast
                custom_filter = ast.literal_eval(self.custom_domain)
                return base_domain + custom_filter
            except Exception as e:
                raise ValidationError(_("Domínio personalizado inválido: %s") % str(e))
        
        return base_domain

    def action_preview_products(self):
        """Mostra preview dos produtos que serão indexados"""
        try:
            domain = self._get_domain_filter()
            limit = min(self.max_products, 20) if self.max_products > 0 else 20
            
            products = self.env['product.template'].search(domain, limit=limit)
            total_count = self.env['product.template'].search_count(domain)
            
            if not products:
                raise UserError(_("Nenhum produto encontrado com os filtros especificados"))
            
            # Atualiza contador
            self.total_found = total_count
            
            # Mostra lista de produtos
            product_names = [f"• {p.name} [{p.default_code or 'Sem código'}]" for p in products]
            if len(product_names) < total_count:
                product_names.append(f"... e mais {total_count - len(product_names)} produtos")
            
            preview_text = f"Total encontrado: {total_count} produtos\n\nPrimeiros produtos:\n" + "\n".join(product_names)
            self.progress_log = preview_text
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Preview da Indexação"),
                    'message': _("%d produtos serão indexados") % total_count,
                    'type': 'info',
                }
            }
            
        except Exception as e:
            raise UserError(_("Erro no preview: %s") % str(e))

    def action_start_indexation(self):
        """Inicia a indexação dos produtos"""
        try:
            # Validações
            if self.batch_size <= 0:
                raise ValidationError(_("Tamanho do lote deve ser maior que zero"))
            
            # Obtém domínio
            domain = self._get_domain_filter()
            limit = self.max_products if self.max_products > 0 else None
            
            # Marca como iniciado
            self.indexation_started = True
            self.indexation_completed = False
            self.progress_log = _("🔄 Iniciando indexação...\n")
            
            # Inicia processo via service
            service = self.env['product.ai.search.service']
            result = service.index_products(
                domain=domain,
                limit=limit,
                batch_size=self.batch_size
            )
            
            # Atualiza resultados
            self.total_found = result.get('total_products', 0)
            self.total_indexed = result.get('indexed_products', 0)
            self.total_failed = result.get('failed_products', 0)
            self.indexation_time = result.get('elapsed_time', 0)
            self.indexation_rate = result.get('rate_per_minute', 0)
            self.indexation_completed = True
            
            # Log final
            if result.get('success'):
                self.progress_log += f"\n✅ Indexação concluída com sucesso!\n"
                self.progress_log += f"• Produtos processados: {self.total_indexed}/{self.total_found}\n"
                self.progress_log += f"• Tempo total: {self.indexation_time:.1f} segundos\n"
                self.progress_log += f"• Taxa: {self.indexation_rate:.1f} produtos/minuto\n"
                self.progress_log += f"• Embeddings gerados com OpenAI\n"
                self.progress_log += f"• Armazenados no Elasticsearch\n"
                
                notification = {
                    'title': _("✅ Indexação Concluída"),
                    'message': _("%d produtos indexados com sucesso!") % self.total_indexed,
                    'type': 'success',
                }
            else:
                self.progress_log += f"\n❌ Falha na indexação: {result.get('message', 'Erro desconhecido')}\n"
                self.error_details = result.get('message', '')
                
                notification = {
                    'title': _("❌ Falha na Indexação"),
                    'message': result.get('message', 'Erro desconhecido'),
                    'type': 'danger',
                }
            
            # Retorna para atualizar a tela
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': notification
            }
            
        except Exception as e:
            self.indexation_completed = True
            self.error_details = str(e)
            self.progress_log += f"\n❌ Erro fatal: {str(e)}\n"
            
            raise UserError(_("Erro na indexação: %s") % str(e))

    def action_check_elasticsearch_status(self):
        """Verifica status do Elasticsearch"""
        try:
            service = self.env['product.ai.search.service']
            status = service.check_index_status()
            
            if status.get('exists'):
                if status.get('has_data'):
                    message = _("✅ Elasticsearch está funcionando e contém dados")
                    notification_type = 'success'
                else:
                    message = _("⚠️ Elasticsearch conectado mas índice está vazio")
                    notification_type = 'warning'
            else:
                message = _("❌ Problemas com Elasticsearch: %s") % status.get('error', 'Erro desconhecido')
                notification_type = 'danger'
            
            self.progress_log = f"Status do Elasticsearch:\n{message}\n\nDetalhes:\n{status}"
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Status do Elasticsearch"),
                    'message': message,
                    'type': notification_type,
                }
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Erro na Verificação"),
                    'message': str(e),
                    'type': 'danger',
                }
            }

    def action_reset(self):
        """Reseta o wizard"""
        self.write({
            'indexation_started': False,
            'indexation_completed': False,
            'total_found': 0,
            'total_indexed': 0,
            'total_failed': 0,
            'indexation_time': 0,
            'indexation_rate': 0,
            'progress_log': '',
            'error_details': '',
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Reset Concluído"),
                'message': _("Formulário reiniciado com sucesso"),
                'type': 'info',
            }
        }
