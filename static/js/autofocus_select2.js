(function () {
    "use strict";
    // Regex for the select2 class
    const select2_regex = /^select2-/

    function add_focus2(e){
        // Get the classlist of the target, check if it has a select2 class,
        // if so get the select2 input and focus it
        let classList = e.target.classList;
        if(Array.from(classList).some(e=> select2_regex.test(e))){
            let select2_input = document.querySelector(".select2-search__field");
            if (select2_input) {
                select2_input.focus();
            }
        }
    }
    // Add the event listener to the main content (#content-main)
    function add_click_listener() {
        // Seules les listes et les fiches d'Unfold ont #content-main ; le tableau de bord,
        // les pages de module et de domaine n'en ont pas : rien a ecouter.
        // / Only Unfold lists and forms have #content-main; the dashboard, module and
        // domain pages don't: nothing to listen to.
        const contenu_principal = document.querySelector("#content-main");
        if (!contenu_principal) {
            return;
        }
        contenu_principal.addEventListener("click", add_focus2, true);
    }

    // Add an event lister to listen for click
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", add_click_listener);
    } else {
        add_click_listener();
    }

})()