# This file is part of the Indico plugins.
# Copyright (C) 2017 - 2024 Max Fischer, Martin Claus, CERN
#
# The Indico plugins are free software; you can redistribute
# them and/or modify them under the terms of the MIT License;
# see the LICENSE file for more details.

import re

from markupsafe import Markup
from wtforms.fields import BooleanField, StringField, URLField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError

from indico.modules.events.payment import PaymentEventSettingsFormBase, PaymentPluginSettingsFormBase
from indico.web.forms.fields import IndicoPasswordField
from indico.web.forms.validators import IndicoRegexp
from indico.web.forms.widgets import SwitchWidget

from indico_payment_eximbay import _


def render_placeholders(headers, **kwargs):
    """Render the list of available placeholders.

    :param headers: the list of header description
    :param kwargs: placeholders
    """
    
    html = _(headers)
    
    if kwargs:
        html += '<div class="placeholders">'
        html += '<strong>Available placeholders:</strong>'
        html += '<ul style="margin:0;">'
        html += ' '.join(f'<li>{{{key}}} - {value}</li>' for key, value in kwargs.items())
        html += '</ul>'
        html += '</div>'
    
    return _(Markup(html))


class FormatField:
    """Validator for format fields, i.e. strings with ``{key}`` placeholders.

    :param max_length: optional maximum length, checked on a test formatting
    :param field_map: keyword arguments to use for test formatting

    On validation, a test mapping is applied to the field. This ensures the
    field has a valid ``str.format`` format, and does not use illegal keys
    (as determined by ``default_field_map`` and ``field_map``).
    The ``max_length`` is validated against the test-formatted field, which
    is an estimate for an average sized input.
    """

    #: default placeholders to test length after formatting
    default_field_map = {
        'event_id': 12345,
        'event_title': 'Placeholder: The Event',
        'registration_db_id': 12345,
        'registration_form_id': 12345,
        'registration_form_title': 'EarlyBird Registration',
        'registration_id': 12345,
        'user_firstname': 'Jane',
        'user_lastname': 'Whiteacre',
    }
    
    #: id-safe placeholders to test length after formatting
    id_safe_field_map = {
        'event_id': 12345,
        'registration_db_id': 12345,
        'registration_form_id': 12345,
        'registration_id': 12345,
    }

    default_field_descriptions = {
        'event_id': 'The ID of the event (e.g. 12345)',
        'event_title': 'The title of the event',
        'registration_db_id': 'The database ID of the registration (e.g. 12345)',
        'registration_form_id': 'The ID of the registration form (e.g. 12345)',
        'registration_form_title': 'The title of the registration form',
        'registration_id': 'The ID of the registration (e.g. 12345)',
        'user_firstname': 'First name of the registrant',
        'user_lastname': 'Last name of the registrant',
    }
    
    id_safe_field_descriptions = {
        'event_id': 'The ID of the event (e.g. 12345)',
        'registration_db_id': 'The database ID of the registration (e.g. 12345)',
        'registration_form_id': 'The ID of the registration form (e.g. 12345)',
        'registration_id': 'The ID of the registration (e.g. 12345)',
    }
    
    def __init__(self, max_length=float('inf'), id_safe=False):
        """Format field validator, i.e. strings with ``{key}`` placeholders.

        :param max_length: optional maximum length,
                           checked on a test formatting
        :param field_map: keyword arguments to use for test formatting
        :param id_safe: only allow fields safe for a eximbay id argument
        """
        self.max_length = max_length
        self.id_safe = id_safe
        self.field_map = self.id_safe_field_map if id_safe else self.default_field_map

    def __call__(self, form, field):
        """Validate format field data.

        Returns true on successful validation, else an ValidationError is
        thrown.
        """
        if not field.data:
            return True
        
        try:
            test_format = field.data.format(**self.field_map)
        except KeyError as exc:
            raise ValidationError(_('Invalid format string key: {}').format(exc))
        except ValueError as exc:
            raise ValidationError(_('Malformed format string: {}').format(exc))
        
        if len(test_format) > self.max_length:
            raise ValidationError(
                _('Format string too long: shortest replacement with {len}, expected {max}')
                .format(len=len(test_format), max=self.max_length)
            )
        
        if self.id_safe and not re.match(r'^[A-Za-z0-9.:_-]+$', test_format):
            raise ValidationError(_('This field may only contain alphanumeric chars, dots, colons, '
                                    'hyphens and underscores.'))
        
        return True


class PluginSettingsForm(PaymentPluginSettingsFormBase):
    """Configuration form for the Plugin across all events."""

    url = URLField(
        label=_('API URL'),
        validators=[DataRequired()],
        description=_(
            'Default URL to connect the Eximbay Payment Service for v2.3</br>'
            '<i>* Note: API Key authentication is not supported.</i>'
            '<div><ul style="margin:0;">'
            '<li>Service server: <u>https://api.eximbay.com</u><br>'
            '<i>* Use the issued <b>MID</b> and <b>Secret Key</b> after contract.</i>'
            '</li>'
            '<li>Test server: <u>https://api-test.eximbay.com</u></li>'
            '</ul>'
            '</div>'
            '*Event managers will be able to override this.'
        ),
    )
    account_id = StringField(
        label=_('MID #1'),
        validators=[
            Optional(),
            IndicoRegexp(r'^[A-Z0-9]{10}$', message='Field must contain up to 10 digits and alphabets.')
        ],
        description=_(
            'Default Eximbay MID (Merchant ID) for Domestic Credit Cards: 10 characters.'
            '*Event managers will be able to override this.'
        )
    )
    account_key = StringField(
        label=_('API Key #1'),
        validators=[
            Optional(),
            IndicoRegexp(r'^[A-Z0-9_]{25}$', message='Field must contain with 25 digits and alphabets and underscore.')
        ],
        description=_(
            'Default Secret key for Eximbay Domestic Credit MID (25 characters).<br>'
            '*Event managers will be able to override this.'
        )
    )
    account_id2 = StringField(
        label=_('MID #2'),
        validators=[
            Optional(),
            IndicoRegexp(r'^[A-Z0-9]{10}$', message='Field must contain up to 10 digits and alphabets.')
        ],
        description=_(
            'Default Eximbay MID (Merchant ID) for Global Credit Cards (10 characters).<br>'
            '*Event managers will be able to override this.'
        )
    )
    account_key2 = StringField(
        label=_('API Key #2'),
        validators=[
            Optional(),
            IndicoRegexp(r'^[A-Z0-9_]{25}$', message='Field must contain with 25 digits and alphabets and underscore.')
        ],
        description=_(
            'Default Secret key for Eximbay Global Credit MID (25 characters).<br>'
            '*Event managers will be able to override this.'
        )
    )
    order_description = StringField(
        label=_('Order Description'),
        validators=[DataRequired(), FormatField(max_length=100)],
        description=render_placeholders((
            'The default description of each order in a human readable way (max. 100 chars).<br>'
            'It is presented to the registrant during the transaction with Eximbay.<br>'
            '*Event managers will be able to override this. '
        ), **FormatField.default_field_descriptions)
    )
    order_identifier = StringField(
        label=_('Order Identifier'),
        validators=[DataRequired(), FormatField(max_length=30, id_safe=True)],
        description=render_placeholders((
            'The default identifier of each order for further processing (max. 30 chars).<br>'
            'Event managers will be able to override this.<br>'
        ), **FormatField.id_safe_field_descriptions)
    )
    announcement = StringField(
        label=_('Announcement'),
        validators=[Optional(), FormatField(max_length=100)],
        description=_(
            'Default notification message on the Payment Page'
            '*Event managers will be able to override this.'
        )
    )
    notification_mail = StringField(
        label=_('Notification Email'),
        validators=[Optional(), Email(), Length(0, 50)],
        description=render_placeholders((
            'Email address to receive notifications of failed transactions.<br>'
            "This is independent of Indico's own payment notifications.<br>"
            '*Event managers will be able to override this.'
        ))
    )


class EventSettingsForm(PaymentEventSettingsFormBase):
    """Configuration form for the plugin for a specific event."""

    url = URLField(
        label=_('API URL'),
        validators=[DataRequired()],
        description=render_placeholders((
            'URL to connect the Eximbay Payment Service for v2.3</br>'
            '<i>* Note: API Key authentication is not supported.</i>'
            '<div><ul style="margin:0;">'
            '<li>Service server: <u>https://api.eximbay.com</u><br>'
            '<i>* Use the issued <b>MID</b> and <b>Secret Key</b> after contract.</i>'
            '</li>'
            '<li>Test server: <u>https://api-test.eximbay.com</u></li>'
            '<ul>'
            '<li>Test MID: <code>1849705C64</code></li>'
            '<li>Test API Key: <code>test_1849705C642C217E0B2D</code></li>'
            '</ul>'
            '</ul>'
            '</div>'
            )
        ),
    )
    account_id = StringField(
        label=_('MID #1'),
        validators=[
            Optional(),
            IndicoRegexp(r'^[A-Z0-9]{10}$', message='Field must contain up to 10 digits and alphabets.')
        ],
        description=render_placeholders(
            'Eximbay MID (Merchant ID) for Domestic Credit Cards: 10 characters.'
        )
    )
    account_key = IndicoPasswordField(
        label=_('API Key #1'),
        validators=[
            Optional(),
            IndicoRegexp(r'^[A-Z0-9_]{25}$', message='Field must contain with 25 digits and alphabets and underscore.')
        ],
        description=render_placeholders(
            'Secret key for Eximbay Domestic Credit MID (25 characters).'
        )
    )
    account_id2 = StringField(
        label=_('MID #2'),
        validators=[
            Optional(),
            IndicoRegexp(r'^[A-Z0-9]{10}$', message='Field must contain up to 10 digits and alphabets.')
        ],
        description=render_placeholders(
            'Eximbay MID (Merchant ID) for Global Credit Cards (10 characters).'
        )
    )
    account_key2 = IndicoPasswordField(
        label=_('API Key #2'),
        validators=[
            Optional(),
            IndicoRegexp(r'^[A-Z0-9_]{25}$', message='Field must contain with 25 digits and alphabets and underscore.')
        ],
        description=render_placeholders(
            'Secret key for Eximbay Global Credit MID (25 characters).'
        )
    )
    order_description = StringField(
        label=_('Order Description'),
        validators=[DataRequired(), FormatField(max_length=100)],
        description=render_placeholders((
            'The description of each order in a human readable way (max. 100 chars). '
            'It is presented to the registrant during the transaction with Eximbay.'
            ), **FormatField.default_field_descriptions)
    )
    order_identifier = StringField(
        label=_('Order Identifier'),
        validators=[DataRequired(), FormatField(max_length=30, id_safe=True)],
        description=render_placeholders((
            'The default identifier of each order for further processing (max. 30 chars).'
            ), **FormatField.id_safe_field_descriptions)
    )
    announcement = StringField(
        label=_('Announcement'),
        validators=[Optional(), FormatField(max_length=100)],
        description=_(
            'Notification Message on the Payment Page'
        )
    )
    notification_mail = StringField(
        label=_('Notification Email'),
        validators=[DataRequired(), Email(), Length(0, 50)],
        description=render_placeholders((
            'Email address to receive notifications of failed transactions. '
            "This is independent of Indico's own payment notifications.")
        )
    )
