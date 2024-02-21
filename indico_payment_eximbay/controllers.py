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

import requests
from urllib.parse import urljoin, parse_qsl, urlsplit

from flask import flash, redirect, request
from flask_pluginengine import current_plugin

from werkzeug.exceptions import BadRequest

from indico.modules.events.payment.models.transactions import TransactionAction
from indico.modules.events.payment.notifications import notify_amount_inconsistency
from indico.modules.events.payment.util import TransactionStatus, register_transaction
from indico.modules.events.registration.models.registrations import Registration
from indico.web.flask.util import url_for
from indico.web.rh import RH

from indico_payment_eximbay.util import (PROVIDER_EXIMBAY, EXIMBAY_PP_DIRECT_URL,
                                         get_fgkey, get_transdata)
from indico_payment_eximbay.notifications import (notify_payment_error_manager,
                                                  notify_payment_error_register,
                                                  notify_account_error)
from indico_payment_eximbay import _


class TransactionFailure(Exception):
    """A transaction with Eximbay failed.

    :param step: name of the step at which the transaction failed
    :param details: verbose description of what went wrong
    """

    def __init__(self, step, details=None):
        self.step = step
        self.details = details


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
            # verify the signature of Eximbay for the transaction
            if not self._verify_signature(assert_response):
                return
            
            # we have already handled the transaction
            if self._is_duplicate_transaction(assert_response):
                return
            
            if not self._confirm_transaction(assert_response):
                # send error message to manager and registor
                return
            
            # if this matches, the user completed the transaction as requested by Indico
            if not self._verify_amount(assert_response):
                return
            
            self._register_payment(assert_response)
        
        except TransactionFailure as err:
            current_plugin.logger.warning("Eximbay transaction failed during %s: %s", err.step, err.details)
            raise
    
    def _verify_signature(self, transaction_data):
        """Verify the transaction data and signature with Eximbay
        
        Check fgkey from data with securitykey
        """
        settings = current_plugin.event_settings.get_all(self.registration.registration_form.event)
        
        manager_email = settings.get('notification_mail')
        fgkey = get_fgkey(settings.get('account_securitykey'), transaction_data)
        
        if not settings['account_id'] == transaction_data['mid']:
            notify_account_error(self.registration, transaction_data, manager_email)
            return False
        
        if not fgkey == str(transaction_data['fgkey']):
            notify_payment_error_manager(self.registration, transaction_data, manager_email)
            return False

        return True
    
    def _verify_amount(self, assert_data):
        """Verify the amount and currency of the payment.

        Sends an email but still registers incorrect payments.
        """
        expected_amount = float(self.registration.price)
        expected_currency = self.registration.currency
        amount = float(assert_data.get('amt'))
        currency = assert_data.get('cur')
        
        if expected_amount == amount and expected_currency == currency:
            return True
        else:
            current_plugin.logger.warning("Payment doesn't match event's fee: %s %s != %s %s",
                                        amount, currency, expected_amount, expected_currency)
            
            notify_amount_inconsistency(self.registration, amount, currency)
            
            return False

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
            old['transid'] == new['transid'] and
            float(old['amt']) == float(new['amt'])
        )

    def _confirm_transaction(self, assert_data):
        """Confirm to Eximbay server that the transaction is accepted
        """
        completion_data = {
            'txntype': 'QUERY',
            'keyfield': 'TRANSID'
            }
        
        for key in ('ref', 'cur', 'amt', 'transid'):
            completion_data[key] = assert_data.get(key)
        
        response = self._perform_request('confirm', completion_data)
        res = dict(parse_qsl(urlsplit(response.text).path))
        
        if 'rescode' in assert_data and  'rescode' in res and \
            assert_data['rescode'] == '0000' and res['rescode'] == '0000':
            
            self.registration.transaction.data = {}
            return res['status'] in ('SALE', 'AUTH')
        else:
            settings = current_plugin.event_settings.get_all(self.registration.registration_form.event)
            manager_email = settings.get('notification_mail')
            
            # store error code & message to notify
            data = {}
            for key in ['rescode','resmsg']:
                if key in assert_data:
                    data[key] = assert_data.get(key)
            
            self.registration.transaction.data = data
            notify_payment_error_manager(self.registration, assert_data, manager_email)
            notify_payment_error_register(self.registration, assert_data)
            return False

    def _register_payment(self, assert_data):
        """Register the transaction as paid."""
        ## not nessary params
        except_keys = ['cardholder','email','cardno1','cardno4','authcode']
        
        store_data = {}
        for key in assert_data:
            if key not in except_keys:
                store_data[key] = assert_data.get(key)
        
        register_transaction(
            registration = self.registration,
            amount = float(assert_data.get('amt')),
            currency = assert_data.get('cur'),
            action = TransactionAction.complete,
            provider = PROVIDER_EXIMBAY,
            data = store_data
        )

    def _perform_request(self, task, assert_data):
        """
        Helper for performing a request against Eximbay

        :param task: description of the request, used for error handling
        :type task: basestring
        :param endpoint: the URL endpoint *relative* to the Eximbay base URL
        :type endpoint: basestring
        :param assert_data: assert_data passed during the request

        This will automatically raise any HTTP errors encountered during the request.
        If the request itself fails, a :py:exc:`~.TransactionFailure` is raised for ``task``.
        
        3.2	Querying a Single Transaction
        """
        settings = current_plugin.event_settings.get_all(self.registration.registration_form.event)
        
        assert_data['mid'] = settings['account_id']
        data = get_transdata(settings['account_securitykey'], assert_data)
        
        request_url = urljoin(settings['url'], EXIMBAY_PP_DIRECT_URL)
        try:
            response = requests.post(url=request_url, data=data, timeout=5)
            response.raise_for_status()
        except requests.HTTPError:
            raise TransactionFailure(step=task, details=response.text)
        
        return response


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
                msg = 'Your payment has failed.'
                if hasattr(transaction, 'data') and \
                    'rescode' in transaction.data and \
                    'resmsg' in transaction.data:
                    msg = msg + ' [' + transaction.data['rescode'] + \
                            '] ( ' + transaction.data['resmsg'] + ' )'
                
                flash(_(msg), 'info')
        except TransactionFailure:
            flash(_('Your payment has failed.'), 'error')
        
        return redirect(url_for('event_registration.display_regform', self.registration.locator.registrant))
