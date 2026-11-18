import urllib.parse
import urllib.request
import re
import threading
from typing import Optional, List
from .torrent_downloader import bdecode

class BTDIGSearcher:
    def search(self, query: str, limit: int = 20) -> List[dict]:
        encoded_query = urllib.parse.quote(query)
        url = f"https://btdig.com/search?q={encoded_query}&p=0&order=0"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept': 'text/html'
        }
        
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8.0) as response:
                html = response.read().decode('utf-8', errors='ignore')
                
            results = []
            
            # For a more robust approach without bs4, we can split by torrent item container
            items = html.split('torrent_name')[1:]  # skip the first chunk before any result
            
            for item in items[:limit]:
                # Extract magnet and hash
                magnet_match = re.search(r'href="(magnet:\?xt=urn:btih:([a-zA-Z0-9]+)[^"]*)"', item)
                if not magnet_match:
                    continue
                    
                magnet = magnet_match.group(1).replace('&amp;', '&')
                info_hash = magnet_match.group(2).upper()
                
                # Extract name (remove HTML tags)
                name_match = re.search(r'<a[^>]*>(.*?)</a>', item, re.DOTALL | re.IGNORECASE)
                name = ""
                if name_match:
                    name = re.sub(r'<[^>]+>', '', name_match.group(1)).strip()
                if not name:
                    # fallback to dn from magnet
                    dn_match = re.search(r'&dn=([^&]+)', magnet)
                    if dn_match:
                        name = urllib.parse.unquote(dn_match.group(1).replace('+', ' '))
                
                # Extract size
                size_match = re.search(r'class="torrent_size"[^>]*>(.*?)</span>', item, re.IGNORECASE)
                size_str = size_match.group(1).strip() if size_match else "Unknown"
                
                # Extract seeders
                seeder_match = re.search(r'class="torrent_seed"[^>]*>(.*?)</span>', item, re.IGNORECASE)
                if not seeder_match:
                     seeder_match = re.search(r'class="torrent_files"[^>]*>.*?(\d+).*?</span>', item, re.IGNORECASE)
                seeders_str = seeder_match.group(1).strip() if seeder_match else "0"
                try:
                    seeders = int(re.sub(r'\D', '', seeders_str)) if seeders_str else 0
                except ValueError:
                    seeders = 0
                    
                results.append({
                    'name': name,
                    'info_hash': info_hash,
                    'magnet': magnet,
                    'size_str': size_str,
                    'seeders': seeders,
                    'source': 'btdig'
                })
                
            return results
        except Exception:
            return []

class MagnetResolver:
    def resolve_metadata(self, magnet_or_hash: str, timeout_s: float = 10.0) -> Optional[dict]:
        # Extract info_hash
        info_hash = ""
        if magnet_or_hash.startswith("magnet:"):
            match = re.search(r'urn:btih:([a-zA-Z0-9]{40})', magnet_or_hash, re.IGNORECASE)
            if match:
                info_hash = match.group(1).upper()
        elif re.match(r'^[a-fA-F0-9]{40}$', magnet_or_hash):
            info_hash = magnet_or_hash.upper()
            
        if not info_hash:
            return None
            
        apis = [
            f"https://itorrents.org/torrent/{info_hash}.torrent",
            f"https://torrent.ubuntu.com/simple/{info_hash}.torrent"
        ]
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        }
        
        for api_url in apis:
            try:
                req = urllib.request.Request(api_url, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout_s) as response:
                    torrent_data = response.read()
                    
                # Decode bencode
                decoded = bdecode(torrent_data)
                
                if not decoded or b'info' not in decoded:
                    continue
                    
                info = decoded[b'info']
                name = info.get(b'name', b'').decode('utf-8', errors='ignore')
                
                files = []
                total_size = 0
                
                if b'files' in info:
                    # Multi-file torrent
                    for f in info[b'files']:
                        file_length = f.get(b'length', 0)
                        file_path = [p.decode('utf-8', errors='ignore') for p in f.get(b'path', [])]
                        file_name = '/'.join(file_path)
                        files.append({
                            'name': file_name,
                            'size': file_length
                        })
                        total_size += file_length
                else:
                    # Single file torrent
                    total_size = info.get(b'length', 0)
                    files.append({
                        'name': name,
                        'size': total_size
                    })
                    
                return {
                    'name': name,
                    'info_hash': info_hash,
                    'total_size': total_size,
                    'file_count': len(files),
                    'files': files
                }
                
            except Exception:
                continue
                
        return None

class TorrentSearchEngine:
    def search(self, query: str, limit: int = 20, timeout_s: float = 10.0) -> List[dict]:
        searcher = BTDIGSearcher()
        results = []
        
        # Run BTDIGSearcher in a thread with timeout
        def worker():
            nonlocal results
            results = searcher.search(query, limit)
            
        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=timeout_s)
        
        # Sort by seeders desc
        results.sort(key=lambda x: x.get('seeders', 0), reverse=True)
        return results
    
    def resolve(self, magnet_or_hash: str, timeout_s: float = 10.0) -> Optional[dict]:
        return MagnetResolver().resolve_metadata(magnet_or_hash, timeout_s)
    
    def hash_to_magnet(self, info_hash: str, name: str = '') -> str:
        trackers = [
            'udp://tracker.opentrackr.org:1337/announce',
            'udp://open.tracker.cl:1337/announce',
            'udp://open.demonii.com:1337/announce',
        ]
        magnet = f'magnet:?xt=urn:btih:{info_hash}'
        if name:
            magnet += f'&dn={urllib.parse.quote(name)}'
        for t in trackers:
            magnet += f'&tr={urllib.parse.quote(t)}'
        return magnet
