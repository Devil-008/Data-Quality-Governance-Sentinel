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
  Tooltip,
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
  const [sortConfig, setSortConfig] = useState({ key: null, direction: "asc" });

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
    let direction = "asc";
    if (sortConfig.key === key && sortConfig.direction === "asc") {
      direction = "desc";
    } else if (sortConfig.key === key && sortConfig.direction === "desc") {
      key = null;
      direction = "asc";
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

    const valA = a[sortConfig.key]
      ? a[sortConfig.key].toString().toLowerCase()
      : "";
    const valB = b[sortConfig.key]
      ? b[sortConfig.key].toString().toLowerCase()
      : "";

    if (valA < valB) {
      return sortConfig.direction === "asc" ? -1 : 1;
    }
    if (valA > valB) {
      return sortConfig.direction === "asc" ? 1 : -1;
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
          {loading ? (
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
        PaperProps={{
          sx: { width: { xs: "100%", md: 720 }, bgcolor: "#ffffff" },
        }}
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
                <Typography
                  variant="h5"
                  sx={{ fontWeight: 700, color: "primary.main" }}
                >
                  {profile.dataset.dataset_name}
                </Typography>
                <Typography variant="subtitle2" color="text.secondary">
                  Source: {profile.dataset.connector_name} · Type:{" "}
                  {profile.dataset.dataset_type}
                </Typography>
                <Typography variant="h6" sx={{ mt: 1, fontWeight: 700 }}>
                  Data Quality Score: {profile.dataset.quality_score ?? 0}%
                </Typography>
              </Box>

              {(() => {
                const llm = profile.llm_report || {};
                const python = profile.python_result || {};
                const isPipeline = profile.dataset.dataset_type === "pipeline";

                const getBarColor = (pct, isOutlier = false) => {
                  if (pct == null) return "grey.300";
                  if (isOutlier) {
                    if (pct === 0) return "#2e7d32"; // Green for 0 outliers
                    if (pct < 10) return "#ed6c02"; // Amber for few outliers
                    return "#d32f2f"; // Red for many outliers
                  }
                  if (pct < 33) return "#2e7d32"; // Green for low missing/junk
                  if (pct < 66) return "#ed6c02"; // Amber
                  return "#d32f2f"; // Red
                };

                const renderBar = (label, pct) => {
                  const isOutlier = label.toLowerCase().includes("outlier");
                  // For outliers, 0% means 100% health, 100% means 0% health
                  const displayPct = isOutlier
                    ? Math.max(0, 100 - (pct ?? 0))
                    : (pct ?? 0);
                  const color = getBarColor(pct, isOutlier);

                  return (
                    <Box sx={{ mb: 2 }}>
                      <Box
                        sx={{
                          display: "flex",
                          justifyContent: "space-between",
                          mb: 0.5,
                        }}
                      >
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {label}
                        </Typography>
                        <Typography
                          variant="body2"
                          sx={{ fontWeight: 700, color: color }}
                        >
                          {pct != null ? `${pct}%` : "N/A"}
                        </Typography>
                      </Box>
                      <Box
                        sx={{
                          height: 8,
                          width: "100%",
                          bgcolor: "grey.200",
                          borderRadius: 4,
                          overflow: "hidden",
                        }}
                      >
                        <Box
                          sx={{
                            height: "100%",
                            width: `${displayPct}%`,
                            bgcolor: color,
                            transition: "width 0.5s ease",
                          }}
                        />
                      </Box>
                    </Box>
                  );
                };

                return (
                  <Box>
                    {/* Metrics Section */}
                    <Card variant="outlined" sx={{ mb: 3, p: 2 }}>
                      {renderBar("Missing Data", llm.missing_data_pct)}
                      {renderBar(
                        "Junk Data (Incorrect Format)",
                        llm.junk_data_pct,
                      )}
                      {renderBar("Outliers", llm.outlier_pct)}
                    </Card>

                    {/* Trend Section */}
                    <Box sx={{ mb: 3 }}>
                      <Typography
                        variant="subtitle2"
                        sx={{
                          fontWeight: 700,
                          mb: 1,
                          display: "flex",
                          alignItems: "center",
                          gap: 1,
                        }}
                      >
                        <span role="img" aria-label="chart">
                          📈
                        </span>{" "}
                        Trend Analysis
                      </Typography>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{
                          p: 2,
                          bgcolor: "grey.50",
                          borderRadius: 1,
                          border: "1px solid",
                          borderColor: "divider",
                        }}
                      >
                        {llm.trend || "No prior runs to compute deviation."}
                      </Typography>
                    </Box>

                    {/* Summary Section */}
                    <Box sx={{ mb: 3 }}>
                      <Typography
                        variant="subtitle2"
                        sx={{ fontWeight: 700, mb: 1 }}
                      >
                        Summary
                      </Typography>

                      <Typography
                        variant="body2"
                        sx={{ fontWeight: 600, mb: 0.5 }}
                      >
                        Technical Summary
                      </Typography>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{
                          mb: 2,
                          p: 1.5,
                          bgcolor: "grey.50",
                          borderRadius: 1,
                          border: "1px border-left",
                          borderLeft: "4px solid",
                          borderLeftColor: "primary.main",
                        }}
                      >
                        {python.technical_summary ||
                          llm.technical_summary ||
                          "No technical summary available."}
                      </Typography>

                      <Typography
                        variant="body2"
                        sx={{ fontWeight: 600, mb: 0.5 }}
                      >
                        Trend Analysis
                      </Typography>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{ mb: 2 }}
                      >
                        {llm.trend || "N/A"}
                      </Typography>

                      <Typography
                        variant="body2"
                        sx={{ fontWeight: 600, mb: 1 }}
                      >
                        Metadata Overview
                      </Typography>
                      <TableContainer
                        component={Paper}
                        variant="outlined"
                        sx={{ mb: 2, boxShadow: "none" }}
                      >
                        <Table size="small">
                          <TableHead sx={{ bgcolor: "grey.50" }}>
                            <TableRow>
                              <TableCell sx={{ fontWeight: 700 }}>
                                Property
                              </TableCell>
                              <TableCell sx={{ fontWeight: 700 }}>
                                Value
                              </TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            <TableRow>
                              <TableCell sx={{ fontWeight: 600 }}>
                                Table/Dataset Name
                              </TableCell>
                              <TableCell>
                                {profile.dataset.dataset_name}
                              </TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell sx={{ fontWeight: 600 }}>
                                Schema
                              </TableCell>
                              <TableCell>
                                {profile.dataset.schema_name || "N/A"}
                              </TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell sx={{ fontWeight: 600 }}>
                                Connector Type
                              </TableCell>
                              <TableCell>
                                {profile.dataset.connector_type || "N/A"}
                              </TableCell>
                            </TableRow>
                            {profile.dataset.linked_service_name && (
                              <TableRow>
                                <TableCell sx={{ fontWeight: 600 }}>Linked Service</TableCell>
                                <TableCell>{profile.dataset.linked_service_name}</TableCell>
                              </TableRow>
                            )}
                            {profile.dataset.source_system_type && (
                              <TableRow>
                                <TableCell sx={{ fontWeight: 600 }}>Source System</TableCell>
                                <TableCell>{profile.dataset.source_system_type}</TableCell>
                              </TableRow>
                            )}
                            <TableRow>
                              <TableCell sx={{ fontWeight: 600 }}>Row Count</TableCell>
                              <TableCell>
                                {(() => {
                                  const count = profile.dataset.row_count ?? profile.python_result?.row_count ?? profile.python_result?.summary?.row_count;
                                  return count != null ? Number(count).toLocaleString() : "N/A";
                                })()}
                              </TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell sx={{ fontWeight: 600 }}>Column Count</TableCell>
                              <TableCell>
                                {profile.dataset.column_count || profile.python_result?.column_count || profile.python_result?.columns_scanned || (profile.columns?.length || 0)}
                              </TableCell>
                            </TableRow>
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </Box>

                    {/* Technical Discovery & Schema */}
                    {(() => {
                      let tables = [];
                      let sourceKind = 'table';
                      try {
                        const pj = profile.dataset.profiling_json ? JSON.parse(profile.dataset.profiling_json) : null;
                        const discoveryContext = pj?.profile?.summary?.technical_context || pj?.profile?.summary || pj;
                        
                        // Priority 1: python_result from the last quality scan
                        if (profile.python_result?.table_info) {
                           const ti = profile.python_result.table_info;
                           tables = [{
                             table_name:   ti.table_name,
                             schema:       ti.schema,
                             column_count: ti.column_count,
                             columns:      ti.columns,
                             primary_keys: ti.primary_keys,
                             foreign_keys: ti.foreign_keys
                           }];
                           sourceKind = discoveryContext?.source_kind || 'table';
                        } 
                        // Priority 2: initial discovery context
                        else if (discoveryContext?.tables) {
                          tables = discoveryContext.tables;
                          sourceKind = discoveryContext.source_kind || 'table';
                        }
                      } catch (e) {
                        console.error("Error parsing profiling metadata", e);
                      }

                      if (tables.length === 0) return null;

                      return (
                        <Box sx={{ mb: 3 }}>
                          <Typography
                            variant="subtitle2"
                            sx={{
                              fontWeight: 700,
                              mb: 1,
                              display: "flex",
                              alignItems: "center",
                              gap: 1,
                            }}
                          >
                            <span role="img" aria-label="discovery">
                              🔎
                            </span>{" "}
                            Technical Discovery & Schema
                          </Typography>
                          {tables.map((table, tidx) => {
                            const pkSet = new Set(table.primary_keys || []);
                            const fkMap = new Map((table.foreign_keys || []).map(f => [f.column, f]));

                            return (
                              <Box key={tidx} sx={{ mb: 2 }}>
                                <Paper variant="outlined" sx={{ p: 2, bgcolor: 'grey.50' }}>
                                  <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
                                    <Box>
                                      <Typography variant="body2" sx={{ fontWeight: 700, color: 'primary.main' }}>
                                        {table.table_name}
                                      </Typography>
                                      <Typography variant="caption" color="text.secondary">
                                        Schema: {table.schema || 'N/A'} · Source Kind: {sourceKind}
                                      </Typography>
                                    </Box>
                                    <Chip 
                                      label={`${table.column_count || table.columns?.length || 0} Columns`} 
                                      size="small" 
                                      sx={{ fontWeight: 600, bgcolor: 'white' }} 
                                    />
                                  </Stack>

                                  <TableContainer component={Paper} sx={{ maxHeight: 300, boxShadow: 'none', border: '1px solid', borderColor: 'divider' }}>
                                    <Table size="small" stickyHeader>
                                      <TableHead>
                                        <TableRow>
                                          <TableCell sx={{ fontWeight: 700, bgcolor: 'white', fontSize: '0.75rem' }}>Column Name</TableCell>
                                          <TableCell sx={{ fontWeight: 700, bgcolor: 'white', fontSize: '0.75rem' }}>Data Type</TableCell>
                                          <TableCell sx={{ fontWeight: 700, bgcolor: 'white', fontSize: '0.75rem' }}>Keys</TableCell>
                                        </TableRow>
                                      </TableHead>
                                      <TableBody>
                                        {(table.columns || []).map((col, cidx) => {
                                          const isPk = pkSet.has(col.name) || col.is_pk;
                                          const fk = fkMap.get(col.name);
                                          
                                          return (
                                            <TableRow key={cidx} hover>
                                              <TableCell sx={{ fontSize: '0.75rem', py: 0.5, fontFamily: 'monospace' }}>
                                                {col.name}
                                              </TableCell>
                                              <TableCell sx={{ fontSize: '0.7rem', py: 0.5 }}>
                                                <Chip 
                                                  label={col.type} 
                                                  size="small" 
                                                  variant="outlined" 
                                                  sx={{ height: 18, fontSize: '0.6rem', color: 'text.secondary' }} 
                                                />
                                              </TableCell>
                                              <TableCell sx={{ py: 0.5 }}>
                                                <Stack direction="row" spacing={0.5}>
                                                  {isPk && (
                                                    <Chip label="PK" size="small" color="primary" sx={{ height: 16, fontSize: '0.6rem', fontWeight: 800 }} />
                                                  )}
                                                  {fk && (
                                                    <Tooltip title={`References ${fk.ref_table}(${fk.ref_column})`}>
                                                      <Chip label="FK" size="small" color="secondary" sx={{ height: 16, fontSize: '0.6rem', fontWeight: 800 }} />
                                                    </Tooltip>
                                                  )}
                                                </Stack>
                                              </TableCell>
                                            </TableRow>
                                          );
                                        })}
                                      </TableBody>
                                    </Table>
                                  </TableContainer>

                                  {(table.foreign_keys && table.foreign_keys.length > 0) && (
                                    <Box sx={{ mt: 2 }}>
                                      <Typography variant="caption" sx={{ fontWeight: 700, mb: 0.5, display: 'block' }}>
                                        Foreign Key Constraints
                                      </Typography>
                                      <Stack direction="row" spacing={1} flexWrap="wrap">
                                        {table.foreign_keys.map((f, fidx) => (
                                          <Chip 
                                            key={fidx}
                                            label={`${f.column} ➔ ${f.ref_table}(${f.ref_column})`}
                                            size="small"
                                            variant="outlined"
                                            sx={{ fontSize: '0.65rem', bgcolor: 'white' }}
                                          />
                                        ))}
                                      </Stack>
                                    </Box>
                                  )}
                                </Paper>
                              </Box>
                            );
                          })}
                        </Box>
                      );
                    })()}

                    {/* Intelligence Sections */}
                    <Stack spacing={3}>
                      {isPipeline && python.run_details?.length > 0 && (
                        <Box>
                          <Typography
                            variant="subtitle2"
                            sx={{
                              fontWeight: 700,
                              mb: 1,
                              color: "error.main",
                              display: "flex",
                              alignItems: "center",
                              gap: 1,
                            }}
                          >
                            <span role="img" aria-label="history">
                              📜
                            </span>{" "}
                            Pipeline Execution History
                          </Typography>
                          <TableContainer
                            component={Paper}
                            variant="outlined"
                            sx={{ mb: 2, maxHeight: 400, overflow: "auto" }}
                          >
                            <Table size="small" stickyHeader>
                              <TableHead>
                                <TableRow>
                                  <TableCell
                                    sx={{
                                      fontWeight: 700,
                                      bgcolor: "grey.100",
                                    }}
                                  >
                                    Status
                                  </TableCell>
                                  <TableCell
                                    sx={{
                                      fontWeight: 700,
                                      bgcolor: "grey.100",
                                    }}
                                  >
                                    Run Start
                                  </TableCell>
                                  <TableCell
                                    sx={{
                                      fontWeight: 700,
                                      bgcolor: "grey.100",
                                    }}
                                  >
                                    Duration
                                  </TableCell>
                                  <TableCell
                                    sx={{
                                      fontWeight: 700,
                                      bgcolor: "grey.100",
                                    }}
                                  >
                                    Reason/Solution
                                  </TableCell>
                                </TableRow>
                              </TableHead>
                              <TableBody>
                                {python.run_details.map((run, idx) => (
                                  <TableRow key={idx} hover>
                                    <TableCell>
                                      <Chip
                                        label={run.status}
                                        size="small"
                                        color={
                                          run.status === "SUCCESS"
                                            ? "success"
                                            : run.status === "FAILED"
                                              ? "error"
                                              : "warning"
                                        }
                                        sx={{
                                          fontWeight: 600,
                                          height: 20,
                                          fontSize: "0.65rem",
                                        }}
                                      />
                                    </TableCell>
                                    <TableCell sx={{ fontSize: "0.75rem" }}>
                                      {run.run_start
                                        ? new Date(
                                            run.run_start,
                                          ).toLocaleString()
                                        : "-"}
                                    </TableCell>
                                    <TableCell sx={{ fontSize: "0.75rem" }}>
                                      {run.duration_minutes
                                        ? `${run.duration_minutes}m`
                                        : "-"}
                                    </TableCell>
                                    <TableCell>
                                      {run.status === "FAILED" && (
                                        <Box>
                                          <Typography
                                            variant="caption"
                                            sx={{
                                              color: "error.main",
                                              fontWeight: 600,
                                              display: "block",
                                            }}
                                          >
                                            {run.failure_reason}
                                          </Typography>
                                          {run.recommended_solution && (
                                            <Typography
                                              variant="caption"
                                              sx={{
                                                color: "primary.main",
                                                fontStyle: "italic",
                                              }}
                                            >
                                              Fix: {run.recommended_solution}
                                            </Typography>
                                          )}
                                        </Box>
                                      )}
                                      {run.status === "SUCCESS" && (
                                        <Typography
                                          variant="caption"
                                          color="text.secondary"
                                        >
                                          Success
                                        </Typography>
                                      )}
                                    </TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </TableContainer>
                        </Box>
                      )}

                      {python.pipeline_meta?.activities?.length > 0 && (
                        <Box>
                          <Typography
                            variant="subtitle2"
                            sx={{
                              fontWeight: 700,
                              mb: 1,
                              display: "flex",
                              alignItems: "center",
                              gap: 1,
                            }}
                          >
                            <span role="img" aria-label="activities">
                              ⚡
                            </span>{" "}
                            Pipeline Activities
                          </Typography>
                          <Box
                            sx={{
                              p: 2,
                              bgcolor: "grey.50",
                              borderRadius: 1,
                              border: "1px solid",
                              borderColor: "divider",
                            }}
                          >
                            <Stack
                              direction="row"
                              flexWrap="wrap"
                              spacing={1}
                              useFlexGap
                            >
                              {python.pipeline_meta.activities.map(
                                (act, idx) => (
                                  <Chip
                                    key={idx}
                                    label={`${act.name} (${act.type})`}
                                    size="small"
                                    variant="outlined"
                                    sx={{ bgcolor: "white" }}
                                  />
                                ),
                              )}
                            </Stack>
                          </Box>
                        </Box>
                      )}

                      <Box>
                        <Typography
                          variant="subtitle2"
                          sx={{ fontWeight: 700, mb: 1 }}
                        >
                          Contextual Insights
                        </Typography>
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          sx={{
                            p: 2,
                            bgcolor: "grey.50",
                            borderRadius: 1,
                            border: "1px solid",
                            borderColor: "divider",
                          }}
                        >
                          {python.contextual_summary ||
                            llm.contextual_summary ||
                            "No contextual insights available."}
                        </Typography>
                      </Box>

                      <Box>
                        <Typography
                          variant="subtitle2"
                          sx={{ fontWeight: 700, mb: 1 }}
                        >
                          Baseline & Anomalies
                        </Typography>
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          sx={{
                            p: 2,
                            bgcolor: "grey.50",
                            borderRadius: 1,
                            border: "1px solid",
                            borderColor: "divider",
                          }}
                        >
                          {python.differences ||
                            llm.differences ||
                            "This is the first recorded run; no baseline exists."}
                        </Typography>
                      </Box>

                      {llm.pii_inspection && (
                        <Box>
                          <Typography
                            variant="subtitle2"
                            sx={{ fontWeight: 700, mb: 1 }}
                          >
                            PII Data Inspection
                          </Typography>
                          <Typography
                            variant="body2"
                            color="text.secondary"
                            sx={{
                              p: 2,
                              bgcolor: "grey.50",
                              borderRadius: 1,
                              border: "1px solid",
                              borderColor: "divider",
                            }}
                          >
                            {llm.pii_inspection}
                          </Typography>
                        </Box>
                      )}

                      {(llm.recommendations?.length > 0 ||
                        python.findings?.length > 0) && (
                        <Box>
                          <Typography
                            variant="subtitle2"
                            sx={{
                              fontWeight: 700,
                              mb: 1,
                              color: "primary.main",
                            }}
                          >
                            Actionable Recommendations
                          </Typography>
                          <Box
                            sx={{
                              p: 2,
                              bgcolor: "primary.50",
                              borderRadius: 1,
                              border: "1px solid",
                              borderColor: "primary.100",
                            }}
                          >
                            <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
                              {(llm.recommendations || [])
                                .concat(python.findings || [])
                                .map((rec, idx) => (
                                  <li key={idx}>
                                    <Typography
                                      variant="body2"
                                      color="text.primary"
                                      sx={{ fontWeight: 500 }}
                                    >
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
