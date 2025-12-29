/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

//publicWidget.registry.FixPriceOrderWithStyle = publicWidget.Widget.extend({
//    selector: '.oe_website_sale',
//    start() {
//        this.fixPrices();
//        $('.product_price').addClass('processed');
//        return this._super(...arguments);
//    },
//    fixPrices() {
//        $('.product_price').each(function () {
//            const $priceContainer = $(this);
//            const $priceSpans = $priceContainer.children('span');
//
//            if ($priceSpans.length >= 2) {
//                const parsePrice = ($el) => {
//                    let text = $el.text().replace(/\s/g, '').replace(',', '.').replace(/[^0-9.]/g, '');
//                    return parseFloat(text) || 0;
//                };
//
//                let firstPriceVal = parsePrice($priceSpans.eq(0));
//                let secondPriceVal = parsePrice($priceSpans.eq(1));
//
//                let $originalSpan, $discountSpan;
//
//                if (firstPriceVal >= secondPriceVal) {
//                    $originalSpan = $priceSpans.eq(0);
//                    $discountSpan = $priceSpans.eq(1);
//                } else {
//                    $originalSpan = $priceSpans.eq(1);
//                    $discountSpan = $priceSpans.eq(0);
//                }
//
//                $originalSpan.addClass('oe_striked_price text-muted').css('text-decoration', 'line-through');
//
//                $priceContainer.empty();
//                $priceContainer.append($originalSpan).append($discountSpan);
//            }
//        });
//    },
//});

publicWidget.registry.PlaceholderOnShopAddress = publicWidget.Widget.extend({
    selector: '.oe_website_sale',

    start() {
        if (window.location.pathname.includes('/shop/address')) {
            this.addPlaceholders();
            this.addRequiredFields();
            this.addAsteriskToLabels();
            this.addIdentificationValidation();
        }
        return this._super(...arguments);
    },

    addPlaceholders() {
        const fields = [
            {name: 'name', placeholder: 'Ej: Jorge Lopez', title: 'Agregue su nombre completo'},
            {name: 'email', placeholder: 'Ej: example@gmail.com', title: 'Ingrese un correo válido'},
            {name: 'phone', placeholder: 'Ej: +593 987654321', title: 'Agregue su número de teléfono'},
            {name: 'street', placeholder: 'Ej: Av. Loja y Universitaria', title: 'Número y calle'},
            {name: 'street2', placeholder: 'Ej: Departamento 4B', title: 'Apartamento, suite, etc.'},
            {name: 'city', placeholder: 'Ej: Loja', title: 'Ingrese su ciudad'},
            {name: 'zip', placeholder: 'Ej: 110101', title: 'Código postal (opcional)'},
            {name: 'vat', placeholder: 'Ej: 0102030405', title: 'Número de identificación personal o empresa'},
            {name: 'company_name', placeholder: 'Ej: Mi Empresa S.A.', title: 'Nombre de la empresa (opcional)'},
        ];

        fields.forEach(({name, placeholder, title}) => {
            const input = document.querySelector(`input[name="${name}"]`);
            if (input) {
                input.setAttribute('placeholder', placeholder);
                input.setAttribute('title', title);
            }
        });

        const countrySelect = document.querySelector('select[name="country_id"]');
        if (countrySelect) {
            countrySelect.setAttribute('title', 'Seleccione su país');
        }

        const stateSelect = document.querySelector('select[name="state_id"]');
        if (stateSelect) {
            stateSelect.setAttribute('title', 'Seleccione su provincia o estado');
        }
    },

    addAsteriskToLabels() {
        const requiredLabels = [
            'name',
            'email',
            'street',
            'city',
            'vat',
        ];

        requiredLabels.forEach((fieldName) => {
            const label = document.querySelector(`label[for="${fieldName}"]`);
            if (label && !label.innerHTML.includes('*')) {
                label.innerHTML += ' <span class="text-danger">*</span>';
            }
        });
    },

    addRequiredFields() {
        const requiredFields = [
            'name',
            'email',
            'phone',
            'street',
            'city',
            'vat'
        ];

        requiredFields.forEach((fieldName) => {
            const input = document.querySelector(`[name="${fieldName}"]`);
            if (input) {
                input.setAttribute('required', 'required');
            }
        });
    },

    addIdentificationValidation() {
    const vatInput = document.querySelector('input[name="vat"]');
    const identificationTypeSelect = document.querySelector('select[name="l10n_latam_identification_type_id"]');

    if (!vatInput || !identificationTypeSelect) return;

    // Función para actualizar placeholder según el tipo
    const updatePlaceholder = () => {
        const selectedOption = identificationTypeSelect.selectedOptions[0];
        if (selectedOption) {
            const optionText = selectedOption.textContent.toLowerCase();
            let placeholder = 'Ingrese su número de identificación';

            if (optionText.includes('cedula') || optionText.includes('cédula')) {
                placeholder = 'Ej: 0102030405 (10 dígitos)';
            } else if (optionText.includes('ruc')) {
                placeholder = 'Ej: 0102030405001 (13 dígitos)';
            } else if (optionText.includes('pasaporte')) {
                placeholder = 'Ej: AB123456 (letras y números)';
            }

            vatInput.setAttribute('placeholder', placeholder);
        }
    };

    // Actualizar placeholder cuando cambie el tipo
    identificationTypeSelect.addEventListener('change', () => {
        updatePlaceholder();
        // Revalidar el campo actual si tiene contenido
        if (vatInput.value.trim()) {
            vatInput.validateIdentification();
        }
    });

    // Inicializar placeholder
    updatePlaceholder();

    // Agregar evento de validación en tiempo real
    vatInput.addEventListener('input', function(e) {
        this.validateIdentification();
    });

    // Agregar evento de validación al perder el foco
    vatInput.addEventListener('blur', function(e) {
        this.validateIdentification();
    });

    // Método de validación personalizado
    vatInput.validateIdentification = function() {
        const value = this.value.trim();
        const errorElement = this.parentNode.querySelector('.identification-error');

        // Remover mensaje de error anterior
        if (errorElement) {
            errorElement.remove();
        }

        if (value === '') {
            this.setCustomValidity('');
            this.classList.remove('is-invalid', 'is-valid');
            return;
        }

        // Obtener el tipo de identificación seleccionado
        const selectedOption = identificationTypeSelect.selectedOptions[0];
        if (!selectedOption.value) {
            this.setCustomValidity('Seleccione primero el tipo de identificación');
            this.classList.add('is-invalid');
            return;
        }

        const identificationType = selectedOption.textContent.toLowerCase();
        const validationResult = validateByType(value, identificationType);

        if (!validationResult.isValid) {
            // Crear elemento de error
            const errorDiv = document.createElement('div');
            errorDiv.className = 'identification-error text-danger small mt-1';
            errorDiv.textContent = validationResult.message;
            this.parentNode.appendChild(errorDiv);

            // Marcar campo como inválido
            this.setCustomValidity(validationResult.message);
            this.classList.add('is-invalid');
            this.classList.remove('is-valid');
        } else {
            // Campo válido
            this.setCustomValidity('');
            this.classList.remove('is-invalid');
            this.classList.add('is-valid');
        }
    };

    // Función para validar según el tipo seleccionado
    function validateByType(value, identificationType) {
        if (identificationType.includes('cedula') || identificationType.includes('cédula')) {
            return validateCedula(value);
        } else if (identificationType.includes('ruc')) {
            return validateRUC(value);
        } else if (identificationType.includes('pasaporte')) {
            return validatePasaporte(value);
        } else {
            // Tipo genérico o desconocido
            return {
                isValid: true,
                message: 'Identificación válida'
            };
        }
    }

    function validateCedula(cedula) {
        if (cedula.length !== 10 || !/^\d{10}$/.test(cedula)) {
            return {
                isValid: false,
                message: 'La cédula debe tener exactamente 10 dígitos numéricos'
            };
        }

        return {
            isValid: true,
            message: 'Cédula válida'
        };
    }

    function validateRUC(ruc) {
        if (ruc.length !== 13 || !/^\d{13}$/.test(ruc)) {
            return {
                isValid: false,
                message: 'El RUC debe tener exactamente 13 dígitos numéricos'
            };
        }

        return {
            isValid: true,
            message: 'RUC válido'
        };
    }

    function validatePasaporte(pasaporte) {
        if (pasaporte.length < 6 || pasaporte.length > 20) {
            return {
                isValid: false,
                message: 'El pasaporte debe tener entre 6 y 20 caracteres'
            };
        }

        if (!/^[A-Za-z0-9]+$/.test(pasaporte)) {
            return {
                isValid: false,
                message: 'El pasaporte solo puede contener letras y números'
            };
        }

        return {
            isValid: true,
            message: 'Pasaporte válido'
        };
    }
}
});
