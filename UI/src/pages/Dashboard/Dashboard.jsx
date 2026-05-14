import React, { useEffect } from "react";
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  Button,
  Stack,
  Alert,
  Chip,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  Paper,
} from "@mui/material";
import HubIcon from "@mui/icons-material/Hub";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import StorageIcon from "@mui/icons-material/Storage";
import PrivacyTipIcon from "@mui/icons-material/PrivacyTip";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import EventRepeatIcon from "@mui/icons-material/EventRepeat";
import RefreshIcon from "@mui/icons-material/Refresh";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
  BarChart,
  Bar,
} from "recharts";
import { useDispatch, useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import { fetchDashboard } from "../../redux/slices/dashboardSlice";
import StatCard from "../../components/StatCard";
import Loader from "../../components/Loader";
import AlertTable from "../../components/AlertTable";

const SEVERITY_COLORS = {
  critical: "#dc2626",
  high: "#ea580c",
  medium: "#f59e0b",
  low: "#3b82f6",
  info: "#6b7280",
};

const Dashboard = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { data, loading, error } = useSelector((s) => s.dashboard);

  useEffect(() => {
    dispatch(fetchDashboard());
  }, [dispatch]);

  if (loading && !data) return <Loader label="Loading dashboard..." />;

  const overview = data || {};
  const cards = overview.cards || {};
  const charts = overview.charts || {};
  const recentAlerts = overview.recent_alerts || [];
  const connectorHealth = overview.connector_health || [];
  const recentActivity = overview.recent_activity || [];

  const hasNoConnectors = (cards.total_connectors ?? 0) === 0;

  const severityData = (charts.severity || []).map((s) => ({
    name: s.severity,
    value: s.c,
    color: SEVERITY_COLORS[s.severity] || "#6b7280",
  }));

  const trendData = (charts.trend || []).map((t) => ({
    day: t.day
      ? new Date(t.day).toLocaleDateString(undefined, {
          month: "short",
          day: "numeric",
        })
      : "-",
    count: t.c,
  }));
  const categoryData = (charts.category || []).map((c) => ({
    category: c.category,
    count: c.c,
  }));

  return (
    <Box>
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          mb: 3,
        }}
      >
        <Typography
          variant="h5"
          sx={{ fontWeight: 700, color: "text.primary" }}
        >
          Platform Overview
        </Typography>
        <Button
          startIcon={<RefreshIcon />}
          onClick={() => dispatch(fetchDashboard())}
          variant="outlined"
          size="small"
        >
          Refresh
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {hasNoConnectors && (
        <Alert
          severity="info"
          sx={{ mb: 2 }}
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => navigate("/connectors")}
            >
              Add Connector
            </Button>
          }
        >
          <strong>No connectors configured yet.</strong> Add a connector to
          start monitoring your data sources.
        </Alert>
      )}

      {/* Stat Cards */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={4} lg={2}>
          <StatCard
            icon={<HubIcon />}
            label="Total Connectors"
            value={cards.total_connectors}
            color="#e0875a"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={4} lg={2}>
          <StatCard
            icon={<CheckCircleIcon />}
            label="Connected Connectors"
            value={cards.healthy_connectors}
            color="#16a34a"
            textColor={(theme) =>
              theme.palette.mode === "dark" ? "#ffffff" : "#111827"
            }
          />
        </Grid>
        <Grid item xs={12} sm={6} md={4} lg={2}>
          <StatCard
            icon={<StorageIcon />}
            label="Datasets"
            value={cards.dataset_count}
            color="#0891b2"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={4} lg={2}>
          <StatCard
            icon={<PrivacyTipIcon />}
            label="PII Datasets"
            value={cards.pii_datasets}
            color="#dc2626"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={4} lg={2}>
          <StatCard
            icon={<ErrorOutlineIcon />}
            label="Critical Alerts"
            value={cards.critical_alerts}
            color="#ea580c"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={4} lg={2}>
          <StatCard
            icon={<EventRepeatIcon />}
            label="Monitoring Jobs"
            value={cards.monitoring_jobs}
            color="#7c3aed"
          />
        </Grid>
      </Grid>

      {/* Charts Row */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} md={4}>
          <Card sx={{ height: 320 }}>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
                Alerts by Severity (30d)
              </Typography>
              {severityData.length === 0 ? (
                <Box
                  sx={{
                    height: 240,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <Typography color="text.secondary" variant="body2">
                    No alerts yet
                  </Typography>
                </Box>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie
                      data={severityData}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={50}
                      outerRadius={90}
                      label={(e) => `${e.name}: ${e.value}`}
                    >
                      {severityData.map((entry, idx) => (
                        <Cell key={idx} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={5}>
          <Card sx={{ height: 320 }}>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
                Alert Trend (Last 7 Days)
              </Typography>
              {trendData.length === 0 ? (
                <Box
                  sx={{
                    height: 240,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <Typography color="text.secondary" variant="body2">
                    No data
                  </Typography>
                </Box>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={trendData}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                    <XAxis dataKey="day" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line
                      type="monotone"
                      dataKey="count"
                      stroke="#e0875a"
                      // stroke="#2563eb"
                      strokeWidth={2}
                      name="Alerts"
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card sx={{ height: 320 }}>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
                Alerts by Category (30d)
              </Typography>
              {categoryData.length === 0 ? (
                <Box
                  sx={{
                    height: 240,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <Typography color="text.secondary" variant="body2">
                    No data
                  </Typography>
                </Box>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={categoryData}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                    <XAxis
                      dataKey="category"
                      tick={{ fontSize: 10 }}
                      angle={-30}
                      textAnchor="end"
                      height={60}
                    />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#7c3aed" />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tables Row */}
      <Grid container spacing={2}>
        <Grid item xs={12} lg={7}>
          <Card>
            <CardContent>
              <Stack
                direction="row"
                justifyContent="space-between"
                alignItems="center"
                sx={{ mb: 1 }}
              >
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  Recent Alerts
                </Typography>
                <Button size="small" onClick={() => navigate("/alerts")}>
                  View all
                </Button>
              </Stack>
              <AlertTable
                alerts={recentAlerts}
                onRowClick={(a) => navigate(`/alerts?id=${a.id}`)}
                dense
              />
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} lg={5}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
                Connector Health
              </Typography>
              {connectorHealth.length === 0 ? (
                <Typography
                  color="text.secondary"
                  variant="body2"
                  sx={{ p: 2, textAlign: "center" }}
                >
                  No connectors yet.
                </Typography>
              ) : (
                <Paper variant="outlined" sx={{ boxShadow: "none" }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>
                          <strong>Name</strong>
                        </TableCell>
                        <TableCell>
                          <strong>Type</strong>
                        </TableCell>
                        <TableCell>
                          <strong>Status</strong>
                        </TableCell>
                        <TableCell>
                          <strong>Last Scanned</strong>
                        </TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {connectorHealth.map((c) => (
                        <TableRow key={c.id}>
                          <TableCell>{c.name}</TableCell>
                          <TableCell>
                            <Chip
                              label={c.type}
                              size="small"
                              variant="outlined"
                            />
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={c.status}
                              size="small"
                              color={
                                c.status === "Connected"
                                  ? "success"
                                  : c.status === "Connection Failed" ||
                                      c.status === "failed"
                                    ? "error"
                                    : "default"
                              }
                            />
                          </TableCell>
                          <TableCell>
                            <Typography variant="caption">
                              {c.last_scanned_at
                                ? new Date(c.last_scanned_at).toLocaleString()
                                : "-"}
                            </Typography>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Paper>
              )}
            </CardContent>
          </Card>
          <Card sx={{ mt: 2 }}>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
                Recent Monitoring Activity
              </Typography>
              {recentActivity.length === 0 ? (
                <Typography
                  color="text.secondary"
                  variant="body2"
                  sx={{ p: 2, textAlign: "center" }}
                >
                  No monitoring runs yet.
                </Typography>
              ) : (
                <Paper variant="outlined" sx={{ boxShadow: "none" }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>
                          <strong>Type</strong>
                        </TableCell>
                        <TableCell>
                          <strong>Target</strong>
                        </TableCell>
                        <TableCell>
                          <strong>Status</strong>
                        </TableCell>
                        <TableCell>
                          <strong>When</strong>
                        </TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {recentActivity.map((r) => (
                        <TableRow key={r.id}>
                          <TableCell>
                            <Chip label={r.run_type} size="small" />
                          </TableCell>
                          <TableCell>{r.connector_name || "-"}</TableCell>
                          <TableCell>
                            <Chip
                              label={r.status}
                              size="small"
                              color={
                                r.status === "success"
                                  ? "success"
                                  : r.status === "failed"
                                    ? "error"
                                    : "default"
                              }
                            />
                          </TableCell>
                          <TableCell>
                            <Typography variant="caption">
                              {r.started_at
                                ? new Date(r.started_at).toLocaleString()
                                : "-"}
                            </Typography>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Paper>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Dashboard;
