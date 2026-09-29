from editor import detect_editor, get_code, set_code, normalize_code
from logger import log_info, log_error

def type_code(page, code: str, max_retries: int = 3) -> bool:
    """Rewritten code_typer using editor.py's robust multi-engine injection and verification."""
    log_info(f"[CODE TYPER] Injecting {len(code.splitlines())} lines of code...")
    return set_code(page, code, max_retries=max_retries)

def read_code(page) -> str:
    """Reads back active editor code content."""
    return get_code(page)

__all__ = ["type_code", "read_code", "detect_editor", "set_code", "get_code", "normalize_code"]
