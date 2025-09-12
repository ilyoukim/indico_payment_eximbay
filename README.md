# Eximbay Payment Plugin

This plugin provides a payment option for Indico's payment module using the Eximbay API.

When used, the user will be sent to Eximbay to make the payment,
 and afterwards they are automatically sent back to Indico.


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

- Restart uWSGI service (as root, optional): sometimes takes more than a few seconds, don't abort
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

- API URL : https://secureapi.test.eximbay.com
- Account ID : 1849705C64
- Secret Key : 289F40E6640124B2628640168C3C5464
- credit card
    - Card Type : VISA
    - Card No : 4111 1111 1111 1111
    - Expiry Date : 12/xx
    - CVV : 123


## Reference

- Eximbay API : https://developer.eximbay.com/eximbay/api_list/reference.html

- Error Code :  https://developer.eximbay.com/eximbay/api_sdk/code-error.html
