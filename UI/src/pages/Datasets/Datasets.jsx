import React, { useEffect, useState } from 'react';
import {
  Box, Typography, Card, CardContent, Stack, TextField, MenuItem, Button,
  Drawer, IconButton, Divider, Chip, Table, TableHead, TableRow, TableCell,
  TableBody, Paper, Alert, CircularProgress, Switch, FormControlLabel,
  Accordion, AccordionSummary, AccordionDetails,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import CloseIcon from '@mui/icons-material/Close';
import RuleIcon from '@mui/icons-material/Rule';
import PrivacyTipIcon from '@mui/icons-material/PrivacyTip';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useDispatch, useSelector } from 'react-redux';
import {
  fetchDatasets, fetchDatasetProfile, runQualityCheck, runPiiScan, clearProfile, clearLastAction,
} from '../../redux/slices/datasetSlice';
import { fetchConnectors } from '../../redux/slices/connectorSlice';
import DatasetTable from '../../components/DatasetTable';
import Loader from '../../components/Loader';

const Datasets = () => {
  const dispatch = useDispatch();
  const { list, loading, profile, lastAction } = useSelector((s) => s.datasets);
  const connectors = useSelector((s) => s.connectors.list);
  const [filters, setFilters] = useState({ connector_id: '', contains_pii: 'all', q: '' });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [runningQuality, setRunningQuality] = useState(false);
  const [runningPii, setRunningPii] = useState(false);

  const applyFilters = () => {
    const params = {};
    if (filters.connector_id) params.connector_id = filters.connector_id;
    if (filters.contains_pii === 'pii') params.contains_pii = true;
    if (filters.contains_pii === 'none') params.contains_pii = false;
    if (filters.q) params.q = filters.q;
    dispatch(fetchDatasets(params));
  };

  useEffect(() => {
    dispatch(fetchConnectors());
    dispatch(fetchDatasets());
  }, [dispatch]);

  const openProfile = (d) => {
    dispatch(fetchDatasetProfile(d.id));
    setDrawerOpen(true);
  };

  const closeProfile = () => {
    setDrawerOpen(false);
    dispatch(clearProfile());
    dispatch(clearLastAction());
  };

  const handleQuality = async () => {
    if (!profile?.dataset?.id) return;
    setRunningQuality(true);
    await dispatch(runQualityCheck(profile.dataset.id));
    setRunningQuality(false);
    dispatch(fetchDatasetProfile(profile.dataset.id));
    dispatch(fetchDatasets());
  };

  const handlePii = async () => {
    if (!profile?.dataset?.id) return;
    setRunningPii(true);
    await dispatch(runPiiScan(profile.dataset.id));
    setRunningPii(false);
    dispatch(fetchDatasetProfile(profile.dataset.id));
    dispatch(fetchDatasets());
  };

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Typography variant="h5" sx={{ fontWeight: 700 }}>Datasets</Typography>
        <Button startIcon={<RefreshIcon />} onClick={applyFilters} variant="outlined">
          Refresh
        </Button>
      </Stack>

      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }}>
            <TextField
              select
              label="Connector"
              size="small"
              value={filters.connector_id}
              onChange={(e) => setFilters((f) => ({ ...f, connector_id: e.target.value }))}
              sx={{ minWidth: 200 }}
            >
              <MenuItem value="">All</MenuItem>
              {connectors.map((c) => (
                <MenuItem key={c.id} value={c.id}>{c.name} ({c.type})</MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="PII"
              size="small"
              value={filters.contains_pii}
              onChange={(e) => setFilters((f) => ({ ...f, contains_pii: e.target.value }))}
              sx={{ minWidth: 160 }}
            >
              <MenuItem value="all">All</MenuItem>
              <MenuItem value="pii">Contains PII</MenuItem>
              <MenuItem value="none">No PII</MenuItem>
            </TextField>
            <TextField
              label="Search name"
              size="small"
              value={filters.q}
              onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
              onKeyDown={(e) => { if (e.key === 'Enter') applyFilters(); }}
              sx={{ flex: 1, minWidth: 200 }}
            />
            <Button variant="contained" onClick={applyFilters}>Apply</Button>
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          {loading && (!list || list.length === 0) ? (
            <Loader label="Loading datasets..." />
          ) : (
            <DatasetTable datasets={list} onRowClick={openProfile} />
          )}
        </CardContent>
      </Card>

      <Drawer anchor="right" open={drawerOpen} onClose={closeProfile} PaperProps={{ sx: { width: { xs: '100%', md: 720 } } }}>
        <Box sx={{ p: 3 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
            <Typography variant="h6" sx={{ fontWeight: 700 }}>Dataset Profile</Typography>
            <IconButton onClick={closeProfile}><CloseIcon /></IconButton>
          </Stack>
          {!profile ? (
            <Loader label="Loading..." />
          ) : (
            <Box>
              <Card variant="outlined" sx={{ mb: 2 }}>
                <CardContent>
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>{profile.dataset.dataset_name}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {profile.dataset.connector_name} · {profile.dataset.schema_name || '-'} · {profile.dataset.dataset_type}
                  </Typography>
                  <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap', gap: 1 }}>
                    <Chip
                      label={`Rows: ${profile.dataset.row_count != null && profile.dataset.row_count >= 0 ? profile.dataset.row_count : '-'}`}
                      size="small"
                    />
                    <Chip
                      label={`Columns: ${profile.dataset.column_count ?? (profile.columns?.length || 0)}`}
                      size="small"
                    />
                    {profile.dataset.quality_score != null && (
                      <Chip
                        label={`Quality: ${profile.dataset.quality_score}%`}
                        size="small"
                        color={profile.dataset.quality_score >= 90 ? 'success' : profile.dataset.quality_score >= 70 ? 'warning' : 'error'}
                      />
                    )}
                    {profile.dataset.contains_pii ? (
                      <Chip
                        label={profile.dataset.pii_categories ? `PII: ${profile.dataset.pii_categories}` : 'PII'}
                        size="small" color="error"
                      />
                    ) : null}
                  </Stack>
                </CardContent>
              </Card>

              <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
                <Button
                  startIcon={runningQuality ? <CircularProgress size={16} /> : <RuleIcon />}
                  variant="outlined" disabled={runningQuality} onClick={handleQuality}
                >
                  Run Quality Check
                </Button>
                <Button
                  startIcon={runningPii ? <CircularProgress size={16} /> : <PrivacyTipIcon />}
                  variant="outlined" disabled={runningPii} onClick={handlePii}
                >
                  Run PII Scan
                </Button>
              </Stack>

              {lastAction && (
                <Alert severity={lastAction.error ? 'error' : 'success'} sx={{ mb: 2 }} onClose={() => dispatch(clearLastAction())}>
                  {lastAction.type === 'quality' && !lastAction.error &&
                    `Quality check complete. Score: ${lastAction.score ?? '-'}%. Issues found: ${lastAction.issues?.length ?? 0}.`}
                  {lastAction.type === 'pii' && !lastAction.error &&
                    `PII scan complete. PII columns: ${lastAction.pii?.length ?? 0}.`}
                  {lastAction.error && lastAction.error}
                </Alert>
              )}

              <Typography variant="subtitle2" sx={{ mt: 1, mb: 1, fontWeight: 600 }}>Columns</Typography>
              <Paper variant="outlined" sx={{ boxShadow: 'none', mb: 2 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell><strong>Name</strong></TableCell>
                      <TableCell><strong>Type</strong></TableCell>
                      <TableCell><strong>Nullable</strong></TableCell>
                      <TableCell><strong>PII</strong></TableCell>
                      <TableCell><strong>Null %</strong></TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(profile.columns || []).map((col) => (
                      <TableRow key={col.id}>
                        <TableCell>{col.column_name}</TableCell>
                        <TableCell><Chip label={col.data_type || '-'} size="small" variant="outlined" /></TableCell>
                        <TableCell>{col.is_nullable ? 'Yes' : 'No'}</TableCell>
                        <TableCell>
                          {col.is_pii ? (
                            <Chip label={col.pii_category || 'PII'} size="small" color="error" />
                          ) : '-'}
                        </TableCell>
                        <TableCell>{col.null_pct != null ? `${col.null_pct}%` : '-'}</TableCell>
                      </TableRow>
                    ))}
                    {(profile.columns || []).length === 0 && (
                      <TableRow>
                        <TableCell colSpan={5} align="center">
                          <Typography variant="body2" color="text.secondary">No columns discovered.</Typography>
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </Paper>

              <Typography variant="subtitle2" sx={{ mt: 2, mb: 1, fontWeight: 600 }}>Schema History Snapshots</Typography>
              {(profile.schema_history || []).length === 0 ? (
                <Paper variant="outlined" sx={{ boxShadow: 'none', mb: 2, p: 2, textAlign: 'center' }}>
                  <Typography variant="body2" color="text.secondary">
                    No snapshots yet. Snapshots are captured each time the connector is scanned.
                  </Typography>
                </Paper>
              ) : (
                <Box sx={{ mb: 2 }}>
                  {(profile.schema_history || []).map((h) => {
                    let snapshot = [];
                    try { snapshot = JSON.parse(h.snapshot_json || '[]'); } catch (e) { snapshot = []; }
                    return (
                      <Accordion key={h.id} disableGutters sx={{ mb: 1 }}>
                        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                          <Stack direction="row" spacing={2} alignItems="center" sx={{ width: '100%' }}>
                            <Chip label={`#${h.id}`} size="small" />
                            <Typography variant="body2">
                              {h.captured_at ? new Date(h.captured_at).toLocaleString() : '-'}
                            </Typography>
                            <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
                              {snapshot.length} columns
                            </Typography>
                          </Stack>
                        </AccordionSummary>
                        <AccordionDetails>
                          <Table size="small">
                            <TableHead>
                              <TableRow>
                                <TableCell><strong>Name</strong></TableCell>
                                <TableCell><strong>Type</strong></TableCell>
                                <TableCell><strong>Nullable</strong></TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {snapshot.map((s, i) => (
                                <TableRow key={i}>
                                  <TableCell>{s.name || s.column_name || '-'}</TableCell>
                                  <TableCell>{s.type || s.data_type || '-'}</TableCell>
                                  <TableCell>{s.nullable || s.is_nullable ? 'Yes' : 'No'}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </AccordionDetails>
                      </Accordion>
                    );
                  })}
                </Box>
              )}

              <Typography variant="subtitle2" sx={{ mt: 2, mb: 1, fontWeight: 600 }}>Recent Runs</Typography>
              <Paper variant="outlined" sx={{ boxShadow: 'none' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell><strong>Type</strong></TableCell>
                      <TableCell><strong>Status</strong></TableCell>
                      <TableCell><strong>Started</strong></TableCell>
                      <TableCell><strong>Duration</strong></TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(profile.runs || []).map((r) => (
                      <TableRow key={r.id}>
                        <TableCell><Chip label={r.run_type} size="small" /></TableCell>
                        <TableCell>
                          <Chip
                            label={r.status}
                            size="small"
                            color={r.status === 'success' ? 'success' : r.status === 'failed' ? 'error' : 'default'}
                          />
                        </TableCell>
                        <TableCell><Typography variant="caption">{r.started_at ? new Date(r.started_at).toLocaleString() : '-'}</Typography></TableCell>
                        <TableCell><Typography variant="caption">{r.duration_ms ? `${r.duration_ms} ms` : '-'}</Typography></TableCell>
                      </TableRow>
                    ))}
                    {(profile.runs || []).length === 0 && (
                      <TableRow>
                        <TableCell colSpan={4} align="center">
                          <Typography variant="body2" color="text.secondary">No runs yet.</Typography>
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </Paper>
            </Box>
          )}
        </Box>
      </Drawer>
    </Box>
  );
};

export default Datasets;
