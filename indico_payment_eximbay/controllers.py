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
Callbacks for asynchronous replies by the Eximbay service and to redirect the user
"""

import json
import requests
from datetime import datetime
from urllib.parse import urljoin

from flask import flash, redirect, request, render_template_string
from flask_pluginengine import current_plugin

from werkzeug.exceptions import BadRequest, NotFound

from indico.core.plugins import url_for_plugin
from indico.modules.events.payment.controllers import RHPaymentBase
from indico.modules.events.payment.models.transactions import TransactionAction
from indico.modules.events.payment.notifications import notify_amount_inconsistency
from indico.modules.events.payment.util import TransactionStatus, get_active_payment_plugins, register_transaction
from indico.modules.events.registration.models.registrations import Registration
from indico.web.flask.util import url_for
from indico.web.rh import RH

from indico_payment_eximbay import _
from indico_payment_eximbay.util import (PROVIDER_EXIMBAY, EXIMBAY_SDK_URL,
                                         EXIMBAY_READY_URL, EXIMBAY_VERIFY_URL,
                                         get_request_header)
from indico_payment_eximbay.notifications import notify_account_error, notify_payment_error


class TransactionFailure(Exception):
    """A transaction with Eximbay failed.

    :param step: name of the step at which the transaction failed
    :param details: verbose description of what went wrong
    """

    def __init__(self, step, details=None):
        self.step = step
        self.details = details


class RHEximbayBase(RH):
    """Request Handler for asynchronous callbacks from Eximbay.

    These handlers are used either by

    - the user, when he is redirected from Eximbay back to Indico
    - Eximbay, when it sends back the result of a transaction
    """

    CSRF_ENABLED = False

    def _process_args(self):
        self.registration = Registration.query.filter_by(uuid=request.args['token']).first()
        if not self.registration:
            raise BadRequest


class RHInitEximbayPayment(RHPaymentBase):
    """Handler for initial to use Eximbay service"""

    def _get_fgkey(self, api_url, api_key, data):
        """
        # https://developer.eximbay.com/eximbay/payment_linkage/preparing-fgkey.html
        """
        request_url = urljoin(api_url, EXIMBAY_READY_URL)
        
        headers = get_request_header(api_key)

        try:
            response = requests.post(url=request_url, headers=headers, data=json.dumps(data), timeout=5)
            response.raise_for_status()
            recv = response.json()
        except requests.HTTPError:
            raise TransactionFailure(step='ready', details=response.text)
        
        resCode = recv.get("rescode", "").strip()
        resMsg = recv.get("resmsg", "").strip()

        if resCode == "0000" and resMsg == "Success":
            return recv.get("fgkey", "").strip()
        else:
            raise TransactionFailure(step='ready', details=response.text)

    def _get_transaction_parameters(self, params):
        """Get parameters for creating a transaction request."""
        event_settings = current_plugin.event_settings.get_all(self.event)

        api_url = event_settings.get('url')

        is_korean = params.get('issuer_country') == "KR"

        if is_korean:
            mid = event_settings.get('account_id', None)
            api_key = event_settings.get('account_key', None)
        else:
            mid = event_settings.get('account_id2', None)
            api_key = event_settings.get('account_key2', None)
        
        # check API Key validation
        if api_key and len(api_key) == 25:
            pass
        else:
            return None
        
        format_map = {
            'user_id': self.registration.user_id,
            'event_id': self.registration.event_id,
            'event_title': self.registration.event.title,
            'registration_form_id': self.registration.registration_form_id,
            'registration_form_title': self.registration.registration_form.title,
            'registration_db_id': self.registration.id,
            'registration_id': self.registration.friendly_id,
            'user_firstname': self.registration.first_name,
            'user_lastname': self.registration.last_name,
        }
        order_description = event_settings['order_description'].format(**format_map)
        order_identifier = event_settings['order_identifier'].format(**format_map)

        # see the Eximbay Manual on what these things mean
        # where to asynchronously call back from Eximbay
        # https://developer.eximbay.com/eximbay/api_list/reference.html#create_FGkey
        transaction_params = {
            "merchant": {
                "mid": mid,                                     # merchant ID
            },
            "payment": {
                "transaction_type": "PAYMENT",
                "payment_method": "P000",                       # P000: Credit Card
                "lang": "EN",                                   # default: EN
                "order_id": order_identifier[:30],              # orderId : unique value (max. 30 char)
                "currency": self.registration.currency,         # currency: USD, EUR, KRW ...
                "amount": str(self.registration.price),         # total price > 0
            },
            "buyer": {
                "name": self.registration.full_name,
                "email": self.registration.email,
            },
            "product": [{
                "name": order_description[:255],                # product name: max 255 char
                "unit_price": str(self.registration.price),     # product price > 0
                "quantity": str(1),                             # product quantity > 0
            }],
            "url": {
                "return_url": url_for_plugin('payment_eximbay.return', self.registration.locator.uuid, _external=True),
                "status_url": url_for_plugin('payment_eximbay.notify', self.registration.locator.uuid, _external=True),
            },
            "settings": {
                "display_type": "R",                            # R: redirect, P: popup
            },
        }

        # Korea Domestic Card
        if is_korean:
            transaction_params['payment']['lang'] = 'KR'
            transaction_params['settings']['issuer_country'] = 'KR'
        
        transaction_params['fgkey'] = self._get_fgkey(api_url, api_key, transaction_params)

        return transaction_params
    
    def _generate_page(self, request_data):
        """Initialize payment page to connect eximbay payment redirect
        """
        htmlTemplate = """
            <!doctype html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <link rel="icon" href="data:,">
                <script type="text/javascript" src="{{ sdk_url }}"></script>
                <script type="text/javascript">
                    const EXIMBAY_PAYLOAD = {{ data | tojson }};

                    function payment() {
                        EXIMBAY.request_pay(EXIMBAY_PAYLOAD);
                    }
                    
                    (function run() {
                    if (document.readyState !== "loading") {
                        // DOM already parsed → run immediately
                        payment();
                    } else {
                        // Wait until DOM is ready
                        document.addEventListener("DOMContentLoaded", payment, { once: true });
                    }
                    })();
                </script>
            </head>
            </html>
            """
    
        sdk_url = urljoin(current_plugin.settings.get('url'), EXIMBAY_SDK_URL)
        data = { "sdk_url": sdk_url, "data": request_data }
        
        html = render_template_string(htmlTemplate, **data)

        return html

    # def _init_payment_page(self, transaction_data):
    #     """Initialize payment page to connect eximbay payment redirect
    #     """
    #     request_url = urljoin(current_plugin.settings.get('url'), EXIMBAY_READY_URL)

    #     resp = requests.post(request_url, headers="", json=transaction_data)
    #     try:
    #         resp.raise_for_status()
    #     except request.RequestException as exc:
    #         current_plugin.logger.error('Could not initialize payment: %s', exc.response.text)
    #         raise Exception('Could not initialize payment')
    #     return resp.json()

    def _process_args(self):
        super()._process_args()
        if 'eximbay' not in get_active_payment_plugins(self.event):
            raise NotFound

    def _process(self):
        transaction_data = self._get_transaction_parameters(request.args)
        
        html = self._generate_page(transaction_data)
        
        return html


class RHEximbayNotify(RHEximbayBase):
    """Handler for notification from Eximbay service"""

    def _process(self):
        """process the reply from Eximbay about the transaction."""
        if self.token is not None:
            self._process_confirmation()
        else:
            return redirect(url_for('event_registration.display_regform', self.registration.locator.registrant))

    def _process_confirmation(self):
        """Process the confirmation response inside indico.
        
        Assert transaction status from Eximbay
        """
        assert_response = request.form
        try:
            # we have already handled the transaction
            if self._is_duplicate_transaction(assert_response):
                return
            
            # check the mid, code, message
            if not self.is_authorized_transaction(assert_response):
                return
            
            # verify message with eximbay verify api
            if not self._verify_transaction(assert_response):
                # send error message to manager and register
                return
            
            # if this matches, the user completed the transaction as requested by Indico
            if not self._verify_amount(assert_response):
                return
            
            self._register_payment(assert_response)
        
        except TransactionFailure as err:
            current_plugin.logger.warning("Eximbay transaction failed during %s: %s", err.step, err.details)
            raise
    
    def _is_duplicate_transaction(self, transaction_data):
        """Check if this transaction has already been recorded"""
        prev_transaction = self.registration.transaction
        if (not prev_transaction or
            prev_transaction.provider != PROVIDER_EXIMBAY):
            return False
        
        old = prev_transaction.data
        new = transaction_data
        
        return (
                old['order_id'] == new['order_id'] and
                old['transaction_id'] == new['transaction_id']
            )

    def is_authorized_transaction(self, transaction_data):
        """Verify the transaction data
        
        https://developer.eximbay.com/eximbay/payment_linkage/preparing-fgkey.html#afterCalling
        """
        settings = current_plugin.event_settings.get_all(self.event)
        
        mids = [settings.get('account_id', None),
                settings.get('account_id2', None)]

        resCode = transaction_data.get('rescode','').strip()
        resMsg = transaction_data.get('resmsg','').strip()
        
        if transaction_data['mid'] in mids and \
            resCode == '0000' and resMsg == "Success":
            return True
        else:
            manager_email = settings.get('notification_mail')

            notify_account_error(self.registration, transaction_data, manager_email)
            return False
    
    def _verify_transaction(self, assert_data):
        """Verify transaction with Eximbay verify api
        
        https://developer.eximbay.com/eximbay/payment_linkage/preparing-fgkey.html#paymentVerify
        """
        response = self._perform_request('verify', EXIMBAY_VERIFY_URL, assert_data)
        res = json.load(response.text)
        
        resCode = res.get('rescode','').strip()

        if resCode == '0000':
            return True
        else:
            settings = current_plugin.event_settings.get_all(self.event)
            manager_email = settings.get('notification_mail')
            
            notify_payment_error(self.registration, assert_data, manager_email)
            notify_payment_error(self.registration, assert_data)
            
            return False

    def _verify_amount(self, assert_data):
        """Verify the amount and currency of the payment.

        Sends an email but still registers incorrect payments.
        """
        settings = current_plugin.event_settings.get_all(self.event)
        
        expected_amount = float(self.registration.price)
        expected_currency = self.registration.currency
        amount = float(assert_data['amount'])
        currency = assert_data['currency']
        
        if expected_amount == amount and expected_currency == currency:
            return True
        else:
            manager_email = settings.get('notification_mail')
            # current_plugin.logger.warning("Payment doesn't match event's fee: %s %s != %s %s",
            #                                 amount, currency, expected_amount, expected_currency)
            
            notify_amount_inconsistency(self.registration, amount, currency)
            notify_payment_error(self.registration, assert_data, manager_email)
            
            return False

    def _register_payment(self, assert_data):
        """Register the transaction as paid."""
        # check transaction with actual transaction with payment url
        settings = current_plugin.event_settings.get_all(self.event)
        
        api_url = settings.get('url')
        
        valid_trans = (api_url == "https://secureapi.eximbay.com")
        
        ## not necessary params
        except_keys = ['ver','transaction_type','mid',
                       'payment_method','email',
                       'card_holder','card_number1','card_number4',
                       'pay_to','fgkey'
                       ]
        
        store_data = {}
        for key in assert_data:
            if key not in except_keys:
                store_data[key] = assert_data.get(key)
        
        if not valid_trans:
            store_data['resmsg'] = "Transaction with the Test server."
        
        register_transaction(
            registration = self.registration,
            amount = float(assert_data.get('amount','0')),
            currency = assert_data.get('currency',''),
            action = TransactionAction.complete,
            provider = PROVIDER_EXIMBAY,
            data = {'Transaction': store_data}
        )

    def _perform_request(self, task, endpoint, data):
        """
        Helper for performing a request against Eximbay

        :param task: description of the request, used for error handling
        :type task: basestring
        :param endpoint: the URL endpoint *relative* to the Eximbay base URL
        :type endpoint: basestring
        :param data: data passed during the request

        This will automatically raise any HTTP errors encountered during the request.
        If the request itself fails, a :py:exc:`~.TransactionFailure` is raised for ``task``.
        
        3.2	Querying a Single Transaction
        """
        settings = current_plugin.event_settings.get_all(self.event)
        
        api_url = settings.get('url')

        res_mid = data.get('mid', '')
        mid1 = settings.get('account_id', None)
        mid2 = settings.get('account_id2', None)

        if res_mid == mid1:
            api_key = settings.get('account_key', None)
        elif res_mid == mid2:
            api_key = settings.get('account_key2', None)
        else:
            raise TransactionFailure(step=task, details="MID error")
        
        if api_key is None:
            raise TransactionFailure(step=task, details="Security Key error")
        
        request_url = urljoin(api_url, endpoint)

        headers = get_request_header(api_key)

        try:
            response = requests.post(url=request_url, headers=headers, data=json.dumps(data), timeout=5)
            response.raise_for_status()
        except requests.HTTPError:
            raise TransactionFailure(step=task, details=response.text)
        
        return response.json()


class RHEximbayReturn(RHEximbayBase):
    """Confirmation message after payment"""

    def _process(self):
        transaction = self.registration.transaction
        
        try:
            if hasattr(transaction, 'status') and \
                transaction.status == TransactionStatus.successful:
                flash(_('Your payment has been confirmed.'), 'success')
            # else:
            #     # issue: logout for development
            #     flash(_('Your payment has failed.'), 'info')
        except TransactionFailure:
            flash(_('Your payment has failed.'), 'error')
        
        return redirect(url_for('event_registration.display_regform', self.registration.locator.registrant))
