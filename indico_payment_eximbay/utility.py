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
from __future__ import unicode_literals, division

import iso4217
import operator
import hashlib
from werkzeug.exceptions import NotImplemented as HTTPNotImplemented

from indico.util.i18n import make_bound_gettext

#: internationalisation/localisation of strings
gettext = make_bound_gettext('payment_eximbay')


#: currencies for which the major to minor currency ratio is not a multiple of 10
NON_DECIMAL_CURRENCY = {'MRU', 'MGA'}


def validate_currency(iso_code):
    """
    Check whether the currency can be properly handled by this plugin

    :param iso_code: an ISO4217 currency code, e.g. ``"EUR"``
    :type iso_code: basestring
    :raises: :py:exc:`~.HTTPNotImplemented` if the currency is not valid
    """
    if iso_code in NON_DECIMAL_CURRENCY:
        raise HTTPNotImplemented(
            gettext("Unsupported currency '{0}' for Eximbay. Please contact the organisers").format(iso_code)
        )
    try:
        iso4217.Currency(iso_code)
    except ValueError:
        raise HTTPNotImplemented(
            gettext("Unknown currency '{0}' for Eximbay. Please contact the organisers").format(iso_code)
        )

def get_fgkey(exb_secret, data):
    """
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
