import functools
import json
import sys
import time
import hashlib
import pickle
from threading import Lock
import logging

from odoo.http import Response, request

_logger = logging.getLogger(__name__)

class APICache:
    def __init__(self, timeout=3600, max_size=10000):
        self.timeout = timeout
        self.max_size = max_size
        self._cache_storage = {}  # Renombrado para evitar conflicto con el método cache
        self.lock = Lock()

    def _generate_key(self, *args, **kwargs):
        try:
            # Obtener el cuerpo de la solicitud si existe
            body_data = {}
            try:
                # Intentar obtener el cuerpo como JSON
                if request and hasattr(request, 'httprequest'):
                    body_data = request.httprequest.data.decode('utf-8') or {}
            except (ValueError, TypeError):
                # Si el cuerpo no es JSON válido, usar como string
                body_data = request.httprequest.data.decode('utf-8') if request.httprequest.data else ''
            # Combinar args[1:] (ignorando self), kwargs y body_data
            key_data = (args[1:] if len(args) > 1 else (), tuple(sorted(kwargs.items())), body_data)
            key_str = pickle.dumps(key_data)
            return hashlib.md5(key_str).hexdigest()
        except Exception as e:
            _logger.error(f"Error generando clave de caché: {str(e)}")
            # Fallback: usar strings para args, kwargs y body
            body_str = request.httprequest.data.decode('utf-8') if request and request.httprequest.data else ''
            return hashlib.md5((str(args[1:]) + str(kwargs) + body_str).encode('utf-8')).hexdigest()


    def cache(self):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                key = self._generate_key(*args, **kwargs)
                with self.lock:
                    if key in self._cache_storage:
                        result, timestamp = self._cache_storage[key]
                        if time.time() - timestamp < self.timeout:
                            _logger.debug(f"Cache hit para {func.__name__} con key={key}")
                            return result
                    try:
                        result = func(*args, **kwargs)
                        if len(self._cache_storage) >= self.max_size:
                            self._cleanup()
                        self._cache_storage[key] = (result, time.time())
                        _logger.debug(f"Nuevo resultado cacheado para {func.__name__} con key={key}")
                        return result
                    except Exception as e:
                        _logger.error(f"Error en {func.__name__}: {str(e)}")
                        raise

            wrapper.cache_clear = self.clear
            wrapper.cache_info = self.info
            return wrapper
        return decorator

    def _cleanup(self):
        with self.lock:
            current_time = time.time()
            expired_keys = [
                key for key, (_, timestamp) in self._cache_storage.items()
                if current_time - timestamp >= self.timeout
            ]
            for key in expired_keys:
                del self._cache_storage[key]
            if len(self._cache_storage) > self.max_size:
                sorted_items = sorted(self._cache_storage.items(), key=lambda x: x[1][1])
                for key, _ in sorted_items[self.max_size//2:]:
                    del self._cache_storage[key]

    def clear(self):
        with self.lock:
            self._cache_storage.clear()

    # def info(self):
    #     with self.lock:
    #         return {
    #             'size': len(self._cache_storage),
    #             'max_size': self.max_size,
    #             'timeout': self.timeout
    #         }
    def info(self):
        with self.lock:
            cache_details = []
            for key, (result, timestamp) in self._cache_storage.items():
                # Convertir el resultado a algo legible (si es HttpResponse, extraer el contenido)
                content = result.get_data().decode('utf-8') if isinstance(result, Response) else str(result)
                try:
                    # Intentar parsear el contenido como JSON para hacerlo más legible
                    content = json.loads(content)
                except json.JSONDecodeError:
                    pass  # Si no es JSON válido, dejar como string
                entry_size = (
                        sys.getsizeof(key) +
                        sys.getsizeof(result) +
                        sys.getsizeof(timestamp) +
                        sys.getsizeof((result, timestamp))
                )
                cache_details.append({
                    'key': key,
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp)),
                    'age_seconds': int(time.time() - timestamp),
                    'size_bytes': entry_size,
                    'size_mb': entry_size / (1024 * 1024),
                    'content': content
                })
            total_size = sum(
                sys.getsizeof(k) + sys.getsizeof(v[0]) + sys.getsizeof(v[1]) + sys.getsizeof(v)
                for k, v in self._cache_storage.items()
            )
            return {
                'size': len(self._cache_storage),
                'max_size': self.max_size,
                'timeout': self.timeout,
                'total_size_bytes': total_size,
                'total_size_mb': total_size / (1024 * 1024),
                'entries': cache_details
            }