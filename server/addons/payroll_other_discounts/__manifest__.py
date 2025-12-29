{
    'name': "Payroll Other Discounts",
    'version': '2.0',
    'category': 'hr',
    'summary': "módulo que maneja descuentos, créditos y conceptos similares para ser llamados en nómina.",
    'depends': ['base', 'hr', 'hr_payroll'],
    'data': [
        'security/access_to_other_discount.xml',
        'security/ir.model.access.csv',
        'data/domain_view.xml',
        'views/hr_payroll_discount_category_view.xml',
        'views/hr_payroll_discount_view.xml',
        'views/import_normalize_view.xml',
    ],
    'assets': {
    },
    'license': 'LGPL-3',
}
