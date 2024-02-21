# -*- coding: utf-8 -*-
##
## This file is part of the Eximbay Indico EPayment Plugin.
## Copyright (C) 2019 - 2023 Gyujin Kim
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

import hashlib
import operator

from indico_payment_eximbay import _


# Eximbay API details
EXIMBAY_API_SPEC = '2.3'
EXIMBAY_API_VERSION = '230'
EXIMBAY_PP_BASIC_URL = '/Gateway/BasicProcessor.krp'
EXIMBAY_PP_DIRECT_URL = '/Gateway/DirectProcessor.krp'

# payment provider identifier
PROVIDER_EXIMBAY = 'eximbay'

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
    if code in EXIMBAY_PAYMETHOD:
        return EXIMBAY_PAYMETHOD.get(code)
    else:
        return code

def get_fgkey(exb_secret, data):
    """Specific function for Eximbay
    Generate fgkey from input parameters and secretkey
    Eximbay manual Chapter 4
    
    :param data: request or response params
    :return: fgkey
    """
    if len(exb_secret) < 32:
        raise KeyError
    
    newData = {}
    newData.update(data)
    
    # remove fgkey
    newData.pop('fgkey', None)
    
    # A : Make sorted query with list type
    params = sorted(newData.items(), key=operator.itemgetter(0))
    
    query = "&".join( ("{}={}".format(key, value) for key, value in params) )
    
    # B: string concat secretkey and A with ? character
    sp = '%s?%s' % (exb_secret, query)

    # C: generate hashing from B and SHA256 function
    # convert character set to UTF-8
    fgkey = hashlib.sha256(sp.encode('utf-8')).hexdigest()
    return fgkey.upper()


def get_transdata(exb_secret, assert_data, isKOR=False):
    """Generate eximbay transaction data
    # see the Eximbay Manual on what these things mean
    
    assert_data : dict
    
    transdata = {
        'charset': 'UTF-8',                 ## default
        'ver': '230',                       ## eximbay version
        'txntype': 'PAYMENT',               # message type: PAYMENT, QUERY
        'ostype': 'P',                      # P:pc (default), M:mobile
        'displaytype': 'P',                 # P:popup, R:page redirect
        'paymethod': 'P000',                # P000: Credit Card, P001: PayPal, etc ...
        'lang': display_language,           # KR, EN, CN, JP
        'issuercountry': country,           # Nessary for Korea domestic credit card
        'mid': exim_account_id,
        'ref': order_identifier,            # orderId : unique value
        'amt': registration_price,
        'cur': registration_currency,
        'buyer': registration_full_name,
        'email': registration_email,
        'item_0_product': order_description,
        'item_0_unitPrice': registration_price,
        'item_0_quantity': '1',
        'returnurl': return_url,
        'statusurl': status_post_url,       # where to asynchronously call back from Eximbay
        }
    """
    
    transdata = {
            'charset': 'UTF-8',
            'ver': EXIMBAY_API_VERSION,
            'txntype': 'PAYMENT',
            'ostype': 'P',                      # P:pc, M:mobile
            'displaytype': 'P',                 # P:popup, R:page redirect
            'paymethod': 'P000',                # Credit Card
            'lang': 'EN',                       # KR, EN, CN, JP
        }
    
    # Korea Domestic Card
    if isKOR:
        transdata['lang'] = 'KR'
        transdata['issuercountry'] = 'KR'
    
    transdata.update(assert_data)
    
    transdata['fgkey'] = get_fgkey(exb_secret, transdata)
    
    return transdata
