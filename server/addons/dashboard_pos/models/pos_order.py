# -*- coding: utf-8 -*-
################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#    Copyright (C) 2022-TODAY Cybrosys Technologies (<https://www.cybrosys.com>)
#    Author: Subina P (odoo@cybrosys.com)
#
#    This program is free software: you can modify
#    it under the terms of the GNU Affero General Public License (AGPL) as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
################################################################################
import pytz
from datetime import datetime
from odoo import api, models, fields
from odoo.exceptions import ValidationError


class PosOrder(models.Model):
    _inherit = 'pos.order'


    # def create(self, vals):
    #     # Llama al método create de la clase padre para crear el registro en pos.order
    #     order = super(PosOrder, self).create(vals)
    #     print("se llaa al metodo create aaca ")
    #     print("se llaa al metodo c
    #
    #     return order


    @api.model
    def get_department(self, option):
        """ Function to get the order details of company wise"""

        company_id = self.env.company.id
        # noinspection PyInterpreter
        if option == 'pos_hourly_sales':

            user_tz = self.env.user.tz if self.env.user.tz else pytz.UTC
            query = '''select  EXTRACT(hour FROM date_order at time zone 'utc' at time zone '{}') 
                       as date_month,sum(amount_total) from pos_order where  
                       EXTRACT(month FROM date_order::date) = EXTRACT(month FROM CURRENT_DATE) 
                       AND pos_order.company_id = ''' + str(
                company_id) + ''' group by date_month '''
            query = query.format(user_tz)
            label = 'HOURS'
        elif option == 'pos_monthly_sales':
            query = '''select  date_order::date as date_month,sum(amount_total) from pos_order where 
             EXTRACT(month FROM date_order::date) = EXTRACT(month FROM CURRENT_DATE) AND pos_order.company_id = ''' + str(
                company_id) + '''  group by date_month '''
            label = 'DAYS'
        else:
            query = '''select TO_CHAR(date_order,'MON')date_month,sum(amount_total) from pos_order where
             EXTRACT(year FROM date_order::date) = EXTRACT(year FROM CURRENT_DATE) AND pos_order.company_id = ''' + str(
                company_id) + ''' group by date_month'''
            label = 'MONTHS'
        self._cr.execute(query)
        docs = self._cr.dictfetchall()
        order = []
        for record in docs:
            order.append(record.get('sum'))
        today = []
        for record in docs:
            today.append(record.get('date_month'))
        final = [order, today, label]
        return final

    @api.model
    def get_details(self):
        """ Function to get the payment details"""
        company_id = self.env.company.id
        cr = self._cr
        cr.execute(
            """select pos_payment_method.name ->>'en_US',sum(amount) from pos_payment inner join pos_payment_method on 
            pos_payment_method.id=pos_payment.payment_method_id group by pos_payment_method.name ORDER 
            BY sum(amount) DESC; """)
        payment_details = cr.fetchall()
        cr.execute(
            '''select hr_employee.name,sum(pos_order.amount_paid) as total,count(pos_order.amount_paid) as orders 
            from pos_order inner join hr_employee on pos_order.user_id = hr_employee.user_id 
            where pos_order.company_id =''' + str(
                company_id) + " " + '''GROUP BY hr_employee.name order by total DESC;''')
        salesperson = cr.fetchall()
        total_sales = []
        for rec in salesperson:
            rec = list(rec)
            sym_id = rec[1]
            company = self.env.company
            if company.currency_id.position == 'after':
                rec[1] = "%s %s" % (sym_id, company.currency_id.symbol)
            else:
                rec[1] = "%s %s" % (company.currency_id.symbol, sym_id)
            rec = tuple(rec)
            total_sales.append(rec)
        cr.execute(
            '''select DISTINCT(product_template.name) as product_name,sum(qty) as total_quantity from 
       pos_order_line inner join product_product on product_product.id=pos_order_line.product_id inner join 
       product_template on product_product.product_tmpl_id = product_template.id  where pos_order_line.company_id =''' + str(
                company_id) + ''' group by product_template.id ORDER 
       BY total_quantity DESC Limit 10 ''')
        selling_product = cr.fetchall()
        sessions = self.env['pos.config'].search([])
        sessions_list = []
        dict = {
            'opened': 'Opened',
            'opening_control': "Opening Control"
        }
        for session in sessions:
            st = dict.get(session.pos_session_state)
            if st == None:
                sessions_list.append({
                    'session': session.name,
                    'status': 'Closed'
                })
            else:
                sessions_list.append({
                    'session': session.name,
                    'status': dict.get(session.pos_session_state)
                })
        payments = []
        for rec in payment_details:
            rec = list(rec)
            sym_id = rec[1]
            company = self.env.company
            if company.currency_id.position == 'after':
                rec[1] = "%s %s" % (sym_id, company.currency_id.symbol)
            else:
                rec[1] = "%s %s" % (company.currency_id.symbol, sym_id)
            rec = tuple(rec)
            payments.append(rec)
        return {
            'payment_details': payments,
            'salesperson': total_sales,
            'selling_product': sessions_list,
        }

    @api.model
    def get_refund_details(self):
        """ Function to get the Refund details"""
        default_date = datetime.today().date()
        pos_order = self.env['pos.order'].search([])
        total = 0
        today_refund_total = 0
        total_order_count = 0
        total_refund_count = 0
        today_sale = 0
        a = 0
        for rec in pos_order:
            if rec.amount_total < 0.0 and rec.date_order.date() == default_date:
                today_refund_total = today_refund_total + 1
            total_sales = rec.amount_total
            total = total + total_sales
            total_order_count = total_order_count + 1
            if rec.date_order.date() == default_date:
                today_sale = today_sale + 1
            if rec.amount_total < 0.0:
                total_refund_count = total_refund_count + 1
        magnitude = 0
        while abs(total) >= 1000:
            magnitude += 1
            total /= 1000.0
        # add more suffixes if you need them
        val = '%.2f%s' % (total, ['', 'K', 'M', 'G', 'T', 'P'][magnitude])
        pos_session = self.env['pos.session'].search([])
        total_session = 0
        for record in pos_session:
            total_session = total_session + 1
        return {
            'total_sale': val,
            'total_order_count': total_order_count,
            'total_refund_count': total_refund_count,
            'total_session': total_session,
            'today_refund_total': today_refund_total,
            'today_sale': today_sale,
        }

    @api.model
    def get_the_top_customer(self, ):
        """ To get the top Customer details"""
        company_id = self.env.company.id
        query = '''select res_partner.name as customer,pos_order.partner_id,sum(pos_order.amount_paid) as amount_total from pos_order 
        inner join res_partner on res_partner.id = pos_order.partner_id where pos_order.company_id = ''' + str(
            company_id) + ''' GROUP BY pos_order.partner_id,
        res_partner.name  ORDER BY amount_total  DESC LIMIT 10;'''
        self._cr.execute(query)
        docs = self._cr.dictfetchall()

        order = []
        for record in docs:
            order.append(record.get('amount_total'))
        day = []
        for record in docs:
            day.append(record.get('customer'))
        final = [order, day]
        return final

    @api.model
    def get_the_top_products(self):
        """ Function to get the top products"""
        company_id = self.env.company.id
        query = '''select DISTINCT(product_template.name)->>'en_US' as product_name,sum(qty) as total_quantity from 
       pos_order_line inner join product_product on product_product.id=pos_order_line.product_id inner join 
       product_template on product_product.product_tmpl_id = product_template.id where pos_order_line.company_id = ''' + str(
            company_id) + ''' group by product_template.id ORDER 
       BY total_quantity DESC Limit 10 '''
        self._cr.execute(query)
        top_product = self._cr.dictfetchall()
        total_quantity = []
        for record in top_product:
            total_quantity.append(record.get('total_quantity'))
        product_name = []
        for record in top_product:
            product_name.append(record.get('product_name'))
        final = [total_quantity, product_name]
        return final

    @api.model
    def get_the_top_categories(self):
        """ Function to get the top Product categories"""
        company_id = self.env.company.id
        query = '''select DISTINCT(product_category.complete_name) as product_category,sum(qty) as total_quantity 
        from pos_order_line inner join product_product on product_product.id=pos_order_line.product_id  inner join 
        product_template on product_product.product_tmpl_id = product_template.id inner join product_category on 
        product_category.id =product_template.categ_id where pos_order_line.company_id = ''' + str(
            company_id) + ''' group by product_category ORDER BY total_quantity DESC '''
        self._cr.execute(query)
        top_product = self._cr.dictfetchall()
        total_quantity = []
        for record in top_product:
            total_quantity.append(record.get('total_quantity'))
        product_categ = []
        for record in top_product:
            product_categ.append(record.get('product_category'))
        final = [total_quantity, product_categ]
        return final

    class PosOrder(models.Model):
        _inherit = 'pos.order'

        @api.model
        def get_user_pos(
                self,
                offset=0,
                limit=20,
                date_start=None,
                date_end=None,
                filter_users=None,
                filter_warehouse=None,
                filter_sector=None,
        ):
            domain = []

            if date_start or date_end:
                date_domain = []
                try:
                    if date_start and date_end:
                        ds = fields.Date.from_string(date_start)
                        de = fields.Date.from_string(date_end)
                        date_domain = [('date_order', '>=', ds), ('date_order', '<=', de)]
                    elif date_start:
                        ds = fields.Date.from_string(date_start)
                        date_domain = [('date_order', '>=', ds)]
                    elif date_end:
                        de = fields.Date.from_string(date_end)
                        date_domain = [('date_order', '<=', de)]
                    domain += date_domain
                except ValueError as e:
                    raise ValidationError(f"Formato de fecha inválido: {e}")

            if filter_users:
                domain.append(('employee_id', 'in', filter_users))

            if filter_warehouse:
                domain.append(('warehouse_id', 'in', filter_warehouse))

            if filter_sector:
                domain.append(('employee_id.department_id.parent_id', 'in', filter_sector))

            # Idioma del usuario
            lang = self.env.context.get('lang', 'en_US')
            params = []

            # Consulta para los registros paginados
            query = '''
                SELECT
                    po.id,
                    po.date_order,
                    po.cashier_employee,
                    po.employee_id,
                    COALESCE(hd.name->>%s, hd.name->>'en_US') AS department_name,
                    COALESCE(hd_parent.name->>%s, hd_parent.name->>'en_US') AS parent_department_name,
                    he.name AS employee_name,
                    he.id AS employee_id,
                    po.warehouse_id,
                    po.warehouse_name,
                    po.sale_cash,
                    po.sale_card,
                    po.sale_check_transfer,
                    po.sale_credit,
                    po.note_credit_cash,
                    po.note_credit_card,
                    po.note_credit_check_transfer,
                    po.note_credit_credit,
                    po.scope_card,
                    po.scope_check_transfer,
                    po.scope_credit,
                    po.scope_advance,
                    po.note_credit_scope_card,
                    po.note_credit_scope_check_transfer,
                    po.note_credit_scope_credit,
                    po.retention,
                    po.advance_cash,
                    po.note_credit_advance_cash,
                    po.total_scope,
                    po.total_cash,
                    po.counting_cash,
                    po.missing,
                    po.surplus
                FROM pos_order_dashboard po
                LEFT JOIN hr_employee he ON po.employee_id = he.id
                LEFT JOIN hr_department hd ON he.department_id = hd.id
                LEFT JOIN hr_department hd_parent ON hd.parent_id = hd_parent.id
                LEFT JOIN stock_warehouse sw ON po.warehouse_id = sw.id
            '''

            # Consulta para calcular los totales acumulados
            totals_query = '''
                    SELECT
                        SUM(po.sale_cash) AS sale_cash,
                        SUM(po.sale_card) AS sale_card,
                        SUM(po.sale_check_transfer) AS sale_check_transfer,
                        SUM(po.sale_credit) AS sale_credit,
                        SUM(po.note_credit_cash) AS note_credit_cash,
                        SUM(po.note_credit_card) AS note_credit_card,
                        SUM(po.note_credit_check_transfer) AS note_credit_check_transfer,
                        SUM(po.note_credit_credit) AS note_credit_credit,
                        SUM(po.scope_card) AS scope_card,
                        SUM(po.scope_check_transfer) AS scope_check_transfer,
                        SUM(po.scope_credit) AS scope_credit,
                        SUM(po.scope_advance) AS scope_advance,
                        SUM(po.note_credit_scope_card) AS note_credit_scope_card,
                        SUM(po.note_credit_scope_check_transfer) AS note_credit_scope_check_transfer,
                        SUM(po.note_credit_scope_credit) AS note_credit_scope_credit,
                        SUM(po.retention) AS retention,
                        SUM(po.advance_cash) AS advance_cash,
                        SUM(po.note_credit_advance_cash) AS note_credit_advance_cash,
                        SUM(po.total_scope) AS total_scope,
                        SUM(po.total_cash) AS total_cash,
                        SUM(po.counting_cash) AS counting_cash,
                        SUM(po.missing) AS missing,
                        SUM(po.surplus) AS surplus
                    FROM pos_order_dashboard po
                    LEFT JOIN hr_employee he ON po.employee_id = he.id
                    LEFT JOIN hr_department hd ON he.department_id = hd.id
                    LEFT JOIN hr_department hd_parent ON hd.parent_id = hd_parent.id
                '''

            where_clauses = []
            where_params = []
            if domain:
                for field, operator, value in domain:
                    if operator == 'in' and isinstance(value, list):
                        value_str = ", ".join(map(str, value))
                        if field == 'employee_id.department_id':
                            where_clauses.append(f"he.department_id IN ({value_str})")
                        elif field == 'employee_id.department_id.parent_id':
                            where_clauses.append(f"hd.parent_id IN ({value_str})")
                        else:
                            where_clauses.append(f"po.{field} IN ({value_str})")
                    else:
                        if field == 'employee_id.department_id':
                            where_clauses.append(f"he.department_id {operator} %s")
                        elif field == 'employee_id.department_id.parent_id':
                            where_clauses.append(f"hd.parent_id {operator} %s")
                        else:
                            where_clauses.append(f"po.{field} {operator} %s")
                        where_params.append(value)

            # Agregar la cláusula WHERE a ambas consultas
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
                totals_query += " WHERE " + " AND ".join(where_clauses)

            totals_params = where_params.copy()
            self._cr.execute(totals_query, totals_params)
            totals_result = self._cr.dictfetchone()
            totals = {key: float(value or 0.0) for key, value in totals_result.items()}

            # Agregar ordenamiento y paginación a la consulta de registros
            query_params = [lang, lang] + where_params + [offset, limit]
            query += '''
                ORDER BY sw.sequence ASC, po.date_order ASC
                OFFSET %s
                LIMIT %s
            '''

            self._cr.execute(query, query_params)
            docs = self._cr.dictfetchall()

            orders_data = []
            for doc in docs:
                orders_data.append({
                    'id': doc['id'],
                    'date_order': doc['date_order'].strftime('%Y-%m-%d') if doc['date_order'] else '',
                    'employee_id': doc['employee_id'] or 0,
                    'employee_name': doc['employee_name'] or '',
                    'cashier_employee': doc['cashier_employee'] or '',
                    'department_name': doc['department_name'] or '',
                    'parent_department_name': doc['parent_department_name'] or '',
                    'warehouse_id': doc['warehouse_id'] or '',
                    'warehouse_name': doc['warehouse_name'] or '',
                    'sale_cash': self.format_numeric(doc['sale_cash']) or 0.0,
                    'sale_card': self.format_numeric(doc['sale_card']) or 0.0,
                    'sale_check_transfer': self.format_numeric(doc['sale_check_transfer']) or 0.0,
                    'sale_credit': self.format_numeric(doc['sale_credit']) or 0.0,
                    'note_credit_cash': self.format_numeric(doc['note_credit_cash']) or 0.0,
                    'note_credit_card': self.format_numeric(doc['note_credit_card']) or 0.0,
                    'note_credit_check_transfer': self.format_numeric(doc['note_credit_check_transfer']) or 0.0,
                    'note_credit_credit': self.format_numeric(doc['note_credit_credit']) or 0.0,
                    'scope_card': self.format_numeric(doc['scope_card']) or 0.0,
                    'scope_check_transfer': self.format_numeric(doc['scope_check_transfer']) or 0.0,
                    'scope_credit': self.format_numeric(doc['scope_credit']) or 0.0,
                    'scope_advance': self.format_numeric(doc['scope_advance']) or 0.0,
                    'note_credit_scope_card': self.format_numeric(doc['note_credit_scope_card']) or 0.0,
                    'note_credit_scope_check_transfer': self.format_numeric(doc['note_credit_scope_check_transfer']) or 0.0,
                    'note_credit_scope_credit': self.format_numeric(doc['note_credit_scope_credit']) or 0.0,
                    'retention': self.format_numeric(doc['retention']) or 0.0,
                    'advance_cash': self.format_numeric(doc['advance_cash']) or 0.0,
                    'note_credit_advance_cash': self.format_numeric(doc['note_credit_advance_cash']) or 0.0,
                    'total_scope': self.format_numeric(doc['total_scope']) or 0.0,
                    'total_cash': self.format_numeric(doc['total_cash']) or 0.0,
                    'counting_cash': self.format_numeric(doc['counting_cash']) or 0.0,
                    'missing': self.format_numeric(doc['missing']) or 0.0,
                    'surplus': self.format_numeric(doc['surplus']) or 0.0,
                })

            return {
                'orders': orders_data,
                'user_lang': lang,
                'totals': totals
            }

        def format_numeric(self, value, default=0.0):
            return '{:.2f}'.format(float(value or default))




class PosOrderDashboard(models.Model):
    _name = 'pos.order.dashboard'
    _description = 'Pos Order Dashboard'

    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén')
    warehouse_name = fields.Char(string='Nombre de Almacén')
    date_order = fields.Date(string='Fecha del Pedido')
    cashier_employee = fields.Char(string='Empleado Cajero Nombre')
    employee_id = fields.Many2one('hr.employee', string='Empleado Cajero')

    sale_cash = fields.Float(string='Venta Efectivo', digits='Order Dashboard Decimal')
    sale_card = fields.Float(string='Venta Tarjeta', digits='Order Dashboard Decimal')
    sale_check_transfer = fields.Float(string='Venta Cheque/Transferencia', digits='Order Dashboard Decimal')
    sale_credit = fields.Float(string='Venta Crédito', digits='Order Dashboard Decimal')

    note_credit_cash = fields.Float(string='Nota de Crédito Efectivo', digits='Order Dashboard Decimal')
    note_credit_card = fields.Float(string='Nota de Crédito Tarjeta', digits='Order Dashboard Decimal')
    note_credit_check_transfer = fields.Float(string='Nota de Crédito Checque/Transferencia', digits='Order Dashboard Decimal')
    note_credit_credit = fields.Float(string='Nota de Crédito Crédit', digits='Order Dashboard Decimal')

    scope_card = fields.Float(string='Alcance Tarjeta', digits='Order Dashboard Decimal')
    scope_check_transfer = fields.Float(string='Alcance Checque/Transferencia', digits='Order Dashboard Decimal')
    scope_credit = fields.Float(string='Alcance Crédito', digits='Order Dashboard Decimal')
    scope_advance = fields.Float(string='Alcance Anticipo', digits='Order Dashboard Decimal')

    note_credit_scope_card = fields.Float(string='NC Alcance Tarjeta', digits='Order Dashboard Decimal')
    note_credit_scope_check_transfer = fields.Float(string='NC Alcance Checque/Transferencia', digits='Order Dashboard Decimal')
    note_credit_scope_credit = fields.Float(string='NC Alcance Crédito', digits='Order Dashboard Decimal')

    retention = fields.Float(string='Retención', digits='Order Dashboard Decimal')

    advance_cash = fields.Float(string='Anticipo Efectivo', digits='Order Dashboard Decimal')
    note_credit_advance_cash = fields.Float(string='Anticipo Efectivo', digits='Order Dashboard Decimal')

    total_scope = fields.Float(string='Total Alcance', digits='Order Dashboard Decimal')
    total_cash = fields.Float(string='Total Efectivo', digits='Order Dashboard Decimal')
    counting_cash = fields.Float(string='Arqueo Efectivo', digits='Order Dashboard Decimal')
    missing = fields.Float(string='Faltante', digits='Order Dashboard Decimal')
    surplus = fields.Float(string='Sobrante', digits='Order Dashboard Decimal')

