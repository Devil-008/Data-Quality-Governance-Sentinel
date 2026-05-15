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
  TableContainer,
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
            onClick={() => dispatch(fetchDatasets(filters))}
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
              {/* Header Info */}
              <Box sx={{ mb: 3 }}>
                <Typography variant="h5" sx={{ fontWeight: 700, color: "primary.main" }}>
                  {profile.dataset.dataset_name}
                </Typography>
                <Typography variant="subtitle2" color="text.secondary">
                  Source: {profile.dataset.connector_name} · Type: {profile.dataset.dataset_type}
                </Typography>
                <Typography variant="h6" sx={{ mt: 1, fontWeight: 700 }}>
                  Data Quality Score: {profile.dataset.quality_score ?? 0}%
                </Typography>
              </Box>

              {(() => {
                const llm = profile.llm_report || {};
                const python = profile.python_result || {};

                const getBarColor = (pct) => {
                  if (pct == null) return "grey.300";
                  if (pct < 33) return "#2e7d32"; // Green
                  if (pct < 66) return "#ed6c02"; // Amber
                  return "#d32f2f"; // Red
                };

                const renderBar = (label, pct) => (
                  <Box sx={{ mb: 2 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {label}
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 700, color: getBarColor(pct) }}>
                        {pct != null ? `${pct}%` : "N/A"}
                      </Typography>
                    </Box>
                    <Box sx={{ height: 8, width: '100%', bgcolor: 'grey.200', borderRadius: 4, overflow: 'hidden' }}>
                      <Box sx={{ height: '100%', width: `${pct ?? 0}%`, bgcolor: getBarColor(pct), transition: 'width 0.5s ease' }} />
                    </Box>
                  </Box>
                );

                return (
                  <Box>
                    {/* Metrics Section */}
                    <Card variant="outlined" sx={{ mb: 3, p: 2 }}>
                      {renderBar("Missing Data", llm.missing_data_pct)}
                      {renderBar("Junk Data (Incorrect Format)", llm.junk_data_pct)}
                      {renderBar("Outliers", llm.outlier_pct)}
                    </Card>

                    {/* Trend Section */}
                    <Box sx={{ mb: 3 }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <span role="img" aria-label="chart">📈</span> Trend Analysis
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ p: 2, bgcolor: 'grey.50', borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
                        {llm.trend || "No prior runs to compute deviation."}
                      </Typography>
                    </Box>

                    {/* Summary Section */}
                    <Box sx={{ mb: 3 }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                        Summary
                      </Typography>
                      
                      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                        Technical Context
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                        {llm.technical_summary || "N/A"}
                      </Typography>

                      <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                        Metadata Overview
                      </Typography>
                      <TableContainer component={Paper} variant="outlined" sx={{ mb: 2, boxShadow: 'none' }}>
                        <Table size="small">
                          <TableHead sx={{ bgcolor: 'grey.50' }}>
                            <TableRow>
                              <TableCell sx={{ fontWeight: 700 }}>Property</TableCell>
                              <TableCell sx={{ fontWeight: 700 }}>Value</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            <TableRow>
                              <TableCell sx={{ fontWeight: 600 }}>Table/Dataset Name</TableCell>
                              <TableCell>{profile.dataset.dataset_name}</TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell sx={{ fontWeight: 600 }}>Schema</TableCell>
                              <TableCell>{profile.dataset.schema_name || "N/A"}</TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell sx={{ fontWeight: 600 }}>Connector Type</TableCell>
                              <TableCell>{profile.dataset.connector_type || "N/A"}</TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell sx={{ fontWeight: 600 }}>Row Count</TableCell>
                              <TableCell>{profile.dataset.row_count ?? "N/A"}</TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell sx={{ fontWeight: 600 }}>Column Count</TableCell>
                              <TableCell>{profile.dataset.column_count ?? (profile.columns?.length || 0)}</TableCell>
                            </TableRow>
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </Box>

                    {/* LLM Based Sections */}
                    <Stack spacing={3}>
                      <Box>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                          Contextual Summary
                        </Typography>
                        <Typography variant="body2" color="text.secondary" sx={{ p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                          {llm.contextual_summary || "N/A"}
                        </Typography>
                      </Box>

                      <Box>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                          PII Data Inspection
                        </Typography>
                        <Typography variant="body2" color="text.secondary" sx={{ p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                          {llm.pii_inspection || "No PII patterns detected."}
                        </Typography>
                      </Box>

                      <Box>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                          Differences / Baseline Comparison
                        </Typography>
                        <Typography variant="body2" color="text.secondary" sx={{ p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                          {llm.differences || "This is the first recorded run; no baseline exists."}
                        </Typography>
                      </Box>

                      {llm.recommendations && llm.recommendations.length > 0 && (
                        <Box>
                          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                            Recommendations
                          </Typography>
                          <Box sx={{ p: 2, bgcolor: 'primary.50', borderRadius: 1, border: '1px solid', borderColor: 'primary.100' }}>
                            <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
                              {llm.recommendations.map((rec, idx) => (
                                <li key={idx}>
                                  <Typography variant="body2" color="text.primary">
                                    {rec}
                                  </Typography>
                                </li>
                              ))}
                            </ul>
                          </Box>
                        </Box>
                      )}
                    </Stack>
                  </Box>
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
