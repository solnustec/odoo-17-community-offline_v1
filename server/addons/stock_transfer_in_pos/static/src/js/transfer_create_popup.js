/** @odoo-module **/
/* global Sha1 */
/**
     * This file is used register a popup for transferring the stock of selected products
     */

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { _t } from "@web/core/l10n/translation";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useRef, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { TransferRefPopup } from "./transfer_ref_popup";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { RecordSelectorReadonly } from "@stock_transfer_in_pos/js/record_selector_extend";
import { NumberPopup } from "@point_of_sale/app/utils/input_popups/number_popup";


export class CreateTransferPopup extends AbstractAwaitablePopup {
    static template = "CreateTransferPopup";
    static components = { RecordSelectorReadonly };
    static defaultProps = {
        confirmText: _t("Save"),
        cancelText: _t("Discard"),
        clearText: _t("Clear"),
        title: "",
        body: "",
    };
       setup() {
        super.setup();
        this.pos = usePos();
        this.orm = useService("orm");
        this.dest_tr = useRef("dest_tr");
        this.source_tr = useRef("source_tr");
        this.type_transfer = useRef("type_transfer");
        this.note = useRef("note");
        this.source_loc = useRef("source_loc");
        this.dest_loc = useRef("dest_loc");
        this.stage = useRef("state");
        this.state = useState({
          selectedWO: false,
          selectedWD: false,
          warehouse_origin: false,
          company_id: this.pos.company.id,
          isProcessing: false,  // Guard para evitar doble envío
        });

//        console.log("ver el thisss", this)

        onWillStart(async () => {
            this.state.selectedWO = await this.orm.call(
                'stock.picking',
                'get_warehouse_from_config',
                [[this.pos.pos_session.config_id[0]]],
                {}
            );
        })
    }
       _clickPicking(ev){
       // This hide and show destination and source location based on the picking type selected
           var type = ev.target.selectedOptions[0].dataset.type
           this.source_tr.el.classList.remove('d-none')
           this.dest_tr.el.classList.remove('d-none')
           if (type == 'incoming') {
               this.source_tr.el.classList.add('d-none')
           }
           else if (type == 'outgoing') {
              this.dest_tr.el.classList.add('d-none')
           }
       }
        async Create(){
        // This get all the values you selected in the popup and transfer the stock by passing data backend.

            // Guard para evitar doble envío cuando se presiona Enter rápidamente
            if (this.state.isProcessing) {
                console.log("⚠️ Create ya está procesando, ignorando llamada duplicada");
                return;
            }
            this.state.isProcessing = true;

            const cashier = this.pos?.get_cashier();
            if (!cashier) {
                this.state.isProcessing = false;
                return;
            }

            var line = this.pos?.get_order()?.orderlines?.filter((line) => line.product?.type == "product" && line.quantity > 0);


            console.log("aaa", line)

            if(line.length === 0){
                await this.env.services.popup.add(ErrorPopup, {
                    title: _t("Transferencia no válida"),
                    body: _t("No hay productos válidos para transferir. "
                            + "Revise que las cantidades sean mayores a cero y sin valores negativos."),
                });
                this.state.isProcessing = false;
                return; // Importante: detener la ejecución si no hay productos
            }



            const cashierHash = cashier.barcode;
            const employee = this.pos.employees.find(emp => emp.barcode === cashierHash);

            // Verificar si el empleado necesita PIN
            let pinVerified = false;
            if (employee) {
                if (!employee.pin) {
                    // No tiene PIN configurado, puede continuar
                    pinVerified = true;
                } else {
                    // Tiene PIN, necesita verificación
                    pinVerified = await this.checkPin(employee);
                }
            }

            if (!pinVerified) {
                // Si no se verificó el PIN, no continuar pero tampoco cerrar el popup
                this.state.isProcessing = false;
                return;
            }

            // Continuar con la creación de la transferencia
            var type_transfer = this.type_transfer.el.value;
            var note = this.note.el.value;



            var product = {'pro_id':[],'qty':[]}

            for(var i=0; i<line.length;i++){
                 product['pro_id'].push(line[i].product.id)
                 product['qty'].push(line[i].quantity)
            }

            var self = this;
            await this.orm.call(
            "pos.config", "create_transfer", [this.state.selectedWO,this.state.selectedWD, type_transfer, note, product], {}
            ).then(async function(result) {
                self.pos.popup.add(TransferRefPopup, {
                    data: result
                });

                // Actualizar el stock localmente de forma inmediata
                // La notificación del bus llegará después, pero esto hace la actualización visual instantánea
                for (let i = 0; i < product['pro_id'].length; i++) {
                    const productId = product['pro_id'][i];
                    const qty = product['qty'][i];
                    const prod = self.pos.db.product_by_id[productId];
                    if (prod && prod.pos_stock_available !== undefined) {
                        // Reducir el stock disponible por la cantidad transferida
                        prod.pos_stock_available = Math.max(0, prod.pos_stock_available - qty);
                        console.log(`📦 Stock reducido localmente para producto ${productId}: ${prod.pos_stock_available}`);
                    }
                }
            })

            const order = this.pos?.get_order();
            const orderlines = order?.get_orderlines() ?? [];

            orderlines.forEach((orderline) => {
                order.removeOrderline(orderline);
            });

           this.cancel();

        }

        onUpdateSelectedWO(selectedWO){
            this.state.selectedWO = selectedWO;
        }

        onUpdateSelectedWD(selectedWD){
            this.state.selectedWD = selectedWD;
        }


        async checkPin(employee) {
            const { confirmed, payload: inputPin } = await this.env.services.popup.add(NumberPopup, {
                isPassword: true,
                title: _t("Password?"),
            });

            if (!confirmed) {
                return false;
            }

            if (employee.pin !== Sha1.hash(inputPin)) {
                await this.env.services.popup.add(ErrorPopup, {
                    title: _t("Incorrect Password"),
                    body: _t("Please try again."),
                });
                return false;
            }
            return true;
        }
}
