<template>
  <footer class="footer pt-5 mt-5">

    <hr class="horizontal dark mb-5">
    <div class="container">
      <div class=" row">
        <div class="col-md-3 mb-4 ms-auto">
          <div>
            <h6 class="font-weight-bolder">{{ place.organisation }}</h6>
          </div>
          <div>
            <h6 class="mt-3 mb-2 opacity-8">Social</h6>
            <ul class="d-flex flex-row ms-n3 nav">
              <li class="nav-item">
                <a class="nav-link pe-1" href="https://www.facebook.com/CreativeTim/" target="_blank">
                  <i class="fab fa-facebook text-lg opacity-8" aria-hidden="true"></i>
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link pe-1" href="https://twitter.com/creativetim" target="_blank">
                  <i class="fab fa-twitter text-lg opacity-8" aria-hidden="true"></i>
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link pe-1" href="https://dribbble.com/creativetim" target="_blank">
                  <i class="fab fa-dribbble text-lg opacity-8" aria-hidden="true"></i>
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link pe-1" href="https://github.com/creativetimofficial" target="_blank">
                  <i class="fab fa-github text-lg opacity-8" aria-hidden="true"></i>
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link pe-1" href="https://www.youtube.com/channel/UCVyTG4sCw-rOvB9oHkzZD1w"
                   target="_blank">
                  <i class="fab fa-youtube text-lg opacity-8" aria-hidden="true"></i>
                </a>
              </li>
            </ul>
          </div>
        </div>
        <div class="col-md-2 col-sm-6 col-6 mb-4">
          <div>
            <h6 class="font-weight-bolder text-sm">Coopérative</h6>
            <ul class="flex-column ms-n3 nav">
              <li class="nav-item">
                <a class="nav-link" href="https://wiki.tibillet.re" target="_blank">
                  A Propos
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link" href="https://www.les-scic.coop/" target="_blank">
                  Les SCIC
                </a>
              </li>
<!--              <li class="nav-item">-->
<!--                <a class="nav-link" href="https://www.creative-tim.com/templates/premium" target="_blank">-->
<!--                  Premium Tools-->
<!--                </a>-->
<!--              </li>-->
<!--              <li class="nav-item">-->
<!--                <a class="nav-link" href="https://www.creative-tim.com/blog" target="_blank">-->
<!--                  Blog-->
<!--                </a>-->
<!--              </li>-->
            </ul>
          </div>
        </div>
        <div class="col-md-2 col-sm-6 col-6 mb-4">
          <div>
            <h6 class="font-weight-bolder text-sm">Resources & Sponsors</h6>
            <ul class="flex-column ms-n3 nav">
              <li class="nav-item">
                <a class="nav-link" href="https://www.creative-tim.com/" target="_blank">
                  Design source
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link" href="https://jb.gg/OpenSourceSupport" target="_blank">
                  JetBrain IDE
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link" href="https://www.communecter.org/#" target="_blank">
                  Communecter
                </a>
              </li>
            </ul>
          </div>
        </div>
        <div class="col-md-2 col-sm-6 col-6 mb-4">
          <div>
            <h6 class="font-weight-bolder text-sm">Aide &amp; Support</h6>
            <ul class="flex-column ms-n3 nav">
              <li class="nav-item">
                <a class="nav-link" href="mailto:contact@tibillet.re" target="_blank">
                  Nous contacter
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link" href="https://github.com/TiBillet/TiBillet" target="_blank">
                  Dépot Github
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link" href="mailto:contact@tibillet.re" target="_blank">
                  Développement spécialisé
                </a>
              </li>
<!--              <li class="nav-item">-->
<!--                <a class="nav-link" href="https://www.creative-tim.com/sponsorships" target="_blank">-->
<!--                  Sponsorships-->
<!--                </a>-->
<!--              </li>-->
            </ul>
          </div>
        </div>
        <div class="col-md-2 col-sm-6 col-6 mb-4 me-auto">
          <div>
            <h6 class="font-weight-bolder text-sm">Legal</h6>
            <ul class="flex-column ms-n3 nav">
              <li class="nav-item">
                <a class="nav-link" href="https://github.com/TiBillet/TiBillet/blob/main/code_of_conduct-FR.md" target="_blank">
                  CGU/CGV
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link" href="https://github.com/TiBillet/TiBillet/blob/main/code_of_conduct-FR.md" target="_blank">
                  Code de conduite
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link" href="https://github.com/TiBillet/TiBillet/blob/main/LICENSE" target="_blank">
                  Licenses (EULA)
                </a>
              </li>
            </ul>
          </div>
        </div>
        <div class="col-12">
          <div class="text-center">
            <p class="my-4 text-sm">
              Tout droits presque reservés : Copyleft 2022 <a href="#" target="https://www.tibillet.re">Tibillet</a>.
            </p>
          </div>
        </div>
      </div>
    </div>
  </footer>

</template>

<script setup>
// console.log('-> Footer.vue')

const props = defineProps({
  place: Object
})
</script>
