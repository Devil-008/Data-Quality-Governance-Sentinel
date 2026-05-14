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
  Divider,
  Chip,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  Paper,
  Alert,
  CircularProgress,
  Switch,
  FormControlLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Pagination,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import CloseIcon from "@mui/icons-material/Close";
import RuleIcon from "@mui/icons-material/Rule";
import PrivacyTipIcon from "@mui/icons-material/PrivacyTip";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { useDispatch, useSelector } from "react-redux";
import {
  fetchDatasets,
  fetchDatasetProfile,
  runQualityCheck,
  runPiiScan,
  clearProfile,
  clearLastAction,
} from "../../redux/slices/datasetSlice";
import { fetchConnectors } from "../../redux/slices/connectorSlice";
import DatasetTable from "../../components/DatasetTable";
import Loader from "../../components/Loader";

const ITEMS_PER_PAGE = 10;

const Datasets = () => {
  const dispatch = useDispatch();
  const {
    list: allDatasets,
    loading,
    profile,
    lastAction,
  } = useSelector((s) => s.datasets);
  const connectors = useSelector((s) => s.connectors.list);
  const [filters, setFilters] = useState({ connector_id: "", q: "" });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [page, setPage] = useState(1);

  const applyFilters = (newFilters) => {
    const params = {};
    if (newFilters.connector_id) params.connector_id = newFilters.connector_id;
    if (newFilters.q) params.q = newFilters.q;
    dispatch(fetchDatasets(params));
    setPage(1);
  };

  const handleFilterChange = (key, value) => {
    const updatedFilters = { ...filters, [key]: value };
    setFilters(updatedFilters);
    // applyFilters(updatedFilters);
     if (key === "connector_id") {
    applyFilters(updatedFilters);
  }
  };

  useEffect(() => {
    dispatch(fetchConnectors());
    dispatch(fetchDatasets());
  }, [dispatch]);

  const handlePageChange = (event, value) => {
    setPage(value);
  };

  const openProfile = (d) => {
    dispatch(fetchDatasetProfile(d.id));
    setDrawerOpen(true);
  };

  const closeProfile = () => {
    setDrawerOpen(false);
    dispatch(clearProfile());
  };

  // const startIndex = (page - 1) * ITEMS_PER_PAGE;
  // const paginatedDatasets = allDatasets.slice(
  //   startIndex,
  //   startIndex + ITEMS_PER_PAGE,
  // );datasets

  const searchedDatasets = allDatasets.filter((d) => {
    const search = filters.q.toLowerCase();

    return (
      console.log(allDatasets),
      d.dataset_name?.toLowerCase().includes(search) ||
        d.schema_name?.toLowerCase().includes(search) ||
        d.connector_name?.toLowerCase().includes(search)
    );
  });

  const startIndex = (page - 1) * ITEMS_PER_PAGE;

  const paginatedDatasets = searchedDatasets.slice(
    startIndex,
    startIndex + ITEMS_PER_PAGE,
  );

  return (
    <Box> 
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{ mb: 3 }}
      >
        <Typography variant="h5" sx={{ fontWeight: 700, color: "text.primary" }}>
          Datasets
        </Typography>
        <Stack direction="row" spacing={1}>
          <TextField
            label="Search"
            size="small"
            value={filters.q}
            onChange={(e) => handleFilterChange("q", e.target.value)}
            sx={{ flex: 1, maxWidth: 200 }}
          />
          <Button
            startIcon={<RefreshIcon />}
            onClick={() => applyFilters(filters)}
            variant="outlined"
          ></Button>
        </Stack>
      </Stack>

      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Stack
            direction={{ xs: "column", md: "row" }}
            spacing={2}
            alignItems={{ md: "center" }}
          >
            <TextField
              select
              label="Connector"
              size="small"
              value={filters.connector_id}
              onChange={(e) =>
                handleFilterChange("connector_id", e.target.value)
              }
              sx={{ minWidth: 200 }}
            >
              <MenuItem value="">All</MenuItem>
              {connectors.map((c) => (
                <MenuItem key={c.id} value={c.id}>
                  {c.name} ({c.type})
                </MenuItem>
              ))}
            </TextField>
            {/* <TextField
              label="Search"
              size="small"
              value={filters.q}
              onChange={(e) => handleFilterChange('q', e.target.value)}
              sx={{ flex: 1, minWidth: 200 }}
            /> */}
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          {loading ? (
            <Loader label="Loading datasets..." />
          ) : (
            <>
              <DatasetTable
                datasets={paginatedDatasets}
                onRowClick={openProfile}
              />
              {/* {allDatasets.length > ITEMS_PER_PAGE && ( */}
              {searchedDatasets.length > ITEMS_PER_PAGE && (
                <Box sx={{ display: "flex", justifyContent: "center", mt: 3 }}>
                  <Pagination
                    // count={Math.ceil(allDatasets.length / ITEMS_PER_PAGE)}
                    count={Math.ceil(searchedDatasets.length / ITEMS_PER_PAGE)}
                    page={page}
                    onChange={handlePageChange}
                    color="primary"
                  />
                </Box>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <Drawer
        anchor="right"
        open={drawerOpen}
        onClose={closeProfile}
        PaperProps={{ sx: { width: { xs: "100%", md: 720 } } }}
      >
        <Box sx={{ p: 3 }}>
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            sx={{ mb: 2 }}
          >
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              Dataset Profile
            </Typography>
            <IconButton onClick={closeProfile}>
              <CloseIcon />
            </IconButton>
          </Stack>
          {!profile ? (
            <Loader label="Loading..." />
          ) : (
            <Box>
              <Card variant="outlined" sx={{ mb: 2 }}>
                <CardContent>
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    {profile.dataset.dataset_name}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {profile.dataset.connector_name} ·{" "}
                    {profile.dataset.schema_name || "-"} ·{" "}
                    {profile.dataset.dataset_type}
                  </Typography>
                  <Stack
                    direction="row"
                    spacing={1}
                    sx={{ mt: 1, flexWrap: "wrap", gap: 1 }}
                  >
                    <Chip
                      label={`Rows: ${profile.dataset.row_count != null && profile.dataset.row_count >= 0 ? profile.dataset.row_count : "-"}`}
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
                        color={
                          profile.dataset.quality_score >= 90
                            ? "success"
                            : profile.dataset.quality_score >= 70
                              ? "warning"
                              : "error"
                        }
                      />
                    )}
                    {profile.dataset.contains_pii ? (
                      <Chip
                        label={
                          profile.dataset.pii_categories
                            ? `PII: ${profile.dataset.pii_categories}`
                            : "PII"
                        }
                        size="small"
                        color="error"
                      />
                    ) : null}
                  </Stack>
                </CardContent>
              </Card>

              <Card variant="outlined" sx={{ mb: 2 }}>
                <CardContent>
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    Technical Summary
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {profile.dataset.connector_name} ·{" "}
                    {profile.dataset.schema_name || "-"} ·{" "}
                    {profile.dataset.dataset_type}
                  </Typography>
                  <Stack
                    direction="row"
                    spacing={1}
                    sx={{ mt: 1, flexWrap: "wrap", gap: 1 }}
                  >
                    <Chip
                      label={`Rows: ${profile.dataset.row_count != null && profile.dataset.row_count >= 0 ? profile.dataset.row_count : "-"}`}
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
                        color={
                          profile.dataset.quality_score >= 90
                            ? "success"
                            : profile.dataset.quality_score >= 70
                              ? "warning"
                              : "error"
                        }
                      />
                    )}
                    {profile.dataset.contains_pii ? (
                      <Chip
                        label={
                          profile.dataset.pii_categories
                            ? `PII: ${profile.dataset.pii_categories}`
                            : "PII"
                        }
                        size="small"
                        color="error"
                      />
                    ) : null}
                  </Stack>
                </CardContent>
              </Card>

              <Card variant="outlined" sx={{ mb: 2 }}>
                <CardContent>
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    Contextual Summary
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {profile.dataset.connector_name} ·{" "}
                    {profile.dataset.schema_name || "-"} ·{" "}
                    {profile.dataset.dataset_type}
                  </Typography>
                  <Stack
                    direction="row"
                    spacing={1}
                    sx={{ mt: 1, flexWrap: "wrap", gap: 1 }}
                  >
                    <Chip
                      label={`Rows: ${profile.dataset.row_count != null && profile.dataset.row_count >= 0 ? profile.dataset.row_count : "-"}`}
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
                        color={
                          profile.dataset.quality_score >= 90
                            ? "success"
                            : profile.dataset.quality_score >= 70
                              ? "warning"
                              : "error"
                        }
                      />
                    )}
                    {profile.dataset.contains_pii ? (
                      <Chip
                        label={
                          profile.dataset.pii_categories
                            ? `PII: ${profile.dataset.pii_categories}`
                            : "PII"
                        }
                        size="small"
                        color="error"
                      />
                    ) : null}
                  </Stack>
                </CardContent>
              </Card>
              <Card variant="outlined" sx={{ mb: 2 }}>
                <CardContent>
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    Different
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {profile.dataset.connector_name} ·{" "}
                    {profile.dataset.schema_name || "-"} ·{" "}
                    {profile.dataset.dataset_type}
                  </Typography>
                  <Stack
                    direction="row"
                    spacing={1}
                    sx={{ mt: 1, flexWrap: "wrap", gap: 1 }}
                  >
                    <Chip
                      label={`Rows: ${profile.dataset.row_count != null && profile.dataset.row_count >= 0 ? profile.dataset.row_count : "-"}`}
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
                        color={
                          profile.dataset.quality_score >= 90
                            ? "success"
                            : profile.dataset.quality_score >= 70
                              ? "warning"
                              : "error"
                        }
                      />
                    )}
                    {profile.dataset.contains_pii ? (
                      <Chip
                        label={
                          profile.dataset.pii_categories
                            ? `PII: ${profile.dataset.pii_categories}`
                            : "PII"
                        }
                        size="small"
                        color="error"
                      />
                    ) : null}
                  </Stack>
                </CardContent>
              </Card>

              <Card variant="outlined" sx={{ mb: 3, bgcolor: "#f8f9fa" }}>
                <CardContent>
                  <Typography
                    variant="subtitle2"
                    sx={{
                      fontWeight: 600,
                      mb: 1,
                      display: "flex",
                      alignItems: "center",
                      gap: 1,
                    }}
                  >
                    <span role="img" aria-label="sparkles">
                      ✨
                    </span>{" "}
                    Overall Summary
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {profile.dataset.quality_score != null ||
                    profile.dataset.contains_pii != null ? (
                      <>
                        <strong>Data Quality:</strong>{" "}
                        {profile.dataset.quality_score != null
                          ? `The dataset has a quality score of ${profile.dataset.quality_score}%. `
                          : "No quality data available. "}
                        <br />
                        <strong>PII:</strong>{" "}
                        {profile.dataset.contains_pii
                          ? `PII data was detected (${profile.dataset.pii_categories || "various categories"}). `
                          : "No PII data detected. "}
                        <br />
                        <br />
                        <em>Reasoning:</em> (LLM generated reasoning and summary
                        will appear here based on the column distributions and
                        PII matches...)
                      </>
                    ) : (
                      "Run Quality and PII checks to generate an AI summary."
                    )}
                  </Typography>
                </CardContent>
              </Card>
            </Box>
          )}
        </Box>
      </Drawer>
    </Box>
  );
};

export default Datasets;
