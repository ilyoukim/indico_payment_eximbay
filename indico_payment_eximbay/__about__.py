"""
++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
``indico_payment_eximbay`` - EXIMBAY EPayment Plugin for Indico
++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

.. image:: https://readthedocs.org/projects/indico_payment_eximbay/badge/?version=latest
    :target: http://indico-eximbay.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation

.. image:: https://img.shields.io/pypi/v/indico_payment_eximbay.svg
    :alt: Available on PyPI
    :target: https://pypi.python.org/pypi/indico_payment_eximbay/

.. image:: https://img.shields.io/github/license/xxx/indico_payment_eximbay.svg
    :alt: License
    :target: https://github.com/xxx/indico_payment_eximbay/blob/master/LICENSE

.. image:: https://img.shields.io/github/commits-since/xxx/indico_sixpay/v2.0.0.svg
    :alt: Repository
    :target: https://github.com/xxx/indico_sixpay/tree/master

Plugin for the Indico event management system to use EPayment via Eximbay Payment services.

Quick Guide
-----------

To enable the plugin, it must be installed for the python version running ``indico``.

.. code:: bash

    python -m pip install indico_payment_eximbay

Once installed, it can be enabled in the administrator and event settings.
Configuration uses the same options for global defaults and event specific overrides.

Disclaimer
----------

This plugin is in no way endorsed, supported or provided by Eximbay, Indico or any other service, provider or entity.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""
__title__ = 'indico_payment_eximbay'
__summary__ = 'Indico EPayment Plugin for Eximbay services'
# __url__ = 'https://github.com/xxx/indico_payment_eximbay'
__url__ = ''

__version__ = '3.0.0'
__author__ = 'Gyujin Kim'
__email__ = 'ilyoukim@postech.ac.kr'
__copyright__ = '2019 - 2023 %s' % __author__
