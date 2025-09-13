# Eximbay Payment Plugin

This plugin provides a payment option for Indico's payment module using the Eximbay Open API.

When used, the user will be sent to Eximbay to make the payment,
 and afterwards they are automatically sent back to Indico.

**Note: The payment system supports API Key only authentication; Security Key (old version) is not available.**


## Installation guide
https://docs.getindico.io/en/stable/installation/plugins/

- Logged in as the indico user
    ```bash
    su - indico
    source ~/.venv/bin/activate
    ```

- Stop Indico service (as root)
    ```bash
    systemctl stop indico-celery.service

    systemctl stop indico-uwsgi.service (optional)
    ```

- Install plugin
    ```bash
    pip install git+https://{git_server}/indico_payment_eximbay.git
    
    # Installation branch for development
    pip install git+https://<git repository url>.git@<branch>
    ```

- Enable plugins : /opt/indico/etc/indico.conf
    ```sh
    # Add Eximbay Plugin
    PLUGINS = {'payment_manual', 'payment_eximbay'}
    ```

- Database migration
    ```bash
    indico db upgrade

    indico db --all-plugins upgrade
    ```

- Restart uWSGI service (as root) : optional

  > Don't abort, sometimes takes more than a few seconds
    ```bash
    systemctl restart indico-uwsgi.service
    ```

- Reload uWSGI
    ```bash
    touch ~/web/indico.wsgi
    ```

- Restart Celery worker (as root)
    ```bash
    systemctl restart indico-celery.service
    ```


## Development test information

* https://developer.eximbay.com/eximbay/payment_linkage/preparing-payment.html
- API URL : https://api-test.eximbay.com
- Test MID : 1849705C64
- Test API Key : test_1849705C642C217E0B2D
- credit card
    - Card Type : VISA
    - Card No : 4111 1111 1111 1111
    - Expiry Date : 12/xx
    - CVV : 123


## Reference


- Technical 
Integration Guide v2.3

    https://developer.eximbay.com/eximbay/payment_linkage/legacy.html



- Error Code :  https://developer.eximbay.com/eximbay/api_sdk/code-error.html
