/** @odoo-module **/
import {AbstractAwaitablePopup} from "@point_of_sale/app/popup/abstract_awaitable_popup";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {useService} from "@web/core/utils/hooks";
import {useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";

export class PopupKardex extends AbstractAwaitablePopup {
    static template = "pos_custom_check.ProductInfoPopup";

    setup() {
        super.setup();
        this.pos = usePos();
        this.popup = useService("popup");
        this.product = this.props.product;
        this.orm = useService("orm"); // Servicio ORM para llamadas al backend
        this.state = useState({
            startDate: this.props.startDate || "", // Valor por defecto
            filterType: this.props.filterType || "sales", // Valor por defecto
            filteredData: this.props.combinedData || [], // Datos iniciales
        });
    }

    onInputChangeSelect(event) {
        const field = event.target.getAttribute("data-field");
        const value = event.target.value;

        if (!field) {
            return;
        }

        // Actualiza correctamente el estado según el campo
        this.state[field] = value;

    }

    async applyFilter() {
        const pos_id = this.pos.config.point_of_sale_id;
        const productId = this.product.id;
        const filterType = this.state.filterType;
        const startDate = this.state.startDate || null;

        const warehouseIds = await this.orm.call('stock.warehouse', 'get_warehouses_by_external_ids', [pos_id]);

        const calls = {
            sales:   () => this.orm.call('stock.picking', 'get_pos_sales_by_warehouse', [warehouseIds, productId, startDate]),
            refunds: () => this.orm.call('stock.picking', 'get_pos_refunds_by_warehouse', [warehouseIds, productId, startDate]),
            transfers: () => this.orm.call('stock.picking', 'get_product_transfers_by_warehouse', [warehouseIds, productId, startDate]),
            all: async () => {
                const [salesRes, refundsRes, transfersRes] = await Promise.all([
                    calls.sales(),
                    calls.refunds(),
                    calls.transfers(),
                ]);
                return {
                    sales: salesRes.result.sales,
                    refunds: refundsRes.result.refund,
                    transfers: transfersRes.result.transfers,
                };
            },
        };

        let data = [];

        if (filterType === "sales") {
            const res = await calls.sales();
            data = res.result.sales;
        } else if (filterType === "refunds") {
            const res = await calls.refunds();
            data = res.result.refund;
        } else if (filterType === "transfers") {
            const res = await calls.transfers();
            data = res.result.transfers;
        } else if (filterType === "regulation") {
            data = [];
        } else if (filterType === "all") {
            const res = await calls.all();
            data = [...res.sales, ...res.refunds, ...res.transfers];
        }


        this.state.filteredData = data;
    }

    _rowDate(row) {
        return row.date_order || row.date || row.date_done || null;
    }

    getDataWithBalance() {
        let balance = 0;

        // 1) Orden cronológico (más antiguo primero)
        const sorted = [...this.state.filteredData].sort((a, b) => {
            const ad = this._rowDate(a) ? new Date(this._rowDate(a)) : new Date(0);
            const bd = this._rowDate(b) ? new Date(this._rowDate(b)) : new Date(0);
            return ad - bd;
        });

        // 2) Invertir el array para procesar del más reciente al más antiguo
        const reversed = [...sorted].reverse();

        // 3) Calcular balance empezando desde el último registro (más reciente)
        const withBalance = reversed.map((row, index) => {
            const entrada = parseFloat(row.quantity_in) || 0;
            const salidaRaw = row.quantity_out ?? row.quantity;
            const salida = parseFloat(salidaRaw) || 0;
            const saldo = parseFloat(row.stock) || 0;

            if (index === 0) {
                // El primer registro procesado (más reciente) tiene el saldo real
                balance = saldo;
            } else {
                // Para ir hacia atrás en el tiempo: deshacemos las operaciones del registro anterior
                // balance_anterior = balance_actual - entradas_posteriores + salidas_posteriores
                const registroAnterior = reversed[index - 1];
                const entradaAnterior = parseFloat(registroAnterior.quantity_in) || 0;
                const salidaAnterior = parseFloat(registroAnterior.quantity_out ?? registroAnterior.quantity) || 0;

                balance = balance - entradaAnterior + salidaAnterior;
            }

            return {
                ...row,
                balance: Number(balance).toFixed(0)
            };
        });

        // 4) Volver al orden cronológico original (más antiguo primero)
        return withBalance;
    }


    confirm() {
        console.log("Confirmado:", this.product);
        // Aquí puedes implementar la lógica que necesites con el producto
    }

    cancel() {
        this.props.close({confirmed: false, payload: null});
    }
}
