import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { motion, useScroll, useTransform } from 'framer-motion';
import {
  ArrowUpRight, ShieldCheck, Workflow, Database, Brain, AlertTriangle,
  GitBranch, Activity, Sparkles, ChevronRight, CircleDot,
} from 'lucide-react';

const CONNECTORS = [
  { name: 'MySQL',          mono: 'mysql' },
  { name: 'MS SQL Server',  mono: 'mssql' },
  { name: 'GitHub',         mono: 'github' },
  { name: 'Azure Data Factory', mono: 'adf' },
  { name: 'Databricks',     mono: 'databricks' },
  { name: 'Snowflake',      mono: 'snowflake' },
  { name: 'AWS Glue',       mono: 'glue' },
  { name: 'Postgres',       mono: 'postgres' },
  { name: 'Apache Kafka',   mono: 'kafka' },
  { name: 'Amazon S3',      mono: 's3' },
];

const AGENTS = [
  { name: 'QualityWatcher',   role: 'scores incoming records',                     icon: ShieldCheck },
  { name: 'DriftSentinel',    role: 'detects schema drift vs. contract',           icon: GitBranch },
  { name: 'AnomalyHunter',    role: 'flags statistical outliers',                  icon: Activity },
  { name: 'PIIScout',         role: 'classifies + masks PII in flight',            icon: AlertTriangle },
  { name: 'PolicyEnforcer',   role: 'enforces tag-based access policies',          icon: Workflow },
  { name: 'AutoRemediator',   role: 'applies safe fixes; escalates risky ones',    icon: Brain },
];

export default function Landing2() {
  const navigate = useNavigate();
  const { token } = useSelector((state: any) => state.auth);

  useEffect(() => {
    if (token) {
      navigate('/dashboard', { replace: true });
    }
  }, [token, navigate]);

  const { scrollYProgress } = useScroll();
  const heroY = useTransform(scrollYProgress, [0, 0.3], [0, -80]);

  return (
    <div className="bg-[var(--bg)] text-[var(--fg)] overflow-x-hidden">
      <TopBar />

      {/* ─────────────────────────────────────── HERO ─────────────────────────────────────── */}
      <section className="relative grain pt-28 pb-24 px-6 lg:px-12 overflow-hidden">
        {/* atmospheric backdrop */}
        <div
          aria-hidden
          className="absolute inset-0 opacity-[0.55] pointer-events-none"
          style={{
            background:
              'radial-gradient(60% 50% at 70% 20%, color-mix(in srgb, var(--accent) 24%, transparent), transparent 65%), radial-gradient(40% 35% at 15% 80%, color-mix(in srgb, var(--accent-2) 18%, transparent), transparent 60%)',
          }}
        />
        {/* corner crosshairs — technical detail */}
        <Crosshair className="top-6 left-6" />
        <Crosshair className="top-6 right-6" />

        <motion.div style={{ y: heroY }} className="relative max-w-6xl mx-auto">
          {/* eyebrow status */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            className="flex items-center gap-2.5 mb-7"
          >
            <span className="relative inline-flex size-2 rounded-full bg-[var(--success)] text-[var(--success)] pulse-dot" />
            <span className="font-mono text-[11px] tracking-[0.22em] uppercase text-[var(--fg-muted)]">
              v0.1 · agents online · 6 / 6
            </span>
          </motion.div>

          {/* headline */}
          <motion.h1
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay: 0.05 }}
            className="font-display font-[400] text-[clamp(2.6rem,7vw,5.6rem)] leading-[0.95] tracking-[-0.025em] max-w-5xl"
          >
            Data quality that{' '}
            <em className="italic font-[300] accent-text">watches itself</em>.
            <br />
            Governance that{' '}
            <em className="italic font-[300]">acts</em> before you do.
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: 'easeOut', delay: 0.2 }}
            className="mt-7 max-w-2xl text-[17px] leading-[1.55] text-[var(--fg-muted)]"
          >
            DataSentinel AI is an autonomous, multi-agent platform that continuously observes
            every connected source — MySQL, MS SQL Server, GitHub, ADF, Databricks and more —
            detecting drift, anomalies, and PII exposure, and remediating issues without waiting
            for a human to press <span className="font-mono text-[var(--fg)]">run</span>.
          </motion.p>

          {/* CTAs */}
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: 'easeOut', delay: 0.35 }}
            className="mt-10 flex flex-wrap items-center gap-3"
          >
            <Link
              to="/login"
              className="group inline-flex items-center gap-2 h-12 px-6 rounded-[10px] bg-[var(--accent)] text-[var(--accent-fg)] font-medium shadow-[0_18px_44px_-16px_var(--accent)] hover:bg-[var(--accent-hover)] transition"
            >
              Open the console
              <ArrowUpRight className="size-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </Link>
            <a
              href="#agents"
              className="inline-flex items-center gap-2 h-12 px-6 rounded-[10px] border border-[var(--border-strong)] text-[var(--fg)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition"
            >
              See the agents
              <ChevronRight className="size-4" />
            </a>
            <span className="ml-1 font-mono text-[11px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
              demo · admin@datasentinel.ai
            </span>
          </motion.div>

          {/* terminal-style telemetry strip */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.5 }}
            className="mt-16 rounded-[14px] border border-[var(--border)] bg-[var(--bg-elev-1)] overflow-hidden"
          >
            <div className="flex items-center gap-2 px-4 h-8 border-b border-[var(--border-soft)] bg-[var(--bg-elev-2)]">
              <span className="size-2 rounded-full bg-[var(--danger)]" />
              <span className="size-2 rounded-full bg-[var(--warning)]" />
              <span className="size-2 rounded-full bg-[var(--success)]" />
              <span className="ml-3 font-mono text-[10.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
                datasentinel · live event stream
              </span>
            </div>
            <TelemetryFeed />
          </motion.div>

          {/* trust stats */}
          <div className="mt-12 grid grid-cols-2 md:grid-cols-4 gap-px bg-[var(--border-soft)] rounded-[14px] overflow-hidden border border-[var(--border-soft)]">
            <Stat label="datasets governed" value="14.2M" />
            <Stat label="quality avg." value="94.7%" />
            <Stat label="agents always-on" value="6" />
            <Stat label="MTTR for drift" value="< 30s" />
          </div>
        </motion.div>
      </section>

      {/* ─────────────────────────────────────── CONNECTORS MARQUEE ─────────────────────────────────────── */}
      <section className="px-6 lg:px-12 py-16 border-y border-[var(--border-soft)]">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-baseline justify-between flex-wrap gap-4 mb-8">
            <div>
              <div className="eyebrow mb-2">Connectors</div>
              <h2 className="font-display text-3xl lg:text-4xl">
                Connect once. Observe <em className="italic accent-text">forever</em>.
              </h2>
            </div>
            <p className="text-sm text-[var(--fg-muted)] max-w-md">
              Once a source is configured, agents subscribe to its change-feed and never sleep.
              No cron triggers, no manual re-runs.
            </p>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-px bg-[var(--border-soft)] rounded-[14px] overflow-hidden border border-[var(--border-soft)]">
            {CONNECTORS.map((c) => (
              <div
                key={c.name}
                className="group relative bg-[var(--panel)] p-5 hover:bg-[var(--panel-soft)] transition"
              >
                <div className="flex items-center justify-between">
                  <span className="font-display text-[15px]">{c.name}</span>
                  <CircleDot className="size-3 text-[var(--success)] opacity-70 group-hover:opacity-100" />
                </div>
                <div className="mt-3 font-mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--fg-subtle)]">
                  {c.mono}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─────────────────────────────────────── AGENTS ─────────────────────────────────────── */}
      <section id="agents" className="px-6 lg:px-12 py-24 relative">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-end justify-between flex-wrap gap-4 mb-12">
            <div>
              <div className="eyebrow mb-2">The Sentinel Stack</div>
              <h2 className="font-display text-3xl lg:text-5xl max-w-3xl leading-[1.05]">
                Six agents.{' '}
                <em className="italic font-[300]">One responsibility each.</em>{' '}
                Always observing.
              </h2>
            </div>
            <p className="text-sm text-[var(--fg-muted)] max-w-sm">
              Each agent owns a narrow contract and coordinates through a shared event bus.
              Issues flow to the right specialist instantly.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-px bg-[var(--border-soft)] rounded-[14px] overflow-hidden border border-[var(--border-soft)]">
            {AGENTS.map(({ name, role, icon: Icon }, i) => (
              <motion.div
                key={name}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-80px' }}
                transition={{ duration: 0.55, delay: i * 0.06, ease: [0.16, 1, 0.3, 1] }}
                className="group relative bg-[var(--panel)] p-6 hover:bg-[var(--panel-soft)] transition"
              >
                <div className="flex items-start justify-between mb-5">
                  <div className="size-10 rounded-lg bg-[var(--bg-elev-2)] border border-[var(--border)] flex items-center justify-center text-[var(--accent)] group-hover:border-[var(--accent)]/40 transition">
                    <Icon className="size-4.5" strokeWidth={1.5} />
                  </div>
                  <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] flex items-center gap-1.5">
                    <span className="size-1.5 rounded-full bg-[var(--success)]" />
                    online
                  </span>
                </div>
                <h3 className="font-display text-xl mb-1.5">{name}</h3>
                <p className="text-sm text-[var(--fg-muted)] leading-relaxed">{role}</p>
                <div className="mt-5 pt-4 border-t border-dashed border-[var(--border)] font-mono text-[10.5px] tracking-[0.14em] uppercase text-[var(--fg-subtle)] flex items-center justify-between">
                  <span>events / min</span>
                  <span className="text-[var(--fg)]">{(80 + i * 47) % 220}</span>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ─────────────────────────────────────── WORKFLOW ─────────────────────────────────────── */}
      <section className="px-6 lg:px-12 py-24 bg-[var(--bg-elev-1)] border-y border-[var(--border-soft)]">
        <div className="max-w-6xl mx-auto">
          <div className="eyebrow mb-2">From signal to safe action</div>
          <h2 className="font-display text-3xl lg:text-5xl max-w-3xl leading-[1.05] mb-12">
            Detect. Decide. <em className="italic accent-text">Defend</em>.
          </h2>

          <ol className="grid md:grid-cols-4 gap-px bg-[var(--border-soft)] rounded-[14px] overflow-hidden border border-[var(--border-soft)]">
            {[
              { step: '01', title: 'Observe',     body: 'Agents tail every connector’s change feed in real time, building a live picture of every dataset.' },
              { step: '02', title: 'Score',       body: 'Each event is scored for quality, drift, anomaly, and PII risk against learned baselines.' },
              { step: '03', title: 'Remediate',   body: 'Safe fixes apply automatically. Risky ones route to a human approver with full context attached.' },
              { step: '04', title: 'Learn',       body: 'Outcomes feed back into the agents’ baselines — the system gets better the longer it runs.' },
            ].map(({ step, title, body }) => (
              <li key={step} className="bg-[var(--panel)] p-6 relative">
                <div className="font-mono text-[12px] tracking-[0.2em] text-[var(--accent)] mb-4">/ {step}</div>
                <h3 className="font-display text-xl mb-2">{title}</h3>
                <p className="text-sm text-[var(--fg-muted)] leading-relaxed">{body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ─────────────────────────────────────── FEATURE GRID ─────────────────────────────────────── */}
      <section className="px-6 lg:px-12 py-24">
        <div className="max-w-6xl mx-auto grid lg:grid-cols-12 gap-6">
          <div className="lg:col-span-5">
            <div className="eyebrow mb-2">What ships in v0.1</div>
            <h2 className="font-display text-3xl lg:text-5xl leading-[1.05]">
              Built for teams who can’t afford a{' '}
              <em className="italic">silent failure</em>.
            </h2>
            <p className="mt-5 text-[var(--fg-muted)] leading-relaxed text-[15px]">
              Approval workflows, audit trails, lineage, and a learning loop — wrapped in
              a console your engineers will actually open.
            </p>
          </div>
          <div className="lg:col-span-7 grid sm:grid-cols-2 gap-3">
            <Feature title="Schema drift detection" body="Contract-based diff every commit, every event." icon={GitBranch} />
            <Feature title="PII discovery & masking" body="Classifies sensitive fields, masks in-flight." icon={ShieldCheck} />
            <Feature title="Human approval flow" body="Risky remediations route to a queue with context." icon={Sparkles} />
            <Feature title="Pipeline failure email" body="The exact template your ops team expects." icon={AlertTriangle} />
            <Feature title="Lineage graph" body="Field-level lineage across every connector." icon={Database} />
            <Feature title="Always-on agents" body="No cron. The platform watches itself." icon={Activity} />
          </div>
        </div>
      </section>

      {/* ─────────────────────────────────────── CTA ─────────────────────────────────────── */}
      <section className="relative px-6 lg:px-12 py-28 overflow-hidden">
        <div
          aria-hidden
          className="absolute inset-0 opacity-60"
          style={{
            background:
              'radial-gradient(50% 50% at 50% 50%, color-mix(in srgb, var(--accent) 22%, transparent), transparent 70%)',
          }}
        />
        <div className="relative max-w-3xl mx-auto text-center">
          <div className="eyebrow mb-3">/ ready_when_you_are</div>
          <h2 className="font-display text-4xl lg:text-6xl leading-[0.98] tracking-tight">
            Stop reacting.{' '}
            <em className="italic accent-text">Start governing.</em>
          </h2>
          <p className="mt-6 text-[var(--fg-muted)] max-w-xl mx-auto">
            Sign in with the seeded admin account to walk through a fully populated console —
            connectors, pipelines, agents, alerts, and the email workflow.
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link
              to="/login"
              className="inline-flex items-center gap-2 h-12 px-7 rounded-[10px] bg-[var(--accent)] text-[var(--accent-fg)] font-medium shadow-[0_22px_50px_-18px_var(--accent)] hover:bg-[var(--accent-hover)] transition"
            >
              Open the console
              <ArrowUpRight className="size-4" />
            </Link>
            <Link
              to="/register"
              className="inline-flex items-center gap-2 h-12 px-7 rounded-[10px] border border-[var(--border-strong)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition"
            >
              Create an account
            </Link>
          </div>
        </div>
      </section>

      {/* footer */}
      <footer className="px-6 lg:px-12 py-10 border-t border-[var(--border-soft)]">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-4 text-[11px] font-mono uppercase tracking-[0.18em] text-[var(--fg-subtle)]">
          <span>© {new Date().getFullYear()} DataSentinel AI</span>
          <span className="flex items-center gap-4">
            <span>v0.1 · build {new Date().toISOString().slice(0, 10)}</span>
            <span className="flex items-center gap-1.5">
              <span className="size-1.5 rounded-full bg-[var(--success)]" />
              All systems operational
            </span>
          </span>
        </div>
      </footer>
    </div>
  );
}

/* ────────────────────────────────────────── helpers ────────────────────────────────────────── */

function TopBar() {
  return (
    <div className="absolute top-0 inset-x-0 z-30 px-6 lg:px-12 h-16 flex items-center justify-between">
      <Link to="/" className="flex items-center gap-2.5">
        <span className="relative flex items-center justify-center size-8 rounded-lg bg-[var(--accent)] text-[var(--accent-fg)]">
          <span className="font-display font-semibold leading-none">D</span>
        </span>
        <span className="font-display text-[15px]">DataSentinel AI</span>
      </Link>
      <nav className="hidden md:flex items-center gap-6 text-sm text-[var(--fg-muted)]">
        <a href="#agents" className="hover:text-[var(--fg)]">Agents</a>
        <a href="#agents" className="hover:text-[var(--fg)]">Workflow</a>
        <Link to="/login" className="hover:text-[var(--fg)]">Sign in</Link>
        <Link
          to="/login"
          className="inline-flex items-center h-9 px-4 rounded-lg bg-[var(--fg)] text-[var(--bg)] font-medium hover:opacity-90 transition"
        >
          Get started
        </Link>
      </nav>
    </div>
  );
}

function Crosshair({ className }: { className: string }) {
  return (
    <div className={`absolute size-3 ${className}`} aria-hidden>
      <span className="absolute inset-y-0 left-1/2 w-px bg-[var(--fg-subtle)]/40" />
      <span className="absolute inset-x-0 top-1/2 h-px bg-[var(--fg-subtle)]/40" />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-[var(--panel)] p-6">
      <div className="font-display text-3xl lg:text-4xl">{value}</div>
      <div className="mt-1 font-mono text-[10.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
        {label}
      </div>
    </div>
  );
}

function Feature({
  title, body, icon: Icon,
}: { title: string; body: string; icon: typeof GitBranch }) {
  return (
    <div className="group p-5 rounded-[12px] border border-[var(--border)] bg-[var(--panel)] hover:bg-[var(--panel-soft)] hover:border-[var(--border-strong)] transition">
      <Icon className="size-4 text-[var(--accent)] mb-3" strokeWidth={1.5} />
      <h3 className="font-display text-[17px] mb-1">{title}</h3>
      <p className="text-[13px] text-[var(--fg-muted)] leading-relaxed">{body}</p>
    </div>
  );
}

const TELEMETRY_LINES = [
  { lvl: 'INFO', src: 'QualityWatcher',   msg: 'profiled orders.public.customers  → score 89.1%' },
  { lvl: 'WARN', src: 'DriftSentinel',    msg: 'new column tenure_months on gold.churn_features (contract diff)' },
  { lvl: 'INFO', src: 'AnomalyHunter',    msg: 'order_volume z-score 4.2σ vs 7d baseline · ack required' },
  { lvl: 'CRIT', src: 'PIIScout',         msg: 'unmasked phone numbers detected in crm_contacts (412 rows)' },
  { lvl: 'INFO', src: 'AutoRemediator',   msg: 'applied null-tolerance fix on bronze.events.user_id' },
  { lvl: 'INFO', src: 'PolicyEnforcer',   msg: 'enforced confidential tag on customers.ssn → masked' },
  { lvl: 'WARN', src: 'PipelineRunner',   msg: 'CRM Contacts Quality Sweep: connection timeout → alert dispatched' },
];

function TelemetryFeed() {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1800);
    return () => clearInterval(id);
  }, []);

  const lines = Array.from({ length: 7 }, (_, i) => TELEMETRY_LINES[(tick + i) % TELEMETRY_LINES.length]);

  return (
    <div className="p-5 font-mono text-[12.5px] leading-[1.85] text-[var(--fg-muted)] min-h-[260px]">
      {lines.map((l, i) => (
        <motion.div
          key={`${tick}-${i}`}
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: i === 0 ? 1 : 0.6 - i * 0.07, x: 0 }}
          transition={{ duration: 0.4 }}
          className="flex gap-3 whitespace-nowrap overflow-hidden"
        >
          <span className="text-[var(--fg-subtle)]">
            {new Date(Date.now() - i * 1800).toLocaleTimeString('en-IN', { hour12: false })}
          </span>
          <span
            className={
              l.lvl === 'CRIT'
                ? 'text-[var(--danger)]'
                : l.lvl === 'WARN'
                ? 'text-[var(--warning)]'
                : 'text-[var(--accent-2)]'
            }
          >
            [{l.lvl}]
          </span>
          <span className="text-[var(--fg)]">{l.src}</span>
          <span className="truncate">— {l.msg}</span>
        </motion.div>
      ))}
    </div>
  );
}
