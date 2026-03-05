'use client';

import { useState, useEffect, useCallback } from 'react';
import { useSettings } from './useSettings';

export function useOnboarding() {
    const { settings, updateSettings, isLoading } = useSettings();
    const [showTutorial, setShowTutorial] = useState(false);

    useEffect(() => {
        if (!isLoading && settings && settings.onboarding_completed === false) {
            setShowTutorial(true);
        }
    }, [isLoading, settings]);

    const completeOnboarding = useCallback(async () => {
        try {
            await updateSettings({ onboarding_completed: true });
            setShowTutorial(false);
        } catch (error) {
            console.error('Failed to complete onboarding:', error);
            // Fallback: hide it anyway to not annoy the user
            setShowTutorial(false);
        }
    }, [updateSettings]);

    const skipOnboarding = useCallback(async () => {
        // For now, skip also marks as completed to avoid showing on next reload
        // In a more complex flow, skip might just hide it for the session
        await completeOnboarding();
    }, [completeOnboarding]);

    const restartTutorial = useCallback(() => {
        setShowTutorial(true);
    }, []);

    return {
        showTutorial,
        setShowTutorial,
        completeOnboarding,
        skipOnboarding,
        restartTutorial,
        isLoading: isLoading || settings === null,
    };
}
