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
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });

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

  const handleSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    } else if (sortConfig.key === key && sortConfig.direction === 'desc') {
      key = null;
      direction = 'asc';
    }
    setSortConfig({ key, direction });
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
      d.dataset_name?.toLowerCase().includes(search) ||
      d.dataset_type?.toLowerCase().includes(search) ||
      d.connector_name?.toLowerCase().includes(search)
    );
  });

  const sortedDatasets = [...searchedDatasets].sort((a, b) => {
    if (!sortConfig.key) return 0;
    
    const valA = a[sortConfig.key] ? a[sortConfig.key].toString().toLowerCase() : "";
    const valB = b[sortConfig.key] ? b[sortConfig.key].toString().toLowerCase() : "";

    if (valA < valB) {
      return sortConfig.direction === 'asc' ? -1 : 1;
    }
    if (valA > valB) {
      return sortConfig.direction === 'asc' ? 1 : -1;
    }
    return 0;
  });

  const startIndex = (page - 1) * ITEMS_PER_PAGE;

  const paginatedDatasets = sortedDatasets.slice(
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
        <Typography variant="h5" sx={{ fontWeight: 700 }}>
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
          {/* <TextField
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
          </TextField> */}
          <Button
            startIcon={<RefreshIcon />}
            onClick={() => applyFilters(filters)}
            variant="outlined"
          ></Button>
        </Stack>
      </Stack>

      <Card>
        <CardContent>
          {loading && (!allDatasets || allDatasets.length === 0) ? (
            <Loader label="Loading datasets..." />
          ) : (
            <>
              <DatasetTable
                datasets={paginatedDatasets}
                onRowClick={openProfile}
                sortConfig={sortConfig}
                onSort={handleSort}
              />
              {sortedDatasets.length > ITEMS_PER_PAGE && (
                <Box sx={{ display: "flex", justifyContent: "center", mt: 3 }}>
                  <Pagination
                    count={Math.ceil(sortedDatasets.length / ITEMS_PER_PAGE)}
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
                    {/* <Chip
                      label={`Rows: ${profile.dataset.row_count != null && profile.dataset.row_count >= 0 ? profile.dataset.row_count : "-"}`}
                      size="small"
                    />
                    <Chip
                      label={`Columns: ${profile.dataset.column_count ?? (profile.columns?.length || 0)}`}
                      size="small"
                    /> */}
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

              {(() => {
                let aiAnalysis = null;
                if (profile.dataset.ai_analysis_json) {
                  try {
                    aiAnalysis = JSON.parse(profile.dataset.ai_analysis_json);
                  } catch (e) {
                    console.error("Failed to parse ai_analysis_json", e);
                  }
                }
                const llm = aiAnalysis?.llm;
                const python = aiAnalysis?.python;

                if (!llm && !python) {
                  return (
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
                          <span role="img" aria-label="sparkles">✨</span> Overall Summary
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          No  analysis data available. Run Quality and PII checks to generate an summary.
                        </Typography>
                      </CardContent>
                    </Card>
                  );
                }

                return (
                  <Card variant="outlined" sx={{ mb: 3, bgcolor: "#f8f9fa" }}>
                    <CardContent>
                      <Typography
                        variant="subtitle2"
                        sx={{
                          fontWeight: 600,
                          mb: 2,
                          display: "flex",
                          alignItems: "center",
                          gap: 1,
                        }}
                      >
                        <span role="img" aria-label="sparkles">✨</span>Analysis Summary
                      </Typography>
                      
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                          Contextual Summary
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {llm?.contextual_summary || "N/A"}
                        </Typography>
                      </Box>

                      <Box sx={{ mb: 2 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                          Technical Summary
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {llm?.technical_summary || "N/A"}
                        </Typography>
                      </Box>

                      <Box sx={{ mb: 2 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                          Differences
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {llm?.differences || "N/A"}
                        </Typography>
                      </Box>

                      {llm?.recommendations && llm.recommendations.length > 0 && (
                        <Box sx={{ mb: 2 }}>
                          <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                            Recommendations
                          </Typography>
                          <Box component="ul" sx={{ m: 0, pl: 2 }}>
                            {llm.recommendations.map((rec, idx) => (
                              <Typography component="li" variant="body2" color="text.secondary" key={idx}>
                                {rec}
                              </Typography>
                            ))}
                          </Box>
                        </Box>
                      )}


                      {/* <Stack direction="row" spacing={3} sx={{ mb: 2 }}>
                        <Box>
                          <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                            Rules Passed
                          </Typography>
                          <Typography variant="body2" color="success.main">
                            {llm?.rules_passed || 0}
                          </Typography>
                        </Box>
                        <Box>
                          <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                            Rules Failed
                          </Typography>
                          <Typography variant="body2" color="error.main">
                            {llm?.rules_failed || 0}
                          </Typography>
                        </Box>
                        <Box>
                          <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                            Severity
                          </Typography>
                          <Chip 
                            label={llm?.severity ? llm.severity.toUpperCase() : "N/A"} 
                            size="small" 
                            color={llm?.severity === 'critical' ? 'error' : llm?.severity === 'high' ? 'warning' : 'default'} 
                          />
                        </Box>
                        <Box>
                          <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                            Rulebook Used
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            {llm?.rulebook_used || "N/A"}
                          </Typography>
                        </Box>
                      </Stack> */}


                    </CardContent>
                  </Card>
                );
              })()}
            </Box>
          )}
        </Box>
      </Drawer>
    </Box>
  );
};

export default Datasets;
