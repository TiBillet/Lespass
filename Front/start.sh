# Petit soucis de licence qui empêche
# certains assets d'être up sur gituhb.
# On s'en occupe bientôt, promis !
cp -r /nonfree/css/now-design* /Front/src/assets/css/
cp -r /nonfree/css/nucleo* /Front/src/assets/css/
cp -r /nonfree/js/now-design* /Front/src/assets/js/
cp -r /nonfree/fonts/nucleo* /Front/src/assets/fonts/

npm install
#npm run dev
sleep 30d