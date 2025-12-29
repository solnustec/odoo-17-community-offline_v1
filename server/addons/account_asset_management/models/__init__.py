# -*- coding: utf-8 -*-

from . import account_account
from . import account_asset_group
from . import account_asset_profile
from . import account_asset_recompute_trigger
from . import account_move

# Primero definir asset_class (base de productos y activos)
from . import asset_class

# Luego extender productos
from . import product_template_inherit

# Ahora account.asset (usa asset_class y product.template)
from . import account_asset

# Extensiones de account.asset
from . import account_asset_extension

# Después account_move_line (usa asset_extension)
from . import account_move_line

# Ahora sí: líneas de activos (usa state de account.asset)
from . import account_asset_line

# Transferencias entre custodios
from . import asset_transfer

# Asignaciones iniciales de custodios
from . import asset_assignment

# Herencia de empleados (relacionar activos con custodios)
from . import hr_employee_inherit

# Transferencias Masivas
from . import asset_mass_transfer_wizard

# Asignaciones Masivas
from . import asset_mass_assignment

# Cálculo correcto de Suma de Depreciaciones
from . import account_asset_line_extend
