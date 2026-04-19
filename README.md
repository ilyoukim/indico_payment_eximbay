# Eximbay Payment Plugin

This plugin integrates Eximbay Open API as a payment provider for Indico’s payment module.

When a user selects this payment method, they are redirected to Eximbay to complete the transaction.  
After the payment is processed, the user is automatically redirected back to Indico.

> ⚠️ **Note**  
> Only **API Key authentication** is supported.  
> The legacy **Security Key method is not supported**.


## 📦 Installations
Refer to the official Indico plugin installation guide:  
👉 https://docs.getindico.io/en/stable/installation/plugins/


### 1. Activate Indico environment

```sh
su - indico
source ~/.venv/bin/activate
```

### 2. Stop Indico services (as root)
```sh
systemctl stop indico-celery.service
```

### 3. Install the plugin

```sh
pip install git+https://{git_server}/indico_payment_eximbay.git
```

### 4. Installation from a specific branch (development)
```sh
pip install git+https://<git repository url>.git@<branch>
```
Or:
```
git clone git+https://<git repository url>.git@<branch>
pip install -e .
```




## ⚙️ Configuration

### Edit the Indico configuration file:
```
/opt/indico/etc/indico.conf
```

```python
# Add CSP Exceptions
CSP_ENABLED = True
CSP_SCRIPT_SOURCES = { 
    'https://api-test.eximbay.com',
    'https://api.eximbay.com'
}

# Add Eximbay Plugin
PLUGINS = {'payment_manual', 'payment_eximbay'}
```

### Database migration
```sh
indico db upgrade

indico db --all-plugins upgrade
```

## 🔄 Apply Changes

#### Reload uWSGI
```sh
touch ~/web/indico.wsgi
```

#### Restart Celery (as root)
```sh
systemctl restart indico-celery.service
```


## 🧪 Development & Test Information

### API Endpoint
  | Environment | URL |
  |-------------|-----|
  | **Test** | [https://api-test.eximbay.com](https://api-test.eximbay.com) |
  | **Production** | [https://api.eximbay.com](https://api.eximbay.com) |

### Test Credentials
- MID : 1849705C64
- API Key : test_1849705C642C217E0B2D

### Test Card
- Card Type : VISA
- Card No : 4111 1111 1111 1111
- Expiry Date : 12/xx
- CVV : 123

### 📖 Payment integration guide:  

- https://developer.eximbay.com/eximbay/payment_linkage/firewall.html

- https://developer.eximbay.com/eximbay/payment_linkage/preparing-payment.html



## 📚 Reference

### Technical Documentation

* Integration Guide v2.3 (Old version)  
https://developer.eximbay.com/eximbay/payment_linkage/legacy.html

### Error Code
- https://developer.eximbay.com/eximbay/api_sdk/code-error.html



## Acknowledgements

This plugin was developed by referencing the 
[indico-plugin-payment-sixpay](https://github.com/maxfischer2781/indico_sixpay) 
project, adapting its payment plugin structure, transaction handling patterns, 
and `PaymentPluginMixin` integration approach for **Eximbay Open API**.

This is an **independent implementation** tailored specifically for Eximbay, 
while following Indico's official payment plugin API guidelines.
