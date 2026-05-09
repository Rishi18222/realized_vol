"""Streamlit calculator: inverse 1-SD strikes + probability between two strikes.

Local:  cd inverse_straddle_web && pip install -r requirements.txt && streamlit run app.py

Deploy: Streamlit Community Cloud -> app path: inverse_straddle_web/app.py

Static (no Python): open index.html in a browser or upload to GitHub Pages / Netlify.
"""

import math
from datetime import date, timedelta

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


st.set_page_config(page_title="Range probability", layout="centered")

ATM_IV_GUIDE_URL = "https://www.nseindia.com/option-chain"


@st.dialog("How to find ATM IV", width="large")
def _atm_iv_guide_dialog() -> None:
    """Large, readable popup with steps and web link."""
    st.markdown(
        '<div style="font-size:1.35rem;line-height:1.75;">'
        '<p style="margin-top:0;"><strong>ATM IV</strong> is the implied volatility at the strike '
        "closest to <strong>spot or futures</strong>, for <strong>the expiry you&apos;re trading</strong>.</p>"
        "<ol style='margin-bottom:1rem;padding-left:1.35rem;'>"
        "<li>Open an <strong>option chain</strong> (broker or official NSE).</li>"
        "<li>Select your <strong>stock</strong> and <strong>expiry date</strong>.</li>"
        "<li>Read IV at <strong>ATM</strong>: the strike column nearest the current spot/futures.</li>"
        "</ol>"
        "<p>Use the official NSE page below when you prefer the exchange site.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.link_button(
        "Open NSE option chain in browser →",
        ATM_IV_GUIDE_URL,
        use_container_width=True,
        type="primary",
    )


st.title("Will the stock finish inside your price range?")

if st.button("How to find ATM IV — open guide", key="atm_iv_guide_btn", type="secondary"):
    _atm_iv_guide_dialog()

col_a, col_b = st.columns(2)
with col_a:
    st.caption("ATM IV (% or decimal)")
    atm_iv = st.number_input(
        "ATM IV (% or decimal)",
        value=14.0,
        format="%.4f",
        label_visibility="collapsed",
    )
    futures_price = st.number_input("Stock Price", value=24200.0, format="%.2f")
    dte_days = st.number_input("Days from today", min_value=1, value=3, step=1)
with col_b:
    strike_1 = st.number_input("Lower Price", value=23100.0, format="%.2f")
    strike_2 = st.number_input("Upper Price", value=23500.0, format="%.2f")
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
        pct = 100.0 * float(out["probability_between_strikes"])
        expiry_on = date.today() + timedelta(days=int(dte_days))
        expiry_str = expiry_on.strftime("%d %B %Y")
        st.markdown(
            f"<div style='margin-top:0.75rem;line-height:1.85;'>"
            f"<p style='font-size:2rem;margin:0 0 0.5rem 0;font-weight:700;'>{pct:.2f}% chance</p>"
            f"<p style='margin:0.4rem 0;font-size:1.1rem;'>to close between "
            f"<strong>{strike_1:,.2f}</strong> &nbsp;and&nbsp; <strong> {strike_2:,.2f}</strong></p>"
            f"<p style='margin:0.4rem 0;color:#666;font-size:1rem;'> On {expiry_str}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )
    except ValueError as e:
        st.error(str(e))
