{
    'name': "Interconexión de Módulos",
    'version': '17.0.1.3.0',
    'category': 'Point of Sale, Inventory, HR, Multi-Company',
    'summary':
        """
        Interconexión de módulos: sincronización integral entre Punto de Venta,
        Inventario y Recursos Humanos.
        """,
    'description':
        """
        Módulo diseñado para conectar los sistemas de Punto de Venta,
        Inventario y Recursos Humanos, permitiendo que cualquier cambio en uno se refleje automáticamente
        en los demás. Por ejemplo, si se actualiza la información de un empleado (como un cambio de departamento),
        la modificación se propaga en todo el sistema, asegurando una gestión coherente y eficiente en entornos multiempresa.

        Características principales:
        - Campo department_id en pos.config para relación directa POS-Departamento
        - Sincronización bidireccional automática entre allowed_pos (usuario) y basic_employee_ids (POS)
        - Asignación automática de empleados a POS cuando cambia su departamento
        - Asignación automática de todos los empleados cuando se asigna departamento a un POS
        - Vista centralizada para gestión de asignaciones de empleados a POS
        - Acciones masivas para reasignar empleados y sincronizar departamentos
        """,
    'author': 'SOLNUSTEC',
    'company': 'SOLNUSTEC',
    'website': "https://www.solnustec.com",
    'depends': ['base', 'stock', 'product_expiry', 'hr', 'point_of_sale', 'pos_restrict'],
    'data': [
        'views/hr_department_views.xml',
        'views/stock_warehouse_view.xml',
        'views/view_warehouse_tree.xml',
        'views/stock_lots_views.xml',
        'views/stock_picking.xml',
        'views/res_config_settings_view.xml',
        'views/stock_return_picking_view.xml',
        'views/pos_config_views.xml',
        'views/hr_employee_pos_views.xml',
    ],
    # 'external_dependencies': {
        # 'python': ['pandas'],
    # },
    # 'images': ['static/description/banner.png'],
    'license': "AGPL-3",
    'installable': True,
    'application': False,
}