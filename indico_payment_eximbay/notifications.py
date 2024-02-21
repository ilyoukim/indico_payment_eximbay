# This file is part of Indico.
# Copyright (C) 2002 - 2023 CERN
#
# Indico is free software; you can redistribute it and/or
# modify it under the terms of the MIT License; see the
# LICENSE file for more details.

from indico.core.notifications import email_sender, make_email
from indico.web.flask.templating import get_template_module


def notify_payment_error(registration, data):
    notify_payment_error_manager(registration, data)
    notify_payment_error_register(registration, data)

@email_sender
def notify_payment_error_manager(registration, data):
    event = registration.registration_form.event
    to_list = event.creator.email
    
    with event.creator.force_user_locale():
        tpl = get_template_module('payment_eximbay:emails/payment_error_notify_manager.html',
                                  event=event, registration=registration, data=data,
                                  errCode=data['rescode'], errMsg=data['resmsg'])
        return make_email(to_list, template=tpl, html=True)

@email_sender
def notify_payment_error_register(registration, data):
    event = registration.registration_form.event
    to_list = registration.email
    to_list = registration.email
    
    with event.creator.force_user_locale():
        tpl = get_template_module('payment_eximbay:emails/payment_error_notify_register.html',
                                  event=event, registration=registration, data=data,
                                  errCode=data['rescode'], errMsg=data['resmsg'])
        return make_email(to_list, template=tpl, html=True)

# @email_sender
# def notify_amount_inconsistency(registration, amount, currency):
#     event = registration.registration_form.event
#     to = event.creator.email
#     with event.creator.force_user_locale():
#         tpl = get_template_module('events/payment/emails/error_notify.txt',
#                                   event=event, registration=registration, amount=amount, currency=currency)
#         return make_email(to, template=tpl)
