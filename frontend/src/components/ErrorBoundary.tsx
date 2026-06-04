import { Component, type ErrorInfo, type ReactNode } from 'react';

/**
 * Interface defining the expected props for the ErrorBoundary component.
 * @property children - The component tree wrapped by this error boundary.
 */
export interface ErrorBoundaryProps {
  children: ReactNode;
  fallbackTitle?: string;
  fallbackMessage?: string;
}

/**
 * Interface defining the internal state for the ErrorBoundary component.
 * @property hasError - Boolean flag indicating if a child component has crashed.
 */

interface ErrorBoundaryState {
  hasError: boolean;
}

/**
 * ErrorBoundary - A robust React class component that acts as a safety net.
 * It catches runtime rendering errors anywhere in the child component tree,
 * logs the details, and displays a clean fallback UI with a retry mechanism.
 */

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    hasError: false,
  };

  /**
   * Built-in React lifecycle method invoked after an error is thrown by a child component.
   * Updates the component state to trigger a re-render showing the fallback UI.
   */
  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  /**
   * Built-in React lifecycle method used to capture and log error information.
   * Useful for tracking application crashes in development and production environments.
   */

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  /**
   * Resets the error state back to false.
   * Allows the system to re-render the layout without forcing a complete browser refresh.
   */

  private handleRetry = (): void => {
    this.setState({ hasError: false });
  };

  render(): ReactNode {
    // If a crash is detected, render the friendly branded fallback screen
    const {
      children,
      fallbackTitle = 'Something went wrong',
      fallbackMessage = 'We could not load this part of the schedule. Try again to continue.',
    } = this.props;

    if (this.state.hasError) {
      return (
        <section
          role="alert"
          className="mx-auto flex max-w-xl flex-col items-center gap-4 rounded-lg border border-brand-danger/40 bg-white p-6 text-center shadow-sm"
        >
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-danger/10 text-2xl font-semibold text-brand-danger">
            !
          </div>
          <div className="space-y-2">
            <h2 className="text-xl font-semibold text-brand-primary">{fallbackTitle}</h2>
            <p className="text-sm text-brand-excluded">{fallbackMessage}</p>
          </div>
          <button
            type="button"
            onClick={this.handleRetry}
            className="rounded-md bg-brand-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-primary/90 focus:outline-none focus:ring-2 focus:ring-brand-primary focus:ring-offset-2"
          >
            Try again
          </button>
        </section>
      );
    }
    // Default behavior: Render child components normally if no error exists
    return children;
  }
}
