/** @odoo-module **/

import {Component, onWillStart, useState} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";

export class ProductDetailsModal extends Component {
    static template = "sales_report.ProductDetailsModal";
    // static props = {
    //     isOpen: {type: Boolean, optional: true},
    //     product: {type: Object},
    //     onClose: {type: Function, optional: true},
    //     onUpdateProduct: {type: Function, optional: true},
    // };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.local = useState({...(this.props.product || {})});
        this.state = useState({
            is_promotion_user: false,
            is_purchase_admin: true,
            isOpen: this.props.isOpen,
            // updateProductDiscount: this.props.updateProductDiscount,
            product_id: null,
            selectedProduct: {},
            pvp: 0,
            pvf: 0,
            priceWithDiscount: 0,
            purchaseHistoryOffset: 5,
            hasMorePurchases: true,
            isLoadingMore: false,
            currentPage: 1,
            totalPages: 1,
        });
        onWillStart(async () => {
            await this.getProductInfo(this.props.productId);
            this.state.product_id = this.props.productId
            this.state.is_promotion_user = this.props.is_promotion_user
            this.state.is_purchase_admin = this.props.is_purchase_admin
            // this.updatePriceWithDiscountAndUtility()
        });
    }

    close() {
        this.props.onClose?.();
    }

    addToCart() {
        this.props.onOpenCartModal(this.state.product_id);
    }

    // updateProductDiscount(){
    //     this.props.updateProductDiscount(this.state.product_id, this.state.selectedProduct.discount_percentage);
    // }

    //     Product information
    async getProductInfo(product_id) {

        // Get initial purchase history information for the product (7 items for infinite scroll)
        // This loads the first batch of purchase history records for display
        if (this.state.is_promotion_user) {

        }
        const productLastPurchase = await this.orm.call('product.product', 'get_complete_purchase_history', [product_id, 5, 0]);

        const productData = await this.orm.call("product.product", "get_product_info", [product_id]);

        // Resolver laboratorio y marca desde product.template si no vienen en ProductDetails
        let currentLaboratoryId = this.props.ProductDetails?.laboratory_id || null;
        let currentBrandId = this.props.ProductDetails?.brand_id || null;
        if (!currentLaboratoryId || !currentBrandId) {
            try {
                const tmplInfo = await this.orm.read("product.template", [productData.product_tmpl_id.id], [
                    "laboratory_id", "brand_id"
                ]);
                if (tmplInfo && tmplInfo.length) {
                    currentLaboratoryId = currentLaboratoryId || (tmplInfo[0].laboratory_id ? tmplInfo[0].laboratory_id[0] : null);
                    currentBrandId = currentBrandId || (tmplInfo[0].brand_id ? tmplInfo[0].brand_id[0] : null);
                }
            } catch (e) {
            }
        }
        const currentLaboratory = (this.props.laboratories || []).find(l => l.id === currentLaboratoryId);
        const currentBrand = (this.props.brands || []).find(b => b.id === currentBrandId);


        const coupons = [
            {value: 0, title: "No Aplica", selected: false},
            {value: 1, title: "Por Unidad", selected: false},
            {value: 2, title: "Por Cajas", selected: false},
            {value: 3, title: "2do. con Descuento", selected: false},
        ]
        coupons.map(coupon => {
            coupon.selected = coupon.value === productData.product_tmpl_id.coupon;
        })
        const price_with_discount = productData.product_tmpl_id.price_with_tax - (productData.product_tmpl_id.price_with_tax * (productData.product_discount / 100));
        const cost_include_taxes = productData.product_tmpl_id.avg_standar_price_old * (1 + (productData.product_tmpl_id.supplier_taxes_info.amount / 100))
        const utility = ((price_with_discount - cost_include_taxes) / cost_include_taxes) * 100
        //Programs
        const programs = productData.loyalty_program || [];
        //Program_type
        const promotion_program = programs.find(p => p.program_type === 'promotion') || null;
        //const promotion_loyalty_card_program_list= programs.filter(p => p.program_type === 'promotion' || p.program_type === 'loyalty') || null;
        //const promotion_loyalty_card_program_2 = promotion_loyalty_card_program_list.find(p => p.applies_to_the_second === true) || null;
        //const promotion_loyalty_card_program_2 = programs.find(p => p.applies_to_the_second === true) || null;
        const loyalty_card_program = programs.find(p => p.program_type === 'loyalty') || null;
        const coupon_program = programs.find(p => p.program_type === 'coupons') || null;
        //Rules
        const promotion_rule = productData.rules_data.find(r => r.program_id === promotion_program?.id) || null;
        const coupon_rule = productData.rules_data.find(r => r.program_id === coupon_program?.id) || null;
        //Discount reward
        //const promotion_reward_discount = productData.reward_discount.find(r => r.program_id === promotion_program?.id) || null;
        //const promotion_reward_discount = promotion_reward_discount_list[0] || null;
        //const promotion_reward_discount_2 = promotion_reward_discount_list[1] || null;
        const promotion_reward_discount_list = productData.reward_discount.filter(r => r.program_id === promotion_program?.id) || [];
        const promotion_reward_discount = promotion_reward_discount_list.find(r => r.is_main === false && r.is_temporary === false) || null;
        const promotion_temporary_reward_discount = promotion_reward_discount_list.find(r => r.is_main === false && r.is_temporary === true) || null;
        const promotion_reward_discount_2 = promotion_reward_discount_list.find(r => r.is_main === true) || null;
        //const loyalty_card_reward_discount = productData.reward_discount.find(r => r.program_id === loyalty_card_program?.id) || null;
        //const loyalty_card_reward_discount = loyalty_card_reward_discount_list[0] || null;
        //const loyalty_card_reward_discount_2 = loyalty_card_reward_discount_list[1] || null;
        const loyalty_card_reward_discount_list = productData.reward_discount.filter(r => r.program_id === loyalty_card_program?.id) || [];
        const loyalty_card_reward_discount = loyalty_card_reward_discount_list.find(r => r.is_main === false && r.is_temporary === false) || null;
        const loyalty_card_temporary_reward_discount = loyalty_card_reward_discount_list.find(r => r.is_main === false && r.is_temporary === true) || null;
        const loyalty_card_reward_discount_2 = loyalty_card_reward_discount_list.find(r => r.is_main === true) || null;
        const coupon_reward_discount = productData.reward_discount.find(r => r.program_id === coupon_program?.id) || null;
        //Product reward
        const promotion_reward_product = productData.reward_product.find(r => r.program_id === promotion_program?.id) || null;
        const loyalty_card_reward_product = productData.reward_product.find(r => r.program_id === loyalty_card_program?.id) || null;
        const coupon_reward_product = productData.reward_product.find(r => r.program_id === coupon_program?.id) || null;
        //Loyalty_Card state
        const loyalty_card = !!loyalty_card_program;
        //Flag para recompensa de descuento temporal
        //const is_temporary = promotion_reward_discount?.is_temporary || false;


        this.state.selectedProduct = {
            "id": product_id,
            "utility": this.props.ProductDetails.utility,
            "product_tmpl_id": productData.product_tmpl_id.id,
            "name": productData.product_tmpl_id.name || null,

            "standard_price": this.props.ProductDetails.standar_price_old,
            "avg_standard_price": productData.product_tmpl_id.avg_standar_price_old,
            "program_note": promotion_program?.note_promotion || loyalty_card_program?.note_promotion || '',
            // standard_price_taxer: standard_price_taxer,
            "list_price": productData.product_tmpl_id.list_price,
            "tax_string": productData.product_tmpl_id?.tax_string || "",
            "name_unidad": productData.product_tmpl_id.uom_id_name,
            "id_unidad": productData.product_tmpl_id.uom_id,
            "name_po_unidad": productData.product_tmpl_id.uom_po_id_name,
            "id_po_unidad": productData.product_tmpl_id.uom_po_id,
            "taxer_amount": productData.product_tmpl_id.tax_amount || 0,
            "price_with_tax": productData.product_tmpl_id.price_with_tax.toFixed(2),
            "supplier_tax": productData.product_tmpl_id.supplier_taxes_info.amount,
            "price_with_taxer": productData.product_tmpl_id.price_with_tax.toFixed(2),
            "price_with_discount": price_with_discount.toFixed(2),
            "price_base_with_discount": price_with_discount,
            "utility_percentage": utility.toFixed(2),
            "quantity_general": productData.product_tmpl_id?.qty_available || 0,
            "loyalty_program_id": promotion_program?.id || null,
            "loyalty_card_program_id": loyalty_card_program?.id || null,
            "loyalty_coupon_program_id": coupon_program?.id || null,
            //"loyalty_program_date_from": promotion_program?.date_from || loyalty_card_program?.date_from || null,
            //"loyalty_program_date_to": promotion_program?.date_to || loyalty_card_program?.date_to || null,
            "loyalty_program_discount_date_from": promotion_reward_discount?.date_from || loyalty_card_reward_discount?.date_from || promotion_temporary_reward_discount?.date_from || loyalty_card_temporary_reward_discount?.date_from || null,
            "loyalty_program_discount_date_to": promotion_reward_discount?.date_to || loyalty_card_reward_discount?.date_to || promotion_temporary_reward_discount?.date_to || loyalty_card_temporary_reward_discount?.date_to|| null,
            "loyalty_program_product_date_from": promotion_reward_product?.date_from || loyalty_card_reward_product?.date_from || null,
            "loyalty_program_product_date_to": promotion_reward_product?.date_to || loyalty_card_reward_product?.date_to || null,
            "program_mandatory": promotion_program?.mandatory_promotion || loyalty_card_program?.mandatory_promotion || false,
            "coupon_program_mandatory": coupon_program?.mandatory_promotion || false,
            "discount_percentage": productData.product_discount || 0,
            "temporary_discount_percentage": productData.temporary_product_discount || 0,
            "coupon_discount_percentage": coupon_reward_discount?.discount || promotion_reward_discount_2?.discount || loyalty_card_reward_discount_2?.discount || 0,
            "discount_reward_id": promotion_reward_discount?.id || null,
            "temporary_discount_reward_id": promotion_temporary_reward_discount?.id || null,
            "discount_reward_id_2": promotion_reward_discount_2?.id || null,
            "loyalty_card_discount_reward_id": loyalty_card_reward_discount?.id || null,
            "loyalty_card_temporary_discount_reward_id": loyalty_card_temporary_reward_discount?.id || null,
            "loyalty_card_discount_reward_id_2": loyalty_card_reward_discount_2?.id || null,
            "coupon_discount_reward_id": coupon_reward_discount?.id || null,
            // promociones producto gratis
            "product_reward_required_points": promotion_reward_product?.required_points || loyalty_card_reward_product?.required_points || null,
            "product_reward_qty": promotion_reward_product?.reward_product_qty || loyalty_card_reward_product?.reward_product_qty || null,
            "product_reward_id": promotion_reward_product?.id || null,
            "loyalty_card_product_reward_id": loyalty_card_reward_product?.id || null,
            "coupon_product_reward_id": coupon_reward_product?.id || null,
            "last_purchase_info": productLastPurchase.length > 0 || [],
            "loyalty_card": loyalty_card,
            "coupons": coupons,
            "promotion_rule_id": promotion_rule?.id || null,
            "coupon_rule_id": coupon_rule?.id || null,
            //"coupon_loyalty_program_date_from": coupon_program?.date_from || promotion_loyalty_card_program_2?.date_from || null,
            //"coupon_loyalty_program_date_to": coupon_program?.date_to || promotion_loyalty_card_program_2?.date_to || null,
            "coupon_loyalty_program_discount_date_from": coupon_reward_discount?.date_from || promotion_reward_discount_2?.date_from || loyalty_card_reward_discount_2?.date_from || null,
            "coupon_loyalty_program_discount_date_to": coupon_reward_discount?.date_to || promotion_reward_discount_2?.date_to || loyalty_card_reward_discount_2?.date_to || null,
            //"is_temporary": is_temporary,
        };

        // Valores actuales de laboratorio y marca
        this.state.selectedProduct.laboratory_id = currentLaboratory ? currentLaboratory.id : null;
        this.state.selectedProduct.brand_id = currentBrand ? currentBrand.id : null;
        this.state.selectedProduct.laboratory_name = currentLaboratory ? currentLaboratory.name : null;
        this.state.selectedProduct.brand_name = currentBrand ? currentBrand.name : null;

        // Initialize infinite scroll state management
        // These variables control the pagination and loading behavior
        this.state.product_id = product_id;
        this.state.purchaseHistoryOffset = 5; // Next offset to load (starts after initial 7 items)
        this.state.hasMorePurchases = productLastPurchase.length >= 5; // Check if more data is available
        this.state.isLoadingMore = false; // Prevents multiple simultaneous requests

        this.state.showProductModal = true;
    }

    async onChangeProductBrandLaboratory(product_id, laboratory_id, brand_id) {
        try {
            await this.orm.call(
                "product.product",
                "write",
                [[product_id], {
                    laboratory_id: laboratory_id,
                    brand_id: brand_id
                }]
            );
        } catch (error) {
            console.error("Error al cambiar la marca y laboratorio:", error);
        }
    }

    onLaboratoryChange(ev) {
        const laboratory_id = ev.target.value ? parseInt(ev.target.value) : null;
        this.state.selectedProduct.laboratory_id = laboratory_id;
        const currentLaboratory = (this.props.laboratories || []).find(l => l.id === laboratory_id);
        this.state.selectedProduct.laboratory_name = currentLaboratory ? currentLaboratory.name : null;

    }

    onBrandChange(ev) {
        const brand_id = ev.target.value ? parseInt(ev.target.value) : null;
        this.state.selectedProduct.brand_id = brand_id;
        const currentBrand = (this.props.brands || []).find(b => b.id === brand_id);
        this.state.selectedProduct.brand_name = currentBrand ? currentBrand.name : null;

    }

    onPurchaseOrderChange(event) {
        const orderId = event.target.value;
        this.state.selectedPurchaseOrderId = orderId ? parseInt(orderId) : null;
    }


    async openStock() {
        if (!this.state.product_id) {
            return;
        }
        try {
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Stock",
                res_model: "stock.quant",
                views: [
                    [false, "tree"],
                    [false, "form"]
                ],
                domain: [["product_id", "=", this.props.productId], ["location_id.replenish_location", "=", true]],
                context: {
                    multi_select: true,
                    create: false,
                    inventory_mode: false,
                    default_product_id: this.props.productId,
                },
                target: "new",
            }).then(() => {
                setTimeout(() => {
                    const controlPanel = document.querySelector('.o_control_panel_breadcrumbs');
                    if (controlPanel) {
                        controlPanel.classList.add('d-none');
                    }
                }, 100);
            });
        } catch (error) {
            this.notification.add("Error al abrir stock.", error, {type: 'danger'});
        }
    }

    async openMovementHistory() {
        if (!this.state.product_id) {
            return;
        }
        try {
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Historial de Movimientos",
                res_model: "stock.move.line",
                views: [
                    [false, "tree"],
                    [false, "form"]
                ],
                domain: [["product_id", "=", this.props.productId]],
                context: {
                    multi_select: true,
                    default_product_id: this.props.productId,
                },
                target: "new",
            });
        } catch (error) {
            this.notification.add("Error al abrir el historial de movimientos.", error, {type: 'danger'});
        }
    }

    async openPromotionProgram() {
        // if (!this.state.selectedProduct.loyalty_promo_program_id) {
        //     this.showError("Programa de Promoción no disponible.");
        //     return;
        // }
        try {
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Promociones",
                res_model: "loyalty.program",
                res_id: this.state.selectedProduct.loyalty_program_id,
                views: [[false, "form"]],
                target: "new",
            });
        } catch (error) {
            this.notification.add("Error al abrir el Programa de Promoción.", error, {type: 'danger'});
        }
    }

    onListPriceChange(ev) {
        this.state.selectedProduct.list_price = parseFloat(ev.target.value) || 0;
        const discount_percentage_to_send = this.state.selectedProduct.temporary_discount_percentage || this.state.selectedProduct.discount_percentage
        this.updatePriceWithDiscountAndUtility(this.state.selectedProduct.list_price, discount_percentage_to_send);
        this.render();
    }

    onNameChange(ev) {
        this.state.selectedProduct.name = ev.target.value;
    }

    // promociones
    onMandatoryPromotionChange(ev) {
        this.state.selectedProduct.program_mandatory = ev.target.checked;
    }

    onMandatoryCouponChange(ev) {
        this.state.selectedProduct.coupon_program_mandatory = ev.target.checked;
    }

    onStartDateDiscountPromotionChange(ev) {
        this.state.selectedProduct.loyalty_program_discount_date_from = ev.target.value || null;
    }

    onEndDateDiscountPromotionChange(ev) {
        this.state.selectedProduct.loyalty_program_discount_date_to = ev.target.value || null;
    }

    onStartDateProductPromotionChange(ev) {
        this.state.selectedProduct.loyalty_program_product_date_from = ev.target.value || null;
    }

    onEndDateProductPromotionChange(ev) {
        this.state.selectedProduct.loyalty_program_product_date_to = ev.target.value || null;
    }

    onStartDateDiscountCouponPromotionChange(ev) {
        this.state.selectedProduct.coupon_loyalty_program_discount_date_from = ev.target.value || null;
    }

    onEndDateDiscountCouponPromotionChange(ev) {
        this.state.selectedProduct.coupon_loyalty_program_discount_date_to = ev.target.value || null;
    }

    onEndDateRewardChange(ev) {
        this.state.selectedProduct.end_date_reward = ev.target.value;
    }

    onRewardQuantityChange(ev) {
        this.state.selectedProduct.product_reward_qty = parseFloat(ev.target.value) || 0;
    }

    onRewardProductChangeRequiredPoints(ev) {
        this.state.selectedProduct.product_reward_required_points = parseFloat(ev.target.value) || 0;
    }

    onDiscountPromotionChange(ev) {
        this.state.selectedProduct.discount_percentage = ev.target.value || 0;

        // Si se ingresa descuento normal mayor a cero y el temporal es mayor a cero:
        // Se borra el descuento temporal y las fechas.
        if (this.state.selectedProduct.discount_percentage>0 && this.state.selectedProduct.temporary_discount_percentage>0) {
            this.state.selectedProduct.temporary_discount_percentage = 0;
            this.state.selectedProduct.loyalty_program_discount_date_from = null;
            this.state.selectedProduct.loyalty_program_discount_date_to = null;
        }
        // this.state.selectedProduct.price_with_discount = (this.state.selectedProduct.price_with_tax - (this.state.selectedProduct.price_with_tax * (this.state.selectedProduct.discount_percentage / 100))).toFixed(2);
        this.updatePriceWithDiscountAndUtility(null, this.state.selectedProduct.discount_percentage);
        this.render();
    }

    onDiscountTemporaryPromotionChange(ev) {
        this.state.selectedProduct.temporary_discount_percentage = ev.target.value || 0;

        // Si se ingresa descuento temporal mayor a cero y el normal es mayor a cero:
        // Se borra el descuento normal y las fechas.
        if (this.state.selectedProduct.temporary_discount_percentage>0 && this.state.selectedProduct.discount_percentage>0) {
            this.state.selectedProduct.discount_percentage = 0;
            this.state.selectedProduct.loyalty_program_discount_date_from = null;
            this.state.selectedProduct.loyalty_program_discount_date_to = null;
        }
        this.updatePriceWithDiscountAndUtility(null, this.state.selectedProduct.temporary_discount_percentage);
        this.render();
    }

    onDiscountCouponChange(ev) {
        this.state.selectedProduct.coupon_discount_percentage = parseFloat(ev.target.value) || 0;
    }

    onChangeCoupon(ev) {
        const selectedValue = ev.target.checked;
        const value = ev.target.value;
        this.state.selectedProduct.coupons.map(
            (coupon) => {
                if (coupon.value === parseInt(value)) {
                    coupon.selected = selectedValue;
                } else {
                    coupon.selected = false;
                }
            }
        );

        this.render();
    }

    onChangeLoyaltyCard(ev) {
        this.state.selectedProduct.loyalty_card = ev.target.checked;
    }

    onChangeProgramNote(ev) {
        this.state.selectedProduct.program_note = ev.target.value;
    }

    updatePriceWithDiscountAndUtility(list_price = null, function_discount_percentage) {
        /*
        Formula de utilidad
        * ---------------------------------------------
        * pvp incluido el descuento - costo incluido el impuesto
        * ---------------------------------------------  * 100
        *          costo incluido el impuesto
        * */
        //si no ntiene costo promeido usar el ultimo costo
        // if (parseFloat(this.state.selectedProduct.avg_standard_price) > 0) {
        //     console.log('this.state.selectedProduct.avg_standard_price', this.state.selectedProduct.avg_standard_price)
        const pvp_include_discount = this.state.selectedProduct.price_with_tax - (this.state.selectedProduct.price_with_tax * (function_discount_percentage / 100)
            )
        ;
        const cost_incluce_tax = this.state.selectedProduct.avg_standard_price * (1 + (this.state.selectedProduct.supplier_tax / 100));
        const utility = ((pvp_include_discount - cost_incluce_tax) / cost_incluce_tax) * 100;
        this.state.selectedProduct.price_with_discount = pvp_include_discount.toFixed(4);
        this.state.selectedProduct.utility_percentage = utility.toFixed(2);
        // } else {
        //     console.log('this.state.selectedProduct.standar_price_old', this.state.selectedProduct)
        //     console.log('this.state.selectedProduct.standar_price_old', this.state.selectedProduct.standard_price)
        //     const pvp_include_discount = this.state.selectedProduct.price_with_tax - (this.state.selectedProduct.price_with_tax * (this.state.selectedProduct.discount_percentage / 100));
        //     const cost_incluce_tax = this.state.selectedProduct.standard_price * (1 + (this.state.selectedProduct.supplier_tax / 100));
        //     const utility = ((pvp_include_discount - cost_incluce_tax) / cost_incluce_tax) * 100;
        //     this.state.selectedProduct.price_with_discount = pvp_include_discount.toFixed(4);
        //     this.state.selectedProduct.utility_percentage = utility.toFixed(2);
        // }
        // if (!list_price) {
        //     this.state.pvf = this.state.selectedProduct.standard_price || 0;
        //     this.state.pvp = this.state.selectedProduct.price_with_taxer || 0;
        //     const discount_percentage = this.state.selectedProduct.discount_percentage || 0;
        //     if (discount_percentage) {
        //         const price_with_discount = parseFloat(this.state.pvp) * (parseFloat(discount_percentage) / 100);
        //         const pvp_discount = parseFloat(this.state.pvp) - price_with_discount;
        //         if (this.state.pvf > 0 && this.state.pvp > 0) {
        //             const utility = ((pvp_discount.toFixed(2) - this.state.pvf) / this.state.pvf) * 100;
        //             this.state.selectedProduct.utility_percentage = utility.toFixed(2);
        //         } else {
        //             this.state.selectedProduct.utility_percentage = 'N/A';
        //         }
        //     }
        // } else {
        //     let pvp = list_price || 0;
        //     const taxer_amount = this.state.selectedProduct.taxer_amount || 0;
        //     this.state.selectedProduct.price_with_taxer = (1 + (parseFloat(taxer_amount) / 100)) * parseFloat(pvp).toFixed(2);
        //     let pvf = this.state.selectedProduct.standard_price || 0;
        //     const discount_percentage = this.state.selectedProduct.discount_percentage || 0;
        //     if (discount_percentage) {
        //         const price_with_discount = parseFloat(this.state.selectedProduct.price_with_taxer) * (parseFloat(discount_percentage) / 100);
        //         const pvp_discount = parseFloat(this.state.selectedProduct.price_with_taxer) - price_with_discount;
        //         if (pvf > 0 && this.state.selectedProduct.price_with_taxer > 0) {
        //             const utility = ((pvp_discount.toFixed(2) - pvf) / pvf) * 100;
        //             this.state.selectedProduct.utility_percentage = utility.toFixed(2);
        //         } else {
        //             this.state.selectedProduct.utility_percentage = 'N/A';
        //         }
        //     }
        // }

    }

    async validateForm() {
        if (!this.state.selectedProduct.name || this.state.selectedProduct.name.trim() === "") {
            this.notification.add("El nombre del producto no puede estar vacío.", {type: "danger"});
            return false;
        }
        if (this.state.selectedProduct.list_price == null || isNaN(this.state.selectedProduct.list_price) || this.state.selectedProduct.list_price <= 0) {
            this.notification.add("El precio de lista debe ser un número válido y no puede ser negativo.", {type: "danger"});
            return false;
        }
        if (this.state.selectedProduct.discount_percentage < 0 || this.state.selectedProduct.discount_percentage > 100) {
            this.notification.add("El porcentaje de descuento debe estar entre 0 y 100.", {type: "danger"});
            return false;
        }
        if (this.state.selectedProduct.product_reward_qty < 0) {
            this.notification.add("El campo Base no puede ser negativo.", {type: "danger"});
            return false;
        }
        if (this.state.selectedProduct.product_reward_required_points < 0) {
            this.notification.add("El campo Promoción no pueden ser negativo.", {type: "danger"});
            return false;
        }
        if (this.state.selectedProduct.loyalty_program_product_date_from && this.state.selectedProduct.loyalty_program_product_date_to) {
            const startDate = new Date(this.state.selectedProduct.loyalty_program_product_date_from);
            const endDate = new Date(this.state.selectedProduct.loyalty_program_product_date_to);
            if (startDate > endDate) {
                this.notification.add("La fecha de inicio de la recompensa de productos gratis no puede ser posterior a la fecha de fin.", {type: "danger"});
                return false;
            }
        }
        // si el campo  product_reward_required_points es mayor a cero y product_reward_qty es mayor a cero los campo de fechas son obligatorios
        if (this.state.selectedProduct.product_reward_required_points > 0 && this.state.selectedProduct.product_reward_qty > 0) {
            if (!this.state.selectedProduct.loyalty_program_product_date_from || !this.state.selectedProduct.loyalty_program_product_date_to) {
                this.notification.add("Las fechas de inicio y fin de la recompensa de producto gratis son obligatorias cuando se especifican puntos y cantidad de promoción.", {type: "danger"});
                return false;
            }
        }
        // si se ingresa un porcentaje de descuento menor a cero o mayor a 100 para el programa de cupones
        if (this.state.selectedProduct.coupon_discount_percentage < 0 || this.state.selectedProduct.coupon_discount_percentage > 100) {
            this.notification.add("El porcentaje de descuento para el programa de cupones debe estar entre 0 y 100.", {type: "danger"});
            return false;
        }
        // no se puede ingresar un descuento vacio o igual a cero para crear/actualizar un programa de cupones igual a 3
        //if (!this.state.selectedProduct.coupon_discount_percentage || Math.round(this.state.selectedProduct.coupon_discount_percentage) === 0) {
        //    const coupon_value = this.state.selectedProduct.coupons.find(coupon => coupon.selected).value || 0
        //    if (coupon_value === 3) {
        //        this.notification.add("No se puede ingresar vacio o cero el descuento para crear/actualizar un programa de cupones de tipo 3", {type: "danger"});
        //        return false;
        //    }
        //}
        // si para el programa de cupones se ingresa una fecha de inicio mayor que la fecha de finalización
        if (this.state.selectedProduct.coupon_loyalty_program_discount_date_from && this.state.selectedProduct.coupon_loyalty_program_discount_date_to) {
            const startDate = new Date(this.state.selectedProduct.coupon_loyalty_program_discount_date_from);
            const endDate = new Date(this.state.selectedProduct.coupon_loyalty_program_discount_date_to);
            if (startDate > endDate) {
                this.notification.add("La fecha de inicio de la recompensa de descuento del programa de cupones no puede ser posterior a la fecha de finalización.", {type: "danger"});
                return false;
            }
        }
        // no se puede ingresar una fecha de inicio o de finalización vacía cuando se selecciona un programa de cupones: 1, 2 o 3
        //const coupon_value = this.state.selectedProduct.coupons.find(coupon => coupon.selected).value || 0
        //if (coupon_value === 1 || coupon_value === 2 || coupon_value === 3) {
        //    if (!this.state.selectedProduct.coupon_loyalty_program_discount_date_from || !this.state.selectedProduct.coupon_loyalty_program_discount_date_to) {
        //        this.notification.add("Las fechas de inicio y de finalización de la recompensa de descuento del programa de cupones (1, 2 o 3) son obligatorias", {type: "danger"});
        //        return false;
        //    }
        //}
        // no se puede ingresar vacio o cero el descuento, y los puntos o la cantidad de promocion al mismo tiempo para el programa de promociones
        //if (!this.state.selectedProduct.discount_percentage || Math.round(this.state.selectedProduct.discount_percentage) === 0) {
        //    if ((!this.state.selectedProduct.product_reward_required_points || this.state.selectedProduct.product_reward_required_points === 0) || (!this.state.selectedProduct.product_reward_qty || this.state.selectedProduct.product_reward_qty === 0)) {
        //        this.notification.add("No se puede ingresar vacio o cero el descuento, y los puntos o la cantidad de promocion al mismo tiempo, dado que la promocion requiere de por lo menos una recompensa", {type: "danger"});
        //        return false;
        //    }
        //}
        // no se puede ingresar vacio o cero el descuento para el programa de cupones
        if (!this.state.selectedProduct.coupon_discount_percentage || Math.round(this.state.selectedProduct.coupon_discount_percentage) === 0) {
            const coupon_value = this.state.selectedProduct.coupons.find(coupon => coupon.selected).value || 0
            if (coupon_value === 1 || coupon_value === 2 || coupon_value === 3) {
                this.notification.add("No se puede ingresar vacio o cero el descuento, para crear un programa de cupones", {type: "danger"});
                return false;
            }
        }
        // el porcentaje de la promocion de descuento temporal tiene que estar entre 0 y 100
        if (this.state.selectedProduct.temporary_discount_percentage < 0 || this.state.selectedProduct.temporary_discount_percentage > 100) {
            this.notification.add("El porcentaje de descuento temporal debe estar entre 0 y 100.", {type: "danger"});
            return false;
        }
        // para la promocion de descuento temporal es obligatorio ingresar fechas
        if (this.state.selectedProduct.temporary_discount_percentage > 0) {
            if (!this.state.selectedProduct.loyalty_program_discount_date_from || !this.state.selectedProduct.loyalty_program_discount_date_to) {
                this.notification.add("Las fechas de inicio y fin de la recompensa de descuento temporal son obligatorias.", {type: "danger"});
                return false;
            }
        }
        return true;
    }

    /**
     * Load more purchase history items for infinite scroll
     * Fetches the next 7 purchase records and appends them to the existing list
     *
     * Features:
     * - Prevents duplicate requests with loading state
     * - Shows loading indicator for better UX
     * - Filters out duplicate records
     * - Updates pagination state automatically
     */
    async loadMorePurchaseHistory() {
        // Prevent multiple simultaneous requests
        if (!this.state.hasMorePurchases || this.state.isLoadingMore) {
            return;
        }

        this.state.isLoadingMore = true;

        try {
            // Add a small delay to show loading indicator for better UX
            await new Promise(resolve => setTimeout(resolve, 800));

            // Fetch next batch of purchase history records
            const newPurchases = await this.orm.call('product.product', 'get_complete_purchase_history', [
                this.state.product_id,
                7,
                this.state.purchaseHistoryOffset
            ]);

            if (newPurchases.length > 0) {
                // Create a Set to track existing purchase IDs to avoid duplicates
                // Uses a composite key combining order_name, date_order, price_unit, and product_qty
                const existingIds = new Set(this.props.lastPurchases.map(p => `${p.order_name}_${p.date_order}_${p.price_unit}_${p.product_qty}`));

                // Filter out duplicates using the composite key
                // This ensures each purchase record appears only once in the list
                const uniqueNewPurchases = newPurchases.filter(purchase => {
                    const purchaseKey = `${purchase.order_name}_${purchase.date_order}_${purchase.price_unit}_${purchase.product_qty}`;
                    return !existingIds.has(purchaseKey);
                });

                // Append only unique purchases to avoid data duplication
                if (uniqueNewPurchases.length > 0) {
                    this.props.lastPurchases = [...this.props.lastPurchases, ...uniqueNewPurchases];
                    this.state.purchaseHistoryOffset += 7; // Increment offset for next batch
                    this.state.hasMorePurchases = newPurchases.length >= 7; // Check if more data might be available
                } else {
                    // If all new purchases were duplicates, we've reached the end of available data
                    this.state.hasMorePurchases = false;
                }
            } else {
                // No more data available from the server
                this.state.hasMorePurchases = false;
            }
        } catch (error) {
            console.error('Error loading more purchase history:', error);
        } finally {
            this.state.isLoadingMore = false;
        }
    }

    /**
     * Handle scroll event for infinite scroll
     * Triggers loading more items when user reaches the bottom
     *
     * Features:
     * - Detects when user reaches bottom of scrollable area
     * - Uses 50px threshold for better UX
     * - Automatically triggers loading of next batch
     */
    onPurchaseHistoryScroll(event) {
        const {scrollTop, scrollHeight, clientHeight} = event.target;

        // Check if user has scrolled to the bottom (with a small threshold for better UX)
        // This triggers loading before user reaches the very end
        if (scrollHeight - scrollTop <= clientHeight + 50) {
            this.loadMorePurchaseHistory();
        }
    }

    async openPurchaseOrder(order_id) {
        if (!order_id) return;
        try {
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Orden de Compra",
                res_model: "purchase.order",
                res_id: order_id,
                views: [[false, "form"]],
                target: "new",
            });
        } catch (error) {
            try {
                console.error('Error al abrir Orden de Compra:', error);
            } catch (e) {
            }
            this.notification.add("Error al abrir la Orden de Compra.", {type: 'danger'});
        }
    }

    async openVendorBill(invoice_id) {
        if (!invoice_id) return;
        try {
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Factura",
                res_model: "account.move",
                res_id: invoice_id,
                views: [[false, "form"]],
                target: "new",
                context: {default_move_type: 'in_invoice'},
            });
        } catch (error) {
            try {
                console.error('Error al abrir Factura:', error);
            } catch (e) {
            }
            this.notification.add("Error al abrir la factura.", {type: 'danger'});
        }
    }

    //dar de baj un producto no disponible para el proveedor
    async onProductNotAvailableForSupplier(product_id) {
        try {
            await this.orm.call(
                "product.product",
                "set_disabled_product",
                [product_id]
            );
            this.close()
            // Refresh product list to reflect changes
            // await this.get_products(this.state.laboratory_id, this.state.brand_id);
        } catch (error) {
            console.error("Error al desactivar el producto:", error);
            // this.showError("Se produjo un error al desactivar el producto.");
        }
    }

    async saveProductChanges() {
        //Fechas por defecto (cuando no se ingresan) para la promocion de producto gratis
        //const today_date = new Date();
        //const yesterday_date = new Date();
        //yesterday_date.setDate(today_date.getDate() - 1);
        //const last_date_actual_year = new Date(today_date.getFullYear(), 11, 31);
        //function convertDate(date) {
        //    return date.toISOString().split('T')[0];  // => 'YYYY-MM-DD'
        //}
        //const default_loyalty_program_product_date_from = convertDate(yesterday_date);
        //const default_loyalty_program_product_date_to = convertDate(last_date_actual_year)

        let data = []

        data.push({
            "product_info": {
                "product_id": this.state.selectedProduct.id,
                "name": this.state.selectedProduct.name,
                'laboratory_id': this.state.selectedProduct.laboratory_id,
                'brand_id': this.state.selectedProduct.brand_id,
                "list_price": this.state.selectedProduct.list_price,
            },
            "loyalty_info": {
                "program_id": this.state.selectedProduct.loyalty_program_id,
                "loyalty_card_program_id": this.state.selectedProduct.loyalty_card_program_id,
                "coupon_program_id": this.state.selectedProduct.loyalty_coupon_program_id,
                "mandatory_promotion": this.state.selectedProduct.program_mandatory,
                "coupon_mandatory_promotion": this.state.selectedProduct.coupon_program_mandatory,
                //"date_from": this.state.selectedProduct.loyalty_program_date_from,
                //"date_to": this.state.selectedProduct.loyalty_program_date_to,
                //"coupon_date_from": this.state.selectedProduct.coupon_loyalty_program_date_from,
                //"coupon_date_to": this.state.selectedProduct.coupon_loyalty_program_date_to,
                "discount_date_from": this.state.selectedProduct.loyalty_program_discount_date_from,
                "discount_date_to": this.state.selectedProduct.loyalty_program_discount_date_to,
                "product_date_from": this.state.selectedProduct.loyalty_program_product_date_from,
                "product_date_to": this.state.selectedProduct.loyalty_program_product_date_to,
                "coupon_discount_date_from": this.state.selectedProduct.coupon_loyalty_program_discount_date_from,
                "coupon_discount_date_to": this.state.selectedProduct.coupon_loyalty_program_discount_date_to,
                "note_promotion": this.state.selectedProduct.program_note,
                "loyalty_card": this.state.selectedProduct.loyalty_card,
                "coupon": this.state.selectedProduct.coupons.find(coupon => coupon.selected).value || 0,
                //"is_temporary": this.state.selectedProduct.is_temporary,
                //reglas
                "promotion_rule_id": this.state.selectedProduct.promotion_rule_id,
                "coupon_rule_id": this.state.selectedProduct.coupon_rule_id,
                //promocion de descuento
                "discount_reward_id": this.state.selectedProduct.discount_reward_id,
                "temporary_discount_reward_id": this.state.selectedProduct.temporary_discount_reward_id,
                "discount_reward_id_2": this.state.selectedProduct.discount_reward_id_2,
                "loyalty_card_discount_reward_id": this.state.selectedProduct.loyalty_card_discount_reward_id,
                "loyalty_card_temporary_discount_reward_id": this.state.selectedProduct.loyalty_card_temporary_discount_reward_id,
                "loyalty_card_discount_reward_id_2": this.state.selectedProduct.loyalty_card_discount_reward_id_2,
                "coupon_discount_reward_id": this.state.selectedProduct.coupon_discount_reward_id,
                "discount": this.state.selectedProduct.discount_percentage,
                "temporary_discount": this.state.selectedProduct.temporary_discount_percentage,
                "coupon_discount": this.state.selectedProduct.coupon_discount_percentage,
                //promocion de producto gratis
                "product_reward_id": this.state.selectedProduct.product_reward_id,
                "loyalty_card_product_reward_id": this.state.selectedProduct.loyalty_card_product_reward_id,
                "coupon_product_reward_id": this.state.selectedProduct.coupon_product_reward_id,
                "product_reward_qty": this.state.selectedProduct.product_reward_qty,
                "product_reward_required_points": this.state.selectedProduct.product_reward_required_points,
                // "required_points": this.state.selectedProduct.required_points,
            }
        })

        const data_promotions = []
        data_promotions.push({
            "product_id": this.state.selectedProduct.id,
            "desc_esp": this.state.selectedProduct.temporary_discount_percentage || this.state.selectedProduct.discount_percentage,
            "obligatory_promotion": this.state.selectedProduct.program_mandatory,
            "date_from": this.state.selectedProduct.loyalty_program_product_date_from,
            "date_to": this.state.selectedProduct.loyalty_program_product_date_to,
            "base_cant": this.state.selectedProduct.product_reward_required_points,
            "promo_cant": this.state.selectedProduct.product_reward_qty,
            "program_note": this.state.selectedProduct.program_note,
            "coupon_discount": this.state.selectedProduct.coupon_discount_percentage,
            "obligatory_coupon": this.state.selectedProduct.coupon_program_mandatory,
            "coupon_date_from": this.state.selectedProduct.coupon_loyalty_program_discount_date_from,
            "coupon_date_to": this.state.selectedProduct.coupon_loyalty_program_discount_date_to,
            "acumulable": this.state.selectedProduct.loyalty_card,
            "coupon": this.state.selectedProduct.coupons.find(coupon => coupon.selected).value,
        })
        if (!await this.validateForm()) {
            return;
        }
        await this.orm.call("loyalty.sync", "sync_loyalty_programs", [data_promotions])
        await this.orm.call("loyalty.program", "save_product_info_and_loyalty_data", [data])
        // Actualizar marca y laboratorio si han cambiado
        if (this.state.selectedProduct.laboratory_id || this.state.selectedProduct.brand_id) {
            await this.onChangeProductBrandLaboratory(
                this.state.selectedProduct.id,
                this.state.selectedProduct.laboratory_id,
                this.state.selectedProduct.brand_id
            );
        }
        //datos para actualizar en la tabla principal
        const effectiveDiscount = this.state.selectedProduct.temporary_discount_percentage || this.state.selectedProduct.discount_percentage;
        const payload = {
            product_id: this.state.selectedProduct.id,
            discount_percentage: this.state.selectedProduct.discount_percentage,
            effective_discount_percentage: effectiveDiscount,
        };

        this.state.selectedProduct = {}
        this.close();
        this.notification.add("Los cambios se han guardado correctamente.",
            {
                type: "success"
            }
        )

        //funcion para actualizar el descuento en la tabla principal
        try {
            if (typeof this.props.onUpdateProduct === "function") {
                this.props.onUpdateProduct(payload);
            }
            this.notification.add("Descuento actualizado.", {type: "success"});
        } catch (error) {
            this.notification.add("No se pudo guardar el descuento.", {type: "danger"});
        }
    }

    /**
     * Copia al portapapeles: nombre del producto, cantidad vendida y stock de Matilde
     */
    async copySelectedProductName() {
        try {
            const name = this.state?.selectedProduct?.name || '';
            if (!name) {
                this.notification.add('Nombre no disponible', {type: 'warning'});
                return;
            }
            const quantitySold = this.props?.ProductDetails?.quantity_sold || 0;
            // Buscar el stock específico de la bodega Matilde
            const matildeWarehouse = this.state?.warehouses?.find(w =>
                w.warehouse_name && w.warehouse_name.toLowerCase().includes('bodega matilde')
            );
            const stockMatilde = matildeWarehouse?.stock || 0;
            const text = `Nombre: "${name}", cantidad vendida: ${quantitySold}, stock Matilde: ${stockMatilde}`;
            await navigator.clipboard.writeText(text);
            this.notification.add('Resumen copiado al portapapeles', {type: 'success'});
        } catch (e) {
            this.notification.add('No se pudo copiar el resumen', {type: 'danger'});
        }
    }
}