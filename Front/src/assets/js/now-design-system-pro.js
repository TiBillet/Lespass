/*!

=========================================================
* Now UI Design System PRO - v2.1.0
=========================================================

* Product Page: https://www.creative-tim.com/product/soft-ui-design-system
* Copyright 2021 Creative Tim (https://www.creative-tim.com)

* Coded by Creative Tim

=========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

*/

// Function for smooth scroll to element
function smoothToPricing(id) {
  if (document.getElementById(id)) {
    document.getElementById(id).scrollIntoView({
      behavior: 'smooth'
    });
  }
}

// initialization of Popovers
var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'))
var popoverList = popoverTriggerList.map(function(popoverTriggerEl) {
  return new bootstrap.Popover(popoverTriggerEl)
})

// initialization of Tooltips
var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
var tooltipList = tooltipTriggerList.map(function(tooltipTriggerEl) {
  return new bootstrap.Tooltip(tooltipTriggerEl)
})

// helper for adding on all elements multiple attributes
function setAttributes(el, options) {
  Object.keys(options).forEach(function(attr) {
    el.setAttribute(attr, options[attr]);
  })
}

// activate popovers
var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-toggle="popover"]'))
var popoverList = popoverTriggerList.map(function(popoverTriggerEl) {
  return new bootstrap.Popover(popoverTriggerEl)
})

// activate tooltips
var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-toggle="tooltip"]'))
var tooltipList = tooltipTriggerList.map(function(tooltipTriggerEl) {
  return new bootstrap.Tooltip(tooltipTriggerEl)
})

// Multi Level Dropdown
function dropDown(a) {
  if (!document.querySelector('.dropdown-hover')) {
    event.stopPropagation();
    event.preventDefault();
    var multilevel = a.parentElement.parentElement.children;


    for (var i = 0; i < multilevel.length; i++) {
      if (multilevel[i].lastElementChild != a.parentElement.lastElementChild) {
        multilevel[i].lastElementChild.classList.remove('show');
        multilevel[i].firstElementChild.classList.remove('show');
      }
    }

    if (!a.nextElementSibling.classList.contains("show")) {
      a.nextElementSibling.classList.add("show");
      a.classList.add("show");

    } else {
      a.nextElementSibling.classList.remove("show");
      a.classList.remove("show");

    }
  }
}

// Colored shadows from Cards
if (document.querySelector('.blur-shadow-node16')) {
  var shadowCards = document.querySelectorAll('.blur-shadow-node16');

  for (var i = 0; i < shadowCards.length; i++) {
    var div = document.createElement("DIV");
    shadowCards[i].parentElement.appendChild(div);
    div.classList.add('colored-shadow');


    var currentSrc = shadowCards[i].children[0].getAttribute('src');
    var el = shadowCards[i].nextElementSibling;

    el.style.backgroundImage = 'url(' + currentSrc + ')';
  }
}

// Colored shadows for Avatars
if (document.querySelector('.blur-shadow-avatar')) {

  var shadowCards = document.querySelectorAll('.blur-shadow-avatar');

  for (var i = 0; i < shadowCards.length; i++) {

    var div = document.createElement("DIV");
    shadowCards[i].parentElement.appendChild(div);
    div.classList.add('colored-shadow', 'start-0', 'end-0', 'mx-auto');

    var avatarClasses = ['avatar-xs', 'avatar-sm', 'avatar-lg', 'avatar-xl', 'avatar-xxl'];

    for (var k = 0; k < avatarClasses.length; k++) {
      if (shadowCards[i].firstElementChild.classList.contains(avatarClasses[k])) {
        div.classList.add(avatarClasses[k]);
      }
    }

    var currentSrc = shadowCards[i].children[0].getAttribute('src');
    var el = shadowCards[i].nextElementSibling;

    el.style.backgroundImage = 'url(' + currentSrc + ')';
  }
}

//Google Maps
if (document.querySelector('#google-maps')) {
  var myLatlng = new google.maps.LatLng(40.748817, -73.985428);
  var mapOptions = {
    zoom: 13,
    center: myLatlng,
    scrollwheel: false, //we disable de scroll over the map, it is a really annoing when you scroll through page
    styles: [{
        "featureType": "administrative",
        "elementType": "labels.text.fill",
        "stylers": [{
          "color": "#444444"
        }]
      },
      {
        "featureType": "landscape",
        "elementType": "all",
        "stylers": [{
          "color": "#f2f2f2"
        }]
      },
      {
        "featureType": "poi",
        "elementType": "all",
        "stylers": [{
          "visibility": "off"
        }]
      },
      {
        "featureType": "road",
        "elementType": "all",
        "stylers": [{
          "saturation": -100
        }, {
          "lightness": 45
        }]
      },
      {
        "featureType": "road.highway",
        "elementType": "all",
        "stylers": [{
          "visibility": "simplified"
        }]
      },
      {
        "featureType": "road.arterial",
        "elementType": "labels.icon",
        "stylers": [{
          "visibility": "off"
        }]
      },
      {
        "featureType": "transit",
        "elementType": "all",
        "stylers": [{
          "visibility": "off"
        }]
      },
      {
        "featureType": "water",
        "elementType": "all",
        "stylers": [{
          "color": "#C5CBF5"
        }, {
          "visibility": "on"
        }]
      }
    ]
  };

  var map = new google.maps.Map(document.getElementById("google-maps"), mapOptions);

  var marker = new google.maps.Marker({
    position: myLatlng,
    title: "Hello World!"
  });

  // To add the marker to the map, call setMap();
  marker.setMap(map);
}

// Tabs navigation

var total = document.querySelectorAll('.nav-pills');

total.forEach(function(item, i) {
  var moving_div = document.createElement('div');
  var first_li = item.querySelector('li:first-child .nav-link');
  var tab = first_li.cloneNode();
  tab.innerHTML = "-";

  moving_div.classList.add('moving-tab', 'position-absolute', 'nav-link', 'rounded-pill');
  moving_div.appendChild(tab);
  item.appendChild(moving_div);

  var list_length = item.getElementsByTagName("li").length;

  moving_div.style.padding = '0px';
  moving_div.style.width = item.querySelector('li:nth-child(1)').offsetWidth + 'px';
  moving_div.style.transform = 'translate3d(0px, 0px, 0px)';
  moving_div.style.transition = '.5s ease';

  item.onmouseover = function(event) {
    let target = getEventTarget(event);
    let li = target.closest('li'); // get reference
    if (li) {
      let nodes = Array.from(li.closest('ul').children); // get array
      let index = nodes.indexOf(li) + 1;
      item.querySelector('li:nth-child(' + index + ') .nav-link').onclick = function() {
        moving_div = item.querySelector('.moving-tab');
        let sum = 0;
        if (item.classList.contains('flex-column')) {
          for (var j = 1; j <= nodes.indexOf(li); j++) {
            sum += item.querySelector('li:nth-child(' + j + ')').offsetHeight;
          }
          moving_div.style.transform = 'translate3d(0px,' + sum + 'px, 0px)';
          moving_div.style.height = item.querySelector('li:nth-child(' + j + ')').offsetHeight;
        } else {
          for (var j = 1; j <= nodes.indexOf(li); j++) {
            sum += item.querySelector('li:nth-child(' + j + ')').offsetWidth;
          }
          moving_div.style.transform = 'translate3d(' + sum + 'px, 0px, 0px)';
          moving_div.style.width = item.querySelector('li:nth-child(' + index + ')').offsetWidth + 'px';
        }
      }
    }
  }
});


// Tabs navigation resize

window.addEventListener('resize', function(event) {
  total.forEach(function(item, i) {
    item.querySelector('.moving-tab').remove();
    var moving_div = document.createElement('div');
    var tab = item.querySelector(".nav-link.active").cloneNode();
    tab.innerHTML = "-";

    moving_div.classList.add('moving-tab', 'position-absolute', 'nav-link', 'rounded-pill');
    moving_div.appendChild(tab);

    item.appendChild(moving_div);

    moving_div.style.padding = '0px';
    moving_div.style.transition = '.5s ease';

    let li = item.querySelector(".nav-link.active").parentElement;

    if (li) {
      let nodes = Array.from(li.closest('ul').children); // get array
      let index = nodes.indexOf(li) + 1;

      let sum = 0;
      if (item.classList.contains('flex-column')) {
        for (var j = 1; j <= nodes.indexOf(li); j++) {
          sum += item.querySelector('li:nth-child(' + j + ')').offsetHeight;
        }
        moving_div.style.transform = 'translate3d(0px,' + sum + 'px, 0px)';
        moving_div.style.width = item.querySelector('li:nth-child(' + index + ')').offsetWidth + 'px';
        moving_div.style.height = item.querySelector('li:nth-child(' + j + ')').offsetHeight;
      } else {
        for (var j = 1; j <= nodes.indexOf(li); j++) {
          sum += item.querySelector('li:nth-child(' + j + ')').offsetWidth;
        }
        moving_div.style.transform = 'translate3d(' + sum + 'px, 0px, 0px)';
        moving_div.style.width = item.querySelector('li:nth-child(' + index + ')').offsetWidth + 'px';

      }
    }
  });

  if (window.innerWidth < 991) {
    total.forEach(function(item, i) {
      if (!item.classList.contains('flex-column')) {
        item.classList.add('flex-column', 'on-resize');
      }
    });
  } else {
    total.forEach(function(item, i) {
      if (item.classList.contains('on-resize')) {
        item.classList.remove('flex-column', 'on-resize');
      }
    })
  }
});


function getEventTarget(e) {
  e = e || window.event;
  return e.target || e.srcElement;
}

// End tabs navigation


// Copy code function

function copyCode(el) {
  const selection = window.getSelection();
  const range = document.createRange();
  const textToCopy = el.nextElementSibling;
  range.selectNodeContents(textToCopy);
  selection.removeAllRanges();
  selection.addRange(range);
  const successful = document.execCommand('copy');
  window.getSelection().removeAllRanges()
  if (!el.parentElement.querySelector('.alert')) {
    var alert = document.createElement('div');
    alert.classList.add('alert', 'alert-success', 'position-absolute', 'top-0', 'border-0', 'text-white', 'w-25', 'end-0', 'start-0', 'mt-2', 'mx-auto', 'py-2');
    alert.style.transform = 'translate3d(0px, 0px, 0px)'
    alert.style.opacity = '0';
    alert.style.transition = '.35s ease';
    setTimeout(function() {
      alert.style.transform = 'translate3d(0px, 20px, 0px)';
      alert.style.setProperty("opacity", "1", "important");
    }, 100);
    alert.innerHTML = "Code successfully copied!";
    el.parentElement.appendChild(alert);
    setTimeout(function() {
      alert.style.transform = 'translate3d(0px, 0px, 0px)'
      alert.style.setProperty("opacity", "0", "important");
    }, 2000);
    setTimeout(function() {
      el.parentElement.querySelector('.alert').remove();
    }, 2500);
  }
}

// End copy code function