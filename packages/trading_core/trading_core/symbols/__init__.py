import re

class SymbolMapper:
    """Provides logic for translating broker-specific symbols to/from neutral format.
    
    Neutral Format: {UNDERLYING}{EXPIRY_YYMMDD}{STRIKE}{TYPE}
    Example: NIFTY26MAR24500CE
    """
    
    # Simple regex for Fyers format: NSE:NIFTY26MAR24500CE or NSE:NIFTY50-INDEX
    FYERS_REGEX = r"(?:NSE:|MCX:|BSE:)([A-Z0-9]+)(?:(\d{2}[A-Z]{1,3}\d{0,2})(\d+)(CE|PE))?"
    
    # Upstox doesn't follow a simple pattern (uses numeric / pipe keys).
    # We will assume that the metadata for Upstox (instrument keys) is mapped
    # at ingestion time or stored in a persistent lookup table.
    
    @staticmethod
    def fyers_to_neutral(symbol: str) -> str:
        """Translates Fyers symbol to neutral format.
        Strips prefix and standardizes the expiry part if possible.
        """
        match = re.match(SymbolMapper.FYERS_REGEX, symbol)
        if not match:
            return symbol.split(":")[1] if ":" in symbol else symbol
        
        underlying = match.group(1)
        expiry = match.group(2)
        strike = match.group(3)
        option_type = match.group(4)
        
        if not expiry:
            return underlying
            
        return f"{underlying}{expiry}{strike}{option_type}"
    
    @staticmethod
    def neutral_to_fyers(neutral: str) -> str:
        """Prepends the exchange prefix for Fyers."""
        return f"NSE:{neutral}"
    
    @staticmethod
    def parse_neutral(neutral: str) -> dict:
        """Extracts components from a neutral symbol."""
        # Generic match for {UNDERLYING}{EXPIRY}{STRIKE}{TYPE}
        match = re.match(r"([A-Z]+)(\d{2}[A-Z]{3}\d{0,2})(\d+)(CE|PE)", neutral)
        if not match:
            return {"underlying": neutral, "is_option": False}
            
        return {
            "underlying": match.group(1),
            "expiry": match.group(2),
            "strike": float(match.group(3)),
            "type": match.group(4),
            "is_option": True
        }
