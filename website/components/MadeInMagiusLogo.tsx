type MadeInMagiusLogoProps = {
  compact?: boolean;
  className?: string;
};

export default function MadeInMagiusLogo({
  compact = false,
  className = '',
}: MadeInMagiusLogoProps) {
  return (
    <span
      aria-label="MadeInMagius"
      className={`magi-madeinmagius-logo ${compact ? 'is-compact' : ''} ${className}`.trim()}
    >
      <span className="magi-madeinmagius-wordmark" aria-hidden="true">
        <span className="magi-madeinmagius-text">
          <span>MadeIn</span><strong>Magius</strong>
        </span>
      </span>
    </span>
  );
}
