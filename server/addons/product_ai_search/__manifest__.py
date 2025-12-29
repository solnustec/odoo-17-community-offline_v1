{
    'name': 'Búsqueda Inteligente de Productos con IA',
    'version': '17.0.2.0.0',
    'category': 'Herramientas',
    'summary': 'Búsqueda inteligente de productos utilizando embeddings con LlamaIndex, Elasticsearch y análisis de receitas médicas',
    'description': '''
    Este módulo proporciona búsqueda inteligente de productos utilizando:
    - LlamaIndex para generación de embeddings
    - Elasticsearch para almacenamiento vectorial
    - OpenAI para embeddings semánticos y GPT-4 Vision
    - Búsqueda en lenguaje natural en español
    - Análisis de receitas médicas por imagem

    Funcionalidades:
    - Indexación automática de productos
    - Búsqueda semántica avanzada
    - Análisis de receitas médicas con GPT-4 Vision
    - Extracción automática de medicamentos de imágenes
    - Búsqueda automática de productos baseada en receitas
    - API REST para integración
    - Interface web para upload de receitas
    - Configuración flexible de Elasticsearch

    Casos de uso:
    - Farmácias: análise rápida de receitas y verificación de estoque
    - Hospitales: gestão de medicamentos prescritos
    - Distribuidoras: identificação automática de productos
    ''',
    'author': 'Solnus Technology',
    'website': 'https://solnustec.com',
    'depends': [
        'base',
        'product',
        'website',
    ],
    'external_dependencies': {
        'python': [
            'llama_index',
            'elasticsearch',  # Para Elasticsearch vector store
            'openai',
            'pandas',
            'tqdm',
            'python-dotenv',
            'Pillow',
            'requests',
        ],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'views/product_ai_search_config_views.xml',
        'views/product_ai_search_test_views.xml',
        'views/product_ai_search_indexer_views.xml',
        'views/prescription_templates.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
