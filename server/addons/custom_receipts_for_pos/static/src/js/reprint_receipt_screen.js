/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ReprintReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/reprint_receipt_screen";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { ConfirmPopup } from "@point_of_sale/app/utils/confirm_popup/confirm_popup";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";

patch(ReprintReceiptScreen.prototype, {
  setup() {
    super.setup();
    this.notificationService = useService("notification");
    this.pos = usePos();
    this.popup = useService("popup");
  },
  async tryReprint() {
    let printData;
    const { confirmed } = await this.popup.add(ConfirmPopup, {
      title: "Reimprimir Recibo",
      body: "¿Desea reimprimir el recibo?",
      confirmText: "Con Cupones",
      cancelText: "Sin Cupones",
    });

    printData = {
      ...this.props.order.export_for_printing(),
      print_coupons: confirmed,
    };

    this.printer.print(
      OrderReceipt,
      {
        data: printData,
        formatCurrency: this.env.utils.formatCurrency,
      },
      { webPrintFallback: true }
    );
  },
});
