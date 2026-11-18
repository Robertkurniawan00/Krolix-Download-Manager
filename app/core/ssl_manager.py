import ssl
import json
from typing import Set


class SSLManager:
    _instance = None
    
    @classmethod
    def get_instance(cls) -> 'SSLManager':
        if cls._instance is None:
            cls._instance = SSLManager()
        return cls._instance
    
    def __init__(self):
        self._bypassed_domains: Set[str] = set()
        self._loaded = False
    
    def _ensure_loaded(self):
        if self._loaded:
            return
            
        try:
            # Lazy import to avoid circular dependencies
            from app.core.database import Database
            db = Database.get_instance()
            val = db.get_setting('ssl_bypass_domains')
            if val:
                domains = json.loads(val)
                self._bypassed_domains = set(domains)
        except Exception:
            pass
            
        self._loaded = True

    def _save(self):
        try:
            from app.core.database import Database
            db = Database.get_instance()
            db.set_setting('ssl_bypass_domains', json.dumps(list(self._bypassed_domains)))
        except Exception:
            pass
    
    def get_ssl_context(self, host: str) -> ssl.SSLContext:
        if self.is_bypassed(host):
            return self.create_bypass_context()
        return self.create_verified_context()
    
    def add_bypass(self, domain: str) -> None:
        self._ensure_loaded()
        domain = domain.lower()
        if domain not in self._bypassed_domains:
            self._bypassed_domains.add(domain)
            self._save()
    
    def remove_bypass(self, domain: str) -> None:
        self._ensure_loaded()
        domain = domain.lower()
        if domain in self._bypassed_domains:
            self._bypassed_domains.remove(domain)
            self._save()
    
    def list_bypassed(self) -> list:
        self._ensure_loaded()
        return list(self._bypassed_domains)
    
    def is_bypassed(self, host: str) -> bool:
        self._ensure_loaded()
        host = host.lower()
        for domain in self._bypassed_domains:
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
