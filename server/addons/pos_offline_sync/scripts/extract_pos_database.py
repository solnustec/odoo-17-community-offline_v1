# -*- coding: utf-8 -*-
"""
=============================================================================
Script de Extracción de Base de Datos para POS Offline
=============================================================================

Este script extrae SOLO los datos necesarios de la base de datos principal
(cloud) para crear una base de datos optimizada para el servidor offline.

MODELOS EXTRAÍDOS:
-----------------
CORE:
- res.company (empresa)
- res.currency (monedas)
- res.country, res.country.state (países/estados)
- res.users (usuarios POS)
- res.partner (clientes - solo activos y necesarios para POS)

PRODUCTOS:
- product.category
- product.template (solo disponibles en POS)
- product.product (solo disponibles en POS)
- product.pricelist, product.pricelist.item
- uom.uom, uom.category

POS:
- pos.config (configuración del POS específico)
- pos.payment.method
- pos.category
- hr.employee (solo empleados de POS)

PROMOCIONES:
- loyalty.program (activos)
- loyalty.rule
- loyalty.reward
- loyalty.card (solo las del POS)

CONTABILIDAD (mínimo para facturación):
- account.tax
- account.fiscal.position
- account.journal (solo diarios de POS)

ECUADOR:
- l10n_latam.identification.type
- l10n_ec.sri.payment

STOCK:
- stock.warehouse
- stock.location (solo del warehouse del POS)
- stock.quant (solo del location del POS)

USO:
----
Desde el shell de Odoo del servidor CLOUD:
    python odoo-bin shell -d database_cloud
    >>> exec(open('path/to/extract_pos_database.py').read())
    >>> extract = POSDataExtractor(env, pos_config_id=1)
    >>> extract.analyze()
    >>> extract.export_to_sql('/path/to/output')

=============================================================================
"""

import json
import os
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class POSDataExtractor:
    """
    Extrae datos necesarios para POS Offline desde la base de datos principal.
    """

    def __init__(self, env, pos_config_id=None, company_id=None):
        """
        Inicializa el extractor.

        Args:
            env: Odoo environment
            pos_config_id: ID del pos.config para el cual extraer datos
            company_id: ID de la compañía (opcional, se toma del pos.config)
        """
        self.env = env
        self.pos_config_id = pos_config_id
        self.company_id = company_id

        # Cargar configuración
        self._load_config()

        # Datos extraídos
        self.data = {}
        self.stats = {}

    def _load_config(self):
        """Carga la configuración del POS."""
        if self.pos_config_id:
            self.pos_config = self.env['pos.config'].browse(self.pos_config_id)
            if not self.pos_config.exists():
                raise ValueError(f"POS Config {self.pos_config_id} no existe")
            self.company_id = self.pos_config.company_id.id
            self.company = self.pos_config.company_id
            self.warehouse = self.pos_config.picking_type_id.warehouse_id
            self.stock_location = self.warehouse.lot_stock_id if self.warehouse else None
        else:
            # Usar primera compañía si no se especifica
            self.company = self.env['res.company'].search([], limit=1)
            self.company_id = self.company.id
            self.pos_config = None
            self.warehouse = None
            self.stock_location = None

    def analyze(self):
        """Analiza y muestra estadísticas de los datos a extraer."""
        print("\n" + "=" * 70)
        print(" ANÁLISIS DE DATOS PARA EXTRACCIÓN POS OFFLINE")
        print("=" * 70)

        if self.pos_config:
            print(f"\n📍 POS Config: {self.pos_config.name} (ID: {self.pos_config_id})")
        print(f"🏢 Compañía: {self.company.name} (ID: {self.company_id})")
        if self.warehouse:
            print(f"🏭 Warehouse: {self.warehouse.name}")
        if self.stock_location:
            print(f"📦 Stock Location: {self.stock_location.complete_name}")

        print("\n" + "-" * 70)
        print(" CONTEO DE REGISTROS A EXTRAER")
        print("-" * 70)

        # Contar registros por modelo
        counts = {
            'res.company': 1,
            'res.currency': self.env['res.currency'].search_count([('active', '=', True)]),
            'res.country': self.env['res.country'].search_count([]),
            'res.country.state': self.env['res.country.state'].search_count([]),
            'res.users': self._count_pos_users(),
            'res.partner': self._count_pos_partners(),
            'product.category': self.env['product.category'].search_count([]),
            'product.template': self._count_pos_products('product.template'),
            'product.product': self._count_pos_products('product.product'),
            'product.pricelist': self._count_pricelists(),
            'uom.uom': self.env['uom.uom'].search_count([]),
            'uom.category': self.env['uom.category'].search_count([]),
            'pos.config': 1 if self.pos_config else self.env['pos.config'].search_count([('company_id', '=', self.company_id)]),
            'pos.payment.method': self._count_payment_methods(),
            'pos.category': self.env['pos.category'].search_count([]) if 'pos.category' in self.env else 0,
            'hr.employee': self._count_pos_employees(),
            'loyalty.program': self._count_loyalty_programs(),
            'loyalty.rule': self._count_loyalty_rules(),
            'loyalty.reward': self._count_loyalty_rewards(),
            'account.tax': self.env['account.tax'].search_count([('company_id', '=', self.company_id)]),
            'account.fiscal.position': self.env['account.fiscal.position'].search_count([('company_id', '=', self.company_id)]),
            'account.journal': self._count_pos_journals(),
            'stock.warehouse': 1 if self.warehouse else self.env['stock.warehouse'].search_count([('company_id', '=', self.company_id)]),
            'stock.location': self._count_stock_locations(),
            'stock.quant': self._count_stock_quants(),
        }

        # Ecuador específico
        if 'l10n_latam.identification.type' in self.env:
            counts['l10n_latam.identification.type'] = self.env['l10n_latam.identification.type'].search_count([])
        if 'l10n_ec.sri.payment' in self.env:
            counts['l10n_ec.sri.payment'] = self.env['l10n_ec.sri.payment'].search_count([])

        total = 0
        for model, count in sorted(counts.items()):
            print(f"  {model:40} {count:>8}")
            total += count

        print("-" * 70)
        print(f"  {'TOTAL':40} {total:>8}")
        print("=" * 70)

        self.stats = counts
        return counts

    def _count_pos_users(self):
        """Cuenta usuarios que pueden usar POS."""
        return self.env['res.users'].search_count([
            ('active', '=', True),
            ('company_id', '=', self.company_id),
        ])

    def _count_pos_partners(self):
        """Cuenta partners relevantes para POS."""
        # Clientes activos + Consumidor Final
        return self.env['res.partner'].search_count([
            ('active', '=', True),
            '|',
            ('customer_rank', '>', 0),
            ('name', 'ilike', 'consumidor final'),
        ])

    def _count_pos_products(self, model):
        """Cuenta productos disponibles en POS."""
        return self.env[model].search_count([
            ('available_in_pos', '=', True),
            ('active', '=', True),
        ])

    def _count_pricelists(self):
        """Cuenta listas de precios."""
        if self.pos_config and self.pos_config.pricelist_id:
            return self.env['product.pricelist'].search_count([
                '|',
                ('id', '=', self.pos_config.pricelist_id.id),
                ('company_id', '=', self.company_id),
            ])
        return self.env['product.pricelist'].search_count([
            ('company_id', 'in', [self.company_id, False])
        ])

    def _count_payment_methods(self):
        """Cuenta métodos de pago del POS."""
        if self.pos_config:
            return len(self.pos_config.payment_method_ids)
        return self.env['pos.payment.method'].search_count([
            ('company_id', '=', self.company_id)
        ])

    def _count_pos_employees(self):
        """Cuenta empleados de POS."""
        return self.env['hr.employee'].search_count([
            ('company_id', '=', self.company_id),
            ('active', '=', True),
        ])

    def _count_loyalty_programs(self):
        """Cuenta programas de lealtad activos."""
        return self.env['loyalty.program'].search_count([
            ('active', '=', True),
            ('company_id', 'in', [self.company_id, False]),
        ])

    def _count_loyalty_rules(self):
        """Cuenta reglas de programas activos."""
        programs = self.env['loyalty.program'].search([
            ('active', '=', True),
            ('company_id', 'in', [self.company_id, False]),
        ])
        return self.env['loyalty.rule'].search_count([
            ('program_id', 'in', programs.ids)
        ])

    def _count_loyalty_rewards(self):
        """Cuenta recompensas de programas activos."""
        programs = self.env['loyalty.program'].search([
            ('active', '=', True),
            ('company_id', 'in', [self.company_id, False]),
        ])
        return self.env['loyalty.reward'].search_count([
            ('program_id', 'in', programs.ids)
        ])

    def _count_pos_journals(self):
        """Cuenta diarios de POS."""
        return self.env['account.journal'].search_count([
            ('company_id', '=', self.company_id),
            ('type', 'in', ['cash', 'bank', 'sale']),
        ])

    def _count_stock_locations(self):
        """Cuenta ubicaciones de stock."""
        if self.stock_location:
            return self.env['stock.location'].search_count([
                '|',
                ('id', '=', self.stock_location.id),
                ('id', 'parent_of', self.stock_location.id),
            ])
        return self.env['stock.location'].search_count([
            ('company_id', '=', self.company_id)
        ])

    def _count_stock_quants(self):
        """Cuenta quants de stock."""
        if self.stock_location:
            return self.env['stock.quant'].search_count([
                ('location_id', '=', self.stock_location.id),
                ('quantity', '>', 0),
            ])
        return 0

    def extract_all(self):
        """Extrae todos los datos necesarios."""
        print("\n" + "=" * 70)
        print(" EXTRAYENDO DATOS...")
        print("=" * 70)

        self.data = {
            'metadata': {
                'extracted_at': datetime.now().isoformat(),
                'source_database': self.env.cr.dbname,
                'pos_config_id': self.pos_config_id,
                'company_id': self.company_id,
                'company_name': self.company.name,
            },
            'models': {}
        }

        # Extraer cada modelo
        extractors = [
            ('res.company', self._extract_company),
            ('res.currency', self._extract_currencies),
            ('res.country', self._extract_countries),
            ('res.country.state', self._extract_states),
            ('uom.category', self._extract_uom_categories),
            ('uom.uom', self._extract_uoms),
            ('res.users', self._extract_users),
            ('res.partner', self._extract_partners),
            ('product.category', self._extract_product_categories),
            ('product.template', self._extract_product_templates),
            ('product.product', self._extract_products),
            ('product.pricelist', self._extract_pricelists),
            ('pos.payment.method', self._extract_payment_methods),
            ('pos.config', self._extract_pos_config),
            ('hr.employee', self._extract_employees),
            ('loyalty.program', self._extract_loyalty_programs),
            ('account.tax', self._extract_taxes),
            ('account.fiscal.position', self._extract_fiscal_positions),
            ('account.journal', self._extract_journals),
            ('stock.warehouse', self._extract_warehouses),
            ('stock.location', self._extract_locations),
            ('stock.quant', self._extract_quants),
        ]

        # Ecuador específico
        if 'l10n_latam.identification.type' in self.env:
            extractors.append(('l10n_latam.identification.type', self._extract_identification_types))
        if 'l10n_ec.sri.payment' in self.env:
            extractors.append(('l10n_ec.sri.payment', self._extract_sri_payments))

        for model, extractor in extractors:
            try:
                print(f"  Extrayendo {model}...", end=" ")
                records = extractor()
                self.data['models'][model] = records
                print(f"✓ ({len(records)} registros)")
            except Exception as e:
                print(f"✗ Error: {e}")
                _logger.error(f"Error extrayendo {model}: {e}")

        print("\n" + "=" * 70)
        print(" EXTRACCIÓN COMPLETADA")
        print("=" * 70)

        return self.data

    def _extract_company(self):
        """Extrae datos de la compañía."""
        company = self.company
        return [{
            'id': company.id,
            'name': company.name,
            'vat': company.vat,
            'email': company.email,
            'phone': company.phone,
            'street': company.street,
            'city': company.city,
            'country_id': company.country_id.id if company.country_id else None,
            'state_id': company.state_id.id if company.state_id else None,
            'currency_id': company.currency_id.id if company.currency_id else None,
            'partner_id': company.partner_id.id if company.partner_id else None,
        }]

    def _extract_currencies(self):
        """Extrae monedas activas."""
        records = self.env['res.currency'].search([('active', '=', True)])
        return [{
            'id': r.id,
            'name': r.name,
            'symbol': r.symbol,
            'rate': r.rate,
            'active': r.active,
            'position': r.position,
            'decimal_places': r.decimal_places,
        } for r in records]

    def _extract_countries(self):
        """Extrae países."""
        records = self.env['res.country'].search([])
        return [{
            'id': r.id,
            'name': r.name,
            'code': r.code,
            'phone_code': r.phone_code,
            'currency_id': r.currency_id.id if r.currency_id else None,
        } for r in records]

    def _extract_states(self):
        """Extrae estados/provincias."""
        records = self.env['res.country.state'].search([])
        return [{
            'id': r.id,
            'name': r.name,
            'code': r.code,
            'country_id': r.country_id.id,
        } for r in records]

    def _extract_uom_categories(self):
        """Extrae categorías de UoM."""
        records = self.env['uom.category'].search([])
        return [{
            'id': r.id,
            'name': r.name,
        } for r in records]

    def _extract_uoms(self):
        """Extrae unidades de medida."""
        records = self.env['uom.uom'].search([])
        return [{
            'id': r.id,
            'name': r.name,
            'category_id': r.category_id.id,
            'factor': r.factor,
            'factor_inv': r.factor_inv,
            'rounding': r.rounding,
            'active': r.active,
            'uom_type': r.uom_type,
        } for r in records]

    def _extract_users(self):
        """Extrae usuarios."""
        records = self.env['res.users'].search([
            ('active', '=', True),
            ('company_id', '=', self.company_id),
        ])
        return [{
            'id': r.id,
            'name': r.name,
            'login': r.login,
            'active': r.active,
            'company_id': r.company_id.id,
            'partner_id': r.partner_id.id,
        } for r in records]

    def _extract_partners(self):
        """Extrae partners/clientes."""
        records = self.env['res.partner'].search([
            ('active', '=', True),
            '|',
            ('customer_rank', '>', 0),
            ('name', 'ilike', 'consumidor final'),
        ])
        data = []
        for r in records:
            partner_data = {
                'id': r.id,
                'name': r.name,
                'email': r.email,
                'phone': r.phone,
                'mobile': r.mobile,
                'vat': r.vat,
                'street': r.street,
                'city': r.city,
                'zip': r.zip,
                'country_id': r.country_id.id if r.country_id else None,
                'state_id': r.state_id.id if r.state_id else None,
                'active': r.active,
                'customer_rank': r.customer_rank,
                'type': r.type,
            }
            # Campos LATAM si existen
            if hasattr(r, 'l10n_latam_identification_type_id'):
                partner_data['l10n_latam_identification_type_id'] = r.l10n_latam_identification_type_id.id if r.l10n_latam_identification_type_id else None
            data.append(partner_data)
        return data

    def _extract_product_categories(self):
        """Extrae categorías de productos."""
        records = self.env['product.category'].search([])
        return [{
            'id': r.id,
            'name': r.name,
            'complete_name': r.complete_name,
            'parent_id': r.parent_id.id if r.parent_id else None,
        } for r in records]

    def _extract_product_templates(self):
        """Extrae templates de productos."""
        records = self.env['product.template'].search([
            ('available_in_pos', '=', True),
            ('active', '=', True),
        ])
        return [{
            'id': r.id,
            'name': r.name,
            'type': r.type,
            'categ_id': r.categ_id.id if r.categ_id else None,
            'list_price': r.list_price,
            'standard_price': r.standard_price,
            'uom_id': r.uom_id.id if r.uom_id else None,
            'uom_po_id': r.uom_po_id.id if r.uom_po_id else None,
            'available_in_pos': r.available_in_pos,
            'active': r.active,
            'sale_ok': r.sale_ok,
            'purchase_ok': r.purchase_ok,
        } for r in records]

    def _extract_products(self):
        """Extrae productos."""
        records = self.env['product.product'].search([
            ('available_in_pos', '=', True),
            ('active', '=', True),
        ])
        return [{
            'id': r.id,
            'name': r.name,
            'default_code': r.default_code,
            'barcode': r.barcode,
            'product_tmpl_id': r.product_tmpl_id.id,
            'list_price': r.list_price,
            'standard_price': r.standard_price,
            'active': r.active,
            'available_in_pos': r.available_in_pos,
        } for r in records]

    def _extract_pricelists(self):
        """Extrae listas de precios."""
        records = self.env['product.pricelist'].search([
            ('company_id', 'in', [self.company_id, False])
        ])
        data = []
        for r in records:
            pricelist_data = {
                'id': r.id,
                'name': r.name,
                'active': r.active,
                'currency_id': r.currency_id.id if r.currency_id else None,
                'company_id': r.company_id.id if r.company_id else None,
                'items': []
            }
            # Extraer items de la lista de precios
            for item in r.item_ids:
                pricelist_data['items'].append({
                    'id': item.id,
                    'product_tmpl_id': item.product_tmpl_id.id if item.product_tmpl_id else None,
                    'product_id': item.product_id.id if item.product_id else None,
                    'categ_id': item.categ_id.id if item.categ_id else None,
                    'min_quantity': item.min_quantity,
                    'applied_on': item.applied_on,
                    'compute_price': item.compute_price,
                    'fixed_price': item.fixed_price,
                    'percent_price': item.percent_price,
                    'date_start': item.date_start.isoformat() if item.date_start else None,
                    'date_end': item.date_end.isoformat() if item.date_end else None,
                })
            data.append(pricelist_data)
        return data

    def _extract_payment_methods(self):
        """Extrae métodos de pago."""
        if self.pos_config:
            records = self.pos_config.payment_method_ids
        else:
            records = self.env['pos.payment.method'].search([
                ('company_id', '=', self.company_id)
            ])
        return [{
            'id': r.id,
            'name': r.name,
            'is_cash_count': r.is_cash_count,
            'company_id': r.company_id.id if r.company_id else None,
        } for r in records]

    def _extract_pos_config(self):
        """Extrae configuración de POS."""
        if self.pos_config:
            records = self.pos_config
        else:
            records = self.env['pos.config'].search([
                ('company_id', '=', self.company_id)
            ], limit=1)

        if not records:
            return []

        r = records
        return [{
            'id': r.id,
            'name': r.name,
            'company_id': r.company_id.id,
            'pricelist_id': r.pricelist_id.id if r.pricelist_id else None,
            'picking_type_id': r.picking_type_id.id if r.picking_type_id else None,
            'payment_method_ids': r.payment_method_ids.ids,
            'iface_tax_included': r.iface_tax_included,
        }]

    def _extract_employees(self):
        """Extrae empleados."""
        records = self.env['hr.employee'].search([
            ('company_id', '=', self.company_id),
            ('active', '=', True),
        ])
        return [{
            'id': r.id,
            'name': r.name,
            'user_id': r.user_id.id if r.user_id else None,
            'company_id': r.company_id.id,
            'active': r.active,
        } for r in records]

    def _extract_loyalty_programs(self):
        """Extrae programas de lealtad."""
        records = self.env['loyalty.program'].search([
            ('active', '=', True),
            ('company_id', 'in', [self.company_id, False]),
        ])
        data = []
        for r in records:
            program_data = {
                'id': r.id,
                'name': r.name,
                'active': r.active,
                'program_type': r.program_type,
                'applies_on': r.applies_on if hasattr(r, 'applies_on') else None,
                'trigger': r.trigger if hasattr(r, 'trigger') else None,
                'company_id': r.company_id.id if r.company_id else None,
                'rules': [],
                'rewards': [],
            }
            # Reglas
            for rule in r.rule_ids:
                program_data['rules'].append({
                    'id': rule.id,
                    'mode': rule.mode if hasattr(rule, 'mode') else None,
                    'minimum_qty': rule.minimum_qty if hasattr(rule, 'minimum_qty') else 0,
                    'minimum_amount': rule.minimum_amount if hasattr(rule, 'minimum_amount') else 0,
                    'product_ids': rule.product_ids.ids if hasattr(rule, 'product_ids') else [],
                })
            # Recompensas
            for reward in r.reward_ids:
                program_data['rewards'].append({
                    'id': reward.id,
                    'reward_type': reward.reward_type,
                    'discount': reward.discount if hasattr(reward, 'discount') else 0,
                    'discount_mode': reward.discount_mode if hasattr(reward, 'discount_mode') else None,
                    'required_points': reward.required_points if hasattr(reward, 'required_points') else 0,
                })
            data.append(program_data)
        return data

    def _extract_taxes(self):
        """Extrae impuestos."""
        records = self.env['account.tax'].search([
            ('company_id', '=', self.company_id)
        ])
        return [{
            'id': r.id,
            'name': r.name,
            'type_tax_use': r.type_tax_use,
            'amount_type': r.amount_type,
            'amount': r.amount,
            'active': r.active,
            'company_id': r.company_id.id,
        } for r in records]

    def _extract_fiscal_positions(self):
        """Extrae posiciones fiscales."""
        records = self.env['account.fiscal.position'].search([
            ('company_id', '=', self.company_id)
        ])
        return [{
            'id': r.id,
            'name': r.name,
            'active': r.active if hasattr(r, 'active') else True,
            'company_id': r.company_id.id,
        } for r in records]

    def _extract_journals(self):
        """Extrae diarios contables."""
        records = self.env['account.journal'].search([
            ('company_id', '=', self.company_id),
            ('type', 'in', ['cash', 'bank', 'sale']),
        ])
        return [{
            'id': r.id,
            'name': r.name,
            'type': r.type,
            'code': r.code,
            'company_id': r.company_id.id,
        } for r in records]

    def _extract_warehouses(self):
        """Extrae warehouses."""
        if self.warehouse:
            records = self.warehouse
        else:
            records = self.env['stock.warehouse'].search([
                ('company_id', '=', self.company_id)
            ], limit=1)

        if not records:
            return []

        r = records
        return [{
            'id': r.id,
            'name': r.name,
            'code': r.code,
            'company_id': r.company_id.id,
            'lot_stock_id': r.lot_stock_id.id if r.lot_stock_id else None,
        }]

    def _extract_locations(self):
        """Extrae ubicaciones de stock."""
        if self.stock_location:
            records = self.env['stock.location'].search([
                '|',
                ('id', '=', self.stock_location.id),
                ('id', 'parent_of', self.stock_location.id),
            ])
        else:
            records = self.env['stock.location'].search([
                ('company_id', '=', self.company_id)
            ])
        return [{
            'id': r.id,
            'name': r.name,
            'complete_name': r.complete_name,
            'usage': r.usage,
            'company_id': r.company_id.id if r.company_id else None,
            'parent_id': r.location_id.id if r.location_id else None,
        } for r in records]

    def _extract_quants(self):
        """Extrae stock quants."""
        if not self.stock_location:
            return []

        records = self.env['stock.quant'].search([
            ('location_id', '=', self.stock_location.id),
            ('quantity', '>', 0),
        ])
        return [{
            'id': r.id,
            'product_id': r.product_id.id,
            'location_id': r.location_id.id,
            'quantity': r.quantity,
            'reserved_quantity': r.reserved_quantity,
        } for r in records]

    def _extract_identification_types(self):
        """Extrae tipos de identificación LATAM."""
        records = self.env['l10n_latam.identification.type'].search([])
        return [{
            'id': r.id,
            'name': r.name,
            'l10n_ec_code': r.l10n_ec_code if hasattr(r, 'l10n_ec_code') else None,
        } for r in records]

    def _extract_sri_payments(self):
        """Extrae formas de pago SRI Ecuador."""
        records = self.env['l10n_ec.sri.payment'].search([])
        return [{
            'id': r.id,
            'name': r.name,
            'code': r.code,
        } for r in records]

    def export_to_json(self, output_dir):
        """Exporta los datos a archivos JSON."""
        if not self.data:
            self.extract_all()

        os.makedirs(output_dir, exist_ok=True)

        # Exportar metadata
        metadata_file = os.path.join(output_dir, 'metadata.json')
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.data['metadata'], f, indent=2, ensure_ascii=False)

        # Exportar cada modelo
        for model, records in self.data['models'].items():
            filename = model.replace('.', '_') + '.json'
            filepath = os.path.join(output_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(records, f, indent=2, ensure_ascii=False, default=str)

        print(f"\n✓ Datos exportados a: {output_dir}")
        return output_dir

    def export_to_sql(self, output_dir):
        """
        Exporta los datos en formato SQL para importar en la BD offline.
        """
        if not self.data:
            self.extract_all()

        os.makedirs(output_dir, exist_ok=True)

        # Crear script SQL principal
        sql_file = os.path.join(output_dir, 'import_pos_data.sql')

        with open(sql_file, 'w', encoding='utf-8') as f:
            f.write("-- =====================================================\n")
            f.write("-- Script de importación de datos POS Offline\n")
            f.write(f"-- Generado: {datetime.now().isoformat()}\n")
            f.write(f"-- Fuente: {self.data['metadata']['source_database']}\n")
            f.write("-- =====================================================\n\n")

            f.write("BEGIN;\n\n")

            # Generar INSERTs para cada modelo
            for model, records in self.data['models'].items():
                if not records:
                    continue

                table_name = model.replace('.', '_')
                f.write(f"-- {model} ({len(records)} registros)\n")

                for record in records:
                    # Construir INSERT
                    columns = [k for k in record.keys() if not isinstance(record[k], (list, dict))]
                    values = []
                    for col in columns:
                        val = record[col]
                        if val is None:
                            values.append('NULL')
                        elif isinstance(val, bool):
                            values.append('TRUE' if val else 'FALSE')
                        elif isinstance(val, (int, float)):
                            values.append(str(val))
                        else:
                            # Escapar comillas simples
                            val_str = str(val).replace("'", "''")
                            values.append(f"'{val_str}'")

                    f.write(f"INSERT INTO {table_name} ({', '.join(columns)}) ")
                    f.write(f"VALUES ({', '.join(values)}) ")
                    f.write(f"ON CONFLICT (id) DO UPDATE SET ")
                    f.write(', '.join([f"{col} = EXCLUDED.{col}" for col in columns if col != 'id']))
                    f.write(";\n")

                f.write("\n")

            f.write("COMMIT;\n")

        print(f"\n✓ SQL exportado a: {sql_file}")

        # También exportar JSON para referencia
        self.export_to_json(os.path.join(output_dir, 'json'))

        return sql_file


# =============================================================================
# FUNCIONES DE AYUDA
# =============================================================================

def create_extractor(env, pos_config_id=None):
    """Crea una instancia del extractor."""
    return POSDataExtractor(env, pos_config_id=pos_config_id)


def quick_analyze(env, pos_config_id=None):
    """Análisis rápido de datos a extraer."""
    extractor = POSDataExtractor(env, pos_config_id=pos_config_id)
    return extractor.analyze()


def quick_export(env, output_dir, pos_config_id=None):
    """Exportación rápida de datos."""
    extractor = POSDataExtractor(env, pos_config_id=pos_config_id)
    extractor.extract_all()
    extractor.export_to_sql(output_dir)
    return extractor


# =============================================================================
# EJECUCIÓN DESDE SHELL
# =============================================================================

if 'env' in dir():
    print("\n" + "=" * 70)
    print(" EXTRACTOR DE DATOS POS OFFLINE")
    print("=" * 70)
    print("\nUso:")
    print("  1. quick_analyze(env)  # Analizar datos")
    print("  2. quick_analyze(env, pos_config_id=1)  # Analizar para POS específico")
    print("  3. quick_export(env, '/tmp/pos_data')  # Exportar datos")
    print("  4. quick_export(env, '/tmp/pos_data', pos_config_id=1)")
    print("\nO manualmente:")
    print("  extractor = POSDataExtractor(env, pos_config_id=1)")
    print("  extractor.analyze()")
    print("  extractor.extract_all()")
    print("  extractor.export_to_sql('/tmp/pos_data')")
    print("\n")
