# This file is part of Indico.
# Copyright (C) 2002 - 2024 CERN
#
# Indico is free software; you can redistribute it and/or
# modify it under the terms of the MIT License; see the
# LICENSE file for more details.

from indico.core.notifications import email_sender, make_email
from indico.web.flask.templating import get_template_module

from indico_payment_eximbay.util import get_paymethod

@email_sender
def notify_account_error(registration, data, to_address):
    event = registration.registration_form.event
    # to_address = event.creator.email
    
    with event.creator.force_user_locale():
        tpl = get_template_module('payment_eximbay:emails/account_error_notify.html',
                                  event=event, registration=registration, data=data)
        return make_email(to_address, template=tpl, html=True)

@email_sender
def notify_payment_error(registration, data, to_address=None):
    # Define the allowed keys for the notification data
    allowed_keys = {
        'order_id', 'amount', 'currency', 'access_country', 'email',
        'payment_method', 'transaction_date', 'transaction_id',
        'card_holder', 'card_number4', 'auth_code',
        'rescode', 'resmsg'
    }

    # Filter the input data to include only allowed keys
    newdata = {key: data.get(key, '') for key in allowed_keys}
    
    event = registration.registration_form.event
    
    paymethod = get_paymethod(data.get('payment_method',''))

    if to_address:
        template_file = 'payment_error_notify_manager.html'
    else:
        template_file = 'payment_error_notify_register.html'
        to_address = (registration.email, data.get('email'))
        to_address = list(set(to_address))
    
    with event.creator.force_user_locale():
        tpl = get_template_module('payment_eximbay:emails/' + template_file,
                                    event=event, registration=registration, data=newdata,
                                    paymethod=paymethod, orderID=data.get('order_id',''),
                                    errCode=data.get('rescode',''), errMsg=data.get('resmsg',''))
        return make_email(to_address, template=tpl, html=True)
