/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ProductCard } from "@point_of_sale/app/generic_components/product_card/product_card";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";

/** Popup propio, simple y sin dependencias de core especiales */
class PosImagePopup extends Component {
    static template = "pos_product_image_popup.PosImagePopup";
    static props = {
        title: { type: String, optional: true },
        imgUrl: String,
        confirmText: { type: String, optional: true },
        /** inyectado por el servicio popup: */
        close: Function,
    };
}

patch(ProductCard.prototype, {
    setup() {
        super.setup();
        this.popup = useService("popup");
    },

    async onImageExpandClick(ev) {
        ev.stopPropagation();
        const imgUrl = this.props.imageUrl;
        const name = this.props.name || "Imagen del producto";
        if (!imgUrl) return;

        // ⬇️ Montamos nuestro popup personalizado
        await this.popup.add(PosImagePopup, {
            title: name,
            imgUrl,
            confirmText: "Cerrar",
        });
    },
});
