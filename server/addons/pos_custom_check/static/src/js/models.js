/** @odoo-module */

import {Order, Orderline, Payment} from "@point_of_sale/app/store/models";
import {patch} from "@web/core/utils/patch";

import { registry } from "@web/core/registry";

patch(Payment.prototype, {
  setup(_defaultObj, options) {
    super.setup(...arguments);
    this.allow_check_info = this.allow_check_info || false;
    this.code_payment_method = this.code_payment_method || false;
    this.check_number = this.check_number || false;
    this.bank_account = this.bank_account || false;
    this.owner_name = this.owner_name || false;
    this.bank_name = this.bank_name || false;
    this.bank_id = this.bank_id || false;
    this.number_voucher = this.number_voucher || false;
    this.type_card = this.type_card || false;
    this.number_lote = this.number_lote || false;
    this.holder_card = this.holder_card || false;
    this.bin_tc = this.bin_tc || false;
    this.institution_cheque = this.institution_cheque || false;
    this.institution_card = this.institution_card || false;
    this.institution_discount = this.institution_discount || false;
    this.payment_transaction_id = this.payment_transaction_id || false;
    this.payment_transfer_number = this.payment_transfer_number || false;
    this.payment_bank_name = this.payment_bank_name || false;
    this.orderer_identification = this.orderer_identification || false;
    this.selecteInstitutionCredit = this.selecteInstitutionCredit || false;
    // Autorización manual
    this.self_authorized = this.self_authorized || false;
    this.self_authorized_by = this.self_authorized_by || false;
  },
  getCheckInfo() {
    const check_info = this;
    return check_info;
  },
  // Métodos para institution_cheque
  get_institution_cheque() {
    return this.institution_cheque;
  },
  set_institution_cheque(institution) {
    this.institution_cheque = institution;
  },
  // Métodos para institution_cheque
  get_selecteInstitutionCredit() {
    return this.selecteInstitutionCredit;
  },
  set_selecteInstitutionCredit(selecteInstitutionCredit) {
    this.selecteInstitutionCredit = selecteInstitutionCredit;
  },
  //Id Institution

  get_bank_id() {
    return this.bank_id;
  },
  set_bank_id(bank_id) {
    this.bank_id = bank_id;
  },

  get_institution_id() {
    return this.institution_discount;
  },
  set_institution_id(institution) {
    this.institution_discount = institution;
  },

  // Métodos para institution_card
  get_institution_card() {
    return this.institution_card;
  },
  set_institution_card(institution) {
    this.institution_card = institution;
  },
  set_allow_check_info(allow_check_info) {
    this.allow_check_info = allow_check_info;
  },
  get_allow_check_info() {
    return this.allow_check_info;
  },
  set_check_number(check_number) {
    this.check_number = check_number;
  },
  get_check_number() {
    return this.check_number;
  },
  set_bank_name(bank_name) {
    this.bank_name = bank_name;
  },
  get_bank_name() {
    return this.bank_name;
  },
  set_owner_name(owner_name) {
    this.owner_name = owner_name;
  },
  get_owner_name() {
    return this.owner_name;
  },
  set_bank_account(bank_account) {
    this.bank_account = bank_account;
  },
  get_bank_account() {
    return this.bank_account;
  },

  // Métodos para la tarjeta
  set_number_voucher(number_voucher) {
    this.number_voucher = number_voucher;
  },
  get_number_voucher() {
    return this.number_voucher;
  },
  set_type_card(type_card) {
    this.type_card = type_card;
  },
  get_type_card() {
    return this.type_card;
  },
  set_number_lote(number_lote) {
    this.number_lote = number_lote;
  },
  get_number_lote() {
    return this.number_lote;
  },
  set_holder_card(holder_card) {
    this.holder_card = holder_card;
  },
  get_holder_card() {
    return this.holder_card;
  },
  set_bin_tc(bin_tc) {
    this.bin_tc = bin_tc;
  },
  get_bin_tc() {
    return this.bin_tc;
  },

  get_code_payment_method() {
    return this.code_payment_method;
  },

  set_payment_transaction_id(val) {
      this.payment_transaction_id = val;
  },
  get_payment_transaction_id() {
      return this.payment_transaction_id;
  },

  set_payment_transfer_number(val) {
      this.payment_transfer_number = val;
  },
  get_payment_transfer_number() {
      return this.payment_transfer_number;
  },

  set_payment_bank_name(val) {
      this.payment_bank_name = val;
  },
  get_payment_bank_name() {
      return this.payment_bank_name;
  },
  set_orderer_identification(orderer_identification) {
    this.orderer_identification = orderer_identification;
  },

  get_orderer_identification() {
    return this.orderer_identification;
  },

  init_from_JSON(json) {
    super.init_from_JSON(...arguments);
    this.allow_check_info = json.allow_check_info || false;
    this.code_payment_method = json.code_payment_method || false;
    this.check_number = json.check_number || false;
    this.bank_account = json.bank_account || false;
    this.owner_name = json.owner_name || false;
    this.bank_name = json.bank_name || false;
    this.number_voucher = json.number_voucher || false;
    this.type_card = json.type_card || false;
    this.number_lote = json.number_lote || false;
    this.holder_card = json.holder_card || false;
    this.bin_tc = json.bin_tc || false;
    this.institution_cheque = json.institution_cheque || false;
    this.institution_card = this.institution_card || false;
    this.institution_cheque = json.institution_cheque || false;
    this.institution_card = json.institution_card || false;
    this.institution_discount = json.institution_discount || false;
    this.bank_id = json.bank_id || false;
    this.payment_transaction_id = json.payment_transaction_id || false;
    this.payment_transfer_number = json.payment_transfer_number || false;
    this.payment_bank_name = json.payment_bank_name || false;
    this.orderer_identification = json.orderer_identification || false;
    this.selecteInstitutionCredit = json.selecteInstitutionCredit || false;
    // Autorización manual
    this.self_authorized = json.self_authorized || false;
    this.self_authorized_by = json.self_authorized_by || false;
  },

  export_as_JSON() {
    const json = super.export_as_JSON(...arguments);
    json.allow_check_info = this.allow_check_info || false;
    json.code_payment_method = this.code_payment_method || false;
    json.check_number = this.check_number || false;
    json.bank_account = this.bank_account || false;
    json.owner_name = this.owner_name || false;
    json.bank_name = this.bank_name || false;
    json.number_voucher = this.number_voucher || false;
    json.type_card = this.type_card || false;
    json.number_lote = this.number_lote || false;
    json.holder_card = this.holder_card || false;
    json.bin_tc = this.bin_tc || false;
    json.institution_cheque = this.institution_cheque || false;
    json.institution_card = this.institution_card || false;
    json.institution_card = this.institution_card || false;
    json.institution_discount = this.institution_discount || false;
    json.bank_id = this.bank_id || false;
    json.payment_transaction_id = this.payment_transaction_id || false;
    json.payment_transfer_number = this.payment_transfer_number || false;
    json.payment_bank_name = this.payment_bank_name || false;
    json.orderer_identification = this.orderer_identification || false;
    json.selecteInstitutionCredit = this.selecteInstitutionCredit || false;
    // Autorización manual
    json.self_authorized = this.self_authorized || false;
    json.self_authorized_by = this.self_authorized_by || false;
    return json;
  },


  export_for_printing() {
    const json = super.export_for_printing(...arguments);
    json.allow_check_info = this.get_allow_check_info();
    json.check_number = this.get_check_number();
    json.bank_account = this.get_bank_account();
    json.owner_name = this.get_owner_name();
    json.bank_name = this.get_bank_name();
    json.number_voucher = this.get_number_voucher();
    json.type_card = this.get_type_card();
    json.number_lote = this.get_number_lote();
    json.holder_card = this.get_holder_card();
    json.bin_tc = this.get_bin_tc();
    json.institution_cheque = this.get_institution_cheque();
    json.institution_card = this.get_institution_card();
    json.institution_discount = this.get_institution_id();
    json.bank_id = this.get_bank_id();
    json.selecteInstitutionCredit = this.get_selecteInstitutionCredit();
    //Agregar Sucursal al POS
    if (this.pos && this.pos.config){
        json.sucursal = this.pos.config.name || '';
    }
    return json;
  }
});

// ---------------------------------------------------------------------
// NUEVO BLOQUE: agrega la sucursal al export_for_printing del pedido
// ---------------------------------------------------------------------
patch(Order.prototype, {
    export_for_printing() {
        const json = super.export_for_printing(...arguments);

        // Se copia el nombre de la sucursal configurada en el POS
        if (this.pos && this.pos.config) {
            json.sucursal = this.pos.config.name || '';
        }

        return json;
    },
});