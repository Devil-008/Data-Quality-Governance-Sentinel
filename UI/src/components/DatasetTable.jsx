import React from 'react';
import {
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Paper, Chip, Box, Typography, IconButton, Tooltip,
} from '@mui/material';
import StorageIcon from '@mui/icons-material/Storage';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';

const DatasetTable = ({ datasets = [], onRowClick }) => {
  if (!datasets || datasets.length === 0) {
    return (
      <Box sx={{ p: 4, textAlign: 'center' }}>
        <StorageIcon sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
        <Typography color="text.secondary">
          No datasets discovered yet. Create a connector and run a scan to populate datasets.
        </Typography>
      </Box>
    );
  }

  return (
    <TableContainer component={Paper} sx={{ boxShadow: 'none', border: '1px solid', borderColor: 'divider' }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell><strong>Name</strong></TableCell>
            <TableCell><strong>Connector</strong></TableCell>
            <TableCell><strong>Schema</strong></TableCell>
            <TableCell><strong>Type</strong></TableCell>
            <TableCell><strong>Columns</strong></TableCell>
            <TableCell><strong>Row Count</strong></TableCell>
            <TableCell><strong>Quality</strong></TableCell>
            <TableCell><strong>PII</strong></TableCell>
            <TableCell align="right"><strong>Action</strong></TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {datasets.map((d) => (
            <TableRow key={d.id} hover sx={{ cursor: onRowClick ? 'pointer' : 'default' }}>
              <TableCell>
                <Typography variant="body2" sx={{ fontWeight: 500 }}>
                  {d.dataset_name}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="caption" color="text.secondary">
                  {d.connector_name || '-'}
                </Typography>
              </TableCell>
              <TableCell>{d.schema_name || '-'}</TableCell>
              <TableCell>
                <Chip label={d.dataset_type || 'table'} size="small" variant="outlined" />
              </TableCell>
              <TableCell>{d.column_count ?? '-'}</TableCell>
              <TableCell>{d.row_count != null && d.row_count >= 0 ? d.row_count : '-'}</TableCell>
              <TableCell>
                {d.quality_score != null ? (
                  <Chip
                    label={`${d.quality_score}%`}
                    size="small"
                    color={d.quality_score >= 90 ? 'success' : d.quality_score >= 70 ? 'warning' : 'error'}
                  />
                ) : (
                  '-'
                )}
              </TableCell>
              <TableCell>
                {d.contains_pii ? (
                  <Chip label="PII" size="small" color="error" />
                ) : (
                  <Chip label="None" size="small" variant="outlined" />
                )}
              </TableCell>
              <TableCell align="right">
                <Tooltip title="View Profile">
                  <IconButton size="small" onClick={() => onRowClick && onRowClick(d)}>
                    <OpenInNewIcon fontSize="small" />
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
