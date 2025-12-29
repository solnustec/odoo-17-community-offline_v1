/** @odoo-module **/
import { registry } from "@web/core/registry";
import { jsonrpc } from "@web/core/network/rpc_service";
import { _t } from "@web/core/l10n/translation";
import { Component } from "@odoo/owl";
import { onMounted, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

class HelpDeskDashBoard extends Component {
    setup() {
        super.setup();
        this.ref = useRef("helpDeskDashboard");
        this.rpc = useService("rpc");
        this.actionService = useService("action");
        this.filters = {
            date_start: '',
            date_end: '',
            assigned_user: '',
            client: ''
        };
        onMounted(this.onMounted);
    }

    onMounted() {
        this.loadFilterOptions();
        this.render_dashboards();
        this.render_graphs();
    }

    async loadFilterOptions() {
        // Load assigned users
        const users = await this.rpc('/helpdesk/assigned_users', {});
        const userSelect = this.ref.el.querySelector('#assigned_user');
        userSelect.innerHTML = '';
        const allOption = document.createElement('option');
        allOption.value = '';
        allOption.textContent = 'Todos';
        userSelect.appendChild(allOption);
        users.forEach(user => {
            const option = document.createElement('option');
            option.value = user.id;
            option.textContent = user.name;
            userSelect.appendChild(option);
        });

        // Load clients
        const clients = await this.rpc('/helpdesk/employees', {});
        const clientSelect = this.ref.el.querySelector('#client');
        clientSelect.innerHTML = '';
        const allClientOption = document.createElement('option');
        allClientOption.value = '';
        allClientOption.textContent = 'Todos';
        clientSelect.appendChild(allClientOption);
        clients.forEach(client => {
            const option = document.createElement('option');
            option.value = client.id;
            option.textContent = client.name;
            clientSelect.appendChild(option);
        });
    }

    applyFilters(ev) {
        ev.stopPropagation();
        this.filters.date_start = this.ref.el.querySelector('#date_start').value;
        this.filters.date_end = this.ref.el.querySelector('#date_end').value;
        this.filters.assigned_user = this.ref.el.querySelector('#assigned_user').value;
        this.filters.client = this.ref.el.querySelector('#client').value;
        this.render_dashboards();
        this.render_graphs();
    }

    resetFilters(ev) {
        ev.stopPropagation();
        this.filters = {
            date_start: '',
            date_end: '',
            assigned_user: '',
            client: ''
        };
        this.ref.el.querySelector('#date_start').value = '';
        this.ref.el.querySelector('#date_end').value = '';
        this.ref.el.querySelector('#assigned_user').value = '';
        this.ref.el.querySelector('#client').value = '';
        this.render_dashboards();
        this.render_graphs();
    }

    getFilterDomain() {
        const domain = [];
        if (this.filters.date_start) {
            const dateStart = new Date(this.filters.date_start);
            dateStart.setHours(5);
            domain.push(['create_date', '>=', dateStart.toISOString()]);
        }
        if (this.filters.date_end) {
            const dateEnd = new Date(this.filters.date_end);
            dateEnd.setHours(28, 59, 59);
            domain.push(['create_date', '<=', dateEnd.toISOString()]);
        }
        if (this.filters.assigned_user) {
            domain.push(['assigned_user_id', '=', parseInt(this.filters.assigned_user)]);
        }
        if (this.filters.client) {
            domain.push(['customer_id', '=', parseInt(this.filters.client)]);
        }
        return domain;
    }

    render_graphs() {
        this.render_tickets_month_graph();
    }

    render_tickets_month_graph() {
        var self = this;
        var ctx = this.ref.el.querySelector('#ticket_month');

        jsonrpc('/web/dataset/call_kw/ticket.helpdesk/get_tickets_view', {
            model: "ticket.helpdesk",
            method: "get_tickets_view",
            args: [this.getFilterDomain()],
            kwargs: {},
        }).then(function (values) {
            var assignedData = values.assigned_users_ticket_counts || [];

            var labels = assignedData.map(user => user.name);
            var dataValues = assignedData.map(user => user.ticket_count);

            const backgroundColors = [
                "#4BC0C0", "#FF6384", "#36A2EB", "#FFCE56", "#9966FF",
                "#FF9F40", "#66FF66", "#FF6666", "#66B2FF", "#FF99CC"
            ];

            var data = {
                labels: labels,
                datasets: [{
                    label: 'Tickets asignados',
                    data: dataValues,
                    backgroundColor: backgroundColors,
                    borderColor: "#fff",
                    borderWidth: 1
                }]
            };

            var options = {
                indexAxis: 'y',  // barras horizontales
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    title: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return ` ${context.label}: ${context.parsed.x} tickets`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        ticks: { precision: 0 }
                    },
                    y: {
                        ticks: {
                            font: {
                                size: 14
                            }
                        }
                    }
                }
            };

            new Chart(ctx, {
                type: "bar",
                data: data,
                options: options
            });
        });
    }


    render_dashboards() {
        var self = this;
        jsonrpc('/web/dataset/call_kw/ticket.helpdesk/get_tickets_count', {
            model: 'ticket.helpdesk',
            method: 'get_tickets_count',
            args: [this.getFilterDomain()],
            kwargs: {},
        }).then(function(result) {
            // Clear previous counts
            self.ref.el.querySelector('#inbox_count').innerHTML = '';
            self.ref.el.querySelector('#inprogress_count').innerHTML = '';
            self.ref.el.querySelector('#wait_count').innerHTML = '';
            self.ref.el.querySelector('#done_count').innerHTML = '';
            self.ref.el.querySelector('#cancelled_count').innerHTML = '';

            // Update counts
            var inbox_count_span = document.createElement("span");
            inbox_count_span.textContent = result.inbox_count;
            self.ref.el.querySelector('#inbox_count').appendChild(inbox_count_span);

            var progress_count_span = document.createElement("span");
            progress_count_span.textContent = result.progress_count;
            self.ref.el.querySelector('#inprogress_count').appendChild(progress_count_span);

            var wait_count_span = document.createElement("span");
            wait_count_span.textContent = result.wait_count;
            self.ref.el.querySelector('#wait_count').appendChild(wait_count_span);

            var done_count_span = document.createElement("span");
            done_count_span.textContent = result.done_count;
            self.ref.el.querySelector('#done_count').appendChild(done_count_span);

            var cancelled_count_span = document.createElement("span");
            cancelled_count_span.textContent = result.cancelled_count;
            self.ref.el.querySelector('#cancelled_count').appendChild(cancelled_count_span);

            // Update priority progress bars
            var priorityCounts = {
                low: result.low_count1,
                normal: result.normal_count1,
                high: result.high_count1,
                very_high: result.very_high_count1
            };
            for (var priority in priorityCounts) {
                var progressBarWidth = priorityCounts[priority] + "%";
                var progressBar = $("<div class='progress-bar'></div>").css("width", progressBarWidth);
                var progressBarContainer = $("<div class='progress'></div>").append(progressBar);
                var progressValue = $("<div class='progress-value'></div>").text(priorityCounts[priority] + "%");
                $("." + priority + "_count").empty().append(progressBarContainer);
                $("." + priority + "_count .progress-value").empty().append(progressValue);
            }

            self.rpc('/help/tickets', { domain: self.getFilterDomain() }).then((values) => {
                $('.pending_tickets').empty().append(values);
            });
        });
    }

    tickets_inbox(ev) {
        var self = this;
        ev.stopPropagation();
        ev.preventDefault();
        self.actionService.doAction({
            name: _t("Bandeja de Entrada"),
            type: 'ir.actions.act_window',
            res_model: 'ticket.helpdesk',
            view_mode: 'tree,form',
            views: [[false, 'list'], [false, 'form']],
            domain: [['stage_id.name', '=', 'Bandeja de Entrada']].concat(this.getFilterDomain()),
            context: {default_stage_id_name: 'Draft'},
            target: 'current'
        });
    }

    tickets_inprogress(ev) {
        var self = this;
        ev.stopPropagation();
        ev.preventDefault();
        self.actionService.doAction({
            name: _t("En Curso"),
            type: 'ir.actions.act_window',
            res_model: 'ticket.helpdesk',
            view_mode: 'tree,form',
            views: [[false, 'list'], [false, 'form']],
            domain: [['stage_id.name', '=', 'En Curso']].concat(this.getFilterDomain()),
            context: {create: false},
            target: 'current'
        });
    }

    tickets_wait(ev) {
        var self = this;
        ev.stopPropagation();
        ev.preventDefault();
        self.actionService.doAction({
            name: _t("En Espera"),
            type: 'ir.actions.act_window',
            res_model: 'ticket.helpdesk',
            view_mode: 'tree,form',
            views: [[false, 'list'], [false, 'form']],
            domain: [['stage_id.name', '=', 'En Espera']].concat(this.getFilterDomain()),
            context: {create: false},
            target: 'current'
        });
    }

    tickets_done(ev) {
        var self = this;
        ev.stopPropagation();
        ev.preventDefault();
        self.actionService.doAction({
            name: _t("Finalizado"),
            type: 'ir.actions.act_window',
            res_model: 'ticket.helpdesk',
            view_mode: 'tree,form',
            views: [[false, 'list'], [false, 'form']],
            domain: [['stage_id.name', '=', 'Resuelto']].concat(this.getFilterDomain()),
            context: {create: false},
            target: 'current'
        });
    }

    tickets_cancelled(ev) {
        var self = this;
        ev.stopPropagation();
        ev.preventDefault();
        self.actionService.doAction({
            name: _t("Cancelado"),
            type: 'ir.actions.act_window',
            res_model: 'ticket.helpdesk',
            view_mode: 'tree,form',
            views: [[false, 'list'], [false, 'form']],
            domain: [['stage_id.name', '=', 'Cancelado']].concat(this.getFilterDomain()),
            context: {create: false},
            target: 'current'
        });
    }

    tickets_low(ev) {
        var self = this;
        ev.stopPropagation();
        ev.preventDefault();
        self.actionService.doAction({
            name: _t("Tickets con Prioridad Baja"),
            type: 'ir.actions.act_window',
            res_model: 'ticket.helpdesk',
            view_mode: 'tree,form',
            views: [[false, 'list'], [false, 'form']],
            domain: [['priority', '=', '1']].concat(this.getFilterDomain()),
            context: {create: false},
            target: 'current'
        });
    }

    tickets_normal(ev) {
        var self = this;
        ev.stopPropagation();
        ev.preventDefault();
        self.actionService.doAction({
            name: _t("Tickets con Prioridad Normal"),
            type: 'ir.actions.act_window',
            res_model: 'ticket.helpdesk',
            view_mode: 'tree,form',
            views: [[false, 'list'], [false, 'form']],
            domain: [['priority', '=', '2']].concat(this.getFilterDomain()),
            context: {create: false},
            target: 'current'
        });
    }

    tickets_high(ev) {
        var self = this;
        ev.stopPropagation();
        ev.preventDefault();
        self.actionService.doAction({
            name: _t("Tickets con Prioridad Alta"),
            type: 'ir.actions.act_window',
            res_model: 'ticket.helpdesk',
            view_mode: 'tree,form',
            views: [[false, 'list'], [false, 'form']],
            domain: [['priority', '=', '3']].concat(this.getFilterDomain()),
            context: {create: false},
            target: 'current'
        });
    }

    tickets_very_high(ev) {
        var self = this;
        ev.stopPropagation();
        ev.preventDefault();
        self.actionService.doAction({
            name: _t("Tickets con Prioridad Muy Alta"),
            type: 'ir.actions.act_window',
            res_model: 'ticket.helpdesk',
            view_mode: 'tree,form',
            views: [[false, 'list'], [false, 'form']],
            domain: [['priority', '=', '4']].concat(this.getFilterDomain()),
            context: {create: false},
            target: 'current'
        });
    }
}

HelpDeskDashBoard.template = 'DashBoardHelpDesk';
registry.category("actions").add("helpdesk_dashboard", HelpDeskDashBoard);