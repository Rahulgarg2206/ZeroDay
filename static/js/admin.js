// Screen size check
function checkScreenSize() {
    const smallScreenOverlay = document.getElementById('smallScreenOverlay');
    if (window.innerWidth < 802) {
        smallScreenOverlay.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    } else {
        smallScreenOverlay.style.display = 'none';
        document.body.style.overflow = '';
    }
}

// Add event listeners
window.addEventListener('load', checkScreenSize);
window.addEventListener('resize', checkScreenSize); 