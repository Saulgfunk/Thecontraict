import { cn } from "@/lib/utils";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const buttonVariants: Record<ButtonVariant, string> = {
  primary:
    "bg-primary text-primary-foreground shadow-[0_1px_2px_rgb(0_0_0/0.12),inset_0_1px_0_rgb(255_255_255/0.12)] hover:bg-primary-strong",
  secondary:
    "border border-border bg-surface text-foreground shadow-[0_1px_2px_rgb(0_0_0/0.04)] hover:border-primary/40 hover:text-primary",
  ghost: "text-foreground hover:bg-foreground/5",
  danger: "border border-border bg-surface text-danger hover:border-danger/40 hover:bg-danger/5",
};

export function Button({
  variant = "primary",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      className={cn(
        "inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium whitespace-nowrap transition-colors active:translate-y-px disabled:pointer-events-none disabled:opacity-50",
        buttonVariants[variant],
        className,
      )}
      {...props}
    />
  );
}

const fieldClass =
  "h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm shadow-[inset_0_1px_1px_rgb(0_0_0/0.03)] outline-none transition placeholder:text-muted/70 hover:border-foreground/20 focus:border-primary focus:ring-4 focus:ring-primary/15 disabled:opacity-60 file:mr-3 file:rounded-md file:border-0 file:bg-primary/10 file:px-3 file:py-1 file:text-sm file:font-medium file:text-primary";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(fieldClass, className)} {...props} />;
}

export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(fieldClass, "pr-8", className)} {...props} />;
}

export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("flex flex-col gap-1.5 text-sm", className)}>
      <span className="font-medium">{label}</span>
      {children}
      {hint && <span className="text-muted text-xs">{hint}</span>}
    </label>
  );
}

export function Card({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: string;
  description?: string;
  actions?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "border-border/80 bg-surface animate-rise rounded-2xl border shadow-(--shadow-card)",
        className,
      )}
    >
      {(title || actions) && (
        <header className="flex items-start justify-between gap-4 px-6 pt-5 pb-1">
          <div>
            {title && <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>}
            {description && <p className="text-muted mt-0.5 text-sm">{description}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className="px-6 py-5">{children}</div>
    </section>
  );
}

const badgeTones = {
  neutral: "bg-foreground/5 text-muted ring-foreground/10",
  primary: "bg-primary/10 text-primary ring-primary/20",
  danger: "bg-danger/10 text-danger ring-danger/20",
  warning: "bg-warning/10 text-warning ring-warning/25",
  success: "bg-success/10 text-success ring-success/20",
};

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: keyof typeof badgeTones;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset",
        badgeTones[tone],
      )}
    >
      {children}
    </span>
  );
}

export function ErrorText({ children }: { children: React.ReactNode }) {
  if (!children) return null;
  return (
    <p role="alert" className="text-danger text-sm">
      {children}
    </p>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <p className="text-muted flex items-center gap-2 text-sm">
      <span className="border-primary/30 border-t-primary size-4 animate-spin rounded-full border-2" />
      {label}
    </p>
  );
}

export function PageHeader({
  title,
  eyebrow,
  description,
  actions,
  leading,
}: {
  title: string;
  eyebrow?: string;
  /** Shown left of the title, e.g. an avatar. */
  leading?: React.ReactNode;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="flex min-w-0 items-center gap-4">
        {leading}
        <div className="min-w-0">
          {eyebrow && (
            <p className="text-accent mb-1 text-xs font-semibold tracking-[0.14em] uppercase">
              {eyebrow}
            </p>
          )}
          <h1 className="font-serif text-3xl font-medium tracking-tight sm:text-[2.1rem]">
            {title}
          </h1>
          {description && <p className="text-muted mt-2 max-w-2xl text-sm">{description}</p>}
        </div>
      </div>
      {actions}
    </div>
  );
}
