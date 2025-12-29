/** @odoo-module **/
import {AbstractAwaitablePopup} from "@point_of_sale/app/popup/abstract_awaitable_popup";
import {_t} from "@web/core/l10n/translation";

export class CustomModal extends AbstractAwaitablePopup {
    static template = "CustomModalTemplate";
    static defaultProps = {
        closeText: _t("Regresar al punto de venta"),
        pos: null,
        laboratory: null,
        date_start: null,
        date_end: null,
        employee: null,
        date_print: null,
        tableData: null,
        registration_number: null,
        warehouse_name: null,
    };

    get total_missing() {
        return this.props.tableData
            ? this.props.tableData.reduce((acc, row) => acc + (Number(row.stock_missing) || 0), 0)
            : 0;
    }

    get total_left_over() {
        return this.props.tableData
            ? this.props.tableData.reduce((acc, row) => acc + (Number(row.stock_over) || 0), 0)
            : 0;
    }

    close() {
        this.cancel();
    }
} 