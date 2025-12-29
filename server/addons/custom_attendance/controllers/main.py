# -- coding: utf-8 --
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import http, _
from odoo.http import request

import pytz

from odoo import api, http, models, tools, SUPERUSER_ID
from odoo.http import request, Response, ROUTING_KEYS, Stream
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class HrAttendanceCustom(http.Controller):

    @http.route('/api/attendance/create', type='json', auth='my_api_key', csrf=False)
    def create_attendance(self, records, **kwargs):
        results = []

        if not records or not isinstance(records, list):
            return {'status': 'error', 'message': 'Invalid input data'}

        attendances = []

        for record in records:
            nip = record.get('nip')
            attendances.append({
                "user_id": nip,
                "timestamp": self.convert_to_utc(record.get("timestamp")),
                "reference": record.get("reference", ""),
            })

        unique_criteria = [(att['user_id'], att['timestamp']) for att in attendances]

        existing_records = request.env['hr.attendance.general'].sudo().search([
            '|',
            ('user_id', 'in', [x[0] for x in unique_criteria]),
            ('timestamp', 'in', [x[1] for x in unique_criteria]),
        ])

        existing_set = set((rec.user_id, rec.timestamp) for rec in existing_records)

        new_attendances = [
            att for att in attendances
            if (att['user_id'], att['timestamp']) not in existing_set
        ]

        for attendance in new_attendances:
            try:
                request.env['hr.attendance.general'].sudo().create({
                    'user_id': attendance['user_id'],
                    'timestamp': attendance['timestamp'],
                    'reference': attendance.get('reference', ''),
                    'origen': 'Biométrico',
                })
                results.append({
                    'status': 'created',
                    'user_id': attendance['user_id'],
                    'timestamp': attendance['timestamp'],
                })
            except Exception as e:
                results.append({
                    'status': 'error',
                    'user_id': attendance['user_id'],
                    'timestamp': attendance['timestamp'],
                    'error': str(e),
                })
                return {
                    'status': 'error',
                    'message': 'Attendance records processed',
                    'results': results
                }

        for existing in existing_records:
            results.append({
                'status': 'existing',
                'user_id': existing.user_id,
                'timestamp': existing.timestamp,
                'user_id_exist': existing.user_id_exist,
                'color': existing.color,
            })

        return {
            'status': 'success',
            'message': 'Attendance records processed',
            'results': results
        }

    def add_mode_to_entry(self, entry):
        if entry:
            for entry in entry:
                if 'check_in' in entry:
                    entry['in_mode'] = 'biome'
                if 'check_out' in entry:
                    entry['out_mode'] = 'biome'
        return entry

    def join_references(self, text_1, text_2):
        value = ""
        if text_1 and text_2:
            value = "E: " + text_1 + ", S: " + text_2
        elif text_1 and not text_2:
            value = text_1
        elif text_2 and not text_1:
            value = text_2
        return value

    def convert_to_utc(self, hour_ecuador):
        hour_ecuador = self.str_to_datetime(hour_ecuador)
        # Zona horaria de Ecuador
        ecuador_tz = pytz.timezone('America/Guayaquil')
        utc_tz = pytz.utc

        # Si hora_ecuador no tiene zona horaria (naive), la localizamos
        if hour_ecuador.tzinfo is None:
            ecuador_time = ecuador_tz.localize(
                hour_ecuador)
        else:
            # Si ya tiene zona horaria, simplemente asumimos que es de Ecuador
            ecuador_time = hour_ecuador.astimezone(ecuador_tz)
        whitout_time_zone = ecuador_time.astimezone(utc_tz)
        return whitout_time_zone.replace(tzinfo=None)

    def str_to_datetime(self, date):
        if isinstance(date, str):
            try:
                # Intentar convertir el string a un objeto datetime
                date = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                raise ValueError(
                    "Fecha en formato incorrecto. El formato debe ser 'YYYY-MM-DD HH:MM:SS'.")

        return date


class BiometricController(http.Controller):

    @http.route('/iclock/cdata', type='http', auth='public', methods=['GET'], csrf=False)
    def iclock_ping(self):
        """Responde al ping del biométrico"""
        _logger.info("📡 GET recibido desde el biométrico (ping/check)")
        return "OK"

    @http.route('/iclock/cdata', type='http', auth='public', methods=['POST'], csrf=False)
    def iclock_datos(self):
        """
        Recibe datos desde dispositivos ZKTeco (SenseFace, SpeedFace, iFace, etc.)
        Formato de asistencia esperado:
            200     2025-10-07 17:12:09     4       4       0       0       0       0       0       0
        Formato OPLOG (ignorar):
            OPLOG 82    200    2025-11-12 17:31:33    add adms address    0    0    0
        """
        try:
            raw_data = request.httprequest.get_data()
            contenido = raw_data.decode(errors="ignore").strip()
            device_sn = (
                    request.httprequest.headers.get("SN")
                    or request.httprequest.args.get("SN")
                    or "unknown"
            )

            _logger.info("📡 POST recibido desde biométrico SN=%s", device_sn)
            _logger.debug("📝 Contenido crudo recibido:\n%s", contenido)

            if not contenido:
                _logger.warning("⚠️ No se recibieron datos desde el biométrico.")
                return "OK"

            results = []
            new_attendances = []
            existing_records = []
            skipped_oplog = 0

            for linea in contenido.splitlines():
                linea = linea.strip()
                if not linea:
                    continue

                # ═══════════════════════════════════════════════════════════
                # FILTRAR LÍNEAS OPLOG - Son logs del sistema, no asistencias
                # ═══════════════════════════════════════════════════════════
                if linea.upper().startswith("OPLOG"):
                    skipped_oplog += 1
                    _logger.debug("⏭️ Ignorando OPLOG: %s", linea)
                    continue

                campos = linea.split()
                if len(campos) < 2:
                    _logger.warning("⚠️ Línea inválida: %s", linea)
                    continue

                # Validar que el primer campo sea numérico (user_id)
                user_id = campos[0]
                if not user_id.isdigit():
                    _logger.warning("⚠️ user_id no numérico, ignorando: %s", linea)
                    continue

                # Construir fecha/hora
                fecha_hora = campos[1]
                if len(campos) > 2 and ":" in campos[2]:
                    fecha_hora = f"{fecha_hora} {campos[2]}"

                # Validar formato de fecha
                try:
                    timestamp = self.convert_to_utc(fecha_hora)
                except Exception as e:
                    _logger.error("❌ Error al convertir fecha '%s': %s", fecha_hora, str(e))
                    continue

                # Verificar duplicados
                existing = request.env["hr.attendance.general"].sudo().search([
                    ("user_id", "=", user_id),
                    ("timestamp", "=", timestamp)
                ], limit=1)

                if existing:
                    existing_records.append(existing)
                else:
                    new_attendances.append({
                        "user_id": user_id,
                        "timestamp": timestamp,
                        "reference": "biometric",
                        "device_sn": device_sn,
                    })

            # Crear nuevos registros en batch para mejor rendimiento
            AttendanceModel = request.env["hr.attendance.general"].sudo()
            for attendance in new_attendances:
                try:
                    AttendanceModel.create({
                        "user_id": attendance["user_id"],
                        "timestamp": attendance["timestamp"],
                        "reference": attendance["reference"],
                        "device_sn": attendance["device_sn"],
                        "origen": "Biométrico",
                    })
                    results.append({
                        "status": "created",
                        "user_id": attendance["user_id"],
                        "timestamp": attendance["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                    })
                except Exception as e:
                    _logger.error("❌ Error creando asistencia: %s", str(e))

            _logger.info(
                "✅ Procesamiento completado. Nuevos: %s, Existentes: %s, OPLOG ignorados: %s",
                len(new_attendances), len(existing_records), skipped_oplog
            )

            return "OK"

        except Exception as e:
            _logger.error("💥 Error procesando datos del biométrico: %s", str(e))
            return "ERROR"

    @http.route('/iclock/getrequest', type='http', auth='public', methods=['GET'], csrf=False)
    def getrequest(self):
        _logger.info("📡 GET /iclock/getrequest recibido (consulta de comandos)")

        return "OK"

    def convert_to_utc(self, hour_ecuador):
        hour_ecuador = self.str_to_datetime(hour_ecuador)
        # Zona horaria de Ecuador
        ecuador_tz = pytz.timezone('America/Guayaquil')
        utc_tz = pytz.utc

        # Si hora_ecuador no tiene zona horaria (naive), la localizamos
        if hour_ecuador.tzinfo is None:
            ecuador_time = ecuador_tz.localize(
                hour_ecuador)
        else:
            # Si ya tiene zona horaria, simplemente asumimos que es de Ecuador
            ecuador_time = hour_ecuador.astimezone(ecuador_tz)
        whitout_time_zone = ecuador_time.astimezone(utc_tz)
        return whitout_time_zone.replace(tzinfo=None)

    def str_to_datetime(self, date):
        if isinstance(date, str):
            try:
                date = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                raise ValueError(
                    "Fecha en formato incorrecto. El formato debe ser 'YYYY-MM-DD HH:MM:SS'.")

        return date
