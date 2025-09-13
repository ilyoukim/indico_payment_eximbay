# -*- coding: utf-8 -*-
##
## This file is part of the Eximbay Indico EPayment Plugin.
## Copyright (C) 2019 - 2024 Gyujin Kim
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
from datetime import datetime
from urllib.parse import urljoin

from indico.core.plugins import IndicoPlugin, url_for_plugin
from indico.modules.events.payment import PaymentPluginMixin

from indico_payment_eximbay.forms import EventSettingsForm, PluginSettingsForm
from indico_payment_eximbay.util import (EXIMBAY_SERVICE_DOMAIN, EXIMBAY_SDK_URL,
                                         EXIMBAY_CURRENCY, get_transdata)

class EximbayPaymentPlugin(PaymentPluginMixin, IndicoPlugin):
    """Eximbay

    Provides an EPayment method using the Eximbay API.
    """
    configurable = True
    #: form for default configuration across events
    settings_form = PluginSettingsForm
    #: form for configuration for specific events
    event_settings_form = EventSettingsForm
    #: Set containing all valid currencies.
    valid_currencies = EXIMBAY_CURRENCY
    
    #: global default settings - should be a reasonable default
    default_settings = {
        'method_name': 'Online Payment with Eximbay',
        'url': EXIMBAY_SERVICE_DOMAIN,
        'account_id': None,
        'account_key': None,
        'account_id2': None,
        'account_key2': None,
        'order_description': '{event_title} {registration_form_title}',
        'order_identifier': 'e{event_id}f{registration_form_id}r{registration_id}',
        'announcement': '',
        'notification_mail': None
    }
    #: per event default settings - use the global settings
    default_event_settings = {
        'enabled': False,
        'method_name': None,
        'url': None,
        'account_id': None,
        'account_key': None,
        'account_id2': None,
        'account_key2': None,
        'order_description': None,
        'order_identifier': None,
        'announcement': '',
        'notification_mail': None
    }
    
    @property
    def logo_url(self):
        return url_for_plugin(self.name + '.static', filename='images/logo.png')
    
    def get_blueprints(self):
        """Blueprint for URL endpoints with callbacks"""
        from indico_payment_eximbay.blueprint import blueprint
        return blueprint

    def _get_transaction_parameters(self, data, mid, isKor=False):
        """Get parameters for creating a transaction request."""
        # event = data['event']
        registration = data['registration']
        # settings = data['settings']
        event_settings = data['event_settings']

        api_url = event_settings.get('url')
        
        if mid == event_settings.get('account_id', None):
            api_key = event_settings.get('account_key', None)
        elif mid == event_settings.get('account_id2', None):
            api_key = event_settings.get('account_key2', None)
        else:
            return None
        
        # check security Key validation
        if isinstance(api_key, str) and len(api_key) < 25:
            pass
        else:
            None
        
        format_map = {
            'user_id': registration.user_id,
            'event_id': registration.event_id,
            'event_title': registration.event.title,
            'registration_form_id': registration.registration_form_id,
            'registration_form_title': registration.registration_form.title,
            'registration_db_id': registration.id,
            'registration_id': registration.friendly_id,
            'user_firstname': registration.first_name,
            'user_lastname': registration.last_name,
        }
        order_description = event_settings['order_description'].format(**format_map)
        order_identifier = event_settings['order_identifier'].format(**format_map)

        # max 30 characters
        order_id = "{0}_{1:%m%d%H%M%S}".format(order_identifier, datetime.now())[:30]
        
        # see the Eximbay Manual on what these things mean
        # where to asynchronously call back from Eximbay
        transaction_data = {
            "merchant": {
                "mid": mid,                             # merchant ID
            },
            "payment": {
                "order_id": order_id,                   # orderId : unique value
                "currency": registration.currency,
                "amount": str(registration.price),      # total price
            },
            "buyer": {
                "name": registration.full_name,
                "email": registration.email,
            },
            "product": [{
                "name": order_description,
                "unit_price": str(registration.price),
                "quantity": str(1),
                "link":""                               # open marker일 경우 필수라고 하는데 확인이 필요함
            }],
            "url": {
                "return_url": url_for_plugin('payment_eximbay.return', registration.locator.uuid, _external=True),
                "status_url": url_for_plugin('payment_eximbay.notify', registration.locator.uuid, _external=True),
            },
        }

        transaction_data = get_transdata(api_url, api_key, transaction_data, isKor)

        return transaction_data
    
    def adjust_payment_form_data(self, data):
        """Prepare the payment form shown to registrants
        parameters check: template/event_payment_form.html
        
        api_url : eximbay payment service url
        valid_trans : to announce for no actual transaction
        
        eximbay : translation data set for Korean Credit Card
        eximbay_global : translation data set for Global Credit Card
        api_url : redirection url after click send
        """
        event_settings = data['event_settings']
        registration = data['registration']
        
        format_map = {
            'user_id': registration.user_id,
            'event_id': registration.event_id,
            'event_title': registration.event.title,
            'registration_form_id': registration.registration_form_id,
            'registration_form_title': registration.registration_form.title,
            'registration_db_id': registration.id,
            'registration_id': registration.friendly_id,
            'user_firstname': registration.first_name,
            'user_lastname': registration.last_name,
        }

        api_url = event_settings.get('url')
        mid1 = event_settings.get('account_id', None)
        mid2 = event_settings.get('account_id2', None)
        
        # Display message
        data['announcement'] = event_settings.get('announcement')
        data['valid_trans'] = (api_url == EXIMBAY_SERVICE_DOMAIN)
        
        data['item_name'] = event_settings['order_description'].format(**format_map)

        data['data_korean'] = bool(mid1)
        data['data_global'] = bool(mid2)
