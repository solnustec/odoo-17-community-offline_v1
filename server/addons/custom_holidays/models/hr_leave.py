# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    # Tracking fields for group validation
    first_validator_id = fields.Many2one(
        'res.users',
        string="Primera Validacion Por",
        readonly=True,
        copy=False,
        tracking=True,
    )
    first_validation_date = fields.Datetime(
        string="Fecha Primera Validacion",
        readonly=True,
        copy=False,
    )
    second_validator_id = fields.Many2one(
        'res.users',
        string="Segunda Validacion Por",
        readonly=True,
        copy=False,
        tracking=True,
    )
    second_validation_date = fields.Datetime(
        string="Fecha Segunda Validacion",
        readonly=True,
        copy=False,
    )

    # Computed field to check if group validation is enabled
    use_group_validation = fields.Boolean(
        compute='_compute_use_group_validation',
        store=False,
    )

    # Computed fields to check current user's group membership
    is_user_first_validator = fields.Boolean(
        compute='_compute_user_validator_groups',
        store=False,
    )
    is_user_second_validator = fields.Boolean(
        compute='_compute_user_validator_groups',
        store=False,
    )

    @api.depends('holiday_status_id', 'holiday_status_id.leave_validation_type',
                 'holiday_status_id.first_validator_group_id')
    def _compute_use_group_validation(self):
        for leave in self:
            leave_type = leave.holiday_status_id
            leave.use_group_validation = bool(
                leave_type and
                leave_type.leave_validation_type == 'both' and
                leave_type.first_validator_group_id and
                leave_type.second_validator_group_id
            )

    @api.depends('holiday_status_id', 'holiday_status_id.first_validator_group_id',
                 'holiday_status_id.second_validator_group_id')
    def _compute_user_validator_groups(self):
        """Compute if current user is in first or second validator group"""
        for leave in self:
            leave_type = leave.holiday_status_id
            user_id = self.env.user.id

            # Check first validator group
            if leave_type and leave_type.first_validator_group_id:
                leave.is_user_first_validator = user_id in leave_type.first_validator_group_id.users.ids
            else:
                leave.is_user_first_validator = False

            # Check second validator group
            if leave_type and leave_type.second_validator_group_id:
                leave.is_user_second_validator = user_id in leave_type.second_validator_group_id.users.ids
            else:
                leave.is_user_second_validator = False

    def _check_user_in_first_validator_group(self):
        """Check if current user belongs to first validator group"""
        self.ensure_one()
        leave_type = self.holiday_status_id
        if not leave_type.first_validator_group_id:
            return False
        # Check using group's user_ids
        return self.env.user.id in leave_type.first_validator_group_id.users.ids

    def _check_user_in_second_validator_group(self):
        """Check if current user belongs to second validator group"""
        self.ensure_one()
        leave_type = self.holiday_status_id
        if not leave_type.second_validator_group_id:
            return False
        # Check using group's user_ids
        return self.env.user.id in leave_type.second_validator_group_id.users.ids

    def _is_group_validation_configured(self):
        """Check if group validation is configured for this leave type"""
        self.ensure_one()
        leave_type = self.holiday_status_id
        return bool(
            leave_type and
            leave_type.leave_validation_type == 'both' and
            leave_type.first_validator_group_id and
            leave_type.second_validator_group_id
        )

    def action_confirm(self):
        """
        Override to handle group-based validation.
        If user is in first validator group, skip 'confirm' and go directly to 'validate1'.
        """
        for leave in self:
            # Check if group validation is configured
            if leave._is_group_validation_configured():
                leave_type = leave.holiday_status_id

                # Check if user belongs to first validator group
                if leave._check_user_in_first_validator_group():
                    # Skip confirm, go directly to validate1
                    leave.write({
                        'state': 'validate1',
                        'first_validator_id': self.env.user.id,
                        'first_validation_date': fields.Datetime.now(),
                    })
                    # Send activity to second validators if needed
                    leave._create_second_validation_activity()
                else:
                    raise UserError(_(
                        "No tienes permisos para crear solicitudes de ausencia de tipo '%s'. "
                        "Debes pertenecer al grupo '%s'."
                    ) % (leave_type.name, leave_type.first_validator_group_id.full_name))
            else:
                # Standard Odoo behavior
                super(HrLeave, leave).action_confirm()

        return True

    def action_approve(self):
        """
        Override to handle the first approval step for group validation.
        For group validation, first approval is automatic at confirm.
        """
        for leave in self:
            # Check if group validation is configured and leave is in confirm state
            if leave._is_group_validation_configured() and leave.state == 'confirm':
                leave_type = leave.holiday_status_id

                # Check if user belongs to first validator group
                if leave._check_user_in_first_validator_group():
                    leave.write({
                        'state': 'validate1',
                        'first_validator_id': self.env.user.id,
                        'first_validation_date': fields.Datetime.now(),
                    })
                    leave._create_second_validation_activity()
                else:
                    raise UserError(_(
                        "No tienes permisos para aprobar la primera validacion. "
                        "Debes pertenecer al grupo '%s'."
                    ) % leave_type.first_validator_group_id.full_name)
            else:
                super(HrLeave, leave).action_approve()

        return True

    def action_validate(self):
        """
        Override to handle the second approval step for group validation.
        Only users in second_validator_group can validate.
        """
        for leave in self:
            # Check if group validation is configured
            if leave._is_group_validation_configured():
                leave_type = leave.holiday_status_id

                if leave.state != 'validate1':
                    raise UserError(_(
                        "Esta solicitud debe estar en estado 'Primera Aprobacion' "
                        "para realizar la segunda validacion."
                    ))

                # Check if user belongs to second validator group
                if leave._check_user_in_second_validator_group():
                    # Perform standard validation
                    result = super(HrLeave, leave).action_validate()
                    # Record who validated and when
                    leave.write({
                        'second_validator_id': self.env.user.id,
                        'second_validation_date': fields.Datetime.now(),
                    })
                    return result
                else:
                    raise UserError(_(
                        "No tienes permisos para realizar la segunda validacion. "
                        "Debes pertenecer al grupo '%s'."
                    ) % leave_type.second_validator_group_id.full_name)
            else:
                return super(HrLeave, leave).action_validate()

        return True

    def action_refuse(self):
        """
        Override to allow second validators to refuse requests.
        Only restricts for validate1 state with group validation.
        """
        for leave in self:
            # Only check permissions for group validation in validate1 state
            if leave._is_group_validation_configured() and leave.state == 'validate1':
                leave_type = leave.holiday_status_id

                # Check if user belongs to second validator group
                if not leave._check_user_in_second_validator_group():
                    raise UserError(_(
                        "No tienes permisos para rechazar esta solicitud. "
                        "Debes pertenecer al grupo '%s'."
                    ) % leave_type.second_validator_group_id.full_name)

        return super(HrLeave, self).action_refuse()

    def action_cancel(self):
        """
        Override to allow second validators to cancel validated leaves.
        For group validation, second validators can cancel any leave.
        """
        for leave in self:
            # Check if group validation is configured
            if leave._is_group_validation_configured():
                # Check if user belongs to second validator group
                if leave._check_user_in_second_validator_group():
                    # Allow cancel - use 'refuse' state (no 'cancel' state exists)
                    leave._remove_resource_leave()
                    if leave.meeting_id:
                        leave.meeting_id.unlink()
                    leave.with_context(from_cancel_wizard=True).write({
                        'state': 'refuse',
                        'active': False
                    })
                else:
                    raise UserError(_(
                        "No tienes permisos para cancelar esta solicitud. "
                        "Debes pertenecer al grupo '%s'."
                    ) % leave.holiday_status_id.second_validator_group_id.full_name)
            else:
                # Standard Odoo behavior - opens cancel wizard
                return super(HrLeave, leave).action_cancel()

        return True

    def _create_second_validation_activity(self):
        """Create activity for second validators when request reaches validate1 state"""
        self.ensure_one()
        leave_type = self.holiday_status_id

        if not leave_type.second_validator_group_id:
            return

        # Get users from second validator group
        second_validators = leave_type.second_validator_group_id.users

        if second_validators:
            # Create activity for the first available validator
            activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
            if activity_type:
                self.activity_schedule(
                    activity_type_id=activity_type.id,
                    summary=_("Segunda validacion requerida"),
                    note=_("La solicitud de ausencia de %s requiere segunda validacion.") % self.employee_id.name,
                    user_id=second_validators[0].id,
                )
