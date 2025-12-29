import base64
from odoo import models, fields, api
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import pytz
import requests
from .EncryptDecrypt import Encrypt, Decrypt
import logging

_logger = logging.getLogger(__name__)

from odoo.modules.module import get_module_path

MODULE_PATH = get_module_path('payments_ahorita')

# from EncryptDecrypt import Encrypt, Decrypt


class Payment(models.Model):
    _name = 'payment.payment'
    _description = 'Pago ahorita'

    def get_param(self, key):
        return self.env['ir.config_parameter'].sudo().get_param(key) or ""

    def get_credentials_json(self):
        """Load JSON data from file or return default"""
        json_file = Path('credentials.json')
        if json_file.exists():
            with open(json_file, 'r', encoding='utf-8') as file:
                return json.load(file)
        return ""

    def generate_keys(self):
        # Generate a 256-bit (32-byte) AES key (fixed from 16 to 32 bytes)
        aes_key = os.urandom(16)

        # Generate a 128-bit (16-byte) Initialization Vector
        iv = os.urandom(16)

        # Convert both to Base64
        aes_key_b64 = base64.b64encode(aes_key).decode('utf-8')
        iv_b64 = base64.b64encode(iv).decode('utf-8')

        # Concatenate with | separator
        combined = f"{aes_key_b64}|{iv_b64}"

        return combined

    def get_public_key(self):
        """Load JSON data from file or return default"""
        json_file = Path('public_key.pem')
        if json_file.exists():
            with open(json_file, 'r', encoding='utf-8') as file:
                return file.read()
        return ""

    def get_private_key(self):
        """Load JSON data from file or return default"""
        json_file = Path('private_key.pem')
        if json_file.exists():
            with open(json_file, 'r', encoding='utf-8') as file:
                return file.read()
        return ""

    def post_data(self, url, secret, data, bearer=""):
        payload = {
            "clientCode": "consultaCuxibamba",
            "secret": [
                secret
            ],
            "data": data
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"

        response = requests.post(
            url,
            data=json.dumps(payload),  # Convert dict to JSON string
            headers=headers,
            verify=False
        )
        decript = Decrypt()
        if response.status_code == 200:
            result = json.loads(response.text.encode("UTF-8"))
            secret_decrypted = decript.decrypt_with_rsa(self.get_private_key(), result["secret"][0])
            json_decrypted = decript.decrypt_json_AES(result["data"], secret_decrypted)
            data = {"secret": secret_decrypted, "data": json_decrypted}
            return data
        else:
            print(f"Request failed with status code {response.status_code}")
            return False

    def get_token(self):
        key = self.generate_keys()
        json_data = self.get_credentials_json()
        encript = Encrypt()
        # Encrypt the JSON data with AES
        encrypted_data = encript.encrypt_json_AES(json_data, key)
        public_key_pem = self.get_public_key()
        secret_encrypted = encript.encrypt_with_rsa(public_key_pem, key)
        data = self.post_data(
            self.get_param('ahorita_token_url'),
            secret_encrypted,
            encrypted_data
        )
        if data:
            bearer = data["data"]["data"]["token"]
            secret = data["secret"]
            return {"secret": secret, "bearer": bearer}
        return ""

    def format_time(self, dt):
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]

    def get_credentials_json(self):
        json_file = Path(MODULE_PATH) / 'data' / 'credentials.json'
        if json_file.exists():
            with open(json_file, 'r', encoding='utf-8') as file:
                return json.load(file)
        return ""

    def get_public_key(self):
        pem_path = Path(MODULE_PATH) / 'data' / 'public_key.pem'
        if pem_path.exists():
            return pem_path.read_text(encoding='utf-8')
        return ""

    def get_private_key(self):
        pem_path = Path(MODULE_PATH) / 'data' / 'private_key.pem'
        if pem_path.exists():
            return pem_path.read_text(encoding='utf-8')
        return ""

    def generateDeeplink(self, userId=415472, messageId="Nro. Factura", transactionId="PK factura",
                         deviceId="127.0.01", amount=0.10):
        """Load JSON data from file or return default"""
        json_file = Path(MODULE_PATH) / 'data' / 'example.json'
        if json_file.exists():
            with open(json_file, 'r', encoding='utf-8') as file:
                json_data = json.load(file)
                json_data["userId"] = userId
                json_data["messageId"] = messageId
                json_data["transactionId"] = transactionId
                json_data["deviceId"] = deviceId
                json_data["information"]["deepLinksInformation"][0]["amount"] = amount
                timezone = pytz.timezone("America/Guayaquil")
                current_time = datetime.now(timezone)
                json_data["messageCreationDate"] = self.format_time(current_time)
                # El enlace estará disponible por 10 horas
                json_data["information"]["deepLinksInformation"][0]["dateTimeExpired"] = self.format_time(
                    current_time + timedelta(hours=10))
                data = self.get_token()
                deeplink = ""
                encript = Encrypt()
                public_key_pem = self.get_public_key()
                encrypted_secret = encript.encrypt_with_rsa(public_key_pem, data["secret"])
                encrypted_data = encript.encrypt_json_AES(json_data, data["secret"])
                result = self.post_data(
                    self.get_param('ahorita_generate_url'),
                    encrypted_secret,
                    encrypted_data,
                    data["bearer"]
                )
                if result["data"] and result["data"]["information"] and result["data"]["information"]["deeplink"]:
                    deeplink = result["data"]["information"]["deeplink"] or "none"
                    deeplink = self.get_param('ahorita_deeplink_url') + deeplink
                return deeplink
        return ""

    def queryPayment(self, userId=415472, messageId="Nro. Factura", transactionId="PK factura",
                     deviceId="127.0.01", amount=0.10):
        """Load JSON data from file or return default"""
        json_file = Path('get_payment.json')
        if json_file.exists():
            with open(json_file, 'r', encoding='utf-8') as file:
                json_data = json.load(file)
                # json_data["UserId"] = userId
                # json_data["MessageId"] = messageId
                # json_data["TransactionId"] = transactionId
                # json_data["SourceIP"] = deviceId
                # json_data["information"]["deepLinksInformation"][0]["amount"] = amount
                # timezone = pytz.timezone("America/Guayaquil")
                # current_time = datetime.now(timezone)
                # json_data["messageCreationDate"] = self.format_time(current_time)
                # # El enlace estará disponible por 10 horas
                # json_data["information"]["deepLinksInformation"][0]["dateTimeExpired"] = self.format_time(
                #     current_time + timedelta(hours=10))
                data = self.get_token()
                deeplink = ""
                encript = Encrypt()
                public_key_pem = self.get_public_key()
                encrypted_secret = encript.encrypt_with_rsa(public_key_pem, data["secret"])
                encrypted_data = encript.encrypt_json_AES(json_data, data["secret"])
                result = self.post_data(
                    self.get_param('ahorita_query_url'),
                    encrypted_secret,
                    encrypted_data,
                    data["bearer"]
                )
                print(result)
                # if result["data"] and result["data"]["information"] and result["data"]["information"]["deeplink"]:
                #     deeplink = result["data"]["information"]["deeplink"] or "none"
                #     deeplink = self.deeplink_url + deeplink
                return deeplink
        return ""

