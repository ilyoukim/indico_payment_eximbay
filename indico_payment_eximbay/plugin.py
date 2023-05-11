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
from __future__ import unicode_literals, absolute_import
import urlparse

import requests
from werkzeug.exceptions import NotImplemented as \
    HTTPNotImplemented, InternalServerError as HTTPInternalServerError

from wtforms.fields.core import StringField
from wtforms.fields.html5 import URLField
from wtforms.validators import DataRequired, Optional, Regexp, Length, Email, ValidationError

from indico.core.plugins import IndicoPlugin, url_for_plugin
from indico.modules.events.payment import \
    PaymentEventSettingsFormBase, PaymentPluginMixin, PaymentPluginSettingsFormBase
from indico.util.string import remove_accents, unicode_to_ascii

from .utility import gettext, get_fgkey
# blueprint mounts the request handlers onto URLs
from .blueprint import blueprint


# Dear Future Maintainer,
#
# while an improvement over Indico 1.2, the Indico 2.0 plugin/core
# facilities are rather lacking in documentation. I have added
# some notes for each **base**type on how they are integrated with
# the rest of Indico. Be aware that this is reconstructed from
# implementations, not from official API docs.
#
# Regards,
# Past Maintainer


# PaymentPluginSettingsFormBase from indico.modules.events.payment
# - A codified Form for users to fill in. The *class attributes* define
#   which fields exist, their shape, description, etc.
# - Each field is a type from wtforms.fields.core.Field. You probably want to have:
#   - label: Name of the field, an internationalised identifier
#   - validators: Input validation, see wtforms.validators
#   - description: help text of the field, an internationalised text

class FormatField(object):
    """
    Validator for format fields, i.e. strings with ``{key}`` placeholders

    :param max_length: optional maximum length, checked on a test formatting
    :type max_length: int
    :param field_map: keyword arguments to use for test formatting

    On validation, a test mapping is applied to the field. This ensures the
    field has a valid ``str.format`` format, and does not use illegal keys
    (as determined by ``default_field_map`` and ``field_map``).
    The ``max_length`` is validated against the test-formatted field, which
    is an estimate for an average sized input.
    """
    #: default placeholders to test length after formatting
    default_field_map = {
        'user_id': 1234,
        'user_name': 'Jane Whiteacre',
        'event_id': 123,
        'event_title': 'Placeholder: The Event',
        'eventuser_id': 'e123u1234',
        'registration_title': 'Registration'
    }

    def __init__(self, max_length=float('inf'), field_map=None):
        self.max_length = max_length
        self.field_map = self.default_field_map.copy()
        if field_map is not None:
            self.field_map.update(field_map)

    def __call__(self, form, field):
        if not field.data:
            return True
        try:
            test_format = field.data.format(**self.field_map)
        except KeyError as err:
            raise ValidationError('Invalid format string key: {}'.format(err))
        except ValueError as err:
            raise ValidationError('Malformed format string: {}'.format(err))
        if len(test_format) > self.max_length:
            raise ValidationError(
                'Too long format string: shortest replacement with {0}, expected {1}'.format(
                    len(test_format), self.max_length
                )
            )
        else:
            return True


class PluginSettingsForm(PaymentPluginSettingsFormBase):
    """Configuration form for the Plugin across all events"""
    url = URLField(
        gettext('Eximbay URL'),
        [DataRequired()],
        description=gettext('URL to contact the Eximbay Payment Service.'
                            'Test server is "https://secureapi.test.eximbay.com"'),
    )
    account_id = StringField(
        label='Account ID',
        # can be set EITHER or BOTH globally and per event
        validators=[Optional(), Regexp(r'[A-Z0-9]{0,10}', message='Field must contain up to 10 digits and alpabets.')],
        description=gettext('ID of your Eximbay account, such as "1849705C64".')
    )
    account_securitykey = StringField(
       label='Account Secret Key',
       # can be set EITHER or BOTH globally and per event
       validators=[Optional(), Regexp(r'[A-Z0-9]{0,40}', message='Field must contain up to 10 digits and alpabets.')],
       description=gettext('Secret key of your Eximbay account, such as "289F40E6640124B2628640168C3C5464".')
    )
    order_description = StringField(
        label=gettext('Order Description'),
        validators=[DataRequired(), FormatField(max_length=80)],
        description=gettext('The description of each order in a human readable way.'
                            'This description is presented to the registrant during the transaction with Eximbay.')
    )
    order_identifier = StringField(
        label=gettext('Order Identifier'),
        validators=[DataRequired(), FormatField(max_length=80)],
        description=gettext('The identifier of each order for further processing.')
    )


class EventSettingsForm(PaymentEventSettingsFormBase):
    """Configuration form for the Plugin for a specific event"""
    # every setting may be overwritten for each event
    url = PluginSettingsForm.url
    account_id = PluginSettingsForm.account_id
    account_securitykey = PluginSettingsForm.account_securitykey
    order_description = PluginSettingsForm.order_description
    order_identifier = PluginSettingsForm.order_identifier


# PaymentPluginMixin, IndicoPlugin
# This is basically a registry of setting fields, logos and other rendering stuff
# All the business logic is in :py:func:`adjust_payment_form_data`
class EximbayPaymentPlugin(PaymentPluginMixin, IndicoPlugin):
    """
    Eximbay

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
        'order_identifier': '{eventuser_id}',
    }
    #: per event default settings - use the global settings
    default_event_settings = {
        'enabled': False,
        'method_name': None,
        'url': None,
        'account_id': None,
        'account_securitykey': None,
        'order_description': None,
        'order_identifier': None
    }
    
    @property
    def logo_url(self):
        return url_for_plugin(self.name + '.static', filename='images/logo.png')
    
    def get_blueprints(self):
        """Blueprint for URL endpoints with callbacks"""
        return blueprint

    # Dear Future Maintainer,
    # - business logic is here!
    # - see PaymentPluginMixin.render_payment_form for what `data` provides
    # - What happens here
    #   - We already send all payment details to Eximbay to get a *signed* request url for this transaction
    #   - We have added `success`, `cancel` and `failure` for *eximbay* to redirect the user back to us AFTER his request
    #   - We have added `notify` for *eximbay* to inform us asynchronously about the result
    #   - We put the transaction URL we got into `data` for the *user* to perform his request securely
    #   - Return uses `indico_payment_eximbay/templates/event_payment_form.html`, presenting a trigger button to the user
    def adjust_payment_form_data(self, data):
        """Prepare the payment form shown to registrants"""
        # indico does not seem to provide stacking of settings
        # we merge event on top of global settings, but remove placeholder defaults
        event_settings, global_settings = data['event_settings'], data['settings']
        plugin_settings = {
            key: event_settings[key] if event_settings.get(key) is not None else global_settings[key]
            for key in
            (set(event_settings) | set(global_settings))
        }
        
        # parameters of the transaction for eximbay - amount, currency, ...
        data['eximbay'] = self._get_transaction_parameters(data)
        data['payment_url'] = urlparse.urljoin(plugin_settings.get('url'), '/Gateway/BasicProcessor.krp')
        return data

    @staticmethod
    def get_field_format_map(registration):
        """Generates dict which provides registration information for format fields"""
        return {
            'user_id': registration.user_id,
            'user_name': registration.full_name,
            'user_firstname': registration.first_name,
            'user_lastname': registration.last_name,
            'event_id': registration.event_id,
            'event_title': registration.event.title,
            'eventuser_id': 'e{0}u{1}'.format(registration.event_id, registration.friendly_id),
            'registration_title': registration.registration_form.title
        }

    def _get_transaction_parameters(self, data):
        """Parameters for formulating a transaction request *without* any business logic hooks"""
        plugin_settings = data['event_settings']
        registration = data['registration']
        format_map = self.get_field_format_map(data['registration'])
        fieldList = ['order_description', 'order_identifier','account_id', 'account_securitykey']
        for format_field in fieldList:
            try:
                if not plugin_settings.has_key(format_field):
                    raise KeyError
                data[format_field] = plugin_settings.get(format_field).format(**format_map)
            except ValueError:
                message = "Invalid format field placeholder for {0}, please contact the event organisers!"
                raise HTTPNotImplemented((
                        gettext(message) + '\n\n[' + message + ']'
                    ).format(self.name)
                 )
            except KeyError:
                message = "Unknown format field placeholder '{0}' for {1}, please contact the event organisers!"
                raise HTTPNotImplemented((
                        gettext(message) + '\n\n[' + message + ']'
                    ).format(format_field, self.name)
                )
        
        # security Key is not accurate
        if len(data['account_securitykey']) < 20:
            raise KeyError
        
        # see the Eximbay Manual on what these things mean
        # where to asynchronously call back from Eximbay
        transaction_parameters = {
            'ver': '230',
            'txntype': 'PAYMENT',
            'charset': 'UTF-8',
            'ostype': 'P',
            'displaytype': 'P',
            'lang': 'EN',
            'paymethod': 'P000',
            'mid': data['account_id'],
            'ref': data['order_identifier'],
            'amt': data['amount'],
            'cur': data['currency'],
            'buyer': registration.full_name,
            'email': registration.email,
            'item_0_product': data['order_description'],
            'item_0_quantity': '1',
            'item_0_unitPrice': data['amount'],
            'returnurl': url_for_plugin('payment_eximbay.success', registration.locator.uuid, _external=True),
            'statusurl': url_for_plugin('payment_eximbay.notify', registration.locator.uuid, _external=True),
        }
        
        transaction_parameters['fgkey'] = get_fgkey(data['account_securitykey'], transaction_parameters)
        return transaction_parameters
