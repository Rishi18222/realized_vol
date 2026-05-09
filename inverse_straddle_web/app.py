"""Streamlit calculator: inverse 1-SD strikes + probability between two strikes.

Local:  cd inverse_straddle_web && pip install -r requirements.txt && streamlit run app.py

Deploy: Streamlit Community Cloud -> app path: inverse_straddle_web/app.py

Static (no Python): open index.html in a browser or upload to GitHub Pages / Netlify.
"""

import math

import streamlit as st


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def inverse_1sd_and_range_prob(
    atm_iv,
    futures_price,
    dte_days,
    strike_1,
    strike_2,
    model="lognormal",
    annual_days=252,
):
    if dte_days <= 0:
        raise ValueError("dte_days must be > 0")
    if futures_price <= 0:
        raise ValueError("futures_price must be > 0")

    iv = float(atm_iv)
    if iv > 1.0:
        iv = iv / 100.0
    if iv <= 0:
        raise ValueError("atm_iv must be > 0")

    T = float(dte_days) / float(annual_days)
    sigma_t = iv * math.sqrt(T)

    k_low = min(float(strike_1), float(strike_2))
    k_high = max(float(strike_1), float(strike_2))

    if model.lower() == "normal":
        std_price = futures_price * sigma_t
        lower_1sd = futures_price - std_price
        upper_1sd = futures_price + std_price
        z_low = (k_low - futures_price) / std_price
        z_high = (k_high - futures_price) / std_price
        prob_range = _norm_cdf(z_high) - _norm_cdf(z_low)
    elif model.lower() == "lognormal":
        lower_1sd = futures_price * math.exp(-sigma_t)
        upper_1sd = futures_price * math.exp(+sigma_t)
        if k_low <= 0:
            raise ValueError("Strikes must be > 0 for lognormal model")
        mu = -0.5 * sigma_t * sigma_t
        z_low = (math.log(k_low / futures_price) - mu) / sigma_t
        z_high = (math.log(k_high / futures_price) - mu) / sigma_t
        prob_range = _norm_cdf(z_high) - _norm_cdf(z_low)
    else:
        raise ValueError("model must be 'lognormal' or 'normal'")

    return {
        "model": model.lower(),
        "futures_price": float(futures_price),
        "atm_iv_decimal": iv,
        "dte_days": int(dte_days),
        "time_to_expiry_years": T,
        "sigma_sqrt_t": sigma_t,
        "one_sd_lower_strike": lower_1sd,
        "one_sd_upper_strike": upper_1sd,
        "range_low_strike": k_low,
        "range_high_strike": k_high,
        "probability_between_strikes": prob_range,
    }


st.set_page_config(page_title="Inverse straddle / 1-SD calculator", layout="centered")
st.title("Inverse 1-SD calculator + range probability")
st.markdown(
    "From **ATM IV**, **futures**, and **DTE**, computes implied ±1σ strikes (lognormal or normal model) "
    "and **P(lower strike ≤ ST ≤ upper strike)** at expiry."
)

col_a, col_b = st.columns(2)
with col_a:
    atm_iv = st.number_input("ATM IV (% or decimal)", value=14.0, format="%.4f")
    futures_price = st.number_input("Futures price", value=24200.0, format="%.2f")
    dte_days = st.number_input("Days to expiry", min_value=1, value=3, step=1)
with col_b:
    strike_1 = st.number_input("Strike 1", value=23100.0, format="%.2f")
    strike_2 = st.number_input("Strike 2", value=23500.0, format="%.2f")
    model = st.selectbox("Model", ["lognormal", "normal"], index=0)
    annual_days = st.selectbox("Annual days", [252, 365], index=0)

if st.button("Calculate", type="primary"):
    try:
        out = inverse_1sd_and_range_prob(
            atm_iv=atm_iv,
            futures_price=futures_price,
            dte_days=int(dte_days),
            strike_1=strike_1,
            strike_2=strike_2,
            model=model,
            annual_days=int(annual_days),
        )
        st.subheader("Results")
        c1, c2, c3 = st.columns(3)
        c1.metric("1σ lower strike", f"{out['one_sd_lower_strike']:.2f}")
        c2.metric("1σ upper strike", f"{out['one_sd_upper_strike']:.2f}")
        c3.metric(
            "P(range)",
            f"{100 * out['probability_between_strikes']:.2f}%",
            help=f"Between {out['range_low_strike']:.2f} and {out['range_high_strike']:.2f}",
        )
        st.caption(
            f"σ√T = {out['sigma_sqrt_t']:.6f} | T = {out['time_to_expiry_years']:.6f} years | "
            f"IV (decimal) = {out['atm_iv_decimal']:.6f} | model = {out['model']}"
        )
    except ValueError as e:
        st.error(str(e))
