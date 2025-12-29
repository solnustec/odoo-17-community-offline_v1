/** @odoo-module **/

odoo.define('internal_control/js/survey_form_mock', [], function (require) {
    'use strict';

    const SurveyFormWidget = {
        include: function (methods) {
            console.warn('[MockSurveyFormWidget] include() fue llamado');
            Object.assign(this, methods);
        }
    };

    return SurveyFormWidget;
});
