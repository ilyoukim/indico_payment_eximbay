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
"""
Definition of callbacks exposed by the Indico server
"""
from __future__ import unicode_literals

from indico.core.plugins import IndicoPluginBlueprint

from .request_handlers import EximbayResponseHandler, \
        EximbayCancelHandler, EximbayFailureHandler, EximbaySuccessHandler


#: url mount points exposing callbacks
blueprint = IndicoPluginBlueprint(
    'payment_eximbay', __name__,
    url_prefix='/event/<confId>/registrations/<int:reg_form_id>/payment/response/eximbay'
)

# blueprint.add_url_rule('/failure', 'failure', EximbayCancelHandler, methods=('GET', 'POST'))
# blueprint.add_url_rule('/cancel', 'cancel', EximbayFailureHandler, methods=('GET', 'POST'))
blueprint.add_url_rule('/success', 'success', EximbaySuccessHandler, methods=('GET', 'POST'))
# Used by Eximbay to send an asynchronous notification for the transaction
blueprint.add_url_rule('/ipn', 'notify', EximbayResponseHandler, methods=('POST',))
