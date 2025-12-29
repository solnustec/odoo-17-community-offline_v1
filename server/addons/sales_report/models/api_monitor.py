from odoo import fields, models, api


class ApiMonitor(models.Model):
    _name = 'api.monitor'
    _description = 'Monitor de APIs'
    _order = 'name'

    name = fields.Char(string='Nombre API', required=True)
    endpoint = fields.Char(string='Endpoint', required=True, help='Ruta del endpoint a monitorear')
    active = fields.Boolean(string='Activo', default=True)

    # Configuración de monitoreo
    check_interval = fields.Integer(
        string='Intervalo de Verificación (minutos)',
        default=5,
        help='Cada cuántos minutos verificar si la API está recibiendo datos'
    )
    max_delay = fields.Integer(
        string='Retraso Máximo Permitido (minutos)',
        default=2,
        help='Tiempo máximo sin recibir datos antes de marcar como inactiva'
    )

    # Estado actual
    status = fields.Selection([
        ('active', 'Activa'),
        ('inactive', 'Inactiva'),
        ('warning', 'Advertencia'),
    ], string='Estado', default='active', compute='_compute_status', store=True)

    last_request_date = fields.Datetime(string='Última Petición', readonly=True)
    last_check_date = fields.Datetime(string='Última Verificación', readonly=True)
    request_count = fields.Integer(string='Total Peticiones', readonly=True, default=0)

    # Estadísticas
    inactive_count = fields.Integer(string='Veces Inactiva', readonly=True, default=0)
    last_inactive_date = fields.Datetime(string='Última Vez Inactiva', readonly=True)

    # Notificaciones
    notify_push = fields.Many2many(comodel_name='res.users',
                                   string='Notificacion Usuarios', )
    notify_on_inactive = fields.Boolean(string='Notificar si Inactiva', default=True)

    # Historial
    log_ids = fields.One2many('api.monitor.log', 'monitor_id', string='Historial')

    @api.depends('last_request_date', 'max_delay')
    def _compute_status(self):
        for record in self:
            if not record.last_request_date:
                record.status = 'warning'
                continue

            now = fields.Datetime.now()
            time_diff = (now - record.last_request_date).total_seconds() / 60

            if time_diff <= record.max_delay:
                record.status = 'active'
            elif time_diff <= record.max_delay * 1.5:
                record.status = 'warning'
            else:
                record.status = 'inactive'

    def register_request(self):
        """Método para registrar que la API recibió una petición"""
        self.ensure_one()
        self.write({
            'last_request_date': fields.Datetime.now(),
            'request_count': self.request_count + 1
        })

    def check_status(self):
        """Verifica el estado de la API"""
        self.ensure_one()
        now = fields.Datetime.now()
        self.last_check_date = now

        if not self.last_request_date:
            self._create_log('warning', 'No hay registro de peticiones')
            return False

        time_diff = (now - self.last_request_date).total_seconds() / 60

        if time_diff > self.max_delay:
            # API inactiva
            self.write({
                'inactive_count': self.inactive_count + 1,
                'last_inactive_date': now
            })
            self._create_log('error',
                             f'API inactiva. Última petición hace {int(time_diff)} minutos')

            if self.notify_on_inactive and self.notify_push:
                print(self.notify_push,'asldjasldjasldjasdklasdjal')
                for push in self.notify_push:
                    self._send_notification(push)

            return False
        else:
            self._create_log('success',
                             f'API activa. Última petición hace {int(time_diff)} minutos')
            return True

    def _create_log(self, log_type, message):
        """Crea un registro en el historial"""
        self.env['api.monitor.log'].create({
            'monitor_id': self.id,
            'log_type': log_type,
            'message': message,
            'check_date': fields.Datetime.now()
        })

    def _send_notification(self, push_user):
        """Envía notificación por email"""
        try:

            device = self.env['push.device'].find_by_user(push_user.id)
            print(device, 'dsadsadasd', push_user)
            if not device:
                return

            # En otro modelo, collamando a este metodo desde otro modelo:
            self.env['firebase.service'].send_push_notification(
                registration_token=device.register_id,
                title="Monitor de API - Alerta",
                body="La API '%s' está inactiva." % self.name,
            )
        except Exception as e:
            print(e)

    @api.model
    def cron_check_all_apis(self):
        """Cron job para verificar todas las APIs activas"""
        apis = self.search([('active', '=', True)])

        for api in apis:
            try:
                api.check_status()
            except Exception as e:
                pass


class ApiMonitorLog(models.Model):
    _name = 'api.monitor.log'
    _description = 'Historial de Monitoreo de API'
    _order = 'check_date desc'

    monitor_id = fields.Many2one('api.monitor', string='API', required=True, ondelete='cascade')
    check_date = fields.Datetime(string='Fecha de Verificación', required=True,
                                 default=fields.Datetime.now)
    log_type = fields.Selection([
        ('success', 'Éxito'),
        ('warning', 'Advertencia'),
        ('error', 'Error')
    ], string='Tipo', required=True)
    message = fields.Text(string='Mensaje')
