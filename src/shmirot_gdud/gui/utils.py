from bidi.algorithm import get_display

def bidi_text(text: str) -> str:
    """
    Uses python-bidi to correctly handle BiDi text rendering for Tkinter.
    This handles mixed English/Hebrew, numbers, parentheses, etc.
    """
    if not text:
        return text
    
    try:
        return get_display(text)
    except Exception:
        # Fallback if something goes wrong, though get_display is robust
        return text[::-1] if any("\u0590" <= c <= "\u05FF" for c in text) else text
