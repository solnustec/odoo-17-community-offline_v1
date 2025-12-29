# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProductAISearchConfig(models.TransientModel):
    """
    Configuração do módulo Product AI Search
    """
    _name = 'product.ai.search.config'
    _description = 'Configuração de Búsqueda IA para Produtos'

    # Configuração apenas para Elasticsearch
    vector_store_type = fields.Selection([
        ('elasticsearch', 'Elasticsearch'),
    ], string='Tipo de Vector Store', required=True,
       help='Vector store utilizado para almacenar embeddings')

    # Configuração pré-definida
    config_preset = fields.Selection([
        ('custom', 'Configuración Personalizada'),
        ('local', 'Elasticsearch Local'),
        ('cloud', 'Elasticsearch Cloud'),
    ], string='Configuración Predefinida',
       help='Use configuraciones predefinidas para facilitar la configuración')

    # Configuração de Elasticsearch
    elasticsearch_url = fields.Char(
        string='URL de Elasticsearch',
        help='URL completa del servidor Elasticsearch'
    )
    elasticsearch_index = fields.Char(
        string='Nombre del Índice ES',
        help='Nombre del índice en Elasticsearch'
    )
    elasticsearch_strategy = fields.Selection([
        ('dense', 'Vector Denso'),
        ('hybrid', 'Híbrido (Denso + BM25)'),
    ], string='Estrategia ES')
    
    # Configuração de autenticação Elasticsearch
    elasticsearch_auth_type = fields.Selection([
        ('none', 'Sin Autenticación'),
        ('basic', 'Usuario/Contraseña'),
        ('api_key', 'API Key'),
    ], string='Tipo de Autenticación',
       help='Tipo de autenticación para Elasticsearch')
    
    elasticsearch_username = fields.Char(
        string='Usuario ES',
        help='Usuario para autenticación básica'
    )
    elasticsearch_password = fields.Char(
        string='Contraseña ES',
        help='Contraseña para autenticación básica'
    )
    elasticsearch_api_key = fields.Char(
        string='API Key ES',
        help='API Key para Elasticsearch Cloud'
    )
    elasticsearch_verify_certs = fields.Boolean(
        string='Verificar Certificados',
        help='Verificar certificados SSL para conexiones HTTPS'
    )

    # Configuração de OpenAI
    openai_api_key = fields.Char(
        string='Clave API OpenAI',
        required=True,
        help='Clave de la API de OpenAI para generación de embeddings'
    )

    # Configuração de Indexación
    batch_size = fields.Integer(
        string='Tamaño del Lote',
        help='Número de productos procesados por lote'
    )
    auto_index = fields.Boolean(
        string='Indexación Automática',
        help='Indexar automáticamente cuando los productos son creados/actualizados'
    )

    @api.model
    def default_get(self, fields_list):
        """Carrega valores salvos dos parâmetros do sistema"""
        res = super().default_get(fields_list)
        
        # Carrega parâmetros do banco de dados
        IrConfigParameter = self.env['ir.config_parameter'].sudo()
        
        def get_param(key, default_value=''):
            value = IrConfigParameter.get_param(f'product_ai_search.{key}', default_value)
            return value
        
        # Carrega TODOS os valores salvos
        saved_values = {
            'vector_store_type': get_param('vector_store_type', 'elasticsearch'),
            'config_preset': get_param('config_preset', 'custom'),
            'elasticsearch_url': get_param('elasticsearch_url', 'http://elasticsearch:9200'),
            'elasticsearch_index': get_param('elasticsearch_index', 'products_odoo_ai'),
            'elasticsearch_strategy': get_param('elasticsearch_strategy', 'dense'),
            'elasticsearch_auth_type': get_param('elasticsearch_auth_type', 'none'),
            'elasticsearch_username': get_param('elasticsearch_username', ''),
            'elasticsearch_password': get_param('elasticsearch_password', ''),
            'elasticsearch_api_key': get_param('elasticsearch_api_key', ''),
            'elasticsearch_verify_certs': get_param('elasticsearch_verify_certs', 'True') == 'True',
            'openai_api_key': get_param('openai_api_key', ''),
            'batch_size': int(get_param('batch_size', '50') or '50'),
            'auto_index': get_param('auto_index', 'False') == 'True',
        }
        
        # Atualiza apenas os campos solicitados (ou todos se fields_list estiver vazio)
        if fields_list:
            saved_values = {k: v for k, v in saved_values.items() if k in fields_list}
        
        # Sobrescreve os valores padrão com os valores salvos
        res.update(saved_values)
        
        return res

    @api.model
    def get_current_config(self):
        """Obtém configuração atual diretamente do banco de dados"""
        IrConfigParameter = self.env['ir.config_parameter'].sudo()
        
        def get_param(key, default_value=''):
            return IrConfigParameter.get_param(f'product_ai_search.{key}', default_value)
        
        current_config = {
            'elasticsearch_url': get_param('elasticsearch_url', 'http://elasticsearch:9200'),
            'elasticsearch_index': get_param('elasticsearch_index', 'products_odoo_ai'),
            'elasticsearch_api_key': get_param('elasticsearch_api_key', ''),
            'openai_api_key': get_param('openai_api_key', ''),
            'batch_size': int(get_param('batch_size', '50') or '50'),
        }
        
        return current_config


    def reset_to_defaults(self):
        """Restaura los valores por defecto"""
        set_param = self.env['ir.config_parameter'].sudo().set_param
        
        # Valores por defecto
        defaults = {
            'vector_store_type': 'elasticsearch',
            'config_preset': 'custom',
            'elasticsearch_url': 'http://elasticsearch:9200',
            'elasticsearch_index': 'products_odoo_ai',
            'elasticsearch_strategy': 'dense',
            'elasticsearch_auth_type': 'none',
            'elasticsearch_username': '',
            'elasticsearch_password': '',
            'elasticsearch_api_key': '',
            'elasticsearch_verify_certs': 'True',
            'openai_api_key': '',
            'batch_size': '50',
            'auto_index': 'False',
        }
        
        for key, value in defaults.items():
            set_param(f'product_ai_search.{key}', value)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("🔄 Configuración Restaurada"),
                'message': _("Se restauraron los valores por defecto. ¡Recarga la página para ver los cambios!"),
                'type': 'info',
                'sticky': False,
            }
        }

    def save_config(self):
        """Guarda configurações no banco de dados usando ir.config_parameter"""
        self.ensure_one()
        
        # Validações gerais
        if not self.openai_api_key or self.openai_api_key.strip() == '':
            raise ValidationError(_("La clave de la API de OpenAI es obligatoria"))
        
        if not self.openai_api_key.startswith('sk-'):
            raise ValidationError(_("La clave de la API de OpenAI debe comenzar con 'sk-'"))
        
        if self.batch_size <= 0:
            raise ValidationError(_("El tamaño del lote debe ser mayor que cero"))
        
        # Validações específicas para Elasticsearch
        if not self.elasticsearch_url or not self.elasticsearch_url.startswith('http'):
            raise ValidationError(_("La URL de Elasticsearch debe ser válida (ej: http://localhost:9200)"))
        if not self.elasticsearch_index or self.elasticsearch_index.strip() == '':
            raise ValidationError(_("El nombre del índice de Elasticsearch es obligatorio"))
        
        # Validações de autenticação
        if self.elasticsearch_auth_type == 'basic':
            if not self.elasticsearch_username or not self.elasticsearch_password:
                raise ValidationError(_("Usuario y contraseña son obligatorios para autenticación básica"))
        elif self.elasticsearch_auth_type == 'api_key':
            if not self.elasticsearch_api_key:
                raise ValidationError(_("API Key es obligatoria para autenticación por API Key"))
        
        # GUARDA TODOS OS PARÂMETROS NO BANCO DE DADOS
        IrConfigParameter = self.env['ir.config_parameter'].sudo()
        
        # Salva cada campo individualmente
        IrConfigParameter.set_param('product_ai_search.vector_store_type', self.vector_store_type or 'elasticsearch')
        IrConfigParameter.set_param('product_ai_search.config_preset', self.config_preset or 'custom')
        IrConfigParameter.set_param('product_ai_search.elasticsearch_url', self.elasticsearch_url or '')
        IrConfigParameter.set_param('product_ai_search.elasticsearch_index', self.elasticsearch_index or 'products_odoo_ai')
        IrConfigParameter.set_param('product_ai_search.elasticsearch_strategy', self.elasticsearch_strategy or 'dense')
        IrConfigParameter.set_param('product_ai_search.elasticsearch_auth_type', self.elasticsearch_auth_type or 'none')
        IrConfigParameter.set_param('product_ai_search.elasticsearch_username', self.elasticsearch_username or '')
        IrConfigParameter.set_param('product_ai_search.elasticsearch_password', self.elasticsearch_password or '')
        IrConfigParameter.set_param('product_ai_search.elasticsearch_api_key', self.elasticsearch_api_key or '')
        IrConfigParameter.set_param('product_ai_search.elasticsearch_verify_certs', str(bool(self.elasticsearch_verify_certs)))
        IrConfigParameter.set_param('product_ai_search.openai_api_key', self.openai_api_key or '')
        IrConfigParameter.set_param('product_ai_search.batch_size', str(int(self.batch_size or 50)))
        IrConfigParameter.set_param('product_ai_search.auto_index', str(bool(self.auto_index)))
        
        # Faz commit das alterações
        self.env.cr.commit()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("✅ Configuração Salva"),
                'message': _("Todas as configurações foram salvas no banco de dados! URL: %s") % self.elasticsearch_url,
                'type': 'success',
                'sticky': False,
            }
        }

    def test_connection(self):
        """Testa a conexão SEM salvar a configuração primeiro"""
        self.ensure_one()
        
        try:
            # NÃO SALVA - apenas testa com valores atuais do formulário
            # Valida apenas campos essenciais para o teste
            if not self.elasticsearch_url or not self.elasticsearch_url.startswith('http'):
                raise ValidationError(_("Digite uma URL válida para Elasticsearch antes de testar"))
            
            if not self.openai_api_key or not self.openai_api_key.startswith('sk-'):
                raise ValidationError(_("Configure a chave OpenAI antes de testar"))
            
            # Temporarily set parameters just for testing (não persiste no banco)
            IrConfigParameter = self.env['ir.config_parameter'].sudo()
            
            # Salva valores atuais temporariamente para o teste
            old_values = {}
            temp_params = {
                'elasticsearch_url': self.elasticsearch_url,
                'elasticsearch_index': self.elasticsearch_index or 'products_test',
                'elasticsearch_auth_type': self.elasticsearch_auth_type or 'none',
                'elasticsearch_api_key': self.elasticsearch_api_key or '',
                'elasticsearch_verify_certs': str(bool(self.elasticsearch_verify_certs)),
                'openai_api_key': self.openai_api_key,
            }
            
            # Backup dos valores antigos e aplica valores temporários
            for key, value in temp_params.items():
                param_key = f'product_ai_search.{key}'
                old_values[param_key] = IrConfigParameter.get_param(param_key, '')
                IrConfigParameter.set_param(param_key, value)
            
            try:
                # Testa conexão
                service = self.env['product.ai.search.service']
                status = service.check_index_status()
                
                vector_store_name = "Elasticsearch"
                
                if status.get('exists'):
                    message = _("✅ Conexión exitosa con %s!\n URL: %s\n Índice: %s") % (
                        vector_store_name,
                        self.elasticsearch_url,
                        status.get('index_name', 'N/A')
                    )
                    if status.get('has_data'):
                        message += _("\n 📊 El índice contiene datos")
                    else:
                        message += _("\n 📭 El índice está vacío")
                    notification_type = 'success'
                else:
                    message = _("❌ Error en la conexión con %s:\n URL: %s\n Error: %s") % (
                        vector_store_name,
                        self.elasticsearch_url,
                        status.get('error', 'Error desconocido')
                    )
                    notification_type = 'danger'
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _("🔗 Teste de Conexão - %s") % vector_store_name,
                        'message': message,
                        'type': notification_type,
                        'sticky': notification_type == 'danger',
                    }
                }
            
            finally:
                # Restaura valores antigos (rollback)
                for param_key, old_value in old_values.items():
                    IrConfigParameter.set_param(param_key, old_value)
            
        except ValidationError as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("❌ Erro de Validação"),
                    'message': str(e),
                    'type': 'warning',
                    'sticky': True,
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("❌ Erro no Teste"),
                    'message': _("Erro inesperado: %s") % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def index_products_action(self):
        """Acción para indexar produtos"""
        try:
            # Salva a configuração atual
            self.save_config()
            
            service = self.env['product.ai.search.service']
            vector_store_name = "Elasticsearch"
            
            # Indexa produtos com configurações atuais
            result = service.index_products(
                limit=100,  # Límite para prueba
                batch_size=self.batch_size
            )
            
            if result['success']:
                message = _("¡Indexación completada en %s! %d productos indexados en %.1f segundos.") % (
                    vector_store_name,
                    result['indexed_products'], 
                    result['elapsed_time']
                )
                notification_type = 'success'
            else:
                message = _("Error en la indexación con %s: %s") % (vector_store_name, result['message'])
                notification_type = 'danger'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Indexación de Productos - %s") % vector_store_name,
                    'message': message,
                    'type': notification_type,
                }
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Error en la Indexación"),
                    'message': str(e),
                    'type': 'danger',
                }
            }

    def action_open_test(self):
        """Abre la pantalla de prueba de búsqueda"""
        return {
            'type': 'ir.actions.act_window',
            'name': _("🔍 Prueba de Búsqueda IA"),
            'res_model': 'product.ai.search.test',
            'view_mode': 'form',
            'target': 'new',
            'context': {},
        }

    def action_open_indexer(self):
        """Abre la pantalla del indexador de productos"""
        return {
            'type': 'ir.actions.act_window',
            'name': _("🤖 Indexador de Productos IA"),
            'res_model': 'product.ai.search.indexer',
            'view_mode': 'form',
            'target': 'new',
            'context': {},
        }

    @api.onchange('config_preset')
    def _onchange_config_preset(self):
        """Aplica configuraciones predefinidas"""
        if self.config_preset == 'local':
            self.elasticsearch_url = 'http://elasticsearch:9200'
            self.elasticsearch_auth_type = 'none'
            self.elasticsearch_verify_certs = True
            self.elasticsearch_username = ''
            self.elasticsearch_password = ''
            self.elasticsearch_api_key = ''
        elif self.config_preset == 'cloud':
            self.elasticsearch_url = 'https://my-elasticsearch-project-eec211.es.us-central1.gcp.elastic.cloud:443'
            self.elasticsearch_auth_type = 'api_key'
            self.elasticsearch_verify_certs = True
            self.elasticsearch_username = ''
            self.elasticsearch_password = ''
            # Deixa o API key vazio para o usuário preencher ou usar o preset cloud


