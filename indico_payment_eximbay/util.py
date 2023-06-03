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

import operator
import hashlib
from werkzeug.exceptions import NotImplemented as HTTPNotImplemented

from indico_payment_eximbay import _


# Eximbay API details
EXIMBAY_API_SPEC = '2.3'
EXIMBAY_PP_BASIC_URL = '/Gateway/BasicProcessor.krp'
EXIMBAY_PP_DIRECT_URL = '/Gateway/DirectProcessor.krp'

# payment provider identifier
PROVIDER_EXIMBAY = 'eximbay'

# Support Currency : Eximbay manual - Appendix A
EXIMBAY_CURRENCY = {'KRW','USD','EUR','GBP','JPY','THB','SGD','RUB','HKD','CAD','AUD'}

# Support Language : Eximbay manual - Appendix B
EXIMBAY_LANGUAGE = {'KR','EN','CN','JP','RU','TH','TW','VN'}


def validate_currency(iso_code):
    """
    Check whether the currency can be properly handled by this plugin

    :param iso_code: an ISO4217 currency code, e.g. ``"EUR"``
    :raises: :py:exc:`~.HTTPNotImplemented` if the currency is not valid
    """
    if iso_code in EXIMBAY_CURRENCY:
        raise HTTPNotImplemented(
            _("Unsupported currency '{0}' for Eximbay. Please contact the organisers").format(iso_code)
        )


def validate_language(lang_code):
    """
    Check whether the currency can be properly handled by this plugin

    :raises: :py:exc:`~.HTTPNotImplemented` if the currency is not valid
    """
    if lang_code in EXIMBAY_LANGUAGE:
        raise HTTPNotImplemented(
            _("Unsupported language '{0}' for Eximbay. Please contact the organisers").format(lang_code)
        )


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
    
    if 'fgkey' in newData:
        del newData['fgkey']
    
    # A : Make sorted query with list type
    params = sorted(newData.items(), key=operator.itemgetter(0))
    
    query = "&".join(["{}={}".format(key, value) for key, value in params])
    
    # B: string concat secretkey and A with ? character
    sp = '%s?%s' % (exb_secret, query)

    # C: generate hashing from B and SHA256 function
    # convert character set to UTF-8
    fgkey = hashlib.sha256(sp.encode('utf-8')).hexdigest()
    return fgkey.upper()


def get_transdata(exb_secret, assert_data):
    """Generate eximbay transaction data
    # see the Eximbay Manual on what these things mean
    
    assert_data : dict
    
    transdata = {
        'charset': 'UTF-8',                 ## default
        'ver': '230',                       ## eximbay version
        'txntype': 'PAYMENT',               # message type: PAYMENT, QUERY
        'ostype': 'P',                      # P:pc, M:mobile
        'displaytype': 'P',                 # P:popup, R:page redirect
        'paymethod': 'P000',                # P000: Credit Card, P001: PayPal, etc ...
        'mid': exim_account_id,
        'lang': display_language,           # KR, EN, CN, JP
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
    transdata = {}
    
    if not 'charset' in assert_data:
        transdata['charset'] = 'UTF-8'
    
    if not 'ver' in assert_data:
        transdata['ver'] = '230'

    transdata.update(assert_data)
    
    transdata['fgkey'] = get_fgkey(exb_secret, transdata)
    
    return transdata
