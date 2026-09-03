# quickbooks/services.py
import requests
import base64
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from datetime import datetime, date, timedelta
import logging

logger = logging.getLogger(__name__)


# ============================================================
# QUICKBOOKS AUTH SERVICE
# ============================================================

class QuickBooksAuthService:
    """Handles OAuth2 authentication with QuickBooks"""

    def __init__(self, user=None):
        self.user = user
        self.client_id = settings.QUICKBOOKS['CLIENT_ID']
        self.client_secret = settings.QUICKBOOKS['CLIENT_SECRET']
        self.redirect_uri = settings.QUICKBOOKS['REDIRECT_URI']
        self.environment = settings.QUICKBOOKS['ENVIRONMENT']
        self.auth_urls = settings.QUICKBOOKS_AUTH_URLS[self.environment]

    def get_auth_url(self):
        """Generate the authorization URL"""
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'scope': settings.QUICKBOOKS['SCOPES'],
            'redirect_uri': self.redirect_uri,
            'state': 'random_state_string',
        }
        auth_url = f"{self.auth_urls['auth_url']}?{requests.compat.urlencode(params)}"
        return auth_url

    def exchange_code_for_tokens(self, auth_code, realm_id):
        """Exchange authorization code for tokens"""
        token_url = self.auth_urls['token_url']

        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        data = {
            'grant_type': 'authorization_code',
            'code': auth_code,
            'redirect_uri': self.redirect_uri,
        }

        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status()

        token_data = response.json()

        if self.user:
            from quickbooks.models import QuickBooksToken
            QuickBooksToken.objects.update_or_create(
                user=self.user,
                defaults={
                    'access_token': token_data['access_token'],
                    'refresh_token': token_data['refresh_token'],
                    'realm_id': realm_id,
                    'expires_at': timezone.now() + timedelta(seconds=token_data['expires_in']),
                }
            )

        return token_data

    # ✅ Add the missing refresh_access_token method
    def refresh_access_token(self, refresh_token):
        """Refresh the access token when expired"""
        token_url = self.auth_urls['token_url']

        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
        }

        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status()

        return response.json()

    def get_valid_token(self):
        """Get a valid token, refresh if expired"""
        from quickbooks.models import QuickBooksToken

        token = QuickBooksToken.objects.get(user=self.user)

        if token.is_expired():
            token_data = self.refresh_access_token(token.refresh_token)
            token.access_token = token_data['access_token']
            token.refresh_token = token_data['refresh_token']
            token.expires_at = timezone.now() + timedelta(seconds=token_data['expires_in'])
            token.save()

        return token


# ============================================================
# QUICKBOOKS PUSH SERVICE
# ============================================================

class QuickBooksPushService:
    """Push data to QuickBooks with auto-refresh"""

    def __init__(self, user):
        self.user = user
        from quickbooks.models import QuickBooksToken

        # Get token
        self.token = QuickBooksToken.objects.get(user=user)

        # ✅ Check if token is expired and refresh if needed
        if self.token.is_expired():
            logger.info("🔄 Token expired, refreshing...")
            auth_service = QuickBooksAuthService(user)
            try:
                token_data = auth_service.refresh_access_token(self.token.refresh_token)
                self.token.access_token = token_data['access_token']
                self.token.refresh_token = token_data['refresh_token']
                self.token.expires_at = timezone.now() + timedelta(seconds=token_data['expires_in'])
                self.token.save()
                logger.info("✅ Token refreshed successfully")
            except Exception as e:
                logger.error(f"❌ Token refresh failed: {str(e)}")
                # If refresh fails, user needs to reconnect
                raise Exception("QuickBooks token expired. Please reconnect to QuickBooks at /quickbooks/connect/")

        self.environment = settings.QUICKBOOKS['ENVIRONMENT']
        self.api_url = settings.QUICKBOOKS_AUTH_URLS[self.environment]['api_url']

    def _get_headers(self):
        """Get headers for API requests"""
        return {
            'Authorization': f'Bearer {self.token.access_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

    def find_customer_by_email(self, email):
        """Find a customer by email in QuickBooks"""
        url = f"{self.api_url}{self.token.realm_id}/query"

        query = f"SELECT * FROM Customer WHERE PrimaryEmailAddr = '{email}'"

        headers = self._get_headers()
        params = {'query': query}

        logger.info(f"🔍 Searching for customer with email: {email}")

        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 401:
            logger.error("❌ Token expired or invalid. Please reconnect to QuickBooks.")
            raise Exception("QuickBooks token expired. Please reconnect at /quickbooks/connect/")

        response.raise_for_status()

        data = response.json()
        customers = data.get('QueryResponse', {}).get('Customer', [])

        if customers:
            logger.info(f"✅ Customer found: {customers[0].get('Id')}")
            return customers[0]
        return None

    def find_invoice_by_doc_number(self, doc_number):
        """Find an invoice by its DocNumber"""
        if not doc_number:
            return None

        url = f"{self.api_url}{self.token.realm_id}/query"
        query = f"SELECT * FROM Invoice WHERE DocNumber = '{doc_number}'"

        headers = self._get_headers()
        params = {'query': query}

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()
        invoices = data.get('QueryResponse', {}).get('Invoice', [])

        if invoices:
            logger.info(f"✅ Invoice found with DocNumber {doc_number}, ID: {invoices[0].get('Id')}")
            return invoices[0]
        return None

    def find_payment_by_reference(self, payment_ref_num):
        """Find a payment by its PaymentRefNum"""
        if not payment_ref_num:
            return None

        url = f"{self.api_url}{self.token.realm_id}/query"
        query = f"SELECT * FROM Payment WHERE PaymentRefNum = '{payment_ref_num}'"

        headers = self._get_headers()
        params = {'query': query}

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()
        payments = data.get('QueryResponse', {}).get('Payment', [])

        if payments:
            logger.info(f"✅ Payment found with PaymentRefNum {payment_ref_num}, ID: {payments[0].get('Id')}")
            return payments[0]
        return None

    def create_customer1(self, customer_data):
        """Create customer in QuickBooks - with duplicate check"""
        url = f"{self.api_url}{self.token.realm_id}/customer"

        # First, check if customer already exists by email
        email = customer_data.get('email', '')
        if email:
            existing = self.find_customer_by_email(email)
            if existing:
                logger.info(f"✅ Customer already exists with email {email}, ID: {existing.get('Id')}")
                return {'Customer': existing}

        # If not found, create new customer
        payload = {
            "DisplayName": customer_data.get('display_name', 'Customer'),
            "GivenName": customer_data.get('first_name', ''),
            "FamilyName": customer_data.get('last_name', ''),
            "PrimaryEmailAddr": {
                "Address": customer_data.get('email', '')
            },
            "PrimaryPhone": {
                "FreeFormNumber": customer_data.get('phone', '')
            },
            "CustomField": [
                {
                    "DefinitionId": "3",  # essco_customer_id is the 3rd custom field
                    "StringValue": customer_data.get('customer_id', '')
                }
            ]
        }

        headers = self._get_headers()

        logger.info(f"Sending customer data to QuickBooks: {payload}")

        response = requests.post(url, headers=headers, json=payload)

        logger.info(f"Response status: {response.status_code}")
        if response.status_code != 200:
            logger.info(f"Response body: {response.text}")

        response.raise_for_status()
        return response.json()

    def create_customer(self, customer_data):
        """Create customer in QuickBooks - with automatic update for existing customers"""
        url = f"{self.api_url}{self.token.realm_id}/customer"

        # First, check if customer already exists by email
        email = customer_data.get('email', '')
        if email:
            existing = self.find_customer_by_email(email)
            if existing:
                # ✅ UPDATE the existing customer with new DisplayName
                customer_id = existing.get('Id')
                sync_token = existing.get('SyncToken', '0')

                update_payload = {
                    "Id": customer_id,
                    "SyncToken": sync_token,
                    "DisplayName": f"{customer_data.get('display_name', 'Customer')} ({customer_data.get('customer_id', '')})",
                    "PrimaryEmailAddr": {"Address": customer_data.get('email', '')},
                }

                headers = self._get_headers()
                response = requests.post(url, headers=headers, json=update_payload)
                response.raise_for_status()

                logger.info(f"✅ Updated customer with email {email}, ID: {customer_id}")
                return {'Customer': response.json()['Customer']}

        # If not found, create new customer
        payload = {
            "DisplayName": f"{customer_data.get('display_name', 'Customer')} ({customer_data.get('customer_id', '')})",
            "GivenName": customer_data.get('first_name', ''),
            "FamilyName": customer_data.get('last_name', ''),
            "PrimaryEmailAddr": {
                "Address": customer_data.get('email', '')
            },
            "PrimaryPhone": {
                "FreeFormNumber": customer_data.get('phone', '')
            },
        }

        headers = self._get_headers()

        logger.info(f"Sending customer data to QuickBooks: {payload}")

        response = requests.post(url, headers=headers, json=payload)

        logger.info(f"Response status: {response.status_code}")
        if response.status_code != 200:
            logger.info(f"Response body: {response.text}")

        response.raise_for_status()
        return response.json()


    def create_invoice(self, invoice_data):
        """Create invoice in QuickBooks - with duplicate check"""
        url = f"{self.api_url}{self.token.realm_id}/invoice"

        # ✅ Check if invoice already exists by DocNumber
        doc_number = invoice_data.get('doc_number', '')
        if doc_number:
            existing = self.find_invoice_by_doc_number(doc_number)
            if existing:
                logger.info(f"✅ Invoice already exists with DocNumber {doc_number}, ID: {existing.get('Id')}")
                return {'Invoice': existing}

        # Format dates
        due_date = invoice_data.get('due_date')
        txn_date = invoice_data.get('txn_date')

        if due_date and hasattr(due_date, 'strftime'):
            due_date = due_date.strftime('%Y-%m-%d')
        if txn_date and hasattr(txn_date, 'strftime'):
            txn_date = txn_date.strftime('%Y-%m-%d')

        payload = {
            "CustomerRef": {
                "value": invoice_data.get('customer_ref')
            },
            "Line": [
                {
                    "Amount": float(invoice_data.get('amount', 0)),
                    "DetailType": "SalesItemLineDetail",
                    "SalesItemLineDetail": {
                        "ItemRef": {
                            "value": "1"
                        },
                        "Qty": 1,
                        "UnitPrice": float(invoice_data.get('amount', 0))
                    },
                    "Description": invoice_data.get('description', 'HP Loan')
                }
            ],
            "DueDate": due_date,
            "TxnDate": txn_date,
            "TotalAmt": float(invoice_data.get('amount', 0)),
            # ✅ Add DocNumber to make it unique and searchable
            "DocNumber": doc_number,
            # ✅ Add Custom Fields
            "CustomField": [
                {
                    "DefinitionId": "1",  # essco_invoice_id
                    "StringValue": invoice_data.get('invoice_id', '')
                },
                {
                    "DefinitionId": "2",  # essco_loan_id
                    "StringValue": invoice_data.get('loan_id', '')
                }
            ]
        }

        headers = self._get_headers()

        logger.info(f"Sending invoice data to QuickBooks: {payload}")

        response = requests.post(url, headers=headers, json=payload)

        logger.info(f"Response status: {response.status_code}")
        if response.status_code != 200:
            logger.info(f"Response body: {response.text}")

        response.raise_for_status()
        return response.json()

    def create_payment(self, payment_data):
        """Create payment in QuickBooks - with separate interest via Sales Receipt"""
        url = f"{self.api_url}{self.token.realm_id}/payment"

        # Check for duplicates using PaymentRefNum
        payment_ref_num = payment_data.get('PaymentRefNum', '')
        if payment_ref_num:
            existing = self.find_payment_by_reference(payment_ref_num)
            if existing:
                # ✅ UPDATE the existing payment
                payment_id = existing.get('Id')
                sync_token = existing.get('SyncToken', '0')

                update_payload = {
                    "Id": payment_id,
                    "SyncToken": sync_token,
                    "CustomerRef": {"value": str(payment_data.get('customer_ref'))},
                    "TotalAmt": float(payment_data.get('principal_amount', payment_data.get('amount', 0))),
                    "Line": [
                        {
                            "Amount": float(payment_data.get('principal_amount', payment_data.get('amount', 0))),
                            "LinkedTxn": [
                                {
                                    "TxnId": str(payment_data.get('invoice_ref')),
                                    "TxnType": "Invoice"
                                }
                            ]
                        }
                    ],
                    "PaymentRefNum": str(payment_ref_num)
                }

                headers = self._get_headers()
                response = requests.post(url, headers=headers, json=update_payload)
                response.raise_for_status()

                logger.info(f"✅ Updated payment with PaymentRefNum {payment_ref_num}, ID: {payment_id}")
                return {'Payment': response.json()['Payment']}

        # Format the payment date
        payment_date = payment_data.get('payment_date')
        if payment_date:
            if isinstance(payment_date, str):
                date_str = payment_date
            elif hasattr(payment_date, 'strftime'):
                date_str = payment_date.strftime('%Y-%m-%d')
            else:
                date_str = str(payment_date)
        else:
            date_str = date.today().strftime('%Y-%m-%d')

        # ✅ Create principal payment (linked to invoice)
        principal_payload = {
            "CustomerRef": {
                "value": str(payment_data.get('customer_ref'))
            },
            "TotalAmt": float(payment_data.get('principal_amount', payment_data.get('amount', 0))),
            "TxnDate": date_str,
            "Line": [
                {
                    "Amount": float(payment_data.get('principal_amount', payment_data.get('amount', 0))),
                    "LinkedTxn": [
                        {
                            "TxnId": str(payment_data.get('invoice_ref')),
                            "TxnType": "Invoice"
                        }
                    ]
                }
            ],
            "PaymentRefNum": payment_ref_num
        }

        headers = self._get_headers()

        import json
        logger.info(f"Sending principal payment to QuickBooks: {json.dumps(principal_payload, indent=2)}")

        response = requests.post(url, headers=headers, json=principal_payload)
        response.raise_for_status()

        # ✅ Create Sales Receipt for interest (does NOT reduce invoice)
        interest_amount = float(payment_data.get('interest_amount', 0))
        if interest_amount > 0:
            sales_receipt_url = f"{self.api_url}{self.token.realm_id}/salesreceipt"

            sales_receipt_payload = {
                "CustomerRef": {"value": str(payment_data.get('customer_ref'))},
                "Line": [
                    {
                        "Amount": interest_amount,
                        "DetailType": "SalesItemLineDetail",
                        "SalesItemLineDetail": {
                            "ItemRef": {"value": "19"}  # Interest Income item ID
                        }
                    }
                ],
                "TxnDate": date_str,
                "DocNumber": f"INT-{payment_ref_num}"
            }

            logger.info(f"Sending sales receipt for interest: {json.dumps(sales_receipt_payload, indent=2)}")

            response = requests.post(sales_receipt_url, headers=headers, json=sales_receipt_payload)
            response.raise_for_status()

        # ✅ Return ONLY the principal payment response
        return {'Payment': response.json()['Payment']} if 'Payment' in response.json() else response.json()


    def create_sales_receiptold(self, receipt_data):
        """Create a sales receipt for interest income"""
        url = f"{self.api_url}{self.token.realm_id}/salesreceipt"

        # Format the payment date
        payment_date = receipt_data.get('payment_date')
        if payment_date:
            if isinstance(payment_date, str):
                date_str = payment_date
            elif hasattr(payment_date, 'strftime'):
                date_str = payment_date.strftime('%Y-%m-%d')
            else:
                date_str = str(payment_date)
        else:
            date_str = date.today().strftime('%Y-%m-%d')

        # Build sales receipt payload
        payload = {
            "CustomerRef": {"value": str(receipt_data.get('customer_ref'))},
            "Line": [
                {
                    "Amount": float(receipt_data.get('total_amount', 0)),
                    "DetailType": "SalesItemLineDetail",
                    "SalesItemLineDetail": {
                        "ItemRef": {"value": "19"}  # Interest Income item ID
                    }
                }
            ],
            "TxnDate": date_str,
            "DocNumber": receipt_data.get('PaymentRefNum', '')
        }

        headers = self._get_headers()

        import json
        logger.info(f"Sending sales receipt to QuickBooks: {json.dumps(payload, indent=2)}")

        response = requests.post(url, headers=headers, json=payload)

        logger.info(f"Response status: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"Response body: {response.text}")

        response.raise_for_status()
        return response.json()


    def create_sales_receipt(self, receipt_data):
        """Create a sales receipt for interest income - with duplicate check"""
        url = f"{self.api_url}{self.token.realm_id}/salesreceipt"

        # ✅ Check for duplicates using DocNumber
        doc_number = receipt_data.get('PaymentRefNum', '')
        if doc_number:
            existing = self.find_sales_receipt_by_doc_number(doc_number)
            if existing:
                logger.info(f"✅ Sales Receipt already exists with DocNumber {doc_number}, ID: {existing.get('Id')}")
                return {'SalesReceipt': existing}

        # Format the payment date
        payment_date = receipt_data.get('payment_date')
        if payment_date:
            if isinstance(payment_date, str):
                date_str = payment_date
            elif hasattr(payment_date, 'strftime'):
                date_str = payment_date.strftime('%Y-%m-%d')
            else:
                date_str = str(payment_date)
        else:
            date_str = date.today().strftime('%Y-%m-%d')

        # Build sales receipt payload
        payload = {
            "CustomerRef": {"value": str(receipt_data.get('customer_ref'))},
            "Line": [
                {
                    "Amount": float(receipt_data.get('total_amount', 0)),
                    "DetailType": "SalesItemLineDetail",
                    "SalesItemLineDetail": {
                        "ItemRef": {"value": "19"}  # Interest Income item ID
                    }
                }
            ],
            "TxnDate": date_str,
            "DocNumber": doc_number
        }

        headers = self._get_headers()

        import json
        logger.info(f"Sending sales receipt to QuickBooks: {json.dumps(payload, indent=2)}")

        response = requests.post(url, headers=headers, json=payload)

        logger.info(f"Response status: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"Response body: {response.text}")

        response.raise_for_status()
        return response.json()

    def get_all_sales_receipts(self):
        """Fetch all sales receipts from QuickBooks"""
        url = f"{self.api_url}{self.token.realm_id}/query"
        query = "SELECT * FROM SalesReceipt"

        headers = self._get_headers()
        params = {'query': query}

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()
        return data.get('QueryResponse', {}).get('SalesReceipt', [])


    def find_sales_receipt_by_doc_number(self, doc_number):
        """Find a sales receipt by its DocNumber"""
        if not doc_number:
            return None

        url = f"{self.api_url}{self.token.realm_id}/query"
        query = f"SELECT * FROM SalesReceipt WHERE DocNumber = '{doc_number}'"

        headers = self._get_headers()
        params = {'query': query}

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()
        receipts = data.get('QueryResponse', {}).get('SalesReceipt', [])

        if receipts:
            logger.info(f"✅ Sales Receipt found with DocNumber {doc_number}, ID: {receipts[0].get('Id')}")
            return receipts[0]
        return None

    def sync_payment_to_quickbooks(self, payment):
        """Sync an installment payment from Django to QuickBooks."""

        # Get invoice data
        if not payment.loan or not payment.loan.quickbooks_invoice_id:
            logger.warning(f"Loan {payment.loan_id} not synced to QuickBooks yet.")
            return False

        # Check for duplicates using PaymentRefNum
        payment_ref_num = payment.receipt_number
        existing = self.find_payment_by_reference(payment_ref_num)
        if existing:
            logger.info(f"Payment {payment_ref_num} already exists in QuickBooks.")
            return True

        # ✅ Calculate principal and interest split
        principal_portion = float(payment.principal_applied)
        interest_portion = float(payment.interest_applied)

        # Build the payment payload with split
        payment_data = {
            'customer_ref': payment.loan.quickbooks_customer_id,
            'invoice_ref': payment.loan.quickbooks_invoice_id,
            'total_amount': float(payment.amount),
            'principal_amount': principal_portion,
            'interest_amount': interest_portion,
            'payment_date': payment.payment_date,
            'PaymentRefNum': payment_ref_num,
            'memo': f"Installment payment for {payment.loan.loan_id}",
        }

        # Call your existing create_payment method
        result = self.create_payment(payment_data)
        payment.quickbooks_payment_id = result['Payment']['Id']
        payment.save()

        return True




    def get_customer(self, customer_id):
        """Fetch a customer from QuickBooks by ID"""
        url = f"{self.api_url}{self.token.realm_id}/customer/{customer_id}"
        headers = self._get_headers()

        logger.info(f"🔍 Fetching customer {customer_id} from QuickBooks")

        response = requests.get(url, headers=headers)

        if response.status_code == 404:
            logger.warning(f"⚠️ Customer {customer_id} not found in QuickBooks")
            return None

        response.raise_for_status()
        return response.json()

    def get_invoice(self, invoice_id):
        """Fetch an invoice from QuickBooks by ID"""
        url = f"{self.api_url}{self.token.realm_id}/invoice/{invoice_id}"
        headers = self._get_headers()

        logger.info(f"🔍 Fetching invoice {invoice_id} from QuickBooks")

        response = requests.get(url, headers=headers)

        if response.status_code == 404:
            logger.warning(f"⚠️ Invoice {invoice_id} not found in QuickBooks")
            return None

        response.raise_for_status()
        return response.json()

    def get_payment(self, payment_id):
        """Fetch a payment from QuickBooks by ID"""
        url = f"{self.api_url}{self.token.realm_id}/payment/{payment_id}"
        headers = self._get_headers()

        logger.info(f"🔍 Fetching payment {payment_id} from QuickBooks")

        response = requests.get(url, headers=headers)

        if response.status_code == 404:
            logger.warning(f"⚠️ Payment {payment_id} not found in QuickBooks")
            return None

        response.raise_for_status()
        return response.json()

    def verify_loan_sync(self, loan):
        """Verify if a loan is properly synced to QuickBooks"""
        result = {
            'verified': False,
            'customer_exists': False,
            'invoice_exists': False,
            'payment_exists': False,
            'details': {}
        }

        # Check customer
        if loan.quickbooks_customer_id:
            customer = self.get_customer(loan.quickbooks_customer_id)
            if customer:
                result['customer_exists'] = True
                result['details']['customer'] = customer.get('Customer', {})

        # Check invoice
        if loan.quickbooks_invoice_id:
            invoice = self.get_invoice(loan.quickbooks_invoice_id)
            if invoice:
                result['invoice_exists'] = True
                result['details']['invoice'] = invoice.get('Invoice', {})

                # Verify amount matches
                qb_amount = float(invoice.get('Invoice', {}).get('TotalAmt', 0))
                django_amount = float(loan.principal_amount)
                result['details']['amount_match'] = abs(qb_amount - django_amount) < 0.01

        # Check payment (if deposit was made)
        if loan.quickbooks_payment_id:
            payment = self.get_payment(loan.quickbooks_payment_id)
            if payment:
                result['payment_exists'] = True
                result['details']['payment'] = payment.get('Payment', {})

        # Overall verification
        result['verified'] = (
            result['customer_exists'] and
            result['invoice_exists']
        )

        return result
    def get_all_customers(self):
        """Fetch all customers from QuickBooks"""
        url = f"{self.api_url}{self.token.realm_id}/query"
        query = "SELECT * FROM Customer"

        headers = self._get_headers()
        params = {'query': query}

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()
        return data.get('QueryResponse', {}).get('Customer', [])

    def get_all_invoices(self):
        """Fetch all invoices from QuickBooks"""
        url = f"{self.api_url}{self.token.realm_id}/query"
        query = "SELECT * FROM Invoice"

        headers = self._get_headers()
        params = {'query': query}

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()
        return data.get('QueryResponse', {}).get('Invoice', [])

    def get_all_payments(self):
        """Fetch all payments from QuickBooks"""
        url = f"{self.api_url}{self.token.realm_id}/query"
        query = "SELECT * FROM Payment"

        headers = self._get_headers()
        params = {'query': query}

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()
        return data.get('QueryResponse', {}).get('Payment', [])

