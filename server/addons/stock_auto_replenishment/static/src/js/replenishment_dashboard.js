/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class AutoReplenishmentDashboard extends Component {
    static template = "stock_auto_replenishment.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            data: {},
            loading: true,
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "auto.replenishment.dashboard",
                "get_dashboard_data",
                []
            );
        } catch (error) {
            console.error("Error loading dashboard data:", error);
        }
        this.state.loading = false;
    }

    async refresh() {
        await this.loadData();
    }

    openPickings(state) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Transferencias Automáticas",
            res_model: "stock.picking",
            view_mode: "tree,form",
            views: [[false, "list"], [false, "form"]],
            domain: state ?
                [["is_auto_replenishment", "=", true], ["state", state === "waiting" ? "in" : "=", state === "waiting" ? ["waiting", "confirmed"] : state]] :
                [["is_auto_replenishment", "=", true]],
        });
    }

    openQueue(state) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Cola de Procurements",
            res_model: "product.replenishment.procurement.queue",
            view_mode: "tree,form",
            views: [[false, "list"], [false, "form"]],
            domain: state ? [["state", "=", state]] : [],
        });
    }

    openOrderpoints(needsReplenish) {
        const domain = [["trigger", "=", "auto"]];
        if (needsReplenish) {
            domain.push(["qty_to_order", ">", 0]);
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Reglas Automáticas",
            res_model: "stock.warehouse.orderpoint",
            view_mode: "tree,form",
            views: [[false, "list"], [false, "form"]],
            domain: domain,
        });
    }
}

AutoReplenishmentDashboard.props = ["*"];

registry.category("actions").add("auto_replenishment_dashboard", AutoReplenishmentDashboard);
