document.addEventListener('DOMContentLoaded', function () {
    document.getElementById('apply-btn').addEventListener('click', function (ev) {
        ev.preventDefault();
        document.getElementById("wrap").style.opacity = '0.3'
        document.getElementById('apply-btn').setAttribute('disabled', 'disabled')
        document.getElementById('apply-btn').classList.add('o_loading')

        var domain = window.location.origin + "/";
        var url_check_cedula = domain + "check_cedula";
        var url_applicant = domain + "website/form/hr/applicant/hr/applicant";
        var form = document.getElementById('hr_recruitment_form');
        var formData = new FormData(form);
        var valid = true;

        form.querySelectorAll('[required]').forEach(function (field) {
            if (!field.value) {
                field.classList.add('is-invalid');
                field.focus();
                document.getElementById("wrap").style.opacity = '1'
                document.getElementById('apply-btn').removeAttribute('disabled', 'disabled')
                valid = false;
            } else {

                field.classList.remove('is-invalid');
            }
        });
        form.querySelectorAll('[data-regex-validation]').forEach(function (field) {
            var regexPattern = field.getAttribute('data-regex-validation');
            var regex = new RegExp(regexPattern);
            var value = field.value
            let test_regex = regex.test(value)
            var errorClass = field.name + "-error-message"
            var errorMessageElement = form.querySelector('.' + errorClass);

            if (!test_regex || !value) {
                field.classList.add('is-invalid');
                field.focus();
                valid = false;
                errorMessageElement.style.display = 'block';
            } else {
                field.classList.remove('is-invalid');
                if (errorMessageElement) {
                    errorMessageElement.style.display = 'none';
                }
            }
        });

        if (valid) {
            var cedula = form.querySelector('[name="identification"]').value;
            fetch(url_check_cedula, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({identification: cedula})
            })
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {

                    var identification_exist = JSON.parse(data.result);
                    if (identification_exist.exists === true) {
                        const divError = document.getElementById('error')
                        divError.classList.remove('d-none')
                        document.getElementById("wrap").style.opacity = '1'
                        document.getElementById('apply-btn').removeAttribute('disabled', 'disabled')
                        divError.innerText = "La identificación que has proporcionado ya ha sido utilizada para postular a esta vacante.\n"
                    } else {
                        fetch(url_applicant, {
                            method: 'POST',
                            body: formData,
                        })
                            .then(response => {
                                return response.json().then(data => {
                                    if (!response.ok) {
                                        throw { status: response.status, data: data };
                                    }
                                    return data;
                                });
                            })
                            .then(function (data) {
                                if (data && data.redirect_url) {
                                    window.location.href = data.redirect_url;
                                } else {
                                    console.log('Error al procesar la respuesta del servidor');

                                }
                            })
                            .catch(function (error) {
                                const divError = document.getElementById('error');
                                divError.classList.remove('d-none');
                                document.getElementById("wrap").style.opacity = '1';
                                document.getElementById('apply-btn').removeAttribute('disabled', 'disabled');

                                let errorHTML = error.data.message;

                                if (error.data.missing_fields) {
                                    errorHTML += `<ul class="mt-2 mb-0">`;

                                    if (Array.isArray(error.data.missing_fields)) {
                                        error.data.missing_fields.forEach(field => {
                                            errorHTML += `<li>El campo <strong>${field}</strong> es requerido</li>`;
                                        });
                                    } else {
                                        Object.entries(error.data.missing_fields).forEach(([field, isMissing]) => {
                                            if (isMissing) {
                                                errorHTML += `<li>El campo <strong>${field}</strong> es requerido</li>`;
                                            }
                                        });
                                    }

                                    errorHTML += `</ul>`;
                                }

                                divError.innerHTML = errorHTML;
                            });
                    }
                })
                .catch(function (error) {
                    console.log('Error al verificar la cédula:', error);
                });
        }else {
            document.getElementById("wrap").style.opacity = '1'
            document.getElementById('apply-btn').removeAttribute('disabled', 'disabled')
        }
    });
});
