/** @odoo-module **/

import {registry} from "@web/core/registry";
import {Component, onWillStart, useState, onWillUnmount, onMounted} from '@odoo/owl';
import {useService} from '@web/core/utils/hooks';

const actionRegistry = registry.category("actions");

export class ServerDashboard extends Component {
    setup() {
        this.orm = useService('orm');
        this.state = useState({
            stats: null,
            loading: true,
            error: null
        });

        this.refreshInterval = null;

        onWillStart(async () => {
            await this.loadStats();
        });

        onMounted(() => {
            this.refreshInterval = setInterval(() => {
                this.loadStats();
            }, 10000);
        });

        onWillUnmount(() => {
            if (this.refreshInterval) {
                clearInterval(this.refreshInterval);
                this.refreshInterval = null;
            }
        });
    }

    async loadStats() {
        try {
            this.state.loading = true;
            this.state.error = null;
            this.state.stats = await this.orm.call(
                'server.monitor',
                'get_server_stats',
                [],
                {}
            );
        } catch (e) {
            this.state.error = e.message || String(e);
        } finally {
            this.state.loading = false;
        }
    }
}


ServerDashboard.template = 'server_monitor.ServerDashboard';
actionRegistry.add("server_monitor", ServerDashboard);