/** @odoo-module **/
import {ProductInfoPopup} from "@point_of_sale/app/screens/product_screen/product_info_popup/product_info_popup";
import {patch} from "@web/core/utils/patch";
import {useService} from "@web/core/utils/hooks";
import {useState} from "@odoo/owl";
import {PopupVademecum} from "./info_popup";

patch(ProductInfoPopup.prototype, {
    setup() {
        super.setup();
        this.dialogService = useService("dialog");

        this.state = useState({
            medicines: [],
        });
        this.pos = useService("pos");

        this.selectMedicineInPopup = this.selectMedicineInPopup.bind(this);
    },

    async selectMedicineInPopup(medicineName) {
        if (this.pos) {
            this.pos.searchProductWord = medicineName;
        }

        if (this.props.close) {
            this.props.close();
        }
    },


    async searchMedicine() {
        const productId = this.props.product.product_tmpl_id;
        try {
            const alternatives = await this.orm.call('product.template', 'vademecum_products', [productId]);

            if (alternatives && alternatives.length > 0) {
                this.state.medicines = alternatives;
            } else {
                this.state.medicines = [];
            }

            this.dialogService.add(PopupVademecum, {
                medicines: this.state.medicines || [],
                selectMedicine: this.selectMedicineInPopup,
                close: this.cancel.bind(this),
            });
        } catch (error) {
            console.error("Error en la búsqueda de productos", error);
            this.state.medicines = [];
        }
    }

});
