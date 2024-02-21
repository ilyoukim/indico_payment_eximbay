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
