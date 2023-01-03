## Install :

#curl -s https://packages.stripe.dev/api/security/keypair/stripe-cli-gpg/public | gpg --dearmor | sudo tee /usr/share/keyrings/stripe.gpg
#echo "deb [signed-by=/usr/share/keyrings/stripe.gpg] https://packages.stripe.dev/stripe-cli-debian-local stable main" | sudo tee -a /etc/apt/sources.list.d/stripe.list
#sudo apt update
#sudo apt install stripe
#stripe login

## RUN :

stripe listen --forward-to https://tibillet.localhost/api/webhook_stripe/ --skip-verify
