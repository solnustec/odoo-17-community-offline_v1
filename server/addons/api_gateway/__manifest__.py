# -*- coding: utf-8 -*-
{
    'name': 'API Gateway',
    'version': '17.0.1.0.0',
    'summary': 'Gateway proxy para APIs externas desde sucursales OFFLINE',
    'description': """
        Módulo que actúa como proxy/gateway para permitir que las sucursales
        OFFLINE puedan comunicarse con APIs externas a través del servidor PRINCIPAL.

        Funcionalidades:
        - Proxy genérico para cualquier API configurada
        - Endpoints específicos para Ahorita y Deuna
        - Recepción de webhooks y almacenamiento para consulta posterior
        - Log de todas las transacciones
        - Configuración de APIs permitidas
    """,
    'author': 'Solnustec',
    'website': 'https://www.solnustec.com',
    'category': 'Technical',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/api_gateway_views.xml',
        'views/api_gateway_menu.xml',
        'data/api_gateway_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
