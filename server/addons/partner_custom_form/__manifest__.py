{
    'name': 'Formulario actualizacion clientes',
    'version': '1.0',
    'summary': 'Permite obtener un formulario para actualizar los datos de los clientes',
    'author': 'Holger Jaramillo',
    'category': 'Tools',
    'depends': ['base','mail','mass_mailing'],
    'data': [
        'views/form.xml',
        'views/update_thank_you.xml',
    ],

    'assets': {},
    'license': 'AGPL-3',
    'installable': True,
    'application': True,
}
