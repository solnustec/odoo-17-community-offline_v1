# -*- coding: utf-8 -*-
"""
Extensión de account.move para sincronización offline POS Ecuador.

FLUJO DE SINCRONIZACIÓN:
========================

1. SERVIDOR OFFLINE:
   - Se crea factura en BORRADOR (draft) con SU propio número
   - Se genera clave de acceso de 49 dígitos (sin postear ni enviar al SRI)
   - Se sincroniza al servidor principal

2. SERVIDOR PRINCIPAL (ONLINE):
   - Se recibe la orden con la clave de acceso del offline
   - Se crea factura con SU propio número pero MISMA clave de acceso
   - Se POSTEA la factura (context: skip_l10n_ec_authorization=True)
   - El EDI envía al SRI usando la clave de acceso del OFFLINE
   - El SRI autoriza con esa clave

IMPORTANTE:
- El número de factura puede ser diferente entre OFFLINE y ONLINE
- Lo que DEBE ser igual es la CLAVE DE ACCESO (49 dígitos)
- Solo ONLINE envía al SRI
- No bloquear facturación en OFFLINE
"""
import logging
from odoo import models, api

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    """
    Extensión de account.move para sincronización POS offline Ecuador.

    Permite que facturas sincronizadas desde offline usen la MISMA clave
    de acceso que se generó en el servidor offline.
    """
    _inherit = 'account.move'

    def _l10n_ec_set_authorization_number(self):
        """
        Override para preservar la clave de acceso del offline durante el post.

        FLUJO:
        - Si context tiene 'skip_l10n_ec_authorization=True' y ya existe clave:
          → NO regenerar (usar la del offline)
        - De lo contrario:
          → Generar clave normalmente

        Esto es CRÍTICO para que el servidor principal use la misma clave
        que se generó en el servidor offline.
        """
        self.ensure_one()

        # Si viene del sync offline y ya tiene clave de acceso, NO regenerar
        if self.env.context.get('skip_l10n_ec_authorization'):
            if self.l10n_ec_authorization_number:
                _logger.info(
                    f'[SYNC] Preservando clave de acceso del offline para factura {self.name}: '
                    f'{self.l10n_ec_authorization_number[:20]}... (NO se regenera)'
                )
                return self.l10n_ec_authorization_number

        # Generar clave normalmente (comportamiento estándar)
        return super()._l10n_ec_set_authorization_number()

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override para preservar clave de acceso en creación.

        Cuando se crea una factura desde sync offline con clave de acceso
        ya establecida, se asegura de que no se sobrescriba.
        """
        # Guardar las claves de acceso que vienen en vals
        auth_numbers = {}
        for i, vals in enumerate(vals_list):
            if vals.get('l10n_ec_authorization_number'):
                auth_numbers[i] = vals['l10n_ec_authorization_number']

        moves = super().create(vals_list)

        # Restaurar claves de acceso si fueron sobrescritas
        if self.env.context.get('skip_l10n_ec_authorization') and auth_numbers:
            for i, move in enumerate(moves):
                if i in auth_numbers and move.l10n_ec_authorization_number != auth_numbers[i]:
                    move.with_context(skip_l10n_ec_authorization=True).write({
                        'l10n_ec_authorization_number': auth_numbers[i]
                    })
                    _logger.info(
                        f'[SYNC] Restaurada clave de acceso para {move.name}: '
                        f'{auth_numbers[i][:20]}...'
                    )

        return moves

    def _post(self, soft=True):
        """
        Override para preservar la clave de acceso del offline durante post.

        En el post normal, l10n_ec_edi regenera la clave de acceso.
        Necesitamos preservar la clave del offline si viene del sync.
        """
        # Guardar las claves de acceso ANTES del post
        auth_numbers = {}
        if self.env.context.get('skip_l10n_ec_authorization'):
            for move in self:
                if move.l10n_ec_authorization_number:
                    auth_numbers[move.id] = move.l10n_ec_authorization_number
                    _logger.info(
                        f'[SYNC] Preservando clave de acceso antes de post: '
                        f'{move.l10n_ec_authorization_number[:20]}...'
                    )

        # Ejecutar el post normal
        result = super()._post(soft=soft)

        # Restaurar las claves de acceso si fueron cambiadas
        if auth_numbers:
            for move in self:
                if move.id in auth_numbers:
                    expected_auth = auth_numbers[move.id]
                    if move.l10n_ec_authorization_number != expected_auth:
                        # Restaurar la clave de acceso original del offline
                        _logger.info(
                            f'[SYNC] Restaurando clave de acceso después de post: '
                            f'{expected_auth[:20]}...'
                        )
                        self.env.cr.execute(
                            "UPDATE account_move SET l10n_ec_authorization_number = %s WHERE id = %s",
                            (expected_auth, move.id)
                        )
                        move.invalidate_recordset(['l10n_ec_authorization_number'])

        return result

    def write(self, vals):
        """
        Override para prevenir sobrescritura de clave de acceso del offline.
        """
        # Si viene del sync offline y está intentando sobrescribir la clave
        if self.env.context.get('skip_l10n_ec_authorization'):
            # Preservar la clave de acceso existente si ya existe
            for move in self:
                if move.l10n_ec_authorization_number and 'l10n_ec_authorization_number' in vals:
                    if vals['l10n_ec_authorization_number'] != move.l10n_ec_authorization_number:
                        # Mantener la clave del offline
                        vals['l10n_ec_authorization_number'] = move.l10n_ec_authorization_number
                        _logger.info(
                            f'[SYNC] Previniendo sobrescritura de clave de acceso '
                            f'para {move.name}'
                        )

        return super().write(vals)
