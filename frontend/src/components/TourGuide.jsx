import React, { useState, useEffect } from 'react';
import { Joyride, STATUS } from 'react-joyride';

const TOUR_STEPS = [
  {
    target: '.tour-sidebar',
    content: 'Here is your main navigation. You can jump between the Dashboard, Data Analysis, and Settings from here.',
    disableBeacon: true,
    placement: 'right',
  },
  {
    target: '.tour-live-chart',
    content: 'This is the Live Telemetry Chart. It streams real-time seismic data directly from your device.',
    placement: 'bottom',
  },
  {
    target: '.tour-device-details',
    content: 'Here you can check the specific hardware and location details configured for this sensor node.',
    placement: 'right',
  },
  {
    target: '.tour-system-status',
    content: 'Keep an eye on system health, network connections, and CPU/Disk usage to ensure continuous operation.',
    placement: 'left',
  }
];

export default function TourGuide() {
  const [run, setRun] = useState(false);
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    // Check if the user has already seen or skipped the tour
    const hasSeenTour = localStorage.getItem('has_seen_tour');
    if (!hasSeenTour) {
      setShowModal(true);
    }
  }, []);

  const handleStartTour = () => {
    setShowModal(false);
    setRun(true);
    localStorage.setItem('has_seen_tour', 'true');
  };

  const handleSkipTour = () => {
    setShowModal(false);
    localStorage.setItem('has_seen_tour', 'true');
  };

  const handleJoyrideCallback = (data) => {
    const { status } = data;
    if ([STATUS.FINISHED, STATUS.SKIPPED].includes(status)) {
      setRun(false);
    }
  };

  return (
    <>
      {showModal && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl p-8 max-w-md w-full border border-gray-100 dark:border-slate-700 animate-slide-up mx-4">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Welcome to CrisisLab!</h2>
            <p className="text-gray-600 dark:text-gray-300 mb-6">
              Would you like a quick tour to familiarize yourself with the essential features of the dashboard?
            </p>
            <div className="flex space-x-4">
              <button
                onClick={handleSkipTour}
                className="flex-1 bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-slate-600 px-4 py-3 rounded-xl font-semibold transition-colors"
              >
                Skip Tour
              </button>
              <button
                onClick={handleStartTour}
                className="flex-1 bg-amber-500 hover:bg-amber-600 text-white px-4 py-3 rounded-xl font-semibold transition-colors shadow-md hover:shadow-lg"
              >
                Start Tour
              </button>
            </div>
          </div>
        </div>
      )}

      <Joyride
        steps={TOUR_STEPS}
        run={run}
        continuous={true}
        showProgress={true}
        showSkipButton={true}
        callback={handleJoyrideCallback}
        styles={{
          options: {
            primaryColor: '#f59e0b', // amber-500
            zIndex: 10000,
          },
          tooltipContainer: {
            textAlign: 'left'
          },
          buttonNext: {
            backgroundColor: '#f59e0b',
            borderRadius: '8px'
          },
          buttonBack: {
            marginRight: 10,
            color: '#6b7280'
          },
          buttonSkip: {
            color: '#6b7280'
          }
        }}
      />
    </>
  );
}
