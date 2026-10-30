document.querySelectorAll('.password-toggle').forEach(button => {
  button.addEventListener('click', () => {
    const input = button.previousElementSibling;
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    button.textContent = show ? 'Скрыть' : 'Показать';
    button.setAttribute('aria-label', show ? 'Скрыть пароль' : 'Показать пароль');
    button.setAttribute('aria-pressed', String(show));
  });
});
document.querySelectorAll('form[data-validate]').forEach(form => {
  form.noValidate = true;
  const error = form.querySelector('.form-error');
  form.addEventListener('submit', event => {
    const invalid = Array.from(form.elements).find(input => input.willValidate && !input.validity.valid);
    if (invalid) {
      event.preventDefault();
      invalid.setAttribute('aria-invalid', 'true');
      error.textContent = invalid.validationMessage;
      invalid.focus();
    } else {
      error.textContent = '';
      form.querySelector('[type=submit]').classList.add('loading');
    }
  });
  form.addEventListener('input', event => event.target.removeAttribute('aria-invalid'));
});
document.querySelectorAll('form[data-confirm]').forEach(form => {
  form.addEventListener('submit', event => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});
