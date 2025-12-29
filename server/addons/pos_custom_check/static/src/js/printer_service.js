/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PrinterService } from "@point_of_sale/app/printer/printer_service";
import { loadAllImages } from "@point_of_sale/utils";

patch(PrinterService.prototype, {
    async print(component, props, options) {
        const el = await this.renderer.toHtml(component, props);
        // Load all images before printing
        try {
            await loadAllImages(el);
            return await this.printHtml(el, options);

        } catch (e) {
            console.error("Images could not be loaded correctly", e);
        }


    },
});