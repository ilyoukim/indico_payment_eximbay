# -*- coding: utf-8 -*-
##
## This file is part of the Eximbay Indico EPayment Plugin.
## Copyright (C) 2019 - 2026 Gyujin Kim
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
from urllib.parse import urlencode, urljoin

from flask import flash, redirect, request
from flask_pluginengine import current_plugin

from werkzeug.exceptions import BadRequest, NotFound

from indico.core.plugins import url_for_plugin
from indico.modules.events.payment.controllers import RHPaymentBase
from indico.modules.events.payment.models.transactions import TransactionAction
from indico.modules.events.payment.notifications import notify_amount_inconsistency
from indico.modules.events.payment.util import get_active_payment_plugins, register_transaction
from indico.modules.events.registration.models.registrations import Registration
from indico.web.flask.util import url_for
from indico.web.rh import RH

from indico_payment_eximbay import _
from indico_payment_eximbay.util import (EXIMBAY_SERVICE_DOMAIN, EXIMBAY_VERIFY_URL,
                                        PROVIDER_EXIMBAY, get_request_header)
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
        self.token = request.args['token']

        self.registration = Registration.query.filter_by(uuid=self.token).first()
        if not self.registration:
            raise BadRequest


class RHInitEximbayPayment(RHPaymentBase):
     """Handler for initial to use Eximbay service"""


class RHEximbayNotify(RHEximbayBase):
    """Handler for notification from Eximbay service"""

    def _process(self):
        """Process the notification callback from Eximbay about the transaction."""
        if self.token:
            self._process_confirmation()
        else:
            return redirect(url_for('event_registration.display_regform', self.registration.locator.registrant))

    def _process_confirmation(self):
        """Process the confirmation response inside indico.

        Assert transaction status from Eximbay
        """
        event = self.registration.registration_form.event
        settings = current_plugin.event_settings.get_all(event)

        assert_response = request.form

        try:
            # we have already handled the transaction
            if self._is_duplicate_transaction(assert_response):
                return

            # check the mid, code, message
            if not self.is_authorized_transaction(settings, assert_response):
                return

            # verify message with eximbay verify api
            if not self._verify_transaction(settings, assert_response):
                # send error message to manager and register
                return

            # if this matches, the user completed the transaction as requested by Indico
            if not self._verify_amount(settings, assert_response):
                return

            self._register_payment(settings, assert_response)

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

    def is_authorized_transaction(self, settings, transaction_data):
        """Verify the transaction data

        https://developer.eximbay.com/eximbay/payment_linkage/preparing-fgkey.html#afterCalling
        """
        mids = [settings.get('account_id', ''),
                settings.get('account_id2', '')]

        mid = transaction_data.get('mid', '').strip()
        resCode = transaction_data.get('rescode', '').strip()
        resMsg = transaction_data.get('resmsg', '').strip()

        if (mid in mids) and resCode == '0000' and ("success" in resMsg.lower()):
            return True

        manager_email = settings.get('notification_mail')
        notify_account_error(self.registration, transaction_data, manager_email)
        return False

    def _verify_transaction(self, settings, assert_data):
        """Verify transaction with Eximbay verify api

        https://developer.eximbay.com/eximbay/payment_linkage/preparing-fgkey.html#paymentVerify
        """
        res = self._perform_request(settings, 'verify', EXIMBAY_VERIFY_URL, assert_data)

        resCode = res.get('rescode', '').strip()

        if resCode == '0000':
            return True

        manager_email = settings.get('notification_mail')

        notify_payment_error(self.registration, {"received": assert_data, "verify": res}, manager_email, send_all=True)
        notify_payment_error(self.registration, assert_data)

        return False

    def _verify_amount(self, settings, assert_data):
        """Verify the amount and currency of the payment.

        Sends an email to the manager and rejects registration if amounts mismatch.
        """
        expected_amount = float(self.registration.price)
        expected_currency = self.registration.currency
        amount = float(assert_data.get('amount', '0').strip())
        currency = assert_data.get('currency', '').strip()

        if expected_amount == amount and expected_currency == currency:
            return True

        manager_email = settings.get('notification_mail')
        # current_plugin.logger.warning("Payment doesn't match event's fee: %s %s != %s %s",
        #                                 amount, currency, expected_amount, expected_currency)

        notify_amount_inconsistency(self.registration, amount, currency)
        notify_payment_error(self.registration, assert_data, manager_email)

        return False

    def _register_payment(self, settings, assert_data):
        """Register the transaction as paid."""
        # check transaction with actual transaction with payment url
        api_url = settings.get('url')

        valid_trans = bool(api_url == EXIMBAY_SERVICE_DOMAIN)

        # Exclude unnecessary parameters from being stored
        exclude_keys = {
            'ver', 'transaction_type', 'mid', 'payment_method', 'email',
            'card_holder', 'card_number1', 'card_number4', 'pay_to', 'fgkey'
        }

        # Store only relevant transaction data
        store_data = {key: value for key, value in assert_data.items() if key not in exclude_keys}

        if not valid_trans:
            store_data['resmsg'] = "Transaction with the Test server."

        register_transaction(
            registration = self.registration,
            amount = float(assert_data.get('amount', '0').strip()),
            currency = assert_data.get('currency', '').strip(),
            action = TransactionAction.complete,
            provider = PROVIDER_EXIMBAY,
            data = {'Transaction': store_data}
        )

    def _perform_request(self, settings, task, endpoint, data):
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
        api_url = settings.get('url', '').strip()

        res_mid = data.get('mid', '').strip()
        mid1 = settings.get('account_id', '').strip()
        mid2 = settings.get('account_id2', '').strip()

        if res_mid == mid1:
            api_key = settings.get('account_key', '').strip()
        elif res_mid == mid2:
            api_key = settings.get('account_key2', '').strip()
        else:
            raise TransactionFailure(step=task, details="Invalid MID in transaction data")

        if len(api_key) != 25:
            raise TransactionFailure(step=task, details="Invalid or missing API Security Key")

        request_url = urljoin(api_url, endpoint)
        headers = get_request_header(api_key)
        encoded = {"data": urlencode(data)}

        try:
            response = requests.post(url=request_url, headers=headers, data=json.dumps(encoded), timeout=5)
            response.raise_for_status()
        except requests.RequestException as e:
            raise TransactionFailure(step=task, details=str(e))

        return response.json()


class RHEximbayReturn(RHEximbayBase):
    """Confirmation message after payment"""

    def _process(self):
        # transaction = self.registration.transaction
        #
        # try:
        #     if hasattr(transaction, 'status') and \
        #         transaction.status == TransactionStatus.successful:
        #         flash(_('Your payment has been confirmed.'), 'success')
        #     # else:
        #     #     # issue: logout for development
        #     #     flash(_('Your payment has failed.'), 'info')
        # except TransactionFailure:
        #     flash(_('Your payment has failed.'), 'error')

        return redirect(url_for('event_registration.display_regform', self.registration.locator.registrant))
