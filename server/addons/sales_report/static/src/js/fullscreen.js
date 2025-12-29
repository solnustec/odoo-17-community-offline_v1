// custom_fullscreen.js
odoo.define('dashboard_pos.custom_fullscreen', [], function (require) {
    "use strict";

    function toggleSidebar() {
        if ($('.dashboard_for_report_sales').length) {
            $('.mk_apps_sidebar_panel').css('display', 'none');
        } else {
            $('.mk_apps_sidebar_panel').css('display', '');
        }
    }

    $(document).ready(function () {
        toggleSidebar();

        var observer = new MutationObserver(function (mutations) {
            mutations.forEach(function () {
                toggleSidebar();
            });
        });
        observer.observe(document.body, {
            childList: true,
            subtree: true,
        });
    });
});