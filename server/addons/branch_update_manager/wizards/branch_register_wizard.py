# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BranchRegisterWizard(models.TransientModel):
    """Wizard para registrar una sucursal en el servidor central."""
    _name = 'branch.register.wizard'
    _description = 'Branch Registration Wizard'

    cloud_url = fields.Char(
        string='Cloud Server URL',
        required=True,
        help='URL del servidor central (ej: https://erp.empresa.com)'
    )
    registration_code = fields.Char(
        string='Registration Code',
        required=True,
        help='Código de registro proporcionado por el administrador'
    )
    result_message = fields.Text(
        string='Result',
        readonly=True
    )
    state = fields.Selection([
        ('form', 'Form'),
        ('result', 'Result'),
    ], default='form')

    def action_register(self):
        """Registra la sucursal en el servidor central."""
        self.ensure_one()

        result = self.env['branch.update.agent'].register_branch(
            self.cloud_url,
            self.registration_code
        )

        if result.get('success'):
            self.write({
                'state': 'result',
                'result_message': _(
                    'Branch registered successfully!\n\n'
                    'Branch Name: %s\n'
                    'The branch is now connected to the central server and '
                    'will automatically receive updates.'
                ) % result.get('branch_name', 'Unknown'),
            })
        else:
            self.write({
                'state': 'result',
                'result_message': _(
                    'Registration failed!\n\n'
                    'Error: %s\n\n'
                    'Please verify the registration code and try again.'
                ) % result.get('message', 'Unknown error'),
            })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'branch.register.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class BranchRegisterWizardView(models.TransientModel):
    """Vista del wizard."""
    _inherit = 'branch.register.wizard'

    @api.model
    def _get_wizard_views(self):
        return '''
        <record id="view_branch_register_wizard_form" model="ir.ui.view">
            <field name="name">branch.register.wizard.form</field>
            <field name="model">branch.register.wizard</field>
            <field name="arch" type="xml">
                <form>
                    <group invisible="state != 'form'">
                        <group>
                            <field name="cloud_url" placeholder="https://erp.empresa.com"/>
                            <field name="registration_code"/>
                        </group>
                    </group>
                    <group invisible="state != 'result'">
                        <field name="result_message" nolabel="1"/>
                    </group>
                    <field name="state" invisible="1"/>
                    <footer>
                        <button name="action_register" type="object"
                                string="Register" class="btn-primary"
                                invisible="state != 'form'"/>
                        <button string="Close" class="btn-secondary" special="cancel"/>
                    </footer>
                </form>
            </field>
        </record>
        '''
