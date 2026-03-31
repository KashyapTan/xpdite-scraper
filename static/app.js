/**
 * XpditeS Scraper - Frontend JavaScript
 */

document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const urlInput = document.getElementById('urlInput');
    const modeSelect = document.getElementById('modeSelect');
    const tierSelect = document.getElementById('tierSelect');
    const scrapeBtn = document.getElementById('scrapeBtn');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const errorMessage = document.getElementById('errorMessage');
    const emptyState = document.getElementById('emptyState');
    const resultContent = document.getElementById('resultContent');
    const resultStats = document.getElementById('resultStats');
    const resultActions = document.getElementById('resultActions');
    const copyBtn = document.getElementById('copyBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    const tierUsed = document.getElementById('tierUsed');
    const charCount = document.getElementById('charCount');
    const elapsedTime = document.getElementById('elapsedTime');

    // State
    let currentUrl = '';
    let currentContent = '';

    /**
     * Show loading state
     */
    function showLoading() {
        emptyState.style.display = 'none';
        loadingIndicator.style.display = 'flex';
        errorMessage.style.display = 'none';
        resultContent.style.display = 'none';
        resultStats.style.display = 'none';
        resultActions.style.display = 'none';
        scrapeBtn.disabled = true;
        scrapeBtn.textContent = 'Scraping...';
    }

    /**
     * Show error state
     */
    function showError(message) {
        loadingIndicator.style.display = 'none';
        emptyState.style.display = 'none';
        errorMessage.style.display = 'block';
        errorMessage.textContent = message;
        resultContent.style.display = 'none';
        resultStats.style.display = 'none';
        resultActions.style.display = 'none';
        resetButton();
    }

    /**
     * Show success state
     */
    function showSuccess(data) {
        loadingIndicator.style.display = 'none';
        emptyState.style.display = 'none';
        errorMessage.style.display = 'none';
        
        tierUsed.textContent = data.tier_used;
        charCount.textContent = data.char_count.toLocaleString();
        elapsedTime.textContent = `${data.elapsed_time}s`;
        
        resultContent.value = data.content;
        currentContent = data.content;
        
        resultStats.style.display = 'flex';
        resultContent.style.display = 'block';
        resultActions.style.display = 'flex';
        resetButton();
    }

    /**
     * Reset scrape button
     */
    function resetButton() {
        scrapeBtn.disabled = false;
        scrapeBtn.textContent = 'Start Scraping';
    }

    /**
     * Validate URL
     */
    function validateUrl(url) {
        if (!url || !url.trim()) {
            return { valid: false, error: 'Please enter a URL' };
        }
        
        let cleanUrl = url.trim();
        
        // Auto-prepend https:// if missing
        if (!cleanUrl.startsWith('http://') && !cleanUrl.startsWith('https://')) {
            cleanUrl = 'https://' + cleanUrl;
        }
        
        try {
            new URL(cleanUrl);
            return { valid: true, url: cleanUrl };
        } catch {
            return { valid: false, error: 'Invalid URL format' };
        }
    }

    /**
     * Perform scrape request
     */
    async function performScrape(url) {
        currentUrl = url;
        showLoading();

        try {
            const response = await fetch('/api/scrape', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: url,
                    mode: modeSelect.value,
                    tier: tierSelect.value
                })
            });

            const data = await response.json();

            if (!response.ok) {
                showError(data.detail || 'An error occurred during scraping');
                return;
            }

            if (data.success) {
                showSuccess(data);
            } else {
                showError(data.error || 'Failed to scrape the URL');
            }
        } catch (error) {
            showError(`Network error: ${error.message}`);
        }
    }

    /**
     * Copy content to clipboard
     */
    async function copyToClipboard() {
        try {
            await navigator.clipboard.writeText(currentContent);
            
            const originalText = copyBtn.textContent;
            copyBtn.textContent = 'Copied!';
            copyBtn.style.color = '#34d399';
            copyBtn.style.borderColor = '#34d399';
            
            setTimeout(() => {
                copyBtn.textContent = originalText;
                copyBtn.style.color = '';
                copyBtn.style.borderColor = '';
            }, 2000);
        } catch (error) {
            console.error('Failed to copy:', error);
        }
    }

    /**
     * Download content as file
     */
    function downloadContent() {
        const mode = modeSelect.value;
        const extension = mode === 'full' ? 'md' : 'txt';
        const hostname = new URL(currentUrl).hostname.replace(/[^a-z0-9]/gi, '_');
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        const filename = `${hostname}_${timestamp}.${extension}`;

        const blob = new Blob([currentContent], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // Event Listeners
    scrapeBtn.addEventListener('click', () => {
        const validation = validateUrl(urlInput.value);
        if (!validation.valid) {
            showError(validation.error);
            return;
        }
        performScrape(validation.url);
    });

    // Enter key on URL input
    urlInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            scrapeBtn.click();
        }
    });

    copyBtn.addEventListener('click', copyToClipboard);
    downloadBtn.addEventListener('click', downloadContent);
});
