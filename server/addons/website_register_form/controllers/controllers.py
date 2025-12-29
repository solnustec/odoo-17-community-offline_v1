from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.http import request, route
import re
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class AuthSignupExtended(AuthSignupHome):

    def get_auth_signup_qcontext(self):
        qcontext = super(AuthSignupExtended, self).get_auth_signup_qcontext()
        qcontext.update({
            'identification_types': request.env['l10n_latam.identification.type'].sudo().search([]),
            'vat': qcontext.get('vat', ''),
            'l10n_latam_identification_type_id': qcontext.get('l10n_latam_identification_type_id', ''),
        })
        return qcontext

    def _find_existing_partner_by_vat(self, vat, identification_type_id):
        try:
            if vat and identification_type_id:
                return request.env['res.partner'].sudo().search([
                    ('vat', '=', vat),
                    ('l10n_latam_identification_type_id', '=', int(identification_type_id))
                ], limit=1)
            return None
        except Exception as e:
            _logger.error("Error in _find_existing_partner_by_vat: %s", str(e))
            return None

    def _handle_existing_partner(self, existing_partner, login, kw, vat, identification_type_id):
        try:
            user_values = {
                'login': login,
                'password': kw.get('password'),
                'name': kw.get('name', '').strip(),
            }

            partner_values = {
                'name': kw.get('name', '').strip(),
                'email': login,
                'country_id': 63,
                'vat': vat,
                'l10n_latam_identification_type_id': int(
                    identification_type_id) if identification_type_id and identification_type_id.isdigit() else False,
            }

            existing_partner.write(partner_values)

            if existing_partner.user_ids:
                existing_user = existing_partner.user_ids[0]
                existing_user.write(user_values)
            else:
                user_values['partner_id'] = existing_partner.id
                request.env['res.users'].sudo().with_context(
                    no_reset_password=True,
                    create_user=True
                ).create(user_values)

            request.env.cr.commit()

            auth_result = request.session.authenticate(request.db, login, kw.get('password'))
            if not auth_result:
                raise UserError("Authentication failed after account update")

            return request.redirect('/')

        except Exception as e:
            _logger.error("Error updating existing partner: %s", str(e))
            raise

    @route('/web/signup', type='http', auth='public', website=True, sitemap=False)
    def web_auth_signup(self, *args, **kw):
        try:
            vat = (kw.get('vat') or '').strip()
            identification_type_id = kw.get('l10n_latam_identification_type_id')
            login = (kw.get('login') or '').strip().lower()
            name = (kw.get('name') or '').strip()
            password = kw.get('password')

            existing_user = request.env['res.users'].sudo().search([('login', '=', login)], limit=1)
            if existing_user:
                return request.render('auth_signup.signup', {
                    'error': 'Ya existe un usuario registrado con este correo electrónico.',
                    'vat': vat,
                    'l10n_latam_identification_type_id': identification_type_id,
                    'identification_types': request.env['l10n_latam.identification.type'].sudo().search([]),
                })

            if not all([login, name, password]):
                return request.render('auth_signup.signup', {
                    'error': 'Todos los campos son requeridos.',
                    'vat': vat,
                    'l10n_latam_identification_type_id': identification_type_id,
                    'identification_types': request.env['l10n_latam.identification.type'].sudo().search([]),
                })

            identification_type = None
            if identification_type_id and identification_type_id.isdigit():
                identification_type = request.env['l10n_latam.identification.type'].sudo().browse(
                    int(identification_type_id))

            if identification_type:
                if identification_type.name.lower() == 'cédula':
                    if not re.fullmatch(r'\d{10}', vat):
                        return request.render('auth_signup.signup', {
                            'error': 'La cédula debe tener exactamente 10 dígitos.',
                            'vat': vat,
                            'l10n_latam_identification_type_id': identification_type_id,
                            'identification_types': request.env['l10n_latam.identification.type'].sudo().search([]),
                        })
                elif identification_type.name.lower() == 'ruc':
                    if not (re.fullmatch(r'\d{13}', vat) and vat.endswith('001')):
                        return request.render('auth_signup.signup', {
                            'error': 'El RUC debe tener 13 dígitos y terminar en 001.',
                            'vat': vat,
                            'l10n_latam_identification_type_id': identification_type_id,
                            'identification_types': request.env['l10n_latam.identification.type'].sudo().search([]),
                        })

            existing_partner = self._find_existing_partner_by_vat(vat, identification_type_id)

            if existing_partner:
                return self._handle_existing_partner(existing_partner, login, kw, vat, identification_type_id)

            # Proceed with normal signup for new users
            response = super(AuthSignupExtended, self).web_auth_signup(*args, **kw)

            # Assign additional fields to partner for new registrations
            user = request.env['res.users'].sudo().search([('login', '=', login)], limit=1)
            if user and user.partner_id:
                request.session['partner_id'] = user.partner_id.id
                partner = user.partner_id
                vals = {
                    'country_id': 63,
                }
                if vat:
                    vals['vat'] = vat
                if identification_type_id and identification_type_id.isdigit():
                    vals['l10n_latam_identification_type_id'] = int(identification_type_id)

                try:
                    partner.write(vals)
                    request.env.cr.commit()
                except Exception as e:
                    _logger.error("Error updating new partner: %s", str(e))

            return response


        except Exception as e:
            _logger.error("Signup error: %s", str(e))
            return request.render('auth_signup.signup', {
                'error': 'Ocurrió un error durante el registro. Por favor intente nuevamente.',
                'vat': vat,
                'l10n_latam_identification_type_id': identification_type_id,
                'identification_types': request.env['l10n_latam.identification.type'].sudo().search([]),
            })
