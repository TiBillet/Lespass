const attachMembershipForm = (root = document) => {
  const form = root.querySelector('#membership-form');
  if (!form) return;
  if (form.dataset.membershipValidators === '1') return;
  form.dataset.membershipValidators = '1';

  const emailInput = form.querySelector('#membership-email');
  const confirmInput = form.querySelector('#confirm-email');
  const errorDiv = form.querySelector('#email-error');

  const validateEmails = () => {
    if (!emailInput || !confirmInput || !errorDiv) return true;
    const email = emailInput.value || '';
    const confirmEmail = confirmInput.value || '';
    if (email !== confirmEmail) {
      confirmInput.setCustomValidity('Les adresses e-mail ne correspondent pas.');
      errorDiv.textContent = 'Les adresses e-mail ne correspondent pas.';
      return false;
    }
    confirmInput.setCustomValidity('');
    errorDiv.textContent = '';
    return true;
  };

  const validateMsRequired = () => {
    let ok = true;
    const groups = form.querySelectorAll('[data-ms-required="true"]');
    groups.forEach(group => {
      const inputName = group.getAttribute('data-input-name');
      const boxes = group.querySelectorAll(`input[type="checkbox"][name="${inputName}"]`);
      const anyChecked = Array.from(boxes).some(cb => cb.checked);
      const error = group.querySelector('[data-ms-error]');
      if (!anyChecked) {
        ok = false;
        if (error) {
          error.textContent = group.getAttribute('data-error-message') || 'Veuillez cocher au moins une option.';
          error.style.display = 'block';
        }
        boxes.forEach(cb => cb.setAttribute('aria-invalid', 'true'));
      } else {
        if (error) {
          error.textContent = '';
          error.style.display = 'none';
        }
        boxes.forEach(cb => cb.removeAttribute('aria-invalid'));
      }
    });
    return ok;
  };

  const validateBlRequired = () => {
    let ok = true;
    const groups = form.querySelectorAll('[data-bl-required="true"]');
    groups.forEach(group => {
      const input = group.querySelector('input[type="checkbox"]');
      const error = group.querySelector('[data-bl-error]');
      if (!input) return;
      if (!input.checked) {
        ok = false;
        if (error) {
          error.textContent = group.getAttribute('data-error-message') || 'Veuillez cocher cette case.';
          error.style.display = 'block';
        }
        input.setAttribute('aria-invalid', 'true');
      } else {
        if (error) {
          error.textContent = '';
          error.style.display = 'none';
        }
        input.removeAttribute('aria-invalid');
      }
    });
    return ok;
  };

  const validateAll = () => {
    const okEmails = validateEmails();
    const okMs = validateMsRequired();
    const okBl = validateBlRequired();
    return okEmails && okMs && okBl;
  };

  form.addEventListener('submit', (event) => {
    if (!validateAll()) {
      event.preventDefault();
    }
  });

  form.addEventListener('htmx:configRequest', (event) => {
    if (!validateAll()) {
      event.preventDefault();
    }
  });

  if (emailInput && confirmInput) {
    emailInput.addEventListener('input', validateEmails);
    confirmInput.addEventListener('input', validateEmails);
  }

  form.addEventListener('change', (event) => {
    const target = event.target;
    if (target && target.closest('[data-ms-required="true"]')) {
      validateMsRequired();
    }
    if (target && target.closest('[data-bl-required="true"]')) {
      validateBlRequired();
    }
  });
};

export const init = () => {
  attachMembershipForm(document);
  document.body.addEventListener('htmx:afterSwap', (event) => {
    attachMembershipForm(event.target || document);
  });
};
