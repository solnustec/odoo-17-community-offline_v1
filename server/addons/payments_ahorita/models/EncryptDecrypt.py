import os
import base64
import json
from pathlib import Path

import requests
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad, unpad
from Crypto.Hash import SHA256


class Encrypt:
    @staticmethod
    def encrypt_with_rsa(public_key_pem, plaintext):
        """Encrypt data with RSA public key using OAEP-SHA256"""
        try:
            # Normalize PEM format if needed
            if "-----BEGIN PUBLIC KEY-----" not in public_key_pem:
                body = public_key_pem.strip().replace("\n", "")
                formatted = "\n".join(body[i:i + 64] for i in range(0, len(body), 64))
                public_key_pem = f"-----BEGIN PUBLIC KEY-----\n{formatted}\n-----END PUBLIC KEY-----"

            public_key = RSA.import_key(public_key_pem)
            cipher = PKCS1_OAEP.new(public_key, hashAlgo=SHA256)

            data_bytes = plaintext.encode('utf-8')
            max_length = public_key.size_in_bytes() - 2 * SHA256.digest_size - 2

            if len(data_bytes) > max_length:
                raise ValueError(f"Data too long for RSA encryption. Max is {max_length} bytes")

            encrypted = cipher.encrypt(data_bytes)
            return base64.b64encode(encrypted).decode('utf-8')

        except Exception as e:
            raise ValueError(f"RSA encryption failed: {e}")

    @staticmethod
    def encrypt_json_AES(data, combined_key):
        """Encrypt JSON data with AES-CBC"""
        try:
            aes_key_b64, iv_b64 = combined_key.split("|")
            aes_key = base64.b64decode(aes_key_b64)
            iv = base64.b64decode(iv_b64)

            json_str = json.dumps(data)
            data_bytes = json_str.encode('utf-8')

            cipher = AES.new(aes_key, AES.MODE_CBC, iv)
            padded_data = pad(data_bytes, AES.block_size)
            encrypted_data = cipher.encrypt(padded_data)

            return base64.b64encode(encrypted_data).decode('utf-8')
        except Exception as e:
            raise ValueError(f"AES encryption failed: {str(e)}")

class Decrypt():
    @staticmethod
    def decrypt_with_rsa(private_key_pem, encrypted_b64):
        """Decrypt Base64-encoded RSA-encrypted string using OAEP-SHA256"""
        try:
            private_key = RSA.import_key(private_key_pem)
            cipher = PKCS1_OAEP.new(private_key, hashAlgo=SHA256)

            encrypted_bytes = base64.b64decode(encrypted_b64)
            decrypted_bytes = cipher.decrypt(encrypted_bytes)

            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            raise ValueError(f"RSA decryption failed: {e}")

    @staticmethod
    def decrypt_json_AES(encrypted_b64, combined_key):
        """Decrypt AES-CBC encrypted Base64 string back to JSON"""
        try:
            aes_key_b64, iv_b64 = combined_key.split("|")
            aes_key = base64.b64decode(aes_key_b64)
            iv = base64.b64decode(iv_b64)

            encrypted_data = base64.b64decode(encrypted_b64)

            cipher = AES.new(aes_key, AES.MODE_CBC, iv)
            padded_data = cipher.decrypt(encrypted_data)
            data_bytes = unpad(padded_data, AES.block_size)

            json_str = data_bytes.decode('utf-8')
            return json.loads(json_str)
        except Exception as e:
            raise ValueError(f"AES decryption failed: {str(e)}")