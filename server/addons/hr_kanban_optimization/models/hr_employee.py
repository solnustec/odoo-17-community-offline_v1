# -*- coding: utf-8 -*-
"""
HR Employee Kanban Optimization Module - Advanced Performance Features

This module implements enterprise-grade optimizations for hr.employee kanban view:
- Multi-tier caching (Memory LRU + optional Redis)
- Selective cache invalidation by employee/field
- SQL-optimized computed fields
- Image caching with size variants
- Batch processing with pagination
- Resilience and graceful degradation
"""

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from functools import wraps
from contextlib import contextmanager

from odoo import api, fields, models, _, SUPERUSER_ID
from odoo.exceptions import AccessError, UserError
from odoo.tools import image_process, sql
from odoo.tools.misc import DEFAULT_SERVER_DATE_FORMAT

_logger = logging.getLogger(__name__)


# =============================================================================
# ADVANCED CACHE IMPLEMENTATION
# =============================================================================

class LRUCache:
    """
    Thread-safe LRU (Least Recently Used) Cache with TTL support.

    Features:
    - O(1) access time
    - Automatic expiration
    - Memory-efficient with configurable max size
    - Thread-safe operations
    """

    def __init__(self, max_size=1000, default_ttl=300):
        self._cache = OrderedDict()
        self._timestamps = {}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key, default=None):
        """Get item from cache with TTL check."""
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return default

            # Check TTL
            timestamp, ttl = self._timestamps.get(key, (0, 0))
            if time.time() - timestamp > ttl:
                self._delete_key(key)
                self._misses += 1
                return default

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]

    def set(self, key, value, ttl=None):
        """Set item in cache with optional custom TTL."""
        ttl = ttl or self._default_ttl
        with self._lock:
            # Remove oldest items if at capacity
            while len(self._cache) >= self._max_size:
                oldest_key = next(iter(self._cache))
                self._delete_key(oldest_key)

            self._cache[key] = value
            self._timestamps[key] = (time.time(), ttl)
            self._cache.move_to_end(key)

    def delete(self, key):
        """Delete specific key from cache."""
        with self._lock:
            self._delete_key(key)

    def _delete_key(self, key):
        """Internal delete without lock."""
        self._cache.pop(key, None)
        self._timestamps.pop(key, None)

    def invalidate_pattern(self, pattern_func):
        """Invalidate all keys matching a pattern function."""
        with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if pattern_func(k)]
            for key in keys_to_delete:
                self._delete_key(key)
            return len(keys_to_delete)

    def clear(self):
        """Clear entire cache."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._timestamps.clear()
            return count

    def get_stats(self):
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            return {
                'size': len(self._cache),
                'max_size': self._max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': f'{hit_rate:.1f}%',
            }


class RedisCacheAdapter:
    """
    Redis cache adapter for distributed caching.
    Falls back gracefully if Redis is unavailable.
    """

    def __init__(self, host='localhost', port=6379, db=0, prefix='odoo:hr_kanban:', default_ttl=300):
        self._prefix = prefix
        self._default_ttl = default_ttl
        self._redis = None
        self._available = False
        self._last_check = 0
        self._check_interval = 60  # Check Redis availability every 60 seconds

        try:
            import redis
            self._redis = redis.Redis(host=host, port=port, db=db, socket_timeout=1)
            self._redis.ping()
            self._available = True
            _logger.info("Redis cache connected: %s:%s", host, port)
        except Exception as e:
            _logger.warning("Redis not available, using memory cache: %s", e)

    def _check_availability(self):
        """Periodically check if Redis became available."""
        if self._available:
            return True
        if time.time() - self._last_check < self._check_interval:
            return False
        self._last_check = time.time()
        try:
            if self._redis:
                self._redis.ping()
                self._available = True
                _logger.info("Redis connection restored")
                return True
        except Exception:
            pass
        return False

    def _make_key(self, key):
        return f"{self._prefix}{key}"

    def get(self, key, default=None):
        if not self._check_availability():
            return default
        try:
            value = self._redis.get(self._make_key(key))
            if value:
                return json.loads(value)
        except Exception as e:
            _logger.debug("Redis get error: %s", e)
            self._available = False
        return default

    def set(self, key, value, ttl=None):
        if not self._check_availability():
            return False
        try:
            ttl = ttl or self._default_ttl
            self._redis.setex(self._make_key(key), ttl, json.dumps(value))
            return True
        except Exception as e:
            _logger.debug("Redis set error: %s", e)
            self._available = False
        return False

    def delete(self, key):
        if not self._check_availability():
            return False
        try:
            self._redis.delete(self._make_key(key))
            return True
        except Exception:
            return False

    def invalidate_pattern(self, pattern):
        if not self._check_availability():
            return 0
        try:
            keys = self._redis.keys(self._make_key(pattern))
            if keys:
                return self._redis.delete(*keys)
        except Exception:
            pass
        return 0

    def clear(self):
        if not self._check_availability():
            return 0
        try:
            keys = self._redis.keys(self._make_key('*'))
            if keys:
                return self._redis.delete(*keys)
        except Exception:
            pass
        return 0

    @property
    def is_available(self):
        return self._available


class HybridCache:
    """
    Two-tier cache: fast memory LRU + distributed Redis.
    Provides best of both worlds: speed + persistence.
    """

    def __init__(self, use_redis=False, **redis_kwargs):
        self._memory = LRUCache(max_size=500, default_ttl=300)
        self._redis = RedisCacheAdapter(**redis_kwargs) if use_redis else None

    def get(self, key, default=None):
        # Try memory first (fastest)
        value = self._memory.get(key)
        if value is not None:
            return value

        # Try Redis if available
        if self._redis and self._redis.is_available:
            value = self._redis.get(key)
            if value is not None:
                # Populate memory cache
                self._memory.set(key, value, ttl=60)  # Short TTL for memory
                return value

        return default

    def set(self, key, value, ttl=None):
        self._memory.set(key, value, ttl)
        if self._redis:
            self._redis.set(key, value, ttl)

    def delete(self, key):
        self._memory.delete(key)
        if self._redis:
            self._redis.delete(key)

    def invalidate_employee(self, employee_id):
        """Invalidate all cache entries for a specific employee."""
        pattern_func = lambda k: f'emp_{employee_id}_' in k or f'_emp_{employee_id}' in k
        count = self._memory.invalidate_pattern(pattern_func)
        if self._redis:
            count += self._redis.invalidate_pattern(f'*emp_{employee_id}*')
        return count

    def invalidate_all(self):
        """Clear all caches."""
        count = self._memory.clear()
        if self._redis:
            count += self._redis.clear()
        return count

    def get_stats(self):
        stats = {'memory': self._memory.get_stats()}
        if self._redis:
            stats['redis_available'] = self._redis.is_available
        return stats


# Global cache instances
_kanban_cache = HybridCache(use_redis=False)  # Set to True to enable Redis
_image_cache = LRUCache(max_size=200, default_ttl=3600)  # 1 hour for images
_activities_cache = LRUCache(max_size=500, default_ttl=120)  # 2 min for activities


# =============================================================================
# CACHE DECORATORS
# =============================================================================

def cached_method(cache_instance, key_func, ttl=None):
    """Decorator for caching method results."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            cache_key = key_func(self, *args, **kwargs)
            result = cache_instance.get(cache_key)
            if result is not None:
                return result
            result = func(self, *args, **kwargs)
            if result is not None:
                cache_instance.set(cache_key, result, ttl)
            return result
        return wrapper
    return decorator


# =============================================================================
# MAIN MODEL
# =============================================================================

class HrEmployeeKanbanOptimization(models.Model):
    _inherit = 'hr.employee'

    # =========================================================================
    # OPTIMIZED COMPUTED FIELDS
    # =========================================================================

    has_image = fields.Boolean(
        string='Has Image',
        compute='_compute_has_image',
        store=True,
        index=True,
        help='Boolean flag indicating if employee has a profile image'
    )

    activities_summary = fields.Json(
        string='Activities Summary',
        compute='_compute_activities_summary_optimized',
        compute_sudo=True,
        help='Lightweight JSON summary of activities for kanban view'
    )

    # Stored summary for faster access (updated via cron or triggers)
    activities_summary_stored = fields.Json(
        string='Cached Activities Summary',
        help='Pre-computed activities summary, updated periodically'
    )

    last_activity_update = fields.Datetime(
        string='Last Activity Update',
        help='Timestamp of last activity summary computation'
    )

    image_small_url = fields.Char(
        string='Small Image URL',
        compute='_compute_image_urls',
        help='URL to fetch small image on demand'
    )

    # =========================================================================
    # OPTIMIZED COMPUTE METHODS
    # =========================================================================

    @api.depends('image_1920')
    def _compute_has_image(self):
        """
        Compute has_image flag by checking if image attachment exists.
        Uses ir.attachment query to avoid loading binary data.
        """
        if not self.ids:
            return

        # Query ir.attachment to check for image existence without loading binary
        # Images in Odoo are stored as attachments with res_field = 'image_1920'
        self.env.cr.execute("""
            SELECT res_id
            FROM ir_attachment
            WHERE res_model = 'hr.employee'
              AND res_field = 'image_1920'
              AND res_id IN %s
        """, (tuple(self.ids),))

        employees_with_image = {row[0] for row in self.env.cr.fetchall()}

        for employee in self:
            employee.has_image = employee.id in employees_with_image

    def _compute_activities_summary_optimized(self):
        """
        Optimized activity summary computation using SQL aggregation.
        Reduces N+1 queries to a single aggregated query.
        """
        if not self.ids:
            return

        today = fields.Date.context_today(self)

        # Single SQL query to get all activity stats
        self.env.cr.execute("""
            SELECT
                ma.res_id as employee_id,
                COUNT(*) as total_count,
                COUNT(CASE WHEN ma.date_deadline < %s THEN 1 END) as overdue_count,
                COUNT(CASE WHEN ma.date_deadline = %s THEN 1 END) as today_count,
                COUNT(CASE WHEN ma.date_deadline > %s THEN 1 END) as upcoming_count,
                MIN(ma.date_deadline) as next_deadline
            FROM mail_activity ma
            WHERE ma.res_model = 'hr.employee'
              AND ma.res_id IN %s
            GROUP BY ma.res_id
        """, (today, today, today, tuple(self.ids)))

        results = {row[0]: {
            'count': row[1],
            'overdue': row[2],
            'today': row[3],
            'upcoming': row[4],
            'next_deadline': row[5],
        } for row in self.env.cr.fetchall()}

        for employee in self:
            data = results.get(employee.id)
            if not data or data['count'] == 0:
                employee.activities_summary = {
                    'count': 0,
                    'has_overdue': False,
                    'has_today': False,
                    'next_deadline': False,
                    'summary_text': ''
                }
            else:
                parts = []
                if data['overdue']:
                    parts.append(f"{data['overdue']} overdue")
                if data['today']:
                    parts.append(f"{data['today']} today")
                if data['upcoming']:
                    parts.append(f"{data['upcoming']} upcoming")

                employee.activities_summary = {
                    'count': data['count'],
                    'has_overdue': data['overdue'] > 0,
                    'has_today': data['today'] > 0,
                    'next_deadline': str(data['next_deadline']) if data['next_deadline'] else False,
                    'summary_text': ', '.join(parts)
                }

    def _compute_image_urls(self):
        """Compute URLs for on-demand image loading."""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for employee in self:
            employee.image_small_url = f'{base_url}/hr_kanban_optimization/employee/{employee.id}/image'

    # =========================================================================
    # BATCH UPDATE FOR STORED SUMMARIES
    # =========================================================================

    @api.model
    def _cron_update_activity_summaries(self):
        """
        Cron job to pre-compute and store activity summaries.
        Run this periodically (e.g., every 5 minutes) for large datasets.
        """
        _logger.info("Starting activity summary batch update")

        today = fields.Date.context_today(self)
        batch_size = 500
        offset = 0
        total_updated = 0

        while True:
            # Process in batches to avoid memory issues
            employees = self.search([], limit=batch_size, offset=offset)
            if not employees:
                break

            # Get all activity data in one query
            self.env.cr.execute("""
                SELECT
                    ma.res_id,
                    COUNT(*) as total,
                    COUNT(CASE WHEN ma.date_deadline < %s THEN 1 END) as overdue,
                    COUNT(CASE WHEN ma.date_deadline = %s THEN 1 END) as today_count,
                    MIN(ma.date_deadline) as next_deadline
                FROM mail_activity ma
                WHERE ma.res_model = 'hr.employee'
                  AND ma.res_id IN %s
                GROUP BY ma.res_id
            """, (today, today, tuple(employees.ids)))

            results = {r[0]: r for r in self.env.cr.fetchall()}
            now = fields.Datetime.now()

            for emp in employees:
                data = results.get(emp.id)
                summary = {
                    'count': data[1] if data else 0,
                    'has_overdue': (data[2] > 0) if data else False,
                    'has_today': (data[3] > 0) if data else False,
                    'next_deadline': str(data[4]) if data and data[4] else False,
                }

                # Direct SQL update to avoid triggering compute
                self.env.cr.execute("""
                    UPDATE hr_employee
                    SET activities_summary_stored = %s,
                        last_activity_update = %s
                    WHERE id = %s
                """, (json.dumps(summary), now, emp.id))

            total_updated += len(employees)
            offset += batch_size

            # Commit batch to release locks
            self.env.cr.commit()

        _logger.info("Activity summary update complete: %d employees updated", total_updated)
        return total_updated

    # =========================================================================
    # SELECTIVE CACHE INVALIDATION
    # =========================================================================

    @classmethod
    def _get_cache_key(cls, prefix, employee_id=None, **kwargs):
        """Generate cache key with optional employee-specific prefix."""
        key_parts = [prefix]
        if employee_id:
            key_parts.append(f'emp_{employee_id}')
        for k, v in sorted(kwargs.items()):
            key_parts.append(f'{k}_{v}')
        return '_'.join(str(p) for p in key_parts)

    def _invalidate_employee_caches(self):
        """Invalidate caches for specific employees only."""
        for emp_id in self.ids:
            count = _kanban_cache.invalidate_employee(emp_id)
            _image_cache.invalidate_pattern(lambda k: f'emp_{emp_id}_' in k)
            _activities_cache.invalidate_pattern(lambda k: f'emp_{emp_id}_' in k)
            _logger.debug("Invalidated caches for employee %s: %d entries", emp_id, count)

    # =========================================================================
    # OPTIMIZED CRUD WITH SELECTIVE INVALIDATION
    # =========================================================================

    # Fields that affect kanban display
    _KANBAN_RELEVANT_FIELDS = {
        'name', 'job_title', 'work_email', 'work_phone', 'image_1920', 'image_128',
        'department_id', 'company_id', 'category_ids', 'parent_id', 'user_id',
        'hr_presence_state', 'active'
    }

    @api.model_create_multi
    def create(self, vals_list):
        """Override create with selective cache invalidation."""
        result = super().create(vals_list)
        # For new employees, only need to invalidate list caches
        _kanban_cache.invalidate_pattern(lambda k: k.startswith('list_'))
        return result

    def write(self, vals):
        """Override write with field-aware selective invalidation."""
        # Check if any kanban-relevant field is being updated
        relevant_changes = bool(set(vals.keys()) & self._KANBAN_RELEVANT_FIELDS)

        result = super().write(vals)

        if relevant_changes:
            self._invalidate_employee_caches()

        # Image change needs special handling
        if 'image_1920' in vals or 'image_128' in vals:
            for emp_id in self.ids:
                _image_cache.invalidate_pattern(lambda k: f'emp_{emp_id}_' in k)

        return result

    def unlink(self):
        """Override unlink with cache cleanup."""
        emp_ids = self.ids
        result = super().unlink()

        # Clean up caches for deleted employees
        for emp_id in emp_ids:
            _kanban_cache.invalidate_employee(emp_id)
            _image_cache.invalidate_pattern(lambda k: f'emp_{emp_id}_' in k)

        return result

    # =========================================================================
    # OPTIMIZED WEB_SEARCH_READ WITH CACHING
    # =========================================================================

    @api.model
    def web_search_read(self, domain, specification, offset=0, limit=None, order=None, count_limit=None):
        """Override web_search_read with intelligent caching."""
        context = self.env.context

        # Only cache for kanban optimization context
        if not context.get('kanban_view_optimization'):
            return super().web_search_read(domain, specification, offset, limit, order, count_limit)

        # Generate cache key
        cache_key = self._get_cache_key(
            'list',
            domain=hashlib.md5(str(domain).encode()).hexdigest()[:8],
            spec=hashlib.md5(str(specification).encode()).hexdigest()[:8],
            offset=offset,
            limit=limit,
            order=order or 'default',
            company=context.get('allowed_company_ids', [0])[0] if context.get('allowed_company_ids') else 0,
            lang=context.get('lang', 'en_US')
        )

        # Try cache
        cached = _kanban_cache.get(cache_key)
        if cached is not None:
            _logger.debug("Cache HIT for kanban list: %s", cache_key[:16])
            return cached

        # Execute query
        result = super().web_search_read(domain, specification, offset, limit, order, count_limit)

        # Cache result with 5 minute TTL
        _kanban_cache.set(cache_key, result, ttl=300)
        _logger.debug("Cache SET for kanban list: %s", cache_key[:16])

        return result

    # =========================================================================
    # IMAGE CACHING AND OPTIMIZATION
    # =========================================================================

    @api.model
    def get_employee_image(self, employee_id, size='128'):
        """
        Get employee image with multi-size caching.
        Images are cached by (employee_id, size) to avoid reprocessing.
        """
        valid_sizes = {'64': 64, '128': 128, '256': 256, '512': 512}
        size_px = valid_sizes.get(str(size), 128)

        # Check image cache first
        cache_key = f'emp_{employee_id}_img_{size_px}'
        cached = _image_cache.get(cache_key)
        if cached is not None:
            _logger.debug("Image cache HIT: employee %s, size %s", employee_id, size_px)
            return cached

        try:
            employee = self.browse(employee_id)
            employee.check_access_rights('read')
            employee.check_access_rule('read')

            if not employee.exists():
                result = {'success': False, 'error': 'Employee not found', 'placeholder': True}
                return result

            # Check has_image first (stored field, no binary load)
            if not employee.has_image:
                result = {
                    'success': True,
                    'has_image': False,
                    'placeholder': True,
                    'employee_id': employee_id,
                    'name': employee.name,
                }
                _image_cache.set(cache_key, result, ttl=3600)
                return result

            # Load and process image
            # Use image_128 for small sizes, image_1920 for larger
            image_field = 'image_128' if size_px <= 128 else 'image_1920'
            image_data = employee[image_field]

            if not image_data:
                result = {
                    'success': True,
                    'has_image': False,
                    'placeholder': True,
                    'employee_id': employee_id,
                }
                _image_cache.set(cache_key, result, ttl=3600)
                return result

            # Process image only if needed
            processed = image_process(image_data, size=(size_px, size_px))

            result = {
                'success': True,
                'has_image': True,
                'image_data': processed.decode('utf-8') if isinstance(processed, bytes) else processed,
                'employee_id': employee_id,
                'size': size_px,
            }

            # Cache processed image for 1 hour
            _image_cache.set(cache_key, result, ttl=3600)
            _logger.debug("Image cache SET: employee %s, size %s", employee_id, size_px)

            return result

        except AccessError:
            _logger.warning("Access denied for employee image: %s", employee_id)
            return {'success': False, 'error': 'Access denied', 'placeholder': True}
        except Exception as e:
            _logger.exception("Error fetching employee image %s", employee_id)
            return {'success': False, 'error': str(e), 'placeholder': True}

    # =========================================================================
    # OPTIMIZED DETAILS AND ACTIVITIES ENDPOINTS
    # =========================================================================

    @api.model
    def get_employee_details(self, employee_id):
        """Get employee details with caching."""
        cache_key = f'emp_{employee_id}_details'
        cached = _kanban_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            employee = self.browse(employee_id)
            employee.check_access_rights('read')
            employee.check_access_rule('read')

            if not employee.exists():
                return {'success': False, 'error': 'Employee not found'}

            # Use read() for optimized field access
            data = employee.read([
                'work_email', 'work_phone', 'mobile_phone', 'job_title',
                'department_id', 'parent_id', 'user_id', 'company_id'
            ])[0]

            # Get categories efficiently
            categories = []
            if employee.category_ids:
                categories = employee.category_ids.read(['name', 'color'])

            result = {
                'success': True,
                'employee_id': employee_id,
                'work_email': data.get('work_email') or '',
                'work_phone': data.get('work_phone') or '',
                'mobile_phone': data.get('mobile_phone') or '',
                'job_title': data.get('job_title') or '',
                'department_id': data['department_id'][0] if data.get('department_id') else False,
                'department_name': data['department_id'][1] if data.get('department_id') else '',
                'manager_id': data['parent_id'][0] if data.get('parent_id') else False,
                'manager_name': data['parent_id'][1] if data.get('parent_id') else '',
                'user_id': data['user_id'][0] if data.get('user_id') else False,
                'user_name': data['user_id'][1] if data.get('user_id') else '',
                'company_name': data['company_id'][1] if data.get('company_id') else '',
                'category_ids': categories,
            }

            # Cache for 2 minutes
            _kanban_cache.set(cache_key, result, ttl=120)
            return result

        except AccessError:
            return {'success': False, 'error': 'Access denied'}
        except Exception as e:
            _logger.exception("Error fetching employee details %s", employee_id)
            return {'success': False, 'error': str(e)}

    @api.model
    def get_employee_activities(self, employee_id):
        """Get activities with SQL optimization and caching."""
        cache_key = f'emp_{employee_id}_activities'
        cached = _activities_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            employee = self.browse(employee_id)
            employee.check_access_rights('read')
            employee.check_access_rule('read')

            if not employee.exists():
                return {'success': False, 'error': 'Employee not found'}

            today = fields.Date.context_today(self)

            # Optimized SQL query with all needed data
            self.env.cr.execute("""
                SELECT
                    ma.id,
                    mat.name as activity_type,
                    mat.icon,
                    ma.summary,
                    ma.date_deadline,
                    ru.name as user_name,
                    ma.user_id,
                    CASE
                        WHEN ma.date_deadline < %s THEN 'overdue'
                        WHEN ma.date_deadline = %s THEN 'today'
                        ELSE 'planned'
                    END as state
                FROM mail_activity ma
                LEFT JOIN mail_activity_type mat ON mat.id = ma.activity_type_id
                LEFT JOIN res_users ru ON ru.id = ma.user_id
                WHERE ma.res_model = 'hr.employee'
                  AND ma.res_id = %s
                ORDER BY
                    CASE
                        WHEN ma.date_deadline < %s THEN 0
                        WHEN ma.date_deadline = %s THEN 1
                        ELSE 2
                    END,
                    ma.date_deadline
            """, (today, today, employee_id, today, today))

            activities = []
            for row in self.env.cr.fetchall():
                activities.append({
                    'id': row[0],
                    'activity_type': row[1] or '',
                    'icon': row[2] or 'fa-tasks',
                    'summary': row[3] or '',
                    'date_deadline': str(row[4]) if row[4] else '',
                    'user_name': row[5] or '',
                    'user_id': row[6],
                    'state': row[7],
                })

            result = {
                'success': True,
                'employee_id': employee_id,
                'employee_name': employee.name,
                'activities': activities,
                'count': len(activities),
            }

            # Cache for 2 minutes (activities change frequently)
            _activities_cache.set(cache_key, result, ttl=120)
            return result

        except AccessError:
            return {'success': False, 'error': 'Access denied'}
        except Exception as e:
            _logger.exception("Error fetching employee activities %s", employee_id)
            return {'success': False, 'error': str(e)}

    # =========================================================================
    # OPTIMIZED BATCH DATA ENDPOINT WITH PAGINATION
    # =========================================================================

    @api.model
    def get_kanban_batch_data(self, employee_ids, fields_list=None, page=1, page_size=50):
        """
        Batch fetch data with pagination support.

        :param employee_ids: List of employee IDs (or None for paginated fetch)
        :param fields_list: Fields to fetch
        :param page: Page number (1-indexed)
        :param page_size: Items per page
        :return: dict with data and pagination info
        """
        if not employee_ids and page:
            # Paginated fetch mode
            offset = (page - 1) * page_size
            employee_ids = self.search([], limit=page_size, offset=offset).ids
            total_count = self.search_count([])
        else:
            total_count = len(employee_ids) if employee_ids else 0

        if not employee_ids:
            return {
                'success': True,
                'data': {},
                'pagination': {'page': page, 'page_size': page_size, 'total': 0}
            }

        # Default essential fields only
        default_fields = [
            'id', 'name', 'job_title', 'has_image',
            'hr_presence_state', 'hr_icon_display', 'show_hr_icon_display'
        ]
        fields_to_read = fields_list or default_fields

        try:
            # Use read() for optimized batch field access
            employees = self.browse(employee_ids)
            employees.check_access_rights('read')
            employees.check_access_rule('read')

            # Single read() call for all employees
            records_data = employees.read(fields_to_read)

            result = {}
            for data in records_data:
                emp_id = data['id']
                result[emp_id] = {}
                for field in fields_to_read:
                    value = data.get(field)
                    # Handle Many2one fields
                    if isinstance(value, tuple) and len(value) == 2:
                        result[emp_id][field] = {'id': value[0], 'name': value[1]}
                    else:
                        result[emp_id][field] = value

            return {
                'success': True,
                'data': result,
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total': total_count,
                    'total_pages': (total_count + page_size - 1) // page_size
                }
            }

        except AccessError:
            return {'success': False, 'error': 'Access denied'}
        except Exception as e:
            _logger.exception("Error in batch employee data")
            return {'success': False, 'error': str(e)}

    # =========================================================================
    # CACHE MANAGEMENT API
    # =========================================================================

    @api.model
    def get_cache_stats(self):
        """Get cache statistics for monitoring."""
        return {
            'kanban_cache': _kanban_cache.get_stats(),
            'image_cache': _image_cache.get_stats(),
            'activities_cache': _activities_cache.get_stats(),
        }

    @api.model
    def clear_all_caches(self):
        """Clear all caches (admin action)."""
        counts = {
            'kanban': _kanban_cache.invalidate_all(),
            'image': _image_cache.clear(),
            'activities': _activities_cache.clear(),
        }
        _logger.info("All caches cleared: %s", counts)
        return counts

    @api.model
    def warmup_cache(self, limit=100):
        """
        Pre-populate cache with most accessed employees.
        Call this after server restart or cache clear.
        """
        employees = self.search([], limit=limit, order='write_date desc')

        # Trigger computation of optimized fields
        _ = employees.mapped('has_image')
        _ = employees.mapped('activities_summary')

        _logger.info("Cache warmup complete: %d employees", len(employees))
        return len(employees)


# =============================================================================
# MAIL ACTIVITY HOOK FOR CACHE INVALIDATION
# =============================================================================

class MailActivity(models.Model):
    _inherit = 'mail.activity'

    @api.model_create_multi
    def create(self, vals_list):
        result = super().create(vals_list)
        self._invalidate_employee_activity_cache(result)
        return result

    def write(self, vals):
        result = super().write(vals)
        if 'date_deadline' in vals or 'activity_type_id' in vals:
            self._invalidate_employee_activity_cache(self)
        return result

    def unlink(self):
        activities_to_invalidate = self.filtered(lambda a: a.res_model == 'hr.employee')
        emp_ids = activities_to_invalidate.mapped('res_id')
        result = super().unlink()
        for emp_id in emp_ids:
            _activities_cache.invalidate_pattern(lambda k: f'emp_{emp_id}_' in k)
        return result

    def _invalidate_employee_activity_cache(self, activities):
        """Invalidate activity cache for affected employees."""
        for activity in activities:
            if activity.res_model == 'hr.employee':
                _activities_cache.invalidate_pattern(
                    lambda k, eid=activity.res_id: f'emp_{eid}_' in k
                )
