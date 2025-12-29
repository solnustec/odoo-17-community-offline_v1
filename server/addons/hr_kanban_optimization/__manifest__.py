# -*- coding: utf-8 -*-
{
    'name': 'HR Employee Kanban Optimization',
    'version': '17.0.2.0.0',
    'category': 'Human Resources/Employees',
    'summary': 'Enterprise-grade performance optimization for HR Employee Kanban view',
    'description': """
HR Employee Kanban Optimization Module - Advanced Performance Edition
=====================================================================

This module provides enterprise-grade performance improvements for the HR Employee
Kanban view, designed to handle 200+ employee records efficiently.

Key Features
------------

**Multi-Tier Caching System**
* Thread-safe LRU (Least Recently Used) cache with configurable TTL
* Optional Redis support for distributed/persistent caching
* Automatic cache warmup and maintenance
* Selective invalidation by employee or field type

**Optimized Data Loading**
* SQL-optimized computed fields (avoid N+1 queries)
* Lazy loading images with IntersectionObserver
* Deferred loading of secondary fields on hover
* Batch data fetching with pagination support

**Image Optimization**
* Multi-size image caching (64, 128, 256, 512px)
* HTTP endpoint with browser caching headers
* Placeholder support for employees without images

**Activity Summary**
* Pre-computed JSON field for lightweight activity info
* SQL aggregation for efficient activity counting
* Cron job for periodic summary updates

**Monitoring & Management**
* Cache statistics API
* Manual cache clear/warmup endpoints
* Detailed logging for debugging

Technical Requirements
----------------------
* Odoo 17.0 Community/Enterprise
* PostgreSQL 12+
* Optional: Redis 6+ for distributed caching

Configuration
-------------
To enable Redis caching, modify the cache initialization in models/hr_employee.py:
    _kanban_cache = HybridCache(use_redis=True, host='localhost', port=6379)

API Endpoints
-------------
* GET  /hr_kanban_optimization/employee/<id>/image?size=128
* POST /hr_kanban_optimization/employee/<id>/details
* POST /hr_kanban_optimization/employee/<id>/activities
* POST /hr_kanban_optimization/batch
* POST /hr_kanban_optimization/cache/stats (HR Manager only)
* POST /hr_kanban_optimization/cache/clear (HR Manager only)
* POST /hr_kanban_optimization/cache/warmup (HR Manager only)
    """,
    'author': 'Odoo Community',
    'website': 'https://github.com/odoo/odoo',
    'license': 'LGPL-3',
    'depends': [
        'hr',
        'mail',
    ],
    'data': [
        'data/cron_data.xml',
        'views/hr_employee_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hr_kanban_optimization/static/src/scss/employee_kanban.scss',
            'hr_kanban_optimization/static/src/js/lazy_image.js',
            'hr_kanban_optimization/static/src/js/employee_kanban_controller.js',
            'hr_kanban_optimization/static/src/xml/employee_kanban_templates.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}
