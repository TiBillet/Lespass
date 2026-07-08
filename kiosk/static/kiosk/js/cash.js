let selectedAmount = 0;
let currentAmount = 0;

document.addEventListener("DOMContentLoaded", function () {
  selectedAmount = parseInt(localStorage.getItem("selectedAmount"));
  const paymentMethod = localStorage.getItem("paymentMethod");

  if (selectedAmount && paymentMethod) {
    document.getElementById("selectedAmount").textContent = selectedAmount;
    document.getElementById("paymentMethod").textContent = paymentMethod;
  }
});

function addAmount() {
  const amountInput = document.getElementById("amountInput");
  const amountToAdd = parseInt(amountInput.value);

  if (!isNaN(amountToAdd) && amountToAdd > 0) {
    currentAmount += amountToAdd;
    if (currentAmount > selectedAmount) {
      currentAmount = selectedAmount;
    }
    updateProgressBar();
    amountInput.value = "";
  } else {
    alert("Veuillez entrer un montant valide.");
  }
}

function updateProgressBar() {
  const progressBar = document.getElementById("progressBar");
  const currentAmountElement = document.getElementById("currentAmount");
  const remainingAmount = selectedAmount - currentAmount;
  const percentage = (currentAmount / selectedAmount) * 100;

  progressBar.style.width = percentage + "%";
  progressBar.textContent = remainingAmount + "€ restant";
  currentAmountElement.textContent = currentAmount + "";

  if (currentAmount >= selectedAmount) {
    showSpinnerAndRedirect();
  }
}
function showSpinnerAndRedirect() {
  document.getElementById("spinner").style.display = "block";
  setTimeout(function () {
    window.location.href = "recapsolde.html";
  }, 3000);
}
