import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Formik, Form } from 'formik';
import * as Yup from 'yup';
import { useState } from 'react';
import { Mail, Lock, ArrowRight, AlertCircle } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';

const Schema = Yup.object({
  email: Yup.string().email('Invalid email').required('Required'),
  password: Yup.string().min(6, 'Min 6 chars').required('Required'),
});

export default function Login2() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [serverError, setServerError] = useState<string | null>(null);
  const sessionExpired = params.get('session') === 'expired';
  const from = params.get('from') || '/dashboard';

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-[var(--bg)]">
      {/* ───────────── left: form ───────────── */}
      <div className="flex items-center justify-center p-8 lg:p-14">
        <div className="w-full max-w-sm">
          <Link to="/" className="flex items-center gap-2.5 mb-12">
            <span className="size-9 rounded-lg bg-[var(--accent)] text-[var(--accent-fg)] flex items-center justify-center font-display font-semibold">D</span>
            <span className="font-display text-base">DataSentinel AI</span>
          </Link>

          <div className="eyebrow mb-3">/ sign_in</div>
          <h1 className="font-display text-4xl lg:text-5xl leading-[1.02] tracking-tight">
            Welcome back.
          </h1>
          <p className="mt-3 text-[var(--fg-muted)]">
            Sign in to your governance console. Demo:{' '}
            <code className="font-mono text-[var(--fg)] text-[12.5px]">admin@datasentinel.ai</code> ·{' '}
            <code className="font-mono text-[var(--fg)] text-[12.5px]">Admin@123</code>
          </p>

          {sessionExpired && (
            <div className="mt-6 p-3.5 rounded-lg border border-[var(--warning)]/40 bg-[color-mix(in_srgb,var(--warning)_10%,transparent)] text-[var(--warning)] text-sm flex items-center gap-2">
              <AlertCircle className="size-4 shrink-0" />
              Your session expired. Please sign in again.
            </div>
          )}

          <Formik
            initialValues={{ email: 'admin@datasentinel.ai', password: 'Admin@123' }}
            validationSchema={Schema}
            onSubmit={async (values, { setSubmitting }) => {
              setServerError(null);
              try {
                await login(values.email, values.password);
                navigate(from);
              } catch (e) {
                setServerError(e?.response?.data?.message || e?.message || 'Login failed');
              } finally {
                setSubmitting(false);
              }
            }}
          >
            {({ values, errors, touched, handleChange, handleBlur, isSubmitting }) => (
              <Form className="mt-8 space-y-4">
                <Input
                  label="Email"
                  name="email"
                  type="email"
                  iconLeft={<Mail className="size-4" />}
                  value={values.email}
                  onChange={handleChange}
                  onBlur={handleBlur}
                  error={touched.email ? errors.email : undefined}
                  autoComplete="email"
                />
                <Input
                  label="Password"
                  name="password"
                  type="password"
                  iconLeft={<Lock className="size-4" />}
                  value={values.password}
                  onChange={handleChange}
                  onBlur={handleBlur}
                  error={touched.password ? errors.password : undefined}
                  autoComplete="current-password"
                />

                {serverError && (
                  <div className="p-3 rounded-lg border border-[var(--danger)]/40 bg-[color-mix(in_srgb,var(--danger)_10%,transparent)] text-[var(--danger)] text-sm flex items-center gap-2">
                    <AlertCircle className="size-4" />
                    {serverError}
                  </div>
                )}

                <Button
                  type="submit"
                  size="lg"
                  loading={isSubmitting}
                  iconRight={<ArrowRight className="size-4" />}
                  className="w-full"
                >
                  Sign in
                </Button>

                <p className="text-center text-sm text-[var(--fg-muted)] pt-2">
                  Don’t have an account?{' '}
                  <Link to="/register" className="text-[var(--accent)] hover:underline">
                    Create one
                  </Link>
                </p>
              </Form>
            )}
          </Formik>
        </div>
      </div>

      {/* ───────────── right: editorial illustration ───────────── */}
      <div className="hidden lg:flex relative overflow-hidden border-l border-[var(--border)] bg-[var(--bg-elev-1)] grain">
        <div
          aria-hidden
          className="absolute inset-0 opacity-60"
          style={{
            background:
              'radial-gradient(50% 50% at 70% 30%, color-mix(in srgb, var(--accent) 28%, transparent), transparent 70%), radial-gradient(40% 40% at 20% 80%, color-mix(in srgb, var(--accent-2) 20%, transparent), transparent 60%)',
          }}
        />
        <div className="relative m-auto max-w-md p-10">
          <div className="eyebrow mb-4">/ status</div>
          <p className="font-display italic text-3xl leading-tight tracking-tight">
            “The agents are watching{' '}
            <span className="accent-text not-italic">14.2M</span> records,{' '}
            so your team doesn’t have to.”
          </p>
          <p className="mt-8 font-mono text-[11px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
            — DataSentinel · always-on
          </p>

          <div className="mt-12 rounded-xl border border-[var(--border)] bg-[var(--bg-elev-2)] p-5 space-y-3">
            {[
              { lbl: 'agents online',  val: '6/6',  c: 'text-[var(--success)]' },
              { lbl: 'connectors',     val: '5',    c: 'text-[var(--fg)]' },
              { lbl: 'avg quality',    val: '94.7%', c: 'text-[var(--accent)]' },
              { lbl: 'open alerts',    val: '4',    c: 'text-[var(--warning)]' },
            ].map((r) => (
              <div key={r.lbl} className="flex items-center justify-between font-mono text-[12.5px]">
                <span className="text-[var(--fg-subtle)] tracking-wider uppercase">{r.lbl}</span>
                <span className={`${r.c} font-medium`}>{r.val}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
