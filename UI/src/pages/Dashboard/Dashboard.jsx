import React, { useEffect } from "react";
import {
  Box, Grid, Card, CardContent, Typography, Button, Stack,
  Alert, Chip, Table, TableHead, TableRow, TableCell, TableBody, Paper,
  useTheme, Avatar
} from '@mui/material';
import HubIcon from '@mui/icons-material/Hub';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import StorageIcon from '@mui/icons-material/Storage';
import PrivacyTipIcon from '@mui/icons-material/PrivacyTip';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import EventRepeatIcon from '@mui/icons-material/EventRepeat';
import RefreshIcon from '@mui/icons-material/Refresh';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Legend, BarChart, Bar,
  AreaChart, Area
} from 'recharts';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { fetchDashboard } from '../../redux/slices/dashboardSlice';
import StatCard from '../../components/StatCard';
import Loader from '../../components/Loader';
import AlertTable from '../../components/AlertTable';

const SEVERITY_COLORS = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#f59e0b',
  low: '#3b82f6',
  info: '#6b7280',
};

const Dashboard = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const theme = useTheme();
  const { data, loading, error } = useSelector((s) => s.dashboard);

  useEffect(() => {
    dispatch(fetchDashboard());
  }, [dispatch]);

  if (loading && !data) return <Loader label="Computing intelligence..." />;

  const overview = data || {};
  const cards = overview.cards || {};
  const charts = overview.charts || {};
  const recentAlerts = overview.recent_alerts || [];
  const connectorHealth = overview.connector_health || [];
  const recentActivity = overview.recent_activity || [];

  const severityData = (charts.severity || []).map((s) => ({
    name: s.severity.charAt(0).toUpperCase() + s.severity.slice(1),
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
    count: c.c 
  }));

  const cardConfigs = [
    { label: 'Total Connectors', value: cards.total_connectors, icon: <HubIcon />, color: '#6366f1' },
    { label: 'Healthy Connectors', value: cards.healthy_connectors, icon: <CheckCircleIcon />, color: '#10b981' },
    { label: 'Total Datasets', value: cards.dataset_count, icon: <StorageIcon />, color: '#0ea5e9' },
    { label: 'PII Datasets', value: cards.pii_datasets, icon: <PrivacyTipIcon />, color: '#f43f5e' },
    { label: 'Critical Alerts', value: cards.critical_alerts, icon: <ErrorOutlineIcon />, color: '#f97316' },
    { label: 'Active Jobs', value: cards.monitoring_jobs, icon: <EventRepeatIcon />, color: '#8b5cf6' },
  ];

  return (
    <Box sx={{ pb: 4 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', mb: 4 }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 800, letterSpacing: '-0.02em', color: 'text.primary' }}>
            Executive Dashboard
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Real-time governance oversight and data quality intelligence.
          </Typography>
        </Box>
        <Stack direction="row" spacing={2}>
          <Button 
            startIcon={<RefreshIcon />} 
            onClick={() => dispatch(fetchDashboard())} 
            variant="contained" 
            sx={{ 
              borderRadius: 2,
              textTransform: 'none',
              fontWeight: 600,
              boxShadow: '0 4px 12px rgba(0,0,0,0.1)'
            }}
          >
            Refresh Data
          </Button>
        </Stack>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3, borderRadius: 2 }}>
          {error}
        </Alert>
      )}

      {/* Stats Grid */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        {cardConfigs.map((config, idx) => (
          <Grid item xs={12} sm={6} md={4} lg={2} key={idx}>
            <StatCard 
              icon={config.icon} 
              label={config.label} 
              value={config.value} 
              color={config.color}
            />
          </Grid>
        ))}
      </Grid>

      {/* Main Charts Row */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={8}>
          <Card sx={{ borderRadius: 3, boxShadow: '0 4px 20px rgba(0,0,0,0.05)', border: '1px solid', borderColor: 'divider' }}>
            <CardContent sx={{ p: 3 }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
                <Box>
                  <Typography variant="h6" sx={{ fontWeight: 700 }}>Alert Velocity</Typography>
                  <Typography variant="caption" color="text.secondary">Alert frequency over the last 7 days</Typography>
                </Box>
                <TrendingUpIcon color="primary" />
              </Stack>
              <Box sx={{ height: 300, width: '100%' }}>
                {trendData.length === 0 ? (
                  <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Typography color="text.secondary">No historical data available</Typography>
                  </Box>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={trendData}>
                      <defs>
                        <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={theme.palette.primary.main} stopOpacity={0.1}/>
                          <stop offset="95%" stopColor={theme.palette.primary.main} stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={theme.palette.divider} />
                      <XAxis 
                        dataKey="day" 
                        axisLine={false} 
                        tickLine={false} 
                        tick={{ fill: theme.palette.text.secondary, fontSize: 12 }} 
                      />
                      <YAxis 
                        axisLine={false} 
                        tickLine={false} 
                        tick={{ fill: theme.palette.text.secondary, fontSize: 12 }}
                      />
                      <Tooltip 
                        contentStyle={{ 
                          borderRadius: '8px', 
                          border: 'none', 
                          boxShadow: '0 4px 12px rgba(0,0,0,0.1)' 
                        }} 
                      />
                      <Area 
                        type="monotone" 
                        dataKey="count" 
                        stroke={theme.palette.primary.main} 
                        strokeWidth={3} 
                        fillOpacity={1} 
                        fill="url(#colorCount)" 
                        name="Alerts"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card sx={{ height: '100%', borderRadius: 3, boxShadow: '0 4px 20px rgba(0,0,0,0.05)', border: '1px solid', borderColor: 'divider' }}>
            <CardContent sx={{ p: 3 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>Severity Mix</Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 3 }}>
                Distribution of alerts by impact level
              </Typography>
              <Box sx={{ height: 280 }}>
                {severityData.length === 0 ? (
                  <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Typography color="text.secondary">System healthy</Typography>
                  </Box>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={severityData}
                        dataKey="value"
                        nameKey="name"
                        innerRadius={60}
                        outerRadius={80}
                        paddingAngle={5}
                      >
                        {severityData.map((entry, idx) => (
                          <Cell key={idx} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip 
                         contentStyle={{ 
                          borderRadius: '8px', 
                          border: 'none', 
                          boxShadow: '0 4px 12px rgba(0,0,0,0.1)' 
                        }} 
                      />
                      <Legend verticalAlign="bottom" height={36}/>
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tables Row */}
      <Grid container spacing={3}>
        <Grid item xs={12} lg={7}>
          <Card sx={{ borderRadius: 3, boxShadow: '0 4px 20px rgba(0,0,0,0.05)', border: '1px solid', borderColor: 'divider' }}>
            <CardContent sx={{ p: 3 }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
                <Box>
                  <Typography variant="h6" sx={{ fontWeight: 700 }}>Critical Incidents</Typography>
                  <Typography variant="caption" color="text.secondary">Most recent high-priority alerts</Typography>
                </Box>
                <Button size="small" onClick={() => navigate('/alerts')} sx={{ textTransform: 'none', fontWeight: 600 }}>
                  View All Alerts
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
          <Stack spacing={3}>
            <Card sx={{ borderRadius: 3, boxShadow: '0 4px 20px rgba(0,0,0,0.05)', border: '1px solid', borderColor: 'divider' }}>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>Infrastructure Health</Typography>
                {connectorHealth.length === 0 ? (
                  <Typography color="text.secondary" variant="body2" sx={{ p: 2, textAlign: 'center' }}>
                    No connectors configured.
                  </Typography>
                ) : (
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ borderBottom: 'none', fontWeight: 600 }}>Source</TableCell>
                        <TableCell sx={{ borderBottom: 'none', fontWeight: 600 }}>Status</TableCell>
                        <TableCell sx={{ borderBottom: 'none', fontWeight: 600 }}>Last Scan</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {connectorHealth.slice(0, 5).map((c) => (
                        <TableRow key={c.id} hover sx={{ '&:last-child td, &:last-child th': { border: 0 } }}>
                          <TableCell>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                              <Typography variant="body2" sx={{ fontWeight: 500 }}>{c.name}</Typography>
                              <Chip label={c.type} size="small" variant="outlined" sx={{ height: 20, fontSize: '0.65rem' }} />
                            </Box>
                          </TableCell>
                          <TableCell>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                              <Box sx={{ 
                                width: 8, 
                                height: 8, 
                                borderRadius: '50%', 
                                bgcolor: c.status === 'Connected' ? 'success.main' : 'error.main' 
                              }} />
                              <Typography variant="caption">{c.status}</Typography>
                            </Box>
                          </TableCell>
                          <TableCell>
                            <Typography variant="caption" color="text.secondary">
                              {c.last_scanned_at ? new Date(c.last_scanned_at).toLocaleDateString() : '-'}
                            </Typography>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>

            <Card sx={{ borderRadius: 3, boxShadow: '0 4px 20px rgba(0,0,0,0.05)', border: '1px solid', borderColor: 'divider' }}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                  <Typography variant="h6" sx={{ fontWeight: 700 }}>Monitoring Stream</Typography>
                  <Button 
                    size="small" 
                    onClick={() => navigate('/data-quality-history')} 
                    sx={{ textTransform: 'none', fontWeight: 600 }}
                  >
                    View All
                  </Button>
                </Stack>
                <Stack spacing={2}>
                  {recentActivity.length === 0 ? (
                    <Typography color="text.secondary" variant="body2" sx={{ textAlign: 'center' }}>
                      No recent activity.
                    </Typography>
                  ) : (
                    recentActivity.slice(0, 5).map((r) => (
                      <Box key={r.id} sx={{ display: 'flex', alignItems: 'start', gap: 2 }}>
                        <Avatar sx={{ width: 32, height: 32, bgcolor: r.status === 'success' ? 'success.light' : 'error.light', fontSize: '0.75rem' }}>
                          {r.run_type?.charAt(0).toUpperCase()}
                        </Avatar>
                        <Box sx={{ flex: 1 }}>
                          <Stack direction="row" justifyContent="space-between" alignItems="center">
                            <Typography variant="body2" sx={{ fontWeight: 700, color: 'text.primary' }}>
                              {r.dataset_name || r.connector_name}
                            </Typography>
                            <Chip 
                              label={r.run_type} 
                              size="small" 
                              sx={{ 
                                height: 18, 
                                fontSize: '0.65rem', 
                                textTransform: 'uppercase', 
                                fontWeight: 700,
                                bgcolor: 'primary.light',
                                color: 'primary.dark',
                                border: 'none'
                              }} 
                            />
                          </Stack>
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                            {r.connector_name} • {new Date(r.started_at).toLocaleString()}
                          </Typography>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.25 }}>
                            <Box sx={{ 
                              width: 6, 
                              height: 6, 
                              borderRadius: '50%', 
                              bgcolor: r.status === 'success' ? 'success.main' : 'error.main' 
                            }} />
                            <Typography variant="caption" sx={{ fontWeight: 500, color: r.status === 'success' ? 'success.main' : 'error.main' }}>
                              {r.status}
                            </Typography>
                          </Box>
                        </Box>
                      </Box>
                    ))
                  )}
                </Stack>
              </CardContent>
            </Card>
          </Stack>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Dashboard;
