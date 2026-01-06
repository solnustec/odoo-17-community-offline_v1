# -*- coding: utf-8 -*-
{
    'name': 'POS Reload Warning',
    'version': '17.0.1.1.0',
    'category': 'Point of Sale',
    'summary': 'Advertencia al recargar la página del POS',
    'description': """
        Este módulo agrega una advertencia cuando el usuario intenta recargar
        la página del punto de venta (POS) o usa Ctrl+R.

        Esto ayuda a prevenir la pérdida accidental de datos en órdenes
        no guardadas.

        La advertencia NO se muestra durante el proceso de cierre de caja
        para permitir el flujo normal de cierre del sistema.
    """,
    'author': 'Solnustec',
    'depends': ['point_of_sale', 'pos_close_session'],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_reload_warning/static/src/js/reload_warning.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
