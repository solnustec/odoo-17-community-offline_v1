# -*- coding: utf-8 -*-
##############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Dhanya B (odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
import io
import zipfile
import base64
from odoo.tools.translate import _
from lxml import etree
import boto3
import os
from odoo.tools import format_datetime

_logger = logging.getLogger(__name__)

PRIORITIES = [
    ('0', 'Muy Bajo'),
    ('1', 'Bajo'),
    ('2', 'Normal'),
    ('3', 'Alto'),
    ('4', 'Muy alto')
]
RATING = [
    ('0', 'Muy bajo'),
    ('1', 'Bajo'),
    ('2', 'Normal'),
    ('3', 'Alto'),
    ('4', 'Muy alto'),
    ('5', 'Extremadamente alto')
]

class TicketHelpDesk(models.Model):
    """Help_ticket model"""
    _name = 'ticket.helpdesk'
    _description = 'Helpdesk Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    def _default_show_create_task(self):
        """Task creation"""
        return self.env['ir.config_parameter'].sudo().get_param(
            'odoo_website_helpdesk.show_create_task')

    def _default_show_category(self):
        """Show category default"""
        return self.env['ir.config_parameter'].sudo().get_param(
            'odoo_website_helpdesk.show_category')

    name = fields.Char('Nombre', default=lambda self: self.env['ir.sequence'].
                       next_by_code('ticket.helpdesk') or _('New'),
                       help='Nombre del ticket')
    customer_id = fields.Many2one(
        'res.partner',
        string='Nombre del cliente',
        help='Nombre del cliente',
        default=lambda self: self.env.user.partner_id.id,
    )
    user_vat = fields.Char(related='user_id.identification_id', string='Número de identificación', store=False)
    user_email = fields.Char(related='user_id.work_email', string='Email de usuario', store=False)
    user_phone = fields.Char(compute='_compute_user_phone', string='Teléfono de usuario', store=False)
    user_address = fields.Char(related='user_id.partner_id.contact_address', string='Dirección de usuario', store=False)

    customer_name = fields.Char('Nombre del cliente', help='Nombre del cliente')
    subject = fields.Text('Asunto', required=True,
                          help='Asunto del Ticket')
    description = fields.Text('Descripción', required=True,
                              help='Descripción')
    email = fields.Char('Email', help='Email')
    phone = fields.Char('Celular', help='Número de teléfono')
    team_id = fields.Many2one('team.helpdesk', string='Equipo de soporte técnico',
                              help='Nombre del equipo del Soporte técnico')
    product_ids = fields.Many2many('product.template',
                                   string='Producto',
                                   help='Nombre del producto')
    project_id = fields.Many2one('project.project',
                                 string='Proyecto',
                                 readonly=False,
                                 related='team_id.project_id',
                                 store=True,
                                 help='Nombre del proyecto')
    company_id = fields.Many2one(
        'res.company', string='Compañía',
        default=lambda self: self.env.company,
        required=True, index=True, readonly=True)

    priority = fields.Selection(PRIORITIES, string='Prioridad', default='0', help='Prioridad del Ticket')
    stage_id = fields.Many2one('ticket.stage', string='Escenario',
                               default=lambda self: self.env['ticket.stage'].search(
                                   [('name', '=', 'Bandeja de Entrada')], limit=1).id,
                               tracking=True,
                               group_expand='_read_group_stage_ids',
                               help='Escenarios')

    user_id = fields.Many2one(
        'res.users',
        default=lambda self: self.env.user,
        check_company=True,
        index=True,
        tracking=True,
        help='Usuario',
        string='Usuario'
    )
    department_id = fields.Many2one('hr.department', string='Departamento', compute='_compute_department_job',
                                    store=False)
    job_id = fields.Many2one('hr.job', string='Cargo', compute='_compute_department_job', store=False)
    cost = fields.Float('Costo por hora', help='Costo por unidad')
    service_product_id = fields.Many2one('product.product',
                                         string='Producto de servicio',
                                         help='Producto de servicio',
                                         domain=[('detailed_type', '=', 'service')])
    create_date = fields.Datetime('Fecha de creación', help='Fecha en que se creó')
    start_date = fields.Datetime('Fecha de Inicio', help='Fecha en que el ticket se inicio')
    end_date = fields.Datetime('Fecha de Resolución', help='Fecha en que el ticket se resolvió')
    waiting_date = fields.Datetime('Fecha de puesto en Espera', help='Fecha en que el ticket se puso en espera')
    canceled_date = fields.Datetime('Fecha de Cancelación', help='Fecha en que el ticket se canceló')
    public_ticket = fields.Boolean(string="Ticket público",
                                   help='Ticket visible públicamente')
    invoice_ids = fields.Many2many('account.move',
                                   string='Facturas',
                                   help='Facturas relacionadas')
    task_ids = fields.Many2many('project.task',
                                string='Tareas',
                                help='Tareas relacionadas')
    color = fields.Integer(string="Color", help='Color')
    replied_date = fields.Datetime('Fecha de respuesta', help='Fecha de respuesta')
    last_update_date = fields.Datetime('Última actualización del Ticket',
                                       help='Fecha de la última actualización del Ticket')
    ticket_type_id = fields.Many2one('helpdesk.type',
                                     string='Tipo de ticket', help='Tipo de ticket')
    team_head_id = fields.Many2one('res.users', string='Líder del equipo',
                                   compute='_compute_team_head_id',
                                   help='Nombre del líder del equipo')
    assigned_user_ids = fields.Many2many(
        'res.users',
        string="Usuarios Asignados",
        domain="[('id', 'in', assignable_user_ids)]",
        help="Usuarios asignados al ticket"
    )
    assignable_user_ids = fields.Many2many(
        'res.users',
        compute='_compute_assignable_user_ids',
        string="Usuarios asignables"
    )
    category_id = fields.Many2one('helpdesk.category', string='Categoría',
                                  help='Categoría del ticket')
    tags_ids = fields.Many2many('helpdesk.tag', help='Etiquetas', string='Etiquetas')
    assign_user = fields.Boolean(default=False, help='Asignar usuario',
                                 string='Asignar usuario')
    attachment_ids = fields.One2many(
        'ticket.upload.attachment',
        'ticket_id',
        string='Archivos adjuntos',
        readonly=True
    )

    merge_ticket_invisible = fields.Boolean(string='Unir ticket',
                                            help='Mostrar opción de unir ticket o no',
                                            default=False)
    merge_count = fields.Integer(string='Cantidad de tickets unidos',
                                 help='Número de tickets unidos')
    active = fields.Boolean(default=True, help='Activo', string='Activo')

    show_create_task = fields.Boolean(string="Mostrar creación de tarea",
                                      help='Mostrar o no la opción para crear tarea',
                                      default=_default_show_create_task,
                                      compute='_compute_show_create_task')
    create_task = fields.Boolean(string="Crear tarea", readonly=False,
                                 help='Crear tarea o no',
                                 related='team_id.create_task', store=True)
    billable = fields.Boolean(string="Facturable", default=False,
                              help='Indica si es facturable o no')
    show_category = fields.Boolean(default=_default_show_category,
                                   string="Mostrar categoría",
                                   help='Mostrar categoría o no',
                                   compute='_compute_show_category')
    customer_rating = fields.Selection(RATING, default='0')
    review = fields.Char('Reseña', help='Reseña del ticket')
    kanban_state = fields.Selection([
        ('pending_validation', 'En espera de validación'),
        ('validated', 'Validado'),
    ], default='pending_validation', string='Estado de Validación')
    mantenimiento_ids = fields.One2many('mantenimiento.preventivo', 'ticket_id', string='Mantenimiento')
    show_mantenimiento = fields.Boolean(string="¿Es mantenimiento preventivo?", default=False)
    general_observacion = fields.Text(string="Observaciones Generales")
    validar_ticket = fields.Boolean(string='Validar Ticket', default=False)
    stage_closing = fields.Boolean(related='stage_id.closing_stage', store=True)
    area_id = fields.Many2one('helpdesk.area', string='Área', help='Área del ticket', required=True)
    subarea_id = fields.Many2one(
        'helpdesk.subarea',
        string='Subárea',
        help='Subárea del ticket',
        required=True,
        domain="[('area_id', '=?', area_id)]"
    )
    approved = fields.Boolean(string="Aprobado", default=False, help='Indica si el ticket está aprobado o no')
    description_technical = fields.Text(string="Descripción del Técnico", help='Descripción de parte del técnico')
    nro_de_serie = fields.Char(string='Número de Serie',
                               help='Número de serie del equipo, obligatorio para áreas de Computadoras o Sistemas de Seguridad')
    is_serial_number_required = fields.Boolean(
        string='¿Es requerido el número de serie?',
        compute='_compute_is_serial_number_required',
        help='Indica si el número de serie es obligatorio según el área seleccionada'
    )

    technical_attachment_ids = fields.One2many(
        'ticket.upload.attachment',
        'ticket_id',
        string='Archivos técnicos adjuntos',
        domain=[('is_technical', '=', True)],
        readonly=True
    )

    @api.depends('area_id')
    def _compute_is_serial_number_required(self):
        for record in self:
            record.is_serial_number_required = record.area_id and record.area_id.name in ['Computadoras',
                                                                                          'Sistemas de Seguridad']

    @api.depends('user_id')
    def _compute_user_phone(self):
        for record in self:
            employee = record.user_id.employee_ids and record.user_id.employee_ids[0] or False
            record.user_phone = employee.private_phone if employee else False

    def _get_technician_with_least_tickets(self, area_id):
        if not area_id:
            return False

        # Buscar empleados asignados al área
        employees = self.env['hr.employee'].search([('helpdesk_area_ids', 'in', [area_id])])
        if not employees:
            return False

        # Obtener usuarios técnicos
        user_ids = employees.mapped('user_id').filtered(lambda u: u.active)

        # Si estamos en un write (no creación), filtrar por assignable_user_ids
        if self.ids and hasattr(self, 'assignable_user_ids'):
            user_ids = user_ids.filtered(lambda u: u.id in self.assignable_user_ids.ids)

        if not user_ids:
            return False

        ticket_counts = self.env['ticket.helpdesk'].read_group(
            domain=[('assigned_user_ids', 'in', user_ids.ids), ('stage_closing', '=', False)],
            fields=['assigned_user_ids'],
            groupby=['assigned_user_ids']
        )

        ticket_count_dict = {rec['assigned_user_ids'][0]: rec['assigned_user_ids_count'] for rec in ticket_counts}
        for user_id in user_ids.ids:
            if user_id not in ticket_count_dict:
                ticket_count_dict[user_id] = 0

        if ticket_count_dict:
            return min(ticket_count_dict, key=ticket_count_dict.get)
        return False

    @api.onchange('area_id')
    def _onchange_area_id(self):
        if self.area_id:
            # Asignar automáticamente la primera subárea disponible
            first_subarea = self.env['helpdesk.subarea'].search([('area_id', '=', self.area_id.id)], limit=1)
            self.subarea_id = first_subarea.id if first_subarea else False
            # Asignar automáticamente el técnico con menos tickets
            assigned_user_id = self._get_technician_with_least_tickets(self.area_id.id)
            self.assigned_user_ids = [(6, 0, [assigned_user_id])] if assigned_user_id else [(6, 0, [])]
            # Limpiar el número de serie si el área no es Computadoras o Sistemas de Seguridad
            if self.area_id.name not in ['Computadoras', 'Sistemas de Seguridad']:
                self.nro_de_serie = False
            return {
                'domain': {
                    'subarea_id': [('area_id', '=', self.area_id.id)],
                    'assigned_user_ids': [('id', 'in', self.assignable_user_ids.ids),
                                          ('employee_ids.helpdesk_area_ids', 'in', self.area_id.id)]
                }
            }
        else:
            self.subarea_id = False
            self.assigned_user_ids = [(6, 0, [])]
            self.nro_de_serie = False
            return {
                'domain': {
                    'subarea_id': [],
                    'assigned_user_ids': [('id', 'in', self.assignable_user_ids.ids)]
                }
            }

    @api.constrains('area_id', 'subarea_id', 'nro_de_serie')
    def _check_subarea_and_serial(self):
        for ticket in self:
            if ticket.subarea_id and ticket.subarea_id.area_id != ticket.area_id:
                raise ValidationError(_('La subárea seleccionada no pertenece al área especificada.'))

    @api.depends()
    def _compute_assignable_user_ids(self):
        group = self.env.ref('odoo_website_helpdesk.helpdesk_assigned_user', raise_if_not_found=False)
        users = group.users if group else self.env['res.users']
        for record in self:
            record.assignable_user_ids = users

    @api.depends('user_id')
    def _compute_department_job(self):
        for rec in self:
            employee = rec.user_id.employee_ids and rec.user_id.employee_ids[0] or False
            rec.department_id = employee.department_id.id if employee else False
            rec.job_id = employee.job_id.id if employee else False

    @api.onchange('team_id')
    def _onchange_team_id(self):
        """Actualiza el dominio de assigned_user_ids según el equipo seleccionado"""
        domain = [('id', 'in', self.assignable_user_ids.ids)]
        if self.team_id:
            domain.append(('id', 'in', self.team_id.member_ids.mapped('id')))
        if self.area_id:
            employees = self.env['hr.employee'].search([('helpdesk_area_ids', 'in', self.area_id.id)])
            user_ids = employees.mapped('user_id').ids
            domain.append(('id', 'in', user_ids))
        return {'domain': {'assigned_user_ids': domain}}

    @api.depends('team_id')
    def _compute_team_head_id(self):
        """Compute the team head function"""
        self.team_head_id = self.team_id.team_lead_id.id

    def _compute_show_category(self):
        show_category = self._default_show_category()
        for rec in self:
            rec.show_category = show_category

    def _compute_show_create_task(self):
        """Compute the created task"""
        show_create_task = self._default_show_create_task()
        for record in self:
            record.show_create_task = show_create_task

    def auto_close_ticket(self):
        """Automatically closing the ticket"""
        auto_close = self.env['ir.config_parameter'].sudo().get_param(
            'odoo_website_helpdesk.auto_close_ticket')
        if auto_close:
            no_of_days = self.env['ir.config_parameter'].sudo().get_param(
                'odoo_website_helpdesk.no_of_days')
            records = self.env['ticket.helpdesk'].search([])
            for rec in records:
                days = (fields.Datetime.today() - rec.create_date).days
                if days >= int(no_of_days):
                    close_stage_id = self.env['ticket.stage'].search(
                        [('closing_stage', '=', True)])
                    if close_stage_id:
                        rec.stage_id = close_stage_id

    def default_stage_id(self):
        """Method to return the default stage"""
        return self.env['ticket.stage'].search(
            [('name', '=', 'Bandeja de Entrada')], limit=1).id

    @api.model
    def _read_group_stage_ids(self, stages, domain, order):
        """
        return the stages to stage_ids
        """
        stage_ids = self.env['ticket.stage'].search([])
        return stage_ids

    @api.model_create_multi
    def create(self, vals_list):
        """Create function"""
        records = self.browse()
        for vals in vals_list:
            draft_stage = self.env['ticket.stage'].search([('name', '=', 'Bandeja de Entrada')], limit=1)
            if not draft_stage:
                raise ValidationError(
                    _("La etapa 'Bandeja de Entrada' no está definida. Por favor, configure una etapa con el nombre 'Bandeja de Entrada' como etapa inicial."))
            vals['stage_id'] = draft_stage.id

            # Generación del nombre/secuencia
            if vals.get('name', _('New')) == _('New'):
                ticket_type_id = vals.get('ticket_type_id')
                priority = vals.get('priority', '1')
                if priority not in ['1', '2', '3', '4']:
                    raise ValidationError(_("La prioridad debe estar entre 1 y 4."))
                if ticket_type_id:
                    ticket_type = self.env['helpdesk.type'].browse(ticket_type_id)
                    type_prefix = ticket_type.name[:3].upper() if ticket_type.name else 'TKT'
                    sequence_code = f"ticket.helpdesk.{type_prefix.lower()}.p{priority}"
                    sequence = self.env['ir.sequence'].search([('code', '=', sequence_code)], limit=1)
                    if not sequence:
                        sequence = self.env['ir.sequence'].create({
                            'name': f"Secuencia para {type_prefix}-P{priority}",
                            'code': sequence_code,
                            'prefix': f"{type_prefix}-P{priority}-",
                            'padding': 5,
                            'number_increment': 1,
                            'company_id': False,
                        })
                    vals['name'] = sequence.next_by_code(sequence_code)
                else:
                    vals['name'] = self.env['ir.sequence'].next_by_code('ticket.helpdesk') or _('New')

            # Asignación automática de técnico
            if vals.get('area_id'):
                temp_record = self.new(vals)
                temp_record._compute_assignable_user_ids()
                area = self.env['helpdesk.area'].browse(vals['area_id'])
                if area.exists():
                    technician_id = temp_record._get_technician_with_least_tickets(area.id)
                    if technician_id:
                        vals['assigned_user_ids'] = [(6, 0, [technician_id])]
                    else:
                        _logger.warning("No se encontró un técnico disponible para el área %s", area.name)

        # Crear todos los registros de una vez
        records = super(TicketHelpDesk, self).create(vals_list)

        # Envío de notificaciones
        template_creator = self.env.ref('odoo_website_helpdesk.ticket_created', raise_if_not_found=False)
        template_admin = self.env.ref('odoo_website_helpdesk.ticket_created_admin_notification',
                                      raise_if_not_found=False)
        template_notify_customer = self.env.ref('odoo_website_helpdesk.odoo_website_helpdesk_to_customer',
                                                raise_if_not_found=False)
        template_notify_assigned = self.env.ref('odoo_website_helpdesk.odoo_website_helpdesk_assign_user',
                                                raise_if_not_found=False)

        for record in records:
            # Notificación al creador
            if template_creator:
                template_creator.send_mail(record.id, force_send=True)

            # Notificación a managers
            if template_admin:
                admin_users = self.env['res.users'].search([
                    ('groups_id', 'in', self.env.ref('odoo_website_helpdesk.helpdesk_manager').id),
                    ('active', '=', True)
                ])
                for admin_user in admin_users:
                    mail_values = {
                        'email_to': admin_user.partner_id.email,
                        'auto_delete': True,
                    }
                    template_admin.with_context(mail_values).send_mail(
                        record.id, force_send=True, email_values=mail_values)

            # Notificación al usuario asignado (si hay)
            if template_notify_assigned and record.assigned_user_ids:
                for user in record.assigned_user_ids:
                    if user.email:
                        template_notify_assigned.send_mail(record.id, force_send=True,
                                                           email_values={'email_to': user.email})

            # Notificación al cliente (opcional si tienes campo `customer_id`)
            if template_notify_customer and record.customer_id and record.customer_id.email:
                template_notify_customer.send_mail(record.id, force_send=True)

        return records

    def write(self, vals):
        """Write function"""
        has_manager_access = self.env.user.has_group('odoo_website_helpdesk.helpdesk_manager')
        is_assigned_user = self.env.user.id in self.assigned_user_ids.ids
        if not (has_manager_access or is_assigned_user):
            raise ValidationError(
                _("Solo los administradores o los usuarios asignados pueden modificar el estado del ticket.")
            )

        # Stage transition validation
        if 'stage_id' in vals:
            if not self.exists():
                raise ValidationError(
                    _("No se puede modificar el estado de un ticket antes de que haya sido creado.")
                )

            new_stage_id = vals['stage_id']
            new_stage = self.env['ticket.stage'].browse(new_stage_id)
            bandeja_entrada = self.env.ref('odoo_website_helpdesk.stage_inbox', raise_if_not_found=False)
            en_curso = self.env.ref('odoo_website_helpdesk.stage_in_progress', raise_if_not_found=False)
            en_espera = self.env.ref('odoo_website_helpdesk.stage_in_wait', raise_if_not_found=False)
            resuelto = self.env.ref('odoo_website_helpdesk.stage_done', raise_if_not_found=False)
            cancelado = self.env.ref('odoo_website_helpdesk.stage_canceled', raise_if_not_found=False)

            for record in self:
                current_stage = record.stage_id
                if current_stage == bandeja_entrada and new_stage != en_curso:
                    raise ValidationError(
                        _("Un ticket en 'Bandeja de Entrada' solo puede pasar a 'En Curso'.")
                    )
                elif current_stage == en_curso and new_stage not in [en_espera, resuelto, cancelado]:
                    raise ValidationError(
                        _("Un ticket en 'En Curso' solo puede pasar a 'En Espera', 'Resuelto' o 'Cancelado'.")
                    )
                elif current_stage == en_espera and new_stage != en_curso:
                    raise ValidationError(
                        _("Un ticket en 'En Espera' solo puede pasar a 'En Curso'.")
                    )
                elif current_stage == resuelto:
                    raise ValidationError(
                        _("Un ticket en 'Resuelto' no puede cambiar a ninguna otra etapa.")
                    )
                elif current_stage == cancelado:
                    raise ValidationError(
                        _("Un ticket en 'Cancelado' no puede cambiar a ninguna otra etapa.")
                    )

        old_stages = {record.id: record.stage_id for record in self}

        # Verificar si ticket_type_id o priority están en los valores a actualizar
        if 'ticket_type_id' in vals or 'priority' in vals:
            for record in self:
                if record.stage_closing:
                    continue
                ticket_type_id = vals.get('ticket_type_id',
                                          record.ticket_type_id.id if record.ticket_type_id else False)
                priority = vals.get('priority', record.priority)
                if priority not in ['1', '2', '3', '4']:
                    raise ValidationError(_("La prioridad debe estar entre 1 y 4."))
                if ticket_type_id:
                    ticket_type = self.env['helpdesk.type'].browse(ticket_type_id)
                    type_prefix = ticket_type.name[:3].upper() if ticket_type.name else 'TKT'
                    sequence_code = f"ticket.helpdesk.{type_prefix.lower()}.p{priority}"
                    sequence = self.env['ir.sequence'].search([('code', '=', sequence_code)], limit=1)
                    if not sequence:
                        sequence = self.env['ir.sequence'].create({
                            'name': f"Secuencia para {type_prefix}-P{priority}",
                            'code': sequence_code,
                            'prefix': f"{type_prefix}-P{priority}-",
                            'padding': 5,
                            'number_increment': 1,
                            'company_id': False,
                        })
                    vals['name'] = sequence.next_by_code(sequence_code)
                else:
                    vals['name'] = self.env['ir.sequence'].next_by_code('ticket.helpdesk') or _('New')

        # Validar nro_de_serie si el área cambia
        if 'area_id' in vals or 'nro_de_serie' in vals:
            for record in self:
                area_id = vals.get('area_id', record.area_id.id)
                area = self.env['helpdesk.area'].browse(area_id)
                if area.name in ['Computadoras', 'Sistemas de Seguridad']:
                    nro_de_serie = vals.get('nro_de_serie', record.nro_de_serie)
                    if not nro_de_serie:
                        raise ValidationError(
                            _('El número de serie es obligatorio para las áreas de Computadoras o Sistemas de Seguridad.')
                        )

        assigned_user_changed = 'assigned_user_ids' in vals
        stage_changed = 'stage_id' in vals
        area_changed = 'area_id' in vals
        # Asignar automáticamente el técnico con menos tickets si cambia el area_id
        if area_changed and vals.get('area_id'):
            technician_id = self._get_technician_with_least_tickets(vals['area_id'])
            if technician_id:
                # Asignar solo el técnico con menos tickets si no se especificaron usuarios asignados
                if 'assigned_user_ids' not in vals:
                    vals['assigned_user_ids'] = [(6, 0, [technician_id])]
            else:
                _logger.warning("No se encontró un técnico disponible para el área %s", vals.get('area_id'))
                if 'assigned_user_ids' not in vals:
                    vals['assigned_user_ids'] = [(6, 0, [])]
        result = super(TicketHelpDesk, self).write(vals)
        if assigned_user_changed or area_changed:
            template_notify_customer = self.env.ref('odoo_website_helpdesk.odoo_website_helpdesk_to_customer',
                                                    raise_if_not_found=False)
            template_notify_assigned = self.env.ref('odoo_website_helpdesk.odoo_website_helpdesk_assign_user',
                                                    raise_if_not_found=False)
            for record in self:
                if template_notify_customer and record.customer_id and record.assigned_user_ids and record.customer_id.email:
                    template_notify_customer.send_mail(record.id, force_send=True)
                if template_notify_assigned and record.assigned_user_ids:
                    for user in record.assigned_user_ids:
                        if user.email:
                            template_notify_assigned.send_mail(record.id, force_send=True,
                                                               email_values={'email_to': user.email})
        if stage_changed:
            for record in self:
                new_stage = record.stage_id
                old_stage = old_stages.get(record.id)
                if new_stage != old_stage:
                    if new_stage.id == self.env.ref('odoo_website_helpdesk.stage_in_progress').id:
                        if not record.start_date:
                            record.start_date = fields.Datetime.now()
                    elif new_stage.id == self.env.ref('odoo_website_helpdesk.stage_in_wait').id:
                        if not record.waiting_date:
                            record.waiting_date = fields.Datetime.now()
                    elif new_stage.id == self.env.ref('odoo_website_helpdesk.stage_done').id:
                        if not record.end_date:
                            record.end_date = fields.Datetime.now()
                    elif new_stage.id == self.env.ref('odoo_website_helpdesk.stage_canceled').id:
                        if not record.canceled_date:
                            record.canceled_date = fields.Datetime.now()
                    record.last_update_date = fields.Datetime.now()
                    if new_stage.id == self.env.ref('odoo_website_helpdesk.stage_in_progress').id:
                        template = self.env.ref('odoo_website_helpdesk.ticket_stage_in_progress',
                                                raise_if_not_found=False)
                        if template and record.customer_id.email:
                            template.send_mail(record.id, force_send=True)
                    elif new_stage.id == self.env.ref('odoo_website_helpdesk.stage_in_wait').id:
                        template = self.env.ref('odoo_website_helpdesk.ticket_stage_pending', raise_if_not_found=False)
                        if template and record.customer_id.email:
                            template.send_mail(record.id, force_send=True)
                    elif new_stage.id == self.env.ref('odoo_website_helpdesk.stage_done').id:
                        template = self.env.ref('odoo_website_helpdesk.ticket_approved', raise_if_not_found=False)
                        if template and record.customer_id.email:
                            template.send_mail(record.id, force_send=True)
                    elif new_stage.id == self.env.ref('odoo_website_helpdesk.stage_canceled').id:
                        template = self.env.ref('odoo_website_helpdesk.ticket_canceled', raise_if_not_found=False)
                        if template and record.customer_id.email:
                            template.send_mail(record.id, force_send=True)
        return result

    def format_local_datetime(self, datetime_value):
        if not datetime_value:
            return 'N/A'
        return format_datetime(
            self.env,
            datetime_value,
            dt_format='dd/MM/yyyy HH:mm',
            tz='America/Lima'
        )

    def action_upload_attachment(self):
        return {
            'name': _('Subir archivo'),
            'type': 'ir.actions.act_window',
            'res_model': 'ticket.upload.attachment',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_ticket_id': self.id,
            }
        }

    def action_download_all(self):
        self.ensure_one()
        attachments = self.attachment_ids
        if not attachments:
            raise UserError(_("No hay archivos adjuntos para descargar."))

        # Crear un archivo ZIP con todos los adjuntos
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            s3 = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=os.getenv('AWS_REGION')
            )
            bucket = os.getenv('AWS_BUCKETNAME')
            for attachment in attachments:
                if attachment.datas:
                    zip_file.writestr(attachment.name, base64.b64decode(attachment.datas))
                elif attachment.file_url:
                    # Descargar el archivo desde S3
                    key = attachment.file_url.split(f'https://{bucket}.s3.amazonaws.com/')[1]
                    response = s3.get_object(Bucket=bucket, Key=key)
                    zip_file.writestr(attachment.name, response['Body'].read())

        zip_buffer.seek(0)
        zip_data = base64.b64encode(zip_buffer.getvalue())

        # Crear un adjunto temporal para el archivo ZIP
        zip_attachment = self.env['ir.attachment'].create({
            'name': f'attachments_{self.name}.zip',
            'datas': zip_data,
            'type': 'binary',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{zip_attachment.id}?download=true',
            'target': 'self',
        }

    def action_upload_technical_attachment(self):
        return {
            'name': _('Subir archivo técnico'),
            'type': 'ir.actions.act_window',
            'res_model': 'ticket.upload.attachment',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_ticket_id': self.id,
                'default_is_technical': True,
            }
        }

    def action_download_all_technical(self):
        self.ensure_one()
        attachments = self.technical_attachment_ids
        if not attachments:
            raise UserError(_("No hay archivos técnicos adjuntos para descargar."))

        # Same implementation as action_download_all but for technical attachments
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            s3 = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=os.getenv('AWS_REGION')
            )
            bucket = os.getenv('AWS_BUCKETNAME')
            for attachment in attachments:
                if attachment.datas:
                    zip_file.writestr(attachment.name, base64.b64decode(attachment.datas))
                elif attachment.file_url:
                    key = attachment.file_url.split(f'https://{bucket}.s3.amazonaws.com/')[1]
                    response = s3.get_object(Bucket=bucket, Key=key)
                    zip_file.writestr(attachment.name, response['Body'].read())

        zip_buffer.seek(0)
        zip_data = base64.b64encode(zip_buffer.getvalue())

        zip_attachment = self.env['ir.attachment'].create({
            'name': f'technical_attachments_{self.name}.zip',
            'datas': zip_data,
            'type': 'binary',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{zip_attachment.id}?download=true',
            'target': 'self',
        }

    def action_create_invoice(self):
        """Create Invoice based on the ticket"""
        tasks = self.env['project.task'].search(
            [('project_id', '=', self.project_id.id),
             ('ticket_id', '=', self.id)]).filtered(
            lambda line: not line.ticket_billed)
        if not tasks:
            raise UserError('No Tasks to Bill')
        total = sum(x.effective_hours for x in tasks if
                    x.effective_hours > 0 and not x.some_flag)
        invoice_no = self.env['ir.sequence'].next_by_code(
            'ticket.invoice')
        self.env['account.move'].create([
            {
                'name': invoice_no,
                'move_type': 'out_invoice',
                'partner_id': self.customer_id.id,
                'ticket_id': self.id,
                'date': fields.Date.today(),
                'invoice_date': fields.Date.today(),
                'invoice_line_ids': [(0, 0,
                                      {
                                          'product_id': self.service_product_id.id,
                                          'name': self.service_product_id.name,
                                          'quantity': total,
                                          'product_uom_id': self.service_product_id.uom_id.id,
                                          'price_unit': self.cost,
                                          'account_id': self.service_product_id.categ_id.property_account_income_categ_id.id,
                                      })],
            }, ])
        for task in tasks:
            task.ticket_billed = True
        return {
            'effect': {
                'fadeout': 'medium',
                'message': 'Billed Successfully!',
                'type': 'rainbow_man',
            }
        }

    def action_create_tasks(self):
        """Task creation"""
        task_id = self.env['project.task'].create({
            'name': self.name + '-' + self.subject,
            'project_id': self.project_id.id,
            'company_id': self.env.company.id,
            'ticket_id': self.id,
        })
        self.write({
            'task_ids': [(4, task_id.id)]
        })
        return {
            'name': 'Tasks',
            'res_model': 'project.task',
            'view_id': False,
            'res_id': task_id.id,
            'view_mode': 'form',
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    def action_open_tasks(self):
        """View the Created task """
        return {
            'name': 'Tasks',
            'domain': [('ticket_id', '=', self.id)],
            'res_model': 'project.task',
            'view_id': False,
            'view_mode': 'tree,form',
            'type': 'ir.actions.act_window',
        }

    def action_open_invoices(self):
        """View the Created invoice"""
        return {
            'name': 'Invoice',
            'domain': [('ticket_id', '=', self.id)],
            'res_model': 'account.move',
            'view_id': False,
            'view_mode': 'tree,form',
            'type': 'ir.actions.act_window',
        }

    def action_open_merged_tickets(self):
        """Open the merged tickets tree view"""
        ticket_ids = self.env['support.ticket'].search(
            [('merged_ticket', '=', self.id)])
        helpdesk_ticket_ids = ticket_ids.mapped('display_name')
        help_ticket_records = self.env['ticket.helpdesk'].search(
            [('name', 'in', helpdesk_ticket_ids)])
        return {
            'type': 'ir.actions.act_window',
            'name': 'Helpdesk Ticket',
            'view_mode': 'tree,form',
            'res_model': 'ticket.helpdesk',
            'domain': [('id', 'in', help_ticket_records.ids)],
            'context': self.env.context,
        }

    def action_send_reply(self):
        """Acción para enviar correo usando directamente la plantilla 'ticket_communication'"""
        self.ensure_one()

        template = self.env.ref('odoo_website_helpdesk.ticket_communication', raise_if_not_found=False)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Enviar Comunicación',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'views': [[False, 'form']],
            'context': {
                'default_model': 'ticket.helpdesk',
                'default_res_ids': [self.id],
                'default_template_id': template.id if template else False,
                'default_composition_mode': 'comment',
            }
        }