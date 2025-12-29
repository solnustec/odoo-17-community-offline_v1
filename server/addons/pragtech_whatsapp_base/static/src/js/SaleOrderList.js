/** @odoo-module **/

import {patch} from "@web/core/utils/patch";
import {SaleOrderList} from "@pos_sale/app/order_management_screen/sale_order_list/sale_order_list";

patch(SaleOrderList.prototype, {
    setup() {
        super.setup();

        // Filtros nuevos
        this.startDate = null;
        this.endDate = null;

        // Por defecto → fecha del día actual
        const today = new Date();
        this.defaultDate = today.toISOString().split("T")[0];
    },

    // Método para setear una fecha específica
    setFilterDate(dateString) {
        this.startDate = dateString;
        this.endDate = dateString;
        this.render();
    },

    // Método para setear rango
    setFilterRange(start, end) {
        this.startDate = start;
        this.endDate = end;
        this.render();
    },

    get filteredOrders() {
        let orders = this.props.orders;

        // ❌ Quitamos filtro por estado
        // orders = orders.filter(order => order.state === 'sale');

        // ✔ Convertir fecha del sale.order
        function getOrderDate(order) {
            return order.date_order?.split(" ")[0]; // yyyy-mm-dd
        }

        // ✔ Filtro por fecha del día por defecto
        let start = this.startDate || this.defaultDate;
        let end = this.endDate || this.defaultDate;

        return orders.filter(order => {
            const od = getOrderDate(order);
            return od >= start && od <= end;
        });
    }
});
