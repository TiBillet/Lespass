const messageElement = document.getElementById("message");
const fullMessage = "Merci de poser votre carte sur le lecteur NFC";

messageElement.textContent = fullMessage;

function addBlinkEffect() {
  const period = document.createElement("span");
  period.textContent = ".";
  period.classList.add("blink");
  messageElement.appendChild(period);
  setInterval(() => {
    period.classList.toggle("blink");
  }, 800);
}

addBlinkEffect();
