console.log('-> commun.js');
const domain = `${window.location.protocol}//${window.location.host}`;


function goPage(url) {
    // TODO: dev, pensez à modifier les urls (supprimer /mvt) pour la prod.
    url = domain + '/mvt' + url
    console.log('-> goPage dev, url =', url);
    window.location = url
}
