# Eximbay Payment Plugin

This plugin provides a payment option for Indico's payment module using the
Eximbay API.

When used, the user will be sent to Saferpay to make the payment, and afterwards
they are automatically sent back to Indico.

## Changelog

### 3.0.1

- for Korea domestic credit card

### 3.0

- Initial release for Indico 3.2

## Installation
pip install git+https://{git_server}/indico_payment_eximbay.git


## Development test information
- url : https://secureapi.test.eximbay.com
- mid : 1849705C64
- secretkey : 289F40E6640124B2628640168C3C5464
- credit card
    - Card Type : VISA
    - Card No : 4111 1111 1111 1111
    - Expiry Date : 12/xx
    - CVV : 123