odoo.define('companiesweb.bring_data', function (require) {
    "use strict";

    $(document).ready(function () {
        // Función para obtener las empresas de una provincia
        function obtenerEmpresasPorEstado(estado) {
            // URL de la API
            fetch(`http://localhost:8069/api/company_by_state?state_name=${estado}`)
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        const companies = data.companies;
                        const container = document.querySelector('#nav_tabs_content_1721534277802_89 .container-fluid .row.s_nb_column_fixed');

                        // Limpiar cualquier contenido existente
                        container.innerHTML = '';

                        // Iterar sobre las empresas para generar el HTML dinámico
                        if (companies.length > 0) {
                            companies.forEach(company => {
                                const companyHTML = `
                                    <div class="col-md-12 col-12 mb-4 s_media_list_item pb16 pt0">
                                        <div class="row s_col_no_resize s_col_no_bgcolor g-0 o_colored_level o_cc o_cc4 bg-o-color-4 rounded shadow align-items-center">
                                            <div class="col-lg-3 text-center">
                                                <strong>${company.name}</strong>
                                            </div>
                                            <div class="col-lg-3 text-center">
                                                ${company.street} ${company.street2}
                                            </div>
                                            <div class="col-lg-3 text-center">
                                                ${company.state}
                                            </div>
                                            <div class="col-lg-3 text-center">
                                                ${company.phone || 'Sin contacto'}
                                            </div>
                                        </div>
                                    </div>`;
                                // Insertar el HTML en el contenedor
                                container.insertAdjacentHTML('beforeend', companyHTML);
                            });
                        } else {
                            container.innerHTML = `<p>No hay empresas disponibles para el estado seleccionado.</p>`;
                        }
                    } else {
                        console.error('Error en la respuesta de la API:', data);
                        container.innerHTML = `<p>Error al obtener las empresas. Inténtalo más tarde.</p>`;
                    }
                })
                .catch(error => {
                    console.error('Error al obtener los datos:', error);
                    container.innerHTML = `<p>Error al cargar las empresas. Inténtalo más tarde.</p>`;
                });
        }
    });
});
