# -*- coding: utf-8 -*-
from odoo import models, fields, api
import base64
import qrcode
from io import BytesIO
from dateutil.relativedelta import relativedelta


class AccountAssetExtension(models.Model):
    _inherit = "account.asset"

    # ==============================
    # CAMPOS Y QR EXISTENTES
    # ==============================

    qr_info = fields.Text(
        string="Información QR",
        compute="_compute_qr_info",
        store=True
    )

    @api.depends("asset_custodian_id", "asset_department_custodian_id", "date_start")
    def _compute_qr_info(self):
        for asset in self:
            lines = []
            if asset.asset_custodian_id:
                lines.append("Custodio: %s" % (asset.asset_custodian_id.name or ""))
            if asset.asset_department_custodian_id:
                lines.append("Departamento: %s" % (asset.asset_department_custodian_id.name or ""))
            if asset.date_start:
                lines.append("Fecha de Compra: %s" % asset.date_start.strftime("%Y-%m-%d"))
            asset.qr_info = "\n".join(lines) if lines else "SIN DATOS"

    def get_qr_code_image(self):
        """Genera la imagen QR en base64"""
        if not self.qr_info:
            return ""

        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(self.qr_info)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            buffer = BytesIO()
            img.save(buffer, format="PNG")
            qr_image = base64.b64encode(buffer.getvalue()).decode()

            return qr_image
        except Exception:
            return ""

    # ==============================
    # CAMPOS DE PRODUCTO / ASSET
    # ==============================

    product_id = fields.Many2one(
        "product.template",
        string="Producto asociado",
        domain="[('detailed_type', '=', 'activos_bienes')]",
        help="Selecciona un producto de tipo Activos/Bienes",
    )

    asset_product_type = fields.Selection(
        related="product_id.detailed_type",
        string="Tipo de Producto",
        store=True,
        readonly=True
    )

    asset_code = fields.Char(
        string="Código de Activo",
        readonly=True,
        copy=False,
        index=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        assets = super().create(vals_list)
        for asset in assets:
            if not asset.asset_code:
                last_asset = self.search([('asset_code', '!=', False)], order="id desc", limit=1)
                if last_asset and last_asset.asset_code.isdigit():
                    next_number = int(last_asset.asset_code) + 1
                else:
                    next_number = 1
                asset.asset_code = str(next_number).zfill(6)

            if not asset.product_id and asset.account_move_line_ids:
                aml = asset.account_move_line_ids.filtered(lambda l: l.product_id)[:1]
                if aml:
                    asset.product_id = aml.product_id.product_tmpl_id.id
                    asset.name = aml.product_id.name
        return assets

    def write(self, vals):
        res = super().write(vals)

        # Verificamos si el campo 'asset_custodian_id' fue modificado
        if 'asset_custodian_id' in vals and not self.asset_custodian_id:
            # Si no tiene un custodio asignado
            if not self.asset_custodian_id:
                # Crear la asignación pendiente
                self.env["asset.assignment"].create({
                    "asset_id": self.id,
                    "custodian_id": vals.get('asset_custodian_id'),
                    "assign_date": fields.Date.context_today(self),
                    "note": "Asignación generada desde el registro del activo",
                    "state": "pending",  # Estado pendiente hasta que el custodio firme
                    "signed_by_custodian": False,  # Custodio aún no ha firmado
                })

                # Actualizamos el custodio del activo
                self.asset_custodian_id = vals.get('asset_custodian_id')

                # Enviar la notificación al custodio
                self._send_checklist_notification()

        return res

    def _send_checklist_notification(self):
        """Enviar la notificación al custodio para que confirme la asignación"""
        # Aseguramos que se envíe una notificación usando la plantilla de CheckList
        notification = self.env["mail.activity"].create({
            "activity_type_id": self.env.ref('mail.mail_activity_data_todo').id,  # Tipo de actividad (checklist)
            "res_model": "account.asset",
            "res_id": self.id,
            "summary": "Confirmación de Asignación de Custodio",
            "user_id": self.asset_custodian_id.user_id.id,  # Asignar al custodio
            "note": "Por favor complete el CheckList para confirmar la asignación del activo.",
        })
        notification.sudo().action_done()

    @api.onchange("product_id")
    def _onchange_product_id_set_name(self):
        if self.product_id:
            self.name = self.product_id.name

    class_id = fields.Many2one(
        related="product_id.class_id",
        string="Clase",
        store=True,
        index=True,
        readonly=True
    )
    subclass_id = fields.Many2one(
        related="product_id.subclass_id",
        string="Subclase",
        store=True,
        index=True,
        readonly=True
    )
    asset_brand_id = fields.Many2one(
        related="product_id.asset_brand_id",
        comodel_name="asset.brand",
        string="Marca",
        store=True,
        index=True,
        readonly=True
    )
    asset_model = fields.Char(
        related="product_id.asset_model",
        string="Modelo",
        readonly=True
    )
    asset_serial = fields.Char(
        related="product_id.asset_serial",
        string="Serie",
        readonly=True
    )
    asset_specification = fields.Char(
        related="product_id.asset_specification",
        string="Especificaciones",
        readonly=True
    )
    asset_prev_code = fields.Char(
        string="Cod. Anterior"
    )
    asset_material = fields.Char(
        related="product_id.asset_material",
        string="Material Producto",
        readonly=True
    )
    asset_color = fields.Char(
        related="product_id.asset_color",
        string="Color Producto",
        readonly=True
    )
    asset_status = fields.Selection(
        [
            ('operativo', 'OPERATIVO'),
            ('no_operativo', 'NO OPERATIVO'),
        ],
        string="Estado del Activo",
        default='operativo',
        required=True,
        help="Estado operativo del activo. Por defecto, todo activo nuevo se marca como OPERATIVO.",
    )

    asset_custodian_id = fields.Many2one(
        "hr.employee",
        string="Custodio",
        store=True,
        index=True,
        help="Empleado responsable de este activo.",
        readonly=True
    )
    asset_custodian_identification = fields.Char(
        related="asset_custodian_id.identification_id",
        string="Cédula del Custodio",
        store=True,
        index=True,
        readonly=True
    )
    asset_sucursal_custodian_id = fields.Many2one(
        'hr.work.location',
        string="Sucursal",
        related='asset_custodian_id.work_location_id',
        store=True,
        index=True,
        readonly=True
    )
    asset_department_custodian_id = fields.Many2one(
        'hr.department',
        string="Departamento",
        related='asset_custodian_id.department_id',
        store=True,
        index=True,
        readonly=True
    )
    asset_location = fields.Char(
        string="Ubicación Física",
        help="Ubicación física donde se encuentra el activo."
    )

    def validate(self):
        res = super().validate()
        for asset in self:
            if asset.asset_custodian_id:
                existing = self.env["asset.assignment"].search(
                    [("asset_id", "=", asset.id)],
                    limit=1
                )
                if not existing:
                    self.env["asset.assignment"].create({
                        "asset_id": asset.id,
                        "custodian_id": asset.asset_custodian_id.id,
                        "note": "Asignación inicial creada al confirmar el activo",
                    })
        return res

    def action_open_mass_transfer_wizard(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Transferencia Masiva",
            "res_model": "asset.mass.transfer.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_asset_ids": [(6, 0, self.ids)]
            },
        }

    # ==============================
    # MÉTODO PARA IMPRIMIR EN ZPL
    # ==============================

    def action_print_zpl(self):
        """Generar archivo ZPL descargable para impresora Zebra"""
        self.ensure_one()

        zpl_code = f"""
^XA
^PW472
^LL236
^FO20,20^A0N,25,25^FD{self.name or ''}^FS
^FO250,20^A0N,20,20^FD{self.asset_code or ''}^FS
^FO20,60^BQN,2,5
^FDMA,{self.qr_info or 'SIN_DATOS'}^FS
^XZ
"""
        return {
            "type": "ir.actions.act_url",
            "url": f"/asset/print_zpl/{self.id}",
            "target": "self",
        }

    # ============================================================
    # CAMPOS DE CONTROL DE DEPRECIACIÓN
    # ============================================================

    last_depreciation_date = fields.Date(
        string="Última Fecha Depreciada",
        compute="_compute_depreciation_progress",
        store=True,
        help="Muestra la fecha de la última línea de depreciación contabilizada."
    )

    depreciation_count = fields.Integer(
        string="N° de Depreciaciones Realizadas",
        compute="_compute_depreciation_progress",
        store=True,
        help="Cantidad de depreciaciones contabilizadas para este activo."
    )

    @api.depends(
        "depreciation_line_ids.move_check",
        "depreciation_line_ids.type",
        "depreciation_line_ids.line_date"
    )
    def _compute_depreciation_progress(self):
        for asset in self:
            # Solo líneas de tipo 'depreciate' con asiento contable realizado
            lines = asset.depreciation_line_ids.filtered(
                lambda l: l.type == "depreciate" and l.move_check
            )

            if lines:
                last_line = lines.sorted("line_date")[-1]
                asset.last_depreciation_date = last_line.line_date
                asset.depreciation_count = len(lines)
            else:
                asset.last_depreciation_date = False
                asset.depreciation_count = 0

    # ============================================================
    # OVERRIDE PARA DEPRECIACIÓN PARCIAL POR DÍAS (NORMA ECUATORIANA)
    # ============================================================

    def _compute_depreciation_table_lines(
            self, table, depreciation_start_date, depreciation_stop_date, line_dates
    ):
        """
        Ajuste para depreciación:
        - Si compra el 1ro del mes: depreciación mensual fija, último mes ajusta residuales
        - Si compra otro día: primer mes proporcional por días, resto fijo, último mes ajusta
        """
        # Ejecutamos el procedimiento estándar primero
        super()._compute_depreciation_table_lines(
            table, depreciation_start_date, depreciation_stop_date, line_dates
        )

        # Si no hay líneas de depreciación, salir
        if not table or not table[0].get("lines"):
            return table

        currency = self.company_id.currency_id
        start = self.date_start

        # Valor mensual fijo
        meses_totales = self.method_number * 12
        valor_mensual_fijo = currency.round(self.depreciation_base / meses_totales)

        # Recolectar todas las líneas de todos los años fiscales
        all_lines = []
        for entry in table:
            all_lines.extend(entry.get("lines", []))

        if not all_lines:
            return table

        # --- CASO 1: Compra el primer día del mes ---
        if start.day == 1:
            # Todos los meses tienen depreciación fija
            total_asignado = 0.0
            for i, line in enumerate(all_lines):
                if i < len(all_lines) - 1:
                    # Meses normales: valor fijo
                    line["amount"] = valor_mensual_fijo
                    total_asignado += valor_mensual_fijo
                else:
                    # Último mes: ajustar para cuadrar con la base depreciable
                    line["amount"] = currency.round(self.depreciation_base - total_asignado)

        # --- CASO 2: Compra en día diferente al primero ---
        else:
            import calendar
            _, ultimo_dia_real = calendar.monthrange(start.year, start.month)
            dias_restantes = ultimo_dia_real - start.day + 1

            # Mes contable de 30 días (Ecuador)
            dias_mes_contable = 30
            valor_por_dia = valor_mensual_fijo / dias_mes_contable

            # Depreciación proporcional del primer mes
            depreciacion_primer_mes = currency.round(valor_por_dia * dias_restantes)

            total_asignado = 0.0
            for i, line in enumerate(all_lines):
                if i == 0:
                    # Primer mes: proporcional por días
                    line["amount"] = depreciacion_primer_mes
                    total_asignado += depreciacion_primer_mes
                elif i < len(all_lines) - 1:
                    # Meses intermedios: valor fijo
                    line["amount"] = valor_mensual_fijo
                    total_asignado += valor_mensual_fijo
                else:
                    # Último mes: ajustar residual
                    line["amount"] = currency.round(self.depreciation_base - total_asignado)

        # Recalcular remaining_value para todas las líneas
        remaining = self.depreciation_base
        for line in all_lines:
            remaining -= line["amount"]
            line["remaining_value"] = currency.round(remaining)

        return table

    def _compute_depreciation_amount_per_fiscal_year(
            self, table, line_dates, depreciation_start_date, depreciation_stop_date
    ):
        """
        Calcula el monto de depreciación por año fiscal:
        - Primer día del mes: depreciación mensual fija
        - Otro día: primer mes proporcional, resto fijo
        - Último período siempre ajusta residuales
        """
        self.ensure_one()
        currency = self.company_id.currency_id

        # Valor mensual fijo
        meses_totales = self.method_number * 12
        valor_mensual_fijo = currency.round(self.depreciation_base / meses_totales)

        start = self.date_start
        residual = self.depreciation_base

        # Calcular depreciación del primer mes
        if start.day == 1:
            # Compra el primero: mes completo
            depreciacion_primer_mes = valor_mensual_fijo
        else:
            # Compra otro día: proporcional
            import calendar
            _, ultimo_dia_real = calendar.monthrange(start.year, start.month)
            dias_restantes = ultimo_dia_real - start.day + 1
            valor_por_dia = valor_mensual_fijo / 30  # Mes contable Ecuador
            depreciacion_primer_mes = currency.round(valor_por_dia * dias_restantes)

        # Asignar montos a cada año fiscal
        is_first_entry = True
        total_entries = len(table)

        for idx, entry in enumerate(table):
            is_last_entry = (idx == total_entries - 1)

            if is_first_entry:
                # Primer año fiscal
                entry["period_amount"] = valor_mensual_fijo
                entry["fy_amount"] = depreciacion_primer_mes
                entry["day_amount"] = 0
                residual -= depreciacion_primer_mes
                is_first_entry = False

            elif is_last_entry:
                # Último año fiscal: asignar todo el residual restante
                entry["period_amount"] = valor_mensual_fijo
                entry["fy_amount"] = currency.round(residual)
                entry["day_amount"] = 0
                residual = 0

            else:
                # Años intermedios: 12 meses fijos
                meses_en_fy = 12
                fy_amount = currency.round(valor_mensual_fijo * meses_en_fy)

                # No exceder el residual disponible
                if fy_amount > residual:
                    fy_amount = residual

                entry["period_amount"] = valor_mensual_fijo
                entry["fy_amount"] = fy_amount
                entry["day_amount"] = 0
                residual -= fy_amount

        return table

    # ============================================================
    # CAMPOS DE DEPRECIACIONES HISTÓRICAS DINÁMICAS (3 MESES)
    # ============================================================

    dep_label_prev2 = fields.Char(string="Mes -2", compute="_compute_last3_deps", store=True)
    dep_label_prev1 = fields.Char(string="Mes -1", compute="_compute_last3_deps", store=True)
    dep_label_curr = fields.Char(string="Mes 0", compute="_compute_last3_deps", store=True)

    dep_prev2 = fields.Monetary(string="Antepenúltima Depreciación", compute="_compute_last3_deps", store=True)
    dep_prev1 = fields.Monetary(string="Penúltima Depreciación", compute="_compute_last3_deps", store=True)
    dep_curr = fields.Monetary(string="Ultima Depreciación", compute="_compute_last3_deps", store=True)

    @api.depends("depreciation_line_ids.amount",
                 "depreciation_line_ids.line_date",
                 "depreciation_line_ids.move_check")
    def _compute_last3_deps(self):
        for asset in self:

            # 1) Tomar depreciaciones contabilizadas reales
            posted = asset.depreciation_line_ids.filtered(
                lambda l: l.type == "depreciate" and l.move_check
            )

            if not posted:
                asset.dep_curr = asset.dep_prev1 = asset.dep_prev2 = 0
                asset.dep_label_curr = asset.dep_label_prev1 = asset.dep_label_prev2 = ""
                continue

            # 2) Tomar la ÚLTIMA depreciación registrada
            last_line = posted.sorted("line_date")[-1]
            m0 = last_line.line_date
            m1 = m0 - relativedelta(months=1)
            m2 = m0 - relativedelta(months=2)

            def get_amount(date_ref):
                line = posted.filtered(
                    lambda l: l.line_date.year == date_ref.year
                              and l.line_date.month == date_ref.month
                )
                return line.amount if line else 0

            asset.dep_curr = get_amount(m0)
            asset.dep_prev1 = get_amount(m1)
            asset.dep_prev2 = get_amount(m2)

            asset.dep_label_curr = m0.strftime("%B %Y").capitalize()
            asset.dep_label_prev1 = m1.strftime("%B %Y").capitalize()
            asset.dep_label_prev2 = m2.strftime("%B %Y").capitalize()
