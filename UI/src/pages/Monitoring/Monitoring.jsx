import React, { useEffect, useState } from "react";
import {
  Box,
  Typography,
  Card,
  CardContent,
  Button,
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
  Grid,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import RefreshIcon from "@mui/icons-material/Refresh";
import DeleteIcon from "@mui/icons-material/Delete";
import PlayCircleIcon from "@mui/icons-material/PlayCircle";
import { useDispatch, useSelector } from "react-redux";
import {
  fetchJobs,
  fetchRuns,
  createJob,
  deleteJob,
} from "../../redux/slices/monitoringSlice";
import {
  fetchConnectors,
  scanConnector,
} from "../../redux/slices/connectorSlice";
import Loader from "../../components/Loader";

const JOB_TYPES = [
  { value: "scan", label: "Scan (full discovery + drift + PII)" },
  { value: "quality", label: "Quality (per dataset)" },
  { value: "schema_drift", label: "Schema Drift" },
  { value: "pii", label: "PII Scan" },
  { value: "cloud", label: "Cloud Health" },
];

const INTERVALS = [5, 15, 30, 60, 180, 360, 720, 1440];

const Monitoring = () => {
  const dispatch = useDispatch();
  const { jobs, runs, loading, error } = useSelector((s) => s.monitoring);
  const connectors = useSelector((s) => s.connectors.list);

  const [searchTerm, setSearchTerm] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({
    connector_id: "",
    job_type: "scan",
    interval_minutes: 60,
    enabled: true,
  });
  const [formError, setFormError] = useState(null);

  useEffect(() => {
    // API calls removed
  }, [dispatch]);

  const refresh = () => {
    // API calls removed
  };

  const openDialog = () => {
    setForm({
      connector_id: "",
      job_type: "scan",
      interval_minutes: 60,
      enabled: true,
    });
    setFormError(null);
    setDialogOpen(true);
  };

  const handleSave = async () => {
    setFormError(null);
    if (!form.connector_id) {
      setFormError("Connector is required");
      return;
    }
    // API calls removed
    setDialogOpen(false);
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this monitoring job?")) return;
    // API calls removed
  };

  const handleTriggerScan = async (connectorId) => {
    // API calls removed
    refresh();
  };

  const filteredJobs = jobs.filter(j => 
    j.connector_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    j.job_type?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const filteredRuns = runs.filter(r => 
    r.connector_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    r.dataset_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    r.status?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    r.run_type?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    r.message?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <Box>
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{ mb: 3 }}
      >
        <Typography variant="h5" sx={{ fontWeight: 700 }}>
          Monitoring
        </Typography>
        <Stack direction="row" spacing={1}>
          <TextField
            label="Search"
            size="small"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            sx={{ flex: 1, maxWidth: 200 }}
          />
          {/* <Button startIcon={<AddIcon />} onClick={openDialog} variant="contained">New Job</Button> */}
          <Button
            startIcon={<RefreshIcon />}
            onClick={refresh}
            variant="outlined"
          ></Button>
        </Stack>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Grid container spacing={2}>
        {/* <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
                Scheduled Jobs ({filteredJobs.length})
              </Typography>
              {loading && jobs.length === 0 ? (
                <Loader label="Loading jobs..." />
              ) : filteredJobs.length === 0 ? (
                <Box sx={{ py: 4, textAlign: 'center' }}>
                  <Typography color="text.secondary">
                    {searchTerm ? "No matching jobs found." : "No scheduled jobs yet."}
                  </Typography>
                </Box>
              ) : (
                <Paper variant="outlined" sx={{ boxShadow: 'none' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell><strong>Connector</strong></TableCell>
                        <TableCell><strong>Type</strong></TableCell>
                        <TableCell><strong>Interval (min)</strong></TableCell>
                        <TableCell><strong>Enabled</strong></TableCell>
                        <TableCell><strong>Last Run</strong></TableCell>
                        <TableCell><strong>Next Run</strong></TableCell>
                        <TableCell align="right"><strong>Actions</strong></TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {filteredJobs.map((j) => (
                        <TableRow key={j.id} hover>
                          <TableCell>{j.connector_name}</TableCell>
                          <TableCell><Chip label={j.job_type} size="small" variant="outlined" /></TableCell>
                          <TableCell>{j.interval_minutes}</TableCell>
                          <TableCell>
                            <Chip label={j.enabled ? 'Yes' : 'No'} size="small" color={j.enabled ? 'success' : 'default'} />
                          </TableCell>
                          <TableCell>
                            <Typography variant="caption">
                              {j.last_run_at ? new Date(j.last_run_at).toLocaleString() : '-'}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Typography variant="caption">
                              {j.next_run_at ? new Date(j.next_run_at).toLocaleString() : '-'}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Tooltip title="Trigger Scan Now">
                              <IconButton size="small" color="primary" onClick={() => handleTriggerScan(j.connector_id)}>
                                <PlayCircleIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Delete Job">
                              <IconButton size="small" color="error" onClick={() => handleDelete(j.id)}>
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
        </Grid> */}

        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
                Recent Monitoring Runs ({filteredRuns.length})
              </Typography>
              {filteredRuns.length === 0 ? (
                <Box sx={{ py: 4, textAlign: "center" }}>
                  <Typography color="text.secondary">
                    {searchTerm ? "No matching runs found." : "No runs yet. Trigger a scan from the Connectors page or create a job."}
                  </Typography>
                </Box>
              ) : (
                <Paper variant="outlined" sx={{ boxShadow: "none" }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>
                          <strong>Type</strong>
                        </TableCell>
                        <TableCell>
                          <strong>Connector</strong>
                        </TableCell>
                        <TableCell>
                          <strong>Dataset</strong>
                        </TableCell>
                        <TableCell>
                          <strong>Status</strong>
                        </TableCell>
                        <TableCell>
                          <strong>Started</strong>
                        </TableCell>
                        <TableCell>
                          <strong>Finished</strong>
                        </TableCell>
                        <TableCell>
                          <strong>Message</strong>
                        </TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {filteredRuns.map((r) => (
                        <TableRow key={r.id} hover>
                          <TableCell>
                            <Chip label={r.run_type} size="small" />
                          </TableCell>
                          <TableCell>{r.connector_name || "-"}</TableCell>
                          <TableCell>{r.dataset_name || "-"}</TableCell>
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
                          <TableCell>
                            <Typography variant="caption">
                              {r.finished_at
                                ? new Date(r.finished_at).toLocaleString()
                                : "-"}
                            </Typography>
                          </TableCell>
                          <TableCell sx={{ maxWidth: 280 }}>
                            <Typography
                              variant="caption"
                              sx={{
                                display: "-webkit-box",
                                WebkitLineClamp: 2,
                                WebkitBoxOrient: "vertical",
                                overflow: "hidden",
                              }}
                            >
                              {r.message || "-"}
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

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>New Monitoring Job</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {formError && <Alert severity="error">{formError}</Alert>}
            <TextField
              select
              label="Connector *"
              value={form.connector_id}
              onChange={(e) =>
                setForm((f) => ({ ...f, connector_id: e.target.value }))
              }
              fullWidth
            >
              <MenuItem value="">— Select —</MenuItem>
              {connectors.map((c) => (
                <MenuItem key={c.id} value={c.id}>
                  {c.name} ({c.type})
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Job Type"
              value={form.job_type}
              onChange={(e) =>
                setForm((f) => ({ ...f, job_type: e.target.value }))
              }
              fullWidth
            >
              {JOB_TYPES.map((j) => (
                <MenuItem key={j.value} value={j.value}>
                  {j.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Interval (minutes)"
              value={form.interval_minutes}
              onChange={(e) =>
                setForm((f) => ({ ...f, interval_minutes: e.target.value }))
              }
              fullWidth
            >
              {INTERVALS.map((m) => (
                <MenuItem key={m} value={m}>
                  {m}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Enabled"
              value={form.enabled ? "1" : "0"}
              onChange={(e) =>
                setForm((f) => ({ ...f, enabled: e.target.value === "1" }))
              }
              fullWidth
            >
              <MenuItem value="1">Yes</MenuItem>
              <MenuItem value="0">No</MenuItem>
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleSave} variant="contained">
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Monitoring;
