# Django, ajout "Access-Control-Allow-Origin"
- Dans le conteneur:
```
pip install django-cors-headers
```
- Dans TiBillet/settings.py:   
. SHARED_APPS = (   
...   
'corsheaders',   
  )  
- 
. MIDDLEWARE = [  
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    ...
]   
corsheaders.middleware.CorsMiddleware avant django.middleware.common.CommonMiddleware   


. CORS_ORIGIN_ALLOW_ALL=True   
ou
CORS_ORIGIN_WHITELIST = [   
    'http://google.com',   
    'http://hostname.example.com',   
    'http://localhost:8000',   
    'http://127.0.0.1:9000'   
]   