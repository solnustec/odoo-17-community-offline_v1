/** @odoo-module **/
/**
 * This file is used register a popup for transferring the stock of selected products
 */

import {AbstractAwaitablePopup} from "@point_of_sale/app/popup/abstract_awaitable_popup";
import {_t} from "@web/core/l10n/translation";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {onMounted, useState, onPatched, useEffect} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {ConfirmPopup} from "@point_of_sale/app/utils/confirm_popup/confirm_popup";
import {CustomModal} from "./custom_modal";


export class CreateRegulationPopup extends AbstractAwaitablePopup {
    static template = "CreateRegulationPopup";
    static defaultProps = {
        confirmText: _t("Save"),
        cancelText: _t("Discard"),
        clearText: _t("Clear"),
        title: "",
        body: "",
        start_date: '',
        end_date: ''
    };

    async setup() {
        super.setup();
        onMounted(this.onMounted);
        this.pos = usePos();
        this.orm = useService("orm");
        this.popup = useService("popup");
        this.state = useState({
            products: [],
            products_to_regulation: [],
            extra_data: {
                laboratory_id: '',
                laboratory_id_old: '',
                laboratory_name: '',
                warehouse_id: '',
                warehouse_name: '',
                warehouse_external_id: '',
                employee_id_old: '',
                location_id: '',
                start_date: '',
                end_date: '',
            },
            pos_config: '',
            time_refresh: null,
            product_stock_data: {
                product_id_old: '',
                stock_over: 0,
                stock_missing: 0
            }
        })
        this.notificationService = useService("notification");
        // actualizar los productos cada cierto tiempo
        let intervalId = null;
        useEffect(
            () => {
                if (this.state.products.length && this.state.time_refresh) {
                    this.clearIntervalIfNeeded(intervalId);
                    intervalId = setInterval(async () => {
                        await this.updateProducts();
                    }, this.state.time_refresh);
                } else {
                    clearInterval(intervalId);
                    intervalId = null;
                }
                return () => {
                    this.clearIntervalIfNeeded(intervalId);
                };
            },
            () => [this.state.products.length, this.state.time_refresh]
        );

    }

    async onMounted() {
        this.state.extra_data.warehouse_id = this.props.warehouse_id
        this.state.extra_data.warehouse_name = this.props.warehouse_name
        this.state.extra_data.warehouse_external_id = this.props.warehouse_external_id
        this.state.extra_data.employee_id_old = this.props.employee_id_old
        this.state.extra_data.location_id = this.props.location_id
        this.state.extra_data.start_date = this.props.start_date || '';
        this.state.extra_data.end_date = this.props.end_date || '';
        this.state.pos_config = this.pos.config.id
        this.state.time_refresh = await this.env.services.orm.call('pos.config', 'get_time_refresh', [this.pos.config.id]);
        this.state.time_refresh = this.state.time_refresh * 1000
    }

    clearIntervalIfNeeded(intervalId) {
        if (intervalId) {
            clearInterval(intervalId);
            intervalId = null;
        }
    };


// funcion que se ejecuta al cambiar de laboratorio
    async _clickPicking(ev) {
        this.state.products_to_regulation = []
        let laboratory_id = ev.target.selectedOptions[0].value
        let laboratory_id_old = ev.target.selectedOptions[0].getAttribute('id-old')
        this.state.extra_data.laboratory_id = laboratory_id
        this.state.extra_data.laboratory_id_old = laboratory_id_old
        this.state.extra_data.laboratory_name = ev.target.selectedOptions[0].textContent.trim()
        try {
            if (!laboratory_id) {
                this.state.products = []
                return
            }
            this.state.products = await this.orm.call(
                "pos.config",
                "get_products_by_laboratory",
                [],
                {laboratory_id: laboratory_id, picking_type_id: this.pos.config.picking_type_id[0]}
            )
            if (this.state.products.length > 0) {
                this.state.enable_sync = true
            }

        } catch (error) {
            this.cancel()
            this.notificationService.add(
                ("Error al obtener la información" + error),
                {type: "warning"}
            );
        }

    }


    async updateProducts() {
        try {
            const laboratory_id = this.state.extra_data.laboratory_id;
            if (laboratory_id) {
                this.state.products = await this.orm.call(
                    "pos.config",
                    "get_products_by_laboratory",
                    [],
                    {laboratory_id: laboratory_id, picking_type_id: this.pos.config.picking_type_id[0]}
                );
            }
        } catch (error) {
            this.notificationService.add(
                ("Error al actualizar los productos: " + error),
                {type: "warning"}
            );
        }
    }

//funcion para el calculo del stock en el front
    async _stockCount(ev) {
        const productId = ev.target.id.split('-')[0]; // Supondo que o ID seja algo como "123-conteo"
        const current_stock_html_element = document.getElementById(productId + '-stock');

        const stock_counted = Number(ev.target.value);
        const current_stock = Number(current_stock_html_element.value);

        const product_stock_data = {
            product_id: productId,
            stock_over: 0,
            stock_missing: 0,
        };

        if (stock_counted > current_stock) {
            product_stock_data.stock_over = stock_counted - current_stock;
        } else if (stock_counted < current_stock) {
            product_stock_data.stock_missing = current_stock - stock_counted;
        }

        this.update_product_stock(productId, product_stock_data.stock_over, product_stock_data.stock_missing, stock_counted, current_stock);

        // Atualize os campos de Sobrante e Faltante no HTML
        document.getElementById(productId + '-sobrante').value = product_stock_data.stock_over;
        document.getElementById(productId + '-faltante').value = product_stock_data.stock_missing;
    }

    update_product_stock(productId, stockOver, stockMissing, stockCounted, current_stock) {
        const productIdNumber = Number(productId);

        const product = this.state.products.find(item => item.product_id === productIdNumber);
        const productName = product ? product.product_name : '';

        const existingIndex = this.state.products_to_regulation.findIndex(
            item => Number(item.product_id) === productIdNumber
        );
        if (existingIndex !== -1) {
            this.state.products_to_regulation[existingIndex] = {
                product_id: productId,
                product_name: productName,
                stock_over: stockOver,
                stock_missing: stockMissing,
                stock_counted: stockCounted,
                current_stock: current_stock,
            };
        } else {
            this.state.products_to_regulation.push({
                product_id: productId,
                product_name: productName,
                stock_over: stockOver,
                stock_missing: stockMissing,
                stock_counted: stockCounted,
                current_stock: current_stock,
            });
        }
    }

    async _confirmAction({title, body}) {
        const {confirmed} = await this.popup.add(ConfirmPopup, {
            title, body,
        });
        return confirmed;
    }

    async Create() {
        const confirmed = await this._confirmAction({
            title: "¿Desea registrar la regulación de inventario?",
            body: "recuerde que el proceso es irreversible, y no se puede deshacer",
        })
        if (!confirmed) return;

        try {
            if (!this.state.products_to_regulation.length) {
                this.notificationService.add(
                    ("No haz realizado ningun cambio en el inventario, por favor selecciona un laboratorio, para poder continuar"),
                    {
                        type: "danger",
                        title: _t(
                            "Error, No se puede registrar la regulación de inventario."
                        ),
                        sticky: true,

                    }
                );
                this.cancel();
                return
            }
            const result = await this.orm.call(
                "pos.config",
                "adjust_inventory_from_pos",
                [
                    this.state.products_to_regulation,
                    this.state.extra_data,
                    this.state.pos_config,
                    this.pos.config.sync_data
                ], {}
            );

            if (result[0].success) {

                this.notificationService.add(
                    ("Regulación de stock guardada con exito"),
                    {type: "info"}
                );

                await this.popup.add(CustomModal, {
                    pos: this.pos,
                    warehouse_name: this.state.extra_data.warehouse_name,
                    registration_number: result[0].detail_id,
                    laboratory: this.state.extra_data.laboratory_name,
                    date_start: this.formatDate(this.state.extra_data.start_date),
                    date_end: this.formatDate(this.state.extra_data.end_date),
                    employee: this.pos.user.name,
                    date_print: new Date().toLocaleDateString(),
                    tableData: this.state.products_to_regulation,
                });
            } else {
                this.notificationService.add(
                    result[0].message || "Error al registrar la regulación de inventario",
                    {type: "warning"}
                );
            }

        } catch (error) {
            this.notificationService.add(
                ("Error al ajustar inventario, intentelo de nuevo mas tarde " + error),
                {type: "warning"}
            );
        }
        this.state.products_to_regulation = []
        this.state.products = []
        this.cancel();
    }

    formatDate(dateString) {
        const [year, month, day] = dateString.split('-');
        return `${day}/${month}/${year}`;
    }
}
