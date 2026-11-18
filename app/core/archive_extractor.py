import os
import zipfile
import tarfile
import subprocess
from typing import Tuple

class ArchiveExtractor:
    @staticmethod
    def is_archive(file_path: str) -> bool:
        if not file_path:
            return False
        lower = str(file_path).lower()
        return lower.endswith(('.zip', '.tar', '.gz', '.tgz', '.bz2', '.rar', '.7z'))

    @staticmethod
    def _is_safe_path(base_dir: str, target_path: str) -> bool:
        base = os.path.abspath(base_dir)
        target = os.path.abspath(target_path)
        return target.startswith(base + os.sep) or target == base

    @staticmethod
    def extract(file_path: str, extract_to: str = None) -> Tuple[bool, str]:
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"

        if not extract_to:
            base_name = os.path.splitext(file_path)[0]
            extract_to = base_name

        os.makedirs(extract_to, exist_ok=True)
        lower = file_path.lower()

        try:
            if lower.endswith('.zip'):
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    # Guard against Zip Slip
                    for member in zip_ref.namelist():
                        dest = os.path.join(extract_to, member)
                        if not ArchiveExtractor._is_safe_path(extract_to, dest):
                            raise ValueError(f"Security Alert: Malicious path traversal detected in zip archive: {member}")
                    zip_ref.extractall(extract_to)
                return True, extract_to
            elif lower.endswith(('.tar', '.gz', '.tgz', '.bz2')):
                with tarfile.open(file_path, 'r:*') as tar_ref:
                    # Guard against Tar Slip
                    for member in tar_ref.getmembers():
                        dest = os.path.join(extract_to, member.name)
                        if not ArchiveExtractor._is_safe_path(extract_to, dest):
                            raise ValueError(f"Security Alert: Malicious path traversal detected in tar archive: {member.name}")
                    if hasattr(tarfile, 'data_filter'):
                        tar_ref.extractall(extract_to, filter='data')
                    else:
                        tar_ref.extractall(extract_to)
                return True, extract_to
            elif lower.endswith(('.rar', '.7z')):
                # Attempt to use WinRAR or 7z if installed on the system
                winrar_paths = [
                    r"C:\Program Files\WinRAR\WinRAR.exe",
                    r"C:\Program Files (x86)\WinRAR\WinRAR.exe",
                    r"C:\Program Files\7-Zip\7z.exe"
                ]
                extractor_exe = next((p for p in winrar_paths if os.path.exists(p)), None)
                if extractor_exe:
                    if "7z" in extractor_exe.lower():
                        cmd = [extractor_exe, "x", "-y", f"-o{extract_to}", file_path]
                    else:
                        cmd = [extractor_exe, "x", "-y", file_path, extract_to]
                    cflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    subprocess.run(cmd, check=True, creationflags=cflags)
                    return True, extract_to
                return False, "WinRAR or 7-Zip not found to extract this archive."
            return False, "Unsupported archive format"
        except Exception as e:
            return False, str(e)
