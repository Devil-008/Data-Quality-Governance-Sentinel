import React, { useEffect, useState } from 'react';
import {
  Box, Typography, Button, Card, CardContent, Stack, Chip, IconButton,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField, MenuItem,
  Table, TableHead, TableRow, TableCell, TableBody, Paper, Alert, Tooltip,
  CircularProgress,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import RefreshIcon from '@mui/icons-material/Refresh';
import DeleteIcon from '@mui/icons-material/Delete';
import PlayCircleIcon from '@mui/icons-material/PlayCircle';
import WifiTetheringIcon from '@mui/icons-material/WifiTethering';
import { useDispatch, useSelector } from 'react-redux';
import {
  fetchConnectors, createConnector, testConnection, scanConnector,
  deleteConnector, clearTestResult, clearScanResult, testExistingConnector,
} from '../../redux/slices/connectorSlice';
import Loader from '../../components/Loader';

const CONNECTOR_TYPES = [
  { value: 'mysql', label: 'MySQL' },
  { value: 'mssql', label: 'MSSQL' },
  { value: 'azure_adf', label: 'Azure Data Factory' },
  { value: 'databricks', label: 'Databricks' },
  { value: 'github', label: 'GitHub' },
];

const TYPE_FIELDS = {
  mysql: [
    { key: 'host', label: 'Host', required: true },
    { key: 'port', label: 'Port', required: true, defaultValue: '3306' },
    { key: 'username', label: 'Username', required: true },
    { key: 'password', label: 'Password', required: true, secret: true },
    { key: 'database', label: 'Database Name', required: true },
  ],
  mssql: [
    { key: 'server', label: 'Server', required: true },
    { key: 'port', label: 'Port', required: true, defaultValue: '1433' },
    { key: 'username', label: 'Username', required: true },
    { key: 'password', label: 'Password', required: true, secret: true },
    { key: 'database', label: 'Database', required: true },
  ],
  azure_adf: [
    { key: 'subscription_id', label: 'Subscription ID', required: true },
    { key: 'tenant_id', label: 'Tenant ID', required: true },
    { key: 'client_id', label: 'Client ID', required: true },
    { key: 'client_secret', label: 'Client Secret', required: true, secret: true },
    { key: 'resource_group', label: 'Resource Group Name', required: true },
    { key: 'factory_name', label: 'ADF Factory Name', required: true },
  ],
  databricks: [
    { key: 'workspace_url', label: 'Workspace URL', required: true, placeholder: 'https://adb-xxx.azuredatabricks.net' },
    { key: 'token', label: 'Personal Access Token', required: true, secret: true },
    { key: 'cluster_id', label: 'Cluster ID', required: false },
  ],
  github: [
    { key: 'repository_url', label: 'Repository URL', required: true, placeholder: 'https://github.com/owner/repo' },
    { key: 'token', label: 'Token', required: true, secret: true },
  ],
};

const Connectors = () => {
  const dispatch = useDispatch();
  const { list, loading, error, testResult, scanResult, testLoading } =
    useSelector((s) => s.connectors);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState('');
  const [type, setType] = useState('mysql');
  const [config, setConfig] = useState({});
  const [savingError, setSavingError] = useState(null);
  const [runningTest, setRunningTest] = useState({});
  const [runningScan, setRunningScan] = useState({});

  useEffect(() => {
    dispatch(fetchConnectors());
  }, [dispatch]);

  useEffect(() => {
    const defaults = {};
    (TYPE_FIELDS[type] || []).forEach((f) => {
      if (f.defaultValue !== undefined) defaults[f.key] = f.defaultValue;
    });
    setConfig(defaults);
    dispatch(clearTestResult());
  }, [type, dispatch]);

  const openDialog = () => {
    setName('');
    setType('mysql');
    setConfig({});
    setSavingError(null);
    dispatch(clearTestResult());
    setDialogOpen(true);
  };

  const closeDialog = () => {
    setDialogOpen(false);
    dispatch(clearTestResult());
  };

  const updateField = (key, val) => setConfig((c) => ({ ...c, [key]: val }));

  const handleTestNew = async () => {
    setSavingError(null);
    await dispatch(testConnection({ type, config }));
  };

  const handleSave = async () => {
    setSavingError(null);
    if (!name.trim()) {
      setSavingError('Connector name is required');
      return;
    }
    const fields = TYPE_FIELDS[type] || [];
    for (const f of fields) {
      if (f.required && !config[f.key]) {
        setSavingError(`${f.label} is required`);
        return;
      }
    }
    const res = await dispatch(createConnector({ name, type, config }));
    if (createConnector.fulfilled.match(res)) {
      closeDialog();
      dispatch(fetchConnectors());
    } else {
      setSavingError(res.payload || 'Failed to create connector');
    }
  };

  const handleTestExisting = async (id) => {
    setRunningTest((s) => ({ ...s, [id]: true }));
    await dispatch(testExistingConnector(id));
    setRunningTest((s) => ({ ...s, [id]: false }));
    dispatch(fetchConnectors());
  };

  const handleScan = async (id) => {
    setRunningScan((s) => ({ ...s, [id]: true }));
    await dispatch(scanConnector(id));
    setRunningScan((s) => ({ ...s, [id]: false }));
    dispatch(fetchConnectors());
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this connector and all related datasets/alerts?')) return;
    await dispatch(deleteConnector(id));
    dispatch(fetchConnectors());
  };

  const fields = TYPE_FIELDS[type] || [];

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Typography variant="h5" sx={{ fontWeight: 700 }}>Connectors</Typography>
        <Stack direction="row" spacing={1}>
          <Button startIcon={<RefreshIcon />} onClick={() => dispatch(fetchConnectors())} variant="outlined">
            Refresh
          </Button>
          <Button startIcon={<AddIcon />} onClick={openDialog} variant="contained">
            Add Connector
          </Button>
        </Stack>
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {scanResult && (
        <Alert
          severity={scanResult.status === 'failed' ? 'error' : 'success'}
          sx={{ mb: 2 }}
          onClose={() => dispatch(clearScanResult())}
        >
          {scanResult.status === 'failed'
            ? `Scan failed: ${scanResult.error || 'unknown error'}`
            : `Scan complete. Datasets: ${scanResult.result?.datasets ?? 0}, schema drifts: ${scanResult.result?.drifts ?? 0}, PII datasets: ${scanResult.result?.pii_datasets ?? 0}.`}
        </Alert>
      )}

      <Card>
        <CardContent>
          {loading && (!list || list.length === 0) ? (
            <Loader label="Loading connectors..." />
          ) : !list || list.length === 0 ? (
            <Box sx={{ textAlign: 'center', py: 6 }}>
              <Typography color="text.secondary">
                No connectors yet. Click "Add Connector" to create your first one.
              </Typography>
            </Box>
          ) : (
            <Paper variant="outlined" sx={{ boxShadow: 'none' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell><strong>Name</strong></TableCell>
                    <TableCell><strong>Type</strong></TableCell>
                    <TableCell><strong>Status</strong></TableCell>
                    <TableCell><strong>Last Tested</strong></TableCell>
                    <TableCell><strong>Last Scanned</strong></TableCell>
                    <TableCell align="right"><strong>Actions</strong></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {list.map((c) => (
                    <TableRow key={c.id} hover>
                      <TableCell sx={{ fontWeight: 500 }}>{c.name}</TableCell>
                      <TableCell><Chip label={c.type} size="small" variant="outlined" /></TableCell>
                      <TableCell>
                        <Chip
                          label={c.status || 'unknown'}
                          size="small"
                          color={c.status === 'healthy' ? 'success' : c.status === 'unhealthy' || c.status === 'failed' ? 'error' : 'default'}
                        />
                      </TableCell>
                      <TableCell>
                        <Typography variant="caption">
                          {c.last_tested_at ? new Date(c.last_tested_at).toLocaleString() : '-'}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="caption">
                          {c.last_scanned_at ? new Date(c.last_scanned_at).toLocaleString() : '-'}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Tooltip title="Test Connection">
                          <span>
                            <IconButton size="small" onClick={() => handleTestExisting(c.id)} disabled={runningTest[c.id]}>
                              {runningTest[c.id] ? <CircularProgress size={16} /> : <WifiTetheringIcon fontSize="small" />}
                            </IconButton>
                          </span>
                        </Tooltip>
                        <Tooltip title="Run Scan">
                          <span>
                            <IconButton size="small" color="primary" onClick={() => handleScan(c.id)} disabled={runningScan[c.id]}>
                              {runningScan[c.id] ? <CircularProgress size={16} /> : <PlayCircleIcon fontSize="small" />}
                            </IconButton>
                          </span>
                        </Tooltip>
                        <Tooltip title="Delete">
                          <IconButton size="small" color="error" onClick={() => handleDelete(c.id)}>
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Paper>
          )}
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onClose={closeDialog} maxWidth="sm" fullWidth>
        <DialogTitle>Add Connector</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {savingError && <Alert severity="error">{savingError}</Alert>}
            <TextField
              label="Connector Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              fullWidth
              required
            />
            <TextField
              select
              label="Connector Type"
              value={type}
              onChange={(e) => setType(e.target.value)}
              fullWidth
            >
              {CONNECTOR_TYPES.map((t) => (
                <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>
              ))}
            </TextField>
            {fields.map((f) => (
              <TextField
                key={f.key}
                label={f.label + (f.required ? ' *' : '')}
                value={config[f.key] || ''}
                onChange={(e) => updateField(f.key, e.target.value)}
                type={f.secret ? 'password' : 'text'}
                placeholder={f.placeholder || ''}
                fullWidth
              />
            ))}
            {testResult && (
              <Alert severity={testResult.ok ? 'success' : 'error'}>
                {testResult.ok
                  ? (testResult.details?.version || 'Connection successful')
                  : (testResult.error || testResult.message || 'Connection failed')}
              </Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog}>Cancel</Button>
          <Button
            onClick={handleTestNew}
            disabled={testLoading}
            startIcon={testLoading ? <CircularProgress size={16} /> : <WifiTetheringIcon />}
          >
            Test Connection
          </Button>
          <Button onClick={handleSave} variant="contained" disabled={loading}>
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Connectors;
