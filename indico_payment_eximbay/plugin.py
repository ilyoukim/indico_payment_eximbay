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
Core of the Eximbay plugin

The entry point for indico is the :py:class:`~.EximbayPaymentPlugin`.
It handles configuration via the settings forms, initiates payments
and provides callbacks for finished payments via its blueprint.
"""
import dateutil.parser

from indico.core.plugins import IndicoPlugin, url_for_plugin
from indico.modules.events.payment import PaymentPluginMixin
from indico.util.date_time import now_utc

from indico_payment_eximbay.forms import EventSettingsForm, PluginSettingsForm


class EximbayPaymentPlugin(PaymentPluginMixin, IndicoPlugin):
    """Eximbay

    Provides an EPayment method using the Eximbay API.
    """
    
    configurable = True
    #: form for default configuration across events
    settings_form = PluginSettingsForm
    #: form for configuration for specific events
    event_settings_form = EventSettingsForm
    #: global default settings - should be a reasonable default
    default_settings = {
        'method_name': 'Eximbay',
        'url': 'https://secureapi.eximbay.com',
        'account_id': None,
        'account_securitykey': None,
        'order_description': '{event_title}, {registration_title}, {user_name}',
        'order_identifier': 'e{event_id}r{registration_id}_u{eventuser_id}',
        'notification_mail': None
    }
    #: per event default settings - use the global settings
    default_event_settings = {
        'enabled': False,
        'method_name': None,
        'url': None,
        'account_id': None,
        'account_securitykey': None,
        'order_description': None,
        'order_identifier': None,
        'notification_mail': None
    }
    
    @property
    def logo_url(self):
        return url_for_plugin(self.name + '.static', filename='images/logo.png')
    
    def get_blueprints(self):
        """Blueprint for URL endpoints with callbacks"""
        from indico_payment_eximbay.blueprint import blueprint
        return blueprint

    def is_pending_transaction_expired(self, transaction):
        if not (expiration := transaction.data.get('Init_PP_response', {}).get('Expiration')):
            return False
        return dateutil.parser.parse(expiration) <= now_utc()
