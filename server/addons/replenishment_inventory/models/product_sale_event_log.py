# -*- coding: utf-8 -*-
"""
Event Log Particionado - Arquitectura de 4 Capas

Tabla de auditoría/histórico particionada por día.
Permite análisis histórico sin impactar el rendimiento de las tablas
principales.

Patrón: Particionado por rango de fechas (PARTITION BY RANGE)
"""

import logging
from datetime import date, timedelta
from odoo import models, fields, api
from odoo.tools import sql

_logger = logging.getLogger(__name__)


class ProductSaleEventLog(models.Model):
    """
    Log de eventos de venta/transferencia particionado por día.

    Esta tabla es append-only y se usa para:
    - Auditoría completa de eventos procesados
    - Análisis histórico (BI, reportes)
    - Debugging y troubleshooting

    Características:
    - Particionada por event_date para queries eficientes por rango
    - Las particiones antiguas se pueden archivar o eliminar fácilmente
    - No tiene índices pesados (optimizada para INSERT)
    """
    _name = 'product.sale.event.log'
    _description = 'Log de Eventos de Venta (Particionado)'
    _order = 'event_date desc, id desc'
    _log_access = False  # Deshabilitar write_date/create_uid para rendimiento

    # Datos del evento
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        index=True,
        ondelete='set null'  # Mantener log aunque se borre el producto
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén',
        index=True,
        ondelete='set null'
    )
    quantity = fields.Float(
        string='Cantidad',
        default=0.0
    )
    event_date = fields.Date(
        string='Fecha del Evento',
        required=True,
        index=True
    )
    event_hour = fields.Float(
        string='Hora del Evento',
        default=0.0
    )
    record_type = fields.Selection(
        selection=[
            ('sale', 'Venta'),
            ('transfer', 'Transferencia'),
        ],
        string='Tipo',
        default='sale'
    )
    is_legacy_system = fields.Boolean(
        string='Sistema Legado',
        default=False
    )

    # Referencias al origen
    source_model = fields.Char(
        string='Modelo Origen',
        help='Nombre del modelo que generó este evento'
    )
    source_id = fields.Integer(
        string='ID Origen',
        help='ID del registro original'
    )
    queue_id = fields.Integer(
        string='ID Cola',
        help='ID del registro en la cola antes de procesar'
    )

    # Metadata de procesamiento
    processed_at = fields.Datetime(
        string='Fecha Procesamiento',
        default=fields.Datetime.now
    )
    batch_id = fields.Char(
        string='ID Batch',
        help='Identificador del batch de procesamiento'
    )
    processing_time_ms = fields.Integer(
        string='Tiempo Procesamiento (ms)',
        default=0
    )

    def _auto_init(self):
        """
        Override para evitar que Odoo intente crear la tabla.

        Esta tabla se crea manualmente como particionada en init(),
        por lo que debemos saltar la creación automática si ya existe.
        """
        # Verificar si la tabla ya existe (particionada o no)
        self.env.cr.execute("""
            SELECT 1 FROM pg_class WHERE relname = 'product_sale_event_log'
        """)
        table_exists = self.env.cr.fetchone()

        if table_exists:
            # La tabla existe, solo ejecutar la lógica de columnas/índices
            # pero NO intentar crear la tabla
            return self._init_column_indexes()

        # Si no existe, dejar que Odoo la cree (será convertida a particionada en init())
        return super()._auto_init()

    def _init_column_indexes(self):
        """
        Inicializa columnas e índices sin crear la tabla.

        Cuando la tabla ya existe como particionada, Odoo no puede usar
        CREATE TABLE, pero sí puede agregar columnas o índices faltantes.
        """
        # No hacer nada especial - la tabla particionada ya tiene su estructura
        # Retornar True para indicar que no hubo cambios
        return True

    def init(self):
        """
        Configura la tabla particionada y crea particiones iniciales.

        NOTA: PostgreSQL no permite ALTER TABLE a particionado en tablas
        existentes, por lo que se crea la estructura en la instalación.
        """
        # Verificar si la tabla ya está particionada
        self.env.cr.execute("""
            SELECT relkind
            FROM pg_class
            WHERE relname = 'product_sale_event_log'
        """)
        result = self.env.cr.fetchone()

        if result and result[0] == 'p':
            # Ya es particionada, solo crear particiones nuevas
            _logger.info("Event log ya está particionado, verificando particiones")
            self._ensure_partitions_exist()
            return

        if result:
            # Tabla existe pero no es particionada - convertir
            _logger.warning(
                "product_sale_event_log existe pero no es particionada. "
                "Convirtiendo a tabla particionada..."
            )
            self._convert_to_partitioned()
            return

        # Crear tabla particionada desde cero
        self._create_partitioned_table()

    def _create_partitioned_table(self):
        """
        Crea la tabla particionada y las particiones iniciales.
        """
        _logger.info("Creando tabla product_sale_event_log particionada...")

        # Primero eliminar la tabla si existe (Odoo puede haberla creado)
        self.env.cr.execute("""
            DROP TABLE IF EXISTS product_sale_event_log CASCADE
        """)

        # Crear tabla particionada
        self.env.cr.execute("""
            CREATE TABLE product_sale_event_log (
                id SERIAL,
                product_id INTEGER REFERENCES product_product(id) ON DELETE SET NULL,
                warehouse_id INTEGER REFERENCES stock_warehouse(id) ON DELETE SET NULL,
                quantity FLOAT DEFAULT 0.0,
                event_date DATE NOT NULL,
                event_hour FLOAT DEFAULT 0.0,
                record_type VARCHAR(20) DEFAULT 'sale',
                is_legacy_system BOOLEAN DEFAULT FALSE,
                source_model VARCHAR(128),
                source_id INTEGER,
                queue_id INTEGER,
                processed_at TIMESTAMP DEFAULT NOW(),
                batch_id VARCHAR(64),
                processing_time_ms INTEGER DEFAULT 0,
                PRIMARY KEY (id, event_date)
            ) PARTITION BY RANGE (event_date)
        """)

        # Crear índices en la tabla padre (se heredan a particiones)
        self.env.cr.execute("""
            CREATE INDEX idx_event_log_product
            ON product_sale_event_log (product_id, event_date)
        """)

        self.env.cr.execute("""
            CREATE INDEX idx_event_log_warehouse
            ON product_sale_event_log (warehouse_id, event_date)
        """)

        self.env.cr.execute("""
            CREATE INDEX idx_event_log_batch
            ON product_sale_event_log (batch_id)
        """)

        # Crear particiones para los últimos 7 días y los próximos 7
        self._ensure_partitions_exist()

        _logger.info("Tabla product_sale_event_log creada con particionado")

    def _convert_to_partitioned(self):
        """
        Convierte la tabla existente (no particionada) a particionada.

        Proceso:
        1. Renombra la tabla existente
        2. Crea la nueva tabla particionada
        3. Copia los datos (si existen)
        4. Elimina la tabla antigua
        """
        _logger.info("Convirtiendo product_sale_event_log a tabla particionada...")

        # 1. Verificar si hay datos
        self.env.cr.execute("""
            SELECT COUNT(*) FROM product_sale_event_log
        """)
        row_count = self.env.cr.fetchone()[0]
        _logger.info("Registros existentes a migrar: %s", row_count)

        # 2. Renombrar tabla existente
        self.env.cr.execute("""
            ALTER TABLE product_sale_event_log
            RENAME TO product_sale_event_log_old
        """)

        # 3. Crear tabla particionada
        self.env.cr.execute("""
            CREATE TABLE product_sale_event_log (
                id SERIAL,
                product_id INTEGER REFERENCES product_product(id) ON DELETE SET NULL,
                warehouse_id INTEGER REFERENCES stock_warehouse(id) ON DELETE SET NULL,
                quantity FLOAT DEFAULT 0.0,
                event_date DATE NOT NULL,
                event_hour FLOAT DEFAULT 0.0,
                record_type VARCHAR(20) DEFAULT 'sale',
                is_legacy_system BOOLEAN DEFAULT FALSE,
                source_model VARCHAR(128),
                source_id INTEGER,
                queue_id INTEGER,
                processed_at TIMESTAMP DEFAULT NOW(),
                batch_id VARCHAR(64),
                processing_time_ms INTEGER DEFAULT 0,
                PRIMARY KEY (id, event_date)
            ) PARTITION BY RANGE (event_date)
        """)

        # 4. Crear índices
        self.env.cr.execute("""
            CREATE INDEX idx_event_log_product
            ON product_sale_event_log (product_id, event_date)
        """)
        self.env.cr.execute("""
            CREATE INDEX idx_event_log_warehouse
            ON product_sale_event_log (warehouse_id, event_date)
        """)
        self.env.cr.execute("""
            CREATE INDEX idx_event_log_batch
            ON product_sale_event_log (batch_id)
        """)

        # 5. Crear particiones
        self._ensure_partitions_exist()

        # 6. Si hay datos, copiarlos
        if row_count > 0:
            # Obtener fechas distintas para crear particiones específicas
            self.env.cr.execute("""
                SELECT DISTINCT event_date
                FROM product_sale_event_log_old
                WHERE event_date IS NOT NULL
            """)
            dates = [row[0] for row in self.env.cr.fetchall()]

            for event_date in dates:
                self._create_partition_for_date(event_date)

            # Copiar datos
            self.env.cr.execute("""
                INSERT INTO product_sale_event_log
                    (id, product_id, warehouse_id, quantity, event_date, event_hour,
                     record_type, is_legacy_system, source_model, source_id,
                     queue_id, processed_at, batch_id, processing_time_ms)
                SELECT id, product_id, warehouse_id, quantity,
                       COALESCE(event_date, CURRENT_DATE), event_hour,
                       record_type, is_legacy_system, source_model, source_id,
                       queue_id, processed_at, batch_id, processing_time_ms
                FROM product_sale_event_log_old
            """)
            _logger.info("Datos migrados: %s registros", row_count)

            # Actualizar secuencia del id
            self.env.cr.execute("""
                SELECT setval('product_sale_event_log_id_seq',
                              COALESCE((SELECT MAX(id) FROM product_sale_event_log), 0) + 1,
                              false)
            """)

        # 7. Eliminar tabla antigua
        self.env.cr.execute("""
            DROP TABLE product_sale_event_log_old CASCADE
        """)

        _logger.info("Conversión a tabla particionada completada")

    @api.model
    def _ensure_partitions_exist(self):
        """
        Asegura que existan particiones para el rango de fechas necesario.
        Crea particiones para los últimos 7 días y los próximos 7.
        """
        today = date.today()

        # Rango de particiones a crear
        start_date = today - timedelta(days=7)
        end_date = today + timedelta(days=7)

        current = start_date
        while current <= end_date:
            self._create_partition_for_date(current)
            current += timedelta(days=1)

    @api.model
    def _create_partition_for_date(self, partition_date):
        """
        Crea una partición para una fecha específica si no existe.

        Args:
            partition_date: Fecha para la partición
        """
        partition_name = f"product_sale_event_log_{partition_date.strftime('%Y%m%d')}"
        next_date = partition_date + timedelta(days=1)

        # Verificar si ya existe
        self.env.cr.execute("""
            SELECT 1
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = %s
        """, (partition_name,))

        if self.env.cr.fetchone():
            return  # Ya existe

        try:
            self.env.cr.execute(f"""
                CREATE TABLE {partition_name}
                PARTITION OF product_sale_event_log
                FOR VALUES FROM ('{partition_date}') TO ('{next_date}')
            """)
            _logger.info("Partición creada: %s", partition_name)
        except Exception as e:
            # Puede fallar si otro proceso la creó simultáneamente
            _logger.debug("No se pudo crear partición %s: %s", partition_name, e)

    @api.model
    def log_events(self, events, batch_id=None):
        """
        Registra múltiples eventos en el log.

        Args:
            events: Lista de diccionarios con los datos del evento
            batch_id: Identificador opcional del batch

        Returns:
            int: Número de eventos registrados
        """
        if not events:
            return 0

        # Verificar si la tabla está particionada
        if not self._is_table_partitioned():
            _logger.warning(
                "Event log no está particionado aún. "
                "Ejecute una actualización del módulo para activarlo."
            )
            return 0

        # Asegurar que existe la partición para hoy
        today = date.today()
        self._create_partition_for_date(today)

        # INSERT masivo
        values = []
        params = []
        for evt in events:
            values.append("""
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s)
            """)
            params.extend([
                evt.get('product_id'),
                evt.get('warehouse_id'),
                evt.get('quantity', 0),
                evt.get('event_date', today),
                evt.get('event_hour', 0),
                evt.get('record_type', 'sale'),
                evt.get('is_legacy_system', False),
                evt.get('source_model'),
                evt.get('source_id'),
                evt.get('queue_id'),
                batch_id,
                evt.get('processing_time_ms', 0)
            ])

        query = """
            INSERT INTO product_sale_event_log
                (product_id, warehouse_id, quantity, event_date, event_hour,
                 record_type, is_legacy_system, source_model, source_id,
                 queue_id, processed_at, batch_id, processing_time_ms)
            VALUES {}
        """.format(', '.join(values))

        try:
            self.env.cr.execute(query, params)
            return len(events)
        except Exception as e:
            _logger.error("Error insertando eventos en log: %s", e)
            return 0

    @api.model
    def _is_table_partitioned(self):
        """
        Verifica si la tabla está particionada.

        Returns:
            bool: True si la tabla está particionada
        """
        self.env.cr.execute("""
            SELECT relkind
            FROM pg_class
            WHERE relname = 'product_sale_event_log'
        """)
        result = self.env.cr.fetchone()
        return result and result[0] == 'p'

    @api.model
    def cleanup_old_partitions(self, days=90):
        """
        Elimina particiones más antiguas que N días.

        Args:
            days: Eliminar particiones más antiguas que N días

        Returns:
            int: Número de particiones eliminadas
        """
        cutoff_date = date.today() - timedelta(days=days)
        cutoff_str = cutoff_date.strftime('%Y%m%d')

        # Obtener particiones a eliminar
        self.env.cr.execute("""
            SELECT c.relname
            FROM pg_inherits i
            JOIN pg_class c ON c.oid = i.inhrelid
            JOIN pg_class p ON p.oid = i.inhparent
            WHERE p.relname = 'product_sale_event_log'
              AND c.relname < %s
            ORDER BY c.relname
        """, (f'product_sale_event_log_{cutoff_str}',))

        partitions_to_drop = [row[0] for row in self.env.cr.fetchall()]
        deleted = 0

        for partition in partitions_to_drop:
            try:
                self.env.cr.execute(f"DROP TABLE {partition}")
                _logger.info("Partición eliminada: %s", partition)
                deleted += 1
            except Exception as e:
                _logger.error("Error eliminando partición %s: %s", partition, e)

        return deleted

    @api.model
    def get_partition_stats(self):
        """
        Obtiene estadísticas de las particiones existentes.

        Returns:
            list: Lista de diccionarios con info de cada partición
        """
        self.env.cr.execute("""
            SELECT
                c.relname as partition_name,
                pg_size_pretty(pg_relation_size(c.oid)) as size,
                pg_relation_size(c.oid) as size_bytes,
                (SELECT COUNT(*) FROM pg_class c2
                 WHERE c2.relname = c.relname) as estimated_rows
            FROM pg_inherits i
            JOIN pg_class c ON c.oid = i.inhrelid
            JOIN pg_class p ON p.oid = i.inhparent
            WHERE p.relname = 'product_sale_event_log'
            ORDER BY c.relname DESC
        """)

        return [{
            'partition_name': row[0],
            'size': row[1],
            'size_bytes': row[2],
        } for row in self.env.cr.fetchall()]

    @api.model
    def cron_manage_partitions(self):
        """
        Cron job para gestión de particiones.

        - Crea particiones futuras (próximos 7 días)
        - Elimina particiones antiguas (> 90 días)
        """
        _logger.info("Iniciando gestión de particiones de event log")

        # Crear particiones futuras
        today = date.today()
        for i in range(1, 8):
            self._create_partition_for_date(today + timedelta(days=i))

        # Limpiar particiones antiguas
        deleted = self.cleanup_old_partitions(days=90)

        _logger.info(
            "Gestión de particiones completada: %s particiones eliminadas",
            deleted
        )

        return True
