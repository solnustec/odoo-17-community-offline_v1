from odoo import models, fields

class ReportHelpdeskTicketFull(models.AbstractModel):
    _name = 'report.odoo_website_helpdesk.report_helpdesk_ticket_full'
    _description = 'Reporte Completo Ticket Helpdesk'

    def _get_report_values(self, docids, data=None):
        docs = self.env['ticket.helpdesk'].browse(docids)
        local_time = fields.Datetime.context_timestamp(self.env.user, fields.Datetime.now())
        return {
            'docs': docs,
            'print_date': local_time.strftime('%d/%m/%Y %H:%M:%S'),
            'dict_priorities': dict([
                ('0', 'Muy bajo'),
                ('1', 'Bajo'),
                ('2', 'Normal'),
                ('3', 'Alto'),
                ('4', 'Muy alto'),
            ]),
            'dict_ratings': dict([
                ('0', 'Muy bajo'),
                ('1', 'Bajo'),
                ('2', 'Normal'),
                ('3', 'Alto'),
                ('4', 'Muy alto'),
                ('5', 'Extremadamente alto'),
            ]),
        }
