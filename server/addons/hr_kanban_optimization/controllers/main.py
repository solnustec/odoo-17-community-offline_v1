# -*- coding: utf-8 -*-
"""
HTTP Controllers for HR Kanban Optimization

Provides endpoints for:
- Lazy-loaded employee images
- Cache management
- Statistics and monitoring
"""

import base64
import logging

from odoo import http
from odoo.http import request, Response
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


class HrKanbanOptimizationController(http.Controller):
    """Controller for HR Kanban Optimization module."""

    # =========================================================================
    # IMAGE ENDPOINTS
    # =========================================================================

    @http.route(
        '/hr_kanban_optimization/employee/<int:employee_id>/image',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False
    )
    def get_employee_image(self, employee_id, size='128', **kwargs):
        """
        Serve employee image with caching headers.

        :param employee_id: Employee ID
        :param size: Image size (64, 128, 256, 512)
        :return: Image response or placeholder
        """
        try:
            Employee = request.env['hr.employee']
            result = Employee.get_employee_image(employee_id, size)

            if not result.get('success') or not result.get('has_image'):
                # Return 1x1 transparent PNG as placeholder
                transparent_png = base64.b64decode(
                    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
                )
                return Response(
                    transparent_png,
                    content_type='image/png',
                    headers={
                        'Cache-Control': 'public, max-age=86400',  # 1 day
                        'X-Employee-Has-Image': 'false',
                    }
                )

            # Decode and serve image
            image_data = result['image_data']
            if isinstance(image_data, str):
                image_data = base64.b64decode(image_data)

            return Response(
                image_data,
                content_type='image/png',
                headers={
                    'Cache-Control': 'public, max-age=3600',  # 1 hour
                    'X-Employee-Id': str(employee_id),
                    'X-Image-Size': str(size),
                }
            )

        except AccessError:
            return Response('Access Denied', status=403)
        except Exception as e:
            _logger.exception("Error serving employee image %s", employee_id)
            return Response('Error', status=500)

    @http.route(
        '/hr_kanban_optimization/employee/<int:employee_id>/image/check',
        type='json',
        auth='user',
        methods=['POST']
    )
    def check_employee_image(self, employee_id, **kwargs):
        """
        Check if employee has image without loading the binary.
        Useful for lazy loading decisions.
        """
        try:
            Employee = request.env['hr.employee'].sudo()
            employee = Employee.browse(employee_id)

            if not employee.exists():
                return {'exists': False, 'has_image': False}

            return {
                'exists': True,
                'has_image': employee.has_image,
                'employee_id': employee_id,
            }
        except Exception as e:
            _logger.exception("Error checking employee image %s", employee_id)
            return {'error': str(e)}

    # =========================================================================
    # DATA ENDPOINTS
    # =========================================================================

    @http.route(
        '/hr_kanban_optimization/employee/<int:employee_id>/details',
        type='json',
        auth='user',
        methods=['POST']
    )
    def get_employee_details(self, employee_id, **kwargs):
        """Get deferred employee details."""
        return request.env['hr.employee'].get_employee_details(employee_id)

    @http.route(
        '/hr_kanban_optimization/employee/<int:employee_id>/activities',
        type='json',
        auth='user',
        methods=['POST']
    )
    def get_employee_activities(self, employee_id, **kwargs):
        """Get employee activities."""
        return request.env['hr.employee'].get_employee_activities(employee_id)

    @http.route(
        '/hr_kanban_optimization/batch',
        type='json',
        auth='user',
        methods=['POST']
    )
    def get_batch_data(self, employee_ids=None, fields_list=None, page=1, page_size=50, **kwargs):
        """Get batch employee data with pagination."""
        return request.env['hr.employee'].get_kanban_batch_data(
            employee_ids=employee_ids,
            fields_list=fields_list,
            page=page,
            page_size=page_size
        )

    # =========================================================================
    # CACHE MANAGEMENT ENDPOINTS (Admin only)
    # =========================================================================

    @http.route(
        '/hr_kanban_optimization/cache/stats',
        type='json',
        auth='user',
        methods=['POST']
    )
    def get_cache_stats(self, **kwargs):
        """Get cache statistics (requires HR Manager access)."""
        if not request.env.user.has_group('hr.group_hr_manager'):
            return {'error': 'Access denied. HR Manager required.'}
        return request.env['hr.employee'].get_cache_stats()

    @http.route(
        '/hr_kanban_optimization/cache/clear',
        type='json',
        auth='user',
        methods=['POST']
    )
    def clear_cache(self, **kwargs):
        """Clear all caches (requires HR Manager access)."""
        if not request.env.user.has_group('hr.group_hr_manager'):
            return {'error': 'Access denied. HR Manager required.'}
        return request.env['hr.employee'].clear_all_caches()

    @http.route(
        '/hr_kanban_optimization/cache/warmup',
        type='json',
        auth='user',
        methods=['POST']
    )
    def warmup_cache(self, limit=100, **kwargs):
        """Warmup cache with recent employees (requires HR Manager access)."""
        if not request.env.user.has_group('hr.group_hr_manager'):
            return {'error': 'Access denied. HR Manager required.'}
        count = request.env['hr.employee'].warmup_cache(limit=limit)
        return {'success': True, 'employees_cached': count}
