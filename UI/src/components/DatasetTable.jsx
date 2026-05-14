import React from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Box,
  Typography,
  IconButton,
  Tooltip,
  TableSortLabel,
} from "@mui/material";
import StorageIcon from "@mui/icons-material/Storage";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import PsychologyIcon from "@mui/icons-material/Psychology";
import LightbulbIcon from "@mui/icons-material/Lightbulb";

import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import UnfoldMoreIcon from "@mui/icons-material/UnfoldMore";

const DatasetTable = ({ datasets = [], onRowClick, sortConfig, onSort }) => {
  if (!datasets || datasets.length === 0) {
    return (
      <Box sx={{ p: 4, textAlign: "center" }}>
        <StorageIcon sx={{ fontSize: 48, color: "text.disabled", mb: 1 }} />
        <Typography color="text.secondary">
          No datasets discovered yet. Create a connector and run a scan to
          populate datasets.
        </Typography>
      </Box>
    );
  }

  return (
    <TableContainer
      component={Paper}
      sx={{ boxShadow: "none", border: "1px solid", borderColor: "divider" }}
    >
      <Table size="small">
        <TableHead>
          <TableRow sx={{ bgcolor: "grey.100" }}>
            <TableCell>
              <strong>Name</strong>
            </TableCell>
            <TableCell
              onClick={() => onSort && onSort("connector_name")}
              sx={{
                cursor: "pointer",
                userSelect: "none",
                whiteSpace: "nowrap",
              }}
            >
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                <strong>Connector</strong>
                {sortConfig?.key !== "connector_name" ? (
                  <UnfoldMoreIcon
                    fontSize="small"
                    sx={{ color: "text.disabled" }}
                  />
                ) : sortConfig.direction === "asc" ? (
                  <KeyboardArrowUpIcon fontSize="small" color="primary" />
                ) : (
                  <KeyboardArrowDownIcon fontSize="small" color="primary" />
                )}
              </Box>
            </TableCell>
            <TableCell>
              <strong>Schema</strong>
            </TableCell>
            <TableCell>
              <strong>Type</strong>
            </TableCell>
            <TableCell>
              <strong>Outlier</strong>
            </TableCell>
            <TableCell>
              <strong>Confident (%)</strong>
            </TableCell>
            <TableCell>
              <strong>PII</strong>
            </TableCell>
            <TableCell align="right">
              <strong>Deep Thinking</strong>
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {datasets.map((d) => (
            <TableRow
              key={d.id}
              hover
              sx={{
                cursor: onRowClick ? "pointer" : "default",
                borderBottom: "1px solid secondary.main",
              }}
            >
              <TableCell>
                <Typography variant="body2" sx={{ fontWeight: 500 }}>
                  {d.dataset_name}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="caption" color="text.secondary">
                  {d.connector_name || "-"}
                </Typography>
              </TableCell>
              <TableCell>{d.schema_name || "-"}</TableCell>
              <TableCell>
                <Chip
                  label={d.dataset_type || "table"}
                  size="small"
                  variant="outlined"
                />
              </TableCell>
              {/* <TableCell>{d.outlier_count != null ? d.outlier_count : "-"}</TableCell> */}
              <TableCell>
                {d.outlier_count != null ? (
                  <Box sx={{ minWidth: 120 }}>
                    {/* <Typography
                      variant="caption"
                      sx={{
                        fontWeight: 700,
                        color:
                          d.outlier_count > 80
                            ? "error.main"
                            : d.outlier_count > 40
                              ? "warning.main"
                              : "success.main",
                      }}
                    >
                      {d.outlier_count}
                    </Typography> */}

                    <Box
                      sx={{
                        mt: 0.5,
                        height: 6,
                        borderRadius: 5,
                        bgcolor: "action.hover",
                        overflow: "hidden",
                      }}
                    >
                      <Box
                        sx={{
                          width: `${Math.min(d.outlier_count, 100)}%`,
                          height: "100%",
                          borderRadius: 5,
                          bgcolor:
                            d.outlier_count > 80
                              ? "error.main"
                              : d.outlier_count > 40
                                ? "warning.main"
                                : "success.main",
                        }}
                      />
                    </Box>
                  </Box>
                ) : (
                  "-"
                )}
              </TableCell>
              <TableCell>
                {d.confidence_score != null ? `${d.confidence_score}` : "-"}
              </TableCell>

              <TableCell>
                {d.pii_percentage != null ? (
                  d.pii_percentage > 0 ? (
                    <Chip
                      label={`PII (${d.pii_percentage}%)`}
                      size="small"
                      color="error"
                    />
                  ) : (
                    <Chip label="None" size="small" variant="outlined" />
                  )
                ) : d.contains_pii === true ? (
                  <Chip label="PII" size="small" color="error" />
                ) : d.contains_pii === false ? (
                  <Chip label="None" size="small" variant="outlined" />
                ) : null}
              </TableCell>
              <TableCell align="right">
                <Tooltip title="View Profile">
                  <IconButton
                    size="small"
                    onClick={() => onRowClick && onRowClick(d)}
                  >
                    {/* <OpenInNewIcon fontSize="small" />
                    <PsychologyIcon fontSize="small" /> */}
                    <LightbulbIcon
                      fontSize="small"
                      sx={{
                        color: "#f59e0b",
                      }}
                    />
                  </IconButton>
                </Tooltip>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
};

export default DatasetTable;
