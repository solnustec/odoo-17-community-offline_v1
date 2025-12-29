{
    'name': 'Paso de Reclutamiento a Empleado',
    'version': '1.1',
    'category': 'Human Resources/Employees',
    'summary': 'Pasa la información recolectada en reclutamiento al empleado',
    'author': 'Klever Ontaneda',
    'description': """
    Pasa la información recolectada en reclutamiento al empleado
    """,
    'depends': ['base','custom', 'hr',
                'hr_contract', 'hr_recruitment',
                ],
    'data': [
        # 'security/ir.model.access.csv',
        # 'views/templates.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'AGPL-3',
}
