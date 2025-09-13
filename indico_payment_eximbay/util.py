# -*- coding: utf-8 -*-
##
## This file is part of the Eximbay Indico EPayment Plugin.
## Copyright (C) 2019 - 2025 Gyujin Kim
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

import copy
import base64
import requests
import json
from urllib.parse import urljoin

from indico_payment_eximbay import _


# payment provider identifier
PROVIDER_EXIMBAY = 'eximbay'

# Eximbay API details
EXIMBAY_SERVICE_DOMAIN = "https://api.eximbay.com"

EXIMBAY_SDK_URL = "v2/javascriptSDK.js"

EXIMBAY_PAYMENT_URL = "v1/payments/payments"
EXIMBAY_READY_URL = "v1/payments/ready"
EXIMBAY_CONFIRM_URL = "v1/payments/confirm"
EXIMBAY_VERIFY_URL= "v1/payments/verify"
EXIMBAY_RETRIEVE_URL = "v1/payments/retrieve"
EXIMBAY_CANCEL_URL = "v1/payments/{transaction_id}/cancel"


# Support Currency : Eximbay manual - Appendix A
EXIMBAY_CURRENCY = {'KRW','USD','EUR','GBP','JPY','THB','SGD','RUB','HKD','CAD','AUD'}

# Support Language : Eximbay manual - Appendix B
EXIMBAY_LANGUAGE = {'KR','EN','CN','JP','RU','TH','TW','VN'}

EXIMBAY_PAYMETHOD = {
    "P000": "Credit Card",
    "P101": "VISA",
    "P102": "MasterCard",
    "P103": "AMEX",
    "P104": "JCB",
    "P105": "CUP(UnionPay 2D)",
    "P106": "Diners",
    "P107": "Discover",
    "P108": "Mir",
    "P001": "PayPal",
    "P002": "CUP(UnionPay)",
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
    "P006": "Japanese Convenience Store, Internet Banking Payment",
    "P171": "Razer Merchant Services(Malaysia)",
    "P172": "Razer Merchant Services(Vietnam)",
    "P173": "Razer Merchant Services(Thailand)",
    "P011": "YooMoney",
    "PG01": "2C2P",
    "P185": "GrabPay(SGD)",
    "P189": "GrabPay(MYR)",
    "P190": "GrabPay(PHP)",
    "P186": "LinePay(2C2P)",
    "P194": "LinePay(eContext)",
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
    "P127": "MIRAEASSET",
    "P128": "KONA Card",
    "P129": "TOSS Card",
    "P130": "CHAI Card",
    "P301": "BANK PAY",
    "P302": "KAKAO PAY",
    "P303": "TOSS",
    "P304": "PAYCO",
    "P305": "Virtual Account",
    "P306": "SMILE PAY",
    "P015": "NAVER PAY(CARD & POINT)",
    "P307": "NAVER PAY(CARD)",
    "P308": "NAVER PAY(POINT)",
}


def get_paymethod(code):
    EXIMBAY_PAYMETHOD.get(code, code)

def get_request_header(api_key):
    text = api_key + ":"
    encoded = base64.b64encode(text.encode("utf-8")).decode("utf-8")
    
    headers = {
        "Authorization": "Basic " + encoded,
        "Content-Type": "application/json"
    }

    return headers
