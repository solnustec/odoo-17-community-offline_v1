odoo.define('internal_control.survey_section_single', [], function (require) {
    'use strict';

    function showOnlyActiveSection() {
        var $breadcrumb = document.querySelector('ol.breadcrumb');
        if ($breadcrumb) {
            var items = $breadcrumb.querySelectorAll('li.breadcrumb-item');
            items.forEach(function (li) {
                li.style.display = 'none';
            });
            var active = $breadcrumb.querySelector('li.breadcrumb-item.active');
            if (active) {
                active.style.display = '';
            }
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        showOnlyActiveSection();

        var $breadcrumb = document.querySelector('ol.breadcrumb');
        if ($breadcrumb) {
            var observer = new MutationObserver(function () {
                showOnlyActiveSection();
            });
            observer.observe($breadcrumb, { childList: true, subtree: true, attributes: true });
        }

        document.body.addEventListener('click', function (ev) {
            if (ev.target.closest('.o_survey_next, .o_survey_prev')) {
                setTimeout(showOnlyActiveSection, 100);
            }
        });
    });
});
