# -*- coding: utf-8 -*-
##
## This file is part of the Eximbay Indico EPayment Plugin.
## Copyright (C) 2019 - 2025 Gyujin Kim
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

from indico.core.plugins import IndicoPlugin, url_for_plugin
from indico.modules.events.payment import PaymentPluginMixin

from indico_payment_eximbay.forms import EventSettingsForm, PluginSettingsForm
from indico_payment_eximbay.util import (EXIMBAY_SERVICE_DOMAIN, EXIMBAY_CURRENCY)


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
        'account_id': '',
        'account_key': '',
        'account_id2': '',
        'account_key2': '',
        'order_description': '{event_title} {registration_form_title}',
        'order_identifier': 'e{event_id}f{registration_form_id}r{registration_id}',
        'announcement': '',
        'notification_mail': ''
    }
    #: per event default settings - use the global settings as fallback
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

    def adjust_payment_form_data(self, data):
        """Prepare the payment form shown to registrants
        parameters check: template/event_payment_form.html
        
        api_url : eximbay payment service url
        valid_trans : to announce for no actual transaction
        
        korean : translation data set for Korean Credit Card
        global : translation data set for Global Credit Card
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
        order_identifier = event_settings['order_identifier'].format(**format_map)
        order_description = event_settings['order_description'].format(**format_map)
        
        data['order_id'] = order_identifier[:30]
        data['item_name'] = order_description[:255]
        
        # Display message
        data['test'] = (api_url != EXIMBAY_SERVICE_DOMAIN)
        data['announcement'] = event_settings.get('announcement', '')

        data['korean'] = bool(event_settings.get('account_id', ''))
        data['global'] = bool(event_settings.get('account_id2', ''))
