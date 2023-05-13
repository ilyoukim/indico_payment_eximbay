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
from indico_payment_eximbay.util import (PROVIDER_EXIMBAY, EXIMBAY_PP_BASIC_URL, EXIMBAY_PP_DIRECT_URL,
                                         get_request_header, get_terminal_id, get_fgkey)


class TransactionFailure(Exception):
    """A transaction with Eximbay failed.

    :param step: name of the step at which the transaction failed
    :param details: verbose description of what went wrong
    """

    def __init__(self, step, details=None):
        self.step = step
        self.details = details


class RHEximbayBase(RH):
    """
    Request Handler for asynchronous callbacks from Eximbay

    These handlers are used either by

    - the user, when he is redirected from Eximbay back to Indico
    - Eximbay, when it sends back the result of a transaction
    """

    CSRF_ENABLED = False

    def _process_args(self):
        self.registration = Registration.query.filter_by(uuid=request.args['token']).first()
        if not self.registration:
            raise BadRequest
        try:
            self.token = self.registration.transaction.data['Init_PP_response']['Token']
        except KeyError:
            # if the transaction was already recorded as successful via background notification,
            # we no longer have a token in the local transaction
            self.token = None


class RHInitEximbayPayment(RHPaymentBase):
    def _get_transaction_parameters(self):
        """Get parameters for creating a transaction request."""
        settings = EximbayPaymentPlugin.event_settings.get_all(self.event)
        
        # security Key is not accurate
        if len(settings['account_securitykey']) < 20:
            raise KeyError
        
        format_map = {
            'user_id': self.registration.user_id,
            'user_name': self.registration.full_name,
            'user_firstname': self.registration.first_name,
            'user_lastname': self.registration.last_name,
            'frendly_id': self.registration.friendly_id,
            'event_id': self.registration.event_id,
            'event_title': self.registration.event.title,
            'registration_id': self.registration.id,
            'regform_title': self.registration.registration_form.title
        }
        order_description = settings['order_description'].format(**format_map)
        order_identifier = settings['order_identifier'].format(**format_map)
        
        # see the Eximbay Manual on what these things mean
        # where to asynchronously call back from Eximbay
        transaction_data = {
            'ver': '230',
            'txntype': 'PAYMENT',
            'charset': 'UTF-8',
            'ostype': 'P',                      # P:pc, M:mobile
            'displaytype': 'P',                 # P:popup, R:page redirect
            'paymethod': 'P000',                # Credit Card
            'mid': settings['account_id'],
            'lang': settings['language'],       # KR, EN, CN, JP
            'ref': order_identifier,            # orderId : unique value
            'amt': self.registration.price,
            'cur': self.registration.currency,
            'buyer': self.registration.full_name,
            'email': self.registration.email,
            'item_0_product': order_description,
            'item_0_unitPrice': self.registration.price,
            'item_0_quantity': '1',
            'returnurl': url_for_plugin('payment_eximbay.success', self.registration.locator.uuid, _external=True),
            'statusurl': url_for_plugin('payment_eximbay.notify', self.registration.locator.uuid, _external=True),
        }
        
        transaction_data['fgkey'] = get_fgkey(settings['account_securitykey'], transaction_data)
        
        # transaction_parameters = {
        #     'RequestHeader': EXIMBAY_PP_BASIC_URL,
        #     'TerminalId': get_terminal_id(settings['account_id']),
        #     'Payment': eximdata,
        #     # callbacks of the transaction - where to announce success etc., when redircting the user
        #     'ReturnUrls': {
        #         'Success': url_for_plugin('payment_sixpay.success', self.registration.locator.uuid, _external=True),
        #         # 'Fail': url_for_plugin('payment_sixpay.failure', self.registration.locator.uuid, _external=True),
        #         # 'Abort': url_for_plugin('payment_sixpay.cancel', self.registration.locator.uuid, _external=True)
        #     },
        #     'Notification': {
        #         # where to asynchronously call back from SIXPay
        #         'NotifyUrl': url_for_plugin('payment_sixpay.notify', self.registration.locator.uuid, _external=True)
        #     }
        # }
        
        # return transaction_parameters
        return transaction_data

    def _init_payment_page(self, transaction_data):
        """Initialize payment page."""
        endpoint = urljoin(EximbayPaymentPlugin.settings.get('url'), EXIMBAY_PP_BASIC_URL)
        resp = requests.post(url=endpoint, data=transaction_data, timeout=5)
        try:
            resp.raise_for_status()
        except RequestException as exc:
            EximbayPaymentPlugin.logger.error('Could not initialize payment: %s', exc.response.text)
            raise Exception('Could not initialize payment')
        return resp

    def _process_args(self):
        RHPaymentBase._process_args(self)
        if 'eximbay' not in get_active_payment_plugins(self.event):
            raise NotFound
        if not EximbayPaymentPlugin.instance.supports_currency(self.registration.currency):
            raise BadRequest

    def _process(self):
        transaction_params = self._get_transaction_parameters()
        init_response = self._init_payment_page(transaction_params)
        # payment_url = init_response['RedirectUrl']

        # create pending transaction and store Saferpay transaction token
        new_indico_txn = register_transaction(
            registration = self.registration,
            amount = self.registration.price,
            currency = self.registration.currency,
            action = TransactionAction.pending,
            provider = PROVIDER_EXIMBAY,
            data = {'Init_PP_response': init_response}
        )
        if not new_indico_txn:
            # set it on the current transaction if we could not create a next one
            # this happens if we already have a pending transaction and it's incredibly
            # ugly...
            self.registration.transaction.data = {'Init_PP_response': init_response}
        # return redirect(payment_url)



class RHEximbayIPN(RHEximbayBase):
    """Handler for notification from Eximbay service"""

    def _process(self):
        """process the reply from Eximbay about the transaction."""
        if self.token is not None:
            self._process_confirmation()

    def _process_confirmation(self):
        """Process the confirmation response inside indico."""
        # assert transaction status from Eximbay
        assert_response = self._assert_payment()
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
    
    def _assert_payment(self):
        """Check the status of the transaction with Eximbay.
        
        post = {
           'ver': '230',
           'txntype': 'PAYMENT',
           'mid': '1849705C64',
           'payto': 'EXIMBAY.COM',
           'ref': 'item_buy_unique',
           'amt': '10000',
           'cur': 'KRW',
           'accesscountry': 'KR',
           'paymethod': 'P101',
           'cardholder': 'NAME',
           'email': 'xxx@xxx.xx',
           'cardno1': '4111',
           'cardno4': '1111',
           'resdt': '20191030145148',
           'transid': { 24 digit & alphabetics },
           'authcode': '881693',
           'rescode': '0000',
           'resmsg': 'Success.',
           'fgkey': { length : 64 characters },
           'baseamt': '',
           'basecur': '',
           'baserate': '',
           'foreignamt': '',
           'foreigncur': '',
           'foreignrate': '',
           'dccrate': '',
           'dm_decision': '',
           'dm_review': '',
           'dm_reject': '',
           'param1': '',
           'param2': '',
           'param3': '',
        }
        
        Returns transaction assert data.
        """
        return request.form
    
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
        
        response = self._perform_request('confirm', EXIMBAY_PP_DIRECT_URL, data)
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


class UserCancelHandler(RHEximbayBase):
    """User Message on cancelled payment"""
    def _process(self):
        register_transaction(
            registration = self.registration,
            amount = self.registration.transaction.amount,
            currency = self.registration.transaction.currency,
            # XXX: this is indeed reject and not cancel (cancel is "mark as unpaid" and
            # only used for manual transactions)
            action = TransactionAction.reject,
            provider=PROVIDER_EXIMBAY,
        )
        flash(_('You cancelled the payment.'), 'info')
        return redirect(url_for('event_registration.display_regform', self.registration.locator.registrant))


class UserFailureHandler(RHEximbayBase):
    """User Message on failed payment"""
    def _process(self):
        register_transaction(
            registration = self.registration,
            amount = self.registration.transaction.amount,
            currency = self.registration.transaction.currency,
            action = TransactionAction.reject,
            provider=PROVIDER_EXIMBAY,
        )
        flash(_('Your payment has failed.'), 'info')
        return redirect(url_for('event_registration.display_regform', self.registration.locator.registrant))


class UserSuccessHandler(RHEximbayIPN):
    """User redirect target in case of successful payment."""
    
    def _process(self):
        try:
            if self.token is not None:
                self._process_confirmation()
        except TransactionFailure as err:
            # EximbayPaymentPlugin.logger.warning("Eximbay transaction failed during %s: %s" % (err.step, err.details))
            flash(_('Your payment could not be confirmed. Please contact an organizer.'), 'info')
        else:
            flash(_('Your payment has been confirmed.'), 'success')
        return redirect(url_for('event_registration.display_regform', self.registration.locator.registrant))
