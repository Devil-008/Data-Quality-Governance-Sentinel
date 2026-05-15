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
    dispatch(clearTestResult());
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

    let res;
    if (editMode) {
      res = await dispatch(
        updateConnector({ id: editingId, name, type, config }),
      );
    } else {
      res = await dispatch(createConnector({ name, type, config }));
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

      <Dialog open={dialogOpen} onClose={closeDialog} maxWidth="sm" fullWidth>
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
              <Alert severity={testResult.ok ? "success" : "error"}>
                {testResult.ok
                  ? testResult.details?.version || "Connection successful"
                  : testResult.error ||
                    testResult.message ||
                    "Connection failed"}
              </Alert>
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
    </Box>
  );
};

export default Connectors;
