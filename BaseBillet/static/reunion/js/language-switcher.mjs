/**
 * Gestion du changement de langue.
 */

const setLanguage = (langCode) => {
    const formData = new FormData();
    formData.append('language', langCode);
    formData.append('next', window.location.pathname + window.location.search);

    fetch('/i18n/setlang/', {
        method: 'POST',
        body: formData,
        headers: {
            'X-CSRFToken': getCookie('csrftoken')
        }
    }).then(response => {
        if (response.ok) {
            window.location.reload();
        }
    });
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

export const init = () => {
    const attachEvents = () => {
        const langBtns = document.querySelectorAll('.language-select-btn');
        const langSelect = document.querySelector('#languageSelect');

        langBtns.forEach(btn => {
            if (!btn.dataset.langBound) {
                btn.addEventListener('click', () => {
                    setLanguage(btn.dataset.lang);
                });
                btn.dataset.langBound = 'true';
            }
        });

        if (langSelect && !langSelect.dataset.langBound) {
            langSelect.addEventListener('change', (e) => {
                setLanguage(e.target.value);
            });
            langSelect.dataset.langBound = 'true';
        }
    }

    attachEvents();

    document.body.addEventListener('htmx:afterSwap', () => {
        attachEvents();
    });
}
