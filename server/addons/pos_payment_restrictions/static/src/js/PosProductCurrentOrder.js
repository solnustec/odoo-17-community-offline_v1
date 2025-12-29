/** @odoo-module */
import {patch} from '@web/core/utils/patch';
import {PosStore} from "@point_of_sale/app/store/pos_store";
import {_t} from "@web/core/l10n/translation";
import {ConfirmPopup} from "@point_of_sale/app/utils/confirm_popup/confirm_popup";

patch(PosStore.prototype, {
  // async addProductToCurrentOrder(product, options = {}) {
  //   await super.addProductToCurrentOrder(...arguments)
  //   const product_name = product.display_name;
  //   console.log(product.get)
  //   if (product_name) {
  //     this.popup.add(ConfirmPopup, {
  //       title: _t("Existing orderlines"),
  //       body: product_name,
  //     });
  //
  //   }
  // }
})
