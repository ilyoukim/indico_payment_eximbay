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
from urllib.parse import urljoin

from indico.core.plugins import IndicoPlugin, url_for_plugin
from indico.modules.events.payment import PaymentPluginMixin

from indico_payment_eximbay.forms import EventSettingsForm, PluginSettingsForm
from indico_payment_eximbay.util import (EXIMBAY_PP_BASIC_URL, get_transdata)

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
        'method_name': 'Eximbay Global',
        'url': 'https://secureapi.eximbay.com',
        'account_id': None,
        'account_securitykey': None,
        'language': 'EN',
        'order_description': '{event_title}, {regform_title}, {user_name}',
        'order_identifier': 'e{event_id}u{user_id}r{registration_id}',
    }
    #: per event default settings - use the global settings
    default_event_settings = {
        'enabled': False,
        'method_name': None,
        'url': None,
        'account_id': None,
        'account_securitykey': None,
        'language': None,
        'order_description': None,
        'order_identifier': None,
    }
    
    @property
    def logo_url(self):
        return url_for_plugin(self.name + '.static', filename='images/logo.png')
    
    def get_blueprints(self):
        """Blueprint for URL endpoints with callbacks"""
        from indico_payment_eximbay.blueprint import blueprint
        return blueprint

    def _get_transaction_parameters(self, data):
        """Get parameters for creating a transaction request."""
        event = data['event']
        settings = data['event_settings']
        registration = data['registration']
        
        # security Key is not accurate
        if len(settings['account_securitykey']) < 32:
            raise KeyError
        
        format_map = {
            'user_id': registration.user_id,
            'user_name': registration.full_name,
            'user_firstname': registration.first_name,
            'user_lastname': registration.last_name,
            'event_id': registration.event_id,
            'event_title': registration.event.title,
            'registration_id': registration.id,
            'regform_title': registration.registration_form.title
        }
        order_description = settings['order_description'].format(**format_map)
        order_identifier = settings['order_identifier'].format(**format_map)
        
        # see the Eximbay Manual on what these things mean
        # where to asynchronously call back from Eximbay
        transaction_data = {
            'txntype': 'PAYMENT',
            'ostype': 'P',                      # P:pc, M:mobile
            'displaytype': 'P',                 # P:popup, R:page redirect
            'paymethod': 'P000',                # Credit Card
            'mid': settings['account_id'],
            'lang': settings['language'],       # KR, EN, CN, JP
            'ref': order_identifier,            # orderId : unique value
            'amt': str(registration.price),
            'cur': registration.currency,
            'buyer': registration.full_name,
            'email': registration.email,
            'item_0_product': order_description,
            'item_0_unitPrice': str(registration.price),
            'item_0_quantity': '1',
            'returnurl': url_for_plugin('payment_eximbay.return', registration.locator.uuid, _external=True),
            'statusurl': url_for_plugin('payment_eximbay.notify', registration.locator.uuid, _external=True),
            }
        
        transaction_data = get_transdata(settings['account_securitykey'], transaction_data)
        return transaction_data
    
    def adjust_payment_form_data(self, data):
        """Prepare the payment form shown to registrants
        parameters check: template/event_payment_form.html
        
        base_url : eximbay payment service url
        eximbay : traslation data set
        payment_url : redirection url after click send
        """
        base_url = data['event_settings']['url']
        
        data['eximbay'] = self._get_transaction_parameters(data)
        data['payment_url'] = urljoin(base_url, EXIMBAY_PP_BASIC_URL)

