# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    module_l10n_fr_hr_payroll = fields.Boolean(string='French Payroll')
    module_l10n_be_hr_payroll = fields.Boolean(string='Belgium Payroll')
    module_l10n_in_hr_payroll = fields.Boolean(string='Indian Payroll')
    module_hr_payroll_account = fields.Boolean(string='Payroll with Accounting')
    module_hr_payroll_account_sepa = fields.Boolean(string='Payroll with SEPA payment')
    group_payslip_display = fields.Boolean(implied_group="hr_payroll.group_payslip_display")

    enable_import = fields.Boolean(string='Import payslips', default=False)
    mode_of_attendance = fields.Selection(
        selection=[
            ('employee', 'Por Empleado'),
            ('departament', 'Por Departamento'),
        ],
        string='Horarios Basados',
        default='employee',
        required=False
    )

    # Configuraciones de página para reportes
    page_orientation = fields.Selection([
        ('portrait', 'Vertical'),
        ('landscape', 'Horizontal')
    ], string='Orientación de Página',
        config_parameter='hr_payroll.page_orientation',
        default='landscape')

    page_fit_to_width = fields.Integer(
        string='Ajustar al Ancho',
        config_parameter='hr_payroll.page_fit_to_width',
        default=1,
        help='Número de páginas de ancho para ajustar (0 = sin ajuste)')

    page_fit_to_height = fields.Integer(
        string='Ajustar a la Altura',
        config_parameter='hr_payroll.page_fit_to_height',
        default=0,
        help='Número de páginas de alto para ajustar (0 = sin ajuste)')

    page_margin_left = fields.Float(
        string='Margen Izquierdo (pulgadas)',
        config_parameter='hr_payroll.page_margin_left',
        default=0.1,
        digits=(3, 2),
        help='Margen izquierdo en pulgadas')

    page_margin_right = fields.Float(
        string='Margen Derecho (pulgadas)',
        config_parameter='hr_payroll.page_margin_right',
        default=0.1,
        digits=(3, 2),
        help='Margen derecho en pulgadas')

    page_margin_top = fields.Float(
        string='Margen Superior (pulgadas)',
        config_parameter='hr_payroll.page_margin_top',
        default=0.1,
        digits=(3, 2),
        help='Margen superior en pulgadas')

    page_margin_bottom = fields.Float(
        string='Margen Inferior (pulgadas)',
        config_parameter='hr_payroll.page_margin_bottom',
        default=0.1,
        digits=(3, 2),
        help='Margen inferior en pulgadas')

    page_center_horizontally = fields.Boolean(
        string='Centrar Horizontalmente',
        config_parameter='hr_payroll.page_center_horizontally',
        default=True,
        help='Centrar el contenido horizontalmente en la página')

    page_paper_size = fields.Selection([
        ('9', 'A4 (210 x 297 mm)'),
        ('1', 'Letter (8.5 x 11 in)'),
        ('5', 'Legal (8.5 x 14 in)'),
        ('8', 'A3 (297 x 420 mm)'),
        ('11', 'A5 (148 x 210 mm)'),
        ('13', 'B4 (250 x 353 mm)'),
        ('14', 'B5 (176 x 250 mm)'),
    ], string="Tamaño de Papel",
        default='9',
        config_parameter='hr_payroll.page_paper_size',
        help="Selecciona el tamaño de papel para los reportes de asistencia")

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        enable_import = self.env['ir.config_parameter'].sudo().get_param(
            'hr_payroll.enable_import')
        mode_of_attendance = self.env['ir.config_parameter'].sudo().get_param(
            'hr_payroll.mode_of_attendance')

        # Obtener configuraciones de página
        page_orientation = self.env['ir.config_parameter'].sudo().get_param('hr_payroll.page_orientation')
        page_fit_to_width = self.env['ir.config_parameter'].sudo().get_param('hr_payroll.page_fit_to_width')
        page_fit_to_height = self.env['ir.config_parameter'].sudo().get_param('hr_payroll.page_fit_to_height')
        page_margin_left = self.env['ir.config_parameter'].sudo().get_param('hr_payroll.page_margin_left')
        page_margin_right = self.env['ir.config_parameter'].sudo().get_param('hr_payroll.page_margin_right')
        page_margin_top = self.env['ir.config_parameter'].sudo().get_param('hr_payroll.page_margin_top')
        page_margin_bottom = self.env['ir.config_parameter'].sudo().get_param('hr_payroll.page_margin_bottom')
        page_center_horizontally = self.env['ir.config_parameter'].sudo().get_param('hr_payroll.page_center_horizontally')
        page_paper_size = self.env['ir.config_parameter'].sudo().get_param('hr_payroll.page_paper_size')

        res.update(
            enable_import=enable_import if enable_import else False,
            mode_of_attendance=mode_of_attendance if mode_of_attendance else False,

            page_orientation=page_orientation if page_orientation else 'landscape',
            page_fit_to_width=int(page_fit_to_width) if page_fit_to_width else 1,
            page_fit_to_height=int(page_fit_to_height) if page_fit_to_height else 0,
            page_margin_left=float(page_margin_left) if page_margin_left else 0.1,
            page_margin_right=float(page_margin_right) if page_margin_right else 0.1,
            page_margin_top=float(page_margin_top) if page_margin_top else 0.1,
            page_margin_bottom=float(page_margin_bottom) if page_margin_bottom else 0.1,
            page_center_horizontally=page_center_horizontally == 'True' if page_center_horizontally else True,
            page_paper_size=page_paper_size if page_paper_size else '9',
        )
        return res
    def set_values(self):

        old_mode = self.env['ir.config_parameter'].sudo().get_param('hr_payroll.mode_of_attendance')
        super(ResConfigSettings, self).set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'hr_payroll.enable_import', self.enable_import
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'hr_payroll.mode_of_attendance', self.mode_of_attendance
        )

        # Guardar configuraciones de página
        self.env['ir.config_parameter'].sudo().set_param(
            'hr_payroll.page_orientation', self.page_orientation
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'hr_payroll.page_fit_to_width', self.page_fit_to_width
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'hr_payroll.page_fit_to_height', self.page_fit_to_height
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'hr_payroll.page_margin_left', self.page_margin_left
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'hr_payroll.page_margin_right', self.page_margin_right
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'hr_payroll.page_margin_top', self.page_margin_top
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'hr_payroll.page_margin_bottom', self.page_margin_bottom
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'hr_payroll.page_center_horizontally', self.page_center_horizontally
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'hr_payroll.page_paper_size', self.page_paper_size
        )


        new_mode = self.mode_of_attendance
        if old_mode != new_mode:
            self._update_employee_schedules_in_chunks()

    def _update_employee_schedules_in_chunks(self, start_id=0, chunk_size=500):
        Employee = self.env['hr.employee']
        while True:
            employees = Employee.search(
                [('id', '>=', start_id)],
                limit=chunk_size, order='id asc'
            )

            if not employees:
                break

            last_id_in_chunk = employees[-1].id

            for emp in employees:
                try:
                    new_calendar = emp.get_active_schedule_based_on_config()
                    if new_calendar:
                        emp._create_schedule_history(new_calendar.id)
                except Exception as e:
                    _logger.error(f"Error al procesar empleado {emp.id}: {e}")

            start_id = last_id_in_chunk + 1

