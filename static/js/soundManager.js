class SoundManager {
    constructor() {
        if (SoundManager.instance) {
            return SoundManager.instance;
        }
        SoundManager.instance = this;
        this.initialized = false;
        this.sounds = new Map();
    }

    init() {
        if (this.initialized) return;
        this.createAudioElements();
        this.setupInitialization();
        this.initialized = true;
    }

    createAudioElements() {
        // Create notification sound
        const notificationSound = new Audio('/static/audio/notification.mp3');
        notificationSound.preload = 'auto';
        this.sounds.set('notification', notificationSound);

        // Create unlock sound
        const unlockSound = new Audio('/static/audio/unlock.mp3');
        unlockSound.preload = 'auto';
        this.sounds.set('unlock', unlockSound);
    }

    setupInitialization() {
        const initializeAudio = () => {
            this.sounds.forEach(sound => {
                sound.play().then(() => {
                    sound.pause();
                    sound.currentTime = 0;
                }).catch(console.error);
            });
        };

        // Initialize on first user interaction
        const handleInteraction = () => {
            initializeAudio();
            document.removeEventListener('click', handleInteraction);
            document.removeEventListener('touchstart', handleInteraction);
        };

        document.addEventListener('click', handleInteraction);
        document.addEventListener('touchstart', handleInteraction);
    }

    play(soundName) {
        const sound = this.sounds.get(soundName);
        if (sound) {
            sound.currentTime = 0;
            return sound.play().catch(error => {
                console.log('Playback failed:', error);
                // Retry on next user interaction
                this.setupInitialization();
            });
        }
    }
}

// Create global instance
window.soundManager = new SoundManager();
