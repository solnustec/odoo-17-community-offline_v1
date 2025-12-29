/** @odoo-module */

import {PosStore} from "@point_of_sale/app/store/pos_store";
import {Order} from "@point_of_sale/app/store/models";
import {patch} from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

patch(PosStore.prototype, {
    // @Override
    async _processData(loadedData) {
        await super._processData(...arguments);
        if (this.isEcuadorianCompany()) {
            this.l10n_latam_identification_types = loadedData["l10n_latam.identification.type"];
            this.finalConsumerId = loadedData["final_consumer_id"];
        }
    },
    isEcuadorianCompany() {
        return this.company.country?.code == "EC";
    },
    // @Override
    // For EC, if the partner on the refund was End Consumer we need to allow the user to change it.
    async selectPartner({missingFields = []} = {}) {
        if (!this.isEcuadorianCompany()) {
            return super.selectPartner(...arguments);
        }
        const currentOrder = this.get_order();
        if (!currentOrder) {
            return;
        }
        const currentPartner = currentOrder.get_partner();
        if (currentPartner && currentPartner.id === this.finalConsumerId) {
            const {confirmed, payload: newPartner} = await this.showTempScreen("PartnerListScreen", {
                partner: currentPartner,
            });
            if (confirmed) {
                currentOrder.set_partner(newPartner);
            }
            return;
        }
        return super.selectPartner(...arguments);
    },

    async _save_to_server(orders, options) {
        if (!orders || !orders.length) {
            return Promise.resolve([]);
        }

        // Filter out orders that are already being synced
        const ordersToSync = orders.filter(order => !this.syncingOrders.has(order.id));

        if (!ordersToSync.length) {
            return Promise.resolve([]);
        }

        // Add these order IDs to the syncing set
        ordersToSync.forEach(order => this.syncingOrders.add(order.id));

        this.set_synch("connecting", ordersToSync.length);
        options = options || {};

        // Keep the order ids that are about to be sent to the
        // backend. In between create_from_ui and the success callback
        // new orders may have been added to it.
        const order_ids_to_sync = ordersToSync.map((o) => o.id);

        for (const order of ordersToSync) {
            order.to_invoice = options.to_invoice || false;
        }
        // we try to send the order. silent prevents a spinner if it takes too long. (unless we are sending an invoice,
        // then we want to notify the user that we are waiting on something )
        const orm = options.to_invoice ? this.orm : this.orm.silent;

        try {
            // FIXME POSREF timeout
            // const timeout = typeof options.timeout === "number" ? options.timeout : 30000 * orders.length;
            const serverIds = await orm.call(
                "pos.order",
                "create_from_ui",
                [ordersToSync, options.draft || false],
                {
                    context: this._getCreateOrderContext(ordersToSync, options),
                }
            );

            for (const serverId of serverIds) {
                const order = this.env.services.pos.orders.find(
                    (order) => order.name === serverId.pos_reference
                );

                if (order) {
                    order.server_id = serverId.id;
                    order.set_sri_authorization(serverId.sri_authorization);
                }
            }

            for (const order_id of order_ids_to_sync) {
                this.db.remove_order(order_id);
            }

            this.failed = false;
            this.set_synch("connected");
            return serverIds;
        } catch (error) {
            console.warn("Failed to send orders:", ordersToSync);
            if (error.code === 200) {
                // Business Logic Error, not a connection problem
                // Hide error if already shown before ...
                if ((!this.failed || options.show_error) && !options.to_invoice) {
                    this.failed = error;
                    this.set_synch("error");
                    throw error;
                }
            }
            this.set_synch("disconnected");
            throw error;
        } finally {
            order_ids_to_sync.forEach(order_id => this.syncingOrders.delete(order_id));
        }
    }
});


patch(Order.prototype, {
    setup() {
        super.setup(...arguments);

        if (this.pos.isEcuadorianCompany()) {
            this._setDefaultPartnerIfNeeded();
        }
    },

    async _setDefaultPartnerIfNeeded() {
        // Early returns para simplificar lógica
        if (this.is_return) {
            return;
        }

        if (this.get_partner()) {
            return;
        }

        if (!this.pos.finalConsumerId) {
            return;
        }

        try {
            // Opción 1: Si el partner está en cache del POS
            const partner = this.pos.db.get_partner_by_id(this.pos.finalConsumerId);
            if (partner) {
                this.set_partner(partner);
                return;
            }

            // Opción 2: Si no está en cache, buscarlo
            const partners = await this.env.services.orm.searchRead(
                "res.partner",
                [["id", "=", this.pos.finalConsumerId]],
                ["id", "name", "vat"]
            );

            if (partners.length > 0) {
                this.set_partner(partners[0]);
            }
        } catch (error) {
            console.error("Error al cargar consumidor final:", error);
        }
    }
    //TODO validar ests campos en el backend
    // set_sri_authorization(code) {
    //     this.sri_authorization = code;
    // },
    // get_sri_authorization() {
    //     return this.sri_authorization || "";
    // },
    // export_as_JSON() {
    //     const json = super.export_as_JSON(...arguments);
    //     json.sri_authorization = this.get_sri_authorization();
    //     return json;
    // },
    // init_from_JSON(json) {
    //     super.init_from_JSON(...arguments);
    //     this.sri_authorization = json.sri_authorization || "";
    // },
    // export_for_printing() {
    //     const res = super.export_for_printing(...arguments);
    //     res.sri_authorization = this.get_sri_authorization();
    //     return res;
    // },
});


