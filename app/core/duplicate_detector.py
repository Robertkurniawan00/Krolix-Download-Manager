import os
import hashlib
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from dataclasses import dataclass
from typing import Optional


@dataclass
class DuplicateResult:
    is_duplicate: bool
    match_type: str  # 'url_exact', 'url_normalized', 'filename', 'file_on_disk', 'hash', ''
    existing_task_id: Optional[str] = None
    existing_path: Optional[str] = None
    existing_filename: Optional[str] = None
    confidence: float = 1.0  # 0.0-1.0


class DuplicateDetector:
    @staticmethod
    def strip_tracking_params(url: str) -> str:
        parsed = urlparse(url)
        params = parse_qsl(parsed.query, keep_blank_values=True)
        tracking_prefixes = ('utm_', 'fbclid', 'gclid', 'ref', 'source', 'medium', 'campaign')
        
        filtered_params = []
        for k, v in params:
            k_lower = k.lower()
            is_tracking = any(k_lower.startswith(prefix) or k_lower == prefix for prefix in tracking_prefixes)
            if not is_tracking:
                filtered_params.append((k, v))
                
        new_query = urlencode(filtered_params)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

    @staticmethod
    def normalize_url(url: str) -> str:
        url = DuplicateDetector.strip_tracking_params(url)
        parsed = urlparse(url)
        
        # Normalize scheme to https
        scheme = 'https' if parsed.scheme in ('http', 'https') else parsed.scheme
        
        # Strip trailing slash from path
        path = parsed.path
        if path.endswith('/'):
            path = path[:-1]
            
        return urlunparse((scheme, parsed.netloc, path, parsed.params, parsed.query, parsed.fragment))

    @classmethod
    def check(cls, url: str, filename: str, save_path: str, db=None) -> DuplicateResult:
        def _get_val(item, key, default=None):
            if isinstance(item, dict):
                return item.get(key, default)
            return getattr(item, key, default)

        # 1. URL exact match
        tasks = db.get_tasks_by_url(url) if (db and hasattr(db, 'get_tasks_by_url')) else []
        if tasks:
            for task in tasks:
                st = str(_get_val(task, 'status', '')).lower()
                if st not in ('cancelled', 'canceled', 'error'):
                    return DuplicateResult(
                        is_duplicate=True,
                        match_type='url_exact',
                        existing_task_id=_get_val(task, 'id'),
                        existing_path=_get_val(task, 'save_path'),
                        existing_filename=_get_val(task, 'filename')
                    )
                    
        # 2. URL normalized match
        normalized_url = cls.normalize_url(url)
        if normalized_url != url:
            norm_tasks = db.get_tasks_by_url(normalized_url) if (db and hasattr(db, 'get_tasks_by_url')) else []
            if norm_tasks:
                for task in norm_tasks:
                    st = str(_get_val(task, 'status', '')).lower()
                    if st not in ('cancelled', 'canceled', 'error'):
                        return DuplicateResult(
                            is_duplicate=True,
                            match_type='url_normalized',
                            existing_task_id=_get_val(task, 'id'),
                            existing_path=_get_val(task, 'save_path'),
                            existing_filename=_get_val(task, 'filename')
                        )
        
        # 3. Filename match
        filename_tasks = db.get_tasks_by_filename(filename) if (db and hasattr(db, 'get_tasks_by_filename')) else []
        if filename_tasks:
            for task in filename_tasks:
                st = str(_get_val(task, 'status', '')).lower()
                if st not in ('cancelled', 'canceled', 'error'):
                    return DuplicateResult(
                        is_duplicate=True,
                        match_type='filename',
                        existing_task_id=_get_val(task, 'id'),
                        existing_path=_get_val(task, 'save_path'),
                        existing_filename=_get_val(task, 'filename'),
                        confidence=0.7
                    )
                    
        # 4. File on disk
        full_path = os.path.join(save_path, filename) if (save_path and filename) else ""
        if full_path and os.path.exists(full_path):
            # 5. Hash match
            try:
                file_size = os.path.getsize(full_path)
                if file_size > 1024 * 1024:  # > 1MB
                    try:
                        with open(full_path, 'rb') as f:
                            data = f.read(64 * 1024)
                            file_hash = hashlib.sha256(data).hexdigest()
                            
                        # Compare against any completed tasks where the first 64KB hash was stored
                        if db and hasattr(db, 'get_task_by_hash'):
                            hash_task = db.get_task_by_hash(file_hash)
                            if hash_task:
                                return DuplicateResult(
                                    is_duplicate=True,
                                    match_type='hash',
                                    existing_task_id=_get_val(hash_task, 'id'),
                                    existing_path=_get_val(hash_task, 'save_path'),
                                    existing_filename=_get_val(hash_task, 'filename')
                                )
                    except Exception:
                        pass
            except Exception:
                pass

            return DuplicateResult(
                is_duplicate=True,
                match_type='file_on_disk',
                existing_path=save_path,
                existing_filename=filename
            )
            
        return DuplicateResult(is_duplicate=False, match_type='')
