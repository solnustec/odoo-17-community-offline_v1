/** @odoo-module */
import {patch} from "@web/core/utils/patch";
import {OrderWidget} from "@point_of_sale/app/generic_components/order_widget/order_widget";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {useService} from "@web/core/utils/hooks";
import {useState, onWillUpdateProps, onMounted} from "@odoo/owl";
import {ConfirmPopup} from "@point_of_sale/app/utils/confirm_popup/confirm_popup";
import {_t} from "@web/core/l10n/translation";

patch(OrderWidget.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
        this.orm = useService("orm");
        this.popup = useService("popup");
        this.notification = useService("pos_notification");
        this.pos.order_widget = this;

        this.state = useState({
            isPricing: false,
            grossvalue: 0,
            previousLinesSignature: "",
            subtotalTax0: 0,
            subtotalTax15: 0,
            totalTax: 0,
            operationResult: 0,
        });

        this._computeToken = 0;

        this.state.previousLinesSignature = this.getLinesSignature(this.props.lines);

        onMounted(async () => {
            await this.refreshTotals(this.props.lines);
        });

        onWillUpdateProps(async (nextProps) => {
            const newSignature = await this.getLinesSignature(nextProps.lines);
            if (newSignature !== this.state.previousLinesSignature) {
                this.state.previousLinesSignature = newSignature;
            }
            await this.refreshTotals(nextProps.lines);
        });
    },

    async refreshTotals(lines) {
        const localToken = ++this._computeToken;
        try {
            this.state.isPricing = true;
            const order = this.pos.get_order();
            if (!order) return;

            // Si otro flujo (institucional) está actualizando precios, no recalculamos
            if (order._inInstitutionalUpdate) {
                await this.computeValues(lines);
                return;
            }

            // Solo recalcula precios base si no hay descuento institucional
            let institutionActive = false;
            try {
                const raw = localStorage.getItem("percentageInstitution");
                institutionActive = !!raw && JSON.parse(raw)?.additional_discount_percentage > 0;
            } catch {
                institutionActive = !!localStorage.getItem("percentageInstitution");
            }

            if (order.prices_update_in_lines && !institutionActive) {
                await order.prices_update_in_lines();
            }

            await this.computeValues(lines);
        } finally {
            if (localToken === this._computeToken) {
                this.state.isPricing = false;
            }
        }
    },


    set_grossvalue(val) {
        this.state.grossvalue = val;
    },

    async calculateGrossvalue(lines) {
        let total = 0;
        (lines || []).forEach((line) => {
//            if (!line.is_reward_line) {
            total += line.get_price_with_tax_before_discount();
//            }
        });
        return Number.isFinite(total) ? total.toFixed(2) : "0.00";
    },

    async computeValues(lines) {
        await this.update_extra_info_lines_discount(lines);

        let subtotalTax0 = 0;
        let subtotalTax15 = 0;
        let totalTax = 0;
        let operationResult = 0;

        (lines || []).forEach((line) => {
            const taxes = line.get_taxes();
            let taxRate = 0;

            if (taxes && taxes.length > 0) {
                taxRate = taxes.reduce((sum, tax) => sum + tax.amount, 0);
            }

            // precio sin impuesto que pudiera venir con o sin descuento
            const priceWithoutTax = line.get_price_without_tax();
            const discount = line.discount || 0;

            // Intentar obtener el precio con impuesto antes de descuento (método existente en el código)
            const priceWithTaxBeforeDiscount = (typeof line.get_price_with_tax_before_discount === 'function')
                ? line.get_price_with_tax_before_discount()
                : (priceWithoutTax * (1 + taxRate / 100));

            // Base sin impuesto antes de aplicar descuento (si taxRate === 0, es igual a priceWithTaxBeforeDiscount)
            const priceWithoutTaxBeforeDiscount = priceWithTaxBeforeDiscount / (1 + taxRate / 100);

            // Aplicar descuento solo una vez sobre la base antes del descuento
            const priceAfterDiscount = priceWithoutTaxBeforeDiscount * (1 - discount / 100);

            // Calcular impuesto: si es línea recompensa, calcular impuesto sobre la base sin descuento
            let taxAmount = 0;
            if (taxRate > 0) {
                if (line.is_reward_line) {
                    taxAmount = priceWithoutTaxBeforeDiscount * (taxRate / 100);
                } else {
                    taxAmount = priceAfterDiscount * (taxRate / 100);
                }
            }

            // Subtotal de la línea: si es recompensa usar base sin descuento; si no, usar precio con descuento
//            let lineSubtotal = line.is_reward_line ? priceWithoutTaxBeforeDiscount : priceAfterDiscount;
            let lineSubtotal = line.is_reward_line ? 0 : priceAfterDiscount;

            // Cálculo de operationResult solo para líneas con impuesto y que no sean recompensa
            if (taxRate > 0 && !line.is_reward_line) {
                const priceBase = lineSubtotal;
                const lineOperation = (priceBase - taxAmount) * 0.15;
                operationResult += lineOperation;
            }

            totalTax += taxAmount;

            if (taxRate === 0) {
                subtotalTax0 += lineSubtotal;
            } else if (taxRate === 15) {
                subtotalTax15 += lineSubtotal;
            }
        });


        this.state.subtotalTax0 = subtotalTax0.toFixed(2);
        this.state.subtotalTax15 = subtotalTax15.toFixed(2);
        this.state.totalTax = Number.isFinite(totalTax) ? Number(totalTax.toFixed(2)) : 0;
        this.state.operationResult = Number.isFinite(operationResult) ? Number(operationResult.toFixed(2)) : 0;

        const total_brute = await this.calculateGrossvalue(lines);
        this.set_grossvalue(total_brute);
    },

    getLinesSignature(lines) {
        return (lines || [])
            .map((line) => `${line.product.id}-${line.quantity}`)
            .sort()
            .join("|");
    },

    async update_extra_info_lines_discount(lines) {
        for (let normalLine of (lines || [])) {
            if (normalLine.is_reward_line) continue;

            const discountLines = (lines || []).filter(line =>
                line.reward_prod_id &&
                line.reward_prod_id === normalLine.product.id &&
                line.price !== 0
            );

            let discountLineToUse = null;
            if (discountLines.length > 0) {
                const negativeCouponLines = discountLines.filter(l => l.coupon_id && l.coupon_id < 0);
                const positiveCouponLines = discountLines.filter(l => l.coupon_id && l.coupon_id > 0);
                if (negativeCouponLines.length > 0) {
                    discountLineToUse = negativeCouponLines[0];
                } else if (positiveCouponLines.length > 0) {
                    discountLineToUse = positiveCouponLines[0];
                } else {
                    discountLineToUse = discountLines[0];
                }
            }

            if (discountLineToUse) {
                normalLine.set_percent_discount(discountLineToUse.percent_discount);
            } else {
                normalLine.set_percent_discount(0);
            }
        }
    },

    get orderedLines() {
        const lines = this.props.lines || [];
        const normalLines = [];
        const rewardLines = [];
        lines.forEach((line) => (line.is_reward_line ? rewardLines : normalLines).push(line));
        if (rewardLines.length > 0) {
            normalLines.push({
                uniqueKey: "separator",
                is_separator: true,
                productName: "Recompensas",
                getDisplayData: () => ({productName: "Recompensas"}),
            });
        }
        return [...normalLines, ...rewardLines];
    },

    get formattedGrossValue() {
        return this.state.isPricing
            ? _t("Cargando…")
            : this.env.utils.formatCurrency(this.state.grossvalue);
    },
    get formattedSubtotalTax0() {
        return this.state.isPricing
            ? _t("Cargando…")
            : this.env.utils.formatCurrency(this.state.subtotalTax0);
    },
    get formattedSubtotalTax15() {
        return this.state.isPricing
            ? _t("Cargando…")
            : this.env.utils.formatCurrency(this.state.subtotalTax15);
    },
    get formattedTotalTax() {
        return this.state.isPricing
            ? _t("Cargando…")
            : this.env.utils.formatCurrency(this.state.totalTax);
    },
    get formattedOperationResult() {
        return this.state.isPricing
            ? _t("Cargando…")
            : this.env.utils.formatCurrency(this.state.operationResult);
    },

    async deleteProductsOrder() {
        const order = this.pos.get_order();
        const lines = order.get_orderlines();
        if (lines.length) {
            const {confirmed} = await this.popup.add(ConfirmPopup, {
                title: 'Orden',
                body: '¿Quieres eliminar todos los productos de la orden?',
            });
            if (confirmed) {
                lines.filter(l => l.get_product()).forEach(l => order.removeOrderline(l));
                order._updateRewards(true, true);
            }
        } else {
            this.notification.add(_t("No hay productos para eliminar."), 3000);
        }
    },
});
