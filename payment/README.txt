BISNU-X PAYMENT CONFIGURATION

CURRENT STATE
-------------
Razorpay credentials are intentionally NOT configured.

Therefore:

PREMIUM = COMING SOON
ULTRA   = COMING SOON

When the production Razorpay configuration is added on the
backend/server:

RAZORPAY_KEY_ID
RAZORPAY_KEY_SECRET
RAZORPAY_WEBHOOK_SECRET
RAZORPAY_PREMIUM_PLAN_ID
RAZORPAY_ULTRA_PLAN_ID

the corresponding plans become available automatically.

IMPORTANT
---------
The payment QR does NOT grant Premium.

Premium access is granted only after the backend receives and
cryptographically verifies the Razorpay webhook.

Never put RAZORPAY_KEY_SECRET or RAZORPAY_WEBHOOK_SECRET
inside the Android APK.
