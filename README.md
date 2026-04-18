# Eximbay Payment Plugin

This plugin provides a payment option for Indico's payment module using the Eximbay Open API.

When used, the user will be sent to Eximbay to make the payment,
 and afterwards they are automatically sent back to Indico.

**Note: The payment system supports API Key only authentication; Security Key (old version) is not available.**


## Installation guide
https://docs.getindico.io/en/stable/installation/plugins/

- Logged in as the indico user
    ```sh
    $ su - indico
    $ source ~/.venv/bin/activate
    ```

- Stop Indico service (as root)
    ```sh
    $ systemctl stop indico-celery.service
    ```

- Install plugin
    ```sh
    $ pip install git+https://{git_server}/indico_payment_eximbay.git
    ```

- Installation branch for development
    ```sh
    $ pip install git+https://<git repository url>.git@<branch>

    or

    $ git clone git+https://<git repository url>.git@<branch>
    $ pip install -e .
    ```

- Enable plugins : /opt/indico/etc/indico.conf
    ```sh
    # Add CSP Exceptions if CSP_Enabled
    CSP_ENABLED = True
    CSP_SCRIPT_SOURCES = { 
        'https://api-test.eximbay.com',
        'https://api.eximbay.com'
    }

    # Add Eximbay Plugin
    PLUGINS = {'payment_manual', 'payment_eximbay'}
    ```

- Database migration
    ```sh
    $ indico db upgrade

    $ indico db --all-plugins upgrade
    ```

- Reload uWSGI
    ```sh
    $ touch ~/web/indico.wsgi
    ```

- Restart Celery worker (as root)
    ```sh
    $ systemctl restart indico-celery.service
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
