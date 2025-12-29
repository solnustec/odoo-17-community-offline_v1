/** @odoo-module **/

/**
 * Classifies the input to detect barcode (numeric + ≥8 digits).
 * @param {string} input
 * @returns {'barcode' | 'text'}
 */
export function classifySearchInput(input) {
    const cleaned = (input || "").trim();
    if (!cleaned) return "text";

    const isNumeric = /^\d+$/.test(cleaned);
    const length = cleaned.length;

    const type = isNumeric && length >= 8 ? "barcode" : "text";

    return type;
}

/**
 * Splits and normalizes search input.
 * @param {string} rawString
 * @returns {string[]} normalized terms
 */
export function parseSearchInput(rawString) {
    const terms = (rawString || "")
        .trim()
        .replace(/;product_tmpl_id:\d+$/, "")
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "") // remove accents
        .split(/\s+/)
        .filter(Boolean);

    return terms;
}

/**
 * Build safe and flat domain for barcode or multi-term name search.
 * @param {string[]} terms
 * @param {Object} posConfig
 * @returns {Array} ORM domain
 */

export function buildSearchDomain(terms, posConfig) {
    const domain = [
        ["available_in_pos", "=", true],
        ["sale_ok", "=", true],
        ['detailed_type', '=', 'product'],
    ];

    if (!terms.length) return domain;

    if (terms.length === 1) {
        //si es solo un terminjo de busqueda hacer busqueda exacta en default_code y barcode
        const term = terms[0].trim();
        const searchConditions = [
            ["default_code", "=", term],
        ];
        if (term.length > 0) {
            searchConditions.push(["barcode", "=", term]);
        }
        // Averificar si el término es numérico
        const isNumeric = /^\d+$/.test(term);
        if (isNumeric) {
            //si es numérico buscar en multi_barcode_ids
            searchConditions.push([
                "multi_barcode_ids.product_multi_barcode",
                "like",
                term,
            ]);
        } else {
            searchConditions.push(['name', 'ilike', '%' + terms.join('%') + '%'],);
        }
        // Construir OR: necesitamos n-1 operadores "|" para n condiciones
        for (let i = 0; i < searchConditions.length - 1; i++) {
            domain.push("|");
        }
        domain.push(...searchConditions);
        // domain.push(['name', 'ilike', '%' + terms.join('%') + '%'])
    } else {
        //si es mas de un termino hacer busqueda ilike en name, default_code y barcode
        const allConditions = [];
        // allConditions.push(['name', 'ilike', '%' + terms.join('%') + '%'])
        for (const term of terms) {
            const trimmed = term.trim();
            if (!trimmed) continue;
            allConditions.push(["name", "ilike", trimmed]);
            allConditions.push(["default_code", "ilike", trimmed]);
        }
        if (allConditions.length > 0) {
            // Agregar OR operators
            for (let i = 0; i < allConditions.length - 1; i++) {
                domain.push("|");
            }
            domain.push(...allConditions);
        }
    }

    if (
        posConfig.limit_categories &&
        posConfig.iface_available_categ_ids?.length
    ) {
        domain.push(["pos_categ_ids", "in", posConfig.iface_available_categ_ids]);
    }

    return domain;
}


export function filterProductsClientSide(products, terms, excludedIds = []) {
    // If the search term is numeric (likely a barcode), trust backend results
    // since the domain already includes multi_barcode_ids search
    const isNumericSearch = terms.length === 1 && /^\d+$/.test(terms[0]);
    if (isNumericSearch) {
        return products.filter((product) => !excludedIds.includes(product.id));
    }

    // Otherwise, apply standard filtering
    return products
        .filter((product) => {
            const barcodes = (product.multi_barcode_ids || []).map((b) =>
                typeof b === "object" && b.product_multi_barcode
                    ? b.product_multi_barcode.toLowerCase()
                    : (b || "").toString().toLowerCase()
            );

            const matches = terms.every((term) => {
                const t = term.toLowerCase();
                const nameMatch = (product.display_name || "")
                    .toLowerCase()
                    .includes(t);
                const codeMatch = (product.default_code || "")
                    .toLowerCase()
                    .includes(t);
                const barcodeMatch = barcodes.some((code) => code.includes(t));

                return nameMatch || codeMatch || barcodeMatch;
            });

            return matches;
        })
        .filter((product) => !excludedIds.includes(product.id));
}
