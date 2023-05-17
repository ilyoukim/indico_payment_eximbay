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
"""
Definition of callbacks exposed by the Indico server
"""

from indico.core.plugins import IndicoPluginBlueprint

from indico_payment_eximbay.controllers import RHEximbayNotify, RHEximbayReturn


blueprint = IndicoPluginBlueprint(
    'payment_eximbay', __name__,
    url_prefix='/event/<int:event_id>/registrations/<int:reg_form_id>/payment/eximbay'
)


blueprint.add_url_rule('/return', 'return', RHEximbayReturn, methods=('GET', 'POST'))

# Used by Eximbay to send an asynchronous notification for the transaction (pending, successful, etc)
blueprint.add_url_rule('/status', 'notify', RHEximbayNotify, methods=('POST',))
