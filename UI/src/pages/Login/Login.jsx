import React, { useState, useEffect } from "react";
import {
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  Typography,
  Alert,
  InputAdornment,
  IconButton,
  Stack,
} from "@mui/material";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import ShieldIcon from "@mui/icons-material/Shield";
import { useDispatch, useSelector } from "react-redux";
import { login, clearError } from "../../redux/slices/authSlice";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Formik, Form } from "formik";
import { Mail } from "lucide-react";

const Login = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const sessionExpired = params.get("session") === "expired";
  const { loading, error, token } = useSelector((s) => s.auth);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);

  useEffect(() => {
    if (token) {
      navigate("/dashboard", { replace: true });
    }
  }, [token, navigate]);

  useEffect(() => {
    return () => {
      dispatch(clearError());
    };
  }, [dispatch]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const result = await dispatch(login({ username, password }));
    if (login.fulfilled.match(result)) {
      navigate("/dashboard", { replace: true });
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-[var(--bg)]">
      <div className="flex items-center justify-center p-8 lg:p-14">
        <div className="w-full max-w-sm">
          <Link to="/" className="flex items-center gap-2.5 mb-12 text-(--fg)">
            <span className="size-9 rounded-lg bg-[var(--accent)] text-[var(--accent-fg)] flex items-center justify-center font-display font-semibold">
              D
            </span>
            <span className="font-display text-base">DataSentinel AI</span>
          </Link>
          <div className="eyebrow mb-3">/ sign_in</div>
          <h1 className="font-display text-4xl lg:text-5xl leading-[1.02] tracking-tight">
            Welcome back.
          </h1>
          <p className="mt-3 text-[var(--fg-muted)]">
            Sign in to your governance console. Demo:{" "}
            <code className="font-mono text-[var(--fg)] text-[12.5px]">
              admin@datasentinel.ai
            </code>{" "}
            ·{" "}
            <code className="font-mono text-[var(--fg)] text-[12.5px]">
              Admin@123
            </code>
          </p>

          {sessionExpired && (
            <div className="mt-6 p-3.5 rounded-lg border border-[var(--warning)]/40 bg-[color-mix(in_srgb,var(--warning)_10%,transparent)] text-[var(--warning)] text-sm flex items-center gap-2">
              <AlertCircle className="size-4 shrink-0" />
              Your session expired. Please sign in again.
            </div>
          )}

          <Box
            sx={{
              maxHeight: "100vh",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "#0a0a0c",
              mt: 2,
            }}
          >
            <Card
              sx={{
                maxWidth: 420,
                width: "100%",
                backgroundColor: "#0a0a0c",
              }}
            >
              <CardContent sx={{ p: 1 }}>
                <form onSubmit={handleSubmit}>
                  <Stack spacing={3}>
                    {error && <Alert severity="error">{error}</Alert>}

                    <Box>
                      <Typography
                        sx={{
                          color: "#c9c9c9",
                          fontSize: "12px",
                          letterSpacing: 2,
                          mb: 1,
                        }}
                      >
                        EMAIL
                      </Typography>
                      <TextField
                        label="Username"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        placeholder="admin@datasentinel.ai"
                        variant="outlined"
                        required 
                        fullWidth
                        autoFocus
                        InputProps={{
                          startAdornment: (
                            <InputAdornment position="start">
                              <Mail sx={{ color: "#888" }} />
                            </InputAdornment>
                          ),
                        }}
                        sx={{
                          input: {
                            color: "#fff",
                          },
                          "& .MuiOutlinedInput-root": {
                            backgroundColor: "#141418",
                            height: "3rem",
                            "& fieldset": {
                              borderColor: "rgba(255,255,255,0.1)",
                            },
                            "&:hover fieldset": {
                              borderColor: "rgba(255,255,255,0.25)",
                            },
                            "&.Mui-focused fieldset": {
                              borderColor: "#ff8a3d",
                            },
                          },
                        }}
                      />
                    </Box>
                    <Box>
                      <Typography
                        sx={{
                          color: "#c9c9c9",
                          fontSize: "12px",
                          letterSpacing: 2,
                          mb: 1,
                        }}
                      >
                        PASSWORD
                      </Typography>
                      <TextField
                        label="Password"
                        type={showPwd ? "text" : "password"}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="••••••••"
                        required
                        fullWidth
                        InputProps={{
                          startAdornment: (
                            <InputAdornment position="start">
                              <Lock sx={{ color: "#888" }} />
                            </InputAdornment>
                          ),
                          endAdornment: (
                            <InputAdornment position="end">
                              <IconButton
                                onClick={() => setShowPwd((s) => !s)}
                                edge="end"
                              >
                                {showPwd ? (
                                  <VisibilityOffIcon sx={{ color: "#888" }} />
                                ) : (
                                  <VisibilityIcon sx={{ color: "#888" }} />
                                )}
                              </IconButton>
                            </InputAdornment>
                          ),
                        }}
                        sx={{
                          input: {
                            color: "#fff",
                          },
                          "& .MuiOutlinedInput-root": {
                            backgroundColor: "#141418",
                            height: "3rem",
                            "& fieldset": {
                              borderColor: "rgba(255,255,255,0.1)",
                            },
                            "&:hover fieldset": {
                              borderColor: "rgba(255,255,255,0.25)",
                            },
                            "&.Mui-focused fieldset": {
                              borderColor: "#ff8a3d",
                            },
                          },
                        }}
                        InputProps={{
                          endAdornment: (
                            <InputAdornment position="end">
                              <IconButton
                                onClick={() => setShowPwd((s) => !s)}
                                edge="end"
                                size="small"
                              >
                                {showPwd ? (
                                  <VisibilityOffIcon />
                                ) : (
                                  <VisibilityIcon />
                                )}
                              </IconButton>
                            </InputAdornment>
                          ),
                        }}
                      />
                    </Box>
                    <Button
                      type="submit"
                      variant="contained"
                      size="large"
                      disabled={loading || !username || !password}
                      fullWidth
                      sx={{
                        mt: 2,
                        py: 1.5,
                        fontWeight: 600,
                        fontSize: "16px",
                        color: "#000",
                        background: "linear-gradient(#d97742 0%, #d97742 100%)",
                        "&:hover": {
                          background:
                            "linear-gradient( #e0875a 0%, #e0875a 100%)",
                        },
                      }}
                    >
                      {loading ? "Signing in..." : "Sign In"}
                    </Button>
                    <Typography
                      variant="caption"
                      align="center"
                      color="text.secondary"
                    >
                      Default credentials: <strong>admin / Admin@123</strong>
                    </Typography>
                  </Stack>

                  <p className="text-center text-sm text-[var(--fg-muted)] pt-2">
                    Don’t have an account?{" "}
                    <Link
                      to="/register"
                      className="text-[var(--accent)] hover:underline"
                    >
                      Create one
                    </Link>
                  </p>
                </form>
              </CardContent>
            </Card>
          </Box>
        </div>
      </div>

      {/* ───────────── right: editorial illustration ───────────── */}
      <div className="hidden lg:flex relative overflow-hidden border-l border-[var(--border)] bg-[var(--bg-elev-1)] grain">
        <div
          aria-hidden
          className="absolute inset-0 opacity-60"
          style={{
            background:
              "radial-gradient(50% 50% at 70% 30%, color-mix(in srgb, var(--accent) 28%, transparent), transparent 70%), radial-gradient(40% 40% at 20% 80%, color-mix(in srgb, var(--accent-2) 20%, transparent), transparent 60%)",
          }}
        />
        <div className="relative m-auto max-w-md p-10">
          <div className="eyebrow mb-4">/ status</div>
          <p className="text-(--fg) font-display italic text-3xl leading-tight tracking-tight">
            “The agents are watching{" "}
            <span className="accent-text not-italic">14.2M</span> records, so
            your team doesn’t have to.”
          </p>
          <p className="mt-8 font-mono text-[11px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
            — DataSentinel · always-on
          </p>

          <div className="mt-12 rounded-xl border border-[var(--border)] bg-[var(--bg-elev-2)] p-5 space-y-3">
            {[
              { lbl: "agents online", val: "6/6", c: "text-[var(--success)]" },
              { lbl: "connectors", val: "5", c: "text-[var(--fg)]" },
              { lbl: "avg quality", val: "94.7%", c: "text-[var(--accent)]" },
              { lbl: "open alerts", val: "4", c: "text-[var(--warning)]" },
            ].map((r) => (
              <div
                key={r.lbl}
                className="flex items-center justify-between font-mono text-[12.5px]"
              >
                <span className="text-[var(--fg-subtle)] tracking-wider uppercase">
                  {r.lbl}
                </span>
                <span className={`${r.c} font-medium`}>{r.val}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
