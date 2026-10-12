
// Force le theme clair pour l'admin tant que le theme dark n'est pas implémenté.
// Sert dans le cas où le mode "dark" a été activé avant la màj V2

const LIGHT_THEME_KEY = "\"light\""
window.onload = function (){
    let theme = localStorage.getItem("adminTheme");
    if(theme !== LIGHT_THEME_KEY) {
        localStorage.setItem("adminTheme", LIGHT_THEME_KEY);
        location.reload();
    }
}