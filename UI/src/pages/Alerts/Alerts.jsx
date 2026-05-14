import React, { useEffect, useState } from "react";
import {
  Box,
  Typography,
  Card,
  CardContent,
  Stack,
  TextField,
  MenuItem,
  Button,
  Drawer,
  IconButton,
  Chip,
  Alert as MuiAlert,
  Divider,
  Paper,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  CircularProgress,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import CloseIcon from "@mui/icons-material/Close";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import VisibilityIcon from "@mui/icons-material/Visibility";
import PsychologyIcon from "@mui/icons-material/Psychology";
import { useDispatch, useSelector } from "react-redux";
import { useSearchParams } from "react-router-dom";
import {
  fetchAlerts,
  fetchAlertDetail,
  updateAlertStatus,
  clearDetail,
} from "../../redux/slices/alertSlice";
import AlertTable, {
  SEVERITY_COLOR,
  STATUS_COLOR,
} from "../../components/AlertTable";
import Loader from "../../components/Loader";

const SEVERITIES = ["", "critical", "high", "medium", "low", "info"];
const CATEGORIES = [
  "",
  "quality",
  "schema_drift",
  "pii",
  "governance",
  "pipeline",
  "cloud",
  "databricks",
];
const STATUSES = ["", "open", "acknowledged", "resolved"];

const Alerts = () => {
  const dispatch = useDispatch();
  const { list, loading, detail, detailLoading, error } = useSelector(
    (s) => s.alerts,
  );
  const [filters, setFilters] = useState({
    severity: "",
    category: "",
    status: "",
  });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [searchParams] = useSearchParams();

  const applyFilters = () => {
    // API calls removed
  };

  useEffect(() => {
    // API calls removed
    const id = searchParams.get("id");
    if (id) {
      setDrawerOpen(true);
    }
  }, [dispatch, searchParams]);

  const openDrawer = (a) => {
    setDrawerOpen(true);
  };

  const closeDrawer = () => {
    setDrawerOpen(false);
    dispatch(clearDetail());
  };

  const handleStatus = async (status) => {
    if (!detail) return;
    setUpdating(true);
    // API calls removed
    setUpdating(false);
    applyFilters();
  };

  return (
    <Box>
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{ mb: 3 }}
      >
        <Typography variant="h5" sx={{ fontWeight: 700, color: "text.primary" }}>
          Alerts
        </Typography>
        <Stack direction="row" spacing={1}>
          <TextField
            label="Search"
            size="small"
            sx={{ flex: 1, maxWidth: 200 }}
          />
          <Button
            startIcon={<RefreshIcon />}
            onClick={applyFilters}
            variant="outlined"
          ></Button>
        </Stack>
      </Stack>

      {error && (
        <MuiAlert severity="error" sx={{ mb: 2 }}>
          {error}
        </MuiAlert>
      )}

      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Stack
            direction={{ xs: "column", md: "row" }}
            spacing={2}
            alignItems={{ md: "center" }}
          >
            <TextField
              select
              label="Severity"
              size="small"
              value={filters.severity}
              onChange={(e) =>
                setFilters((f) => ({ ...f, severity: e.target.value }))
              }
              sx={{ minWidth: 160 }}
            >
              {SEVERITIES.map((s) => (
                <MenuItem key={s} value={s}>
                  {s === "" ? "All" : s}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Category"
              size="small"
              value={filters.category}
              onChange={(e) =>
                setFilters((f) => ({ ...f, category: e.target.value }))
              }
              sx={{ minWidth: 180 }}
            >
              {CATEGORIES.map((c) => (
                <MenuItem key={c} value={c}>
                  {c === "" ? "All" : c}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Status"
              size="small"
              value={filters.status}
              onChange={(e) =>
                setFilters((f) => ({ ...f, status: e.target.value }))
              }
              sx={{ minWidth: 160 }}
            >
              {STATUSES.map((s) => (
                <MenuItem key={s} value={s}>
                  {s === "" ? "All" : s}
                </MenuItem>
              ))}
            </TextField>
            <Button variant="contained" onClick={applyFilters}>
              Apply
            </Button>
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          {loading ? (
            <Loader label="Loading alerts..." />
          ) : (
            <AlertTable alerts={list} onRowClick={openDrawer} />
          )}
        </CardContent>
      </Card>

      <Drawer
        anchor="right"
        open={drawerOpen}
        onClose={closeDrawer}
        PaperProps={{ sx: { width: { xs: "100%", md: 680 } } }}
      >
        <Box sx={{ p: 3 }}>
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            sx={{ mb: 2 }}
          >
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              Alert Details
            </Typography>
            <IconButton onClick={closeDrawer}>
              <CloseIcon />
            </IconButton>
          </Stack>
          {detailLoading ? (
            <Loader label="Loading..." />
          ) : !detail ? (
            <Typography color="text.secondary">No alert selected.</Typography>
          ) : (
            <Box>
              <Stack
                direction="row"
                spacing={1}
                sx={{ mb: 2, flexWrap: "wrap", gap: 1 }}
              >
                <Chip
                  label={(detail.severity || "").toUpperCase()}
                  color={SEVERITY_COLOR[detail.severity] || "default"}
                  size="small"
                />
                <Chip label={detail.category} variant="outlined" size="small" />
                <Chip
                  label={detail.status}
                  color={STATUS_COLOR[detail.status] || "default"}
                  size="small"
                  variant="outlined"
                />
                {detail.connector_name && (
                  <Chip
                    label={`Connector: ${detail.connector_name}`}
                    size="small"
                    variant="outlined"
                  />
                )}
                {detail.dataset_name && (
                  <Chip
                    label={`Dataset: ${detail.dataset_name}`}
                    size="small"
                    variant="outlined"
                  />
                )}
              </Stack>

              <Typography variant="h6" sx={{ fontWeight: 600 }}>
                {detail.title}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Created:{" "}
                {detail.created_at
                  ? new Date(detail.created_at).toLocaleString()
                  : "-"}
                {detail.resolved_at &&
                  ` · Resolved: ${new Date(detail.resolved_at).toLocaleString()}`}
              </Typography>

              <Card variant="outlined" sx={{ mt: 2 }}>
                <CardContent>
                  <Typography
                    variant="subtitle2"
                    sx={{ fontWeight: 600, mb: 1 }}
                  >
                    Message
                  </Typography>
                  <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                    {detail.message}
                  </Typography>
                </CardContent>
              </Card>

              {detail.ai_summary ||
              detail.ai_root_cause ||
              detail.ai_impact ||
              detail.ai_recommendation ? (
                <Card
                  variant="outlined"
                  sx={{ mt: 2, borderColor: "primary.main" }}
                >
                  <CardContent>
                    <Stack
                      direction="row"
                      alignItems="center"
                      spacing={1}
                      sx={{ mb: 1 }}
                    >
                      <PsychologyIcon color="primary" />
                      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                        AI Analysis
                      </Typography>
                    </Stack>
                    {detail.ai_summary && (
                      <Box sx={{ mb: 1.5 }}>
                        <Typography
                          variant="caption"
                          sx={{
                            fontWeight: 600,
                            color: "text.secondary",
                            textTransform: "uppercase",
                          }}
                        >
                          Summary
                        </Typography>
                        <Typography variant="body2">
                          {detail.ai_summary}
                        </Typography>
                      </Box>
                    )}
                    {detail.ai_root_cause && (
                      <Box sx={{ mb: 1.5 }}>
                        <Typography
                          variant="caption"
                          sx={{
                            fontWeight: 600,
                            color: "text.secondary",
                            textTransform: "uppercase",
                          }}
                        >
                          Root Cause
                        </Typography>
                        <Typography variant="body2">
                          {detail.ai_root_cause}
                        </Typography>
                      </Box>
                    )}
                    {detail.ai_impact && (
                      <Box sx={{ mb: 1.5 }}>
                        <Typography
                          variant="caption"
                          sx={{
                            fontWeight: 600,
                            color: "text.secondary",
                            textTransform: "uppercase",
                          }}
                        >
                          Impact
                        </Typography>
                        <Typography variant="body2">
                          {detail.ai_impact}
                        </Typography>
                      </Box>
                    )}
                    {detail.ai_recommendation && (
                      <Box>
                        <Typography
                          variant="caption"
                          sx={{
                            fontWeight: 600,
                            color: "text.secondary",
                            textTransform: "uppercase",
                          }}
                        >
                          Recommendation
                        </Typography>
                        <Typography variant="body2">
                          {detail.ai_recommendation}
                        </Typography>
                      </Box>
                    )}
                  </CardContent>
                </Card>
              ) : (
                <MuiAlert severity="info" sx={{ mt: 2 }}>
                  No AI analysis available. Configure{" "}
                  <code>MISTRAL_API_KEY</code> in the backend
                  <code>.env</code> to enable AI-powered root cause and
                  recommendations.
                </MuiAlert>
              )}

              <Divider sx={{ my: 2 }} />

              <Stack direction="row" spacing={1}>
                <Button
                  variant="outlined"
                  disabled={updating || detail.status === "acknowledged"}
                  startIcon={
                    updating ? (
                      <CircularProgress size={16} />
                    ) : (
                      <VisibilityIcon />
                    )
                  }
                  onClick={() => handleStatus("acknowledged")}
                >
                  Acknowledge
                </Button>
                <Button
                  variant="contained"
                  color="success"
                  disabled={updating || detail.status === "resolved"}
                  startIcon={
                    updating ? (
                      <CircularProgress size={16} />
                    ) : (
                      <CheckCircleOutlineIcon />
                    )
                  }
                  onClick={() => handleStatus("resolved")}
                >
                  Resolve
                </Button>
                {detail.status !== "open" && (
                  <Button
                    variant="text"
                    disabled={updating}
                    onClick={() => handleStatus("open")}
                  >
                    Reopen
                  </Button>
                )}
              </Stack>
            </Box>
          )}
        </Box>
      </Drawer>
    </Box>
  );
};

export default Alerts;
