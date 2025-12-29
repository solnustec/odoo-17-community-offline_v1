/** @odoo.module **/


$(document).ready(async function () {
    update_lis_product()
    const product_detail = document.getElementById("product_detail")
    if (product_detail) {
        let products = []
        const product_data_string = product_detail.getAttribute("data-product-tracking-info")
        const product_data_json = JSON.parse(product_data_string)
        const price_element = document.querySelector(".oe_currency_value");
        const product_price_text = price_element.textContent;
        // const product_price = product_price_text.replace(",", ".");
        const price_container = document.querySelector('.oe_price')

        products.push({
            "product_id": product_data_json.item_id,
            // "price": product_price_text
        })
        await fetch('/website/loyalty_data', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({products: products})
        })
            .then(response => response.json())
            .then(data => {
                if (data.result.rewards !== undefined) {
//                    console.log(data)
                    price_container.classList.add('d-none')
                    document.querySelector('.oe_currency_value')
                    const original_price = document.querySelector('.oe_currency_value')
                    original_price.textContent = '$' + parseFloat(data.result.rewards[0].original_price).toFixed(2)
                    original_price.classList.add('price-discount')
                    original_price.parentNode.classList.add('h6')
                    const price_html_element = document.createElement('span')
                    price_html_element.className = 'oe_price mx-2 h4';
                    price_html_element.textContent = '$' + parseFloat(data.result.rewards[0].discounted_price).toFixed(2)
                    document.querySelector('.oe_price').append(price_html_element)
                    price_container.classList.remove('d-none')
                }
            })
    }

    // CODIOG PARA LA LISTA DE PRODUYCTOS LA PAGINA DE LISTADO DE PRODUCTOS
    const mainRow = document.querySelector(".o_wsale_products_main_row");

    if (mainRow) {
        const productElements = mainRow.querySelectorAll('div.o_wsale_product_sub');

        const productData = Array.from(productElements).map((element) => {
            const productInput = element.querySelector('input[name="product_id"]');
            const priceSpan = element.querySelector('.product_price .oe_currency_value');
            if (productInput && priceSpan) {
                return {
                    product_id: productInput.value,
                    price: parseFloat(priceSpan.textContent.replace(',', '.').trim())
                };
            }

            return null;
        }).filter(item => item !== null);
        const payload = {
            products: productData
        };

        fetch('/website/loyalty_data', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    console.error("Error en la API:", data.error);
                } else {
                    data.result.rewards.forEach((reward) => {
                        const productElement = document.querySelector(`input[name="product_id"][value="${reward.discount_product_id}"]`);
                        if (productElement) {
                            const priceContainer = productElement.closest('.o_wsale_product_sub').querySelector('.product_price');

                            if (priceContainer) {
                                // Buscar o crear el elemento del precio original
                                let originalPriceElement = priceContainer.querySelector('.price-discount');
                                if (!originalPriceElement) {
                                    originalPriceElement = document.createElement('span');
                                    originalPriceElement.className = 'price-discount';
                                    priceContainer.insertBefore(originalPriceElement, priceContainer.firstChild);
                                }
                                originalPriceElement.textContent = `$ ${reward.original_price}`;
                                const currencyValueElement = priceContainer.querySelector('.oe_currency_value');
                                if (currencyValueElement) {
                                    currencyValueElement.textContent = `${reward.discounted_price}`;
                                }
                            }
                        }
                    });
                }
            })
            .catch(error => {
                console.error("Error al enviar datos a la API:", error);
            });
    }
})


const update_lis_product = () => {

    document.querySelectorAll('.o_cart_product').forEach((productEl) => {
        const priceEls = productEl.querySelectorAll('.oe_currency_value');
        let numericPrice = null;
        priceEls.forEach(el => {
            let text = el.textContent.replace(/\uFEFF/g, '').trim();
            let value = parseFloat(text.replace(',', '.').replace(/[^\d.-]/g, ''));
            if (!isNaN(value) && value >= 0) {
                numericPrice = value;
            }
        });

        productEl.classList.toggle('valid-price', numericPrice !== null);
    });
}


const cartProducts = document.getElementById("cart_products");


if (cartProducts) {
    update_lis_product();

    const observer = new MutationObserver((mutations) => {
        update_lis_product();
    });

    observer.observe(cartProducts, {
        childList: true,
        subtree: true,
        attributes: true,
        characterData: true
    });
}

