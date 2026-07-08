document.addEventListener("DOMContentLoaded", function () {
  const selectedAmount = parseInt(localStorage.getItem("selectedAmount"));
  const currentBalance = 100; // valeur test
  const newBalance = currentBalance + selectedAmount;

  document.getElementById("newBalance").textContent = newBalance;

  let countdown = 10;
  const countdownElement = document.getElementById("countdown");
  const countdownInterval = setInterval(function () {
    countdown--;
    countdownElement.textContent = countdown;

    if (countdown <= 0) {
      clearInterval(countdownInterval);
      window.location.href = "Index.html";
    }
  }, 1000);
});
