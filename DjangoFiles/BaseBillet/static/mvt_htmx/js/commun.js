console.log('-> commun.js');
const domain = `${window.location.protocol}//${window.location.host}`;
console.log('domain =', domain);

 // une fois l'élément remplacé par le contenu de la requête
 htmx.on("htmx:afterSettle", (evt) => {
  console.log('-> htmx:afterSwap evt =', evt);
  
  if (evt.target.id === "tibillet-membership-modal") {
    const elementModal = document.querySelector(
      "#tibillet-membership-modal",
    );
    const modal = bootstrap.Modal.getOrCreateInstance(elementModal); // Returns a Bootstrap modal instance
    modal.show();
  }
});