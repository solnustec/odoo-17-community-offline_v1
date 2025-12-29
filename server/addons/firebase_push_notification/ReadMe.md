**Notificaciones Push firebase para la aplicación móvil**

- Requerimientos
    - obtener credenciales de firebase en formato json
    - Crear un parametro del sistema en odoo ```ir.config_parameter```, `Ajustes/Tecnico/Parámetros del sistema` con la
      clave ```firebase.credentials_json```
    - formato del archivo json de credenciales de firebase
    - `{
"type": "service_account",
"project_id": "fcuxibamba-94",
"private_key_id": "a47fd06c428833f4d79399",
"private_key": "-----BEGIN PRIVATE
KEY-----\==\n-----END
PRIVATE KEY-----\n",
"client_email": "firebase-adminsdk-fbsvc@fcuxibamba-94.iam.gserviceaccount.com",
"client_id": "106290930309-1-62",
"auth_uri": "https://accounts.google.com/o/oauth2/auth",
"token_uri": "https://oauth2.googleapis.com/token",
"auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
"
client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40fcuxibamba-34.iam.gserviceaccount.com",
"universe_domain": "googleapis.com"
}
`
    - 

- Notificaciones Push firebase para la aplicación móvil

`
request.env['firebase.service'].send_push_notification(
registration_token="dpwk4dznS8vBY9mIGXxAUb:APA91bFJjnq57hs8WQOSBfBKiUFMkW2Xv_MdRvAhc0FL8buyOaD7gOlkgEN_B4ypxhhbwpKHH5ZEq2pGORBjkXCAUKmc3eeajqtLmMyjlo7ZAUFm_pvaE7w",
                    title="Banners",
                    body="asdasd"
                )
                `



