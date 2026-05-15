import React, { useEffect, useState, useMemo } from 'react';
import {
  Box, Typography, Container, Paper, Chip, IconButton, Tooltip,
  ToggleButton, ToggleButtonGroup, TextField, MenuItem, Stack,
  Avatar, Collapse, Divider, Badge, LinearProgress, Button,
  useTheme, alpha, CircularProgress, Grid,
} from '@mui/material';
import { useDispatch, useSelector } from 'react-redux';
import { fetchRuns } from '../../redux/slices/monitoringSlice';
import { fetchConnectors } from '../../redux/slices/connectorSlice';
import RefreshIcon from '@mui/icons-material/Refresh';
import TimelineIcon from '@mui/icons-material/Timeline';
import TableRowsIcon from '@mui/icons-material/TableRows';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty';
import StorageIcon from '@mui/icons-material/Storage';
import AccountTreeIcon from '@mui/icons-material/AccountTree';
import HubIcon from '@mui/icons-material/Hub';
import PrivacyTipIcon from '@mui/icons-material/PrivacyTip';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import FilterListIcon from '@mui/icons-material/FilterList';
import Loader from '../../components/Loader';
import { format, formatDistanceToNow } from 'date-fns';

// ─── Helpers ─────────────────────────────────────────────────────────────────

const STATUS_META = {
  success: { color: '#16a34a', bg: '#dcfce7', icon: <CheckCircleOutlineIcon sx={{ fontSize: 16 }} />, label: 'Success' },
  failed: { color: '#dc2626', bg: '#fee2e2', icon: <ErrorOutlineIcon sx={{ fontSize: 16 }} />, label: 'Failed' },
  running: { color: '#2563eb', bg: '#dbeafe', icon: <HourglassEmptyIcon sx={{ fontSize: 16 }} />, label: 'Running' },
};

const TYPE_META = {
  quality: { icon: <TimelineIcon sx={{ fontSize: 15 }} />, color: '#7c3aed', label: 'Quality' },
  scan: { icon: <StorageIcon sx={{ fontSize: 15 }} />, color: '#0284c7', label: 'Scan' },
  pipeline: { icon: <AccountTreeIcon sx={{ fontSize: 15 }} />, color: '#d97706', label: 'Pipeline' },
};

const getStatusMeta = (status) => STATUS_META[status?.toLowerCase()] || { color: '#6b7280', bg: '#f3f4f6', icon: null, label: status || 'Unknown' };
const getTypeMeta = (type) => TYPE_META[type?.toLowerCase()] || { icon: <StorageIcon sx={{ fontSize: 15 }} />, color: '#6b7280', label: type || 'Run' };

function QualityBadge({ score }) {
  if (score == null) return null;
  const color = score >= 80 ? '#16a34a' : score >= 50 ? '#d97706' : '#dc2626';
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
      <Box sx={{ width: 56, height: 5, borderRadius: 3, bgcolor: '#e2e8f0', overflow: 'hidden' }}>
        <Box sx={{ width: `${Math.min(score, 100)}%`, height: '100%', bgcolor: color, borderRadius: 3, transition: 'width .4s' }} />
      </Box>
      <Typography sx={{ fontSize: 11, fontWeight: 700, color }}>{score.toFixed(0)}%</Typography>
    </Box>
  );
}

function PiiFlag({ pii }) {
  if (!pii) return null;
  return (
    <Chip
      icon={<PrivacyTipIcon sx={{ fontSize: 12, color: '#dc2626 !important' }} />}
      label="PII"
      size="small"
      sx={{ height: 18, fontSize: 10, fontWeight: 700, bgcolor: '#fee2e2', color: '#dc2626', border: '1px solid #fca5a5', px: 0.2 }}
    />
  );
}

// ─── Timeline Node ────────────────────────────────────────────────────────────

function TimelineNode({ run, isLast, groupDate }) {
  const [expanded, setExpanded] = useState(false);
  const theme = useTheme();
  const sm = getStatusMeta(run.status);
  const tm = getTypeMeta(run.run_type);
  const hasAlert = run.quality_score != null && (run.quality_score < 50 || run.pii_percentage > 0);

  const metrics = useMemo(() => {
    try {
      return run.metrics_json ? JSON.parse(run.metrics_json) : null;
    } catch (e) {
      console.warn('Failed to parse metrics_json', e);
      return null;
    }
  }, [run.metrics_json]);

  const llm = metrics?.llm || metrics?.llm_report || {};
  const python = metrics?.python || {};

  const hasData = (val) => {
    if (val === null || val === undefined || val === '') return false;
    if (Array.isArray(val) && val.length === 0) return false;
    if (typeof val === 'object' && Object.keys(val).length === 0) return false;
    return true;
  };

  return (
    <Box sx={{ display: 'flex', gap: 0, position: 'relative' }}>
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', mr: 2, flexShrink: 0 }}>
        <Box
          sx={{
            width: 40, height: 40, borderRadius: '50%',
            bgcolor: sm.bg, border: `2px solid ${sm.color}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: sm.color, flexShrink: 0, zIndex: 1,
            boxShadow: `0 0 0 4px ${alpha(sm.color, 0.1)}`,
          }}
        >
          {React.cloneElement(sm.icon, { sx: { fontSize: 20 } })}
        </Box>
        {!isLast && (
          <Box sx={{ width: 2, flexGrow: 1, minHeight: 24, bgcolor: theme.palette.divider, mt: 0.5 }} />
        )}
      </Box>

      <Paper
        variant="outlined"
        sx={{
          flex: 1, mb: 2, borderRadius: 3, overflow: 'hidden',
          borderColor: hasAlert ? alpha('#dc2626', 0.4) : theme.palette.divider,
          transition: 'all .2s cubic-bezier(0.4, 0, 0.2, 1)',
          '&:hover': { 
            boxShadow: theme.shadows[4],
            transform: 'translateY(-1px)',
            borderColor: theme.palette.primary.light
          },
        }}
      >
        <Box 
          onClick={() => setExpanded(v => !v)}
          sx={{ 
            px: 2.5, py: 1.75, display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap',
            cursor: 'pointer',
            transition: 'background-color 0.2s',
            '&:hover': { bgcolor: alpha(theme.palette.action.hover, 0.05) }
          }}
        >
          <Chip
            icon={React.cloneElement(tm.icon, { sx: { fontSize: 14, color: `${tm.color} !important` } })}
            label={tm.label}
            size="small"
            sx={{ height: 26, fontSize: 12, fontWeight: 700, bgcolor: alpha(tm.color, 0.1), color: tm.color, border: `1px solid ${alpha(tm.color, 0.25)}` }}
          />

          {run.connector_name && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
              <HubIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
              <Typography sx={{ fontSize: 14, fontWeight: 600 }}>{run.connector_name}</Typography>
            </Box>
          )}

          {run.dataset_name && (
            <>
              <Typography sx={{ fontSize: 14, color: 'text.disabled' }}>›</Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                <StorageIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
                <Typography sx={{ fontSize: 14, color: 'text.secondary', fontWeight: 500 }}>{run.dataset_name}</Typography>
              </Box>
            </>
          )}

          <Box sx={{ ml: 'auto', display: 'flex', alignItems: 'center', gap: 2 }}>
            <PiiFlag pii={run.pii_percentage > 0} />
            {run.quality_score != null && (
              <Box sx={{ scale: '1.1' }}>
                <QualityBadge score={run.quality_score} />
              </Box>
            )}
            {hasAlert && (
              <Tooltip title="Quality < 50% or PII detected — alert sent">
                <WarningAmberIcon sx={{ fontSize: 20, color: '#d97706' }} />
              </Tooltip>
            )}
            <Typography sx={{ fontSize: 12, color: 'text.disabled', whiteSpace: 'nowrap' }}>
              {run.started_at ? formatDistanceToNow(new Date(run.started_at), { addSuffix: true }) : ''}
            </Typography>
            <Chip
              label={sm.label}
              size="small"
              sx={{ height: 24, fontSize: 11, fontWeight: 800, bgcolor: sm.bg, color: sm.color }}
            />
            <IconButton size="small" sx={{ p: 0.25 }}>
              {expanded ? <ExpandLessIcon sx={{ fontSize: 22 }} /> : <ExpandMoreIcon sx={{ fontSize: 22 }} />}
            </IconButton>
          </Box>
        </Box>

        <Collapse in={expanded}>
          <Divider />
          <Box sx={{ px: 3, py: 2.5, bgcolor: '#ffffff' }}>
            <Stack direction="row" spacing={5} sx={{ mb: 3, flexWrap: 'wrap' }}>
              <Box>
                <Typography sx={{ fontSize: 11, color: 'text.disabled', fontWeight: 800, textTransform: 'uppercase', mb: 0.75 }}>Run ID</Typography>
                <Typography sx={{ fontSize: 13, fontFamily: 'monospace', fontWeight: 600 }}>#{run.id}</Typography>
              </Box>
              {run.started_at && (
                <Box>
                  <Typography sx={{ fontSize: 11, color: 'text.disabled', fontWeight: 800, textTransform: 'uppercase', mb: 0.75 }}>Started</Typography>
                  <Typography sx={{ fontSize: 13, fontWeight: 500 }}>{format(new Date(run.started_at), 'MMM dd, yyyy HH:mm:ss')}</Typography>
                </Box>
              )}
              {run.finished_at && (
                <Box>
                  <Typography sx={{ fontSize: 11, color: 'text.disabled', fontWeight: 800, textTransform: 'uppercase', mb: 0.75 }}>Finished</Typography>
                  <Typography sx={{ fontSize: 13, fontWeight: 500 }}>{format(new Date(run.finished_at), 'MMM dd, yyyy HH:mm:ss')}</Typography>
                </Box>
              )}
              {python.score != null && (
                <Box>
                  <Typography sx={{ fontSize: 11, color: 'text.disabled', fontWeight: 800, textTransform: 'uppercase', mb: 0.75 }}>Quality Score</Typography>
                  <Typography sx={{ fontSize: 13, fontWeight: 800, color: python.score >= 80 ? 'success.main' : 'warning.main' }}>{python.score}%</Typography>
                </Box>
              )}
              {hasData(python.confidence) && (
                <Box>
                  <Typography sx={{ fontSize: 11, color: 'text.disabled', fontWeight: 800, textTransform: 'uppercase', mb: 0.75 }}>Confidence</Typography>
                  <Typography sx={{ fontSize: 13, fontWeight: 500 }}>{(python.confidence * 100).toFixed(0)}%</Typography>
                </Box>
              )}
              {hasData(python.severity) && (
                <Box>
                  <Typography sx={{ fontSize: 11, color: 'text.disabled', fontWeight: 800, textTransform: 'uppercase', mb: 0.75 }}>Severity</Typography>
                  <Chip label={python.severity} size="small" sx={{ height: 20, fontSize: 10, fontWeight: 800, textTransform: 'uppercase', bgcolor: python.severity === 'critical' ? '#fee2e2' : '#f3f4f6', color: python.severity === 'critical' ? '#dc2626' : 'text.secondary' }} />
                </Box>
              )}
            </Stack>

            <Stack spacing={2.5}>
              {hasData(llm.technical_summary) && (
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, bgcolor: '#fff', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
                  <Typography sx={{ fontSize: 11, color: 'primary.main', fontWeight: 900, textTransform: 'uppercase', mb: 1, display: 'flex', alignItems: 'center', gap: 0.75 }}>
                    <CheckCircleOutlineIcon sx={{ fontSize: 16 }} /> Technical Summary
                  </Typography>
                  <Typography sx={{ fontSize: 13.5, lineHeight: 1.6, color: 'text.primary' }}>{llm.technical_summary}</Typography>
                </Paper>
              )}

              {hasData(llm.contextual_summary) && (
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, bgcolor: '#fff', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
                  <Typography sx={{ fontSize: 11, color: '#6366f1', fontWeight: 900, textTransform: 'uppercase', mb: 1, display: 'flex', alignItems: 'center', gap: 0.75 }}>
                    <TimelineIcon sx={{ fontSize: 16 }} /> Contextual Analysis
                  </Typography>
                  <Typography sx={{ fontSize: 13.5, lineHeight: 1.6, color: 'text.secondary' }}>{llm.contextual_summary}</Typography>
                </Paper>
              )}

              {hasData(python) && (
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, bgcolor: alpha(theme.palette.primary.main, 0.01) }}>
                   <Typography sx={{ fontSize: 11, color: 'text.secondary', fontWeight: 900, textTransform: 'uppercase', mb: 2, display: 'flex', alignItems: 'center', gap: 0.75 }}>
                    <TableRowsIcon sx={{ fontSize: 16 }} /> Technical Details
                  </Typography>
                  <Grid container spacing={3}>
                    {hasData(python.total_rules) && (
                      <Grid item xs={6} sm={3}>
                        <Typography sx={{ fontSize: 10, color: 'text.disabled', fontWeight: 700, textTransform: 'uppercase' }}>Total Rules</Typography>
                        <Typography sx={{ fontSize: 14, fontWeight: 700 }}>{python.total_rules}</Typography>
                      </Grid>
                    )}
                    {hasData(python.passed) && (
                      <Grid item xs={6} sm={3}>
                        <Typography sx={{ fontSize: 10, color: 'text.disabled', fontWeight: 700, textTransform: 'uppercase' }}>Passed</Typography>
                        <Typography sx={{ fontSize: 14, fontWeight: 700, color: 'success.main' }}>{python.passed}</Typography>
                      </Grid>
                    )}
                    {hasData(python.failed) && (
                      <Grid item xs={6} sm={3}>
                        <Typography sx={{ fontSize: 10, color: 'text.disabled', fontWeight: 700, textTransform: 'uppercase' }}>Failed</Typography>
                        <Typography sx={{ fontSize: 14, fontWeight: 700, color: 'error.main' }}>{python.failed}</Typography>
                      </Grid>
                    )}
                    {hasData(python.outlier_count) && (
                      <Grid item xs={6} sm={3}>
                        <Typography sx={{ fontSize: 10, color: 'text.disabled', fontWeight: 700, textTransform: 'uppercase' }}>Outliers</Typography>
                        <Typography sx={{ fontSize: 14, fontWeight: 700 }}>{python.outlier_count}</Typography>
                      </Grid>
                    )}
                    {hasData(python.pii_columns) && (
                      <Grid item xs={12}>
                        <Typography sx={{ fontSize: 10, color: 'text.disabled', fontWeight: 700, textTransform: 'uppercase', mb: 0.5 }}>PII Columns</Typography>
                        <Stack direction="row" spacing={1} flexWrap="wrap" gap={1}>
                          {python.pii_columns.map(col => <Chip key={col} label={col} size="small" sx={{ fontSize: 11 }} />)}
                        </Stack>
                      </Grid>
                    )}
                    {hasData(python.failed_rules) && (
                       <Grid item xs={12}>
                        <Typography sx={{ fontSize: 10, color: 'text.disabled', fontWeight: 700, textTransform: 'uppercase', mb: 1 }}>Failed Rules</Typography>
                        <Stack spacing={1}>
                          {python.failed_rules.map((fr, i) => (
                            <Box key={i} sx={{ p: 1, bgcolor: '#fee2e2', borderRadius: 1, border: '1px solid #fca5a5' }}>
                              <Typography sx={{ fontSize: 12, fontWeight: 700, color: '#b91c1c' }}>{fr.rule}</Typography>
                              <Typography sx={{ fontSize: 11, color: '#b91c1c' }}>{fr.reason}</Typography>
                            </Box>
                          ))}
                        </Stack>
                      </Grid>
                    )}
                    {hasData(python.findings) && (
                       <Grid item xs={12}>
                        <Typography sx={{ fontSize: 10, color: 'text.disabled', fontWeight: 700, textTransform: 'uppercase', mb: 1 }}>Findings</Typography>
                        <Stack spacing={0.5}>
                          {python.findings.map((f, i) => (
                            <Typography key={i} sx={{ fontSize: 12.5, color: 'text.secondary', display: 'flex', gap: 1 }}>
                              • {f}
                            </Typography>
                          ))}
                        </Stack>
                      </Grid>
                    )}
                  </Grid>
                </Paper>
              )}

              {hasData(llm.recommendations) && (
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, bgcolor: alpha('#6366f1', 0.03), borderColor: alpha('#6366f1', 0.2) }}>
                  <Typography sx={{ fontSize: 11, color: '#6366f1', fontWeight: 900, textTransform: 'uppercase', mb: 1.5, display: 'flex', alignItems: 'center', gap: 0.75 }}>
                    <WarningAmberIcon sx={{ fontSize: 16 }} /> Recommendations
                  </Typography>
                  <Stack spacing={1.5}>
                    {llm.recommendations.map((rec, i) => (
                      <Box key={i} sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start' }}>
                        <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: '#6366f1', mt: 1, flexShrink: 0 }} />
                        <Typography sx={{ fontSize: 13.5, color: 'text.primary', fontWeight: 500 }}>{rec}</Typography>
                      </Box>
                    ))}
                  </Stack>
                </Paper>
              )}
            </Stack>
          </Box>
        </Collapse>
      </Paper>
    </Box>
  );
}

// ─── Date Group ───────────────────────────────────────────────────────────────

function DateGroup({ dateLabel, runs }) {
  return (
    <Box sx={{ mb: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
        <Typography sx={{ fontSize: 13, fontWeight: 900, color: 'text.disabled', textTransform: 'uppercase', letterSpacing: 1.2 }}>
          {dateLabel}
        </Typography>
        <Box sx={{ flex: 1, height: 1, bgcolor: 'divider' }} />
        <Typography sx={{ fontSize: 12, color: 'text.disabled', fontWeight: 600 }}>{runs.length} run{runs.length !== 1 ? 's' : ''}</Typography>
      </Box>
      {runs.map((run, i) => (
        <TimelineNode key={run.id} run={run} isLast={i === runs.length - 1} />
      ))}
    </Box>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

const DataQualityHistory = () => {
  const dispatch = useDispatch();
  const theme = useTheme();
  const { runs, loading } = useSelector((s) => s.monitoring);
  const connectors = useSelector((s) => s.connectors.list);

  const [filterConnector, setFilterConnector] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    dispatch(fetchRuns(100));
    dispatch(fetchConnectors());
  }, [dispatch]);

  // Filtered + grouped runs
  const [searchTerm, setSearchTerm] = useState('');

  const filtered = useMemo(() => {
    return runs.filter((r) => {
      const matchConnector = !filterConnector || String(r.connector_id) === filterConnector;
      const matchType = !filterType || r.run_type === filterType;
      const matchStatus = !filterStatus || r.status === filterStatus;
      
      const searchStr = searchTerm.toLowerCase();
      const matchSearch = !searchTerm || 
        (r.connector_name?.toLowerCase().includes(searchStr)) ||
        (r.dataset_name?.toLowerCase().includes(searchStr)) ||
        (r.message?.toLowerCase().includes(searchStr));

      return matchConnector && matchType && matchStatus && matchSearch;
    });
  }, [runs, filterConnector, filterType, filterStatus, searchTerm]);

  // Group by date
  const grouped = useMemo(() => {
    const groups = {};
    filtered.forEach((r) => {
      const d = r.started_at ? format(new Date(r.started_at), 'MMM dd, yyyy') : 'Unknown date';
      if (!groups[d]) groups[d] = [];
      groups[d].push(r);
    });
    return groups;
  }, [filtered]);

  // Stats
  const stats = useMemo(() => {
    const total = filtered.length;
    const success = filtered.filter(r => r.status?.toLowerCase() === 'success').length;
    const failed = filtered.filter(r => r.status?.toLowerCase() === 'failed').length;
    const pii = filtered.filter(r => r.pii_percentage > 0).length;
    const lowQ = filtered.filter(r => r.quality_score != null && r.quality_score < 50).length;
    return { total, success, failed, pii, lowQ };
  }, [filtered]);

  const activeFilters = [filterConnector, filterType, filterStatus].filter(Boolean).length;

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ mb: 6 }}>

        {/* Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 3 }}>
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 800, letterSpacing: -0.5 }}>
              Data Quality History
            </Typography>
            <Typography sx={{ color: 'text.secondary', mt: 0.5, fontSize: 15, fontWeight: 500 }}>
              Timeline of all pipeline runs, quality checks &amp; scans
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <TextField
              placeholder="Search history..."
              size="small"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              sx={{ 
                width: 240,
                '& .MuiOutlinedInput-root': {
                  borderRadius: 2,
                  bgcolor: 'action.hover',
                  '& fieldset': { borderColor: 'transparent' },
                  '&:hover fieldset': { borderColor: 'divider' },
                  '&.Mui-focused fieldset': { borderColor: 'primary.main' },
                }
              }}
            />
            <Tooltip title="Filters">
              <Badge badgeContent={activeFilters} color="primary">
                <IconButton onClick={() => setShowFilters(v => !v)} sx={{ border: `1px solid ${theme.palette.divider}` }}>
                  <FilterListIcon />
                </IconButton>
              </Badge>
            </Tooltip>
            <Tooltip title="Refresh">
              <IconButton
                onClick={() => dispatch(fetchRuns(100))}
                disabled={loading}
                sx={{ border: `1px solid ${theme.palette.divider}` }}
              >
                {loading ? <CircularProgress size={18} /> : <RefreshIcon />}
              </IconButton>
            </Tooltip>
          </Stack>
        </Box>

        {/* Stat pills */}
        <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: 'wrap', gap: 1 }}>
          {[
            { label: 'Total Runs', value: stats.total, color: '#6366f1' },
            { label: 'Success', value: stats.success, color: '#16a34a' },
            { label: 'Failed', value: stats.failed, color: '#dc2626' },
            { label: 'PII Detected', value: stats.pii, color: '#f43f5e' },
            { label: 'Quality < 50%', value: stats.lowQ, color: '#d97706' },
          ].map((s) => (
            <Paper
              key={s.label}
              variant="outlined"
              sx={{ px: 2, py: 0.75, borderRadius: 2, display: 'flex', alignItems: 'center', gap: 1, borderColor: alpha(s.color, 0.3) }}
            >
              <Typography sx={{ fontSize: 18, fontWeight: 800, color: s.color, lineHeight: 1 }}>{s.value}</Typography>
              <Typography sx={{ fontSize: 11, color: 'text.secondary' }}>{s.label}</Typography>
            </Paper>
          ))}
        </Stack>

        {/* Filters */}
        <Collapse in={showFilters}>
          <Paper variant="outlined" sx={{ p: 2, mb: 2, borderRadius: 2, display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
            <TextField
              select label="Connector" size="small" value={filterConnector}
              onChange={(e) => setFilterConnector(e.target.value)}
              sx={{ minWidth: 180 }}
            >
              <MenuItem value="">All Connectors</MenuItem>
              {connectors.map((c) => (
                <MenuItem key={c.id} value={String(c.id)}>{c.name}</MenuItem>
              ))}
            </TextField>
            <TextField
              select label="Run Type" size="small" value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              sx={{ minWidth: 140 }}
            >
              <MenuItem value="">All Types</MenuItem>
              <MenuItem value="quality">Quality</MenuItem>
              <MenuItem value="scan">Scan</MenuItem>
              <MenuItem value="pipeline">Pipeline</MenuItem>
            </TextField>
            <TextField
              select label="Status" size="small" value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              sx={{ minWidth: 130 }}
            >
              <MenuItem value="">All Statuses</MenuItem>
              <MenuItem value="success">Success</MenuItem>
              <MenuItem value="failed">Failed</MenuItem>
              <MenuItem value="running">Running</MenuItem>
            </TextField>
            {activeFilters > 0 && (
              <Button size="small" onClick={() => { setFilterConnector(''); setFilterType(''); setFilterStatus(''); }}>
                Clear filters
              </Button>
            )}
          </Paper>
        </Collapse>

        {/* Timeline */}
        {loading && runs.length === 0 ? (
          <Loader label="Loading history..." />
        ) : filtered.length === 0 ? (
          <Paper variant="outlined" sx={{ p: 6, textAlign: 'center', borderRadius: 3 }}>
            <TimelineIcon sx={{ fontSize: 40, color: 'text.disabled', mb: 1 }} />
            <Typography color="text.secondary">No runs found{activeFilters ? ' for selected filters' : ''}.</Typography>
          </Paper>
        ) : (
          <Box>
            {Object.entries(grouped).map(([dateLabel, groupRuns]) => (
              <DateGroup key={dateLabel} dateLabel={dateLabel} runs={groupRuns} />
            ))}
          </Box>
        )}
      </Box>
    </Box>
  );
};

export default DataQualityHistory;