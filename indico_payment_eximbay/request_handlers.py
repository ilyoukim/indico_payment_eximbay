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
from __future__ import unicode_literals
import urlparse
from xml.dom.minidom import parseString

import requests
from flask import flash, redirect, request
from flask_pluginengine import current_plugin
from werkzeug.exceptions import BadRequest

from indico.modules.events.payment.models.transactions import TransactionAction
from indico.modules.events.payment.notifications import notify_amount_inconsistency
from indico.modules.events.payment.util import register_transaction
from indico.modules.events.registration.models.registrations import Registration
from indico.web.flask.util import url_for
from indico.web.rh import RH

from .utility import gettext, get_fgkey

# RH from indico.web.rh
# - the logic to execute when Eximbay/Users are redirected *after* a transaction
# - see blueprint.py for how RH's are mounted!


class BaseRequestHandler(RH):
    """
    Request Handler for asynchronous callbacks from Eximbay

    These handlers are used either by

    - the user, when he is redirected from Eximbay back to Indico
    - Eximbay, when it sends back the result of a transaction
    """
    CSRF_ENABLED = False

    def _process_args(self):
        self.token = request.args['token']
        self.registration = Registration.find_first(uuid=self.token)
        if not self.registration:
            raise BadRequest


class TransactionFailure(Exception):
    """
    A Transaction with Eximbay failed

    :param step: name of the step at which the transaction failed
    :type step: basestring
    :param details: verbose description of what went wrong
    :type step: basestring
    """
    def __init__(self, step, details=None):
        self.step = step
        self.details = details


class EximbayResponseHandler(BaseRequestHandler):
    """Handler for notification from Eximbay service"""
    def __init__(self):
        super(EximbayResponseHandler, self).__init__()
        # registration context is not initialised before `self._process_args`...
        self.eximbay_url = None             # type: str
        self.eximbay_account = None         # type: str
        self.eximbay_securitykey = None     # type: str

    def _process_args(self):
        super(EximbayResponseHandler, self)._process_args()
        # prefer event supplied eximbay url over global eximbay url
        self.eximbay_url = current_plugin.event_settings.get(self.registration.registration_form.event, 'url') \
            or current_plugin.settings.get('url')
        self.eximbay_account = current_plugin.event_settings.get(self.registration.registration_form.event, 'account_id') \
            or current_plugin.settings.get('account_id')
        self.eximbay_securitykey = current_plugin.event_settings.get(self.registration.registration_form.event, 'account_securitykey') \
            or current_plugin.settings.get('account_securitykey')

    def _process(self):
        """process the reply from Eximbay about the transaction"""
        try:
            self._process_confirmation()
        except TransactionFailure as err:
            current_plugin.logger.warning("Eximbay transaction failed during %s: %s" % (err.step, err.details))

    def _process_confirmation(self):
        """Process the confirmation response inside indico"""
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
        transaction_data = request.form
        try:
            # verify the signature of Eximbay for the transaction
            self._verify_signature(transaction_data)
            if self._is_duplicate_transaction(transaction_data):
                # we have already handled the transaction
                return True
            if self._confirm_transaction(transaction_data):
                # if this matches, the user completed the transaction as requested by Indico
                self._verify_amount(transaction_data)
                self._register_transaction(transaction_data)
        except TransactionFailure as err:
            current_plugin.logger.warning("Eximbay transaction failed during %s: %s" % (err.step, err.details))
            raise
        return True
    
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
        
        request_url = urlparse.urljoin(self.eximbay_url, endpoint)
        try:
            response = requests.post(url=request_url, data=data, timeout=5)
            response.raise_for_status()
        except request.RequestException as e:
            raise RuntimeError("request error : %r" % (e.respone))
        return response
    
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
    
    def _is_duplicate_transaction(self, data):
        """Check if this transaction has already been recorded"""
        prev_transaction = self.registration.transaction
        if not prev_transaction or prev_transaction.provider != 'eximbay':
            return False
        return all(
            prev_transaction.data.get(key) == data.get(key)
            for key in ('ref', 'cur', 'amt', 'mid')
        )

    def _confirm_transaction(self, data):
        """Confirm to Eximbay server that the transaction is accepted"""
        completion_data = { 'keyfield': 'TRANSID', 'lang': 'EN' }
        for key in ('ref', 'cur', 'amt', 'transid'):
            completion_data[key] = data.get(key)
        
        response = self._perform_request('confirm', '/Gateway/DirectProcessor.krp', **completion_data)
        try:
            res = dict(urlparse.parse_qsl(urlparse.urlsplit(response.text).path))
            if not res['rescode'] == '0000':
                raise TransactionFailure(step='confirm transaction', details=res['rescode'])
        except:
            raise TransactionFailure(step='response at confirm', details=response.text)
        assert res['status'] == 'SALE'
        return True

    def _verify_amount(self, data):
        """Verify the amount and currency of the payment; sends an email but still registers incorrect payments"""
        expected_amount = float(self.registration.price)
        expected_currency = self.registration.currency
        amount = float(data['amt'])
        currency = data['cur']
        if expected_amount == amount and expected_currency == currency:
            return True
        current_plugin.logger.warning(
            "Payment doesn't match events fee: %s %s != %s %s",
            amount, currency, expected_amount, expected_currency
        )
        notify_amount_inconsistency(self.registration, amount, currency)
        return False

    def _register_transaction(self, data):
        """Register the transaction persistently within Indico"""
        register_transaction(
            registration = self.registration,
            amount = float(data['amt']),
            currency = data['cur'],
            action = TransactionAction.complete,
            provider = 'eximbay',
            data = data,
        )


class EximbayCancelHandler(BaseRequestHandler):
    """User Message on cancelled payment"""
    def _process(self):
        flash(gettext('You cancelled the payment.'), 'info')
        return redirect(url_for('event_registration.display_regform', self.registration.locator.registrant))


class EximbayFailureHandler(BaseRequestHandler):
    """User Message on failed payment"""
    def _process(self):
        flash(gettext('Your payment has failed.'), 'info')
        return redirect(url_for('event_registration.display_regform', self.registration.locator.registrant))


class EximbaySuccessHandler(EximbayResponseHandler):
    """User Message on successful payment"""
    def _process(self):
        try:
            self._process_confirmation()
        except TransactionFailure as err:
            current_plugin.logger.warning("Eximbay transaction failed during %s: %s" % (err.step, err.details))
            flash(gettext('Your payment could not be confirmed. Please contact an organizer.'), 'info')
        else:
            flash(gettext('Your payment has been confirmed.'), 'success')
        return redirect(url_for('event_registration.display_regform', self.registration.locator.registrant))
