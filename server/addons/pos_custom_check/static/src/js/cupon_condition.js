/** @odoo-module **/

import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { PromoCodeButton } from "@pos_loyalty/app/control_buttons/promo_code_button/promo_code_button";

// Reemplaza el botón original sin condición
ProductScreen.addControlButton({
    component: PromoCodeButton,
    position: ['replace', 'PromoCodeButton'],
    // Sin condición - siempre visible
});