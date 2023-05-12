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
from indico_payment_eximbay.util import (PROVIDER_EXIMBAY, get_fgkey)



class TransactionFailure(Exception):
    """A transaction with Eximbay failed.

    :param step: name of the step at which the transaction failed
    :param details: verbose description of what went wrong
    """

    def __init__(self, step, details=None):
        self.step = step
        self.details = details


# RH from indico.web.rh
# - the logic to execute when Eximbay/Users are redirected *after* a transaction
# - see blueprint.py for how RH's are mounted!

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
        
        plugin_settings = settings['event_settings']
        registration = settings['registration']
        format_map = self.get_field_format_map(settings['registration'])
        fieldList = ['order_description', 'order_identifier','account_id', 'account_securitykey']
        for format_field in fieldList:
            try:
                if not plugin_settings.has_key(format_field):
                    raise KeyError
                settings[format_field] = plugin_settings.get(format_field).format(**format_map)
            except ValueError:
                message = "Invalid format field placeholder for {0}, please contact the event organisers!"
                raise HTTPNotImplemented((
                        _(message) + '\n\n[' + message + ']'
                    ).format(self.name)
                 )
            except KeyError:
                message = "Unknown format field placeholder '{0}' for {1}, please contact the event organisers!"
                raise HTTPNotImplemented((
                        _(message) + '\n\n[' + message + ']'
                    ).format(format_field, self.name)
                )
        
        # security Key is not accurate
        if len(settings['account_securitykey']) < 20:
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
            'mid': settings['account_id'],
            'ref': settings['order_identifier'],
            'amt': registration.price,
            'cur': registration.currency,
            'buyer': registration.full_name,
            'email': registration.email,
            'item_0_product': settings['order_description'],
            'item_0_unitPrice': registration.price,
            'item_0_quantity': '1',
            'returnurl': url_for_plugin('payment_eximbay.success', registration.locator.uuid, _external=True),
            'statusurl': url_for_plugin('payment_eximbay.notify', registration.locator.uuid, _external=True),
        }
        
        transaction_parameters['fgkey'] = get_fgkey(settings['account_securitykey'], transaction_parameters)
        return transaction_parameters

    def _init_payment_page(self, transaction_data):
        """Initialize payment page."""
        
        request_url = urljoin(self.eximbay_url, endpoint)
        response = requests.post(url=request_url, data=transaction_data, timeout=5)
        try:
            response.raise_for_status()
        except RequestException as exc:
            EximbayPaymentPlugin.logger.error('Could not initialize payment: %s', exc.response.text)
            raise Exception('Could not initialize payment')
        return response
    
    
        # prefer event supplied eximbay url over global eximbay url
        # check account exist : Eximbay is not supported
        self.eximbay_url = EximbayPaymentPlugin.settings.get(self.registration.registration_form.event, 'url') \
            or EximbayPaymentPlugin.settings.get('url')
        self.eximbay_account = EximbayPaymentPlugin.settings.get(self.registration.registration_form.event, 'account_id') \
            or EximbayPaymentPlugin.settings.get('account_id')
        self.eximbay_securitykey = EximbayPaymentPlugin.settings.get(self.registration.registration_form.event, 'account_securitykey') \
            or EximbayPaymentPlugin.settings.get('account_securitykey')

    def _process_args(self):
        RHPaymentBase._process_args(self)
        if 'eximbay' not in get_active_payment_plugins(self.event):
            raise NotFound
        if not EximbayPaymentPlugin.instance.supports_currency(self.registration.currency):
            raise BadRequest

    def _process(self):
        transaction_params = self._get_transaction_parameters()
        init_response = self._init_payment_page(transaction_params)
        payment_url = init_response['RedirectUrl']

        # create pending transaction and store Saferpay transaction token
        new_indico_txn = register_transaction(
            self.registration,
            self.registration.price,
            self.registration.currency,
            TransactionAction.pending,
            PROVIDER_EXIMBAY,
            {'Init_PP_response': init_response}
        )
        if not new_indico_txn:
            # set it on the current transaction if we could not create a next one
            # this happens if we already have a pending transaction and it's incredibly
            # ugly...
            self.registration.transaction.data = {'Init_PP_response': init_response}
        return redirect(payment_url)



class EximbayNotificationHandler(RHEximbayBase):
    """Handler for notification from Eximbay service"""

    def _process(self):
        """process the reply from Eximbay about the transaction"""
        if self.token is not None:
            self._process_confirmation()

    def _process_confirmation(self):
        """Process the confirmation response inside indico"""
        # assert transaction status from Eximbay
        try:
            assert_response = self._assert_payment()
            # verify the signature of Eximbay for the transaction
            self._verify_signature(assert_response)
            if self._is_duplicate_transaction(assert_response):
                # we have already handled the transaction
                return
            if self._confirm_transaction(assert_response):
                # if this matches, the user completed the transaction as requested by Indico
                self._verify_amount(assert_response)
                self._register_payment(assert_response)
        except TransactionFailure as err:
            EximbayPaymentPlugin.logger.warning("Eximbay transaction failed during %s: %s" % (err.step, err.details))
            raise
    
    def _perform_request(self, task, endpoint, **kwargs):
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
    
    def _assert_payment(self):
        """Check the status of the transaction with SIXPay.

        Returns transaction assert data.
        """
        #post = {
        #    'ver': '230',
        #    'txntype': 'PAYMENT',
        #    'mid': '1849705C64',
        #    'payto': 'EXIMBAY.COM',
        #    'ref': 'item_buy_unique',
        #    'amt': '10000',
        #    'cur': 'KRW',
        #    'accesscountry': 'KR',
        #    'paymethod': 'P101',
        #    'cardholder': 'NAME',
        #    'email': 'xxx@xxx.xx',
        #    'cardno1': '4111',
        #    'cardno4': '1111',
        #    'resdt': '20191030145148',
        #    'transid': { 24 digit & alphabetics },
        #    'authcode': '881693',
        #    'rescode': '0000',
        #    'resmsg': 'Success.',
        #    'fgkey': { length : 64 characters },
        #    'baseamt': '',
        #    'basecur': '',
        #    'baserate': '',
        #    'foreignamt': '',
        #    'foreigncur': '',
        #    'foreignrate': '',
        #    'dccrate': '',
        #    'dm_decision': '',
        #    'dm_review': '',
        #    'dm_reject': '',
        #    'param1': '',
        #    'param2': '',
        #    'param3': '',
        # }
        return request.form
    
    def _verify_signature(self, data):
        """Verify the transaction data and signature with Eximbay"""
        """ check fgkey from data & fgkey """
        if not self.eximbay_account == data['mid']:
            raise TransactionFailure(step='verification', details='mismatched account ID')
        
        if not data['rescode'] == '0000':
            raise TransactionFailure(step='verification', details='rescode is not %s' % data['rescode'])
        
        if not data['resmsg'] == 'Success.':
            raise TransactionFailure(step='verification', details='respone message is %s' % data['resmsg'])
        
        fgkey = get_fgkey(self.eximbay_securitykey, data)
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
        """Confirm to Eximbay server that the transaction is accepted"""
        
        completion_data = { 'keyfield': 'TRANSID', 'lang': 'EN' }
        for key in ('ref', 'cur', 'amt', 'transid'):
            completion_data[key] = assert_data.get(key)
        
        response = self._perform_request('confirm', '/Gateway/DirectProcessor.krp', **completion_data)
        try:
            res = dict(parse_qsl(urlsplit(response.text).path))
            if not res['rescode'] == '0000':
                raise TransactionFailure(step='confirm transaction', details=res['rescode'])
        except:
            raise TransactionFailure(step='response at confirm', details=response.text)
        assert res['status'] == 'SALE'
        return True

    def _verify_amount(self, assert_data):
        """Verify the amount and currency of the payment; sends an email but still registers incorrect payments"""
        expected_amount = float(self.registration.price)
        expected_currency = self.registration.currency
        amount = float(assert_data['amt'])
        currency = assert_data['cur']
        if expected_amount == amount and expected_currency == currency:
            return True
        EximbayPaymentPlugin.logger.warning(
            "Payment doesn't match events fee: %s %s != %s %s",
            amount, currency, expected_amount, expected_currency
        )
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
            self.registration,
            self.registration.transaction.amount,
            self.registration.transaction.currency,
            TransactionAction.complete,
            PROVIDER_EXIMBAY,
            data={'Transaction': assert_data}
        )


class UserCancelHandler(RHEximbayBase):
    """User Message on cancelled payment"""
    def _process(self):
        register_transaction(
            self.registration,
            self.registration.transaction.amount,
            self.registration.transaction.currency,
            # XXX: this is indeed reject and not cancel (cancel is "mark as unpaid" and
            # only used for manual transactions)
            TransactionAction.reject,
            provider=PROVIDER_EXIMBAY,
        )
        flash(_('You cancelled the payment.'), 'info')
        return redirect(url_for('event_registration.display_regform', self.registration.locator.registrant))


class UserFailureHandler(RHEximbayBase):
    """User Message on failed payment"""
    def _process(self):
        register_transaction(
            self.registration,
            self.registration.transaction.amount,
            self.registration.transaction.currency,
            TransactionAction.reject,
            provider=PROVIDER_EXIMBAY,
        )
        flash(_('Your payment has failed.'), 'info')
        return redirect(url_for('event_registration.display_regform', self.registration.locator.registrant))


class UserSuccessHandler(EximbayNotificationHandler):
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
