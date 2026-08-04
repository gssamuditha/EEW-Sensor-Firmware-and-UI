import React, { useState, useEffect } from 'react';
import { Joyride, STATUS, ACTIONS, EVENTS } from 'react-joyride';
import { useNavigate } from 'react-router-dom';

const TOUR_STEPS = [
  {
    target: '.tour-nav-dashboard',
    content: 'Welcome to your Dashboard! This is your central hub for all realtime information.',
    disableBeacon: true,
    placement: 'right',
  },
  {
    target: '.tour-device-details',
    content: 'This panel shows your hardware identity, network IPs, and sensor coordinates.',
    disableBeacon: true,
    placement: 'right',
  },
  {
    target: '.tour-live-chart',
    content: 'Here is your Live Telemetry Chart. It streams real-time seismic data directly from your device.',
    disableBeacon: true,
    placement: 'auto', 
  },
  {
    target: '.tour-system-status',
    content: 'Keep an eye on system health, network connections, and CPU/Disk usage here.',
    disableBeacon: true,
    placement: 'left',
  },
  {
    target: '.tour-timezone',
    content: 'You can toggle all times between UTC and Local time using this dropdown.',
    disableBeacon: true,
    placement: 'left',
  },
  {
    target: '.tour-nav-export',
    content: 'Data Export: Head over here to download custom MiniSEED or CSV data archives.',
    disableBeacon: true,
    placement: 'right',
  },
  {
    target: '.tour-nav-analysis',
    content: 'Analysis: Here you can filter data on a maximum 1-hour window for a selected time, filter out desired frequencies, remove noise, and visualize seismic data clearly.',
    disableBeacon: true,
    placement: 'right',
  },
  {
    target: '.tour-nav-settings',
    content: 'Settings: Configure your hardware device, network IPs, and system parameters here.',
    disableBeacon: true,
    placement: 'right',
  }
];

export default function TourGuide() {
  const [run, setRun] = useState(false);
  const [tourKey, setTourKey] = useState(0);
  const [showModal, setShowModal] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const hasSeenTour = localStorage.getItem('has_seen_tour');
    if (!hasSeenTour) {
      setShowModal(true);
    }
  }, []);

  const handleStartTour = () => {
    setShowModal(false);
    localStorage.setItem('has_seen_tour', 'true');
    navigate('/dashboard');
    setTourKey(prev => prev + 1); // Reset internal Joyride state
    setTimeout(() => {
      setRun(true);
    }, 800);
  };

  const handleSkipTour = () => {
    setShowModal(false);
    localStorage.setItem('has_seen_tour', 'true');
  };

  const handleJoyrideCallback = (data) => {
    const { status, type } = data;

    if ([STATUS.FINISHED, STATUS.SKIPPED].includes(status)) {
      setRun(false);
      return;
    }

    if (type === EVENTS.TARGET_NOT_FOUND) {
      console.warn('Tour target not found. Pausing tour to prevent infinite loop.', data);
      return;
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
        key={tourKey}
        steps={TOUR_STEPS}
        run={run}
        continuous={true}
        showProgress={true}
        showSkipButton={true}
        disableBeacon={true}
        callback={handleJoyrideCallback}
        styles={{
          options: {
            primaryColor: '#f59e0b', // This sets the default color for the "Open the dialog" beacon and the Next button
            zIndex: 10000,
            arrowColor: '#334155', // slate-700
            backgroundColor: '#334155', // slate-700
            textColor: '#f8fafc', // slate-50
            overlayColor: 'rgba(176, 181, 203, 0.6)',
          },
          // MANUALLY ADJUST THE BEACON ("Open the dialog" button) COLOR HERE:
          beacon: {
            // backgroundColor: 'transparent'
          },
          beaconInner: {
            backgroundColor: '#f59e0b', // Inner circle color (default orange)
          },
          beaconOuter: {
            borderColor: '#f59e0b', // Outer pulsing circle color (default orange)
            backgroundColor: 'rgba(245, 158, 11, 0.2)' // Outer background tint
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
