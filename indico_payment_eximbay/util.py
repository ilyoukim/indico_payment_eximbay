# -*- coding: utf-8 -*-
##
## This file is part of the Eximbay Indico EPayment Plugin.
## Copyright (C) 2019 - 2026 Gyujin Kim
##
## This is free software; you can redistribute it and/or
## modify it under the terms of the GNU General Public License as
## published by the Free Software Foundation; either version 3 of the
## License, or (at your option) any later version.
##
## This software is distributed in the hope that it will be useful, but
## WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
## General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Eximbay Indico EPayment Plugin;if not, see <http://www.gnu.org/licenses/>.

import base64
import json
import requests
from urllib.parse import urljoin

from indico.core.plugins import url_for_plugin

from indico_payment_eximbay import _


# payment provider identifier
PROVIDER_EXIMBAY = "eximbay"


# Eximbay API URLs
EXIMBAY_SERVICE_DOMAIN = "https://api.eximbay.com"

EXIMBAY_SDK_URL = "v2/javascriptSDK.js"

EXIMBAY_PAYMENT_URL = "v1/payments/payments"
EXIMBAY_READY_URL = "v1/payments/ready"
EXIMBAY_CONFIRM_URL = "v1/payments/confirm"
EXIMBAY_VERIFY_URL= "v1/payments/verify"
EXIMBAY_RETRIEVE_URL = "v1/payments/retrieve"
EXIMBAY_CANCEL_URL = "v1/payments/<transaction_id>/cancel"


# https://developer.eximbay.com/eximbay/api_sdk/code-etc.html
# Support Currency : Eximbay manual - Appendix A
EXIMBAY_CURRENCY = {"KRW","USD","EUR","GBP","JPY","THB","SGD","RUB","HKD","CAD","AUD"}

# Support Language : Eximbay manual - Appendix B
EXIMBAY_LANGUAGE = {"KR","EN","CN","JP","RU","TH","TW","VN"}


# https://developer.eximbay.com/eximbay/api_sdk/code-organization.html
EXIMBAY_PAYMETHOD = {
    "P000": "Credit Card",
    "P101": "VISA",
    "P102": "MasterCard",
    "P103": "AMEX",
    "P104": "JCB",
    "P106": "Diners",
    "P107": "Discover",
    "P108": "Mir",
    "P109": "UnionPay",
    "P001": "PayPal",
    "P002": "CUP(UPOP)",
    "P003": "Alipay or Alipay Plus",
    "P174": "Alipay Plus(Alipay_CN)",
    "P175": "Alipay Plus(TRUEMONEY)",
    "P176": "Alipay Plus(DANA)",
    "P177": "Alipay Plus(Alipay_HK)",
    "P178": "Alipay Plus(TNG)",
    "P179": "Alipay Plus(GCASH)",
    "P141": "WeChat(PC)",
    "P142": "WeChat(Mobile)",
    "P143": "WeChat(POP)",
    "P144": "WeChat(MINI)",
    "P006": "ECONTEXT",
    "P197": "Klarna",
    "P350": "GrabPay(MYR)",
    "P351": "GrabPay(SGD)",
    "P352": "ShopeePay(THB)",
    "P353": "JKOPAY(TWD)",
    "P354": "PayPay",
    "P110": "BC Card",
    "P111": "KB Card",
    "P112": "HANA Card",
    "P113": "SAMSUNG Card",
    "P114": "SHINHAN Card",
    "P115": "HYUNDAI Card",
    "P116": "LOTTE Card",
    "P117": "NONGHYEOP Card",
    "P119": "CITI Card",
    "P120": "WOORI Card",
    "P121": "SUHYEOP Card",
    "P122": "JEJU Card",
    "P123": "JEONBUK Card",
    "P124": "GWANGJU Card",
    "P125": "KAKAOBANK",
    "P126": "KBANK",
    "P127": "MIRAE ASSET",
    "P128": "KONA Card",
    "P129": "TOSS Card",
    "P130": "CHAI Card",
    "P301": "BANK PAY",
    "P302": "KAKAO PAY",
    "P303": "TOSS",
    "P304": "PAYCO",
    "P305": "Virtual Account",
    "P015": "NAVER PAY(CARD & POINT)",
    "P307": "NAVER PAY(CARD)",
    "P308": "NAVER PAY(POINT)",
}


def get_paymethod(code):
    return str(EXIMBAY_PAYMETHOD.get(code, code))


def get_request_header(api_key):
    """Base64 encoding

    - https://developer.eximbay.com/eximbay/payment_linkage/preparing-payment.html#apiAuthentication
    """
    text = api_key + ":"
    encoded = base64.b64encode(text.encode("utf-8")).decode("utf-8")

    headers = {
        "Authorization": "Basic " + encoded,
        "Content-Type": "application/json"
    }

    return headers


def _get_fgkey(api_url, api_key, data):
    """
    # https://developer.eximbay.com/eximbay/payment_linkage/preparing-fgkey.html
    """
    request_url = urljoin(api_url, EXIMBAY_READY_URL)

    headers = get_request_header(api_key)

    try:
        response = requests.post(url=request_url, headers=headers, data=json.dumps(data), timeout=5)
        response.raise_for_status()
        recv = response.json()
    except requests.RequestException as e:
        raise TransactionFailure(step="ready", details=str(e))

    resCode = recv.get("rescode", "").strip()
    resMsg = recv.get("resmsg", "").strip()

    if resCode == "0000" and resMsg == "Success":
        return recv.get("fgkey", "").strip()
    else:
        raise TransactionFailure(step="ready", details=response.text)


def get_transaction_params(event_settings, registration, is_kor: bool):
    """Get parameters for creating a transaction request."""
    api_url = event_settings.get("url")

    if is_kor:
        mid = event_settings.get("account_id", "")
        api_key = event_settings.get("account_key", "")
    else:
        mid = event_settings.get("account_id2", "")
        api_key = event_settings.get("account_key2", "")

    # check API Key validation
    if api_key and len(api_key) == 25:
        pass
    else:
        return {}

    format_map = {
        "user_id": registration.user_id,
        "event_id": registration.event_id,
        "event_title": registration.event.title,
        "registration_form_id": registration.registration_form_id,
        "registration_form_title": registration.registration_form.title,
        "registration_db_id": registration.id,
        "registration_id": registration.friendly_id,
        "user_firstname": registration.first_name,
        "user_lastname": registration.last_name,
    }
    order_description = event_settings["order_description"].format(**format_map)
    order_identifier = event_settings["order_identifier"].format(**format_map)

    # https://developer.eximbay.com/eximbay/api_list/reference.html
    transaction_params = {
        "merchant": {
            "mid": mid,                                     # merchant ID
        },
        "payment": {
            "transaction_type": "PAYMENT",
            "payment_method": "P000",                       # P000: Credit Card
            "lang": "EN",                                   # default: EN
            "order_id": order_identifier[-30:],             # orderId : unique value (max. 30 char)
            "currency": registration.currency,              # currency: USD, EUR, KRW ...
            "amount": str(registration.price),              # total price > 0
        },
        "buyer": {
            "name": registration.full_name,
            "email": registration.email,
        },
        "product": [{
            "name": order_description[-255:],               # product name: max 255 char
            "unit_price": str(registration.price),          # product price > 0
            "quantity": str(1),                             # product quantity > 0
        }],
        "url": {
            "return_url": url_for_plugin("payment_eximbay.return", registration.locator.uuid, _external=True),
            "status_url": url_for_plugin("payment_eximbay.notify", registration.locator.uuid, _external=True),
        },
        "settings": {
            "display_type": "R",                            # R: redirect, P: popup
        },
    }

    # Korea Domestic Card
    if is_kor:
        transaction_params["payment"]["lang"] = "KR"
        transaction_params["settings"]["issuer_country"] = "KR"

    transaction_params["fgkey"] = _get_fgkey(api_url, api_key, transaction_params)

    return transaction_params
