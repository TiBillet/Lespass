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
        document.querySelector("#content-main").addEventListener("click",add_focus2,true);
    }

    // Add an event lister to listen for click
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", add_click_listener);
    } else {
        add_click_listener();
    }

})()