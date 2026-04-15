try:
    from py_vollib.black_scholes import black_scholes as bs
    from py_vollib.black_scholes.greeks.numerical import delta, gamma, theta, vega, rho
    from py_vollib.black_scholes.implied_volatility import implied_volatility as iv
except ImportError:
    bs = None
    delta = None
    gamma = None
    theta = None
    vega = None
    rho = None
    iv = None
import datetime


def _to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def calc_sma(values: list[float | None], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    for idx in range(len(values)):
        if idx < period - 1:
            continue
        window = values[idx - period + 1 : idx + 1]
        if any(v is None for v in window):
            continue
        output[idx] = sum(window) / period
    return output


def calc_ema(values: list[float | None], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) < period:
        return output

    alpha = 2 / (period + 1)
    seed_start = None

    for idx in range(0, len(values) - period + 1):
        window = values[idx : idx + period]
        if all(v is not None for v in window):
            seed_start = idx
            break

    if seed_start is None:
        return output

    seed_window = values[seed_start : seed_start + period]
    ema_prev = sum(seed_window) / period
    seed_idx = seed_start + period - 1
    output[seed_idx] = ema_prev

    for idx in range(seed_idx + 1, len(values)):
        value = values[idx]
        if value is None:
            output[idx] = None
            continue
        ema_prev = (value * alpha) + (ema_prev * (1 - alpha))
        output[idx] = ema_prev

    return output


def calc_rsi(values: list[float | None], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return output

    deltas: list[float | None] = [None]
    for idx in range(1, len(values)):
        prev_value = values[idx - 1]
        curr_value = values[idx]
        if prev_value is None or curr_value is None:
            deltas.append(None)
        else:
            deltas.append(curr_value - prev_value)

    seed = deltas[1 : period + 1]
    if any(delta is None for delta in seed):
        return output

    gains = [max(delta, 0) for delta in seed if delta is not None]
    losses = [abs(min(delta, 0)) for delta in seed if delta is not None]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        output[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        output[period] = 100 - (100 / (1 + rs))

    for idx in range(period + 1, len(values)):
        delta_value = deltas[idx]
        if delta_value is None:
            output[idx] = None
            continue

        gain = max(delta_value, 0)
        loss = abs(min(delta_value, 0))
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

        if avg_loss == 0:
            output[idx] = 100.0
        else:
            rs = avg_gain / avg_loss
            output[idx] = 100 - (100 / (1 + rs))

    return output


def compute_indicator_rows(rows: list[dict], indicators: list[str]) -> None:
    if not rows or not indicators:
        return

    closes = [_to_float(row.get("close")) for row in rows]
    ema20 = calc_ema(closes, 20) if "ema_20" in indicators else None
    sma20 = calc_sma(closes, 20) if "sma_20" in indicators else None
    rsi14 = calc_rsi(closes, 14) if "rsi_14" in indicators else None

    macd_line = None
    macd_signal = None
    macd_histogram = None
    if "macd" in indicators:
        ema12 = calc_ema(closes, 12)
        ema26 = calc_ema(closes, 26)
        macd_line = []
        for idx in range(len(closes)):
            if ema12[idx] is None or ema26[idx] is None:
                macd_line.append(None)
            else:
                macd_line.append(ema12[idx] - ema26[idx])
        macd_signal = calc_ema(macd_line, 9)
        macd_histogram = []
        for idx in range(len(closes)):
            if macd_line[idx] is None or macd_signal[idx] is None:
                macd_histogram.append(None)
            else:
                macd_histogram.append(macd_line[idx] - macd_signal[idx])

    for idx, row in enumerate(rows):
        if ema20 is not None:
            row["ema_20"] = ema20[idx]
        if sma20 is not None:
            row["sma_20"] = sma20[idx]
        if rsi14 is not None:
            row["rsi_14"] = rsi14[idx]
        if macd_line is not None:
            row["macd_line"] = macd_line[idx]
            row["macd_signal"] = macd_signal[idx]
            row["macd_histogram"] = macd_histogram[idx]

# Risk-free rate (7% for India)
RISK_FREE_RATE = 0.07

class OptionGreeks:
    """Calculates Option Greeks using py_vollib."""
    
    @staticmethod
    def calculate_iv(price: float, S: float, K: float, T_days: float, r: float, option_type: str) -> float:
        """Calculates Implied Volatility."""
        if iv is None or T_days <= 0 or S <= 0 or K <= 0 or price <= 0:
            return 0.15 # Fallback
        
        T_years = T_days / 365.0
        flag = option_type.lower()[0] # 'c' or 'p'
        
        try:
            return iv(price, S, K, T_years, r, flag)
        except Exception:
            return 0.15 # Fallback on error
            
    @staticmethod
    def calculate_delta(S: float, K: float, T_days: float, r: float, sigma: float, option_type: str) -> float:
        if delta is None or T_days <= 0 or S <= 0 or K <= 0 or sigma <= 0:
            return 0.0
        
        T_years = T_days / 365.0
        flag = option_type.lower()[0]
        
        try:
            return delta(flag, S, K, T_years, r, sigma)
        except Exception:
            return 0.0

    @staticmethod
    def calculate_gamma(S: float, K: float, T_days: float, r: float, sigma: float, option_type: str) -> float:
        if gamma is None or T_days <= 0 or S <= 0 or K <= 0 or sigma <= 0:
            return 0.0
        
        T_years = T_days / 365.0
        flag = option_type.lower()[0]
        
        try:
            return gamma(flag, S, K, T_years, r, sigma)
        except Exception:
            return 0.0

    @staticmethod
    def calculate_theta(S: float, K: float, T_days: float, r: float, sigma: float, option_type: str) -> float:
        if theta is None or T_days <= 0 or S <= 0 or K <= 0 or sigma <= 0:
            return 0.0
        
        T_years = T_days / 365.0
        flag = option_type.lower()[0]
        
        try:
            return theta(flag, S, K, T_years, r, sigma)
        except Exception:
            return 0.0

    @staticmethod
    def calculate_vega(S: float, K: float, T_days: float, r: float, sigma: float, option_type: str) -> float:
        if vega is None or T_days <= 0 or S <= 0 or K <= 0 or sigma <= 0:
            return 0.0
        
        T_years = T_days / 365.0
        flag = option_type.lower()[0]
        
        try:
            return vega(flag, S, K, T_years, r, sigma)
        except Exception:
            return 0.0
