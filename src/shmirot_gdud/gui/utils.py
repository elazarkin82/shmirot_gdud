def bidi_text(text: str) -> str:
    """
    Reverses the text if it contains Hebrew characters to simulate RTL rendering
    in an LTR environment.
    """
    if not text:
        return text
        
    # Check if text contains Hebrew
    has_hebrew = any("\u0590" <= c <= "\u05FF" for c in text)
    
    if has_hebrew:
        # Simple reversal. 
        # Note: This doesn't handle complex BiDi (mixed English/Hebrew) perfectly,
        # but works for predominantly Hebrew strings.
        return text[::-1]
    
    return text
