import psutil
import subprocess
import platform
from odoo import models, api
from odoo.exceptions import UserError


class ServerMonitor(models.Model):
    _name = 'server.monitor'
    _description = 'Monitor del Servidor'
    _order = 'id desc'


    @api.model
    def get_server_stats(self):
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            disk = psutil.disk_usage('/')
            cpu_freq = psutil.cpu_freq().current if psutil.cpu_freq() else 0

            load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else (0, 0, 0)
            load_avg_rounded = [round(x, 2) for x in load_avg]

            stats = {
                'hostname': platform.node(),
                'system': platform.system(),
                'release': platform.release(),
                'uptime': subprocess.check_output(['uptime', '-p']).decode().strip(),
                'cpu_percent': round(psutil.cpu_percent(interval=1), 1),
                'cpu_count': psutil.cpu_count(),
                'cpu_freq': round(cpu_freq, 0),
                'mem_total': round(mem.total / (1024 ** 3), 2),
                'mem_used': round(mem.used / (1024 ** 3), 2),
                'mem_percent': round(mem.percent, 1),
                'swap_total': round(swap.total / (1024 ** 3), 2),
                'swap_used': round(swap.used / (1024 ** 3), 2),
                'swap_percent': round(swap.percent, 1),
                'disk_total': round(disk.total / (1024 ** 3), 2),
                'disk_used': round(disk.used / (1024 ** 3), 2),
                'disk_percent': round(disk.percent, 1),
                'load_avg': load_avg_rounded,
                'top_processes': [],
                'connections': len(psutil.net_connections()),
            }

            # Primera llamada para inicializar cpu_percent
            for proc in psutil.process_iter(['pid']):
                try:
                    proc.cpu_percent()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Esperar un momento para obtener datos reales
            import time
            time.sleep(0.5)

            print(psutil.process_iter(['pid']))

            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'username']):
                try:
                    cpu_pct = proc.cpu_percent()
                    mem_info = proc.memory_info()
                    mem_pct = proc.memory_percent()

                    info = {
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'username': proc.info['username'],
                        'cpu_percent': round(cpu_pct, 1),
                        'memory_percent': round(mem_pct, 1),
                        'memory_mb': round(mem_info.rss / (1024 ** 2), 1)
                    }
                    processes.append(info)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            # Ordenar por CPU + memoria para mejor distribución
            processes = sorted(
                processes,
                key=lambda x: (x.get('cpu_percent', 0) + x.get('memory_percent', 0) / 10),
                reverse=True
            )[:15]

            stats['top_processes'] = processes

            return stats

        except Exception as e:
            raise UserError(f"Error al obtener métricas del servidor: {str(e)}")

