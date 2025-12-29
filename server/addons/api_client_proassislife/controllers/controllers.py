import requests
import json
from odoo import http
from odoo.http import request


class ExternalAPIController(http.Controller):

    @http.route('/api/get_token', type='json', auth='public', methods=['POST'], csrf=False)
    def get_token(self):
        url = "https://proassisapp.com/proassislife/servicios/oauth/token"
        headers = {
            "Cache-Control": "no-cache",
            "Authorization": "Basic QlUxdUxpTmZmbkEyV0tzMUphTVRRdy4uOmFBcEQwb3RrVS1vUzRYd21NQURRUHcuLg==",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "client_credentials"}

        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
