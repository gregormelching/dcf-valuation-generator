const MC_TIMEOUT_MS = 60000;

function showError(panel, message) {
    panel.innerHTML = '<div class="error-card"><h3>Could not load the Monte Carlo panel.</h3><p></p></div>';
    panel.querySelector('.error-card p').textContent = message;
}

document.addEventListener('DOMContentLoaded', () => {
    const panel = document.getElementById('mc-panel');

    if (!panel) return;

    const dataUrl = panel.dataset.url;
    if (!dataUrl) {
        showError(panel, 'The panel carries no data-url attribute.');
        return;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), MC_TIMEOUT_MS);

    fetch(dataUrl, { signal: controller.signal })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }
            return response.text();
        })
        .then(htmlText => {
            panel.innerHTML = htmlText;
        })
        .catch(error => {
            const message = error.name === 'AbortError'
                ? `Timed out after ${MC_TIMEOUT_MS / 1000} s.`
                : error.message;
            showError(panel, message);
            console.error('Monte Carlo panel:', error);
        })
        .finally(() => clearTimeout(timer));
});
