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
Callbacks for asynchronous replies by the Eximbay service and to redirect the user
"""

from datetime import datetime
import json
import requests
from urllib.parse import urljoin

from flask import flash, jsonify,redirect, request
from flask_pluginengine import current_plugin, render_template

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
from indico_payment_eximbay.plugin import EximbayPaymentPlugin
from indico_payment_eximbay.util import (PROVIDER_EXIMBAY, EXIMBAY_SDK_URL,
                                         EXIMBAY_READY_URL, EXIMBAY_VERIFY_URL,
                                         get_request_header)
from indico_payment_eximbay.notifications import (notify_payment_error,
                                                  notify_account_error)


class TransactionFailure(Exception):
    """A transaction with Eximbay failed.

    :param step: name of the step at which the transaction failed
    :param details: verbose description of what went wrong
    """

    def __init__(self, step, details=None):
        self.step = step
        self.details = details



class RHInitEximbayPayment(RHPaymentBase):

    def _get_fgkey(self, api_url, api_key, data):
        # url = "https://api-test.eximbay.com/v1/payments/ready"
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

    def _get_transaction_parameters(self, isKor):
       # event = data['event']
        # registration = data['registration']
        # settings = data['settings']
        event_settings = EximbayPaymentPlugin.event_settings.get_all(self.event)

        api_url = event_settings.get('url')
        
        if isKor:
            mid = event_settings.get('account_id', None)
            api_key = event_settings.get('account_key', None)
        else:
            mid == event_settings.get('account_id2', None)
            api_key = event_settings.get('account_key2', None)
        
        # check security Key validation
        if isinstance(api_key, str) and len(api_key) < 25:
            pass
        else:
            None
        
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

        # max 30 characters
        order_id = "{0}_{1:%m%d%H%M%S}".format(order_identifier, datetime.now())[:30]
        
        # see the Eximbay Manual on what these things mean
        # where to asynchronously call back from Eximbay
        transaction_parameters = {
            "merchant": {
                "mid": mid,                                     # merchant ID
            },
            "payment": {
                "transaction_type": "PAYMENT",
                "payment_method": "P000",
                "lang": "EN",
                "order_id": order_id,                           # orderId : unique value (30 char)
                "currency": self.registration.currency,
                "amount": str(self.registration.price),         # total price
            },
            "buyer": {
                "name": self.registration.full_name,
                "email": self.registration.email,
            },
            "product": [{
                "name": order_description,
                "unit_price": str(self.registration.price),
                "quantity": str(1),
                "link":""                                       # open marker일 경우 필수라고 하는데 확인이 필요함
            }],
            "url": {
                "return_url": url_for_plugin('payment_eximbay.return', self.registration.locator.uuid, _external=True),
                "status_url": url_for_plugin('payment_eximbay.notify', self.registration.locator.uuid, _external=True),
            },
            "settings": {
                "display_type": "R",
            },
        }

        # Korea Domestic Card
        if isKor:
            transaction_parameters['payment']['lang'] = 'KR'
            transaction_parameters['settings']['issuer_country'] = 'KR'
        
        transaction_parameters['fgkey'] = self._get_fgkey(api_url, api_key, transaction_parameters)

        return transaction_parameters
    
    def _generate_page(self, transaction_data):
        """Initialize payment page to connect eximbay payment redirect
        """
        htmlTemplate = """
            <!doctype html>
            <html>
            <body>
            <script type="text/javascript" src="{{ eximbay_sdk_url }}"></script>
            <script type="text/javascript">
                function payment() {
                    EXIMBAY.request_pay("{{ trans_data | tojson }}");
                }
            </script>
            <p>TEST</p>
            </body>
            </html>
            """
    
        # <script>
        #     window.onload = payment;
        # </script>
        data = {
            "sdk_url": EXIMBAY_SDK_URL,
            "data": transaction_data,
            }
        html = render_template(htmlTemplate, **data)
        return html

    def _init_payment_page(self, transaction_data):
        """Initialize payment page to connect eximbay payment redirect
        """
        request_url = urljoin(EximbayPaymentPlugin.settings.get('url'), EXIMBAY_READY_URL)

        resp = requests.post(request_url, headers="", json=transaction_data)
        try:
            resp.raise_for_status()
        except request.RequestException as exc:
            EximbayPaymentPlugin.logger.error('Could not initialize payment: %s', exc.response.text)
            raise Exception('Could not initialize payment')
        return resp.json()

    def _process_args(self):
        RHPaymentBase._process_args(self)
        if 'eximbay' not in get_active_payment_plugins(self.event):
            raise NotFound

    def _process(self):
        isKor = request.args.get('country','') == "KR"
        
        transaction_params = self._get_transaction_parameters(isKor)
        
        html = self._generate_page(transaction_params)
        # html_template = self._init_payment_page(transaction_params)

        # return redirect(payment_url)
        return jsonify(html=html)



class RHEximbayNotify(RH):
    """Handler for notification from Eximbay service"""

    CSRF_ENABLED = False

    def _process_args(self):
        self.token = request.args['token']
        self.registration = Registration.query.filter_by(uuid=self.token).first()
        if not self.registration:
            raise BadRequest

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
        
        Check mid from data which is include settings
        """
        settings = current_plugin.event_settings.get_all(self.registration.registration_form.event)
        
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
        """
        response = self._perform_request('verify', EXIMBAY_VERIFY_URL, assert_data)
        res = json.load(response.text)
        
        resCode0 = res.get('rescode','').strip()
        resCode1 = assert_data.get('rescode','').strip()

        if resCode0 == resCode1 == '0000':
            return True
        
        settings = current_plugin.event_settings.get_all(self.registration.registration_form.event)
        manager_email = settings.get('notification_mail')
        
        notify_payment_error(self.registration, assert_data, manager_email)
        notify_payment_error(self.registration, assert_data)
        
        return False

    def _verify_amount(self, assert_data):
        """Verify the amount and currency of the payment.

        Sends an email but still registers incorrect payments.
        """
        expected_amount = float(self.registration.price)
        expected_currency = self.registration.currency
        amount = float(assert_data['amount'])
        currency = assert_data.get['currency']
        
        if expected_amount == amount and expected_currency == currency:
            return True
        else:
            current_plugin.logger.warning("Payment doesn't match event's fee: %s %s != %s %s",
                                            amount, currency, expected_amount, expected_currency)
            
            notify_amount_inconsistency(self.registration, amount, currency)
            
            return False

    def _register_payment(self, assert_data):
        """Register the transaction as paid."""
        # check transaction with actual transaction with payment url
        settings = current_plugin.event_settings.get_all(self.registration.registration_form.event)
        
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
        
        store_data['valid_trans'] = valid_trans
        
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
        settings = current_plugin.event_settings.get_all(self.registration.registration_form.event)
        
        api_url = settings.get('url')

        res_mid = data.get('mid', '')
        mid1 = settings.get('account_id', None)
        mid2 = settings.get('account_id2', None)

        if res_mid == mid1:
            api_key = settings.get('account_key', None)
        elif res_mid == mid2:
            api_key = settings.get('account_key2', None)
        else:
            raise TransactionFailure(step=task, details="mid error")
        
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


class RHEximbayReturn(RH):
    """Confirmation message after payment"""

    CSRF_ENABLED = False

    def _process_args(self):
        self.token = request.args['token']
        try:
            if self.token is not None:
                pass
        except TransactionFailure:
            flash(_('Your payment could not be confirmed. Please contact the event organizers.'), 'warning')
        
        self.registration = Registration.query.filter_by(uuid=self.token).first()
        if not self.registration:
            raise BadRequest

    def _process(self):
        transaction = self.registration.transaction
        try:
            if hasattr(transaction, 'status') and \
                transaction.status == TransactionStatus.successful:
                flash(_('Your payment has been confirmed.'), 'success')
            else:
                flash(_('Your payment has failed.'), 'info')
        except TransactionFailure:
            flash(_('Your payment has failed.'), 'error')
        
        return redirect(url_for('event_registration.display_regform', self.registration.locator.registrant))
