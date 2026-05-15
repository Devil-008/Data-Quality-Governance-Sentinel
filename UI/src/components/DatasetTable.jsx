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
} from "@mui/material";
import StorageIcon from "@mui/icons-material/Storage";
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

  // Shared header cell style
  const headerCellSx = {
    fontSize: "0.875rem",       // 14px — clearly larger than default small
    fontWeight: 700,
    color: "text.primary",
    letterSpacing: "0.02em",
    py: 1.5,
    whiteSpace: "nowrap",
  };

  // Shared body cell style
  const bodyCellSx = {
    fontSize: "0.9125rem",
    fontWeight: 600,
    py: 1.25,
  };

  return (
    <TableContainer
      component={Paper}
      sx={{ boxShadow: "none", border: "1px solid", borderColor: "divider" }}
    >
      <Table size="small">
        <TableHead>
          <TableRow sx={{ bgcolor: "grey.100" }}>
            {/* Name */}
            <TableCell sx={headerCellSx}>Name</TableCell>

            {/* Connector — sortable */}
            <TableCell
              sx={{ ...headerCellSx, cursor: "pointer", userSelect: "none" }}
              onClick={() => onSort && onSort("connector_name")}
            >
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                Connector
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

            <TableCell sx={headerCellSx}>Schema</TableCell>
            <TableCell sx={headerCellSx}>Type</TableCell>
            <TableCell sx={headerCellSx}>Outliers</TableCell>
            <TableCell sx={headerCellSx}>Confident (%)</TableCell>
            <TableCell sx={headerCellSx}>PII</TableCell>
            <TableCell sx={{ ...headerCellSx, textAlign: "right" }}>
              Deep Thinking
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
                "&:last-child td": { borderBottom: 0 },
              }}
            >
              {/* Name */}
              <TableCell sx={bodyCellSx}>
                <Typography
                  variant="body2"
                  sx={{ fontWeight: 600, fontSize: "0.9125rem" }}
                >
                  {d.dataset_name}
                </Typography>
              </TableCell>

              {/* Connector */}
              <TableCell sx={bodyCellSx}>
                <Typography sx={{ fontWeight: 600, fontSize: "0.9125rem" }}>
                  {d.connector_name || "-"}
                </Typography>
              </TableCell>

              {/* Schema */}
              <TableCell sx={bodyCellSx}>
                <Typography sx={{ fontWeight: 600, fontSize: "0.9125rem" }}>
                  {d.schema_name || "-"}
                </Typography>
              </TableCell>

              {/* Type */}
              <TableCell sx={bodyCellSx}>
                <Chip
                  label={d.dataset_type || "table"}
                  size="small"
                  variant="outlined"
                  sx={{ fontSize: "0.75rem", fontWeight: 500 }}
                />
              </TableCell>

              {/* Outliers */}
              <TableCell sx={bodyCellSx}>
                {d.outlier_count != null ? (
                  (() => {
                    const count = d.outlier_count;
                    let color = "#2e7d32"; // Green
                    let progress = 0;
                    if (count > 10) {
                      color = "#d32f2f"; // Red
                      progress = 100;
                    } else if (count > 0) {
                      color = "#ed6c02"; // Amber
                      progress = 50;
                    }
                    return (
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
                        <Typography sx={{ fontWeight: 700, fontSize: "0.875rem", color: color, minWidth: 20 }}>
                          {count}
                        </Typography>
                        <Box sx={{ height: 6, width: 40, bgcolor: "grey.200", borderRadius: 3, overflow: "hidden", display: { xs: 'none', sm: 'block' } }}>
                          <Box sx={{ height: "100%", width: `${progress}%`, bgcolor: color }} />
                        </Box>
                      </Box>
                    );
                  })()
                ) : (
                  "-"
                )}
              </TableCell>

              {/* Confident (%) */}
              <TableCell sx={bodyCellSx}>
                {d.confidence_score != null ? (
                  (() => {
                    const score = Math.round(d.confidence_score);
                    let color = "#2e7d32"; // Green
                    if (score < 70) color = "#d32f2f"; // Red
                    else if (score < 90) color = "#ed6c02"; // Amber

                    return (
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
                        <Typography sx={{ fontWeight: 700, fontSize: "0.875rem", color: color, minWidth: 30 }}>
                          {score}
                        </Typography>
                        <Box sx={{ height: 6, width: 60, bgcolor: "grey.200", borderRadius: 3, overflow: "hidden", display: { xs: 'none', sm: 'block' } }}>
                          <Box sx={{ height: "100%", width: `${score}%`, bgcolor: color }} />
                        </Box>
                      </Box>
                    );
                  })()
                ) : (
                  "-"
                )}
              </TableCell>

              {/* PII */}
              <TableCell sx={bodyCellSx}>
                {d.pii_percentage != null ? (
                  d.pii_percentage > 0 ? (
                    <Chip
                      label={`PII (${d.pii_percentage}%)`}
                      size="small"
                      color="error"
                      sx={{ fontSize: "0.75rem", fontWeight: 600 }}
                    />
                  ) : (
                    <Chip
                      label="None"
                      size="small"
                      variant="outlined"
                      sx={{ fontSize: "0.75rem" }}
                    />
                  )
                ) : d.contains_pii === true ? (
                  <Chip
                    label="PII"
                    size="small"
                    color="error"
                    sx={{ fontSize: "0.75rem", fontWeight: 600 }}
                  />
                ) : d.contains_pii === false ? (
                  <Chip
                    label="None"
                    size="small"
                    variant="outlined"
                    sx={{ fontSize: "0.75rem" }}
                  />
                ) : null}
              </TableCell>

              {/* Deep Thinking */}
              <TableCell align="right" sx={bodyCellSx}>
                <Tooltip title="View Profile">
                  <IconButton
                    size="small"
                    onClick={() => onRowClick && onRowClick(d)}
                  >
                    <LightbulbIcon
                      fontSize="small"
                      sx={{ color: "#f59e0b" }}
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