-- disable stripe payment provider
UPDATE payment_provider
   SET paymentez_application_key = NULL,
       paymentez_application_code = NULL,
