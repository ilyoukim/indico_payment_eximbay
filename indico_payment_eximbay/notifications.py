# This file is part of Indico.
# Copyright (C) 2002 - 2023 CERN
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
    # to_list = event.creator.email
    
    with event.creator.force_user_locale():
        tpl = get_template_module('payment_eximbay:emails/payment_account_error_notify.html',
                                  event=event, registration=registration, data=data)
        return make_email(to_address, template=tpl, html=True)

@email_sender
def notify_payment_error_manager(registration, data, to_address):
    ## minimum params
    keys = ['ref','amt','cur','accesscountry','paymethod','email','resdt','transid','rescode','resmsg']
    
    newdata = {}
    for key in data:
        if key in keys:
            newdata[key] = data.get(key)
    
    event = registration.registration_form.event
    paymethod = get_paymethod(data['paymethod'])

    with event.creator.force_user_locale():
        tpl = get_template_module('payment_eximbay:emails/payment_error_notify_manager.html',
                                  event=event, registration=registration, data=newdata,
                                  paymethod=paymethod, errCode=data['rescode'], errMsg=data['resmsg'])
        return make_email(to_address, template=tpl, html=True)

@email_sender
def notify_payment_error_register(registration, data):
    event = registration.registration_form.event
    to_list = (registration.email, data.get('email'))
    to_list = list(set(to_list))
    
    paymethod = get_paymethod(data['paymethod'])
    
    with event.creator.force_user_locale():
        tpl = get_template_module('payment_eximbay:emails/payment_error_notify_register.html',
                                  event=event, registration=registration, data=data,
                                  paymethod=paymethod, errCode=data['rescode'], errMsg=data['resmsg'])
        return make_email(to_list, template=tpl, html=True)
