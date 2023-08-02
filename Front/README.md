# Vue 3 + Vite

## Récupérer le projet
https://git.3peaks.re/icon/TibilletGestionLieuVue.git
- git clone   
        ou
- téléchargement

## Installer les modules du projet
````
cd "répertoire racine du projet"
npm install
````

## Lancer le serveur de développement
````
npm run dev
````

## Conteneur docker (dans le dossier Docker)

### Lancement du conteneur
````
docker-compose up -d
docker exec -ti node16 bash
````

### Installation des modules du projet (Le faire qu'une fois !!)
````
cd tibillet-gestion-lieu-vue
npm install
````

### Lancer le serveur(front) de développement
````
cd tibillet-gestion-lieu-vue
npm run dev
````

## Divers
### Comment créer un projet vue3 avec vite
- Installation
````
npm create vite@latest tibillet-billetterie-vue --template vue
cd tibillet-billetterie-vue
npm install
````

- Dépendances

````
npm install vue -S
npm install vuex@next -S
npm install mitt -S
npm install vuex-persistedstate -S
````

- Ajouter une variable globale à vue
````
let app = createApp(App)
app.config.globalProperties.globalVar = 'globalVar'
app.use(router).mount('#app')
````
