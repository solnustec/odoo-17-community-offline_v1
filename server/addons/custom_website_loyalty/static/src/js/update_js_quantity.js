function calculateTotalPrice() {
    // Obtener la cantidad del input
    var quantity = parseFloat($('input[name="add_qty"]').val()) || 0;
    // Obtener el product_template_id del atributo data-id del span
    var productTemplateId = $('.oe_price_discount_c').attr('data-id');

    if (!productTemplateId || quantity <= 0) {
        updateTotalPriceDisplay(0);
        return;
    }

    // Llamar a la API para calcular el precio con descuento
    $.ajax({
        url: '/api/product/cart/discount',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            product_tmpl_id: productTemplateId,
            product_uom_qty: quantity
        }),
        success: function(response) {
            if (response.result.success) {
                var totalPrice = response.result.result;
                updateTotalPriceDisplay(totalPrice);
            } else {
                var unitPrice = parseFloat($('.oe_price_discount_c').data('price')) || 0;
                var totalPrice = quantity * unitPrice;
                updateTotalPriceDisplay(totalPrice);
            }
        },
        error: function(xhr, status, error) {
            console.error('Error en la llamada AJAX:', error);
            // Fallback al cálculo manual
            var unitPrice = parseFloat($('.oe_price_discount_c').data('price')) || 0;
            var totalPrice = quantity * unitPrice;
            updateTotalPriceDisplay(totalPrice);
        }
    });
}

// Función para actualizar la visualización del precio total
function updateTotalPriceDisplay(totalPrice) {
    if (typeof totalPrice === 'number') {
        $('.oe_price_discount_c .oe_currency_value').text(totalPrice.toFixed(2).replace('.', ','));
    } else {
        $('.oe_price_discount_c .oe_currency_value').text(totalPrice);
    }
}

$(document).ready(function() {
    // Event listener para cantidad
    $(document).on('change input', 'input[name="add_qty"]', function() {
        calculateTotalPrice();
    });

    // Observer para detectar cambios en el precio (cuando cambia el data-id)
    var priceElement = document.querySelector('.oe_price_discount_c');
    if (priceElement) {
        var observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'attributes' && mutation.attributeName === 'data-id') {
                    console.log('Product template ID changed:', mutation.target.getAttribute('data-id'));
                    calculateTotalPrice();
                }
            });
        });

        observer.observe(priceElement, {
            attributes: true,
            attributeFilter: ['data-id']
        });
    }

    setTimeout(function() {
        calculateTotalPrice();
    }, 100);
});