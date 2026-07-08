const rfid = new NfcReader() //TODO: import dynamic cordova 
let totalAmount = 0;

function goBack() {
  window.history.back();
}

function selectAmount(amount) {
  totalAmount += amount;
  document.getElementById("totalAmount").textContent = `${totalAmount}`;
}

function validateAmount() {
  if (totalAmount > 0) {
    localStorage.setItem("selectedAmount", totalAmount);
    return true;
  } else {
    alert("Veuillez sélectionner un montant.");
    return false;
  }
}

function selectPaymentMethod(method) {
  localStorage.setItem("paymentMethod", method);

  if (method === "Carte bancaire") {
    window.location.href = "confirmationCB.html";
  } else if (method === "Espèces") {
    window.location.href = "confirmationCash.html";
  }
}

function clearAmount() {
  totalAmount = 0;
  document.getElementById("totalAmount").textContent = `${totalAmount}`;
  localStorage.removeItem("selectedAmount");
}

document.addEventListener("DOMContentLoaded", function () {
  const selectedAmount = localStorage.getItem("selectedAmount");
  const paymentMethod = localStorage.getItem("paymentMethod");

  if (selectedAmount && paymentMethod) {
    document.getElementById("selectedAmount").textContent = selectedAmount;
    document.getElementById("paymentMethod").textContent = paymentMethod;
  }
});

function updateDarkModeButton() {
  const button = document.getElementById("toggleDarkModeBtn");
  if (button) {
    if (document.body.classList.contains("dark-mode")) {
      button.innerHTML = 'Mode Jour';
      button.setAttribute('aria-label', 'Activer le mode jour');
    } else {
      button.innerHTML = 'Mode Nuit';
      button.setAttribute('aria-label', 'Activer le mode nuit');
    }
  }
}

function toggleDarkMode() {
  document.body.classList.toggle("dark-mode");
  const elements = document.querySelectorAll(
    ".main-center, .card, .btn-amount, .btn-validate, .btn-clear, .btn-cancel, .btn-toggle-dark-mode, .cancel-page, .success-page, .btn-return"
  );
  elements.forEach((el) => el.classList.toggle("dark-mode"));

  if (document.body.classList.contains("dark-mode")) {
    localStorage.setItem("theme", "dark");
    applyDarkModeStyles();
  } else {
    localStorage.setItem("theme", "light");
    removeDarkModeStyles();
  }
  updateDarkModeButton();
}

function applyDarkModeStyles() {
  // Apply dark mode styles for confirmationCB.html
  const card = document.querySelector(".card");
  if (card) {
    card.style.backgroundColor = "#3a3a3a"; // Slightly lighter than default #2d2d2d
    card.style.boxShadow = "0 4px 12px rgba(255, 255, 255, 0.15)";
    card.style.border = "1px solid rgba(255, 255, 255, 0.1)";
  }

  // Update cancel button styling for dark mode
  const cancelButton = document.querySelector(".btn-cancel");
  if (cancelButton) {
    cancelButton.style.border = "4px solid #ffcc00"; // Brighter, thicker border for better visibility
    cancelButton.style.backgroundColor = "#d00000"; // Darker red for better contrast
    cancelButton.style.boxShadow = "0 6px 15px rgba(255, 204, 0, 0.4), 0 0 5px rgba(255, 255, 255, 0.3)"; // Enhanced shadow with yellow glow
    cancelButton.style.color = "#ffffff"; // Ensure text is white for contrast
    cancelButton.style.textShadow = "0 1px 2px rgba(0, 0, 0, 0.5)"; // Add text shadow for better readability
    cancelButton.style.fontWeight = "900"; // Extra bold text
  }

  // Ensure spinner is visible in dark mode
  const spinner = document.querySelector(".spinner_bootstrap");
  if (spinner) {
    spinner.style.borderColor = "rgba(255, 255, 255, 0.2)";
    spinner.style.borderTopColor = "#3a86ff"; // Bright blue for visibility
  }

  // Enhance text contrast
  const paymentInfo = document.querySelector(".payment-info");
  if (paymentInfo) {
    paymentInfo.style.color = "#ffffff";
    paymentInfo.style.textShadow = "0 1px 2px rgba(0, 0, 0, 0.3)";
  }

  // Make payment icons more visible
  const paymentIcons = document.querySelector(".payment-icons");
  if (paymentIcons) {
    paymentIcons.style.color = "#ffffff";
    paymentIcons.style.fontSize = "2.2rem"; // Slightly larger
    paymentIcons.style.textShadow = "0 1px 3px rgba(0, 0, 0, 0.4)";
  }
}

function removeDarkModeStyles() {
  // Remove dark mode styles for confirmationCB.html
  const card = document.querySelector(".card");
  if (card) {
    card.style.backgroundColor = "";
    card.style.boxShadow = "";
    card.style.border = "";
  }

  // Reset cancel button styling
  const cancelButton = document.querySelector(".btn-cancel");
  if (cancelButton) {
    cancelButton.style.border = "3px solid #fff";
    cancelButton.style.backgroundColor = "";
    cancelButton.style.boxShadow = "0 6px 12px rgba(220, 53, 69, 0.4)";
    cancelButton.style.color = "";
    cancelButton.style.textShadow = "";
    cancelButton.style.fontWeight = "";
  }

  // Reset spinner
  const spinner = document.querySelector(".spinner_bootstrap");
  if (spinner) {
    spinner.style.borderColor = "";
    spinner.style.borderTopColor = "";
  }

  // Reset text contrast
  const paymentInfo = document.querySelector(".payment-info");
  if (paymentInfo) {
    paymentInfo.style.color = "";
    paymentInfo.style.textShadow = "";
  }

  // Reset payment icons
  const paymentIcons = document.querySelector(".payment-icons");
  if (paymentIcons) {
    paymentIcons.style.color = "";
    paymentIcons.style.fontSize = "";
    paymentIcons.style.textShadow = "";
  }
}

// Function to initialize the page
function initializePage() {
  const theme = localStorage.getItem("theme");
  if (theme === "dark") {
    document.body.classList.add("dark-mode");
    const elements = document.querySelectorAll(
      ".main-center, .card, .btn-amount, .btn-validate, .btn-clear, .btn-cancel, .btn-toggle-dark-mode, .cancel-page, .success-page, .btn-return"
    );
    elements.forEach((el) => el.classList.add("dark-mode"));
    applyDarkModeStyles();
  }
  updateDarkModeButton();

  // Initialize countdown timer for cancel page
  const countdownElement = document.getElementById('countdown');
  if (countdownElement) {
    let seconds = 15;
    const timer = setInterval(function () {
      seconds--;
      countdownElement.textContent = seconds;

      if (seconds <= 0) {
        clearInterval(timer);
        window.location.href = "/kiosk/";
      }
    }, 1000);
  }

  // Initialize amount display if available
  const selectedAmount = localStorage.getItem("selectedAmount");
  const paymentMethod = localStorage.getItem("paymentMethod");

  if (selectedAmount && paymentMethod) {
    const selectedAmountElement = document.getElementById("selectedAmount");
    const paymentMethodElement = document.getElementById("paymentMethod");

    if (selectedAmountElement) {
      selectedAmountElement.textContent = selectedAmount;
    }

    if (paymentMethodElement) {
      paymentMethodElement.textContent = paymentMethod;
    }
  }
}


// Initialize on page load
document.addEventListener("DOMContentLoaded", initializePage);

// Initialize when HTMX swaps content
document.addEventListener('htmx:afterSwap', function (event) {
  // Only run if the swap target is the tb-kiosque element or its children
  if (event.detail.target.id === 'tb-kiosque' || event.detail.target.closest('#tb-kiosque')) {
    initializePage();
  }
});
