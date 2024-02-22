# Eximbay Payment Plugin

This plugin provides a payment option for Indico's payment module using the Eximbay API.

When used, the user will be sent to Eximbay to make the payment,
 and afterwards they are automatically sent back to Indico.


## Installation guide
https://docs.getindico.io/en/stable/installation/upgrade/

```bash
sudo systemctl stop indico-celery.service
```

```bash
pip install git+https://{git_server}/indico_payment_eximbay.git
```

```sh
## /opt/indico/etc/indico.conf

# Add Eximbay Plugin
PLUGINS = {'payment_manual', 'payment_eximbay'}
```

```bash
indico db --all-plugins upgrade

touch ~/web/indico.wsgi
```

```bash
sudo systemctl start indico-celery.service
```


## Development test information

- API URL : https://secureapi.test.eximbay.com
- Account ID : 1849705C64
- Secret Key : 289F40E6640124B2628640168C3C5464
- credit card
    - Card Type : VISA
    - Card No : 4111 1111 1111 1111
    - Expiry Date : 12/xx
    - CVV : 123


## Reference

- Eximbay API : https://developer.eximbay.com/api_list/reference.html

- Error Code : https://developer.eximbay.com/api_sdk/code-error.html
