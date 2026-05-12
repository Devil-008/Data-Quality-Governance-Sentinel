import React from 'react';
import {
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Paper, Chip, Box, Typography, IconButton, Tooltip,
} from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';

export const SEVERITY_COLOR = {
  critical: 'error',
  high: 'warning',
  medium: 'warning',
  low: 'info',
  info: 'default',
};

export const STATUS_COLOR = {
  open: 'error',
  acknowledged: 'warning',
  resolved: 'success',
};

const formatDate = (val) => {
  if (!val) return '-';
  try {
    return new Date(val).toLocaleString();
  } catch (e) {
    return val;
  }
};

const AlertTable = ({ alerts = [], onRowClick, dense = false, hideSource = false }) => {
  if (!alerts || alerts.length === 0) {
    return (
      <Box sx={{ p: 4, textAlign: 'center' }}>
        <Typography color="text.secondary">No alerts to display.</Typography>
      </Box>
    );
  }

  return (
    <TableContainer component={Paper} sx={{ boxShadow: 'none', border: '1px solid', borderColor: 'divider' }}>
      <Table size={dense ? 'small' : 'medium'}>
        <TableHead>
          <TableRow>
            <TableCell><strong>Severity</strong></TableCell>
            <TableCell><strong>Category</strong></TableCell>
            <TableCell><strong>Title</strong></TableCell>
            {!hideSource && <TableCell><strong>Source</strong></TableCell>}
            <TableCell><strong>Status</strong></TableCell>
            <TableCell><strong>Created</strong></TableCell>
            <TableCell align="right"><strong>Action</strong></TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {alerts.map((a) => (
            <TableRow key={a.id} hover sx={{ cursor: onRowClick ? 'pointer' : 'default' }}>
              <TableCell>
                <Chip
                  label={(a.severity || '').toUpperCase()}
                  color={SEVERITY_COLOR[a.severity] || 'default'}
                  size="small"
                />
              </TableCell>
              <TableCell>
                <Chip label={a.category || '-'} variant="outlined" size="small" />
              </TableCell>
              <TableCell>
                <Typography variant="body2" sx={{ fontWeight: 500 }}>
                  {a.title || '-'}
                </Typography>
              </TableCell>
              {!hideSource && (
                <TableCell>
                  <Typography variant="caption" color="text.secondary">
                    {a.connector_name || a.dataset_name || '-'}
                  </Typography>
                </TableCell>
              )}
              <TableCell>
                <Chip
                  label={a.status || 'open'}
                  color={STATUS_COLOR[a.status] || 'default'}
                  size="small"
                  variant="outlined"
                />
              </TableCell>
              <TableCell>
                <Typography variant="caption">{formatDate(a.created_at)}</Typography>
              </TableCell>
              <TableCell align="right">
                <Tooltip title="View Details">
                  <IconButton size="small" onClick={() => onRowClick && onRowClick(a)}>
                    <VisibilityIcon fontSize="small" />
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

export default AlertTable;
