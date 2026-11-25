import ssl
import json
import threading
from typing import Set


class SSLManager:
    _instance = None
    _singleton_lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> 'SSLManager':
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = SSLManager()
            return cls._instance
    
    def __init__(self):
        self._bypassed_domains: Set[str] = set()
        self._loaded = False
        self._lock = threading.RLock()
    
    def _ensure_loaded(self):
        with self._lock:
            if self._loaded:
                return
            try:
                from app.core.database import Database
                db = Database.get_instance()
                val = db.get_setting('ssl_bypass_domains')
                if val:
                    domains = json.loads(val)
                    self._bypassed_domains = set(d.lower() for d in domains if isinstance(d, str))
            except Exception:
                pass
            self._loaded = True

    def _save(self):
        try:
            with self._lock:
                snapshot = list(self._bypassed_domains)
            from app.core.database import Database
            db = Database.get_instance()
            db.set_setting('ssl_bypass_domains', json.dumps(snapshot))
        except Exception:
            pass
    
    def get_ssl_context(self, host: str) -> ssl.SSLContext:
        if self.is_bypassed(host):
            return self.create_bypass_context()
        return self.create_verified_context()
    
    def add_bypass(self, domain: str) -> None:
        self._ensure_loaded()
        domain = domain.lower().strip()
        if not domain:
            return
        with self._lock:
            if domain not in self._bypassed_domains:
                self._bypassed_domains.add(domain)
                self._save()
    
    def remove_bypass(self, domain: str) -> None:
        self._ensure_loaded()
        domain = domain.lower().strip()
        with self._lock:
            if domain in self._bypassed_domains:
                self._bypassed_domains.remove(domain)
                self._save()
    
    def list_bypassed(self) -> list:
        self._ensure_loaded()
        with self._lock:
            return list(self._bypassed_domains)
    
    def is_bypassed(self, host: str) -> bool:
        self._ensure_loaded()
        host = (host or "").lower().strip()
        with self._lock:
            for domain in list(self._bypassed_domains):
                if host == domain or host.endswith('.' + domain):
                    return True
        return False
    
    def create_verified_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        return ctx
    
    def create_bypass_context(self) -> ssl.SSLContext:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
