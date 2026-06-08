/**
 * Interface defining the optional properties for the LoadingSpinner component.
 * @property label - Accessible text displayed below the spinner and used for screen readers.
 * @property size - Controls the physical dimensions of the spinner (small, medium, or large).
 */

export interface LoadingSpinnerProps {
  label?: string;
  size?: 'small' | 'medium' | 'large';
}

const spinnerSizeClasses: Record<NonNullable<LoadingSpinnerProps['size']>, string> = {
  small: 'h-6 w-6 border-2',
  medium: 'h-10 w-10 border-4',
  large: 'h-16 w-16 border-4',
};
/**
 * LoadingSpinner - A reusable, accessible functional component that renders
 * an animated loading indicator styled with custom Tailwind design tokens.
 */

export function LoadingSpinner({ label = 'Loading…', size = 'medium' }: LoadingSpinnerProps) {
  return (
    <div
      role="status"
      aria-label={label}
      className="flex flex-col items-center justify-center gap-3 p-4 text-brand-primary"
    >
      <div
        className={`${spinnerSizeClasses[size]} animate-spin rounded-full border-brand-primary/20 border-t-brand-primary`}
      />
      <span className="text-sm font-medium text-brand-excluded">{label}</span>
    </div>
  );
}
