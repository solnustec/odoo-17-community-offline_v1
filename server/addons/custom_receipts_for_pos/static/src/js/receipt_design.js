/** @odoo-module **/

import {OrderReceipt} from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import {Orderline} from "@point_of_sale/app/store/models";
import {patch} from "@web/core/utils/patch";
import {Component, useState, xml} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";

// ✅ Patch para Orderline
patch(Orderline.prototype, {
    setup(_defaultObj, options) {
        super.setup(...arguments);
        if (options.json && options.json.reward_product_id) {
            this._reward_product_id = options.json.reward_product_id;
            this._program_id = options.json.program_id;
            this._original_id_reward = options.json.original_id_reward;
        }
    },

    getDisplayData() {
        const originalData = super.getDisplayData();
        return {
            ...originalData,
            id: this.get_id(),
            product_id: this.get_product_id(),
            is_reward_line: this.get_is_reward_line(),
            refunded_orderline_id: this.get_refunded_orderline_id(),
            reward_id: this.get_reward_id(),
            reward_product_id: this.get_reward_product_id(),
        };
    },

    get_id() {
        return this.id;
    },

    get_product_id() {
        return this.product.id;
    },

    get_refunded_orderline_id() {
        return this.refunded_orderline_id;
    },

    get_reward_id() {
        return this.reward_id;
    },

    get_is_reward_line() {
        return this.is_reward_line;
    },

    get_reward_product_id() {
        return this._reward_product_id;
    },
});

// ✅ Patch de OrderReceipt
patch(OrderReceipt.prototype, {
    setup() {
        super.setup();
        this.rpc = useService("rpc");
        this.state = useState({
            template: true,
            showCoupons: this.props?.data?.print_coupons !== false,
            branch_point_of_sale: ''
        });
        this.pos = useState(useService("pos"));
        this.BrachPointOfSaleLoad()
    },

    async BrachPointOfSaleLoad() {
        try {
            const config = await this.rpc('/get_warehouse', {
                pos_session_id: this.pos.pos_session.id,
            });
            this.props.data.sucursal = config.name || '';
        } catch (error) {
            console.error("Error al cargar la configuración de Deuna:", error);
        }
    },


    get templateProps() {
        if (!this._processedOrderlines) {
            const data_orderlines = this.props.data.orderlines;
            this.props.data.is_refund_order = this.get_is_order_refund(data_orderlines);
            // Calcular taxincluded en JavaScript
            const difference = Math.abs(this.props.data.amount_total - this.props.data.total_with_tax || 0);
            this.props.data.taxincluded = difference <= 0.000001 ? 1 : 0;

            this._processedOrderlines = this.update_orderlines_without_discount_line(data_orderlines);
        }
        return {
            formatCurrency: this.env.utils.formatCurrency,
            pos: this.pos,
            data: this.props.data,
            showCoupons: this.state.showCoupons,
            receipt: this.props.data,
            orderlines: this._processedOrderlines,
            paymentlines: this.props.data.paymentlines,
        };
    },

    update_orderlines_without_discount_line(data_orderlines) {
        if (!data_orderlines || !Array.isArray(data_orderlines)) {
            return [];
        }

        if (this.props.data.is_refund_order) {
            data_orderlines = this.invert_orderlines_values(data_orderlines);
        }

        return data_orderlines.filter(orderline => {
            return !this.isDiscountLine(orderline);
        });
    },

    isDiscountLine(orderline) {
        return (
            (orderline.productName && orderline.productName.toLowerCase().includes("discount")) ||
            (orderline.productName && orderline.productName.toLowerCase().includes("descuento")) ||
            (orderline.price && parsePrice(orderline.price) < 0) ||
            (orderline.reward_product_id && parsePrice(orderline.price) !== 0)
        );
    },

    get_is_order_refund(orderlines) {
        if (orderlines) {
            return !!orderlines[0].refunded_orderline_id;
        }
    },

    invert_orderlines_values(data_orderlines) {
        return data_orderlines.map((orderline) => ({
            ...orderline,
            qty: orderline.qty
                ? String(-parseFloat(orderline.qty.replace(",", "."))).replace(".", ",")
                : orderline.qty,
            price: orderline.price
                ? "$ " +
                String(
                    -parseFloat(orderline.price.replace("$", "").replace(",", "."))
                ).replace(".", ",")
                : orderline.price,
        }));
    },

    get templateComponent() {
        const mainRef = this;
        const showCoupons = mainRef.state.showCoupons;

        const generateTemplate2 = () => {
            return `
        <br />
        <div style="text-align:start; font-family: 'Courier New', monospace; font-size: 12px;page-break-before: always;font-weight: bold">
            <p>
                ${mainRef.props.data.name}<br />
                Cliente: ${mainRef.props.data.partner?.name || "N/A"}<br />
                Dirección: ${mainRef.props.data.partner?.address || "N/A"}<br />
                Teléfono: ${mainRef.props.data.partner?.mobile || "N/A"}<br />
                Email: ${mainRef.props.data.partner?.email || "N/A"}<br />
                Cédula/RUC: ${mainRef.props.data.partner?.vat || "N/A"}<br />
            </p>                  
        </div>
        <br />
      `;
        };

        const threshold = 10;
        const times = Math.floor(mainRef.props.data.amount_total / threshold);
        let dynamicTemplates = [];

        const enableCouponPrinting = mainRef.pos.company.enable_coupon_printing;
        if (showCoupons && enableCouponPrinting) {
            for (let i = 0; i < times; i++) {
                dynamicTemplates.push(generateTemplate2());
            }
        }

        return class extends Component {
            setup() {
            }

            get shouldPrintSecondReceipt() {
                return this.props.data.paymentlines.some((line) => {
                    const match = line.name.match(/^(CREDITO|TARJETA)/i);
                    const paymentCode = match ? match[0].toUpperCase() : "";
                    return paymentCode === "TARJETA" || paymentCode === "CREDITO";
                });
            }

            static template = xml`
        <div>
          <div>${mainRef.pos.config.design_receipt}</div>
          <t t-if="this.shouldPrintSecondReceipt">
            <div style="page-break-before: always;"></div>
            <div>${mainRef.pos.config.design_receipt}</div>
          </t>
          ${dynamicTemplates.map((template) => template)}
        </div>
      `;
        };
    },
});

function parsePrice(price) {
    return parseFloat(price.replace("$", "").replace(",", ".").trim());
}