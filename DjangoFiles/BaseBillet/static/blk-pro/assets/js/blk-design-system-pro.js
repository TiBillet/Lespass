/*!

 =========================================================
 * Blk• Design System Pro - v1.0.0
 =========================================================

 * Product Page: https://www.creative-tim.com/product/blk-design-system-pro
 * Copyright 2019 Creative Tim (http://www.creative-tim.com)

 * Coded by www.creative-tim.com

 =========================================================

 * The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

 */


var transparent = true;
var big_image;

var transparentDemo = true;
var fixedTop = false;

var navbar_initialized,
  backgroundOrange = false,
  toggle_initialized = false;

var $datepicker = $('.datepicker');
var $collapse = $('.navbar .collapse');
var $html = $('html');
var $tagsinput = $('.tagsinput');

(function() {
  var isWindows = navigator.platform.indexOf('Win') > -1 ? true : false;

  if (isWindows) {
    // if we are on windows OS we activate the perfectScrollbar function


    if ($('.tab-content .table-responsive').length != 0) {

      $('.table-responsive').each(function() {
        var ps2 = new PerfectScrollbar($(this)[0]);
      });
    }



    $html.addClass('perfect-scrollbar-on');
  } else {
    $html.addClass('perfect-scrollbar-off');
  }
})();

$(document).ready(function() {

  // Multilevel Dropdown menu

  $('.dropdown-menu a.dropdown-toggle').on('click', function(e) {
    var $el = $(this);
    var $parent = $(this).offsetParent(".dropdown-menu");
    if (!$(this).next().hasClass('show')) {
      $(this).parents('.dropdown-menu').first().find('.show').removeClass("show");
    }
    var $subMenu = $(this).next(".dropdown-menu");
    $subMenu.toggleClass('show');

    $(this).closest("a").toggleClass('open');

    $(this).parents('a.dropdown-item.dropdown.show').on('hidden.bs.dropdown', function(e) {
      $('.dropdown-menu .show').removeClass("show");
    });

    if (!$parent.parent().hasClass('navbar-nav')) {
      $el.next().css({
        "top": $el[0].offsetTop,
        "left": $parent.outerWidth() - 4
      });
    }

    return false;
  });

  //  Activate the Tooltips
  $('[data-toggle="tooltip"], [rel="tooltip"]').tooltip();

  var tagClass = $tagsinput.data('color');

  if ($tagsinput.length != 0) {
    $tagsinput.tagsinput();
  }

  $('.bootstrap-tagsinput').find('.tag').addClass('badge-' + tagClass);

  //    Activate bootstrap-select

  if ($(".selectpicker").length != 0) {
    $(".selectpicker").selectpicker({
      iconBase: "tim-icons",
      tickIcon: "icon-check-2"
    });
  };

  if ($(window).width() >= 768) {
    big_image = $('.header[data-parallax="true"]');
    if (big_image.length != 0) {
      $(window).on('scroll', blackKit.checkScrollForParallax);
    }
  }


  // Activate Popovers and set color for popovers
  $('[data-toggle="popover"]').each(function() {
    color_class = $(this).data('color');
    $(this).popover({
      template: '<div class="popover popover-' + color_class + '" role="tooltip"><div class="arrow"></div><h3 class="popover-header"></h3><div class="popover-body"></div></div>'
    });
  });

  var squares1 = document.getElementById("square1");
  var squares2 = document.getElementById("square2");
  var squares3 = document.getElementById("square3");
  var squares4 = document.getElementById("square4");
  var squares5 = document.getElementById("square5");
  var squares6 = document.getElementById("square6");
  var squares9 = document.getElementById("square7");
  var squares10 = document.getElementById("square8");

  if (!(/^((?!chrome|android).)*safari/i.test(navigator.userAgent))) {
    if ($('.square').length != 0) {

      $(document).mousemove(function(e) {
        posX = event.clientX - window.innerWidth / 2;
        posY = event.clientY - window.innerWidth / 6;

        squares1.style.transform = "perspective(500px) rotateY(" + posX * 0.05 + "deg) rotateX(" + posY * (-0.05) + "deg)";
        squares2.style.transform = "perspective(500px) rotateY(" + posX * 0.05 + "deg) rotateX(" + posY * (-0.05) + "deg)";
        squares3.style.transform = "perspective(500px) rotateY(" + posX * 0.05 + "deg) rotateX(" + posY * (-0.05) + "deg)";
        squares4.style.transform = "perspective(500px) rotateY(" + posX * 0.05 + "deg) rotateX(" + posY * (-0.05) + "deg)";
        squares5.style.transform = "perspective(500px) rotateY(" + posX * 0.05 + "deg) rotateX(" + posY * (-0.05) + "deg)";
        squares6.style.transform = "perspective(500px) rotateY(" + posX * 0.05 + "deg) rotateX(" + posY * (-0.05) + "deg)";
        squares9.style.transform = "perspective(500px) rotateY(" + posX * 0.02 + "deg) rotateX(" + posY * (-0.02) + "deg)";
        squares10.style.transform = "perspective(500px) rotateY(" + posX * 0.02 + "deg) rotateX(" + posY * (-0.02) + "deg)";

      });
    }
  }

  // Activate the image for the navbar-collapse
  blackKit.initNavbarImage();

  $navbar = $('.navbar[color-on-scroll]');
  scroll_distance = $navbar.attr('color-on-scroll') || 500;

  // Check if we have the class "navbar-color-on-scroll" then add the function to remove the class "navbar-transparent" so it will transform to a plain color.
  if ($('.navbar[color-on-scroll]').length != 0) {
    blackKit.checkScrollForTransparentNavbar();
    $(window).on('scroll', blackKit.checkScrollForTransparentNavbar)
  }

  $('.form-control').on("focus", function() {
    $(this).parent('.input-group').addClass("input-group-focus");
  }).on("blur", function() {
    $(this).parent(".input-group").removeClass("input-group-focus");
  });

  // Activate bootstrapSwitch
  $('.bootstrap-switch').each(function() {
    $this = $(this);
    data_on_label = $this.data('on-label') || '';
    data_off_label = $this.data('off-label') || '';

    $this.bootstrapSwitch({
      onText: data_on_label,
      offText: data_off_label
    });
  });

  if ($(window).width() >= 992) {
    big_image = $('.page-header-image[data-parallax="true"]');

    $(window).on('scroll', blackKit.checkScrollForParallax);
  }

  // Activate Carousel
  $('.carousel').carousel({
    interval: 4000
  });

  if ($(".datetimepicker").length != 0) {
    $('.datetimepicker').datetimepicker({
      icons: {
        time: "tim-icons icon-watch-time",
        date: "tim-icons icon-calendar-60",
        up: "fa fa-chevron-up",
        down: "fa fa-chevron-down",
        previous: 'tim-icons icon-minimal-left',
        next: 'tim-icons icon-minimal-right',
        today: 'fa fa-screenshot',
        clear: 'fa fa-trash',
        close: 'fa fa-remove'
      }
    });
  }

  if ($(".datepicker").length != 0) {
    $('.datepicker').datetimepicker({
      format: 'MM/DD/YYYY',
      icons: {
        time: "tim-icons icon-watch-time",
        date: "tim-icons icon-calendar-60",
        up: "fa fa-chevron-up",
        down: "fa fa-chevron-down",
        previous: 'tim-icons icon-minimal-left',
        next: 'tim-icons icon-minimal-right',
        today: 'fa fa-screenshot',
        clear: 'fa fa-trash',
        close: 'fa fa-remove'
      }
    });
  }

  if ($(".timepicker").length != 0) {
    $('.timepicker').datetimepicker({
      //          format: 'H:mm',    // use this format if you want the 24hours timepicker
      format: 'h:mm A', //use this format if you want the 12hours timpiecker with AM/PM toggle
      icons: {
        time: "tim-icons icon-watch-time",
        date: "tim-icons icon-calendar-60",
        up: "fa fa-chevron-up",
        down: "fa fa-chevron-down",
        previous: 'tim-icons icon-minimal-left',
        next: 'tim-icons icon-minimal-right',
        today: 'fa fa-screenshot',
        clear: 'fa fa-trash',
        close: 'fa fa-remove'
      }
    });
  }
});


// Add (+/-) Button Number Incrementers

function up(max) {
  document.getElementById("myNumber").value = parseInt(document.getElementById("myNumber").value) + 1;
  if (document.getElementById("myNumber").value >= parseInt(max)) {
    document.getElementById("myNumber").value = max;
  }
}

function down(min) {
  document.getElementById("myNumber").value = parseInt(document.getElementById("myNumber").value) - 1;
  if (document.getElementById("myNumber").value <= parseInt(min)) {
    document.getElementById("myNumber").value = min;
  }
}




// Returns a function, that, as long as it continues to be invoked, will not
// be triggered. The function will be called after it stops being called for
// N milliseconds. If `immediate` is passed, trigger the function on the
// leading edge, instead of the trailing.

var didScroll;
var lastScrollTop = 0;
var delta = 5;
var navbarHeight = 0;

function hasScrolled() {
  var st = $(this).scrollTop();
  // Make sure they scroll more than delta
  if (Math.abs(lastScrollTop - st) <= delta)
    return;

  // If they scrolled down and are past the navbar, add class .nav-up.
  // This is necessary so you never see what is "behind" the navbar.
  if (st > lastScrollTop && st > navbarHeight) {
    // Scroll Down
    $('.navbar.nav-down').removeClass('nav-down').addClass('nav-up');
  } else {
    // Scroll Up
    if (st + $(window).height() < $(document).height()) {
      $('.navbar.nav-up').removeClass('nav-up').addClass('nav-down');
    }
  }

  lastScrollTop = st;
};

$(window).on('resize', function() {
  blackKit.initNavbarImage();
});


blackKit = {
  misc: {
    navbar_menu_visible: 0
  },

  checkScrollForTransparentNavbar: debounce(function() {
    if ($(document).scrollTop() > scroll_distance) {
      if (transparent) {
        transparent = false;
        $('.navbar[color-on-scroll]').removeClass('navbar-transparent');
      }
    } else {
      if (!transparent) {
        transparent = true;
        $('.navbar[color-on-scroll]').addClass('navbar-transparent');
      }
    }
  }, 17),

  initDatePicker: function() {
    if ($datepicker.length != 0) {
      $datepicker.datetimepicker({
        icons: {
          time: "tim-icons icon-watch-time",
          date: "tim-icons icon-calendar-60",
          up: "fa fa-chevron-up",
          down: "fa fa-chevron-down",
          previous: 'tim-icons icon-minimal-left',
          next: 'tim-icons icon-minimal-right',
          today: 'fa fa-screenshot',
          clear: 'fa fa-trash',
          close: 'fa fa-remove'
        }
      });
    }
  },

  initNavbarImage: function() {
    var $navbar = $('.navbar').find('.navbar-translate').siblings('.navbar-collapse');
    var background_image = $navbar.data('nav-image');

    if ($(window).width() < 991 || $('body').hasClass('burger-menu')) {
      if (background_image != undefined) {
        $navbar.css('background', "url('" + background_image + "')")
          .removeAttr('data-nav-image')
          .css('background-size', "cover")
          .addClass('has-image');
      }
    } else if (background_image != undefined) {
      $navbar.css('background', "")
        .attr('data-nav-image', '' + background_image + '')
        .css('background-size', "")
        .removeClass('has-image');
    }
  },

  initSliders: function() {
    // Sliders for demo purpose in refine cards section
    var slider = document.getElementById('sliderRegular');

    noUiSlider.create(slider, {
      start: 40,
      connect: [true, false],
      range: {
        min: 0,
        max: 100
      }
    });

    var slider2 = document.getElementById('sliderDouble');

    noUiSlider.create(slider2, {
      start: [20, 60],
      connect: true,
      range: {
        min: 0,
        max: 100
      }
    });
  },

  checkScrollForMovingNavbar: function() {

    // Hide Header on on scroll down
    navbarHeight = $('.navbar').outerHeight();

    $(window).scroll(function(event) {
      didScroll = true;
    });

    setInterval(function() {
      if (didScroll) {
        hasScrolled();
        didScroll = false;
      }
    }, 250);


  },

  checkScrollForParallax: debounce(function() {

    oVal = ($(window).scrollTop() / 3);
    big_image.css({
      'transform': 'translate3d(0,' + oVal + 'px,0)',
      '-webkit-transform': 'translate3d(0,' + oVal + 'px,0)',
      '-ms-transform': 'translate3d(0,' + oVal + 'px,0)',
      '-o-transform': 'translate3d(0,' + oVal + 'px,0)'
    });

  }, 6),

  initVideoBackground: function() {
    $('[data-toggle="video"]').click(function() {
      id_video = $(this).data('video');
      video = $('#' + id_video).get(0);

      parent = $(this).parent('div').parent('div');

      if (video.paused) {
        video.play();
        $(this).html('<i class="fa fa-pause"></i> Pause Video');
        parent.addClass('state-play');
      } else {
        video.pause();
        $(this).html('<i class="fa fa-play"></i> Play Video');
        parent.removeClass('state-play');
      }
    });
  },

  initContactUsMap: function() {
    var myLatlng = new google.maps.LatLng(40.748817, -73.985428);
    var mapOptions = {
      zoom: 13,
      center: myLatlng,
      scrollwheel: false, //we disable de scroll over the map, it is a really annoing when you scroll through page
      styles: [{
          "elementType": "geometry",
          "stylers": [{
            "color": "#1d2c4d"
          }]
        },
        {
          "elementType": "labels.text.fill",
          "stylers": [{
            "color": "#8ec3b9"
          }]
        },
        {
          "elementType": "labels.text.stroke",
          "stylers": [{
            "color": "#1a3646"
          }]
        },
        {
          "featureType": "administrative.country",
          "elementType": "geometry.stroke",
          "stylers": [{
            "color": "#4b6878"
          }]
        },
        {
          "featureType": "administrative.land_parcel",
          "elementType": "labels.text.fill",
          "stylers": [{
            "color": "#64779e"
          }]
        },
        {
          "featureType": "administrative.province",
          "elementType": "geometry.stroke",
          "stylers": [{
            "color": "#4b6878"
          }]
        },
        {
          "featureType": "landscape.man_made",
          "elementType": "geometry.stroke",
          "stylers": [{
            "color": "#334e87"
          }]
        },
        {
          "featureType": "landscape.natural",
          "elementType": "geometry",
          "stylers": [{
            "color": "#023e58"
          }]
        },
        {
          "featureType": "poi",
          "elementType": "geometry",
          "stylers": [{
            "color": "#283d6a"
          }]
        },
        {
          "featureType": "poi",
          "elementType": "labels.text.fill",
          "stylers": [{
            "color": "#6f9ba5"
          }]
        },
        {
          "featureType": "poi",
          "elementType": "labels.text.stroke",
          "stylers": [{
            "color": "#1d2c4d"
          }]
        },
        {
          "featureType": "poi.park",
          "elementType": "geometry.fill",
          "stylers": [{
            "color": "#023e58"
          }]
        },
        {
          "featureType": "poi.park",
          "elementType": "labels.text.fill",
          "stylers": [{
            "color": "#3C7680"
          }]
        },
        {
          "featureType": "road",
          "elementType": "geometry",
          "stylers": [{
            "color": "#304a7d"
          }]
        },
        {
          "featureType": "road",
          "elementType": "labels.text.fill",
          "stylers": [{
            "color": "#98a5be"
          }]
        },
        {
          "featureType": "road",
          "elementType": "labels.text.stroke",
          "stylers": [{
            "color": "#1d2c4d"
          }]
        },
        {
          "featureType": "road.highway",
          "elementType": "geometry",
          "stylers": [{
            "color": "#2c6675"
          }]
        },
        {
          "featureType": "road.highway",
          "elementType": "geometry.fill",
          "stylers": [{
            "color": "#9d2a80"
          }]
        },
        {
          "featureType": "road.highway",
          "elementType": "geometry.stroke",
          "stylers": [{
            "color": "#9d2a80"
          }]
        },
        {
          "featureType": "road.highway",
          "elementType": "labels.text.fill",
          "stylers": [{
            "color": "#b0d5ce"
          }]
        },
        {
          "featureType": "road.highway",
          "elementType": "labels.text.stroke",
          "stylers": [{
            "color": "#023e58"
          }]
        },
        {
          "featureType": "transit",
          "elementType": "labels.text.fill",
          "stylers": [{
            "color": "#98a5be"
          }]
        },
        {
          "featureType": "transit",
          "elementType": "labels.text.stroke",
          "stylers": [{
            "color": "#1d2c4d"
          }]
        },
        {
          "featureType": "transit.line",
          "elementType": "geometry.fill",
          "stylers": [{
            "color": "#283d6a"
          }]
        },
        {
          "featureType": "transit.station",
          "elementType": "geometry",
          "stylers": [{
            "color": "#3a4762"
          }]
        },
        {
          "featureType": "water",
          "elementType": "geometry",
          "stylers": [{
            "color": "#0e1626"
          }]
        },
        {
          "featureType": "water",
          "elementType": "labels.text.fill",
          "stylers": [{
            "color": "#4e6d70"
          }]
        }
      ]
    };

    var map = new google.maps.Map(document.getElementById("contactUsMap"), mapOptions);

    var marker = new google.maps.Marker({
      position: myLatlng,
      title: "Hello World!"
    });

    // To add the marker to the map, call setMap();
    marker.setMap(map);
  },


  initContactUs2Map: function() {
    var myLatlng = new google.maps.LatLng(40.748817, -73.985428);
    var mapOptions = {
      zoom: 13,
      center: myLatlng,
      scrollwheel: false, //we disable de scroll over the map, it is a really annoing when you scroll through page
      styles: [{
          "elementType": "geometry",
          "stylers": [{
            "color": "#1d2c4d"
          }]
        },
        {
          "elementType": "labels.text.fill",
          "stylers": [{
            "color": "#8ec3b9"
          }]
        },
        {
          "elementType": "labels.text.stroke",
          "stylers": [{
            "color": "#1a3646"
          }]
        },
        {
          "featureType": "administrative.country",
          "elementType": "geometry.stroke",
          "stylers": [{
            "color": "#4b6878"
          }]
        },
        {
          "featureType": "administrative.land_parcel",
          "elementType": "labels.text.fill",
          "stylers": [{
            "color": "#64779e"
          }]
        },
        {
          "featureType": "administrative.province",
          "elementType": "geometry.stroke",
          "stylers": [{
            "color": "#4b6878"
          }]
        },
        {
          "featureType": "landscape.man_made",
          "elementType": "geometry.stroke",
          "stylers": [{
            "color": "#334e87"
          }]
        },
        {
          "featureType": "landscape.natural",
          "elementType": "geometry",
          "stylers": [{
            "color": "#023e58"
          }]
        },
        {
          "featureType": "poi",
          "elementType": "geometry",
          "stylers": [{
            "color": "#283d6a"
          }]
        },
        {
          "featureType": "poi",
          "elementType": "labels.text.fill",
          "stylers": [{
            "color": "#6f9ba5"
          }]
        },
        {
          "featureType": "poi",
          "elementType": "labels.text.stroke",
          "stylers": [{
            "color": "#1d2c4d"
          }]
        },
        {
          "featureType": "poi.park",
          "elementType": "geometry.fill",
          "stylers": [{
            "color": "#023e58"
          }]
        },
        {
          "featureType": "poi.park",
          "elementType": "labels.text.fill",
          "stylers": [{
            "color": "#3C7680"
          }]
        },
        {
          "featureType": "road",
          "elementType": "geometry",
          "stylers": [{
            "color": "#304a7d"
          }]
        },
        {
          "featureType": "road",
          "elementType": "labels.text.fill",
          "stylers": [{
            "color": "#98a5be"
          }]
        },
        {
          "featureType": "road",
          "elementType": "labels.text.stroke",
          "stylers": [{
            "color": "#1d2c4d"
          }]
        },
        {
          "featureType": "road.highway",
          "elementType": "geometry",
          "stylers": [{
            "color": "#2c6675"
          }]
        },
        {
          "featureType": "road.highway",
          "elementType": "geometry.fill",
          "stylers": [{
            "color": "#9d2a80"
          }]
        },
        {
          "featureType": "road.highway",
          "elementType": "geometry.stroke",
          "stylers": [{
            "color": "#9d2a80"
          }]
        },
        {
          "featureType": "road.highway",
          "elementType": "labels.text.fill",
          "stylers": [{
            "color": "#b0d5ce"
          }]
        },
        {
          "featureType": "road.highway",
          "elementType": "labels.text.stroke",
          "stylers": [{
            "color": "#023e58"
          }]
        },
        {
          "featureType": "transit",
          "elementType": "labels.text.fill",
          "stylers": [{
            "color": "#98a5be"
          }]
        },
        {
          "featureType": "transit",
          "elementType": "labels.text.stroke",
          "stylers": [{
            "color": "#1d2c4d"
          }]
        },
        {
          "featureType": "transit.line",
          "elementType": "geometry.fill",
          "stylers": [{
            "color": "#283d6a"
          }]
        },
        {
          "featureType": "transit.station",
          "elementType": "geometry",
          "stylers": [{
            "color": "#3a4762"
          }]
        },
        {
          "featureType": "water",
          "elementType": "geometry",
          "stylers": [{
            "color": "#0e1626"
          }]
        },
        {
          "featureType": "water",
          "elementType": "labels.text.fill",
          "stylers": [{
            "color": "#4e6d70"
          }]
        }
      ]
    };

    var map = new google.maps.Map(document.getElementById("contactUs2Map"), mapOptions);

    var marker = new google.maps.Marker({
      position: myLatlng,
      title: "Hello World!"
    });

    // To add the marker to the map, call setMap();
    marker.setMap(map);
  }
}

// Returns a function, that, as long as it continues to be invoked, will not
// be triggered. The function will be called after it stops being called for
// N milliseconds. If `immediate` is passed, trigger the function on the
// leading edge, instead of the trailing.

function debounce(func, wait, immediate) {
  var timeout;
  return function() {
    var context = this,
      args = arguments;
    clearTimeout(timeout);
    timeout = setTimeout(function() {
      timeout = null;
      if (!immediate) func.apply(context, args);
    }, wait);
    if (immediate && !timeout) func.apply(context, args);
  };
};