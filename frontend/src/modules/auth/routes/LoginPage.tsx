import { StateCard } from '@shared/ui/states/StateCard';

export function LoginPage() {
  return (
    <div className="login-shell">
      <StateCard
        eyebrow="local auth"
        title="Login route placeholder"
        description="Stage 0 wires auth entry, refresh strategy and form ownership boundaries. Full auth UX is intentionally deferred."
      />
    </div>
  );
}
