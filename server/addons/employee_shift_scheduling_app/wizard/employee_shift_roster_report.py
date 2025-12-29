# -*- coding: utf-8 -*-


from odoo import fields, models, api, _
import base64
import os
from datetime import datetime, date
from datetime import *
from io import BytesIO
import xlsxwriter
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from xlsxwriter.utility import xl_col_to_name
from odoo.tools import config
import string
import random
from num2words import num2words
from dateutil.relativedelta import relativedelta
from odoo.tools.misc import xlwt
import pytz


class employee_shift_roster_report(models.TransientModel):
    _name = "employee.shift.roster.report.wizard"

    start_date = fields.Date(string="Start Date")
    end_date = fields.Date(string="End Date")
    file = fields.Binary()
    file_name = fields.Char(string="File Name")

    def print_excel_report(self):
        if self.start_date > self.end_date:
            raise ValidationError('End Date is Greater then start date')
        name_of_file = 'Informe de turnos de empleados.xlsx'
        file_path = 'Informe de turnos de empleados' + '.xlsx'
        workbook = xlsxwriter.Workbook('/tmp/' + file_path)
        allocation_ids = self.env["employee.shift.allocation"].search(
            [('from_date', '=', self.start_date), ('to_date', '=', self.end_date)])
        bold = workbook.add_format({'bold': True})
        align_left = workbook.add_format({'align': 'center'})
        merge_format = workbook.add_format({
            'bold': 1,
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'fg_color': 'gray', })

        cell_format = workbook.add_format({
            'bold': 1,
            'align': 'center',

        })
        title = "Turno de empleados"
        date = str(self.start_date) + " to " + str(self.end_date)
        date_format = workbook.add_format({'num_format': 'dd/mm/yy'})
        for shift_id in allocation_ids.mapped('shift_id'):
            worksheet = workbook.add_worksheet(shift_id.name)
            f_allocation_ids = self.env["employee.shift.allocation"].search([('shift_id', '=', shift_id.id),('from_date', '=', self.start_date), ('to_date', '=', self.end_date)])
            worksheet.set_column(0, 0, 20)
            worksheet.set_column(0, 1, 23)
            worksheet.set_column(0, 2, 20)
            worksheet.set_column(0, 3, 15)
            worksheet.set_column(0, 4, 15)
            worksheet.set_column(0, 5, 15)

            worksheet.set_row(0, 30)

            worksheet.merge_range('A1:J1', title, merge_format)
            worksheet.merge_range('A2:J2', date, merge_format)

            row = 4;
            column = 0
            worksheet.write(row + 1, column, "Employee", cell_format)
            column += 1
            worksheet.write(row + 1, column, "Department", cell_format)
            column += 1
            worksheet.write(row + 1, column, "Job Position", cell_format)
            column += 1
            row += 1
            for allocation_id in f_allocation_ids:
                column = 0
                worksheet.write(row + 1, column, allocation_id.employee_id.name)
                column += 1
                worksheet.write(row + 1, column, allocation_id.employee_id.department_id.name)
                column += 1
                worksheet.write(row + 1, column, allocation_id.employee_id.job_id.name)
                column += 1
                for workday in allocation_id.workday_ids:
                    if workday.date:
                        t = workday.date.strftime('%d')
                    else:
                        t = "False"
                    worksheet.write(4 + 1, column, 'Working Day', cell_format)
                    worksheet.write(row + 1, column, t)
                    column += 1
                for weekend in allocation_id.weekend_ids:
                    if weekend.date:
                        t = weekend.date.strftime('%d')
                    else:
                        t = "False"
                    worksheet.write(4 + 1, column, 'Week Off', cell_format)
                    worksheet.write(row + 1, column, t)
                    column += 1
                row += 1

        workbook.close()
        export_id = base64.b64encode(open('/tmp/' + file_path, 'rb+').read())
        result_id = self.env['employee.shift.roster.report.wizard'].create(
            {'file': export_id, 'file_name': name_of_file})
        return {
            'name': 'Informe de turnos de empleados',
            'view_mode': 'form',
            'res_id': result_id.id,
            'res_model': 'employee.shift.roster.report.wizard',
            'view_type': 'form',
            'type': 'ir.actions.act_window',
            'target': 'new',
        }
