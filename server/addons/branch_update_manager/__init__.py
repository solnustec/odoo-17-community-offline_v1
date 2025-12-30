# -*- coding: utf-8 -*-

from . import models
from . import controllers
from . import wizards


def post_init_hook(env):
    """Initialize the module after installation."""
    # Create default configuration
    config = env['ir.config_parameter'].sudo()

    # Set default values if not exist
    if not config.get_param('branch_update.api_key'):
        import secrets
        config.set_param('branch_update.api_key', secrets.token_urlsafe(32))

    if not config.get_param('branch_update.check_interval'):
        config.set_param('branch_update.check_interval', '5')  # minutes

    if not config.get_param('branch_update.auto_apply'):
        config.set_param('branch_update.auto_apply', 'True')

    if not config.get_param('branch_update.backup_before_update'):
        config.set_param('branch_update.backup_before_update', 'True')


def uninstall_hook(env):
    """Clean up on uninstall."""
    # Remove scheduled actions
    env['ir.cron'].search([
        ('model_id.model', '=', 'branch.update.agent')
    ]).unlink()
