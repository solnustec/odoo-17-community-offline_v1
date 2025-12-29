/** @odoo-module */

import {patch} from "@web/core/utils/patch";
import {PosStore} from "@point_of_sale/app/store/pos_store";
import { OfflineErrorPopup } from "@point_of_sale/app/errors/popups/offline_error_popup";
import { ConnectionLostError, RPCError } from "@web/core/network/rpc_service";

patch(PosStore.prototype, {
    async _processData(loadedData) {
        await super._processData(...arguments);

        // Cargar los bancos como ya tienes implementado
        this.banks = loadedData['banks'];

        // Cargar las tarjetas de crédito desde el modelo 'credit.card'
        this.cards = await this.env.services.orm.searchRead(
            'credit.card',
            [],
            ['id', 'name_card']  // Campos que queremos cargar
        );
    },

    async verify_connection_pos() {
        try {
            const result = await this.env.services.orm.call(
                "pos.config",
                "ping_connection",
                []
            );

            return result === true;
        } catch (error) {
            this.env.services.popup.add(OfflineErrorPopup)
            return false;
        }
    },

    async _flush_orders_retry(orders, options) {
        if (!Array.isArray(orders) || orders.length === 0) {
            throw new Error('Orders must be a non-empty array');
        }

        let errors = [];
        let serverIds = [];
        let successfulOrders = [];

        for (let i = 0; i < orders.length; i++) {
            const order = orders[i];
            try {
                const server_ids = await this._save_to_server([order], options);

                // Validar respuesta del servidor
                if (!server_ids || !server_ids[0] || !server_ids[0].pos_reference || !server_ids[0].id) {
                    throw new Error(`Invalid server response for order ${i}`);
                }

                this.validated_orders_name_server_id_map[server_ids[0].pos_reference] = server_ids[0].id;
                serverIds.push(server_ids[0]);
                successfulOrders.push(order);

            } catch (error) {
                errors.push({
                    order: order,
                    index: i,
                    error: error
                });
            }
        }

        // Éxito total
        if (serverIds.length === orders.length) {
            this.set_synch('connected');
            return serverIds;
        }

        // Error parcial o total
        const lastError = errors[errors.length - 1]?.error;

        if (lastError instanceof ConnectionLostError) {
            this.set_synch('disconnected');
        } else {
            this.set_synch('error');
        }

        // Crear error detallado
        const detailedError = new Error(
            `Failed to save ${errors.length}/${orders.length} orders. ` +
            `Successful: ${successfulOrders.length}`
        );
        detailedError.failedOrders = errors;
        detailedError.successfulOrders = successfulOrders;
        detailedError.originalError = lastError;

        throw detailedError;
    }

});
