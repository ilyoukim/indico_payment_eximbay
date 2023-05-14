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
Callbacks for asynchronous replies by the Eximbay service and to redirect the user
"""
import json
import time
from urllib.parse import urljoin, parse_qsl, urlsplit

import requests
from flask import flash, redirect, request
from requests import RequestException
from werkzeug.exceptions import BadRequest, NotFound
from werkzeug.exceptions import NotImplemented as HTTPNotImplemented

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
from indico_payment_eximbay.util import (PROVIDER_EXIMBAY, EXIMBAY_PP_BASIC_URL, EXIMBAY_PP_DIRECT_URL, get_fgkey)


class TransactionFailure(Exception):
    """A transaction with Eximbay failed.

    :param step: name of the step at which the transaction failed
    :param details: verbose description of what went wrong
    """

    def __init__(self, step, details=None):
        self.step = step
        self.details = details


class RHEximbayIPN(RH):
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

    def _process_confirmation(self):
        """Process the confirmation response inside indico.
        
        Assert transaction status from Eximbay
        """
        assert_response = request.form
        try:
            # verify the signature of Eximbay for the transaction
            self._verify_signature(assert_response)
            if self._is_duplicate_transaction(assert_response):
                # we have already handled the transaction
                return
            elif self._confirm_transaction(assert_response):
                # if this matches, the user completed the transaction as requested by Indico
                self._verify_amount(assert_response)
                self._register_payment(assert_response)
        except TransactionFailure as err:
            EximbayPaymentPlugin.logger.warning("Eximbay transaction failed during %s: %s", err.step, err.details)
            raise
    
    def _perform_request(self, endpoint, **kwargs):
        """
        Helper for performing a request against Eximbay

        :param task: description of the request, used for error handling
        :type task: basestring
        :param endpoint: the URL endpoint *relative* to the Eximbay base URL
        :type endpoint: basestring
        :param **kwargs: kwargs passed during the request

        This will automatically raise any HTTP errors encountered during the request.
        If the request itself fails, a :py:exc:`~.TransactionFailure` is raised for ``task``.
        """
        data = {
            'ver': '230',
            'txntype': 'QUERY',
            'charset': 'UTF-8',
            'mid': self.eximbay_account
        }
        data.update(kwargs)
        data['fgkey'] = get_fgkey(self.eximbay_securitykey, data)
        
        request_url = urljoin(self.eximbay_url, endpoint)
        try:
            response = requests.post(url=request_url, data=data, timeout=5)
            response.raise_for_status()
        except request.RequestException as e:
            raise RuntimeError("request error : %r" % (e.respone))
        return response

    def _verify_signature(self, data):
        """Verify the transaction data and signature with Eximbay
        
        Check fgkey from data with securitykey
        """
        settings = EximbayPaymentPlugin.event_settings.get_all(self.event)
        
        if not settings['account_id'] == data['mid']:
            raise TransactionFailure(step='verification', details='mismatched account ID')
        
        if not data['rescode'] == '0000':
            raise TransactionFailure(step='verification', details='rescode is not %s' % data['rescode'])
        
        if not data['resmsg'] == 'Success.':
            raise TransactionFailure(step='verification', details='respone message is %s' % data['resmsg'])
        
        fgkey = get_fgkey(settings['account_securitykey'], data)
        if not fgkey == str(data['fgkey']):
            raise RuntimeError("Return hash key error : %r ... %r" % (fgkey, data))
    
    def _is_duplicate_transaction(self, transaction_data):
        """Check if this transaction has already been recorded"""
        
        prev_transaction = self.registration.transaction
        if (not prev_transaction or
            prev_transaction.provider != PROVIDER_EXIMBAY):
            return False
        
        old = prev_transaction.data
        new = transaction_data
        return (
            old['ref'] == new['ref'] and
            old['cur'] == new['cur'] and
            old['amt'] == new['amt'] and
            old['mid'] == new['mid']
        )

    def _confirm_transaction(self, assert_data):
        """Confirm to Eximbay server that the transaction is accepted
        3.2	Querying a Single Transaction
        """
        
        settings = EximbayPaymentPlugin.event_settings.get_all(self.event)
        
        completion_data = {}
        for key in ('ref', 'cur', 'amt', 'transid'):
            completion_data[key] = assert_data.get(key)
        
        data = {
            'ver': '230',
            'charset': 'UTF-8',
            'txntype': 'QUERY',
            'keyfield': 'TRANSID',
            'mid': settings['account_id'],
            'lang': settings['language'],
        }
        data.update(completion_data)
        data['fgkey'] = get_fgkey(settings['account_securitykey'], data)
        
        request_url = urljoin(self.eximbay_url, EXIMBAY_PP_DIRECT_URL)
        request_url = 'http://127.0.0.1:5000/quarks'
        try:
            response = requests.post(url=request_url, data=data, timeout=5)
            response.raise_for_status()
        except request.RequestException as e:
            raise RuntimeError("request error : %r" % (e.respone))
        
        try:
            res = dict(parse_qsl(urlsplit(response.text).path))
            if not res['rescode'] == '0000':
                raise TransactionFailure(step='confirm transaction', details=res['rescode'])
        except:
            raise TransactionFailure(step='response at confirm', details=response.text)
        assert res['status'] == 'SALE'
        return True

    def _verify_amount(self, assert_data):
        """Verify the amount and currency of the payment.
        
        Sends an email but still registers incorrect payments.
        """
        expected_amount = float(self.registration.price)
        expected_currency = self.registration.currency
        amount = float(assert_data['amt'])
        currency = assert_data['cur']
        if expected_amount == amount and expected_currency == currency:
            return True
        EximbayPaymentPlugin.logger.warning("Payment doesn't match events fee: %s %s != %s %s",
                                            amount, currency, expected_amount, expected_currency)
        notify_amount_inconsistency(self.registration, amount, currency)
        return False

    def _cancel_transaction(self, assert_data):
        """Inform Sixpay that the transaction is canceled.

        Cancel the transaction at Sixpay. This method is implemented but
        not used and tested yet.
        """
        return None
    
    def _register_payment(self, assert_data):
        """Register the transaction as paid."""
        register_transaction(
            registration = self.registration,
            amount = self.registration.transaction.amount,
            currency = self.registration.transaction.currency,
            action = TransactionAction.complete,
            provider = PROVIDER_EXIMBAY,
            data=assert_data
        )


class RHEximbayReturn(RHEximbayIPN):
    """Confirmation message after successful payment"""

    def _process(self):
        # flash(_('Your payment request has been processed.'), 'return')
        return redirect(url_for('event_registration.display_regform', self.registration.locator.registrant))
