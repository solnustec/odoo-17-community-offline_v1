from odoo import models, fields, api

class MantenimientoPreventivo(models.Model):
    _name = "mantenimiento.preventivo"
    _description = "Mantenimiento Preventivo de Equipos"

    ticket_id = fields.Many2one('ticket.helpdesk', string='Ticket')

    sucursal = fields.Char(string="Sucursal")
    fecha = fields.Date(string="Fecha")
    ciudad = fields.Char(string="Ciudad")
    direccion = fields.Char(string="Dirección")

    name_mantenimiento = fields.Char(string="Id del Mantenimiento")

    nombre_equipo = fields.Char(string="Nombre del Equipo")
    nombre_equipo_observacion = fields.Text(string="Observación del Equipo")

    anydesk = fields.Char(string="Anydesk")
    anydesk_observacion = fields.Text(string="Observación del Anydesk")

    # Procesador
    procesador_core = fields.Selection([
        ('i3', 'Core i3'),
        ('i5', 'Core i5'),
        ('i7', 'Core i7'),
        ('i9', 'Core i9'),
    ], string="Procesador")
    procesador_generacion = fields.Selection([
        ('8va', '8va Gen'),
        ('9na', '9na Gen'),
        ('10ma', '10ma Gen'),
        ('11va', '11va Gen'),
    ], string="Generación del Procesador")
    procesador_observacion = fields.Text(string="Observación del Procesador")

    # Memoria RAM
    ram_size = fields.Selection([
        ('4gb', '4GB RAM'),
        ('8gb', '8GB RAM'),
    ], string="Tamaño de RAM")
    mem_ram_observacion = fields.Text(string="Observación de la Memoria RAM")

    # Almacenamiento
    almacenamiento_size = fields.Selection([
        ('240gb', 'SSD 240GB'),
        ('480gb', 'SSD 480GB'),
    ], string="Almacenamiento")
    almacenamiento_observacion = fields.Text(string="Observación del Almacenamiento")

    # Sistema Operativo
    sistema_operativo = fields.Selection([
        ('windows10', 'Windows 10 Pro 64 Bits'),
        ('windows11', 'Windows 11 Pro 64 Bits'),
    ], string="Nombre del Sistema Operativo")
    sistem_operativa_observacion = fields.Text(string="Observación del Sistema Operativo")

    # Impresora
    printer_types = fields.Selection([
        ('T20II', 'T20II'),
        ('T20III', 'T20III'),
    ], string="Versión de Impresora")
    impresora_observacion = fields.Text(string="Observación de la Impresora")

    # Monitor
    model_monitor = fields.Selection([
        ('20MP38HQ', '20MP38HQ'),
        ('20MK400H', '20MK400H'),
    ], string="Modelo del Monitor")
    monitor_observacion = fields.Text(string="Observación del Monitor")

    # Escáner
    model_escaner = fields.Selection([
        ('Honeywell', 'Honeywell'),
        ('Zebra', 'Zebra'),
        ('DS22085R', 'DS22085R'),
        ('HSM-1200G', 'HSM-1200G'),
        ('LI2208', 'LI2208'),
    ], string="Modelo del Escáner")
    escaner_observacion = fields.Text(string="Observación del Escáner")

    # Teclado
    model_teclado = fields.Selection([
        ('Genius', 'Genius'),
        ('Logitech', 'Logitech'),
    ], string="Modelo del Teclado")
    teclado_observacion = fields.Text(string="Observación del Teclado")

    # Mouse
    model_mouse = fields.Selection([
        ('Genius', 'Genius'),
        ('Logitech', 'Logitech'),
    ], string="Modelo del Mouse")
    mouse_observacion = fields.Text(string="Observación del Mouse")

    # Caja de dinero
    model_cajaDinero = fields.Selection([
        ('3nSTAR', '3nSTAR'),
        ('Zk-Teko', 'Zk-Teko'),
        ('CD-350', 'CD-350'),
        ('CD-325', 'CD-325'),
        ('ZK-C0508', 'ZK-C0508'),
    ], string="Modelo de la Caja de Dinero")
    cajadinero_observacion = fields.Text(string="Observación de la Caja de Dinero")

    # Regulador de Voltaje
    model_regulador = fields.Selection([
        ('Forza', 'Forza'),
        ('Speedmind', 'Speedmind'),
        ('FVR-1001', 'FVR-1001'),
        ('FVR-1011', 'FVR-1011'),
        ('REG-1200', 'REG-1200'),
    ], string="Modelo del Regulador de Voltaje")
    reguladorVoltaje_observacion = fields.Text(string="Observación del Regulador de Voltaje")

    # UPS
    model_UPS = fields.Selection([
        ('Forza', 'Forza'),
        ('NT-511', 'NT-511'),
        ('NT-1001', 'NT-1001'),
    ], string="Modelo del UPS")
    ups_observacion = fields.Text(string="Observación del UPS")

    # NVR
    nvr_equipment = fields.Char(string="NVR")
    nvr_observacion = fields.Text(string="Observación del NVR")

    # BIOMÉTRICO
    biometric_equipment = fields.Char(string="Biométrico")
    biometric_observacion = fields.Text(string="Observación del Biométrico")

    # Parte Electrica
    electric_equipment = fields.Char(string="Parte Eléctrica")
    electric_observacion = fields.Text(string="Observación de la Parte Eléctrica")

    # Internet
    ip_sucursal = fields.Char(string="IP Sucursal")
    internet_velocity= fields.Char(string="Velocidad Internet")
    type_internet = fields.Char(string="Tipo de Internet")
    internet_provider = fields.Char(string="Proveedor de Internet")
    internet_observacion = fields.Text(string="Observación del Internet")

    # Alarma
    model_alarm = fields.Char(string="Alarma")
    alarm_sensor1 = fields.Char(string="Tipo 1 de sensor de alarma")
    alarm_sensor2 = fields.Char(string="Tipo 2 de sensor de alarma")
    energizacion_alarm = fields.Char(string="Energización")
    teclado_alarm =fields.Char(string="Teclado")
    sirena_alarm = fields.Char(string="Sirena")
    code_alarm = fields.Char(string="Código de alarma")
    battery_alarm = fields.Char(string="Batería de la Alarma")
    panic_buttons_alarm = fields.Boolean(string="¿Botón de Pánico?")
    alarm_observacion = fields.Text(string="Observación del Sistema de Alarma")