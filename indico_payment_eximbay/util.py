# -*- coding: utf-8 -*-
##
## This file is part of the Eximbay Indico EPayment Plugin.
## Copyright (C) 2019 - 2020 Gyujin Kim
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
import uuid

import iso4217
import operator
import hashlib
from werkzeug.exceptions import NotImplemented as HTTPNotImplemented

from indico_payment_eximbay import _


# Eximbay API details
EXIMBAY_API_SPEC = '2.3'
# EXIMBAY_PP_INIT_URL = 'Payment/v1/PaymentPage/Initialize'
# EXIMBAY_PP_ASSERT_URL = 'Payment/v1/PaymentPage/Assert'
# EXIMBAY_PP_CAPTURE_URL = 'Payment/v1/Transaction/Capture'
# EXIMBAY_PP_CANCEL_URL = 'Payment/v1/Transaction/Cancel'

# payment provider identifier
PROVIDER_EXIMBAY = 'eximbay'

#: currencies for which the major to minor currency ratio is not a multiple of 10
NON_DECIMAL_CURRENCY = {'MRU', 'MGA'}


def validate_currency(iso_code):
    """
    Check whether the currency can be properly handled by this plugin

    :param iso_code: an ISO4217 currency code, e.g. ``"EUR"``
    :raises: :py:exc:`~.HTTPNotImplemented` if the currency is not valid
    """
    if iso_code in NON_DECIMAL_CURRENCY:
        raise HTTPNotImplemented(
            _("Unsupported currency '{0}' for Eximbay. Please contact the organisers").format(iso_code)
        )
    try:
        iso4217.Currency(iso_code)
    except ValueError:
        raise HTTPNotImplemented(
            _("Unknown currency '{0}' for Eximbay. Please contact the organisers").format(iso_code)
        )

def get_request_header(api_spec, account_id):
    return {
        'SpecVersion': api_spec,
        'CustomerId': get_customer_id(account_id),
        'RequestId': str(uuid.uuid4()),
        'RetryIndicator': 0,
    }


def get_customer_id(account_id):
    """Extract customer ID from account ID.

    Customer ID is the first part (befor the hyphen) of the account ID.
    """
    return account_id.split('-')[0]


def get_terminal_id(account_id):
    """Extract the teminal ID from account ID.

    The Terminal ID is the second part (after the hyphen) of the
    account ID.
    """
    return account_id.split('-')[1]


def get_fgkey(exb_secret, data):
    """Specific function for Eximbay
    Generate fgkey from input parameters and secretkey
    
    :param data: request or response params
    :return: fgkey
    """
    if len(exb_secret) < 1:
        return ''
    
    if 'fgkey' in data:
        newData = {key: value for key, value in data.items()}
        del newData['fgkey']
    else:
        newData = data
    
    # A : Make sorted query
    query = sorted(newData.items(), key=operator.itemgetter(0))
    
    params = ''
    for (key, value) in query:
        params += '%s=%s&' % (key, value)
    
    # B: string concat secretkey and A with ? character
    sp = '%s?%s' % (exb_secret, params[:-1])

    # C: generate hashing from B and SHA256 function
    # convert character set to UTF-8
    fgkey = hashlib.sha256(sp.encode('utf-8')).hexdigest()
    return fgkey.upper()
