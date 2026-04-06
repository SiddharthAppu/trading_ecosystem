from py_vollib.black_scholes import black_scholes as bs
from py_vollib.black_scholes.greeks.numerical import delta, gamma, theta, vega, rho
from py_vollib.black_scholes.implied_volatility import implied_volatility as iv
import datetime

# Risk-free rate (7% for India)
RISK_FREE_RATE = 0.07

class OptionGreeks:
    """Calculates Option Greeks using py_vollib."""
    
    @staticmethod
    def calculate_iv(price: float, S: float, K: float, T_days: float, r: float, option_type: str) -> float:
        """Calculates Implied Volatility."""
        if T_days <= 0 or S <= 0 or K <= 0 or price <= 0:
            return 0.15 # Fallback
        
        T_years = T_days / 365.0
        flag = option_type.lower()[0] # 'c' or 'p'
        
        try:
            return iv(price, S, K, T_years, r, flag)
        except Exception:
            return 0.15 # Fallback on error
            
    @staticmethod
    def calculate_delta(S: float, K: float, T_days: float, r: float, sigma: float, option_type: str) -> float:
        if T_days <= 0 or S <= 0 or K <= 0 or sigma <= 0:
            return 0.0
        
        T_years = T_days / 365.0
        flag = option_type.lower()[0]
        
        try:
            return delta(flag, S, K, T_years, r, sigma)
        except Exception:
            return 0.0

    @staticmethod
    def calculate_gamma(S: float, K: float, T_days: float, r: float, sigma: float, option_type: str) -> float:
        if T_days <= 0 or S <= 0 or K <= 0 or sigma <= 0:
            return 0.0
        
        T_years = T_days / 365.0
        flag = option_type.lower()[0]
        
        try:
            return gamma(flag, S, K, T_years, r, sigma)
        except Exception:
            return 0.0

    @staticmethod
    def calculate_theta(S: float, K: float, T_days: float, r: float, sigma: float, option_type: str) -> float:
        if T_days <= 0 or S <= 0 or K <= 0 or sigma <= 0:
            return 0.0
        
        T_years = T_days / 365.0
        flag = option_type.lower()[0]
        
        try:
            return theta(flag, S, K, T_years, r, sigma)
        except Exception:
            return 0.0

    @staticmethod
    def calculate_vega(S: float, K: float, T_days: float, r: float, sigma: float, option_type: str) -> float:
        if T_days <= 0 or S <= 0 or K <= 0 or sigma <= 0:
            return 0.0
        
        T_years = T_days / 365.0
        flag = option_type.lower()[0]
        
        try:
            return vega(flag, S, K, T_years, r, sigma)
        except Exception:
            return 0.0
