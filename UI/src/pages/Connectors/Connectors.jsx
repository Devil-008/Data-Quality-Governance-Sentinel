import React, { useEffect, useState } from "react";
import {
  Box,
  Typography,
  Button,
  Card,
  CardContent,
  Stack,
  Chip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  MenuItem,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  TableContainer,
  Paper,
  Alert,
  Tooltip,
  CircularProgress,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import RefreshIcon from "@mui/icons-material/Refresh";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import WifiTetheringIcon from "@mui/icons-material/WifiTethering";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { useDispatch, useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import {
  fetchConnectors,
  createConnector,
  testConnection,
  deleteConnector,
  updateConnector,
  clearTestResult,
  testExistingConnector,
} from "../../redux/slices/connectorSlice";
import Loader from "../../components/Loader";

const CONNECTOR_TYPES = [
  { value: "mysql", label: "MySQL" },
  { value: "mssql", label: "MSSQL" },
  { value: "azure_adf", label: "Azure Data Factory" },
  { value: "databricks", label: "Databricks" },
  { value: "github", label: "GitHub" },
];

const TYPE_FIELDS = {
  mysql: [
    { key: "host", label: "Host", required: true },
    { key: "port", label: "Port", required: true, defaultValue: "3306" },
    { key: "username", label: "Username", required: true },
    { key: "password", label: "Password", required: true, secret: true },
    { key: "database", label: "Database Name", required: false },
  ],
  mssql: [
    { key: "server", label: "Server", required: true },
    { key: "port", label: "Port", required: true, defaultValue: "1433" },
    { key: "username", label: "Username", required: true },
    { key: "password", label: "Password", required: true, secret: true },
    { key: "database", label: "Database", required: false },
  ],
  azure_adf: [
    { key: "subscription_id", label: "Subscription ID", required: true },
    { key: "tenant_id", label: "Tenant ID", required: true },
    { key: "client_id", label: "Client ID", required: true },
    {
      key: "client_secret",
      label: "Client Secret",
      required: true,
      secret: true,
    },
    { key: "resource_group", label: "Resource Group Name", required: true },
    { key: "factory_name", label: "ADF Factory Name", required: true },
  ],
  databricks: [
    {
      key: "workspace_url",
      label: "Workspace URL",
      required: true,
      placeholder: "https://adb-xxx.azuredatabricks.net",
    },
    {
      key: "token",
      label: "Personal Access Token",
      required: true,
      secret: true,
    },
    { key: "cluster_id", label: "Cluster ID", required: false },
  ],
  github: [
    {
      key: "repository_url",
      label: "Repository URL",
      required: true,
      placeholder: "https://github.com/owner/repo",
    },
    { key: "token", label: "Token", required: true, secret: true },
  ],
};

const Connectors = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { list, loading, error, testResult, testLoading } = useSelector(
    (s) => s.connectors,
  );

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [name, setName] = useState("");
  const [type, setType] = useState("mysql");
  const [config, setConfig] = useState({});
  const [savingError, setSavingError] = useState(null);
  const [runningTest, setRunningTest] = useState({});
  const [search, setSearch] = useState("");
  const [credDialogOpen, setCredDialogOpen] = useState(false);
  const [activeAsset, setActiveAsset] = useState(null);
  const [assetCreds, setAssetCreds] = useState({}); // { assetName: { field: value } }
  const fields = TYPE_FIELDS[type] || [];
  // const fields = TYPE_FIELDS[type] || [];

  useEffect(() => {
    dispatch(fetchConnectors());
  }, [dispatch]);

  useEffect(() => {
    const defaults = {};
    (TYPE_FIELDS[type] || []).forEach((f) => {
      if (f.defaultValue !== undefined) defaults[f.key] = f.defaultValue;
    });
    if (!editMode) {
      setConfig(defaults);
    }
    dispatch(clearTestResult());
  }, [type, dispatch, editMode]);

  const openAddDialog = () => {
    setEditMode(false);
    setEditingId(null);
    setName("");
    setType("mysql");
    setConfig({});
    setSavingError(null);
    dispatch(clearTestResult());
    setDialogOpen(true);
  };

  const openEditDialog = (connector) => {
    setEditMode(true);
    setEditingId(connector.id);
    setName(connector.name);
    setType(connector.type);
    setConfig(connector.config || {});
    setSavingError(null);
    dispatch(clearTestResult());
    setDialogOpen(true);
  };

  const closeDialog = () => {
    setDialogOpen(false);
    setActiveAsset(null);
    setCredDialogOpen(false);
    dispatch(clearTestResult());
  };

  const openCredDialog = (asset) => {
    setActiveAsset(asset);
    // Initialize with existing if any
    setAssetCreds(prev => ({
      ...prev,
      [asset.name]: prev[asset.name] || {}
    }));
    setCredDialogOpen(true);
  };

  const updateAssetCred = (field, val) => {
    setAssetCreds(prev => ({
      ...prev,
      [activeAsset.name]: {
        ...prev[activeAsset.name],
        [field]: val
      }
    }));
  };

  const updateField = (key, val) => setConfig((c) => ({ ...c, [key]: val }));

  const handleTestNew = async () => {
    setSavingError(null);
    await dispatch(testConnection({ type, config }));
  };
  const filteredConnectors = (list || []).filter((c) => {
    const q = search.trim().toLowerCase();

    return (
      String(c.name || "")
        .toLowerCase()
        .includes(q) ||
      String(c.type || "")
        .toLowerCase()
        .includes(q)
    );
  });

  const handleSave = async () => {
    setSavingError(null);
    if (!name.trim()) {
      setSavingError("Connector name is required");
      return;
    }
    const fields = TYPE_FIELDS[type] || [];
    for (const f of fields) {
      if (f.required && !config[f.key]) {
        setSavingError(`${f.label} is required`);
        return;
      }
    }

    const dataset_credentials = Object.entries(assetCreds).map(([name, creds]) => {
      // Find the original asset metadata from the preview
      const asset = testResult?.preview?.datasets?.find(d => d.name === name);
      if (!asset) return null;

      return {
        dataset_name: name,
        schema_name: asset.schema,
        dataset_type: asset.dataset_type || "dataset",
        source_system_type: asset.source_system_type,
        linked_service_name: asset.linked_service_name,
        connection_hint: asset.connection_hint || {},
        credentials: creds
      };
    }).filter(dc => dc && Object.keys(dc.credentials).length > 0);

    let res;
    if (editMode) {
      res = await dispatch(
        updateConnector({ id: editingId, name, type, config, dataset_credentials }),
      );
    } else {
      res = await dispatch(createConnector({ name, type, config, dataset_credentials }));
    }

    if (
      createConnector.fulfilled.match(res) ||
      updateConnector.fulfilled.match(res)
    ) {
      closeDialog();
      dispatch(fetchConnectors());
    } else {
      setSavingError(
        res.payload ||
          (editMode
            ? "Failed to update connector"
            : "Failed to create connector"),
      );
    }
  };

  const handleTestExisting = async (id) => {
    setRunningTest((s) => ({ ...s, [id]: true }));
    await dispatch(testExistingConnector(id));
    setRunningTest((s) => ({ ...s, [id]: false }));
    dispatch(fetchConnectors());
  };

  const handleDelete = async (id) => {
    if (
      !window.confirm("Delete this connector and all related datasets/alerts?")
    )
      return;
    await dispatch(deleteConnector(id));
    dispatch(fetchConnectors());
  };

  return (
    <Box>
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{ mb: 3 }}
      >
        <Typography variant="h5" sx={{ fontWeight: 700 }}>
          Connectors
        </Typography>
        <Stack direction="row" spacing={1}>
          <TextField
            label="Search name or type"
            size="small"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ flex: 1, maxWidth: 220 }}
          />
          
          <Button
            startIcon={<AddIcon />}
            onClick={openAddDialog}
            variant="contained"
          >
            Add Connector
          </Button>
          <Button
            startIcon={<RefreshIcon />}
            onClick={() => dispatch(fetchConnectors())}
            variant="outlined"
          ></Button>
        </Stack>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Card>
        <CardContent>
          {loading && (!list || list.length === 0) ? (
            <Loader label="Loading connectors..." />
          ) : !list || list.length === 0 ? (
            <Box sx={{ textAlign: "center", py: 6 }}>
              <Typography color="text.secondary">
                No connectors yet. Click "Add Connector" to create your first
                one.
              </Typography>
            </Box>
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
                      <strong>Last Tested</strong>
                    </TableCell>
                    <TableCell align="right">
                      <strong>Actions</strong>
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {filteredConnectors.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} align="center">
                        No connectors found
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredConnectors.map((c) => (
                      <TableRow key={c.id} hover>
                        <TableCell sx={{ fontWeight: 500 }}>{c.name}</TableCell>
                        <TableCell>
                          <Chip
                            label={c.type}
                            size="small"
                            variant="outlined"
                          />
                        </TableCell>
                        <TableCell>
                          <Chip
                            label={c.status || "unknown"}
                            size="small"
                            color={
                              c.status === "Connected"
                                ? "success"
                                : c.status === "Connection Failed"
                                  ? "error"
                                  : "default"
                            }
                          />
                        </TableCell>
                        <TableCell>
                          <Typography variant="caption">
                            {c.last_tested_at
                              ? new Date(c.last_tested_at).toLocaleString()
                              : "-"}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Tooltip title="Test Connection">
                            <span>
                              <IconButton
                                size="small"
                                onClick={() => handleTestExisting(c.id)}
                                disabled={runningTest[c.id]}
                              >
                                {runningTest[c.id] ? (
                                  <CircularProgress size={16} />
                                ) : (
                                  <WifiTetheringIcon fontSize="small" />
                                )}
                              </IconButton>
                            </span>
                          </Tooltip>
                          <Tooltip title="Edit">
                            <IconButton
                              size="small"
                              color="primary"
                              onClick={() => openEditDialog(c)}
                            >
                              <EditIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="Delete">
                            <IconButton
                              size="small"
                              color="error"
                              onClick={() => handleDelete(c.id)}
                            >
                              <DeleteIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </Paper>
          )}
        </CardContent>
      </Card>

      <Dialog 
        open={dialogOpen} 
        onClose={closeDialog} 
        maxWidth={testResult?.preview ? "md" : "sm"} 
        fullWidth
        PaperProps={{ sx: { bgcolor: "#ffffff" } }}
      >
        <DialogTitle>
          {editMode ? "Edit Connector" : "Add Connector"}
        </DialogTitle>
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
                <MenuItem key={t.value} value={t.value}>
                  {t.label}
                </MenuItem>
              ))}
            </TextField>
            {fields.map((f) => (
              <TextField
                key={f.key}
                label={f.label + (f.required ? " *" : "")}
                value={config[f.key] || ""}
                onChange={(e) => updateField(f.key, e.target.value)}
                type={f.secret ? "password" : "text"}
                placeholder={f.placeholder || ""}
                fullWidth
              />
            ))}
            {testResult && (
              <Box>
                <Alert severity={testResult.ok ? "success" : "error"} sx={{ mb: testResult.preview ? 2 : 0 }}>
                  {testResult.ok
                    ? testResult.details?.version || "Connection successful"
                    : testResult.error ||
                      testResult.message ||
                      "Connection failed"}
                </Alert>

                {testResult.ok && testResult.preview && (
                  <Box sx={{ mt: 1 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1, color: 'primary.main', display: 'flex', alignItems: 'center', gap: 1 }}>
                      <span role="img" aria-label="discovery">🔍</span> Discovery Preview
                    </Typography>
                    <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 250, overflow: 'auto', bgcolor: 'grey.50' }}>
                      <Table size="small" stickyHeader>
                        <TableHead>
                          <TableRow>
                            <TableCell sx={{ fontWeight: 700, bgcolor: 'grey.100', fontSize: '0.7rem' }}>Asset Name</TableCell>
                            <TableCell sx={{ fontWeight: 700, bgcolor: 'grey.100', fontSize: '0.7rem' }}>Type</TableCell>
                            <TableCell sx={{ fontWeight: 700, bgcolor: 'grey.100', fontSize: '0.7rem' }}>Source System</TableCell>
                            <TableCell sx={{ fontWeight: 700, bgcolor: 'grey.100', fontSize: '0.7rem' }}>Details</TableCell>
                            <TableCell sx={{ fontWeight: 700, bgcolor: 'grey.100', fontSize: '0.7rem' }} align="right">Action</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {(testResult.preview.datasets || []).map((d, i) => (
                            <TableRow key={`ds-${i}`} hover>
                              <TableCell sx={{ fontSize: '0.7rem', py: 0.5, fontWeight: 500 }}>{d.name}</TableCell>
                              <TableCell sx={{ fontSize: '0.7rem', py: 0.5 }}>
                                <Chip label={d.adf_dataset_type || d.dataset_type} size="small" variant="outlined" sx={{ height: 18, fontSize: '0.6rem', bgcolor: 'white' }} />
                              </TableCell>
                              <TableCell sx={{ fontSize: '0.7rem', py: 0.5 }}>{d.source_system_type || '-'}</TableCell>
                              <TableCell sx={{ fontSize: '0.65rem', py: 0.5, color: 'text.secondary' }}>
                                {(() => {
                                  const h = d.connection_hint || {};
                                  const tableName = h.table ? `${h.schema ? h.schema + '.' : ''}${h.table}` : null;
                                  const path = h.container ? `${h.container}${h.folder_path ? '/' + h.folder_path : ''}` : null;
                                  
                                  return (
                                    <Stack direction="row" alignItems="center" spacing={0.5}>
                                      <Typography variant="inherit" sx={{ fontWeight: tableName ? 600 : 400 }}>
                                        {tableName || path || h.host || '-'}
                                      </Typography>
                                      {d.columns && d.columns.length > 0 && (
                                        <Tooltip 
                                          arrow
                                          title={
                                            <Box sx={{ p: 0.5 }}>
                                              <Typography variant="caption" sx={{ fontWeight: 800, display: 'block', mb: 0.5, borderBottom: '1px solid rgba(255,255,255,0.2)', pb: 0.5 }}>
                                                Schema ({d.columns.length} Columns)
                                              </Typography>
                                              {d.columns.slice(0, 15).map((col, idx) => (
                                                <Typography key={idx} variant="caption" display="block" sx={{ fontSize: '0.65rem', lineHeight: 1.2 }}>
                                                  <span style={{ color: '#90caf9' }}>{col.name}</span>: <span style={{ opacity: 0.8 }}>{col.type}</span>
                                                </Typography>
                                              ))}
                                              {d.columns.length > 15 && (
                                                <Typography variant="caption" sx={{ fontStyle: 'italic', opacity: 0.7, mt: 0.5, display: 'block' }}>
                                                  + {d.columns.length - 15} more columns
                                                </Typography>
                                              )}
                                            </Box>
                                          }
                                        >
                                          <InfoOutlinedIcon sx={{ fontSize: '0.9rem', cursor: 'help', color: 'primary.main', ml: 0.5 }} />
                                        </Tooltip>
                                      )}
                                    </Stack>
                                  );
                                })()}
                              </TableCell>
                              <TableCell align="right" sx={{ py: 0.5 }}>
                                {d.needs_credentials && (
                                  <Button 
                                    size="small" 
                                    variant={assetCreds[d.name] && Object.keys(assetCreds[d.name]).length > 0 ? "contained" : "outlined"}
                                    color={assetCreds[d.name] && Object.keys(assetCreds[d.name]).length > 0 ? "success" : "primary"}
                                    onClick={() => openCredDialog(d)}
                                    sx={{ fontSize: '0.6rem', height: 20, px: 1, minWidth: 0 }}
                                  >
                                    {assetCreds[d.name] && Object.keys(assetCreds[d.name]).length > 0 ? "Configured" : "Setup"}
                                  </Button>
                                )}
                              </TableCell>
                            </TableRow>
                          ))}
                          {(testResult.preview.pipelines || []).map((p, i) => (
                            <TableRow key={`pl-${i}`} hover>
                              <TableCell sx={{ fontSize: '0.7rem', py: 0.5, fontWeight: 500 }}>{p.name}</TableCell>
                              <TableCell sx={{ fontSize: '0.7rem', py: 0.5 }}>
                                <Chip label="pipeline" color="info" size="small" sx={{ height: 18, fontSize: '0.6rem' }} />
                              </TableCell>
                              <TableCell sx={{ fontSize: '0.7rem', py: 0.5 }}>-</TableCell>
                              <TableCell sx={{ fontSize: '0.65rem', py: 0.5, color: 'text.secondary' }}>Pipeline Execution</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                    <Typography variant="caption" sx={{ mt: 1, display: 'block', color: 'text.secondary', fontStyle: 'italic' }}>
                      * Total { (testResult.preview.datasets?.length || 0) + (testResult.preview.pipelines?.length || 0) } items will be imported.
                    </Typography>
                  </Box>
                )}
              </Box>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog}>Cancel</Button>
          <Button
            onClick={handleTestNew}
            disabled={testLoading}
            startIcon={
              testLoading ? (
                <CircularProgress size={16} />
              ) : (
                <WifiTetheringIcon />
              )
            }
          >
            Test Connection
          </Button>
          <Button onClick={handleSave} variant="contained" disabled={loading}>
            Save
          </Button>
        </DialogActions>
      </Dialog>

      {/* Tier-2 Credential Sub-Dialog */}
      <Dialog 
        open={credDialogOpen} 
        onClose={() => setCredDialogOpen(false)} 
        maxWidth="xs" 
        fullWidth
        PaperProps={{ sx: { borderRadius: 2, boxShadow: 24 } }}
      >
        <DialogTitle sx={{ pb: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            Setup Credentials
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {activeAsset?.name} ({activeAsset?.source_system_type})
          </Typography>
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {activeAsset?.required_fields?.map((field) => (
              <TextField
                key={field}
                label={field.charAt(0).toUpperCase() + field.slice(1).replace('_', ' ')}
                fullWidth
                size="small"
                type={field.includes('password') || field.includes('key') || field.includes('token') || field.includes('secret') ? "password" : "text"}
                value={assetCreds[activeAsset.name]?.[field] || ""}
                onChange={(e) => updateAssetCred(field, e.target.value)}
              />
            ))}
            {(!activeAsset?.required_fields || activeAsset.required_fields.length === 0) && (
              <Typography variant="body2" color="text.secondary">
                No extra credentials required for this asset.
              </Typography>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCredDialogOpen(false)} size="small">Cancel</Button>
          <Button 
            onClick={() => setCredDialogOpen(false)} 
            variant="contained" 
            size="small"
            disabled={activeAsset?.required_fields?.some(f => !assetCreds[activeAsset.name]?.[f])}
          >
            Done
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Connectors;
