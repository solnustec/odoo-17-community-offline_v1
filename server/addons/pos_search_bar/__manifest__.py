# -*- coding: utf-8 -*-
{
    "name": "POS Search Bar for multiple words",
    "summary": "Extends POS SearchBar to include the Cashier field in ticket search. Improves performance in searching for products.",
    "description": """
Custom module to patch the Point of Sale TicketScreen SearchBar in Odoo 17,
adding a new search criterion \"Cashier\" to search by cashier name.
""",
    "author": "Fabricio Franco",
    "website": "Novacode Solutions",
    "category": "Point of Sale",
    "version": "17.0.1.0.0",
    "depends": [
        "point_of_sale",
    ],
    "data": [
        # view templates that need loading at install
    ],
    "assets": {
        # JS patch for POS SearchBar
        "point_of_sale._assets_pos": [
            "pos_search_bar/static/src/utils/product_search_utils.js",
            "pos_search_bar/static/src/js/*.js",
            "pos_search_bar/static/src/xml/*.xml",
        ],
    },
    "installable": True,
    "application": False,
}
